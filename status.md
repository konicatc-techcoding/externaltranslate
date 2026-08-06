# ExternalTranslate — Stage 2 交接狀態 (status.md)

> 本文件供後續 model／agent 快速接手。最後更新：2026-08-03。
> 閱讀本檔前，請先重讀 `AGENTS.md`、`BUILD.md`、`PLAN.md` 與
> `.hermes/plans/2026-08-02-stage-2-gemini-live.md`。

---

## 1. 專案定錨

| 項目 | 值 |
|---|---|
| 專案根目錄 | `C:\Users\razer\Documents\HermesWorkspace\ExternalTranslate` |
| Branch / remote | `main` → `origin/main` (`github.com/konicatc-techcoding/externaltranslate.git`) |
| 已發布 HEAD | `b0a0a6a059536bac4313bc8b4a861012ce52f141` (`feat(audio): add input and WASAPI loopback capture`) |
| Python | 3.11，套件管理 `uv`；Windows Git Bash |
| 關鍵執行規則 | 所有 Python／uv 指令必須 `PYTHONPATH=''` |

### 完成並已發布
- **Stage 0**：骨架、依賴盤點、安全邊界。
- **Stage 1**：Windows input capture、meter、16 kHz mono PCM16、100 ms chunk、bounded drop-oldest queue。
- **Stage 1.2**：WASAPI loopback、render endpoint 列舉、stereo downmix、source XOR、真實硬體驗收、commit + push。

### Stage 2（進行中）
官方 `google-genai` Gemini Live Translate adapter、provider-neutral events、安全 CLI、外層長期 AudioSource／內層 session supervisor。**尚未驗收、尚未 commit、尚未 push。**

---

## 2. PCM 合約（硬性不變）

```text
sample_rate    = 16000
channels       = 1
sample_width   = 2
encoding       = signed PCM16 little-endian
chunk_duration = 100 ms
bytes_per_chunk = 3200
```

Source invariant（Stage 1.2 沿用）：

```text
INPUT_DEVICE XOR WASAPI_LOOPBACK   （不得混音／同時持有兩種 source）
```

---

## 3. Stage 2 已實作並驗證通過的部分

- 官方 `google-genai>=2.16,<3` async Live API，使用 `LiveConnectConfig` + `input_audio_transcription` + `output_audio_transcription` + `translation_config(target_language_code="zh-Hant")`。
- `GeminiLiveSession.send_audio()`：SDK send 前強制 3,200-byte PCM contract，`audio/pcm;rate=16000` Blob。
- `receive_events()`：跨多個 model turn 持續 receive；mapping interim／final input/output transcription；丟棄 translated audio；`GoAway` 對映為 provider-neutral control event。
- Session supervisor：
  - AudioSource 在整個 pipeline **只 start 一次、只 stop 一次**。
  - **唯一 persistent PCM reader** 位於 Gemini sessions 外層，經容量 1 的 drop-oldest async handoff 供當前 session sender 消費（rotation 不會建立第二個 `get_pcm_chunk()` consumer）。
  - 預設 480 秒主動 rotation；`GoAway` 提前換線；retryable connect／send／receive／EOF 受控重連。
  - Backoff：`0.5 → 1 → 2 → 4 → 5 → 5…` 秒上限。
  - Permanent auth／permission／configuration／policy 錯誤 fail closed。
  - Timer 與 error／GoAway 共用單一 replacement ownership path；同 tick race 只產生一個 replacement。
  - Session task／client／source cleanup 皆嘗試；cleanup failure 與 primary/cancellation 狀態以 safe 訊息組合呈現。
  - 不使用 session resumption（刻意決策）。
  - 同一 logical event sink 跨 session 持續，不清除字幕狀態。
- Provider-originated raw SDK／client exception 已與 `__cause__`／`__context__` 脫鉤（send/receive connect 邊界），不經 traceback 洩漏 raw detail。
- CLI `externaltranslate-gemini-smoke`：
  - 無 `--api-key`；key 只能來自 environment／hidden prompt；本機安全取得。
  - 預設只輸出 metadata；`--show-text` 才顯示文字。
  - Smoke 成功條件：收到 **非空、`finished=true`、`language_code=zh-Hant`** 的 output transcription；僅 connect 成功／partial／英文不符。
- Config：strict closed Gemini schema；`session_rotation_seconds` 預設 480、範圍 60–540，由 production CLI 接入 supervisor。

### 最新驗證結果（fresh）
| Gate | 結果 |
|---|---:|
| `PYTHONPATH='' uv run pytest -W error -q` | **167 passed** |
| `uv run ruff check backend` | 通過 |
| `uv run mypy backend/app` | 31 source files，無問題 |
| `npm run test` | 1 passed |
| `npm run build` | 通過 |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| `uv lock --check` / `uv pip check` | 通過 |
| `git diff --check` | 通過 |

---

## 4. ⚠️ 待辦（接手者下一步——依此繼續）

**狀態：第三輪 independent fail-closed review（deleg_031e460b）已 **PASSED**：
`{"passed": true, "security_concerns": [], "logic_errors": [], "suggestions": [...]}`。**
全部前幾輪 findings 已驗證解決（直接檢查 + 真實例外 shape 重現，非僅信實作測試）。`__close_client`（BaseException + 雙 close + sanitize）、WebSocket 分類、`connect()` 手動 context 管理（session-exit+primary/cancellation 結合、suppress_context 切斷）皆通過。

### 第二輪 review 修正摘要（已完成，TDD）
1. **`_close_client()`**：改為 catch `BaseException`（含 `CancelledError`）並 sanitize 成 `TranslationProviderError`；無論 `aclose()` 結果為何，都會嘗試 async `aclose()` **且** sync `close()`。
2. **WebSocket send／handshake 分類**：新增 `_is_retryable_websocket_transport()`（使用真實 `websockets` 例外型別）：
   - `ConnectionClosed` → 異常關閉/1011-1014 retry（code != 1000）。
   - `InvalidStatus` → HTTP 408/409/425/429 與 5xx retry；401/403 permanent。
   - `google-genai` `APIError` 分類維持不變。
3. **`connect().__aexit__` 併發失敗**：改用**手動管理 SDK context**（`__aenter__/__aexit__` 分開 capture），把 session-exit 失敗與 primary/cancellation 分開記錄；結合時以 safe 訊息回報（保留 primary 的 retryable、`from None` 切斷 chain、不洩漏 raw detail），且 client cleanup 仍會嘗試。
   - 註：`from None` 使 `__suppress_context__=True`，因此即使 sanitized primary 殘留在 `__context__`，rendered traceback 也不含 raw/secret（有測試驗證 `traceback.format_exception` 無 secret）。

### 修正後新增/更新 tests
- `backend/tests/translation/test_gemini_websocket_classification.py`（新增）：真實 `ConnectionClosedError` 於 send/receive 判 retryable；`InvalidStatus` 429/503/408 retryable、403/401 permanent。
- `backend/tests/translation/test_gemini_adapter.py`（更新/新增）：`aclose()` CancelledError 仍嘗試 sync close；`__aexit__` 失敗 + primary 結合回報；既有 detach/preserve tests 維持。

### 最新驗證結果（fresh，修正後）
| Gate | 結果 |
|---|---:|
| `PYTHONPATH='' uv run pytest -W error -q` | **177 passed** |
| `uv run ruff check backend` | 通過 |
| `uv run mypy backend/app` | 31 source files，無問題 |
| `npm run test` / `npm run build` | 通過 / 通過 |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| `uv lock --check` / `uv pip check` / `git diff --check` | 通過 |

### 真實 Gemini smoke 結果（2026-08-06）
- **Capture 正常**：loopback 實測 10 s → 100 chunks、320,000 bytes、RMS −10.5 dBFS、peak −5.6 dBFS、0 drop、restart 通過。
- **Gemini 全鏈路正常**：`--show-text` 診斷顯示 input 英文轉錄 + output 中文翻譯都有收到。
- **原始失敗原因**：連續語音下 Gemini Live Translate 只送 `finished=false` 的即時字幕，smoke 原先要求 `finished=true` 故誤判失敗。
- **處理**（使用者拍板「放寬」）：smoke 驗收改為**接受非空 `zh-Hant` output（含 interim）**，仍拒絕空白與非中文。TDD 後 `test_gemini_smoke_acceptance.py` 更新。
- **✅ 最終真實 smoke 通過（2026-08-06）**：
  `{"status": "ok", "summary": {"input_transcription_events": 23, "output_transcription_events": 22, "finished_output_events": 0}}`
  （無 `--show-text` 故不印文字；`finished=0` 為連續語音之預期行為。）

### 尚未完成（阻塞驗收）
- [x] 第三輪 independent fail-closed review（deleg_031e460b）通過。
- [x] **真實 Gemini Live smoke** 通過（input 23 / output 22）。
- [x] 使用者驗收通過（2026-08-06），授權 commit + push。
- [x] **Stage 2 已 commit + push**：`28a4120`（`b0a0a6a..28a4120 main -> main`，35 files，+4047/−7）。

---

## 6. 真實 Gemini smoke 操作指引

API key **不得**貼進聊天、command line、YAML、Git、log 或 fixture。若 process environment 無 `GEMINI_API_KEY`，CLI 以 hidden prompt 安全詢問。

Looopback（建議用 dynamic default resolution，不固定 index）：
```bash
PYTHONPATH='' .venv/Scripts/externaltranslate-gemini-smoke.exe \
  --source-kind wasapi_loopback --duration 30
```
Input device：
```bash
PYTHONPATH='' .venv/Scripts/externaltranslate-gemini-smoke.exe \
  --source-kind input_device --device-index "<ENUM_INDEX>" --channel 1 --duration 30
```
Smoke 前先列舉（index 可能因重開機／插拔改變）：
```bash
PYTHONPATH='' .venv/Scripts/externaltranslate-loopback-devices.exe
PYTHONPATH='' .venv/Scripts/externaltranslate-audio-devices.exe
```

---

## 7. Credential 與安全原則（不可違反）

- API key 一律記為 `[REDACTED]`；不得寫入本檔或任何 committed/Git 檔案。
- 真實錄音、WAV、PCM、raw audio、transcript、credential、裝置識別資料不得 commit。
- Config 採 strict closed schema；未知／未 wiring 欄位 fail closed。
- 不得修改系統 PATH、安裝驅動或全域套件。

---

## 8. 接手 checklist（快速恢復工作）

1. `cd C:\Users\razer\Documents\HermesWorkspace\ExternalTranslate`
2. 重讀 `AGENTS.md`、`BUILD.md`、`PLAN.md`、`status.md`、`.hermes/plans/2026-08-02-stage-2-gemini-live.md`。
3. `git status --short --branch` 確認 working tree（目前有多個 Stage 2 未提交檔案）。
4. 從 §4 依序修 blocking 問題（TDD：先 RED 後 GREEN）。
5. 跑 §4.4 的完整 gates。
6. 派新一輪 independent fail-closed review。
7. review 通過後安排真實 smoke，再交使用者驗收與 commit/push 授權。

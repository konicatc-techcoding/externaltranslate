# ExternalTranslate — Stage 3.2 交接狀態 (status.md)

> 本文件供後續 model／agent 快速接手。最後更新：2026-08-09（Stage 3.2 實作與真實 smoke）。
> 閱讀本檔前，請先重讀 `AGENTS.md`、`BUILD.md`、`PLAN.md` 與
> `.hermes/plans/2026-08-09_123446-stage-3-captions.md`、
> `.hermes/plans/2026-08-09_124912-stage-3.2-observability.md`。

---

## 1. 專案定錨

| 項目 | 值 |
|---|---|
| 專案根目錄 | `C:\Users\razer\Documents\HermesWorkspace\ExternalTranslate` |
| Branch / remote | `main` → `origin/main` (`github.com/konicatc-techcoding/externaltranslate.git`) |
| 已發布 HEAD | `6691416`（`docs(status): record Stage 3 acceptance and release`）；Stage 3 實作為前一個 commit `c618fb4`（`feat(captions): …`） |
| Python | 3.11，套件管理 `uv`；Windows Git Bash |
| 關鍵執行規則 | 所有 Python／uv 指令必須 `PYTHONPATH=''`；證實 backend 需 canonical `uv run pytest -W error` |

### 完成並已發布
- **Stage 0**：骨架、依賴盤點、安全邊界。
- **Stage 1**：Windows input capture、meter、16 kHz mono PCM16、100 ms chunk、bounded drop-oldest queue。
- **Stage 1.2**：WASAPI loopback、render endpoint 列舉、stereo downmix、source XOR、真實硬體驗收、commit + push。
- **Stage 2**：官方 `google-genai` Gemini Live Translate、provider-neutral events、安全 CLI、長期 AudioSource／外層 session supervisor；177 tests、3 輪 independent review、真實 Gemini smoke（input 23／output 22），commit + push（`ac5934e`）。
- **Stage 3（已實作＋驗證，已 commit + push `c618fb4`）**：`backend/app/captions/`（models／sanitizer／assembler／store）組裝 canonical `CaptionState`；`caption.max_payload_length` strict schema；**215 passed**、Ruff/Mypy clean、audit 0（已修 `nanoid` patch advisory）。

### Stage 3.2（已實作＋真實 smoke 通過，**尚未 commit**）
計劃檔：`.hermes/plans/2026-08-09_124912-stage-3.2-observability.md`（`.hermes/` 被 `.gitignore` 排除，不入 Git）。

- 新增 `backend/app/status/`（models／store／publisher）：component/state/reason 三個 StrEnum、
  frozen `ComponentStatus`、`RuntimeStatusSnapshot`、memory-only `StatusStore`（store 自己蓋
  monotonic revision，`updated_at` 倒退 fail closed）。
- **Publisher 不接受自由文字**：`detail` 由白名單欄位（generation／reason／attempt／
  delay_seconds／rotation_seconds／text_length）組成，`reason` 只能是列舉值。傳 `text=`／
  `api_key=`／`transcript=` 直接 `StatusError`，逐字稿與 credential 在型別層就進不了 log/payload。
  這比計劃的 `detail: str` 更嚴，是刻意加嚴。
- `TranslationPipeline` 新增選用 `status_publisher`，於 supervisor 路徑（非 audio callback）發布
  audio／provider／session 狀態；發布為 best-effort，publisher 失敗不影響翻譯。
  **`fail_closed` 不會被 teardown 的 `stopped` 覆蓋**。
- CLI 新增 `--status-events`、`--caption-state`；`create_caption_observer()` 以
  `caption_max_payload_length(settings)` 建 assembler，**Stage 3 遺留的「validated 但沒接線」已補齊**。
  caption 狀態發布放在 CLI composition root，`captions` 套件不依賴 `status` 套件（Stage 4 照此接 WebSocket）。

### ⚠️ 真實 smoke 的關鍵發現（2026-08-09）

**1. output transcription 是 delta，不是 cumulative — Stage 3 的核心假設錯誤，已修正。**
實測片段依序為「自然的、」→「真實的對話。」→「我們希望」→「英語感覺很有」…，串接後才是完整句子
（input 側同樣是 delta，帶前導空白）。原 `CaptionAssembler` 用 replace 語意，字幕只會顯示最後一個
片段。已改為 **append**：
- 片段累加；`finished=True` 收尾為 final，下一個片段開新字幕。
- 累積文字超過 `max_payload_length` 時**保留尾端**（`sanitize_caption` 的截斷方向也一併改為保留尾端），
  否則連續語音會在上限處凍結不再更新。
- delta 語意下無法以「文字相同」去重（相同片段是新語音），原 dedup 規則移除；空字串／純空白仍忽略。

**2. `finished=true` 一次都沒出現**（`finished_output_events: 0`，23 筆 output 全為 interim）。
字幕實務上會一直停在 partial，只有 session 邊界才會收束。句尾標點是否應該升級為 final 屬產品決策，
留給 Stage 3.1 一併處理（見下方待決）。

**3. `caption_sink` 的 `session_generation` 永遠是 0。**
`backend/app/translation/gemini_live.py` 只在 GoAway 時送 `SESSION_EXPIRING`，**從不送
`SESSION_STARTED`／`SESSION_STOPPED`**，所以 assembler 的 generation 永遠不遞增。rotation 時仍會靠
`SESSION_EXPIRING` 清掉未確認 partial，功能不受影響，但 Stage 4 UI 想用 generation 辨識換線就會失效。
建議修法：由 adapter 在 session 建立／結束時送出對應事件（會動到 Stage 2 已通過 review 的程式與其測試）。
**尚未實作，待使用者決定放 Stage 3.2 或 Stage 4。**

### 修正後的確認 smoke（2026-08-09，第二次真實執行）
指令：`--source-kind wasapi_loopback --duration 30 --status-events --caption-state --show-text`
（loopback，英文連續語音；逐字稿內容不記錄於本檔）。

- `{"status": "ok", "summary": {"input_transcription_events": 27, "output_transcription_events": 27, "finished_output_events": 0}}`
- **append 修正成立**：caption `text_length` 由 7 單調累積到 118，`revision` 1→27，
  且**每一筆的長度增量都等於該筆 output fragment 的長度**（27/27 完全吻合），
  代表沒有漏接、沒有重複累加、也沒有插入多餘字元。
- caption `revision` 27 = output 事件數 27，每筆 output 都造成一次可見變化。
- Status 序列完整且 revision 1→36 單調：
  `audio starting→running`、`provider connecting(attempt=1)→connected(generation=1)`、
  `session active(generation=1 rotation_seconds=480.0)`、`caption_sink active(reason=partial)`×27、
  收尾 `session stopped→provider stopped→audio stopping→stopped`，皆為 metadata，無文字外洩。
- `finished_output_events` 仍為 0，`caption_sink` 的 `generation` 仍為 0——與上述發現 2、3 一致，
  已分別延到 Stage 3.1 與 Stage 4。

### Stage 3.1（已實作，2026-08-10）
計劃檔：`.hermes/plans/2026-08-10_105311-stage-3.1-caption-formatter.md`

- `backend/app/captions/formatter.py`：`display_width()`（CJK／全形 2 欄、其餘 1 欄，
  `Ambiguous` 固定 1）與 `wrap_caption()`（中文標點禁則、拉丁字詞不硬拆、滑動視窗）。
- `CaptionState.lines`：顯示視窗；`text` 仍是 canonical 累積尾端。**斷行由後端統一產生**，
  overlay 與 Stage 5 的 GT Title 渲染同一份。
- `caption.chars_per_line`（4–60，預設 20）與 `caption.max_lines`（1–10，預設 2）。
- `PUT /api/settings/caption-layout`：**執行中可用**（音訊來源仍 409），assembler 立即重排、
  revision +1 讓 WebSocket 推播。
- 控制頁「字幕顯示範圍」面板；`/overlay?lines=N` 降級為本頁顯示行數的覆寫。
- **斷行以 code point 為單位，不做 grapheme 分群**（使用者決議）；限制已寫入 formatter
  docstring 與 README。

實測：面板 20/2 → 送出 6/5 即時生效（無需重整）、999 被 422 拒絕且生效值不變。
**待使用者確認**：中英數混排的實際效果（使用者表示情況少見，有問題再回報）。

### ⏳ 待辦：v0.1 驗收剩餘項目（使用者有空時執行）

`BUILD.md` 驗收標準之一「模擬網路錯誤與裝置錯誤不會使程式無預期結束」尚未實測，
目前是 v0.1 的 blocker。使用者已表示有空時進行（2026-08-10）。

- [ ] **斷網測試**：翻譯執行中中斷網路數秒後恢復。預期：`gemini_provider` 進入 `backoff`
      並顯示 attempt／delay，恢復後重新 `connected`；服務不崩潰，錯誤訊息為繁體中文。
- [ ] **裝置錯誤測試**：翻譯執行中停用或拔除正在使用的音訊裝置。預期：`audio_source`
      轉為 `error`，pipeline 安全停止，UI 顯示可行動的繁體中文訊息，之後仍可重新 Start。
- [ ] 兩項結果補進 `docs/reports/v0.1-verification.md` §5（目前標為 C｜未驗證）。

### 已決議（2026-08-10，字幕版面）
- **vMix 會同時使用 GT Title 與 Browser Input** → **Stage 3.1 升級為 Stage 5 的硬前置條件**。
  GT Title 是文字欄位、沒有瀏覽器可排版，必須由後端送出已切好行的文字；且兩個畫面必須共用
  同一份 `CaptionState.lines`，否則換行位置不一致。
- **顯示範圍以「每行字數 × 行數」定義**（例如每行 10 字 2 行、每行 6 字 5 行），字數以全形寬
  計算（CJK 一格、ASCII 半格）。實作為 `caption.chars_per_line` 與 `caption.max_lines`。
- **控制頁要能直接調整這兩個值**並即時生效；設定為單一真實來源，`/overlay` 的 query param
  僅作單一實例的臨時覆寫。
- **不先做 CSS `em` 的近似版**：只有純中文準確，且會與 Stage 3.1 的正式行為並存造成混淆。
  v0.1 維持現有的 `lines`（視覺行數）。
- 以上皆已寫入 `PLAN.md` 的 Stage 3.1 與 Stage 5。

### 已決議（2026-08-09，使用者拍板）
- **發現 3（adapter 補送 session 事件）→ 延到 Stage 4**，已記入 `PLAN.md` Stage 4 的
  「從 Stage 3.2 帶入的待辦」。理由：現在功能不受影響，且會動到 Stage 2 已過 review 的 adapter，
  等 UI 真正需要 generation 時連同需求一起設計。
- **發現 2（句尾標點升級 final）→ 延到 Stage 3.1**，已記入 `PLAN.md` Stage 3.1 能力清單。
  理由：斷句規則要看到實際 overlay 才決定得準。Stage 3.2 維持只有 `finished=true` 與 session
  邊界會收束字幕。

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
3. `git status --short --branch` 確認 working tree（目前 clean，`main` 與 `origin/main` 同步於 `6691416`）。
4. 從 §4 依序修 blocking 問題（TDD：先 RED 後 GREEN）。
5. 跑 §4.4 的完整 gates。
6. 派新一輪 independent fail-closed review。
7. review 通過後安排真實 smoke，再交使用者驗收與 commit/push 授權。

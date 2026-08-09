# ExternalTranslate Staged Development Plan

> **For Hermes:** Implement this plan one stage at a time. Read `AGENTS.md`, `BUILD.md`, and this file before changing code. Stop after every stage, run the stage's real verification, report results in Traditional Chinese, and wait for explicit user approval before continuing.

**Goal:** 以底層優先、垂直切片的方式，逐步完成 Windows 外部音訊擷取、Gemini Live Translate 繁體中文字幕、本機控制與 Overlay、vMix 整合，以及最終 Windows 安裝程式。

**Architecture:** 先建立最小 Python/React 骨架，再依序打通 audio capture、PCM pipeline、Gemini、caption state、WebSocket 和最小 UI。每個階段都必須產生可執行、可測試的增量，不先製作完整視覺 UI，也不在底層尚未驗證前宣稱整合完成。

**Tech Stack:** Python 3.11、FastAPI、WebSocket、`google-genai`、PortAudio/`sounddevice`、React、TypeScript、pywebview、PyInstaller onedir、Inno Setup、pytest、Vitest、Playwright。

---

## 1. 文件分工

- `AGENTS.md`：不可違反的開發、安全、驗證與溝通規則。
- `BUILD.md`：產品架構、打包策略、版本範圍與驗收標準。
- `PLAN.md`：實際執行順序、每個 Stage 的檔案、測試、CLI smoke test 和停止點。

若三份文件有衝突：

1. 先停止實作。
2. 用繁體中文列出衝突位置與影響。
3. 由使用者決定要修改哪份文件。
4. 不自行猜測或默默選擇其中一個版本。

## 2. 開發節奏

每個 Stage 固定採用：

```text
Prerequisite check
→ Read current implementation
→ Write failing tests
→ Minimal implementation
→ Unit/integration tests
→ Real CLI/application smoke test
→ Regression check
→ Traditional Chinese stage report
→ STOP and wait for approval
```

每份階段報告必須包含：

- 新增與修改的檔案。
- 新增的功能。
- 未包含的功能。
- 實際執行的命令。
- 測試通過、失敗與略過數量。
- 真實硬體、Gemini 或 vMix 驗證結果。
- 尚未安裝的外部程式或驅動。
- 下一個 Stage，但不得自行開始。

## 3. 版本與 Stage 對應

| Release | Stage | 能力 |
|---|---:|---|
| v0.1 | 0–4、1.2 | 專案骨架、環境檢查、可切換的實體輸入／WASAPI loopback、Gemini、字幕狀態、最小控制與預覽 UI |
| v0.2 | 3.1、4.1 | Unicode 行寬、多行字幕、完整樣式與 Overlay 穩定化 |
| v0.3 | 5 | vMix API、GT Title、Browser Input、更新節流與恢復 |
| v0.4 | 1.1 | ASIO 實機支援與更多 Audio Interface 診斷 |
| v0.5 | 6 | pywebview、PyInstaller onedir、Inno Setup、升級/解除安裝 |
| v1.0 | 6.1 | 完整 prerequisite matrix、soak test、正式操作文件與安裝版 |

主 Stage 代表新的管線能力；既有能力的修正、邊界情況與強化使用子 Stage，例如 `1.1`、`3.1`、`6.1`。

---

# v0.1 執行計畫

## Stage 0：專案骨架、依賴盤點與安全邊界

### 目標

建立可重現的 Python/React 開發骨架、測試入口、繁體中文 prerequisite model，以及 API key/configuration 邊界。這一階段不擷取音訊、不呼叫 Gemini。

### Stage 0 prerequisite gate

先檢查但不要擅自安裝：

- Windows 10/11 64-bit。
- Python 3.11 與建立虛擬環境的能力。
- Node.js 20.19+ 或 22.12+ 與 npm（符合目前 Vite 8 toolchain）。
- Git。
- 可用的 WASAPI/WDM 音訊輸入裝置與驅動。
- 選定 Audio Interface 是否要求 ASIO。
- vMix 是否已安裝與版本；v0.1 不使用，但記錄供 Stage 5 使用。
- FFmpeg 是否已安裝；v0.1 不需要，必須明確標示為非必要。

若必要項目缺少，先向使用者說明用途、建議版本、影響、安裝和驗證方法，取得同意後才能安裝系統級程式或修改 PATH。

### 預計檔案

```text
Create: pyproject.toml
Create: package.json
Create: .gitignore
Create: .env.example
Create: README.md
Create: config/default.yaml
Create: backend/app/__init__.py
Create: backend/app/config.py
Create: backend/app/prerequisites/models.py
Create: backend/app/prerequisites/checker.py
Create: backend/app/security/credentials.py
Create: backend/tests/prerequisites/test_checker.py
Create: backend/tests/security/test_credentials.py
Create: frontend/package.json
Create: frontend/tsconfig.json
Create: frontend/vite.config.ts
Create: frontend/src/main.tsx
Create: frontend/src/types/status.ts
Create: frontend/src/i18n/zh-TW.ts
Create: frontend/src/App.tsx
Create: frontend/src/App.test.tsx
```

實作時若工具生成不同的必要骨架檔案，先在 Stage 報告中列出；不得加入與 Stage 0 無關的框架。

### 任務順序

1. 建立 Python package、pytest、lint 和 type-check 最小設定。
2. 執行空測試套件，確認測試入口可運行。
3. 建立 React/TypeScript strict mode、Vitest 與 production build。
4. 建立繁體中文最小 UI shell，只顯示產品名稱與「尚未檢查環境」。
5. 建立 typed prerequisite result model。
6. 以測試先行建立 Python、Node/npm、OS 和 feature dependency 狀態檢查。
7. 建立 API key credential protocol；v0.1 預設 memory-only，Windows Credential Manager 實作邊界可先以明確未設定狀態存在，但不能假裝已保存。
8. 建立 config priority：runtime override → user config → project default。
9. 建立 `.gitignore`，排除 secrets、logs、recordings、transcripts、cache、build 和 coverage。
10. 撰寫繁體中文 README，列出目前可執行的真實命令。

### 自動驗證

```text
python -m pytest backend/tests -v
python -m ruff check backend
python -m mypy backend/app
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

命令名稱可依實際 scaffold 工具微調，但必須固定寫入 README 和 Stage 報告。

### CLI smoke test

執行 prerequisite checker，輸出繁體中文 JSON 或表格，至少辨識：

- OS/architecture
- Python
- Node/npm
- FFmpeg 非必要狀態
- vMix 條件必要狀態
- 音訊檢查尚未執行

### Stage 0 完成條件

- Backend 和 frontend 可在全新 checkout 依 README 啟動測試。
- 缺少 prerequisite 時提供繁體中文可操作訊息。
- 沒有任何 Gemini key 出現在 repository 或測試輸出。
- Frontend production build 成功。
- 停止，提交 Stage 0 報告，等待使用者批准 Stage 1。

---

## Stage 1：Windows 音訊裝置、Capture、Meter 與 PCM Pipeline

### 目標

使用真實 Windows microphone/audio interface 完成裝置列舉、channel 選擇、非阻塞 capture、meter、PCM conversion 與 bounded queue，並建立可替換的 `AudioSource` 邊界。這一階段只實作 `INPUT_DEVICE`，不呼叫 Gemini。

### Stage 1 prerequisite gate

- 確認 `sounddevice`/PortAudio 的安裝來源與 Windows wheel/native dependency。
- 確認至少一個真實 input device 可使用。
- 若選定裝置需要 ASIO，先報告；除非 v0.1 硬體無法以 WASAPI/WDM 使用，ASIO adapter 留到 Stage 1.1。
- 不把虛擬音訊測試宣稱為真實 Audio Interface 驗證。

### 預計檔案

```text
Create: backend/app/audio/models.py
Create: backend/app/audio/devices.py
Create: backend/app/audio/capture.py
Create: backend/app/audio/sources/__init__.py
Create: backend/app/audio/sources/base.py
Create: backend/app/audio/sources/input_device.py
Create: backend/app/audio/meter.py
Create: backend/app/audio/converter.py
Create: backend/app/audio/queue.py
Create: backend/app/cli/audio_devices.py
Create: backend/app/cli/audio_smoke.py
Create: backend/tests/audio/test_devices.py
Create: backend/tests/audio/test_capture.py
Create: backend/tests/audio/test_meter.py
Create: backend/tests/audio/test_converter.py
Create: backend/tests/audio/test_queue.py
Modify: backend/app/prerequisites/checker.py
Modify: README.md
```

### 任務順序

1. 定義 `AudioSourceKind.INPUT_DEVICE`／`WASAPI_LOOPBACK`、`AudioSource` protocol、`AudioDeviceInfo`、`AudioFormat` 和 capture lifecycle models；Stage 1 只實作 `INPUT_DEVICE` adapter。
2. 以 fixture/mock 測試裝置欄位正規化，但保留真實 enumeration smoke test。
3. 實作 host API、device、input channel、default sample rate 列舉。
4. 實作 callback-only enqueue，callback 內禁止 network、logging flood 或 blocking I/O。
5. 實作 RMS/peak meter 與 clipping state。
6. 實作任意受支援輸入到官方要求 PCM 的 converter。
7. 實作 bounded queue 和明確 overflow policy；預設丟棄最舊 chunk，避免延遲無限累積。
8. 實作可重複 Start/Stop 的 audio lifecycle。
9. 實作裝置拔除、channel 錯誤和 unsupported sample rate 的繁體中文錯誤。
10. 建立 audio smoke CLI，輸出裝置、meter、chunk count、格式與 queue drop count。

### 自動驗證

```text
python -m pytest backend/tests/audio -v
python -m ruff check backend/app/audio backend/tests/audio
python -m mypy backend/app/audio
```

測試至少涵蓋：

- Mono/stereo/multi-channel 選擇。
- 不同 sample rate。
- PCM16 little-endian。
- 100 ms chunk boundary。
- Queue overflow。
- Start/Stop 重複操作。
- Callback exception isolation。

### 真實 CLI smoke test

- 列出真實音訊裝置。
- 使用使用者選定 device/channel 擷取至少 10 秒。
- 顯示 RMS/peak。
- 預設只在memory中建立短WAV並驗證 header/byte format；只有使用者明確指定輸出路徑時才持久化非敏感測試檔。
- 確認停止後 device handle 釋放，可再次啟動。

### Stage 1 完成條件

- 至少一個真實 Windows input device 通過功能測試。
- 送出格式符合 Gemini 實作當下官方要求。
- Queue 不會無限成長。
- 沒有 Gemini 或 UI 功能被提前加入。
- 停止，提交 Stage 1 報告，等待使用者批准 Stage 1.2。

---

## Stage 1.2：Windows 系統輸出 WASAPI Loopback（2026-08-02 review remediation）

### 目標

新增 `WASAPI_LOOPBACK` 音訊來源，擷取使用者選定 Windows render endpoint 上實際播放的 system mix。`INPUT_DEVICE` 與 `WASAPI_LOOPBACK` 必須二選一；v0.1 不同時擷取、不混音，也不提供 per-process audio capture。

### Stage 1.2 prerequisite gate

- 重新閱讀 Microsoft WASAPI loopback 官方文件：
  - https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording
- 以 throwaway spike 實測並比較 `PyAudioWPatch`、`SoundCard` 與 native WASAPI adapter；標準 `python-sounddevice` 不得在未實測前假設支援 loopback。
- 檢查候選套件的 Python 3.11 Windows x64 wheel、維護狀態、授權、PortAudio/native dependency 與 PyInstaller 相容性。
- 確認至少一個真實 Windows render endpoint，並準備可重複播放的非敏感測試訊號。
- 不修改系統 PATH、不安裝 driver、不啟用 Stereo Mix，也不安裝虛擬 audio cable；若驗證需要系統級變更，先說明並取得使用者批准。

實測選定 `PyAudioWPatch 0.2.12.8`：標準 `sounddevice 0.5.5` 沒有 loopback
device/flag；`SoundCard 0.4.6` direct WASAPI/CFFI可擷取但採 blocking pull，且有已知
Windows channel/blocksize/underrun限制；`PyAudioWPatch` 的 callback與 loopback virtual
endpoint最符合既有 non-blocking architecture。兩個候選皆以真實 Windows render endpoint
及440 Hz訊號驗證，未修改driver、PATH、Stereo Mix或virtual cable。
Packaging metadata確認：`PyAudioWPatch` 為 Apache-2.0並提供 CPython 3.11 Windows x64
wheel（內含patched PortAudio）；`SoundCard` 為 BSD-3-Clause、`py3-none-any` wheel並依賴
CFFI/native WASAPI。PyInstaller `onedir` native-library收集仍屬Stage 6實機gate，本階段不
以source-mode import/capture取代packaged smoke。

### 來源與生命週期規則

- `INPUT_DEVICE` 與 `WASAPI_LOOPBACK` 共用 meter、converter、100 ms chunker 和 bounded queue。
- UI／CLI 可選指定 render endpoint；「Windows default output」只在 Start 時解析成實際 endpoint。
- capture 期間 default output 若改變，v0.1 不做無縫遷移；停止目前 stream、提供繁體中文訊息並要求重新啟動。
- 切換 source 前必須停止並釋放目前 stream，不得同時保留兩個 active callback。
- Loopback native format 不可假設；必須從實際 endpoint 取得 sample rate、channel count 與 sample format，再 downmix/resample 為 16 kHz mono PCM16 little-endian。
- Exclusive-mode、endpoint unplug、silence、unsupported format 與 queue overflow 必須回傳可操作錯誤，不得拖垮其他元件。

### 實作檔案

```text
Create: backend/app/audio/sources/wasapi_loopback.py
Create: backend/app/cli/loopback_devices.py
Create: backend/app/cli/loopback_smoke.py
Create: backend/tests/audio/test_wasapi_loopback.py
Create: backend/tests/audio/test_source_controller.py
Modify: backend/app/audio/models.py
Modify: backend/app/audio/capture.py
Modify: backend/app/audio/converter.py
Modify: backend/app/config.py
Modify: config/default.yaml
Modify: pyproject.toml
Modify: README.md
```

### 任務順序

1. 建立隔離的 loopback library comparison spike，輸出裝置清單、native format、10 秒 capture、meter 與資源釋放證據。
2. 根據實測結果選定單一正式 backend，記錄未採用方案及原因。
3. 以 fake adapter 先寫 `WASAPI_LOOPBACK` 枚舉、選擇和 lifecycle failing tests。
4. 實作 render endpoint 與 Windows default output 列舉，不把 output endpoint 假裝成一般 microphone。
5. 實作 non-blocking loopback callback，只將 native frames 放入 bounded handoff。
6. 將 stereo／multi-channel native frames 共用 Stage 1 converter 轉成 16 kHz mono PCM16。
7. 實作 source switching：Stop → release → select → Start；失敗時保留可恢復狀態。
8. 實作 endpoint unplug、default-output change、exclusive-mode failure、silence 與 restart error mapping。
9. 建立 loopback smoke CLI，輸出 source kind、endpoint、native format、meter、chunk count、drop count 與轉換後格式；不得輸出錄音內容。
10. 更新 README 與非敏感 default config；預設 source 保持 `INPUT_DEVICE`，不得未經使用者選擇就擷取系統輸出。
11. 使用strict audio schema與單一production source factory消費validated selection/channel/queue設定；prerequisite依啟用來源區分`not_checked`與`optional`。

### 自動驗證

```text
python -m pytest backend/tests/audio/test_wasapi_loopback.py backend/tests/audio/test_source_switching.py -v
python -m pytest backend/tests/audio -v
python -m ruff check backend/app/audio backend/tests/audio
python -m mypy backend/app/audio
```

測試至少涵蓋：

- `INPUT_DEVICE`／`WASAPI_LOOPBACK` 二選一，拒絕同時 active。
- 指定 render endpoint 與 default-output resolution。
- Stereo／multi-channel downmix、44.1/48 kHz resampling、PCM16 little-endian 與 100 ms chunk。
- 無聲輸出、queue overflow、endpoint unplug、default-output change、重複 Start/Stop 和 source switching。
- Stop/open/close/manager terminate或native status query失敗均保留可重試ownership；
  `active`維持safe boolean API，malformed native payload不可逃出callback。
- Callback 不執行 network I/O 或 blocking work。

### 真實 CLI smoke test

- 在選定 render endpoint 播放已知非敏感測試訊號至少 10 秒。
- 確認 loopback meter 隨播放訊號變化，停止播放後回到 silence threshold。
- 驗證 native format metadata、轉換後 16 kHz mono PCM16、chunk count 與 queue drop count。
- 切換至真實 microphone/audio interface，再切回 loopback；每次確認前一個 device handle 已釋放。
- vMix 不是 Stage 1.2 prerequisite；若用 vMix 產生測試聲音，只驗證其輸出被選定 endpoint 擷取，不啟用 vMix HTTP API 功能。

2026-08-02 非敏感實機結果（裝置名稱與當次index不寫入版本控制）：

- Windows default render endpoint以 native 48 kHz stereo成功開啟；device index於每次測試前重新列舉。
- 正式10秒CLI capture：100個3,200-byte chunks、320,000 PCM bytes、16 kHz mono
  PCM16、160,000 frames、restart verified、callback/status/processing errors皆0、
  raw/PCM queue drops皆0。
- WAV獨立讀回：10.0秒、FFT peak `440.0 Hz`、0 clipped samples；檔案位於 repository外
  Windows Temp，不納入Git。
- 真實 source switch：WASAPI input endpoint → default loopback（讀取3,200-byte PCM
  chunk）→同一input endpoint；最後沒有 active source。

### Stage 1.2 完成條件

- 至少一個真實 Windows render endpoint 通過 loopback 功能測試。
- 使用者可在 `INPUT_DEVICE` 與 `WASAPI_LOOPBACK` 間切換，但不能同時擷取或混音。
- 兩種來源輸出相同的 downstream PCM contract，且共用 bounded queue。
- Audio config未知或未接線欄位fail closed；所有已知selection/channel/queue欄位有production consumer。
- 裝置失效或 library/backend 問題有繁體中文可操作訊息，不以 mock 宣稱 loopback 可用。
- 停止，提交 Stage 1.2 報告，等待使用者批准 Stage 2。

---

## Stage 2：Gemini Live Translate CLI Integration

### 目標

在沒有完整 UI 的情況下，打通真實音訊 → Gemini Live Translate → `zh-Hant` output transcription 的核心管線。

### Stage 2 prerequisite gate

- 重新閱讀官方文件：
  - https://ai.google.dev/gemini-api/docs/live-api/live-translate
- 記錄當下模型名稱、SDK 版本、audio format、chunk 建議、事件結構、session 限制與 `zh-Hant` 支援。
- 使用者自行提供 Gemini API key；在測試前才要求輸入，不要求使用者在聊天或 repository 內貼出 key。
- 驗證 key 只存在程序記憶體或 Windows Credential Manager，不出現在 command history、URL 或 log。

### 預計檔案

```text
Create: backend/app/translation/base.py
Create: backend/app/translation/models.py
Create: backend/app/translation/gemini_live.py
Create: backend/app/services/translation_pipeline.py
Create: backend/app/cli/gemini_smoke.py
Create: backend/tests/translation/test_gemini_adapter.py
Create: backend/tests/services/test_translation_pipeline.py
Modify: config/default.yaml
Modify: .env.example
Modify: README.md
```

### 任務順序

1. 定義 provider-neutral `TranslationProvider` protocol。
2. 定義 input/output/error/session events。
3. 以 fake provider 寫 pipeline failing tests。
4. 實作 audio sender 和 event receiver 為獨立 async tasks。
5. 依官方文件實作 Gemini Live adapter，不猜測 Preview API。
6. 將模型名稱與 `target_language_code=zh-Hant` 放在設定。
7. 實作 timeout、取消、正常關閉和 error mapping。
8. 將AudioSource lifecycle置於Gemini session supervisor外層；capture只start一次。
9. 每480秒主動建立新session，收到GoAway時提前換線，不使用session resumption。
10. connect/send/receive/EOF暫時性錯誤採`0.5 → 1 → 2 → 4 → 5秒上限`
    bounded backoff；authentication/permission/configuration錯誤fail closed。
11. Timer與error共用單一replacement ownership path；舊session完成cleanup後才建立下一個，
    不得產生duplicate sender或無界PCM backlog。
12. 實作 bounded audio handoff，Gemini變慢或重連時不阻塞capture callback。
13. 建立真實 Gemini smoke CLI。
14. 驗證日誌和例外不包含 API key或完整敏感逐字稿。

### 自動驗證

```text
python -m pytest backend/tests/translation backend/tests/services -v
python -m ruff check backend/app/translation backend/app/services
python -m mypy backend/app/translation backend/app/services
```

Fake provider 只用於可重現的錯誤與 lifecycle 測試；不能取代真實 Gemini smoke test。

### 真實 CLI smoke test

```text
使用者選定的 INPUT_DEVICE 或 WASAPI_LOOPBACK
→ Stage 1／1.2 PCM pipeline
→ Gemini Live Translate
→ Terminal 顯示 input/output transcription metadata
```

必須驗證：

- Session 可建立。
- `INPUT_DEVICE` 與 `WASAPI_LOOPBACK` 各完成至少一次真實 Gemini smoke test；若外部權限或硬體造成阻塞，必須精確列出未驗證來源。
- 真實語音產生繁體中文 output transcription。
- Start/Stop 可重複。
- 無語音、網路斷線、無效 key 和 API error 都有繁體中文訊息。
- 停止後所有 async task、audio stream 和 Gemini session 都結束。
- 使用縮短的test rotation interval驗證replacement session；production default維持480秒。
- Connect/send/receive/EOF/GoAway後可受控重連，且AudioSource不重啟。
- Permanent authentication/permission錯誤不重試，transient retry沒有tight loop。

### Stage 2 完成條件

- 真實音訊到 `zh-Hant` 文字的底層管線通過。
- 若 API key、帳務、地區或 Preview 權限阻塞，精確報告 blocker，不得用 mock 宣稱完成。
- 尚未製作完整 UI。
- 停止，提交 Stage 2 報告，等待使用者批准 Stage 3。

---

## Stage 3：Transcript Assembler 與 Canonical CaptionState

### 目標

將 Gemini 實際回傳事件整理為穩定、可測試、與 UI/vMix 解耦的 canonical caption state。

### 預計檔案

```text
Create: backend/app/captions/models.py
Create: backend/app/captions/assembler.py
Create: backend/app/captions/sanitizer.py
Create: backend/app/captions/store.py
Create: backend/tests/captions/test_assembler.py
Create: backend/tests/captions/test_sanitizer.py
Create: backend/tests/captions/test_store.py
Modify: backend/app/services/translation_pipeline.py
```

### 任務順序

1. 根據 Stage 2 真實事件確認事件是 delta 或 cumulative；不得先假設。
2. 建立包含 `revision`、`text`、`partial`、`status`、`updated_at` 的 `CaptionState`。
3. 實作 partial/final 合併與去重。
4. 實作 out-of-order/repeated event 防護。
5. 實作 session 重連時清除未確認 partial、保留必要 final state。
6. 實作 configurable maximum payload length。
7. 預設只保存記憶體狀態，不寫 transcript 檔案。
8. 將 pipeline 輸出改成 canonical state。

### 自動驗證

```text
python -m pytest backend/tests/captions backend/tests/services -v
python -m ruff check backend/app/captions backend/tests/captions
python -m mypy backend/app/captions
```

至少測試：

- Delta event。
- Cumulative event。
- 重複 partial。
- Final replacement。
- 空字串。
- 中文、英文、數字與 emoji。
- Oversized payload。
- Session reset。

### CLI smoke test

執行 Stage 2 真實管線，但輸出 `CaptionState` revision/status，而不是直接輸出原始 Gemini event。確認字幕不重複、不倒退且停止後 state 合理。

### Stage 3 完成條件

- UI 和未來 vMix 不需要理解 Gemini 原始事件。
- Canonical state 有完整單元測試。
- 完整 Unicode 行寬、多行滑動與樣式保留到 Stage 3.1（v0.2）。
- 停止，提交 Stage 3 報告，等待使用者批准 Stage 4。

---

## Stage 4：FastAPI/WebSocket 與最小繁體中文 UI

### 目標

把已驗證的底層能力接到可操作的最小 UI，完成 v0.1。UI 只做必要控制和真實字幕預覽，不先製作完整設計系統或 vMix 頁面。

### 預計檔案

```text
Create: backend/app/main.py
Create: backend/app/api/routes/status.py
Create: backend/app/api/routes/settings.py
Create: backend/app/api/routes/pipeline.py
Create: backend/app/api/routes/credentials.py
Create: backend/app/api/websocket.py
Create: backend/tests/api/test_status.py
Create: backend/tests/api/test_credentials.py
Create: backend/tests/api/test_pipeline.py
Create: backend/tests/api/test_websocket.py
Create: frontend/src/api/client.ts
Create: frontend/src/api/websocket.ts
Create: frontend/src/types/caption.ts
Create: frontend/src/components/PrerequisitePanel.tsx
Create: frontend/src/components/ApiKeyField.tsx
Create: frontend/src/components/AudioDeviceSelector.tsx
Create: frontend/src/components/AudioMeter.tsx
Create: frontend/src/components/CaptionPreview.tsx
Create: frontend/src/pages/ControlPage.tsx
Create: frontend/src/pages/OverlayPage.tsx
Create: frontend/src/styles/base.css
Create: frontend/src/**/*.test.tsx
Modify: frontend/src/App.tsx
Modify: README.md
```

### 任務順序

1. 建立只監聽 `127.0.0.1` 的 FastAPI application factory。
2. 建立 typed status/settings/pipeline endpoints。
3. 建立 API key submit/test/clear endpoints；完整 key 不得回傳。
4. 建立 caption WebSocket，加入 payload validation 和 connection lifecycle。
5. 建立 prerequisite panel。
6. 建立遮罩 API key 欄位、顯示/隱藏、測試、清除與保存選項。
7. 建立真實 audio device/channel selector。
8. 建立 meter 與 Start/Stop 控制。
9. 建立只使用文字節點的 CaptionPreview。
10. 建立最小 `/overlay`，支援基本字型、大小、字色與背景色。
11. 建立 UI 狀態：idle、checking、ready、listening、translating、stopping、error。
12. 建立 WebSocket reconnect 和 stale state 顯示。
13. 執行 backend/frontend 及真實端到端驗證。

### 安全驗證

- UI/HTML/JavaScript bundle 不含真實 API key。
- Key 不在 localStorage、sessionStorage、URL、WebSocket 或 log。
- 字幕不使用 `innerHTML`。
- Oversized caption 被安全拒絕或截斷。
- 非 loopback host 預設無法啟動控制服務。
- 所有 request model 有 backend validation。

### 自動驗證

```text
python -m pytest backend/tests -v
python -m ruff check backend
python -m mypy backend/app
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

如 Stage 4 引入 Playwright：

```text
npm --prefix frontend run test:e2e
```

### 真實應用 smoke test

1. 啟動 backend 和 frontend。
2. 開啟繁體中文控制頁。
3. 執行 prerequisite check。
4. 在 UI 輸入使用者提供的 Gemini API key 並測試。
5. 選擇真實 microphone/audio interface 和 channel。
6. Start 後確認 meter、Gemini status 和繁體中文字幕更新。
7. 開啟 `/overlay`，確認與控制頁使用同一份 `CaptionState`。
8. Stop 後確認 audio/Gemini/WebSocket lifecycle 正常。
9. 再次 Start，確認沒有殘留 handle 或 task。
10. 模擬斷網與裝置錯誤，確認繁體中文錯誤且應用程式不崩潰。

### Stage 4 / v0.1 完成條件

- `BUILD.md` 的 v0.1 驗收標準全部有實際結果。
- 所有 v0.1 必要 prerequisites 已完成版本與功能驗證。
- 真實語音可在本機 UI 顯示 `zh-Hant` 字幕。
- Backend、frontend tests、lint、type check 和 production build 全部通過。
- 產出 `docs/reports/v0.1-verification.md`，列出硬體、驅動、SDK、模型、命令和實際結果。
- 停止，不自行進入 v0.2。

---

# v0.2：字幕與 Overlay 強化

## Stage 3.1：Unicode Caption Formatting Refinement

### 能力

- Unicode display width。
- 中文標點優先斷句。
- 最大行數與最大行寬。
- 滑動窗口。
- partial/final 樣式區分。
- 中英文、emoji、combining character 測試。

### 預計檔案

```text
Create: backend/app/captions/formatter.py
Create: backend/tests/captions/test_formatter.py
Modify: backend/app/captions/models.py
Modify: backend/app/captions/store.py
```

## Stage 4.1：Overlay Style Refinement

### 能力

- 字型、大小、粗細、文字色。
- 描邊、陰影、背景色、透明度、padding、圓角。
- 對齊、最大行數、行寬。
- 斷線保留與淡出。
- Overlay screenshot/Playwright 視覺與尺寸驗證。

完成 v0.2 後停止，等待 Stage 5 批准。

---

# v0.3：vMix Integration

## Stage 5：vMix HTTP API、GT Title 與 Browser Input

### 能力

- vMix 安裝、執行狀態與 Web API prerequisite check。
- `GET /api/` XML state discovery。
- Input GUID/name 和 `Subtitle.Text` 驗證。
- `SetText` 的 `Value`、`Input`、`SelectedName` 正確 encoding。
- 更新去重與每秒最大更新次數。
- Timeout、HTTP 500、vMix offline 和 reconnect。
- Browser Input overlay URL 與顯示/隱藏控制。
- vMix failure 不影響 web overlay。

### 預計檔案

```text
Create: backend/app/outputs/base.py
Create: backend/app/outputs/vmix.py
Create: backend/tests/outputs/test_vmix.py
Create: frontend/src/components/VmixSettings.tsx
Create: frontend/src/components/VmixStatus.tsx
Modify: backend/app/prerequisites/checker.py
Modify: backend/app/services/translation_pipeline.py
Modify: frontend/src/pages/ControlPage.tsx
```

必須以真實 vMix 執行 API smoke test；mock HTTP 只能補充錯誤測試。

---

# v0.4：Audio Interface/ASIO Refinement

## Stage 1.1：ASIO 與硬體診斷

只有在實際硬體和驅動需求確認後才決定 adapter。必須先告知使用者：

- 原廠驅動名稱與版本。
- 安裝影響與是否需重新啟動。
- PortAudio build 是否具 ASIO 能力。
- 授權或再散布限制。
- 實際 device/channel 驗證程序。

不得只因系統中出現 ASIO driver 名稱就宣稱支援。

---

# v0.5：Windows Packaging

## Stage 6：pywebview、PyInstaller onedir 與 Inno Setup

### 能力

- pywebview desktop shell。
- 單一 instance guard。
- Loopback backend lifecycle。
- React static assets 嵌入。
- `%LOCALAPPDATA%\ExternalTranslate` 設定/log/cache 位置。
- PyInstaller onedir build。
- Inno Setup installer。
- 安裝、升級、解除安裝。
- 安裝後 prerequisite health check。
- End-user 不需安裝 Python 或 Node.js。

### 預計檔案

```text
Create: backend/app/desktop.py
Create: packaging/externaltranslate.spec
Create: packaging/installer.iss
Create: scripts/build_frontend.py
Create: scripts/build_windows.py
Create: scripts/verify_install.py
Create: backend/tests/test_resource_paths.py
Create: docs/windows-installation.md
Modify: pyproject.toml
Modify: README.md
```

先完成 onedir smoke test，再建立 installer；不直接跳到 onefile。

---

# v1.0：Release Hardening

## Stage 6.1：正式發行驗證

- 全新 Windows VM 安裝測試。
- 所有必要 runtime、driver、external program 的版本與功能驗證。
- 連續運行 soak test。
- 網路中斷、裝置拔除、Gemini session 重建、vMix 重啟。
- CPU、memory、queue depth 和 latency 長時間觀察。
- 安裝、升級、修復、解除安裝。
- API key 清除與 Credential Manager 清理。
- 正式支援矩陣和繁體中文操作手冊。

只有所有啟用功能與必要 prerequisites 都在真實環境通過，才能標示 v1.0。

---

## 4. 目前下一步

Stage 0、Stage 1、Stage 1.2 與 Stage 2 已完成並通過驗證與發布：

- **Stage 0**：專案骨架、依賴盤點與安全邊界。
- **Stage 1**：`INPUT_DEVICE` adapter、Windows input 列舉、non-blocking callback handoff、
  RMS/peak meter、streaming resample 至 16 kHz mono PCM16 little-endian、固定 100 ms chunk、
  bounded drop-oldest queue、繁體中文錯誤與可重複 Start/Stop；真實 WASAPI input 實機 smoke 通過。
- **Stage 1.2**：`WASAPI_LOOPBACK` render endpoint 列舉、default-output resolution、
  多聲道 downmix、`INPUT_DEVICE XOR WASAPI_LOOPBACK` atomic source switch；真實 loopback
  10 秒實機（100 chunks／320,000 bytes／440 Hz）與 source-switch smoke 通過。
- **Stage 2**：官方 `google-genai` Gemini Live Translate adapter、permanent AudioSource 外層的
  session supervisor（480 秒 rotation、GoAway、bounded backoff、fail-closed、唯一 persistent
  PCM reader）、安全 smoke CLI；177 tests、3 輪 independent review 通過、真實 Gemini smoke
  （input 23 / output 22）通過，已 commit + push（`ac5934e`）。
- **Stage 3（已實作，待 review/commit）**：`backend/app/captions/`（models／sanitizer／
  assembler／store），把 `TranslationEvent` 組裝成 canonical `CaptionState`（partial/final、
  去重、empty、session reset 保留 final）。config 新增 `caption.max_payload_length` strict
  schema。全量 **215 passed**、Ruff/Mypy clean、audit 0（已修 `nanoid` patch advisory）。

下一個可執行工作是 **Stage 3.2：Runtime Component Status & Observability**。已在
`.hermes/plans/2026-08-09_124912-stage-3.2-observability.md` 有細部計劃，提供元件狀態與
structured log（Gemini 連線/session/rotation）。通過 review 後由 supervisor 發布並以 CLI
`--status-events` 顯示。此 Stage 純為字幕組裝，不需 API key 或硬體。

```text
Stage 3（完成待 review）→ Stage 3.2 Observability
```

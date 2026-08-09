# ExternalTranslate

ExternalTranslate 是 Windows 本機優先的即時翻譯字幕應用程式。專案可從麥克風／Audio Interface 或 Windows 系統播放輸出擷取音訊，透過 Gemini Live Translate 產生繁體中文字幕，並在後續 Stage 輸出到網頁 Overlay 與 vMix。

## 目前狀態

目前完成：

- **Stage 0**：專案骨架、依賴盤點與安全邊界。
- **Stage 1**：Windows input-device 列舉、capture、meter、16 kHz mono PCM16
  轉換、100 ms chunk、bounded queue 與重複 Start/Stop。
- **Stage 1.2**：Windows WASAPI system-output loopback、render endpoint列舉、
  stereo downmix、default-output resolution、source XOR與真實Start/Stop/switch。
- **Stage 2**：官方`google-genai` Live Translate adapter、provider-neutral
  transcription events、安全CLI，以及持續AudioSource外層的Gemini session supervisor。
  Automated tests已涵蓋8分鐘主動rotation、GoAway換線、錯誤分類與bounded backoff；
  真實Gemini smoke已通過並完成驗收。
- **Stage 3**：`backend/app/captions/`（models／sanitizer／assembler／store）把
  provider-neutral `TranslationEvent` 組裝成canonical `CaptionState`（partial/final、
  空白處理、session reset保留final），並新增`caption.max_payload_length` strict schema。
  Gemini Live的output transcription為**增量片段**，assembler會累加片段；累積文字超過
  `caption.max_payload_length`時保留最新的尾端，不會停在上限。
- **Stage 3.2（驗證中）**：`backend/app/status/`（models／store／publisher）提供runtime元件
  狀態與sanitized structured log，session supervisor在連線、rotation、backoff與fail-closed
  時發布狀態；CLI新增`--status-events`與`--caption-state`。真實Gemini smoke尚未完成前，
  不視為Stage 3.2驗收通過。

目前不會：

- 啟動 FastAPI/WebSocket。
- 連線 vMix。
- 安裝或修改任何系統驅動、PATH 或全域套件。

## 必要環境

### Stage 0–1.2 必要

- Windows 10/11 64-bit
- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ 或 22.12+ 與 npm（符合目前 Vite 8 工具鏈要求）
- Git for Windows
- 可用的 WASAPI/WDM 麥克風或 Audio Interface
- 可用的 Windows WASAPI render endpoint（使用 system-output mode 時）

### 後續條件必要

- 原廠 ASIO Driver：只有選定硬體需要 ASIO 時才需要
- Gemini API Key：Stage 2，由使用者在本機 UI 或安全輸入流程自行提供
- vMix：Stage 5

### FFmpeg

v0.1 不依賴 FFmpeg。即使系統已安裝，Stage 0–4 也不會使用。若後續加入 FFmpeg 功能，會先說明用途、支援版本、安裝影響與驗證方式。

## 安裝專案依賴

在專案根目錄執行：

```bash
uv sync --dev
npm install
```

這兩個命令只安裝專案內 Python/npm 依賴，不修改系統 PATH、音訊驅動或全域套件。

## Stage 0–2 驗證命令

### Backend tests

```bash
uv run python -m pytest backend/tests -v
```

### Python lint

```bash
uv run ruff check backend
```

### Python type check

```bash
uv run mypy backend/app
```

### Frontend tests

```bash
npm --prefix frontend test -- --run
```

### Frontend production build

```bash
npm --prefix frontend run build
```

### Prerequisite CLI smoke test

```bash
uv run externaltranslate-prerequisites
```

CLI預設讀取 `config/default.yaml`。若要套用非秘密使用者設定或明確runtime來源：

```bash
uv run externaltranslate-prerequisites --user-config "${USER_CONFIG_PATH}"
uv run externaltranslate-prerequisites --source-kind wasapi_loopback
```

Explicit `--source-kind`會原子切換來源並清除另一來源的device/endpoint selection，
避免使用者YAML中的舊selection與`INPUT_DEVICE XOR WASAPI_LOOPBACK`衝突。

輸出為 UTF-8 JSON，包含：

- Windows 與 CPU 架構
- Python 3.11
- Node.js/npm
- Git
- FFmpeg 的「v0.1 不需要」狀態
- vMix 的「Stage 5 條件必要」狀態
- `sounddevice`／PortAudio 版本與可用 input endpoint 數量
- `PyAudioWPatch` 版本與可用 WASAPI loopback render endpoint 數量

Endpoint列舉只代表 adapter可載入，狀態為 `not_checked`，不等同功能已通過；必須再執行
對應 smoke test驗證 open、PCM、Stop與restart。未啟用的另一種來源只標為optional。

### 列舉 Windows 音訊輸入裝置

```bash
uv run externaltranslate-audio-devices
```

輸出包含 device index、Windows host API、input channel 數、native sample rate 與
latency。Device index 可能在重新插拔或重新開機後改變，執行 capture 前應重新列舉。

### 真實音訊 capture smoke test

```bash
uv run externaltranslate-audio-smoke --device-index "${DEVICE_INDEX}" --channel 1 --duration 10
```

先將 `DEVICE_INDEX` 設為當次列舉取得的整數。Smoke test 會：

- 只使用 `INPUT_DEVICE`，不啟用 loopback。
- 從 device native format 轉換成 16 kHz mono signed PCM16 little-endian。
- 產生固定 100 ms／3,200-byte chunks。
- 回報 RMS、peak、clipping、callback/processing error 與 queue drop count。
- 驗證 WAV header、PCM byte count、Stop、handle release 與再次 Start。
- 未指定 `--output` 時只在memory中建立WAV並驗證，不建立暫存錄音檔。

若要保留明確指定的非敏感測試檔，可加上 `--output <path>`；真實錄音不得提交 Git。

### 列舉 Windows system-output loopback endpoints

```bash
uv run externaltranslate-loopback-devices
```

輸出包含 render endpoint index、名稱、native channels/sample rate，以及是否為當下
Windows default output。Index 可能因重新開機、裝置插拔或 driver變更而改變。

### 真實 WASAPI loopback smoke test

使用每次 Start 當下的 Windows default output：

```bash
uv run externaltranslate-loopback-smoke --duration 10
```

指定本次列舉得到的 endpoint index：

```bash
uv run externaltranslate-loopback-smoke --endpoint-index "${ENDPOINT_INDEX}" --duration 10
```

先將 `ENDPOINT_INDEX` 設為當次 loopback列舉取得的整數。

Smoke test會將 native stereo/multi-channel system mix downmix/resample為 16 kHz mono
PCM16、產生固定100 ms／3,200-byte chunks，並驗證 WAV header、meter、queue drops、
Stop與再次Start；restart必須再次取得有效PCM才算通過。未指定 `--output` 時WAV只存在
memory。若要保留非敏感 WAV，`--output` 在本機 Git Bash環境建議直接傳入
quoted Windows path，例如：

```bash
uv run externaltranslate-loopback-smoke --duration 10 \
  --output 'C:\Users\<user>\AppData\Local\Temp\loopback-smoke.wav'
```

WASAPI silence可能不產生 callback packet；smoke test若完全沒有 PCM會 fail closed，不會誤報
成功。Capture期間若 Windows default output改變，default mode會停止目前 stream並要求重新
Start；explicit endpoint mode則固定擷取所選 endpoint。`INPUT_DEVICE`與
`WASAPI_LOOPBACK`永遠二選一，不同時擷取或混音。

### Gemini Live Translate smoke test

Gemini API Key不得放入command line、YAML或repository。若process environment沒有
`GEMINI_API_KEY`，CLI會以hidden prompt安全詢問；不要把key貼進聊天或log。

WASAPI loopback：

```bash
uv run externaltranslate-gemini-smoke \
  --source-kind wasapi_loopback \
  --duration 30
```

Input device：

```bash
uv run externaltranslate-gemini-smoke \
  --source-kind input_device \
  --device-index "${DEVICE_INDEX}" \
  --channel 1 \
  --duration 30
```

CLI預設只輸出transcription metadata，不輸出完整文字；只有使用者明確加上
`--show-text`才會顯示文字。Smoke驗收：只要實際收到非空、language code為
`zh-Hant`的output transcription（含即時interim）即回報成功——這是因為連續語音下
Gemini Live Translate主要送出`finished=false`的即時字幕；僅connect成功、空白輸出或
只收到input transcription都不算通過。

### 觀察運行狀態與字幕狀態

```bash
uv run externaltranslate-gemini-smoke \
  --source-kind wasapi_loopback --duration 30 \
  --status-events --caption-state
```

`--status-events`會為每次元件狀態轉移輸出一行JSON：`audio_source`（starting／running／
stopping／stopped／error）、`gemini_provider`（connecting／connected／backoff／fail_closed／
stopped）、`gemini_session`（active／rotating／stopped，含generation與rotation原因
`timer`／`goaway`）與`caption_sink`（active／reset）。狀態只包含metadata：component、state、
revision與白名單欄位（generation、reason、attempt、delay_seconds、rotation_seconds、
text_length），永遠不含字幕文字、API key、裝置識別或SDK原始錯誤內容；同一份sanitized紀錄
也會寫入`externaltranslate.status` logger。

`--caption-state`輸出canonical `CaptionState`（revision、caption_status、language_code、
text_length、session_generation），字幕文字仍只有在加上`--show-text`時才會顯示。字幕
payload上限來自validated設定`caption.max_payload_length`，只存在記憶體，不寫入逐字稿檔案。

Permanent的authentication／permission／policy錯誤會讓`gemini_provider`停在`fail_closed`，
不會被後續的`stopped`覆蓋，避免把不可恢復的credential問題顯示成正常結束。

AudioSource在整個pipeline只start一次。Gemini session預設每480秒主動換新連線，收到
server GoAway會提前換線；retryable connect/send/receive/EOF錯誤採
`0.5 → 1 → 2 → 4 → 5秒上限`backoff。Authentication、permission、invalid
configuration與policy錯誤fail closed，不會無限重試。換線期間沿用audio source既有
bounded drop-oldest queue；唯一的persistent PCM reader位於Gemini sessions外層，透過
容量1的drop-oldest async handoff供當前session sender消費。Rotation不會建立第二個
`get_pcm_chunk()` consumer，也不建立無界buffer或追送長時間過期音訊。

## 設定優先順序

非秘密設定依以下順序覆蓋：

```text
Runtime override → 使用者設定 → config/default.yaml
```

Audio設定使用strict schema：未知欄位或尚未接線的值會fail closed，不會接受後忽略。
Validated `source_kind`、device/endpoint selection、channel與queue capacities由同一
production audio source factory消費，以維持 `INPUT_DEVICE XOR WASAPI_LOOPBACK`。
Gemini設定同樣使用strict schema；`session_rotation_seconds`預設480，允許範圍為
60–540秒，且由production CLI實際傳入session supervisor。

`config/default.yaml` 和使用者 YAML 不得包含 API key、password、token 或 secret。開發環境可參考 `.env.example`，但正式程式會從繁體中文本機 UI 接收 Gemini API Key，並預設只保存在程序記憶體。

## 安全原則

- Gemini API Key 不進入 Git、YAML、前端資源、browser storage、URL 或日誌。
- 本機服務在後續 Stage 預設只綁定 `127.0.0.1`。
- 逐字稿預設不保存。
- WASAPI loopback可能包含通知、會議或其他程式聲音；只在使用者明確選擇時啟動，音訊預設不保存。
- 真實錄音、逐字稿、API 回應與使用者裝置識別資料不得提交。

## 開發文件

- `AGENTS.md`：開發與安全規則
- `BUILD.md`：版本和打包設計
- `PLAN.md`：逐 Stage 執行計畫

每個 Stage 完成後必須停止、提交繁體中文驗證報告，等待使用者批准下一個 Stage。

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
- **Stage 4 Phase A/B（驗證中）**：只綁`127.0.0.1`的FastAPI控制服務、`PipelineRuntime`、
  caption WebSocket，以及繁體中文控制頁與`/overlay`。真實端到端smoke尚未完成前，
  不視為Stage 4／v0.1驗收通過。
- **Stage 3.1（驗證中）**：後端字幕排版器——以全形寬計算的「每行字數 × 行數」、中文標點
  禁則、拉丁字詞不硬拆、滑動視窗。控制頁可於翻譯進行中即時調整並重新排版；overlay 與
  vMix GT Title 共用同一份`CaptionState.lines`。
- **Stage 4.1（驗證中）**：字幕外觀與操作——字型（微軟正黑體／標楷體／Noto Sans TC）、
  字級、文字顏色、向上滑動效果（可開關並調整毫秒）、**一鍵清空字幕**、
  **字幕格式預設的存讀刪**，以及**設定持久化**：控制頁改過的版面、樣式與音訊來源會寫回
  `config/user.yaml`，重新啟動或換電腦後自動還原。音訊裝置以名稱記憶並於啟動時比對回編號，
  找不到或同名多個時維持未選擇並說明原因。
- **Stage 3.2**：`backend/app/status/`（models／store／publisher）提供runtime元件
  狀態與sanitized structured log，session supervisor在連線、rotation、backoff與fail-closed
  時發布狀態；CLI新增`--status-events`與`--caption-state`。真實Gemini smoke尚未完成前，
  不視為Stage 3.2驗收通過。

目前不會：

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

## 啟動本機應用（Stage 4）

開兩個終端機。後端：

```bash
uv run externaltranslate-serve
```

前端（開發模式）：

```bash
npm --prefix frontend run dev
```

控制頁在 <http://localhost:5180>，Overlay在 <http://localhost:5180/overlay>。

開發模式的埠固定為5180（`strictPort`），避免被其他工具佔用後靜默改號。Vite只綁定
`localhost`，用`127.0.0.1:5180`會連不上，請用`localhost`。HTTP走Vite proxy到
`127.0.0.1:8765`；**WebSocket不走proxy**，直接連後端——Vite 8的ws proxy在此環境會在
upgrade階段丟`write ECONNABORTED`，改為直連後連續連線皆正常。正式build由後端自行提供，
屆時同源，不需要任何proxy。

由於dev的WebSocket是跨來源，後端對`/ws/captions`檢查`Origin`：只接受loopback來源
（`localhost`／`127.0.0.1`／`::1`），其他一律以1008關閉。瀏覽器不對WebSocket套用同源政策，
沒有這道檢查的話，任何網頁都能連上本機讀取字幕。無`Origin`的非瀏覽器用戶端（CLI、測試）
不受限。

服務**只會綁定`127.0.0.1`**；
`--host`傳入任何非loopback位址會直接失敗且不啟動server，`features.lan_access`也不會放行。

API Key在控制頁輸入，只保留在後端程序記憶體：不寫入設定檔、不回傳給前端（連遮罩片段都沒有，
只回報「已設定／未設定」）、不進入`localStorage`／`sessionStorage`／cookie／URL／log。

### 字幕顯示範圍（每行字數 × 行數）

在控制頁的「字幕顯示範圍」面板直接設定，**翻譯進行中也可以調整，會立即重新排版**，
不需停止翻譯或重新整理：

- **每行字數**（4–60）：以**全形字**計算。一行的容量是「字數 × 2 欄」，中文字佔 2 欄、
  英數佔 1 欄。純中文即每行剛好 N 字；中英數混排時一行會放進更多字元，但**視覺寬度一致**
  ——這是「字數」在混排下唯一講得通的定義。
- **行數**（1–10）：顯示最新的 N 行（滑動視窗）。

也可用 API 直接改：

```bash
curl -X PUT http://127.0.0.1:8765/api/settings/caption-layout -H "Content-Type: application/json" -d "{\"chars_per_line\":10,\"max_lines\":2}"
```

**斷行由後端統一產生**（`backend/app/captions/formatter.py`），結果放在
`CaptionState.lines`，overlay 與之後的 vMix GT Title 渲染同一份，換行位置不可能不一致。
規則包含中文標點禁則（`。、，！？」）`不落行首、`「（`不留行尾）與拉丁字詞不硬拆。
`CaptionState.text` 仍是未格式化的完整累積尾端；`lines` 只是顯示視窗。

**已知限制**：後端以欄數計算，瀏覽器以實際字型排版，比例字型下同欄數的兩行視覺寬度仍會
略有差異。斷行以 code point 為單位，不做 grapheme 分群（2026-08-10 決議），ZWJ 組合表情
若剛好落在行尾邊界可能被拆開；翻譯輸出以繁體中文為主，實務上不會遇到。

### 字幕樣式（字型／字級／顏色／滑動）

控制頁的「字幕樣式」面板，同樣**翻譯進行中可調整、立即生效**：

- **字型**：白名單三選一——`jhenghei`（微軟正黑體）、`kai`（標楷體）、
  `noto-sans-tc`（Noto Sans TC，**Windows 未內建，播放端需另行安裝**，未安裝時瀏覽器
  會自動 fallback）。字型是白名單而非自由字串：這個值會進到 CSS font stack，
  且 overlay 網址常被複製到 vMix／OBS，自由字串等於注入點。
- **字級**：12–200 px。
- **文字顏色**：嚴格 `#RRGGBB`。
- **向上滑動效果**：可開關；開啟時新行由下往上推入，滑動時間 120–1000 ms。

```bash
curl -X PUT http://127.0.0.1:8765/api/settings/caption-style -H "Content-Type: application/json" -d "{\"font\":\"kai\",\"size\":64,\"scroll\":true,\"scroll_ms\":250,\"color\":\"#FFCC00\"}"
```

樣式**只影響網頁 overlay**；Stage 5 的 vMix GT Title 有自己的字型與動畫設定，
共用的只有後端斷好的 `CaptionState.lines`。

### 清空字幕

控制頁的紅底白字「清空字幕」按鈕（`POST /api/captions/clear`）會立刻清掉目前畫面上的
字幕並讓 revision +1 推播出去。用途是長時間沒有偵測到語音時，手動移除過期字幕；
**不會停止翻譯**，下一段語音照常接上。

### 字幕格式預設

把目前生效的版面＋樣式（每行字數、行數、字型、字級、顏色、滑動與滑動時間）存成具名預設，
之後一鍵套用：

| 動作 | API |
|---|---|
| 列出 | `GET /api/caption-presets` |
| 儲存目前設定 | `PUT /api/caption-presets`（body：`{"name": "..."}`） |
| 套用 | `POST /api/caption-presets/{name}/apply` |
| 刪除 | `DELETE /api/caption-presets/{name}` |

存放於 `config/caption-presets.json`（已 gitignore）。所有預設放在**同一個 JSON 檔內、以名稱
為 key**，名稱不會被當成檔案路徑，因此預設名稱無法用來做路徑穿越。名稱上限 60 字元、
最多 50 組；檔案損毀或個別項目不合法時只略過壞掉的部分，不會讓控制頁開不起來。

### 設定持久化與換電腦

控制頁改過的**字幕版面與樣式**以及**音訊來源**會寫回 `config/user.yaml`，重新啟動後端後
自動還原，不必每次重設。換到另一台電腦時複製這兩個檔案即可：

```text
config/user.yaml              ← 目前生效的字幕版面與樣式
config/caption-presets.json   ← 所有已儲存的字幕預設
```

兩者都已被 `.gitignore` 排除，不會進版控。三個刻意的行為：

- **API Key 永遠不會被寫進去**：寫檔前仍跑 secret 欄位檢查，key 只留在程序記憶體。
- **`config/user.yaml` 解析失敗時拒絕覆寫**：直接蓋掉等於銷毀使用者可能還想修好的設定。
- **寫檔失敗不影響操作**：磁碟唯讀或路徑不存在時設定照常生效，只是沒存下來；
  持久化是便利功能，不該讓直播中的調整失敗。

**音訊裝置以名稱記憶，不記編號**。裝置編號只是列舉清單裡的位置，插拔、重開機或換電腦後
同一個編號可能是完全不同的硬體，直接沿用會安靜地錄到錯的來源。所以存進 `user.yaml` 的是
`device_name` 與 `device_host_api`（系統音源則是 `loopback_endpoint_name`），編號在**每次啟動時
用名稱比對回來**：

| 情況 | 結果 |
|---|---|
| 重啟軟體、插拔其他裝置、重開機 | 找回同一個裝置 |
| 上次的裝置不在了 | **不猜**，維持未選擇並在控制頁說明原因 |
| 有多個同名裝置（兩支相同型號的麥克風） | **不猜**，維持未選擇並請你重新選擇 |
| 裝置列舉失敗（驅動異常） | 服務照常啟動，維持未選擇並說明原因 |

同名裝置若分屬不同 host API（Windows 常把同一支麥克風同時列在 MME／DirectSound／WASAPI 下），
會用 host API 區分；若驅動重裝導致 host API 改變而名稱仍唯一，則以名稱為準。

系統音源若使用「Windows 預設輸出」（不指定 endpoint），本來就與機器無關，不需要比對。

### Overlay 顯示參數

`/overlay`可用query參數自訂，全部為樣式參數，不含任何credential：

| 參數 | 說明 | 預設 |
|---|---|---|
| `width` | 字幕框寬度（`1600`為px，`75%`為百分比） | `90%` |
| `lines` | **本頁**顯示行數上限（1–10），覆寫後端設定 | 後端設定值 |
| `size` | 字級px（12–200） | `48` |
| `font` | `jhenghei`／`kai`／`noto-sans-tc`（白名單） | `jhenghei` |
| `color` | 文字色，嚴格`#RRGGBB` | `#FFFFFF` |
| `bg` | 字幕框背景色，嚴格`#RRGGBB` | `#000000` |
| `opacity` | 背景透明度0–1，`0`為完全透明 | `0.5` |
| `align` | `left`／`center`／`right` | `left` |

例如：`http://localhost:5180/overlay?lines=1&width=1600&size=56&opacity=0`

非法或超出範圍的參數一律fail closed回預設值。頁面背景恆為透明，供vMix Browser Input與
OBS Browser Source去背；字幕框自己的底色由`bg`與`opacity`決定。

`lines`**只覆寫這個 overlay 顯示幾行，不改後端斷行**——因此可以同時開兩個高度不同的
Browser Input 吃同一份字幕。要改每行字數請用控制頁或 caption-layout API。

## 設定優先順序

非秘密設定依以下順序覆蓋：

```text
Runtime override → 使用者設定 → config/default.yaml
```

「使用者設定」預設就是 `config/user.yaml`（可用 `--user-config` 指定別的檔案）。
控制頁調整字幕版面與樣式時，程式會把結果**寫回這個檔案**，所以下次啟動讀到的就是上次的設定。

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

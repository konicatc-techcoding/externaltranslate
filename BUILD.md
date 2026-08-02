# ExternalTranslate BUILD.md

## 文件用途

本文件定義 ExternalTranslate 的 Windows 打包方向、執行環境、必要先決條件，以及第一個可驗證版本 `v0.1` 的範圍。`AGENTS.md` 定義所有開發代理必須遵守的規則；本文件定義實際要建造與交付的版本。

## 最終產品建議

### 推薦架構

建議把最終產品打包為單一 Windows 桌面應用程式，內部仍保留清楚的程序邊界：

```text
ExternalTranslate.exe
  ├─ Python application core
  │   ├─ audio capture
  │   ├─ Gemini Live Translate client
  │   ├─ caption formatter
  │   ├─ local FastAPI/WebSocket service
  │   └─ vMix adapter
  ├─ compiled React frontend
  └─ native desktop window (pywebview)
```

推薦組合：

- Python 3.11 application core
- FastAPI + WebSocket
- React + TypeScript，建置後作為靜態資源內嵌
- `pywebview` 作為 Windows 桌面視窗
- PyInstaller `onedir` 產出應用程式目錄
- Inno Setup 建立正式安裝程式
- Windows Credential Manager 保存使用者選擇儲存的 Gemini API key

### 為什麼 v0.1 不優先使用 PyInstaller onefile

`onefile` 每次啟動通常需要解壓縮，較容易出現啟動變慢、防毒軟體誤判、內嵌前端資源路徑與 native library 載入問題。建議先用 `onedir` 完成可靠版本，再由 Inno Setup 包成一個安裝檔。對使用者而言仍是一個正常安裝的程式，但開發與除錯更穩定。

### Node.js 的定位

Node.js 只作為前端建置工具。正式安裝包應包含已編譯的前端資源，因此一般使用者不需要另外安裝 Node.js。開發機與打包機仍須檢查並驗證指定 Node.js LTS 與 npm 版本。

### FFmpeg 的定位

v0.1 不預設依賴 FFmpeg。音訊擷取與 PCM 轉換先使用 PortAudio/`sounddevice` 與 Python 音訊處理完成。只有在後續確認需要裝置格式橋接、錄音轉檔或額外 resampling 能力時才加入 FFmpeg。若加入，必須決定由安裝程式合法隨附固定版本，或要求使用者另行安裝，並處理授權、PATH 與版本驗證。

### vMix 與驅動

- vMix 不隨本程式打包；啟用 vMix 功能前必須檢查 vMix 是否已安裝、正在執行、Web API 已啟用且指定端點可連線。
- 一般 Windows 音訊先支援 WASAPI/WDM。
- 專業 Audio Interface 若需要 ASIO，必須安裝原廠驅動，並驗證應用程式實際能透過 ASIO-capable capture path 開啟指定 channel。
- 驅動、ASIO、vMix 或其他系統程式的安裝與 PATH 修改都要先取得使用者同意。

## 執行資料位置

建議正式版本使用：

```text
%LOCALAPPDATA%\ExternalTranslate\
├─ config.yaml
├─ logs\
├─ cache\
└─ state\
```

Gemini API key 不得寫入 `config.yaml`。使用者在繁體中文 UI 輸入 API key 後：

1. 只送往 `127.0.0.1` 的本機後端。
2. 預設只保留於程序記憶體。
3. 使用者勾選「安全地記住 API Key」時，才寫入 Windows Credential Manager。
4. UI 只顯示遮罩值與是否已設定，不回傳完整 key。
5. API key 不得出現在 URL、日誌、錯誤訊息、前端儲存或字幕 WebSocket 中。

## 應用程式啟動流程

1. 啟動單一 instance guard，避免重複開啟多個服務。
2. 執行 prerequisite health check。
3. 由作業系統配置可用的 loopback port，或使用已驗證未占用的設定 port。
4. 啟動 FastAPI/WebSocket 於 `127.0.0.1`。
5. 開啟 pywebview 控制視窗。
6. 載入繁體中文設定精靈。
7. 使用者輸入 Gemini API key、選擇音訊裝置並執行連線測試。
8. 如啟用 vMix，執行 vMix API 測試和 Title/Browser Input 驗證。
9. 關閉桌面視窗時，依序停止音訊、Gemini session、WebSocket、vMix sender 與本機服務。

## Prerequisite Health Check

程式必須有繁體中文的「環境檢查」頁面，至少顯示：

| 項目 | v0.1 狀態 | 驗證內容 |
|---|---|---|
| Windows 10/11 64-bit | 必要 | OS 與架構 |
| Gemini API key | 必要 | 可建立 Gemini Live session；不可只檢查非空字串 |
| 音訊輸入裝置 | 必要 | 可開啟選定 device/channel 並讀到 frames |
| WASAPI/WDM driver | 必要 | 實際 capture smoke test |
| ASIO driver | 條件必要 | 選定硬體需要 ASIO 時才要求，但一旦選用就必須完整安裝並驗證 |
| vMix | 條件必要 | 啟用 vMix output 時必須完成安裝與 API smoke test |
| Node.js/npm | 開發/打包必要 | 版本、npm install、frontend build |
| FFmpeg | v0.1 非必要 | 未啟用依賴時明確顯示「此版本不需要」 |

「條件必要」表示該功能一旦被使用，就必須完成所有相關驅動和外部程式安裝，否則不得宣稱完整運行；未啟用的選配功能不應阻塞其他模式啟動。

## Gemini 官方規格來源

Gemini 整合只以以下官方文件為主要依據：

- https://ai.google.dev/gemini-api/docs/live-api/live-translate

在實作 Gemini 階段前必須重新確認：

- 最新支援模型名稱
- `google-genai` 支援版本
- input/output transcription event 結構
- PCM sample rate、sample format、channel 與 chunk 建議
- `zh-Hant` 支援狀態
- session、rate limit、preview 限制與錯誤行為

Google API key 由使用者自行提供，程式必須提供繁體中文輸入欄位、顯示/隱藏切換、連線測試、清除 key，以及選擇是否保存到 Windows Credential Manager。

# v0.1 版本定義

## v0.1 目標

交付一個可在開發機上啟動的 Windows MVP，完成環境檢查、API key 輸入、音訊裝置偵測與擷取、Gemini 即時翻譯文字接收，以及本機繁體中文字幕預覽。v0.1 先證明核心音訊到字幕管線可靠；正式安裝器和完整 vMix 輸出可在後續版本完成。

## v0.1 包含範圍

### 1. 專案骨架

- Python 3.11 backend package
- React + TypeScript frontend
- FastAPI REST/WebSocket
- 測試、lint、type-check 與 build scripts
- `.env.example`、預設設定與 `.gitignore`
- 繁體中文 README 開發啟動說明

### 2. 環境檢查

- 顯示 Python、Node.js/npm 與必要 native dependency 狀態
- 列出音訊 host API、device、input channel 和 sample rate
- 顯示 v0.1 是否需要 FFmpeg
- 產生繁體中文可操作錯誤訊息
- 不自動修改 PATH 或安裝驅動

### 3. Gemini API Key 設定

- 繁體中文遮罩輸入欄位
- 顯示/隱藏 key
- 測試連線
- 清除 key
- 預設只存在記憶體
- Windows Credential Manager 保存選項的介面與後端邊界
- key 不進入 URL、log、browser storage 或 WebSocket caption payload

### 4. 音訊 Proof of Concept

- 選擇 microphone/audio interface
- 選擇 input channel
- RMS/peak meter
- 轉換為 Gemini 當前官方要求的 PCM 格式
- bounded queue
- 可控 Start/Stop
- 裝置拔除與開啟失敗處理

### 5. Gemini Live Translate

- Provider adapter
- 依官方文件建立 Live Translate session
- 目標語言預設 `zh-Hant`
- 傳送即時 PCM chunks
- 接收 input/output transcription
- partial/final 或官方等價事件的正確組裝
- timeout、取消、正常關閉與可理解錯誤

### 6. 本機字幕預覽

- FastAPI/WebSocket 將 canonical caption state 送到 UI
- 繁體中文控制頁
- 字幕頁只使用文字節點，不使用 `innerHTML`
- 基本字型、大小、文字色、背景色
- 最大 payload 長度
- Gemini 或裝置錯誤狀態顯示

## v0.1 不包含範圍

- 正式 Windows installer
- 完整 vMix GT Title `SetText`
- vMix Browser Input 自動配置
- 完整 Unicode 行寬與多行滾動策略
- ASIO 專用 capture adapter，除非 Stage 1 實機證明選定硬體必須使用
- 字幕歷史保存
- 多語言 UI
- LAN 遠端控制
- 翻譯音訊播放或錄製

這些項目保留給後續小版本，避免 v0.1 同時驗證太多高風險整合。

## v0.1 驗收標準

- 全新開發環境的缺失 prerequisites 能被偵測並以繁體中文說明。
- 所有 v0.1 必要依賴完成版本與功能驗證。
- UI 可以輸入使用者提供的 Gemini API key，完整 key 不會被回傳或記錄。
- 至少一個真實 Windows 音訊輸入裝置可被開啟並持續取得 frames。
- 送往 Gemini 的格式符合實作當下官方文件。
- 真實語音能產生 `zh-Hant` output transcription 並顯示於本機字幕頁。
- Start/Stop 可重複操作，不殘留 audio stream、task 或 Gemini session。
- 模擬網路錯誤與裝置錯誤不會使整個程式無預期結束。
- automated tests、lint、type check 與 frontend production build 全部通過。
- 若缺少真實 API、硬體或服務，必須列為 blocker，不能用 mock 結果宣稱整合完成。

## v0.1 建議實作順序

1. 建立最小 Python/React 專案骨架與測試指令。
2. 建立 prerequisite checker 與繁體中文狀態模型。
3. 建立 API key 的記憶體與 Credential Manager abstraction。
4. 建立音訊裝置列舉、capture 與 meter。
5. 建立 PCM converter 與 bounded queue。
6. 依官方文件建立 Gemini provider adapter。
7. 建立 transcript assembler 與 canonical caption state。
8. 建立控制頁、API key 欄位與字幕預覽。
9. 執行真實裝置和 Gemini smoke test。
10. 執行長時間與重複 Start/Stop 測試，完成 v0.1 報告後停止。

## 後續版本方向

- `v0.2`：Unicode 行寬、最大行數、字幕樣式與 Overlay 穩定化。
- `v0.3`：vMix API、GT Title、Browser Input 與斷線恢復。
- `v0.4`：ASIO 實機支援、更多 Audio Interface 測試與音訊診斷。
- `v0.5`：PyInstaller onedir、Inno Setup、升級與解除安裝流程。
- `v1.0`：完整安裝版、長時間 soak test、正式操作文件與支援矩陣。

版本號可以依實際風險調整，但不得跳過前一版本的實際驗證結果。

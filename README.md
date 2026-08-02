# ExternalTranslate

ExternalTranslate 是 Windows 本機優先的即時翻譯字幕應用程式。專案將從麥克風或 Audio Interface 擷取音訊，透過 Gemini Live Translate 產生繁體中文字幕，並在後續 Stage 輸出到網頁 Overlay 與 vMix。

## 目前狀態

目前只完成 **Stage 0：專案骨架、依賴盤點與安全邊界**。

Stage 0 不會：

- 開啟麥克風或 Audio Interface。
- 呼叫 Gemini API。
- 啟動 FastAPI/WebSocket。
- 連線 vMix。
- 安裝或修改任何系統驅動、PATH 或全域套件。

## 必要環境

### Stage 0 必要

- Windows 10/11 64-bit
- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ 或 22.12+ 與 npm（符合目前 Vite 8 工具鏈要求）
- Git for Windows

### 後續條件必要

- 可用的 WASAPI/WDM 麥克風或 Audio Interface：Stage 1
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

## Stage 0 驗證命令

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

輸出為 UTF-8 JSON，包含：

- Windows 與 CPU 架構
- Python 3.11
- Node.js/npm
- Git
- FFmpeg 的「v0.1 不需要」狀態
- vMix 的「Stage 5 條件必要」狀態
- 音訊裝置的「Stage 1 尚未檢查」狀態

## 設定優先順序

非秘密設定依以下順序覆蓋：

```text
Runtime override → 使用者設定 → config/default.yaml
```

`config/default.yaml` 和使用者 YAML 不得包含 API key、password、token 或 secret。開發環境可參考 `.env.example`，但正式程式會從繁體中文本機 UI 接收 Gemini API Key，並預設只保存在程序記憶體。

## 安全原則

- Gemini API Key 不進入 Git、YAML、前端資源、browser storage、URL 或日誌。
- 本機服務在後續 Stage 預設只綁定 `127.0.0.1`。
- 逐字稿預設不保存。
- 真實錄音、逐字稿、API 回應與使用者裝置識別資料不得提交。

## 開發文件

- `AGENTS.md`：開發與安全規則
- `BUILD.md`：版本和打包設計
- `PLAN.md`：逐 Stage 執行計畫

每個 Stage 完成後必須停止、提交繁體中文驗證報告，等待使用者批准下一個 Stage。

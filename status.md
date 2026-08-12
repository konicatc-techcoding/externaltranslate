# ExternalTranslate — Stage 4.1 交接狀態 (status.md)

> 本文件供後續 model／agent 快速接手。最後更新：2026-08-10（Stage 4.1 字幕外觀、清空、預設與設定持久化）。
> 閱讀本檔前，請先重讀 `AGENTS.md`、`BUILD.md`、`PLAN.md` 與
> `.hermes/plans/2026-08-09_123446-stage-3-captions.md`、
> `.hermes/plans/2026-08-09_124912-stage-3.2-observability.md`、
> `.hermes/plans/2026-08-10_105311-stage-3.1-caption-formatter.md`。

---

## 0. 下一步（Next Action）

> **Stage 5 已完成並通過實機驗收（2026-08-12）。** 收尾的三個決定都由使用者拍板，
> 見下方「Stage 5 收尾決定」。目前**沒有進行中的工作**。

1. **v0.1 驗收剩餘項目：裝置錯誤測試**（見下方 ⏳ 待辦；斷網已通過）。
   **這是 v0.1 的 blocker，排在任何新功能之前。** 使用者要取得外接裝置測實體拔除；
   看門狗修法已定但尚未實作，且「偵測到要停止 pipeline 還是只顯示錯誤」尚未決定。
2. 使用者回報中英數混排斷行的實際效果後再調整 formatter（目前無已知問題）。
3. **「啟用 vMix 輸出」勾選框**（2026-08-11 已修）待順手驗證：翻譯中取消勾選 → 確認 →
   GT Title 立刻清空且不再更新、overlay 繼續；再勾回來 → 字幕當場回到 Title 上。
4. **Stage 6 onedir 已完成（2026-08-12），待使用者在目標機器實測**。要測的是：
   複製 `dist/ExternalTranslate/` 到那台 → 執行 `ExternalTranslate.exe` → 控制台自動開啟
   → **音訊來源列得出來**（這是打包最容易壞的地方）→ 設定改了會寫進
   `%LOCALAPPDATA%\ExternalTranslate`。
   **Inno Setup 安裝程式等使用者說 onedir OK 之後再考慮。**
5. 其他候選：字幕語言（見 `PLAN.md`「候選功能：字幕語言」）、Stage 1.1 ASIO
   （**只有實際硬體需要時才做，目前沒有需要**）。**皆未經指示，不得自行動工。**
6. Playwright overlay 驗證**已完成**（2026-08-12），見下方。

### Stage 6：PyInstaller onedir（2026-08-12，已實作＋實機驗證）

使用者決定**先做 onedir，OK 之後再考慮 Inno Setup**。

`PYTHONPATH='' uv run python scripts/build_windows.py` → `dist/ExternalTranslate/`（約 72 MB）。
複製整個資料夾到目標機器、執行 `ExternalTranslate.exe`，**那台不需要 Python／Node／uv**。

- **刻意不做 pywebview**：原生視窗需要 WebView2 執行環境，而本專案不替使用者安裝執行環境
  （與「不自動安裝 Node」同一條原則）。改為啟動後開預設瀏覽器。要原生視窗的話排到
  安裝程式那一輪。
- **保留主控台視窗**：它印出網址，啟動失敗時也看得到原因；windowed build 會無聲失敗。
  關掉視窗就停止服務——與 `run.bat` 同一個心智模型。
- **`backend/app/resources.py` 是唯一知道檔案在哪的地方。** 先前有五處各自算
  `Path(__file__).parents[3]`，每一處在凍結後都會指向那台機器上不存在的原始碼樹。
- **打包後寫入 `%LOCALAPPDATA%\ExternalTranslate`**，從原始碼執行則維持 `config/`
  ——後者是刻意的，否則開發者的既有設定會在這次改動後無聲搬家。
  寫入位置與程式目錄分離，換掉整個資料夾升級也不會弄丟設定（有測試斷言
  可寫路徑不在 bundle 內）。
- **單一實例**：啟動前先探連接埠，已被佔用就印 `already_running` 並 exit 1。

**踩到的坑（會再踩，寫下來）：`importlib.import_module` 的模組 PyInstaller 看不到。**
第一次 build 出來的程式可以開頁面、可以讀設定，**但音訊裝置列舉 500**：
`ModuleNotFoundError: No module named 'pyaudiowpatch'`。`sounddevice`、`soxr`、
`websockets` 同理，全部得寫進 spec 的 `hiddenimports`。
**這種錯誤不會在啟動時出現，只會在操作者打開音訊面板那一刻出現**——所以打包後一定要
實際打過 `/api/devices` 與 `/api/loopback-endpoints`，不能只看首頁有沒有開。

實測（2026-08-12，`dist/ExternalTranslate/ExternalTranslate.exe`）：
`/`、`/overlay`、`/api/settings`、`/api/devices`、`/api/loopback-endpoints`、
`/api/prerequisites`、`/api/caption-presets` 全部 200；loopback 正確回報
`Speakers (Realtek(R) Audio)`；WebSocket 同源連上；改字幕版面後
`%LOCALAPPDATA%\ExternalTranslate\config\user.yaml` 出現 `chars_per_line: 14`、
`idle_reset_ms: 2500`；重複啟動印出 `already_running` 並 exit 1。

**尚未做**：Inno Setup 安裝程式（使用者說 onedir OK 之後再考慮）、
全新 Windows VM 的安裝測試（Stage 6.1）。

### Playwright overlay 驗證（2026-08-12，已實作＋已驗證抓得到 bug）

`npm run test:e2e`（＝ `vite build && playwright test`）。7 個測試，Chromium。

- **測的是正式建置的頁面**，由 `vite preview` 服務；**字幕 socket 在頁面裡被
  `addInitScript` 換掉**，所以不需要後端、API Key 或麥克風，而且測試能決定每一筆字幕
  何時抵達——「連續兩次滑動」這種時序才測得出來的東西，靠真後端反而做不到。
- **範圍照使用者 2026-08-10 的決定：只做尺寸與行為斷言，不做像素快照比對。**
- 涵蓋：框高 = 字級 × 1.3 × 行數、超出行數被裁掉且框不長高、只有最上面那行被擠掉才播
  動畫、**前一次沒播完就再滑動要重播**、整段被換掉不播、body 背景全透明（vMix 去底）、
  頁面不出現捲軸。
- **已確認會抓到那個 bug**：把 `SLIDE_CLASS` 的交替拿掉（還原成修好之前的單一 class）
  再跑，第四個測試失敗——第二次滑動的 `currentTime` 是 133 ms（動畫從沒重新開始），
  而不是接近 0。其餘六個仍然通過，正好說明**只有那一個測試在守這件事**。
- `vite preview` 必須加 `--host 127.0.0.1`：vite 預設綁 localhost（IPv6 `::1`），
  而 Playwright 的就緒檢查打的是 `127.0.0.1`。
- vitest 的 `exclude` 要排除 `e2e/**`，否則預設的 `**/*.spec.ts` 會把 Playwright
  的測試撈進 jsdom 跑。
- 執行產物（`test-results/`、`playwright-report/`）已加入 `.gitignore`。
  第一次執行需 `npx playwright install chromium`（約 115 MB）。

### Stage 5 收尾決定（2026-08-12 使用者拍板，不得自行推翻）

1. **vMix prerequisite 維持現狀，不改。** 它只查本機 `vmix.exe`，而 vMix 在別台，
   所以那一列永遠顯示「未偵測到」——**這是已知且接受的**。實際的連線檢查由控制頁的
   「從 vMix 讀取 input」負責。那一列的 `action` 文字還寫著「Stage 5 前確認…」，
   措辭已過期但使用者決定不動。**不要「順手修好」它。**
2. **「Browser Input 顯示/隱藏控制」砍掉**，理由記在 `PLAN.md` Stage 5。
3. **拓樸 B 的區網 overlay ＋ IP 名單：使用者傾向不做**（2026-08-12）。
   因此 **Browser Input 只在「程式與 vMix 同一台」時可用**，程式在別台時用 GT Title
   ——這是產品限制，不是待辦缺口。設計形狀仍保留在下方，日後要做再拿出來；
   **未經指示不得動工。**
4. **滑動抖動的第二輪修正實測通過**（2026-08-12）。

### vMix 在另一台（2026-08-11 使用者更正，蓋掉先前記錄）

**vMix 執行在另一台電腦上；本機安裝的那份不能用。** 本檔先前寫的「同一台」「無法變更
IP」都是錯的，已作廢。

**正式使用時兩種拓樸都會出現**（2026-08-11 使用者確認）：
- **A：程式跑在 vMix 那台**——全部本機通訊，Browser Input 直接可用，不需要任何安全讓步。
  vMix 那台本來就有節目聲音，WASAPI loopback 抓到的就是播出訊號。
- **B：程式跑在收音那台、vMix 在別台**——GT Title 可用（已實證），**Browser Input 不可用**。

因此**不能假設任何一種**，設計與文件都要同時成立。

三個直接後果：

1. **GT Title 跨機器已經在實機上成立**——下方 Phase B 三項都是對著另一台的 vMix 通過的。
   這正是當初「我們主動連出去，所以 GT Title 可以跨機器」那個判斷的實證。
2. **Browser Input 在拓樸 B 無法運作，而且不是「還沒去測」**。它要求 vMix 那台**連進來**
   抓 `/overlay`，但 `resolve_bind_host()` 只允許 `127.0.0.1`，`features.lan_access` 被刻意
   忽略。這是 Stage 4 的安全決定，不是疏漏。
   拓樸 A 則沒有這個問題——程式與 vMix 同機，Browser Input 指 `127.0.0.1` 即可。
   **要在 B 支援 Browser Input，必然等於讓區網上任何人都能抓到字幕。** 值得注意的是
   B 之下字幕本來就以明文經過區網（vMix 面板已有這則警告），差別在「只有 vMix 那台收得到」
   變成「誰都能主動抓」——是程度差異，不是性質差異。這個取捨要使用者自己拍板。
3. vMix prerequisite 目前找的是**本機**的 `vmix.exe`。既然 vMix 一律在別台，那個檢查對
   這個使用者永遠是「未偵測到」，等於一列雜訊——真正該查的是設定裡那台主機的 Web API
   通不通。

### 拓樸 B 的 Browser Input：**2026-08-12 使用者傾向不做**，以下僅供日後參考

先前（08-11）同意過方向，隔日改為傾向不做。**未經新的明確指示不得動工。**
現況因此是：**拓樸 B 用 GT Title，沒有 Browser Input。**

當初要的是「一份 IP 名單／可輸入欄位，只有名單上的 IP 抓得到 Browser Input」。
真要復活這件事，以下是必須先講明的形狀：

- **IP 名單不能取代綁定位址**。要讓別台連得進來，socket 就必須綁在區網位址上；名單是
  連線被接受**之後**才由應用層過濾。兩件事都要做，名單不是「不用開放」的替代品。
- **建議開第二個 socket，而不是在同一個 socket 上比對路徑**。控制頁與 API 留在
  `127.0.0.1`，另開一個只掛 `/overlay`（含靜態檔）與 `/ws/captions` 的小 app 綁區網位址。
  這樣「API 不對外」是**結構上做不到**，而不是靠一條路徑比對規則；那條規則寫錯的代價是
  `/api/credentials`（可被 POST 覆蓋 API key）、`/api/pipeline/start|stop`、`/api/settings`
  全部對區網敞開。
- **只信 socket 的對端位址，永不看 `X-Forwarded-For`**（那是請求方自己填的）。
- **WebSocket 的 Origin allowlist 要一併放行該區網來源**，否則 `/overlay` 連得到頁面卻
  拿不到字幕。
- 預設關閉；控制頁必須顯示「服務已對外：<位址>:<port>，允許 <ip 清單>」。
- **這道防線擋不了的**：同區網上偽裝成名單內 IP 的機器（ARP 層的事），以及區網上的被動
  竊聽——`/overlay` 是 HTTP，沒有加密。字幕內容在拓樸 B 下本來就以明文過區網。

**前置條件：一鍵啟動——2026-08-11 已完成**（見下方），與這件事是否要做無關，
它本來就是拓樸 A 把程式裝到 vMix 那台所需要的。

### 一鍵啟動（2026-08-11，已實作＋實測）

`backend/app/api/static.py`：後端直接提供 `frontend/dist`，`run.bat` 一鍵建置並啟動。
**一個程序、一個埠**（127.0.0.1:8765），控制台在 `/`、字幕頁在 `/overlay`。

- **不是 catch-all**：只有 `/` 與 `/overlay` 兩條路由回 `index.html`（`App.tsx` 就是靠
  `window.location.pathname` 二選一），`/assets` 掛 `StaticFiles`。用 catch-all 的話，
  打錯的 API 路徑會拿到 HTML，呼叫端變成 JSON parse 失敗而不是看到 404。
- **掛在所有 router 之後**，頁面不可能蓋掉它自己要呼叫的路由（有測試）。
- **沒建置不是錯誤**：`frontend/dist` 不存在時 API 照常運作、頁面 404，
  `app.state.frontend_dist` 為 None，`externaltranslate-serve` 印出的 JSON 多一個
  `ui` 欄位據實回報。分得清「還沒建置」與「服務掛了」。
- 執行期不需要 Node。要在沒有 Node 的機器上跑，把整個 `frontend/dist` 複製過去即可。

**`run.bat` 的兩條硬規則（2026-08-11 使用者實測後才發現，兩個都踩到了）**：
1. **必須是 CRLF 換行。** 第一版是 LF，cmd 會找不到 label、把行接在一起，錯誤訊息長得像
   「'?' 不是內部或外部命令」。已加 `.gitattributes`（`*.bat text eol=crlf`）確保任何
   checkout 都拿到 CRLF。
2. **批次檔本身必須是純 ASCII。** 中文放進去會亂碼；加了 `chcp 65001` 之後顯示雖然正確，
   但 **cmd 會算錯下一行的讀取位移**（多位元組字元的已知缺陷），後面的行從字元中間接續，
   出現 `'ode' 不是內部或外部命令` 這種錯誤。所以中文訊息一律放在 `scripts/run-*.txt`
   （UTF-8），批次檔用 `type` 印出來——批次剖析器永遠看不到那些位元組。
   **不要把中文寫回 `run.bat`。**

兩條分支都實測過：有 `frontend/dist` 時走 serve 分支（`uv sync` → 印出網址 → 啟動）；
沒有 npm 時印出中文說明並以 exit 1 結束。

實測（2026-08-11，真實服務＋瀏覽器）：`/` 與 `/overlay` 皆 200 text/html、
`/assets/*.js` 200、`/api/settings` 200、`/nonsense` 404 application/json；
控制台在 8765 開啟後 **WebSocket 同源連上**（`ws://127.0.0.1:8765/ws/captions`），
console 無錯誤；`/overlay?lines=3` 正確渲染 `.overlay-shell`。

### Stage 5 Phase B 驗收紀錄（2026-08-11，真實 vMix 28.0.0.42，**在另一台電腦**）

- [x] **GT Title 與 `/overlay` 斷行一致**。Stage 3.1 升級為 Stage 5 硬前置條件的整個
      理由在此，現已由實機確認。
- [x] **停止翻譯後 GT Title 與 overlay 都清空**。
- [x] **翻譯途中 vMix 死掉（2026-08-11 通過）**。強制關閉 vMix 後翻譯照常運行；
      重新開啟 vMix 專案後**字幕自己接回去**，不需要重開翻譯。
      注意這次能自動接回，是因為重開的是**同一個專案、GUID 沒變**。`start()` 只在
      開始時驗證一次 GUID，重連時不再驗；若 vMix 開回來載入的是別的 preset 或 Title
      被重新加過，GUID 會變，狀態可能顯示 active 但畫面上沒有字。**此邊界情況未測。**
      （使用者第一次做的是「取消勾選啟用 vMix 輸出」，那是正常關閉路徑，不會產生
      `VmixError`、backoff 或復原，測不到隔離設計要保護的情況——但因此測出了下面
      那個勾選框的錯誤。）
- [x] **Browser Input 實際顯示（2026-08-11 通過，拓樸 A）**。程式以 `prebuilt` 分支裝在
      vMix 那台，Browser Input 指 `http://127.0.0.1:8765/overlay`。
      **拓樸 B（程式在別台）仍然不行**，見上方第 2 點。

**Phase B 四項全數通過（限拓樸 A；拓樸 B 只有 GT Title 可用）。**

#### 滑動抖動（2026-08-11 使用者在 Browser Input 回報，已修）

第一次修抖動（2026-08-10）修的是**觸發條件**；這次是同一個症狀的另外三個原因，
都在 `CaptionPreview`：

1. **連續滑動不會重播動畫。** 同一個 class 再設一次不會重啟 CSS animation，所以前一次
   還在播時來的第二次滑動**完全沒有動畫**，接著第一支計時器把 class 拿掉，transform
   從半途瞬間跳回 0——那一下就是抖動。改用兩個同內容、不同名稱的 keyframes 交替
   （`caption-slide-up` / `caption-slide-up-again`），換名字才會重啟。
2. **每個片段都在重建 DOM。** `key` 是 `${index}-${line}`，文字一變就等於換了身分，
   React 會丟掉 `<p>` 再建一個——一秒好幾次，而且發生在動畫進行中。改成只用 index，
   文字就地更新。
3. **整段被換掉時也會滑動。** `idle_reset_ms` 停頓重來、或清空字幕時，視窗從滿的變成
   一行，`!first.startsWith(previous)` 成立就播了動畫，把新句子從下面拖上來。
   加上「行數變少就不是捲動」——捲動永遠不會讓行數變少。

`prebuilt` 分支已同步重新建置。

**這次測出來的錯誤（2026-08-11 已修）：`set_vmix_enabled()` 只寫設定，不動正在跑的輸出。**
`runtime.py` 的 `start()` 把 `self._vmix_output` 複製進區域變數 `vmix_output`，
caption sink 閉包用的是那個副本，所以翻譯中改 `self._vmix_output` 影響不到它。
結果是勾選框看起來已經生效（UI 已取消勾選），GT Title 卻繼續更新到下次開始翻譯為止
——和先前修掉的「input 下拉選單『—』無作用」同一類：**畫面宣稱的狀態與實際不符**。
`vmix.host`／`input_guid`／`fields` 維持「下次開始才生效」是對的（中途改目標會讓舊
Title 留著字且沒人能清），但**啟用開關不一樣**：直播中「把字幕從 Title 上拿掉」是
當下就要的動作，而且 `_close_vmix_output()` 這條乾淨路徑早就存在。

修法（2026-08-11）：
- `set_vmix_enabled()` 改為 async，翻譯中會**當場**關閉（清空欄位）或開啟輸出；
  `PUT /api/settings/vmix` 隨之改為 async route。
- caption sink 改成**每次都讀 `self._vmix_output`**，不再於 `start()` 複製進區域變數。
  這是原本失效的真正原因，也是「開回來要當場接上」得以成立的前提。
- **開關兩個方向都必須即時**：只做關閉的話，謊言只是換一邊——勾選框打勾而字幕沒出去。
- 前端：**翻譯中**取消勾選會先跳確認（`確定停用`／`取消`），沒在翻譯時直接生效——
  畫面上本來就沒有字幕，跳確認只是擋路。啟用方向不確認。
  確認用面板內嵌區塊而非 `window.confirm`：直播中搶走焦點的 modal 比它防的錯誤更糟。

> 已結案的決策（皆為使用者 2026-08-10 拍板，不得自行推翻）：
> - 音訊裝置持久化採「記名稱、啟動時比對回編號」，見下方 Stage 4.1 音訊裝置持久化。
>   **編號永遠不寫入設定檔。**
> - **Playwright overlay 驗證排到 Stage 5（vMix）之後**，且只做尺寸與行為斷言、
>   不做像素快照比對。理由見 `PLAN.md` Stage 4.1 剩餘能力。
> - 打包分兩件事：**「一鍵啟動」（後端直接吐前端靜態檔 ＋ 捷徑）可以早做**，
>   **「一鍵安裝」（Stage 6 pywebview／PyInstaller／Inno Setup）排到 Stage 5 之後**。
>   理由：PyInstaller 最怕依賴變動，vMix 整合會再動執行期形狀；且 v0.1 驗收未關。
>   使用者尚未指示開始，勿自行動工。
> - **字幕語言（2026-08-11 使用者決定先不做）**：換一種輸出語言、以及同時輸出多種語言，
>   兩者的起點、會撞到的東西與排程建議都寫在 `PLAN.md`「候選功能：字幕語言」。
>   **尚未列入任何 release，未經使用者指示不得動工。**
> - **Browser Input 跨機器**：目前**不支援**，且是刻意的。`resolve_bind_host()` 只允許
>   `127.0.0.1`，`features.lan_access` 被明確忽略（Stage 4 決定：把服務攤上網路等於把
>   「這台機器聽得到的聲音」也攤上去）。**GT Title 跨機器可以**（我們主動連出去），
>   **Browser Input 不行**（對方要連進來）。
>   使用者 2026-08-10 要求記錄，之後有空再做。真要做的最低限度：明確開關（非預設）、
>   綁定位址由使用者指定、控制頁標示服務已對外，且**建議只開 `/overlay`，控制頁與 API
>   維持 loopback**。未經使用者指示不得動工。

---

## 1. 專案定錨

| 項目 | 值 |
|---|---|
| 專案根目錄 | `C:\Users\razer\Documents\HermesWorkspace\ExternalTranslate` |
| Branch / remote | `main` → `origin/main` (`github.com/konicatc-techcoding/externaltranslate.git`) |
| 已發布 HEAD | 以 `git log --oneline -1 origin/main` 為準；本檔不記死 hash（會立刻過期）。目前未 push 的內容見 §0。 |
| Python | 3.11，套件管理 `uv`；Windows Git Bash |
| 關鍵執行規則 | 所有 Python／uv 指令必須 `PYTHONPATH=''`；證實 backend 需 canonical `uv run pytest -W error` |

### 完成並已發布
- **Stage 0**：骨架、依賴盤點、安全邊界。
- **Stage 1**：Windows input capture、meter、16 kHz mono PCM16、100 ms chunk、bounded drop-oldest queue。
- **Stage 1.2**：WASAPI loopback、render endpoint 列舉、stereo downmix、source XOR、真實硬體驗收、commit + push。
- **Stage 2**：官方 `google-genai` Gemini Live Translate、provider-neutral events、安全 CLI、長期 AudioSource／外層 session supervisor；177 tests、3 輪 independent review、真實 Gemini smoke（input 23／output 22），commit + push（`ac5934e`）。
- **Stage 3（已實作＋驗證，已 commit + push `c618fb4`）**：`backend/app/captions/`（models／sanitizer／assembler／store）組裝 canonical `CaptionState`；`caption.max_payload_length` strict schema；**215 passed**、Ruff/Mypy clean、audit 0（已修 `nanoid` patch advisory）。

### Stage 3.2（已實作＋真實 smoke 通過，已 commit）
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

### Stage 4（Phase A/B，已 commit）
- `backend/app/api/`：只綁 `127.0.0.1` 的 FastAPI 控制服務、`PipelineRuntime`、
  caption WebSocket（`/ws/captions`）、catalog／settings／credentials／pipeline routes。
- WebSocket 有 **Origin allowlist**（瀏覽器不對 WS 套用 same-origin policy，沒這道檢查
  任何網頁都能讀本機字幕），非 loopback 來源以 1008 關閉；無 `Origin` 的非瀏覽器用戶端放行。
- `frontend/`：繁體中文控制頁與 `/overlay`；dev server 固定 **port 5180**（5173 被 agentos 佔用），
  dev 時 WebSocket **直連後端**（Vite 8 的 ws proxy 會 `write ECONNABORTED`）。
- 途中修掉的兩個真實 bug：Stop 後再 Start 失敗（改為一個 runtime 一個 assembler ＋
  `reset()` 維持 revision 單調）；`caption_sink` 卡在 idle（改用共用的
  `backend/app/status/caption_status.py`）。
- 控制頁另有翻譯計時器（開始翻譯歸零起算、停止時凍結）。

### Stage 5 Phase A（2026-08-10，vMix 輸出，**已於 2026-08-12 通過實機驗收**）
計劃檔：`.hermes/plans/2026-08-10_162520-stage-5-vmix.md`

環境：實作期間以假 vMix 驗證。（本機 `C:\Program Files (x86)\vMix\vmix.exe` 那份**不能使用**；
實際驗收用的 vMix 28.0.0.42 在**另一台電腦**上，見上方「vMix 在另一台」。）
官方 API 事實：port 8088、`GET /api/` 回 XML、`SetText` 參數為
`Function`／`Input`／`SelectedName`／`Value`。**文件說** GT Title 文字欄位名稱要加 `.Text`
後綴——**這是 Phase B 要驗證的事，不是前提**；實測時以 `GET /api/vmix/inputs` 回報的名稱為準。

- `backend/app/outputs/`：`base.py`（`CaptionOutput` protocol ＋ `NullOutput`）、
  `vmix.py`（client：XML 探索、`SetText`、錯誤分類）、`sender.py`（節流送出器）、
  `vmix_output.py`（行→欄位映射與狀態轉換）。
- **設定欄位叫 `input_guid` 不叫 `input_key`**：既有的秘密欄位檢查會拒絕任何 `_key` 結尾的
  欄位。那個檢查是對的，改名字而不是替它開後門。
- **不加 `httpx` 依賴**：用 stdlib `http.client` ＋ `asyncio.to_thread`。一開始用
  `urllib.urlopen`，連線被拒時 socket 交給 GC，在 `-W error` 下變成測試失敗；自己持有
  connection、`finally` 關閉才乾淨。
- **假 vMix**（`backend/tests/outputs/fake_vmix.py`）以 stdlib `ThreadingHTTPServer` 開真實
  TCP，可切換逾時／500／404／斷線／壞 XML。驗證了中文、`&`、`%`、`

`、空字串的往返編碼。
- **節流保證尾筆**：只丟棄過快的更新而不補送最後一筆，字幕會永遠停在倒數第二個片段。
- **`flush()`** 讓「停止時清空欄位」不必等節流窗口、也不會被關閉流程丟掉。
- **失敗全隔離**：vMix 沒開／中途掛掉／回 500，翻譯與 overlay 完全不受影響（有測試斷言）。
  `vmix_output` 元件狀態只發布轉換，不是每個片段一筆。
- **狀態 detail 只多一個白名單欄位 `field_count`**（數量，不是內容）。

Gates：**542 backend passed**、ruff、mypy 65 files、**118 frontend passed**、build 通過。

**未驗證（Phase B）**：`.Text` 後綴是否如文件所述、單欄位多行的顯示方式、中文在 GT Title
的字型表現。假伺服器是照文件寫的，只能證明我們送的東西符合文件。

### 句尾換行（2026-08-10，Stage 3.1 遺留問題結案）

使用者原本提案「句號超過一行的 2/3 就換行」；改為**看剩餘空間**後實作。

- `。！？` 結束一句時，若該行**剩餘不足 4 個全形字**，下一句另起一行。
  `backend/app/captions/formatter.py` 的 `_sentence_cut()`／`SENTENCE_BREAK_MIN_CHARS`。
- **為什麼不用比例**：每行 60 字時「超過 2/3」代表句子在第 41 字結束就丟掉近 20 字的可用
  空間。以剩餘 4 字為準，不論 10 字或 60 字，留白都不超過 4 字。
- **只認全形 `。！？`**：半形句點出現在「3.5 公里」「Mr. Chen」。句尾後緊跟的
  `」』）` 併入同一句。
- **判斷只看已顯示的內容，不看下一句多長**：字幕是片段串流，下一句通常還在打字中，
  用它的長度判斷會讓已定案的斷行隨後續文字反覆改變、在讀者眼前跳動。這是刻意的取捨。
- **只做斷行，刻意不做「句尾收束為 final」**：滑動視窗已決定觀眾看到什麼，收束會改動
  `CaptionState` 語意（text 被清、revision 跳動、GT Title 收到的形狀改變），收益小而牽動大。
- 設定為 `caption.sentence_breaks`（**layout 而非 style**，因為它會 reflow），預設開啟，
  控制頁「字幕顯示範圍」面板可切換。

實測（每行 10 字，「我們現在開始。請看螢幕」）：
關閉→`我們現在開始。請看螢` / `幕`（一個字被孤立）；開啟→`我們現在開始。` / `請看螢幕`。

**使用者回報的抖動已修正**（2026-08-10）：啟用句尾換行後滑動效果會抖。原因不在斷行，
在 `CaptionPreview` 的觸發條件——原本是「第一行內容變了就播動畫」，但有兩件事會改變
第一行卻沒有捲動：標點被拉回上一行（行變長）、視窗未滿時新增一行（既有文字不動）。
句尾換行讓第二種變頻繁，抖動才被看見。
改為**只在最上面那行被換掉時才播**：文字只會往後累加，所以被「編輯」的行必定以舊內容為
前綴（`!first.startsWith(previous)`），真正捲動時前綴關係不成立。一個條件同時涵蓋
視窗未滿、標點回拉、最後一行增長、`max_lines=1` 換句四種情況。

### 停頓後重新開始（2026-08-11，多行字幕的可讀性）

使用者把行數加到 5 行後回報：「一直在看最後兩行，多行的價值好像變少」。這個判斷正確，
原因在 `wrap_caption()` 最後一行 `lines[-max_lines:]`——**只要累積文字超過 N 行，
視窗就永遠在滑動**，新字一律在最下面，上面幾行都是已經讀過的歷史。多行真正好讀的是
**填充模式**（從第 1 行往下長、既有行不動），而它以前只在每次開始翻譯後出現一次。

- 設定 `caption.idle_reset_ms`：距離上一個 output 片段超過這個時間，下一段從第 1 行
  重新開始。**0 為關閉，且是預設值**；其餘允許 500–30000。
- **訊號是「字幕閒置」不是「音訊靜音」**：翻譯比語音晚一到兩秒，用音訊靜音會在片段還
  在送的時候切掉沒人讀過的字。
- **重置是「延後執行」不是「到時清空」**：時間到只立旗標，畫面不動；等下一個片段來
  才丟掉舊文字。理由與 Stage 4.1「斷線保留字幕」同一條——**空白的 vMix input 看起來
  像翻譯停了**。附帶好處是不需要背景計時器，判斷就寫在 `_accept_output()` 裡，
  用既有注入的 `now` 就能測。
- **與「句尾收束為 final」的先前決定不衝突**：那次拒絕的是用標點改動 `CaptionState`
  語意；這次是時間驅動、且發生在沒人正在讀的空檔，換到的是填充模式本身。
- 已知取捨：**講者在句子中間停頓超過門檻，前半句會被丟掉**。所以下限訂 500 ms、
  建議值 2500 ms 以上。若實測會切斷，再考慮「句尾是 `。！？` 才提早重置」的分級。
- preset 會連同這個值一起存與套用（`CaptionPreset.idle_reset_ms`，預設 0，
  舊 preset 檔仍可讀）；套用舊 preset 等於把它關掉，preset 清單那一列會標示。
- `_snapshot_key` 加入 `idle_reset_ms`，否則只改這一項不會經 WebSocket 推播，
  第二個分頁的面板會停在舊值。

實測（2026-08-11，真實瀏覽器 ＋ 服務）：面板輸入 2500 → `/api/settings`、
`/api/pipeline/status` 的 `layout` 與 `config/user.yaml` 三處一致 → **重啟後端**→
仍為 2500。100／-1／30001 皆 422 且生效值不變。**真實翻譯下的可讀性尚未驗收。**

Gates：**569 backend passed**、ruff、mypy 65 files、**134 frontend passed**、build、tsc。

### Stage 4.1 補完（2026-08-10，字幕外觀）
使用者決定先補完外觀，理由是它直接決定字幕在 vMix 畫面上的呈現效果。

- **`backend/app/config.py` 的 `CAPTION_STYLE_FIELDS` 是單一真實來源**：每個外觀欄位的
  名稱、預設值、檢查函式與繁體中文錯誤訊息都在這張表裡。config 驗證、`caption_style()`、
  `PipelineRuntime.update_caption_style()` 與 preset 驗證全部走這張表——外觀從 5 個欄位長到
  14 個，逐處手寫檢查正是「API 收得下、runtime 卻忽略」的來源。
  Pydantic model 刻意**不重複寫 bound**，只宣告型別，由 runtime 驗證後映射成 422。
- 新增欄位：`weight`、`outline_width`（0–8）、`outline_color`、`shadow`、`background_color`、
  `background_opacity`（0–1）、`padding`（0–64）、`radius`（0–48）、`align`。
- **描邊用一圈 `text-shadow`，不用 `-webkit-text-stroke`**：stroke 以字邊為中心、會把中文
  筆畫變細，正好在需要它更清楚時失效；shadow ring 畫在文字後方不動字形。
  `textShadowFor()` 在 `frontend/src/overlay/style.ts`。
- **`outline_width` 預設 0**：升級後自動長出描邊會改變既有 overlay 外觀。
- `parseOverlayStyle` 拆成 `parseOverlayOverrides()`（只回傳「有給且合法」的 key）＋
  `captionStyleToOverlay()`。**非法 query 參數退回後端設定**，而不是退回會與控制頁矛盾的硬編預設。
- **控制頁預覽改用真實樣式**（`captionStyleToOverlay(status.style)`）。先前預覽固定用
  `DEFAULT_OVERLAY_STYLE`，等於調了看不到，違背「調整時應即時預覽」的規劃。
- **斷線保留與淡出**：overlay 保留最後字幕並降到 45% 透明度（`.overlay-shell .caption-box--stale`）；
  控制頁維持虛線外框。空白的 vMix input 看起來像翻譯停了，比一句稍舊的字幕更糟。
- **舊 preset 檔仍可讀**：`CaptionPreset` 的新欄位都有 default，缺欄位不會讓整組 preset
  在載入時被當成無效而消失（有測試）。

實測（2026-08-10，真實瀏覽器）：控制頁送出
`size 56 / bold / outline 4 #101010 / shadow / bg opacity 0 / padding 24 / radius 20 / center`
→ 頁面 computed style 為 8 圈描邊 + 投影、`font-weight 700`、`text-align center`、
`padding 24px`、`border-radius 20px`、背景 `rgba(0,0,0,0)`；`config/user.yaml` 同步寫入全部欄位。

### Stage 4.1（已實作＋實測通過，已 commit）
使用者需求：字型／字級／滑動效果 → 一鍵清空字幕 → 顏色與字幕格式預設 → 重啟還原設定。

- **字幕樣式**：`caption.font`（`jhenghei`／`kai`／`noto-sans-tc` 白名單）、`caption.size`
  （12–200）、`caption.color`（嚴格 `#RRGGBB`）、`caption.scroll` 與 `caption.scroll_ms`
  （120–1000）。`PUT /api/settings/caption-style`，**執行中可改、立即生效**。
  字型是白名單而非自由字串：值會進 CSS font stack，且 overlay 網址會被複製到 vMix／OBS。
- **清空字幕**：`POST /api/captions/clear` + 控制頁紅底白字按鈕；清畫面、revision +1 推播，
  **不停止翻譯**。
- **字幕格式預設**：`backend/app/captions/presets.py` + `/api/caption-presets`
  （GET 列出／PUT 存目前設定／POST `{name}/apply`／DELETE）。存於
  `config/caption-presets.json`（已 gitignore）。**所有預設放在同一個 JSON 檔、以名稱為 key**
  ——名稱因此不可能被當成檔案路徑，杜絕路徑穿越；名稱上限 60 字元、上限 50 組；
  檔案損毀或個別項目不合法時只略過壞掉的部分（壞掉的預設不該讓人開不了節目）。
- **設定持久化**：`save_user_settings()`（`backend/app/config.py`）把版面與樣式寫回
  `config/user.yaml`；`serve.py` 預設讀同一個檔。**沒有發明新機制**——user.yaml 本來就是
  `runtime > user > default` 的使用者層，只是以前只能手改。三個刻意行為：
  1. 寫檔前跑既有 secret 欄位檢查，**API key 絕不落地**（有測試斷言檔內不含 key 也不含 `api_key`）。
  2. `user.yaml` 解析失敗時**拒絕覆寫**，不銷毀使用者可能還想修好的設定。
  3. 寫檔失敗（唯讀／路徑不存在）**不影響設定變更本身**，持久化不該讓直播中的調整失敗。
#### 音訊裝置持久化（2026-08-10 使用者拍板：記名稱比對）
- `backend/app/audio/identity.py`：`resolve_device_index()`／`resolve_endpoint_index()`
  以**名稱（＋host API）**找回目前的列舉編號。**編號永遠不寫入 `user.yaml`**——編號是列舉
  清單裡的位置，插拔／重開機／換電腦後同一個數字可能是不同硬體，寫進去等於「看起來成功、
  實際錄錯來源」。
- 存的是 `audio.device_name`、`audio.device_host_api`、`audio.loopback_endpoint_name`
  （皆為 strict schema 新欄位，與既有 index 欄位同樣遵守 INPUT_DEVICE XOR WASAPI_LOOPBACK）。
- **不猜**：找不到、同名多個、或列舉失敗時一律維持未選擇，並由
  `RuntimeSnapshot.audio_notice` →`/api/pipeline/status` 與 WebSocket → 控制頁黃色提示說明原因。
  同名但不同 host API（Windows 常把同一支麥克風列在 MME／DirectSound／WASAPI 下）用 host API
  區分；host API 變了但名稱唯一則以名稱為準。
- `serve.py` 在建立 runtime 後呼叫 `restore_audio_selection()`；沒有存過名稱時直接 return，
  不會為了沒東西可還原而去列舉硬體。
- 系統音源選「Windows 預設輸出」時 `loopback_endpoint_name` 為 null，本來就與機器無關。

實測（2026-08-10，真實硬體）：選 index 9 的 `Microphone (Realtek(R) Audio)`（WASAPI，同名裝置
另有 MME 與 DirectSound 兩筆）→ `user.yaml` 只寫入名稱與 host API →**重啟後端**→ device_index
還原為 9、`audio_notice` 為 None。把名稱改成不存在的裝置再重啟 → device_index 為 None、
`audio_notice` 為「找不到上次使用的音訊裝置「…」，已改為未選擇；請重新選擇音訊來源。」

實測（2026-08-10）：改設定 → 殺掉後端 → 重新啟動 → `chars_per_line 12 / max_lines 4 /
font kai / size 64 / color #FFCC00 / scroll false / scroll_ms 400` 七項全部還原。

| Gate | 結果 |
|---|---:|
| `PYTHONPATH='' uv run pytest -W error -q` | **468 passed** |
| `uv run ruff check backend` | 通過 |
| `uv run mypy backend/app` | 59 source files，無問題 |
| `npm run test` | 15 files / **108 passed** |
| `npm run build` | 通過 |

### ⏳ 待辦：v0.1 驗收剩餘項目（使用者有空時執行）

`BUILD.md` 驗收標準之一「模擬網路錯誤與裝置錯誤不會使程式無預期結束」尚未實測，
目前是 v0.1 的 blocker。使用者已表示有空時進行（2026-08-10）。

- [x] **斷網測試（2026-08-10 通過）**：使用者於翻譯途中停用 Wi-Fi，程式續存。
- [ ] **裝置錯誤測試——發現缺口，修法已定但延後實作**：使用者於翻譯途中停用內建麥克風，
      **翻譯沒有停止也沒有報錯**。查證後確認是程式行為，不是測試方式問題：
      `input_device.py` 有數 `status_events` 但從未據以動作；`translation_pipeline.py` 的
      `_read_audio` 收到 `TimeoutError` 就 `continue`。**「裝置停止送資料」與「房間安靜」
      目前無法區分。**
      **修法（使用者 2026-08-10 決定先不做）**：看門狗盯 `CaptureStats.callback_blocks`
      是否停止增加——安靜時 callback 仍會觸發並送近 0 的 PCM，裝置死掉時 callback 完全停止，
      兩者可精確區分。**偵測後要停止 pipeline 或只顯示錯誤，尚未決定。**
      **待測**：實體拔除外接裝置（與「停用」行為可能不同），使用者取得裝置後再測。
- [x] 結果已補進 `docs/reports/v0.1-verification.md` §5 與新增的 §5.1。

執行方式：開著控制頁看元件狀態，或另開終端機用
`curl -s http://127.0.0.1:8765/api/pipeline/status` 取狀態快照（不含字幕文字）。

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

## 4. Stage 2 review 與 smoke 歷程（存查，非待辦）

> 下一步請看 §0；本節保留 Stage 2 的 review／修正紀錄以便回溯決策。

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
3. `git status --short --branch` 確認 working tree（Stage 4.1 commit 後為 clean；
   `main` 領先 `origin/main`，push 需使用者授權）。
4. 依 §0 的 Next Action 繼續；不得自行決定 §0 第 2 點。
5. 動程式一律 TDD（先 RED 後 GREEN），完成後跑完整 gates：
   `PYTHONPATH='' uv run pytest -W error -q`、`uv run ruff check backend`、
   `uv run mypy backend/app`、`npm run test`、`npm run build`。
6. 需要時派 independent fail-closed review，再安排真實 smoke 與使用者驗收。

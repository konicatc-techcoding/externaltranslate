# ExternalTranslate — Stage 4.1 交接狀態 (status.md)

> 本文件供後續 model／agent 快速接手。最後更新：2026-08-10（Stage 4.1 字幕外觀、清空、預設與設定持久化）。
> 閱讀本檔前，請先重讀 `AGENTS.md`、`BUILD.md`、`PLAN.md` 與
> `.hermes/plans/2026-08-09_123446-stage-3-captions.md`、
> `.hermes/plans/2026-08-09_124912-stage-3.2-observability.md`、
> `.hermes/plans/2026-08-10_105311-stage-3.1-caption-formatter.md`。

---

## 0. 下一步（Next Action）

1. **等使用者授權 commit**（Stage 5 Phase A 已完成，尚未 commit）。
2. **Stage 5 Phase B：真實 vMix 驗收**。使用者需啟動 vMix、開啟 Web Controller、
   建立 GT Title。計劃檔 §5 有完整步驟。
   **關鍵：不要照 `.Text` 慣例猜欄位名稱**——建好 Title 後按控制頁「從 vMix 讀取 input」，
   用 vMix 自己回報的名稱填入欄位清單。那份名單才是權威，也正是 Phase B 要驗證的事之一。
   **2026-08-10 現況**：使用者目前無法變更 IP，因此 Phase B 先在**同一台**執行；
   跨機器的 GT Title 待日後有條件再測。
   **在 Phase B 通過前，Stage 5 一律標為「待實機驗收」，不得宣稱完成。**
3. **v0.1 驗收剩餘項目**：斷網測試與裝置錯誤測試（見下方 ⏳ 待辦）。
4. 使用者回報中英數混排斷行的實際效果後再調整 formatter（目前無已知問題）。

> 已結案的決策（皆為使用者 2026-08-10 拍板，不得自行推翻）：
> - 音訊裝置持久化採「記名稱、啟動時比對回編號」，見下方 Stage 4.1 音訊裝置持久化。
>   **編號永遠不寫入設定檔。**
> - **Playwright overlay 驗證排到 Stage 5（vMix）之後**，且只做尺寸與行為斷言、
>   不做像素快照比對。理由見 `PLAN.md` Stage 4.1 剩餘能力。
> - 打包分兩件事：**「一鍵啟動」（後端直接吐前端靜態檔 ＋ 捷徑）可以早做**，
>   **「一鍵安裝」（Stage 6 pywebview／PyInstaller／Inno Setup）排到 Stage 5 之後**。
>   理由：PyInstaller 最怕依賴變動，vMix 整合會再動執行期形狀；且 v0.1 驗收未關。
>   使用者尚未指示開始，勿自行動工。
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

### Stage 5 Phase A（2026-08-10，vMix 輸出，**待實機驗收**）
計劃檔：`.hermes/plans/2026-08-10_162520-stage-5-vmix.md`

環境：vMix **28.0.0.42** 已安裝於 `C:\Program Files (x86)\vMix\vmix.exe`，實作期間未啟動。
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

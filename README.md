# 台灣輿情觀測

每天彙整國內各大媒體的新聞標題，回答三件事：今天在吵什麼、各家媒體著重什麼、有沒有報導分布或用語不尋常的議題。

純靜態網站（GitHub Pages）＋ GitHub Actions 排程，不需要伺服器，也不需要安裝任何套件（Python 標準函式庫即可）。

## 結構

| 路徑 | 用途 |
| --- | --- |
| `index.html`、`assets/` | 網站前端（原生 JS，無外部相依） |
| `pipeline/sources.json` | 媒體清單、RSS 位址、立場標記（可自行調整） |
| `pipeline/fetch.py` | 抓 RSS 標題，累積到 `data/raw/<日期>.json` |
| `pipeline/analyze.py` | 議題分群、熱度、異常訊號 → `data/daily/<日期>.json` |
| `pipeline/ai_enrich.py` | （選用）AI：語意合併、60 秒導讀、報導切角 |
| `pipeline/article.py` | 熱門事件的內文抓取（robots.txt、Google News 連結解碼、內文擷取、通稿偵測） |
| `pipeline/report.py` | 一分鐘報告：寫作、程式檢查、AI 逐句查核 |
| `pipeline/make_demo.py` | 產生虛構的示範資料 |
| `.github/workflows/update.yml` | 每小時抓取、分析、部署 |

## 上線步驟

1. 合併到 `main`。
2. Settings → Pages → Source 選 **Deploy from a branch**，Branch 選 **gh-pages**（第一次排程跑完後才會出現）。
3. Actions → **Update data and deploy** → Run workflow，看 log 裡每家媒體是否抓得到。

## 啟用 AI（選用，建議用 Claude）

設定金鑰後，每天台北時間 8、13、21 點各執行一次 AI，產生：

- **語意合併**：把用詞不同、其實是同一事件的議題合併（結果存在 `data` 分支的 `merges/`，每小時分群都會套用）。
- **同一件事，幾種說法**：前幾大議題的 2–3 種報導切角，各附原始標題。
- **一分鐘看懂今天**（`pipeline/report.py`）：只對前 4 個熱門事件，各讀 2–4 家不同媒體的**新聞內文**，寫成約 450 字、一分鐘讀完的報告，顯示在首頁最上方（取代只看標題的 60 秒導讀）。
  - 每句都附引用編號，點了直接開原文。
  - **驗證**：程式先檢查引用編號、句中數字、「」引述是否真的出現在被引用的內文；再由另一個模型逐句對照原文查核，沒有充分依據的句子一律刪除，刪除紀錄公開在「引用來源與查核紀錄」。驗證失敗時不更新報告。
  - **內文訊號（不靠 AI）**：多家內文高度相似（疑似同一份通稿）、多次引用不具名消息來源。
  - **著作權**：內文只在 Actions 執行時存在記憶體裡，不存檔、不上網站；網站只放改寫後的句子與原文連結。抓取遵守 robots.txt，同一網站每 1.5 秒最多一次請求。

步驟：

1. 到 Claude Console（platform.claude.com）在 Billing 購買額度，再到 API keys 建立金鑰。
2. 本 repo → Settings → Secrets and variables → Actions → New repository secret，名稱 `ANTHROPIC_API_KEY`，貼上金鑰。（舊的 `GEMINI_API_KEY` 可以刪掉；兩個都在時預設用 Claude。）
3. Actions → Update data and deploy → Run workflow，勾選「這次強制執行 AI 註解」。
4. 看執行紀錄裡 `[ai]`、`[report]` 開頭的幾行：抓了幾篇內文、失敗原因、刪了幾句、token 用量。

可調整的 repository variables（同一頁的 Variables 分頁）：

| 變數 | 預設 | 用途 |
| --- | --- | --- |
| `AI_PROVIDER` | `claude` | 兩把金鑰都設時指定用哪家 |
| `AI_MODEL` | `claude-haiku-5-5` | 合併、切角、逐句查核 |
| `AI_MODEL_WRITER` | `claude-sonnet-5-5` | 撰寫一分鐘報告 |
| `AI_HOURS` | `8,13,21` | 台北時間哪幾點執行 AI |
| `AI_DEEP` | `1` | 設 `0` 關閉讀內文與報告 |

用量粗估：每次 AI 時段約 4–6 萬 token 輸入（報告寫作與查核占大部分），一天三次。價格以 docs.claude.com 公告為準。
金鑰只放在 Secrets，不要寫進程式碼或貼到任何對話裡。

真實資料存放在 `data` 分支（永遠只有一個 commit），`main` 上的 `data/` 只是示範資料。

## 本機預覽

```bash
python pipeline/make_demo.py        # 產生示範資料
python -m http.server 8000          # 開 http://localhost:8000
python pipeline/run.py              # 抓真實資料（會先清掉示範資料）
```

## 注意

- 標題分析只用標題與連結；一分鐘報告會讀熱門事件的內文，但內文不存檔、不公開，只顯示改寫摘要與原文連結。
- 「異常訊號」是提醒去看的線索，不是任何媒體刻意放話的證明。
- `sources.json` 的 RSS 位址需在第一次執行後依 log 校正；`lean` 為一般外界認知，僅用於統計報導分布。

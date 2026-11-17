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
| `pipeline/ai_enrich.py` | （選用）Claude API：語意合併、60 秒導讀、報導切角 |
| `pipeline/make_demo.py` | 產生虛構的示範資料 |
| `.github/workflows/update.yml` | 每小時抓取、分析、部署 |

## 上線步驟

1. 合併到 `main`。
2. Settings → Pages → Source 選 **Deploy from a branch**，Branch 選 **gh-pages**（第一次排程跑完後才會出現）。
3. Actions → **Update data and deploy** → Run workflow，看 log 裡每家媒體是否抓得到。

## 啟用 AI（選用）

設定金鑰後，每天台北時間 8、13、21 點各呼叫一次 Claude API，產生三樣東西：

- **語意合併**：把用詞不同、其實是同一事件的議題合併（結果存在 `data` 分支的 `merges/`，每小時分群都會套用）。
- **60 秒導讀**：首頁最上方，三件事的白話說明。
- **同一件事，幾種說法**：前幾大議題的 2–3 種報導切角，各附原始標題。

步驟（Claude 或 Gemini 擇一）：

1. 取得金鑰：
   - **Gemini**：到 Google AI Studio（aistudio.google.com）建立 API key。Secret 名稱用 `GEMINI_API_KEY`。
   - **Claude**：到 Claude Console（platform.claude.com）在 Billing 購買額度，再到 API keys 建立金鑰。Secret 名稱用 `ANTHROPIC_API_KEY`。
2. 本 repo → Settings → Secrets and variables → Actions → New repository secret，填入上面的名稱與金鑰。
3. Actions → Update data and deploy → Run workflow，勾選「這次強制執行 AI 註解」。
4. 看執行紀錄裡 `[ai]` 開頭的幾行，會顯示使用哪一家、合併了幾組、註解了幾個議題與 token 用量。

可調整的 repository variables（同一頁的 Variables 分頁）：`AI_PROVIDER`（`claude` 或 `gemini`，兩把金鑰都設時用來指定）、`AI_MODEL`（預設 `claude-haiku-5-5` 或 `gemini-3.8-flash`）、`AI_HOURS`（預設 `8,13,21`）。
金鑰只放在 Secrets，不要寫進程式碼或貼到任何對話裡。

真實資料存放在 `data` 分支（永遠只有一個 commit），`main` 上的 `data/` 只是示範資料。

## 本機預覽

```bash
python pipeline/make_demo.py        # 產生示範資料
python -m http.server 8000          # 開 http://localhost:8000
python pipeline/run.py              # 抓真實資料（會先清掉示範資料）
```

## 注意

- 只使用標題與連結，不抓內文；每則標題都標示來源並連回原文。
- 「異常訊號」是提醒去看的線索，不是任何媒體刻意放話的證明。
- `sources.json` 的 RSS 位址需在第一次執行後依 log 校正；`lean` 為一般外界認知，僅用於統計報導分布。

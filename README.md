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
| `pipeline/ai_enrich.py` | （選用）Claude API 命名、摘要、切角比較 |
| `pipeline/make_demo.py` | 產生虛構的示範資料 |
| `.github/workflows/update.yml` | 每小時抓取、分析、部署 |

## 上線步驟

1. 合併到 `main`。
2. Settings → Pages → Source 選 **GitHub Actions**。
3. Actions → **Update data and deploy** → Run workflow，看 log 裡每家媒體是否抓得到。
4. （選用）Settings → Secrets and variables → Actions 新增 secret `ANTHROPIC_API_KEY` 啟用 AI 註解；可用 variable `AI_MODEL`、`AI_EVERY_HOURS` 調整。

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

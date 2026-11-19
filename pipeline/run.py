#!/usr/bin/env python3
"""一次跑完：抓標題 → 分析 → （選用）AI 註解。給 GitHub Actions 用。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_enrich  # noqa: E402
import analyze  # noqa: E402
import fetch  # noqa: E402



def purge_demo():
    """第一次抓真實資料前，清掉示範資料。"""
    for sub in ("raw", "daily"):
        for p in (analyze.DATA / sub).glob("*.json"):
            if '"demo":true' in p.read_text(encoding="utf-8")[:400].replace(" ", "") or '"mode":"demo"' in p.read_text(encoding="utf-8")[:400]:
                p.unlink()


if __name__ == "__main__":
    purge_demo()
    date = fetch.fetch_all()
    (analyze.DATA / "daily").mkdir(parents=True, exist_ok=True)
    if analyze.analyze(date):
        ai_enrich.enrich(date, force="--force-ai" in sys.argv, fresh="--fresh" in sys.argv)
    analyze.write_index()  # 即使今天還沒資料也要有索引檔，部署才不會失敗

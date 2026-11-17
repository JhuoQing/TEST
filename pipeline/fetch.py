#!/usr/bin/env python3
"""抓取各媒體 RSS 標題，累積進 data/raw/<台北日期>.json。

只用 Python 標準函式庫。RSS 通常只保留最新幾十則，所以要一天多次執行、
每次把新標題併進當日檔案（以「媒體 + 正規化標題」去重）。
單一來源失敗不會中斷整體流程，結果寫進 data/health.json。
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; tw-opinion-dashboard/1.0; +https://github.com/JhuoQing/TEST)"
RAW_KEEP_DAYS = 14  # 原始標題只留 14 天，避免 repo 無限長大


def gnews_url(site):
    q = urllib.parse.quote(f"site:{site} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


MAX_BYTES = 5 * 1024 * 1024  # 單一 feed 上限 5 MB，避免異常回應吃光記憶體


def http_get(url, timeout=25):
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError("只允許 http(s) 來源")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("回應超過大小上限")
    return data


def get_feed(url, is_gnews, state):
    """Google News 連續查詢會被限流（HTTP 429）：每次查詢間隔 3 秒，被擋就等 20 秒再試一次。"""
    if is_gnews:
        wait = 3 - (time.time() - state.get("last", 0))
        if wait > 0:
            time.sleep(wait)
    try:
        return http_get(url)
    except urllib.error.HTTPError as e:
        if not (is_gnews and e.code == 429):
            raise
        time.sleep(20)
        return http_get(url)
    finally:
        if is_gnews:
            state["last"] = time.time()


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_time(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except Exception:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TPE)
    return dt.astimezone(TPE)


def parse_feed(xml_bytes):
    """回傳 [(title, link, datetime|None)]，支援 RSS 2.0 / RDF / Atom。"""
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = link = when = None
        for c in el:
            t = local(c.tag)
            if t == "title":
                title = "".join(c.itertext()).strip()
            elif t == "link":
                link = (c.text or "").strip() or c.attrib.get("href", "")
            elif t in ("pubdate", "published", "updated", "date") and when is None:
                when = parse_time(c.text)
        if title:
            out.append((title, link or "", when))
    return out


TAIL = re.compile(r"\s*[-－–—|｜]\s*[^-－–—|｜]{1,24}$")


def clean_title(title, is_gnews):
    title = re.sub(r"\s+", " ", title).strip()
    if is_gnews:  # Google News 標題結尾是「 - 媒體名」
        title = TAIL.sub("", title)
    return title


def norm_key(title):
    return re.sub(r"[\W_]+", "", title).lower()


def fetch_all(now=None):
    now = now or datetime.now(TPE)
    today = now.strftime("%Y-%m-%d")
    cfg = json.loads((ROOT / "pipeline" / "sources.json").read_text(encoding="utf-8"))
    raw_dir = DATA / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{today}.json"
    day = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else {"date": today, "items": []}
    seen = {(it["source"], norm_key(it["title"])) for it in day["items"]}
    health = {"checked_at": now.isoformat(timespec="seconds"), "sources": []}
    added_total = 0
    gstate = {}

    for src in cfg["sources"]:
        got, added, errors = 0, 0, []
        for feed in src["feeds"]:
            is_gnews = feed["type"] == "gnews"
            url = gnews_url(feed["site"]) if is_gnews else feed["url"]
            try:
                entries = parse_feed(get_feed(url, is_gnews, gstate))
            except Exception as e:  # 單一 feed 失敗就記錄後繼續
                errors.append(f"{url}: {type(e).__name__}: {e}"[:200])
                continue
            for title, link, when in entries:
                got += 1
                est = when is None  # feed 沒給時間就用抓取時間，並標記為估計值
                when = when or now
                if when.strftime("%Y-%m-%d") != today:
                    continue  # 只收今天（台北時間）的標題
                title = clean_title(title, is_gnews)
                key = (src["id"], norm_key(title))
                if len(key[1]) < 6 or key in seen:
                    continue
                seen.add(key)
                item = {"source": src["id"], "title": title, "link": link,
                        "time": when.isoformat(timespec="minutes")}
                if est:
                    item["est"] = 1
                day["items"].append(item)
                added += 1
        added_total += added
        health["sources"].append({"id": src["id"], "name": src["name"], "ok": got > 0,
                                  "fetched": got, "added": added, "errors": errors})

    day["items"].sort(key=lambda it: it["time"])
    day["updated_at"] = now.isoformat(timespec="seconds")
    raw_path.write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (DATA / "health.json").write_text(json.dumps(health, ensure_ascii=False, indent=1), encoding="utf-8")

    cutoff = (now - timedelta(days=RAW_KEEP_DAYS)).strftime("%Y-%m-%d")
    for p in raw_dir.glob("*.json"):
        if p.stem < cutoff:
            p.unlink()

    ok = sum(1 for s in health["sources"] if s["ok"])
    print(f"[fetch] {today}: +{added_total} 則，當日累計 {len(day['items'])} 則；來源正常 {ok}/{len(health['sources'])}")
    for s in health["sources"]:
        if not s["ok"]:
            print(f"  ! {s['name']} 無資料：{'; '.join(s['errors']) or '0 則'}")
    return today


if __name__ == "__main__":
    fetch_all()
    sys.exit(0)

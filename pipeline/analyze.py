#!/usr/bin/env python3
"""把當日標題分群成議題、計算熱度與異常訊號，輸出 data/daily/<日期>.json。

只用 Python 標準函式庫，不需要斷詞套件：中文以「字元 bigram」做 TF-IDF，
關鍵詞用高頻 n-gram 找。所有門檻集中在下面的常數；分群門檻已用 2026-11-14 的真實標題校過一次。
"""
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TPE = timezone(timedelta(hours=8))

# ---- 可調參數 -------------------------------------------------------------
ASSIGN_T = 0.13        # 標題與議題中心的 cosine 相似度門檻
MERGE_T = 0.26         # 兩個議題合併的門檻
MAX_DF = 0.12          # 出現在超過 12% 標題的 bigram 視為無鑑別力
TOP_TOPICS = 30        # 輸出前幾大議題
MAX_HEADLINES = 60     # 每個議題最多保留幾則標題
SINGLE_SHARE = 0.60    # 單一媒體佔比達此值 → 「單一媒體主推」
LEAN_MIN = 10          # 有立場標記的報導至少幾則才計算立場落差
LEAN_GAP = 0.35        # 與當日基準差距達此值才提示
ANON_RATIO = 0.30      # 含匿名消息用語的標題佔比
BURST_WINDOW_MIN = 20  # 同步出稿的時間窗（分鐘）
BURST_MIN_SOURCES = 5
MATCH_T = 0.30         # 跨日議題比對門檻

ANON = re.compile(r"知情人士|消息人士|人士透露|人士指出|據傳|據了解|據悉|爆料|驚爆|踢爆|網傳|內幕|不具名|匿名|高層透露|私下透露|放話|傳將|傳已|傳遭|盛傳")
EXCL = re.compile(r"獨家|^獨／")
CJK = re.compile(r"[一-鿿]+")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9\-]+|\d{2,}")
STOP = set("快訊 獨家 最新 曝光 回應 表示 今天 今日 明天 網友 懶人包 一次看 直播 影片 更新 不斷更新 記者 報導 指出 強調 喊話 怒批 痛批 發聲".split())
LEAN_NAME = {"green": "偏綠", "blue": "偏藍"}


JUNK = re.compile(r"相關報導$|^影音$")
SUFFIX = re.compile(r"\s*(?:[|｜]\s*#.*|[|｜]\s*[^|｜]{0,20}(?:新聞|報導|頻道|NEWS)[^|｜]{0,24}|@\w+|[-－–—]\s*(?:娛樂|政治|社會|生活|國際|財經|體育|地方|兩岸|要聞|即時|新聞|健康|科技|旅遊|房產|股市|運動|影劇|全球|產經)\S{0,4})\s*$", re.I)


def tidy(title):
    """去掉媒體自己加的尾巴（頻道名、分類名）；回傳 None 表示這則不是新聞標題。"""
    for _ in range(3):
        new = SUFFIX.sub("", title).strip()
        if new == title:
            break
        title = new
    return None if JUNK.search(title) or len(title) < 6 else title


PREFIX = re.compile(r"^(?:[(（【\[][^)）】\]]{1,6}[)）】\]]\s*)?(?:[^\s／/》]{1,8}[／》]\s*)?(?:[\u4e00-\u9fff]{2,4}觀點[：:]\s*)?")


def title_key(title):
    """標題的比對鍵：去掉標點與空白。AI 合併提示用它記住「哪些標題屬於同一事件」。"""
    return re.sub(r"[\W_]+", "", title).lower()


def apply_merges(groups, items, date):
    """套用 AI 存下的合併提示（data/merges/<日期>.json）：含有同一組標題的群合併成一群。"""
    path = DATA / "merges" / f"{date}.json"
    if not path.exists():
        return groups
    hints = [set(g) for g in json.loads(path.read_text(encoding="utf-8")).get("groups", [])]
    keys = [title_key(it["title"]) for it in items]
    parent = list(range(len(groups)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for hint in hints:
        hit = [gi for gi, g in enumerate(groups) if sum(1 for i in g if keys[i] in hint) >= min(2, len(g))
               and sum(1 for i in g if keys[i] in hint) >= 0.3 * len(g)]
        for gi in hit[1:]:
            parent[find(gi)] = find(hit[0])
    merged = defaultdict(list)
    for gi, g in enumerate(groups):
        merged[find(gi)].extend(g)
    return [sorted(g) for g in merged.values()]


SEG = re.compile(r"\s*[-－–—|｜]\s*([^-－–—|｜]{0,14})$")


def strip_boilerplate(items):
    """同一媒體當天有 3 則以上標題用同樣的結尾（「- 上市櫃」「| 全球財經」這類欄目名），就把那段結尾去掉。"""
    def tail(t):
        m = SEG.search(t)
        return m.group(1).strip() if m else None
    for _ in range(3):
        count = Counter((it["source"], tail(it["title"])) for it in items)
        changed = False
        for it in items:
            tl = tail(it["title"])
            if tl is not None and count[(it["source"], tl)] >= 3:
                new = SEG.sub("", it["title"]).strip()
                if len(new) >= 6:
                    it["title"], changed = new, True
        if not changed:
            break
    return items


def runs(title):
    """分析時略過「NBA／」「快訊／」「（影）」「某某觀點：」這類欄目前綴，避免同欄目的文章被當成同一議題。"""
    return CJK.findall(PREFIX.sub("", title, count=1))


def tokens(title):
    out = []
    for r in runs(title):
        out.extend(r[i:i + 2] for i in range(len(r) - 1))
    out.extend(w.lower() for w in LATIN.findall(PREFIX.sub("", title, count=1)))
    return out


def ngrams(title, lo=2, hi=6):
    out = set()
    for r in runs(title):
        for n in range(lo, hi + 1):
            for i in range(len(r) - n + 1):
                out.add(r[i:i + n])
    out.update(w for w in LATIN.findall(title) if len(w) >= 3)
    return out


def vectorize(items):
    docs = [Counter(tokens(it["title"])) for it in items]
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())
    vecs = []
    for d in docs:
        v = {t: (1 + math.log(c)) * math.log(n / df[t]) for t, c in d.items() if 2 <= df[t] <= max(3, MAX_DF * n)}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cluster(vecs):
    """單趟分群：每則標題併入最相近的議題中心，否則自成一群；最後再合併相近的群。"""
    cents, norms2, members = [], [], []
    index = defaultdict(set)
    for i, v in enumerate(vecs):
        dots = defaultdict(float)
        for t, w in v.items():
            for c in index[t]:
                dots[c] += w * cents[c][t]
        best, best_s = -1, ASSIGN_T
        for c, d in dots.items():
            s = d / math.sqrt(norms2[c])
            if s >= best_s:
                best, best_s = c, s
        if best < 0:
            cents.append(dict(v)); norms2.append(1.0 if v else 1e-9); members.append([i])
            for t in v:
                index[t].add(len(cents) - 1)
        else:
            norms2[best] += 2 * dots[best] + 1.0
            cen = cents[best]
            for t, w in v.items():
                cen[t] = cen.get(t, 0.0) + w
                index[t].add(best)
            members[best].append(i)

    parent = list(range(len(cents)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(len(cents)):
        if len(members[a]) < 2:
            continue
        dots = defaultdict(float)
        for t, w in cents[a].items():
            for b in index[t]:
                if b > a and len(members[b]) >= 2:
                    dots[b] += w * cents[b][t]
        for b, d in dots.items():
            if d / math.sqrt(norms2[a] * norms2[b]) >= MERGE_T:
                parent[find(b)] = find(a)
    groups = defaultdict(list)
    for c in range(len(cents)):
        groups[find(c)].extend(members[c])
    return [sorted(g) for g in groups.values()]


def is_fragment(g, titles):
    """g 的左或右幾乎總是接同一個字 → 它只是更長詞語被切斷的一段。"""
    left, right, total = Counter(), Counter(), 0
    for t in titles:
        for r in runs(t):
            k = r.find(g)
            while k >= 0:
                total += 1
                left[r[k - 1] if k > 0 else ""] += 1
                right[r[k + len(g)] if k + len(g) < len(r) else ""] += 1
                k = r.find(g, k + 1)
    if not total:
        return False  # 英數詞
    for side in (left, right):
        ch, c = side.most_common(1)[0]
        if ch and c / total >= 0.8:
            return True
    return False


def keyphrases(idx, grams, gdf, n_all, titles, k=5):
    size = len(idx)
    df = Counter()
    for i in idx:
        df.update(grams[i])
    need = max(2, math.ceil(0.25 * size))
    cand = {g: c for g, c in df.items() if c >= need and g not in STOP}
    cand = {g: c for g, c in cand.items() if not is_fragment(g, titles)}
    scored = sorted(cand, key=lambda g: -cand[g] * math.log(n_all / gdf[g] + 1) * math.sqrt(len(g)))
    out = []
    for g in scored:
        if any(g in o or o in g for o in out):
            continue
        out.append(g)
        if len(out) == k:
            break
    return out, {g: cand[g] for g in out}


def centroid(idx, vecs, top=30):
    c = defaultdict(float)
    for i in idx:
        for t, w in vecs[i].items():
            c[t] += w
    norm = math.sqrt(sum(x * x for x in c.values())) or 1.0
    full = {t: x / norm for t, x in c.items()}
    return full, dict(sorted(full.items(), key=lambda kv: -kv[1])[:top])


def cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def parse_t(s):
    return datetime.fromisoformat(s)


def pick_digest(g, vecs, full, items, k=3):
    """挑 2–3 則最能代表議題、且彼此角度不同（內容不重複、盡量不同媒體）的標題，當作「新聞在講什麼」。"""
    cand = [i for i in sorted(g, key=lambda i: -cos(vecs[i], full))[:30] if len(items[i]["title"]) >= 8]
    chosen = []
    while len(chosen) < k and cand:
        def score(i):
            red = max((cos(vecs[i], vecs[j]) for j in chosen), default=0.0)
            same = sum(1 for j in chosen if items[j]["source"] == items[i]["source"])
            return cos(vecs[i], full) - 0.8 * red - 0.15 * same
        best = max(cand, key=score)
        cand.remove(best)
        chosen.append(best)
    return [{"s": items[i]["source"], "t": items[i]["title"]} for i in chosen]


def find_signals(idx, items, src_meta, base_share, lean_base):
    size = len(idx)
    sig = []
    by_src = Counter(items[i]["source"] for i in idx)
    top_src, top_n = by_src.most_common(1)[0]
    name = lambda s: src_meta[s]["name"]

    # 1) 單一媒體主推
    share = top_n / size
    if size >= 6 and share >= SINGLE_SHARE and base_share.get(top_src, 0) <= 0.30:
        sig.append({"type": "single", "level": "high" if share >= 0.8 else "mid",
                    "title": f"{name(top_src)}主推",
                    "detail": f"{size} 則報導中 {top_n} 則來自{name(top_src)}（{share:.0%}），該媒體今日整體佔比只有 {base_share.get(top_src, 0):.0%}。其他媒體少有跟進。"})

    # 2) 立場落差
    lean = Counter(src_meta[items[i]["source"]].get("lean", "unknown") for i in idx)
    g, b = lean["green"], lean["blue"]
    if g + b >= LEAN_MIN and lean_base is not None:
        gs = g / (g + b)
        for side, s, base in (("green", gs, lean_base), ("blue", 1 - gs, 1 - lean_base)):
            if s - base >= LEAN_GAP:
                other = "blue" if side == "green" else "green"
                sig.append({"type": "lean", "level": "high" if s >= 0.9 else "mid",
                            "title": f"{LEAN_NAME[side]}媒體報導明顯較多",
                            "detail": f"有立場標記的 {g + b} 則報導中，{LEAN_NAME[side]}媒體佔 {s:.0%}，今日基準為 {base:.0%}；{LEAN_NAME[other]}媒體相對冷處理。"})

    # 3) 匿名／未具名消息用語
    anon = [i for i in idx if ANON.search(items[i]["title"])]
    if len(anon) >= 3 and len(anon) / size >= ANON_RATIO:
        words = Counter(m for i in anon for m in ANON.findall(items[i]["title"]))
        sig.append({"type": "anon", "level": "mid",
                    "title": "大量未具名消息用語",
                    "detail": f"{len(anon)} 則標題（{len(anon) / size:.0%}）使用「{'」「'.join(w for w, _ in words.most_common(3))}」等用語，消息來源不明確。"})

    # 4) 獨家起頭後多家跟進
    order = sorted(idx, key=lambda i: items[i]["time"])
    first = order[0]
    if EXCL.search(items[first]["title"]) and len(by_src) >= 4:
        sig.append({"type": "exclusive", "level": "low",
                    "title": f"由{name(items[first]['source'])}獨家起頭",
                    "detail": f"最早一則為{name(items[first]['source'])}的獨家（{items[first]['time'][11:16]}），之後 {len(by_src) - 1} 家媒體跟進。"})

    # 5) 多家同步出稿
    firsts = {}
    for i in order:
        if items[i].get("est"):
            continue
        firsts.setdefault(items[i]["source"], parse_t(items[i]["time"]))
    ts = sorted(firsts.values())
    best = 0
    for a in range(len(ts)):
        n = sum(1 for t in ts[a:] if t - ts[a] <= timedelta(minutes=BURST_WINDOW_MIN))
        if n > best:
            best, best_at = n, ts[a]
    if best >= BURST_MIN_SOURCES and best >= 0.6 * len(by_src):
        sig.append({"type": "burst", "level": "low",
                    "title": f"{best} 家媒體同步出稿",
                    "detail": f"{best} 家媒體在 {best_at.strftime('%H:%M')} 起 {BURST_WINDOW_MIN} 分鐘內各自發出第一則報導，常見於記者會、新聞稿或突發事件。"})
    return sig


SENS = re.compile(r"[！!]|驚爆|怒批|痛批|痛轟|怒轟|狂酸|開嗆|嗆爆|傻眼|吵翻|炸鍋|打臉|超扯|竟然|嚇呆|嚇壞|震撼|崩潰|暴怒|看傻|慘了|氣炸|轟動|瘋傳|全網|網炸")
HOT_N = 10          # 「熱門議題」指前幾大
FOLLOW_SOURCES = 3  # 第幾家媒體跟進才算「擴散」


def media_metrics(scored, items, src_count):
    """各媒體的報導風格指標（只看標題，不靠 AI）：
    hot   跟熱門程度：自家標題有多少比例在報前 10 大議題（低＝走自己的議程）
    first 搶先報：前 10 大議題中，有幾個是由這家最先發出標題
    sens  聳動用語：標題含驚嘆號或情緒性字眼的比例
    anon  匿名消息：標題含「知情人士」「據傳」等不具名來源用語的比例
    另回傳前 10 大議題的「擴散速度」中位數：從第一則到第 3 家媒體跟進的分鐘數。"""
    hot_idx, first, gaps = set(), Counter(), []
    for _, g in scored[:HOT_N]:
        hot_idx.update(g)
        order = sorted(g, key=lambda i: items[i]["time"])
        first[items[order[0]]["source"]] += 1
        seen, t0 = set(), parse_t(items[order[0]]["time"])
        for i in order:
            seen.add(items[i]["source"])
            if len(seen) >= FOLLOW_SOURCES:
                gaps.append(round((parse_t(items[i]["time"]) - t0).total_seconds() / 60))
                break
    per = defaultdict(lambda: {"hot": 0, "sens": 0, "anon": 0})
    for i, it in enumerate(items):
        m = per[it["source"]]
        m["hot"] += i in hot_idx
        m["sens"] += bool(SENS.search(it["title"]))
        m["anon"] += bool(ANON.search(it["title"]))
    out = []
    for s, c in src_count.most_common():
        m = per[s]
        out.append({"id": s, "count": c, "hot": round(m["hot"] / c, 3), "first": first.get(s, 0),
                    "sens": round(m["sens"] / c, 3), "anon": round(m["anon"] / c, 3)})
    gaps.sort()
    follow = gaps[len(gaps) // 2] if gaps else None
    return out, follow


def load_history(date, days=6):
    out = []
    d0 = datetime.strptime(date, "%Y-%m-%d")
    for k in range(1, days + 1):
        p = DATA / "daily" / f"{(d0 - timedelta(days=k)).strftime('%Y-%m-%d')}.json"
        out.append(json.loads(p.read_text(encoding="utf-8")) if p.exists() else None)
    return out  # [昨天, 前天, ...]


def analyze(date):
    raw = json.loads((DATA / "raw" / f"{date}.json").read_text(encoding="utf-8"))
    items = []
    for it in raw["items"]:
        t = tidy(it["title"])
        if t:
            items.append({**it, "title": t})
    items = strip_boilerplate(items)
    cfg = raw.get("sources") or json.loads((ROOT / "pipeline" / "sources.json").read_text(encoding="utf-8"))["sources"]
    src_meta = {s["id"]: s for s in cfg}
    n = len(items)
    if n == 0:
        print(f"[analyze] {date}: 沒有標題，略過")
        return None

    vecs = vectorize(items)
    grams = [ngrams(it["title"]) for it in items]
    gdf = Counter()
    for g in grams:
        gdf.update(g)
    src_count = Counter(it["source"] for it in items)
    base_share = {s: c / n for s, c in src_count.items()}
    lean_all = Counter(src_meta[it["source"]].get("lean", "unknown") for it in items)
    lean_base = lean_all["green"] / (lean_all["green"] + lean_all["blue"]) if lean_all["green"] and lean_all["blue"] else None

    groups = [g for g in apply_merges(cluster(vecs), items, date) if len(g) >= 3]
    scored = []
    for g in groups:
        ns = len({items[i]["source"] for i in g})
        if ns < 2 and len(g) < 6:
            continue  # 單一媒體的小群不算議題；大群留著當「主推」訊號
        scored.append((len(g) * (1 + math.log(ns)), g))
    scored.sort(key=lambda x: -x[0])
    scored = scored[:TOP_TOPICS]
    max_heat = scored[0][0] if scored else 1.0

    history = load_history(date)
    topics, all_signals, kw_total = [], [], Counter()
    for rank, (heat, g) in enumerate(scored, 1):
        full, vec = centroid(g, vecs)
        kws, kw_df = keyphrases(g, grams, gdf, n, [items[i]["title"] for i in g])
        rep = max(g, key=lambda i: cos(vecs[i], full))
        by_src = Counter(items[i]["source"] for i in g)
        hours = [0] * 24
        for i in g:
            hours[int(items[i]["time"][11:13])] += 1
        share = len(g) / n

        # 跨日比對：往回逐日找同一議題
        trend, days_running, alive = [], 1, True
        for h in history:
            m = None
            if h:
                cands = [(cos(vec, t.get("_v", {})), t) for t in h["topics"]]
                cands = [c for c in cands if c[0] >= MATCH_T]
                if cands:
                    m = max(cands, key=lambda c: c[0])[1]
            trend.append({"date": h["date"] if h else None, "share": round(m["share"], 4) if m else 0})
            if m and alive:
                days_running += 1
            else:
                alive = False
        prev = trend[0]["share"] if trend else 0
        if not history or history[0] is None:
            status = "—"
        elif prev == 0:
            status = "新議題"
        elif share >= prev * 1.5:
            status = "升溫"
        elif share <= prev * 0.67:
            status = "降溫"
        else:
            status = "延燒"

        signals = find_signals(g, items, src_meta, base_share, lean_base)
        if status == "新議題" and rank <= 5:
            signals.append({"type": "spike", "level": "low", "title": "今日突然竄起",
                            "detail": f"昨天沒有對應議題，今天直接進入熱度第 {rank} 名。"})
        order = sorted(g, key=lambda i: items[i]["time"])
        topic = {
            "id": f"t{rank}", "rank": rank,
            "label": "・".join(kws[:2]) if kws else re.split(r"[\s，、：:｜|！？]", items[rep]["title"])[0][:14],
            "keywords": kws, "rep": items[rep]["title"],
            "size": len(g), "n_sources": len(by_src),
            "heat": round(100 * heat / max_heat), "share": round(share, 4),
            "status": status, "days": days_running,
            "trend": list(reversed(trend)) + [{"date": date, "share": round(share, 4)}],
            "digest": pick_digest(g, vecs, full, items),
            "first": items[order[0]]["time"][11:16], "peak": hours.index(max(hours)),
            "by_source": dict(by_src), "hours": hours, "signals": signals,
            "headlines": [{"s": items[i]["source"], "t": items[i]["title"], "l": items[i]["link"], "h": items[i]["time"][11:16]}
                          for i in order[:MAX_HEADLINES]],
            "_v": {t: round(w, 4) for t, w in vec.items()},
        }
        topics.append(topic)
        for s in signals:
            all_signals.append({**s, "topic": topic["id"], "label": topic["label"]})
        for k in kws:
            kw_total[k] += kw_df[k]

    metrics, follow = media_metrics(scored, items, src_count)
    level_rank = {"high": 0, "mid": 1, "low": 2}
    all_signals.sort(key=lambda s: (level_rank[s["level"]], int(s["topic"][1:])))
    in_topics = sum(t["size"] for t in topics)
    out = {
        "date": date, "updated_at": raw.get("updated_at") or datetime.now(TPE).isoformat(timespec="seconds"),
        "mode": "demo" if raw.get("demo") else "live",
        "totals": {"headlines": n, "sources": len(src_count), "topics": len(topics),
                   "top3_share": round(sum(t["size"] for t in topics[:3]) / n, 4),
                   "in_topics_share": round(in_topics / n, 4), "follow_median": follow,
                   "sensational_share": round(sum(1 for it in items if SENS.search(it["title"])) / n, 4)},
        "sources": [{"id": s, "name": src_meta[s]["name"], "lean": src_meta[s].get("lean", "unknown"),
                     "kind": src_meta[s].get("kind", ""), "count": c} for s, c in src_count.most_common()],
        "topics": topics, "signals": all_signals,
        "keywords": [{"text": k, "n": c} for k, c in kw_total.most_common(40)],
        "media": metrics,
    }

    out_dir = DATA / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{date}.json"
    prev_ai = None
    if path.exists():
        prev_ai = json.loads(path.read_text(encoding="utf-8"))
    carry_ai(out, prev_ai)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_index()
    print(f"[analyze] {date}: {n} 則標題 → {len(topics)} 個議題，{len(all_signals)} 個訊號")
    return path


def carry_ai(out, prev):
    """同一天重跑時，沿用上一版 AI 對相同議題的註解，避免每小時都呼叫 API。

    議題編號（t1、t2…）是排名，每次重跑都可能變，所以用議題向量比對新舊議題。"""
    if not prev:
        return
    if prev.get("ai_meta"):
        out["ai_meta"] = prev["ai_meta"]
    old_new = {}
    for t in out["topics"]:
        best = max(prev.get("topics", []), key=lambda o: cos(t["_v"], o.get("_v", {})), default=None)
        if best and cos(t["_v"], best.get("_v", {})) >= 0.6:
            old_new.setdefault(best["id"], t["id"])
            if best.get("ai"):
                t["ai"] = best["ai"]
    brief = prev.get("ai_brief")
    if brief:
        items = [{**it, "id": old_new.get(it.get("id"))} for it in brief.get("items", [])]
        out["ai_brief"] = {**brief, "items": items}
    rep = prev.get("ai_report")
    if rep:  # 報告段落連到的議題編號也要換成新的；對不到就不連結
        out["ai_report"] = {**rep, "sections": [{**sec, "topic": old_new.get(sec.get("topic"))} for sec in rep.get("sections", [])]}


def write_index():
    days = sorted(p.stem for p in (DATA / "daily").glob("*.json"))
    (DATA / "index.json").write_text(json.dumps({"dates": days, "latest": days[-1] if days else None}), encoding="utf-8")


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TPE).strftime("%Y-%m-%d")
    analyze(date)

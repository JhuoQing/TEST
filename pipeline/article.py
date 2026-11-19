#!/usr/bin/env python3
"""抓新聞內文（只給熱門事件用）。只用 Python 標準函式庫。

原則：
- 遵守 robots.txt；讀不到 robots.txt（連線失敗）時視為不允許，直接略過該網站。
- 同一網站兩次請求至少間隔 HOST_GAP 秒，並以本站的 User-Agent 表明身分。
- 內文只回傳給呼叫端在記憶體中使用，這個模組不寫任何檔案；
  網站上只會出現 AI 用自己的話寫的摘要，以及連回原文的連結。
- Google News 的轉址連結會先解碼成媒體原始網址（解不開就略過那一則）。
"""
import base64
import gzip
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

UA = "Mozilla/5.0 (compatible; tw-opinion-dashboard/1.0; +https://github.com/JhuoQing/TEST)"
BOT = "tw-opinion-dashboard"
HOST_GAP = 1.5          # 同一網站請求間隔（秒）
MAX_BYTES = 3 * 1024 * 1024
MAX_CHARS = 2400        # 每篇內文最多保留幾個字給 AI（新聞重點通常在前段）
MIN_CJK = 120           # 少於這個中文字數視為沒抓到內文（付費牆、影音頁等）

_last_hit = {}
_robots = {}


def _wait(host):
    gap = HOST_GAP - (time.time() - _last_hit.get(host, 0))
    if gap > 0:
        time.sleep(gap)
    _last_hit[host] = time.time()


def _decode(raw, headers):
    if headers.get("Content-Encoding", "").lower() == "gzip":
        raw = gzip.decompress(raw)
    m = re.search(r"charset=([\w-]+)", headers.get("Content-Type", ""), re.I) or \
        re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4000], re.I)
    enc = m.group(1) if m else "utf-8"
    enc = enc.decode() if isinstance(enc, bytes) else enc
    try:
        return raw.decode(enc, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def http(url, data=None, headers=None, timeout=20):
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError("只允許 http(s)")
    host = urllib.parse.urlsplit(url).netloc
    _wait(host)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9",
                                                          "Accept-Encoding": "gzip", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("回應超過大小上限")
        return r.geturl(), _decode(raw, r.headers)


def allowed(url):
    parts = urllib.parse.urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _, text = http(base + "/robots.txt", timeout=10)
            rp.parse(text.splitlines())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True   # 沒有 robots.txt（404 等）依慣例視為允許
        except Exception:
            rp = None                 # 連不上就保守略過
        _robots[base] = rp
    rp = _robots[base]
    return bool(rp) and rp.can_fetch(BOT, url)


# ---- Google News 轉址解碼 ----------------------------------------------------
def _gnews_id(url):
    m = re.match(r"https://news\.google\.com/(?:rss/)?articles/([^?/#]+)", url)
    return m.group(1) if m else None


def resolve(url):
    """把 Google News 轉址連結換成媒體原始網址；不是 Google News 連結就原樣回傳。失敗回傳 None。"""
    gid = _gnews_id(url)
    if not gid:
        return url
    # 舊格式：網址直接藏在 base64 裡
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
        m = re.search(rb"https?://[\x21-\x7e]+", raw)
        if m and b"AU_yqL" not in raw[:12]:
            return m.group(0).decode()
    except Exception:
        pass
    # 新格式：先取頁面上的簽章與時間戳，再呼叫 batchexecute 換回原始網址
    try:
        _, page = http(f"https://news.google.com/articles/{gid}", timeout=15)
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            return None
        inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                                           "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts.group(1)), sg.group(1)],
                           separators=(",", ":"))
        body = urllib.parse.urlencode({"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]], separators=(",", ":"))}).encode()
        _, text = http("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body,
                       headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}, timeout=15)
        payload = json.loads(text.split("\n\n", 1)[1])
        for row in payload:
            if isinstance(row, list) and len(row) > 2 and row[1] == "Fbv4je" and row[2]:
                out = json.loads(row[2])[1]
                return out if isinstance(out, str) and out.startswith("http") else None
    except Exception:
        return None
    return None


# ---- 內文擷取 ----------------------------------------------------------------
CJK = re.compile(r"[一-鿿]")
NOISE = re.compile(r"延伸閱讀|看更多|更多新聞|相關新聞|訂閱|下載.{0,6}APP|加入.{0,6}(LINE|好友)|按讚|追蹤我們|版權所有|©|不得轉載|點我|請繼續往下閱讀|廣告|責任編輯|圖／|圖/|照片／|（中央社記者.{0,12}電）$")
CONTAINER = {"article", "div", "section", "main"}
SKIP = {"script", "style", "noscript", "svg", "figure", "figcaption", "aside", "nav", "footer", "header", "form", "button"}
VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area", "base", "col", "embed", "param", "track"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.skip, self.in_p = [], 0, None
        self.buf, self.groups, self.ld, self.in_ld = [], {}, [], False

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        a = dict(attrs)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self.in_ld = True
            self.ld.append("")
        if tag in SKIP:
            self.skip += 1
        sig = None
        if tag in CONTAINER:
            sig = f"{tag}#{a.get('id', '')}.{a.get('class', '')}.{a.get('itemprop', '')}.{len(self.stack)}"
        self.stack.append((tag, sig))
        if tag == "p" and self.in_p is not None:  # 沒關閉的 <p> 遇到下一個 <p>，先收起來
            self._flush()
        if tag == "p" and not self.skip:
            self.in_p = next((s for _, s in reversed(self.stack) if s), "root")
            self.buf = []

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag == "script":
            self.in_ld = False
        while self.stack:
            t, _ = self.stack.pop()
            if t in SKIP:
                self.skip = max(0, self.skip - 1)
            if t == "p" and self.in_p is not None:
                self._flush()
            if t == tag:
                break

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.groups.setdefault(self.in_p, []).append(text)
        self.in_p, self.buf = None, []

    def handle_data(self, data):
        if self.in_ld:
            self.ld[-1] += data
        elif self.in_p is not None and not self.skip:
            self.buf.append(data)


def _ld_body(blobs):
    def walk(x):
        if isinstance(x, dict):
            b = x.get("articleBody")
            if isinstance(b, str) and len(CJK.findall(b)) >= MIN_CJK:
                return b
            for v in x.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(x, list):
            for v in x:
                r = walk(v)
                if r:
                    return r
        return None
    for blob in blobs:
        try:
            r = walk(json.loads(blob.strip()))
        except Exception:
            continue
        if r:
            return html.unescape(re.sub(r"<[^>]+>", " ", r))
    return None


def clean(paras):
    out = []
    for p in paras:
        p = re.sub(r"\s+", " ", p).strip()
        if len(CJK.findall(p)) < 8 or (NOISE.search(p) and len(p) < 60):
            continue
        if p not in out:
            out.append(p)
    return "\n".join(out)


def extract(page):
    """回傳內文純文字；抓不到回傳 None。先找 JSON-LD 的 articleBody，再找 <p> 最集中的區塊。"""
    ex = _Extractor()
    try:
        ex.feed(page)
    except Exception:
        pass
    body = _ld_body(ex.ld)
    if body:
        body = clean(re.split(r"\n+|(?<=。)\s+", body))
    else:
        best = max(ex.groups.values(), key=lambda ps: sum(len(CJK.findall(p)) for p in ps), default=[])
        body = clean(best)
    if not body or len(CJK.findall(body)) < MIN_CJK:
        return None
    return body[:MAX_CHARS]


def fetch_article(link):
    """回傳 {"url": 原始網址, "body": 內文} 或 {"error": 原因}。"""
    url = resolve(link)
    if not url:
        return {"error": "無法解析 Google News 連結"}
    if not allowed(url):
        return {"error": "robots.txt 不允許或無法讀取"}
    try:
        final, page = http(url)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:120]}
    body = extract(page)
    if not body:
        return {"error": "找不到內文（可能是付費牆或影音頁）"}
    return {"url": final, "body": body}


# ---- 不需要 AI 的內文訊號 ----------------------------------------------------
ANON = re.compile(r"知情人士|消息人士|人士透露|人士指出|據了解|據悉|據傳|不具名|匿名|高層透露|私下透露|網傳|放話")


def shingles(text, k=6):
    t = re.sub(r"[\W_]+", "", text)
    return {t[i:i + k] for i in range(max(0, len(t) - k + 1))}


def similarity(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))  # 用較短那篇當分母：一篇整段照抄另一篇也抓得到


def anon_count(text):
    return len(ANON.findall(text))


if __name__ == "__main__":
    import sys
    for u in sys.argv[1:]:
        r = fetch_article(u)
        print(u, "→", r.get("url"), r.get("error") or f"{len(r['body'])} 字\n{r['body'][:300]}")

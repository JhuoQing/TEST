#!/usr/bin/env python3
"""產生 7 天的「示範資料」，讓網站在接上真實 RSS 前就能預覽，也用來測試分析流程。

媒體（示範媒體 A–H）與所有標題都是虛構的，不對應任何真實媒體或事件。
用法：python pipeline/make_demo.py [結束日期 YYYY-MM-DD]
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze  # noqa: E402

DATA = analyze.DATA
TPE = timezone(timedelta(hours=8))

SOURCES = [
    {"id": "A", "name": "示範媒體A", "kind": "報系", "lean": "green"},
    {"id": "B", "name": "示範媒體B", "kind": "電視台", "lean": "green"},
    {"id": "C", "name": "示範媒體C", "kind": "報系", "lean": "blue"},
    {"id": "D", "name": "示範媒體D", "kind": "電視台", "lean": "blue"},
    {"id": "E", "name": "示範媒體E", "kind": "公共媒體", "lean": "neutral"},
    {"id": "F", "name": "示範媒體F", "kind": "網路媒體", "lean": "unknown"},
    {"id": "G", "name": "示範媒體G", "kind": "網路媒體", "lean": "unknown"},
    {"id": "H", "name": "示範媒體H", "kind": "週刊", "lean": "unknown"},
]
ALL = "ABCDEFGH"

# 每個議題：近 7 天每日則數（最後一格是結束日）、由哪些媒體報、開始時間、標題零件
TOPICS = [
    dict(days=[0, 18, 30, 42, 50, 58, 70], who=ALL, start=7,
         heads=["電價調漲方案出爐", "電價審議會拍板調漲", "下月起電價調漲", "電價調漲確定", "電價調漲幅度公布"],
         tails=["民生用電漲幅一次看", "工業用電大戶衝擊最大", "小吃店喊吃不消", "主管機關說明理由", "議員要求重新審議",
                "超商咖啡恐跟漲", "學者：反映成本合理", "住宅千度以下不調", "產業公會盼緩漲", "物價連動效應受關注"]),
    dict(days=[0, 0, 0, 0, 0, 0, 62], who=ALL, start=15, burst=True,
         heads=["颱風海警發布", "颱風逼近北海市", "颱風假明天放不放", "颱風路徑再修正", "颱風停班停課"],
         tails=["北海市晚間八點宣布", "各縣市停班停課一覽", "山區慎防豪雨", "交通異動資訊整理", "市場菜價先漲",
                "航班大亂旅客滯留", "氣象單位最新說明", "風雨最大時段出爐", "沿海低窪地區預防性撤離"]),
    dict(days=[0, 0, 6, 14, 20, 26, 40], who="CCCCDDDDFGE", start=9, anon=0.5,
         heads=["北海市府標案爭議", "北海市府標案疑雲", "北海市標案風波", "市府標案爭議延燒"],
         tails=["知情人士：評選過程有異", "消息人士透露關鍵會議", "據了解承辦人已調職", "議員踢爆得標廠商背景", "市府回應一切合法",
                "評選委員名單受質疑", "議會要求調閱文件", "內幕曝光引發討論", "據悉檢調已掌握資料", "廠商否認特殊關係"]),
    dict(days=[0, 0, 0, 0, 0, 4, 34], who="FFFFFFFFFFG", start=6, anon=0.7, excl=True,
         heads=["星河科技裁員傳聞", "星河科技傳將大裁員", "星河科技人事地震"],
         tails=["員工爆料部門整併", "據傳規模上看千人", "知情人士：下週公布", "內部信件曝光", "網傳名單流出",
                "公司尚未回應", "爆料指高層已離職", "據了解資遣方案討論中", "股價盤後走弱", "匿名員工說法曝光"]),
    dict(days=[30, 34, 28, 22, 26, 20, 24], who="AAAABBBBEFG", start=8,
         heads=["健保費率調整案", "健保費率明年調漲", "健保費率審議"],
         tails=["主管機關：確保財務穩定", "醫界團體表態支持", "保費試算一次看", "財務缺口數字公布", "病友團體盼配套",
                "學者建議擴大費基", "審議會下週開會", "雇主負擔增加幅度", "部分負擔同步檢討"]),
    dict(days=[22, 20, 26, 30, 24, 28, 30], who=ALL, start=10,
         heads=["晶片出口新規上路", "晶片出口管制新規", "半導體出口新規"],
         tails=["業者盤點受影響產品", "設備廠訂單能見度受關注", "法人看後市", "主管機關召集業者說明", "供應鏈調整布局",
                "外資報告出爐", "相關個股表現分歧", "公會提出三點建議"]),
    dict(days=[10, 12, 8, 14, 18, 22, 26], who=ALL, start=9,
         heads=["房貸新制上路", "房貸限縮新制", "第二戶房貸成數下修"],
         tails=["銀行核貸轉趨保守", "首購族影響一次看", "建商推案放緩", "房仲：買氣觀望", "預售屋交屋潮受關注",
                "專家建議先試算", "央行說明政策目標", "中古屋議價空間擴大"]),
    dict(days=[0, 0, 0, 16, 28, 36, 22], who=ALL, start=18,
         heads=["職棒冠軍賽", "職棒總冠軍戰", "冠軍賽第六戰"],
         tails=["門票開賣秒殺", "先發投手預告", "延長賽再見安打", "球迷應援擠爆球場", "交通接駁資訊",
                "封王遊行路線曝光", "年度最有價值球員出爐", "教練賽後談調度"]),
    dict(days=[14, 10, 6, 0, 8, 16, 18], who=ALL, start=11,
         heads=["進口蛋品檢驗", "進口蛋品抽驗結果", "蛋品檢驗不合格"],
         tails=["主管機關公布批號", "通路全面下架", "業者聲明全數退運", "早餐店改用國產蛋", "消費者退貨方式",
                "專家說明風險", "源頭管理將加強"]),
    dict(days=[8, 6, 10, 12, 6, 8, 12], who=ALL, start=7,
         heads=["捷運環狀線延伸段通車", "環狀線延伸段試營運", "捷運環狀線新站啟用"],
         tails=["首日人潮湧現", "免費試乘一個月", "轉乘資訊懶人包", "沿線房價受關注", "通勤時間省二十分鐘",
                "市長視察站體", "周邊公車路線調整"]),
]

PLACES = ["北海市", "東山縣", "南灣市", "西濱縣", "中原市", "青田鄉", "河口鎮", "松嶺區", "港都區", "雲平市", "石門里", "竹圍區"]
NOISE = ["清晨民宅火警幸無人傷", "路口車禍機車騎士送醫", "百貨週年慶開跑", "夜市新攤位引排隊人潮", "國小運動會熱鬧登場",
         "老屋翻新成咖啡館", "公園落羽松轉紅", "警方破獲詐騙機房", "水管破裂路面積水", "馬拉松週日開跑交管",
         "圖書館新館啟用", "流浪動物認養活動", "農會展售會買氣旺", "社區長者共餐滿週年", "燈會主燈設計亮相",
         "游泳池整修延後開放", "公車新路線下週上路", "傳統市場改建動工", "高中生獲國際發明獎", "廟會遶境交通管制",
         "自行車道串聯完工", "淨灘活動清出百公斤垃圾", "古蹟修復工程啟動", "跨年晚會卡司公布", "稻田彩繪吸引遊客",
         "停車費率明年調整", "診所流感疫苗開打", "溫泉季活動起跑", "地方創生市集登場", "路樹修剪引發討論",
         "漁港拍賣價創新高", "咖啡評鑑冠軍出爐", "登山步道封閉整修", "寵物公園正式啟用", "文創園區週末市集",
         "路燈汰換節能工程", "社宅抽籤結果公布", "花海節週末登場", "校園午餐新菜單", "電動機車補助加碼"]


def gen_day(date, col, rng):
    items, used = [], set()

    def add(src, title, hour_lo, hour_hi, minute=None):
        key = (src, title)
        if key in used:
            return
        used.add(key)
        h = rng.randint(hour_lo, min(hour_hi, 23))
        m = rng.randint(0, 59) if minute is None else minute
        t = datetime(date.year, date.month, date.day, h, m, tzinfo=TPE)
        items.append({"source": src, "title": title, "link": "", "time": t.isoformat(timespec="minutes")})

    for tp in TOPICS:
        n = tp["days"][col]
        if not n:
            continue
        start = tp["start"]
        if tp.get("excl"):
            add("F", f"獨家／{tp['heads'][0]} {tp['tails'][0]}", start, start, 5)
        if tp.get("burst"):  # 六家在十分鐘內同步出稿
            for k, s in enumerate("ABCDEG"):
                add(s, f"{tp['heads'][0]} {tp['tails'][k]}", start, start, 30 + k)
        tries = 0
        while sum(1 for it in items if it["title"].split(" ")[0].replace("獨家／", "") in tp["heads"]) < n and tries < n * 20:
            tries += 1
            head, tail = rng.choice(tp["heads"]), rng.choice(tp["tails"])
            if tp.get("anon") and rng.random() > tp["anon"] and any(w in tail for w in ("知情", "消息人士", "據", "爆料", "踢爆", "網傳", "內幕", "匿名")):
                continue
            add(rng.choice(tp["who"]), f"{head} {tail}", start, 23)
    for src in ALL:
        for _ in range(rng.randint(26, 36)):
            add(src, f"{rng.choice(PLACES)}{rng.choice(NOISE)}", 6, 23)
    items.sort(key=lambda it: it["time"])
    return items


def main(end):
    rng = random.Random(20261114)
    end_d = datetime.strptime(end, "%Y-%m-%d")
    (DATA / "raw").mkdir(parents=True, exist_ok=True)
    for col in range(7):
        d = end_d - timedelta(days=6 - col)
        date = d.strftime("%Y-%m-%d")
        raw = {"date": date, "demo": True, "sources": SOURCES, "items": gen_day(d, col, rng),
               "updated_at": datetime(d.year, d.month, d.day, 23, 30, tzinfo=TPE).isoformat(timespec="seconds")}
        (DATA / "raw" / f"{date}.json").write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        analyze.analyze(date)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.now(TPE).strftime("%Y-%m-%d"))

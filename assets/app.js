/* 台灣輿情觀測：讀取 data/index.json 與 data/daily/<日期>.json 後畫出各區塊。
   所有外部文字（標題、媒體名）一律用 textContent 寫入，不組 HTML 字串。 */
(function () {
  'use strict';
  var SVG = 'http://www.w3.org/2000/svg';
  var LEAN = { green: '綠', blue: '藍', neutral: '中', unknown: '' };
  var STATUS = { '新議題': '🆕 新議題', '升溫': '📈 升溫', '降溫': '📉 降溫', '延燒': '🔁 延燒' };
  var LEVEL = { high: '🚨 高度留意', mid: '⚠️ 留意', low: '👀 參考' };
  var VIEWS = ['home', 'topics', 'signals', 'media', 'about'];
  var state = { dates: [], date: null, day: null, cache: {}, view: 'home', autoOpened: false, health: null };
  var app = document.getElementById('app');

  function h(tag, attrs) {
    var el = document.createElement(tag), i, k;
    for (k in attrs || {}) {
      if (k === 'text') el.textContent = attrs[k];
      else if (k === 'on') for (var ev in attrs.on) el.addEventListener(ev, attrs.on[ev]);
      else el.setAttribute(k, attrs[k]);
    }
    for (i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null) continue;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return el;
  }
  function s(tag, attrs, text) {
    var el = document.createElementNS(SVG, tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    if (text != null) el.textContent = text;
    return el;
  }
  function pct(x, d) { return (x * 100).toFixed(d == null ? 1 : d) + '%'; }
  function title(t) { return (t.ai && t.ai.title) || t.label; }
  function srcName(id) {
    var f = state.day.sources.filter(function (x) { return x.id === id; })[0];
    return f ? f.name : id;
  }
  function setWidth(el, p) { el.style.width = Math.max(1, Math.min(100, p)) + '%'; return el; }

  function getJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' ' + r.status);
      return r.json();
    });
  }
  function loadIndex() {
    if (window.__BUNDLE__) return Promise.resolve(window.__BUNDLE__.index);
    return getJSON('data/index.json');
  }
  function loadDay(date) {
    if (state.cache[date]) return Promise.resolve(state.cache[date]);
    var p = window.__BUNDLE__ ? Promise.resolve(window.__BUNDLE__.days[date]) : getJSON('data/daily/' + date + '.json');
    return p.then(function (d) { state.cache[date] = d; return d; });
  }

  function block(name, sub) {
    var el = h('section', { class: 'block' }, h('h2', { text: name }));
    if (sub) el.appendChild(h('p', { class: 'sub', text: sub }));
    return el;
  }

  /* ---------- 區塊 ---------- */
  function stats(d) {
    var t = d.totals;
    function st(v, label) { return h('div', { class: 'stat' }, h('b', { text: v }), h('span', { text: label })); }
    return h('div', { class: 'stats' },
      st(t.headlines.toLocaleString(), '則新聞標題'),
      st(String(t.sources), '家媒體'),
      st(String(d.signals.filter(function (x) { return x.level !== 'low'; }).length), '個需留意的訊號'),
      st(pct(t.top3_share, 0), '版面集中在前三大議題'));
  }

  function aiTag(d) {
    var m = d.ai_meta || {};
    return '🤖 AI 生成' + (m.at ? '・' + m.at.slice(11, 16) + ' 更新' : '') + '・只依據標題歸納，可能有誤';
  }

  /* 60 秒導讀：AI 挑三件事用白話講完；沒有 AI 資料時整塊不顯示 */
  function briefing(d) {
    var b = d.ai_brief;
    if (!b || !b.items || !b.items.length) return null;
    var el = h('section', { class: 'brief' },
      h('div', { class: 'brief-head' }, h('h2', { text: '60 秒導讀' }), h('span', { text: '今天只看三件事' })),
      h('p', { class: 'brief-lead', text: b.lead }));
    var ol = h('ol');
    b.items.forEach(function (it, i) {
      var t = it.id ? d.topics.filter(function (k) { return k.id === it.id; })[0] : null;
      var body = h('div', null, h('b', { text: (t && title(t)) || it.title }), h('p', { text: it.text }));
      var row = t ? h('button', { type: 'button', on: { click: function () { closeReport(); openTopic(t); } } }, h('span', { class: 'n', text: String(i + 1) }), body)
                  : h('div', { class: 'row' }, h('span', { class: 'n', text: String(i + 1) }), body);
      ol.appendChild(h('li', null, row));
    });
    el.appendChild(ol);
    el.appendChild(h('p', { class: 'ai-tag', text: aiTag(d) }));
    return el;
  }

  /* 一分鐘輿情報告：AI 讀過熱門事件的新聞內文後撰寫，每句附引用編號，連回原文 */
  function cites(rep, list) {
    var span = h('span', { class: 'cites' });
    (list || []).forEach(function (n) {
      var r = rep.refs[n - 1];
      if (!r) return;
      var safe = /^https?:\/\//i.test(r.l || '');
      span.appendChild(safe ? h('a', { href: r.l, target: '_blank', rel: 'noopener noreferrer', title: srcName(r.s) + '：' + r.t, text: String(n) })
                            : h('span', { text: String(n) }));
    });
    return span;
  }

  function reportContent(d) {
    var rep = d.ai_report;
    if (!rep || !rep.sections || !rep.sections.length) return null;
    var el = h('div', { class: 'report' }, h('p', { class: 'report-date', text: d.date.replace(/-/g, '/') + '・依 ' + rep.refs.length + ' 篇報導內文整理' }));
    if (rep.lead) el.appendChild(h('p', { class: 'report-lead' }, rep.lead.text, cites(rep, rep.lead.cite)));
    rep.sections.forEach(function (sec, i) {
      var t = sec.topic ? d.topics.filter(function (k) { return k.id === sec.topic; })[0] : null;
      var head = t ? h('button', { type: 'button', class: 'rhead', on: { click: function () { closeReport(); openTopic(t); } } }, h('span', { class: 'n', text: String(i + 1) }), sec.heading, h('small', { text: '看標題 ›' }))
                   : h('div', { class: 'rhead' }, h('span', { class: 'n', text: String(i + 1) }), sec.heading);
      var p = h('p', { class: 'rbody' });
      sec.sentences.forEach(function (x) { p.appendChild(document.createTextNode(x.text)); p.appendChild(cites(rep, x.cite)); });
      var art = h('article', { class: 'rsec' }, head, p);
      if (sec.framing) art.appendChild(h('p', { class: 'rframe' }, h('b', { text: '各家怎麼報　' }), sec.framing.text, cites(rep, sec.framing.cite)));
      (sec.signals || []).forEach(function (x) {
        art.appendChild(h('p', { class: 'rsig' }, (x.type === 'copy' ? '📋 ' : '🕵️ ') + x.text));
      });
      el.appendChild(art);
    });
    var v = rep.verify || {};
    var det = h('details', { class: 'refs' }, h('summary', { text: '引用來源與查核紀錄' }));
    var ol = h('ol');
    rep.refs.forEach(function (r) {
      var safe = /^https?:\/\//i.test(r.l || '');
      ol.appendChild(h('li', null, h('b', { text: srcName(r.s) + '　' }),
        safe ? h('a', { href: r.l, target: '_blank', rel: 'noopener noreferrer', text: r.t }) : r.t));
    });
    det.appendChild(ol);
    if (v.removed && v.removed.length) {
      det.appendChild(h('p', { class: 'sub', text: '以下句子因查核不通過而刪除，不會出現在報告中：' }));
      var ul = h('ul', { class: 'removed' });
      v.removed.forEach(function (x) { ul.appendChild(h('li', null, h('s', { text: x.text }), h('small', { text: x.why }))); });
      det.appendChild(ul);
    }
    el.appendChild(det);
    el.appendChild(h('p', { class: 'ai-tag', text: '🤖 AI 依新聞內文撰寫・每句都對照引用原文查核（' + (v.kept || 0) + '/' + (v.checked || 0) + ' 句通過）・'
      + (rep.at ? rep.at.slice(11, 16) + ' 更新・' : '') + '數字為引用編號，點擊開啟原文' }));
    return el;
  }

  /* 彈出視窗內容：有一分鐘報告就用報告，沒有就退回只看標題的 60 秒導讀 */
  function modalContent(d) {
    var rep = reportContent(d);
    if (rep) return rep;
    var b = briefing(d);
    if (b) b.classList.add('in-modal');
    return b;
  }
  function openReport() {
    var el = modalContent(state.day);
    if (!el) return;
    var box = document.getElementById('report-content');
    box.textContent = '';
    box.appendChild(el);
    var m = document.getElementById('report');
    m.hidden = false;
    box.scrollTop = 0;
    m.querySelector('.close').focus();
    document.body.style.overflow = 'hidden';
  }
  function closeReport() {
    document.getElementById('report').hidden = true;
    if (document.getElementById('sheet').hidden) document.body.style.overflow = '';
    document.getElementById('open-report').focus();
  }

  /* 同一件事，幾種說法：AI 把標題歸成 2–3 種切角，每種附原始標題當證據 */
  function anglesBox(t, max) {
    var list = t.ai && t.ai.angles;
    if (!list || list.length < 2) return null;
    var box = h('div', { class: 'angles' }, h('p', { class: 'label', text: '同一件事，' + list.length + ' 種說法' }));
    list.forEach(function (a) {
      var item = h('div', { class: 'angle' }, h('b', { text: a.name }), h('p', { text: a.desc }));
      a.headlines.slice(0, max || 1).forEach(function (x) {
        item.appendChild(h('p', { class: 'eg' }, '「' + x.t + '」', h('small', { text: srcName(x.s) })));
      });
      box.appendChild(item);
    });
    box.appendChild(h('p', { class: 'ai-tag', text: '🤖 AI 依標題樣本歸納，僅供參考' }));
    return box;
  }

  /* 「新聞在講什麼」：有 AI 摘要就用，沒有就列出角度不同的代表標題 */
  function whatBox(t, withSource) {
    var box = h('div', { class: 'what' }, h('p', { class: 'label', text: '新聞在講什麼' }));
    if (t.ai && t.ai.summary) {
      box.appendChild(h('p', { text: t.ai.summary }));
      box.appendChild(h('p', { class: 'ai-tag', text: '🤖 AI 摘要，只依據標題歸納' }));
      return box;
    }
    var ul = h('ul');
    (t.digest || []).forEach(function (x) {
      ul.appendChild(h('li', null, x.t, withSource === false ? null : h('small', { text: srcName(x.s) })));
    });
    box.appendChild(ul);
    return box;
  }

  function metaLine(t) {
    return t.size + ' 則・' + t.n_sources + ' 家媒體・佔版面 ' + pct(t.share) + (t.first ? '・' + t.first + ' 起' : '');
  }

  /* AI 判定為「多件不相干的事被湊在一起」的群，不放進前五大與熱力表，改列在其他議題並標示 */
  function isMixed(t) { return !!(t.ai && t.ai.mixed); }
  function mainTopics(d) { return d.topics.filter(function (t) { return !isMixed(t); }); }

  function topCards(d) {
    var el = block('前五大主題', '今天最多媒體在報的五件事。點「看詳細」看全部標題與趨勢；其餘議題在「議題」分頁。');
    var wrap = h('div', { class: 'cards' });
    mainTopics(d).slice(0, 5).forEach(function (t, i) {
      var chips = h('div', { class: 'chips' });
      if (STATUS[t.status]) chips.appendChild(h('span', { class: 'chip', text: STATUS[t.status] }));
      var flags = t.signals.filter(function (x) { return x.level !== 'low'; }).length;
      if (flags) chips.appendChild(h('span', { class: 'chip flag', text: '👀 ' + flags + ' 個訊號' }));
      if (t.days > 1) chips.appendChild(h('span', { class: 'chip', text: '連續 ' + t.days + ' 天' }));
      var bar = h('div', { class: 'heatbar', title: '熱度指數' }, setWidth(h('i'), t.heat * 0.7), h('b', { text: String(t.heat) }));
      wrap.appendChild(h('article', { class: 'card' + (i === 0 ? ' first' : '') },
        h('div', { class: 'head' }, h('div', { class: 'badge', text: String(i + 1) }),
          h('div', null, h('h3', { text: title(t) }), chips.children.length ? chips : null)),
        whatBox(t),
        anglesBox(t, 1),
        h('div', { class: 'cfoot' }, h('p', { class: 'meta', text: metaLine(t) }), bar,
          h('button', { class: 'btn', type: 'button', text: '看詳細', on: { click: function () { openTopic(t); } } }))));
    });
    el.appendChild(wrap);
    return el;
  }

  function signals(d) {
    var el = block('異常訊號', '報導分布或用語不尋常的議題。這是提醒你去看的線索，不是結論。');
    var list = d.signals.filter(function (x) { return x.level !== 'low'; });
    var low = d.signals.length - list.length;
    if (!list.length) {
      el.appendChild(h('p', { class: 'empty', style: 'padding:20px 0;text-align:left', text: '今天沒有偵測到需要留意的訊號。' + (low ? '另有 ' + low + ' 個參考級訊號，在各議題明細中顯示。' : '') }));
      return el;
    }
    var grid = h('div', { class: 'signals' });
    list.forEach(function (x) {
      var t = d.topics.filter(function (k) { return k.id === x.topic; })[0];
      grid.appendChild(h('button', { class: 'sig ' + x.level, type: 'button', on: { click: function () { openTopic(t); } } },
        h('span', { class: 'lv', text: LEVEL[x.level] + '｜' + title(t) }),
        h('p', { class: 't', text: x.title }),
        h('p', { class: 'd', text: x.detail })));
    });
    el.appendChild(grid);
    if (low) el.appendChild(h('p', { class: 'sub', style: 'margin-top:10px', text: '另有 ' + low + ' 個參考級訊號（同步出稿、獨家起頭、突然竄起），在各議題明細中顯示。' }));
    return el;
  }

  function ranking(d) {
    var el = block('全部議題排行', '依熱度排序。條越長代表熱度越高；標「綜合」的是多則不相干新聞被歸在一起。點任一列看標題與趨勢。');
    var list = h('ol', { class: 'rank' });
    d.topics.forEach(function (t) {
      list.appendChild(h('li', null, h('button', { type: 'button', on: { click: function () { openTopic(t); } } },
        h('span', { class: 'no', text: String(t.rank) }),
        h('span', { class: 'name' }, title(t), isMixed(t) ? h('span', { class: 'chip', style: 'margin-left:6px', text: '綜合' }) : null,
          STATUS[t.status] ? h('span', { class: 'chip', style: 'margin-left:6px', text: STATUS[t.status] }) : null),
        h('span', { class: 'meta', text: t.size + ' 則・' + t.n_sources + ' 家' }),
        setWidth(h('span', { class: 'bar' }), t.heat))));
    });
    el.appendChild(list);
    return el;
  }

  function cell(v, max, label, tip) {
    var a = max ? v / max : 0;
    var td = h('td', { text: label, title: tip, style: 'background:rgba(var(--seq-rgb),' + (v ? 0.06 + a * 0.94 : 0).toFixed(3) + ')' });
    if (a > 0.55) td.className = 'hi'; else if (!v) td.className = 'zero';
    return td;
  }

  function coverage(d) {
    var el = block('各媒體把版面給了誰', '每格是該媒體今日標題中，有多少比例在報這個議題。橫向比較可看出誰重押、誰冷處理。');
    var srcs = d.sources.filter(function (x) { return x.count >= 5; });
    var topics = mainTopics(d).slice(0, 10), max = 0;
    topics.forEach(function (t) { srcs.forEach(function (x) { max = Math.max(max, (t.by_source[x.id] || 0) / x.count); }); });
    var head = h('tr', null, h('th', { text: '' }));
    srcs.forEach(function (x) {
      head.appendChild(h('th', { scope: 'col' }, x.name, h('small', { text: (LEAN[x.lean] ? LEAN[x.lean] + '・' : '') + x.count + ' 則' })));
    });
    var body = h('tbody');
    topics.forEach(function (t) {
      var tr = h('tr', null, h('th', { scope: 'row', text: title(t), title: title(t) }));
      srcs.forEach(function (x) {
        var n = t.by_source[x.id] || 0, v = n / x.count;
        tr.appendChild(cell(v, max, n ? Math.round(v * 100) + '%' : '·', x.name + '：' + n + ' 則，佔該媒體今日 ' + pct(v)));
      });
      body.appendChild(tr);
    });
    el.appendChild(h('div', { class: 'scroll' }, h('table', { class: 'heat' }, h('thead', null, head), body)));
    el.appendChild(h('div', { class: 'legend' }, h('span', { text: '0%' }), h('i'), h('span', { text: Math.round(max * 100) + '%' }),
      h('span', { text: '　綠／藍／中＝一般認知的立場傾向，可在 sources.json 調整' })));
    return el;
  }

  function keywords(d) {
    var el = block('今日關鍵詞', '字越大，出現在越多則標題裡。');
    var max = d.keywords.length ? d.keywords[0].n : 1;
    var box = h('div', { class: 'words' });
    d.keywords.slice(0, 24).forEach(function (k, i) {
      var size = 13 + Math.round(11 * Math.sqrt(k.n / max));
      box.appendChild(h('span', { class: i < 4 ? 'hot' : '', style: 'font-size:' + size + 'px' }, k.text, h('small', { text: String(k.n) })));
    });
    el.appendChild(box);
    return el;
  }

  /* 媒體風格指標：只看標題、不靠 AI。切換指標後以長條比較各家 */
  var METRICS = [
    { k: 'hot', name: '跟熱門程度', fmt: 'pct', desc: '自家標題有多少比例在報今天前 10 大議題。高＝跟著大家報；低＝走自己的議程或冷處理熱門事件。' },
    { k: 'first', name: '搶先報', fmt: 'n', desc: '前 10 大議題中，有幾個是由這家最先發出標題。代表議題設定力，也可能是獨家或放話的起點。' },
    { k: 'sens', name: '聳動用語', fmt: 'pct', desc: '標題含驚嘆號或「怒批、傻眼、打臉」等情緒性字眼的比例。越高代表越偏向用情緒吸引點擊。' },
    { k: 'anon', name: '匿名消息', fmt: 'pct', desc: '標題含「知情人士、據傳、網傳」等不具名來源用語的比例。不代表內容不實，但較難查證。' }
  ];
  function mediaMetrics(d) {
    var list = (d.media || []).filter(function (m) { return m.count >= 5; });
    if (!list.length) return null;
    var el = block('媒體風格指標', '同一天、同樣的新聞，各家怎麼處理。只計算今日標題 5 則以上的媒體。');
    var t = d.totals;
    var kpi = h('div', { class: 'stats' });
    function st(v, label) { kpi.appendChild(h('div', { class: 'stat' }, h('b', { text: v }), h('span', { text: label }))); }
    st(t.follow_median == null ? '—' : (t.follow_median >= 60 ? (t.follow_median / 60).toFixed(1) + ' 小時' : t.follow_median + ' 分'), '熱門議題擴散到第 3 家媒體（中位數）');
    if (t.sensational_share != null) st(pct(t.sensational_share, 0), '標題帶情緒性用語');
    st(pct(t.top3_share, 0), '版面集中在前三大議題');
    st(String(list.length), '家媒體納入比較');
    el.appendChild(kpi);
    var seg = h('div', { class: 'seg', role: 'tablist' }), desc = h('p', { class: 'sub' }), bars = h('div', { class: 'srcbars' });
    function show(m) {
      Array.prototype.forEach.call(seg.children, function (b) { b.setAttribute('aria-selected', String(b.dataset.k === m.k)); });
      desc.textContent = m.desc;
      bars.textContent = '';
      var rows = list.slice().sort(function (a, b) { return b[m.k] - a[m.k]; });
      var top = rows[0][m.k] || 1;
      rows.forEach(function (r) {
        var x = d.sources.filter(function (z) { return z.id === r.id; })[0] || {};
        bars.appendChild(h('span', { text: srcName(r.id) + (LEAN[x.lean] ? '（' + LEAN[x.lean] + '）' : '') }));
        bars.appendChild(h('span', null, setWidth(h('span', { class: 'b', style: 'display:block' }), 100 * r[m.k] / top)));
        bars.appendChild(h('span', { class: 'n', text: m.fmt === 'pct' ? pct(r[m.k], 0) : r[m.k] + ' 個' }));
      });
      state.metric = m.k;
    }
    METRICS.forEach(function (m) {
      seg.appendChild(h('button', { type: 'button', role: 'tab', 'data-k': m.k, text: m.name, on: { click: function () { show(m); } } }));
    });
    el.appendChild(seg); el.appendChild(desc); el.appendChild(h('div', { class: 'chart pad' }, bars));
    show(METRICS.filter(function (m) { return m.k === state.metric; })[0] || METRICS[0]);
    return el;
  }

  function about(d) {
    var el = block('怎麼算的', null);
    [['資料', '每小時抓取 ' + d.sources.length + ' 家國內媒體的 RSS 與 Google News 標題，只收當天（台北時間）的新聞。'],
     ['議題與熱度', '相似標題自動歸為同一議題；熱度＝報導則數 ×（1＋ln 報導媒體數），以當日最高者為 100。'],
     ['異常訊號', '訊號只代表報導分布或用語「不尋常」，不等於有人刻意放話；突發事件、獨家採訪、媒體專長領域都會造成同樣的形狀。請點進議題看原始標題再判斷。'],
     ['媒體風格指標', '只看標題計算，不靠 AI。立場標記（綠／藍／中）是一般外界認知，僅供對照。'],
     ['一分鐘看懂今天', '每天 8、13、21 點，AI 讀熱門事件中不同媒體的新聞內文後撰寫。每句附引用並逐句對照原文查核，沒依據的句子會刪除並公開紀錄。內文不存檔、不轉載，只連回原文。']
    ].forEach(function (x) { el.appendChild(h('div', { class: 'note' }, h('b', { text: x[0] }), x[1])); });
    if (state.health) {
      var hl = state.health, bad = hl.sources.filter(function (x) { return !x.ok; }).map(function (x) { return x.name; });
      el.appendChild(h('div', { class: 'note' }, h('b', { text: '來源狀態' }), hl.checked_at.replace('T', ' ').slice(0, 16) + ' 檢查：' +
        (hl.sources.length - bad.length) + '/' + hl.sources.length + ' 家正常' + (bad.length ? '；無資料：' + bad.join('、') : '') + '。'));
    }
    return el;
  }

  /* ---------- 議題明細 ---------- */
  function trendChart(t) {
    var pts = t.trend, W = 320, H = 120, L = 8, R = 44, T = 16, B = 22;
    var max = Math.max.apply(null, pts.map(function (p) { return p.share; })) || 0.01;
    var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', role: 'img', 'aria-label': '近七日版面佔比' });
    svg.appendChild(s('line', { class: 'axis', x1: L, x2: W - R, y1: H - B, y2: H - B }));
    var xy = pts.map(function (p, i) {
      return [L + (W - L - R) * i / (pts.length - 1 || 1), T + (H - T - B) * (1 - p.share / max)];
    });
    svg.appendChild(s('polyline', { class: 'ln', points: xy.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ') }));
    xy.forEach(function (p, i) {
      var c = s('circle', { class: 'dot', cx: p[0], cy: p[1], r: 4 });
      c.appendChild(s('title', {}, (pts[i].date || '無資料') + '：' + pct(pts[i].share)));
      svg.appendChild(c);
      if (pts[i].date && (i === 0 || i === pts.length - 1)) {
        svg.appendChild(s('text', { x: p[0], y: H - 6, 'text-anchor': i === 0 ? 'start' : 'end' }, pts[i].date.slice(5).replace('-', '/')));
      }
    });
    var last = xy[xy.length - 1];
    svg.appendChild(s('text', { class: 'val', x: last[0] + 8, y: last[1] + 4 }, pct(pts[pts.length - 1].share)));
    return svg;
  }

  function hourChart(t) {
    var W = 320, H = 90, B = 18, bw = W / 24, max = Math.max.apply(null, t.hours) || 1;
    var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', role: 'img', 'aria-label': '各小時報導則數' });
    svg.appendChild(s('line', { class: 'axis', x1: 0, x2: W, y1: H - B, y2: H - B }));
    t.hours.forEach(function (n, hr) {
      if (n) {
        var bh = (H - B - 12) * n / max;
        var r = s('rect', { class: 'col', x: hr * bw + 1, y: H - B - bh, width: bw - 2, height: bh, rx: 2 });
        r.appendChild(s('title', {}, hr + ' 時：' + n + ' 則'));
        svg.appendChild(r);
        if (n === max) svg.appendChild(s('text', { class: 'val', x: hr * bw + bw / 2, y: H - B - bh - 3, 'text-anchor': 'middle' }, String(n)));
      }
      if (hr % 6 === 0) svg.appendChild(s('text', { x: hr * bw + 1, y: H - 4 }, hr + ' 時'));
    });
    return svg;
  }

  function openTopic(t) {
    var d = state.day, box = document.getElementById('sheet-content');
    box.textContent = '';
    box.appendChild(h('h2', { id: 'sheet-title', text: title(t) }));
    box.appendChild(h('p', { class: 'lead', text: '熱度第 ' + t.rank + ' 名・' + metaLine(t) + (t.days > 1 ? '・已連續 ' + t.days + ' 天' : '') }));
    box.appendChild(whatBox(t));
    var ang = anglesBox(t, 3); if (ang) box.appendChild(ang);
    var kw = h('div', { class: 'kw' });
    t.keywords.forEach(function (k) { kw.appendChild(h('span', { class: 'chip', text: k })); });
    box.appendChild(kw);

    if (t.signals.length || (t.ai && (t.ai.framing || t.ai.leak))) {
      box.appendChild(h('h3', { text: '訊號與判讀' }));
      t.signals.forEach(function (x) {
        box.appendChild(h('div', { class: 'note' }, h('b', { text: LEVEL[x.level] + '｜' + x.title }), x.detail));
      });
      if (t.ai && t.ai.framing) box.appendChild(h('div', { class: 'note' }, h('b', { text: 'AI 判讀｜各媒體切角' }), t.ai.framing));
      if (t.ai && t.ai.leak && t.ai.leak.level && t.ai.leak.level !== 'none') {
        box.appendChild(h('div', { class: 'note' }, h('b', { text: 'AI 判讀｜放話可能性：' + ({ low: '低', mid: '中', high: '高' }[t.ai.leak.level] || t.ai.leak.level) }), t.ai.leak.reason || ''));
      }
    }

    box.appendChild(h('h3', { text: '近七日版面佔比' }));
    box.appendChild(h('div', { class: 'chart' }, trendChart(t)));
    box.appendChild(h('h3', { text: '今日各小時報導則數' }));
    box.appendChild(h('div', { class: 'chart' }, hourChart(t)));

    box.appendChild(h('h3', { text: '各媒體報導則數（括號為佔該媒體今日標題比例）' }));
    var bars = h('div', { class: 'srcbars' });
    var rows = d.sources.map(function (x) { return { x: x, n: t.by_source[x.id] || 0 }; }).sort(function (a, b) { return b.n - a.n; });
    var top = rows[0].n || 1;
    rows.forEach(function (r) {
      bars.appendChild(h('span', { text: r.x.name + (LEAN[r.x.lean] ? '（' + LEAN[r.x.lean] + '）' : '') }));
      bars.appendChild(h('span', null, setWidth(h('span', { class: 'b', style: 'display:block' }), 100 * r.n / top)));
      bars.appendChild(h('span', { class: 'n', text: r.n + ' 則（' + pct(r.n / r.x.count, 0) + '）' }));
    });
    box.appendChild(bars);

    box.appendChild(h('h3', { text: '標題（依時間）' + (t.size > t.headlines.length ? '・顯示前 ' + t.headlines.length + ' 則' : '') }));
    var ul = h('ul', { class: 'hl' });
    t.headlines.forEach(function (x) {
      var safe = /^https?:\/\//i.test(x.l || '');
      var a = safe ? h('a', { href: x.l, target: '_blank', rel: 'noopener noreferrer', text: x.t }) : h('span', { text: x.t });
      ul.appendChild(h('li', null, h('time', { text: x.h }), h('div', null, a, h('small', { text: srcName(x.s) }))));
    });
    box.appendChild(ul);
    var sheet = document.getElementById('sheet');
    sheet.hidden = false;
    box.scrollTop = 0;
    sheet.querySelector('.close').focus();
    document.body.style.overflow = 'hidden';
  }
  function closeSheet() {
    document.getElementById('sheet').hidden = true;
    document.body.style.overflow = '';
  }

  /* ---------- 主流程 ---------- */
  function render() {
    var d = state.day;
    app.textContent = '';
    document.getElementById('demo').hidden = d.mode !== 'demo';
    document.getElementById('updated').textContent = '資料更新：' + d.updated_at.replace('T', ' ').slice(0, 16) + '（台北時間）';
    document.getElementById('open-report').hidden = !(d.ai_report || d.ai_brief);
    Array.prototype.forEach.call(document.querySelectorAll('#tabs a'), function (a) {
      if (a.dataset.view === state.view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (!d.topics.length && state.view !== 'about') { app.appendChild(h('p', { class: 'empty', text: '這一天的標題還不夠多，無法歸納議題。' })); return; }
    var parts = {
      home: [stats, topCards, keywords],
      topics: [ranking],
      signals: [signals],
      media: [mediaMetrics, coverage],
      about: [about]
    }[state.view];
    parts.forEach(function (f) { var el = f(d); if (el) app.appendChild(el); });
    if (!state.autoOpened) { state.autoOpened = true; openReport(); }  // 進站時自動彈出一次
  }

  function route() {
    var v = (location.hash || '').slice(1);
    state.view = VIEWS.indexOf(v) >= 0 ? v : 'home';
    if (state.day) { render(); window.scrollTo(0, 0); }
  }
  window.addEventListener('hashchange', route);
  route();

  function go(date) {
    state.date = date;
    var i = state.dates.indexOf(date);
    document.getElementById('date').value = date;
    document.getElementById('prev').disabled = i <= 0;
    document.getElementById('next').disabled = i >= state.dates.length - 1;
    loadDay(date).then(function (d) { state.day = d; render(); })
      .catch(function (e) { app.textContent = ''; app.appendChild(h('p', { class: 'empty', text: '讀取 ' + date + ' 的資料失敗：' + e.message })); });
  }

  document.getElementById('prev').addEventListener('click', function () { go(state.dates[state.dates.indexOf(state.date) - 1]); });
  document.getElementById('next').addEventListener('click', function () { go(state.dates[state.dates.indexOf(state.date) + 1]); });
  document.getElementById('date').addEventListener('change', function (e) { go(e.target.value); });
  document.getElementById('sheet').addEventListener('click', function (e) { if (e.target.hasAttribute('data-close')) closeSheet(); });
  document.getElementById('report').addEventListener('click', function (e) { if (e.target.hasAttribute('data-close-report')) closeReport(); });
  document.getElementById('open-report').addEventListener('click', openReport);
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (!document.getElementById('sheet').hidden) closeSheet(); else if (!document.getElementById('report').hidden) closeReport();
  });

  loadIndex().then(function (idx) {
    state.dates = idx.dates || [];
    if (!state.dates.length) { app.textContent = ''; app.appendChild(h('p', { class: 'empty', text: '還沒有任何資料。請先執行一次排程（Actions → Update data → Run workflow）。' })); return; }
    var sel = document.getElementById('date');
    state.dates.slice().reverse().forEach(function (d) { sel.appendChild(h('option', { value: d, text: d })); });
    go(idx.latest || state.dates[state.dates.length - 1]);
  }).catch(function (e) { app.textContent = ''; app.appendChild(h('p', { class: 'empty', text: '讀取資料索引失敗：' + e.message })); });

  if (!window.__BUNDLE__) {
    getJSON('data/health.json').then(function (hl) { state.health = hl; if (state.view === 'about' && state.day) render(); }).catch(function () {});
  }
})();

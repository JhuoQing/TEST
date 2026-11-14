/* 台灣輿情觀測：讀取 data/index.json 與 data/daily/<日期>.json 後畫出各區塊。
   所有外部文字（標題、媒體名）一律用 textContent 寫入，不組 HTML 字串。 */
(function () {
  'use strict';
  var SVG = 'http://www.w3.org/2000/svg';
  var LEAN = { green: '綠', blue: '藍', neutral: '中', unknown: '' };
  var STATUS = { '新議題': '● 新議題', '升溫': '▲ 升溫', '降溫': '▼ 降溫', '延燒': '→ 延燒' };
  var LEVEL = { high: '⚠ 高度留意', mid: '△ 留意', low: '○ 參考' };
  var state = { dates: [], date: null, day: null, cache: {}, showAll: false };
  var app = document.getElementById('app');

  function h(tag, attrs) {
    var el = document.createElement(tag), i, k;
    for (k in attrs || {}) {
      if (k === 'text') el.textContent = attrs[k];
      else if (k === 'on') for (var ev in attrs.on) el.addEventListener(ev, attrs.on[ev]);
      else if (k === 'style') el.style.cssText = attrs[k];
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

  /* ---------- 區塊 ---------- */
  function block(name, sub) {
    var el = h('section', { class: 'block' }, h('h2', { text: name }));
    if (sub) el.appendChild(h('p', { class: 'sub', text: sub }));
    return el;
  }

  function tiles(d) {
    var t = d.totals;
    function tile(v, label) { return h('div', { class: 'tile' }, h('b', { text: v }), h('span', { text: label })); }
    return h('div', { class: 'tiles' },
      tile(t.headlines.toLocaleString(), '則新聞標題'),
      tile(String(t.sources), '家媒體'),
      tile(String(d.signals.filter(function (x) { return x.level !== 'low'; }).length), '個需留意的訊號'),
      tile(pct(t.top3_share, 0), '版面集中在前三大議題'));
  }

  function ranking(d) {
    var el = block('今日熱度榜', '大家今天在談什麼。長條為熱度指數（最高 = 100），點任一議題看各家標題。');
    var list = h('ol', { class: 'rank' });
    var shown = state.showAll ? d.topics : d.topics.slice(0, 10);
    shown.forEach(function (t) {
      var flags = t.signals.filter(function (x) { return x.level !== 'low'; }).length;
      var name = h('span', { class: 'name', text: title(t) });
      if (STATUS[t.status]) name.appendChild(h('span', { class: 'chip', text: STATUS[t.status] }));
      if (flags) name.appendChild(h('span', { class: 'chip flag', text: '⚠ ' + flags + ' 訊號' }));
      list.appendChild(h('li', null, h('button', { type: 'button', on: { click: function () { openTopic(t); } } },
        h('span', { class: 'no', text: String(t.rank) }),
        name,
        h('span', { class: 'meta', text: t.size + ' 則・' + t.n_sources + ' 家' }),
        h('span', { class: 'track' }, h('span', { class: 'bar', style: 'width:' + Math.max(1, t.heat * 0.82) + '%' }), h('span', { class: 'val', text: String(t.heat) })),
        h('span', { class: 'line2', text: (t.ai && t.ai.summary) || t.rep }))));
    });
    el.appendChild(list);
    if (d.topics.length > 10) {
      el.appendChild(h('button', { class: 'more', type: 'button', text: state.showAll ? '只看前 10 名' : '顯示全部 ' + d.topics.length + ' 個議題',
        on: { click: function () { state.showAll = !state.showAll; render(); } } }));
    }
    return el;
  }

  function signals(d) {
    var el = block('異常訊號', '報導分布或用語不尋常的議題。這是提醒你去看的線索，不是結論。');
    var list = d.signals.filter(function (x) { return x.level !== 'low'; });
    var low = d.signals.length - list.length;
    if (!list.length) { el.appendChild(h('p', { class: 'empty', text: '今天沒有偵測到需要留意的訊號。' })); return el; }
    var grid = h('div', { class: 'signals' });
    list.forEach(function (x) {
      var t = d.topics.filter(function (k) { return k.id === x.topic; })[0];
      grid.appendChild(h('button', { class: 'sig ' + x.level, type: 'button', on: { click: function () { openTopic(t); } } },
        h('span', { class: 'lv', text: LEVEL[x.level] + '｜' + title(t) }),
        h('p', { class: 't', text: x.title }),
        h('p', { class: 'd', text: x.detail })));
    });
    el.appendChild(grid);
    if (low) el.appendChild(h('p', { class: 'sub', style: 'margin-top:8px', text: '另有 ' + low + ' 個參考級訊號（同步出稿、獨家起頭、突然竄起），在各議題明細中顯示。' }));
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
    var topics = d.topics.slice(0, 10), max = 0;
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
    d.keywords.slice(0, 30).forEach(function (k) {
      var size = 13 + Math.round(17 * Math.sqrt(k.n / max));
      box.appendChild(h('span', { style: 'font-size:' + size + 'px;font-weight:' + (size > 22 ? 800 : 500) }, k.text, h('small', { text: String(k.n) })));
    });
    el.appendChild(box);
    return el;
  }

  function similarity(d) {
    var sim = d.similarity;
    if (!sim || sim.ids.length < 3) return null;
    var el = block('誰跟誰的議程最像', '兩家媒體在各議題的版面分配越接近，數字越高（1.00 = 完全一樣）。長期同步的媒體值得一起觀察。');
    var head = h('tr', null, h('th', { text: '' }));
    sim.ids.forEach(function (id) { head.appendChild(h('th', { scope: 'col', text: srcName(id) })); });
    var body = h('tbody');
    sim.matrix.forEach(function (row, i) {
      var tr = h('tr', null, h('th', { scope: 'row', text: srcName(sim.ids[i]) }));
      row.forEach(function (v, j) {
        tr.appendChild(i === j ? h('td', { class: 'zero', text: '—' }) : cell(v, 1, v.toFixed(2), srcName(sim.ids[i]) + ' × ' + srcName(sim.ids[j]) + '：' + v.toFixed(2)));
      });
      body.appendChild(tr);
    });
    el.appendChild(h('div', { class: 'scroll' }, h('table', { class: 'heat' }, h('thead', null, head), body)));
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
    box.appendChild(h('p', { class: 'lead', text: '熱度第 ' + t.rank + ' 名・' + t.size + ' 則・' + t.n_sources + ' 家媒體・佔今日版面 ' + pct(t.share) +
      (t.days > 1 ? '・已連續 ' + t.days + ' 天' : '') }));
    if (t.ai && t.ai.summary) box.appendChild(h('p', { class: 'sum', text: t.ai.summary }));
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
    box.appendChild(trendChart(t));
    box.appendChild(h('h3', { text: '今日各小時報導則數' }));
    box.appendChild(hourChart(t));

    box.appendChild(h('h3', { text: '各媒體報導則數（括號為該媒體今日標題中的佔比）' }));
    var bars = h('div', { class: 'srcbars' });
    var rows = d.sources.map(function (x) { return { x: x, n: t.by_source[x.id] || 0 }; }).sort(function (a, b) { return b.n - a.n; });
    var top = rows[0].n || 1;
    rows.forEach(function (r) {
      bars.appendChild(h('span', { text: r.x.name + (LEAN[r.x.lean] ? '（' + LEAN[r.x.lean] + '）' : '') }));
      bars.appendChild(h('span', null, h('span', { class: 'b', style: 'display:block;width:' + (100 * r.n / top) + '%' })));
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
    sheet.querySelector('.sheet-body').scrollTop = 0;
    sheet.querySelector('.close').focus();
  }
  function closeSheet() { document.getElementById('sheet').hidden = true; }

  /* ---------- 主流程 ---------- */
  function render() {
    var d = state.day;
    app.textContent = '';
    document.getElementById('demo').hidden = d.mode !== 'demo';
    document.getElementById('updated').textContent = '資料更新：' + d.updated_at.replace('T', ' ').slice(0, 16) + '（台北時間）';
    if (!d.topics.length) { app.appendChild(h('p', { class: 'empty', text: '這一天的標題還不夠多，無法歸納議題。' })); return; }
    app.appendChild(tiles(d));
    if (d.ai_overview) {
      app.appendChild(h('div', { class: 'overview' }, h('p', { text: d.ai_overview }),
        h('small', { text: 'AI 摘要' + (d.ai_meta ? '・' + d.ai_meta.model + '・' + d.ai_meta.at.slice(11, 16) : '') + '。僅根據標題生成，可能有誤。' })));
    }
    [ranking, signals, coverage, keywords, similarity].forEach(function (f) { var el = f(d); if (el) app.appendChild(el); });
  }

  function go(date) {
    state.date = date; state.showAll = false;
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
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeSheet(); });

  loadIndex().then(function (idx) {
    state.dates = idx.dates || [];
    if (!state.dates.length) { app.textContent = ''; app.appendChild(h('p', { class: 'empty', text: '還沒有任何資料。請先執行一次排程（Actions → Update data → Run workflow）。' })); return; }
    var sel = document.getElementById('date');
    state.dates.slice().reverse().forEach(function (d) { sel.appendChild(h('option', { value: d, text: d })); });
    go(idx.latest || state.dates[state.dates.length - 1]);
  }).catch(function (e) { app.textContent = ''; app.appendChild(h('p', { class: 'empty', text: '讀取資料索引失敗：' + e.message })); });

  if (!window.__BUNDLE__) {
    getJSON('data/health.json').then(function (hl) {
      var bad = hl.sources.filter(function (x) { return !x.ok; }).map(function (x) { return x.name; });
      document.getElementById('health').textContent = '來源狀態（' + hl.checked_at.replace('T', ' ').slice(0, 16) + '）：' +
        (hl.sources.length - bad.length) + '/' + hl.sources.length + ' 家正常' + (bad.length ? '；無資料：' + bad.join('、') : '') + '。';
    }).catch(function () {});
  }
})();

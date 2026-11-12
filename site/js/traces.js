/* VLOnto - question traces (traces.html). One tab per legal area (data/traces/index.js), each area's 20 traced answers
   drawn like the panels of the paper's Fig. 6 (js/trace-draw.js), and a focus view in the manner of Fig. 1 with the
   hop-by-hop provenance of Fig. 5.
   - tabs: ARIA tablist, arrow keys / Home / End (selection follows focus), the last tab is remembered (VL.store);
   - an area's data/traces/<id>.js is loaded by script injection when its tab is first opened (no fetch: file:// works);
   - deep links: #area=<id> opens a tab, #area=<id>&q=<rank> also opens that trace's focus view; Esc closes it;
   - window.__VLONTO_METRICS.traces and window.VLApp.traces serve the interaction tests. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS, TD = VL.TraceDraw;
  VL.chrome();
  M.page = 'traces';
  var IDX = window.VLONTO.traces_index;
  var T = M.traces = { available: false, tabs: 0, area: null, loaded: [], cards: 0, renderMs: null, focus: null, opened: 0,
    closed: 0, errors: [] };
  var esc = VL.esc, fmt = VL.fmt;
  var tabsEl = VL.$('#tr-tabs'), panel = VL.$('#tr-panel'), wrap = VL.$('#tr-focus'), dlg = VL.$('#tr-focus-dialog');
  var EXT = VL.ICON.external;
  function f2(x) { return x == null ? '–' : Number(x).toFixed(2); }
  function ext(href, text, sr) {
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + text + EXT + '<span class="sr-only"> (' + esc(sr || 'opens in a new tab') + ')</span></a>';
  }

  if (!IDX || !IDX.available || !IDX.areas || !IDX.areas.length) {
    VL.$('#tr-nodata').hidden = false;
    tabsEl.hidden = true;
    panel.hidden = true;
    VL.$$('[data-legend]').forEach(function (e) { e.hidden = true; });
    T.reason = (IDX && IDX.reason) || 'data/traces/index.js missing';
    VL.fontsReady().then(function () { VL.setReady(); });
    return;
  }
  T.available = true;
  VL.$('#tr-defs').innerHTML = TD.defs();
  var AREAS = IDX.areas, BY = {};
  AREAS.forEach(function (a) { BY[a.id] = a; });
  T.tabs = AREAS.length;

  (function revisions() {
    var r = IDX.source_revisions || {};
    var revs = Object.keys(r).map(function (k) { return esc(k.replace('tmquan/', '')) + ' @' + esc(String(r[k]).slice(0, 10)); }).join(', ');
    VL.$('#tr-revs').innerHTML = 'Data: question traces of ' + esc(VL.releaseLabel()) + ', built ' + esc(IDX.generated || '') + ' from the Hugging Face datasets ' +
      revs + ' (data revisions of build/traces/index.json). <span class="vi" lang="vi">Dữ liệu: truy vết câu hỏi của ' + esc(VL.releaseLabel()) +
      ', tạo ngày ' + esc(IDX.generated || '') + ', từ các phiên bản dữ liệu nêu trên.</span>';
  })();

  /* ------------------------------------------------------------------ tabs */
  tabsEl.innerHTML = AREAS.map(function (a) {
    return '<button type="button" role="tab" id="tr-tab-' + a.id + '" aria-controls="tr-panel" aria-selected="false" tabindex="-1" data-area="' + a.id + '">' +
      '<span lang="vi">' + esc(a.label_vi) + '</span><span aria-hidden="true">·</span><span>' + esc(a.label_en) + '</span>' +
      '<span class="n">' + fmt(a.n_qas) + '<span class="sr-only"> Q&amp;As</span></span></button>';
  }).join('');
  var TABS = VL.$$('[role="tab"]', tabsEl);
  tabsEl.addEventListener('click', function (e) {
    var b = e.target.closest('[role="tab"]');
    if (b) select(b.getAttribute('data-area'), { focusTab: false, user: true });
  });
  tabsEl.addEventListener('keydown', function (e) {
    var i = TABS.indexOf(document.activeElement);
    if (i < 0) return;
    var j = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: TABS.length - 1 }[e.key];
    if (j == null) return;
    e.preventDefault();
    j = (j + TABS.length) % TABS.length;
    select(TABS[j].getAttribute('data-area'), { focusTab: true, user: true });
  });

  var current = null, seq = 0;
  function setHash(h) {
    if (location.hash === h) return;
    try { history.replaceState(history.state, '', h); } catch (e) { location.hash = h; }
  }
  function select(id, opts) {
    opts = opts || {};
    var a = BY[id] || AREAS[0];
    TABS.forEach(function (b) {
      var on = b.getAttribute('data-area') === a.id;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
      if (on && opts.focusTab) { b.focus(); }
      if (on) { try { b.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) { /* old engines */ } }
    });
    panel.setAttribute('aria-labelledby', 'tr-tab-' + a.id);
    VL.store.set('traces.area', a.id);
    if (opts.user) setHash('#area=' + a.id);
    if (current === a.id && panel.querySelector('.tr-grid')) return Promise.resolve(a);
    current = a.id;
    var my = ++seq;
    panel.innerHTML = '<p class="tr-status">Loading ' + esc(a.label_en) + ' · <span lang="vi">Đang tải ' + esc(a.label_vi) + '</span></p>';
    return load(a).then(function (data) {
      if (my !== seq) return a;                 // another tab was chosen meanwhile
      render(a, data);
      return a;
    }, function (err) {
      T.errors.push(String(err && err.message || err));
      panel.innerHTML = '<p class="tr-status">Could not load the traces of this area (' + esc(a.file) + ') · <span lang="vi">Không tải được dữ liệu.</span></p>';
      return a;
    });
  }
  function load(a) {
    var key = 'traces_' + a.id;
    if (window.VLONTO[key]) return Promise.resolve(window.VLONTO[key]);
    return VL.loadScript('data/traces/' + a.file).then(function () {
      var d = window.VLONTO[key];
      if (!d || !d.traces) throw new Error('data/traces/' + a.file + ' did not register ' + key);
      if (T.loaded.indexOf(a.id) < 0) T.loaded.push(a.id);
      return d;
    });
  }

  /* ------------------------------------------------------------------ cards (Fig. 6 panels) */
  function lawHead(law) {
    return law.en.indexOf(law.number) >= 0 ? esc(law.en) : esc(law.en) + ' · <span class="num">' + esc(law.number) + '</span>';
  }
  function lawTitle(law) {
    /* focus title: Vietnamese name · English name · number, without repeating a number that a name already carries */
    var num = law.number || '', named = (law.vi || '').indexOf(num) >= 0 || (law.en || '').indexOf(num) >= 0;
    return '<span lang="vi" class="vi">' + esc(law.vi) + '</span> · ' + esc(law.en) + (num && !named ? ' · <span class="num">' + esc(num) + '</span>' : '');
  }
  function primary(tr) { for (var i = 0; i < tr.paths.length; i++) if (tr.paths[i].pr) return tr.paths[i]; return tr.paths[0]; }
  function bi(n) { return n.vi === n.en ? n.vi : n.vi + ' · ' + n.en; }
  function chainTitle(tr) {
    var p = primary(tr);
    return 'Truy vết · Trace: ' + p.n.map(function (k) { return bi(tr.nodes[k]); }).join(' → ');
  }
  function chainDesc(a, tr) {
    var p = primary(tr), prov = tr.nodes[p.n.length > 3 ? p.n[2] : p.n[p.n.length - 1]];
    var c = tr.counts || {};
    return (tr.verified ? 'Verified: the answer quotes ' + prov.en + ' word for word (5-gram match ' + f2(tr.match) + ').'
      : 'Structure only: the answer does not quote ' + prov.en + ' (5-gram match ' + f2(tr.match) + ' < 0.5); the path is kept, not verified.') +
      ' ' + (c.sources || 0) + ' sources cited, ' + (c.verified_sources || 0) + ' verified. ' + (c.nodes || tr.nodes.length) + ' nodes, ' +
      (c.links || 0) + ' links; ' + (c.other_answers || 0) + ' other answers in ' + a.label_en + ' cite this law.';
  }
  function verdict(tr) {
    return tr.verified ? '<span class="ok">✓ text match ' + f2(tr.match) + '</span>' : 'structural · match ' + f2(tr.match);
  }
  function cardHtml(a, tr) {
    var id = 'tc-' + a.id + '-' + tr.rank;
    return '<article class="tr-card" id="' + id + '" data-rank="' + tr.rank + '">' +
      '<h3 class="tc-head"><span class="tc-rank">' + tr.rank + '</span><a class="tc-open" href="#area=' + a.id + '&amp;q=' + tr.rank + '" title="' +
      esc(tr.law.vi) + ' · ' + esc(tr.law.en) + '">' + lawHead(tr.law) + '</a></h3>' +
      '<div class="tc-body"><p class="tc-q" lang="vi">' + esc(tr.qa.vi) + '</p><p class="tc-g">' + esc(tr.qa.en) + '</p></div>' +
      '<div class="tc-fig">' + TD.svg(tr, 'card', { id: id + '-f', title: chainTitle(tr), desc: chainDesc(a, tr) }) + '</div>' +
      '<p class="tc-prov">hdpl #' + esc(tr.qa.id) + ' · ' + esc(tr.qa.date) + ' · ' + fmt(tr.article.n) + ' answers in the area cite ' + esc(tr.article.en) +
      ' · ' + verdict(tr) + (tr.qa.url ? ' · ' + ext(tr.qa.url, 'source', 'thuvienphapluat.vn, opens in a new tab') : '') + '</p></article>';
  }
  var DATA = {};
  function render(a, data) {
    var t0 = performance.now();
    DATA[a.id] = data;
    var n = data.traces.length, ver = data.traces.filter(function (t) { return t.verified; }).length;
    panel.innerHTML = '<div class="tr-area-head"><h2 id="tr-area-title"><span lang="vi">' + esc(a.label_vi) + '</span> · <span class="en">' +
      esc(a.label_en) + '</span></h2><p>' + fmt(a.n_qas) + ' Q&amp;As in the area, ' + fmt(a.n_qas_with_links) + ' linked to a parsed article · the ' +
      n + ' most-asked articles · ' + ver + ' of ' + n + ' traces text-verified</p></div>' +
      '<div class="tr-grid">' + data.traces.map(function (tr) { return cardHtml(a, tr); }).join('') + '</div>';
    T.renderMs = Math.round(performance.now() - t0);
    T.cards = n;
    T.area = a.id;
    T.renders = (T.renders || 0) + 1;
  }
  panel.addEventListener('click', function (e) {
    var card = e.target.closest('.tr-card');
    if (!card || (e.target.closest('a') && !e.target.closest('.tc-open'))) return;
    e.preventDefault();
    location.hash = 'area=' + current + '&q=' + card.getAttribute('data-rank');
  });

  /* ------------------------------------------------------------------ focus view (Fig. 1 + Fig. 5) */
  var openTrace = null, lastFocus = null;
  function wide() { return window.matchMedia('(min-width: 760px)').matches; }
  function nodeOf(tr, k) { return tr.nodes[k]; }
  function pathLabel(tr, p) {
    var prov = nodeOf(tr, p.n.length > 3 ? p.n[2] : p.n[p.n.length - 1]), work = nodeOf(tr, p.n[p.n.length - 1]);
    if (p.u === 'work') return '<span lang="vi">' + esc(work.vi) + '</span> · ' + esc(work.en) + ' cited as a whole';
    return '<span lang="vi">' + esc(prov.vi) + '</span> · ' + esc(prov.en) + ' of ' + esc(work.en);
  }
  var REASON = { law_not_resolved: 'law not resolved', number_not_in_scope: 'number not in this release', article_not_parsed: 'article not parsed' };
  function hop(cls, num, en, vi, body) {
    return '<section class="hop hop-' + cls + '"><h3><b>' + num + ' ' + en + '</b> <span lang="vi">' + vi + '</span></h3>' + body + '</section>';
  }
  function hopsHtml(a, tr) {
    var p = primary(tr), N = tr.nodes, k3 = p.n.length > 3 ? p.n[2] : null, work = N[p.n[p.n.length - 1]];
    var rec = null, provs = [], whole = [], struct = [];
    N.forEach(function (n) { if (TD.CLASSES[n.c] === 'record') rec = n; });
    tr.paths.forEach(function (q) {
      if (q.u === 'work') whole.push(q); else if (q.v) provs.push(q); else struct.push(q);
    });
    var ans = N[p.n[1]];
    var b1 = hop('q', '1', 'Question', 'Câu hỏi · hdpl #' + esc(tr.qa.id),
      '<p class="strong" lang="vi">' + esc(tr.qa.vi) + '</p><p class="en">' + esc(tr.qa.en) + '</p>' +
      '<p class="pv">q:' + esc(tr.qa.id) + ' · src hdpl · ' + esc(tr.qa.date) + (tr.qa.url ? ' · ' + ext(tr.qa.url, 'thuvienphapluat.vn') : '') + '</p>');
    var items = provs.map(function (q) { return '<li>✓ ' + pathLabel(tr, q) + ' — text match ' + f2(q.m) + '</li>'; })
      .concat(struct.map(function (q) { return '<li>○ ' + pathLabel(tr, q) + ' — match ' + f2(q.m) + ' (kept, not verified)</li>'; }))
      .concat(whole.map(function (q) { return '<li>○ ' + pathLabel(tr, q) + '</li>'; }))
      .concat(tr.unresolved.map(function (u) {
        var what = u.num ? esc(u.num) : ((u.art ? 'Điều ' + esc(u.art) + ' ' : '') + esc(u.t || ''));
        return '<li>○ <span lang="vi">' + what + '</span> — ' + esc(REASON[u.r] || u.r) + ' (listed, not drawn)</li>';
      }));
    var methods = [];
    tr.paths.forEach(function (q) { if (q.me && methods.indexOf(q.me) < 0) methods.push(q.me); });
    var b2 = hop('a', '2', 'Answer', 'Trả lời · ' + tr.paths.length + ' sources',
      '<p>checked · <span lang="vi">đã kiểm tra</span>:</p><ul>' + items.join('') + '</ul>' +
      '<p class="pv">a:' + esc(tr.qa.id) + ' −cites→ ' + tr.paths.length + ' targets · method ' + esc(methods.join(' / ')) + ' · ' +
      esc((ans.p || [])[2] || '') + '</p>');
    var b3 = '';
    if (k3 != null) {
      var prov = N[k3], chain = p.n.slice(2, -1).reverse().map(function (k) { return N[k]; });
      var pathVi = chain.map(function (n) { return n.vi; }).join(' › ');
      var pv = prov.p || [];
      b3 = hop('p', '3', 'Provision', 'Điều khoản · ' + esc(pathVi) + ' = ' + esc(prov.en),
        '<p>reached from 2 by <i>cites</i></p><p class="strong"><span lang="vi">' + esc(prov.vi) + '</span> · ' + esc(prov.en) + '</p>' +
        (p.v ? '<p>✓ found word for word in the answer — text match ' + f2(p.m) + '</p>'
          : '<p>○ the answer does not contain its words — text match ' + f2(p.m) + ' (&lt; 0.5): a structural link, kept and not verified</p>') +
        '<p>Text of the provision: ' + (tr.law.url ? ext(tr.law.url, 'read it at the source', 'thuvienphapluat.vn, opens in a new tab') : 'at the source') + '</p>' +
        '<p class="pv">vbpl:' + esc(pv[1] || tr.law.doc_id) + ' › ' + esc(pathVi) + ' · ' + esc(pv[2] || '') + (pv[3] ? ' · ' + esc(pv[3]) : '') + '</p>');
    }
    var wp = work.p || [];
    var b4 = hop('l', '4', 'Law', 'Văn bản · ' + esc(tr.law.number),
      '<p>reached from 3 by <i>contains</i> and <i>realizes</i></p>' +
      '<p class="strong"><span lang="vi">' + esc(tr.law.vi) + '</span> · ' + esc(tr.law.en) + '</p>' +
      '<p>source status (vbpl): <span lang="vi">' + esc(tr.law.status_vi) + '</span> · ' + esc(tr.law.status_en) + '</p>' +
      '<p>English name: ' + esc(tr.law.en_src || 'machine-assisted') + '</p>' +
      (rec ? '<p>VN record: ' + (rec.u ? ext(rec.u, 'vbpl:' + esc(tr.law.doc_id)) : 'vbpl:' + esc(tr.law.doc_id)) + '</p>' : '') +
      '<p class="pv">' + esc(work.i) + ' · ' + esc(wp[2] || '') + '</p>');
    var terms = tr.terms.map(function (t) {
      var n = N[t.n], d = t.d != null ? N[t.d] : null;
      return '<li><b><span lang="vi">' + esc(n.vi) + '</span> · ' + esc(n.en) + '</b> — ' +
        (d ? 'defined in ' + esc(d.en) + ' (match ' + f2(t.m) + ')' : 'no defining clause in the laws of this trace') +
        (n.u ? ' · ' + ext(n.u, 'tnpl #' + esc((n.p || [])[1] || '')) : '') +
        '<div class="pv">' + esc(n.i) + (d ? ' ←defines− ' + esc(d.i) : '') + ' · ' + esc((n.p || [])[2] || '') + '</div></li>';
    });
    var b5 = hop('t', '5', 'Terms', 'Thuật ngữ · tnpl', terms.length ?
      '<ul>' + terms.join('') + '</ul><p class="en">question → mentions → term → defined by → clause</p>' :
      '<p>No tnpl term is named in the question. <span lang="vi">Câu hỏi không nhắc đến thuật ngữ nào của tnpl.</span></p>');
    return '<div class="tr-hops" aria-label="The trace hop by hop · Truy vết từng bước">' +
      '<div class="col">' + b1 + '<div class="hop-arrow">↓ answered by · <span lang="vi">được trả lời bởi</span></div>' + b2 + '</div>' +
      '<div class="col">' + b3 + '</div>' +
      '<div class="col">' + b4 + '<div class="hop-arrow">↓ defines terms the question mentions · <span lang="vi">định nghĩa thuật ngữ câu hỏi nhắc đến</span></div>' + b5 + '</div></div>';
  }
  function legendHtml() {
    var src = VL.$('[data-legend]');
    return src ? src.outerHTML.replace(' data-legend', '') : '';
  }
  function focusHtml(a, tr, view) {
    var id = 'tf-' + a.id + '-' + tr.rank;
    return '<div class="tf-head"><div><p class="tf-area">#' + tr.rank + ' · <span lang="vi">' + esc(a.label_vi) + '</span> · ' + esc(a.label_en) + '</p>' +
      '<h2 id="tf-title">' + lawTitle(tr.law) + '</h2>' +
      '<p class="tf-q" lang="vi">' + esc(tr.qa.vi) + '</p><p class="tf-g">' + esc(tr.qa.en) + '</p></div>' +
      '<button type="button" class="btn tf-close" data-close aria-label="Đóng · Close (Esc)">Close · <span lang="vi">Đóng</span></button></div>' +
      '<div class="tf-fig" data-view="' + view + '">' + TD.svg(tr, view, { id: id, title: chainTitle(tr), desc: chainDesc(a, tr), nodeTitles: true }) + '</div>' +
      legendHtml() + hopsHtml(a, tr) +
      '<p class="tf-links">' + verdict(tr) + ' · ' + fmt(tr.article.n) + ' answers in ' + esc(a.label_en) + ' cite ' + esc(tr.article.en) + ' (' +
      fmt(tr.article.na) + ' in all areas) · link to this trace: <a href="#area=' + a.id + '&amp;q=' + tr.rank + '">#area=' + a.id + '&amp;q=' + tr.rank + '</a></p>';
  }
  function openFocus(a, tr) {
    if (!wrap.hidden && openTrace && openTrace.a === a && openTrace.tr === tr) return;
    if (wrap.hidden) lastFocus = document.activeElement;
    var view = wide() ? 'wide' : 'tall';
    dlg.innerHTML = focusHtml(a, tr, view);
    wrap.hidden = false;
    document.body.classList.add('tr-modal-open');
    openTrace = { a: a, tr: tr, view: view };
    T.focus = { open: true, area: a.id, rank: tr.rank, view: view };
    T.opened += 1;
    var b = dlg.querySelector('.tf-close');
    (b || dlg).focus();
  }
  function closeFocus(fromRoute) {
    if (wrap.hidden) return;
    wrap.hidden = true;
    dlg.innerHTML = '';
    document.body.classList.remove('tr-modal-open');
    var was = openTrace;
    openTrace = null;
    T.focus = { open: false, area: was && was.a.id, rank: was && was.tr.rank };
    T.closed += 1;
    if (!fromRoute && was) setHash('#area=' + was.a.id);
    var back = was && document.querySelector('#tc-' + was.a.id + '-' + was.tr.rank + ' .tc-open');
    (back || lastFocus || tabsEl).focus();
  }
  wrap.addEventListener('click', function (e) { if (e.target.closest('[data-close]')) closeFocus(false); });
  document.addEventListener('keydown', function (e) {
    if (wrap.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); closeFocus(false); return; }
    if (e.key === 'Tab') {                       // keep the focus inside the dialog
      var f = VL.$$('a[href], button, [tabindex]:not([tabindex="-1"])', dlg).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  var mq = window.matchMedia('(min-width: 760px)');
  function onWidth() {                           // the focus view follows the breakpoint (wide <-> tall drawing)
    if (!openTrace) return;
    var view = wide() ? 'wide' : 'tall';
    if (view === openTrace.view) return;
    var fig = dlg.querySelector('.tf-fig');
    var id = 'tf-' + openTrace.a.id + '-' + openTrace.tr.rank;
    fig.innerHTML = TD.svg(openTrace.tr, view, { id: id, title: chainTitle(openTrace.tr), desc: chainDesc(openTrace.a, openTrace.tr), nodeTitles: true });
    fig.setAttribute('data-view', view);
    openTrace.view = view;
    T.focus.view = view;
  }
  if (mq.addEventListener) mq.addEventListener('change', onWidth); else if (mq.addListener) mq.addListener(onWidth);

  /* ------------------------------------------------------------------ routing: #area=<id>&q=<rank> */
  function route() {
    var h = VL.params(), a = BY[h.area];
    if (!a) {
      closeFocus(true);
      if (!current) return select(initialArea());
      return Promise.resolve();
    }
    var rank = h.q ? parseInt(h.q, 10) : null;
    return select(a.id, {}).then(function () {
      var d = DATA[a.id], tr = null;
      if (d && rank) d.traces.forEach(function (t) { if (t.rank === rank) tr = t; });
      if (tr) openFocus(a, tr); else closeFocus(true);
    });
  }
  function initialArea() {
    var s = VL.store.get('traces.area');
    return BY[s] ? s : AREAS[0].id;
  }
  window.addEventListener('hashchange', route);

  window.VLApp = window.VLApp || {};
  window.VLApp.traces = {
    select: function (id) { return select(id, { user: true }); },
    open: function (id, rank) { location.hash = 'area=' + id + '&q=' + rank; },
    close: function () { closeFocus(false); },
    areas: function () { return AREAS.map(function (a) { return a.id; }); }
  };

  Promise.all([VL.fontsReady(), route()]).then(function () {
    M.tracesReadyMs = Math.round(performance.now());
    VL.setReady({ tracesArea: current });
  });
})();

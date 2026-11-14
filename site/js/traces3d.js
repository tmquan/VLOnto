/* VLOnto - question traces in the 3D legal network (traces.html): ONE WebGL scene with the whole 3D legal network of
   network-3d.html and all 540 traced answers of the 27 legal areas inside it (arXiv:2611.11426).
   - The network is drawn as network-3d.html draws it (js/netscene.js, shared by both pages): every document at its own
     place, its height the legal-force layer (Constitution on top), the change and legal-basis links as curves with the
     same detail policy; data/legal_network.js (40,816 documents) on wide screens, data/legal_network_lite.js (6,000)
     on phones as there (#ds=full|lite picks one), the citation links on the lite network only.
   - The traces live in it (data/traces/graph.js, scripts/site/trace_global.py): every traced law IS its network
     document; its chapters, sections, articles, clauses and points hang just under it, inside the gap above the next
     layer; the answers lie on a plane under the lowest layer, the questions on one further down, the terms they name
     in between, the other answers that cite the same provisions just under the answers, each area's name under its
     questions. On phones the traced laws the lite network lacks are added as documents of their own.
   - Everything is drawn at once: all documents, their links, all areas, questions and traces. Two constant levels:
     with nothing chosen everything is drawn at the light alpha (LIGHT); while traces are chosen, they are solid (their
     nodes and links opaque, their traced paths bold: navy core over the gold halo, js/paper3d.js VL.TraceLines; the V/W
     arms with the term -> defining clause hop) and every other item of the traces (questions, answers, other answers,
     terms, provisions, areas) drops to the faint alpha (FAINT), while the network's documents and links stay at LIGHT.
     Every traced path not chosen is a thread (v1.4): a 1-device-px GL line at THREAD_A, set so that where the 540
     traces bundle (up to 26 threads over one pixel on wide screens at the 99th percentile, 35 on phones) the
     accumulated opacity stays near 0.5 (x FAINT / LIGHT while something is chosen); the traces' context links are
     drawn only between chosen nodes (CTX_REST). The documents are mixed toward the page ground (as network-3d.html
     draws them); the trace nodes, the links and the threads are transparent (no depth write), so a faint node never
     covers what lies behind it. No area is dimmed and nothing fades with distance; a choice writes the alpha
     attributes once.
   - Colour (v1.4): by legal area by default - the 27 areas of the traces in --area-0..26 (css/site.css; 0-11 those of
     network-3d.html), ranked by the areas' documents in the whole network: each document in its area's colour, each
     trace node in the area of its law (laws, provisions) or of the first trace in list order that holds it
     (questions, answers, other answers, terms, area names); or by kind (the paper's class colours, the documents in the
     colour of a law). The legend's switch (VL.store 'traces3d-color'; #color=area|kind) changes the colours only: the
     choice, the alphas and the camera stay. LIGHT and FAINT scale the alpha of either colour.
   - The chosen traces' points (every node of graph.js t[].n) are drawn last, over every stroke: opaque, without depth
     test, at least their size at load, with an ink ring inside a ring of the ground's colour (ORDER: the draw order).
   - Several traces at once: a click on a question (list or scene) chooses it alone; the round button of its row,
     Space on the row or Ctrl/Cmd-click add or remove it; an area heading's 'All 20' chooses the area's 20 questions;
     'Clear', the panel's x and Esc choose none. The Fig. 5 hop panel shows the last chosen trace, with a '3 of 20'
     stepper through the chosen ones (titles and hop data from data/traces/<area>.js, loaded when first needed).
   - The camera is static: the whole scene is framed on load from the network page's direction and moves only when the
     reader moves it or asks for 'Zoom to selection' (all chosen traces) or 'Reset view'.
   - Call-outs (VL.Callouts): the layer names at their corners and, with nothing chosen, the 27 areas' names; the
     shown trace's question, provision and law (phones: question and provision) must be named, its term and area and
     the other chosen questions where they fit; never over ink, the panels or each other.
   - One side list of the 540 questions under the 27 area headings (data/traces/questions.js) with a search (words,
     English gloss, law name or number, area; diacritic-insensitive), arrow keys, Home / End.
   - Deep links: #q=<area>:<rank>; #q=<area>:<r1>,<r2>; #q=<a1>:<r1>,<r2>;<a2>:<r3> (the first listed is shown in the
     panel); #area=<area>&all=1 (the area's 20; &q=<rank> shows that one); v1's #area=<id>&q=<rank>; #area=<id> alone
     scrolls the list to the area. The page writes the form that matches the choice.
   - Without WebGL the page keeps the list, its search and the hop panel and draws the shown trace in 2D
     (js/trace-draw.js, the build-time drawing in the area file).
   window.__VLONTO_METRICS.traces and .callouts, and window.VLApp.traces, serve the interaction tests.
   Text follows the language mode of js/i18n.js (docs/i18n.md; dictionary js/i18n-3d.js, keys tr3d.*): EN shows the
   questions' English glosses, VI the Vietnamese titles, EN-VI both (as in v1). A mode change ('vl:lang') renders the
   text again in place and keeps the choice, the search, the camera, the open panel and the list's scroll and focus. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS, TD = VL.TraceDraw, NS = VL.NetScene;
  VL.chrome({ scene: true });
  M.page = 'traces';
  M.paperStyle = true;
  var IDX = window.VLONTO.traces_index;
  var T = M.traces = { available: false, areas: 0, groups: 0, shown: 0, query: '', loaded: [], selected: [], current: null, panel: null,
    traceSegments: 0, hops: 0, listItems: 0, renders: 0, frames: 0, errors: [], webgl: null, fallback: false, flights: 0, themeRenders: 0,
    cameraMoves: 0, selectionWrites: 0, sceneReady: false, colorBy: null, colorSwitches: 0, legendAreas: 0, legendMaxH: null };
  var esc = VL.esc, fmt = VL.fmt;
  /* a count that picks the English singular (en_one) */
  function nv(c) { return c === 1 ? 1 : fmt(c); }
  function tipAttr(k, vars) { var t = VL.tip(k, vars); return t ? ' title="' + esc(t) + '"' : ''; }
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host'), panel = VL.$('#panel'), tip = VL.$('#tip');
  var legendEl = VL.$('#legend'), statusEl = VL.$('#status'), listEl = VL.$('#tr-list'), searchEl = VL.$('#tr-search'), countEl = VL.$('#tr-count');
  var fbEl = VL.$('#tr-fallback'), veil = VL.$('#veil'), clearEl = VL.$('#tr-clear');
  var EXT = VL.ICON.external;
  /* a match score with two decimals, in the mode's number format (0.92; 0,92 in VI) */
  function f2(x) {
    if (x == null) return '–';
    var dec = '.';
    try { (VL.numberFormat().formatToParts(1.5) || []).forEach(function (p) { if (p.type === 'decimal') dec = p.value; }); } catch (e) { /* old engines */ }
    return Number(x).toFixed(2).replace('.', dec);
  }
  /* a link that opens in a new tab; the note for screen readers sits one level inside the visually hidden span, so it
     is clipped by its 1 px parent for every measuring tool too */
  function ext(href, text, sr) {
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + text + EXT + '<span class="sr-only"><span> (' +
      esc(sr || VL.U('tr3d.newTab')) + ')</span></span></a>';
  }
  function hideVeil() { if (veil) veil.classList.add('hidden'); }
  function veilText(s) { var v = VL.$('#veil-text'); if (v) v.textContent = s; }

  if (!IDX || !IDX.available || !IDX.areas || !IDX.areas.length) {
    VL.$('#tr-nodata').hidden = false;
    VL.$('#side').hidden = true;
    legendEl.hidden = true;
    hideVeil();
    T.reason = (IDX && IDX.reason) || 'data/traces/index.js missing';
    VL.fontsReady().then(function () { VL.setReady(); });
    return;
  }
  T.available = true;
  var AREAS = IDX.areas, BY = {}, AIX = {};
  AREAS.forEach(function (a, i) { BY[a.id] = a; AIX[a.id] = i; });
  T.areas = AREAS.length;

  function renderRevs() {
    var r = IDX.source_revisions || {};
    var revs = Object.keys(r).map(function (k) { return k.replace('tmquan/', '') + ' @' + String(r[k]).slice(0, 10); }).join(', ');
    VL.$('#tr-revs').innerHTML = VL.UH('tr3d.revs', { release: VL.releaseLabel(), date: IDX.generated || '', revs: revs });
  }
  renderRevs();

  var params = VL.params(), mobile = VL.isMobile();
  /* the network of network-3d.html: the full one on wide screens, the lite one on phones (#ds=full|lite) */
  var DS = params.ds === 'full' || params.ds === 'lite' ? params.ds : (mobile ? 'lite' : 'full');
  /* the light alpha: everything with nothing chosen, the network's documents and links always. Model renders of the
     load view, Labour and wages #3 and all 20 of Labour at 0.18, 0.3 and 0.45 in both themes (the v1.2 report): 0.18
     loses the network's links and the traces' strokes on the dark ground, 0.45 lets the 540 strokes and 40,816
     documents compete with a chosen trace; 0.3 keeps the network's layers and every trace legible in both themes.
     #light=<0..1> draws another level (model renders, tests) */
  var LIGHT = (function () { var v = parseFloat(params.light); return v > 0 && v <= 1 ? v : 0.3; })();
  var LIGHT32 = Math.fround(LIGHT);     // as the alpha buffers (Float32Array) hold it
  T.light = LIGHT;
  /* the faint alpha: every item of the traces not chosen while some trace is chosen (the reader's request after v1.2:
     the other questions and answers fade when one is chosen). The network's documents and links stay at LIGHT.
     Model renders of Labour and wages #3 and all 20 of Labour at 0.08, 0.1 and 0.12 in both themes and the colour
     difference of one item alone on the ground (the v1.3 report): the light theme decides; 0.08 is within 15 % of v1.1's
     0.07, which readers found nearly invisible; 0.1 leaves the 2 px provision dots at the edge of visibility; 0.12 keeps
     every item just visible on the white ground and, on the dark one, at well under half of its light-level contrast.
     #faint=<0..1> draws another level (model renders, tests) */
  var FAINT = (function () { var v = parseFloat(params.faint); return v >= 0 && v <= 1 ? v : 0.12; })();
  var FAINT32 = Math.fround(FAINT);
  T.faint = FAINT;

  /* ------------------------------------------------------------------ theme */
  var P = {}, TH = {};
  function readTheme() {
    P = VL.paperTheme();
    var pl = NS.planeTheme();
    /* documents in the paper's colour of a law ('work'); the network's links and the other answers' citations in one
       neutral tone (css/site.css --tr-link, a light grey on either ground): the class colours of the trace nodes and the
       traces' navy and gold stay the only colours that compete for attention */
    TH = { dark: P.dark, bg: P.bg, plane: pl.plane, planeOpacity: pl.planeOpacity, planeLine: pl.planeLine, planeLineOpacity: pl.planeLineOpacity,
      doc: P.cls.work, link: VL.tok('--tr-link') || P.leader,
      /* the 27 legal-area colours (css/site.css --area-0..26: 0-11 as network-3d.html, 12-26 for the rest), by rank */
      areas: VL.areaColors(27), areaNone: VL.tok('--area-none') || '#dcdee2', ink: P.ink };
    M.sceneBg = P.bg;
    M.traceCore = P.core;
  }
  readTheme();

  /* ------------------------------------------------------------------ the questions (one list, area by area) */
  /* an area's name: EN–VI its Vietnamese and English names (v1), EN or VI one name */
  function areaPair(a) { return VL.pair(a.label_vi, a.label_en); }
  /* every traced question (data/traces/questions.js, scripts/site/trace_site.py): {a: area index, id: area id, rank,
     vi: title, en: English gloss, law: {vi, en, number}, verified, match, hay: its folded search text, t: its trace};
     GROUPS[a] = the area's questions by rank; QNODE[node] = the questions of a question node */
  var QS = [], QBY = {}, GROUPS = AREAS.map(function () { return []; }), QNODE = {};
  function loadQuestions() {
    if (window.VLONTO.traces_questions) return Promise.resolve(window.VLONTO.traces_questions);
    return VL.loadScript('data/traces/' + ((IDX.questions && IDX.questions.file) || 'questions.js')).then(function () {
      if (!window.VLONTO.traces_questions) throw new Error('data/traces/questions.js did not register traces_questions');
      return window.VLONTO.traces_questions;
    });
  }
  /* search text: lower case without diacritics (đ -> d), so "lao dong" finds "lao động" */
  function fold(s) { return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase(); }
  /* the search: every word typed (folded, its edge punctuation dropped) starts a word of the entry - letters and digits
     make a word, so 'qh14' and '2019' find 45/2019/QH14 and a word being typed matches as a prefix */
  function words(raw) { return fold(raw).split(/\s+/).map(function (w) { return w.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, ''); }).filter(Boolean); }
  function hasWord(hay, w) {
    for (var i = hay.indexOf(w); i >= 0; i = hay.indexOf(w, i + 1)) if (i === 0 || !/[a-z0-9]/.test(hay.charAt(i - 1))) return true;
    return false;
  }
  function prepareQuestions(d) {
    var fi = {};
    d.fields.forEach(function (f, k) { fi[f] = k; });
    d.areas.forEach(function (ar) {
      var a = BY[ar.id];
      if (!a) return;
      ar.q.forEach(function (r) {
        var q = { a: AIX[a.id], id: a.id, rank: r[fi.rank], vi: r[fi.vi], en: r[fi.en], verified: !!r[fi.verified], match: r[fi.match],
          law: { vi: r[fi.law_vi], en: r[fi.law_en], number: r[fi.law_number] } };
        q.hay = fold([q.vi, q.en, q.law.vi, q.law.en, q.law.number, a.label_vi, a.label_en].join('\n'));
        QS.push(q);
        QBY[a.id + ':' + q.rank] = q;
        GROUPS[q.a].push(q);
      });
    });
    GROUPS.forEach(function (gq) { gq.sort(function (x, y) { return x.rank - y.rank; }); });
    T.listItems = QS.length;
  }
  function linkQuestionNodes() {
    G.t.forEach(function (t) {
      var q = QBY[AREAS[t.a].id + ':' + t.r];
      if (!q) return;
      q.t = t;
      t.q = q;
      (QNODE[t.co[0]] = QNODE[t.co[0]] || []).push(q);
    });
  }

  /* ------------------------------------------------------------------ the traces (data/traces/graph.js, v2) */
  /* G: i ids, c classes, p positions (the network's units x 10, z up), d {law node: network document id}, vi / en
     labels, u source links, e links by kind, t traces {a, r, n nodes, f foreground, e traced segments [i, j, style],
     co call-out nodes [question, answer, provision, law, term or -1, area]}, areas [{id, n: name node}].
     GPOS: scene positions (x, height = z x ZS, depth = y, as js/netscene.js places the documents); a law takes its
     document's exact position */
  var G = null, NG = 0, GPOS = null, GCLS = null, CNAME = [], TRK = {}, AREA_T = [], BYNODE = null, AD = {}, IS_WORK = null;
  /* point sizes of the trace nodes (world units, as the network's documents: js/netscene.js pointSize) */
  var SIZE = { area: 26, work: 18, chapter: 12, section: 11.5, article: 11, clause: 10, point: 9, term: 15, question: 22, answer: 17,
    other_question: 8 };
  function loadGraph() {
    if (window.VLONTO.traces_graph) return Promise.resolve(window.VLONTO.traces_graph);
    return VL.loadScript('data/traces/' + ((IDX.graph && IDX.graph.file) || 'graph.js')).then(function () {
      if (!window.VLONTO.traces_graph) throw new Error('data/traces/graph.js did not register traces_graph');
      return window.VLONTO.traces_graph;
    });
  }
  function prepareGraph(g) {
    if (g.v !== 2 || !g.d || !g.net) throw new Error('data/traces/graph.js is not a v2 graph (rebuild with scripts/site/trace_site.py)');
    G = g;
    NG = g.i.length;
    CNAME = g.classes;
    GCLS = Uint8Array.from(g.c);
    GPOS = new Float32Array(NG * 3);
    for (var i = 0; i < NG; i++) {
      GPOS[3 * i] = g.p[3 * i] / 10;
      GPOS[3 * i + 1] = g.p[3 * i + 2] / 10 * NS.ZS;
      GPOS[3 * i + 2] = g.p[3 * i + 1] / 10;
    }
    var wk = CNAME.indexOf('work');
    IS_WORK = new Uint8Array(NG);
    for (var j = 0; j < NG; j++) IS_WORK[j] = GCLS[j] === wk ? 1 : 0;
    AREA_T = AREAS.map(function () { return []; });
    g.t.forEach(function (t, k) { t.k = k; TRK[t.a + ':' + t.r] = t; if (AREA_T[t.a]) AREA_T[t.a].push(t); });
    AREA_T.forEach(function (l) { l.sort(function (x, y) { return x.r - y.r; }); });
    T.graph = { nodes: NG, links: Object.keys(g.e).reduce(function (s, k) { return s + g.e[k].length / 2; }, 0), traces: g.t.length,
      laws: Object.keys(g.d).length, networkDocs: g.net.nodes };
  }
  function cname(i) { return CNAME[GCLS[i]]; }
  function ptOf(i) { return { x: GPOS[3 * i], y: GPOS[3 * i + 1], z: GPOS[3 * i + 2] }; }
  function num(i) { return String(G.i[i]).split(':').pop(); }
  function key(t) { return AREAS[t.a].id + ':' + t.r; }
  /* [Vietnamese, English] name of a node: questions, answers and other answers by id (their titles are not in the graph) */
  function names(i) {
    var c = cname(i), q = c === 'question' && QNODE[i] ? QNODE[i][0] : null;
    if (q) return [q.vi, q.en || q.vi];      // a traced question: its title and English gloss (data/traces/questions.js)
    var k = { question: 'tr3d.name.question', answer: 'tr3d.name.answer', other_question: 'tr3d.name.otherQuestion' }[c];
    if (k) { var p = VL.kpair(k, { n: num(i) }); return [p.vi, p.en]; }
    return [G.vi[i] || G.i[i], G.en[i] || G.vi[i] || G.i[i]];
  }
  function classNames(c) {
    if (c === 'other_question') { var p = VL.kpair('tr3d.cls.otherQuestion'); return [p.vi, p.en]; }
    var k = VL.PAPER_CLASS[c];
    return k ? [k.vi, k.en] : [c, c];
  }
  /* traces that contain a node (built on first use) */
  function tracesOf(i) {
    if (!BYNODE) {
      BYNODE = {};
      G.t.forEach(function (t) { t.n.forEach(function (j) { (BYNODE[j] = BYNODE[j] || []).push(t.k); }); });
    }
    return BYNODE[i] || [];
  }
  function loadArea(a) {
    var k = 'traces_' + a.id;
    if (window.VLONTO[k]) { if (!AD[a.id]) indexArea(a, window.VLONTO[k]); return Promise.resolve(window.VLONTO[k]); }
    return VL.loadScript('data/traces/' + a.file).then(function () {
      var d = window.VLONTO[k];
      if (!d || !d.traces) throw new Error('data/traces/' + a.file + ' did not register ' + k);
      indexArea(a, d);
      return d;
    });
  }
  function indexArea(a, d) {
    if (T.loaded.indexOf(a.id) < 0) T.loaded.push(a.id);
    AD[a.id] = {};
    d.traces.forEach(function (tr) { AD[a.id][tr.rank] = tr; });
  }

  /* ------------------------------------------------------------------ the network (js/netscene.js) */
  /* D: the dataset (NS.prepare); WDOC[node] = the network point of a law (its document; on phones a traced law the
     lite network lacks is an extra point after the dataset's, EXTRA = those laws); TPT[node] = the trace point of every
     other node (TNODE = the reverse); DOCG[point] = the law node of a network point (-1: not traced) */
  var D = null, NP = 0, EXTRA = [], WDOC = null, TPT = null, TNODE = [], DOCG = null;
  function rankOfY(y) {
    var z = y / NS.ZS, best = 5, bd = Infinity;
    for (var r = 0; r <= 5; r++) { var d = Math.abs((D.layerZ[r] != null ? D.layerZ[r] : (5 - r) * 150) - z); if (d < bd) { bd = d; best = r; } }
    return best;
  }
  function linkNetwork(net) {
    D = NS.prepare(net, DS);
    WDOC = new Int32Array(NG).fill(-1);
    EXTRA = [];
    var inData = 0, dev = 0, laws = 0;
    for (var i = 0; i < NG; i++) {
      if (!IS_WORK[i]) continue;
      laws++;
      var id = G.d[String(i)], j = id != null ? D.idx[String(id)] : null;
      if (j != null) {
        inData++;
        for (var c = 0; c < 3; c++) { dev = Math.max(dev, Math.abs(GPOS[3 * i + c] - D.pos[3 * j + c])); GPOS[3 * i + c] = D.pos[3 * j + c]; }
        WDOC[i] = j;
      } else {
        WDOC[i] = D.N + EXTRA.length;
        EXTRA.push(i);
      }
    }
    NP = D.N + EXTRA.length;
    DOCG = new Int32Array(NP).fill(-1);
    for (var w = 0; w < NG; w++) if (WDOC[w] >= 0) DOCG[WDOC[w]] = w;
    TPT = new Int32Array(NG).fill(-1);
    TNODE = [];
    for (var n = 0; n < NG; n++) if (!IS_WORK[n]) { TPT[n] = TNODE.length; TNODE.push(n); }
    /* the laws' places agree with the network's (graph.js keeps tenths): the largest difference before snapping */
    T.network = { dataset: DS, docs: D.N, extra: EXTRA.length, points: NP, laws: laws, lawsInDataset: inData, lawPosMaxDev: Math.round(dev * 1000) / 1000,
      layers: D.layerZ, extent: D.extent, traceNodes: TNODE.length };
    M.dataset = DS;
    prepareAreas();
  }

  /* ------------------------------------------------------------------ colour by legal area */
  /* AREA_RANK[area] = its colour's index: the 27 areas ranked by their documents in the whole network (graph.js
     areas[].docs, the same on phones, where only the lite network is loaded; ties in list order), so the 12 most
     frequent take network-3d.html's 12 colours and the other 15 --area-12..26. NETA[network area index] = the area (the
     network's 51-entry list; its documents use exactly the 27 areas of the traces). NAREA[node]: a law its document's
     area (graph.js wa); a provision its law's (up the 'contains' links); a question, answer, other answer, term or area
     name the area of the first trace in list order (area, then rank) that holds it - SHARED counts the nodes that traces
     of two or more areas hold. AREA_Q[area] = the questions (traced and other answers) drawn in its colour */
  var AREA_RANK = null, AREA_ORDER = [], NETA = null, NAREA = null, AREA_Q = null, SHARED = 0;
  var STRUCT = { chapter: 1, section: 1, article: 1, clause: 1, point: 1 };
  /* the ranks need graph.js only: the legend and the side list's swatches get them before the network loads */
  function rankAreas() {
    var order = (G.areas || []).map(function (a, k) { return { a: AIX[a.id], docs: a.docs || 0, k: k }; }).filter(function (o) { return o.a != null; });
    order.sort(function (x, y) { return y.docs - x.docs || x.k - y.k; });
    AREA_RANK = new Int16Array(AREAS.length).fill(-1);
    order.forEach(function (o, r) { AREA_RANK[o.a] = r; });
    AREA_ORDER = order.map(function (o) { return o.a; });
  }
  function prepareAreas() {
    if (!AREA_RANK) rankAreas();
    NETA = (D.net.areas || []).map(function (a) { var id = Array.isArray(a) ? a[0] : (a && a.id); return AIX[id] != null ? AIX[id] : -1; });
    NAREA = new Int16Array(NG).fill(-1);
    var wa = G.wa || {};
    Object.keys(wa).forEach(function (k) { NAREA[+k] = wa[k]; });
    var first = new Int16Array(NG).fill(-1), multi = new Uint8Array(NG);
    G.t.forEach(function (t) { t.n.forEach(function (i) { if (first[i] < 0) first[i] = t.a; else if (first[i] !== t.a) multi[i] = 1; }); });
    var parent = new Int32Array(NG).fill(-1), cont = (G.e && G.e.contains) || [];
    for (var j = 0; j < cont.length; j += 2) parent[cont[j + 1]] = cont[j];
    AREA_Q = new Int32Array(AREAS.length);
    SHARED = 0;
    var sharedBy = {};
    for (var i = 0; i < NG; i++) {
      var c = cname(i);
      if (IS_WORK[i]) { if (NAREA[i] < 0) NAREA[i] = first[i]; continue; }
      if (STRUCT[c]) {
        var w = i, hops = 0;
        while (w >= 0 && !IS_WORK[w] && hops++ < 64) w = parent[w];
        NAREA[i] = w >= 0 && IS_WORK[w] && NAREA[w] >= 0 ? NAREA[w] : first[i];
        continue;
      }
      NAREA[i] = first[i];
      if (multi[i]) { SHARED++; sharedBy[c] = (sharedBy[c] || 0) + 1; }
      if ((c === 'question' || c === 'other_question') && NAREA[i] >= 0) AREA_Q[NAREA[i]]++;
    }
    var noDoc = 0;
    for (var j2 = 0; j2 < NP; j2++) if (docArea(j2) < 0) noDoc++;
    T.areaColour = { ranked: AREA_ORDER.map(function (a) { return AREAS[a].id; }), shared: SHARED, sharedByClass: sharedBy,
      unassigned: (function () { var u = 0; for (var q = 0; q < NG; q++) if (NAREA[q] < 0) u++; return u; })(), docsWithoutArea: noDoc,
      questions: AREAS.map(function (a, k) { return AREA_Q[k]; }) };
  }
  /* the colour of an area (its rank's token), or --area-none */
  function areaHex(a) { var r = a != null && a >= 0 ? AREA_RANK[a] : -1; return r >= 0 && TH.areas[r] ? TH.areas[r] : TH.areaNone; }
  /* the area of a network point (a document: its own area field; a traced law the lite network lacks: its law node's) */
  function docArea(j) { return j < D.N ? (D.area[j] >= 0 ? NETA[D.area[j]] : -1) : NAREA[EXTRA[j - D.N]]; }
  function docColor(j) { return state.colorBy === 'area' ? areaHex(docArea(j)) : TH.doc; }
  /* the documents' colours as their buffer holds them (snapshot): the distinct colours and each point's index */
  function docColorTable() {
    var col = netObj.geometry.attributes.aColor.array, pal = [], ix = {}, idx = new Array(NP);
    function h2(v) { var x = Math.round(v * 255); return (x < 16 ? '0' : '') + x.toString(16); }
    for (var j = 0; j < NP; j++) {
      var h = '#' + h2(col[3 * j]) + h2(col[3 * j + 1]) + h2(col[3 * j + 2]);
      if (ix[h] == null) { ix[h] = pal.length; pal.push(h); }
      idx[j] = ix[h];
    }
    return { palette: pal, idx: idx };
  }

  /* ------------------------------------------------------------------ three setup (as js/network3d.js) */
  function rgb(hex) { return VL.rawColor(hex, new THREE.Color()).toArray(); }
  /* depth fade shared by points and lines (js/netscene.js updateFog) */
  var FOG = { value: new THREE.Vector3(1, 1e6, 0) };
  /* #curves=0 draws straight links (one segment each); a software renderer (SwiftShader, llvmpipe) draws coarser curves
     as network-3d.html does; #curves=full keeps the full detail there too */
  var CURVES = params.curves !== '0', SOFT_GL = false, CURVE_FULL = params.curves === 'full';
  var renderer = null, scene, camera, controls, netObj = null, trObj = null, ptMat = null, trMat = null, netEdges = {}, trEdges = null, layerGroup = null;
  var threads = null, boldV = null, boldS = null, fgObj = null, fgMat = null, labelGroup = null, labels = [], callouts = null;
  var needsRender = true, tween = null;
  /* the reader's state: the chosen traces (sel, in list order: area, then rank), the one the panel shows (cur, an index
     of sel), the legend, the search text. No area is ever 'open': the 27 areas are one scene and one list */
  var state = { sel: [], cur: -1, legendOpen: !mobile, query: '', colorBy: 'area' };
  /* colour the points by legal area (the default: the 27 areas' colours) or by kind (the paper's class colours):
     #color=area|kind for links and tests, else the reader's last choice (VL.store), else area */
  var COLOR_KEY = 'traces3d-color';
  state.colorBy = (function () {
    var p = params.color, s = VL.store.get(COLOR_KEY);
    return p === 'area' || p === 'kind' ? p : (s === 'area' || s === 'kind' ? s : 'area');
  })();
  T.colorBy = state.colorBy;
  function current() { return state.cur >= 0 ? state.sel[state.cur] || null : null; }

  function webglOk() {
    try {
      var cv = document.createElement('canvas'), gl = cv.getContext('webgl2');
      if (!gl) return false;
      var lose = gl.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
      return true;
    } catch (e) { return false; }
  }
  function stageSize() { return { w: Math.max(50, host.clientWidth), h: Math.max(50, host.clientHeight) }; }
  function initThree() {
    var sz = stageSize();
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(sz.w, sz.h);
    renderer.setClearColor(TH.bg, 1);
    host.appendChild(renderer.domElement);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, sz.w / sz.h, 5, 80000);
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.09;
    controls.screenSpacePanning = true;
    controls.rotateSpeed = 0.55;
    controls.zoomSpeed = 0.9;
    controls.minDistance = 40;
    controls.maxDistance = 30000;
    controls.addEventListener('change', function () { needsRender = true; scheduleCallouts(); });
    controls.addEventListener('start', hideHint);
    labelGroup = new THREE.Group();
    scene.add(labelGroup);
    /* the traced paths: every trace a thin thread (GL lines, buildThreads), the chosen ones bold ribbons on top */
    boldS = VL.TraceLines({ depthTest: false, renderOrder: ORDER.boldS });
    boldV = VL.TraceLines({ depthTest: false, renderOrder: ORDER.boldV });
    scene.add(boldS.object);
    scene.add(boldV.object);
    try {
      var gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
      M.webglRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    } catch (e) { M.webglRenderer = null; }
    SOFT_GL = NS.softGL(M.webglRenderer);
    M.curveDetail = !CURVES ? 'straight' : SOFT_GL && !CURVE_FULL ? 'reduced' : 'full';
    window.addEventListener('resize', onResize);
    requestAnimationFrame(loop);
  }
  function onResize() {
    if (!renderer) return;
    var sz = stageSize();
    renderer.setSize(sz.w, sz.h);
    camera.aspect = sz.w / sz.h;
    camera.updateProjectionMatrix();
    updatePointScale();
    updateLabelSizes();
    fitLegendHeight();
    needsRender = true;
    scheduleCallouts();
  }
  function updatePointScale() {
    if (ptMat) ptMat.uniforms.uScale.value = renderer.domElement.height / (2 * Math.tan(camera.fov * Math.PI / 360));
    if (fgMat) fgUniforms();
  }
  function updateFog() { if (camera && D) NS.updateFog(FOG, camera, controls.target, D.extent, TH.dark); }
  function loop(t) {
    requestAnimationFrame(loop);
    if (tween) stepTween(t);
    var moved = controls.update();
    if (needsRender || moved || tween) {
      updateFog();
      renderer.render(scene, camera);
      T.frames++;
      needsRender = false;
    }
  }

  /* ------------------------------------------------------------------ scene objects */
  /* a trace node's colour: its area's (colour by area) or its class's (colour by kind) */
  function nodeColor(i) {
    if (state.colorBy === 'area' && NAREA) return areaHex(NAREA[i]);
    return kindColor(i);
  }
  function kindColor(i) {
    var c = cname(i);
    return c === 'work' ? TH.doc : (P.cls[c === 'other_question' ? 'question' : c] || '#9aa3ad');
  }
  function edgeColorOf(k, s, t) {
    if (k === 'cites' && cname(s) === 'other_question') return TH.link;   // 4,000 long citations: background, as the network's
    var c = k === 'contains' ? cname(t) : k === 'cites' ? 'answer' :
      k === 'mentions' || k === 'defines' ? 'term' : k === 'answers' ? 'answer' : 'area';
    return c === 'work' ? TH.doc : (P.cls[c] || '#9aa3ad');
  }
  function pairKey(a, b) { return a < b ? a * NG + b : b * NG + a; }
  /* TRACED: the traced segments of all 540 traces, once each ([i, j] graph nodes): the thin threads; STROKE_AREA: the
     area of the first trace in list order (area, then rank) that holds each (its colour by area). TL: every other link
     of the traces (other answers' citations, the provision chains off the traced paths, applies_to, ...): curves in their
     class colours, with the node -> links index (off, adj) a choice uses to make its own links opaque */
  var TRACED = [], STROKE_AREA = null, TL = null;
  var LIGHT_SEG = 8, TRACE_SEG = 16;
  /* v1.4, after the real-browser screenshots of v1.2 (CI, Chrome + SwiftShader): the 540 traces' light strokes (ribbons of
     the navy core at LIGHT) stacked into a solid navy mass (a near-white one in the dark theme). The traces not chosen are
     now threads: GL lines (THREE.LineSegments, 1 device px, no ribbon geometry), each in its base colour - its area's when
     colouring by area, the links' grey by kind - mixed halfway (THREAD_MIX) to the theme's ink, so that it reads over the
     network's light grey links, at THREAD_A: the alpha for which the 99th-percentile pixel of the load view keeps an
     accumulated opacity 1 - (1 - a)^n of about 0.47, n = the strokes over one device pixel (tools_lang3d/overlap14.py on
     the load view: p99 26 on wide screens, 1100 x 783 at 1 device px, full network; p99 35 on phones, 390 x 700 at 2);
     x FAINT / LIGHT while something is chosen. #thread=<alpha> overrides it (tests, previews) */
  /* colouring by area on wide screens the legend's top stays at or below LEGEND_TOP of the canvas (fitLegendHeight: it
     scrolls inside): the 27 areas' legend (400 x 568 px in EN-VI at 1440 x 900) would otherwise take the room left of
     the scene where the laws' call-outs go. All 540 traces chosen one by one at 1440 x 900 (tools_lang3d sweep): EN-VI
     25 traces with a must-show call-out hidden and 2,646 call-outs shown without the cap, 51 at 0.35, 8 at 0.45, 1 and
     4,603 at 0.55, 2 at 0.6; EN 1 -> 0 (5,035 -> 5,319 shown), VI 1 at 0.55. #lgtop=<fraction> overrides it */
  var LEGEND_TOP = (function () { var v = parseFloat(params.lgtop); return v >= 0 && v < 1 ? v : 0.55; })();
  var THREAD_A = (function () { var v = parseFloat(params.thread); return v > 0 && v <= 1 ? v : (mobile ? 0.018 : 0.024); })(), THREAD_MIX = 0.5;
  /* the context links (9,198: other answers' citations, the provision chains off the paths, terms, applies_to) are drawn
     only between chosen nodes (alpha 1): at the load view their overlap reaches 173 links per device pixel at the 99th
     percentile (citations 177), so any visible alpha stacks into a solid mass (at 0.3 the median covered pixel is at
     0.94) and the alpha for an accumulated 0.5 (0.004) is below one 8-bit step */
  var CTX_REST = 0;
  var TH_VS = ['attribute vec3 aColor; varying vec3 vColor;',
    'void main() { vColor = aColor; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }'].join('\n');
  var TH_FS = ['uniform float uOpacity; varying vec3 vColor;',
    'void main() { gl_FragColor = vec4(vColor, uOpacity); }'].join('\n');
  var BOLD = mobile ? 1.3 : 1.5, FG_SIZE = 1.3;
  /* the draw order. three.js draws the opaque documents first (depth written), then the transparent objects by
     renderOrder: the layer and Q&A planes 0, the network's legal-basis / citation links 1 and change links 2, the traces'
     context links 3, the trace nodes 4, the threads of every trace 5, the chosen traces' bold paths (structural
     8-10, verified 11-13: halo2, halo, core), the chosen traces' points 20 (no depth test: over every stroke), the
     call-outs' leaders 29 and labels 30 (js/labels3d.js) */
  var ORDER = { planes: 0, netLinks: 1, netChange: 2, context: 3, traceNodes: 4, strokes: 5, boldS: 8, boldV: 11, chosen: 20 };
  function buildScene() {
    var t0 = performance.now();
    /* 1. the network's documents, sized as on network-3d.html, and the traced laws the dataset lacks */
    var size = new Float32Array(NP), pos = D.pos;
    size.set(NS.pointSizes(D));
    if (EXTRA.length) { pos = new Float32Array(NP * 3); pos.set(D.pos); }
    EXTRA.forEach(function (gi, k) {
      var j = D.N + k;
      for (var c = 0; c < 3; c++) pos[3 * j + c] = GPOS[3 * gi + c];
      size[j] = NS.pointSize(rankOfY(GPOS[3 * gi + 1]), 0);
    });
    netObj = points(pos, size, NP, 2);
    /* 2. the trace nodes other than the laws: see-through spheres at their alpha (js/netscene.js PT_FS_A), no depth
       write, the shared uniforms of the documents' material */
    var NT = TNODE.length, tp = new Float32Array(NT * 3), ts = new Float32Array(NT);
    TNODE.forEach(function (gi, k) {
      for (var c = 0; c < 3; c++) tp[3 * k + c] = GPOS[3 * gi + c];
      ts[k] = SIZE[cname(gi)] || 9;
    });
    if (!trMat) trMat = new THREE.ShaderMaterial({ uniforms: ptMat.uniforms, vertexShader: NS.PT_VS, fragmentShader: NS.PT_FS_A, transparent: true, depthWrite: false });
    trObj = points(tp, ts, NT, ORDER.traceNodes, trMat);
    updatePointScale();
    /* 3. the network's links (js/netscene.js: segments per kind and dataset, citation links on the lite network only) */
    netKeys().forEach(buildNetEdges);
    /* 4. the traces' links and their traced paths; 5. the layer planes */
    buildTraceLinks();
    buildLayers();
    applyColors();
    applySelection();
    T.edgeCost = edgeCost();
    M.nodes = NP;
    M.edges = Object.keys(netEdges).reduce(function (s, k) { return s + netEdges[k].m; }, 0);
    T.buildMs = Math.round(performance.now() - t0);
  }
  /* a Points object of the scene: the documents' material (an opaque sphere mixed toward the ground by its alpha, as
     on network-3d.html) unless another is given */
  function points(pos, size, n, order, mat) {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(n).fill(LIGHT), 1));
    g.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
    g.computeBoundingSphere();
    if (!ptMat) {
      ptMat = new THREE.ShaderMaterial({
        uniforms: { uScale: { value: 1 }, uBg: { value: VL.rawColor(TH.bg, new THREE.Color()) }, uFog: FOG, uRim: { value: TH.dark ? 0.7 : 0.84 } },
        vertexShader: NS.PT_VS, fragmentShader: NS.PT_FS, transparent: false, depthWrite: true
      });
    }
    var o = new THREE.Points(g, mat || ptMat);
    o.renderOrder = order;
    scene.add(o);
    return o;
  }
  function netKeys() { return NS.EDGE_KEYS.filter(function (k) { return k !== 'citation' || DS === 'lite'; }); }
  function buildNetEdges(k) {
    var pairs = D.edges[k], m = pairs.length / 2, S = NS.segsFor(k, D.N, { curves: CURVES, soft: SOFT_GL, full: CURVE_FULL });
    var A = new Float32Array(m * 3), B = new Float32Array(m * 3), al = new Float32Array(m).fill(1);
    for (var e = 0; e < m; e++) {
      var s = pairs[2 * e], t = pairs[2 * e + 1];
      A[3 * e] = D.pos[3 * s]; A[3 * e + 1] = D.pos[3 * s + 1]; A[3 * e + 2] = D.pos[3 * s + 2];
      B[3 * e] = D.pos[3 * t]; B[3 * e + 1] = D.pos[3 * t + 1]; B[3 * e + 2] = D.pos[3 * t + 2];
    }
    var obj = new THREE.LineSegments(NS.curveGeometry(S, A, B, al, null, D.extent), NS.curveMaterial(false, 1, FOG));
    obj.frustumCulled = false;
    obj.renderOrder = NS.KINDS.indexOf(k) >= 0 ? ORDER.netChange : ORDER.netLinks;
    scene.add(obj);
    netEdges[k] = { obj: obj, m: m, seg: S };
    M.edgeSegments = M.edgeSegments || {};
    M.edgeSegments[k] = S;
  }
  function buildTraceLinks() {
    var traced = new Set();
    TRACED = [];
    var sa = [];
    G.t.forEach(function (t) {
      var e = t.e;
      for (var j = 0; j < e.length; j += 3) {
        var kk = pairKey(e[j], e[j + 1]);
        if (!traced.has(kk)) { traced.add(kk); TRACED.push([e[j], e[j + 1]]); sa.push(t.a); }
      }
    });
    STROKE_AREA = Int16Array.from(sa);
    var kinds = G.kinds || Object.keys(G.e), ss = [], tt = [], ki = [];
    kinds.forEach(function (k, n) {
      var arr = G.e[k] || [];
      for (var j = 0; j < arr.length; j += 2) {
        if (traced.has(pairKey(arr[j], arr[j + 1]))) continue;
        ss.push(arr[j]); tt.push(arr[j + 1]); ki.push(n);
      }
    });
    var m = ss.length;
    TL = { s: Int32Array.from(ss), t: Int32Array.from(tt), k: Uint8Array.from(ki), m: m, kinds: kinds };
    var deg = new Int32Array(NG + 1), e2;
    for (e2 = 0; e2 < m; e2++) { deg[TL.s[e2]]++; deg[TL.t[e2]]++; }
    var off = new Int32Array(NG + 1);
    for (var i = 0; i < NG; i++) off[i + 1] = off[i] + deg[i];
    var fill = off.slice(0, NG), adj = new Int32Array(off[NG]);
    for (e2 = 0; e2 < m; e2++) { adj[fill[TL.s[e2]]++] = e2; adj[fill[TL.t[e2]]++] = e2; }
    TL.off = off;
    TL.adj = adj;
    var S = !CURVES ? 1 : (SOFT_GL && !CURVE_FULL ? 4 : 8);
    var A = new Float32Array(3 * m), B = new Float32Array(3 * m), al = new Float32Array(m).fill(CTX_REST), col = new Float32Array(3 * m);
    for (e2 = 0; e2 < m; e2++) {
      var a = TL.s[e2], b = TL.t[e2];
      for (var c = 0; c < 3; c++) { A[3 * e2 + c] = GPOS[3 * a + c]; B[3 * e2 + c] = GPOS[3 * b + c]; }
    }
    var obj = new THREE.LineSegments(NS.curveGeometry(S, A, B, al, col, D.extent), NS.curveMaterial(true, 1, FOG));
    obj.frustumCulled = false;
    obj.renderOrder = ORDER.context;
    scene.add(obj);
    trEdges = { obj: obj, m: m, seg: S };
    buildThreads();
    T.traced = { segments: TRACED.length, contextLinks: m, strokeSegments: threads.pieces };
  }
  /* the threads: every traced segment once, its curve in LIGHT_SEG pieces (two vertices each), a colour per vertex */
  function buildThreads() {
    var segN = CURVES ? LIGHT_SEG : 1, n = TRACED.length, pos = new Float32Array(n * segN * 6);
    TRACED.forEach(function (pr, i) {
      var pts = NS.curvePts(ptOf(pr[0]), ptOf(pr[1]), segN);
      for (var q = 0; q < segN; q++) {
        var a = pts[q], b = pts[q + 1], o = (i * segN + q) * 6;
        pos[o] = a.x; pos[o + 1] = a.y; pos[o + 2] = a.z; pos[o + 3] = b.x; pos[o + 4] = b.y; pos[o + 5] = b.z;
      }
    });
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(n * segN * 6), 3));
    var mat = new THREE.ShaderMaterial({ uniforms: { uOpacity: { value: THREAD_A } }, vertexShader: TH_VS, fragmentShader: TH_FS,
      transparent: true, depthWrite: false, depthTest: true });
    var obj = new THREE.LineSegments(g, mat);
    obj.renderOrder = ORDER.strokes;
    obj.frustumCulled = false;
    scene.add(obj);
    threads = { obj: obj, mat: mat, segN: segN, n: n, pieces: n * segN };
  }
  /* a thread's colour: its base (its area's by area; the links' grey by kind) mixed THREAD_MIX of the way to the ink
     (in sRGB, per channel, rounded to 8 bits) */
  var THREAD_HEX = {};
  function threadMix(base) {
    var key = base + TH.ink;
    if (THREAD_HEX[key]) return THREAD_HEX[key];
    var a = rgb(base), b = rgb(TH.ink);
    return (THREAD_HEX[key] = '#' + [0, 1, 2].map(function (c) {
      var v = Math.round((a[c] * (1 - THREAD_MIX) + b[c] * THREAD_MIX) * 255); return (v < 16 ? '0' : '') + v.toString(16);
    }).join(''));
  }
  function threadHex(i) { return threadMix(state.colorBy === 'area' ? areaHex(STROKE_AREA[i]) : TH.link); }
  /* per-frame cost of the links: vertices through the shaders and line segments drawn, the network's and the traces' */
  function edgeCost() {
    var c = { curves: CURVES, detail: M.curveDetail, links: 0, vertices: 0, segments: 0, trace: { links: trEdges.m, vertices: trEdges.m * (trEdges.seg + 1),
      segments: trEdges.m * trEdges.seg, strokes: threads.pieces } };
    Object.keys(netEdges).forEach(function (k) { var eo = netEdges[k]; c.links += eo.m; c.vertices += eo.m * (eo.seg + 1); c.segments += eo.m * eo.seg; });
    return c;
  }
  /* the six legal-force layers of network-3d.html and, under the lowest, the answers' and questions' planes */
  function buildLayers() {
    if (layerGroup) {
      scene.remove(layerGroup);
      layerGroup.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    }
    layerGroup = NS.layerPlanes(D, TH);
    [G.planes.z_answer, G.planes.z_question].forEach(function (z) { layerGroup.add(NS.planeAt(z * NS.ZS, D.extent * 1.06, TH)); });
    scene.add(layerGroup);
  }
  function applyColors() {
    var cache = {};
    function c3(hex) { return cache[hex] || (cache[hex] = rgb(hex)); }
    var col = netObj.geometry.attributes.aColor.array, i;
    for (i = 0; i < NP; i++) { var cd = c3(docColor(i)); col[3 * i] = cd[0]; col[3 * i + 1] = cd[1]; col[3 * i + 2] = cd[2]; }
    netObj.geometry.attributes.aColor.needsUpdate = true;
    var tc = trObj.geometry.attributes.aColor.array;
    for (i = 0; i < TNODE.length; i++) { var c = c3(nodeColor(TNODE[i])); tc[3 * i] = c[0]; tc[3 * i + 1] = c[1]; tc[3 * i + 2] = c[2]; }
    trObj.geometry.attributes.aColor.needsUpdate = true;
    /* the network's links: one neutral colour, each kind at its network-3d.html opacity times LIGHT */
    var lc = c3(TH.link);
    Object.keys(netEdges).forEach(function (k) {
      var u = netEdges[k].obj.material.uniforms;
      u.uColA.value.setRGB(lc[0], lc[1], lc[2]);
      u.uColB.value.setRGB(lc[0], lc[1], lc[2]);
      u.uOpacity.value = NS.edgeOpacity(k, TH.dark, D.N) * LIGHT;
    });
    var f = TH.dark ? 0.78 : 0.86, ec = trEdges.obj.geometry.attributes.aColor.array;
    for (var e = 0; e < TL.m; e++) {
      var c0 = c3(edgeColorOf(TL.kinds[TL.k[e]], TL.s[e], TL.t[e]));
      ec[3 * e] = c0[0] * f; ec[3 * e + 1] = c0[1] * f; ec[3 * e + 2] = c0[2] * f;
    }
    trEdges.obj.geometry.attributes.aColor.needsUpdate = true;
    var thc = threads.obj.geometry.attributes.aColor.array, per = threads.segN * 2;
    for (var s2 = 0; s2 < threads.n; s2++) {
      var tc3 = c3(threadHex(s2));
      for (var v = 0; v < per; v++) { var o3 = 3 * (s2 * per + v); thc[o3] = tc3[0]; thc[o3 + 1] = tc3[1]; thc[o3 + 2] = tc3[2]; }
    }
    threads.obj.geometry.attributes.aColor.needsUpdate = true;
    threads.mat.uniforms.uOpacity.value = strokeAlpha;
    VL.rawColor(TH.bg, ptMat.uniforms.uBg.value);
    ptMat.uniforms.uRim.value = TH.dark ? 0.7 : 0.84;
    needsRender = true;
  }

  /* ------------------------------------------------------------------ the choice: solid traces, the other traces faint */
  /* SELW: the network points the last choice set to 1 (put back to LIGHT by the next); the trace points and links are
     all written by every choice (FAINT while something is chosen, LIGHT with nothing chosen, 1 for the chosen traces'
     own). The attributes are written once per choice, never per frame; strokeAlpha is the threads' opacity (THREAD_A,
     x FAINT / LIGHT while something is chosen); the context links are 0 unless both ends are chosen (CTX_REST) */
  var SELW = { net: [], tr: [], links: [] }, selPaths = [], strokeAlpha = THREAD_A;
  function chosenNodes() {
    var has = new Uint8Array(NG), list = [];
    state.sel.forEach(function (t) { t.n.forEach(function (i) { if (!has[i]) { has[i] = 1; list.push(i); } }); });
    return { list: list, has: has };
  }
  function applySelection() {
    if (!netObj) return;
    var t0 = performance.now();
    var na = netObj.geometry.attributes.aAlpha, ta = trObj.geometry.attributes.aAlpha, la = trEdges.obj.geometry.attributes.aAlpha;
    var rest = state.sel.length ? FAINT : LIGHT;
    SELW.net.forEach(function (j) { na.array[j] = LIGHT; });
    ta.array.fill(rest);
    la.array.fill(CTX_REST);
    strokeAlpha = state.sel.length ? THREAD_A * FAINT / LIGHT : THREAD_A;
    threads.mat.uniforms.uOpacity.value = strokeAlpha;
    var ch = chosenNodes(), net = [], tr = [], links = [];
    ch.list.forEach(function (i) {
      if (IS_WORK[i]) { na.array[WDOC[i]] = 1; net.push(WDOC[i]); } else { ta.array[TPT[i]] = 1; tr.push(TPT[i]); }
      for (var q = TL.off[i]; q < TL.off[i + 1]; q++) {
        var e = TL.adj[q], o = TL.s[e] === i ? TL.t[e] : TL.s[e];
        if (ch.has[o] && la.array[e] !== 1) { la.array[e] = 1; links.push(e); }
      }
    });
    SELW = { net: net, tr: tr, links: links };
    na.needsUpdate = true;
    ta.needsUpdate = true;
    la.needsUpdate = true;
    drawSelected();
    T.selectionWrites++;
    T.selectMs = Math.round((performance.now() - t0) * 10) / 10;
    T.solid = { docs: net.length, traceNodes: tr.length, links: links.length };
    needsRender = true;
  }
  /* the paper's trace widths scaled by BOLD: a chosen trace stands out from the light scene */
  function boldStyle(w) {
    var st = VL.traceStyle(P, w);
    Object.keys(st.widths).forEach(function (k) { st.widths[k] *= BOLD; });
    return st;
  }
  /* the chosen traces' traced paths, each segment once (text-verified wins over structural) */
  function drawSelected() {
    var ver = new Set(), seen = new Set(), v = [], s = [];
    state.sel.forEach(function (t) { var e = t.e; for (var j = 0; j < e.length; j += 3) if (e[j + 2] === 1) ver.add(pairKey(e[j], e[j + 1])); });
    state.sel.forEach(function (t) {
      var e = t.e;
      for (var j = 0; j < e.length; j += 3) {
        var kk = pairKey(e[j], e[j + 1]);
        if (seen.has(kk)) continue;
        seen.add(kk);
        (ver.has(kk) ? v : s).push(NS.curvePts(ptOf(e[j]), ptOf(e[j + 1]), CURVES ? TRACE_SEG : 1));
      }
    });
    selPaths = v.concat(s);
    boldV.setStyle(boldStyle(1));
    boldS.setStyle(boldStyle(0.55));
    boldS.setStyle({ opacity: P.dark ? 0.6 : 0.62 });
    boldV.setPaths(v);
    boldS.setPaths(s);
    drawFgNodes();
    T.traceSegments = boldV.count() + boldS.count();
    T.traceVerified = boldV.count();
    T.traceStructural = boldS.count();
    needsRender = true;
  }
  /* the chosen traces' points, drawn last over every stroke (renderOrder ORDER.chosen, no depth test): every node of the
     chosen traces (graph.js t[].n: the question, its answer, the other answers, the provisions, the terms, the area and
     the laws), opaque in its colour (area or kind), no fog, at least as large as at load (x FG_SIZE, or its load size +
     two rings) and at least FG_MIN_PX across, with two thin rings: the ink of the theme (apart from the ground) inside
     a ring of the ground's colour (apart from the navy core or the gold halo under it). Far ones first */
  var FG_MIN_PX = 9, FG_RING_PX = 1.25, fgNodes = [];
  var FG_VS = [
    'attribute vec3 aColor; attribute float aSize;',
    'uniform float uScale; uniform float uMinPx; uniform float uPad;',
    'varying vec3 vColor; varying float vPx;',
    'void main() {',
    '  vColor = aColor;',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  float s = clamp(aSize * uScale / max(1.0, -mv.z), 2.0, 56.0);',
    '  vPx = min(64.0, max(max(s * ' + FG_SIZE.toFixed(2) + ', s + uPad), uMinPx));',
    '  gl_PointSize = vPx;',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  var FG_FS = [
    'uniform vec3 uBg; uniform vec3 uInk; uniform float uRing;',
    'varying vec3 vColor; varying float vPx;',
    'void main() {',
    '  vec2 c = gl_PointCoord - vec2(0.5); float R = 0.5 * vPx, d = length(c) * vPx;',
    '  if (d > R) discard;',
    '  if (d > R - uRing) { gl_FragColor = vec4(uBg, 1.0); return; }',
    '  if (d > R - 2.0 * uRing) { gl_FragColor = vec4(uInk, 1.0); return; }',
    '  float r = d / max(1.0, R - 2.0 * uRing);',
    '  gl_FragColor = vec4(min(vec3(1.0), vColor * (0.92 + 0.1 * (1.0 - r * r))), 1.0);',
    '}'].join('\n');
  function fgUniforms() {
    var dpr = renderer ? renderer.getPixelRatio() : 1;
    fgMat.uniforms.uMinPx.value = FG_MIN_PX * dpr;
    fgMat.uniforms.uRing.value = FG_RING_PX * dpr;
    fgMat.uniforms.uPad.value = 4 * FG_RING_PX * dpr + 0.5;
    VL.rawColor(TH.ink, fgMat.uniforms.uInk.value);
  }
  function drawFgNodes() {
    if (fgObj) { scene.remove(fgObj); fgObj.geometry.dispose(); fgObj = null; }
    T.fgDrawn = 0;
    if (!state.sel.length || !netObj) return;
    var ids = chosenNodes().list;
    var cp = camera.position, d2 = function (i) {
      var dx = GPOS[3 * i] - cp.x, dy = GPOS[3 * i + 1] - cp.y, dz = GPOS[3 * i + 2] - cp.z; return dx * dx + dy * dy + dz * dz;
    };
    ids.sort(function (a, b) { return d2(b) - d2(a); });
    var n = ids.length, pos = new Float32Array(3 * n), col = new Float32Array(3 * n), sz = new Float32Array(n);
    fgNodes = ids.slice();
    var na = netObj.geometry.attributes, ta = trObj.geometry.attributes;
    ids.forEach(function (i, j) {
      var src = IS_WORK[i] ? na : ta, k = IS_WORK[i] ? WDOC[i] : TPT[i];
      for (var c = 0; c < 3; c++) { pos[3 * j + c] = GPOS[3 * i + c]; col[3 * j + c] = src.aColor.array[3 * k + c]; }
      sz[j] = IS_WORK[i] ? Math.max(SIZE.work, src.aSize.array[k]) : src.aSize.array[k];
    });
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
    if (!fgMat) {
      fgMat = new THREE.ShaderMaterial({
        uniforms: { uScale: ptMat.uniforms.uScale, uBg: ptMat.uniforms.uBg, uInk: { value: new THREE.Color() }, uMinPx: { value: FG_MIN_PX },
          uRing: { value: FG_RING_PX }, uPad: { value: 5 } },
        vertexShader: FG_VS, fragmentShader: FG_FS, transparent: true, depthTest: false, depthWrite: false
      });
    }
    fgUniforms();
    fgObj = new THREE.Points(g, fgMat);
    fgObj.renderOrder = ORDER.chosen;
    fgObj.frustumCulled = false;
    scene.add(fgObj);
    T.fgDrawn = n;
  }

  /* ------------------------------------------------------------------ camera */
  /* the network page's direction (js/network3d.js fitAll) */
  var DIR = new THREE.Vector3(0.18, 0.5, 1).normalize();
  /* phones: the hop sheet takes up to 46 % of the stage; the whole scene is framed above it, so a choice never needs
     the camera to move */
  var SHEET = 0.46;
  function boxIn(el) {
    if (!el || el.classList.contains('hidden') || el.hidden) return null;
    var b = el.getBoundingClientRect(), hr = host.getBoundingClientRect();
    return b.width > 1 && b.height > 1 ? { x0: b.left - hr.left, y0: b.top - hr.top, x1: b.right - hr.left, y1: b.bottom - hr.top } : null;
  }
  /* where the whole scene is framed (on load and by Reset view). The scene is taller than wide (six layers and the Q&A
     planes), so it takes the canvas's full height: on wide screens from below the stage tools and the hint to the
     bottom (the narrow legend lies over the scene's lower left, away from the questions at its bottom centre; the open
     hop panel lies over its right part and a call-out whose node is under it is occluded), on phones above the hop sheet
     at its tallest and below the hint. The same before and after a choice, so a choice never needs the camera to move */
  function homeRect() {
    var sz = stageSize(), r = { x0: 0, y0: 0, x1: sz.w, y1: sz.h - 8 }, h = boxIn(VL.$('#hint', stage));
    if (mobile) r.y1 = sz.h * (1 - SHEET) - 6;
    else { var tools = boxIn(VL.$('.stage-tools', stage)); if (tools) r.y0 = Math.max(r.y0, tools.y1 + 6); }
    if (h) r.y0 = Math.max(r.y0, h.y1 + 6);
    if (r.y1 - r.y0 < sz.h * 0.3) r.y1 = Math.min(sz.h, r.y0 + sz.h * 0.3);
    return r;
  }
  /* the part of the canvas the overlays leave free (CSS px): left of the side panel (on phones above the bottom sheet),
     and above the legend when the legend spans most of that width */
  function freeRect() {
    var sz = stageSize(), r = { x0: 0, y0: 0, x1: sz.w, y1: sz.h }, hr = host.getBoundingClientRect();
    if (panel && !panel.classList.contains('hidden')) {
      var pr = panel.getBoundingClientRect();
      if (pr.width > 1 && pr.height > 1) {
        if (pr.top - hr.top > sz.h * 0.2) r.y1 = Math.max(sz.h * 0.35, pr.top - hr.top);
        else if (pr.left - hr.left > sz.w * 0.2) r.x1 = Math.max(sz.w * 0.4, pr.left - hr.left);
      }
    }
    if (legendEl && !legendEl.classList.contains('hidden')) {
      var lr = legendEl.getBoundingClientRect();
      if (lr.width > 0.45 * (r.x1 - r.x0) && lr.top - hr.top > sz.h * 0.4) r.y1 = Math.min(r.y1, Math.max(sz.h * 0.45, lr.top - hr.top - 6));
    }
    return r;
  }
  /* camera for the box (lo, hi) seen along dir: the closest distance at which the box fits the rectangle rect of the
     canvas with the margin; the camera is then shifted sideways so the box centre lands on the rectangle's centre */
  function fitBox(lo, hi, dir, margin, rect) {
    var sz = stageSize(), c = new THREE.Vector3().addVectors(lo, hi).multiplyScalar(0.5);
    dir = dir.clone().normalize();
    rect = rect || { x0: 0, y0: 0, x1: sz.w, y1: sz.h };
    var rw = Math.max(50, rect.x1 - rect.x0), rh = Math.max(50, rect.y1 - rect.y0), tanH = Math.tan(camera.fov * Math.PI / 360);
    var fovSub = 2 * Math.atan(tanH * rh / sz.h) * 180 / Math.PI;
    var cam = new THREE.PerspectiveCamera(fovSub, rw / rh, 1, 1e6), v = new THREE.Vector3();
    var corners = [];
    for (var x = 0; x < 2; x++) for (var y = 0; y < 2; y++) for (var z = 0; z < 2; z++) corners.push(new THREE.Vector3(x ? hi.x : lo.x, y ? hi.y : lo.y, z ? hi.z : lo.z));
    var m = margin || 0.06;
    function ok(d) {
      cam.position.copy(c).addScaledVector(dir, d);
      cam.lookAt(c);
      cam.updateMatrixWorld();
      for (var i = 0; i < corners.length; i++) {
        v.copy(corners[i]).project(cam);
        if (v.z > 1 || Math.abs(v.x) > 1 - 2 * m || Math.abs(v.y) > 1 - 2 * m) return false;
      }
      return true;
    }
    var a = 1, b = 64;
    while (!ok(b) && b < 1e6) b *= 2;
    for (var it = 0; it < 30; it++) { var mid = (a + b) / 2; if (ok(mid)) b = mid; else a = mid; }
    var fwd = dir.clone().negate(), right = new THREE.Vector3().crossVectors(fwd, camera.up).normalize();
    var up = new THREE.Vector3().crossVectors(right, fwd), halfH = b * tanH, halfW = halfH * sz.w / sz.h;
    var ncx = (rect.x0 + rect.x1) / sz.w - 1, ncy = 1 - (rect.y0 + rect.y1) / sz.h;
    var target = c.clone().addScaledVector(right, -ncx * halfW).addScaledVector(up, -ncy * halfH);
    return { pos: target.clone().addScaledVector(dir, b), target: target };
  }
  /* refine a fit on the points themselves (pts: x, y, z, ...): the box's near corners project wider than any point, so
     the box alone leaves the scene smaller than the rectangle allows. Project the points, move the camera along its
     axis until their extent fills the rectangle (less the margin) and sideways until their middle is its middle; a few
     rounds, as moving changes the perspective a little. The view keeps its direction */
  function fitPoints(f, margin, rect, pts) {
    var sz = stageSize(), cam = new THREE.PerspectiveCamera(camera.fov, sz.w / sz.h, 1, 1e6), v = new THREE.Vector3();
    var k = sz.h / (2 * Math.tan(camera.fov * Math.PI / 360)), n = pts.length / 3;
    var rw = (rect.x1 - rect.x0) * (1 - 2 * margin), rh = (rect.y1 - rect.y0) * (1 - 2 * margin);
    var pos = f.pos.clone(), target = f.target.clone(), back = new THREE.Vector3(), right = new THREE.Vector3(), up = new THREE.Vector3();
    for (var it = 0; it < 4; it++) {
      cam.position.copy(pos); cam.up.copy(camera.up); cam.lookAt(target); cam.updateMatrixWorld();
      var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (var i = 0; i < n; i++) {
        v.set(pts[3 * i], pts[3 * i + 1], pts[3 * i + 2]).project(cam);
        var sx = (v.x + 1) / 2 * sz.w, sy = (1 - v.y) / 2 * sz.h;
        if (sx < x0) x0 = sx;
        if (sx > x1) x1 = sx;
        if (sy < y0) y0 = sy;
        if (sy > y1) y1 = sy;
      }
      if (!(x1 > x0 && y1 > y0)) break;
      var s = Math.min(rw / (x1 - x0), rh / (y1 - y0)), d = pos.distanceTo(target) / s;
      back.subVectors(pos, target).normalize();
      right.setFromMatrixColumn(cam.matrixWorld, 0);
      up.setFromMatrixColumn(cam.matrixWorld, 1);
      var dx = ((x0 + x1) / 2 - sz.w / 2) * s - ((rect.x0 + rect.x1) / 2 - sz.w / 2);
      var dy = ((y0 + y1) / 2 - sz.h / 2) * s - ((rect.y0 + rect.y1) / 2 - sz.h / 2);
      target.addScaledVector(right, dx * d / k).addScaledVector(up, -dy * d / k);
      pos.copy(target).addScaledVector(back, d);
    }
    return { pos: pos, target: target };
  }
  function pointsOf(ids) {
    var out = new Float32Array(3 * ids.length);
    ids.forEach(function (i, j) { out[3 * j] = GPOS[3 * i]; out[3 * j + 1] = GPOS[3 * i + 1]; out[3 * j + 2] = GPOS[3 * i + 2]; });
    return out;
  }
  function boxOf(ids) {
    var lo = new THREE.Vector3(Infinity, Infinity, Infinity), hi = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
    ids.forEach(function (i) {
      lo.x = Math.min(lo.x, GPOS[3 * i]); lo.y = Math.min(lo.y, GPOS[3 * i + 1]); lo.z = Math.min(lo.z, GPOS[3 * i + 2]);
      hi.x = Math.max(hi.x, GPOS[3 * i]); hi.y = Math.max(hi.y, GPOS[3 * i + 1]); hi.z = Math.max(hi.z, GPOS[3 * i + 2]);
    });
    return { lo: lo, hi: hi };
  }
  /* the whole scene: the network's documents (every k-th, at most 12,000), every trace node and the corners of the top
     layer and of the questions' plane (the layer names stand at the corners) */
  var FIT = null;
  function scenePoints() {
    if (FIT) return FIT;
    var step = Math.max(1, Math.ceil(D.N / 12000)), nd = Math.ceil(D.N / step), out = new Float32Array(3 * (nd + NG + 8)), o = 0, i;
    for (i = 0; i < D.N; i += step) { out[o++] = D.pos[3 * i]; out[o++] = D.pos[3 * i + 1]; out[o++] = D.pos[3 * i + 2]; }
    for (i = 0; i < NG; i++) { out[o++] = GPOS[3 * i]; out[o++] = GPOS[3 * i + 1]; out[o++] = GPOS[3 * i + 2]; }
    var E = D.extent * 1.06, ys = [NS.layerY(D, 0), G.planes.z_question * NS.ZS];
    ys.forEach(function (y) { [[-E, -E], [E, -E], [E, E], [-E, E]].forEach(function (c) { out[o++] = c[0]; out[o++] = y; out[o++] = c[1]; }); });
    FIT = out.subarray(0, o);
    return FIT;
  }
  function sceneBox() {
    var E = D.extent * 1.06, lo = Infinity;
    for (var i = 0; i < NG; i++) lo = Math.min(lo, GPOS[3 * i + 1]);
    return { lo: new THREE.Vector3(-E, Math.min(lo, G.planes.z_question * NS.ZS), -E), hi: new THREE.Vector3(E, NS.layerY(D, 0), E) };
  }
  /* the whole scene, framed on load and by Reset view only */
  function homeView() {
    var b = sceneBox(), rect = homeRect();
    return fitPoints(fitBox(b.lo, b.hi, DIR, 0.03, rect), 0.03, rect, scenePoints());
  }
  function fitAll(ms) {
    var f = homeView();
    moveCamera(f.pos, f.target, ms);
    if (ms) T.flights++;
  }
  /* Zoom to selection: every chosen trace's foreground nodes in the part of the canvas the panels leave free */
  function chosenFg() {
    var has = new Uint8Array(NG), ids = [];
    state.sel.forEach(function (t) { t.f.forEach(function (i) { if (!has[i]) { has[i] = 1; ids.push(i); } }); });
    return ids;
  }
  function fitChosen(ms) {
    var ids = chosenFg(), b = boxOf(ids), pad = 20, rect = freeRect(), m = mobile ? 0.16 : 0.12;
    b.lo.addScalar(-pad); b.hi.addScalar(pad);
    b.hi.y += 40;                                   // headroom above the law for its call-out
    var f = fitPoints(fitBox(b.lo, b.hi, DIR, m, rect), m, rect, pointsOf(ids));
    moveCamera(f.pos, f.target, ms);
    T.flights++;
  }
  function moveCamera(pos, target, ms) {
    T.cameraMoves++;
    if (!ms) {
      tween = null;
      camera.position.copy(pos); controls.target.copy(target); camera.lookAt(target); controls.update();
      needsRender = true; updateLabelSizes(); scheduleCallouts(); return;
    }
    tween = { t0: null, ms: ms, p0: camera.position.clone(), p1: pos, q0: controls.target.clone(), q1: target };
    M.flying = true;
  }
  function stepTween(t) {
    if (tween.t0 == null) tween.t0 = t;
    var u = Math.min(1, (t - tween.t0) / tween.ms), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.q0, tween.q1, e);
    if (u >= 1) { tween = null; M.flying = false; T.cameraSettled = (T.cameraSettled || 0) + 1; if (state.sel.length) drawFgNodes(); updateLabelSizes(); scheduleCallouts(); }
  }
  function orbit(dAz, dPol, zoom) {
    var off = camera.position.clone().sub(controls.target), sph = new THREE.Spherical().setFromVector3(off);
    sph.theta += dAz;
    sph.phi = Math.min(Math.PI - 0.05, Math.max(0.05, sph.phi + dPol));
    sph.radius *= zoom || 1;
    off.setFromSpherical(sph);
    camera.position.copy(controls.target).add(off);
    camera.lookAt(controls.target);
    controls.update();
    needsRender = true;
    scheduleCallouts();
  }

  /* ------------------------------------------------------------------ call-outs (js/paper3d.js VL.Callouts) */
  function worldPerPx() { return VL.spriteWpp(camera, host.clientHeight); }
  /* call-out text: Vietnamese · English, long names shortened (the full name is in the panel and the tooltip) */
  var LBL = mobile ? { vi: 34, en: 38, one: 24, px: 18, pxSel: 19, qvi: 36, qen: 40, layer: 18 } : { vi: 48, en: 52, one: 30, px: 22, pxSel: 23, qvi: 46, qen: 50, layer: 21 };
  /* which call-outs of the shown trace must be shown (the question always); on phones the law when it fits (the hop
     sheet's title names it), on wide screens the law too */
  var MUST = mobile ? { provision: true, law: false } : { provision: true, law: true };
  function nodeR(i) { return (IS_WORK[i] && netObj ? Math.max(SIZE.work, netObj.geometry.attributes.aSize.array[WDOC[i]]) : (SIZE[cname(i)] || 9)) / 2; }
  function makeLabel(lines, o) {
    var opt = VL.paperCallout(P, !!o.sel);
    opt.lines = lines;
    opt.px = o.px || LBL.px;
    opt.weight = '400';
    var s = VL.TextSprite(lines[0].map(function (p) { return p.text; }).join(''), opt);
    s.__id = o.id; s.__pri = o.pri || 0; s.__must = !!o.must; s.__sel = !!o.sel; s.__layer = !!o.layer;
    s.__node = o.node != null ? o.node : -1;
    s.__r = s.__node >= 0 ? nodeR(s.__node) : 0;
    s.layers.set(1);                  // hidden until VL.Callouts places it
    if (o.at) s.position.set(o.at[0], o.at[1], o.at[2]);
    else s.position.set(GPOS[3 * o.node], GPOS[3 * o.node + 1], GPOS[3 * o.node + 2]);
    s.fit(worldPerPx());
    labelGroup.add(s);
    labels.push(s);
    return s;
  }
  function clearLabels() {
    labels.forEach(function (s) { labelGroup.remove(s); s.dispose(); });
    labels = [];
  }
  function updateLabelSizes() { if (!camera) return; var w = worldPerPx(); labels.forEach(function (s) { s.fit(w); }); }
  /* call-out lines in the language mode (js/paper3d.js VL.paperLines): EN–VI "Tiếng Việt · English" (on one line when
     short), EN or VI one line */
  function bi(i, prefix) {
    var n = names(i), vi = VL.short(prefix ? prefix[0] + n[0] : n[0], LBL.vi), en = n[1] ? VL.short(prefix ? prefix[1] + n[1] : n[1], LBL.en) : '';
    return VL.paperLines(vi, en, P, { oneLine: LBL.one });
  }
  /* the question: EN–VI its Vietnamese title over the English gloss (as in v1), EN the gloss, VI the title */
  function questionLines(t) {
    var q = t.q;
    if (!q) return bi(t.co[0]);
    return VL.paperLines(VL.short(q.vi, LBL.qvi), VL.short(q.en || '', LBL.qen), P, { twoLines: true });
  }
  function areaLines(i) { var p = VL.kpair('tr3d.area'); return bi(i, [p.vi, p.en]); }
  /* "Bậc 0 · Hiến pháp" over "Rank 0 · Constitution" (EN–VI), or one line in EN or VI, as on network-3d.html */
  function rankLabel(r) {
    var rk = (D.net.ranks || [])[r] || {}, k = 'net.rank.' + r;
    var name = VL.i18n.has(k) ? VL.kpair(k) : VL.pair(rk.vi || rk.en || '', rk.en || '');
    return VL.paperTL('net.rank.label', { r: r, name: name }, P, { twoLines: true });
  }
  function planeLines(k) { return VL.paperTL(k, null, P, { twoLines: true }); }
  /* the call-outs: the layer names at their corners (always); the shown trace's question, provision, law (must; on
     phones the law where it fits), term and area, the other chosen questions where they fit; with nothing chosen the
     27 areas' names */
  function buildLabels() {
    if (!labelGroup || !D) return;
    clearLabels();
    var E = D.extent * 1.06, ids = {};
    for (var r = 0; r <= 5; r++) makeLabel(rankLabel(r), { id: 'rank-' + r, layer: true, at: [-E, NS.layerY(D, r), -E], pri: 10 - r, px: LBL.layer });
    makeLabel(planeLines('tr3d.plane.answers'), { id: 'plane-answers', layer: true, at: [-E, G.planes.z_answer * NS.ZS, -E], pri: 4, px: LBL.layer });
    makeLabel(planeLines('tr3d.plane.questions'), { id: 'plane-questions', layer: true, at: [-E, G.planes.z_question * NS.ZS, -E], pri: 3, px: LBL.layer });
    function add(lines, o) { if (ids[o.id]) return; ids[o.id] = 1; makeLabel(lines, o); }
    var cur = current();
    if (cur) {
      var co = cur.co;
      add(questionLines(cur), { id: G.i[co[0]], node: co[0], sel: true, must: true, pri: 1000, px: LBL.pxSel });
      add(bi(co[2]), { id: G.i[co[2]], node: co[2], must: MUST.provision, pri: 900 });
      if (co[3] !== co[2]) add(bi(co[3]), { id: G.i[co[3]], node: co[3], must: MUST.law, pri: 880 });
      add(areaLines(co[5]), { id: G.i[co[5]], node: co[5], pri: 840 });
      if (co[4] >= 0) add(bi(co[4]), { id: G.i[co[4]], node: co[4], pri: 820 });
      state.sel.forEach(function (t, k) { if (t !== cur) add(questionLines(t), { id: G.i[t.co[0]], node: t.co[0], pri: 600 - k }); });
    } else {
      G.areas.forEach(function (a) { add(areaLines(a.n), { id: G.i[a.n], node: a.n, pri: 300, px: LBL.px - 1 }); });
    }
    T.labels = labels.length;
    M.labelsLang = VL.lang();
    scheduleCallouts();
  }
  /* a layer's name stands left of its plane's back-left corner (the planes' left ends are empty; the legend is lower) */
  function layerOffset(w) { return [-w / 2 - 4, 0]; }
  function calloutItems() {
    return labels.map(function (s) { return { id: s.__id, sprite: s, pri: s.__pri, must: s.__must, sel: s.__sel, r: s.__r, fixed: s.__layer ? layerOffset : null }; });
  }
  /* ink the call-outs keep clear of: the chosen traces (their foreground nodes and traced segments), else the labelled
     area nodes; the light rest of the scene is background, as in the paper */
  function calloutInk() {
    var discs = [];
    function disc(i) { discs.push({ id: G.i[i], x: GPOS[3 * i], y: GPOS[3 * i + 1], z: GPOS[3 * i + 2], r: nodeR(i) }); }
    if (state.sel.length) { chosenFg().forEach(disc); return { discs: discs, paths: selPaths }; }
    labels.forEach(function (s) { if (s.__node >= 0) disc(s.__node); });
    return { discs: discs, paths: [] };
  }
  function obstacles() {
    var hr = host.getBoundingClientRect(), out = [];
    ['#legend', '#hint', '.stage-tools', '#status', '#panel'].forEach(function (q) {
      var e = VL.$(q, stage);
      if (!e || e.classList.contains('hidden') || e.hidden || e.offsetParent === null) return;
      var r = e.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      out.push({ x0: r.left - hr.left - 4, x1: r.right - hr.left + 4, y0: r.top - hr.top - 4, y1: r.bottom - hr.top + 4 });
    });
    if (mobile && app.classList.contains('side-open')) {     // phones: the list sheet lies over the stage
      var sd = document.getElementById('side'), sr = sd ? sd.getBoundingClientRect() : { width: 0, height: 0 };
      if (sr.width > 1 && sr.height > 1) out.push({ x0: sr.left - hr.left - 4, x1: sr.right - hr.left + 4, y0: sr.top - hr.top - 4, y1: sr.bottom - hr.top + 4 });
    }
    return out;
  }
  var lastPlacement = '';
  function scheduleCallouts() {
    if (!camera || !labels.length) { if (camera) M.callouts = { runs: (M.callouts && M.callouts.runs) || 0, placed: [], nodes: [], shown: 0, mustHidden: 0 }; return; }
    if (!callouts) {
      callouts = VL.Callouts({
        camera: function () { return camera; },
        size: function () { return { w: host.clientWidth, h: host.clientHeight }; },
        items: calloutItems, ink: calloutInk, ui: obstacles,
        leaderColor: function () { return P.leader; },
        discMaxPx: 30 / Math.min(window.devicePixelRatio || 1, 2), segCap: 16000,
        segPad: Math.ceil(VL.TRACE_W.halo2 * BOLD / 2),   // half the bold outer halo
        metrics: M, key: 'callouts',
        onDone: function (st) {
          T.calloutsShown = st.shown;
          /* a frame only when the call-outs changed (a frame of the full network is slow on a software renderer) */
          var sig = labels.length + '#' + st.placed.map(function (q) { return q.id + ':' + q.box.join(','); }).join('|');
          if (sig !== lastPlacement) { lastPlacement = sig; needsRender = true; M.calloutFrames = (M.calloutFrames || 0) + 1; }
        }
      });
    }
    callouts.schedule();
  }

  /* ------------------------------------------------------------------ the one list: 540 questions under 27 area headings */
  /* the law of a list entry in one language (EN and EN–VI English, as in v1; VI Vietnamese), with its number */
  function lawShort(law) {
    var name = VL.U(VL.pair(law.vi || '', law.en || ''));
    return name.indexOf(law.number) >= 0 || !law.number ? name : name + ' · ' + law.number;
  }
  function verdictBadge(q) {
    return q.verified ? '<span class="tr-badge ok">✓ ' + VL.TH('tr3d.badge.verified') + ' ' + f2(q.match) + '</span>'
      : '<span class="tr-badge st">' + VL.TH('tr3d.badge.structural') + ' ' + f2(q.match) + '</span>';
  }
  /* a question: EN–VI the Vietnamese title (q class) over its English gloss (g class), EN the gloss alone, VI the title
     alone; tag = span or p */
  function qHtml(qa, tag, cq, cg) {
    var mode = VL.lang(), o = '<' + tag + ' class="', c = '</' + tag + '>';
    if (mode === 'en') return o + cq + '"' + (qa.en ? '' : ' lang="vi"') + '>' + esc(qa.en || qa.vi) + c;
    if (mode === 'vi') return o + cq + '" lang="vi">' + esc(qa.vi) + c;
    return o + cq + '" lang="vi">' + esc(qa.vi) + c + (qa.en ? o + cg + '">' + esc(qa.en) + c : '');
  }
  /* an area heading: EN–VI "Tiếng Việt · English" (v1's tab label), EN or VI one name; then the number of its
     questions the search shows and the button that chooses all of them */
  function headName(a) {
    return VL.lang() === 'envi' ? '<span lang="vi">' + esc(a.label_vi) + '</span><span class="sep" aria-hidden="true"> · </span><span>' + esc(a.label_en) + '</span>'
      : VL.UH(areaPair(a));
  }
  function headCount(n) {
    return '<span class="n" aria-hidden="true">' + fmt(n) + '</span><span class="sr-only">' + esc(VL.U('tr3d.groupCount', { n: nv(n) })) + '</span>';
  }
  function headHtml(a, ai) {
    var n = GROUPS[ai].length;
    return '<h3 class="tr-head" id="tr-h-' + a.id + '" tabindex="-1"><span class="tr-head-sw" data-a="' + ai + '" aria-hidden="true"' +
      (AREA_RANK ? ' style="background:' + areaHex(ai) + '"' : '') + '></span><span class="tr-head-name">' + headName(a) + '</span><span class="tr-head-n"></span>' +
      '<button type="button" class="tr-all" data-area="' + a.id + '" aria-pressed="false" aria-label="' + esc(VL.U('tr3d.all.aria', { n: fmt(n), area: VL.U(areaPair(a)) })) + '"' +
      tipAttr('tr3d.all.aria', { n: fmt(n), area: VL.U(areaPair(a)) }) + '>' + VL.UH('tr3d.all', { n: fmt(n) }) + '</button></h3>';
  }
  /* the area's colour before its heading (hidden while colouring by kind: .tr-color-kind) */
  function paintHeads() {
    if (!AREA_RANK) return;
    VL.$$('.tr-head-sw').forEach(function (e) { e.style.background = areaHex(+e.getAttribute('data-a')); });
  }
  function itemId(q) { return 'tr-item-' + q.id + '-' + q.rank; }
  /* a question: the row (a click chooses it alone; Space or Ctrl/Cmd-click adds or removes it) and its round button
     (adds or removes it; out of the tab order, the row's Space does the same) */
  function itemHtml(q) {
    return '<li><button type="button" class="tr-item" id="' + itemId(q) + '" data-area="' + q.id + '" data-rank="' + q.rank + '">' +
      '<span class="tr-rank">' + q.rank + '</span><span class="tr-item-body"><span class="tr-law">' + esc(lawShort(q.law)) + '</span>' +
      qHtml(q, 'span', 'tr-q', 'tr-g') + verdictBadge(q) + '</span></button>' +
      '<button type="button" class="tr-pick" tabindex="-1" data-area="' + q.id + '" data-rank="' + q.rank + '" aria-pressed="false" aria-label="' +
      esc(VL.U('tr3d.pick', { n: q.rank })) + '"' + tipAttr('tr3d.pick', { n: q.rank }) + '><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.2 8.3l2.5 2.5 5.1-5.3"/></svg></button></li>';
  }
  var SEC = [], HEADN = [], HEADB = [], listReady = null;
  function renderList() {
    if (!QS.length) return;
    var t0 = performance.now();
    listEl.innerHTML = AREAS.map(function (a, ai) {
      return '<section class="tr-group" id="tr-g-' + a.id + '" data-area="' + a.id + '" aria-labelledby="tr-h-' + a.id + '">' + headHtml(a, ai) +
        '<ol class="tr-sub">' + GROUPS[ai].map(itemHtml).join('') + '</ol></section>';
    }).join('') + '<p class="tr-status" id="tr-none" hidden></p>';
    QS.forEach(function (q) {
      q.btn = document.getElementById(itemId(q));
      q.li = q.btn ? q.btn.parentNode : null;
      q.pick = q.li ? q.li.querySelector('.tr-pick') : null;
    });
    AREAS.forEach(function (a, ai) {
      SEC[ai] = document.getElementById('tr-g-' + a.id);
      HEADN[ai] = SEC[ai].querySelector('.tr-head-n');
      HEADB[ai] = SEC[ai].querySelector('.tr-all');
    });
    marked = [];
    T.groups = AREAS.length;
    applySearch();
    markList(false);
    T.listMs = Math.round(performance.now() - t0);
    T.renders++;
  }
  /* the search: every word of the query (folded: no case, no diacritics) in the question's title or gloss, its law's
     names or number, or its area's names; empty areas hide their heading; the live line says how many are shown */
  function applySearch() {
    if (!QS.length) return;
    var raw = searchEl ? searchEl.value : '', toks = words(raw), shown = 0;
    GROUPS.forEach(function (gq, ai) {
      var k = 0;
      gq.forEach(function (q) {
        var ok = !toks.length || toks.every(function (w) { return hasWord(q.hay, w); });
        if (q.li) q.li.hidden = !ok;
        if (ok) k++;
      });
      if (SEC[ai]) { SEC[ai].hidden = k === 0; HEADN[ai].innerHTML = headCount(k); }
      shown += k;
    });
    state.query = raw;
    T.query = raw;
    T.shown = shown;
    updateCount();
    var none = document.getElementById('tr-none');
    if (none) { none.hidden = shown > 0; none.textContent = shown ? '' : VL.U('tr3d.noMatch', { q: raw.trim() }); }
  }
  /* the live line: "540 of 540 questions · 3 chosen"; Clear is shown while something is chosen */
  function updateCount() {
    var n = state.sel.length;
    countEl.textContent = VL.U('tr3d.count', { n: fmt(T.shown), total: fmt(QS.length) }) + (n ? ' · ' + VL.U('tr3d.chosen', { n: nv(n) }) : '');
    if (clearEl) clearEl.hidden = !n;
    T.countText = countEl.textContent;
  }
  /* the chosen rows (their round buttons pressed), the shown one (aria-current), the headings whose 20 are all chosen */
  var marked = [];
  function markList(scroll) {
    marked.forEach(function (q) {
      if (q.li) q.li.classList.remove('is-chosen');
      if (q.pick) q.pick.setAttribute('aria-pressed', 'false');
      if (q.btn) q.btn.removeAttribute('aria-current');
    });
    marked = [];
    var per = {};
    state.sel.forEach(function (t) {
      per[t.a] = (per[t.a] || 0) + 1;
      var q = t.q;
      if (!q || !q.li) return;
      q.li.classList.add('is-chosen');
      q.pick.setAttribute('aria-pressed', 'true');
      marked.push(q);
    });
    var cur = current(), cq = cur && cur.q;
    if (cq && cq.btn) {
      cq.btn.setAttribute('aria-current', 'true');
      if (scroll && !cq.li.hidden) { try { cq.btn.scrollIntoView({ block: 'nearest' }); } catch (e) { /* old engines */ } }
    }
    HEADB.forEach(function (b, ai) { if (b) b.setAttribute('aria-pressed', GROUPS[ai].length && per[ai] === GROUPS[ai].length ? 'true' : 'false'); });
    updateCount();
  }
  /* an area's heading at the top of the list (v1's area links #area=<id>; on phones the list sheet opens); a search that
     hides the area is cleared first. Chooses nothing */
  function scrollToArea(id, opts) {
    var a = BY[id];
    if (!a) return Promise.resolve(null);
    opts = opts || {};
    return (listReady || Promise.resolve()).then(function () {
      var ai = AIX[a.id];
      if (SEC[ai] && SEC[ai].hidden && searchEl && searchEl.value) { searchEl.value = ''; applySearch(); }
      if (mobile && opts.open) setSide(true);
      var head = document.getElementById('tr-h-' + a.id);
      if (head) { try { head.scrollIntoView({ block: 'start' }); } catch (e) { /* old engines */ } }
      T.scrolledTo = a.id;
      return a;
    });
  }
  function visibleItems() { var out = []; QS.forEach(function (q) { if (q.btn && !q.li.hidden) out.push(q.btn); }); return out; }
  function isRow(el) { return !!(el && el.classList && el.classList.contains('tr-item')); }
  listEl.addEventListener('click', function (e) {
    var all = e.target.closest('.tr-all');
    if (all) { chooseArea(all.getAttribute('data-area'), { user: true }); if (mobile) setSide(false); return; }
    var pk = e.target.closest('.tr-pick');
    if (pk) { toggleTrace(pk.getAttribute('data-area'), +pk.getAttribute('data-rank'), { user: true, scroll: false }); return; }
    var b = e.target.closest('.tr-item');
    if (!b) return;
    if (e.ctrlKey || e.metaKey) { toggleTrace(b.getAttribute('data-area'), +b.getAttribute('data-rank'), { user: true, scroll: false }); return; }
    chooseOnly(b.getAttribute('data-area'), +b.getAttribute('data-rank'), { user: true, scroll: false });
    if (mobile) setSide(false);
  });
  /* Space on a row adds or removes its question (the button's own Space click is cancelled, so it does not also choose
     it alone); arrows move through the shown questions (across the headings), Home / End to the first / last, up from
     the first back to the search; Enter chooses */
  listEl.addEventListener('keydown', function (e) {
    var k = e.key;
    if ((k === ' ' || k === 'Spacebar') && isRow(e.target)) {
      e.preventDefault();
      if (!e.repeat) toggleTrace(e.target.getAttribute('data-area'), +e.target.getAttribute('data-rank'), { user: true, scroll: false });
      return;
    }
    if (k !== 'ArrowDown' && k !== 'ArrowUp' && k !== 'Home' && k !== 'End') return;
    var items = visibleItems(), i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    if (k === 'ArrowUp' && i === 0 && searchEl) { searchEl.focus(); return; }
    items[k === 'Home' ? 0 : k === 'End' ? items.length - 1 : Math.max(0, Math.min(items.length - 1, i + (k === 'ArrowDown' ? 1 : -1)))].focus();
  });
  listEl.addEventListener('keyup', function (e) { if ((e.key === ' ' || e.key === 'Spacebar') && isRow(e.target)) e.preventDefault(); });
  var searchRaf = 0;
  if (searchEl) {
    searchEl.addEventListener('input', function () {
      if (searchRaf) return;
      searchRaf = requestAnimationFrame(function () { searchRaf = 0; applySearch(); });
    });
    searchEl.addEventListener('keydown', function (e) {
      if ((e.key === 'ArrowDown' || e.key === 'Enter') && !e.isComposing) {
        if (searchRaf) { cancelAnimationFrame(searchRaf); searchRaf = 0; applySearch(); }
        var first = visibleItems()[0];
        if (first) { e.preventDefault(); first.focus(); }
      } else if (e.key === 'Escape' && searchEl.value) {
        e.preventDefault();
        e.stopPropagation();
        searchEl.value = '';
        applySearch();
      }
    });
  }
  if (clearEl) clearEl.addEventListener('click', function () { clearSelection(true); closePanel(); if (searchEl && !mobile) searchEl.focus(); });

  /* ------------------------------------------------------------------ the Fig. 5 hop panel */
  var REASON = { law_not_resolved: 'tr3d.reason.law', number_not_in_scope: 'tr3d.reason.number', article_not_parsed: 'tr3d.reason.article' };
  function primary(tr) { for (var i = 0; i < tr.paths.length; i++) if (tr.paths[i].pr) return tr.paths[i]; return tr.paths[0]; }
  function lawTitle(law) {
    var n = law.number || '', named = (law.vi || '').indexOf(n) >= 0 || (law.en || '').indexOf(n) >= 0;
    return VL.TH(VL.pair(law.vi || '', law.en || '')) + (n && !named ? ' · <span class="num">' + esc(n) + '</span>' : '');
  }
  function pathLabel(tr, p) {
    var N_ = tr.nodes, prov = N_[p.n.length > 3 ? p.n[2] : p.n[p.n.length - 1]], work = N_[p.n[p.n.length - 1]];
    if (p.u === 'work') return VL.TH(VL.pair(work.vi, work.en)) + ' ' + VL.UH('tr3d.citedWhole');
    return VL.TH(VL.pair(prov.vi, prov.en)) + ' ' + VL.UH('tr3d.of') + ' ' + VL.UH(VL.pair(work.vi, work.en));
  }
  /* a hop of the Fig. 5 panel: EN–VI "1 Question Câu hỏi · extra" as in v1, EN or VI "1 Question  extra" in one language */
  function hop(cls, n, k, extra, body) {
    var e = VL.kpair(k), head;
    if (VL.lang() === 'envi') head = '<b>' + n + ' ' + esc(e.en) + '</b> <span lang="vi">' + esc(e.vi) + '</span>' + (extra ? ' · ' + extra : '');
    else head = '<b>' + n + ' ' + VL.UH(k) + '</b>' + (extra ? ' <span>' + extra + '</span>' : '');
    return '<section class="hop hop-' + cls + '"><h3>' + head + '</h3>' + body + '</section>';
  }
  /* a sentence pair (notes, the hop arrows) in EN–VI as v1 wrote it: the English, then the Vietnamese (lang="vi");
     EN or VI: one language */
  function enFirst(k, vars, sep) {
    var t = VL.TL(k, vars);
    if (VL.lang() !== 'envi' || !t.secondary) return VL.UH(k, vars);
    return esc(t.secondary) + (sep == null ? ' ' : sep) + '<span lang="vi">' + esc(t.primary) + '</span>';
  }
  /* where the law's English name comes from (build-time phrases): the phrase in English as in v1, translated in VI */
  var EN_SRC = { 'vbpl English record title (normalised)': 'tr3d.enSrc.vbpl', 'document type + number': 'tr3d.enSrc.typeNumber',
    'machine-assisted translation of the Vietnamese title': 'tr3d.enSrc.machine' };
  function enSource(s) { return !s ? VL.U('tr3d.machineAssisted') : (EN_SRC[s] ? VL.U(EN_SRC[s]) : s); }
  function hopsHtml(tr) {
    var p = primary(tr), N_ = tr.nodes, k3 = p.n.length > 3 ? p.n[2] : null, work = N_[p.n[p.n.length - 1]], mode = VL.lang();
    var rec = null, provs = [], whole = [], struct = [];
    N_.forEach(function (n) { if (TD && TD.CLASSES[n.c] === 'record') rec = n; });
    tr.paths.forEach(function (q) { if (q.u === 'work') whole.push(q); else if (q.v) provs.push(q); else struct.push(q); });
    var ans = N_[p.n[1]];
    var b1 = hop('q', '1', 'tr3d.hop.question', 'hdpl #' + esc(tr.qa.id),
      qHtml(tr.qa, 'p', 'strong', 'en') +
      '<p class="pv">q:' + esc(tr.qa.id) + ' · src hdpl · ' + esc(tr.qa.date) + (tr.qa.url ? ' · ' + ext(tr.qa.url, 'thuvienphapluat.vn') : '') + '</p>');
    var items = provs.map(function (q) { return '<li>✓ ' + pathLabel(tr, q) + ' ' + VL.UH('tr3d.textMatch', { m: f2(q.m) }) + '</li>'; })
      .concat(struct.map(function (q) { return '<li>○ ' + pathLabel(tr, q) + ' ' + VL.UH('tr3d.matchKept', { m: f2(q.m) }) + '</li>'; }))
      .concat(whole.map(function (q) { return '<li>○ ' + pathLabel(tr, q) + '</li>'; }))
      .concat(tr.unresolved.map(function (u) {
        var what = u.num ? esc(u.num) : ((u.art ? 'Điều ' + esc(u.art) + ' ' : '') + esc(u.t || ''));
        return '<li>○ <span lang="vi">' + what + '</span> — ' + (REASON[u.r] ? VL.UH(REASON[u.r]) : esc(u.r)) + ' ' + VL.UH('tr3d.listed') + '</li>';
      }));
    var methods = [];
    tr.paths.forEach(function (q) { if (q.me && methods.indexOf(q.me) < 0) methods.push(q.me); });
    var b2 = hop('a', '2', 'tr3d.hop.answer', VL.UH('tr3d.hop.sources', { n: nv(tr.paths.length) }),
      '<p>' + VL.TH('tr3d.checked') + ':</p><ul>' + items.join('') + '</ul>' +
      '<p class="pv">a:' + esc(tr.qa.id) + ' −cites→ ' + VL.UH('tr3d.targets', { n: fmt(tr.paths.length), m: methods.join(' / ') }) + ' · ' + esc((ans.p || [])[2] || '') + '</p>');
    var b3 = '';
    if (k3 != null) {
      var prov = N_[k3], chain = p.n.slice(2, -1).reverse().map(function (k) { return N_[k]; });
      var pathVi = chain.map(function (n) { return n.vi; }).join(' › '), pathEn = chain.map(function (n) { return n.en || n.vi; }).join(' › '), pv = prov.p || [];
      b3 = hop('p', '3', 'tr3d.hop.provision', mode === 'en' ? esc(pathEn) : '<span lang="vi">' + esc(pathVi) + '</span>',
        '<p>' + VL.UH('tr3d.reachedFrom2', null, { html: { rel: '<i>' + VL.UH('tr3d.rel.cites') + '</i>' } }) + '</p><p class="strong">' + VL.TH(VL.pair(prov.vi, prov.en)) + '</p>' +
        '<p>' + VL.UH(p.v ? 'tr3d.wordForWord' : 'tr3d.notWords', { m: f2(p.m) }) + '</p>' +
        '<p>' + VL.UH('tr3d.provText', null, { html: { link: tr.law.url ? ext(tr.law.url, VL.UH('tr3d.readAtSource'), VL.U('tr3d.srTvpl')) : VL.UH('tr3d.atSource') } }) + '</p>' +
        '<p class="pv">vbpl:' + esc(pv[1] || tr.law.doc_id) + ' › <span lang="vi">' + esc(pathVi) + '</span> · ' + esc(pv[2] || '') + (pv[3] ? ' · ' + esc(pv[3]) : '') + '</p>');
    } else {
      b3 = hop('p', '3', 'tr3d.hop.provision', '', '<p>' + enFirst('tr3d.wholeAnswer') + '</p>');
    }
    var wp = work.p || [];
    var b4 = hop('l', '4', 'tr3d.hop.law', esc(tr.law.number),
      '<p>' + VL.UH('tr3d.reachedFrom3', null, { html: { a: '<i>' + VL.UH('tr3d.rel.contains') + '</i>', b: '<i>' + VL.UH('tr3d.rel.realizes') + '</i>' } }) + '</p>' +
      '<p class="strong">' + VL.TH(VL.pair(tr.law.vi, tr.law.en)) + '</p>' +
      '<p>' + VL.UH('tr3d.sourceStatus') + ' ' + VL.TH(VL.pair(tr.law.status_vi, tr.law.status_en)) + '</p>' +
      '<p>' + VL.UH('tr3d.englishName', { v: enSource(tr.law.en_src) }) + '</p>' +
      (rec ? '<p>' + VL.UH('tr3d.vnRecord', null, { html: { link: rec.u ? ext(rec.u, 'vbpl:' + esc(tr.law.doc_id)) : 'vbpl:' + esc(tr.law.doc_id) } }) + '</p>' : '') +
      (tr.law.doc_id ? '<p>' + netLink(tr.law.doc_id) + '</p>' : '') +
      '<p class="pv">' + esc(work.i) + ' · ' + esc(wp[2] || '') + '</p>');
    var terms = tr.terms.map(function (t) {
      var n = N_[t.n], d = t.d != null ? N_[t.d] : null;
      return '<li><b>' + VL.TH(VL.pair(n.vi, n.en)) + '</b> — ' +
        (d ? VL.UH('tr3d.definedIn', { clause: VL.U(VL.pair(d.vi || '', d.en || '')), m: f2(t.m) }) : VL.UH('tr3d.noDefinition')) +
        (n.u ? ' · ' + ext(n.u, 'tnpl #' + esc((n.p || [])[1] || '')) : '') +
        '<div class="pv">' + esc(n.i) + (d ? ' ←defines− ' + esc(d.i) : '') + ' · ' + esc((n.p || [])[2] || '') + '</div></li>';
    });
    var b5 = hop('t', '5', 'tr3d.hop.terms', 'tnpl', terms.length ?
      '<ul>' + terms.join('') + '</ul><p class="en">' + VL.UH('tr3d.termPath') + '</p>' :
      '<p>' + enFirst('tr3d.noTerm') + '</p>');
    return '<div class="tr-hops" aria-label="' + esc(VL.U('tr3d.hops.aria')) + '">' + b1 +
      '<div class="hop-arrow">↓ ' + enFirst('tr3d.answeredBy', null, ' · ') + '</div>' + b2 + b3 + b4 +
      '<div class="hop-arrow">↓ ' + enFirst('tr3d.definesTerms', null, ' · ') + '</div>' + b5 + '</div>';
  }
  function closeHtml() { return '<button type="button" class="btn panel-close" data-close aria-label="' + esc(VL.U('tr3d.close')) + '"' + tipAttr('tr3d.close') + '>×</button>'; }
  /* the stepper through the chosen traces: "3 of 20" between previous and next (the list's order) */
  function stepHtml() {
    var n = state.sel.length, i = state.cur;
    if (n < 2 || i < 0) return '';
    return '<div class="tr-step" role="group" aria-label="' + esc(VL.U('tr3d.step.aria')) + '">' +
      '<button type="button" class="btn btn-xs" data-step="-1"' + (i <= 0 ? ' disabled' : '') + ' aria-label="' + esc(VL.U('tr3d.step.prev')) + '"' + tipAttr('tr3d.step.prev') + '>‹</button>' +
      '<span class="tr-step-n">' + esc(VL.U('tr3d.step.n', { i: fmt(i + 1), n: fmt(n) })) + '</span>' +
      '<button type="button" class="btn btn-xs" data-step="1"' + (i >= n - 1 ? ' disabled' : '') + ' aria-label="' + esc(VL.U('tr3d.step.next')) + '"' + tipAttr('tr3d.step.next') + '>›</button></div>';
  }
  function netLink(id) { return '<a href="network-3d.html#doc=' + encodeURIComponent(String(id)) + '">' + VL.UH('tr3d.openNetwork') + '</a>'; }
  function tracePanelHtml(a, tr) {
    return closeHtml() + stepHtml() +
      '<p class="tf-area">#' + tr.rank + ' · ' + VL.TH(areaPair(a)) + '</p>' +
      '<h2 id="tp-title">' + lawTitle(tr.law) + '</h2>' +
      qHtml(tr.qa, 'p', 'tf-q', 'tf-g') +
      '<p class="tf-links">' + verdictBadge(tr) + ' · ' + VL.UH('tr3d.answersIn', { n: fmt(tr.article.n), area: VL.U(areaPair(a)), article: VL.U(VL.pair(tr.article.vi || '', tr.article.en || '')),
        na: fmt(tr.article.na) }) + ' · <a href="#q=' + a.id + ':' + tr.rank + '">' + VL.UH('tr3d.linkTrace') + '</a></p>' + hopsHtml(tr);
  }
  /* the panel shows the shown trace (panelNode -1), a trace node's details (its index) or a network document's
     (NG + its point) */
  var panelNode = -1;
  function openPanel(html, keepScroll) {
    var st = panel.scrollTop;
    panel.innerHTML = html;
    panel.classList.remove('hidden');
    stage.classList.add('panel-open');
    panel.scrollTop = keepScroll ? st : 0;
    T.hops = VL.$$('.hop', panel).length;
    T.step = VL.$('.tr-step-n', panel) ? VL.$('.tr-step-n', panel).textContent : null;
    requestAnimationFrame(function () { onResize(); });
  }
  function closePanel() {
    if (panel.classList.contains('hidden')) return;
    panel.classList.add('hidden');
    stage.classList.remove('panel-open');
    T.hops = 0;
    T.step = null;
    panelNode = -1;
    requestAnimationFrame(function () { onResize(); });
  }
  panel.addEventListener('click', function (e) {
    if (e.target.closest('[data-close]')) { clearSelection(true); closePanel(); return; }
    var st = e.target.closest('[data-step]');
    if (st && !st.disabled) { step(+st.getAttribute('data-step'), { user: true }); return; }
    var b = e.target.closest('[data-trace]');
    if (b) { var x = b.getAttribute('data-trace').split(':'); chooseOnly(x[0], +x[1], { user: true }); }
  });

  /* ------------------------------------------------------------------ node details (hover, click) */
  /* the node's name: EN–VI the Vietnamese name over the English one (v1), EN or VI one language */
  function nameHtml(n) {
    if (VL.lang() === 'envi') return '<h2 lang="vi">' + esc(n[0]) + '</h2><p class="vi">' + esc(n[1]) + '</p>';
    return '<h2>' + VL.UH(VL.pair(n[0], n[1])) + '</h2>';
  }
  function areasOf(i) {
    var seen = {}, out = [];
    tracesOf(i).forEach(function (k) { var a = G.t[k].a; if (!seen[a]) { seen[a] = 1; out.push(AREAS[a]); } });
    return out;
  }
  function nodeHtml(i) {
    var n = names(i), c = cname(i), cn = classNames(c), ts = tracesOf(i), ars = areasOf(i), url = G.u[String(i)], doc = IS_WORK[i] ? G.d[String(i)] : null;
    var rows = '<dt>' + VL.UH('tr3d.k.id') + '</dt><dd class="iri">' + esc(G.i[i]) + '</dd>' +
      (ars.length ? '<dt>' + VL.UH('tr3d.k.areas') + '</dt><dd>' + ars.slice(0, 6).map(function (a) { return VL.TH(areaPair(a)); }).join('; ') + (ars.length > 6 ? ' …' : '') + '</dd>' : '') +
      (doc != null ? '<dt>' + VL.UH('tr3d.k.network') + '</dt><dd>' + netLink(doc) + '</dd>' : '') +
      (url ? '<dt>' + VL.UH('tr3d.k.source') + '</dt><dd>' + ext(url, VL.UH('tr3d.openSource'), VL.U('tr3d.newTab')) + '</dd>' : '');
    var list = ts.slice(0, 14).map(function (k) {
      var t = G.t[k], ar = AREAS[t.a];
      return '<li><button type="button" class="linkish" data-trace="' + ar.id + ':' + t.r + '">' + VL.UH(areaPair(ar)) + ' #' + t.r + '</button></li>';
    }).join('');
    return closeHtml() +
      '<p class="panel-kind"><span class="badge">' + VL.TH(VL.pair(cn[0], cn[1])) + '</span></p>' +
      nameHtml(n) + '<dl class="kv">' + rows + '</dl>' +
      '<h3>' + VL.TH('tr3d.inTraces', { n: nv(ts.length) }) + '</h3>' +
      (ts.length ? '<ul class="plist">' + list + '</ul>' + (ts.length > 14 ? '<p class="side-note">' + VL.UH('tr3d.andMore', { n: fmt(ts.length - 14) }) + '</p>' : '') : '');
  }
  /* a document of the network no trace reaches: its title (Vietnamese), number, layer and year, and a link to it on
     network-3d.html */
  function docHtml(j) {
    var r = D.rank[j], rk = 'net.rank.' + r, y = D.year[j];
    return closeHtml() +
      '<p class="panel-kind"><span class="badge">' + VL.TH(VL.kpair('tr3d.cls.document')) + '</span></p>' +
      '<h2 lang="vi">' + esc(D.title[j] || D.num[j] || D.ids[j]) + '</h2>' +
      '<dl class="kv">' + (D.num[j] ? '<dt>' + VL.UH('tr3d.k.number') + '</dt><dd>' + esc(D.num[j]) + '</dd>' : '') +
      '<dt>' + VL.UH('tr3d.k.layer') + '</dt><dd>' + r + ' · ' + (VL.i18n.has(rk) ? VL.TH(VL.kpair(rk)) : '') + '</dd>' +
      (y > 0 ? '<dt>' + VL.UH('tr3d.k.year') + '</dt><dd>' + y + '</dd>' : '') +
      '<dt>' + VL.UH('tr3d.k.network') + '</dt><dd>' + netLink(D.ids[j]) + '</dd></dl>' +
      '<p class="side-note">' + VL.UH('tr3d.notTraced') + '</p>';
  }
  var raycaster = null, ndc = null;
  /* the node under the pointer: {g: trace node or -1, doc: network point or -1}; chosen (solid) nodes and larger ones
     win over light and small ones, the traced laws over other documents */
  function pick(cx, cy) {
    if (!netObj) return null;
    if (!raycaster) { raycaster = new THREE.Raycaster(); ndc = new THREE.Vector2(); }
    var r = renderer.domElement.getBoundingClientRect();
    ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    var dist = camera.position.distanceTo(controls.target);
    raycaster.params.Points.threshold = Math.max(2, dist * worldPerPx() * 6);
    raycaster.setFromCamera(ndc, camera);
    var best = null, bestScore = Infinity, ta = trObj.geometry.attributes, na = netObj.geometry.attributes;
    raycaster.intersectObject(trObj, false).forEach(function (h) {
      var j = h.index, score = h.distanceToRay / (1 + (ta.aAlpha.array[j] > 0.5 ? 1 : 0)) / (0.6 + ta.aSize.array[j] / 12) + h.distance * 1e-4;
      if (score < bestScore) { bestScore = score; best = { g: TNODE[j], doc: -1 }; }
    });
    raycaster.intersectObject(netObj, false).forEach(function (h) {
      var j = h.index, gi = DOCG[j];
      var score = h.distanceToRay / (1 + (na.aAlpha.array[j] > 0.5 ? 1 : 0) + (gi >= 0 ? 0.5 : 0)) / (0.6 + na.aSize.array[j] / 12) + h.distance * 1e-4;
      if (score < bestScore) { bestScore = score; best = { g: gi, doc: j }; }
    });
    return best;
  }
  function pickId(p) { return !p ? null : p.g >= 0 ? G.i[p.g] : 'doc:' + D.ids[p.doc]; }
  /* a click: a question or answer chooses its question (Ctrl/Cmd-click adds or removes it); another node opens its details */
  function clickPick(p, ev) {
    if (!p) return;
    if (p.g >= 0) {
      var c = cname(p.g);
      if (c === 'question' || c === 'answer') {
        var ts = tracesOf(p.g).map(function (k) { return G.t[k]; }).filter(function (t) { return t.co[0] === p.g || t.co[1] === p.g; });
        var t = ts.filter(function (x) { return x.co[0] === p.g; })[0] || ts[0];
        if (t) {
          if (ev && (ev.ctrlKey || ev.metaKey)) toggleTrace(AREAS[t.a].id, t.r, { user: true });
          else chooseOnly(AREAS[t.a].id, t.r, { user: true });
          return;
        }
      }
      T.clicked = G.i[p.g];
      openPanel(nodeHtml(p.g));
      panelNode = p.g;
      return;
    }
    T.clicked = 'doc:' + D.ids[p.doc];
    openPanel(docHtml(p.doc));
    panelNode = NG + p.doc;
  }
  function tipHtml(p) {
    if (p.g >= 0) {
      var n = names(p.g), cn = classNames(cname(p.g)), k = tracesOf(p.g).length, lim = QNODE[p.g] ? 140 : 60;
      return '<b>' + VL.TH(VL.pair(VL.short(n[0], lim), VL.short(n[1], lim))) + '</b>' +
        '<div class="t-sub">' + VL.TH(VL.pair(cn[0], cn[1])) + ' · ' + VL.UH('tr3d.tipTraces', { n: nv(k) }) + '</div>' + tipArea(NAREA ? NAREA[p.g] : -1);
    }
    var j = p.doc, rk = 'net.rank.' + D.rank[j];
    return '<b lang="vi">' + esc(VL.short((D.num[j] ? D.num[j] + ' · ' : '') + D.title[j], 90)) + '</b>' +
      '<div class="t-sub">' + VL.TH(VL.kpair('tr3d.cls.document')) + (VL.i18n.has(rk) ? ' · ' + VL.TH(VL.kpair(rk)) : '') + '</div>' + tipArea(docArea(j));
  }
  /* colouring by area, a point's tooltip names the area of its colour */
  function tipArea(a) {
    if (state.colorBy !== 'area' || a == null || a < 0 || !AREAS[a]) return '';
    return '<div class="t-sub t-area"><span class="t-sw" style="background:' + areaHex(a) + '" aria-hidden="true"></span>' + VL.TH(areaPair(AREAS[a])) + '</div>';
  }
  var down = null, hoverRaf = 0;
  function bindPointer() {
    var cv = renderer.domElement;
    cv.addEventListener('pointerdown', function (e) { down = { x: e.clientX, y: e.clientY }; });
    cv.addEventListener('pointerup', function (e) {
      if (!down) return;
      var moved = Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y);
      down = null;
      if (moved > 6) return;
      clickPick(pick(e.clientX, e.clientY), e);
    });
    cv.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch' || down) { tip.classList.add('hidden'); return; }
      if (hoverRaf) return;
      var x = e.clientX, y = e.clientY;
      hoverRaf = requestAnimationFrame(function () {
        hoverRaf = 0;
        var p = pick(x, y);
        cv.style.cursor = p ? 'pointer' : '';
        T.hover = pickId(p);
        if (!p) { tip.classList.add('hidden'); return; }
        tip.innerHTML = tipHtml(p);
        tip.classList.remove('hidden');
        var hr = stage.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
        var lx = Math.min(hr.width - tw - 8, x - hr.left + 14), ly = y - hr.top + 14;
        if (ly + th > hr.height - 8) ly = y - hr.top - th - 10;
        tip.style.left = Math.max(8, lx) + 'px';
        tip.style.top = Math.max(8, ly) + 'px';
      });
    });
    cv.addEventListener('pointerleave', function () { tip.classList.add('hidden'); });
  }

  /* ------------------------------------------------------------------ the choice */
  var seq = 0;
  function setHash(h) {
    if (location.hash === h) return;
    try { history.replaceState(history.state, '', h); } catch (e) { location.hash = h; }
  }
  function clearHash() {
    if (!location.hash) return;
    try { history.replaceState(history.state, '', location.pathname + location.search); } catch (e) { location.hash = ''; }
  }
  /* the deep link of the choice: one area's 20 -> #area=<id>&all=1 (&q=<rank> when another than its first is shown);
     else #q=<area>:<r>,<r>;<area>:<r> with the shown trace first */
  function hashFor() {
    var sel = state.sel, cur = current();
    if (!sel.length || !cur) return '';
    var a0 = sel[0].a, one = sel.every(function (t) { return t.a === a0; });
    if (one && sel.length > 1 && sel.length === (AREA_T[a0] || []).length) return '#area=' + AREAS[a0].id + '&all=1' + (cur !== sel[0] ? '&q=' + cur.r : '');
    var order = [], by = {};
    [cur].concat(sel.filter(function (t) { return t !== cur; })).forEach(function (t) {
      var id = AREAS[t.a].id;
      if (!by[id]) { by[id] = []; order.push(id); }
      by[id].push(t.r);
    });
    return '#q=' + order.map(function (id) { return id + ':' + by[id].join(','); }).join(';');
  }
  function writeHash() { var h = hashFor(); if (h) setHash(h); else clearHash(); }
  /* the shown question's area on the phones' toolbar */
  function areaLabelM() {
    var m = VL.$('#tr-area-m'), t = current();
    if (m) m.innerHTML = t ? VL.UH(areaPair(AREAS[t.a])) : '';
  }
  function traceOf(areaId, rank) { var a = BY[areaId]; return a ? TRK[AIX[a.id] + ':' + rank] || null : null; }
  function canonical(list) {
    var seen = {}, out = [];
    list.forEach(function (t) { if (t && !seen[t.k]) { seen[t.k] = 1; out.push(t); } });
    return out.sort(function (x, y) { return x.a - y.a || x.r - y.r; });
  }
  function noteCurrent() {
    var t = current();
    T.selected = state.sel.map(key);
    if (!t) { T.current = null; return; }
    var co = t.co;
    T.current = { key: key(t), area: AREAS[t.a].id, rank: t.r, index: state.cur, of: state.sel.length, q: G.i[co[0]], answer: G.i[co[1]],
      provision: G.i[co[2]], law: G.i[co[3]], term: co[4] >= 0 ? G.i[co[4]] : null, areaNode: G.i[co[5]], fg: t.f.length, nodes: t.n.length,
      segments: t.e.length / 3 };
  }
  /* the choice becomes list (traces; kept in the list's order) with cur shown: the rows, the deep link, the scene's
     alphas and bold paths (once), the call-outs and the hop panel */
  function setSelection(list, cur, opts) {
    opts = opts || {};
    list = canonical(list);
    state.sel = list;
    state.cur = list.length ? Math.max(0, list.indexOf(cur)) : -1;
    if (opts.user) writeHash();
    noteCurrent();
    markList(opts.scroll !== false);
    areaLabelM();
    if (!T.fallback) { applySelection(); buildLabels(); }
    T.choices = (T.choices || 0) + 1;
    return showCurrent(opts);
  }
  function chooseOnly(areaId, rank, opts) {
    var t = traceOf(areaId, rank);
    return t ? setSelection([t], t, opts) : Promise.resolve(null);
  }
  /* add a trace (it is shown) or remove it (the shown one removed: its neighbour in the list is shown) */
  function toggleTrace(areaId, rank, opts) {
    var t = traceOf(areaId, rank);
    if (!t) return Promise.resolve(null);
    var i = state.sel.indexOf(t), list = state.sel.slice(), cur = current();
    if (i >= 0) { list.splice(i, 1); if (cur === t) cur = list[Math.min(i, list.length - 1)] || null; }
    else { list.push(t); cur = t; }
    return setSelection(list, cur, opts);
  }
  /* an area heading's 'All 20': its 20 questions become the choice (the first shown); pressed again (all 20 chosen) they
     leave it */
  function chooseArea(areaId, opts) {
    var a = BY[areaId];
    if (!a) return Promise.resolve(null);
    opts = opts || {};
    var ai = AIX[a.id], all = AREA_T[ai] || [];
    if (!all.length) return Promise.resolve(null);
    var allIn = all.every(function (t) { return state.sel.indexOf(t) >= 0; });
    if (allIn && opts.toggle !== false) {
      var rest = state.sel.filter(function (t) { return t.a !== ai; }), cur = current();
      return setSelection(rest, rest.indexOf(cur) >= 0 ? cur : rest[0] || null, opts);
    }
    return setSelection(all, all[0], opts);
  }
  /* the stepper: the previous or next chosen trace is shown (the choice and the scene's alphas stay) */
  function step(d, opts) {
    var n = state.sel.length;
    if (n < 2) return Promise.resolve(null);
    var i = Math.max(0, Math.min(n - 1, state.cur + d));
    if (i === state.cur) return Promise.resolve(current());
    state.cur = i;
    if (opts && opts.user) writeHash();
    noteCurrent();
    markList(true);
    areaLabelM();
    if (!T.fallback) buildLabels();
    T.steps = (T.steps || 0) + 1;
    return showCurrent(opts);
  }
  function clearSelection(user) {
    seq++;                                         // also drops a panel whose area file is still loading
    if (!state.sel.length) return;
    state.sel = [];
    state.cur = -1;
    noteCurrent();
    T.panel = null;
    markList(false);
    if (user) clearHash();
    areaLabelM();
    if (T.fallback) { fbEl.innerHTML = ''; fbEl.classList.add('hidden'); return; }
    applySelection();
    buildLabels();
  }
  /* the hop panel of the shown trace (its area's file loaded first; a later choice wins) */
  function showCurrent(opts) {
    opts = opts || {};
    var t = current();
    if (!t) { seq++; closePanel(); return Promise.resolve(null); }
    var a = AREAS[t.a], my = ++seq;
    if (!AD[a.id]) openPanel(closeHtml() + stepHtml() + '<p class="tr-status">' + VL.TH('tr3d.loading') + '</p>');
    return loadArea(a).then(function () {
      if (my !== seq) return null;
      var tr = AD[a.id][t.r];
      openPanel(tracePanelHtml(a, tr), !!opts.keepScroll);
      panelNode = -1;
      T.panel = key(t);
      if (T.fallback) drawFallback(a, tr);
      return t;
    }, function (err) {
      T.errors.push(String(err && err.message || err));
      if (my === seq) openPanel(closeHtml() + stepHtml() + '<p class="tr-status">' + VL.UH('tr3d.areaError', { file: a.file }) + '</p>');
      return null;
    });
  }

  /* ------------------------------------------------------------------ no WebGL: the shown trace in 2D */
  function drawFallback(a, tr) {
    var view = window.matchMedia('(min-width: 760px)').matches ? 'wide' : 'tall';
    var mode = VL.lang();
    fbEl.innerHTML = '<p class="tr-fb-note">' + enFirst('tr3d.noWebgl') + '</p>' +
      '<div class="tr-fb-fig" data-view="' + view + '">' + TD.svg(tr, view, { id: 'tf-' + a.id + '-' + tr.rank, title: mode === 'en' ? (tr.qa.en || tr.qa.vi) : tr.qa.vi,
        desc: mode === 'envi' ? tr.qa.en : '', nodeTitles: true, lang: mode }) + '</div>';
    M.labelsLang = mode;
    fbEl.classList.remove('hidden');
    T.fallbackView = view;
  }

  /* ------------------------------------------------------------------ legend, tools, theme */
  /* the traced path as the scene draws it: the links' S-curve (vertical tangents, control points at 45 % of the rise),
     navy core over the gold halo; ' s' = structural (fainter, thinner core); ' l' = the traces not chosen: thin threads
     in their colours (by area those of the three largest areas, by kind the one neutral thread colour) */
  function curveSwatch(mod) {
    var d = 'M2 10 C2 6.4 20 5.6 20 2';
    if (mod === ' l') {
      var cols = state.colorBy === 'area' && AREA_RANK ? [0, 1, 2].map(function (r) { return threadMix(TH.areas[r]); }) : [threadMix(TH.link)];
      var ds = cols.length > 1 ? ['M1 10 C1 6.4 16 5.6 16 2', 'M3.5 10 C3.5 6.4 18.5 5.6 18.5 2', 'M6 10 C6 6.4 21 5.6 21 2'] : [d];
      return '<svg class="tr-sw l" viewBox="0 0 22 12" aria-hidden="true">' + cols.map(function (c, k) {
        return '<path class="core" style="stroke:' + c + '" d="' + ds[k] + '"/>';
      }).join('') + '</svg>';
    }
    return '<svg class="tr-sw' + mod + '" viewBox="0 0 22 12" aria-hidden="true"><path class="halo" d="' + d + '"/><path class="core" d="' + d + '"/></svg>';
  }
  /* the legend: a head row (its title, the colour switch), then colouring by area the 27 areas (in the side list's
     order, in three columns) and one line for the kinds (told apart by layer and size), or colouring by
     kind the paper's class colours; the links and the strokes; the note. "Tiếng Việt · English" entries in EN-VI, one
     language in EN or VI */
  function colorSwitch() {
    var SEP = { sep: '\u00a0· ' };
    return '<div class="seg tr-colorby" role="group" aria-label="' + esc(VL.U('tr3d.colorBy.aria')) + '">' + ['area', 'kind'].map(function (m) {
      return '<button type="button" data-color="' + m + '" aria-pressed="' + (state.colorBy === m ? 'true' : 'false') + '">' + VL.TH('tr3d.colorBy.' + m, null, SEP) + '</button>';
    }).join('') + '</div>';
  }
  function areaLegendName(a) { return VL.TH(areaPair(a), null, { sep: '\u00a0· ' }); }
  function renderLegend() {
    var SEP = { sep: '\u00a0· ' }, byArea = state.colorBy === 'area';
    function li(color, pair, small) {
      return '<li><span class="swatch' + (small ? ' small' : '') + '" style="background:' + color + '"></span>' + VL.TH(pair, null, SEP) + '</li>';
    }
    var strokes = '<li>' + curveSwatch('') + VL.TH('tr3d.lg.traced', null, SEP) + '</li>' +
      '<li>' + curveSwatch(' s') + VL.TH('tr3d.lg.structural', null, SEP) + '</li>' +
      '<li>' + curveSwatch(' l') + VL.TH('tr3d.lg.light', null, SEP) + '</li>';
    var docLinks = '<li>' + curveSwatch(' n') + VL.TH('tr3d.lg.docLinks', null, SEP) + '</li>', body;
    if (byArea) {
      var none = T.areaColour ? T.areaColour.unassigned + T.areaColour.docsWithoutArea : 0;
      body = '<ul class="tr-areas">' + AREAS.map(function (a, ai) {
        return '<li data-area="' + a.id + '"><span class="swatch" style="background:' + (AREA_RANK ? areaHex(ai) : 'transparent') + '"></span><span class="tr-an">' + areaLegendName(a) + '</span></li>';
      }).join('') + '</ul><ul>' +
        (none ? li(TH.areaNone, VL.kpair('net.lg.noArea')) : '') +
        '<li><span class="tr-kinds" aria-hidden="true"><i style="width:10px;height:10px"></i><i style="width:7px;height:7px"></i><i style="width:4px;height:4px"></i></span>' +
        VL.TH('tr3d.lg.kinds', null, SEP) + '</li>' + docLinks + strokes + '</ul>';
    } else {
      var items = [li('var(--cls-work)', VL.kpair('tr3d.cls.document')), docLinks,
        /* the provision fan: three flat swatches (chapter, article, point), as the paper's legends use flat colours */
        '<li><span class="tr-sw3" aria-hidden="true">' + ['chapter', 'article', 'point'].map(function (k) {
          return '<span class="swatch" style="background:var(--cls-' + k + ')"></span>'; }).join('') + '</span>' + VL.TH(VL.kpair('tr3d.lg.provisions'), null, SEP) + '</li>'];
      VL.PAPER_CLASSES.forEach(function (c) { if (['term', 'question', 'answer', 'area'].indexOf(c.key) >= 0) items.push(li(c.v, VL.pair(c.vi, c.en))); });
      items.push(li('var(--cls-question)', VL.kpair('tr3d.lg.other'), true));
      body = '<ul>' + items.join('') + strokes + '</ul>';
    }
    legendEl.innerHTML = '<div class="tr-lg-head"><h3>' + VL.TH('tr3d.lg.title') + '</h3>' + colorSwitch() + '</div>' + body +
      '<p class="lg-note">' + enFirst('tr3d.lg.note') + '</p>';
    legendEl.classList.toggle('lg-area', byArea);
    legendEl.classList.toggle('hidden', !state.legendOpen);
    VL.$$('.tr-colorby button', legendEl).forEach(function (b) {
      b.addEventListener('click', function () { setColorBy(b.getAttribute('data-color'), { focus: true }); });
    });
    VL.$('#btn-legend').setAttribute('aria-expanded', state.legendOpen ? 'true' : 'false');
    T.legendEntries = VL.$$('li', legendEl).length;
    T.legendAreas = byArea ? VL.$$('.tr-areas li', legendEl).length : 0;
    fitLegendHeight();
  }
  /* the legend never runs under the stage tools or the first-visit hint above it: taller than the room left, it gets a
     max-height and scrolls */
  function fitLegendHeight() {
    if (!legendEl) return;
    // a resized column (wide screens: .cols-custom, js/common.js VL.columns) can bring the status line under the legend:
    // the legend then sits above it, as on the other 3D views (js/paper3d.js VL.fitLegend); the default layout is as before
    if (stage.classList.contains('cols-custom')) VL.fitLegend(stage, legendEl, statusEl); else stage.classList.remove('legend-lift');
    legendEl.style.maxHeight = '';
    T.legendMaxH = null;
    if (legendEl.classList.contains('hidden')) return;
    var hr = host.getBoundingClientRect(), lr = legendEl.getBoundingClientRect();
    if (lr.width < 2 || lr.height < 2) return;
    var lx0 = lr.left - hr.left, lx1 = lr.right - hr.left, lb = lr.bottom - hr.top, top = 8;
    // colouring by area on wide screens: the 27 areas' legend reaches no higher than LEGEND_TOP of the canvas (it scrolls
    // inside), so the laws' call-outs left of the scene keep their room
    if (state.colorBy === 'area' && !mobile) top = Math.max(top, Math.round(hr.height * LEGEND_TOP));
    ['.stage-tools', '#hint'].forEach(function (q) {
      var b = boxIn(VL.$(q, stage));
      if (b && b.x0 < lx1 && b.x1 > lx0 && (b.y0 + b.y1) / 2 < lb - 40) top = Math.max(top, b.y1 + 8);
    });
    var room = Math.floor(lb - top);
    if (lr.height > room) { legendEl.style.maxHeight = Math.max(80, room) + 'px'; T.legendMaxH = Math.max(80, room); }
  }
  /* colour by area or by kind (the legend's switch, VL.store, #color=): only the colours change - the choice, the alphas,
     the camera and the panel stay; the call-outs are placed again around the new legend */
  function setColorBy(mode, opts) {
    if ((mode !== 'area' && mode !== 'kind') || mode === state.colorBy) return;
    state.colorBy = mode;
    T.colorBy = M.colorBy = mode;
    T.colorSwitches = (T.colorSwitches || 0) + 1;
    VL.store.set(COLOR_KEY, mode);
    app.classList.toggle('tr-color-kind', mode === 'kind');
    renderLegend();
    if (opts && opts.focus) { var b = VL.$('.tr-colorby [data-color="' + mode + '"]', legendEl); if (b) b.focus(); }
    if (renderer && netObj) { applyColors(); drawFgNodes(); }
    tip.classList.add('hidden');
    needsRender = true;
    scheduleCallouts();
  }
  app.classList.toggle('tr-color-kind', state.colorBy === 'kind');
  VL.$('#btn-legend').innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>';
  VL.$('#btn-reset').innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>';
  VL.$('#btn-legend').addEventListener('click', function () { state.legendOpen = !state.legendOpen; renderLegend(); scheduleCallouts(); });
  /* the scene never moves by itself (choosing, searching and the list only change the drawing): Reset view returns to
     the whole scene (the choice stays), Zoom to selection frames every chosen trace (nothing chosen: the whole scene) */
  function resetView() { if (camera && D) fitAll(800); }
  function zoomToSelection() {
    if (!camera || !D) return;
    if (state.sel.length) fitChosen(800);
    else fitAll(800);
  }
  var zoomBtn = VL.$('#btn-zoom');
  if (zoomBtn) {
    zoomBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.3-4.3M11 8.5v5M8.5 11h5"/></svg>';
    zoomBtn.addEventListener('click', zoomToSelection);
  }
  VL.$('#btn-reset').addEventListener('click', resetView);
  VL.$('#btn-reset-m').addEventListener('click', resetView);
  function setSide(open) {
    app.classList.toggle('side-open', open);
    VL.$('#btn-list-m').setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) closePanel();
    scheduleCallouts();          // the sheet is an obstacle of the call-outs while it is open
  }
  VL.$('#btn-list-m').addEventListener('click', function () {
    var open = !app.classList.contains('side-open');
    setSide(open);
    if (!open && current()) showCurrent({});     // the sheet closed: the hop sheet of the shown trace comes back
  });
  host.addEventListener('keydown', function (e) {
    var k = e.key;
    if (!camera) return;
    if (k === 'ArrowLeft') orbit(-0.1, 0);
    else if (k === 'ArrowRight') orbit(0.1, 0);
    else if (k === 'ArrowUp') orbit(0, -0.08);
    else if (k === 'ArrowDown') orbit(0, 0.08);
    else if (k === '+' || k === '=') orbit(0, 0, 0.85);
    else if (k === '-' || k === '_') orbit(0, 0, 1.18);
    else return;
    e.preventDefault();
  });
  document.addEventListener('keydown', function (e) {
    // typing fields keep their Escape, except the list's empty search box (Escape there closes / clears as anywhere)
    var typing = /INPUT|TEXTAREA|SELECT/.test((e.target && e.target.tagName) || '') && !(e.target === searchEl && !searchEl.value);
    if (e.key !== 'Escape' || typing) return;
    if (app.classList.contains('side-open')) { setSide(false); return; }
    if (state.sel.length) { clearSelection(true); closePanel(); return; }
    if (!panel.classList.contains('hidden')) { seq++; closePanel(); }
  });
  function showHint() { if (VL.store.get('hint-traces3d') !== 'off') { VL.$('#hint').classList.remove('hidden'); fitLegendHeight(); scheduleCallouts(); } }
  function hideHint() { var h = VL.$('#hint'); if (h && !h.classList.contains('hidden')) { h.classList.add('hidden'); fitLegendHeight(); scheduleCallouts(); } }
  VL.$('#hint-close').addEventListener('click', function () { hideHint(); VL.store.set('hint-traces3d', 'off'); });
  function status() {
    if (!G) return;
    statusEl.textContent = VL.U('tr3d.status', { docs: fmt(D ? D.N : G.net.nodes), nodes: fmt(TNODE.length || NG), traces: fmt(G.t.length) }) + (T.fps ? ' · ' + fmt(T.fps) + ' fps' : '');
  }
  function applyTheme() {
    readTheme();
    renderLegend();
    if (renderer && netObj) {
      renderer.setClearColor(TH.bg, 1);
      buildLayers();
      applyColors();
      drawSelected();
      buildLabels();
    }
    T.themeRenders++;
    M.themeRenders = (M.themeRenders || 0) + 1;
    needsRender = true;
  }
  window.addEventListener('vlonto-theme', applyTheme);
  function measureFps(ms) {
    return new Promise(function (resolve) {
      var f0 = T.frames, t0 = performance.now(), stop = false;
      (function spin() { if (stop) return; needsRender = true; requestAnimationFrame(spin); })();
      setTimeout(function () {
        stop = true;
        resolve(Math.round((T.frames - f0) * 10000 / (performance.now() - t0)) / 10);
      }, ms);
    });
  }

  /* ------------------------------------------------------------------ language switch (js/i18n.js 'vl:lang'): the data
     line, the list (headings, entries, count; its scroll, focus and search kept), the open panel (scroll kept), legend,
     status, the 2D fallback and the call-outs are rendered again in the new mode, then placed again; the choice and the
     camera stay */
  function applyLang() {
    T.langRenders = (T.langRenders || 0) + 1;
    M.langRenders = (M.langRenders || 0) + 1;
    renderRevs();
    if (QS.length) {
      var side = VL.$('#side'), st = side ? side.scrollTop : 0, act = document.activeElement && listEl.contains(document.activeElement) ? document.activeElement.id : null;
      renderList();
      if (side) side.scrollTop = st;
      if (act && document.getElementById(act)) document.getElementById(act).focus();
    }
    areaLabelM();
    if (!panel.classList.contains('hidden')) {
      var t = current();
      if (panelNode < 0 && t && AD[AREAS[t.a].id]) openPanel(tracePanelHtml(AREAS[t.a], AD[AREAS[t.a].id][t.r]), true);
      else if (panelNode >= NG && D) { var pd = panelNode; openPanel(docHtml(pd - NG), true); panelNode = pd; }
      else if (panelNode >= 0) { var pn = panelNode; openPanel(nodeHtml(pn), true); panelNode = pn; }
    }
    renderLegend();
    status();
    tip.classList.add('hidden');
    if (T.fallback) { var c = current(); if (c && AD[AREAS[c.a].id]) drawFallback(AREAS[c.a], AD[AREAS[c.a].id][c.r]); else M.labelsLang = VL.lang(); }
    else if (labelGroup && D) buildLabels();
    else M.labelsLang = VL.lang();
  }
  document.addEventListener('vl:lang', applyLang);

  /* ------------------------------------------------------------------ routing */
  /* #q=<area>:<r>[,<r>...][;<area>:<r>...] chooses those (the first listed shown); #area=<id>&all=1[&q=<rank>] the
     area's 20; v1's #area=<id>&q=<rank> one; #area=<id> alone scrolls the list to the area and chooses nothing */
  function parseHash() {
    var h = VL.params(), list = [], cur = null, scroll = null;
    if (h.q && String(h.q).indexOf(':') > 0) {
      String(h.q).split(';').forEach(function (grp) {
        var p = grp.split(':'), a = BY[p[0]];
        if (!a || p.length < 2) return;
        p[1].split(',').forEach(function (r) { var t = TRK[AIX[a.id] + ':' + parseInt(r, 10)]; if (t && list.indexOf(t) < 0) list.push(t); });
      });
      cur = list[0] || null;
    } else if (h.area && BY[h.area]) {
      var ai = AIX[h.area];
      if (h.all === '1') { list = (AREA_T[ai] || []).slice(); cur = TRK[ai + ':' + parseInt(h.q, 10)] || list[0] || null; }
      else if (h.q) { var t = TRK[ai + ':' + parseInt(h.q, 10)]; if (t) { list = [t]; cur = t; } }
      else scroll = h.area;
    }
    return { list: list, cur: cur, scroll: scroll };
  }
  function sameChoice(list, cur) {
    var a = canonical(list);
    return a.length === state.sel.length && a.every(function (t, i) { return t === state.sel[i]; }) && cur === current();
  }
  function route() {
    var r = parseHash();
    if (r.list.length) return sameChoice(r.list, r.cur) ? Promise.resolve(null) : setSelection(r.list, r.cur, {});
    if (state.sel.length) { clearSelection(false); closePanel(); }
    return r.scroll ? scrollToArea(r.scroll, { open: true }) : Promise.resolve(null);
  }
  window.addEventListener('hashchange', function () { if (G) route(); });

  /* ------------------------------------------------------------------ test and preview interface */
  function r3(v) { return Math.round(v * 1000) / 1000; }
  function r4(v) { return Math.round(v * 10000) / 10000; }
  /* the threads as their buffer holds them (snapshot): GL lines, the opacity, the distinct colours and each one's index */
  function threadTable() {
    var col = threads.obj.geometry.attributes.aColor.array, per = threads.segN * 2, pal = [], ix = {}, idx = new Array(threads.n);
    function h2(v) { var x = Math.round(v * 255); return (x < 16 ? '0' : '') + x.toString(16); }
    for (var i = 0; i < threads.n; i++) {
      var o = 3 * i * per, h = '#' + h2(col[o]) + h2(col[o + 1]) + h2(col[o + 2]);
      if (ix[h] == null) { ix[h] = pal.length; pal.push(h); }
      idx[i] = ix[h];
    }
    return { kind: 'lines', width: 1, opacity: r4(strokeAlpha), base: THREAD_A, mix: THREAD_MIX, seg: threads.segN, color: TH.link, palette: pal, colorIdx: idx, area: Array.prototype.slice.call(STROKE_AREA) };
  }
  function hist(arr) {
    var h = {};
    for (var i = 0; i < arr.length; i++) { var k = String(r3(arr[i])); h[k] = (h[k] || 0) + 1; }
    return h;
  }
  function nodeIndex(id) {
    var s = String(id);
    if (s.indexOf('doc:') === 0 && D) { var j = D.idx[s.slice(4)]; return j == null ? null : { g: DOCG[j], doc: j }; }
    var i = G ? G.i.indexOf(s) : -1;
    return i < 0 ? null : { g: i, doc: IS_WORK[i] ? WDOC[i] : -1 };
  }
  window.VLApp = window.VLApp || {};
  window.VLApp.traces = {
    area: function (id) { return scrollToArea(id, { open: true }); },     // the list at the area's heading (chooses nothing)
    select: function (id, rank) { return chooseOnly(id, rank, { user: true }); },
    toggle: function (id, rank) { return toggleTrace(id, rank, { user: true }); },
    areaAll: function (id) { return chooseArea(id, { user: true, toggle: false }); },
    clear: function () { clearSelection(true); closePanel(); },
    step: function (d) { return step(d, { user: true }); },
    search: function (q) { if (searchEl) { searchEl.value = q; applySearch(); } return T.shown; },
    question: function (id, rank) { var q = QBY[id + ':' + rank]; return q ? { vi: q.vi, en: q.en, law: q.law, node: q.t ? G.i[q.t.co[0]] : null } : null; },
    choice: function () { return { selected: T.selected.slice(), current: T.current ? T.current.key : null, index: state.cur, of: state.sel.length, hash: location.hash, step: T.step }; },
    /* the alpha the shaders get for a node (a trace node id, or 'doc:<network id>'): 1 = chosen; LIGHT = a document,
       or any node with nothing chosen; FAINT = a trace node not chosen while something is */
    alphaOf: function (id) {
      if (!netObj) return null;
      var n = nodeIndex(id);
      if (!n) return null;
      var a = n.doc >= 0 ? netObj.geometry.attributes.aAlpha.array[n.doc] : trObj.geometry.attributes.aAlpha.array[TPT[n.g]];
      return { alpha: r3(a), light: LIGHT, faint: FAINT, doc: n.doc >= 0, traced: n.g >= 0 };
    },
    /* the materials of the scene's points and lines (the v1.3 report's shader audit): blending flags, the alpha the
       fragment shader writes (its gl_FragColor's last component) and the point sizes (sums of the size attributes:
       a choice never changes them; the chosen traces' foreground nodes are a separate object) */
    materials: function () {
      if (!netObj) return null;
      function alphaOut(fs) { var m = /gl_FragColor = vec4\((.*)\);/.exec(fs || ''), s = m ? m[1] : '', d = 0; for (var i = s.length - 1; i >= 0; i--) { var ch = s[i]; if (ch === ')') d++; else if (ch === '(') d--; else if (ch === ',' && d === 0) return s.slice(i + 1).trim(); } return s; }
      function alphasOut(fs) {
        var re = /gl_FragColor = (vec4\(.*\));/g, m, out = [];
        while ((m = re.exec(fs || ''))) { var a = alphaOut('gl_FragColor = ' + m[1] + ';'); if (out.indexOf(a) < 0) out.push(a); }
        return out;
      }
      function one(name, obj) {
        var mat = obj.material;
        return { name: name, renderOrder: obj.renderOrder, transparent: !!mat.transparent, depthWrite: !!mat.depthWrite, depthTest: mat.depthTest !== false,
          alpha: alphaOut(mat.fragmentShader), alphas: alphasOut(mat.fragmentShader) };
      }
      var out = [one('documents', netObj), one('traceNodes', trObj), one('contextLinks', trEdges.obj)];
      Object.keys(netEdges).forEach(function (k) { out.push(one('networkLinks.' + k, netEdges[k].obj)); });
      out.push(one('strokes', threads.obj));
      [['bold.structural', boldS], ['bold.verified', boldV]].forEach(function (b) {
        b[1].object.children.forEach(function (m, i) { out.push(one(b[0] + '.' + ['halo2', 'halo', 'core'][i], m)); });
      });
      if (layerGroup) {         // the layer and Q&A planes: their meshes' highest draw order
        var po = { name: 'planes', renderOrder: -1, meshes: 0 };
        layerGroup.traverse(function (o) { if (o.material) { po.meshes++; po.renderOrder = Math.max(po.renderOrder, o.renderOrder); } });
        out.push(po);
      }
      if (fgObj) {
        var fo = one('foreground', fgObj);
        fo.count = fgObj.geometry.attributes.position.count;
        fo.uniforms = { minPx: r3(fgMat.uniforms.uMinPx.value), ring: r3(fgMat.uniforms.uRing.value), pad: r3(fgMat.uniforms.uPad.value), fog: 'uFog' in fgMat.uniforms };
        out.push(fo);
      }
      function sum(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return Math.round(s * 10) / 10; }
      return { list: out, sizes: { documents: sum(netObj.geometry.attributes.aSize.array), traceNodes: sum(trObj.geometry.attributes.aSize.array) } };
    },
    /* every alpha of the scene, as the shaders get them: per buffer the values and their counts, the link materials'
       opacities (each kind's network-3d.html opacity times LIGHT), the threads' opacity (THREAD_A, x FAINT / LIGHT while
       something is chosen); mismatched = trace nodes whose alpha is not 1 exactly when chosen */
    alphaState: function () {
      if (!netObj) return null;
      var ch = chosenNodes(), bad = 0, solid = 0, na = netObj.geometry.attributes.aAlpha.array, ta = trObj.geometry.attributes.aAlpha.array;
      for (var i = 0; i < NG; i++) {
        var a = IS_WORK[i] ? na[WDOC[i]] : ta[TPT[i]];
        if ((a === 1) !== !!ch.has[i]) bad++;
        if (a === 1) solid++;
      }
      var docsOff = 0;      // documents no trace reaches must stay light
      for (var j = 0; j < NP; j++) if (DOCG[j] < 0 && na[j] !== LIGHT32) docsOff++;
      var nl = {};
      Object.keys(netEdges).forEach(function (k) {
        nl[k] = { opacity: r3(netEdges[k].obj.material.uniforms.uOpacity.value), base: r3(NS.edgeOpacity(k, TH.dark, D.N)), links: netEdges[k].m,
          alphas: hist(netEdges[k].obj.geometry.attributes.aAlpha.array) };
      });
      return { light: LIGHT, faint: FAINT, rest: r3(state.sel.length ? FAINT32 : LIGHT32), docs: hist(na), traceNodes: hist(ta), traceLinks: hist(trEdges.obj.geometry.attributes.aAlpha.array), chosenNodes: ch.list.length,
        solidNodes: solid, mismatched: bad, untracedDocsNotLight: docsOff, netLinks: nl,
        strokes: { opacity: r4(threads.mat.uniforms.uOpacity.value), base: THREAD_A, mix: THREAD_MIX, width: 1, segments: threads.pieces, traced: TRACED.length, kind: 'lines' },
        contextRest: CTX_REST,
        bold: { verified: boldV.count(), structural: boldS.count() }, fg: T.fgDrawn, solid: T.solid, writes: T.selectionWrites };
    },
    /* the traced laws: each one's network point, its position and the document's (they must be the same) */
    laws: function () {
      if (!D) return null;
      var out = [];
      for (var i = 0; i < NG; i++) {
        if (!IS_WORK[i]) continue;
        var j = WDOC[i], extra = j >= D.N;
        out.push({ node: G.i[i], doc: String(G.d[String(i)]), point: j, extra: extra, docId: extra ? null : D.ids[j], rank: extra ? rankOfY(GPOS[3 * i + 1]) : D.rank[j],
          pos: [r3(GPOS[3 * i]), r3(GPOS[3 * i + 1]), r3(GPOS[3 * i + 2])], data: [G.p[3 * i] / 10, G.p[3 * i + 1] / 10, G.p[3 * i + 2] / 10],
          docPos: extra ? null : [r3(D.pos[3 * j]), r3(D.pos[3 * j + 1]), r3(D.pos[3 * j + 2])] });
      }
      return out;
    },
    areas: function () { return AREAS.map(function (a) { return a.id; }); },
    colorBy: function () { return state.colorBy; },
    setColorBy: function (m) { setColorBy(m); return state.colorBy; },
    /* the colours as drawn: the mode, the areas' ranks, colours and tokens, the area rule's counts */
    colorState: function () {
      if (!AREA_RANK) return null;
      return { mode: state.colorBy, ranked: AREA_ORDER.map(function (a) { return AREAS[a].id; }),
        colors: AREAS.map(function (a, k) { return { id: a.id, rank: AREA_RANK[k], color: areaHex(k), token: '--area-' + AREA_RANK[k] }; }),
        rule: T.areaColour || null, legendAreas: T.legendAreas, fg: T.fgDrawn };
    },
    /* a node (graph id) or document (network id): its area and the colour it is drawn in now */
    colorOf: function (id) {
      var n = nodeIndex(id);
      if (!n) return null;
      if (n.g >= 0) {
        var a = NAREA && NAREA[n.g] >= 0 ? AREAS[NAREA[n.g]].id : null;
        return { node: id, area: a, color: IS_WORK[n.g] ? docColor(WDOC[n.g]) : nodeColor(n.g), rule: nodeColor(n.g), kind: kindColor(n.g) };
      }
      var da = docArea(n.doc);
      return { doc: id, area: da >= 0 ? AREAS[da].id : null, color: docColor(n.doc) };
    },
    pick: function (x, y) { return pickId(pick(x, y)); },
    project: function (id) {                       // screen position (CSS px in the canvas) of a node, for tests
      var n = nodeIndex(id);
      if (!n || !camera) return null;
      var p = n.g >= 0 ? ptOf(n.g) : { x: D.pos[3 * n.doc], y: D.pos[3 * n.doc + 1], z: D.pos[3 * n.doc + 2] };
      var v = new THREE.Vector3(p.x, p.y, p.z).project(camera);
      return { x: (v.x + 1) / 2 * host.clientWidth, y: (1 - v.y) / 2 * host.clientHeight, inside: Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1 && v.z < 1 };
    },
    settle: function () { return T.sceneReady && !tween && !(callouts && callouts.last === null); },
    /* the camera (position, target) and the rectangles the views are framed in; Zoom to selection and Reset view */
    camera: function () { return camera ? { pos: camera.position.toArray(), target: controls.target.toArray() } : null; },
    view: function () { return camera && D ? { home: homeRect(), free: freeRect(), homeView: (function (f) { return { pos: f.pos.toArray(), target: f.target.toArray() }; })(homeView()) } : null; },
    zoom: function () { zoomToSelection(); },
    reset: function () { resetView(); },
    /* the current view as data, for tests and offline previews of the page without a GPU (read-only): the camera, the
       colours, alphas and sizes the shaders get (the network's positions and links are the data files'), the traced and
       chosen segments, the call-outs placed */
    snapshot: function () {
      if (!camera || !netObj) return null;
      var na = netObj.geometry.attributes, ta = trObj.geometry.attributes, la = trEdges.obj.geometry.attributes, solidDocs = [], i;
      for (i = 0; i < NP; i++) if (na.aAlpha.array[i] !== LIGHT32) solidDocs.push([i, r3(na.aAlpha.array[i])]);
      var links = [];
      for (i = 0; i < TL.m; i++) links.push([TL.s[i], TL.t[i], r3(la.aAlpha.array[i]), Math.round(la.aColor.array[3 * i] * 255), Math.round(la.aColor.array[3 * i + 1] * 255), Math.round(la.aColor.array[3 * i + 2] * 255)]);
      var fg = null;
      if (fgObj) {
        var fa = fgObj.geometry.attributes;
        fg = { pos: Array.prototype.map.call(fa.position.array, function (v) { return Math.round(v * 10) / 10; }), size: Array.prototype.map.call(fa.aSize.array, function (v) { return Math.round(v * 10) / 10; }),
          color: Array.prototype.map.call(fa.aColor.array, function (v) { return Math.round(v * 255); }),
          scale: FG_SIZE, minPx: FG_MIN_PX, ringPx: FG_RING_PX, ink: TH.ink, ring: TH.bg, order: ORDER.chosen, nodes: fgNodes.slice() };
      }
      var bold = { v: [], s: [] }, ver = new Set(), seen = new Set();
      state.sel.forEach(function (t) { var e = t.e; for (var j = 0; j < e.length; j += 3) if (e[j + 2] === 1) ver.add(pairKey(e[j], e[j + 1])); });
      state.sel.forEach(function (t) {
        var e = t.e;
        for (var j = 0; j < e.length; j += 3) { var kk = pairKey(e[j], e[j + 1]); if (seen.has(kk)) continue; seen.add(kk); (ver.has(kk) ? bold.v : bold.s).push([e[j], e[j + 1]]); }
      });
      return {
        w: host.clientWidth, h: host.clientHeight, fov: camera.fov, near: camera.near, far: camera.far, dpr: renderer.getPixelRatio(),
        pos: camera.position.toArray().map(r3), target: controls.target.toArray().map(r3), up: camera.up.toArray(),
        dataset: DS, docs: D.N, extra: EXTRA.map(function (gi) { return gi; }), light: LIGHT, bg: TH.bg, dark: !!TH.dark, docColor: TH.doc, linkColor: TH.link,
        colorBy: state.colorBy, docColors: docColorTable(),
        zs: NS.ZS, extent: D.extent, layers: [0, 1, 2, 3, 4, 5].map(function (r) { return NS.layerY(D, r); }), qaPlanes: [G.planes.z_answer * NS.ZS, G.planes.z_question * NS.ZS],
        plane: { color: TH.plane, opacity: TH.planeOpacity, line: TH.planeLine, lineOpacity: TH.planeLineOpacity },
        netLinks: Object.keys(netEdges).map(function (k) { return { kind: k, m: netEdges[k].m, seg: netEdges[k].seg, opacity: r3(netEdges[k].obj.material.uniforms.uOpacity.value) }; }),
        docSize: Array.prototype.map.call(na.aSize.array, function (v) { return Math.round(v * 10) / 10; }), docSolid: solidDocs,
        gpos: Array.prototype.map.call(GPOS, function (v) { return Math.round(v * 10) / 10; }),
        traceNodes: { nodes: TNODE, alpha: Array.prototype.map.call(ta.aAlpha.array, r3), size: Array.prototype.slice.call(ta.aSize.array),
          color: Array.prototype.map.call(ta.aColor.array, function (v) { return Math.round(v * 255); }), blend: trObj.material.transparent && !trObj.material.depthWrite ? 'alpha' : 'opaque' },
        faint: FAINT, traceLinks: links, traceLinkSeg: trEdges.seg, traced: TRACED, strokes: threadTable(),
        bold: bold, boldStyle: { v: boldStyle(1), s: boldStyle(0.55), sOpacity: P.dark ? 0.6 : 0.62, seg: TRACE_SEG }, fg: fg,
        curve: { curves: CURVES, bend: NS.BEND, gap: NS.LAYER_GAP, liftMax: NS.LIFT_MAX },
        rim: ptMat.uniforms.uRim.value, fog: [FOG.value.x, FOG.value.y, FOG.value.z],
        paper: { core: P.core, halo: P.halo, halo2: P.halo2, calloutBg: P.calloutBg, calloutLine: P.calloutLine, selBg: P.selBg,
          selLine: P.selLine, ink: P.ink, ink2: P.ink2, leader: P.leader },
        labels: labels.map(function (s) { return { id: s.__id, sel: !!s.__sel, must: !!s.__must, layer: !!s.__layer, px: s.__px, lines: s.__opts.lines }; }),
        callouts: M.callouts || null, home: homeRect(), free: freeRect(), selected: T.selected, current: T.current
      };
    }
  };

  /* ------------------------------------------------------------------ start */
  renderLegend();
  var t0 = performance.now();
  listReady = loadQuestions().then(function (d) { prepareQuestions(d); renderList(); return d; });
  var routed = null;
  VL.fontsReady().then(function () {
    return Promise.all([loadGraph(), listReady]);
  }).then(function (r) {
    prepareGraph(r[0]);
    linkQuestionNodes();
    rankAreas();
    renderLegend();
    paintHeads();
    T.graphMs = Math.round(performance.now() - t0);
    T.webgl = webglOk();
    /* the side column and the details panel: resizable on wide screens (js/common.js VL.columns); the page's own resize
       follows (renderer size, camera aspect, call-outs, legend; the camera's position and target stay) */
    window.VLApp.columns = VL.columns({ app: VL.$('#app'), side: VL.$('#side'), stage: VL.$('#stage'), panel: VL.$('#panel'),
      onResize: onResize, live: function () { return !SOFT_GL; } });
    if (T.webgl) {
      try { initThree(); } catch (e) { T.webgl = false; T.webglError = String(e && e.message || e); renderer = null; }
    }
    if (!T.webgl) {
      T.fallback = true;
      stage.classList.add('tr-no-webgl');
      if (TD) { var d = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); d.setAttribute('class', 'tr-defs'); d.setAttribute('width', '0'); d.setAttribute('height', '0'); d.setAttribute('aria-hidden', 'true'); d.innerHTML = TD.defs(); document.body.appendChild(d); }
    }
    /* a deep link chooses as soon as the list and the traces are known (the hop panel opens); the scene shows the choice
       when the network is drawn */
    routed = route();
    status();
    if (T.fallback) { hideVeil(); return null; }
    veilText(DS === 'full' ? VL.U('net.loadingAll', { n: fmt(NS.dsCount('full')) }) : VL.U('net.loadingN', { n: fmt(NS.dsCount('lite')) }));
    var tn = performance.now();
    return NS.load(DS).then(function (net) {
      if (!net) throw new Error('data/' + NS.datasetKey(DS) + '.js did not register ' + NS.datasetKey(DS));
      return new Promise(function (res) { setTimeout(function () { res(net); }, 20); });
    }).then(function (net) {
      T.loadMs = Math.round(performance.now() - tn);
      linkNetwork(net);
      buildScene();
      bindPointer();
      showHint();
      fitAll(0);
      buildLabels();
      T.sceneReady = true;
      status();
      hideVeil();
    });
  }).then(function () {
    return routed;
  }).then(function () {
    T.readyMs = Math.round(performance.now() - t0);
    return new Promise(function (res) { requestAnimationFrame(function () { requestAnimationFrame(res); }); });
  }).then(function () {
    return T.fallback ? null : measureFps(700);
  }).then(function (fps) {
    if (fps != null) T.fps = fps;
    status();
    VL.setReady({ tracesQuestions: QS.length, webglRenderer: M.webglRenderer, fps: T.fps, dataset: DS });
  }).catch(function (e) {
    console.error(e);
    T.errors.push(String(e && e.message || e));
    veilText(VL.U('tr3d.loadError', { msg: e && e.message }));
    VL.setReady({ tracesError: String(e && e.message || e) });
  });
})();

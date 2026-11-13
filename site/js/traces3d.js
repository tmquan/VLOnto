/* VLOnto - question traces in 3D (traces.html): ONE interactive WebGL scene with all traced answers of the 27 legal
   areas (data/traces/graph.js, built by scripts/site/trace_global.py): laws, chapters, sections, articles, clauses and
   points, questions, answers, terms and areas, every node once, the areas as regions of the floor in the order of the
   list, each laid out like the paper's Fig. 1 (arXiv:2611.11426). All questions and all areas are one place: no area
   is ever 'opened' and nothing is dimmed by area.
   - the map is static: every node and link keeps its place and the camera only moves when the reader moves it (or asks
     for 'Zoom to selection' / 'Reset view'); choosing, searching and the list change the drawing only;
   - one side list of all 540 traced questions under their 27 area headings (data/traces/questions.js) with a search
     that filters on the question's words, its English gloss, the law's name and number and the area's name
     (diacritic-insensitive), an 'n of 540' live line and arrow keys; a click on a question node in the scene chooses it
     too (hover: its question in a tooltip);
   - choosing a question draws its trace solid and bold on top (navy core over the gold halo, js/paper3d.js
     VL.TraceLines; the V/W arms with the term -> defining clause hop) and fades the rest of the map as a focus volume:
     every other node and link takes an opacity from its 3D distance to the trace (a Gaussian transfer function in the
     shaders, the distances computed once per choice), context nodes become soft splats and the far map a haze toward
     the page ground; it places bilingual call-outs with VL.Callouts (question, provision, law, term, area; never over
     ink or each other) and shows the Fig. 5 hop panel (titles and hop data from data/traces/<area>.js, loaded when a
     question of the area is first chosen; no fetch, file:// works);
   - rotate, zoom and pan (OrbitControls), hover and click any node for its details, deep links #q=<area>:<rank> (and
     v1's #area=<id>&q=<rank>; #area=<id> alone scrolls the list to the area), keyboard (search, list, arrows and +/-
     on the canvas, Esc), reset view (the whole map), zoom to selection, flat legend;
   - phones: the question list (with its search) and the hop panel are bottom sheets; the whole map is drawn;
   - without WebGL the page keeps the list, its search and the hop panel and draws the chosen trace in 2D
     (js/trace-draw.js, the build-time drawing in the area file).
   Points and lines follow js/network3d.js (custom point shader with soft pastel spheres, LineSegments, depth fade,
   render on demand); paper3d.js, labels3d.js and common.js are used as they are.
   window.__VLONTO_METRICS.traces and .callouts, and window.VLApp.traces, serve the interaction tests.
   Text follows the language mode of js/i18n.js (docs/i18n.md; dictionary js/i18n-3d.js, keys tr3d.*): EN shows the
   questions' English glosses, VI the Vietnamese titles, EN–VI both (as in v1); headings, list, hop panel, node panel,
   legend, call-outs and status lines likewise. A mode change ('vl:lang') renders them again in place and keeps the
   chosen trace, the search, the camera, the open panel and the list's scroll and focus. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS, TD = VL.TraceDraw;
  VL.chrome({ scene: true });
  M.page = 'traces';
  M.paperStyle = true;
  var IDX = window.VLONTO.traces_index;
  var T = M.traces = { available: false, areas: 0, groups: 0, shown: 0, query: '', loaded: [], selected: null, traceSegments: 0, hops: 0, listItems: 0,
    renders: 0, frames: 0, errors: [], webgl: null, fallback: false, flights: 0, themeRenders: 0 };
  var esc = VL.esc, fmt = VL.fmt;
  /* a count that picks the English singular (en_one) */
  function nv(c) { return c === 1 ? 1 : fmt(c); }
  function tipAttr(k, vars) { var t = VL.tip(k, vars); return t ? ' title="' + esc(t) + '"' : ''; }
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host'), panel = VL.$('#panel'), tip = VL.$('#tip');
  var legendEl = VL.$('#legend'), statusEl = VL.$('#status'), listEl = VL.$('#tr-list'), searchEl = VL.$('#tr-search'), countEl = VL.$('#tr-count');
  var fbEl = VL.$('#tr-fallback'), veil = VL.$('#veil');
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

  /* ------------------------------------------------------------------ theme */
  var P = {}, TH = {};
  function readTheme() {
    P = VL.paperTheme();
    TH = { dark: P.dark, bg: P.bg };
    M.sceneBg = P.bg;
    M.traceCore = P.core;
  }
  readTheme();

  /* ------------------------------------------------------------------ the questions (one list, area by area) */
  /* an area's name: EN–VI its Vietnamese and English names (v1), EN or VI one name */
  function areaPair(a) { return VL.pair(a.label_vi, a.label_en); }
  /* every traced question (data/traces/questions.js, scripts/site/trace_site.py): {a: area index, id: area id, rank,
     vi: title, en: English gloss, law: {vi, en, number}, verified, match, hay: its folded search text}; GROUPS[a] = the
     area's questions by rank; QNODE[node] = the question of a question node */
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
    G.t.forEach(function (t) { var q = QBY[AREAS[t.a].id + ':' + t.r]; if (q) { QNODE[t.co[0]] = q; q.t = t; } });
  }

  /* ------------------------------------------------------------------ data */
  var G = null, N = 0, POS = null, CLS = null, HOME = null, CNAME = [], TRK = {}, BYNODE = null, AD = {};
  var SIZE = { area: 13, work: 15, record: 9, chapter: 10, section: 9, article: 8.5, clause: 7.5, point: 6.5, term: 10, question: 12,
    answer: 10, other_question: 5 };
  var KIND_ALPHA = { contains: 1, cites: 0.8, mentions: 0.9, defines: 0.95, answers: 1, applies_to: 0.38, realizes: 0.85 };
  function loadGraph() {
    if (window.VLONTO.traces_graph) return Promise.resolve(window.VLONTO.traces_graph);
    return VL.loadScript('data/traces/' + ((IDX.graph && IDX.graph.file) || 'graph.js')).then(function () {
      if (!window.VLONTO.traces_graph) throw new Error('data/traces/graph.js did not register traces_graph');
      return window.VLONTO.traces_graph;
    });
  }
  function prepare(g) {
    G = g;
    N = g.i.length;
    CNAME = g.classes;
    POS = new Float32Array(N * 3);
    for (var k = 0; k < N * 3; k++) POS[k] = g.p[k] / 10;
    CLS = Uint8Array.from(g.c);
    HOME = Int16Array.from(g.h);
    g.t.forEach(function (t, k) { t.k = k; TRK[t.a + ':' + t.r] = t; });
    T.graph = { nodes: N, links: Object.keys(g.e).reduce(function (s, k) { return s + g.e[k].length / 2; }, 0), traces: g.t.length };
  }
  function cname(i) { return CNAME[CLS[i]]; }
  function ptOf(i) { return { x: POS[3 * i], y: POS[3 * i + 1], z: POS[3 * i + 2] }; }
  function num(i) { return String(G.i[i]).split(':').pop(); }
  /* [Vietnamese, English] name of a node: questions, answers and other answers by id (their titles are not in the graph) */
  function names(i) {
    var c = cname(i), q = c === 'question' ? QNODE[i] : null;
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
    var key = 'traces_' + a.id;
    if (window.VLONTO[key]) return Promise.resolve(window.VLONTO[key]);
    return VL.loadScript('data/traces/' + a.file).then(function () {
      var d = window.VLONTO[key];
      if (!d || !d.traces) throw new Error('data/traces/' + a.file + ' did not register ' + key);
      if (T.loaded.indexOf(a.id) < 0) T.loaded.push(a.id);
      AD[a.id] = {};
      d.traces.forEach(function (tr) { AD[a.id][tr.rank] = tr; });
      return d;
    });
  }

  /* ------------------------------------------------------------------ three setup (as js/network3d.js) */
  function rgb(hex) { return VL.rawColor(hex, new THREE.Color()).toArray(); }
  var FOG = { value: new THREE.Vector3(1, 1e6, 0) };
  /* the focus volume's transfer function (see applyFocus): alpha = rest + (1 - rest) * exp(-(d / sigma)^2) of the 3D
     distance d (aDist) to the chosen trace, faded in by uFocus (0: nothing chosen, every node solid) */
  var FOCUS_GLSL = 'float focusAlpha(float d) { float x = d / uSigma; return mix(1.0, uRest + (1.0 - uRest) * exp(-x * x), uFocus); }';
  /* two passes draw the same nodes: the solid one (uHaze 0: shaded spheres with depth writes) takes the nodes of the
     chosen trace (d = 0), or all of them when nothing is chosen; the haze one (uHaze 1) the others as soft splats */
  var PT_VS = [
    'attribute vec3 aColor; attribute float aAlpha; attribute float aSize; attribute float aDist;',
    'uniform float uScale; uniform float uFocus; uniform float uSigma; uniform float uRest; uniform float uHaze; uniform float uSplat;',
    'varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    FOCUS_GLSL,
    'void main() {',
    '  vColor = aColor;',
    '  bool solid = uFocus < 0.5 || aDist <= 0.0;',
    '  vAlpha = (uHaze > 0.5) == solid ? 0.0 : aAlpha * focusAlpha(aDist);',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  vDepth = -mv.z;',
    '  float s = aSize * uScale / max(1.0, -mv.z) * (uHaze > 0.5 ? uSplat : 1.0);',
    '  gl_PointSize = vAlpha < 0.01 ? 0.0 : clamp(s, 1.5, 64.0);',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  var PT_FS = [
    'uniform vec3 uBg; uniform vec3 uFog; uniform float uRim; uniform float uHaze; uniform float uTint;',
    'varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    'void main() {',
    '  vec2 c = gl_PointCoord - vec2(0.5); float r = length(c) * 2.0;',
    '  if (r > 1.0 || vAlpha < 0.01) discard;',
    '  float f = clamp((vDepth - uFog.x) / max(1.0, uFog.y - uFog.x), 0.0, 1.0) * uFog.z;',
    '  if (uHaze > 0.5) {',
    // a soft round splat: Gaussian alpha falloff; the fainter it is, the nearer its colour to the page ground (haze, not glow)
    '    vec3 hc = mix(vColor, uBg, uTint * (1.0 - vAlpha));',
    '    gl_FragColor = vec4(hc, vAlpha * exp(-3.2 * r * r) * (1.0 - f));',
    '    return;',
    '  }',
    '  vec3 n = vec3(c.x * 2.0, -c.y * 2.0, sqrt(max(0.0, 1.0 - r * r)));',
    '  vec3 col = vColor * (0.86 + 0.2 * dot(n, vec3(-0.45, 0.55, 0.70)));',
    '  col = mix(col, vColor * uRim, smoothstep(0.76, 0.96, r));',
    '  gl_FragColor = vec4(mix(uBg, mix(col, uBg, f), vAlpha), 1.0);',
    '}'].join('\n');
  /* links as smooth curves, as the traces and the 3D legal network draw theirs (js/trace-draw.js TD.curve): a cubic Bezier
     with vertical tangents at both ends and control points at 45 % of the height difference; a link within one level is
     lifted into a soft arch (BEND x its horizontal length, at most LIFT_MAX, fading out over one level gap of height
     difference). The vertex shader evaluates the curve: one instanced draw per segment budget, a shared strip of SEG + 1
     points (t) and per-link endpoints, colour and alpha. curvePoint() is the same curve on the CPU (the traced ribbon and
     the call-out ink). #curves=0 draws straight links (one segment) to compare frame rates. */
  var CURVES = VL.params().curves !== '0', CV = { bend: 0.18, gap: 16, liftMax: 6.4 };
  var LN_VS = [
    'attribute float aT; attribute vec3 aA; attribute vec3 aB; attribute vec3 aColor; attribute float aAlpha; attribute float aDA; attribute float aDB;',
    'uniform float uBend; uniform float uLiftMax; uniform float uLayer; uniform float uFocus; uniform float uSigma; uniform float uRest;',
    'uniform vec3 uBg; uniform float uTint;',
    'varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    FOCUS_GLSL,
    'void main() {',
    // the link's distance to the trace along its length; as it fades its colour tends to the page ground, as the splats'
    '  float fa = focusAlpha(mix(aDA, aDB, aT));',
    '  vColor = mix(aColor, uBg, uTint * (1.0 - fa)); vAlpha = aAlpha * fa;',
    '  if (vAlpha < 0.01) { vDepth = 0.0; gl_Position = vec4(0.0, 0.0, 2.0, 1.0); return; }',
    '  vec3 d = aB - aA;',
    '  float k = 0.45 * d.y, lift = min(uBend * length(d.xz), uLiftMax) * clamp(1.0 - abs(d.y) / uLayer, 0.0, 1.0);',
    '  float t = aT, u = 1.0 - t, w0 = u * u * u, w1 = 3.0 * u * u * t, w2 = 3.0 * u * t * t, w3 = t * t * t;',
    '  vec3 p = vec3((w0 + w1) * aA.x + (w2 + w3) * aB.x,',
    '    w0 * aA.y + w1 * (aA.y + k + lift) + w2 * (aB.y - k + lift) + w3 * aB.y,',
    '    (w0 + w1) * aA.z + (w2 + w3) * aB.z);',
    '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
    '  vDepth = -mv.z;',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  function curvePoint(a, b, t) {
    var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, k = 0.45 * dy;
    var lift = Math.min(CV.bend * Math.sqrt(dx * dx + dz * dz), CV.liftMax) * Math.max(0, Math.min(1, 1 - Math.abs(dy) / CV.gap));
    var u = 1 - t, w0 = u * u * u, w1 = 3 * u * u * t, w2 = 3 * u * t * t, w3 = t * t * t;
    return { x: (w0 + w1) * a.x + (w2 + w3) * b.x, y: w0 * a.y + w1 * (a.y + k + lift) + w2 * (b.y - k + lift) + w3 * b.y,
      z: (w0 + w1) * a.z + (w2 + w3) * b.z };
  }
  function curvePts(a, b, n) {
    if (!CURVES) n = 1;
    var out = [];
    for (var i = 0; i <= n; i++) out.push(curvePoint(a, b, i / n));
    return out;
  }
  /* how far a link's curve leaves its chord (world units): an S between levels bends most when its run equals its rise */
  function curveDev(a, b) {
    var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, h = Math.sqrt(dx * dx + dz * dz);
    var lift = Math.min(CV.bend * h, CV.liftMax) * Math.max(0, Math.min(1, 1 - Math.abs(dy) / CV.gap));
    return Math.max(0.34 * Math.min(Math.abs(dy), h), 0.75 * lift);
  }
  var LN_FS = [
    'uniform float uOpacity; uniform vec3 uFog; varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    'void main() {',
    '  if (vAlpha < 0.01) discard;',
    '  float f = clamp((vDepth - uFog.x) / max(1.0, uFog.y - uFog.x), 0.0, 1.0) * uFog.z;',
    '  gl_FragColor = vec4(vColor, vAlpha * uOpacity * (1.0 - f));',
    '}'].join('\n');

  var renderer = null, scene, camera, controls, pointsObj = null, pointsMat = null, hazeObj = null, hazeMat = null, linesMat = null, lineGroups = [];
  var traceV = null, traceS = null, labelGroup = null, labels = [], callouts = null, needsRender = true, tween = null;
  var fgObj = null, fgMat = null;   // the selected trace's own nodes, drawn again over its strokes (as in the paper's figures)
  var EDGE = null;            // {s, t: Int32Array, k: Uint8Array (kind index), base: Float32Array, g, j: group and instance}
  var mobile = VL.isMobile();
  /* the reader's state: the chosen question (sel), the legend, the search text. No area is ever 'open': the 27 areas are
     one map and one list */
  var state = { sel: null, legendOpen: !mobile, query: '' };

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
    renderer = new THREE.WebGLRenderer({ antialias: !mobile, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2));
    renderer.setSize(sz.w, sz.h);
    renderer.setClearColor(TH.bg, 1);
    host.appendChild(renderer.domElement);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, sz.w / sz.h, 2, 40000);
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.09;
    controls.screenSpacePanning = true;
    controls.rotateSpeed = 0.55;
    controls.zoomSpeed = 0.9;
    controls.minDistance = 30;
    controls.maxDistance = 12000;
    controls.addEventListener('change', function () { needsRender = true; scheduleCallouts(); });
    controls.addEventListener('start', hideHint);
    labelGroup = new THREE.Group();
    scene.add(labelGroup);
    traceV = VL.TraceLines({ depthTest: false, renderOrder: 10 });
    traceS = VL.TraceLines({ depthTest: false, renderOrder: 7 });
    scene.add(traceS.object);
    scene.add(traceV.object);
    try {
      var gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
      M.webglRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    } catch (e) { M.webglRenderer = null; }
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
    needsRender = true;
    scheduleCallouts();
  }
  function updatePointScale() {
    if (pointsMat) pointsMat.uniforms.uScale.value = renderer.domElement.height / (2 * Math.tan(camera.fov * Math.PI / 360));
  }
  function updateFog() {
    if (!camera) return;
    var d = camera.position.distanceTo(controls.target), R = Math.max(300, viewRadius), k = FOCUS_U.uFocus.value;
    var base = TH.dark ? FOCUS.fog.dark : FOCUS.fog.light, deep = TH.dark ? FOCUS.fogFocus.dark : FOCUS.fogFocus.light;
    FOG.value.set(Math.max(1, d - 0.4 * R), d + 2.2 * R, base + (deep - base) * k);   // a deeper fog while a question is chosen
  }
  var viewRadius = 1000;
  function loop(t) {
    requestAnimationFrame(loop);
    if (tween) stepTween(t);
    if (fade) stepFade();
    var moved = controls.update();
    if (needsRender || moved || tween || fade) {
      updateFog();
      renderer.render(scene, camera);
      T.frames++;
      needsRender = false;
    }
  }

  /* ------------------------------------------------------------------ scene objects */
  function nodeColor(i) {
    var c = cname(i);
    return P.cls[c === 'other_question' ? 'question' : c] || '#9aa3ad';
  }
  function edgeColor(k, s, t) {
    var c = k === 'contains' ? cname(t) : k === 'cites' ? (cname(s) === 'other_question' ? 'question' : 'answer') :
      k === 'mentions' || k === 'defines' ? 'term' : k === 'realizes' ? 'record' : k === 'answers' ? 'answer' : 'area';
    return P.cls[c] || '#9aa3ad';
  }
  function buildScene() {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(POS, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(N).fill(1), 1));
    g.setAttribute('aDist', new THREE.BufferAttribute(new Float32Array(N), 1));   // distance to the chosen trace (applyFocus)
    var size = new Float32Array(N);
    for (var i = 0; i < N; i++) size[i] = SIZE[cname(i)] || 6;
    g.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
    g.computeBoundingSphere();
    CELL = (G.ext[1] - G.ext[0]) / (G.cols || 7);          // one area cell of the floor's grid, in world units
    SIGMA = FOCUS.sigmaCells * CELL;
    FOCUS_U.uSigma.value = SIGMA;
    FOCUS_U.uRest.value = FOCUS.rest;
    var U = { uScale: { value: 1 }, uBg: { value: VL.rawColor(TH.bg, new THREE.Color()) }, uFog: FOG, uRim: { value: TH.dark ? 0.7 : 0.84 },
      uFocus: FOCUS_U.uFocus, uSigma: FOCUS_U.uSigma, uRest: FOCUS_U.uRest, uHaze: { value: 0 }, uSplat: { value: FOCUS.splat }, uTint: { value: TH.dark ? FOCUS.tint.dark : FOCUS.tint.light } };
    pointsMat = new THREE.ShaderMaterial({ uniforms: U, vertexShader: PT_VS, fragmentShader: PT_FS, transparent: false, depthWrite: true });
    pointsObj = new THREE.Points(g, pointsMat);
    pointsObj.renderOrder = 2;
    scene.add(pointsObj);
    /* the haze: the same nodes, soft splats blended over the solid map and the links, no depth writes */
    var UH = {};
    Object.keys(U).forEach(function (k) { UH[k] = U[k]; });
    UH.uHaze = { value: 1 };
    hazeMat = new THREE.ShaderMaterial({ uniforms: UH, vertexShader: PT_VS, fragmentShader: PT_FS, transparent: true, depthWrite: false,
      depthTest: true, blending: THREE.NormalBlending });
    hazeObj = new THREE.Points(g, hazeMat);
    hazeObj.renderOrder = 3;
    scene.add(hazeObj);
    updatePointScale();
    /* all links as curves (see LN_VS): two instanced draws, links that visibly bend with SEG segments, near-straight ones
       (vertical chains, long runs between regions) with 2 */
    CV = { bend: 0.18, gap: 0.1 * G.H, liftMax: 0.04 * G.H };
    var kinds = G.kinds || Object.keys(G.e), m = 0;
    kinds.forEach(function (k) { m += (G.e[k] || []).length / 2; });
    EDGE = { s: new Int32Array(m), t: new Int32Array(m), k: new Uint8Array(m), base: new Float32Array(m), g: new Uint8Array(m), j: new Int32Array(m) };
    var e = 0, SEG = CURVES ? (mobile ? 6 : 8) : 1, counts = [0, 0];
    kinds.forEach(function (k, ki) {
      var arr = G.e[k] || [];
      for (var j = 0; j < arr.length; j += 2, e++) {
        var s = arr[j], tt = arr[j + 1];
        EDGE.s[e] = s; EDGE.t[e] = tt; EDGE.k[e] = ki;
        EDGE.base[e] = (KIND_ALPHA[k] || 0.8) * (HOME[s] !== HOME[tt] ? 0.35 : 1);   // links between regions: the sharing, faint
        var g = CURVES && curveDev(ptOf(s), ptOf(tt)) >= 1.5 ? 0 : 1;
        EDGE.g[e] = g; EDGE.j[e] = counts[g]++;
      }
    });
    EDGE.kinds = kinds;
    linesMat = new THREE.ShaderMaterial({
      uniforms: { uOpacity: { value: 0.5 }, uFog: FOG, uBend: { value: CV.bend }, uLiftMax: { value: CV.liftMax }, uLayer: { value: CV.gap },
        uFocus: FOCUS_U.uFocus, uSigma: FOCUS_U.uSigma, uRest: FOCUS_U.uRest, uBg: U.uBg, uTint: U.uTint },
      vertexShader: LN_VS, fragmentShader: LN_FS, transparent: true, depthWrite: false, blending: THREE.NormalBlending
    });
    lineGroups = [SEG, CURVES ? 2 : 1].map(function (S, g) {
      var n = counts[g], A = new Float32Array(3 * n), B = new Float32Array(3 * n);
      for (var q = 0; q < m; q++) {
        if (EDGE.g[q] !== g) continue;
        var a = EDGE.s[q], b = EDGE.t[q], o = 3 * EDGE.j[q];
        A[o] = POS[3 * a]; A[o + 1] = POS[3 * a + 1]; A[o + 2] = POS[3 * a + 2];
        B[o] = POS[3 * b]; B[o + 1] = POS[3 * b + 1]; B[o + 2] = POS[3 * b + 2];
      }
      var geo = new THREE.InstancedBufferGeometry(), tt2 = new Float32Array(S + 1), idx = new Uint16Array(2 * S);
      for (var i = 0; i <= S; i++) tt2[i] = i / S;
      for (var j2 = 0; j2 < S; j2++) { idx[2 * j2] = j2; idx[2 * j2 + 1] = j2 + 1; }
      geo.setAttribute('aT', new THREE.BufferAttribute(tt2, 1));
      geo.setIndex(new THREE.BufferAttribute(idx, 1));
      geo.setAttribute('aA', new THREE.InstancedBufferAttribute(A, 3));
      geo.setAttribute('aB', new THREE.InstancedBufferAttribute(B, 3));
      geo.setAttribute('aColor', new THREE.InstancedBufferAttribute(new Float32Array(3 * n), 3));
      geo.setAttribute('aAlpha', new THREE.InstancedBufferAttribute(new Float32Array(n), 1));
      geo.setAttribute('aDA', new THREE.InstancedBufferAttribute(new Float32Array(n), 1));
      geo.setAttribute('aDB', new THREE.InstancedBufferAttribute(new Float32Array(n), 1));
      geo.instanceCount = n;
      var obj = new THREE.LineSegments(geo, linesMat);
      obj.frustumCulled = false;
      obj.renderOrder = 1;
      scene.add(obj);
      return { obj: obj, seg: S, n: n, color: geo.attributes.aColor, alpha: geo.attributes.aAlpha, da: geo.attributes.aDA, db: geo.attributes.aDB };
    });
    for (var e2 = 0; e2 < m; e2++) lineGroups[EDGE.g[e2]].alpha.array[EDGE.j[e2]] = EDGE.base[e2];   // fixed; the focus is in the shader
    lineGroups.forEach(function (L) { L.alpha.needsUpdate = true; });
    T.linksShown = m;
    ALPHA = new Float32Array(N).fill(1);
    T.edgeCost = { curves: CURVES, links: m, vertices: lineGroups.reduce(function (s2, L) { return s2 + L.n * (L.seg + 1); }, 0),
      segments: lineGroups.reduce(function (s2, L) { return s2 + L.n * L.seg; }, 0), groups: lineGroups.map(function (L) { return [L.n, L.seg]; }) };
    applyColors();
    applyFocus(0);
  }
  function applyColors() {
    var col = pointsObj.geometry.attributes.aColor.array, cache = {};
    for (var i = 0; i < N; i++) {
      var hex = nodeColor(i), c = cache[hex] || (cache[hex] = rgb(hex));
      col[3 * i] = c[0]; col[3 * i + 1] = c[1]; col[3 * i + 2] = c[2];
    }
    pointsObj.geometry.attributes.aColor.needsUpdate = true;
    var f = TH.dark ? 0.78 : 0.86;
    for (var e = 0; e < EDGE.s.length; e++) {
      var hx = edgeColor(EDGE.kinds[EDGE.k[e]], EDGE.s[e], EDGE.t[e]), c0 = cache[hx] || (cache[hx] = rgb(hx)), lc = lineGroups[EDGE.g[e]].color.array, o = 3 * EDGE.j[e];
      lc[o] = c0[0] * f; lc[o + 1] = c0[1] * f; lc[o + 2] = c0[2] * f;
    }
    lineGroups.forEach(function (L) { L.color.needsUpdate = true; });
    linesMat.uniforms.uOpacity.value = TH.dark ? 0.42 : 0.55;
    VL.rawColor(TH.bg, pointsMat.uniforms.uBg.value);
    pointsMat.uniforms.uRim.value = TH.dark ? 0.7 : 0.84;
    pointsMat.uniforms.uTint.value = TH.dark ? FOCUS.tint.dark : FOCUS.tint.light;   // the haze tends to this theme's ground
    needsRender = true;
  }
  /* the focus volume (v1.1): a chosen question's trace is drawn solid and bold on top; every other node and link takes an
     opacity from its 3D distance d to the trace (the nearest trace node or link chord):
       alpha = rest + (1 - rest) * exp(-(d / sigma)^2),   sigma = sigmaCells x one area cell of the floor
     The distances are computed here once per choice (per node, and per link end - the line shader interpolates along
     the link); the shaders apply the transfer function and uFocus fades it in and out (uniforms only, no per-frame
     loop over the nodes). Context nodes are soft splats without depth writes, so the far map becomes a haze that fades
     toward the page ground, and the depth fog deepens while a question is chosen. Nothing chosen: the whole map, solid. */
  /* tuned on model renders of Labour and wages #3 (light and dark): sigma 0.7 of an area cell keeps the chosen area
     legible, the next areas at about 0.2 and the far map at the 0.07 floor; the haze (splats and links) tends to the
     page ground by tint x (1 - alpha), more in dark, where pale pastels would otherwise add up to a light mist */
  var FOCUS = { sigmaCells: 0.7, rest: 0.07, tint: { light: 0.5, dark: 0.8 }, splat: 1.3, fog: { light: 0.55, dark: 0.5 }, fogFocus: { light: 0.7, dark: 0.66 },
    fadeMs: 320, bold: mobile ? 1.3 : 1.5, fgSize: 1.35 };
  T.focus = FOCUS;
  var FOCUS_U = { uFocus: { value: 0 }, uSigma: { value: 1 }, uRest: { value: FOCUS.rest } };
  var CELL = 1, SIGMA = 1, ALPHA = null, DIST = null, fade = null;
  function transfer(d) { var x = d / SIGMA; return FOCUS.rest + (1 - FOCUS.rest) * Math.exp(-x * x); }
  /* d of every node to the trace t: the nearest of its link chords (t.e) - its own nodes (t.f) 0, every other node more */
  function traceDistances(t, out) {
    var e = t.e, ns = e.length / 3, Sg = new Float64Array(6 * ns), fg = new Uint8Array(N), k, i;
    for (k = 0; k < ns; k++) {
      var a = e[3 * k], b = e[3 * k + 1];
      for (var c = 0; c < 3; c++) { Sg[6 * k + c] = POS[3 * a + c]; Sg[6 * k + 3 + c] = POS[3 * b + c] - POS[3 * a + c]; }
    }
    t.f.forEach(function (j) { fg[j] = 1; });
    for (i = 0; i < N; i++) {
      if (fg[i]) { out[i] = 0; continue; }
      var px = POS[3 * i], py = POS[3 * i + 1], pz = POS[3 * i + 2], best = Infinity;
      for (k = 0; k < ns; k++) {
        var o = 6 * k, wx = px - Sg[o], wy = py - Sg[o + 1], wz = pz - Sg[o + 2], dx = Sg[o + 3], dy = Sg[o + 4], dz = Sg[o + 5];
        var L = dx * dx + dy * dy + dz * dz, u = L > 0 ? (wx * dx + wy * dy + wz * dz) / L : 0;
        u = u < 0 ? 0 : (u > 1 ? 1 : u);
        var qx = wx - u * dx, qy = wy - u * dy, qz = wz - u * dz, d2 = qx * qx + qy * qy + qz * qz;
        if (d2 < best) best = d2;
      }
      out[i] = Math.max(1e-3, Math.sqrt(best));
    }
    return out;
  }
  function applyFocus(ms) {
    if (!pointsObj) return;
    var sel = state.sel, pa = pointsObj.geometry.attributes, dist = pa.aDist.array;
    if (sel) {
      var t0 = performance.now();
      traceDistances(sel.t, dist);
      pa.aDist.needsUpdate = true;
      for (var e = 0; e < EDGE.s.length; e++) {
        var L = lineGroups[EDGE.g[e]], j = EDGE.j[e];
        L.da.array[j] = dist[EDGE.s[e]];
        L.db.array[j] = dist[EDGE.t[e]];
      }
      lineGroups.forEach(function (L2) { L2.da.needsUpdate = true; L2.db.needsUpdate = true; });
      for (var i = 0; i < N; i++) ALPHA[i] = transfer(dist[i]);
      T.focusMs = Math.round(performance.now() - t0);
    } else ALPHA.fill(1);      // the distances stay for the fade out
    DIST = dist;
    fadeTo(sel ? 1 : 0, ms);
  }
  /* uFocus towards v over ms (FOCUS.fadeMs), stepped by the render loop */
  function fadeTo(v, ms) {
    var u = FOCUS_U.uFocus;
    ms = ms != null ? ms : FOCUS.fadeMs;
    if (!ms || Math.abs(u.value - v) < 1e-3) { u.value = v; fade = null; T.focusValue = v; needsRender = true; return; }
    fade = { from: u.value, to: v, t0: performance.now(), ms: ms };
    needsRender = true;
  }
  function stepFade() {
    var k = Math.min(1, (performance.now() - fade.t0) / fade.ms), s = k * k * (3 - 2 * k);
    FOCUS_U.uFocus.value = fade.from + (fade.to - fade.from) * s;
    T.focusValue = Math.round(FOCUS_U.uFocus.value * 1000) / 1000;
    if (k >= 1) fade = null;
  }

  /* ------------------------------------------------------------------ camera */
  var DIR_ALL = new THREE.Vector3(0, 0.78, 1).normalize();
  var DIR_TRACE = new THREE.Vector3(0.28, 0.42, 1).normalize();
  /* camera position and target that show a box (lo, hi) from direction dir with a margin (share of the frame) */
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
  /* the part of the canvas the whole map is framed in. It is the same before and after a pick, so a pick never needs the
     camera to move: on wide screens the whole canvas below the hint and the stage tools and above the legend - the open
     hop panel lies over the map's right part, and a call-out whose node is under it is occluded, not misplaced; on
     phones above the hop sheet at its tallest (46 % of the stage) and below the hint (the map is as wide as the screen
     there, so a taller rectangle would not make it bigger) */
  var SHEET = 0.46;
  /* wide screens: gutters left and right of the map for the call-outs of its outermost areas (nothing can be placed
     beyond them) */
  var GUTTER = { left: 80, right: 24 };
  function boxIn(el) {
    if (!el || el.classList.contains('hidden') || el.hidden) return null;
    var b = el.getBoundingClientRect(), hr = host.getBoundingClientRect();
    return b.width > 1 && b.height > 1 ? { x0: b.left - hr.left, y0: b.top - hr.top, x1: b.right - hr.left, y1: b.bottom - hr.top } : null;
  }
  function mapRect() {
    var sz = stageSize(), r = { x0: 0, y0: 0, x1: sz.w, y1: sz.h }, h = boxIn(VL.$('#hint', stage)), lg = boxIn(legendEl);
    if (mobile) {
      r.y1 = sz.h * (1 - SHEET) - 6;
    } else {
      var tools = boxIn(VL.$('.stage-tools', stage)), st = boxIn(statusEl);
      r.x0 = GUTTER.left;
      r.x1 = sz.w - GUTTER.right;
      if (tools) r.y0 = Math.max(r.y0, tools.y1 + 6);
      if (lg) r.y1 = Math.min(r.y1, lg.y0 - 6);
      else if (st) r.y1 = Math.min(r.y1, st.y0 - 6);
    }
    if (h) r.y0 = Math.max(r.y0, h.y1 + 6);
    if (r.y1 - r.y0 < sz.h * 0.3) r.y1 = Math.min(sz.h, r.y0 + sz.h * 0.3);
    return r;
  }
  /* camera for the box seen along dir: the closest distance at which the box fits the rectangle rect of the canvas
     (default: all of it) with the margin; the camera is then shifted sideways so the box centre lands on the
     rectangle's centre (the view keeps its direction, so orbiting and picking need no special projection) */
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
    viewRadius = lo.distanceTo(hi) / 2;
    var fwd = dir.clone().negate(), right = new THREE.Vector3().crossVectors(fwd, camera.up).normalize();
    var up = new THREE.Vector3().crossVectors(right, fwd), halfH = b * tanH, halfW = halfH * sz.w / sz.h;
    var ncx = (rect.x0 + rect.x1) / sz.w - 1, ncy = 1 - (rect.y0 + rect.y1) / sz.h;
    var target = c.clone().addScaledVector(right, -ncx * halfW).addScaledVector(up, -ncy * halfH);
    return { pos: target.clone().addScaledVector(dir, b), target: target };
  }
  function boxOf(ids) {
    var lo = new THREE.Vector3(Infinity, Infinity, Infinity), hi = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
    ids.forEach(function (i) {
      lo.x = Math.min(lo.x, POS[3 * i]); lo.y = Math.min(lo.y, POS[3 * i + 1]); lo.z = Math.min(lo.z, POS[3 * i + 2]);
      hi.x = Math.max(hi.x, POS[3 * i]); hi.y = Math.max(hi.y, POS[3 * i + 1]); hi.z = Math.max(hi.z, POS[3 * i + 2]);
    });
    return { lo: lo, hi: hi };
  }
  /* the box fit framed by the nodes themselves: the box's near corners project wider than any node, so the box alone
     leaves the map smaller than the rectangle allows. Project every node with the camera, move it along its axis until
     the nodes' extent fills the rectangle (less the margin) and sideways until their middle is the rectangle's middle;
     a few rounds, as moving changes the perspective a little. The view keeps its direction */
  function fitNodes(f, margin, rect) {
    var sz = stageSize(), cam = new THREE.PerspectiveCamera(camera.fov, sz.w / sz.h, 1, 1e6), v = new THREE.Vector3();
    var k = sz.h / (2 * Math.tan(camera.fov * Math.PI / 360));
    var rw = (rect.x1 - rect.x0) * (1 - 2 * margin), rh = (rect.y1 - rect.y0) * (1 - 2 * margin);
    var pos = f.pos.clone(), target = f.target.clone(), back = new THREE.Vector3(), right = new THREE.Vector3(), up = new THREE.Vector3();
    for (var it = 0; it < 4; it++) {
      cam.position.copy(pos); cam.up.copy(camera.up); cam.lookAt(target); cam.updateMatrixWorld();
      var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (var i = 0; i < N; i++) {
        v.set(POS[3 * i], POS[3 * i + 1], POS[3 * i + 2]).project(cam);
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
      /* s times closer, the nodes' middle sits s times further from the canvas centre: shift it onto the rectangle's */
      var dx = ((x0 + x1) / 2 - sz.w / 2) * s - ((rect.x0 + rect.x1) / 2 - sz.w / 2);
      var dy = ((y0 + y1) / 2 - sz.h / 2) * s - ((rect.y0 + rect.y1) / 2 - sz.h / 2);
      target.addScaledVector(right, dx * d / k).addScaledVector(up, -dy * d / k);
      pos.copy(target).addScaledVector(back, d);
    }
    return { pos: pos, target: target };
  }
  /* the whole map in mapRect(): on load and on Reset view only */
  function homeView() {
    var e = G.ext, rect = mapRect();
    return fitNodes(fitBox(new THREE.Vector3(e[0], 0, e[2]), new THREE.Vector3(e[1], e[4], e[3]), DIR_ALL, 0.03, rect), 0.03, rect);
  }
  function fitAll(ms) {
    var f = homeView();
    moveCamera(f.pos, f.target, ms);
    if (ms) T.flights++;
  }
  /* the camera frames what the call-outs name: the call-out nodes and the trace's nodes in their regions; a traced
     stroke into another region (a shared law or a term defined elsewhere) leaves the frame towards it */
  /* a term shared by several areas is one node, placed in one region: for a question of another area it lies far away */
  function localTerm(t) {
    var k = t.co[4];
    return k >= 0 && (HOME[k] === HOME[t.co[0]] || HOME[k] === HOME[t.co[2]] || HOME[k] === HOME[t.co[3]]);
  }
  function framedNodes(t) {
    var homes = {}, ids = [];
    t.co.forEach(function (k, j) { if (k >= 0 && (j !== 4 || localTerm(t))) { homes[HOME[k]] = 1; ids.push(k); } });
    t.f.forEach(function (i) { if (homes[HOME[i]] && ids.indexOf(i) < 0) ids.push(i); });
    return ids;
  }
  function fitTrace(t, ms) {
    var b = boxOf(framedNodes(t)), pad = 12;
    b.lo.addScalar(-pad); b.hi.addScalar(pad);
    b.hi.y += 30;                                   // headroom above the area node for its call-out
    var f = fitBox(b.lo, b.hi, DIR_TRACE, mobile ? 0.18 : 0.16, freeRect());
    moveCamera(f.pos, f.target, ms);
    T.flights++;
  }
  function moveCamera(pos, target, ms) {
    T.cameraMoves = (T.cameraMoves || 0) + 1;
    if (!ms) {
      tween = null;
      camera.position.copy(pos); controls.target.copy(target); camera.lookAt(target); controls.update();
      needsRender = true; updateLabelSizes(); scheduleCallouts(); return;
    }
    tween = { t0: null, ms: ms, p0: camera.position.clone(), p1: pos, q0: controls.target.clone(), q1: target };
  }
  function stepTween(t) {
    if (tween.t0 == null) tween.t0 = t;
    var u = Math.min(1, (t - tween.t0) / tween.ms), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.q0, tween.q1, e);
    if (u >= 1) { tween = null; T.cameraSettled = (T.cameraSettled || 0) + 1; if (state.sel) drawFgNodes(); scheduleCallouts(); }
  }
  function orbit(dAz, dPol, zoom) {
    var off = camera.position.clone().sub(controls.target), sph = new THREE.Spherical().setFromVector3(off);
    sph.theta += dAz;
    sph.phi = Math.min(Math.PI / 2 - 0.02, Math.max(0.08, sph.phi + dPol));
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
  function makeLabel(lines, o) {
    var opt = VL.paperCallout(P, !!o.sel);
    opt.lines = lines;
    opt.px = o.px || LBL.px;
    opt.weight = '400';
    var s = VL.TextSprite(lines[0].map(function (p) { return p.text; }).join(''), opt);
    s.__id = o.id; s.__pri = o.pri || 0; s.__must = !!o.must; s.__sel = !!o.sel; s.__node = o.node;
    s.__r = (SIZE[cname(o.node)] || 6) / 2;
    s.__lines = o.linesFn || null;
    s.layers.set(1);
    s.position.set(POS[3 * o.node], POS[3 * o.node + 1], POS[3 * o.node + 2]);
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
  /* call-out text: Vietnamese · English, long names shortened (the full name is in the panel and the tooltip) */
  var LBL = mobile ? { vi: 34, en: 38, one: 24, px: 18, pxSel: 19, qvi: 36, qen: 40 } : { vi: 48, en: 52, one: 30, px: 22, pxSel: 23, qvi: 46, qen: 50 };
  /* which call-outs of a picked trace must be shown (the question always); on phones the law when it fits (the hop
     sheet's title names it), on wide screens the law too */
  var MUST = mobile ? { provision: true, law: false } : { provision: true, law: true };
  /* call-out lines in the language mode (js/paper3d.js VL.paperLines): EN–VI "Tiếng Việt · English" (on one line when
     short), EN or VI one line */
  function bi(i, prefix) {
    var n = names(i), vi = VL.short(prefix ? prefix[0] + n[0] : n[0], LBL.vi), en = n[1] ? VL.short(prefix ? prefix[1] + n[1] : n[1], LBL.en) : '';
    return VL.paperLines(vi, en, P, { oneLine: LBL.one });
  }
  /* the question: EN–VI its Vietnamese title over the English gloss (as in v1), EN the gloss, VI the title */
  function questionLines(t) {
    var q = QBY[AREAS[t.a].id + ':' + t.r];
    if (!q) return bi(t.co[0]);
    return VL.paperLines(VL.short(q.vi, LBL.qvi), VL.short(q.en || '', LBL.qen), P, { twoLines: true });
  }
  function areaLines(i) { var p = VL.kpair('tr3d.area'); return bi(i, [p.vi, p.en]); }
  /* the call-outs of the current view: the chosen trace's question, provision, law (must; on phones the law when it
     fits), term and area; with nothing chosen the 27 areas' names */
  function buildLabels() {
    if (!labelGroup) return;
    clearLabels();
    var sel = state.sel;
    if (sel) {
      var t = sel.t, co = t.co;
      // the static map: the question, its provision and its law must be named next to the trace; the term and the area
      // when there is room (the hop panel names them, and the list's heading the area)
      makeLabel(questionLines(t), { id: G.i[co[0]], node: co[0], sel: true, must: true, pri: 1000, px: LBL.pxSel });
      makeLabel(bi(co[2]), { id: G.i[co[2]], node: co[2], must: MUST.provision, pri: 900 });
      if (co[3] !== co[2]) makeLabel(bi(co[3]), { id: G.i[co[3]], node: co[3], must: MUST.law, pri: 880 });
      if (co[4] >= 0) makeLabel(bi(co[4]), { id: G.i[co[4]], node: co[4], must: false, pri: localTerm(t) ? 860 : 820 });
      makeLabel(areaLines(co[5]), { id: G.i[co[5]], node: co[5], must: false, pri: 840 });
    } else {
      // the whole map: the 27 areas' names where they fit
      for (var j = 0; j < N; j++) if (cname(j) === 'area') makeLabel(areaLines(j), { id: G.i[j], node: j, pri: 300, px: LBL.px - 1 });
    }
    T.labels = labels.length;
    M.labelsLang = VL.lang();
    scheduleCallouts();
  }
  function calloutItems() {
    return labels.map(function (s) { return { id: s.__id, sprite: s, pri: s.__pri, must: s.__must, sel: s.__sel, r: s.__r }; });
  }
  /* ink the call-outs keep clear of: the chosen trace (its foreground nodes and traced segments), else the labelled
     area nodes; the faded rest is background, as in the paper */
  function calloutInk() {
    var discs = [], paths = [], sel = state.sel;
    function disc(i) { discs.push({ id: G.i[i], x: POS[3 * i], y: POS[3 * i + 1], z: POS[3 * i + 2], r: (SIZE[cname(i)] || 6) / 2 }); }
    if (sel) {
      sel.t.f.forEach(disc);
      (sel.paths || []).forEach(function (p) { paths.push(p); });
    } else {
      labels.forEach(function (s) { disc(s.__node); });
    }
    return { discs: discs, paths: paths };
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
  function scheduleCallouts() {
    if (!camera || !labels.length) { if (camera) M.callouts = { runs: (M.callouts && M.callouts.runs) || 0, placed: [], nodes: [], shown: 0, mustHidden: 0 }; return; }
    if (!callouts) {
      callouts = VL.Callouts({
        camera: function () { return camera; },
        size: function () { return { w: host.clientWidth, h: host.clientHeight }; },
        items: calloutItems, ink: calloutInk, ui: obstacles,
        leaderColor: function () { return P.leader; },
        discMaxPx: 30 / Math.min(window.devicePixelRatio || 1, 2),
        segPad: Math.ceil(VL.TRACE_W.halo2 * FOCUS.bold / 2),   // half the bold outer halo
        metrics: M, key: 'callouts',
        onDone: function (st) { T.calloutsShown = st.shown; needsRender = true; }
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
     questions the search shows */
  function headName(a) {
    return VL.lang() === 'envi' ? '<span lang="vi">' + esc(a.label_vi) + '</span><span class="sep" aria-hidden="true"> · </span><span>' + esc(a.label_en) + '</span>'
      : VL.UH(areaPair(a));
  }
  function headCount(n) {
    return '<span class="n" aria-hidden="true">' + fmt(n) + '</span><span class="sr-only">' + esc(VL.U('tr3d.groupCount', { n: nv(n) })) + '</span>';
  }
  function itemId(q) { return 'tr-item-' + q.id + '-' + q.rank; }
  function itemHtml(q) {
    return '<li><button type="button" class="tr-item" id="' + itemId(q) + '" data-area="' + q.id + '" data-rank="' + q.rank + '">' +
      '<span class="tr-rank">' + q.rank + '</span><span class="tr-item-body"><span class="tr-law">' + esc(lawShort(q.law)) + '</span>' +
      qHtml(q, 'span', 'tr-q', 'tr-g') + verdictBadge(q) + '</span></button></li>';
  }
  var SEC = [], HEADN = [], listReady = null;
  function renderList() {
    if (!QS.length) return;
    var t0 = performance.now();
    listEl.innerHTML = AREAS.map(function (a, ai) {
      return '<section class="tr-group" id="tr-g-' + a.id + '" data-area="' + a.id + '" aria-labelledby="tr-h-' + a.id + '">' +
        '<h3 class="tr-head" id="tr-h-' + a.id + '" tabindex="-1"><span class="tr-head-name">' + headName(a) + '</span><span class="tr-head-n"></span></h3>' +
        '<ol class="tr-sub">' + GROUPS[ai].map(itemHtml).join('') + '</ol></section>';
    }).join('') + '<p class="tr-status" id="tr-none" hidden></p>';
    QS.forEach(function (q) { q.btn = document.getElementById(itemId(q)); q.li = q.btn ? q.btn.parentNode : null; });
    AREAS.forEach(function (a, ai) { SEC[ai] = document.getElementById('tr-g-' + a.id); HEADN[ai] = SEC[ai].querySelector('.tr-head-n'); });
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
    countEl.textContent = VL.U('tr3d.count', { n: fmt(shown), total: fmt(QS.length) });
    var none = document.getElementById('tr-none');
    if (none) { none.hidden = shown > 0; none.textContent = shown ? '' : VL.U('tr3d.noMatch', { q: raw.trim() }); }
  }
  var curItem = null;
  function markList(scroll) {
    if (curItem) curItem.removeAttribute('aria-current');
    curItem = null;
    var q = state.sel && state.sel.q;
    if (!q || !q.btn) return;
    q.btn.setAttribute('aria-current', 'true');
    curItem = q.btn;
    if (scroll && !q.li.hidden) { try { q.btn.scrollIntoView({ block: 'nearest' }); } catch (e) { /* old engines */ } }
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
  listEl.addEventListener('click', function (e) {
    var b = e.target.closest('.tr-item');
    if (!b) return;
    selectTrace(b.getAttribute('data-area'), +b.getAttribute('data-rank'), { user: true, scroll: false });
    if (mobile) setSide(false);
  });
  /* arrows move through the shown questions (across the headings), Home / End to the first / last, up from the first
     back to the search; Enter (the buttons') chooses */
  listEl.addEventListener('keydown', function (e) {
    var k = e.key;
    if (k !== 'ArrowDown' && k !== 'ArrowUp' && k !== 'Home' && k !== 'End') return;
    var items = visibleItems(), i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    if (k === 'ArrowUp' && i === 0 && searchEl) { searchEl.focus(); return; }
    items[k === 'Home' ? 0 : k === 'End' ? items.length - 1 : Math.max(0, Math.min(items.length - 1, i + (k === 'ArrowDown' ? 1 : -1)))].focus();
  });
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

  /* ------------------------------------------------------------------ the Fig. 5 hop panel */
  var REASON = { law_not_resolved: 'tr3d.reason.law', number_not_in_scope: 'tr3d.reason.number', article_not_parsed: 'tr3d.reason.article' };
  function primary(tr) { for (var i = 0; i < tr.paths.length; i++) if (tr.paths[i].pr) return tr.paths[i]; return tr.paths[0]; }
  function lawTitle(law) {
    var num = law.number || '', named = (law.vi || '').indexOf(num) >= 0 || (law.en || '').indexOf(num) >= 0;
    return VL.TH(VL.pair(law.vi || '', law.en || '')) + (num && !named ? ' · <span class="num">' + esc(num) + '</span>' : '');
  }
  function pathLabel(tr, p) {
    var N_ = tr.nodes, prov = N_[p.n.length > 3 ? p.n[2] : p.n[p.n.length - 1]], work = N_[p.n[p.n.length - 1]];
    if (p.u === 'work') return VL.TH(VL.pair(work.vi, work.en)) + ' ' + VL.UH('tr3d.citedWhole');
    return VL.TH(VL.pair(prov.vi, prov.en)) + ' ' + VL.UH('tr3d.of') + ' ' + VL.UH(VL.pair(work.vi, work.en));
  }
  /* a hop of the Fig. 5 panel: EN–VI \"1 Question Câu hỏi · extra\" as in v1, EN or VI \"1 Question  extra\" in one language */
  function hop(cls, n, key, extra, body) {
    var e = VL.kpair(key), head;
    if (VL.lang() === 'envi') head = '<b>' + n + ' ' + esc(e.en) + '</b> <span lang="vi">' + esc(e.vi) + '</span>' + (extra ? ' · ' + extra : '');
    else head = '<b>' + n + ' ' + VL.UH(key) + '</b>' + (extra ? ' <span>' + extra + '</span>' : '');
    return '<section class="hop hop-' + cls + '"><h3>' + head + '</h3>' + body + '</section>';
  }
  /* a sentence pair (notes, the hop arrows) in EN–VI as v1 wrote it: the English, then the Vietnamese (lang="vi");
     EN or VI: one language */
  function enFirst(key, vars, sep) {
    var t = VL.TL(key, vars);
    if (VL.lang() !== 'envi' || !t.secondary) return VL.UH(key, vars);
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
  function tracePanelHtml(a, tr) {
    return closeHtml() +
      '<p class="tf-area">#' + tr.rank + ' · ' + VL.TH(areaPair(a)) + '</p>' +
      '<h2 id="tp-title">' + lawTitle(tr.law) + '</h2>' +
      qHtml(tr.qa, 'p', 'tf-q', 'tf-g') +
      '<p class="tf-links">' + verdictBadge(tr) + ' · ' + VL.UH('tr3d.answersIn', { n: fmt(tr.article.n), area: VL.U(areaPair(a)), article: VL.U(VL.pair(tr.article.vi || '', tr.article.en || '')),
        na: fmt(tr.article.na) }) + ' · <a href="#area=' + a.id + '&amp;q=' + tr.rank + '">' + VL.UH('tr3d.linkTrace') + '</a></p>' + hopsHtml(tr);
  }
  var panelNode = -1;   // the node whose details the panel shows (-1: the selected trace or nothing)
  function openPanel(html, keepScroll) {
    var st = panel.scrollTop;
    panel.innerHTML = html;
    panel.classList.remove('hidden');
    stage.classList.add('panel-open');
    panel.scrollTop = keepScroll ? st : 0;
    T.hops = VL.$$('.hop', panel).length;
    requestAnimationFrame(function () { onResize(); });
  }
  function closePanel() {
    if (panel.classList.contains('hidden')) return;
    panel.classList.add('hidden');
    stage.classList.remove('panel-open');
    T.hops = 0;
    panelNode = -1;
    requestAnimationFrame(function () { onResize(); });
  }
  panel.addEventListener('click', function (e) {
    if (e.target.closest('[data-close]')) { clearSelection(true); closePanel(); return; }
    var b = e.target.closest('[data-trace]');
    if (b) { var x = b.getAttribute('data-trace').split(':'); selectTrace(x[0], +x[1], { user: true }); }
  });

  /* ------------------------------------------------------------------ node details (hover, click) */
  /* the node's name: EN–VI the Vietnamese name over the English one (v1), EN or VI one language */
  function nameHtml(n) {
    if (VL.lang() === 'envi') return '<h2 lang="vi">' + esc(n[0]) + '</h2><p class="vi">' + esc(n[1]) + '</p>';
    return '<h2>' + VL.UH(VL.pair(n[0], n[1])) + '</h2>';
  }
  function nodeHtml(i) {
    var n = names(i), c = cname(i), cn = classNames(c), ts = tracesOf(i), a = AREAS[HOME[i]];
    var url = G.u[String(i)];
    var rows = '<dt>' + VL.UH('tr3d.k.id') + '</dt><dd class="iri">' + esc(G.i[i]) + '</dd><dt>' + VL.UH('tr3d.k.region') + '</dt><dd>' + VL.TH(areaPair(a)) + '</dd>' +
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
  var raycaster = null, ndc = null;
  function pick(cx, cy) {
    if (!pointsObj) return -1;
    if (!raycaster) { raycaster = new THREE.Raycaster(); ndc = new THREE.Vector2(); }
    var r = renderer.domElement.getBoundingClientRect();
    ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    var dist = camera.position.distanceTo(controls.target);
    raycaster.params.Points.threshold = Math.max(2, dist * worldPerPx() * 6);
    raycaster.setFromCamera(ndc, camera);
    var hits = raycaster.intersectObject(pointsObj, false), best = -1, bestScore = Infinity;
    hits.forEach(function (h) {
      var i = h.index;
      if (!ALPHA || ALPHA[i] < 0.05) return;
      var score = h.distanceToRay / (1 + (ALPHA[i] > 0.5 ? 1 : 0)) / (0.6 + (SIZE[cname(i)] || 6) / 12) + h.distance * 1e-4;
      if (score < bestScore) { bestScore = score; best = i; }
    });
    return best;
  }
  function clickNode(i) {
    var c = cname(i);
    if (c === 'question' || c === 'answer') {
      var ts = tracesOf(i).map(function (k) { return G.t[k]; }).filter(function (t) { return t.co[0] === i || t.co[1] === i; });
      var t = ts.filter(function (x) { return x.co[0] === i; })[0] || ts[0];     // a question node chooses its question
      if (t) { selectTrace(AREAS[t.a].id, t.r, { user: true }); return; }
    }
    T.clicked = G.i[i];
    openPanel(nodeHtml(i));
    panelNode = i;
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
      var i = pick(e.clientX, e.clientY);
      if (i >= 0) clickNode(i);
    });
    cv.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch' || down) { tip.classList.add('hidden'); return; }
      if (hoverRaf) return;
      var x = e.clientX, y = e.clientY;
      hoverRaf = requestAnimationFrame(function () {
        hoverRaf = 0;
        var i = pick(x, y);
        cv.style.cursor = i >= 0 ? 'pointer' : '';
        T.hover = i >= 0 ? G.i[i] : null;
        if (i < 0) { tip.classList.add('hidden'); return; }
        var n = names(i), cn = classNames(cname(i)), k = tracesOf(i).length, lim = QNODE[i] ? 140 : 60;
        tip.innerHTML = '<b>' + VL.TH(VL.pair(VL.short(n[0], lim), VL.short(n[1], lim))) + '</b>' +
          '<div class="t-sub">' + VL.TH(VL.pair(cn[0], cn[1])) + ' · ' + VL.UH('tr3d.tipTraces', { n: nv(k) }) + '</div>';
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

  /* ------------------------------------------------------------------ selection */
  var seq = 0;
  function setHash(h) {
    if (location.hash === h) return;
    try { history.replaceState(history.state, '', h); } catch (e) { location.hash = h; }
  }
  function clearHash() {
    if (!location.hash) return;
    try { history.replaceState(history.state, '', location.pathname + location.search); } catch (e) { location.hash = ''; }
  }
  /* the chosen question's area on the phones' toolbar */
  function areaLabelM() {
    var m = VL.$('#tr-area-m');
    if (m) m.innerHTML = state.sel ? VL.UH(areaPair(AREAS[state.sel.t.a])) : '';
  }
  /* choose a question: its trace solid and bold, the focus volume, call-outs, the hop panel (the area file is loaded for
     the panel); the camera stays where it is ('Zoom to selection' flies in) */
  function selectTrace(areaId, rank, opts) {
    opts = opts || {};
    var a = BY[areaId], t = a ? TRK[AIX[a.id] + ':' + rank] : null;
    if (!t) return Promise.resolve(null);
    var my = ++seq;
    if (!AD[a.id]) openPanel(closeHtml() + '<p class="tr-status">' + VL.TH('tr3d.loading') + '</p>');   // the area's file first
    return loadArea(a).then(function () {
      if (my !== seq) return null;                 // a later choice won, or the panel was closed meanwhile
      var tr = AD[a.id][rank];
      state.sel = { t: t, tr: tr, q: QBY[a.id + ':' + rank] || null };
      if (opts.user) setHash('#q=' + a.id + ':' + rank);
      markList(opts.scroll !== false);
      openPanel(tracePanelHtml(a, tr));
      panelNode = -1;
      var co = t.co;
      T.selected = { area: a.id, rank: rank, q: G.i[co[0]], answer: G.i[co[1]], provision: G.i[co[2]], law: G.i[co[3]],
        term: co[4] >= 0 ? G.i[co[4]] : null, areaNode: G.i[co[5]], fg: t.f.length, nodes: t.n.length, segments: t.e.length / 3 };
      areaLabelM();
      if (T.fallback) { drawFallback(a, tr); return t; }
      applyFocus();
      drawTrace();
      buildLabels();
      return t;
    }, function (err) {
      T.errors.push(String(err && err.message || err));
      if (my === seq) openPanel(closeHtml() + '<p class="tr-status">' + VL.UH('tr3d.areaError', { file: a.file }) + '</p>');
      return null;
    });
  }
  var TRACE_SEG = 16;      // the traced ribbon: the links' curve, finely sampled
  /* the paper's trace widths scaled by FOCUS.bold: the picked trace stands out from the faded graph */
  function boldStyle(w) {
    var st = VL.traceStyle(P, w);
    Object.keys(st.widths).forEach(function (k) { st.widths[k] *= FOCUS.bold; });
    return st;
  }
  function drawTrace() {
    var sel = state.sel, v = [], s = [];
    if (sel) {
      var e = sel.t.e;
      for (var j = 0; j < e.length; j += 3) (e[j + 2] === 1 ? v : s).push(curvePts(ptOf(e[j]), ptOf(e[j + 1]), TRACE_SEG));
      sel.paths = v.concat(s);
    }
    traceV.setStyle(boldStyle(1));
    traceS.setStyle(boldStyle(0.55));
    traceS.setStyle({ opacity: P.dark ? 0.6 : 0.62 });
    traceV.setPaths(v);
    traceS.setPaths(s);
    drawFgNodes();
    T.traceSegments = traceV.count() + traceS.count();
    T.traceVerified = traceV.count();
    T.traceStructural = traceS.count();
    needsRender = true;
  }
  /* the trace's nodes over its strokes: a small Points object (same shader and uniforms as the graph), far ones first */
  function drawFgNodes() {
    if (fgObj) { scene.remove(fgObj); fgObj.geometry.dispose(); fgObj = null; }
    var sel = state.sel;
    if (!sel || !pointsObj) return;
    var cp = camera.position, d2 = function (i) {
      var dx = POS[3 * i] - cp.x, dy = POS[3 * i + 1] - cp.y, dz = POS[3 * i + 2] - cp.z; return dx * dx + dy * dy + dz * dz;
    };
    var ids = sel.t.f.slice().sort(function (a, b) { return d2(b) - d2(a); }), n = ids.length;
    var src = pointsObj.geometry.attributes, pos = new Float32Array(3 * n), col = new Float32Array(3 * n), sz = new Float32Array(n), al = new Float32Array(n);
    ids.forEach(function (i, j) {
      for (var c = 0; c < 3; c++) { pos[3 * j + c] = POS[3 * i + c]; col[3 * j + c] = src.aColor.array[3 * i + c]; }
      sz[j] = src.aSize.array[i] * FOCUS.fgSize;
      al[j] = 1;
    });
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(al, 1));
    g.setAttribute('aDist', new THREE.BufferAttribute(new Float32Array(n), 1));     // on the trace: d = 0, solid
    // transparent (alpha 1): drawn in three.js' transparent pass after the trace's strokes (renderOrder 7 / 10), so the
    // nodes lie over the strokes as in the paper's figures (an opaque material would be drawn before every transparent one)
    if (!fgMat) fgMat = new THREE.ShaderMaterial({ uniforms: pointsMat.uniforms, vertexShader: PT_VS, fragmentShader: PT_FS, depthTest: false, depthWrite: false,
      transparent: true });
    fgObj = new THREE.Points(g, fgMat);
    fgObj.renderOrder = 20;
    fgObj.frustumCulled = false;
    scene.add(fgObj);
    T.fgDrawn = n;
  }
  function clearSelection(user) {
    seq++;                                         // also drops a choice whose area file is still loading
    if (!state.sel) return;
    state.sel = null;
    T.selected = null;
    markList(false);
    if (user) clearHash();
    areaLabelM();
    if (T.fallback) { fbEl.innerHTML = ''; fbEl.classList.add('hidden'); return; }
    applyFocus();
    drawTrace();
    buildLabels();
  }

  /* ------------------------------------------------------------------ no WebGL: the selected trace in 2D */
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
     navy core over the gold halo; ' s' = structural (fainter, thinner core) */
  function curveSwatch(mod) {
    var d = 'M2 10 C2 6.4 20 5.6 20 2';
    return '<svg class="tr-sw' + mod + '" viewBox="0 0 22 12" aria-hidden="true"><path class="halo" d="' + d + '"/><path class="core" d="' + d + '"/></svg>';
  }
  /* the flat legend: "Tiếng Việt · English" entries in EN–VI, one language in EN or VI */
  function renderLegend() {
    var SEP = { sep: '\u00a0· ' };
    function li(color, pair, small) {
      return '<li><span class="swatch' + (small ? ' small' : '') + '" style="background:' + color + '"></span>' + VL.TH(pair, null, SEP) + '</li>';
    }
    var items = VL.PAPER_CLASSES.filter(function (c) { return c.key !== 'intent'; }).map(function (c) { return li(c.v, VL.pair(c.vi, c.en)); });
    items.push(li('var(--cls-question)', VL.kpair('tr3d.lg.other'), true));
    legendEl.innerHTML = '<h3>' + VL.TH('tr3d.lg.title') + '</h3><ul>' + items.join('') +
      '<li>' + curveSwatch('') + VL.TH('tr3d.lg.traced', null, SEP) + '</li>' +
      '<li>' + curveSwatch(' s') + VL.TH('tr3d.lg.structural', null, SEP) + '</li></ul>' +
      '<p class="lg-note">' + enFirst('tr3d.lg.note') + '</p>';
    legendEl.classList.toggle('hidden', !state.legendOpen);
    VL.$('#btn-legend').setAttribute('aria-expanded', state.legendOpen ? 'true' : 'false');
    T.legendEntries = VL.$$('li', legendEl).length;
  }
  VL.$('#btn-legend').innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>';
  VL.$('#btn-reset').innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>';
  VL.$('#btn-legend').addEventListener('click', function () { state.legendOpen = !state.legendOpen; renderLegend(); scheduleCallouts(); });
  function resetView() {
    clearSelection(true);
    closePanel();
    if (camera) fitAll(800);
  }
  /* the map never moves by itself (choosing, searching and the list only change the drawing); this flies to the chosen
     trace, or shows the whole map when nothing is chosen */
  function zoomToSelection() {
    if (!camera) return;
    if (state.sel) fitTrace(state.sel.t, 800);
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
  VL.$('#btn-list-m').addEventListener('click', function () { setSide(!app.classList.contains('side-open')); });
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
    if (state.sel) { clearSelection(true); closePanel(); return; }
    if (!panel.classList.contains('hidden')) { seq++; closePanel(); }
  });
  function showHint() { if (VL.store.get('hint-traces3d') !== 'off') { VL.$('#hint').classList.remove('hidden'); scheduleCallouts(); } }
  function hideHint() { var h = VL.$('#hint'); if (h && !h.classList.contains('hidden')) { h.classList.add('hidden'); scheduleCallouts(); } }
  VL.$('#hint-close').addEventListener('click', function () { hideHint(); VL.store.set('hint-traces3d', 'off'); });
  function status() {
    if (!G) return;
    statusEl.textContent = VL.U('tr3d.status', { nodes: fmt(N), links: fmt(T.graph.links), traces: fmt(G.t.length) }) + (T.fps ? ' · ' + fmt(T.fps) + ' fps' : '');
  }
  function applyTheme() {
    readTheme();
    renderLegend();
    if (renderer) {
      renderer.setClearColor(TH.bg, 1);
      applyColors();
      drawTrace();
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
     status, the 2D fallback and the call-outs are rendered again in the new mode, then placed again; the chosen trace
     and the camera stay */
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
      if (state.sel && panelNode < 0) openPanel(tracePanelHtml(BY[AREAS[state.sel.t.a].id], state.sel.tr), true);
      else if (panelNode >= 0) { var pn = panelNode; openPanel(nodeHtml(pn), true); panelNode = pn; }
    }
    renderLegend();
    status();
    tip.classList.add('hidden');
    if (T.fallback) { if (state.sel) drawFallback(BY[AREAS[state.sel.t.a].id], state.sel.tr); else M.labelsLang = VL.lang(); }
    else if (labelGroup) buildLabels();
    else M.labelsLang = VL.lang();
  }
  document.addEventListener('vl:lang', applyLang);

  /* ------------------------------------------------------------------ routing: #q=<area>:<rank> chooses a question (v1's
     #area=<id>&q=<rank> too); #area=<id> alone scrolls the list to the area's heading and chooses nothing */
  function route() {
    var h = VL.params(), area = null, rank = null;
    if (h.q && String(h.q).indexOf(':') > 0) { var p = String(h.q).split(':'); area = p[0]; rank = parseInt(p[1], 10); }
    else if (h.area) { area = h.area; rank = h.q ? parseInt(h.q, 10) : null; }
    var a = BY[area];
    if (a && rank && TRK[AIX[a.id] + ':' + rank]) {
      if (state.sel && state.sel.t.a === AIX[a.id] && state.sel.t.r === rank) return Promise.resolve(null);
      return selectTrace(a.id, rank, {});
    }
    if (state.sel) { clearSelection(false); closePanel(); }
    return a ? scrollToArea(a.id, { open: true }) : Promise.resolve(null);
  }
  window.addEventListener('hashchange', route);
  window.VLApp = window.VLApp || {};
  window.VLApp.traces = {
    area: function (id) { return scrollToArea(id, { open: true }); },     // the list at the area's heading (chooses nothing)
    select: function (id, rank) { return selectTrace(id, rank, { user: true }); },
    search: function (q) { if (searchEl) { searchEl.value = q; applySearch(); } return T.shown; },
    question: function (id, rank) { var q = QBY[id + ':' + rank]; return q ? { vi: q.vi, en: q.en, law: q.law, node: q.t ? G.i[q.t.co[0]] : null } : null; },
    /* the focus volume at a node: its distance to the chosen trace and the opacity the transfer function gives it */
    focusAt: function (id) { var i = G ? G.i.indexOf(id) : -1; return i < 0 || !ALPHA ? null : { d: DIST ? DIST[i] : 0, alpha: ALPHA[i], focus: FOCUS_U.uFocus.value, sigma: SIGMA, rest: FOCUS.rest }; },
    clear: function () { clearSelection(true); closePanel(); },
    areas: function () { return AREAS.map(function (a) { return a.id; }); },
    pick: function (x, y) { var i = pick(x, y); return i >= 0 ? G.i[i] : null; },
    project: function (id) {                       // screen position (CSS px in the canvas) of a node, for tests
      var i = G.i.indexOf(id);
      if (i < 0 || !camera) return null;
      var v = new THREE.Vector3(POS[3 * i], POS[3 * i + 1], POS[3 * i + 2]).project(camera);
      return { x: (v.x + 1) / 2 * host.clientWidth, y: (1 - v.y) / 2 * host.clientHeight, inside: Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1 && v.z < 1 };
    },
    settle: function () { return !tween && !fade && !(callouts && callouts.last === null); },
    /* the camera (position, target) and the rectangles the views are framed in; Zoom to selection and Reset view */
    camera: function () { return camera ? { pos: camera.position.toArray(), target: controls.target.toArray() } : null; },
    view: function () { return camera ? { map: mapRect(), free: freeRect(), home: (function (f) { return { pos: f.pos.toArray(), target: f.target.toArray() }; })(homeView()) } : null; },
    zoom: function () { zoomToSelection(); },
    reset: function () { resetView(); },
    /* the current view as data (camera, the colours / alphas / sizes the shaders get, the call-outs placed), for tests and
       offline previews of the page without a GPU; read-only */
    snapshot: function () {
      if (!camera) return null;
      var pa = pointsObj.geometry.attributes, lines = [];
      for (var e = 0; e < EDGE.s.length; e++) {
        var L = lineGroups[EDGE.g[e]], j = EDGE.j[e], fv = FOCUS_U.uFocus.value;
        var a0 = L.alpha.array[j] * (1 + (transfer(L.da.array[j]) - 1) * fv), a1 = L.alpha.array[j] * (1 + (transfer(L.db.array[j]) - 1) * fv), al = Math.max(a0, a1);
        if (al > 0.01) lines.push([EDGE.s[e], EDGE.t[e], Math.round(a0 * 1000) / 1000, Math.round(a1 * 1000) / 1000,
          Math.round(L.color.array[3 * j] * 255), Math.round(L.color.array[3 * j + 1] * 255), Math.round(L.color.array[3 * j + 2] * 255), L.seg]);
      }
      var r3 = function (v) { return Math.round(v * 1000) / 1000; };
      return {
        w: host.clientWidth, h: host.clientHeight, fov: camera.fov, near: camera.near,
        pos: camera.position.toArray().map(r3), target: controls.target.toArray().map(r3), up: camera.up.toArray(),
        color: Array.prototype.map.call(pa.aColor.array, function (v) { return Math.round(v * 255); }),
        alpha: Array.prototype.map.call(ALPHA, r3), dist: Array.prototype.map.call(pa.aDist.array, function (v) { return Math.round(v * 10) / 10; }),
        size: Array.prototype.slice.call(pa.aSize.array),
        lines: lines, lineOpacity: linesMat.uniforms.uOpacity.value, curve: { curves: CURVES, bend: CV.bend, gap: CV.gap, liftMax: CV.liftMax, traceSeg: TRACE_SEG },
        bg: TH.bg, rim: pointsMat.uniforms.uRim.value,
        fog: [FOG.value.x, FOG.value.y, FOG.value.z], dark: !!TH.dark,
        paper: { core: P.core, halo: P.halo, halo2: P.halo2, calloutBg: P.calloutBg, calloutLine: P.calloutLine, selBg: P.selBg,
          selLine: P.selLine, ink: P.ink, ink2: P.ink2, leader: P.leader },
        traceStyle: { v: boldStyle(1), s: boldStyle(0.55), sOpacity: P.dark ? 0.6 : 0.62 }, focus: FOCUS,
        focusVolume: { value: FOCUS_U.uFocus.value, sigma: SIGMA, cell: CELL, rest: FOCUS.rest, tint: pointsMat.uniforms.uTint.value, splat: FOCUS.splat },
        labels: labels.map(function (s) { return { id: s.__id, sel: !!s.__sel, must: !!s.__must, px: s.__px, lines: s.__opts.lines }; }),
        callouts: M.callouts || null, free: freeRect(), selected: T.selected
      };
    }
  };

  /* ------------------------------------------------------------------ start */
  renderLegend();
  var t0 = performance.now();
  listReady = loadQuestions().then(function (d) { prepareQuestions(d); renderList(); return d; });
  VL.fontsReady().then(function () {
    return Promise.all([loadGraph(), listReady]);
  }).then(function (r) {
    prepare(r[0]);
    linkQuestionNodes();
    T.webgl = webglOk();
    if (T.webgl) {
      try { initThree(); } catch (e) { T.webgl = false; T.webglError = String(e && e.message || e); renderer = null; }
    }
    if (!T.webgl) {
      T.fallback = true;
      stage.classList.add('tr-no-webgl');
      if (TD) { var d = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); d.setAttribute('class', 'tr-defs'); d.setAttribute('width', '0'); d.setAttribute('height', '0'); d.setAttribute('aria-hidden', 'true'); d.innerHTML = TD.defs(); document.body.appendChild(d); }
    } else {
      buildScene();
      bindPointer();
      showHint();          // first visit: the hint is part of the frame the whole map is placed in
      fitAll(0);
      buildLabels();       // nothing chosen: the 27 areas' names
    }
    T.buildMs = Math.round(performance.now() - t0);
    status();
    return route();
  }).then(function () {
    hideVeil();
    return new Promise(function (res) { requestAnimationFrame(function () { requestAnimationFrame(res); }); });
  }).then(function () {
    return T.fallback ? null : measureFps(700);
  }).then(function (fps) {
    if (fps != null) T.fps = fps;
    status();
    VL.setReady({ tracesQuestions: QS.length, webglRenderer: M.webglRenderer, fps: T.fps });
  }).catch(function (e) {
    console.error(e);
    T.errors.push(String(e && e.message || e));
    var v = VL.$('#veil-text');
    if (v) v.textContent = VL.U('tr3d.loadError', { msg: e && e.message });
    VL.setReady({ tracesError: String(e && e.message || e) });
  });
})();

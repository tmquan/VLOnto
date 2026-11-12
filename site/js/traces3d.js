/* VLOnto - question traces in 3D (traces.html): ONE interactive WebGL scene with all traced answers of the 27 legal
   areas (data/traces/graph.js, built by scripts/site/trace_global.py): laws, chapters, sections, articles, clauses and
   points, questions, answers, terms and areas, every node once, the areas as regions of the floor in the order of the
   tabs, each laid out like the paper's Fig. 1 (arXiv:2611.11426).
   - an area tab flies the camera to its region and lists its 20 traced questions (titles and hop data from
     data/traces/<area>.js, loaded when the area is first opened; no fetch, file:// works);
   - picking a question lights its trace inside the whole graph (navy core over the gold halo, js/paper3d.js
     VL.TraceLines; the V/W arms with the term -> defining clause hop), fades the rest, fits the camera to the trace,
     places bilingual call-outs with VL.Callouts (question, provision, law, term, area; never over ink or each other)
     and shows the Fig. 5 hop panel;
   - rotate, zoom and pan (OrbitControls), hover and click any node for its details, deep links #area=<id>&q=<rank>,
     keyboard (tabs, list, arrows and +/- on the canvas, Esc), reset view, flat legend;
   - phones: the question list and the hop panel are bottom sheets and only the open area's region is drawn (lighter);
   - without WebGL the page keeps the tabs, the list and the hop panel and draws the selected trace in 2D
     (js/trace-draw.js, the build-time drawing in the area file).
   Points and lines follow js/network3d.js (custom point shader with soft pastel spheres, LineSegments, depth fade,
   render on demand); paper3d.js, labels3d.js and common.js are used as they are.
   window.__VLONTO_METRICS.traces and .callouts, and window.VLApp.traces, serve the interaction tests. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS, TD = VL.TraceDraw;
  VL.chrome({ scene: true });
  M.page = 'traces';
  M.paperStyle = true;
  var IDX = window.VLONTO.traces_index;
  var T = M.traces = { available: false, tabs: 0, area: null, loaded: [], selected: null, traceSegments: 0, hops: 0, listItems: 0,
    renders: 0, frames: 0, errors: [], webgl: null, fallback: false, flights: 0, themeRenders: 0 };
  var esc = VL.esc, fmt = VL.fmt;
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host'), panel = VL.$('#panel'), tip = VL.$('#tip');
  var legendEl = VL.$('#legend'), statusEl = VL.$('#status'), tabsEl = VL.$('#tr-tabs'), listEl = VL.$('#tr-list');
  var fbEl = VL.$('#tr-fallback'), veil = VL.$('#veil');
  var EXT = VL.ICON.external;
  function f2(x) { return x == null ? '–' : Number(x).toFixed(2); }
  /* a link that opens in a new tab; the note for screen readers sits one level inside the visually hidden span, so it
     is clipped by its 1 px parent for every measuring tool too */
  function ext(href, text, sr) {
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + text + EXT + '<span class="sr-only"><span> (' +
      esc(sr || 'opens in a new tab') + ')</span></span></a>';
  }
  function hideVeil() { if (veil) veil.classList.add('hidden'); }

  if (!IDX || !IDX.available || !IDX.areas || !IDX.areas.length) {
    VL.$('#tr-nodata').hidden = false;
    tabsEl.hidden = true;
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
  T.tabs = AREAS.length;

  (function revisions() {
    var r = IDX.source_revisions || {};
    var revs = Object.keys(r).map(function (k) { return esc(k.replace('tmquan/', '')) + ' @' + esc(String(r[k]).slice(0, 10)); }).join(', ');
    VL.$('#tr-revs').innerHTML = 'Data: question traces of ' + esc(VL.releaseLabel()) + ', built ' + esc(IDX.generated || '') +
      ' from the Hugging Face datasets ' + revs + '. <span class="vi" lang="vi">Dữ liệu: truy vết câu hỏi của ' + esc(VL.releaseLabel()) +
      ', tạo ngày ' + esc(IDX.generated || '') + '.</span>';
  })();

  /* ------------------------------------------------------------------ theme */
  var P = {}, TH = {};
  function readTheme() {
    P = VL.paperTheme();
    TH = { dark: P.dark, bg: P.bg };
    M.sceneBg = P.bg;
    M.traceCore = P.core;
  }
  readTheme();

  /* ------------------------------------------------------------------ tabs */
  tabsEl.innerHTML = AREAS.map(function (a) {
    return '<button type="button" role="tab" id="tr-tab-' + a.id + '" aria-controls="tr-panel" aria-selected="false" tabindex="-1" data-area="' + a.id + '"' +
      ' aria-label="' + esc(a.label_vi + ' · ' + a.label_en + ', ' + fmt(a.n_qas) + ' Q&As') + '">' +
      '<span lang="vi">' + esc(a.label_vi) + '</span><span class="sep" aria-hidden="true">·</span><span>' + esc(a.label_en) + '</span>' +
      '<span class="n">' + fmt(a.n_qas) + '</span></button>';
  }).join('');
  var TABS = VL.$$('[role="tab"]', tabsEl);
  tabsEl.addEventListener('click', function (e) {
    var b = e.target.closest('[role="tab"]');
    if (b) openArea(b.getAttribute('data-area'), { user: true, fly: true });
  });
  tabsEl.addEventListener('keydown', function (e) {
    var i = TABS.indexOf(document.activeElement);
    if (i < 0) return;
    var j = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: TABS.length - 1 }[e.key];
    if (j == null) return;
    e.preventDefault();
    j = (j + TABS.length) % TABS.length;
    openArea(TABS[j].getAttribute('data-area'), { focusTab: true, user: true, fly: true });
  });

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
  /* bilingual name of a node: questions, answers and other answers by id (their titles are not in the graph) */
  function names(i) {
    var c = cname(i);
    if (c === 'question') return ['Câu hỏi #' + num(i), 'Question #' + num(i)];
    if (c === 'answer') return ['Trả lời #' + num(i), 'Answer #' + num(i)];
    if (c === 'other_question') return ['Câu hỏi khác #' + num(i), 'Other question #' + num(i)];
    return [G.vi[i] || G.i[i], G.en[i] || G.vi[i] || G.i[i]];
  }
  function classNames(c) {
    if (c === 'other_question') return ['Câu hỏi khác', 'Other question'];
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
  var PT_VS = [
    'attribute vec3 aColor; attribute float aAlpha; attribute float aSize;',
    'uniform float uScale; varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    'void main() {',
    '  vColor = aColor; vAlpha = aAlpha;',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  vDepth = -mv.z;',
    '  float s = aSize * uScale / max(1.0, -mv.z);',
    '  gl_PointSize = aAlpha < 0.01 ? 0.0 : clamp(s, 1.5, 64.0);',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  var PT_FS = [
    'uniform vec3 uBg; uniform vec3 uFog; uniform float uRim; varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    'void main() {',
    '  vec2 c = gl_PointCoord - vec2(0.5); float r = length(c) * 2.0;',
    '  if (r > 1.0 || vAlpha < 0.01) discard;',
    '  vec3 n = vec3(c.x * 2.0, -c.y * 2.0, sqrt(max(0.0, 1.0 - r * r)));',
    '  vec3 col = vColor * (0.86 + 0.2 * dot(n, vec3(-0.45, 0.55, 0.70)));',
    '  col = mix(col, vColor * uRim, smoothstep(0.76, 0.96, r));',
    '  float f = clamp((vDepth - uFog.x) / max(1.0, uFog.y - uFog.x), 0.0, 1.0) * uFog.z;',
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
    'attribute float aT; attribute vec3 aA; attribute vec3 aB; attribute vec3 aColor; attribute float aAlpha;',
    'uniform float uBend; uniform float uLiftMax; uniform float uLayer;',
    'varying vec3 vColor; varying float vAlpha; varying float vDepth;',
    'void main() {',
    '  vColor = aColor; vAlpha = aAlpha;',
    '  if (aAlpha < 0.01) { vDepth = 0.0; gl_Position = vec4(0.0, 0.0, 2.0, 1.0); return; }',
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

  var renderer = null, scene, camera, controls, pointsObj = null, pointsMat = null, linesMat = null, lineGroups = [];
  var traceV = null, traceS = null, labelGroup = null, labels = [], callouts = null, needsRender = true, tween = null;
  var fgObj = null, fgMat = null;   // the selected trace's own nodes, drawn again over its strokes (as in the paper's figures)
  var EDGE = null;            // {s, t: Int32Array, k: Uint8Array (kind index), base: Float32Array, g, j: group and instance}
  var mobile = VL.isMobile();
  var state = { area: null, sel: null, legendOpen: !mobile };

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
    var d = camera.position.distanceTo(controls.target), R = Math.max(300, viewRadius);
    FOG.value.set(Math.max(1, d - 0.4 * R), d + 2.2 * R, TH.dark ? 0.5 : 0.55);
  }
  var viewRadius = 1000;
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
    g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(N), 1));
    var size = new Float32Array(N);
    for (var i = 0; i < N; i++) size[i] = SIZE[cname(i)] || 6;
    g.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
    g.computeBoundingSphere();
    pointsMat = new THREE.ShaderMaterial({
      uniforms: { uScale: { value: 1 }, uBg: { value: VL.rawColor(TH.bg, new THREE.Color()) }, uFog: FOG, uRim: { value: TH.dark ? 0.7 : 0.84 } },
      vertexShader: PT_VS, fragmentShader: PT_FS, transparent: false, depthWrite: true
    });
    pointsObj = new THREE.Points(g, pointsMat);
    pointsObj.renderOrder = 2;
    scene.add(pointsObj);
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
      uniforms: { uOpacity: { value: 0.5 }, uFog: FOG, uBend: { value: CV.bend }, uLiftMax: { value: CV.liftMax }, uLayer: { value: CV.gap } },
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
      geo.instanceCount = n;
      var obj = new THREE.LineSegments(geo, linesMat);
      obj.frustumCulled = false;
      obj.renderOrder = 1;
      scene.add(obj);
      return { obj: obj, seg: S, n: n, color: geo.attributes.aColor, alpha: geo.attributes.aAlpha };
    });
    T.edgeCost = { curves: CURVES, links: m, vertices: lineGroups.reduce(function (s2, L) { return s2 + L.n * (L.seg + 1); }, 0),
      segments: lineGroups.reduce(function (s2, L) { return s2 + L.n * L.seg; }, 0), groups: lineGroups.map(function (L) { return [L.n, L.seg]; }) };
    applyColors();
    applyAlpha();
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
    needsRender = true;
  }
  /* node alpha: the selected trace (foreground 1, its other nodes 0.55), the rest faded; on phones only the open area's
     region is drawn (and the selected trace wherever it reaches) */
  var ALPHA = null;
  function applyAlpha() {
    if (!pointsObj) return;
    var a = pointsObj.geometry.attributes.aAlpha.array, sel = state.sel, ai = state.area != null ? AIX[state.area] : -1;
    var fg = sel ? sel.fgSet : null, tn = sel ? sel.nSet : null;
    for (var i = 0; i < N; i++) {
      var v = 1;
      if (sel) v = fg[i] ? 1 : (tn[i] ? 0.55 : 0.12);
      if (mobile && ai >= 0 && HOME[i] !== ai && !(sel && tn[i])) v = 0;
      a[i] = v;
    }
    ALPHA = a;
    pointsObj.geometry.attributes.aAlpha.needsUpdate = true;
    var shown = 0;
    for (var e = 0; e < EDGE.s.length; e++) {
      var s = EDGE.s[e], t = EDGE.t[e], v2 = Math.min(a[s], a[t]) * EDGE.base[e];
      if (sel) v2 *= (fg[s] && fg[t]) ? 1 : 0.6;
      lineGroups[EDGE.g[e]].alpha.array[EDGE.j[e]] = v2;
      if (v2 > 0.01) shown++;
    }
    lineGroups.forEach(function (L) { L.alpha.needsUpdate = true; });
    T.linksShown = shown;
    needsRender = true;
  }

  /* ------------------------------------------------------------------ camera */
  var DIR_AREA = new THREE.Vector3(0.25, 0.62, 1).normalize(), DIR_ALL = new THREE.Vector3(0, 0.78, 1).normalize();
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
  function fitAll(ms) {
    var e = G.ext, f = fitBox(new THREE.Vector3(e[0], 0, e[2]), new THREE.Vector3(e[1], e[4], e[3]), DIR_ALL, 0.03);
    moveCamera(f.pos, f.target, ms);
  }
  function areaBox(ai) {
    var a = G.areas[ai], r = a.r;
    return { lo: new THREE.Vector3(a.c[0] - r, 0, a.c[1] - r), hi: new THREE.Vector3(a.c[0] + r, G.H * 1.25, a.c[1] + r) };
  }
  function flyToArea(ai, ms) {
    var b = areaBox(ai), f = fitBox(b.lo, b.hi, DIR_AREA, mobile ? 0.02 : 0.05);
    moveCamera(f.pos, f.target, ms);
    T.flights++;
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
  function bi(i, prefix) {
    var n = names(i), vi = VL.short(prefix ? prefix[0] + n[0] : n[0], LBL.vi), en = n[1] ? VL.short(prefix ? prefix[1] + n[1] : n[1], LBL.en) : '';
    return VL.paperLines(vi, en, P, { oneLine: LBL.one });
  }
  function questionLines(t) {
    var d = AD[AREAS[t.a].id], tr = d && d[t.r];
    if (!tr) return bi(t.co[0]);
    return [[{ text: VL.short(tr.qa.vi, LBL.qvi), color: P.ink }], [{ text: VL.short(tr.qa.en, LBL.qen), color: P.ink2 }]];
  }
  function areaLines(i) { return bi(i, ['Lĩnh vực: ', 'Area: ']); }
  /* the call-outs of the current view: the selected trace's question, provision, law, term and area (all must); with
     an area open, its area and its most-cited laws; else the areas */
  function buildLabels() {
    if (!labelGroup) return;
    clearLabels();
    var sel = state.sel;
    if (sel) {
      var t = sel.t, co = t.co;
      makeLabel(questionLines(t), { id: G.i[co[0]], node: co[0], sel: true, must: true, pri: 1000, px: LBL.pxSel });
      makeLabel(bi(co[2]), { id: G.i[co[2]], node: co[2], must: true, pri: 900 });
      if (co[3] !== co[2]) makeLabel(bi(co[3]), { id: G.i[co[3]], node: co[3], must: true, pri: 880 });
      if (co[4] >= 0) makeLabel(bi(co[4]), { id: G.i[co[4]], node: co[4], must: localTerm(t), pri: 860 });   // a far term: when there is room
      // phones, a law in another region (the frame spans two regions): the area call-out yields first (the toolbar names the area)
      makeLabel(areaLines(co[5]), { id: G.i[co[5]], node: co[5], must: !(mobile && HOME[co[3]] !== HOME[co[0]]), pri: 840 });
    } else if (state.area != null) {
      var ai = AIX[state.area], an = -1, laws = [];
      for (var i = 0; i < N; i++) {
        if (HOME[i] !== ai) continue;
        var c = cname(i);
        if (c === 'area') an = i;
        else if (c === 'work') laws.push(i);
      }
      if (an >= 0) makeLabel(areaLines(an), { id: G.i[an], node: an, must: true, pri: 800 });
      var cnt = function (i) { return tracesOf(i).filter(function (k) { return G.t[k].a === ai; }).length; };
      laws.sort(function (x, y) { return cnt(y) - cnt(x) || x - y; });
      laws.slice(0, mobile ? 4 : 8).forEach(function (w, r) { makeLabel(bi(w), { id: G.i[w], node: w, pri: 500 - r, px: LBL.px - 1 }); });
    } else {
      for (var j = 0; j < N; j++) if (cname(j) === 'area') makeLabel(areaLines(j), { id: G.i[j], node: j, pri: 300, px: LBL.px - 1 });
    }
    T.labels = labels.length;
    scheduleCallouts();
  }
  function calloutItems() {
    return labels.map(function (s) { return { id: s.__id, sprite: s, pri: s.__pri, must: s.__must, sel: s.__sel, r: s.__r }; });
  }
  /* ink the call-outs keep clear of: the selected trace (its foreground nodes and traced segments); with an area open,
     its laws and area; the faded rest is background, as in the paper */
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
        metrics: M, key: 'callouts',
        onDone: function (st) { T.calloutsShown = st.shown; needsRender = true; }
      });
    }
    callouts.schedule();
  }

  /* ------------------------------------------------------------------ the area list */
  function lawShort(law) {
    var en = law.en || law.vi || '';
    return en.indexOf(law.number) >= 0 || !law.number ? en : en + ' · ' + law.number;
  }
  function verdictBadge(tr) {
    return tr.verified ? '<span class="tr-badge ok">✓ <span lang="vi">kiểm chứng</span> · verified ' + f2(tr.match) + '</span>'
      : '<span class="tr-badge st"><span lang="vi">cấu trúc</span> · structural ' + f2(tr.match) + '</span>';
  }
  function renderList(a, data) {
    var t0 = performance.now();
    VL.$('#tr-area-title').innerHTML = '<span lang="vi">' + esc(a.label_vi) + '</span> · <span class="en">' + esc(a.label_en) + '</span>';
    var ver = data.traces.filter(function (t) { return t.verified; }).length;
    VL.$('#tr-area-note').textContent = fmt(a.n_qas) + ' Q&As in the area · the ' + data.traces.length + ' most-asked articles · ' + ver + ' of ' +
      data.traces.length + ' traces text-verified';
    VL.$('#tr-area-m').textContent = a.label_en;
    listEl.innerHTML = data.traces.map(function (tr) {
      return '<li><button type="button" class="tr-item" data-rank="' + tr.rank + '" id="tr-item-' + tr.rank + '">' +
        '<span class="tr-rank">' + tr.rank + '</span><span class="tr-item-body"><span class="tr-law">' + esc(lawShort(tr.law)) + '</span>' +
        '<span class="tr-q" lang="vi">' + esc(tr.qa.vi) + '</span><span class="tr-g">' + esc(tr.qa.en) + '</span>' + verdictBadge(tr) +
        '</span></button></li>';
    }).join('');
    T.listItems = data.traces.length;
    T.listMs = Math.round(performance.now() - t0);
    markList();
  }
  function markList() {
    VL.$$('.tr-item', listEl).forEach(function (b) {
      var on = !!(state.sel && String(state.sel.t.r) === b.getAttribute('data-rank') && AREAS[state.sel.t.a].id === state.area);
      if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
  }
  listEl.addEventListener('click', function (e) {
    var b = e.target.closest('.tr-item');
    if (!b) return;
    selectTrace(state.area, +b.getAttribute('data-rank'), { user: true });
    if (mobile) setSide(false);
  });
  listEl.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    var items = VL.$$('.tr-item', listEl), i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    items[Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))].focus();
  });

  /* ------------------------------------------------------------------ the Fig. 5 hop panel */
  var REASON = { law_not_resolved: 'law not resolved', number_not_in_scope: 'number not in this release', article_not_parsed: 'article not parsed' };
  function primary(tr) { for (var i = 0; i < tr.paths.length; i++) if (tr.paths[i].pr) return tr.paths[i]; return tr.paths[0]; }
  function lawTitle(law) {
    var num = law.number || '', named = (law.vi || '').indexOf(num) >= 0 || (law.en || '').indexOf(num) >= 0;
    return '<span lang="vi" class="vi">' + esc(law.vi) + '</span> · ' + esc(law.en) + (num && !named ? ' · <span class="num">' + esc(num) + '</span>' : '');
  }
  function pathLabel(tr, p) {
    var N_ = tr.nodes, prov = N_[p.n.length > 3 ? p.n[2] : p.n[p.n.length - 1]], work = N_[p.n[p.n.length - 1]];
    if (p.u === 'work') return '<span lang="vi">' + esc(work.vi) + '</span> · ' + esc(work.en) + ' cited as a whole';
    return '<span lang="vi">' + esc(prov.vi) + '</span> · ' + esc(prov.en) + ' of ' + esc(work.en);
  }
  function hop(cls, n, en, vi, body) {
    return '<section class="hop hop-' + cls + '"><h3><b>' + n + ' ' + en + '</b> <span lang="vi">' + vi + '</span></h3>' + body + '</section>';
  }
  function hopsHtml(tr) {
    var p = primary(tr), N_ = tr.nodes, k3 = p.n.length > 3 ? p.n[2] : null, work = N_[p.n[p.n.length - 1]];
    var rec = null, provs = [], whole = [], struct = [];
    N_.forEach(function (n) { if (TD && TD.CLASSES[n.c] === 'record') rec = n; });
    tr.paths.forEach(function (q) { if (q.u === 'work') whole.push(q); else if (q.v) provs.push(q); else struct.push(q); });
    var ans = N_[p.n[1]];
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
      '<p class="pv">a:' + esc(tr.qa.id) + ' −cites→ ' + tr.paths.length + ' targets · method ' + esc(methods.join(' / ')) + ' · ' + esc((ans.p || [])[2] || '') + '</p>');
    var b3 = '';
    if (k3 != null) {
      var prov = N_[k3], chain = p.n.slice(2, -1).reverse().map(function (k) { return N_[k]; });
      var pathVi = chain.map(function (n) { return n.vi; }).join(' › '), pv = prov.p || [];
      b3 = hop('p', '3', 'Provision', 'Điều khoản · ' + esc(pathVi),
        '<p>reached from 2 by <i>cites</i></p><p class="strong"><span lang="vi">' + esc(prov.vi) + '</span> · ' + esc(prov.en) + '</p>' +
        (p.v ? '<p>✓ found word for word in the answer — text match ' + f2(p.m) + '</p>'
          : '<p>○ the answer does not contain its words — text match ' + f2(p.m) + ' (&lt; 0.5): a structural link, kept and not verified</p>') +
        '<p>Text of the provision: ' + (tr.law.url ? ext(tr.law.url, 'read it at the source', 'thuvienphapluat.vn, opens in a new tab') : 'at the source') + '</p>' +
        '<p class="pv">vbpl:' + esc(pv[1] || tr.law.doc_id) + ' › ' + esc(pathVi) + ' · ' + esc(pv[2] || '') + (pv[3] ? ' · ' + esc(pv[3]) : '') + '</p>');
    } else {
      b3 = hop('p', '3', 'Provision', 'Điều khoản', '<p>The answer cites the law as a whole. <span lang="vi">Câu trả lời trích dẫn cả văn bản.</span></p>');
    }
    var wp = work.p || [];
    var b4 = hop('l', '4', 'Law', 'Văn bản · ' + esc(tr.law.number),
      '<p>reached from 3 by <i>contains</i> and <i>realizes</i></p><p class="strong"><span lang="vi">' + esc(tr.law.vi) + '</span> · ' + esc(tr.law.en) + '</p>' +
      '<p>source status (vbpl): <span lang="vi">' + esc(tr.law.status_vi) + '</span> · ' + esc(tr.law.status_en) + '</p>' +
      '<p>English name: ' + esc(tr.law.en_src || 'machine-assisted') + '</p>' +
      (rec ? '<p>VN record: ' + (rec.u ? ext(rec.u, 'vbpl:' + esc(tr.law.doc_id)) : 'vbpl:' + esc(tr.law.doc_id)) + '</p>' : '') +
      '<p class="pv">' + esc(work.i) + ' · ' + esc(wp[2] || '') + '</p>');
    var terms = tr.terms.map(function (t) {
      var n = N_[t.n], d = t.d != null ? N_[t.d] : null;
      return '<li><b><span lang="vi">' + esc(n.vi) + '</span> · ' + esc(n.en) + '</b> — ' +
        (d ? 'defined in ' + esc(d.en) + ' (match ' + f2(t.m) + ')' : 'no defining clause in the laws of this trace') +
        (n.u ? ' · ' + ext(n.u, 'tnpl #' + esc((n.p || [])[1] || '')) : '') +
        '<div class="pv">' + esc(n.i) + (d ? ' ←defines− ' + esc(d.i) : '') + ' · ' + esc((n.p || [])[2] || '') + '</div></li>';
    });
    var b5 = hop('t', '5', 'Terms', 'Thuật ngữ · tnpl', terms.length ?
      '<ul>' + terms.join('') + '</ul><p class="en">question → mentions → term → defined by → clause</p>' :
      '<p>No tnpl term is named in the question. <span lang="vi">Câu hỏi không nhắc đến thuật ngữ nào của tnpl.</span></p>');
    return '<div class="tr-hops" aria-label="The trace hop by hop · Truy vết từng bước">' + b1 +
      '<div class="hop-arrow">↓ answered by · <span lang="vi">được trả lời bởi</span></div>' + b2 + b3 + b4 +
      '<div class="hop-arrow">↓ defines terms the question mentions · <span lang="vi">định nghĩa thuật ngữ câu hỏi nhắc đến</span></div>' + b5 + '</div>';
  }
  function tracePanelHtml(a, tr) {
    return '<button type="button" class="btn panel-close" data-close aria-label="Close · Đóng (Esc)">×</button>' +
      '<p class="tf-area">#' + tr.rank + ' · <span lang="vi">' + esc(a.label_vi) + '</span> · ' + esc(a.label_en) + '</p>' +
      '<h2 id="tp-title">' + lawTitle(tr.law) + '</h2>' +
      '<p class="tf-q" lang="vi">' + esc(tr.qa.vi) + '</p><p class="tf-g">' + esc(tr.qa.en) + '</p>' +
      '<p class="tf-links">' + verdictBadge(tr) + ' · ' + fmt(tr.article.n) + ' answers in ' + esc(a.label_en) + ' cite ' + esc(tr.article.en) +
      ' (' + fmt(tr.article.na) + ' in all areas) · <a href="#area=' + a.id + '&amp;q=' + tr.rank + '">link to this trace</a></p>' + hopsHtml(tr);
  }
  function openPanel(html) {
    panel.innerHTML = html;
    panel.classList.remove('hidden');
    stage.classList.add('panel-open');
    panel.scrollTop = 0;
    T.hops = VL.$$('.hop', panel).length;
    requestAnimationFrame(function () { onResize(); });
  }
  function closePanel() {
    if (panel.classList.contains('hidden')) return;
    panel.classList.add('hidden');
    stage.classList.remove('panel-open');
    T.hops = 0;
    requestAnimationFrame(function () { onResize(); });
  }
  panel.addEventListener('click', function (e) {
    if (e.target.closest('[data-close]')) { clearSelection(true); closePanel(); return; }
    var b = e.target.closest('[data-trace]');
    if (b) { var x = b.getAttribute('data-trace').split(':'); location.hash = 'area=' + x[0] + '&q=' + x[1]; }
  });

  /* ------------------------------------------------------------------ node details (hover, click) */
  function nodeHtml(i) {
    var n = names(i), c = cname(i), cn = classNames(c), ts = tracesOf(i), a = AREAS[HOME[i]];
    var url = G.u[String(i)];
    var rows = '<dt>Id</dt><dd class="iri">' + esc(G.i[i]) + '</dd><dt>Region</dt><dd><span lang="vi">' + esc(a.label_vi) + '</span> · ' + esc(a.label_en) + '</dd>' +
      (url ? '<dt>Source</dt><dd>' + ext(url, 'open the source', 'opens in a new tab') + '</dd>' : '');
    var list = ts.slice(0, 14).map(function (k) {
      var t = G.t[k], ar = AREAS[t.a];
      return '<li><button type="button" class="linkish" data-trace="' + ar.id + ':' + t.r + '">' + esc(ar.label_en) + ' #' + t.r + '</button></li>';
    }).join('');
    return '<button type="button" class="btn panel-close" data-close aria-label="Close · Đóng (Esc)">×</button>' +
      '<p class="panel-kind"><span class="badge"><span lang="vi">' + esc(cn[0]) + '</span> · ' + esc(cn[1]) + '</span></p>' +
      '<h2 lang="vi">' + esc(n[0]) + '</h2><p class="vi">' + esc(n[1]) + '</p><dl class="kv">' + rows + '</dl>' +
      '<h3>In ' + ts.length + ' trace' + (ts.length === 1 ? '' : 's') + ' · <span lang="vi">Trong ' + ts.length + ' đường truy vết</span></h3>' +
      (ts.length ? '<ul class="plist">' + list + '</ul>' + (ts.length > 14 ? '<p class="side-note">and ' + (ts.length - 14) + ' more</p>' : '') : '');
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
      var t = ts.filter(function (x) { return AREAS[x.a].id === state.area; })[0] || ts[0];
      if (t) { location.hash = 'area=' + AREAS[t.a].id + '&q=' + t.r; return; }
    }
    T.clicked = G.i[i];
    openPanel(nodeHtml(i));
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
        var n = names(i), cn = classNames(cname(i)), k = tracesOf(i).length;
        tip.innerHTML = '<b lang="vi">' + esc(VL.short(n[0], 60)) + '</b>' + (n[1] !== n[0] ? ' · ' + esc(VL.short(n[1], 60)) : '') +
          '<div class="t-sub"><span lang="vi">' + esc(cn[0]) + '</span> · ' + esc(cn[1]) + ' · in ' + k + ' trace' + (k === 1 ? '' : 's') + '</div>';
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
  function openArea(id, opts) {
    opts = opts || {};
    var a = BY[id] || AREAS[0];
    TABS.forEach(function (b) {
      var on = b.getAttribute('data-area') === a.id;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
      if (on && opts.focusTab) b.focus();
      if (on) { try { b.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) { /* old engines */ } }
    });
    VL.$('#tr-panel').setAttribute('aria-labelledby', 'tr-tab-' + a.id);
    VL.store.set('traces.area', a.id);
    if (opts.user) setHash('#area=' + a.id);
    var changed = state.area !== a.id;
    state.area = a.id;
    T.area = a.id;
    if (changed || opts.user) {
      if (state.sel && AREAS[state.sel.t.a].id !== a.id) clearSelection(false);
      if (state.sel && opts.user) clearSelection(false);
      if (pointsObj) { applyAlpha(); buildLabels(); }
      if (opts.fly && camera) { closePanel(); flyToArea(AIX[a.id], opts.ms != null ? opts.ms : 900); }
    }
    var my = ++seq;
    if (AD[a.id] && listEl.getAttribute('data-area') === a.id) return Promise.resolve(a);
    VL.$('#tr-area-title').innerHTML = esc(a.label_en) + ' · <span lang="vi">' + esc(a.label_vi) + '</span>';
    listEl.innerHTML = '<li class="tr-status">Loading · <span lang="vi">Đang tải</span></li>';
    return loadArea(a).then(function (data) {
      if (my !== seq) return a;
      renderList(a, data);
      listEl.setAttribute('data-area', a.id);
      if (state.sel) buildLabels();
      T.renders++;
      return a;
    }, function (err) {
      T.errors.push(String(err && err.message || err));
      listEl.innerHTML = '<li class="tr-status">Could not load the traces of this area (' + esc(a.file) + ') · <span lang="vi">Không tải được dữ liệu.</span></li>';
      return a;
    });
  }
  function selectTrace(areaId, rank, opts) {
    opts = opts || {};
    var a = BY[areaId];
    if (!a) return Promise.resolve(null);
    var t = TRK[AIX[a.id] + ':' + rank];
    if (!t) return Promise.resolve(null);
    var p = state.area === a.id ? Promise.resolve(a) : openArea(a.id, {});
    return p.then(function () { return loadArea(a); }).then(function () {
      var tr = AD[a.id][rank];
      var fgSet = new Uint8Array(N), nSet = new Uint8Array(N);
      t.f.forEach(function (i) { fgSet[i] = 1; });
      t.n.forEach(function (i) { nSet[i] = 1; });
      state.sel = { t: t, tr: tr, fgSet: fgSet, nSet: nSet };
      if (opts.user) setHash('#area=' + a.id + '&q=' + rank);
      markList();
      openPanel(tracePanelHtml(a, tr));
      var co = t.co;
      T.selected = { area: a.id, rank: rank, q: G.i[co[0]], answer: G.i[co[1]], provision: G.i[co[2]], law: G.i[co[3]],
        term: co[4] >= 0 ? G.i[co[4]] : null, areaNode: G.i[co[5]], fg: t.f.length, nodes: t.n.length, segments: t.e.length / 3 };
      if (T.fallback) { drawFallback(a, tr); return t; }
      applyAlpha();
      drawTrace();
      buildLabels();
      fitTrace(t, opts.ms != null ? opts.ms : 900);
      return t;
    });
  }
  var TRACE_SEG = 16;      // the traced ribbon: the links' curve, finely sampled
  function drawTrace() {
    var sel = state.sel, v = [], s = [];
    if (sel) {
      var e = sel.t.e;
      for (var j = 0; j < e.length; j += 3) (e[j + 2] === 1 ? v : s).push(curvePts(ptOf(e[j]), ptOf(e[j + 1]), TRACE_SEG));
      sel.paths = v.concat(s);
    }
    traceV.setStyle(VL.traceStyle(P, 1));
    traceS.setStyle(VL.traceStyle(P, 0.55));
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
      sz[j] = src.aSize.array[i];
      al[j] = 1;
    });
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(al, 1));
    if (!fgMat) fgMat = new THREE.ShaderMaterial({ uniforms: pointsMat.uniforms, vertexShader: PT_VS, fragmentShader: PT_FS, depthTest: false, depthWrite: false });
    fgObj = new THREE.Points(g, fgMat);
    fgObj.renderOrder = 20;
    fgObj.frustumCulled = false;
    scene.add(fgObj);
    T.fgDrawn = n;
  }
  function clearSelection(user) {
    if (!state.sel) return;
    state.sel = null;
    T.selected = null;
    markList();
    if (user) setHash('#area=' + state.area);
    if (T.fallback) { fbEl.innerHTML = ''; fbEl.classList.add('hidden'); return; }
    applyAlpha();
    drawTrace();
    buildLabels();
  }

  /* ------------------------------------------------------------------ no WebGL: the selected trace in 2D */
  function drawFallback(a, tr) {
    var view = window.matchMedia('(min-width: 760px)').matches ? 'wide' : 'tall';
    fbEl.innerHTML = '<p class="tr-fb-note">This browser cannot draw the 3D graph (no WebGL 2); the selected trace is drawn in 2D. ' +
      '<span lang="vi">Trình duyệt không vẽ được đồ thị 3D; đường truy vết được vẽ 2D.</span></p>' +
      '<div class="tr-fb-fig" data-view="' + view + '">' + TD.svg(tr, view, { id: 'tf-' + a.id + '-' + tr.rank, title: tr.qa.vi, desc: tr.qa.en, nodeTitles: true }) + '</div>';
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
  function renderLegend() {
    function li(color, vi, en, small) {
      return '<li><span class="swatch' + (small ? ' small' : '') + '" style="background:' + color + '"></span><span lang="vi">' + esc(vi) + '</span>&nbsp;· ' + esc(en) + '</li>';
    }
    var items = VL.PAPER_CLASSES.filter(function (c) { return c.key !== 'intent'; }).map(function (c) { return li(c.v, c.vi, c.en); });
    items.push(li('var(--cls-question)', 'Câu hỏi khác', 'Other answers citing the provisions', true));
    legendEl.innerHTML = '<h3><span lang="vi">Chú giải</span> · Legend</h3><ul>' + items.join('') +
      '<li>' + curveSwatch('') + '<span lang="vi">Đường truy vết</span>&nbsp;· Traced answer</li>' +
      '<li>' + curveSwatch(' s') + '<span lang="vi">Chỉ khớp cấu trúc</span>&nbsp;· Structure only (match &lt; 0.5)</li></ul>' +
      '<p class="lg-note">Dark strokes lead to the sources whose words the answer contains (word 5-gram match ≥ 0.5) and to the clause that defines the question\'s term. ' +
      '<span lang="vi">Nét đậm dẫn tới nguồn có lời văn nằm trong câu trả lời và tới khoản định nghĩa thuật ngữ của câu hỏi.</span></p>';
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
    if (camera && state.area != null) flyToArea(AIX[state.area], 800);
    else if (camera) fitAll(800);
  }
  VL.$('#btn-reset').addEventListener('click', resetView);
  VL.$('#btn-reset-m').addEventListener('click', resetView);
  function setSide(open) {
    app.classList.toggle('side-open', open);
    VL.$('#btn-list-m').setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) closePanel();
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
    var typing = /INPUT|TEXTAREA|SELECT/.test((e.target && e.target.tagName) || '');
    if (e.key !== 'Escape' || typing) return;
    if (app.classList.contains('side-open')) { setSide(false); return; }
    if (state.sel) { clearSelection(true); closePanel(); return; }
    if (!panel.classList.contains('hidden')) closePanel();
  });
  function showHint() { if (VL.store.get('hint-traces3d') !== 'off') { VL.$('#hint').classList.remove('hidden'); scheduleCallouts(); } }
  function hideHint() { var h = VL.$('#hint'); if (h && !h.classList.contains('hidden')) { h.classList.add('hidden'); scheduleCallouts(); } }
  VL.$('#hint-close').addEventListener('click', function () { hideHint(); VL.store.set('hint-traces3d', 'off'); });
  function status() {
    if (!G) return;
    statusEl.textContent = fmt(N) + ' nodes · ' + fmt(T.graph.links) + ' links · ' + G.t.length + ' traces' + (T.fps ? ' · ' + T.fps + ' fps' : '');
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

  /* ------------------------------------------------------------------ routing: #area=<id>&q=<rank> */
  function initialArea() { var s = VL.store.get('traces.area'); return BY[s] ? s : AREAS[0].id; }
  function route() {
    var h = VL.params(), a = BY[h.area];
    if (!a) {
      if (state.area == null) return openArea(initialArea(), { fly: true, ms: 0 });
      if (state.sel) { clearSelection(false); closePanel(); }
      return Promise.resolve();
    }
    var rank = h.q ? parseInt(h.q, 10) : null;
    var fresh = state.area !== a.id, first = state.area == null, ms = first ? 0 : 900;
    return openArea(a.id, { fly: fresh && !(rank && TRK[AIX[a.id] + ':' + rank]), ms: ms }).then(function () {
      if (rank && TRK[AIX[a.id] + ':' + rank]) {
        if (state.sel && state.sel.t.a === AIX[a.id] && state.sel.t.r === rank) return null;
        return selectTrace(a.id, rank, { ms: ms });
      }
      if (state.sel) { clearSelection(false); closePanel(); }
      return null;
    });
  }
  window.addEventListener('hashchange', route);

  window.VLApp = window.VLApp || {};
  window.VLApp.traces = {
    area: function (id) { return openArea(id, { user: true, fly: true }); },
    select: function (id, rank, ms) { return selectTrace(id, rank, { user: true, ms: ms }); },
    clear: function () { clearSelection(true); closePanel(); },
    areas: function () { return AREAS.map(function (a) { return a.id; }); },
    pick: function (x, y) { var i = pick(x, y); return i >= 0 ? G.i[i] : null; },
    project: function (id) {                       // screen position (CSS px in the canvas) of a node, for tests
      var i = G.i.indexOf(id);
      if (i < 0 || !camera) return null;
      var v = new THREE.Vector3(POS[3 * i], POS[3 * i + 1], POS[3 * i + 2]).project(camera);
      return { x: (v.x + 1) / 2 * host.clientWidth, y: (1 - v.y) / 2 * host.clientHeight, inside: Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1 && v.z < 1 };
    },
    settle: function () { return !tween && !(callouts && callouts.last === null); },
    /* the current view as data (camera, the colours / alphas / sizes the shaders get, the call-outs placed), for tests and
       offline previews of the page without a GPU; read-only */
    snapshot: function () {
      if (!camera) return null;
      var pa = pointsObj.geometry.attributes, lines = [];
      for (var e = 0; e < EDGE.s.length; e++) {
        var L = lineGroups[EDGE.g[e]], j = EDGE.j[e], al = L.alpha.array[j];
        if (al > 0.01) lines.push([EDGE.s[e], EDGE.t[e], Math.round(al * 1000) / 1000,
          Math.round(L.color.array[3 * j] * 255), Math.round(L.color.array[3 * j + 1] * 255), Math.round(L.color.array[3 * j + 2] * 255), L.seg]);
      }
      var r3 = function (v) { return Math.round(v * 1000) / 1000; };
      return {
        w: host.clientWidth, h: host.clientHeight, fov: camera.fov, near: camera.near,
        pos: camera.position.toArray().map(r3), target: controls.target.toArray().map(r3), up: camera.up.toArray(),
        color: Array.prototype.map.call(pa.aColor.array, function (v) { return Math.round(v * 255); }),
        alpha: Array.prototype.map.call(pa.aAlpha.array, r3), size: Array.prototype.slice.call(pa.aSize.array),
        lines: lines, lineOpacity: linesMat.uniforms.uOpacity.value, curve: { curves: CURVES, bend: CV.bend, gap: CV.gap, liftMax: CV.liftMax, traceSeg: TRACE_SEG },
        bg: TH.bg, rim: pointsMat.uniforms.uRim.value,
        fog: [FOG.value.x, FOG.value.y, FOG.value.z], dark: !!TH.dark,
        paper: { core: P.core, halo: P.halo, halo2: P.halo2, calloutBg: P.calloutBg, calloutLine: P.calloutLine, selBg: P.selBg,
          selLine: P.selLine, ink: P.ink, ink2: P.ink2, leader: P.leader },
        traceStyle: { v: VL.traceStyle(P, 1), s: VL.traceStyle(P, 0.55), sOpacity: P.dark ? 0.6 : 0.62 },
        labels: labels.map(function (s) { return { id: s.__id, sel: !!s.__sel, px: s.__px, lines: s.__opts.lines }; }),
        callouts: M.callouts || null, free: freeRect(), selected: T.selected
      };
    }
  };

  /* ------------------------------------------------------------------ start */
  renderLegend();
  var t0 = performance.now();
  VL.fontsReady().then(function () {
    return loadGraph();
  }).then(function (g) {
    prepare(g);
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
      fitAll(0);
    }
    T.buildMs = Math.round(performance.now() - t0);
    status();
    return route();
  }).then(function () {
    hideVeil();
    if (!T.fallback) showHint();
    return new Promise(function (res) { requestAnimationFrame(function () { requestAnimationFrame(res); }); });
  }).then(function () {
    return T.fallback ? null : measureFps(700);
  }).then(function (fps) {
    if (fps != null) T.fps = fps;
    status();
    VL.setReady({ tracesArea: state.area, webglRenderer: M.webglRenderer, fps: T.fps });
  }).catch(function (e) {
    console.error(e);
    T.errors.push(String(e && e.message || e));
    var v = VL.$('#veil-text');
    if (v) v.textContent = 'Could not load the traces: ' + (e && e.message);
    VL.setReady({ tracesError: String(e && e.message || e) });
  });
})();

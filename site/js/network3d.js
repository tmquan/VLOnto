/* VLOnto - 3D Legal Network (raw three.js: GPU points + line segments, precomputed coordinates, no live layout).
   data/legal_network_lite.js (6,000 documents) or data/legal_network.js (40,816) are loaded on demand with <script>
   tags; per-document details (dates, source status, URL, change evidence) come from data/doc_links.js and the
   data/doc_details_NN.js shards (scripts/site/derive_site_data.py). Height = legal-force rank (Constitution on top).
   Paper style (arXiv:2611.11426, Fig. 1 / Fig. 6; js/paper3d.js): white figure ground, the encodings (legal-force layers,
   validity, document type or area, change / legal-basis / citation links) in the paper's pastel register, points shaded
   like the paper's spheres, depth fade, bilingual call-outs with leader lines, and the selection drawn as the traced
   answer: its links as a navy core over a pale-gold halo (thicker along its replacement chain), everything else faded.
   Text follows the language mode of js/i18n.js (docs/i18n.md; dictionary js/i18n-3d.js, keys net.*): call-outs and the
   legend in one language or as "Tiếng Việt · English" pairs, panel labels and sentences in one language, numbers through
   VL.fmt; a mode change ('vl:lang') rebuilds them in place and keeps the camera, the selection and the filters. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome({ scene: true });
  M.page = 'network-3d';
  M.paperStyle = true;

  var ZS = 2.2;                      // vertical exaggeration of the legal-force layers
  var KINDS = ['replaced', 'amended', 'repealed', 'partially_repealed', 'partially_expired'];
  var EDGE_KEYS = KINDS.concat(['basis', 'citation']);
  /* normal (not additive) blending: dense legal-basis bundles must keep their pastel blue, not saturate.
     Per theme: thin pastel lines need more opacity on the white ground. */
  var EDGE_OPACITY = {
    dark: { replaced: 0.9, amended: 0.75, repealed: 0.88, partially_repealed: 0.75, partially_expired: 0.75, basis: 0.12, citation: 0.075 },
    light: { replaced: 0.95, amended: 0.9, repealed: 0.92, partially_repealed: 0.88, partially_expired: 0.88, basis: 0.2, citation: 0.13 }
  };
  /* scene colours of the current theme (css/site.css: paper style tokens, --scene-bg, --net-plane*, --area-*) */
  var TH = {}, P = {};
  function readTheme() {
    P = VL.paperTheme();
    TH = {
      dark: P.dark,
      bg: P.bg,
      plane: VL.tok('--net-plane') || '#c9ced6', planeOpacity: VL.tokNum('--net-plane-opacity', 0.14),
      planeLine: VL.tok('--net-plane-line') || '#d3d7dc', planeLineOpacity: VL.tokNum('--net-plane-line-opacity', 1),
      areas: VL.areaColors(), areaNone: VL.tok('--area-none') || '#dcdee2', areaOther: VL.tok('--area-other') || '#92959a',
      typeOther: VL.hue('slate')
    };
    M.sceneBg = TH.bg;
    M.traceCore = P.core;
  }
  readTheme();
  function edgeOpacity(k) { return EDGE_OPACITY[TH.dark ? 'dark' : 'light'][k] * ((k === 'basis' || k === 'citation') && D && D.N > 20000 ? 0.55 : 1); }
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host'), panel = VL.$('#panel');
  var tip = VL.$('#tip'), legendEl = VL.$('#legend'), statusEl = VL.$('#status');
  var params = VL.params();
  /* the labels follow the global language mode (VL.lang()); there is no per-view label language */
  var state = {
    ds: params.ds === 'full' || params.ds === 'lite' ? params.ds : (VL.isMobile() ? 'lite' : 'full'),
    colorBy: 'validity', hops: 1, layers: true, sel: -1, legendOpen: !VL.isMobile(),
    edges: { replaced: true, amended: true, repealed: true, partially_repealed: true, partially_expired: true, basis: true, citation: null },
    y0: null, y1: null, yUnknown: true
  };

  var renderer, scene, camera, controls, pointsObj = null, pointsMat = null, edgeObjs = {}, hlObj = null, layerGroup = null, labelGroup = null;
  var trace = null, chainTrace = null, egoLines = null, egoInc = [], chainIdx = [], hoverIdx = -1, hoverLabel = null;
  var D = null, DL = null, shards = {}, frames = 0, needsRender = true, tween = null;

  /* ------------------------------------------------------------------ three setup */
  /* colours go to the shaders as sRGB values and are written unchanged, so points and lines show the palette exactly */
  function rgb(hex) { return VL.rawColor(hex, new THREE.Color()).toArray(); }
  /* depth fade shared by points and lines: (near, far, strength), updated from the camera distance every frame */
  var FOG = { value: new THREE.Vector3(1, 1e6, 0) };
  var PT_VS = [
    'attribute vec3 aColor; attribute float aAlpha; attribute float aSize;',
    'uniform float uScale; uniform vec3 uFog; varying vec3 vColor; varying float vAlpha; varying float vFog;',
    'void main() {',
    '  vColor = aColor; vAlpha = aAlpha;',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  vFog = clamp((-mv.z - uFog.x) / max(1.0, uFog.y - uFog.x), 0.0, 1.0) * uFog.z;',
    '  float s = aSize * uScale / max(1.0, -mv.z);',
    '  gl_PointSize = aAlpha < 0.01 ? 0.0 : clamp(s, 2.0, 56.0);',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  /* a soft pastel sphere like the paper's nodes: lit from the upper left, a thin rim 16 % darker, fading to the ground
     with depth and outside the highlight (vAlpha) */
  var PT_FS = [
    'uniform vec3 uBg; uniform float uRim; varying vec3 vColor; varying float vAlpha; varying float vFog;',
    'void main() {',
    '  vec2 c = gl_PointCoord - vec2(0.5); float r = length(c) * 2.0;',
    '  if (r > 1.0 || vAlpha < 0.01) discard;',
    '  vec3 n = vec3(c.x * 2.0, -c.y * 2.0, sqrt(max(0.0, 1.0 - r * r)));',
    '  vec3 col = vColor * (0.86 + 0.2 * dot(n, vec3(-0.45, 0.55, 0.70)));',
    '  col = mix(col, vColor * uRim, smoothstep(0.76, 0.96, r));',
    '  gl_FragColor = vec4(mix(uBg, mix(col, uBg, vFog), vAlpha), 1.0);',
    '}'].join('\n');
  /* links as smooth curves, drawn as the traces draw theirs (js/trace-draw.js TD.curve): a cubic Bezier with tangents
     along the legal-force axis at both ends, control points at 45 % of the height difference (Sankey-like S-curves
     between layers). A link within one layer would be straight that way, so it is lifted into a soft arch above its
     plane (lift = BEND x horizontal length, at most LIFT_MAX = 40 % of a layer gap; fading out over one layer gap of
     height difference). The vertex shader evaluates the curve from the two endpoints of each link: one instanced draw
     per link kind with a shared strip of SEG + 1 points (t) and the endpoints, alpha (filters) and, for mixed kinds,
     the colour as per-link attributes. curvePoint() is the same curve on the CPU for the few traced and emphasised
     links drawn as ribbons. */
  var BEND = 0.18, LAYER_GAP = 150 * ZS, LIFT_MAX = 0.4 * LAYER_GAP;
  /* #curves=0 draws straight links (one segment each) to compare the frame rate of the curves with straight lines */
  var CURVES = params.curves !== '0';
  /* a software renderer (no GPU: SwiftShader, llvmpipe) draws coarser curves, so that a frame of the full network
     costs about what straight links did; #curves=full keeps the full detail there too */
  var SOFT_GL = false, CURVE_FULL = params.curves === 'full';
  var CV_VS = [
    'attribute float aT; attribute vec3 aA; attribute vec3 aB; attribute float aAlpha;',
    '#ifdef INST_COLOR',
    'attribute vec3 aColor;',
    '#endif',
    'uniform vec3 uColA; uniform vec3 uColB; uniform float uBend; uniform float uLiftMax; uniform float uLayer; uniform vec3 uFog;',
    'varying vec3 vColor; varying float vAlpha; varying float vFog;',
    'void main() {',
    '  vAlpha = aAlpha;',
    '  if (aAlpha < 0.01) { vColor = vec3(0.0); vFog = 0.0; gl_Position = vec4(0.0, 0.0, 2.0, 1.0); return; }',
    '#ifdef INST_COLOR',
    '  vColor = aColor;',
    '#else',
    '  vColor = mix(uColA, uColB, aT);',
    '#endif',
    '  vec3 d = aB - aA;',
    '  float k = 0.45 * d.y, lift = min(uBend * length(d.xz), uLiftMax) * clamp(1.0 - abs(d.y) / uLayer, 0.0, 1.0);',
    '  float t = aT, u = 1.0 - t, w0 = u * u * u, w1 = 3.0 * u * u * t, w2 = 3.0 * u * t * t, w3 = t * t * t;',
    '  vec3 p = vec3((w0 + w1) * aA.x + (w2 + w3) * aB.x,',
    '    w0 * aA.y + w1 * (aA.y + k + lift) + w2 * (aB.y - k + lift) + w3 * aB.y,',
    '    (w0 + w1) * aA.z + (w2 + w3) * aB.z);',
    '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
    '  vFog = clamp((-mv.z - uFog.x) / max(1.0, uFog.y - uFog.x), 0.0, 1.0) * uFog.z;',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  var CV_FS = [
    'uniform float uOpacity; varying vec3 vColor; varying float vAlpha; varying float vFog;',
    'void main() {',
    '  if (vAlpha < 0.01) discard;',
    '  gl_FragColor = vec4(vColor, vAlpha * uOpacity * (1.0 - vFog));',
    '}'].join('\n');
  /* the same curve on the CPU (ribbons of the traced chain, the hovered link, the selection's links; call-out ink) */
  function curvePoint(a, b, t) {
    var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, k = 0.45 * dy;
    var lift = Math.min(BEND * Math.sqrt(dx * dx + dz * dz), LIFT_MAX) * Math.max(0, Math.min(1, 1 - Math.abs(dy) / LAYER_GAP));
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
  /* segments per link: fewer for the bulk (basis and citation links, fainter) and on the full dataset */
  function segsFor(k) {
    if (!CURVES) return 1;
    var full = D && D.N > 20000, change = KINDS.indexOf(k) >= 0;
    if (SOFT_GL && !CURVE_FULL) return change ? (full ? 4 : 6) : (full ? 2 : 3);
    return change ? (full ? 8 : 10) : (full ? 4 : 6);
  }
  /* per-frame cost of the visible links: vertices through the shader and line segments drawn (straight: 2 and 1) */
  function edgeCost() {
    var c = { curves: CURVES, detail: SOFT_GL && !CURVE_FULL ? 'reduced' : 'full', links: 0, vertices: 0, segments: 0 };
    EDGE_KEYS.forEach(function (k) {
      var eo = edgeObjs[k];
      if (!eo || !state.edges[k]) return;
      c.links += eo.m; c.vertices += eo.m * (eo.seg + 1); c.segments += eo.m * eo.seg;
    });
    c.vsRatio = c.links ? Math.round(c.vertices / (2 * c.links) * 100) / 100 : 0;
    return c;
  }
  function curveGeometry(S, A, B, al, col) {
    var g = new THREE.InstancedBufferGeometry(), t = new Float32Array(S + 1), idx = new Uint16Array(2 * S);
    for (var i = 0; i <= S; i++) t[i] = i / S;
    for (var j = 0; j < S; j++) { idx[2 * j] = j; idx[2 * j + 1] = j + 1; }
    g.setAttribute('aT', new THREE.BufferAttribute(t, 1));
    g.setIndex(new THREE.BufferAttribute(idx, 1));
    g.setAttribute('aA', new THREE.InstancedBufferAttribute(A, 3));
    g.setAttribute('aB', new THREE.InstancedBufferAttribute(B, 3));
    g.setAttribute('aAlpha', new THREE.InstancedBufferAttribute(al, 1));
    if (col) g.setAttribute('aColor', new THREE.InstancedBufferAttribute(col, 3));
    g.instanceCount = al.length;
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 375 * ZS, 0), 2 * (D ? D.extent : 1400) + 800 * ZS);
    return g;
  }
  function curveMaterial(instColor, opacity) {
    return new THREE.ShaderMaterial({
      defines: instColor ? { INST_COLOR: 1 } : {},
      uniforms: { uOpacity: { value: opacity }, uFog: FOG, uColA: { value: new THREE.Color() }, uColB: { value: new THREE.Color() },
        uBend: { value: BEND }, uLiftMax: { value: LIFT_MAX }, uLayer: { value: LAYER_GAP } },
      vertexShader: CV_VS, fragmentShader: CV_FS, transparent: true, depthWrite: false, blending: THREE.NormalBlending
    });
  }
  function updateFog() {
    if (!camera || !D) return;
    var d = camera.position.distanceTo(controls.target), R = D.extent * 1.1;
    FOG.value.set(Math.max(1, d - 0.4 * R), d + 1.9 * R, TH.dark ? 0.55 : 0.6);
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
    controls.autoRotateSpeed = 1.6;
    controls.addEventListener('change', function () { needsRender = true; scheduleCull(); });
    controls.addEventListener('start', hideHint);
    labelGroup = new THREE.Group();
    scene.add(labelGroup);
    /* the selection's links: thin lines in their link-type colours (egoLines); the traced path, on top of the point cloud
       like the paper's trace, only along the replacement chain (chainTrace) and to a hovered neighbour (trace) */
    egoLines = VL.ColorLines({ depthTest: false, renderOrder: 5, width: 1.6, opacity: 0.95 });
    trace = VL.TraceLines({ depthTest: false, renderOrder: 7 });
    chainTrace = VL.TraceLines({ depthTest: false, renderOrder: 10 });
    scene.add(egoLines.object);
    scene.add(trace.object);
    scene.add(chainTrace.object);
    try {
      var gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
      M.webglRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    } catch (e) { M.webglRenderer = null; }
    SOFT_GL = /swiftshader|llvmpipe|softpipe|software|basic render/i.test(M.webglRenderer || '');
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
    VL.fitLegend(stage, legendEl, statusEl);
    needsRender = true;
    scheduleCull();
  }
  /* legend above the status line where the two would meet (js/paper3d.js); the call-outs avoid the legend */
  function fitLegend() { if (VL.fitLegend(stage, legendEl, statusEl)) scheduleCull(); }
  function updatePointScale() {
    if (!pointsMat) return;
    pointsMat.uniforms.uScale.value = renderer.domElement.height / (2 * Math.tan(camera.fov * Math.PI / 360));
  }
  function loop(t) {
    requestAnimationFrame(loop);
    if (tween) stepTween(t);
    var moved = controls.update();
    if (needsRender || moved || tween || controls.autoRotate) {
      updateFog();
      renderer.render(scene, camera);
      frames++;
      needsRender = false;
    }
  }

  /* ------------------------------------------------------------------ data */
  function loadDataset(name) {
    var key = name === 'full' ? 'legal_network' : 'legal_network_lite';
    if (window.VLONTO[key]) return Promise.resolve(window.VLONTO[key]);
    return VL.loadScript('data/' + key + '.js').then(function () { return window.VLONTO[key]; });
  }
  function prepare(net, name) {
    var F = {};
    net.fields.forEach(function (f, i) { F[f] = i; });
    var N = net.nodes.length;
    var d = {
      name: name, net: net, N: N, ids: new Array(N), num: new Array(N), title: new Array(N),
      type: new Int8Array(N), year: new Int16Array(N), issuer: new Int16Array(N), area: new Int16Array(N),
      validity: new Int8Array(N), rank: new Int8Array(N), degree: new Int32Array(N), pos: new Float32Array(N * 3), idx: {}
    };
    var yMin = 9999, yMax = 0;
    net.nodes.forEach(function (r, i) {
      d.ids[i] = String(r[F.id]);
      d.num[i] = r[F.number] ? VL.nfc(r[F.number]) : '';
      d.title[i] = VL.nfc(r[F.title] || '');
      d.type[i] = r[F.type] == null ? -1 : r[F.type];
      var y = r[F.year] || -1;
      d.year[i] = y;
      if (y > 0) { yMin = Math.min(yMin, y); yMax = Math.max(yMax, y); }
      d.issuer[i] = r[F.issuer] == null ? -1 : r[F.issuer];
      d.area[i] = r[F.area] == null ? -1 : r[F.area];
      d.validity[i] = r[F.validity] == null ? -1 : r[F.validity];
      d.rank[i] = r[F.rank];
      d.degree[i] = r[F.degree] || 0;
      d.pos[3 * i] = r[F.x];
      d.pos[3 * i + 1] = r[F.z] * ZS;
      d.pos[3 * i + 2] = r[F.y];
      d.idx[d.ids[i]] = i;
    });
    d.yMin = yMin; d.yMax = yMax;
    var kinds = net.change_kinds || KINDS;
    d.edges = {};
    EDGE_KEYS.forEach(function (k) { d.edges[k] = []; });
    (net.edges.change || []).forEach(function (e) { var k = kinds[e[2]]; if (d.edges[k]) d.edges[k].push(e[0], e[1]); });
    (net.edges.basis || []).forEach(function (e) { d.edges.basis.push(e[0], e[1]); });
    (net.edges.citation || []).forEach(function (e) { d.edges.citation.push(e[0], e[1]); });
    EDGE_KEYS.forEach(function (k) { d.edges[k] = Int32Array.from(d.edges[k]); });
    d.adj = {};
    d.vis = new Uint8Array(N);
    d.ego = new Uint8Array(N);
    d.layerZ = net.layout && net.layout.z_by_rank ? net.layout.z_by_rank : { 0: 750, 1: 600, 2: 450, 3: 300, 4: 150, 5: 0 };
    d.extent = (net.layout && net.layout.x_y_range) ? Math.max(Math.abs(net.layout.x_y_range[0]), Math.abs(net.layout.x_y_range[1])) : 1400;
    return d;
  }
  function adjacency(k) {
    if (D.adj[k]) return D.adj[k];
    var pairs = D.edges[k], N = D.N, deg = new Int32Array(N + 1);
    for (var i = 0; i < pairs.length; i += 2) { deg[pairs[i]]++; deg[pairs[i + 1]]++; }
    var off = new Int32Array(N + 1);
    for (var j = 0; j < N; j++) off[j + 1] = off[j] + deg[j];
    var fill = off.slice(0, N), nb = new Int32Array(off[N]);
    for (var e = 0; e < pairs.length; e += 2) { var a = pairs[e], b = pairs[e + 1]; nb[fill[a]++] = b; nb[fill[b]++] = a; }
    D.adj[k] = { off: off, nb: nb };
    return D.adj[k];
  }

  /* ------------------------------------------------------------------ colours */
  var areaRank = null;
  function areaColor(a) {
    if (a < 0) return TH.areaNone;
    if (!areaRank) {
      var cnt = {};
      for (var i = 0; i < D.N; i++) if (D.area[i] >= 0) cnt[D.area[i]] = (cnt[D.area[i]] || 0) + 1;
      areaRank = {};
      Object.keys(cnt).sort(function (x, y) { return cnt[y] - cnt[x]; }).forEach(function (k, i) { areaRank[k] = i; });
    }
    var r = areaRank[a];
    return r != null && r < TH.areas.length ? TH.areas[r] : TH.areaOther;
  }
  function nodeColor(i) {
    if (state.colorBy === 'type') { var t = D.net.types[D.type[i]]; return (t && VL.TYPE_COLORS[t.code]) || TH.typeOther; }
    if (state.colorBy === 'area') return areaColor(D.area[i]);
    var v = D.net.validity[D.validity[i]];
    return (VL.VALIDITY[v] || VL.VALIDITY.unknown).color;
  }
  function applyColors() {
    var col = pointsObj.geometry.attributes.aColor.array, cache = {};
    for (var i = 0; i < D.N; i++) {
      var hex = nodeColor(i);
      var c = cache[hex] || (cache[hex] = rgb(hex));
      col[3 * i] = c[0]; col[3 * i + 1] = c[1]; col[3 * i + 2] = c[2];
    }
    pointsObj.geometry.attributes.aColor.needsUpdate = true;
    renderLegend();
    needsRender = true;
  }

  /* ------------------------------------------------------------------ scene objects */
  function disposeScene() {
    if (pointsObj) { scene.remove(pointsObj); pointsObj.geometry.dispose(); pointsMat.dispose(); pointsObj = null; }
    Object.keys(edgeObjs).forEach(function (k) { var o = edgeObjs[k].obj; scene.remove(o); o.geometry.dispose(); o.material.dispose(); });
    edgeObjs = {};
    if (hlObj) { scene.remove(hlObj); hlObj.geometry.dispose(); hlObj.material.dispose(); hlObj = null; }
    if (layerGroup) { scene.remove(layerGroup); layerGroup = null; }
    clearLabels();
  }
  function buildScene() {
    disposeScene();
    areaRank = null;
    var N = D.N, g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(D.pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(N), 1));
    var size = new Float32Array(N), base = [44, 22, 16, 11, 10, 9];
    for (var i = 0; i < N; i++) size[i] = (base[D.rank[i]] || 9) + 2.6 * Math.log2(1 + D.degree[i]);
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
    EDGE_KEYS.forEach(buildEdges);
    buildLayers();
    applyColors();
    applyFilters();
  }
  function edgeColor(k) { return k === 'basis' ? VL.EDGE.basis.color : k === 'citation' ? VL.EDGE.citation.color : VL.CHANGE[k].color; }
  function buildEdges(k) {
    var pairs = D.edges[k], m = pairs.length / 2, S = segsFor(k);
    var A = new Float32Array(m * 3), B = new Float32Array(m * 3), al = new Float32Array(m);
    for (var e = 0; e < m; e++) {
      var s = pairs[2 * e], t = pairs[2 * e + 1];
      A[3 * e] = D.pos[3 * s]; A[3 * e + 1] = D.pos[3 * s + 1]; A[3 * e + 2] = D.pos[3 * s + 2];
      B[3 * e] = D.pos[3 * t]; B[3 * e + 1] = D.pos[3 * t + 1]; B[3 * e + 2] = D.pos[3 * t + 2];
      al[e] = 1;
    }
    /* colour gradient along the link: its kind's colour at the source, 20 % toward the ground at the target */
    var c0 = rgb(edgeColor(k)), f = TH.dark ? 0.62 : 0.8;
    var c2 = TH.dark ? [c0[0] * f, c0[1] * f, c0[2] * f] : [1 - (1 - c0[0]) * f, 1 - (1 - c0[1]) * f, 1 - (1 - c0[2]) * f];
    var mat = curveMaterial(false, edgeOpacity(k));
    mat.uniforms.uColA.value.setRGB(c0[0], c0[1], c0[2]);
    mat.uniforms.uColB.value.setRGB(c2[0], c2[1], c2[2]);
    var obj = new THREE.LineSegments(curveGeometry(S, A, B, al, null), mat);
    obj.frustumCulled = false;
    obj.renderOrder = KINDS.indexOf(k) >= 0 ? 4 : 1;
    obj.visible = !!state.edges[k];
    scene.add(obj);
    edgeObjs[k] = { obj: obj, m: m, seg: S };
    M.edgeSegments = M.edgeSegments || {};
    M.edgeSegments[k] = S;
  }
  function buildLayers() {
    layerGroup = new THREE.Group();
    var E = D.extent * 1.06;
    for (var r = 0; r <= 5; r++) {
      var y = (D.layerZ[r] != null ? D.layerZ[r] : (5 - r) * 150) * ZS;
      var plane = new THREE.Mesh(new THREE.PlaneGeometry(2 * E, 2 * E),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(TH.plane), transparent: true, opacity: TH.planeOpacity, depthWrite: false, side: THREE.DoubleSide }));
      plane.rotation.x = -Math.PI / 2;
      plane.position.y = y - 2;
      plane.renderOrder = 0;
      layerGroup.add(plane);
      var pts = [new THREE.Vector3(-E, y - 2, -E), new THREE.Vector3(E, y - 2, -E), new THREE.Vector3(E, y - 2, E), new THREE.Vector3(-E, y - 2, E)];
      var outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: new THREE.Color(TH.planeLine), transparent: true, opacity: TH.planeLineOpacity }));
      layerGroup.add(outline);
    }
    layerGroup.visible = state.layers;
    scene.add(layerGroup);
    buildLayerLabels();
  }

  /* ------------------------------------------------------------------ labels (constant pixel size, culled) */
  var labels = [], labelGen = 0;
  function worldPerPx() { return VL.spriteWpp(camera, host.clientHeight); }
  /* paper call-out: lines of parts (js/paper3d.js VL.paperLines), px = height of a one-line box in CSS px (text is about
     px / 1.68); node call-outs stand on a thin grey leader above their point, layer call-outs sit at the layer corner */
  function makeLabel(lines, opts) {
    var o = VL.paperCallout(P, !!opts.sel);
    o.lines = lines;
    o.px = opts.px || 22;
    o.weight = opts.weight || '400';
    var s = VL.TextSprite(lines[0].map(function (p) { return p.text; }).join(''), o);
    labelGen++;
    s.__pri = opts.pri || 0;
    s.__layer = !!opts.layer;
    s.__id = opts.id || ('label-' + labels.length);
    s.__must = !!opts.must;
    s.__sel = !!opts.sel;
    s.layers.set(1);                  // hidden until VL.Callouts places it
    s.fit(worldPerPx());
    return s;
  }
  function addLabel(s, x, y, z) {
    s.position.set(x, y, z);
    labelGroup.add(s);
    labels.push(s);
    return s;
  }
  function clearLabels(onlyNodes) {
    labels = labels.filter(function (s) {
      if (onlyNodes && s.__layer) return true;
      labelGroup.remove(s);
      s.dispose();
      return false;
    });
  }
  function updateLabelSizes() { var w = worldPerPx(); labels.forEach(function (s) { s.fit(w); }); }
  /* "Bậc 0 · Hiến pháp" over "Rank 0 · Constitution" (EN–VI), or one line in EN or VI; short names of the layers
     (net.rank.N), the data's own names where the dictionary has none */
  function rankLabel(r) {
    var rk = (D.net.ranks || [])[r] || {}, k = 'net.rank.' + r;
    var name = VL.i18n.has(k) ? VL.kpair(k) : VL.pair(rk.vi || rk.en || '', rk.en || '');
    return VL.paperTL('net.rank.label', { r: r, name: name }, P, { twoLines: true });
  }
  function buildLayerLabels() {
    clearLabels(false);
    M.labelsLang = VL.lang();
    if (!state.layers) return;
    var E = D.extent * 1.06;
    for (var r = 0; r <= 5; r++) {
      var y = (D.layerZ[r] != null ? D.layerZ[r] : (5 - r) * 150) * ZS;
      addLabel(makeLabel(rankLabel(r), { px: 21, pri: 10 - r, layer: true, id: 'rank-' + r }), -E, y, E);
    }
  }
  /* screen-space declutter shared with the playground and the CONSTRUCT view (js/paper3d.js VL.Callouts): call-outs on
     thin leaders in clear space, never over each other or over the highlighted ink (the selection, its neighbours,
     the chain and their links; the faded cloud behind them is background). The selection, the documents of the
     replacement chain and a hovered neighbour always keep their call-outs; layer names sit at the layer corner. */
  var callouts = null, lastPlacement = '';
  function layerOffset(w) { return [w / 2 + 2, 0]; }
  function calloutItems() {
    return labels.map(function (s) {
      return { id: s.__id, sprite: s, pri: s.__pri, must: !!s.__must, sel: !!s.__sel, r: s.__r || 0, fixed: s.__layer ? layerOffset : null, off: s.__layer && !state.layers };
    });
  }
  function ptOf(i) { return { x: D.pos[3 * i], y: D.pos[3 * i + 1], z: D.pos[3 * i + 2] }; }
  function calloutInk() {
    var discs = [], paths = [];
    if (!D || state.sel < 0 || !pointsObj) return { discs: discs, paths: paths };
    var sz = pointsObj.geometry.attributes.aSize.array;
    function disc(i) { discs.push({ id: 'doc-' + D.ids[i], x: D.pos[3 * i], y: D.pos[3 * i + 1], z: D.pos[3 * i + 2], r: sz[i] / 2 }); }
    disc(state.sel);
    chainIdx.forEach(function (i) { if (i !== state.sel) disc(i); });
    for (var i = 0; i < D.N && discs.length < 5000; i++) if (D.ego[i] && i !== state.sel && chainIdx.indexOf(i) < 0) disc(i);
    for (var e = 0; e < egoInc.length && e < 3000; e++) paths.push(curvePts(ptOf(egoInc[e][0]), ptOf(egoInc[e][1]), 4));
    if (chainIdx.length > 1) paths.push(chainCurve(chainIdx, 8));
    return { discs: discs, paths: paths };
  }
  function scheduleCull() {
    if (!camera) return;
    if (!callouts) {
      callouts = VL.Callouts({
        camera: function () { return camera; },
        size: function () { return { w: host.clientWidth, h: host.clientHeight }; },
        items: calloutItems, ink: calloutInk, ui: obstacles,
        leaderColor: function () { return P.leader; },
        discMaxPx: 28 / Math.min(window.devicePixelRatio || 1, 2), segCap: 16000,
        metrics: M, key: 'callouts',
        onDone: function (st) {
          M.labelsShown = st.shown; M.labelsTotal = labels.length;
          /* a frame only when the call-outs changed: new sprites (labelGen) or other boxes; an idle tail run after the
             camera stopped costs no frame (a full frame is slow on a software renderer) */
          var sig = labelGen + '#' + st.placed.map(function (q) { return q.id + ':' + q.box.join(','); }).join('|');
          if (sig !== lastPlacement) { lastPlacement = sig; needsRender = true; M.calloutFrames = (M.calloutFrames || 0) + 1; }
          else M.calloutIdleRuns = (M.calloutIdleRuns || 0) + 1;
        }
      });
    }
    callouts.schedule();
  }
  function obstacles() {
    var hr = host.getBoundingClientRect(), out = [];
    ['#legend', '#hint', '.stage-tools', '#status', '#panel'].forEach(function (sel) {
      var e = VL.$(sel, stage);
      if (!e || e.classList.contains('hidden') || e.offsetParent === null) return;
      var r = e.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      out.push({ x0: r.left - hr.left - 4, x1: r.right - hr.left + 4, y0: r.top - hr.top - 4, y1: r.bottom - hr.top + 4 });
    });
    return out;
  }

  /* ------------------------------------------------------------------ filters, ego highlight */
  function applyFilters() {
    var vis = D.vis, y0 = state.y0 == null ? D.yMin : state.y0, y1 = state.y1 == null ? D.yMax : state.y1, n = 0;
    for (var i = 0; i < D.N; i++) {
      var y = D.year[i];
      var ok = y > 0 ? (y >= y0 && y <= y1) : state.yUnknown;
      vis[i] = ok ? 1 : 0;
      n += vis[i];
    }
    D.visibleCount = n;
    applyAlpha();
    EDGE_KEYS.forEach(function (k) {
      var eo = edgeObjs[k], pairs = D.edges[k], al = eo.obj.geometry.attributes.aAlpha.array, shownE = 0;
      for (var e = 0; e < eo.m; e++) {
        var v = vis[pairs[2 * e]] && vis[pairs[2 * e + 1]] ? 1 : 0;
        al[e] = v; shownE += v;
      }
      eo.shown = shownE;
      eo.obj.geometry.attributes.aAlpha.needsUpdate = true;
      eo.obj.visible = !!state.edges[k];
    });
    renderEdgeToggles();
    if (state.sel >= 0 && !vis[state.sel]) clearSelection();
    else if (state.sel >= 0) computeEgo();
    status();
    needsRender = true;
  }
  function applyAlpha() {
    var a = pointsObj.geometry.attributes.aAlpha.array, ego = state.sel >= 0;
    for (var i = 0; i < D.N; i++) a[i] = !D.vis[i] ? 0 : (ego ? (D.ego[i] ? 1 : 0.14) : 1);
    pointsObj.geometry.attributes.aAlpha.needsUpdate = true;
    EDGE_KEYS.forEach(function (k) { edgeObjs[k].obj.material.uniforms.uOpacity.value = edgeOpacity(k) * (ego ? 0.22 : 1); });
    needsRender = true;
  }
  function enabledKinds() { return EDGE_KEYS.filter(function (k) { return state.edges[k]; }); }
  function computeEgo() {
    var i0 = state.sel, ego = D.ego;
    ego.fill(0);
    ego[i0] = 3;
    var kinds = enabledKinds(), frontier = [i0];
    for (var h = 1; h <= state.hops; h++) {
      var next = [];
      kinds.forEach(function (k) {
        var A = adjacency(k);
        frontier.forEach(function (u) {
          for (var p = A.off[u]; p < A.off[u + 1]; p++) {
            var v = A.nb[p];
            if (!ego[v] && D.vis[v]) { ego[v] = h; next.push(v); }
          }
        });
      });
      frontier = next;
      if (next.length > 6000) break;
    }
    /* highlighted edges inside the neighbourhood: the selection's own links are thin lines in their link-type colours
       (only the replacement chain and a hovered link are traced, as in the paper, where only the traced path is dark);
       with 2 hops the links of its neighbours stay fainter pastel lines */
    var pcol = [], A2 = [], B2 = [], col = [];
    egoInc = [];
    kinds.forEach(function (k) {
      var pairs = D.edges[k], c = rgb(edgeColor(k)), hex = TH.dark ? edgeColor(k) : VL.shade(edgeColor(k), 0.9);
      for (var e = 0; e < pairs.length; e += 2) {
        var s = pairs[e], t = pairs[e + 1];
        if (!ego[s] || !ego[t]) continue;
        if (ego[s] === 3 || ego[t] === 3) {
          if (egoInc.length < 30000) { pcol.push(hex); egoInc.push([s, t, k]); }
        } else if (state.hops > 1 && (ego[s] === 1 || ego[t] === 1) && A2.length < 3 * 30000) {
          A2.push(D.pos[3 * s], D.pos[3 * s + 1], D.pos[3 * s + 2]);
          B2.push(D.pos[3 * t], D.pos[3 * t + 1], D.pos[3 * t + 2]);
          col.push(c[0], c[1], c[2]);
        }
      }
    });
    /* the selection's links on their curves, with fewer segments when there are many */
    var n = egoInc.length, segs = n > 2000 ? 4 : (n > 400 ? 8 : 12);
    egoLines.setStyle({ width: n > 400 ? 1.1 : (n > 120 ? 1.3 : 1.6) });
    egoLines.setPaths(egoInc.map(function (e) { return curvePts(ptOf(e[0]), ptOf(e[1]), segs); }), pcol);
    hoverIdx = -1;
    trace.setPaths([]);
    M.hoverDoc = null;
    if (hlObj) { scene.remove(hlObj); hlObj.geometry.dispose(); hlObj.material.dispose(); hlObj = null; }
    if (A2.length) {
      var al = new Float32Array(A2.length / 3);
      al.fill(1);
      hlObj = new THREE.LineSegments(curveGeometry(CURVES ? 6 : 1, new Float32Array(A2), new Float32Array(B2), al, new Float32Array(col)), curveMaterial(true, 0.9));
      hlObj.frustumCulled = false;
      hlObj.renderOrder = 5;
      scene.add(hlObj);
    }
    var cnt = [0, 0, 0];
    for (var i = 0; i < D.N; i++) if (ego[i] === 1) cnt[1]++; else if (ego[i] === 2) cnt[2]++;
    M.egoHop1 = cnt[1]; M.egoHop2 = cnt[2]; M.egoEdges = n + A2.length / 3;
    M.egoLines = egoLines.count();
    M.traceSegments = trace.count();
    applyAlpha();
    egoLabels();
    needsRender = true;
  }
  /* the replacement chain of a document (older -> newer through 'replaced' changes), as indices of doc_links */
  function replacementChain(fi) {
    var replaces = function (x) { return (DL.byActing[x] || []).filter(function (ci) { return DL.changes[ci][2] === 0; }).map(function (ci) { return DL.changes[ci][1]; }); };
    var replacedBy = function (x) { return (DL.byAffected[x] || []).filter(function (ci) { return DL.changes[ci][2] === 0; }).map(function (ci) { return DL.changes[ci][0]; }); };
    var back = [], fwd = [], seen = {}, cur = fi;
    seen[fi] = 1;
    for (var s = 0; s < 8; s++) { var r = replaces(cur).filter(function (x) { return !seen[x]; }); if (!r.length) break; r.sort(function (a, b) { return DL.year[b] - DL.year[a]; }); cur = r[0]; seen[cur] = 1; back.unshift(cur); }
    cur = fi;
    for (var t = 0; t < 8; t++) { var q = replacedBy(cur).filter(function (x) { return !seen[x]; }); if (!q.length) break; q.sort(function (a, b) { return DL.year[a] - DL.year[b]; }); cur = q[0]; seen[cur] = 1; fwd.push(cur); }
    return (back.length || fwd.length) ? back.concat([fi], fwd) : null;
  }
  /* the chain in 3D: one traced path through the documents of the chain present in this dataset */
  function drawChain(fi) {
    var ch = DL && fi != null ? replacementChain(fi) : null, pts = [];
    chainIdx = [];
    (ch || []).forEach(function (x) {
      var i = D.idx[String(DL.ids[x])];
      if (i != null) { pts.push(ptOf(i)); chainIdx.push(i); }
    });
    if (pts.length < 2) chainIdx = [];
    chainTrace.setStyle(VL.traceStyle(P, 1));
    chainTrace.setPaths(pts.length > 1 ? [chainCurve(chainIdx, 24)] : []);
    M.chainTraceDocs = pts.length > 1 ? pts.length : 0;
    if (state.sel >= 0) egoLabels();
    needsRender = true;
  }
  /* the chain as one polyline along the link curves from document to document */
  function chainCurve(idx, n) {
    var out = [];
    for (var c = 0; c + 1 < idx.length; c++) {
      var seg = curvePts(ptOf(idx[c]), ptOf(idx[c + 1]), n);
      out = out.concat(c ? seg.slice(1) : seg);
    }
    return out;
  }
  /* hovering a neighbour of the selection traces the link(s) between them and keeps the neighbour's call-out */
  function setHover(i) {
    if (!D || state.sel < 0 || i === state.sel || (i >= 0 && D.ego[i] !== 1)) i = -1;
    if (i === hoverIdx) return;
    hoverIdx = i;
    var paths = [];
    if (i >= 0) egoInc.forEach(function (e) { if ((e[0] === i && e[1] === state.sel) || (e[1] === i && e[0] === state.sel)) paths.push(curvePts(ptOf(e[0]), ptOf(e[1]), 24)); });
    trace.setStyle(VL.traceStyle(P, 0.85));
    trace.setPaths(paths);
    M.traceSegments = trace.count();
    M.hoverDoc = i >= 0 ? D.ids[i] : null;
    labels.forEach(function (s) { if (s.__hoverMust) { s.__must = false; s.__hoverMust = false; } });
    if (hoverLabel) {
      labels = labels.filter(function (x) { return x !== hoverLabel; });
      labelGroup.remove(hoverLabel);
      hoverLabel.dispose();
      hoverLabel = null;
    }
    if (i >= 0) {
      var ex = labels.filter(function (x) { return x.__idx === i; })[0];
      if (ex) { if (!ex.__must) { ex.__must = true; ex.__hoverMust = true; } }
      else hoverLabel = docLabel(i, docLines(i), { px: 21, pri: 800, must: true });
    }
    scheduleCull();
    needsRender = true;
  }
  function docLines(j) {
    return D.num[j] ? [[{ text: D.num[j], color: P.ink }].concat(D.year[j] > 0 ? [{ text: ' · ' + D.year[j], color: P.ink2 }] : [])] :
      [[{ text: VL.short(D.title[j], 30), color: P.ink }]];
  }
  function docLabel(i, lines, o) {
    o.id = 'doc-' + D.ids[i];
    var s = addLabel(makeLabel(lines, o), D.pos[3 * i], D.pos[3 * i + 1], D.pos[3 * i + 2]);
    s.__idx = i;
    s.__r = pointsObj.geometry.attributes.aSize.array[i] / 2;
    return s;
  }
  function egoLabels() {
    clearLabels(true);
    hoverLabel = null;
    var i0 = state.sel;
    if (i0 < 0) { scheduleCull(); return; }
    /* the selected document: its title over its number and year, like the paper's call-outs (pale gold = selected) */
    var meta = (D.num[i0] || VL.T('net.noNumber')) + (D.year[i0] > 0 ? ' · ' + D.year[i0] : '');
    M.labelsLang = VL.lang();
    var main = D.title[i0] ? [[{ text: VL.short(D.title[i0], 46), color: P.ink }], [{ text: meta, color: P.ink2 }]] : [[{ text: meta, color: P.ink }]];
    docLabel(i0, main, { px: 25, pri: 1000, sel: true, must: true });
    chainIdx.forEach(function (j) { if (j !== i0) docLabel(j, docLines(j), { px: 21, pri: 900, must: true }); });
    var nb = [];
    for (var i = 0; i < D.N; i++) if ((D.ego[i] === 1 || D.ego[i] === 2) && chainIdx.indexOf(i) < 0) nb.push(i);
    nb.sort(function (a, b) { return (D.ego[a] - D.ego[b]) || (D.degree[b] - D.degree[a]); });
    nb.slice(0, 40).forEach(function (j, r) { docLabel(j, docLines(j), { px: 21, pri: 500 - r - (D.ego[j] === 2 ? 100 : 0) }); });
    if (hoverIdx >= 0) { var h = hoverIdx; hoverIdx = -1; setHover(h); }
    scheduleCull();
  }

  /* ------------------------------------------------------------------ camera */
  function fitAll(ms) {
    var E = D.extent, Ymax = 750 * ZS, cy = Ymax / 2;
    var R = Math.sqrt(2 * E * E + cy * cy) * 0.86;
    var sz = stageSize(), vf = camera.fov * Math.PI / 180, aspect = sz.w / sz.h, hf = 2 * Math.atan(Math.tan(vf / 2) * aspect);
    var d = R / Math.sin(Math.min(vf, hf) / 2);
    var dir = new THREE.Vector3(0.18, 0.5, 1).normalize();
    moveCamera(new THREE.Vector3(dir.x * d, cy + dir.y * d, dir.z * d), new THREE.Vector3(0, cy, 0), ms);
  }
  function flyTo(i, radius) {
    var p = new THREE.Vector3(D.pos[3 * i], D.pos[3 * i + 1], D.pos[3 * i + 2]);
    var sz = stageSize(), vf = camera.fov * Math.PI / 180, aspect = sz.w / sz.h, hf = 2 * Math.atan(Math.tan(vf / 2) * aspect);
    var d = Math.max(260, Math.min(2600, radius || 600)) / Math.sin(Math.min(vf, hf) / 2);
    var dir = new THREE.Vector3().subVectors(camera.position, controls.target);
    if (dir.lengthSq() < 1) dir.set(0.2, 0.5, 1);
    dir.normalize();
    if (dir.y < 0.25) { dir.y = 0.25; dir.normalize(); }
    moveCamera(p.clone().add(dir.multiplyScalar(d)), p, 900);
  }
  function moveCamera(pos, target, ms) {
    if (!ms) {
      camera.position.copy(pos); controls.target.copy(target); camera.lookAt(target); controls.update(); needsRender = true; scheduleCull(); return;
    }
    tween = { t0: null, ms: ms, p0: camera.position.clone(), p1: pos, q0: controls.target.clone(), q1: target };
  }
  function stepTween(t) {
    if (tween.t0 == null) tween.t0 = t;
    var u = Math.min(1, (t - tween.t0) / tween.ms), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.q0, tween.q1, e);
    if (u >= 1) { tween = null; scheduleCull(); }
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
    scheduleCull();
  }
  function measureFps(ms) {
    return new Promise(function (resolve) {
      var was = controls.autoRotate;
      controls.autoRotate = true;
      var f0 = frames, t0 = performance.now();
      setTimeout(function () {
        var fps = Math.round((frames - f0) * 10000 / (performance.now() - t0)) / 10;
        controls.autoRotate = was;
        M.fpsSamples = (M.fpsSamples || []).concat([{ dataset: D.name, fps: fps, edges: edgeCost() }]);
        resolve(fps);
      }, ms);
    });
  }
  window.VLApp.measureFps = measureFps;

  /* ------------------------------------------------------------------ picking + hover */
  var raycaster = null, ndc = null;
  function pick(clientX, clientY) {
    if (!pointsObj) return -1;
    if (!raycaster) { raycaster = new THREE.Raycaster(); ndc = new THREE.Vector2(); }
    var r = renderer.domElement.getBoundingClientRect();
    ndc.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    var dist = camera.position.distanceTo(controls.target);
    raycaster.params.Points.threshold = Math.max(4, dist * worldPerPx() * 7);
    raycaster.setFromCamera(ndc, camera);
    var hits = raycaster.intersectObject(pointsObj, false), best = -1, bestScore = Infinity;
    var alpha = pointsObj.geometry.attributes.aAlpha.array;
    hits.forEach(function (h) {
      var i = h.index;
      if (alpha[i] < 0.05) return;
      var score = h.distanceToRay / (1 + (alpha[i] > 0.5 ? 1 : 0)) + h.distance * 1e-4;
      if (score < bestScore) { bestScore = score; best = i; }
    });
    return best;
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
      if (i >= 0) select(i, true); else clearSelection();
    });
    cv.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch' || down) { tip.classList.add('hidden'); return; }
      if (hoverRaf) return;
      var x = e.clientX, y = e.clientY;
      hoverRaf = requestAnimationFrame(function () {
        hoverRaf = 0;
        var i = pick(x, y);
        cv.style.cursor = i >= 0 ? 'pointer' : '';
        setHover(i);
        if (i < 0) { tip.classList.add('hidden'); return; }
        var t = D.net.types[D.type[i]] || {}, v = VL.VALIDITY[D.net.validity[D.validity[i]]] || VL.VALIDITY.unknown;
        tip.innerHTML = '<b>' + VL.esc(D.num[i] || '–') + '</b> <span lang="vi">' + VL.esc(VL.short(D.title[i], 60)) + '</span>' +
          '<div class="t-sub">' + VL.UH(VL.pair(t.vi, t.en)) + (D.year[i] > 0 ? ' · ' + D.year[i] : '') + ' · ' + VL.UH(v) + '</div>';
        tip.classList.remove('hidden');
        var hr = stage.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
        var lx = Math.min(hr.width - tw - 8, x - hr.left + 14), ly = y - hr.top + 14;
        if (ly + th > hr.height - 8) ly = y - hr.top - th - 10;
        tip.style.left = Math.max(8, lx) + 'px';
        tip.style.top = Math.max(8, ly) + 'px';
      });
    });
    cv.addEventListener('pointerleave', function () { tip.classList.add('hidden'); setHover(-1); });
  }

  /* ------------------------------------------------------------------ details (lazy data) */
  function loadLinks() {
    if (DL) return Promise.resolve(DL);
    return VL.loadScript('data/doc_links.js').then(function () {
      var L = window.VLONTO.doc_links;
      L.idx = {};
      L.ids.forEach(function (id, i) { L.idx[String(id)] = i; });
      L.byActing = {}; L.byAffected = {}; L.basisOut = {};
      L.changes.forEach(function (c, ci) { (L.byActing[c[0]] = L.byActing[c[0]] || []).push(ci); (L.byAffected[c[1]] = L.byAffected[c[1]] || []).push(ci); });
      for (var b = 0; b < L.basis.length; b += 3) (L.basisOut[L.basis[b]] = L.basisOut[L.basis[b]] || []).push(L.basis[b + 1]);
      DL = L;
      return DL;
    });
  }
  function loadShard(fi) {
    var n = Math.floor(fi / 4096), key = 'doc_details_' + (n < 10 ? '0' : '') + n;
    if (shards[key]) return Promise.resolve(shards[key]);
    return VL.loadScript('data/' + key + '.js').then(function () { shards[key] = window.VLONTO[key]; return shards[key]; });
  }
  /* document titles are Vietnamese data: on a page in English their element says lang="vi" (and UI text inside it says
     the page language again) */
  var VI_TEXT = /[àáâãèéêìíòóôõùúýăđĩũơưạ-ỹ]/i;
  function viAttr(s) { return VL.i18n.htmlLang() !== 'vi' && VI_TEXT.test(String(s || '')) ? ' lang="vi"' : ''; }
  function pageLangAttr() { var l = VL.i18n.htmlLang(); return l !== 'vi' ? ' lang="' + l + '"' : ''; }
  function docChip(fi) {
    var id = String(DL.ids[fi]), i = D.idx[id];
    var v = VL.VALIDITY[DL.validity_names[DL.validity[fi]]] || VL.VALIDITY.unknown;
    var label = DL.numbers[fi] || VL.short(DL.titles[fi], 34);
    var title = VL.esc((DL.numbers[fi] ? DL.numbers[fi] + ' · ' : '') + DL.titles[fi] + (DL.year[fi] > 0 ? ' (' + DL.year[fi] + ')' : ''));
    var la = viAttr(DL.titles[fi]);
    return '<button type="button" class="linkish" data-doc="' + VL.esc(id) + '" title="' + title + '"' + la + '><span class="swatch" style="background:' + v.v + '"></span>' + VL.esc(label) +
      (i == null ? ' <span class="muted-small"' + (la ? pageLangAttr() : '') + '>' + VL.UH('net.chip.full') + '</span>' : '') + '</button>';
  }
  function chipList(list, max) {
    max = max || 12;
    var h = '<div class="chip-list">' + list.slice(0, max).map(docChip).join('') + '</div>';
    if (list.length > max) h += '<p class="muted-small">' + VL.UH('net.more', { n: VL.fmt(list.length - max) }) + '</p>';
    return h;
  }
  function chainHtml(fi) {
    var chain = replacementChain(fi);
    if (!chain) return '';
    var items = chain.map(function (x) {
      var lab = (DL.numbers[x] || VL.short(DL.titles[x], 24)) + (DL.year[x] > 0 ? ' (' + DL.year[x] + ')' : ''), la = viAttr(lab);
      return x === fi ? '<span class="cur"' + la + '>' + VL.esc(lab) + '</span>' : '<button type="button" class="linkish" data-doc="' + VL.esc(String(DL.ids[x])) + '"' + la + '>' + VL.esc(lab) + '</button>';
    });
    return '<h3>' + VL.UH('net.chain') + '</h3><div class="chain">' + items.join('<span class="arrow" aria-hidden="true">→</span>') + '</div>';
  }
  /* panel helpers: a field label (one language), a control's Vietnamese tooltip in EN–VI, a count that picks the
     singular of the English (en_one) */
  function dt(k, vars) { return '<dt>' + VL.UH(k, vars) + '</dt>'; }
  /* which evidence set the validity (pipeline/validity.py evidence_source): the code in English as in v1, a Vietnamese
     description in VI */
  var EVIDENCE = { status: 'net.ev.status', text: 'net.ev.text', 'status+text': 'net.ev.statusText', none: 'net.ev.none' };
  function evidenceText(c) { return EVIDENCE[c] ? VL.U(EVIDENCE[c]) : c; }
  function tipAttr(k, vars) { var t = VL.tip(k, vars); return t ? ' title="' + VL.esc(t) + '"' : ''; }
  function nv(c) { return c === 1 ? 1 : VL.fmt(c); }
  function actBtn(act, k) { return '<button class="btn btn-xs" type="button" data-act="' + act + '"' + tipAttr(k) + '>' + VL.UH(k) + '</button>'; }
  function validityBox(v, fi, row) {
    var V = VL.VALIDITY[v] || VL.VALIDITY.unknown;
    var asof = (window.VLONTO.site_meta && window.VLONTO.site_meta.validity_as_of) || '2026-11-08';
    var replacedBy = (DL.byAffected[fi] || []).filter(function (ci) { return DL.changes[ci][2] === 0 || DL.changes[ci][2] === 2; });
    var list = replacedBy.slice(0, 3).map(function (ci) {
      return '<button type="button" class="linkish" data-doc="' + VL.esc(String(DL.ids[DL.changes[ci][0]])) + '">' + VL.esc(DL.numbers[DL.changes[ci][0]] || VL.U('net.laterAct')) + '</button>' +
        (DL.changes[ci][3] ? ' ' + VL.UH('net.fromDate', { date: DL.changes[ci][3] }) : '');
    }).join(', ');
    var by = replacedBy.length ? ' ' + VL.UH('net.replacedBy', null, { html: { list: list } }) : '';
    function strong(k) { return '<strong>' + VL.UH(k) + '</strong>'; }
    var h;
    if (v === 'superseded') h = '<div class="warn-scene" role="note">' + strong('net.v.superseded') + ' ' + VL.UH('net.v.supersededText') + by + '</div>';
    else if (v === 'expired') h = '<div class="warn-scene" role="note">' + strong('net.v.expired') + (row && row[2] ? ' ' + VL.UH('net.v.since', { date: row[2] }) : '') + ' ' + VL.UH('net.v.perSource') + by + '</div>';
    else if (v === 'not_applicable') h = '<div class="warn-scene" role="note">' + strong('net.v.notApplicable') + ' ' + VL.UH('net.v.perSourceStatus') + by + '</div>';
    else if (v === 'not_yet_effective') h = '<div class="muted-scene" role="note">' + strong('net.v.notYet') + (row && row[1] ? VL.UH('net.v.effectiveFrom', { date: row[1] }) : '') + '.</div>';
    else if (v === 'unknown') h = '<div class="muted-scene" role="note">' + strong('net.v.unknown') + ' ' + VL.UH('net.v.unknownText') + '</div>';
    else h = '<div class="ok-scene" role="note"><strong>' + VL.esc(VL.cap(VL.U(V))) + '</strong> ' + VL.UH('net.v.derived', { date: asof }) + (v !== 'in_force' ? ' ' + VL.UH('net.v.amended') : '') + '</div>';
    if (row && row[7]) h += '<div class="warn-scene" role="note">' + VL.UH('net.v.conflict') + '</div>';
    return h;
  }
  function changeGroups(fi, row, shard) {
    var h = '';
    var groups = [];
    KINDS.forEach(function (k, ki) {
      var act = (DL.byActing[fi] || []).filter(function (ci) { return DL.changes[ci][2] === ki; });
      var aff = (DL.byAffected[fi] || []).filter(function (ci) { return DL.changes[ci][2] === ki; });
      var C = VL.CHANGE[k];
      if (act.length) groups.push([VL.pair(C.activeVi, C.active), act.map(function (ci) { return DL.changes[ci][1]; }), null]);
      if (aff.length) groups.push([VL.pair(C.passiveVi, C.passive), aff.map(function (ci) { return DL.changes[ci][0]; }), aff]);
    });
    groups.forEach(function (g) {
      h += '<h3>' + VL.UH(g[0]) + ' (' + VL.fmt(g[1].length) + ')</h3>' + chipList(g[1], 10);
      if (g[2] && shard) {
        var ev = g[2].slice(0, 2).map(function (ci) { return shard.evidence[String(ci)]; }).filter(Boolean);
        ev.forEach(function (e) { h += '<p class="evidence" lang="vi">“' + VL.esc(VL.short(e, 220)) + '”</p>'; });
      }
    });
    return h;
  }
  /* the document's details: field labels and sentences in one language, values (type, issuer, area, legal force,
     validity) as pairs; the title and the source status stay as the source writes them (Vietnamese) */
  var panelArgs = null;
  function docPanel(i, fi, sh) {
    panelArgs = [i, fi, sh];
    var id = D.ids[i], t = D.net.types[D.type[i]] || {}, v = D.net.validity[D.validity[i]] || 'unknown', V = VL.VALIDITY[v] || VL.VALIDITY.unknown;
    var row = null;
    if (sh && fi != null) row = sh.rows[fi - sh.start];
    var issuers = (row && row[5] && row[5].length ? row[5] : (D.issuer[i] >= 0 ? [D.issuer[i]] : [])).map(function (x) { var r = D.net.issuers[x]; return r ? VL.TH(VL.pair(r[1], r[2])) : ''; }).filter(Boolean);
    var area = D.net.areas[D.area[i]];
    var rk = (D.net.ranks || [])[D.rank[i]] || {};
    var title = row && row[8] ? row[8] : D.title[i];
    var tp = VL.pair(t.vi || '', t.en || '');
    var h = '<button class="btn btn-xs panel-close" type="button" data-act="close" aria-label="' + VL.esc(VL.U('net.close')) + '"' + tipAttr('net.close') + '>' + VL.ICON.close + '</button>';
    h += '<div class="panel-kind"><span class="badge"><span class="swatch" style="background:' + VL.typeVar(t.code) + '"></span>' + VL.TH(tp) + '</span>' +
      '<span class="badge"><span class="swatch" style="background:' + V.v + '"></span>' + VL.TH(V) + '</span></div>';
    h += '<h2 lang="vi">' + VL.esc(title) + '</h2>';
    h += '<p class="vi"><span class="nowrap">' + (D.num[i] ? VL.esc(D.num[i]) : VL.TH('net.noNumber')) + '</span>' + (D.year[i] > 0 ? ' · ' + D.year[i] : '') + '</p>';
    h += '<dl class="kv">';
    h += dt('net.k.number') + '<dd class="mono nowrap">' + VL.esc(D.num[i] || '–') + '</dd>';
    h += dt('net.k.type') + '<dd>' + (t.en || t.vi ? VL.TH(tp) : '–') + '</dd>';
    h += dt('net.k.issuer') + '<dd>' + (issuers.length ? issuers.join('; ') : '–') + '</dd>';
    h += dt('net.k.area') + '<dd>' + (area ? VL.TH(VL.pair(area[1], area[2])) : '–') + '</dd>';
    h += dt('net.k.force') + '<dd>' + VL.TH('net.rank.label', { r: D.rank[i], name: VL.pair(rk.vi || rk.en || '', rk.en || '') }) + '</dd>';
    if (row) {
      h += dt('net.k.issued') + '<dd class="nowrap">' + VL.esc(row[0] || '–') + '</dd>';
      h += dt('net.k.inForceFrom') + '<dd class="nowrap">' + VL.esc(row[1] || '–') + '</dd>';
      if (row[2]) h += dt('net.k.noLonger') + '<dd class="nowrap">' + VL.esc(row[2]) + '</dd>';
      if (row[3]) h += dt('net.k.sourceStatus') + '<dd lang="vi">' + VL.esc(row[3]) + '</dd>';
    }
    h += dt('net.k.validity') + '<dd>' + VL.TH(V) + (row && row[6] ? '<div class="muted-small">' + VL.UH('net.k.evidence', { e: evidenceText(row[6]) }) + '</div>' : '') + '</dd>';
    h += '</dl>';
    if (!DL || fi == null) return h + '<p class="muted-small">' + VL.UH('net.loadingDetails') + '</p>';
    h += validityBox(v, fi, row);
    h += chainHtml(fi);
    h += changeGroups(fi, row, sh);
    var bo = DL.basisOut[fi] || [];
    if (bo.length) h += '<h3>' + VL.UH('net.h.basis', { n: VL.fmt(bo.length) }) + '</h3>' + chipList(bo, 10);
    var C = DL.counts;
    h += '<h3>' + VL.UH('net.h.links') + '</h3><dl class="kv">' +
      dt('net.k.basisFor') + '<dd>' + VL.UH('net.v.documents', { n: nv(C.basis_in[fi]) }) + '</dd>' +
      dt('net.k.citations') + '<dd>' + VL.UH('net.v.citations', { a: VL.fmt(C.cite_out[fi]), b: VL.fmt(C.cite_in[fi]) }) + '</dd>' +
      dt('net.k.qa') + '<dd>' + VL.UH('net.v.qa', { n: VL.fmt(C.qa[fi]) }) + '</dd>' +
      dt('net.k.news') + '<dd>' + VL.UH('net.v.news', { n: VL.fmt(C.news[fi]) }) + '</dd>' +
      dt('net.k.articles') + '<dd>' + VL.fmt(C.n_articles[fi]) + '</dd></dl>';
    h += '<h3>' + VL.UH('net.h.source') + '</h3><dl class="kv">';
    if (row && row[4]) {
      var url = row[4].charAt(0) === '=' ? row[4].slice(1) : sh.url_prefix + row[4];
      h += dt('net.k.source') + '<dd><a href="' + VL.esc(url) + '" target="_blank" rel="noopener"' + tipAttr('net.readSource') + '>' + VL.UH('net.readSource') + '</a></dd>';
    }
    var iri = VL.NS.id + 'document/' + id;
    h += '<dt>IRI</dt><dd><span class="iri">' + VL.wbr(iri) + '</span></dd></dl>';
    h += '<div class="panel-actions">' + actBtn('focus', 'net.focus') + actBtn('hops', state.hops === 1 ? 'net.show2' : 'net.show1') +
      '<button class="btn btn-xs" type="button" data-copy="' + VL.esc(iri) + '"' + tipAttr('net.copyIri') + '>' + VL.UH('net.copyIri') + '</button>' +
      (D.rank[i] <= 2 ? '<a class="btn btn-xs" href="sparql.html#q=' + encodeURIComponent('PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\nSELECT ?p ?o WHERE {\n  <' + iri + '> ?p ?o\n}') + '"' + tipAttr('net.querySparql') + '>' +
        VL.UH('net.querySparql') + '</a>' : '') + '</div>';
    return h;
  }
  function select(i, fly) {
    if (i < 0 || !D) return;
    state.sel = i;
    chainIdx = [];
    if (chainTrace) { chainTrace.setPaths([]); M.chainTraceDocs = 0; }
    computeEgo();
    var r = 0, n = 0;
    for (var j = 0; j < D.N; j++) if (D.ego[j] === 1) {
      var dx = D.pos[3 * j] - D.pos[3 * i], dy = D.pos[3 * j + 1] - D.pos[3 * i + 1], dz = D.pos[3 * j + 2] - D.pos[3 * i + 2];
      r += Math.sqrt(dx * dx + dy * dy + dz * dz); n++;
    }
    openPanel(docPanel(i, null, null));
    if (fly !== false) flyTo(i, n ? Math.min(1400, 0.9 * r / n + 120) : 420);
    M.selected = D.ids[i];
    M.panelTitle = D.title[i];
    var token = {};
    select.token = token;
    loadLinks().then(function () {
      var fi = DL.idx[D.ids[i]];
      return loadShard(fi).then(function (sh) {
        if (select.token !== token) return;
        openPanel(docPanel(i, fi, sh), true);
        drawChain(fi);
        M.panelLoaded = D.ids[i];
      });
    }).catch(function (e) { console.error(e); });
  }
  function clearSelection() {
    state.sel = -1;
    if (D) { D.ego.fill(0); applyAlpha(); }
    if (hlObj) { scene.remove(hlObj); hlObj.geometry.dispose(); hlObj.material.dispose(); hlObj = null; }
    if (trace) { trace.setPaths([]); chainTrace.setPaths([]); egoLines.setPaths([]); M.traceSegments = 0; M.chainTraceDocs = 0; M.egoLines = 0; }
    chainIdx = [];
    egoInc = [];
    hoverIdx = -1;
    hoverLabel = null;
    M.hoverDoc = null;
    panelArgs = null;
    clearLabels(true);
    closePanel();
    scheduleCull();
    needsRender = true;
  }
  function openPanel(html, keepScroll) {
    var st = panel.scrollTop;
    panel.innerHTML = html;
    panel.classList.remove('hidden');
    stage.classList.add('panel-open');
    if (keepScroll) panel.scrollTop = st; else panel.scrollTop = 0;
    relayout();
  }
  function closePanel() {
    panel.classList.add('hidden');
    stage.classList.remove('panel-open');
    relayout();
  }
  function relayout() { requestAnimationFrame(function () { onResize(); }); }
  panel.addEventListener('click', function (e) {
    var b = e.target.closest('button, a');
    if (!b) return;
    if (b.hasAttribute('data-doc')) selectById(b.getAttribute('data-doc'));
    else if (b.hasAttribute('data-copy')) VL.copy(b.getAttribute('data-copy'));
    else if (b.getAttribute('data-act') === 'close') clearSelection();
    else if (b.getAttribute('data-act') === 'focus' && state.sel >= 0) flyTo(state.sel);
    else if (b.getAttribute('data-act') === 'hops') setHops(state.hops === 1 ? 2 : 1);
  });
  function selectById(id) {
    id = String(id);
    if (D && D.idx[id] != null) { select(D.idx[id], true); return Promise.resolve(true); }
    if (D && D.name === 'lite') {
      VL.toast(VL.U('net.toast.loadingFull'));
      return switchDataset('full').then(function () { if (D.idx[id] != null) { select(D.idx[id], true); return true; } return false; });
    }
    VL.toast(VL.U('net.toast.notFound', { id: id }));
    return Promise.resolve(false);
  }
  window.VLApp.selectById = selectById;
  /* tests: hover a document (id, or null to end the hover) as the pointer would; returns the traced segments */
  window.VLApp.hoverDoc = function (id) { var i = id == null || !D ? -1 : D.idx[String(id)]; setHover(i == null ? -1 : i); return M.traceSegments; };
  /* the camera (position and orbit target, rounded): tests check that a language switch keeps it */
  function camState(cam, target) {
    if (!cam || !target) return null;
    return [cam.position.x, cam.position.y, cam.position.z, target.x, target.y, target.z].map(function (v) { return Math.round(v * 1000) / 1000; });
  }
  window.VLApp.camera = function () { return camera && controls ? camState(camera, controls.target) : null; };
  window.VLApp.state = function () {
    return { dataset: D && D.name, nodes: D && D.N, selected: state.sel >= 0 ? D.ids[state.sel] : null, panelOpen: !panel.classList.contains('hidden'),
      panelText: panel.textContent, egoHop1: M.egoHop1, labelsShown: M.labelsShown };
  };

  /* ------------------------------------------------------------------ search */
  var foldNum = null, foldTitle = null;
  function searchSource(q) {
    if (!D) return [];
    if (!foldNum || foldNum.length !== D.N) { foldNum = D.num.map(VL.fold); foldTitle = D.title.map(VL.fold); }
    var qf = VL.fold(q.trim());
    if (!qf) return [];
    var res = [];
    for (var i = 0; i < D.N; i++) {
      var s = VL.score(qf, foldNum[i]) * 2;
      if (s < 160) s = Math.max(s, VL.score(qf, foldTitle[i]));
      if (s > 0) res.push([s + (5 - D.rank[i]) * 2 + Math.min(10, Math.log2(1 + D.degree[i])), i]);
    }
    res.sort(function (a, b) { return b[0] - a[0]; });
    return res.slice(0, 12).map(function (x) {
      var i = x[1], t = D.net.types[D.type[i]] || {}, v = VL.VALIDITY[D.net.validity[D.validity[i]]] || VL.VALIDITY.unknown;
      return { i: i, main: D.num[i] || VL.short(D.title[i], 40), sub: VL.short(D.title[i], 64) + (D.year[i] > 0 ? ' · ' + D.year[i] : ''), kind: VL.U(VL.pair(t.vi, t.en)), color: v.v };
    });
  }
  function onPick(it) { select(it.i, true); if (VL.isMobile()) setSide(false); }
  VL.combobox({ input: VL.$('#net-search'), list: VL.$('#net-suggest'), source: searchSource, onPick: onPick, max: 12 });
  VL.combobox({ input: VL.$('#net-search-m'), list: VL.$('#net-suggest-m'), source: searchSource, onPick: onPick, max: 12 });
  window.VLApp.search = function (q) { var r = searchSource(q); if (r.length) onPick(r[0]); return r.map(function (x) { return x.main; }); };

  /* ------------------------------------------------------------------ controls */
  function setSide(open) { app.classList.toggle('side-open', open); VL.$('#btn-side-m').setAttribute('aria-expanded', open ? 'true' : 'false'); }
  VL.$('#btn-side-m').addEventListener('click', function () { setSide(!app.classList.contains('side-open')); });
  function pressed(sel, attr, val) { VL.$$(sel).forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute(attr) === String(val) ? 'true' : 'false'); }); }
  VL.$$('[data-ds]').forEach(function (b) { b.addEventListener('click', function () { switchDataset(b.getAttribute('data-ds')); }); });
  VL.$$('[data-color]').forEach(function (b) {
    b.addEventListener('click', function () { state.colorBy = b.getAttribute('data-color'); pressed('[data-color]', 'data-color', state.colorBy); applyColors(); M.colorBy = state.colorBy; });
  });
  function setHops(h) {
    state.hops = h;
    pressed('[data-hops]', 'data-hops', h);
    if (state.sel >= 0) { computeEgo(); select(state.sel, false); }
  }
  VL.$$('[data-hops]').forEach(function (b) { b.addEventListener('click', function () { setHops(+b.getAttribute('data-hops')); }); });
  VL.$('#show-layers').addEventListener('change', function (e) {
    state.layers = e.target.checked;
    layerGroup.visible = state.layers;
    buildLayerLabels();
    scheduleCull();
    needsRender = true;
  });
  /* the citation layer joins documents, not articles: one line per citing -> cited document pair. Relate that count to the
     citation links of the knowledge graph, which are recorded at document and article level. */
  function citationNote() {
    var kg = ((window.VLONTO || {}).site_meta || {}).kg_counts || {}, eo = edgeObjs.citation;
    var s = VL.U('net.citeNote.pairs') + (eo ? VL.U('net.citeNote.view', { n: VL.fmt(eo.m) }) : '') + '.';
    if (kg.citation_links) {
      s += VL.U('net.citeNote.kg', { n: VL.fmt(kg.citation_links) }) +
        (kg.citation_links_article_level ? VL.U('net.citeNote.article', { n: VL.fmt(kg.citation_links_article_level) }) : '') + VL.U('net.citeNote.end');
    }
    return s;
  }
  /* link swatches drawn as the links are: the S-curve between two levels (vertical tangents, control points at 45 % of the
     height difference); the trace as its navy core on the gold halo */
  var SWATCH_PATH = 'M3 11C3 6.5 19 5.5 19 1';
  function curveSwatch(color) {
    return '<svg class="swatch-curve' + (color ? '' : ' trace') + '" viewBox="0 0 22 12" aria-hidden="true">' + (color ?
      '<path d="' + SWATCH_PATH + '" style="stroke:' + color + '"/>' :
      '<path class="halo" d="' + SWATCH_PATH + '"/><path class="core" d="' + SWATCH_PATH + '"/>') + '</svg>';
  }
  function renderEdgeToggles() {
    var host2 = VL.$('#edge-toggles');
    var h = EDGE_KEYS.map(function (k) {
      var lab = k === 'basis' ? VL.EDGE.basis : k === 'citation' ? VL.EDGE.citation : VL.CHANGE[k];
      /* a control: one language, the Vietnamese as its tooltip in EN–VI (the citation toggle keeps its note instead) */
      var name = VL.pair(lab.vi, lab.en), vt = VL.tip(name);
      var eo = edgeObjs[k], tip = k === 'citation' ? ' title="' + VL.esc(citationNote()) + '"' : (vt ? ' title="' + VL.esc(vt) + '"' : '');
      return '<label class="check"' + tip + '><input type="checkbox" data-edge="' + k + '"' + (state.edges[k] ? ' checked' : '') + '>' +
        curveSwatch(edgeColor(k)) + '<span class="lbl">' + VL.UH(name) +
        (lab.qual ? ' <span class="qual">(' + VL.UH(VL.pair(lab.qualVi, lab.qual)) + ')</span>' : '') + '</span><span class="count">' + (eo ? VL.fmt(eo.m) : '') + '</span></label>';
    }).join('');
    host2.innerHTML = h + '<p class="side-note" id="citation-note">' + VL.esc(citationNote()) + '</p>';
  }
  VL.$('#edge-toggles').addEventListener('change', function (e) {
    var k = e.target.getAttribute('data-edge');
    if (!k) return;
    state.edges[k] = e.target.checked;
    if (edgeObjs[k]) edgeObjs[k].obj.visible = state.edges[k];
    if (state.sel >= 0) computeEgo();
    renderLegend();
    needsRender = true;
  });
  var yFrom = VL.$('#y-from'), yTo = VL.$('#y-to');
  function setupYears() {
    [yFrom, yTo].forEach(function (inp) { inp.min = D.yMin; inp.max = D.yMax; inp.step = 1; });
    yFrom.value = state.y0 == null ? D.yMin : Math.max(D.yMin, state.y0);
    yTo.value = state.y1 == null ? D.yMax : Math.min(D.yMax, state.y1);
    VL.$('#y-from-o').textContent = yFrom.value;
    VL.$('#y-to-o').textContent = yTo.value;
  }
  var yTimer = null;
  function onYear() {
    var a = +yFrom.value, b = +yTo.value;
    if (a > b) { if (this === yFrom) yTo.value = a; else yFrom.value = b; a = +yFrom.value; b = +yTo.value; }
    VL.$('#y-from-o').textContent = a;
    VL.$('#y-to-o').textContent = b;
    state.y0 = a; state.y1 = b;
    clearTimeout(yTimer);
    yTimer = setTimeout(applyFilters, 60);
  }
  yFrom.addEventListener('input', onYear);
  yTo.addEventListener('input', onYear);
  VL.$('#y-unknown').addEventListener('change', function (e) { state.yUnknown = e.target.checked; applyFilters(); });
  VL.$('#btn-reset').addEventListener('click', resetView);
  VL.$('#btn-reset2').innerHTML = VL.ICON.reset;
  VL.$('#btn-reset2').addEventListener('click', resetView);
  VL.$('#btn-legend').innerHTML = VL.ICON.layers;
  VL.$('#btn-legend').addEventListener('click', function () { state.legendOpen = !state.legendOpen; renderLegend(); scheduleCull(); });
  VL.$('#btn-png').addEventListener('click', function () {
    renderer.render(scene, camera);
    renderer.domElement.toBlob(function (b) { VL.downloadBlob(b, 'vlonto-legal-network-3d.png'); VL.toast(VL.U('net.toast.png')); }, 'image/png');
  });
  function resetView() { clearSelection(); fitAll(800); }
  host.addEventListener('keydown', function (e) {
    var k = e.key;
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
    if (e.key === '/' && !typing) { e.preventDefault(); (VL.isMobile() ? VL.$('#net-search-m') : VL.$('#net-search')).focus(); }
    else if (e.key === 'Escape' && !typing) { if (state.sel >= 0) clearSelection(); else if (app.classList.contains('side-open')) setSide(false); }
  });

  /* ------------------------------------------------------------------ legend, hint, status */
  function renderLegend() {
    VL.$('#btn-legend').setAttribute('aria-expanded', state.legendOpen ? 'true' : 'false');
    legendEl.classList.toggle('hidden', !state.legendOpen);
    if (!state.legendOpen || !D) { fitLegend(); return; }
    /* entries as in the paper's legend: "Tiếng Việt · English" in EN–VI, one language in EN or VI, each part shortened */
    function bi(vi, en) { return VL.TH(VL.pair(VL.cap(VL.short(vi || '', 26)), VL.cap(VL.short(en || '', 24)))); }
    function biKey(k) { var e = VL.i18n.get(k) || { vi: '', en: k }; return bi(e.vi, e.en); }
    var items = [], cnt = {};
    if (state.colorBy === 'validity') {
      for (var i = 0; i < D.N; i++) cnt[D.validity[i]] = (cnt[D.validity[i]] || 0) + 1;
      VL.VALIDITY_ORDER.forEach(function (v) {
        var ix = D.net.validity.indexOf(v);
        if (cnt[ix]) items.push([VL.VALIDITY[v].color, VL.VALIDITY[v].vi, VL.VALIDITY[v].en, cnt[ix]]);
      });
    } else if (state.colorBy === 'type') {
      for (var j = 0; j < D.N; j++) cnt[D.type[j]] = (cnt[D.type[j]] || 0) + 1;
      D.net.types.forEach(function (t, ix) { if (cnt[ix]) items.push([VL.TYPE_COLORS[t.code] || TH.typeOther, t.vi, t.en, cnt[ix]]); });
    } else {
      for (var a = 0; a < D.N; a++) cnt[D.area[a]] = (cnt[D.area[a]] || 0) + 1;
      var order = Object.keys(cnt).filter(function (x) { return +x >= 0; }).sort(function (x, y) { return cnt[y] - cnt[x]; });
      var nA = TH.areas.length;
      order.slice(0, nA).forEach(function (x) { var ar = D.net.areas[+x]; items.push([areaColor(+x), ar ? ar[1] : x, ar ? ar[2] : x, cnt[x]]); });
      var rest = order.slice(nA).reduce(function (s, x) { return s + cnt[x]; }, 0);
      var oa = VL.i18n.get('net.lg.otherAreas') || {}, na = VL.i18n.get('net.lg.noArea') || {};
      if (rest) items.push([TH.areaOther, oa.vi, oa.en, rest]);
      if (cnt[-1]) items.push([TH.areaNone, na.vi, na.en, cnt[-1]]);
    }
    var h = '<h3>' + biKey({ validity: 'net.lg.validity', type: 'net.lg.type', area: 'net.lg.area' }[state.colorBy]) + '</h3><ul>' + items.map(function (it) {
      return '<li><span class="swatch" style="background:' + it[0] + '"></span>' + bi(it[1], it[2]) + '</li>';
    }).join('') + '</ul>';
    var ek = enabledKinds();
    h += '<div class="legend-sub"><ul>' + ek.map(function (k) {
      var lab = k === 'basis' ? VL.EDGE.basis : k === 'citation' ? VL.EDGE.citation : VL.CHANGE[k];
      return '<li>' + curveSwatch(edgeColor(k)) + bi(lab.vi, lab.en) + '</li>';
    }).join('') + '<li>' + curveSwatch(null) + biKey('net.lg.trace') + '</li></ul></div>';
    legendEl.innerHTML = h;
    M.legendEntries = VL.$$('li', legendEl).length;
    fitLegend();
  }
  /* ------------------------------------------------------------------ theme switch (light / dark): clear colour, point
     fade colour, node colours, edges (rebuilt with the theme palette and opacity), layer planes and every label sprite;
     the camera, filters and selection stay as they are */
  function disposeGroup(g) { g.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); }
  function applyTheme() {
    readTheme();
    if (!renderer) return;
    renderer.setClearColor(TH.bg, 1);
    if (D && pointsObj) {
      VL.rawColor(TH.bg, pointsMat.uniforms.uBg.value);
      pointsMat.uniforms.uRim.value = TH.dark ? 0.7 : 0.84;
      chainTrace.setStyle(VL.traceStyle(P, 1));
      Object.keys(edgeObjs).forEach(function (k) { var o = edgeObjs[k].obj; scene.remove(o); o.geometry.dispose(); o.material.dispose(); });
      edgeObjs = {};
      EDGE_KEYS.forEach(buildEdges);
      if (layerGroup) { scene.remove(layerGroup); disposeGroup(layerGroup); layerGroup = null; }
      buildLayers();          // layer planes + layer labels (clears the node labels)
      applyColors();          // node colours + legend
      applyFilters();         // edge visibility, toggles, neighbourhood edges and labels of the selection
      if (state.sel >= 0 && !panel.classList.contains('hidden')) M.panelThemed = true;
    }
    M.themeRenders = (M.themeRenders || 0) + 1;
    needsRender = true;
  }
  window.addEventListener('vlonto-theme', applyTheme);
  function showHint() { if (VL.store.get('hint-net3d') !== 'off') { VL.$('#hint').classList.remove('hidden'); scheduleCull(); } }
  function hideHint() { var h = VL.$('#hint'); if (h && !h.classList.contains('hidden')) { h.classList.add('hidden'); scheduleCull(); } }
  VL.$('#hint-close').addEventListener('click', function () { hideHint(); VL.store.set('hint-net3d', 'off'); });
  function status() {
    if (!D) return;
    var e = EDGE_KEYS.reduce(function (s, k) { return s + (state.edges[k] && edgeObjs[k] ? (edgeObjs[k].shown || 0) : 0); }, 0);
    statusEl.textContent = VL.U('net.status', { docs: VL.fmt(D.visibleCount), links: VL.fmt(e) }) + (M.fps ? ' · ' + VL.fmt(M.fps) + ' fps' : '');
    fitLegend();
    VL.$('#ds-note').textContent = VL.U(D.name === 'lite' ? 'net.ds.lite' : 'net.ds.full', { n: VL.fmt(D.N) });
  }

  /* ------------------------------------------------------------------ the page's own text that the declarative
     attributes cannot hold (numbers in the mode's format, markup inside a sentence): dataset buttons, hint, paper line,
     canvas role description, meta description */
  var LITE_N = 6000;   // size of the lite subset (data/legal_network_lite.js: rank 0–2 plus the most connected documents)
  function dsCount(name) {
    var V = window.VLONTO || {}, key = name === 'full' ? 'legal_network' : 'legal_network_lite';
    if (V[key] && V[key].nodes) return V[key].nodes.length;
    return name === 'full' ? (((V.site_meta || {}).kg_counts || {}).documents || null) : LITE_N;
  }
  function renderStatic() {
    VL.$$('[data-ds]').forEach(function (b) {
      var ds = b.getAttribute('data-ds'), k = 'net.dataset.' + ds, vars = { n: VL.fmt(dsCount(ds)) }, t = VL.tip(k, vars);
      b.textContent = VL.U(k, vars);
      if (t) b.setAttribute('title', t); else b.removeAttribute('title');
    });
    var md = document.querySelector('meta[name="description"]');
    if (md) md.setAttribute('content', VL.U('net.page.description', { n: VL.fmt(dsCount('full')) }));
    var hb = VL.$('#hint-body');
    if (hb) hb.innerHTML = VL.UH('net.hint.body', null, { html: { act: '<span class="desk-only">' + VL.UH('net.hint.click') + '</span><span class="touch-only">' +
      VL.UH('net.hint.tap') + '</span>', num: '<span class="nowrap">45/2019/QH14</span>' } });
    var pp = VL.$('#net-paper');
    if (pp) pp.innerHTML = VL.UH('net.paper', { release: VL.releaseLabel() }, { html: { title: '<a href="' + VL.esc(VL.PAPER.url) +
      '" target="_blank" rel="noopener" data-paper-link="side" lang="en">' + VL.esc(VL.PAPER.title) + '</a>' } });
    host.setAttribute('aria-roledescription', VL.U('net.canvas.role'));
  }
  renderStatic();
  /* language switch (js/i18n.js 'vl:lang'): layer and node call-outs, legend, link toggles, status lines, the open
     panel and the page's own text are rebuilt in the new mode, then the call-outs are placed again; the camera, the
     filters, the selection and the hovered neighbour stay */
  function applyLang() {
    renderStatic();
    tip.classList.add('hidden');
    M.langRenders = (M.langRenders || 0) + 1;
    if (!D || !renderer || !pointsObj) { M.labelsLang = VL.lang(); return; }
    buildLayerLabels();
    if (state.sel >= 0) egoLabels(); else scheduleCull();
    renderEdgeToggles();
    renderLegend();
    status();
    if (panelArgs && state.sel >= 0 && !panel.classList.contains('hidden')) openPanel(docPanel(panelArgs[0], panelArgs[1], panelArgs[2]), true);
    needsRender = true;
  }
  document.addEventListener('vl:lang', applyLang);

  /* ------------------------------------------------------------------ dataset switching + start */
  function switchDataset(name) {
    var veil = VL.$('#veil');
    if (!veil) {
      veil = VL.el('div', { 'class': 'loading-veil', id: 'veil' }, '<div><div class="spin"></div><span id="veil-text"></span></div>');
      stage.appendChild(veil);
    }
    VL.$('#veil-text').textContent = name === 'full' ? VL.U('net.loadingAll', { n: VL.fmt(dsCount('full')) }) : VL.U('net.loadingN', { n: VL.fmt(dsCount('lite')) });
    var keepSel = state.sel >= 0 && D ? D.ids[state.sel] : null;
    clearSelection();
    var t0 = performance.now();
    return loadDataset(name).then(function (net) {
      return new Promise(function (res) { setTimeout(function () { res(net); }, 20); });
    }).then(function (net) {
      var t1 = performance.now();
      D = prepare(net, name);
      foldNum = null;
      state.ds = name;
      if (state.edges.citation === null || state.edges.citation === undefined || !switchDataset.userSetCitation) state.edges.citation = (name === 'lite');
      pressed('[data-ds]', 'data-ds', name);
      setupYears();
      buildScene();
      var t2 = performance.now();
      M.dataset = name;
      M.nodes = D.N;
      M.edges = EDGE_KEYS.reduce(function (s, k) { return s + edgeObjs[k].m; }, 0);
      M.edgeCost = edgeCost();
      M.loadMs = Math.round(t1 - t0);
      M.buildMs = Math.round(t2 - t1);
      if (!switchDataset.fitted) { fitAll(0); switchDataset.fitted = true; }
      var v = VL.$('#veil');
      if (v) v.remove();
      renderLegend();
      status();
      if (keepSel && D.idx[keepSel] != null) select(D.idx[keepSel], false);
      return D;
    });
  }
  VL.$('#edge-toggles').addEventListener('change', function (e) { if (e.target.getAttribute('data-edge') === 'citation') switchDataset.userSetCitation = true; });

  VL.fontsReady().then(function () {
    initThree();
    bindPointer();
    return switchDataset(state.ds);
  }).then(function () {
    return new Promise(function (res) { requestAnimationFrame(function () { requestAnimationFrame(res); }); });
  }).then(function () {
    showHint();
    var p = VL.params();
    var go = p.doc ? selectById(p.doc) : (p.q ? Promise.resolve(window.VLApp.search(p.q)) : Promise.resolve());
    return go;
  }).then(function () {
    return measureFps(1500);
  }).then(function (fps) {
    M.fps = fps;
    status();
    VL.setReady({ fps: fps, webglRenderer: M.webglRenderer });
  }).catch(function (e) {
    console.error(e);
    var v = VL.$('#veil-text');
    if (v) v.textContent = VL.U('net.loadError', { msg: e && e.message });
  });
  window.addEventListener('hashchange', function () { var p = VL.params(); if (p.doc) selectById(p.doc); });
})();

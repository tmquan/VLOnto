/* VLOnto - 3D Legal Network (raw three.js: GPU points + line segments, precomputed coordinates, no live layout).
   data/legal_network_lite.js (6,000 documents) or data/legal_network.js (40,816) are loaded on demand with <script>
   tags; per-document details (dates, source status, URL, change evidence) come from data/doc_links.js and the
   data/doc_details_NN.js shards (scripts/site/derive_site_data.py). Height = legal-force rank (Constitution on top). */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome({ scene: true });
  M.page = 'network-3d';

  var ZS = 2.2;                      // vertical exaggeration of the legal-force layers
  var KINDS = ['replaced', 'amended', 'repealed', 'partially_repealed', 'partially_expired'];
  var EDGE_KEYS = KINDS.concat(['basis', 'citation']);
  /* normal (not additive) blending: dense legal-basis bundles must stay blue, not saturate to white.
     Per theme: thin lines need a little more opacity on the light background. */
  var EDGE_OPACITY = {
    dark: { replaced: 0.9, amended: 0.72, repealed: 0.85, partially_repealed: 0.72, partially_expired: 0.72, basis: 0.11, citation: 0.07 },
    light: { replaced: 0.9, amended: 0.82, repealed: 0.85, partially_repealed: 0.78, partially_expired: 0.78, basis: 0.13, citation: 0.085 }
  };
  /* scene colours of the current theme (css/site.css: --scene-bg, --label-*, --layer-label-*, --net-plane*, --area-*) */
  var TH = {};
  function readTheme() {
    TH = {
      dark: VL.theme() === 'dark',
      bg: VL.tok('--scene-bg') || '#0a0f1e',
      labelFg: VL.tok('--label-fg') || '#ffffff', labelBg: VL.tok('--label-bg') || 'rgba(9, 14, 30, 0.82)', labelBorder: VL.tok('--label-border') || '',
      selFg: VL.tok('--label-sel-fg') || '#ffffff', selBg: VL.tok('--label-sel-bg') || 'rgba(43, 85, 208, 0.92)',
      layerFg: VL.tok('--layer-label-fg') || '#c9d2ea', layerBg: VL.tok('--layer-label-bg') || 'rgba(20, 30, 62, 0.85)',
      plane: VL.tok('--net-plane') || '#223066', planeOpacity: VL.tokNum('--net-plane-opacity', 0.075),
      planeLine: VL.tok('--net-plane-line') || '#3a4a80', planeLineOpacity: VL.tokNum('--net-plane-line-opacity', 0.55),
      areas: VL.areaColors(), areaNone: VL.tok('--area-none') || '#56627f', areaOther: VL.tok('--area-other') || '#6b7796',
      typeOther: VL.hue('slate')
    };
    M.sceneBg = TH.bg;
  }
  readTheme();
  function edgeOpacity(k) { return EDGE_OPACITY[TH.dark ? 'dark' : 'light'][k] * ((k === 'basis' || k === 'citation') && D && D.N > 20000 ? 0.55 : 1); }
  var FONT = '"Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif';
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host'), panel = VL.$('#panel');
  var tip = VL.$('#tip'), legendEl = VL.$('#legend'), statusEl = VL.$('#status');
  var params = VL.params();
  var state = {
    ds: params.ds === 'full' || params.ds === 'lite' ? params.ds : (VL.isMobile() ? 'lite' : 'full'),
    colorBy: 'validity', hops: 1, lang: 'en', layers: true, sel: -1, legendOpen: !VL.isMobile(),
    edges: { replaced: true, amended: true, repealed: true, partially_repealed: true, partially_expired: true, basis: true, citation: null },
    y0: null, y1: null, yUnknown: true
  };

  var renderer, scene, camera, controls, pointsObj = null, pointsMat = null, edgeObjs = {}, hlObj = null, layerGroup = null, labelGroup = null;
  var D = null, DL = null, shards = {}, frames = 0, needsRender = true, tween = null;

  /* ------------------------------------------------------------------ three setup */
  var PT_VS = [
    'attribute vec3 aColor; attribute float aAlpha; attribute float aSize;',
    'uniform float uScale; varying vec3 vColor; varying float vAlpha;',
    'void main() {',
    '  vColor = aColor; vAlpha = aAlpha;',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  float s = aSize * uScale / max(1.0, -mv.z);',
    '  gl_PointSize = aAlpha < 0.01 ? 0.0 : clamp(s, 2.0, 56.0);',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  var PT_FS = [
    'uniform vec3 uBg; varying vec3 vColor; varying float vAlpha;',
    'void main() {',
    '  vec2 c = gl_PointCoord - vec2(0.5); float d = length(c);',
    '  if (d > 0.5 || vAlpha < 0.01) discard;',
    '  vec3 col = mix(vColor * 0.55, vColor, smoothstep(0.5, 0.3, d));',
    '  gl_FragColor = vec4(mix(uBg, col, vAlpha), 1.0);',
    '}'].join('\n');
  var LN_VS = [
    'attribute vec3 aColor; attribute float aAlpha; varying vec3 vColor; varying float vAlpha;',
    'void main() { vColor = aColor; vAlpha = aAlpha; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }'].join('\n');
  var LN_FS = [
    'uniform float uOpacity; varying vec3 vColor; varying float vAlpha;',
    'void main() { if (vAlpha < 0.01) discard; gl_FragColor = vec4(vColor, vAlpha * uOpacity); }'].join('\n');

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
    scheduleCull();
  }
  function updatePointScale() {
    if (!pointsMat) return;
    pointsMat.uniforms.uScale.value = renderer.domElement.height / (2 * Math.tan(camera.fov * Math.PI / 360));
  }
  function loop(t) {
    requestAnimationFrame(loop);
    if (tween) stepTween(t);
    var moved = controls.update();
    if (needsRender || moved || tween || controls.autoRotate) {
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
  var _c = null;
  function applyColors() {
    if (!_c) _c = new THREE.Color();
    var col = pointsObj.geometry.attributes.aColor.array, cache = {};
    for (var i = 0; i < D.N; i++) {
      var hex = nodeColor(i);
      var c = cache[hex] || (cache[hex] = _c.set(hex).toArray());
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
      uniforms: { uScale: { value: 1 }, uBg: { value: new THREE.Color(TH.bg) } },
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
    var pairs = D.edges[k], m = pairs.length / 2;
    var pos = new Float32Array(m * 6), col = new Float32Array(m * 6), al = new Float32Array(m * 2);
    var c = new THREE.Color(edgeColor(k)), c2 = c.clone().multiplyScalar(0.45);
    for (var e = 0; e < m; e++) {
      var s = pairs[2 * e], t = pairs[2 * e + 1];
      pos[6 * e] = D.pos[3 * s]; pos[6 * e + 1] = D.pos[3 * s + 1]; pos[6 * e + 2] = D.pos[3 * s + 2];
      pos[6 * e + 3] = D.pos[3 * t]; pos[6 * e + 4] = D.pos[3 * t + 1]; pos[6 * e + 5] = D.pos[3 * t + 2];
      col[6 * e] = c.r; col[6 * e + 1] = c.g; col[6 * e + 2] = c.b;
      col[6 * e + 3] = c2.r; col[6 * e + 4] = c2.g; col[6 * e + 5] = c2.b;
      al[2 * e] = 1; al[2 * e + 1] = 1;
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(al, 1));
    g.computeBoundingSphere();
    var mat = new THREE.ShaderMaterial({
      uniforms: { uOpacity: { value: edgeOpacity(k) } }, vertexShader: LN_VS, fragmentShader: LN_FS,
      transparent: true, depthWrite: false, blending: THREE.NormalBlending
    });
    var obj = new THREE.LineSegments(g, mat);
    obj.renderOrder = KINDS.indexOf(k) >= 0 ? 4 : 1;
    obj.visible = !!state.edges[k];
    scene.add(obj);
    edgeObjs[k] = { obj: obj, m: m };
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
  var labels = [];
  function worldPerPx() { return VL.spriteWpp(camera, host.clientHeight); }
  /* px = label box height in CSS px (text is about px / 1.68) */
  function makeLabel(text, opts) {
    var s = VL.TextSprite(text, {
      px: opts.px || 22, weight: opts.weight || '600', color: opts.color || TH.labelFg,
      bg: opts.bg || TH.labelBg, border: opts.border != null ? opts.border : TH.labelBorder,
      cx: opts.cx != null ? opts.cx : 0.5, cy: opts.cy != null ? opts.cy : -0.35
    });
    s.__pri = opts.pri || 0;
    s.__layer = !!opts.layer;
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
  function rankLabel(r) {
    var rk = (D.net.ranks || [])[r] || {};
    var short = { 0: ['Constitution', 'Hiến pháp'], 1: ['Codes, laws, NA resolutions', 'Bộ luật, luật, nghị quyết QH'], 2: ['Ordinances, NASC resolutions', 'Pháp lệnh, nghị quyết UBTVQH'],
      3: ['Decrees, joint resolutions', 'Nghị định, nghị quyết liên tịch'], 4: ['Prime Minister decisions', 'Quyết định của Thủ tướng'], 5: ['Circulars, other decisions', 'Thông tư, quyết định khác'] }[r];
    return (state.lang === 'vi' ? 'Hạng ' : 'Rank ') + r + ' · ' + (short ? short[state.lang === 'vi' ? 1 : 0] : (rk.en || ''));
  }
  function buildLayerLabels() {
    clearLabels(false);
    if (!state.layers) return;
    var E = D.extent * 1.06;
    for (var r = 0; r <= 5; r++) {
      var y = (D.layerZ[r] != null ? D.layerZ[r] : (5 - r) * 150) * ZS;
      addLabel(makeLabel(rankLabel(r), { px: 22, weight: '500', color: TH.layerFg, bg: TH.layerBg, cx: 0, cy: 0.5, pri: 10 - r, layer: true }), -E, y, E);
    }
  }
  var cullTimer = null;
  function scheduleCull() { if (cullTimer) return; cullTimer = setTimeout(function () { cullTimer = null; cullLabels(); }, 80); }
  function obstacles() {
    var hr = host.getBoundingClientRect(), out = [];
    ['#legend', '#hint', '.stage-tools', '#status'].forEach(function (sel) {
      var e = VL.$(sel, stage);
      if (!e || e.classList.contains('hidden') || e.offsetParent === null) return;
      var r = e.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      out.push({ x0: r.left - hr.left - 4, x1: r.right - hr.left + 4, y0: r.top - hr.top - 4, y1: r.bottom - hr.top + 4 });
    });
    return out;
  }
  var _v = null;
  function cullLabels() {
    if (!camera || !labels.length) return;
    if (!_v) _v = new THREE.Vector3();
    camera.updateMatrixWorld();
    var W = host.clientWidth, H = host.clientHeight, k = H / (2 * Math.tan(camera.fov * Math.PI / 360));
    var items = [];
    labels.forEach(function (s) {
      if (s.__layer && !state.layers) { s.layers.set(1); return; }
      s.getWorldPosition(_v);
      _v.project(camera);
      if (_v.z > 1 || _v.z < -1) { s.layers.set(1); return; }
      var sx = (_v.x + 1) / 2 * W, sy = (1 - _v.y) / 2 * H, w = s.scale.x * k, h = s.scale.y * k;
      var x0 = sx - s.center.x * w, y1 = sy + s.center.y * h;
      items.push({ s: s, x0: x0, x1: x0 + w, y0: y1 - h, y1: y1, p: s.__pri });
    });
    items.sort(function (a, b) { return b.p - a.p; });
    var placed = obstacles(), shown = 0;
    items.forEach(function (it) {
      var inside = it.x0 >= 3 && it.x1 <= W - 3 && it.y0 >= 3 && it.y1 <= H - 3, hit = false;
      for (var i = 0; i < placed.length && !hit; i++) {
        var p = placed[i];
        hit = !(it.x1 + 3 < p.x0 || it.x0 - 3 > p.x1 || it.y1 + 2 < p.y0 || it.y0 - 2 > p.y1);
      }
      if (inside && !hit) { it.s.layers.set(0); placed.push(it); shown++; } else it.s.layers.set(1);
    });
    M.labelsShown = shown;
    M.labelsTotal = labels.length;
    needsRender = true;
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
        al[2 * e] = v; al[2 * e + 1] = v; shownE += v;
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
    // highlighted edges: incident to the selection or to hop-1 nodes, inside the neighbourhood
    var pos = [], col = [], c = new THREE.Color();
    kinds.forEach(function (k) {
      var pairs = D.edges[k];
      c.set(edgeColor(k));
      for (var e = 0; e < pairs.length; e += 2) {
        var s = pairs[e], t = pairs[e + 1];
        if (!ego[s] || !ego[t]) continue;
        var core = (ego[s] === 3 || ego[t] === 3) || (state.hops > 1 && (ego[s] === 1 || ego[t] === 1));
        if (!core) continue;
        pos.push(D.pos[3 * s], D.pos[3 * s + 1], D.pos[3 * s + 2], D.pos[3 * t], D.pos[3 * t + 1], D.pos[3 * t + 2]);
        col.push(c.r, c.g, c.b, c.r * 0.55, c.g * 0.55, c.b * 0.55);
        if (pos.length > 6 * 30000) break;
      }
    });
    if (hlObj) { scene.remove(hlObj); hlObj.geometry.dispose(); hlObj.material.dispose(); hlObj = null; }
    if (pos.length) {
      var g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('aColor', new THREE.Float32BufferAttribute(col, 3));
      var al = new Float32Array(pos.length / 3); al.fill(1);
      g.setAttribute('aAlpha', new THREE.BufferAttribute(al, 1));
      hlObj = new THREE.LineSegments(g, new THREE.ShaderMaterial({ uniforms: { uOpacity: { value: 0.95 } }, vertexShader: LN_VS, fragmentShader: LN_FS, transparent: true, depthWrite: false, blending: THREE.NormalBlending }));
      hlObj.renderOrder = 5;
      scene.add(hlObj);
    }
    var cnt = [0, 0, 0];
    for (var i = 0; i < D.N; i++) if (ego[i] === 1) cnt[1]++; else if (ego[i] === 2) cnt[2]++;
    M.egoHop1 = cnt[1]; M.egoHop2 = cnt[2]; M.egoEdges = pos.length / 6;
    applyAlpha();
    egoLabels();
  }
  function egoLabels() {
    clearLabels(true);
    var i0 = state.sel;
    if (i0 < 0) { scheduleCull(); return; }
    var main = (D.num[i0] ? D.num[i0] + ' · ' : '') + VL.short(D.title[i0], 46);
    addLabel(makeLabel(main, { px: 28, weight: '700', pri: 1000, color: TH.selFg, bg: TH.selBg, border: '' }), D.pos[3 * i0], D.pos[3 * i0 + 1], D.pos[3 * i0 + 2]);
    var nb = [];
    for (var i = 0; i < D.N; i++) if (D.ego[i] === 1 || D.ego[i] === 2) nb.push(i);
    nb.sort(function (a, b) { return (D.ego[a] - D.ego[b]) || (D.degree[b] - D.degree[a]); });
    nb.slice(0, 40).forEach(function (j, r) {
      addLabel(makeLabel(D.num[j] || VL.short(D.title[j], 30), { px: 22, weight: '600', pri: 500 - r - (D.ego[j] === 2 ? 100 : 0) }), D.pos[3 * j], D.pos[3 * j + 1], D.pos[3 * j + 2]);
    });
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
        M.fpsSamples = (M.fpsSamples || []).concat([{ dataset: D.name, fps: fps }]);
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
        if (i < 0) { tip.classList.add('hidden'); return; }
        var t = D.net.types[D.type[i]] || {}, v = VL.VALIDITY[D.net.validity[D.validity[i]]] || VL.VALIDITY.unknown;
        tip.innerHTML = '<b>' + VL.esc(D.num[i] || '–') + '</b> ' + VL.esc(VL.short(D.title[i], 60)) +
          '<div class="t-sub">' + VL.esc(t.en || '') + (D.year[i] > 0 ? ' · ' + D.year[i] : '') + ' · ' + VL.esc(v.en) + '</div>';
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
  function docChip(fi) {
    var id = String(DL.ids[fi]), i = D.idx[id];
    var v = VL.VALIDITY[DL.validity_names[DL.validity[fi]]] || VL.VALIDITY.unknown;
    var label = DL.numbers[fi] || VL.short(DL.titles[fi], 34);
    var title = VL.esc((DL.numbers[fi] ? DL.numbers[fi] + ' · ' : '') + DL.titles[fi] + (DL.year[fi] > 0 ? ' (' + DL.year[fi] + ')' : ''));
    return '<button type="button" class="linkish" data-doc="' + VL.esc(id) + '" title="' + title + '"><span class="swatch" style="background:' + v.v + '"></span>' + VL.esc(label) +
      (i == null ? ' <span class="muted-small">(full)</span>' : '') + '</button>';
  }
  function chipList(list, max) {
    max = max || 12;
    var h = '<div class="chip-list">' + list.slice(0, max).map(docChip).join('') + '</div>';
    if (list.length > max) h += '<p class="muted-small">and ' + VL.fmt(list.length - max) + ' more</p>';
    return h;
  }
  function chainHtml(fi) {
    var replaces = function (x) { return (DL.byActing[x] || []).filter(function (ci) { return DL.changes[ci][2] === 0; }).map(function (ci) { return DL.changes[ci][1]; }); };
    var replacedBy = function (x) { return (DL.byAffected[x] || []).filter(function (ci) { return DL.changes[ci][2] === 0; }).map(function (ci) { return DL.changes[ci][0]; }); };
    var back = [], fwd = [], seen = {}, cur = fi;
    seen[fi] = 1;
    for (var s = 0; s < 8; s++) { var r = replaces(cur).filter(function (x) { return !seen[x]; }); if (!r.length) break; r.sort(function (a, b) { return DL.year[b] - DL.year[a]; }); cur = r[0]; seen[cur] = 1; back.unshift(cur); }
    cur = fi;
    for (var t = 0; t < 8; t++) { var q = replacedBy(cur).filter(function (x) { return !seen[x]; }); if (!q.length) break; q.sort(function (a, b) { return DL.year[a] - DL.year[b]; }); cur = q[0]; seen[cur] = 1; fwd.push(cur); }
    if (!back.length && !fwd.length) return '';
    var items = back.concat([fi], fwd).map(function (x) {
      var lab = (DL.numbers[x] || VL.short(DL.titles[x], 24)) + (DL.year[x] > 0 ? ' (' + DL.year[x] + ')' : '');
      return x === fi ? '<span class="cur">' + VL.esc(lab) + '</span>' : '<button type="button" class="linkish" data-doc="' + VL.esc(String(DL.ids[x])) + '">' + VL.esc(lab) + '</button>';
    });
    return '<h3>Replacement chain</h3><div class="chain">' + items.join('<span class="arrow" aria-hidden="true">→</span>') + '</div>';
  }
  function validityBox(v, fi, row) {
    var V = VL.VALIDITY[v] || VL.VALIDITY.unknown;
    var asof = (window.VLONTO.site_meta && window.VLONTO.site_meta.validity_as_of) || '2026-11-08';
    var replacedBy = (DL.byAffected[fi] || []).filter(function (ci) { return DL.changes[ci][2] === 0 || DL.changes[ci][2] === 2; });
    var by = replacedBy.length ? ' Replaced or repealed by ' + replacedBy.slice(0, 3).map(function (ci) { return '<button type="button" class="linkish" data-doc="' + VL.esc(String(DL.ids[DL.changes[ci][0]])) + '">' + VL.esc(DL.numbers[DL.changes[ci][0]] || 'a later act') + '</button>' + (DL.changes[ci][3] ? ' (from ' + VL.esc(DL.changes[ci][3]) + ')' : ''); }).join(', ') + '.' : '';
    var h;
    if (v === 'superseded') h = '<div class="warn-scene" role="note"><strong>Superseded.</strong> An extracted change relation says this document was replaced or repealed; do not rely on it.' + by + '</div>';
    else if (v === 'expired') h = '<div class="warn-scene" role="note"><strong>No longer in force</strong>' + (row && row[2] ? ' since ' + VL.esc(row[2]) : '') + ' according to the source.' + by + '</div>';
    else if (v === 'not_applicable') h = '<div class="warn-scene" role="note"><strong>No longer applicable</strong> according to the source status.' + by + '</div>';
    else if (v === 'not_yet_effective') h = '<div class="muted-scene" role="note"><strong>Not yet in force</strong>' + (row && row[1] ? '; effective from ' + VL.esc(row[1]) : '') + '.</div>';
    else if (v === 'unknown') h = '<div class="muted-scene" role="note"><strong>Validity unknown.</strong> Neither a source status nor an extracted change relation is available. Check the source before relying on this document.</div>';
    else h = '<div class="ok-scene" role="note"><strong>' + VL.esc(V.en.charAt(0).toUpperCase() + V.en.slice(1)) + '</strong> (derived, as of ' + VL.esc(asof) + ').' + (v !== 'in_force' ? ' Some provisions were amended; read the consolidated text at the source.' : '') + '</div>';
    if (row && row[7]) h += '<div class="warn-scene" role="note">The source status says in force, but a later act’s text says it was superseded. Check manually.</div>';
    return h;
  }
  function changeGroups(fi, row, shard) {
    var h = '';
    var groups = [];
    KINDS.forEach(function (k, ki) {
      var act = (DL.byActing[fi] || []).filter(function (ci) { return DL.changes[ci][2] === ki; });
      var aff = (DL.byAffected[fi] || []).filter(function (ci) { return DL.changes[ci][2] === ki; });
      if (act.length) groups.push([VL.CHANGE[k].active, act.map(function (ci) { return DL.changes[ci][1]; }), null]);
      if (aff.length) groups.push([VL.CHANGE[k].passive, aff.map(function (ci) { return DL.changes[ci][0]; }), aff]);
    });
    groups.forEach(function (g) {
      h += '<h3>' + VL.esc(g[0]) + ' (' + g[1].length + ')</h3>' + chipList(g[1], 10);
      if (g[2] && shard) {
        var ev = g[2].slice(0, 2).map(function (ci) { return shard.evidence[String(ci)]; }).filter(Boolean);
        ev.forEach(function (e) { h += '<p class="evidence" lang="vi">“' + VL.esc(VL.short(e, 220)) + '”</p>'; });
      }
    });
    return h;
  }
  function docPanel(i, fi, sh) {
    var id = D.ids[i], t = D.net.types[D.type[i]] || {}, v = D.net.validity[D.validity[i]] || 'unknown', V = VL.VALIDITY[v] || VL.VALIDITY.unknown;
    var row = null;
    if (sh && fi != null) row = sh.rows[fi - sh.start];
    var issuers = (row && row[5] && row[5].length ? row[5] : (D.issuer[i] >= 0 ? [D.issuer[i]] : [])).map(function (x) { var r = D.net.issuers[x]; return r ? (state.lang === 'vi' ? r[1] : r[2] + ' (' + r[1] + ')') : ''; }).filter(Boolean);
    var area = D.net.areas[D.area[i]];
    var rk = (D.net.ranks || [])[D.rank[i]] || {};
    var title = row && row[8] ? row[8] : D.title[i];
    var h = '<button class="btn btn-xs panel-close" type="button" data-act="close" aria-label="Close details">' + VL.ICON.close + '</button>';
    h += '<div class="panel-kind"><span class="badge"><span class="swatch" style="background:' + VL.typeVar(t.code) + '"></span>' + VL.esc(t.en || '') + ' · <span lang="vi">' + VL.esc(t.vi || '') + '</span></span>' +
      '<span class="badge"><span class="swatch" style="background:' + V.v + '"></span>' + VL.esc(state.lang === 'vi' ? V.vi : V.en) + '</span></div>';
    h += '<h2 lang="vi">' + VL.esc(title) + '</h2>';
    h += '<p class="vi"><span class="nowrap">' + VL.esc(D.num[i] || 'no number') + '</span>' + (D.year[i] > 0 ? ' · ' + D.year[i] : '') + '</p>';
    h += '<dl class="kv">';
    h += '<dt>Number</dt><dd class="mono nowrap">' + VL.esc(D.num[i] || '–') + '</dd>';
    h += '<dt>Type</dt><dd>' + VL.esc(t.en || '–') + ' · <span lang="vi">' + VL.esc(t.vi || '') + '</span></dd>';
    h += '<dt>Issuer</dt><dd>' + (issuers.length ? issuers.map(VL.esc).join('; ') : '–') + '</dd>';
    h += '<dt>Area</dt><dd>' + (area ? VL.esc(area[2]) + ' · <span lang="vi">' + VL.esc(area[1]) + '</span>' : '–') + '</dd>';
    h += '<dt>Legal force</dt><dd>Rank ' + D.rank[i] + ' · ' + VL.esc(rk.en || '') + '</dd>';
    if (row) {
      h += '<dt>Issued</dt><dd class="nowrap">' + VL.esc(row[0] || '–') + '</dd>';
      h += '<dt>In force from</dt><dd class="nowrap">' + VL.esc(row[1] || '–') + '</dd>';
      if (row[2]) h += '<dt>No longer in force</dt><dd class="nowrap">' + VL.esc(row[2]) + '</dd>';
      if (row[3]) h += '<dt>Source status</dt><dd lang="vi">' + VL.esc(row[3]) + '</dd>';
    }
    h += '<dt>Validity</dt><dd>' + VL.esc(V.en) + ' · <span lang="vi">' + VL.esc(V.vi) + '</span>' + (row && row[6] ? '<div class="muted-small">evidence: ' + VL.esc(row[6]) + '</div>' : '') + '</dd>';
    h += '</dl>';
    if (!DL || fi == null) return h + '<p class="muted-small">Loading details…</p>';
    h += validityBox(v, fi, row);
    h += chainHtml(fi);
    h += changeGroups(fi, row, sh);
    var bo = DL.basisOut[fi] || [];
    if (bo.length) h += '<h3>Legal basis (' + bo.length + ')</h3>' + chipList(bo, 10);
    var C = DL.counts;
    h += '<h3>Links and use</h3><dl class="kv">' +
      '<dt>Basis for</dt><dd>' + VL.fmt(C.basis_in[fi]) + ' documents</dd>' +
      '<dt>Citations</dt><dd>cites ' + VL.fmt(C.cite_out[fi]) + ' · cited by ' + VL.fmt(C.cite_in[fi]) + ' documents</dd>' +
      '<dt>Q&amp;As</dt><dd>' + VL.fmt(C.qa[fi]) + ' legal Q&amp;As cite it</dd>' +
      '<dt>Court decisions</dt><dd>' + VL.fmt(C.decisions[fi]) + ' apply it</dd>' +
      '<dt>News</dt><dd>' + VL.fmt(C.news[fi]) + ' articles mention it</dd>' +
      '<dt>Articles</dt><dd>' + VL.fmt(C.n_articles[fi]) + '</dd></dl>';
    h += '<h3>Source and identifiers</h3><dl class="kv">';
    if (row && row[4]) {
      var url = row[4].charAt(0) === '=' ? row[4].slice(1) : sh.url_prefix + row[4];
      h += '<dt>Source</dt><dd><a href="' + VL.esc(url) + '" target="_blank" rel="noopener">Read the text at thuvienphapluat.vn</a></dd>';
    }
    var iri = VL.NS.id + 'document/' + id;
    h += '<dt>IRI</dt><dd><span class="iri">' + VL.wbr(iri) + '</span></dd></dl>';
    h += '<div class="panel-actions"><button class="btn btn-xs" type="button" data-act="focus">Focus</button>' +
      '<button class="btn btn-xs" type="button" data-act="hops">' + (state.hops === 1 ? 'Show 2 hops' : 'Show 1 hop') + '</button>' +
      '<button class="btn btn-xs" type="button" data-copy="' + VL.esc(iri) + '">Copy IRI</button>' +
      (D.rank[i] <= 2 ? '<a class="btn btn-xs" href="sparql.html#q=' + encodeURIComponent('PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\nSELECT ?p ?o WHERE {\n  <' + iri + '> ?p ?o\n}') + '">Query in SPARQL</a>' : '') + '</div>';
    return h;
  }
  function select(i, fly) {
    if (i < 0 || !D) return;
    state.sel = i;
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
        M.panelLoaded = D.ids[i];
      });
    }).catch(function (e) { console.error(e); });
  }
  function clearSelection() {
    state.sel = -1;
    if (D) { D.ego.fill(0); applyAlpha(); }
    if (hlObj) { scene.remove(hlObj); hlObj.geometry.dispose(); hlObj.material.dispose(); hlObj = null; }
    clearLabels(true);
    closePanel();
    scheduleCull();
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
      VL.toast('Not in the lite subset: loading the full network');
      return switchDataset('full').then(function () { if (D.idx[id] != null) { select(D.idx[id], true); return true; } return false; });
    }
    VL.toast('Document ' + id + ' is not in the network');
    return Promise.resolve(false);
  }
  window.VLApp.selectById = selectById;
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
      return { i: i, main: D.num[i] || VL.short(D.title[i], 40), sub: VL.short(D.title[i], 64) + (D.year[i] > 0 ? ' · ' + D.year[i] : ''), kind: t.en || '', color: v.v };
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
  VL.$$('[data-lang]').forEach(function (b) {
    b.addEventListener('click', function () {
      state.lang = b.getAttribute('data-lang');
      pressed('[data-lang]', 'data-lang', state.lang);
      buildLayerLabels();
      if (state.sel >= 0) select(state.sel, false); else scheduleCull();
      renderLegend();
    });
  });
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
    var s = 'Citation lines join a citing and a cited document once per pair' + (eo ? ' (' + VL.fmt(eo.m) + ' pairs in this view)' : '') + '.';
    if (kg.citation_links) {
      s += ' The knowledge graph records ' + VL.fmt(kg.citation_links) + ' citation links' +
        (kg.citation_links_article_level ? ', ' + VL.fmt(kg.citation_links_article_level) + ' of them to a specific article' : '') +
        '; links between the same two documents count as one pair here.';
    }
    return s;
  }
  function renderEdgeToggles() {
    var host2 = VL.$('#edge-toggles');
    var h = EDGE_KEYS.map(function (k) {
      var lab = k === 'basis' ? VL.EDGE.basis : k === 'citation' ? VL.EDGE.citation : VL.CHANGE[k];
      var eo = edgeObjs[k], tip = k === 'citation' ? ' title="' + VL.esc(citationNote()) + '"' : '';
      return '<label class="check"' + tip + '><input type="checkbox" data-edge="' + k + '"' + (state.edges[k] ? ' checked' : '') + '>' +
        '<span class="swatch line" style="background:' + edgeColor(k) + '"></span><span class="lbl">' + VL.esc(lab.en) +
        (lab.qual ? ' <span class="qual">(' + VL.esc(lab.qual) + ')</span>' : '') + '</span><span class="count">' + (eo ? VL.fmt(eo.m) : '') + '</span></label>';
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
    renderer.domElement.toBlob(function (b) { VL.downloadBlob(b, 'vlonto-legal-network-3d.png'); VL.toast('PNG exported'); }, 'image/png');
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
    if (!state.legendOpen || !D) return;
    var items = [], cnt = {};
    if (state.colorBy === 'validity') {
      for (var i = 0; i < D.N; i++) cnt[D.validity[i]] = (cnt[D.validity[i]] || 0) + 1;
      VL.VALIDITY_ORDER.forEach(function (v) {
        var ix = D.net.validity.indexOf(v);
        if (cnt[ix]) items.push([VL.VALIDITY[v].color, state.lang === 'vi' ? VL.VALIDITY[v].vi : VL.VALIDITY[v].en, cnt[ix]]);
      });
    } else if (state.colorBy === 'type') {
      for (var j = 0; j < D.N; j++) cnt[D.type[j]] = (cnt[D.type[j]] || 0) + 1;
      D.net.types.forEach(function (t, ix) { if (cnt[ix]) items.push([VL.TYPE_COLORS[t.code] || TH.typeOther, state.lang === 'vi' ? t.vi : t.en, cnt[ix]]); });
    } else {
      for (var a = 0; a < D.N; a++) cnt[D.area[a]] = (cnt[D.area[a]] || 0) + 1;
      var order = Object.keys(cnt).filter(function (x) { return +x >= 0; }).sort(function (x, y) { return cnt[y] - cnt[x]; });
      var nA = TH.areas.length;
      order.slice(0, nA).forEach(function (x) { var ar = D.net.areas[+x]; items.push([areaColor(+x), ar ? (state.lang === 'vi' ? ar[1] : ar[2]) : x, cnt[x]]); });
      var rest = order.slice(nA).reduce(function (s, x) { return s + cnt[x]; }, 0);
      if (rest) items.push([TH.areaOther, state.lang === 'vi' ? 'lĩnh vực khác' : 'other areas', rest]);
      if (cnt[-1]) items.push([TH.areaNone, state.lang === 'vi' ? 'chưa có lĩnh vực' : 'no area', cnt[-1]]);
    }
    var title = { validity: 'Validity', type: 'Document type', area: 'Legal area' }[state.colorBy];
    var h = '<h3>' + title + '</h3><ul>' + items.map(function (it) {
      return '<li><span class="swatch" style="background:' + it[0] + '"></span>' + VL.esc(VL.short(it[1], 26)) + '</li>';
    }).join('') + '</ul>';
    var ek = enabledKinds();
    if (ek.length) {
      h += '<div class="legend-sub"><ul>' + ek.map(function (k) {
        var lab = k === 'basis' ? VL.EDGE.basis : k === 'citation' ? VL.EDGE.citation : VL.CHANGE[k];
        return '<li><span class="swatch line" style="background:' + edgeColor(k) + '"></span>' + VL.esc(state.lang === 'vi' ? lab.vi : lab.en) + '</li>';
      }).join('') + '</ul></div>';
    }
    legendEl.innerHTML = h;
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
      pointsMat.uniforms.uBg.value.set(TH.bg);
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
    statusEl.textContent = VL.fmt(D.visibleCount) + ' documents · ' + VL.fmt(e) + ' links shown' + (M.fps ? ' · ' + M.fps + ' fps' : '');
    VL.$('#ds-note').textContent = D.name === 'lite' ? 'Lite: all documents of legal-force rank 0–2 plus the most connected ones (' + VL.fmt(D.N) + ').' :
      'Full: all ' + VL.fmt(D.N) + ' documents. Citation links are off by default for speed.';
  }

  /* ------------------------------------------------------------------ dataset switching + start */
  function switchDataset(name) {
    var veil = VL.$('#veil');
    if (!veil) {
      veil = VL.el('div', { 'class': 'loading-veil', id: 'veil' }, '<div><div class="spin"></div><span id="veil-text"></span></div>');
      stage.appendChild(veil);
    }
    VL.$('#veil-text').textContent = name === 'full' ? 'Loading all 40,816 documents…' : 'Loading 6,000 documents…';
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
    if (v) v.textContent = 'Could not load the network: ' + (e && e.message);
  });
  window.addEventListener('hashchange', function () { var p = VL.params(); if (p.doc) selectById(p.doc); });
})();

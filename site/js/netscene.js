/* VLOnto - the 3D legal network's drawing, shared by network-3d.html (js/network3d.js) and traces.html (js/traces3d.js):
   one implementation of the dataset (data/legal_network.js, 40,816 documents, or data/legal_network_lite.js, 6,000), the
   documents as GPU points (soft pastel spheres with a depth fade), the links as curves (one instanced draw per link kind,
   the curve evaluated in the vertex shader), the legal-force layer planes, and the link-detail policy (segments per link
   kind by dataset size, coarser on a software renderer; legal-basis and citation links fainter on the full dataset).
   Height = legal-force rank (Constitution on top): scene y = z x ZS, scene z = the layout's y.
   VL.NetScene holds no state; each page keeps its own scene, camera, selection and filters. */
(function () {
  'use strict';
  var VL = window.VL;
  var ZS = 2.2;                      // vertical exaggeration of the legal-force layers
  var KINDS = ['replaced', 'amended', 'repealed', 'partially_repealed', 'partially_expired'];
  var EDGE_KEYS = KINDS.concat(['basis', 'citation']);
  var LITE_N = 6000;                 // size of the lite subset (data/legal_network_lite.js: rank 0–2 plus the most connected documents)
  /* normal (not additive) blending: dense legal-basis bundles must keep their pastel blue, not saturate.
     Per theme: thin pastel lines need more opacity on the white ground. */
  var EDGE_OPACITY = {
    dark: { replaced: 0.9, amended: 0.75, repealed: 0.88, partially_repealed: 0.75, partially_expired: 0.75, basis: 0.12, citation: 0.075 },
    light: { replaced: 0.95, amended: 0.9, repealed: 0.92, partially_repealed: 0.88, partially_expired: 0.88, basis: 0.2, citation: 0.13 }
  };
  function edgeOpacity(k, dark, N) { return EDGE_OPACITY[dark ? 'dark' : 'light'][k] * ((k === 'basis' || k === 'citation') && N > 20000 ? 0.55 : 1); }
  function edgeColor(k) { return k === 'basis' ? VL.EDGE.basis.color : k === 'citation' ? VL.EDGE.citation.color : VL.CHANGE[k].color; }

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
  /* the same curve on the CPU (ribbons of a traced chain, a hovered link, a selection's links; call-out ink) */
  function curvePoint(a, b, t) {
    var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, k = 0.45 * dy;
    var lift = Math.min(BEND * Math.sqrt(dx * dx + dz * dz), LIFT_MAX) * Math.max(0, Math.min(1, 1 - Math.abs(dy) / LAYER_GAP));
    var u = 1 - t, w0 = u * u * u, w1 = 3 * u * u * t, w2 = 3 * u * t * t, w3 = t * t * t;
    return { x: (w0 + w1) * a.x + (w2 + w3) * b.x, y: w0 * a.y + w1 * (a.y + k + lift) + w2 * (b.y - k + lift) + w3 * b.y,
      z: (w0 + w1) * a.z + (w2 + w3) * b.z };
  }
  function curvePts(a, b, n) {
    var out = [];
    for (var i = 0; i <= n; i++) out.push(curvePoint(a, b, i / n));
    return out;
  }
  /* segments per link: fewer for the bulk (basis and citation links, fainter) and on the full dataset; a software
     renderer (no GPU: SwiftShader, llvmpipe) draws coarser curves, so that a frame of the full network costs about what
     straight links did (o: {curves, soft, full}: curves off = straight, soft = software renderer, full = #curves=full) */
  function segsFor(k, N, o) {
    if (!o.curves) return 1;
    var full = N > 20000, change = KINDS.indexOf(k) >= 0;
    if (o.soft && !o.full) return change ? (full ? 4 : 6) : (full ? 2 : 3);
    return change ? (full ? 8 : 10) : (full ? 4 : 6);
  }
  function softGL(name) { return /swiftshader|llvmpipe|softpipe|software|basic render/i.test(name || ''); }
  function curveGeometry(S, A, B, al, col, extent) {
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
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 375 * ZS, 0), 2 * (extent || 1400) + 800 * ZS);
    return g;
  }
  function curveMaterial(instColor, opacity, FOG) {
    return new THREE.ShaderMaterial({
      defines: instColor ? { INST_COLOR: 1 } : {},
      uniforms: { uOpacity: { value: opacity }, uFog: FOG, uColA: { value: new THREE.Color() }, uColB: { value: new THREE.Color() },
        uBend: { value: BEND }, uLiftMax: { value: LIFT_MAX }, uLayer: { value: LAYER_GAP } },
      vertexShader: CV_VS, fragmentShader: CV_FS, transparent: true, depthWrite: false, blending: THREE.NormalBlending
    });
  }
  /* depth fade shared by points and lines: (near, far, strength), from the camera distance */
  function updateFog(FOG, camera, target, extent, dark) {
    var d = camera.position.distanceTo(target), R = extent * 1.1;
    FOG.value.set(Math.max(1, d - 0.4 * R), d + 1.9 * R, dark ? 0.55 : 0.6);
  }

  /* ------------------------------------------------------------------ data */
  function datasetKey(name) { return name === 'full' ? 'legal_network' : 'legal_network_lite'; }
  function load(name) {
    var key = datasetKey(name);
    if (window.VLONTO[key]) return Promise.resolve(window.VLONTO[key]);
    return VL.loadScript('data/' + key + '.js').then(function () { return window.VLONTO[key]; });
  }
  /* documents of a dataset: the full count from site_meta before the file is loaded, the lite subset's size */
  function dsCount(name) {
    var V = window.VLONTO || {}, key = datasetKey(name);
    if (V[key] && V[key].nodes) return V[key].nodes.length;
    return name === 'full' ? (((V.site_meta || {}).kg_counts || {}).documents || null) : LITE_N;
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
  /* point size of a document: its layer (Constitution largest) and its number of links */
  var SIZE_BY_RANK = [44, 22, 16, 11, 10, 9];
  function pointSize(rank, degree) { return (SIZE_BY_RANK[rank] || 9) + 2.6 * Math.log2(1 + degree); }
  function pointSizes(D) {
    var size = new Float32Array(D.N);
    for (var i = 0; i < D.N; i++) size[i] = pointSize(D.rank[i], D.degree[i]);
    return size;
  }
  function layerY(D, r) { return (D.layerZ[r] != null ? D.layerZ[r] : (5 - r) * 150) * ZS; }
  /* one plane at height y, 2E wide, with its outline (TH: plane, planeOpacity, planeLine, planeLineOpacity), added to g */
  function planeAt(y, E, TH, g) {
    g = g || new THREE.Group();
    var plane = new THREE.Mesh(new THREE.PlaneGeometry(2 * E, 2 * E),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(TH.plane), transparent: true, opacity: TH.planeOpacity, depthWrite: false, side: THREE.DoubleSide }));
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = y - 2;
    plane.renderOrder = 0;
    g.add(plane);
    var pts = [new THREE.Vector3(-E, y - 2, -E), new THREE.Vector3(E, y - 2, -E), new THREE.Vector3(E, y - 2, E), new THREE.Vector3(-E, y - 2, E)];
    var outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: new THREE.Color(TH.planeLine), transparent: true, opacity: TH.planeLineOpacity }));
    g.add(outline);
    return g;
  }
  /* the six legal-force layer planes with their outlines */
  function layerPlanes(D, TH) {
    var g = new THREE.Group(), E = D.extent * 1.06;
    for (var r = 0; r <= 5; r++) planeAt(layerY(D, r), E, TH, g);
    return g;
  }
  /* the plane colours of the current theme (css/site.css --net-plane*) */
  function planeTheme() {
    return { plane: VL.tok('--net-plane') || '#c9ced6', planeOpacity: VL.tokNum('--net-plane-opacity', 0.14),
      planeLine: VL.tok('--net-plane-line') || '#d3d7dc', planeLineOpacity: VL.tokNum('--net-plane-line-opacity', 1) };
  }

  VL.NetScene = {
    ZS: ZS, KINDS: KINDS, EDGE_KEYS: EDGE_KEYS, LITE_N: LITE_N, BEND: BEND, LAYER_GAP: LAYER_GAP, LIFT_MAX: LIFT_MAX,
    PT_VS: PT_VS, PT_FS: PT_FS, CV_VS: CV_VS, CV_FS: CV_FS,
    edgeOpacity: edgeOpacity, edgeColor: edgeColor, curvePoint: curvePoint, curvePts: curvePts, segsFor: segsFor, softGL: softGL,
    curveGeometry: curveGeometry, curveMaterial: curveMaterial, updateFog: updateFog,
    datasetKey: datasetKey, load: load, dsCount: dsCount, prepare: prepare, pointSize: pointSize, pointSizes: pointSizes,
    layerY: layerY, layerPlanes: layerPlanes, planeAt: planeAt, planeTheme: planeTheme
  };
})();

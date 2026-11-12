/* node scripts/site/teaser/test_harness.js [path/to/teaser.js]
   Runs teaser.js under node against a stand-in for the network page: real three.js (with its OrbitControls, kept within
   the page's minDistance/maxDistance as network3d.js sets them), js/paper3d.js (trace and line objects), the real
   network data (positions, links, the Labor Code's neighbourhood), and a stub of what the page provides
   (VLApp.capture as network3d.js defines it - the camera swap hands the camera to the controls and updates them -, a
   frame loop that updates the controls and the depth fade on every frame, the metrics, the colour buttons). Its
   renderer rasterises the network's points and the beads as dots wherever they fall inside the camera's clip volume,
   so gl.readPixels sees what the camera would see: a camera pulled in by the controls, or wrong near/far planes, give
   a blank capture here as in the browser. Checks that the harness reaches ready without errors, keeps the orthographic
   camera at the configured pose and distance, fits near/far around the scene and the page's depth fade to the camera,
   widens the trace, fades the context, builds the subtree, answers every capture of the config at its pixel ratio with
   ink (no blank capture) and the diagnostics, and writes anchors that match teaser-core.js. It cannot check the
   shaders' pixels: that is the browser capture's job. */
'use strict';
var fs = require('fs'), path = require('path'), vm = require('vm');
var HERE = __dirname, SITE = path.join(HERE, '..', '..', '..', 'site');
function load(p) { vm.runInThisContext(fs.readFileSync(p, 'utf8'), { filename: p }); }
global.window = global; global.self = global;
global.requestAnimationFrame = function (f) { return setTimeout(function () { f(Date.now()); }, 1); };
var clicks = [];
global.document = { querySelector: function (sel) {
  var m = /data-color="(\w+)"/.exec(sel);
  return m ? { click: function () { clicks.push(m[1]); applyColors(m[1]); } } : null;
} };
load(path.join(SITE, 'vendor', 'three', 'three.iife.min.js'));
var NET3D = fs.readFileSync(path.join(SITE, 'js', 'network3d.js'), 'utf8');
function pageNumber(re, what) { var m = re.exec(NET3D); if (!m) throw new Error('network3d.js: ' + what + ' not found'); return +m[1]; }
var MIN_DIST = pageNumber(/controls\.minDistance\s*=\s*([0-9.]+)/, 'controls.minDistance');
var MAX_DIST = pageNumber(/controls\.maxDistance\s*=\s*([0-9.]+)/, 'controls.maxDistance');
var FOG = { value: new THREE.Vector3(1, 1e6, 0) };          // the page's depth fade uniform (uFog), shared by its shaders
var TEASER_JS = process.argv[2] ? path.resolve(process.argv[2]) : path.join(HERE, 'teaser.js');
var CLS = { work: '#7dbe8e', record: '#a3d3ae', chapter: '#6fb7b4', section: '#86c4bf', article: '#9ed2c9', clause: '#bde2d9',
  point: '#d9efe9', term: '#8db8e8', question: '#f4b183', answer: '#f8d49b' };
global.VL = { PAPER_CLASS: {}, tok: function () { return ''; }, theme: function () { return 'light'; } };
load(path.join(SITE, 'js', 'paper3d.js'));
var M = global.__VLONTO_METRICS = { fps: 0.4, webglRenderer: 'stub', edgeSegments: { basis: 4 }, edgeCost: { curves: true },
  labelsShown: 0, calloutFrames: 0 };          // the page's call-outs (VL.Callouts) set these
global.VLONTO = {};
load(path.join(SITE, 'data', 'legal_network.js'));
var net = global.VLONTO.legal_network, F = {};
net.fields.forEach(function (f, i) { F[f] = i; });
var N = net.nodes.length, ZS = 2.2, D = { name: 'full', N: N, ids: [], idx: {}, pos: new Float32Array(3 * N), vis: new Uint8Array(N),
  ego: new Uint8Array(N), extent: Math.max(Math.abs(net.layout.x_y_range[0]), Math.abs(net.layout.x_y_range[1])), layerZ: net.layout.z_by_rank };
net.nodes.forEach(function (r, i) {
  D.ids[i] = String(r[F.id]); D.idx[D.ids[i]] = i; D.vis[i] = 1;
  D.pos[3 * i] = r[F.x]; D.pos[3 * i + 1] = r[F.z] * ZS; D.pos[3 * i + 2] = r[F.y];
});
var cfg = JSON.parse(fs.readFileSync(path.join(HERE, 'teaser_config.json'), 'utf8'));
var LAW = D.idx[cfg.selection.doc], OLD = D.idx[cfg.selection.chain[0]];
/* the page's curve (network3d.js curvePoint) */
var BEND = 0.18, LAYER_GAP = 150 * ZS, LIFT_MAX = 0.4 * LAYER_GAP;
function curvePts(a, b, n) {
  var out = [];
  for (var i = 0; i <= n; i++) {
    var t = i / n, dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, k = 0.45 * dy;
    var lift = Math.min(BEND * Math.sqrt(dx * dx + dz * dz), LIFT_MAX) * Math.max(0, Math.min(1, 1 - Math.abs(dy) / LAYER_GAP));
    var u = 1 - t, w0 = u * u * u, w1 = 3 * u * u * t, w2 = 3 * u * t * t, w3 = t * t * t;
    out.push({ x: (w0 + w1) * a.x + (w2 + w3) * b.x, y: w0 * a.y + w1 * (a.y + k + lift) + w2 * (b.y - k + lift) + w3 * b.y, z: (w0 + w1) * a.z + (w2 + w3) * b.z });
  }
  return out;
}
var g = new THREE.BufferGeometry();
g.setAttribute('position', new THREE.BufferAttribute(D.pos, 3));
g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(3 * N), 3));
g.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(N).fill(1), 1));
g.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(N).fill(12), 1));
var points = new THREE.Points(g, new THREE.ShaderMaterial({ uniforms: { uScale: { value: 1 }, uBg: { value: new THREE.Color() }, uFog: FOG, uRim: { value: 0.84 } },
  vertexShader: 'void main(){gl_Position=vec4(0.0);}', fragmentShader: 'void main(){gl_FragColor=vec4(1.0);}' }));
function applyColors(mode) { var a = g.attributes.aColor.array; for (var i = 0; i < N; i++) { a[3 * i] = 0.5; a[3 * i + 1] = 0.6; a[3 * i + 2] = mode === 'validity' ? 0.7 : 0.1; } }
var edges = {}, base = { replaced: 0.95, amended: 0.9, repealed: 0.92, partially_repealed: 0.88, partially_expired: 0.88, basis: 0.11, citation: 0.0715 };
Object.keys(base).forEach(function (k) { edges[k] = { obj: { material: { uniforms: { uOpacity: { value: base[k] } } } }, m: 1 }; });
var scene = new THREE.Scene(), labels = new THREE.Group(), renders = [], listeners = {};
function noop() {}
var canvas = { width: cfg.viewport.width, height: cfg.viewport.height, clientWidth: cfg.viewport.width, clientHeight: cfg.viewport.height,
  style: {}, addEventListener: function (t) { listeners[t] = (listeners[t] || 0) + 1; }, removeEventListener: noop,
  ownerDocument: { addEventListener: noop, removeEventListener: noop }, setPointerCapture: noop, releasePointerCapture: noop,
  getBoundingClientRect: function () { return { left: 0, top: 0, width: cfg.viewport.width, height: cfg.viewport.height }; },
  toDataURL: function () { return 'data:image/png;base64,' + Buffer.from('stub').toString('base64'); } };
canvas.getRootNode = function () { return canvas.ownerDocument; };
/* the drawing buffer: white, with a 3 x 3 px dot (GL rows, bottom up) for every network point and bead inside the clip volume */
var fb = null, fbW = 0, fbH = 0;
var gl = { RGBA: 6408, UNSIGNED_BYTE: 5121, MAX_RENDERBUFFER_SIZE: 34024, MAX_VIEWPORT_DIMS: 3386, MAX_TEXTURE_SIZE: 3379,
  get drawingBufferWidth() { return canvas.width; }, get drawingBufferHeight() { return canvas.height; },
  readPixels: function (x, y, w, h, f, t, out) { if (fb && fbW === w && fbH === h) out.set(fb); else out.fill(255); },
  getParameter: function (q) { return q === 3386 ? new Int32Array([8192, 8192]) : 8192; },
  isContextLost: function () { return false; }, getError: function () { return 0; } };
var renderer = { pr: 1, domElement: canvas, info: { render: { calls: 0, triangles: 0, points: 0, lines: 0, frame: 0 } },
  setPixelRatio: function (p) { this.pr = p; }, getPixelRatio: function () { return this.pr; },
  setSize: function (w, h) { canvas.width = Math.round(w * this.pr); canvas.height = Math.round(h * this.pr); },
  getContext: function () { return gl; }, getClearColor: function (c) { return c.setRGB(1, 1, 1); },
  render: function (s, c) {
    c.updateMatrixWorld(true);
    fbW = canvas.width; fbH = canvas.height; fb = new Uint8Array(fbW * fbH * 4).fill(255);
    var m = new THREE.Matrix4().multiplyMatrices(c.projectionMatrix, c.matrixWorldInverse), v = new THREE.Vector3(), drawn = 0;
    function dot(x, y, z) {
      v.set(x, y, z).applyMatrix4(m);
      if (!(v.x >= -1 && v.x <= 1 && v.y >= -1 && v.y <= 1 && v.z >= -1 && v.z <= 1)) return;
      var px = Math.floor((v.x + 1) / 2 * fbW), py = Math.floor((v.y + 1) / 2 * fbH);
      for (var yy = Math.max(0, py - 1); yy <= Math.min(fbH - 1, py + 1); yy++)
        for (var xx = Math.max(0, px - 1); xx <= Math.min(fbW - 1, px + 1); xx++) { var i = 4 * (yy * fbW + xx); fb[i] = 60; fb[i + 1] = 80; fb[i + 2] = 90; }
      drawn++;
    }
    for (var i = 0; i < N; i++) dot(D.pos[3 * i], D.pos[3 * i + 1], D.pos[3 * i + 2]);
    s.children.forEach(function (o) { if (o.isPoints && o !== points) { var a = o.geometry.attributes.position; for (var k = 0; k < a.count; k++) dot(a.getX(k), a.getY(k), a.getZ(k)); } });
    var ri = this.info.render;
    this.info.render = { calls: drawn ? 2 : 0, triangles: 0, points: drawn, lines: 0, frame: ri.frame + 1 };
    renders.push({ ortho: !!c.isOrthographicCamera, pr: this.pr, drawn: drawn });
  } };
var camera = new THREE.PerspectiveCamera(45, 1, 5, 80000), chainIdx = [];
camera.position.set(0, 1500, 6000);
/* the page's orbit controls (network3d.js initThree), with its damping and distance limits */
var controls = new THREE.OrbitControls(camera, canvas);
controls.enableDamping = true; controls.minDistance = MIN_DIST; controls.maxDistance = MAX_DIST; controls.autoRotate = true;
/* the page's depth fade (network3d.js updateFog) and frame loop: controls.update() on every frame, a render when asked */
var needsRender = false, looping = true;
function updateFog() { var d = camera.position.distanceTo(controls.target), R = D.extent * 1.1; FOG.value.set(Math.max(1, d - 0.4 * R), d + 1.9 * R, 0.6); }
(function loop() {
  if (!looping) return;
  var moved = controls.update();
  if (needsRender || moved) { updateFog(); renderer.render(scene, camera); needsRender = false; }
  setTimeout(loop, 4);
})();
var P = { dark: false, core: '#2c3a47', halo: '#ecc890', halo2: '#f4dcac', cls: CLS };
var chain = VL.TraceLines({ depthTest: false, renderOrder: 10 }), ego = VL.ColorLines({});
global.VLApp = { capture: {
  get: function () { return { THREE: THREE, renderer: renderer, scene: scene, camera: camera, controls: controls, D: D, P: P, state: {},
    points: points, edges: edges, layers: new THREE.Group(), labels: labels, chain: chain, ego: ego, chainIdx: chainIdx.slice(), curvePts: curvePts, ZS: ZS, fog: FOG }; },
  setCamera: function (c) { camera = c; controls.object = c; controls.update(); needsRender = true; },   // as network3d.js
  select: function (id) {
    if (D.idx[id] == null) return false;
    D.ego[LAW] = 3;
    net.edges.change.concat(net.edges.basis).forEach(function (e) { if (e[0] === LAW) D.ego[e[1]] = D.ego[e[1]] || 1; if (e[1] === LAW) D.ego[e[0]] = D.ego[e[0]] || 1; });
    setTimeout(function () { chainIdx = [OLD, LAW]; M.panelLoaded = id; M.chainTraceDocs = 2; M.egoHop1 = 90; }, 20);
    return true;
  },
  render: function () { needsRender = true; }
} };
global.__VLONTO_READY = true;
load(path.join(HERE, 'teaser_data.js'));
load(path.join(HERE, 'teaser-core.js'));
load(TEASER_JS);
var T = global.__TEASER, fails = [];
function check(ok, what) { if (!ok) fails.push(what); }
(function wait(n) {
  if (!T.ready && !T.error && n < 600) return setTimeout(function () { wait(n + 1); }, 20);
  check(T.ready && !T.error, 'ready without error: ' + T.error);
  if (!T.ready) return finish();
  var pose = TZ.cameraPose(cfg.camera);
  check(camera.isOrthographicCamera, 'orthographic camera swapped in');
  var dist = camera.position.distanceTo(controls.target);
  check(Math.abs(dist - cfg.camera.distance) < 1e-6 * cfg.camera.distance,
    'camera kept at the configured distance ' + cfg.camera.distance + ' (the page\'s controls stop at ' + MAX_DIST + '): ' + dist.toFixed(1));
  var jc = T.json && T.json.camera;
  check(jc && jc.scene_depth && jc.near < jc.scene_depth[0] && jc.far > jc.scene_depth[1], 'near/far around the scene\'s depth range');
  var fog = TZ.fog(cfg.camera.distance, D.extent, 0.6);
  check(Math.abs(FOG.value.x - fog.near) < 1e-6 && Math.abs(FOG.value.y - fog.far) < 1e-6 && FOG.value.z === 0.6, 'depth fade fitted to the camera');
  check(listeners.webglcontextlost === 1 && listeners.webglcontextrestored === 1, 'WebGL context loss watched');
  check(Math.abs(camera.position.x - pose.position.x) < 1e-6 && Math.abs(camera.position.y - pose.position.y) < 1e-6, 'camera at the configured pose');
  check(!controls.enabled && !controls.enableDamping && !controls.autoRotate, 'controls frozen');
  check(Math.abs(VL.TRACE_W.core - cfg.trace_pt.core * TZ.cssPerPt(cfg)) < 1e-9, 'trace core width from trace_pt');
  var a = g.attributes.aAlpha.array, faded = 0;
  for (var i = 0; i < N; i++) if (a[i] === Math.fround(cfg.fade.points)) faded++;    // Float32Array
  check(faded === N - 91, 'context faded: ' + faded + ' points');
  check(Math.abs(edges.basis.obj.material.uniforms.uOpacity.value - 0.11 * cfg.fade.edges) < 1e-12, 'links faded');
  var traces = scene.children.filter(function (o) { return o.name === 'vlonto-trace'; }), beads = scene.children.filter(function (o) { return o.isPoints; });
  check(traces.length === 1 && beads.length === 1, 'one traced path and one bead set in the scene');
  check(beads.length && beads[0].geometry.attributes.position.count === Object.keys(cfg.subtree.offsets).length + 2, 'beads for the subtree and both codes');
  var tp = T.json && T.json.paths_pt && T.json.paths_pt.trace;
  check(tp && tp.length === 7 * cfg.subtree.segments + 1, 'traced path: 7 hops on the curve');
  check(T.json && T.json.projection_check_px < 1e-6, 'anchors: three.js == teaser-core.js');
  var names = cfg.captures.map(function (c) { return c.name; });
  (function next(k) {
    if (k >= names.length) return finish();
    T.capture(names[k]).then(function (r) {
      var c = cfg.captures[k];
      check(r.width === Math.round(cfg.viewport.width * c.pixelRatio) && r.height === Math.round(cfg.viewport.height * c.pixelRatio), names[k] + ' size');
      check(renders.length && renders[renders.length - 1].ortho && renders[renders.length - 1].pr === c.pixelRatio, names[k] + ' rendered orthographic at its pixel ratio');
      check(labels.visible === (c.labels === 'site'), names[k] + ' labels ' + c.labels);
      check(!r.blank && r.ink >= cfg.checks.min_ink_fraction, names[k] + ' has ink: ' + r.ink);
      check(r.diag && r.diag.scene_depth.inside_clip && r.diag.render.calls > 0 && r.diag.pixels.size[0] === r.width &&
        r.diag.camera.distance === dist && r.diag.canvas.drawing_buffer[1] === r.height, names[k] + ' diagnostics');
      next(k + 1);
    }).catch(function (e) { fails.push(names[k] + ': ' + e.message); finish(); });
  })(0);
})(0);
function finish() {
  looping = false;
  console.log(JSON.stringify({ ok: !fails.length, fails: fails, steps: T.steps.map(function (s) { return s.step; }), colour_clicks: clicks, drawn: renders.filter(function (r) { return r.ortho; }).map(function (r) { return r.pr + 'x:' + r.drawn; }),
    captures: T.json && T.json.captures.map(function (c) { return c.name + ' ' + c.width + 'x' + c.height + ' ' + c.colorBy + ' ink ' + c.ink; }) }, null, 1));
  process.exit(fails.length ? 1 : 0);
}

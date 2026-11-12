/* node scripts/site/teaser/test_harness.js
   Runs teaser.js under node against a stand-in for the network page: real three.js and js/paper3d.js (trace and line
   objects), the real network data (positions, links, the Labor Code's neighbourhood), and a stub of what the page
   provides (VLApp.capture, the metrics, the renderer, the colour buttons). Checks that the harness reaches ready
   without errors, swaps in an orthographic camera at the configured pose, widens the trace, fades the context,
   builds the subtree (one traced path, the thin branches, the beads), answers every capture of the config at its pixel
   ratio, and writes anchors that match teaser-core.js. It cannot check pixels: that is the browser capture's job. */
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
var points = new THREE.Points(g, new THREE.ShaderMaterial({ uniforms: { uScale: { value: 1 }, uBg: { value: new THREE.Color() }, uFog: { value: new THREE.Vector3() }, uRim: { value: 0.84 } },
  vertexShader: 'void main(){gl_Position=vec4(0.0);}', fragmentShader: 'void main(){gl_FragColor=vec4(1.0);}' }));
function applyColors(mode) { var a = g.attributes.aColor.array; for (var i = 0; i < N; i++) { a[3 * i] = 0.5; a[3 * i + 1] = 0.6; a[3 * i + 2] = mode === 'validity' ? 0.7 : 0.1; } }
var edges = {}, base = { replaced: 0.95, amended: 0.9, repealed: 0.92, partially_repealed: 0.88, partially_expired: 0.88, basis: 0.11, citation: 0.0715 };
Object.keys(base).forEach(function (k) { edges[k] = { obj: { material: { uniforms: { uOpacity: { value: base[k] } } } }, m: 1 }; });
var scene = new THREE.Scene(), labels = new THREE.Group(), renders = [];
var renderer = { pr: 1, domElement: { width: cfg.viewport.width, height: cfg.viewport.height, clientWidth: cfg.viewport.width,
    toDataURL: function () { return 'data:image/png;base64,' + Buffer.from('stub').toString('base64'); } },
  setPixelRatio: function (p) { this.pr = p; }, getPixelRatio: function () { return this.pr; },
  setSize: function (w, h) { this.domElement.width = Math.round(w * this.pr); this.domElement.height = Math.round(h * this.pr); },
  render: function (s, c) { renders.push({ ortho: !!c.isOrthographicCamera, pr: this.pr }); } };
var controls = { target: new THREE.Vector3(), autoRotate: true, enableDamping: true, enabled: true, update: function () { return false; } };
var camera = new THREE.PerspectiveCamera(45, 1, 5, 80000), chainIdx = [];
var P = { dark: false, core: '#2c3a47', halo: '#ecc890', halo2: '#f4dcac', cls: CLS };
var chain = VL.TraceLines({ depthTest: false, renderOrder: 10 }), ego = VL.ColorLines({});
global.VLApp = { capture: {
  get: function () { return { THREE: THREE, renderer: renderer, scene: scene, camera: camera, controls: controls, D: D, P: P, state: {},
    points: points, edges: edges, layers: new THREE.Group(), labels: labels, chain: chain, ego: ego, chainIdx: chainIdx.slice(), curvePts: curvePts, ZS: ZS }; },
  setCamera: function (c) { camera = c; },
  select: function (id) {
    if (D.idx[id] == null) return false;
    D.ego[LAW] = 3;
    net.edges.change.concat(net.edges.basis).forEach(function (e) { if (e[0] === LAW) D.ego[e[1]] = D.ego[e[1]] || 1; if (e[1] === LAW) D.ego[e[0]] = D.ego[e[0]] || 1; });
    setTimeout(function () { chainIdx = [OLD, LAW]; M.panelLoaded = id; M.chainTraceDocs = 2; M.egoHop1 = 90; }, 20);
    return true;
  },
  render: function () {}
} };
global.__VLONTO_READY = true;
load(path.join(HERE, 'teaser_data.js'));
load(path.join(HERE, 'teaser-core.js'));
load(path.join(HERE, 'teaser.js'));
var T = global.__TEASER, fails = [];
function check(ok, what) { if (!ok) fails.push(what); }
(function wait(n) {
  if (!T.ready && !T.error && n < 600) return setTimeout(function () { wait(n + 1); }, 20);
  check(T.ready && !T.error, 'ready without error: ' + T.error);
  if (!T.ready) return finish();
  var pose = TZ.cameraPose(cfg.camera);
  check(camera.isOrthographicCamera, 'orthographic camera swapped in');
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
      next(k + 1);
    }).catch(function (e) { fails.push(names[k] + ': ' + e.message); finish(); });
  })(0);
})(0);
function finish() {
  console.log(JSON.stringify({ ok: !fails.length, fails: fails, steps: T.steps.map(function (s) { return s.step; }), colour_clicks: clicks,
    captures: T.json && T.json.captures.map(function (c) { return c.name + ' ' + c.width + 'x' + c.height + ' ' + c.colorBy; }) }, null, 1));
  process.exit(fails.length ? 1 : 0);
}

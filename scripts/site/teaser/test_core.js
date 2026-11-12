/* node scripts/site/teaser/test_core.js [anchors.json]
   Checks teaser-core.js against three.js: the orthographic camera that teaser.js builds projects the trace subtree, the
   two Labor Code documents and the layer-plane corners to the positions TZ.toScreen computes (within 1e-6 CSS px), and
   the subtree's positions are finite. Writes the anchors in figure points (origin top left) for comparison with
   preview.py --json. Needs only node: the vendored three.js and the network's data are read from site/. */
'use strict';
var fs = require('fs'), path = require('path'), vm = require('vm');
var HERE = __dirname, SITE = path.join(HERE, '..', '..', '..', 'site');
global.window = global; global.self = global;
vm.runInThisContext(fs.readFileSync(path.join(SITE, 'vendor', 'three', 'three.iife.min.js'), 'utf8'));
var TZ = require('./teaser-core.js');
var cfg = JSON.parse(fs.readFileSync(path.join(HERE, 'teaser_config.json'), 'utf8'));
var tr = JSON.parse(fs.readFileSync(path.join(HERE, 'trace_138008514.json'), 'utf8'));
var src = fs.readFileSync(path.join(SITE, 'js', 'network3d.js'), 'utf8');
if (src.indexOf('var ZS = 2.2;') < 0) throw new Error('network3d.js: ZS changed; update test_core.js');
var ZS = 2.2;
global.VLONTO = {};
vm.runInThisContext(fs.readFileSync(path.join(SITE, 'data', 'legal_network.js'), 'utf8'));
var net = global.VLONTO.legal_network, F = {};
net.fields.forEach(function (f, i) { F[f] = i; });
function docPos(id) {
  for (var i = 0; i < net.nodes.length; i++) {
    var r = net.nodes[i];
    if (String(r[F.id]) === id) return { x: r[F.x], y: r[F.z] * ZS, z: r[F.y] };
  }
  throw new Error('document ' + id + ' not in the network');
}
var vw = cfg.viewport.width, vh = cfg.viewport.height;
var fr = TZ.frustum(cfg.camera, vw, vh), pose = TZ.cameraPose(cfg.camera);
var cam = new THREE.OrthographicCamera(fr.left, fr.right, fr.top, fr.bottom, fr.near, fr.far);
cam.up.set(0, 1, 0);
cam.position.set(pose.position.x, pose.position.y, pose.position.z);
cam.lookAt(new THREE.Vector3(pose.target.x, pose.target.y, pose.target.z));
cam.updateProjectionMatrix();
cam.updateMatrixWorld(true);
function three(p) { var v = new THREE.Vector3(p.x, p.y, p.z).project(cam); return { x: (v.x + 1) / 2 * vw, y: (1 - v.y) / 2 * vh, z: v.z }; }
var L = docPos(tr.law.doc), SP = TZ.subtreePositions(L, cfg.subtree.offsets);
SP['doc:' + tr.law.doc] = L;
SP['doc:' + tr.replaced.doc] = docPos(tr.replaced.doc);
var E = Math.max(Math.abs(net.layout.x_y_range[0]), Math.abs(net.layout.x_y_range[1])) * 1.06, pts = {};
Object.keys(SP).forEach(function (k) { pts[k] = SP[k]; });
Object.keys(net.layout.z_by_rank).forEach(function (r) {
  var y = net.layout.z_by_rank[r] * ZS - 2;
  [[-E, -E], [E, -E], [E, E], [-E, E]].forEach(function (q, j) { pts['plane-' + r + '-' + j] = { x: q[0], y: y, z: q[1] }; });
});
var maxd = 0, inside = true, out = {}, k = 1 / TZ.cssPerPt(cfg);
Object.keys(pts).forEach(function (id) {
  var p = pts[id], a = three(p), b = TZ.toScreen(cfg, p);
  if (![p.x, p.y, p.z].every(isFinite)) throw new Error('not finite: ' + id);
  maxd = Math.max(maxd, Math.abs(a.x - b.x), Math.abs(a.y - b.y));
  if (a.z < -1 || a.z > 1) inside = false;                          // between the near and far planes
  out[id] = [+(b.x * k).toFixed(3), +(b.y * k).toFixed(3)];
});
var ok = maxd < 1e-6 && inside;
console.log(JSON.stringify({ ok: ok, points: Object.keys(pts).length, max_diff_css_px: maxd, within_depth_range: inside,
  bead_world: TZ.beadSize(cfg, cfg.subtree.bead_pt), point_scale_pr3: TZ.pointScale(cfg, 3) }));
if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(out, null, 1) + '\n');
process.exit(ok ? 0 : 1);

/* Pure geometry of the Fig. 1 capture (no DOM): the trace subtree hung from the Labor Code, the orthographic camera, and
   the conversions between figure points and CSS pixels. Used by teaser.js in the page and by node in the parity test
   (test_core.js), which checks it against preview.py. Classic script: sets window.TZ, or module.exports under node. */
(function (root) {
  'use strict';
  var TZ = {};
  function v(x, y, z) { return { x: x, y: y, z: z }; }
  /* the local frame at the Labor Code L: out = horizontal unit vector from the network's centre axis through L,
     side = up x out (horizontal), down = -y */
  TZ.frame = function (L) {
    var n = Math.sqrt(L.x * L.x + L.z * L.z) || 1, out = v(L.x / n, 0, L.z / n);
    return { out: out, side: v(out.z, 0, -out.x) };
  };
  /* world position of every subtree node: L + out * o + side * s - (0, d, 0) for offsets [o, d, s] */
  TZ.subtreePositions = function (L, offsets) {
    var f = TZ.frame(L), res = {};
    Object.keys(offsets).forEach(function (id) {
      var o = offsets[id];
      res[id] = v(L.x + f.out.x * o[0] + f.side.x * o[2], L.y - o[1], L.z + f.out.z * o[0] + f.side.z * o[2]);
    });
    return res;
  };
  /* camera pose: target + distance * (cos(el) sin(az), sin(el), cos(el) cos(az)), y up (three.js convention) */
  TZ.cameraPose = function (cam) {
    var a = cam.azimuth_deg * Math.PI / 180, e = cam.elevation_deg * Math.PI / 180, t = cam.target, d = cam.distance;
    return { position: v(t[0] + d * Math.cos(e) * Math.sin(a), t[1] + d * Math.sin(e), t[2] + d * Math.cos(e) * Math.cos(a)),
      target: v(t[0], t[1], t[2]) };
  };
  /* orthographic frustum for a vw x vh CSS-px viewport: half_height world units above and below the target */
  TZ.frustum = function (cam, vw, vh) {
    var hh = cam.half_height, hw = hh * vw / vh;
    return { left: -hw, right: hw, top: hh, bottom: -hh, near: cam.distance - 8000, far: cam.distance + 8000 };
  };
  /* figure points <-> CSS px: the viewport's width is the figure's width */
  TZ.cssPerPt = function (cfg) { return cfg.viewport.width / cfg.figure.width_pt; };
  /* world size of a bead of diameter pt (the points' aSize, drawn at aSize * uScale / depth device px) */
  TZ.beadSize = function (cfg, pt) { return pt * TZ.cssPerPt(cfg) * 2 * cfg.camera.half_height / cfg.viewport.height; };
  /* uScale that gives an orthographic camera the points' world sizes (the shader divides by the depth, about the
     camera's distance from the target: the configured one, or the one measured in the page) */
  TZ.pointScale = function (cfg, pixelRatio, distance) {
    return cfg.viewport.height * pixelRatio / (2 * cfg.camera.half_height) * (distance || cfg.camera.distance);
  };
  /* near and far planes around the scene's depth range [d0, d1] (camera space, + = in front of the camera): a quarter of
     the range and at least 200 world units of margin on either side, never at or behind the camera */
  TZ.clipPlanes = function (d0, d1) {
    var m = Math.max(200, 0.25 * (d1 - d0));
    return { near: Math.max(1, d0 - m), far: d1 + m };
  };
  /* the page's depth fade toward the background (network3d.js updateFog, uniform uFog = near, far, amount): from 0.4 R in
     front of the target to 1.9 R behind it, R = 1.1 x the layout's extent, d = the target's depth from the camera; for an
     orthographic camera d is its distance from the target, so the fade spans the same part of the scene as in the page */
  TZ.fog = function (d, extent, amount) {
    var R = 1.1 * extent;
    return { near: Math.max(1, d - 0.4 * R), far: d + 1.9 * R, amount: amount };
  };
  /* the fade at a depth, as the shaders compute it (vFog): 0 = full colour, amount = the most it fades */
  TZ.fogFactor = function (f, depth) {
    return Math.min(1, Math.max(0, (depth - f.near) / Math.max(1, f.far - f.near))) * f.amount;
  };
  /* screen position (CSS px, origin top left) of a world point, without three.js: the same basis as the camera */
  TZ.basis = function (cam) {
    var a = cam.azimuth_deg * Math.PI / 180, e = cam.elevation_deg * Math.PI / 180;
    var back = v(Math.cos(e) * Math.sin(a), Math.sin(e), Math.cos(e) * Math.cos(a));       // target -> camera
    var right = v(Math.cos(a), 0, -Math.sin(a));                                           // (-back) x up, normalised
    var up = v(-Math.sin(e) * Math.sin(a), Math.cos(e), -Math.sin(e) * Math.cos(a));               // right x (-back)
    return { back: back, right: right, up: up };
  };
  TZ.toScreen = function (cfg, p) {
    var cam = cfg.camera, B = TZ.basis(cam), t = cam.target, dx = p.x - t[0], dy = p.y - t[1], dz = p.z - t[2];
    var sx = dx * B.right.x + dy * B.right.y + dz * B.right.z, sy = dx * B.up.x + dy * B.up.y + dz * B.up.z;
    var depth = -(dx * B.back.x + dy * B.back.y + dz * B.back.z);                         // + = farther than the target
    var vw = cfg.viewport.width, vh = cfg.viewport.height, hh = cam.half_height, hw = hh * vw / vh;
    return { x: (sx / hw + 1) / 2 * vw, y: (1 - sy / hh) / 2 * vh, depth: depth };
  };
  /* CSS px -> figure points (origin top left) */
  TZ.toFigure = function (cfg, s) { var k = 1 / TZ.cssPerPt(cfg); return { x: s.x * k, y: s.y * k }; };
  if (typeof module !== 'undefined' && module.exports) module.exports = TZ;
  else root.TZ = TZ;
})(typeof window !== 'undefined' ? window : this);

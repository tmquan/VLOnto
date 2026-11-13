/* Fig. 1 capture harness (scripts/site/teaser; not part of the site). Runs in teaser.html - site/network-3d.html copied
   by make_page.py with a <base> into site/ - after js/network3d.js, teaser_data.js (config + trace) and teaser-core.js.
   1. wait for the page (window.__VLONTO_READY: full network built, frame rate measured), note the links' opacities;
   2. select the Labor Code without the camera flight (VLApp.capture.select) and wait for its replacement chain;
   3. swap in the orthographic camera of teaser_config.json (fixed pose, no damping), the paper's trace weights; the
      page's orbit controls keep the camera within maxDistance (30000) on every frame, so their limits are lifted first
      (the figure's camera stands farther away); near/far and the page's depth fade are fitted to the scene's depth
      range in camera space before every capture;
   4. fade the context outside the selection's neighbourhood; hang the trace subtree from the Labor Code: the traced
      hops as one path on the links' curve (navy core, gold halo), thin branches to Art. 3(1) and the terms, beads on top;
   5. expose window.__TEASER: ready, capture(name) -> {url: PNG data URL of the WebGL canvas, width, height, ink, blank,
      diag} rendered at that capture's pixel ratio and colouring, and json (camera, selection, anchors in CSS px and
      figure pt, metrics). Every capture counts the pixels that differ from the background with gl.readPixels right after
      the render (same task) and records the camera, the clipping planes, the depth fade, the scene's depth range, the
      renderer's draw counts and the canvas; WebGL context loss is recorded and logged.
   No sleeps: every wait is on a page metric or a frame. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS, TZ = window.TZ, DATA = window.VLONTO_TEASER;
  var T = window.__TEASER = { ready: false, error: null, steps: [], json: null, events: [] };
  if (!DATA || !TZ) { T.error = 'teaser_data.js or teaser-core.js missing'; return; }
  var cfg = DATA.config, tr = DATA.trace, vw = cfg.viewport.width, vh = cfg.viewport.height;
  var MIN_INK = (cfg.checks && cfg.checks.min_ink_fraction) || 0.01;    // a capture with less ink than this is blank
  var t0 = performance.now();
  function step(s, extra) { var r = { step: s, ms: Math.round(performance.now() - t0) }; if (extra) r.info = extra; T.steps.push(r); }
  function until(test, what, ms) {
    var limit = performance.now() + (ms || 900000);
    return new Promise(function (res, rej) {
      (function poll() {
        var ok = false;
        try { ok = test(); } catch (e) { ok = false; }
        if (ok) return res();
        if (performance.now() > limit) return rej(new Error('timed out waiting for ' + what));
        setTimeout(poll, 100);
      })();
    });
  }
  function frames(n) {
    return new Promise(function (res) { var k = 0; (function f() { if (++k > n) res(); else requestAnimationFrame(f); })(); });
  }
  var C, X, THREE, cam, base = {}, beads, beadIds = [], subTrace, thin, paths = {}, SP = {};

  function ptOf(D, i) { return { x: D.pos[3 * i], y: D.pos[3 * i + 1], z: D.pos[3 * i + 2] }; }
  function hexOfClass(cls) { return (X.P.cls && X.P.cls[cls]) || (VL.PAPER_CLASS[cls] || {}).color || '#9aa3ad'; }
  function workColor() { return hexOfClass('work'); }

  /* colours of the documents: the page's own (validity, type, area) through its buttons, or every document in the
     paper's 'Văn bản · Work' colour (class); the two Labor Code beads follow */
  function setColors(mode) {
    var D = X.D, col = X.points.geometry.attributes.aColor;
    if (mode === 'class') {
      var c = VL.rawColor(workColor(), new THREE.Color());
      for (var i = 0; i < D.N; i++) { col.array[3 * i] = c.r; col.array[3 * i + 1] = c.g; col.array[3 * i + 2] = c.b; }
      col.needsUpdate = true;
    } else {
      var b = document.querySelector('[data-color="' + mode + '"]');
      if (!b) throw new Error('no colour button for ' + mode);
      b.click();                                   // network3d.js: state.colorBy = mode; applyColors()
    }
    var bc = beads.geometry.attributes.aColor;
    beadIds.forEach(function (id, k) {
      if (id.indexOf('doc:') !== 0) return;
      var j = D.idx[id.slice(4)];
      bc.array[3 * k] = col.array[3 * j]; bc.array[3 * k + 1] = col.array[3 * j + 1]; bc.array[3 * k + 2] = col.array[3 * j + 2];
    });
    bc.needsUpdate = true;
    T.colorBy = mode;
  }

  /* the traced hops as one path from the Labor Code: follow the trace links (either direction) */
  function tracePathIds() {
    var links = tr.links.filter(function (l) { return l.trace && l.rel !== 'replaced by'; }), used = {}, cur = 'doc:' + tr.law.doc, ids = [cur];
    for (var guard = 0; guard < links.length; guard++) {
      var nxt = null;
      links.forEach(function (l, k) {
        if (used[k] || nxt) return;
        if (l.source === cur) { nxt = l.target; used[k] = 1; } else if (l.target === cur) { nxt = l.source; used[k] = 1; }
      });
      if (!nxt) break;
      ids.push(nxt); cur = nxt;
    }
    if (ids.length !== links.length + 1) throw new Error('trace links do not form one path from the law');
    return ids;
  }
  function polyline(ids, segs) {
    var out = [];
    for (var i = 0; i + 1 < ids.length; i++) {
      var seg = X.curvePts(SP[ids[i]], SP[ids[i + 1]], segs);
      out = out.concat(i ? seg.slice(1) : seg);
    }
    return out;
  }

  function buildSubtree() {
    var D = X.D, li = D.idx[tr.law.doc], oi = D.idx[tr.replaced.doc];
    SP = TZ.subtreePositions(ptOf(D, li), cfg.subtree.offsets);
    SP['doc:' + tr.law.doc] = ptOf(D, li);
    SP['doc:' + tr.replaced.doc] = ptOf(D, oi);
    var segs = cfg.subtree.segments, ids = tracePathIds();
    paths.trace = polyline(ids, segs);
    paths.chain = X.curvePts(SP['doc:' + tr.replaced.doc], SP['doc:' + tr.law.doc], 24);
    subTrace = VL.TraceLines({ depthTest: false, renderOrder: 12 });
    subTrace.setStyle(VL.traceStyle(X.P, 1));
    subTrace.setPaths([paths.trace]);
    X.scene.add(subTrace.object);
    var nodes = {};
    tr.nodes.forEach(function (n) { nodes[n.id] = n; });
    var thinLinks = tr.links.filter(function (l) { return !l.trace; });
    paths.thin = thinLinks.map(function (l) { return X.curvePts(SP[l.source], SP[l.target], segs); });
    thin = VL.ColorLines({ depthTest: false, renderOrder: 11, width: 1.3, opacity: 0.95 });
    thin.setPaths(paths.thin, thinLinks.map(function (l) { return VL.shade(hexOfClass((nodes[l.target] || {}).cls || 'term'), 0.82); }));
    X.scene.add(thin.object);
    /* beads: the subtree's nodes and the two codes, drawn with the page's own point shader on top of the paths */
    beadIds = Object.keys(cfg.subtree.offsets).concat(['doc:' + tr.law.doc, 'doc:' + tr.replaced.doc]);
    var n = beadIds.length, P = new Float32Array(3 * n), Cc = new Float32Array(3 * n), A = new Float32Array(n), S = new Float32Array(n);
    var bead = TZ.beadSize(cfg, cfg.subtree.bead_pt), sz = X.points.geometry.attributes.aSize.array, c = new THREE.Color();
    beadIds.forEach(function (id, k) {
      var p = SP[id];
      P[3 * k] = p.x; P[3 * k + 1] = p.y; P[3 * k + 2] = p.z;
      A[k] = 1;
      if (id.indexOf('doc:') === 0) S[k] = Math.max(bead, sz[D.idx[id.slice(4)]]);
      else { S[k] = bead; VL.rawColor(hexOfClass(nodes[id].cls), c); Cc[3 * k] = c.r; Cc[3 * k + 1] = c.g; Cc[3 * k + 2] = c.b; }
    });
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(P, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(Cc, 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(A, 1));
    g.setAttribute('aSize', new THREE.BufferAttribute(S, 1));
    var pm = X.points.material;
    beads = new THREE.Points(g, new THREE.ShaderMaterial({ uniforms: pm.uniforms, vertexShader: pm.vertexShader,
      fragmentShader: pm.fragmentShader, depthTest: false, depthWrite: false, transparent: true }));
    /* three.js draws every opaque object before every transparent one, whatever their renderOrder: the links and the
       traces are transparent (the trace's halo2, halo and core meshes at renderOrder 12, 13, 14), so the beads must be
       transparent too, and come after the core (the first CI capture had them opaque, under the trace and the links) */
    beads.renderOrder = 20;
    beads.frustumCulled = false;
    X.scene.add(beads);
  }

  /* the context outside the selection's neighbourhood: points at fade.points, links at fade.edges of their opacity */
  function fade() {
    var D = X.D, a = X.points.geometry.attributes.aAlpha;
    for (var i = 0; i < D.N; i++) if (D.vis[i] && !D.ego[i]) a.array[i] = cfg.fade.points;
    a.needsUpdate = true;
    Object.keys(X.edges).forEach(function (k) {
      var o = X.edges[k] && X.edges[k].obj, u = o && o.material && o.material.uniforms && o.material.uniforms.uOpacity;
      if (u && base[k] != null) u.value = base[k] * cfg.fade.edges;
    });
  }

  function useCamera() {
    var ctl = X.controls;
    ctl.autoRotate = false;
    ctl.enableDamping = false;
    ctl.update(); ctl.update();                     // spend any damping left from the page's frame-rate spin
    /* the page's OrbitControls clamp the camera's distance to [minDistance, maxDistance] (40, 30000) on every update(),
       for whichever camera they hold; VLApp.capture.setCamera hands them this one and calls update(), and the page's
       frame loop calls it again on every frame. The figure's camera stands cfg.camera.distance away, so lift the limits
       first: a camera pulled in to 30000 put the whole scene in front of near (52000) and every capture came out white */
    ctl.minDistance = 0;
    ctl.maxDistance = Infinity;
    var fr = TZ.frustum(cfg.camera, vw, vh), pose = TZ.cameraPose(cfg.camera);
    cam = new THREE.OrthographicCamera(fr.left, fr.right, fr.top, fr.bottom, fr.near, fr.far);
    cam.up.set(0, 1, 0);
    cam.position.set(pose.position.x, pose.position.y, pose.position.z);
    ctl.target.set(pose.target.x, pose.target.y, pose.target.z);
    cam.lookAt(ctl.target);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld(true);                    // the anchors are projected before the first frame with this camera
    C.setCamera(cam);
    ctl.enabled = false;                            // a stray pointer must not move the figure
    checkCamera('camera swap');
  }

  /* the camera must still look along the configured direction at the configured target: the anchors depend on both.
     Its distance only moves the clipping planes, the depth fade and the points' scale, which fitDepth() takes from the
     camera as it is; a distance other than the configured one is noted (step 'camera distance') */
  var distanceNoted = false;
  function checkCamera(where) {
    var pose = TZ.cameraPose(cfg.camera), ctl = X.controls;
    var want = new THREE.Vector3(pose.position.x - pose.target.x, pose.position.y - pose.target.y, pose.position.z - pose.target.z);
    var got = cam.position.clone().sub(ctl.target), d = got.length();
    var moved = ctl.target.distanceTo(new THREE.Vector3(pose.target.x, pose.target.y, pose.target.z));
    var turn = want.normalize().angleTo(got.clone().normalize());
    if (turn > 1e-6 || moved > 1e-6 * cfg.camera.distance)
      throw new Error(where + ': the camera turned by ' + turn.toExponential(2) + ' rad or its target moved by ' + moved.toFixed(3));
    if (Math.abs(d - cfg.camera.distance) > 1e-6 * cfg.camera.distance && !distanceNoted) {
      distanceNoted = true;
      step('camera distance', { where: where, distance: d, configured: cfg.camera.distance });
      console.warn('teaser: the camera stands ' + d.toFixed(1) + ' from the target, configured ' + cfg.camera.distance);
    }
    return d;
  }

  /* the page's curve lift above a link's ends (network3d.js: LAYER_GAP = 150 ZS, LIFT_MAX = 0.4 LAYER_GAP) and the
     layer planes' height (as the page draws them, 2 below the layer) */
  function liftMax() { return 0.4 * 150 * X.ZS; }
  function layerY(r) { return (X.D.layerZ[r] != null ? X.D.layerZ[r] : (5 - r) * 150) * X.ZS - 2; }
  /* the scene's depth range in camera space (+ = in front of the camera): the network's points and the links' lift
     above them, the layer planes and the subtree */
  function sceneDepth() {
    cam.updateMatrixWorld(true);
    var e = cam.matrixWorldInverse.elements, D = X.D, d0 = Infinity, d1 = -Infinity, L = liftMax();
    function add(x, y, z) { var d = -(e[2] * x + e[6] * y + e[10] * z + e[14]); if (d < d0) d0 = d; if (d > d1) d1 = d; }
    for (var i = 0; i < D.N; i++) {
      var x = D.pos[3 * i], y = D.pos[3 * i + 1], z = D.pos[3 * i + 2];
      add(x, y, z); add(x, y + L, z);
    }
    var E = D.extent * 1.06;
    for (var r = 0; r <= 5; r++) { var ly = layerY(r); add(-E, ly, -E); add(E, ly, -E); add(E, ly, E); add(-E, ly, E); }
    Object.keys(SP).forEach(function (id) { var p = SP[id]; add(p.x, p.y, p.z); });
    return [d0, d1];
  }
  /* near/far around the scene's depth range and the page's depth fade for this camera (the page's own frames compute
     the same fade in updateFog: it depends only on the camera's distance from the target) */
  function fitDepth() {
    var dist = checkCamera('capture'), dr = sceneDepth(), cp = TZ.clipPlanes(dr[0], dr[1]);
    if (!(dr[0] > 1)) throw new Error('the scene reaches behind the camera: depth ' + dr[0].toFixed(1) + ' to ' + dr[1].toFixed(1));
    cam.near = cp.near; cam.far = cp.far;
    cam.updateProjectionMatrix();
    var amount = X.fog.value.z > 0 ? X.fog.value.z : (X.P.dark ? 0.55 : 0.6);
    var f = TZ.fog(dist, X.D.extent, amount);
    X.fog.value.set(f.near, f.far, f.amount);
    return { distance: dist, depth: dr, clip: cp, fog: f };
  }

  /* WebGL context loss and restore (a large drawing buffer under SwiftShader can lose the context): recorded in
     __TEASER.events and logged as warnings, so that they reach console.log */
  function watchContext(cv) {
    if (!cv || !cv.addEventListener) return;
    ['webglcontextlost', 'webglcontextrestored', 'webglcontextcreationerror'].forEach(function (type) {
      cv.addEventListener(type, function (ev) {
        var e = { type: type, ms: Math.round(performance.now() - t0) };
        if (ev && ev.statusMessage) e.message = ev.statusMessage;
        T.events.push(e);
        console.warn('teaser: ' + type + (e.message ? ' (' + e.message + ')' : ''));
      });
    });
  }

  /* every bead's centre in device px and the colour it should show there: its class colour (raw, as the point shader
     writes it; the centre of the lit sphere has exactly that colour), faded toward the background by the page's depth
     fade at its distance from the camera */
  function beadProbes(pr, fit) {
    var e = cam.matrixWorldInverse.elements, col = beads.geometry.attributes.aColor.array, bg = X.points.material.uniforms.uBg.value;
    return beadIds.map(function (id, k) {
      var p = SP[id], s = screen(p), d = -(e[2] * p.x + e[6] * p.y + e[10] * p.z + e[14]), f = TZ.fogFactor(fit.fog, d);
      var exp = [col[3 * k], col[3 * k + 1], col[3 * k + 2]].map(function (c, j) { return Math.round(255 * (c * (1 - f) + [bg.r, bg.g, bg.b][j] * f)); });
      return { id: id, css: [+s.x.toFixed(2), +s.y.toFixed(2)], x: s.x * pr, y: s.y * pr, expected: exp };
    });
  }
  function beadVisible(p) {
    return !!p.got && Math.max(Math.abs(p.got[0] - p.expected[0]), Math.abs(p.got[1] - p.expected[1]), Math.abs(p.got[2] - p.expected[2])) <= 48;
  }

  /* pixels of the drawing buffer that differ from the background (any channel by more than 2 of 255), read with
     gl.readPixels right after the render in the same task, before the browser may clear the buffer */
  function inkOf(gl, probes) {
    var w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, t = performance.now(), buf = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
    (probes || []).forEach(function (p) {                        // device px, origin top left; GL rows run bottom up
      var x = Math.round(p.x), y = Math.round(p.y);
      if (x < 0 || y < 0 || x >= w || y >= h) { p.got = null; return; }
      var i = 4 * ((h - 1 - y) * w + x);
      p.got = [buf[i], buf[i + 1], buf[i + 2]];
    });
    var bg = new THREE.Color();
    X.renderer.getClearColor(bg);
    var hex = bg.getHex(), br = hex >> 16 & 255, bgr = hex >> 8 & 255, bb = hex & 255, n = 0, x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (var y = 0, i = 0; y < h; y++) {
      for (var x = 0; x < w; x++, i += 4) {
        if (Math.abs(buf[i] - br) > 2 || Math.abs(buf[i + 1] - bgr) > 2 || Math.abs(buf[i + 2] - bb) > 2) {
          n++;
          if (x < x0) x0 = x;
          if (x > x1) x1 = x;
          if (y < y0) y0 = y;
          if (y > y1) y1 = y;
        }
      }
    }
    return { nonbg: n, total: w * h, fraction: n / (w * h), background: '#' + bg.getHexString(), size: [w, h],
      bbox_px: n ? [x0, h - 1 - y1, x1, h - 1 - y0] : null, gl_error: gl.getError(), ms: Math.round(performance.now() - t) };
  }

  /* what a blank capture needs to be explained: camera and clipping, the depth fade, the scene's depth range, the
     renderer's draw counts, the canvas (size, CSS, visibility, what lies over its centre), limits, context state */
  function diagnostics(gl, fit, rinfo, ink) {
    var cv = X.renderer.domElement, rect = null, cs = {}, top = null, sf = X.scene.fog, fv = X.fog.value;
    try { rect = cv.getBoundingClientRect(); cs = window.getComputedStyle(cv); } catch (e) { rect = rect || null; }
    try {
      var el = rect && document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      if (el) top = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
        (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '');
    } catch (e) { top = null; }
    function gp(p) { try { var v = gl.getParameter(p); return v && v.length != null ? Array.prototype.slice.call(v) : v; } catch (e) { return null; } }
    var f = { near: fv.x, far: fv.y, amount: fv.z };
    return {
      camera: { type: cam.type, position: cam.position.toArray(), target: X.controls.target.toArray(), distance: fit.distance,
        near: cam.near, far: cam.far, zoom: cam.zoom, frustum: { left: cam.left, right: cam.right, top: cam.top, bottom: cam.bottom },
        controls: { enabled: X.controls.enabled, minDistance: X.controls.minDistance, maxDistance: String(X.controls.maxDistance) } },
      scene_depth: { min: fit.depth[0], max: fit.depth[1], inside_clip: fit.depth[0] > cam.near && fit.depth[1] < cam.far },
      fog: {
        scene_fog: sf ? { type: sf.isFogExp2 ? 'FogExp2' : 'Fog', colour: '#' + sf.color.getHexString(), near: sf.near, far: sf.far,
          density: sf.density } : null,
        depth_fade: { type: 'linear toward the background (shader uniform uFog)', colour: ink.background, near: f.near, far: f.far,
          amount: f.amount, at_scene_front: TZ.fogFactor(f, fit.depth[0]), at_target: TZ.fogFactor(f, fit.distance),
          at_scene_back: TZ.fogFactor(f, fit.depth[1]) } },
      render: rinfo,
      canvas: { pixels: [cv.width, cv.height], css: [cv.clientWidth, cv.clientHeight],
        rect: rect ? [rect.left, rect.top, rect.width, rect.height] : null, visibility: cs.visibility || null,
        display: cs.display || null, opacity: cs.opacity || null, device_pixel_ratio: window.devicePixelRatio || null,
        drawing_buffer: [gl.drawingBufferWidth, gl.drawingBufferHeight], max_renderbuffer_size: gp(gl.MAX_RENDERBUFFER_SIZE),
        max_viewport_dims: gp(gl.MAX_VIEWPORT_DIMS), max_texture_size: gp(gl.MAX_TEXTURE_SIZE),
        context_lost: gl.isContextLost(), element_at_centre: top },
      pixels: ink,
      points_uScale: X.points.material.uniforms.uScale.value,
      context_events: T.events.slice()
    };
  }

  function screen(p) {
    var v = new THREE.Vector3(p.x, p.y, p.z).project(cam);
    return { x: (v.x + 1) / 2 * vw, y: (1 - v.y) / 2 * vh };
  }
  function anchorsJson() {
    var D = X.D, k = 1 / TZ.cssPerPt(cfg), out = {}, maxd = 0;
    function rec(p, extra) {
      var s = screen(p), s2 = TZ.toScreen(cfg, p);
      maxd = Math.max(maxd, Math.abs(s.x - s2.x), Math.abs(s.y - s2.y));
      var r = { css: [+s.x.toFixed(2), +s.y.toFixed(2)], pt: [+(s.x * k).toFixed(2), +(s.y * k).toFixed(2)] };
      if (extra) Object.keys(extra).forEach(function (e) { r[e] = extra[e]; });
      return r;
    }
    var bs = beads.geometry.attributes.aSize.array, wpp = 2 * cfg.camera.half_height / vh;   // world units per CSS px
    beadIds.forEach(function (id, i) { out[id] = rec(SP[id], { r_pt: +(bs[i] / wpp / 2 * k).toFixed(2) }); });
    var E = D.extent * 1.06, layers = {};
    for (var r = 0; r <= 5; r++) {
      var y = layerY(r);
      var cs = [[-E, -E], [E, -E], [E, E], [-E, E]].map(function (q) { return rec({ x: q[0], y: y, z: q[1] }); });
      layers[r] = cs;
    }
    var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (var i = 0; i < D.N; i++) {
      if (!D.vis[i]) continue;
      var s = screen(ptOf(D, i));
      x0 = Math.min(x0, s.x); x1 = Math.max(x1, s.x); y0 = Math.min(y0, s.y); y1 = Math.max(y1, s.y);
    }
    Object.keys(layers).forEach(function (r) { layers[r].forEach(function (c) { x0 = Math.min(x0, c.css[0]); x1 = Math.max(x1, c.css[0]); y0 = Math.min(y0, c.css[1]); y1 = Math.max(y1, c.css[1]); }); });
    function line(pl) { return pl.map(function (p) { var s = screen(p); return [+(s.x * k).toFixed(2), +(s.y * k).toFixed(2)]; }); }
    return { anchors: out, layer_corners: layers, stack_bbox_css: [x0, y0, x1, y1].map(function (v) { return +v.toFixed(2); }),
      stack_bbox_pt: [x0 * k, y0 * k, x1 * k, y1 * k].map(function (v) { return +v.toFixed(2); }),
      paths_pt: { chain: line(paths.chain), trace: line(paths.trace), thin: paths.thin.map(line) }, projection_check_px: maxd };
  }

  T.capture = function (name) {
    var cap = cfg.captures.filter(function (c) { return c.name === name; })[0];
    if (!cap) return Promise.reject(new Error('no capture named ' + name));
    var r = X.renderer, u = X.points.material.uniforms.uScale;
    return Promise.resolve().then(function () {
      /* the page's own frames run at 1x (cheap under SwiftShader): they upload the colours and, for the site's labels,
         place the call-outs; only the capture itself is rendered at its pixel ratio */
      r.setPixelRatio(1);
      r.setSize(vw, vh);
      u.value = TZ.pointScale(cfg, 1, fitDepth().distance);
      setColors(cap.colorBy || cfg.page.colorBy);
      X.labels.visible = cap.labels === 'site';
      C.render();
      return frames(3);
    }).then(function () {
      if (cap.labels !== 'site') return null;
      var last = -1, same = 0;
      return until(function () {
        var f = M.calloutFrames || 0;
        same = f === last ? same + 1 : 0; last = f;
        return M.labelsShown != null && same >= 5;
      }, 'call-outs settled').then(function () { return frames(2); });
    }).then(function () {
      r.setPixelRatio(cap.pixelRatio);
      r.setSize(vw, vh);
      var fit = fitDepth();
      u.value = TZ.pointScale(cfg, cap.pixelRatio, fit.distance);
      var gl = r.getContext(), t1 = performance.now();
      r.render(X.scene, cam);
      var ri = r.info.render, rinfo = { calls: ri.calls, triangles: ri.triangles, points: ri.points, lines: ri.lines,
        frame: ri.frame, ms: Math.round(performance.now() - t1) };
      var probes = beadProbes(cap.pixelRatio, fit);
      var ink = inkOf(gl, probes);                  // same task as the render: the drawing buffer is still there
      var hidden = probes.filter(function (p) { return !beadVisible(p); }).map(function (p) { return p.id; });
      var url = r.domElement.toDataURL('image/png');
      var info = { name: name, pixelRatio: cap.pixelRatio, width: r.domElement.width, height: r.domElement.height,
        colorBy: T.colorBy, labels: cap.labels, labelsShown: cap.labels === 'site' ? M.labelsShown : 0,
        ink: +ink.fraction.toFixed(6), blank: ink.fraction < MIN_INK, hidden_beads: hidden, diag: diagnostics(gl, fit, rinfo, ink) };
      info.diag.beads = probes.map(function (p) { return { id: p.id, css: p.css, expected: p.expected, got: p.got, visible: beadVisible(p) }; });
      T.json.captures.push(info);
      step('captured ' + name, { name: name, pixelRatio: info.pixelRatio, width: info.width, height: info.height,
        colorBy: info.colorBy, labels: info.labels, labelsShown: info.labelsShown, ink: info.ink, blank: info.blank,
        calls: rinfo.calls, render_ms: rinfo.ms, near: cam.near, far: cam.far, depth: fit.depth, hidden_beads: hidden.length });
      if (hidden.length) console.warn('teaser: ' + name + ': beads hidden (centre pixel not the bead colour): ' + hidden.join(', '));
      if (info.blank) console.warn('teaser: ' + name + ' is blank: ' + ink.nonbg + ' of ' + ink.total + ' pixels differ from ' + ink.background);
      return { url: url, width: info.width, height: info.height, ink: info.ink, blank: info.blank, hidden_beads: hidden, diag: info.diag };
    });
  };

  until(function () { return window.__VLONTO_READY === true && window.VLApp && window.VLApp.capture; }, 'the network page').then(function () {
    step('page ready', { fps: M.fps, webgl: M.webglRenderer, nodes: M.nodes });
    C = window.VLApp.capture; X = C.get(); THREE = X.THREE;
    watchContext(X.renderer.domElement);
    if (!X.D || X.D.name !== cfg.page.dataset) throw new Error('dataset ' + (X.D && X.D.name) + ', expected ' + cfg.page.dataset);
    Object.keys(X.edges).forEach(function (k) {
      var o = X.edges[k] && X.edges[k].obj, u = o && o.material && o.material.uniforms && o.material.uniforms.uOpacity;
      if (u) base[k] = u.value;
    });
    if (!C.select(cfg.selection.doc)) throw new Error('document ' + cfg.selection.doc + ' not in the network');
    return until(function () { return M.panelLoaded === cfg.selection.doc && M.chainTraceDocs >= 2; }, 'the selection and its chain');
  }).then(function () {
    return frames(2);                                // the page's own resize after the panel opened runs first
  }).then(function () {
    X = C.get();                                     // chainIdx is filled now
    var chain = X.chainIdx.map(function (i) { return X.D.ids[i]; });
    if (chain.join(',') !== cfg.selection.chain.join(',')) throw new Error('replacement chain ' + chain.join(' > ') + ', expected ' + cfg.selection.chain.join(' > '));
    step('selected', { doc: cfg.selection.doc, chain: chain, egoHop1: M.egoHop1 });
    var k = TZ.cssPerPt(cfg);
    VL.TRACE_W.core = cfg.trace_pt.core * k; VL.TRACE_W.halo = cfg.trace_pt.halo * k; VL.TRACE_W.halo2 = cfg.trace_pt.halo2 * k;
    X.chain.setStyle(VL.traceStyle(X.P, 1));
    useCamera();
    buildSubtree();
    fade();
    var fit = fitDepth();                            // near/far around the scene with its subtree, the depth fade
    X = C.get();
    T.json = {
      about: 'Fig. 1 capture of the 3D legal network (scripts/site/teaser); figure points have their origin at the top left',
      config: cfg, figure_pt: [cfg.figure.width_pt, cfg.figure.height_pt], viewport_css: [vw, vh],
      checks: { min_ink_fraction: MIN_INK },
      camera: { projection: 'orthographic', position: cam.position.toArray(), target: X.controls.target.toArray(), up: cam.up.toArray(),
        left: cam.left, right: cam.right, top: cam.top, bottom: cam.bottom, near: cam.near, far: cam.far, zoom: cam.zoom,
        distance: fit.distance, scene_depth: fit.depth, depth_fade: fit.fog,
        projectionMatrix: cam.projectionMatrix.toArray(), matrixWorldInverse: cam.matrixWorldInverse.toArray() },
      selection: { doc: cfg.selection.doc, chain: X.chainIdx.map(function (i) { return X.D.ids[i]; }), egoHop1: M.egoHop1,
        egoEdges: M.egoEdges, qa: tr.qa },
      page: { dataset: X.D.name, nodes: X.D.N, edges: M.edges, edgeSegments: M.edgeSegments, fps: M.fps, webglRenderer: M.webglRenderer,
        curves: !!(M.edgeCost && M.edgeCost.curves) },
      trace_widths_css: { core: VL.TRACE_W.core, halo: VL.TRACE_W.halo, halo2: VL.TRACE_W.halo2 },
      captures: []
    };
    var a = anchorsJson();
    Object.keys(a).forEach(function (key) { T.json[key] = a[key]; });
    step('scene ready', { projection_check_px: a.projection_check_px, distance: fit.distance, near: cam.near, far: cam.far,
      scene_depth: fit.depth, depth_fade: fit.fog });
    T.ready = true;
  }).catch(function (e) {
    T.error = String(e && e.message || e);
    step('error', T.error);
    console.error('teaser:', e);
  });
})();

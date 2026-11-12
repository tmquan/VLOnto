/* Fig. 1 capture harness (scripts/site/teaser; not part of the site). Runs in teaser.html - site/network-3d.html copied
   by make_page.py with a <base> into site/ - after js/network3d.js, teaser_data.js (config + trace) and teaser-core.js.
   1. wait for the page (window.__VLONTO_READY: full network built, frame rate measured), note the links' opacities;
   2. select the Labor Code without the camera flight (VLApp.capture.select) and wait for its replacement chain;
   3. swap in the orthographic camera of teaser_config.json (fixed pose, no damping), the paper's trace weights;
   4. fade the context outside the selection's neighbourhood; hang the trace subtree from the Labor Code: the traced
      hops as one path on the links' curve (navy core, gold halo), thin branches to Art. 3(1) and the terms, beads on top;
   5. expose window.__TEASER: ready, capture(name) -> {url: PNG data URL of the WebGL canvas, width, height} rendered at
      that capture's pixel ratio and colouring, and json (camera, selection, anchors in CSS px and figure pt, metrics).
   No sleeps: every wait is on a page metric or a frame. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS, TZ = window.TZ, DATA = window.VLONTO_TEASER;
  var T = window.__TEASER = { ready: false, error: null, steps: [], json: null };
  if (!DATA || !TZ) { T.error = 'teaser_data.js or teaser-core.js missing'; return; }
  var cfg = DATA.config, tr = DATA.trace, vw = cfg.viewport.width, vh = cfg.viewport.height;
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
      fragmentShader: pm.fragmentShader, depthTest: false, depthWrite: false, transparent: false }));
    beads.renderOrder = 14;
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
      var y = (D.layerZ[r] != null ? D.layerZ[r] : (5 - r) * 150) * X.ZS - 2;
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
    var r = X.renderer;
    return Promise.resolve().then(function () {
      setColors(cap.colorBy || cfg.page.colorBy);
      X.labels.visible = cap.labels === 'site';
      r.setPixelRatio(cap.pixelRatio);
      r.setSize(vw, vh);
      X.points.material.uniforms.uScale.value = TZ.pointScale(cfg, cap.pixelRatio);
      C.render();
      return frames(3);                           // the page renders a frame and sets the depth fade for this camera
    }).then(function () {
      if (cap.labels !== 'site') return null;
      var last = -1, same = 0;
      return until(function () {
        var f = M.calloutFrames || 0;
        same = f === last ? same + 1 : 0; last = f;
        return M.labelsShown != null && same >= 5;
      }, 'call-outs settled').then(function () { return frames(2); });
    }).then(function () {
      r.render(X.scene, cam);
      var url = r.domElement.toDataURL('image/png');
      var info = { name: name, pixelRatio: cap.pixelRatio, width: r.domElement.width, height: r.domElement.height,
        colorBy: T.colorBy, labels: cap.labels, labelsShown: cap.labels === 'site' ? M.labelsShown : 0 };
      T.json.captures.push(info);
      step('captured ' + name, info);
      return { url: url, width: info.width, height: info.height };
    });
  };

  until(function () { return window.__VLONTO_READY === true && window.VLApp && window.VLApp.capture; }, 'the network page').then(function () {
    step('page ready', { fps: M.fps, webgl: M.webglRenderer, nodes: M.nodes });
    C = window.VLApp.capture; X = C.get(); THREE = X.THREE;
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
    X = C.get();
    T.json = {
      about: 'Fig. 1 capture of the 3D legal network (scripts/site/teaser); figure points have their origin at the top left',
      config: cfg, figure_pt: [cfg.figure.width_pt, cfg.figure.height_pt], viewport_css: [vw, vh],
      camera: { projection: 'orthographic', position: cam.position.toArray(), target: X.controls.target.toArray(), up: cam.up.toArray(),
        left: cam.left, right: cam.right, top: cam.top, bottom: cam.bottom, near: cam.near, far: cam.far, zoom: cam.zoom,
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
    step('scene ready', { projection_check_px: a.projection_check_px });
    T.ready = true;
  }).catch(function (e) {
    T.error = String(e && e.message || e);
    step('error', T.error);
    console.error('teaser:', e);
  });
})();

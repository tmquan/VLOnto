/* VLOnto - the paper style of the 3D views (the figures of arXiv:2611.11426, Fig. 1 and Fig. 6), shared by
   js/ontology3d.js, js/network3d.js and js/sparql-page.js:
   * VL.paperTheme(el)   colours of the current theme from css/site.css ("paper style" tokens), read from <html> or from
                         an element with data-style="paper"
   * VL.paperLights()    soft light from the upper left of the screen (ambient + a directional light that moves with the
                         camera), so the pastel spheres keep their colour and get the paper's gentle shading
   * VL.paperFog()       depth fade towards the background (VL.fitFog keeps it relative to the camera distance)
   * VL.TraceLines()     the traced path: a navy core over a pale-gold halo (two halo tones), drawn as screen-space
                         lines of constant pixel width with round caps and joins (WebGL lines are 1 px wide); widths
                         are capped (VL.traceStyle), and only the path itself is traced (the chain, a hovered link, or
                         every link of a small selection or result)
   * VL.ColorLines()     thin lines of constant pixel width, each in its own colour: a selection's other links,
                         emphasised in their link-type colours but not traced
   * VL.Callouts()       screen-space placement of the call-outs: text never hides graph ink, call-outs never overlap
   * VL.fitLegend()      moves the legend up above the status line where the two would meet on the stage's bottom edge
   Classic script (works from file://); load after vendor/three/three.iife.min.js, js/common.js and js/labels3d.js. */
(function () {
  'use strict';
  var VL = window.VL;

  /* ------------------------------------------------------------------ tokens */
  VL.paperTheme = function (el) {
    var t = function (n, fb) { return VL.tok(n, el) || fb; };
    var num = function (n, fb) { var v = parseFloat(VL.tok(n, el)); return isNaN(v) ? fb : v; };
    var cls = {};
    VL.PAPER_CLASSES.forEach(function (c) { cls[c.key] = t('--cls-' + c.key, c.color); });
    return {
      dark: VL.theme() === 'dark',
      bg: t('--scene-bg', '#ffffff'),
      ink: t('--paper-ink', '#2b3036'), ink2: t('--paper-ink-2', '#666c73'),
      calloutBg: t('--paper-callout-bg', '#ffffff'), calloutLine: t('--paper-callout-line', '#d3d7dc'), leader: t('--paper-leader', '#a2a8af'),
      core: t('--paper-trace-core', '#2c3a47'), halo: t('--paper-trace-halo', '#ecc890'), halo2: t('--paper-trace-halo-2', '#f4dcac'),
      selBg: t('--paper-sel-bg', '#fdf6e6'), selLine: t('--paper-sel-line', '#2c3a47'),
      fade: num('--paper-fade', 0.2), linkOpacity: num('--paper-link-opacity', 0.7),
      cls: cls
    };
  };
  /* call-out options for VL.TextSprite in the paper style (white box, 1 px light-grey border, square-ish corners,
     Libertinus Sans, thin grey leader line); sel = the selected node's call-out (pale-gold box, border in the core colour) */
  VL.paperCallout = function (P, sel) {
    return { font: VL.PAPER_FONT, bg: sel ? P.selBg : P.calloutBg, border: sel ? P.selLine : P.calloutLine, borderPx: sel ? 1.5 : 1,
      radius: 1.5, leaderColor: P.leader, ink: P.ink, ink2: P.ink2 };
  };
  /* ------------------------------------------------------------------ call-out text in the language mode
     (js/i18n.js, docs/i18n.md). EN and VI: one line in that language (the other one where a record has none, e.g. a
     Vietnamese document title in EN). EN–VI: the paper's "Tiếng Việt · English" in its two greys, on one line when
     short, else Vietnamese over the English gloss (as in Fig. 1). opts: oneLine (characters on one line, default 34),
     twoLines (EN–VI always on two lines), secondary (the whole call-out in the second grey: external terms). */
  function tlLines(t, P, opts) {
    var a = VL.nfc(t.primary), b = VL.nfc(t.secondary);
    if (b) {
      if (!opts.twoLines && a.length + b.length + 3 <= (opts.oneLine || 34)) return [[{ text: a, color: P.ink }, { text: ' · ' + b, color: P.ink2 }]];
      return [[{ text: a, color: P.ink }], [{ text: b, color: P.ink2 }]];
    }
    return [[{ text: a, color: opts.secondary ? P.ink2 : P.ink }]];
  }
  /* parts of a call-out for a pair of data fields (Vietnamese, English) */
  VL.paperLines = function (vi, en, P, opts) { return tlLines(VL.TL(VL.pair(vi || '', en || '')), P, opts || {}); };
  /* parts of a call-out for a dictionary entry (js/i18n-3d.js) or a {vi, en} record, placeholders filled */
  VL.paperTL = function (x, vars, P, opts) { return tlLines(VL.TL(x, vars), P, opts || {}); };
  /* {vi, en} of a dictionary entry with its {placeholders} filled, in both languages whatever the mode (call-outs and
     labels that pass the pair on to VL.paperLines); a value may be text or a {vi, en} record */
  VL.kpair = function (key, vars) {
    var e = (VL.i18n && VL.i18n.get(key)) || { en: key, vi: '' };
    function fill(s, l) {
      return String(s || '').replace(/\{(\w+)\}/g, function (m0, k) {
        var v = vars ? vars[k] : null;
        if (v != null && typeof v === 'object') v = v[l] || v.en || v.vi;
        return v != null ? String(v) : m0;
      });
    }
    return VL.pair(fill(e.vi, 'vi'), fill(e.en, 'en'));
  };

  /* ------------------------------------------------------------------ light and fog */
  /* returns the lights for graph.lights(); call VL.attachCameraLight(scene, camera, light) for the directional one */
  VL.paperLights = function (dark) {
    var amb = new THREE.AmbientLight(0xffffff, (dark ? 0.70 : 0.76) * Math.PI);
    var dir = new THREE.DirectionalLight(0xffffff, (dark ? 0.40 : 0.34) * Math.PI);
    return { ambient: amb, directional: dir };
  };
  /* the directional light rides on the camera: always from the upper left of the screen, like the spheres of the paper */
  VL.attachCameraLight = function (scene, camera, light) {
    if (!camera.parent) scene.add(camera);
    light.position.set(-0.55, 0.85, 0.6);
    camera.add(light);
    light.target.position.set(0, 0, -1);
    camera.add(light.target);
  };
  VL.paperFog = function (scene, color) {
    scene.fog = new THREE.Fog(new THREE.Color(color), 1, 1e6);
    return scene.fog;
  };
  /* soft depth fade: nothing in front of the scene centre, about half way to the background at its far side */
  VL.fitFog = function (fog, camDist, radius) {
    if (!fog || !isFinite(camDist) || !isFinite(radius) || radius <= 0) return;
    fog.near = Math.max(0.1, camDist - 0.5 * radius);
    fog.far = camDist + 2.6 * radius;
  };

  /* ------------------------------------------------------------------ the traced path */
  /* Each segment is a quad expanded in screen space by half the line width and extended by the same amount at both ends;
     the fragment shader keeps the pixels within half the width of the segment (a capsule), so caps and joins are round.
     Colours are uploaded as sRGB values and written unchanged (no colour management in this shader), like the CSS. */
  var TR_VS = [
    'attribute vec3 aOther; attribute float aSide; attribute float aEnd;',
    'uniform vec2 uRes; uniform float uWidth;',
    'varying vec2 vA; varying vec2 vB; varying float vHalf;',
    'vec2 toWin(vec4 c) { return (c.xy / c.w * 0.5 + 0.5) * uRes; }',
    'void main() {',
    '  vec4 a = modelViewMatrix * vec4(position, 1.0);',
    '  vec4 b = modelViewMatrix * vec4(aOther, 1.0);',
    '  float near = projectionMatrix[3][2] / (projectionMatrix[2][2] - 1.0);',
    '  float zn = -near * 1.001;',
    '  if (a.z > zn && b.z > zn) { gl_Position = vec4(0.0, 0.0, 2.0, 1.0); vA = vec2(0.0); vB = vec2(0.0); vHalf = 0.0; return; }',
    '  if (a.z > zn) a = mix(a, b, (a.z - zn) / (a.z - b.z));',
    '  if (b.z > zn) b = mix(b, a, (b.z - zn) / (b.z - a.z));',
    '  vec4 ca = projectionMatrix * a;',
    '  vec4 cb = projectionMatrix * b;',
    '  vec2 wa = toWin(ca), wb = toWin(cb);',
    '  vec2 d = wb - wa; float len = length(d);',
    '  d = len > 0.001 ? d / len : vec2(1.0, 0.0);',
    '  float h = 0.5 * uWidth;',
    '  vec2 w = wa + (vec2(-d.y, d.x) * aSide - d) * (h + 1.0);',
    '  gl_Position = vec4((w / uRes * 2.0 - 1.0) * ca.w, ca.z, ca.w);',
    '  vA = aEnd < 0.5 ? wa : wb; vB = aEnd < 0.5 ? wb : wa; vHalf = h;',
    '}'].join('\n');
  var TR_FS = [
    'uniform vec3 uColor; uniform float uOpacity;',
    'varying vec2 vA; varying vec2 vB; varying float vHalf;',
    'void main() {',
    '  vec2 p = gl_FragCoord.xy, ab = vB - vA;',
    '  float t = clamp(dot(p - vA, ab) / max(dot(ab, ab), 0.000001), 0.0, 1.0);',
    '  float a = clamp(vHalf + 0.5 - length(p - vA - ab * t), 0.0, 1.0);',
    '  if (a <= 0.0) discard;',
    '  gl_FragColor = vec4(uColor, uOpacity * a);',
    '}'].join('\n');
  /* the same ribbons with a colour per vertex (VL.ColorLines) */
  var CL_VS = TR_VS.replace('attribute vec3 aOther;', 'attribute vec3 aOther; attribute vec3 aColor; varying vec3 vColor;')
    .replace('void main() {', 'void main() {\n  vColor = aColor;');
  var CL_FS = TR_FS.replace('uniform vec3 uColor; uniform float uOpacity;', 'uniform float uOpacity; varying vec3 vColor;')
    .replace('gl_FragColor = vec4(uColor, uOpacity * a);', 'gl_FragColor = vec4(vColor, uOpacity * a);');
  function rawColor(hex, c) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    var n = m ? parseInt(m[1], 16) : 0x888888;
    return c.setRGB((n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
  }
  VL.rawColor = rawColor;
  /* segment buffers of the ribbons (four vertices and two triangles per segment): they grow by half when needed (the old
     geometry is freed) and are rewritten in place otherwise, since the ontology view updates them on every layout tick */
  function Ribbons(withColor, meshes) {
    var R = { geo: new THREE.BufferGeometry(), cap: 0, n: 0 };
    function ensure(n) {
      if (n <= R.cap) return;
      var cap = Math.max(64, n, Math.ceil(R.cap * 1.5));
      var g2 = new THREE.BufferGeometry();
      var side = new Float32Array(cap * 4), end = new Float32Array(cap * 4);
      var idx = cap * 4 > 65535 ? new Uint32Array(cap * 6) : new Uint16Array(cap * 6);
      for (var v = 0; v < cap * 4; v++) { side[v] = v % 2 === 0 ? 1 : -1; end[v] = v % 4 < 2 ? 0 : 1; }
      for (var q = 0; q < cap; q++) {
        var o = q * 4;
        idx[q * 6] = o; idx[q * 6 + 1] = o + 1; idx[q * 6 + 2] = o + 2;
        idx[q * 6 + 3] = o; idx[q * 6 + 4] = o + 2; idx[q * 6 + 5] = o + 3;
      }
      g2.setAttribute('position', new THREE.BufferAttribute(new Float32Array(cap * 12), 3));
      g2.setAttribute('aOther', new THREE.BufferAttribute(new Float32Array(cap * 12), 3));
      if (withColor) g2.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(cap * 12), 3));
      g2.setAttribute('aSide', new THREE.BufferAttribute(side, 1));
      g2.setAttribute('aEnd', new THREE.BufferAttribute(end, 1));
      g2.setIndex(new THREE.BufferAttribute(idx, 1));
      R.geo.dispose();
      R.geo = g2;
      R.cap = cap;
      meshes.forEach(function (m) { m.geometry = g2; });
    }
    /* paths: [[p0, p1, ...], ...] of points with x, y, z; colors (withColor only): one hex colour per path */
    R.write = function (paths, colors) {
      var n = 0;
      (paths || []).forEach(function (pl) { if (pl && pl.length > 1) n += pl.length - 1; });
      ensure(n);
      if (n) {
        var A = R.geo.attributes, pos = A.position.array, oth = A.aOther.array, col = withColor ? A.aColor.array : null;
        var c = new THREE.Color(), s = 0;
        (paths || []).forEach(function (pl, pi) {
          if (!pl || pl.length < 2) return;
          if (col) rawColor(colors && colors[pi], c);
          for (var i = 0; i + 1 < pl.length; i++, s++) {
            var a = pl[i], b = pl[i + 1];
            for (var k = 0; k < 4; k++) {
              var own = k < 2 ? a : b, other = k < 2 ? b : a, v = s * 4 + k;
              pos[3 * v] = own.x; pos[3 * v + 1] = own.y || 0; pos[3 * v + 2] = own.z || 0;
              oth[3 * v] = other.x; oth[3 * v + 1] = other.y || 0; oth[3 * v + 2] = other.z || 0;
              if (col) { col[3 * v] = c.r; col[3 * v + 1] = c.g; col[3 * v + 2] = c.b; }
            }
          }
        });
        A.position.needsUpdate = true;
        A.aOther.needsUpdate = true;
        if (col) A.aColor.needsUpdate = true;
      }
      R.geo.setDrawRange(0, n * 6);
      R.n = n;
      return n;
    };
    return R;
  }
  /* widths of the traced path at full weight, in CSS px: a cap (VL.traceStyle never exceeds them), so a trace stays a
     line of the figure on a phone and on a hub */
  var TRACE_W = { core: 2.8, halo: 6.4, halo2: 9.2 };
  VL.TRACE_W = TRACE_W;
  /* opts: depthTest (default true), renderOrder (halo2, halo, core get renderOrder, +1, +2), widths {core, halo, halo2} in
     CSS px, colors {core, halo, halo2} (hex). setPaths([[p0, p1, ...], ...]) takes points with x, y, z. */
  VL.TraceLines = function (opts) {
    opts = opts || {};
    var group = new THREE.Group();
    group.name = 'vlonto-trace';
    var widths = { halo2: TRACE_W.halo2, halo: TRACE_W.halo, core: TRACE_W.core }, colors = { halo2: '#f4dcac', halo: '#ecc890', core: '#2c3a47' };
    var size = new THREE.Vector2(), layers = {}, meshes = [], R = Ribbons(false, meshes);
    ['halo2', 'halo', 'core'].forEach(function (k, i) {
      var mat = new THREE.ShaderMaterial({
        uniforms: { uRes: { value: new THREE.Vector2(1, 1) }, uWidth: { value: 1 }, uColor: { value: new THREE.Color() }, uOpacity: { value: 1 } },
        vertexShader: TR_VS, fragmentShader: TR_FS, transparent: true, depthWrite: false, depthTest: opts.depthTest !== false,
        side: THREE.DoubleSide
      });
      var mesh = new THREE.Mesh(R.geo, mat);
      mesh.frustumCulled = false;
      mesh.renderOrder = (opts.renderOrder || 8) + i;
      mesh.onBeforeRender = function (renderer) {
        renderer.getDrawingBufferSize(size);
        mat.uniforms.uRes.value.copy(size);
        mat.uniforms.uWidth.value = widths[k] * renderer.getPixelRatio();
      };
      layers[k] = { mesh: mesh, mat: mat };
      meshes.push(mesh);
      group.add(mesh);
    });
    function setStyle(st) {
      st = st || {};
      if (st.widths) Object.keys(st.widths).forEach(function (k) { widths[k] = Math.min(TRACE_W[k], st.widths[k]); });
      if (st.colors) Object.keys(st.colors).forEach(function (k) { colors[k] = st.colors[k]; });
      Object.keys(layers).forEach(function (k) {
        rawColor(colors[k], layers[k].mat.uniforms.uColor.value);
        layers[k].mesh.visible = widths[k] > 0 && R.n > 0;
      });
      if (st.opacity != null) Object.keys(layers).forEach(function (k) { layers[k].mat.uniforms.uOpacity.value = st.opacity; });
    }
    function setPaths(paths) {
      R.write(paths);
      setStyle({});
      return R.n;
    }
    function dispose() {
      R.geo.dispose();
      Object.keys(layers).forEach(function (k) { layers[k].mat.dispose(); });
    }
    setStyle({});
    return { object: group, setPaths: setPaths, setStyle: setStyle, count: function () { return R.n; }, dispose: dispose };
  };
  /* trace style of the theme: navy core (light core on the dark ground) over the two gold tones; w (at most 1) scales the
     capped widths */
  VL.traceStyle = function (P, w) {
    w = Math.max(0.3, Math.min(1, w || 1));
    return { colors: { core: P.core, halo: P.halo, halo2: P.halo2 },
      widths: { core: TRACE_W.core * w, halo: TRACE_W.halo * w, halo2: TRACE_W.halo2 * w }, opacity: P.dark ? 0.96 : 1 };
  };
  /* thin lines, each in its own colour, at constant pixel width: the links of a selection that are not on the traced
     path, emphasised in their link-type colours (the paper keeps them pastel). opts: depthTest (default true),
     renderOrder, width (CSS px), opacity. setPaths(paths, colors) takes one hex colour per path. */
  VL.ColorLines = function (opts) {
    opts = opts || {};
    var width = opts.width || 1.6, size = new THREE.Vector2(), meshes = [], R = Ribbons(true, meshes);
    var mat = new THREE.ShaderMaterial({
      uniforms: { uRes: { value: new THREE.Vector2(1, 1) }, uWidth: { value: 1 }, uOpacity: { value: opts.opacity != null ? opts.opacity : 0.95 } },
      vertexShader: CL_VS, fragmentShader: CL_FS, transparent: true, depthWrite: false, depthTest: opts.depthTest !== false,
      side: THREE.DoubleSide
    });
    var mesh = new THREE.Mesh(R.geo, mat);
    mesh.name = 'vlonto-lines';
    mesh.frustumCulled = false;
    mesh.renderOrder = opts.renderOrder || 5;
    mesh.visible = false;
    mesh.onBeforeRender = function (renderer) {
      renderer.getDrawingBufferSize(size);
      mat.uniforms.uRes.value.copy(size);
      mat.uniforms.uWidth.value = width * renderer.getPixelRatio();
    };
    meshes.push(mesh);
    return {
      object: mesh,
      setPaths: function (paths, colors) { R.write(paths, colors); mesh.visible = R.n > 0; return R.n; },
      setStyle: function (st) {
        st = st || {};
        if (st.width != null) width = st.width;
        if (st.opacity != null) mat.uniforms.uOpacity.value = st.opacity;
      },
      count: function () { return R.n; },
      dispose: function () { R.geo.dispose(); mat.dispose(); }
    };
  };
  /* colour of a link by its predicate (CONSTRUCT results): the change, basis and citation colours of the legal network,
     the ontology's subclass and instance colours, else the default link colour; el = the element that scopes the tokens */
  var PRED_TOKEN = { replaces: '--chg-replaced', amends: '--chg-amended', repeals: '--chg-repealed', partiallyRepeals: '--chg-partially_repealed',
    partiallyExpires: '--chg-partially_expired', legalBasis: '--edge-basis', cites: '--edge-citation', subClassOf: '--o3d-link-subclass',
    type: '--o3d-link-instance' };
  /* a hex colour scaled by f (f < 1: deeper), for thin lines that must read on the white ground */
  VL.shade = function (hex, f) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim()), v = m ? parseInt(m[1], 16) : 0x888888;
    return '#' + [v >> 16, (v >> 8) & 255, v & 255].map(function (c) { c = Math.max(0, Math.min(255, Math.round(c * f))); return (c < 16 ? '0' : '') + c.toString(16); }).join('');
  };
  VL.predKind = function (pred) { return String(pred || '').split(/[#:\/]/).pop(); };
  VL.predColor = function (pred, el) { return VL.tok(PRED_TOKEN[VL.predKind(pred)] || '--o3d-link-default', el) || '#9aa3ad'; };
  /* points of a link drawn by 3d-force-graph (curved links keep their curve in link.__curve) */
  VL.linkPoints = function (l, n) {
    if (l.__curve && l.__curve.getPoints) return l.__curve.getPoints(n || 16);
    var s = l.source, t = l.target;
    if (!s || !t || typeof s !== 'object' || typeof t !== 'object' || !isFinite(s.x) || !isFinite(t.x)) return null;
    return [{ x: s.x, y: s.y || 0, z: s.z || 0 }, { x: t.x, y: t.y || 0, z: t.z || 0 }];
  };

  /* ------------------------------------------------------------------ call-out placement (screen-space declutter) */
  /* The paper's rule: text never hides graph ink, call-outs sit in clear space beside the graph on thin leader lines and
     never overlap. A run projects the labelled anchors, the node discs and the links (the "ink") to the canvas (CSS px)
     and places the call-outs one by one: selected and traced ones first, then by priority. Each tries 13 directions
     (outward from the graph centre first) x 7 leader lengths (10 for selected and traced ones), cheapest first (short leaders, small turns, and the
     call-out's previous position, so call-outs do not jump), and takes the first position whose box stays inside the
     canvas and clear of the overlays, of the boxes and leaders already placed, of every node disc and every link. A
     call-out without such a position is hidden (lowest priority first). Selected and traced call-outs ("must", at most
     mustMax of them, by priority) are placed first and, failing that, take the position clear of other call-outs,
     overlays and node centres that covers the least ink; the selected node's own call-out ("sel") may, as a last
     resort, cover the fewest node centres. A must call-out that still has no position is hidden and counted
     (mustHidden): call-outs never overlap. schedule() throttles runs while the camera moves or the layout ticks and adds
     one when they stop.
     cfg: camera(), size() -> {w, h} CSS px, items() -> [{id, sprite (VL.TextSprite, anchored at its node), pri, must,
     sel, r (world radius of the node) or rpx, fixed: [ox, oy] or fn(w, h) (a box at that offset, no leader), off}],
     ink() -> {discs: [{id, x, y, z, r | rpx}], paths: [[{x, y, z}, ...], ...]}, ui() -> [{x0, y0, x1, y1}] overlays,
     leaderColor() -> hex, discMaxPx, segCap, mustMax (8), metrics (object) + key, onDone(stats). */
  var DIRS = [0, 25, -25, 50, -50, 75, -75, 100, -100, 130, -130, 160, 180];
  var LENS = [10, 22, 38, 60, 90, 130, 180], LENS_MUST = LENS.concat([240, 320, 420]);   // must: longer leaders to the periphery
  function Grid(W, H, cs) {
    this.cs = cs;
    this.nx = Math.max(1, Math.ceil(W / cs));
    this.ny = Math.max(1, Math.ceil(H / cs));
    this.cells = new Array(this.nx * this.ny);
    this.stamp = 0;
  }
  Grid.prototype.range = function (x0, y0, x1, y1, fn) {
    var cs = this.cs, i0 = Math.max(0, Math.floor(x0 / cs)), i1 = Math.min(this.nx - 1, Math.floor(x1 / cs));
    var j0 = Math.max(0, Math.floor(y0 / cs)), j1 = Math.min(this.ny - 1, Math.floor(y1 / cs));
    for (var j = j0; j <= j1; j++) for (var i = i0; i <= i1; i++) fn(j * this.nx + i);
  };
  Grid.prototype.add = function (o, x0, y0, x1, y1) {
    var cells = this.cells;
    this.range(x0, y0, x1, y1, function (c) { (cells[c] || (cells[c] = [])).push(o); });
  };
  /* a segment goes into the cells along it (in pieces at most one cell long), not into its whole bounding box */
  Grid.prototype.addSeg = function (o) {
    var dx = o.x1 - o.x0, dy = o.y1 - o.y0, n = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / this.cs)), cells = this.cells;
    function put(c) { var cl = cells[c] || (cells[c] = []); if (cl[cl.length - 1] !== o) cl.push(o); }
    for (var k = 0; k < n; k++) {
      var ax = o.x0 + dx * k / n, ay = o.y0 + dy * k / n, bx = o.x0 + dx * (k + 1) / n, by = o.y0 + dy * (k + 1) / n;
      this.range(Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by), put);
    }
  };
  /* sum of fn(o) over the distinct items in the cells of a rectangle; stop at the first non-zero when first is set */
  Grid.prototype.sum = function (x0, y0, x1, y1, fn, first) {
    var st = ++this.stamp, cells = this.cells, total = 0;
    this.range(x0, y0, x1, y1, function (c) {
      if (first && total) return;
      var cl = cells[c];
      if (!cl) return;
      for (var i = 0; i < cl.length; i++) {
        var o = cl[i];
        if (o._st === st) continue;
        o._st = st;
        total += fn(o) || 0;
        if (first && total) return;
      }
    });
    return total;
  };
  function rectRect(a, b, pad) { return !(a.x1 + pad <= b.x0 || a.x0 - pad >= b.x1 || a.y1 + pad <= b.y0 || a.y0 - pad >= b.y1); }
  function rectPt(b, x, y, pad) { return x > b.x0 - pad && x < b.x1 + pad && y > b.y0 - pad && y < b.y1 + pad; }
  function rectDisc(b, d, pad) {
    var dx = Math.max(b.x0 - d.x, 0, d.x - b.x1), dy = Math.max(b.y0 - d.y, 0, d.y - b.y1);
    return dx * dx + dy * dy < (d.r + pad) * (d.r + pad);
  }
  /* segment against a rectangle grown by pad (Liang-Barsky) */
  function segRect(s, b, pad) {
    var x0 = b.x0 - pad, x1 = b.x1 + pad, y0 = b.y0 - pad, y1 = b.y1 + pad, dx = s.x1 - s.x0, dy = s.y1 - s.y0, t0 = 0, t1 = 1;
    var P = [-dx, dx, -dy, dy], Q = [s.x0 - x0, x1 - s.x0, s.y0 - y0, y1 - s.y0];
    for (var i = 0; i < 4; i++) {
      if (P[i] === 0) { if (Q[i] < 0) return false; continue; }
      var t = Q[i] / P[i];
      if (P[i] < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
    }
    return true;
  }
  function segDisc(s, d) {
    var dx = s.x1 - s.x0, dy = s.y1 - s.y0, L = dx * dx + dy * dy, t = L ? ((d.x - s.x0) * dx + (d.y - s.y0) * dy) / L : 0;
    t = Math.max(0, Math.min(1, t));
    var px = s.x0 + dx * t - d.x, py = s.y0 + dy * t - d.y;
    return px * px + py * py < d.r * d.r;
  }
  function segSeg(a, b) {
    function o(ax, ay, bx, by, cx, cy) { var v = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax); return v > 0 ? 1 : (v < 0 ? -1 : 0); }
    return o(a.x0, a.y0, a.x1, a.y1, b.x0, b.y0) * o(a.x0, a.y0, a.x1, a.y1, b.x1, b.y1) < 0 &&
      o(b.x0, b.y0, b.x1, b.y1, a.x0, a.y0) * o(b.x0, b.y0, b.x1, b.y1, a.x1, a.y1) < 0;
  }
  function r1(v) { return Math.round(v * 10) / 10; }
  VL.Callouts = function (cfg) {
    var self = { runs: 0, last: null }, timer = null, tail = null, lastRun = 0, prev = {};
    var THROTTLE = cfg.throttle || 140, TAIL = cfg.tail || 240, wp = null;
    function hideSprite(s) {
      s.layers.set(1);
      if (s.__leader) s.__leader.visible = false;
    }
    function run() {
      if (timer) { clearTimeout(timer); timer = null; }
      lastRun = performance.now();
      var cam = cfg.camera(), sz = cfg.size(), W = sz.w, H = sz.h;
      if (!cam || !(W > 20 && H > 20)) return null;
      if (!wp) wp = new THREE.Vector3();
      var t0 = performance.now();
      cam.updateMatrixWorld();
      var me = cam.matrixWorldInverse.elements, pe = cam.projectionMatrix.elements, near = cam.near || 0.1;
      var k = H / (2 * Math.tan(cam.fov * Math.PI / 360)), wpp = 1 / k, maxR = cfg.discMaxPx || 1e9;
      function proj(x, y, z, out) {
        var vx = me[0] * x + me[4] * y + me[8] * z + me[12], vy = me[1] * x + me[5] * y + me[9] * z + me[13], vz = me[2] * x + me[6] * y + me[10] * z + me[14];
        if (vz > -near) return false;
        var cx = pe[0] * vx + pe[4] * vy + pe[8] * vz + pe[12], cy = pe[1] * vx + pe[5] * vy + pe[9] * vz + pe[13], cw = pe[3] * vx + pe[7] * vy + pe[11] * vz + pe[15];
        if (!(cw > 0)) return false;
        out.x = (cx / cw + 1) / 2 * W;
        out.y = (1 - cy / cw) / 2 * H;
        out.d = -vz;
        return true;
      }
      var grid = new Grid(W, H, 40), ink = (cfg.ink && cfg.ink()) || {}, discs = [], q = {}, qa = {}, qb = {};
      (ink.discs || []).forEach(function (d) {
        if (!proj(d.x, d.y || 0, d.z || 0, q)) return;
        var r = d.rpx != null ? d.rpx : Math.min(maxR, (d.r || 0) * k / q.d);
        if (q.x + r < 0 || q.y + r < 0 || q.x - r > W || q.y - r > H) return;
        var o = { t: 'd', x: q.x, y: q.y, r: Math.max(1, r), id: d.id };
        discs.push(o);
        grid.add(o, o.x - o.r, o.y - o.r, o.x + o.r, o.y + o.r);
      });
      var nseg = 0, segCap = cfg.segCap || 8000;
      (ink.paths || []).forEach(function (pl) {
        if (!pl) return;
        for (var i = 0; i + 1 < pl.length && nseg < segCap; i++) {
          var p0 = pl[i], p1 = pl[i + 1];
          if (!proj(p0.x, p0.y || 0, p0.z || 0, qa) || !proj(p1.x, p1.y || 0, p1.z || 0, qb)) continue;
          if (Math.max(qa.x, qb.x) < 0 || Math.max(qa.y, qb.y) < 0 || Math.min(qa.x, qb.x) > W || Math.min(qa.y, qb.y) > H) continue;
          grid.addSeg({ t: 's', x0: qa.x, y0: qa.y, x1: qb.x, y1: qb.y });
          nseg++;
        }
      });
      var uiRects = (cfg.ui && cfg.ui()) || [];
      uiRects.forEach(function (r) { var o = { t: 'u', x0: r.x0, y0: r.y0, x1: r.x1, y1: r.y1 }; grid.add(o, o.x0, o.y0, o.x1, o.y1); });
      /* the graph centre on the screen (mean of the node discs on the canvas): call-outs go outward from it first */
      var gx = W / 2, gy = H / 2;
      if (discs.length) {
        gx = 0; gy = 0;
        discs.forEach(function (d) { gx += d.x; gy += d.y; });
        gx /= discs.length; gy /= discs.length;
      }
      var col = cfg.leaderColor ? cfg.leaderColor() : '#a2a8af';
      var items = [], shown = 0, hidden = 0, mustHidden = 0, mustOff = 0, forced = 0, selOnCentres = 0, placed = [];
      (cfg.items() || []).forEach(function (it) {
        var s = it.sprite;
        if (!s) return;
        if (it.off) { hideSprite(s); delete prev[it.id]; return; }
        s.getWorldPosition(wp);
        /* a node off the canvas or under an overlay (panel, legend, hint) is not visible: no call-out */
        if (!proj(wp.x, wp.y, wp.z, q) || q.x < 0 || q.y < 0 || q.x > W || q.y > H ||
            uiRects.some(function (u) { return q.x >= u.x0 && q.x <= u.x1 && q.y >= u.y0 && q.y <= u.y1; })) {
          hideSprite(s);
          delete prev[it.id];
          if (it.must) mustOff++;
          return;
        }
        var z = s.screenSize();
        items.push({ it: it, s: s, x: q.x, y: q.y, r: it.rpx != null ? it.rpx : Math.min(maxR, (it.r || 0) * k / q.d), w: z.w, h: z.h });
      });
      items.sort(function (a, b) {
        return ((b.it.sel ? 1 : 0) - (a.it.sel ? 1 : 0)) || ((b.it.must ? 1 : 0) - (a.it.must ? 1 : 0)) || ((b.it.pri || 0) - (a.it.pri || 0));
      });
      /* at most mustMax must call-outs besides the selected one (by priority); the others compete like the rest */
      var mustMax = cfg.mustMax || 8, nMust = 0;
      items.forEach(function (I) {
        I.sel = !!I.it.sel;
        I.must = I.sel || (!!I.it.must && nMust < mustMax);
        if (I.must && !I.sel) nMust++;
      });
      /* 3: never (outside the canvas, over an overlay, a call-out or a leader); 2: over a node centre; 1: over ink (a node
         disc or a link); 0: clear. lastCentres = node centres under the box of the last check */
      var lastCentres = 0;
      function check(box, lead) {
        lastCentres = 0;
        if (box.x0 < 4 || box.y0 < 4 || box.x1 > W - 4 || box.y1 > H - 4) return 3;
        if (grid.sum(box.x0 - 4, box.y0 - 4, box.x1 + 4, box.y1 + 4, function (o) {
          if (o.t === 'u') return rectRect(box, o, 2) ? 1 : 0;
          if (o.t === 'b') return rectRect(box, o, 3) ? 1 : 0;
          if (o.t === 'l') return segRect(o, box, 2) ? 1 : 0;
          if (o.t === 'd' && rectPt(box, o.x, o.y, 2)) lastCentres++;
          return 0;
        }, true)) return 3;
        if (lead && grid.sum(Math.min(lead.x0, lead.x1), Math.min(lead.y0, lead.y1), Math.max(lead.x0, lead.x1), Math.max(lead.y0, lead.y1), function (o) {
          return (o.t === 'b' || o.t === 'u') && segRect(lead, o, 1) ? 1 : 0;
        }, true)) return 3;
        if (lastCentres) return 2;
        if (grid.sum(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1, function (o) {
          if (o.t === 'd') return rectDisc(box, o, 1) ? 1 : 0;
          if (o.t === 's') return segRect(o, box, 1) ? 1 : 0;
          return 0;
        }, true)) return 1;
        return 0;
      }
      function inkUnder(box) {
        return grid.sum(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1, function (o) {
          if (o.t === 'd') return rectDisc(box, o, 1) ? 1 : 0;
          if (o.t === 's') return segRect(o, box, 1) ? 1 : 0;
          return 0;
        });
      }
      /* soft cost of a leader: crossing another node or another leader */
      function leaderCost(lead, I) {
        return grid.sum(Math.min(lead.x0, lead.x1), Math.min(lead.y0, lead.y1), Math.max(lead.x0, lead.x1), Math.max(lead.y0, lead.y1), function (o) {
          if (o.t === 'd') return (Math.abs(o.x - I.x) + Math.abs(o.y - I.y) > 0.5 && segDisc(lead, o)) ? 12 : 0;
          if (o.t === 'l') return segSeg(lead, o) ? 8 : 0;
          return 0;
        });
      }
      function boxAt(cx, cy, I) { return { x0: cx - I.w / 2, y0: cy - I.h / 2, x1: cx + I.w / 2, y1: cy + I.h / 2, cx: cx, cy: cy }; }
      function put(I, c) {
        var s = I.s, it = I.it;
        s.setOffset(c.box.cx - I.x, c.box.cy - I.y);
        s.layers.set(0);
        var Ld = s.__leader;
        if (c.lead) {
          if (!Ld) { Ld = s.__leader = VL.LeaderSprite(col); Ld.__col = col; }
          if (s.parent && Ld.parent !== s.parent) s.parent.add(Ld);
          if (Ld.__col !== col) { Ld.setColor(col); Ld.__col = col; }
          Ld.position.copy(s.position);
          Ld.layers.set(0);
          var dx = c.lead.x1 - c.lead.x0, dy = c.lead.y1 - c.lead.y0;
          Ld.fit(wpp);
          Ld.setGeom(Math.atan2(-dy, dx), Math.sqrt(Math.pow(c.lead.x0 - I.x, 2) + Math.pow(c.lead.y0 - I.y, 2)), Math.sqrt(dx * dx + dy * dy), 1);
          Ld.visible = true;
          grid.addSeg({ t: 'l', x0: c.lead.x0, y0: c.lead.y0, x1: c.lead.x1, y1: c.lead.y1 });
        } else if (Ld) Ld.visible = false;
        var bo = { t: 'b', x0: c.box.x0, y0: c.box.y0, x1: c.box.x1, y1: c.box.y1 };
        grid.add(bo, bo.x0, bo.y0, bo.x1, bo.y1);
        prev[it.id] = c.key;
        placed.push({ id: it.id, must: !!I.must, sel: !!I.sel, box: [r1(bo.x0), r1(bo.y0), r1(bo.x1), r1(bo.y1)],
          anchor: [r1(I.x), r1(I.y)], leader: c.lead ? [r1(c.lead.x0), r1(c.lead.y0), r1(c.lead.x1), r1(c.lead.y1)] : null, forced: !!c.forced,
          text: I.s.textLines ? I.s.textLines() : null, style: I.s.textStyle ? I.s.textStyle() : null });
        shown++;
      }
      items.forEach(function (I) {
        var it = I.it, best = null, bestCost = Infinity, relaxed = null, relaxedCost = Infinity, onCentres = null, onCentresCost = Infinity;
        if (it.fixed) {
          var f = typeof it.fixed === 'function' ? it.fixed(I.w, I.h) : it.fixed, fb = boxAt(I.x + f[0], I.y + f[1], I);
          if (check(fb, null) === 0) put(I, { box: fb, lead: null, key: 'fixed' });
          else { hideSprite(I.s); delete prev[it.id]; if (I.must) mustHidden++; else hidden++; }
          return;
        }
        var ux = I.x - gx, uy = I.y - gy, ul = Math.sqrt(ux * ux + uy * uy);
        if (ul < 4) { ux = 0.6; uy = -0.8; } else { ux /= ul; uy /= ul; }
        var pk = prev[it.id], lens = I.must ? LENS_MUST : LENS;
        for (var di = 0; di < DIRS.length; di++) {
          var ang = DIRS[di] * Math.PI / 180, cs = Math.cos(ang), sn = Math.sin(ang);
          var dx = ux * cs - uy * sn, dy = ux * sn + uy * cs, m = Math.max(Math.abs(dx), Math.abs(dy));
          for (var li = 0; li < lens.length; li++) {
            var key = di + ':' + li, cost = lens[li] + Math.abs(DIRS[di]) * 0.4 + (pk === key ? -40 : 0);
            if (cost >= bestCost) continue;
            var st = I.r + 1.5, ex = I.x + dx * (st + lens[li]), ey = I.y + dy * (st + lens[li]);
            var box = boxAt(ex + dx / m * I.w / 2, ey + dy / m * I.h / 2, I);
            var lead = { x0: I.x + dx * st, y0: I.y + dy * st, x1: ex, y1: ey };
            var v = check(box, lead);
            if (v === 0) {
              cost += leaderCost(lead, I);
              if (cost < bestCost) { bestCost = cost; best = { box: box, lead: lead, key: key }; }
            } else if (I.must && !best) {
              if (v === 1) {
                var rc = cost + 30 * inkUnder(box) + leaderCost(lead, I);
                if (rc < relaxedCost) { relaxedCost = rc; relaxed = { box: box, lead: lead, key: key }; }
              } else if (v === 2 && I.sel && !relaxed) {
                var cc = cost + 400 * lastCentres + 30 * inkUnder(box) + leaderCost(lead, I);
                if (cc < onCentresCost) { onCentresCost = cc; onCentres = { box: box, lead: lead, key: key, centres: lastCentres }; }
              }
            }
          }
        }
        if (best) { put(I, best); return; }
        if (relaxed) { put(I, relaxed); return; }
        if (onCentres) { put(I, onCentres); selOnCentres += onCentres.centres; return; }
        if (I.sel) {
          /* the selected node's call-out and no free position at all: keep it, outward on a short leader */
          var fx = Math.max(4 + I.w / 2, Math.min(W - 4 - I.w / 2, I.x + ux * (I.r + 24) + ux * I.w / 2));
          var fy = Math.max(4 + I.h / 2, Math.min(H - 4 - I.h / 2, I.y + uy * (I.r + 24) + uy * I.h / 2));
          var fbx = boxAt(fx, fy, I);
          put(I, { box: fbx, lead: { x0: I.x + ux * (I.r + 1.5), y0: I.y + uy * (I.r + 1.5), x1: I.x + ux * (I.r + 24), y1: I.y + uy * (I.r + 24) }, key: 'forced', forced: true });
          forced++;
          return;
        }
        hideSprite(I.s);
        delete prev[it.id];
        if (I.must) mustHidden++; else hidden++;
      });
      self.runs++;
      var out = { runs: self.runs, ms: r1(performance.now() - t0), W: Math.round(W), H: Math.round(H), shown: shown, hidden: hidden,
        mustHidden: mustHidden, mustOffscreen: mustOff, forced: forced, selOnCentres: selOnCentres, links: nseg, placed: placed, centre: [r1(gx), r1(gy)],
        nodes: discs.slice(0, 5000).map(function (d) { return [d.id, r1(d.x), r1(d.y)]; }) };
      self.last = out;
      if (cfg.metrics) cfg.metrics[cfg.key || 'callouts'] = out;
      if (cfg.onDone) cfg.onDone(out);
      return out;
    }
    self.run = run;
    self.schedule = function () {
      if (!timer) timer = setTimeout(run, Math.max(0, THROTTLE - (performance.now() - lastRun)));
      if (tail) clearTimeout(tail);
      tail = setTimeout(function () { tail = null; if (!timer) run(); }, TAIL);
    };
    self.forget = function (id) { if (id == null) prev = {}; else delete prev[id]; };
    return self;
  };

  /* ------------------------------------------------------------------ legend and status line */
  /* The legend (bottom left, up to 720 px wide in the paper style) and the status line (bottom right of the canvas, further
     left when the details panel is open) share the bottom edge of the stage. Where they would meet (the details panel
     open, a narrow window, long EN-VI legend rows), the stage gets .legend-lift and the legend moves up above the status
     line (css/site.css, 3D TRACK). The test is horizontal only, so the lift cannot undo itself; once lifted, a margin
     keeps the legend still while the status width changes with the frame rate. Returns true when the lift changed (the
     caller re-places its call-outs, which avoid the legend). */
  VL.fitLegend = function (stage, legend, status) {
    if (!stage) return false;
    var was = stage.classList.contains('legend-lift'), lift = false;
    if (legend && status && !legend.hidden && !legend.classList.contains('hidden') && legend.offsetParent !== null && status.offsetParent !== null) {
      var a = legend.getBoundingClientRect(), b = status.getBoundingClientRect();
      lift = a.width > 1 && b.width > 1 && b.left - a.right < (was ? 24 : 8);
    }
    if (lift === was) return false;
    stage.classList.toggle('legend-lift', lift);
    return true;
  };
})();

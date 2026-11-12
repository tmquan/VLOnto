/* VLOnto - the paper style of the 3D views (the figures of arXiv:2611.11426, Fig. 1 and Fig. 6), shared by
   js/ontology3d.js, js/network3d.js and js/sparql-page.js:
   * VL.paperTheme(el)   colours of the current theme from css/site.css ("paper style" tokens), read from <html> or from
                         an element with data-style="paper"
   * VL.paperLights()    soft light from the upper left of the screen (ambient + a directional light that moves with the
                         camera), so the pastel spheres keep their colour and get the paper's gentle shading
   * VL.paperFog()       depth fade towards the background (VL.fitFog keeps it relative to the camera distance)
   * VL.TraceLines()     the traced path: a navy core over a pale-gold halo (two halo tones), drawn as screen-space
                         lines of constant pixel width with round caps and joins (WebGL lines are 1 px wide)
   Classic script (works from file://); load after vendor/three/three.iife.min.js and js/common.js. */
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
  /* "Vietnamese · English" parts of a call-out: one line when short, else Vietnamese over English (as in Fig. 1) */
  VL.paperLines = function (vi, en, P, opts) {
    opts = opts || {};
    vi = vi ? VL.nfc(vi) : ''; en = en ? VL.nfc(en) : '';
    if (vi && en && vi !== en) {
      if (vi.length + en.length + 3 <= (opts.oneLine || 34)) return [[{ text: vi, color: P.ink }, { text: ' · ' + en, color: P.ink2 }]];
      return [[{ text: vi, color: P.ink }], [{ text: en, color: P.ink2 }]];
    }
    var only = vi || en;
    return [[{ text: only, color: opts.secondary ? P.ink2 : P.ink }]];
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
  function rawColor(hex, c) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    var n = m ? parseInt(m[1], 16) : 0x888888;
    return c.setRGB((n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
  }
  VL.rawColor = rawColor;
  /* opts: depthTest (default true), renderOrder (halo2, halo, core get renderOrder, +1, +2), widths {core, halo, halo2} in
     CSS px, colors {core, halo, halo2} (hex). setPaths([[p0, p1, ...], ...]) takes points with x, y, z. */
  VL.TraceLines = function (opts) {
    opts = opts || {};
    var group = new THREE.Group();
    group.name = 'vlonto-trace';
    var geo = new THREE.BufferGeometry();
    var widths = { halo2: 11, halo: 7.5, core: 3.2 }, colors = { halo2: '#f4dcac', halo: '#ecc890', core: '#2c3a47' };
    var size = new THREE.Vector2(), nseg = 0, layers = {};
    ['halo2', 'halo', 'core'].forEach(function (k, i) {
      var mat = new THREE.ShaderMaterial({
        uniforms: { uRes: { value: new THREE.Vector2(1, 1) }, uWidth: { value: 1 }, uColor: { value: new THREE.Color() }, uOpacity: { value: 1 } },
        vertexShader: TR_VS, fragmentShader: TR_FS, transparent: true, depthWrite: false, depthTest: opts.depthTest !== false,
        side: THREE.DoubleSide
      });
      var mesh = new THREE.Mesh(geo, mat);
      mesh.frustumCulled = false;
      mesh.renderOrder = (opts.renderOrder || 8) + i;
      mesh.onBeforeRender = function (renderer) {
        renderer.getDrawingBufferSize(size);
        mat.uniforms.uRes.value.copy(size);
        mat.uniforms.uWidth.value = widths[k] * renderer.getPixelRatio();
      };
      layers[k] = { mesh: mesh, mat: mat };
      group.add(mesh);
    });
    function setStyle(st) {
      st = st || {};
      if (st.widths) Object.keys(st.widths).forEach(function (k) { widths[k] = st.widths[k]; });
      if (st.colors) Object.keys(st.colors).forEach(function (k) { colors[k] = st.colors[k]; });
      Object.keys(layers).forEach(function (k) {
        rawColor(colors[k], layers[k].mat.uniforms.uColor.value);
        layers[k].mesh.visible = widths[k] > 0 && nseg > 0;
      });
      if (st.opacity != null) Object.keys(layers).forEach(function (k) { layers[k].mat.uniforms.uOpacity.value = st.opacity; });
    }
    function setPaths(paths) {
      var n = 0;
      (paths || []).forEach(function (pl) { if (pl && pl.length > 1) n += pl.length - 1; });
      var pos = new Float32Array(n * 12), oth = new Float32Array(n * 12), side = new Float32Array(n * 4), end = new Float32Array(n * 4);
      var idx = n * 4 > 65535 ? new Uint32Array(n * 6) : new Uint16Array(n * 6), s = 0;
      (paths || []).forEach(function (pl) {
        if (!pl || pl.length < 2) return;
        for (var i = 0; i + 1 < pl.length; i++, s++) {
          var a = pl[i], b = pl[i + 1];
          for (var k = 0; k < 4; k++) {
            var own = k < 2 ? a : b, other = k < 2 ? b : a, v = s * 4 + k;
            pos[3 * v] = own.x; pos[3 * v + 1] = own.y || 0; pos[3 * v + 2] = own.z || 0;
            oth[3 * v] = other.x; oth[3 * v + 1] = other.y || 0; oth[3 * v + 2] = other.z || 0;
            side[v] = k % 2 === 0 ? 1 : -1;
            end[v] = k < 2 ? 0 : 1;
          }
          var o = s * 4;
          idx[s * 6] = o; idx[s * 6 + 1] = o + 1; idx[s * 6 + 2] = o + 2;
          idx[s * 6 + 3] = o; idx[s * 6 + 4] = o + 2; idx[s * 6 + 5] = o + 3;
        }
      });
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setAttribute('aOther', new THREE.BufferAttribute(oth, 3));
      geo.setAttribute('aSide', new THREE.BufferAttribute(side, 1));
      geo.setAttribute('aEnd', new THREE.BufferAttribute(end, 1));
      geo.setIndex(new THREE.BufferAttribute(idx, 1));
      nseg = n;
      setStyle({});
      return n;
    }
    function dispose() {
      geo.dispose();
      Object.keys(layers).forEach(function (k) { layers[k].mat.dispose(); });
    }
    setStyle({});
    return { object: group, setPaths: setPaths, setStyle: setStyle, count: function () { return nseg; }, dispose: dispose };
  };
  /* trace style of the theme: navy core (light core on the dark ground) over the two gold tones; w scales the widths */
  VL.traceStyle = function (P, w) {
    w = w || 1;
    return { colors: { core: P.core, halo: P.halo, halo2: P.halo2 }, widths: { core: 3.2 * w, halo: 7.5 * w, halo2: 11 * w }, opacity: P.dark ? 0.96 : 1 };
  };
  /* points of a link drawn by 3d-force-graph (curved links keep their curve in link.__curve) */
  VL.linkPoints = function (l, n) {
    if (l.__curve && l.__curve.getPoints) return l.__curve.getPoints(n || 16);
    var s = l.source, t = l.target;
    if (!s || !t || typeof s !== 'object' || typeof t !== 'object' || !isFinite(s.x) || !isFinite(t.x)) return null;
    return [{ x: s.x, y: s.y || 0, z: s.z || 0 }, { x: t.x, y: t.y || 0, z: t.z || 0 }];
  };
})();

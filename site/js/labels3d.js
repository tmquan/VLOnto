/* VLOnto - text labels for the 3D views: THREE.Sprite with a canvas texture drawn here, sizeAttenuation off and an exact
   on-screen size in CSS pixels. (three-spritetext adds its padding to the sprite scale in absolute world units, which
   breaks constant-pixel labels, so it is not used for labels.)
   Paper style (arXiv:2611.11426, Fig. 1): call-outs in Libertinus Sans, white box with a 1 px light-grey border and
   square-ish corners, "Vietnamese · English" in two greys (one line, or Vietnamese over English), and a thin grey leader
   line from the box to its node. The 3D views place their call-outs with VL.Callouts (js/paper3d.js): the sprite sits
   at its node, setOffset() moves the box in screen pixels, and the leader is a separate VL.LeaderSprite. (The older
   mode, a leader drawn into the texture with side 'above' or 'below', is kept for other callers.)
   Load after vendor/three/three.iife.min.js and js/common.js. */
(function () {
  'use strict';
  var VL = window.VL;
  var FONT = '"Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif';
  var F = 40;                    // canvas font size (oversampled; the text shows at about px / 1.68 CSS px)
  function rr(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function fontOf(o, p) { return (p.italic ? 'italic ' : '') + (p.weight || o.weight || '600') + ' ' + F + 'px ' + (o.font || FONT); }
  /* lines of parts [{text, color, weight, italic}]; plain labels are one line of one part */
  function linesOf(s) {
    var o = s.__opts;
    if (o.lines && o.lines.length) {
      return o.lines.map(function (ln) {
        return ln.map(function (p) { return { text: VL.nfc(p.text), color: p.color || o.color || '#ffffff', weight: p.weight, italic: p.italic }; });
      });
    }
    return [[{ text: s.__text, color: o.color || '#ffffff' }]];
  }
  function draw(s, side) {
    var o = s.__opts, lines = linesOf(s);
    var cv = document.createElement('canvas'), ctx = cv.getContext('2d');
    var S = F * 1.68 / s.__drawPx;                       // canvas px per CSS px
    var padX = Math.round(F * (o.padX != null ? o.padX : 0.45)), padY = Math.round(F * 0.2);
    var lh = Math.round(F * 1.28), lh2 = Math.round(F * 1.14);
    var tw = 0;
    lines.forEach(function (ln) {
      var w = 0;
      ln.forEach(function (p) { ctx.font = fontOf(o, p); w += ctx.measureText(p.text).width; });
      tw = Math.max(tw, w);
    });
    var boxW = Math.max(8, Math.ceil(tw) + 2 * padX), boxH = lh + (lines.length - 1) * lh2 + 2 * padY;
    var lead = o.leader ? Math.round(o.leader * S) : 0;
    cv.width = boxW + 2;
    cv.height = boxH + lead + 2;
    ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    var top = side === 'below' ? lead + 1 : 1;
    if (lead) {
      ctx.strokeStyle = o.leaderColor || o.border || '#a2a8af';
      ctx.lineWidth = Math.max(1, S);
      ctx.beginPath();
      if (side === 'below') { ctx.moveTo(cv.width / 2, 0); ctx.lineTo(cv.width / 2, top + 1); }
      else { ctx.moveTo(cv.width / 2, top + boxH - 1); ctx.lineTo(cv.width / 2, cv.height); }
      ctx.stroke();
    }
    var r = o.radius != null ? o.radius * S : Math.round(F * 0.3);
    if (o.bg) {
      ctx.fillStyle = o.bg;
      rr(ctx, 1, top, boxW, boxH, r);
      ctx.fill();
    }
    if (o.border) {
      var bw = o.borderPx ? o.borderPx * S : 3;
      ctx.strokeStyle = o.border;
      ctx.lineWidth = bw;
      rr(ctx, 1 + bw / 2, top + bw / 2, boxW - bw, boxH - bw, r - bw / 2);
      ctx.stroke();
    }
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    lines.forEach(function (ln, i) {
      var y = top + padY + (i === 0 ? lh / 2 : lh + (i - 1) * lh2 + lh2 / 2) + F * 0.05, x = 1 + padX;
      ln.forEach(function (p) {
        ctx.font = fontOf(o, p);
        ctx.fillStyle = p.color;
        ctx.fillText(p.text, x, y);
        x += ctx.measureText(p.text).width;
      });
    });
    var tex = new THREE.CanvasTexture(cv);
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    return { tex: tex, aspect: cv.width / cv.height, hCss: cv.height / S, leadCss: lead / S, boxCss: boxH / S };
  }
  function clearCache(s) {
    Object.keys(s.__cache).forEach(function (k) { s.__cache[k].tex.dispose(); });
    s.__cache = {};
  }
  function use(s, side) {
    var c = s.__cache[side] || (s.__cache[side] = draw(s, side));
    s.__side = side;
    s.__aspect = c.aspect;
    s.__hCss = c.hCss;
    s.__leadCss = c.leadCss;
    if (s.material.map !== c.tex) { s.material.map = c.tex; s.material.needsUpdate = true; }
    if (s.__opts.leader) s.center.set(0.5, side === 'below' ? 1 : 0);
  }
  /* opts: px (height in CSS px of a one-line box), weight, color, bg, border, borderPx, radius (CSS px), font, padX,
     lines (parts as above, instead of text and color), leader (CSS px) + leaderColor + side ('above' | 'below'),
     cx, cy (sprite centre when there is no leader) */
  VL.TextSprite = function (text, opts) {
    opts = opts || {};
    var mat = new THREE.SpriteMaterial({ transparent: true, depthTest: false, depthWrite: false, sizeAttenuation: false, fog: false });
    var s = new THREE.Sprite(mat);
    s.__opts = opts;
    s.__text = VL.nfc(text);
    s.__px = s.__drawPx = opts.px || 22;
    s.__wpp = 0.001;
    s.__cache = {};
    s.renderOrder = 30;
    s.center.set(opts.cx != null ? opts.cx : 0.5, opts.cy != null ? opts.cy : -0.25);
    use(s, opts.side === 'below' ? 'below' : 'above');
    function redraw() { var side = s.__side; clearCache(s); use(s, side); s.fit(s.__wpp); }
    /* box centre at (ox, oy) CSS px from the anchor (screen axes, y down), for call-outs placed by VL.Callouts (no leader
       in the texture: the leader is a VL.LeaderSprite). sizeAttenuation is off, so the offset stays in pixels at any
       distance while the anchor follows its node. */
    function applyOffset() {
      if (!s.__off) return;
      var z = s.screenSize();
      s.center.set(0.5 - s.__off[0] / Math.max(1, z.w), 0.5 + s.__off[1] / Math.max(1, z.h));
    }
    s.setOffset = function (ox, oy) { s.__off = [ox, oy]; applyOffset(); };
    s.setText = function (t) { t = VL.nfc(t); if (t !== s.__text) { s.__text = t; redraw(); } };
    s.setLines = function (lines) { s.__opts.lines = lines; redraw(); };
    s.setPx = function (px) { s.__px = px; s.fit(s.__wpp); };
    /* box above or below the anchor, the leader joining it to the node (no redraw when that texture exists) */
    s.setSide = function (side) { if (side !== s.__side) { use(s, side); s.fit(s.__wpp); } };
    /* restyle in place (theme switch): merge options and redraw the canvas texture */
    s.setStyle = function (o) {
      var changed = false;
      Object.keys(o || {}).forEach(function (k) { if (s.__opts[k] !== o[k]) { s.__opts[k] = o[k]; changed = true; } });
      if (changed) redraw();
    };
    s.fit = function (wpp) {
      if (wpp) s.__wpp = wpp;
      var h = s.__hCss * (s.__px / s.__drawPx) * s.__wpp;
      s.scale.set(h * s.__aspect, h, 1);
      applyOffset();
      if (s.__leader) s.__leader.fit(s.__wpp);
    };
    /* on-screen size in CSS px: whole sprite, and the leader part of it */
    s.screenSize = function () { var k = s.__px / s.__drawPx; return { w: s.__hCss * s.__aspect * k, h: s.__hCss * k, lead: s.__leadCss * k }; };
    s.dispose = function () {
      if (s.__leader) {
        if (s.__leader.parent) s.__leader.parent.remove(s.__leader);
        s.__leader.dispose();
        s.__leader = null;
      }
      clearCache(s);
      s.material.dispose();
    };
    return s;
  };
  /* the thin leader line of a call-out placed by VL.Callouts: a solid sprite at the call-out's anchor, rotated in the
     screen plane, from the edge of the node (start px) to the box (start + len px); never picked by the raycaster */
  VL.LeaderSprite = function (color) {
    var mat = new THREE.SpriteMaterial({ color: new THREE.Color(color || '#a2a8af'), transparent: true, depthTest: false, depthWrite: false,
      sizeAttenuation: false, fog: false });
    var l = new THREE.Sprite(mat);
    l.renderOrder = 29;
    l.raycast = function () {};
    l.center.set(0, 0.5);
    l.__wpp = 0.001;
    l.__geom = null;
    l.setColor = function (hex) { mat.color.set(hex); };
    /* angle in radians in the screen plane (counter-clockwise, x to the right), lengths in CSS px */
    l.setGeom = function (angle, start, len, widthPx) {
      l.__geom = [angle, start, Math.max(1, len), widthPx || 1];
      mat.rotation = angle;
      l.center.set(-start / l.__geom[2], 0.5);
      l.scale.set(l.__geom[2] * l.__wpp, l.__geom[3] * l.__wpp, 1);
    };
    l.fit = function (wpp) {
      if (wpp) l.__wpp = wpp;
      if (l.__geom) l.scale.set(l.__geom[2] * l.__wpp, l.__geom[3] * l.__wpp, 1);
    };
    l.dispose = function () { mat.dispose(); };
    return l;
  };
  /* world size of one CSS pixel for sizeAttenuation=false sprites (an orthographic camera: world units, not per depth) */
  VL.spriteWpp = function (camera, heightPx) {
    if (camera.isOrthographicCamera) return (camera.top - camera.bottom) / camera.zoom / Math.max(1, heightPx);
    return 2 * Math.tan(camera.fov * Math.PI / 360) / Math.max(1, heightPx);
  };
})();

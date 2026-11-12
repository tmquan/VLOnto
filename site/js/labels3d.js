/* VLOnto - text labels for the 3D views: THREE.Sprite with a canvas texture drawn here (rounded background, padding),
   sizeAttenuation off and an exact on-screen size in CSS pixels. (three-spritetext adds its padding to the sprite scale
   in absolute world units, which breaks constant-pixel labels, so it is not used for labels.)
   Load after vendor/three/three.iife.min.js and js/common.js. */
(function () {
  'use strict';
  var VL = window.VL;
  var FONT = '"Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif';
  var F = 40;                    // canvas font size (oversampled; displayed at about px / 1.68)
  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function draw(s) {
    var o = s.__opts;
    var cv = s.__canvas || (s.__canvas = document.createElement('canvas'));
    var ctx = cv.getContext('2d');
    var font = (o.weight || '600') + ' ' + F + 'px ' + FONT;
    ctx.font = font;
    var tw = Math.ceil(ctx.measureText(s.__text).width);
    var padX = Math.round(F * 0.45), padY = Math.round(F * 0.2), lh = Math.round(F * 1.28);
    cv.width = Math.max(8, tw + 2 * padX);
    cv.height = lh + 2 * padY;
    ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (o.bg) {
      ctx.fillStyle = o.bg;
      rr(ctx, 1, 1, cv.width - 2, cv.height - 2, Math.round(F * 0.3));
      ctx.fill();
    }
    if (o.border) {
      ctx.strokeStyle = o.border;
      ctx.lineWidth = 3;
      rr(ctx, 1.5, 1.5, cv.width - 3, cv.height - 3, Math.round(F * 0.3));
      ctx.stroke();
    }
    ctx.font = font;
    ctx.fillStyle = o.color || '#ffffff';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.fillText(s.__text, padX, cv.height / 2 + F * 0.05);
    if (s.material.map) s.material.map.dispose();
    var tex = new THREE.CanvasTexture(cv);
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    s.material.map = tex;
    s.material.needsUpdate = true;
    s.__aspect = cv.width / cv.height;
  }
  /* opts: px (box height in CSS px), weight, color, bg, border, cx, cy (sprite center) */
  VL.TextSprite = function (text, opts) {
    opts = opts || {};
    var mat = new THREE.SpriteMaterial({ transparent: true, depthTest: false, depthWrite: false, sizeAttenuation: false });
    var s = new THREE.Sprite(mat);
    s.__opts = opts;
    s.__text = VL.nfc(text);
    s.__px = opts.px || 22;
    s.__wpp = 0.001;
    s.renderOrder = 30;
    s.center.set(opts.cx != null ? opts.cx : 0.5, opts.cy != null ? opts.cy : -0.25);
    draw(s);
    s.setText = function (t) { t = VL.nfc(t); if (t !== s.__text) { s.__text = t; draw(s); s.fit(s.__wpp); } };
    s.setPx = function (px) { s.__px = px; s.fit(s.__wpp); };
    /* restyle in place (theme switch): merge colour options and redraw the canvas texture */
    s.setStyle = function (o) {
      var changed = false;
      Object.keys(o || {}).forEach(function (k) { if (s.__opts[k] !== o[k]) { s.__opts[k] = o[k]; changed = true; } });
      if (changed) { draw(s); s.fit(s.__wpp); }
    };
    s.fit = function (wpp) {
      if (wpp) s.__wpp = wpp;
      var h = s.__px * s.__wpp;
      s.scale.set(h * s.__aspect, h, 1);
    };
    s.dispose = function () { if (s.material.map) s.material.map.dispose(); s.material.dispose(); };
    return s;
  };
  /* world size of one CSS pixel for sizeAttenuation=false sprites */
  VL.spriteWpp = function (camera, heightPx) { return 2 * Math.tan(camera.fov * Math.PI / 360) / Math.max(1, heightPx); };
})();

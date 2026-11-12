#!/usr/bin/env python3
"""contrast_check.py - WCAG 2.x AA contrast of the rendered VLOnto site, per page x theme x viewport (http).

    $W/python scripts/site/contrast_check.py --root site --out $V/build/site_contrast [--themes light,dark]

Text: every visible DOM text element (direct text nodes, input values, placeholders, the selected option of a select)
that is topmost at its position. The page is scrolled through in viewport chunks; for each chunk the text colour is
read from the computed style (alpha times the opacity of every ancestor), then all text is made transparent with a
stylesheet (no layout change) and the viewport is captured, so the background under each text box is the rendered
background (gradients, images, WebGL canvases and translucent overlays included). The contrast of the text colour
composited over each sampled background pixel is computed with the WCAG relative-luminance formula; an element
passes when its 10th-percentile ratio is at least 4.5:1, or 3:1 for large text (>= 24 px, or >= 18.66 px and bold).
Disabled controls are exempt (WCAG 1.4.3), and canvas/WebGL text (3D labels, chart axes) is not DOM text: those are
reviewed on the screenshots.
UI components (WCAG 1.4.11, 3:1): the boundary of text fields and selects (border or fill against the surrounding
background), the glyph of icon-only buttons against the button, and the keyboard focus ring (a sample of focusable
elements per page: theme toggle, first header link or menu button, first link, button, field and chip/segment; each is
focused with focusVisible and captured while focused): the ring must be drawn (>= 60% of its length in the outline
colour, so not clipped or covered) and its colour must reach 3:1 against the pixels adjacent to it (outside, and inside
when there is a gap of >= 2 px); a two-tone ring is measured against its own halo.
Writes contrast.json and contrast_report.md; exit 1 when any check fails.
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENES = ("index.html", "network-3d.html")   # WebGL pages (index.html is the 3D ontology playground)
PAGES = ["index.html", "about.html", "network-3d.html", "sparql.html", "dashboard.html", "ontology.html",
         "playbook.html", "downloads.html", "ontology/vlonto.html"]
TOL = 0.05   # rounding / anti-aliasing tolerance on the ratio

HIDE_ON = """() => { if (document.getElementById('cc-hide')) return; const s = document.createElement('style'); s.id = 'cc-hide';
  s.textContent = '*, *::before, *::after { color: transparent !important; -webkit-text-fill-color: transparent !important; ' +
    'text-shadow: none !important; text-decoration-color: transparent !important; caret-color: transparent !important; } ' +
    '::placeholder { color: transparent !important; } ::selection { background: transparent !important; }';
  document.head.appendChild(s); }"""
HIDE_OFF = "() => { const s = document.getElementById('cc-hide'); if (s) s.remove(); }"

INDEX = """() => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TITLE', 'OPTION', 'OPTGROUP', 'SELECT', 'TEXTAREA']);
  const els = new Set(), w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    if (!n.nodeValue.trim()) continue;
    const el = n.parentElement;
    if (!el || SKIP.has(el.tagName) || el.closest('svg')) continue;
    els.add(el);
  }
  document.querySelectorAll('input, select, textarea').forEach(e => els.add(e));
  window.__ccEls = Array.from(els);
  return window.__ccEls.length;
}"""

COLLECT = """(arg) => {
  const done = new Set(arg.done), top = arg.top, vw = innerWidth, vh = innerHeight, out = [];
  const parse = s => { const m = /rgba?\\(([^)]+)\\)/.exec(s || ''); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const opac = el => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  const desc = el => { const d = []; for (let e = el; e && d.length < 3 && e !== document.body; e = e.parentElement)
    d.unshift(e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''));
    return d.join(' > '); };
  function clip(el, r) {
    let x0 = r.left, y0 = r.top, x1 = r.right, y1 = r.bottom;
    for (let e = el.parentElement; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') { const b = e.getBoundingClientRect();
        x0 = Math.max(x0, b.left); y0 = Math.max(y0, b.top); x1 = Math.min(x1, b.right); y1 = Math.min(y1, b.bottom); }
    }
    x0 = Math.max(x0, 0); y0 = Math.max(y0, 0); x1 = Math.min(x1, vw); y1 = Math.min(y1, vh);
    return (x1 - x0 >= 2 && y1 - y0 >= 4) ? [x0, y0, x1 - x0, y1 - y0] : null;
  }
  function onTop(el, r) {
    const t = document.elementFromPoint(r[0] + r[2] / 2, r[1] + r[3] / 2);
    return !!t && (t === el || el.contains(t) || t.contains(el) || (t.control && t.control === el));
  }
  window.__ccEls.forEach((el, i) => {
    if (done.has(i) || !el.isConnected) return;
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible' || cs.display === 'none') return;
    const field = /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName);
    if (field && /^(checkbox|radio|range|hidden|color|file|submit|button|image)$/.test(el.type)) return;
    const box = el.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) return;
    /* evaluate an element in a chunk that shows all of it (below the sticky header), unless it is taller than that */
    if (box.height < vh - top - 8 && (box.top < top - 1 || box.bottom > vh + 1)) return;
    let rects = [];
    if (field) {
      const pl = parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth), pr = parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth);
      const pt = parseFloat(cs.paddingTop) + parseFloat(cs.borderTopWidth), pb = parseFloat(cs.paddingBottom) + parseFloat(cs.borderBottomWidth);
      const c = clip(el, { left: box.left + pl, top: box.top + pt, right: box.right - pr, bottom: Math.min(box.bottom - pb, box.top + pt + 40) });
      if (c) rects.push(c);
    } else {
      for (const n of el.childNodes) {
        if (n.nodeType !== 3 || !n.nodeValue.trim()) continue;
        const rg = document.createRange(); rg.selectNodeContents(n);
        for (const q of rg.getClientRects()) { if (q.width < 2 || q.height < 4) continue; const c = clip(el, q); if (c) rects.push(c); }
      }
    }
    rects = rects.filter(r => onTop(el, r));
    if (!rects.length) return;
    let color = cs.color, kind = 'text', text = '';
    if (field) {
      const val = el.tagName === 'SELECT' ? (el.selectedOptions[0] || {}).text || '' : el.value;
      if (!val && el.placeholder) { color = getComputedStyle(el, '::placeholder').color; kind = 'placeholder'; text = el.placeholder; }
      else if (!val) return;
      else { kind = 'field'; text = val; }
    } else text = el.textContent;
    const size = parseFloat(cs.fontSize), weight = parseInt(cs.fontWeight, 10) || 400;
    out.push({ i: i, rects: rects, color: parse(color), opacity: opac(el), size: size, weight: weight,
      large: size >= 24 || (size >= 18.66 && weight >= 700), disabled: !!el.closest(':disabled, [aria-disabled="true"]'),
      kind: kind, sel: desc(el), text: String(text).trim().replace(/\\s+/g, ' ').slice(0, 80) });
  });
  return out;
}"""

# per item: contrast of the composited text colour over every sampled background pixel -> min, p10, median
SAMPLE = """async (arg) => {
  const img = new Image(); img.src = arg.src; await img.decode();
  const cv = document.createElement('canvas'); cv.width = img.naturalWidth; cv.height = img.naturalHeight;
  const cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(img, 0, 0);
  const W = cv.width, H = cv.height, D = cx.getImageData(0, 0, W, H).data, k = arg.dpr;
  const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const L = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  const out = [];
  for (const it of arg.items) {
    if (!it.color) continue;
    const fa = it.color[3] * it.opacity, rs = [], bgs = [];
    for (const [x, y, w, h] of it.rects) {
      const x0 = Math.max(0, Math.floor(x * k)), y0 = Math.max(0, Math.floor(y * k)), x1 = Math.min(W, Math.ceil((x + w) * k)), y1 = Math.min(H, Math.ceil((y + h) * k));
      const sx = Math.max(1, Math.floor((x1 - x0) / 24)), sy = Math.max(1, Math.floor((y1 - y0) / 6));
      for (let yy = y0; yy < y1; yy += sy) for (let xx = x0; xx < x1; xx += sx) {
        const p = (yy * W + xx) * 4, br = D[p], bg = D[p + 1], bb = D[p + 2];
        const fr = fa * it.color[0] + (1 - fa) * br, fg = fa * it.color[1] + (1 - fa) * bg, fb = fa * it.color[2] + (1 - fa) * bb;
        rs.push(ratio(L(fr, fg, fb), L(br, bg, bb))); bgs.push([br, bg, bb]);
      }
    }
    if (!rs.length) continue;
    const ix = rs.map((r, i) => [r, i]).sort((a, b) => a[0] - b[0]);
    const q = f => ix[Math.min(ix.length - 1, Math.floor(f * ix.length))];
    out.push({ i: it.i, min: ix[0][0], p10: q(0.1)[0], median: q(0.5)[0], bg_p10: bgs[q(0.1)[1]], n: rs.length });
  }
  return out;
}"""

# UI components: field boundaries and icon-only buttons in the current viewport (geometry + colours; pixels sampled later)
UI_COLLECT = """() => {
  const vw = innerWidth, vh = innerHeight, out = [];
  const parse = s => { const m = /rgba?\\(([^)]+)\\)/.exec(s || ''); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const vis = (el, b) => { const cs = getComputedStyle(el); if (cs.visibility !== 'visible' || cs.display === 'none') return false;
    if (b.width < 4 || b.height < 4 || b.right < 0 || b.bottom < 0 || b.left > vw || b.top > vh) return false;
    const t = document.elementFromPoint(Math.min(vw - 1, Math.max(0, b.left + b.width / 2)), Math.min(vh - 1, Math.max(0, b.top + b.height / 2)));
    return !!t && (t === el || el.contains(t) || t.contains(el)); };
  const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '');
  document.querySelectorAll('input, select, textarea').forEach(el => {
    if (/^(checkbox|radio|range|hidden|color|file|submit|button|image)$/.test(el.type) || el.disabled) return;
    const b = el.getBoundingClientRect(); if (!vis(el, b)) return; const cs = getComputedStyle(el);
    out.push({ kind: 'field', sel: desc(el), box: [b.left, b.top, b.width, b.height], border: parse(cs.borderTopColor), bw: parseFloat(cs.borderTopWidth) || 0 });
  });
  document.querySelectorAll('button, a.btn, [role=button]').forEach(el => {
    if (el.disabled) return;
    const txt = Array.from(el.childNodes).filter(n => n.nodeType === 3 || (n.nodeType === 1 && !n.classList.contains('sr-only') && n.tagName !== 'svg' && n.tagName !== 'SVG'))
      .map(n => n.textContent).join('').trim();
    if (txt || !el.querySelector('svg')) return;
    const b = el.getBoundingClientRect(); if (!vis(el, b)) return;
    out.push({ kind: 'icon', sel: desc(el), box: [b.left, b.top, b.width, b.height], color: parse(getComputedStyle(el).color) });
  });
  return out;
}"""

UI_SAMPLE = """async (arg) => {
  const img = new Image(); img.src = arg.src; await img.decode();
  const cv = document.createElement('canvas'); cv.width = img.naturalWidth; cv.height = img.naturalHeight;
  const cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(img, 0, 0);
  const W = cv.width, H = cv.height, D = cx.getImageData(0, 0, W, H).data, k = arg.dpr;
  const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const L = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  function px(x, y) { x = Math.round(x * k); y = Math.round(y * k); if (x < 0 || y < 0 || x >= W || y >= H) return null; const p = (y * W + x) * 4; return [D[p], D[p + 1], D[p + 2]]; }
  function ring(b, d0, d1) {   /* pixels on a band d0..d1 css px outside the box */
    const out = [], [x, y, w, h] = b;
    for (let d = d0; d <= d1; d += 1) {
      for (let t = 0; t <= 1; t += 1 / 24) {
        [[x + t * w, y - d], [x + t * w, y + h + d], [x - d, y + t * h], [x + w + d, y + t * h]].forEach(([a, c]) => { const v = px(a, c); if (v) out.push(v); });
      }
    }
    return out;
  }
  function inner(b, inset) { const out = [], [x, y, w, h] = b;
    for (let i = 1; i < 8; i++) for (let j = 1; j < 4; j++) { const v = px(x + inset + (w - 2 * inset) * i / 8, y + inset + (h - 2 * inset) * j / 4); if (v) out.push(v); } return out; }
  const med = arr => { if (!arr.length) return null; const s = arr.slice().sort((a, b) => L(a) - L(b)); return s[Math.floor(s.length / 2)]; };
  const pct = (vals, f) => { const s = vals.slice().sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(f * s.length))] : null; };
  return arg.items.map(it => {
    if (it.kind === 'field') {
      const outside = ring(it.box, 2, 4), inside = inner(it.box, Math.max(2, it.bw + 1)), om = med(outside), im = med(inside);
      if (!om || !im) return Object.assign(it, { skip: true });
      const borderR = it.border && it.bw >= 0.5 && it.border[3] > 0.05 ? pct(outside.map(o => ratio(it.border, o)), 0.1) : 0;
      const fillR = ratio(im, om);
      return Object.assign(it, { outside: om, fill: im, border_ratio: borderR, fill_ratio: fillR, ratio: Math.max(borderR, fillR) });
    }
    if (it.kind === 'icon') {
      const bgv = inner(it.box, 3), bm = med(bgv);
      if (!bm || !it.color) return Object.assign(it, { skip: true });
      return Object.assign(it, { bg: bm, ratio: pct(bgv.map(o => ratio(it.color, o)), 0.1) });
    }
    if (it.kind === 'focus') {
      const off = it.offset, w = it.width, band = ring(it.box, off + 1, off + Math.max(1, w));
      if (!band.length || !it.color) return Object.assign(it, { skip: true });
      return Object.assign(it, { ratio: pct(band.map(o => ratio(it.color, o)), 0.1), bg: med(band) });
    }
    return it;
  });
}"""

# focusable sample: the theme toggle, the first header link or the menu button, first link / button / field in the page
FOCUS_PICK = """() => {
  const pick = [], seen = new Set(), vw = innerWidth, vh = innerHeight;
  const ok = el => { if (!el || seen.has(el)) return false; const b = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return cs.visibility === 'visible' && cs.display !== 'none' && b.width > 2 && b.height > 2 && b.top >= 0 && b.bottom <= vh && b.left >= 0 && b.right <= vw; };
  const add = el => { if (ok(el)) { seen.add(el); pick.push(el); } };
  add(document.querySelector('.vl-theme-btn'));
  add(Array.from(document.querySelectorAll('.vl-nav a')).find(ok) || document.querySelector('.vl-menu-btn'));
  const main = document.querySelector('main, #app, body');
  ['a[href]', 'button', 'input:not([type=hidden]), select, textarea', 'a.btn, .chip, .seg button'].forEach(s => add(Array.from(main.querySelectorAll(s)).find(e => ok(e) && !pick.includes(e))));
  window.__ccFocus = pick;
  return pick.length;
}"""
FOCUS_ON = """(i) => { const el = window.__ccFocus[i]; if (!el) return null;
  el.focus({ focusVisible: true, preventScroll: true }); const cs = getComputedStyle(el), b = el.getBoundingClientRect();
  const parse = s => { const m = /rgba?\\(([^)]+)\\)/.exec(s || ''); if (!m) return null; const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const sh = /^(rgba?\\([^)]+\\))\\s+0px\\s+0px\\s+0px\\s+([\\d.]+)px/.exec(cs.boxShadow || '');
  return { kind: 'focus', sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/)[0] : ''),
    focused: document.activeElement === el, visible: el.matches(':focus-visible'), style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) || 0,
    offset: parseFloat(cs.outlineOffset) || 0, color: parse(cs.outlineColor), shadow: cs.boxShadow,
    halo: sh ? parse(sh[1]) : null, halo_spread: sh ? parseFloat(sh[2]) : 0, box: [b.left, b.top, b.width, b.height] }; }"""
FOCUS_OFF = "() => { const a = document.activeElement; if (a && a !== document.body) a.blur(); }"

# The focus ring as rendered while the element is focused: the ring itself (share of its pixels drawn in the outline
# colour; a clipped or covered ring fails), and the contrast of the outline colour against the pixels adjacent to it,
# just outside the ring and, when the ring stands off the element by >= 2 px (or is drawn >= 2 px inside it), just inside
# it. A two-tone ring (outline inside a contrasting box-shadow halo, WCAG technique C40) is measured against its halo.
# Samples lie on the straight middle part of each edge (rounded corners excluded).
FOCUS_SAMPLE = """async (arg) => {
  const it = arg.item;
  const img = new Image(); img.src = arg.src; await img.decode();
  const cv = document.createElement('canvas'); cv.width = img.naturalWidth; cv.height = img.naturalHeight;
  const cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(img, 0, 0);
  const W = cv.width, H = cv.height, D = cx.getImageData(0, 0, W, H).data, k = arg.dpr;
  const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const L = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  function px(x, y) { x = Math.round(x * k); y = Math.round(y * k); if (x < 0 || y < 0 || x >= W || y >= H) return null; const p = (y * W + x) * 4; return [D[p], D[p + 1], D[p + 2]]; }
  function band(d) {   /* pixels at signed distance d from the border box (d < 0: inside) */
    const out = [], [x, y, w, h] = it.box;
    for (let t = 0.3; t <= 0.7001; t += 0.025) {
      [[x + t * w, y - d], [x + t * w, y + h + d], [x - d, y + t * h], [x + w + d, y + t * h]].forEach(([a, c]) => { const v = px(a, c); if (v) out.push(v); });
    }
    return out;
  }
  const pct = (vals, f) => { const s = vals.slice().sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(f * s.length))] : null; };
  const med = arr => { if (!arr.length) return null; const s = arr.slice().sort((a, b) => L(a) - L(b)); return s[Math.floor(s.length / 2)]; };
  const c = it.color, off = it.offset, w = it.width;
  const ring = [];
  if (w >= 2) { for (let d = off + 1; d <= off + w - 1; d++) ring.push(...band(d)); } else ring.push(...band(off + w / 2));
  const close = v => Math.max(Math.abs(v[0] - c[0]), Math.abs(v[1] - c[1]), Math.abs(v[2] - c[2])) <= 48;
  const drawn = ring.length ? ring.filter(close).length / ring.length : 0;
  const outer = band(off + w + 1), inner = (off >= 2 || off <= -2) ? band(off - 1) : [];
  const ro = outer.length ? pct(outer.map(o => ratio(c, o)), 0.1) : null;
  const ri = inner.length ? pct(inner.map(o => ratio(c, o)), 0.1) : null;
  const vals = [ro, ri].filter(v => v !== null);
  const twoTone = !!(it.halo && it.halo[3] > 0.95 && it.halo_spread > off + w && ratio(c, it.halo) >= 9);
  return Object.assign(it, { drawn: Math.round(drawn * 100) / 100, ratio_outer: ro, ratio_inner: ri, bg: med(outer), inner_bg: inner.length ? med(inner) : null,
    two_tone_c40: twoTone, ratio: vals.length ? Math.min(...vals) : 0, skip: !vals.length });
}"""


def make_server(root: Path):
    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".wasm": "application/wasm",
                          ".woff2": "font/woff2", ".json": "application/json", ".css": "text/css", ".html": "text/html"}

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def check_page(browser, base, page, theme, vp):
    mobile = vp[0] < 700
    dpr = 2 if mobile else 1
    ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, device_scale_factor=dpr, is_mobile=mobile, has_touch=mobile,
                              color_scheme=theme)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
    rec = {"page": page, "theme": theme, "viewport": f"{vp[0]}x{vp[1]}", "text": [], "ui": [], "errors": errors}
    t0 = time.time()
    try:
        pg.goto(base + page, wait_until="load", timeout=120000)
        if not page.startswith("ontology/"):
            pg.wait_for_function("window.__VLONTO_READY === true", timeout=240000)
        pg.wait_for_timeout(2500 if page in SCENES else 900)
        rec["applied"] = pg.evaluate("document.documentElement.getAttribute('data-theme')")
        n = pg.evaluate(INDEX)
        hdr = pg.evaluate("() => { const h = document.querySelector('.vl-header, .vl-doc-bar'); const s = h ? getComputedStyle(h).position : ''; "
                          "return h && (s === 'sticky' || s === 'fixed') ? Math.ceil(h.getBoundingClientRect().height) : 0; }")
        H = pg.evaluate("() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)")
        step = max(200, vp[1] - hdr - 40)
        ys = list(range(0, max(1, H - vp[1] + 1), step))
        if H > vp[1] and (not ys or ys[-1] < H - vp[1]):
            ys.append(H - vp[1])
        done, results, items_all, ui_all = set(), {}, {}, []
        for y in ys[:80]:
            pg.evaluate(f"window.scrollTo(0, {y})")
            pg.wait_for_timeout(150)
            items = pg.evaluate(COLLECT, {"done": sorted(done), "top": hdr if y > 0 else 0})
            ui = pg.evaluate(UI_COLLECT)
            if not items and not ui:
                continue
            pg.evaluate(HIDE_ON)
            pg.wait_for_timeout(80)
            src = data_url(pg.screenshot())
            pg.evaluate(HIDE_OFF)
            if items:
                for r in pg.evaluate(SAMPLE, {"src": src, "dpr": dpr, "items": items}):
                    results[r["i"]] = r
                for it in items:
                    items_all[it["i"]] = it
                    done.add(it["i"])
            if ui:
                fresh = [u for u in ui if (u["kind"], u["sel"]) not in {(v["kind"], v["sel"]) for v in ui_all}]
                if fresh:
                    ui_all += pg.evaluate(UI_SAMPLE, {"src": src, "dpr": dpr, "items": fresh})
        # focus outlines (top of the page)
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(150)
        nf = pg.evaluate(FOCUS_PICK)
        if nf:
            pg.evaluate(HIDE_ON)
            pg.wait_for_timeout(60)
            for i in range(nf):
                f = pg.evaluate(FOCUS_ON, i)
                if not f:
                    continue
                if f["style"] in ("none", "") or f["width"] < 1:
                    pg.evaluate(FOCUS_OFF)
                    ui_all.append(dict(f, ratio=0, note="no outline when focused (box-shadow: " + (f["shadow"] or "none")[:60] + ")"))
                    continue
                pg.wait_for_timeout(80)
                src = data_url(pg.screenshot())     # rendered with the element focused (text hidden)
                pg.evaluate(FOCUS_OFF)
                ui_all.append(pg.evaluate(FOCUS_SAMPLE, {"src": src, "dpr": dpr, "item": f}))
            pg.evaluate(HIDE_OFF)
        for i, r in results.items():
            it = items_all[i]
            need = 3.0 if it["large"] else 4.5
            ok = it["disabled"] or r["p10"] + TOL >= need
            rec["text"].append({"sel": it["sel"], "text": it["text"], "kind": it["kind"], "size": it["size"], "weight": it["weight"],
                                "large": it["large"], "disabled": it["disabled"], "color": it["color"], "opacity": round(it["opacity"], 3),
                                "bg": r["bg_p10"], "p10": round(r["p10"], 2), "min": round(r["min"], 2), "median": round(r["median"], 2),
                                "need": need, "pass": ok})
        for u in ui_all:
            if u.get("skip"):
                continue
            u["need"] = 3.0
            u["pass"] = (u.get("ratio") or 0) + TOL >= 3.0
            if u.get("kind") == "focus" and "drawn" in u and u["drawn"] < 0.6:
                u["pass"] = False
                u["note"] = f"ring not drawn in the outline colour on {round(100 * (1 - u['drawn']))}% of its length (clipped or covered)"
            for k in ("ratio", "border_ratio", "fill_ratio"):
                if isinstance(u.get(k), float):
                    u[k] = round(u[k], 2)
            rec["ui"].append(u)
        rec["candidates"] = n
    except Exception as e:  # noqa
        rec["error"] = str(e)[:600]
    finally:
        ctx.close()
    rec["s"] = round(time.time() - t0, 1)
    rec["text_checked"] = len(rec["text"])
    rec["text_fail"] = [t for t in rec["text"] if not t["pass"]]
    rec["ui_fail"] = [u for u in rec["ui"] if not u["pass"]]
    rec["pass"] = not rec.get("error") and not rec["text_fail"] and not rec["ui_fail"] and rec.get("applied") == theme and rec["text_checked"] > 0
    return rec


def report_md(rep) -> str:
    L = ["# VLOnto site: WCAG AA contrast (rendered)", "",
         f"Pages {len(PAGES)} x themes {', '.join(rep['themes'])} x viewports {', '.join(rep['viewports'])} over http; "
         "text needs 4.5:1 (3:1 at >= 24 px or >= 18.66 px bold), UI components 3:1. Ratio = 10th percentile over the "
         "background pixels under each text box (text hidden, page rendered).", "",
         "| Page | Theme | Viewport | Text checked | Text fails | UI checked | UI fails | Lowest text ratio (need) | Result |",
         "|---|---|---|---:|---:|---:|---:|---|---|"]
    for r in rep["pages"]:
        low = min(r["text"], key=lambda t: t["p10"] / t["need"]) if r["text"] else None
        L.append(f"| {r['page']} | {r['theme']} | {r['viewport']} | {r['text_checked']} | {len(r['text_fail'])} | {len(r['ui'])} | "
                 f"{len(r['ui_fail'])} | {(str(low['p10']) + ' (' + str(low['need']) + ')') if low else '-'} | {'PASS' if r['pass'] else 'FAIL'} |")
    fails = [(r, t) for r in rep["pages"] for t in r["text_fail"]] + [(r, u) for r in rep["pages"] for u in r["ui_fail"]]
    if fails:
        L += ["", "## Failures", "", "| Page | Theme | Viewport | Element | Text / kind | Ratio | Need | Colour | Background |", "|---|---|---|---|---|---:|---:|---|---|"]
        for r, t in fails[:200]:
            L.append(f"| {r['page']} | {r['theme']} | {r['viewport']} | `{t.get('sel', '')}` | {(t.get('text') or t.get('kind') or '')[:50]}"
                     f"{(' - ' + t['note']) if t.get('note') else ''} | "
                     f"{t.get('p10', t.get('ratio'))} | {t['need']} | {t.get('color')} | {t.get('bg') or t.get('outside')} |")
    errs = [r for r in rep["pages"] if r.get("error")]
    if errs:
        L += ["", "## Errors", ""] + [f"- {r['page']} {r['theme']} {r['viewport']}: {r['error']}" for r in errs]
    L += ["", f"Overall: **{'PASS' if rep['ok'] else 'FAIL'}** ({rep['summary']})", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--viewports", default="1440x900,390x844")
    ap.add_argument("--pages", default=",".join(PAGES))
    ap.add_argument("--chrome", type=Path, default=HERE.parent.parent / "tools" / "chrome.sh")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    srv = make_server(root)
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    themes = [t for t in a.themes.split(",") if t]
    vps = [tuple(int(x) for x in v.split("x")) for v in a.viewports.split(",")]
    pages = [p for p in a.pages.split(",") if p]
    rep = {"tool": "contrast_check.py", "themes": themes, "viewports": [f"{w}x{h}" for w, h in vps], "pages": []}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(a.chrome), headless=True)
        rep["browser_version"] = browser.version
        for theme in themes:
            for vp in vps:
                for page in pages:
                    r = check_page(browser, base, page, theme, vp)
                    rep["pages"].append(r)
                    print(f"[{'PASS' if r['pass'] else 'FAIL'}] {page} {theme} {vp[0]}x{vp[1]}: text {r['text_checked']} "
                          f"(fails {len(r['text_fail'])}), ui {len(r['ui'])} (fails {len(r['ui_fail'])}) {r['s']} s"
                          + (f" ERROR {r['error'][:200]}" if r.get("error") else ""), flush=True)
                    for t in (r["text_fail"] + r["ui_fail"])[:6]:
                        print(f"    - {t.get('sel')} {str(t.get('text') or t.get('kind'))[:40]!r} ratio {t.get('p10', t.get('ratio'))} need {t['need']} "
                              f"colour {t.get('color')} bg {t.get('bg') or t.get('outside')}", flush=True)
        browser.close()
    srv.shutdown()
    rep["summary"] = {"runs": len(rep["pages"]), "failed_runs": sum(1 for r in rep["pages"] if not r["pass"]),
                      "text_checked": sum(r["text_checked"] for r in rep["pages"]), "text_fails": sum(len(r["text_fail"]) for r in rep["pages"]),
                      "ui_checked": sum(len(r["ui"]) for r in rep["pages"]), "ui_fails": sum(len(r["ui_fail"]) for r in rep["pages"])}
    rep["ok"] = rep["summary"]["failed_runs"] == 0
    (a.out / "contrast.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "contrast_report.md").write_text(report_md(rep), encoding="utf-8")
    print("RESULT:", "PASS" if rep["ok"] else "FAIL", rep["summary"])
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

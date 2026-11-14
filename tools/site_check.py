#!/usr/bin/env python3
"""site_check.py - render-level checks for a static site in headless Chrome, over http:// AND file://.

Every page is opened in the pinned chrome-headless-shell (tools/chrome.sh: SwiftShader WebGL, vendored
fonts only) at each viewport (default 1440x900 desktop and 390x844 mobile), once served by a local
HTTP server and once as a plain file:// URL with default browser settings (no
--allow-file-access-from-files), i.e. the way a user double-clicks index.html. A run fails on:

  page_load        navigation error, HTTP status >= 400, ready condition not reached
  failed_requests  any request that failed (blocked by CORS/file:// rules, missing file, 4xx/5xx)
  external         any request outside the site root (CDN, ../ outside root) unless --allow-external
  console_errors   console.error messages (CORS, module, WebGL, script errors) and uncaught exceptions
  canvases         every visible <canvas> must be non-blank (pixel std and non-background share)
  page_overflow    content wider than the configured viewport width (also when mobile Chrome zooms the page
                   out to fit it); lists the elements / text runs that stick out
  clipped_text     text cut off by an overflow:hidden/clip ancestor or ellipsis (scroll > client)
  text_overlap     text line boxes of different text nodes intersecting (> 25% of the smaller box)
  broken_word      a line break inside a word between two letters/digits ("N|ă|m", "20|24", "VLO|nto"),
                   typically from overflow-wrap:anywhere / word-break:break-all in narrow cells; breaks after
                   / - . : _ etc. (URL wrapping) and soft hyphens are allowed; skipped when hyphens:auto
  fonts            @font-face faces that failed to load; families used but never loaded
  glyph_coverage   characters not covered by any declared web font in the element's font-family
                   stack (cmaps read from the actual woff2/ttf/data: sources) -> tofu/fallback risk
  glyph_decomposition  characters the first matching web font lacks but can build from canonical-decomposition
                   pieces (e.g. Noto Serif: ≠ = '=' + U+0338); browsers draw those pieces with misplaced overlays
  local_fallback   CDP platform fonts that are not web fonts (warning; failure with --strict-fonts)
  mojibake         UTF-8-as-Latin-1 sequences (e.g. "Ä‘", "á»") or U+FFFD in the rendered text
  broken_images    <img> that did not decode
  static_lint      file:// hazards in HTML/CSS/own JS: type="module", importmap, fetch/XHR/Worker/
                   instantiateStreaming, root-absolute or protocol-relative URLs, missing local files,
                   @font-face files outside the page directory (Firefox blocks them under file://),
                   missing <meta charset="utf-8">.

Warnings (reported, not failures): console warnings, non-NFC text (combining marks), font stacks that start
with a non-web font, text drawn with local fonts (failure with --strict-fonts), networkidle not reached.

Opt-outs for intentional cases: put data-sc-allow="overlap|clip|overflow|wrap|all" on an element (applies to
its subtree). Pages may set window.__VLONTO_READY (boolean; waited for when defined) and
window.__VLONTO_METRICS (object; copied into the report).

Usage
  site_check.py --root site/ [--pages index.html,graph.html | --all] [--out build/site_check]
                [--modes http,file] [--viewports 1440x900,390x844] [--settle-ms 1500]
                [--config pages.json] [--allow-external] [--strict-fonts] [--chrome tools/chrome.sh]
  pages.json: {"pages": [{"path": "graph.html", "ready": "window.__VLONTO_READY === true",
               "settle_ms": 2500, "min_canvases": 1, "allow_console": ["regex"],
               "fail_on_warning": ["Multiple instances of Three.js"]}]}
Outputs: <out>/site_check_report.json, <out>/site_check_report.md, <out>/shots/*.png (full page per
run), <out>/canvas/*.png (each canvas crop). Exit 0 = all pass, 1 = failures, 2 = setup error.
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import http.server
import io
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.parse
from pathlib import Path


# Slow CI runners (GitHub: 4 CPUs, WebGL in SwiftShader) set VLONTO_TIMEOUT_SCALE (scripts/site/ci_check.sh: 4); every
# wait and screenshot limit is multiplied by it. The assertions are unchanged; on the build node it stays 1.
TIMEOUT_SCALE = max(1.0, float(os.environ.get("VLONTO_TIMEOUT_SCALE") or 1))


def T_(ms: int) -> int:
    return int(ms * TIMEOUT_SCALE)


HERE = Path(__file__).resolve().parent
TOLX = 1.0

# --------------------------------------------------------------------------- in-page collector
COLLECT_JS = r"""
(opts) => {
  const TOLX = 1, TOLY = 2;
  // Compare with the configured device width: mobile Chrome zooms a too-wide page out, which makes
  // window.innerWidth grow to the content width and would hide the overflow.
  const vw = opts.viewportWidth || window.innerWidth, vh = window.innerHeight;
  const csCache = new Map();
  const CS = (el) => { let c = csCache.get(el); if (!c) { c = getComputedStyle(el); csCache.set(el, c); } return c; };
  const allowed = (el, kind) => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const a = e.getAttribute('data-sc-allow');
      if (a) { const t = a.split(/\s+/); if (t.includes(kind) || t.includes('all')) return true; }
    }
    return false;
  };
  const desc = (el) => {
    if (!el || el.nodeType !== 1) return '';
    const parts = [];
    for (let e = el; e && e.nodeType === 1 && parts.length < 4; e = e.parentElement) {
      let s = e.tagName.toLowerCase();
      if (e.id) { parts.unshift(s + '#' + e.id); break; }
      const cls = (e.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) s += '.' + cls.join('.');
      const p = e.parentElement;
      if (p) { const sib = Array.from(p.children).filter(x => x.tagName === e.tagName); if (sib.length > 1) s += ':nth-of-type(' + (sib.indexOf(e) + 1) + ')'; }
      parts.unshift(s);
      if (e === document.body) break;
    }
    return parts.join(' > ');
  };
  const visibleEl = (el) => {
    if (typeof el.checkVisibility === 'function' &&
        !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true, contentVisibilityAuto: true})) return false;
    const c = CS(el);
    return c.visibility !== 'hidden' && c.display !== 'none';
  };
  const visuallyHidden = (el) => {
    for (let e = el; e && e.nodeType === 1 && e !== document.body; e = e.parentElement) {
      const c = CS(e);
      if ((c.clip && /^rect\(0(px)?,? 0(px)?,? 0(px)?,? 0(px)?\)$/.test(c.clip)) || c.clipPath === 'inset(50%)') return true;
      if (e instanceof HTMLElement && e.offsetWidth <= 1 && e.offsetHeight <= 1 && (c.overflow === 'hidden' || c.overflow === 'clip')) return true;
    }
    return false;
  };
  const isBox = (e) => (e instanceof HTMLElement) || (e instanceof SVGSVGElement && !e.ownerSVGElement);
  const boxOf = (e) => {
    const r = e.getBoundingClientRect();
    if (e instanceof HTMLElement) { const l = r.left + e.clientLeft, t = r.top + e.clientTop; return {l, t, r: l + e.clientWidth, b: t + e.clientHeight}; }
    return {l: r.left, t: r.top, r: r.right, b: r.bottom};
  };
  const clipAncestors = (el) => {
    const out = [];
    for (let e = el; e && e.nodeType === 1 && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      if (!isBox(e)) continue;
      const c = CS(e);
      if (c.overflowX !== 'visible' || c.overflowY !== 'visible') out.push(e);
    }
    return out;
  };
  const SKIP = 'script,style,noscript,template,textarea,title';

  // ---- text nodes
  const items = [];
  const groups = new Map();
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const raw = n.data;
    if (!raw || !raw.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest(SKIP)) continue;
    if (!visibleEl(el) || visuallyHidden(el)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const rects = Array.from(range.getClientRects()).filter(r => r.width > 0.5 && r.height > 0.5);
    if (!rects.length) continue;
    const c = CS(el);
    let txt = raw.replace(/\s+/g, ' ');
    if (c.textTransform === 'uppercase') txt = txt.toUpperCase();
    else if (c.textTransform === 'lowercase') txt = txt.toLowerCase();
    else if (c.textTransform === 'capitalize') txt = txt + txt.toUpperCase();
    const key = c.fontFamily + '|' + c.fontWeight + '|' + c.fontStyle;
    let g = groups.get(key);
    if (!g) { g = {family: c.fontFamily, weight: c.fontWeight, style: c.fontStyle, chars: new Set(), where: {}}; groups.set(key, g); }
    for (const ch of txt) { if (!g.chars.has(ch)) { g.chars.add(ch); g.where[ch] = desc(el); } }
    items.push({n, el, rects, text: raw.trim().replace(/\s+/g, ' ').slice(0, 80)});
  }

  // ---- clipped text (rect-based: text box outside an overflow:hidden/clip ancestor's padding box)
  const clipped = [], seenClip = new Set();
  for (const it of items) {
    if (allowed(it.el, 'clip')) continue;
    for (const a of clipAncestors(it.el)) {
      const c = CS(a);
      const hx = c.overflowX === 'hidden' || c.overflowX === 'clip';
      const hy = c.overflowY === 'hidden' || c.overflowY === 'clip';
      if (!hx && !hy) continue;
      const bx = boxOf(a);
      let hit = null;
      for (const r of it.rects) {
        const dx = Math.max(0, bx.l - r.left, r.right - bx.r), dy = Math.max(0, bx.t - r.top, r.bottom - bx.b);
        if ((hx && dx > TOLX) || (hy && dy > TOLY)) { hit = {dx, dy}; break; }
      }
      if (hit) {
        const k = desc(a) + '|' + desc(it.el);
        if (!seenClip.has(k)) { seenClip.add(k); clipped.push({container: desc(a), element: desc(it.el), text: it.text,
            dx: +hit.dx.toFixed(1), dy: +hit.dy.toFixed(1), overflow: c.overflowX + '/' + c.overflowY, textOverflow: c.textOverflow, rule: 'text-outside-clip-box'}); }
      }
    }
  }
  // brief criterion: text container with overflow hidden/clip or ellipsis whose scroll size exceeds client size
  for (const it of items) {
    const e = it.el;
    if (!(e instanceof HTMLElement) || allowed(e, 'clip')) continue;
    const c = CS(e);
    const hid = ['hidden', 'clip'].includes(c.overflowX) || ['hidden', 'clip'].includes(c.overflowY);
    if (!hid) continue;
    const inlineOnly = Array.from(e.children).every(ch => CS(ch).display.startsWith('inline') && !['IMG', 'CANVAS', 'SVG', 'VIDEO', 'IFRAME'].includes(ch.tagName.toUpperCase()));
    if (!inlineOnly) continue;
    const ox = e.scrollWidth - e.clientWidth, oy = e.scrollHeight - e.clientHeight;
    if (ox > TOLX || oy > TOLY) {
      const k = desc(e) + '|' + desc(e);
      if (!seenClip.has(k)) { seenClip.add(k); clipped.push({container: desc(e), element: desc(e), text: it.text, dx: ox, dy: oy,
          overflow: c.overflowX + '/' + c.overflowY, textOverflow: c.textOverflow, rule: 'scroll-size-exceeds-client'}); }
    }
  }

  // ---- horizontal page overflow
  const sw = Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0);
  const wide = Math.max(sw, window.innerWidth);
  const pageOverflow = {scrollWidth: sw, innerWidth: window.innerWidth, viewportWidth: vw, overflowPx: wide - vw,
                        zoomedOut: window.innerWidth > vw + TOLX, offenders: []};
  const insideXClip = (e) => { for (let a = e.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) { if (isBox(a) && CS(a).overflowX !== 'visible') return true; } return false; };
  if (wide > vw + TOLX && document.body) {
    for (const e of document.body.querySelectorAll('*')) {
      if (allowed(e, 'overflow')) continue;
      const r = e.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if ((r.right > vw + TOLX || r.left < -TOLX) && !insideXClip(e)) {
        const p = e.parentElement, pr = p ? p.getBoundingClientRect() : null;
        const parentAlso = p && p !== document.body && pr && (pr.right > vw + TOLX || pr.left < -TOLX);
        pageOverflow.offenders.push({kind: 'element', element: desc(e), left: Math.round(r.left), right: Math.round(r.right), root_cause: !parentAlso,
                                     text: (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 60)});
      }
    }
    for (const it of items) {
      if (allowed(it.el, 'overflow') || insideXClip(it.n.parentElement)) continue;
      const out = it.rects.find(r => r.right > vw + TOLX || r.left < -TOLX);
      if (out) pageOverflow.offenders.push({kind: 'text', element: desc(it.el), left: Math.round(out.left), right: Math.round(out.right), root_cause: true, text: it.text});
    }
    pageOverflow.offenders.sort((a, b) => (b.root_cause - a.root_cause) || (b.right - a.right));
    pageOverflow.offenders = pageOverflow.offenders.slice(0, 25);
  }

  // ---- text overlap (visible parts of line boxes of different text nodes)
  const boxes = [];
  items.forEach((it, idx) => {
    if (allowed(it.el, 'overlap')) return;
    const anc = clipAncestors(it.el).map(boxOf);
    for (const r of it.rects) {
      let l = r.left, t = r.top, rr = r.right, b = r.bottom;
      for (const bx of anc) { l = Math.max(l, bx.l); t = Math.max(t, bx.t); rr = Math.min(rr, bx.r); b = Math.min(b, bx.b); }
      if (rr - l >= 1 && b - t >= 1) boxes.push({i: idx, l, t, r: rr, b});
    }
  });
  const G = 64, grid = new Map(), overlaps = [], seenPair = new Set();
  boxes.forEach((bx, k) => {
    for (let gx = Math.floor(bx.l / G); gx <= Math.floor(bx.r / G); gx++) for (let gy = Math.floor(bx.t / G); gy <= Math.floor(bx.b / G); gy++) {
      const key = gx + ',' + gy; let cell = grid.get(key); if (!cell) { cell = []; grid.set(key, cell); }
      for (const j of cell) {
        const o = boxes[j];
        if (o.i === bx.i) continue;
        const pk = Math.min(o.i, bx.i) + ':' + Math.max(o.i, bx.i);
        if (seenPair.has(pk)) continue;
        const iw = Math.min(o.r, bx.r) - Math.max(o.l, bx.l), ih = Math.min(o.b, bx.b) - Math.max(o.t, bx.t);
        if (iw <= 2 || ih <= 0) continue;
        const amin = Math.min((o.r - o.l) * (o.b - o.t), (bx.r - bx.l) * (bx.b - bx.t));
        const hmin = Math.min(o.b - o.t, bx.b - bx.t);
        if (iw * ih > 0.25 * amin && ih > 0.3 * hmin) {
          seenPair.add(pk);
          if (overlaps.length < 50) overlaps.push({a: desc(items[o.i].el), a_text: items[o.i].text, b: desc(items[bx.i].el), b_text: items[bx.i].text,
                                                   w: +iw.toFixed(1), h: +ih.toFixed(1), x: Math.round(Math.max(o.l, bx.l)), y: Math.round(Math.max(o.t, bx.t))});
        }
      }
      cell.push(k);
    }
  });

  // ---- words broken across lines: a line break between two letters/digits/marks inside one word
  // ("N|ă|m", "20|24", "VLO|nto"), e.g. from overflow-wrap:anywhere or word-break:break-all in a narrow cell.
  // Breaks after punctuation (/ - . : _ ? #, URL wrapping) and at soft hyphens are allowed.
  const WORDCH = /[\p{L}\p{N}\p{M}]/u;
  const brokenWords = [], seenBroken = new Set();
  const wrng = document.createRange();
  for (const it of items) {
    if (brokenWords.length >= 50) break;
    if (it.rects.length < 2 || allowed(it.el, 'wrap')) continue;      // one line box: no break inside this node
    const c = CS(it.el);
    if (c.hyphens === 'auto' || (c.writingMode && !c.writingMode.startsWith('horizontal'))) continue;
    const s = it.n.data, re = /\S+/g;
    let mt;
    while ((mt = re.exec(s))) {
      const a = mt.index, b = a + mt[0].length;
      if (b - a < 2) continue;
      wrng.setStart(it.n, a); wrng.setEnd(it.n, b);
      if (Array.from(wrng.getClientRects()).filter(r => r.width > 0.5 && r.height > 0.5).length < 2) continue;
      let prev = null, prevCh = '';
      for (let i = a; i < b; ) {
        const cp = s.codePointAt(i), ch = String.fromCodePoint(cp), len = ch.length;
        wrng.setStart(it.n, i); wrng.setEnd(it.n, i + len);
        const r = Array.from(wrng.getClientRects()).find(q => q.width > 0.1 && q.height > 0.5);
        if (r) {
          if (prev && r.top > prev.top + Math.max(2, 0.5 * prev.height)) {
            if (WORDCH.test(prevCh) && WORDCH.test(ch)) {
              const k = desc(it.el) + '|' + mt[0];
              if (!seenBroken.has(k)) {
                seenBroken.add(k);
                brokenWords.push({element: desc(it.el), word: mt[0].slice(0, 60), before: s.slice(Math.max(a, i - 12), i), after: s.slice(i, Math.min(b, i + 12)),
                                  x: Math.round(r.left), y: Math.round(r.top), overflowWrap: c.overflowWrap, wordBreak: c.wordBreak});
              }
              break;
            }
          }
          prev = r; prevCh = ch;
        }
        i += len;
      }
    }
  }

  // ---- fonts, images, canvases, mojibake, webgl, timing
  const faces = [];
  if (document.fonts) document.fonts.forEach(f => faces.push({family: f.family.replace(/^['"]|['"]$/g, ''), style: f.style, weight: f.weight, status: f.status, unicodeRange: f.unicodeRange}));
  const brokenImages = Array.from(document.images).filter(im => im.complete && im.naturalWidth === 0 && im.getAttribute('src'))
                         .map(im => ({src: im.getAttribute('src'), element: desc(im)}));
  const canvases = Array.from(document.querySelectorAll('canvas')).map((cv, i) => {
    const r = cv.getBoundingClientRect();
    return {index: i, element: desc(cv), w: Math.round(r.width), h: Math.round(r.height), attrW: cv.width, attrH: cv.height, visible: visibleEl(cv) && r.width >= 8 && r.height >= 8};
  });
  const bodyText = document.body ? document.body.innerText : '';
  const MOJI = /Ã[\u0080-\u00BF]|Ä[\u0080-\u00BF\u2018-\u2122]|Æ[\u00A0-\u00BF]|á[º»]|â€|Â[\u0080-\u00A0]|\uFFFD/g;
  const mojibake = []; let m;
  while ((m = MOJI.exec(bodyText)) && mojibake.length < 20) mojibake.push(bodyText.slice(Math.max(0, m.index - 25), m.index + 25));
  const combining = (bodyText.match(/[\u0300-\u036f]/g) || []).length;
  const nfcSample = combining ? (bodyText.match(/.{0,20}[\u0300-\u036f].{0,20}/) || [''])[0] : '';
  let webgl = null;
  try {
    const cv = document.createElement('canvas'); const gl = cv.getContext('webgl2') || cv.getContext('webgl');
    if (gl) { const e = gl.getExtension('WEBGL_debug_renderer_info');
              webgl = {version: gl.getParameter(gl.VERSION), renderer: e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)};
              const lc = gl.getExtension('WEBGL_lose_context'); if (lc) lc.loseContext(); }
    else webgl = {error: 'no WebGL context'};
  } catch (e) { webgl = {error: String(e)}; }
  const nav = performance.getEntriesByType('navigation')[0];
  // mark text parents for CDP platform-font queries
  const marked = []; const seenEl = new Set();
  for (const it of items) { if (!seenEl.has(it.el) && marked.length < opts.maxMarked) { seenEl.add(it.el); it.el.setAttribute('data-sc-t', String(marked.length)); marked.push(desc(it.el)); } }
  return {
    viewport: {w: vw, h: vh, dpr: window.devicePixelRatio}, docHeight: Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0),
    title: document.title, textNodes: items.length,
    groups: Array.from(groups.values()).map(g => ({family: g.family, weight: g.weight, style: g.style, chars: Array.from(g.chars).join(''), where: g.where})),
    clipped, pageOverflow, overlaps, brokenWords, faces, brokenImages, canvases, mojibake, webgl, marked, combining, nfcSample,
    timing: nav ? {domContentLoaded: Math.round(nav.domContentLoadedEventEnd), load: Math.round(nav.loadEventEnd)} : null,
    metrics: (window.__VLONTO_METRICS && typeof window.__VLONTO_METRICS === 'object') ? JSON.parse(JSON.stringify(window.__VLONTO_METRICS)) : null,
    ready: window.__VLONTO_READY === undefined ? null : !!window.__VLONTO_READY,
  };
}
"""

# --------------------------------------------------------------------------- CSS / font parsing
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif",
           "ui-monospace", "ui-rounded", "emoji", "math", "fangsong", "-apple-system", "blinkmacsystemfont"}
IGNORABLE = re.compile(r"[\s\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u2064\ufe00-\ufe0f\ufeff]")


def split_top(s: str, sep: str) -> list[str]:
    out, buf, depth, q = [], [], 0, None
    for ch in s:
        if q:
            buf.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_families(value: str) -> list[str]:
    return [unquote(x) for x in split_top(value, ",")]


def parse_unicode_range(v: str):
    out = []
    for part in split_top(v, ","):
        p = part.upper().replace("U+", "")
        if "?" in p:
            out.append((int(p.replace("?", "0"), 16), int(p.replace("?", "F"), 16)))
        elif "-" in p:
            a, b = p.split("-", 1)
            out.append((int(a, 16), int(b, 16)))
        elif p:
            out.append((int(p, 16), int(p, 16)))
    return out or [(0, 0x10FFFF)]


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class FontRegistry:
    """@font-face faces found in the page's stylesheets, with cmaps loaded from the real files."""

    def __init__(self):
        self.faces: dict[str, list[dict]] = {}  # family(lower) -> faces
        self.errors: list[str] = []
        self._cmap_cache: dict[str, set] = {}

    def _cmap(self, key: str, data: bytes) -> set:
        if key not in self._cmap_cache:
            from fontTools.ttLib import TTFont
            f = TTFont(io.BytesIO(data), fontNumber=0, lazy=True)
            self._cmap_cache[key] = set((f.getBestCmap() or {}).keys())
        return self._cmap_cache[key]

    def add_css(self, css: str, base: Path, root: Path, page_dir: Path, lint: list, seen: set):
        css = strip_comments(css)
        for m in re.finditer(r"@import\s+(?:url\()?\s*['\"]?([^'\")\s;]+)['\"]?\s*\)?", css):
            ref = m.group(1)
            if re.match(r"^[a-z]+:", ref, re.I) or ref.startswith("//"):
                lint.append(("fail", f"external @import {ref}"))
                continue
            p = (base / urllib.parse.unquote(ref)).resolve()
            if p in seen:
                continue
            seen.add(p)
            if p.exists():
                self.add_css(p.read_text(encoding="utf-8", errors="replace"), p.parent, root, page_dir, lint, seen)
            else:
                lint.append(("fail", f"missing @import file {ref}"))
        for block in re.finditer(r"@font-face\s*\{(.*?)\}", css, re.S | re.I):
            decl = {}
            for d in split_top(block.group(1), ";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    decl[k.strip().lower()] = v.strip()
            fam = unquote(decl.get("font-family", "")).strip()
            if not fam:
                continue
            ranges = parse_unicode_range(decl.get("unicode-range", "U+0-10FFFF"))
            cmap, src_desc = None, None
            for item in split_top(decl.get("src", ""), ","):
                um = re.match(r"url\(\s*(['\"]?)(.*?)\1\s*\)", item, re.S)
                if not um:
                    continue
                url = um.group(2).strip()
                try:
                    if url.startswith("data:"):
                        header, _, payload = url.partition(",")
                        data = base64.b64decode(payload) if ";base64" in header else urllib.parse.unquote_to_bytes(payload)
                        key = "data:" + hashlib.sha1(data).hexdigest()
                        src_desc = f"data: ({len(data):,} bytes)"
                    elif re.match(r"^[a-z]+:", url, re.I) or url.startswith("//"):
                        lint.append(("fail", f"external font url {url[:80]}"))
                        continue
                    else:
                        p = (base / urllib.parse.unquote(url.split("#")[0].split("?")[0])).resolve()
                        try:
                            p.relative_to(page_dir)
                        except ValueError:
                            lint.append(("fail", f"@font-face file outside the page directory (Firefox blocks it under file://): {url}"))
                        if not p.exists():
                            lint.append(("fail", f"missing font file {url}"))
                            continue
                        data = p.read_bytes()
                        key = str(p)
                        try:
                            src_desc = str(p.relative_to(root))
                        except ValueError:
                            src_desc = str(p)
                    cmap = self._cmap(key, data)
                    break
                except Exception as e:  # unreadable font
                    self.errors.append(f"{fam}: cannot read {url[:60]}: {e}")
            if cmap is None:
                continue
            self.faces.setdefault(fam.lower(), []).append({"family": fam, "ranges": ranges, "cmap": cmap, "src": src_desc,
                                                           "weight": decl.get("font-weight", "normal"), "style": decl.get("font-style", "normal")})

    def covers(self, family: str, cp: int) -> bool:
        for f in self.faces.get(family.lower(), []):
            if any(lo <= cp <= hi for lo, hi in f["ranges"]) and cp in f["cmap"]:
                return True
        return False

    def support(self, family: str, cp: int) -> str | None:
        """'cmap' if a face of `family` (within its unicode-range) maps cp; 'decomposed' if a face whose
        unicode-range includes cp lacks it but maps every character of cp's canonical decomposition - browsers
        (HarfBuzz) then draw cp from those pieces with that font (e.g. Noto Serif draws ≠ as '=' + U+0338) instead
        of falling back; None otherwise (the browser moves on to the next family)."""
        if self.covers(family, cp):
            return "cmap"
        dec = unicodedata.normalize("NFD", chr(cp))
        if len(dec) > 1:
            for f in self.faces.get(family.lower(), []):
                if any(lo <= cp <= hi for lo, hi in f["ranges"]) and all(ord(x) in f["cmap"] for x in dec):
                    return "decomposed"
        return None


# --------------------------------------------------------------------------- static lint
JS_HAZARDS = [
    (r"\bfetch\s*\(", "fail", "fetch() is blocked for file:// pages in Chrome; load data with <script src=data/*.js> (tools/json2js.py)"),
    (r"\bXMLHttpRequest\b", "fail", "XMLHttpRequest of local files is blocked under file://"),
    (r"instantiateStreaming|compileStreaming", "fail", "WebAssembly.*Streaming needs fetch(); embed the wasm (see vendor/oxigraph)"),
    (r"\bnew\s+(Shared)?Worker\s*\(", "fail", "Workers from file:// URLs are blocked; use a Blob URL or run on the main thread"),
    (r"\bimportScripts\s*\(", "fail", "importScripts is not available for file:// pages"),
    (r"(^|[;\s])import\s*\(", "fail", "dynamic import() of ES modules is blocked under file://"),
    (r"(^|\n)\s*import\s+[\w{*].*\bfrom\s+['\"]", "fail", "ES module import statement: classic scripts only"),
    (r"(^|\n)\s*export\s+(default|const|function|class|\{)", "fail", "ES module export statement: classic scripts only"),
    (r"navigator\.serviceWorker", "warn", "service workers do not exist for file:// pages"),
    (r"history\.(pushState|replaceState)\s*\(", "warn", "history.pushState throws for file:// pages in some browsers; use #hash routing"),
]


def lint_page(root: Path, page: str, allow_external: bool):
    from bs4 import BeautifulSoup
    page_path = (root / page).resolve()
    page_dir = page_path.parent
    html = page_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str]] = []
    reg = FontRegistry()
    css_seen: set = set()
    if not re.search(r"<meta[^>]+charset\s*=\s*['\"]?utf-8", html[:2048], re.I):
        out.append(("fail", 'missing <meta charset="utf-8"> in the first 2 KB (external data scripts are decoded with the page charset under file://)'))
    if not soup.find("meta", attrs={"name": "viewport"}):
        out.append(("warn", "missing <meta name=viewport> (mobile layout)"))

    def check_ref(ref: str, what: str, must_exist=True):
        if not ref or ref.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:", "about:")):
            return None
        if ref.startswith("//"):
            out.append(("fail", f"{what}: protocol-relative URL {ref} resolves to file://{ref[2:]} when opened locally"))
            return None
        if re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I):
            if not allow_external and what != "link(a)":
                out.append(("fail", f"{what}: external resource {ref[:100]} (vendor it; pages must work offline)"))
            return None
        if ref.startswith("/"):
            out.append(("fail", f"{what}: root-absolute URL {ref} breaks under file:// (use a relative path)"))
            return None
        p = (page_dir / urllib.parse.unquote(ref.split("#")[0].split("?")[0])).resolve()
        if must_exist and not p.exists():
            out.append(("fail", f"{what}: missing local file {ref}"))
            return None
        try:
            p.relative_to(root.resolve())
        except ValueError:
            out.append(("warn", f"{what}: {ref} is outside the site root"))
        return p

    def lint_js(text: str, where: str):
        for pat, sev, msg in JS_HAZARDS:
            if re.search(pat, text, re.M):
                out.append((sev, f"{where}: {msg}"))

    for s in soup.find_all("script"):
        typ = (s.get("type") or "").strip().lower()
        if typ == "module":
            out.append(("fail", f"<script type=module{' src=' + s.get('src') if s.get('src') else ''}> is blocked under file:// (CORS); use a classic UMD/IIFE build"))
        if typ == "importmap":
            out.append(("fail", "<script type=importmap>: import maps only serve ES modules, which are blocked under file://"))
        src = s.get("src")
        if src:
            p = check_ref(src, "script")
            rel = src.replace("\\", "/")
            if p and p.suffix in (".js", ".mjs") and "vendor/" not in rel and "/data/" not in "/" + rel:
                lint_js(p.read_text(encoding="utf-8", errors="replace"), src)
        elif typ in ("", "text/javascript", "application/javascript"):
            lint_js(s.get_text(), "inline <script>")
    for l in soup.find_all("link"):
        rels = [r.lower() for r in (l.get("rel") or [])]
        href = l.get("href")
        if "modulepreload" in rels:
            out.append(("fail", f"<link rel=modulepreload href={href}>: ES modules are blocked under file://"))
        if "preconnect" in rels or "dns-prefetch" in rels:
            continue
        p = check_ref(href, "link(" + ",".join(rels) + ")")
        if p and "stylesheet" in rels and p.suffix == ".css" and p not in css_seen:
            css_seen.add(p)
            reg.add_css(p.read_text(encoding="utf-8", errors="replace"), p.parent, root.resolve(), page_dir, out, css_seen)
    for st in soup.find_all("style"):
        reg.add_css(st.get_text(), page_dir, root.resolve(), page_dir, out, css_seen)
    for tag, attr in (("img", "src"), ("source", "src"), ("video", "src"), ("audio", "src"), ("iframe", "src"), ("embed", "src"), ("object", "data")):
        for t in soup.find_all(tag):
            check_ref(t.get(attr), tag)
    for t in soup.find_all(["img", "source"]):
        for part in (t.get("srcset") or "").split(","):
            if part.strip():
                check_ref(part.strip().split()[0], "srcset")
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if href.startswith("#") and len(href) > 1 and not soup.find(id=href[1:]):
            out.append(("warn", f"anchor {href} has no target id on the page"))
        elif href and not href.startswith("#"):
            check_ref(href, "link(a)")
    # de-duplicate, keep order
    seen, uniq = set(), []
    for sev, msg in out:
        if (sev, msg) not in seen:
            seen.add((sev, msg))
            uniq.append({"severity": sev, "message": msg})
    return uniq, reg


# --------------------------------------------------------------------------- helpers
def canvas_stats(png: bytes) -> dict:
    import numpy as np
    from PIL import Image
    im = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.int32)
    lum = 0.299 * im[..., 0] + 0.587 * im[..., 1] + 0.114 * im[..., 2]
    q = (im >> 3)
    keys = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    vals, counts = np.unique(keys, return_counts=True)
    mode_frac = float(counts.max()) / keys.size
    std = float(lum.std())
    return {"std": round(std, 2), "non_background_share": round(1 - mode_frac, 4), "colors_5bit": int(len(vals)),
            "nonblank": bool(std >= 2.0 and (1 - mode_frac) >= 0.01)}


def make_server(root: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm",
                          ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf",
                          ".json": "application/json", ".svg": "image/svg+xml", ".ttl": "text/turtle",
                          ".css": "text/css", ".html": "text/html", ".png": "image/png"}

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def slug(page: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", page.replace("/", "__")).removesuffix(".html")


def parse_viewports(s: str):
    out = []
    for v in s.split(","):
        w, h = v.lower().split("x")
        out.append((int(w), int(h)))
    return out


# --------------------------------------------------------------------------- one run
def run_one(browser, root: Path, page: str, mode: str, vp, base_http: str, cfg: dict, args, reg: FontRegistry, outdir: Path):
    w, h = vp
    mobile = w < 700
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1,
                              is_mobile=mobile, has_touch=mobile)
    pg = ctx.new_page()
    pg.set_default_timeout(T_(30000))
    url = (base_http + urllib.parse.quote(page)) if mode == "http" else (root / page).resolve().as_uri()
    root_prefix = base_http if mode == "http" else root.resolve().as_uri().rstrip("/") + "/"
    rec = {"page": page, "mode": mode, "viewport": f"{w}x{h}", "url": url, "failures": [], "warnings": []}
    console_err, console_warn, page_err, failed, bad_status, external = [], [], [], [], [], []
    allow_console = [re.compile(x) for x in cfg.get("allow_console", [])]
    warn_fail = [re.compile(x) for x in cfg.get("fail_on_warning", []) + (args.fail_on_warning or [])]

    def on_console(msg):
        t = msg.type
        loc = msg.location or {}
        text = f"{msg.text[:400]} @{(loc.get('url') or '')[-80:]}:{loc.get('lineNumber', '')}"
        if t == "error" and not any(r.search(msg.text) for r in allow_console):
            console_err.append(text)
        elif t == "warning":
            console_warn.append(text)
            if any(r.search(msg.text) for r in warn_fail):
                console_err.append("warning-as-error: " + text)

    def on_request(req):
        u = req.url
        if u.startswith(("data:", "blob:", "about:")) or u.startswith(root_prefix):
            return
        if mode == "http" and u.startswith(base_http):
            return
        external.append(u[:200])

    pg.on("console", on_console)
    pg.on("pageerror", lambda e: page_err.append(str(e)[:400]))
    pg.on("requestfailed", lambda r: failed.append(f"{r.url[:200]} :: {r.failure}"))
    pg.on("response", lambda r: bad_status.append(f"{r.status} {r.url[:200]}") if r.status >= 400 else None)
    pg.on("request", on_request)
    pg.on("dialog", lambda d: d.dismiss())
    t0 = time.time()
    try:
        resp = pg.goto(url, wait_until="load", timeout=args.nav_timeout_ms)
        rec["status"] = resp.status if resp else None
        if resp is not None and resp.status >= 400:
            rec["failures"].append(f"page_load: HTTP {resp.status}")
        try:
            pg.wait_for_load_state("networkidle", timeout=args.nav_timeout_ms)
        except Exception:
            rec["warnings"].append("networkidle not reached")
        ready_expr = cfg.get("ready")
        if not ready_expr and pg.evaluate("window.__VLONTO_READY !== undefined"):
            ready_expr = "window.__VLONTO_READY === true"
        if ready_expr:
            try:
                pg.wait_for_function(ready_expr, timeout=cfg.get("ready_timeout_ms", args.ready_timeout_ms))
            except Exception:
                rec["failures"].append(f"page_load: ready condition not reached: {ready_expr}")
        pg.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true")
        pg.wait_for_timeout(cfg.get("settle_ms", args.settle_ms))
    except Exception as e:
        rec["failures"].append(f"page_load: {str(e).splitlines()[0][:300]}")
        rec["load_s"] = round(time.time() - t0, 2)
        _finish(rec, console_err, console_warn, page_err, failed, bad_status, external)
        ctx.close()
        return rec
    rec["load_s"] = round(time.time() - t0, 2)
    data = pg.evaluate(COLLECT_JS, {"maxMarked": 3000, "viewportWidth": w})
    # platform fonts via CDP
    plat = {}
    local_fb = []
    if not args.no_platform_fonts and data["marked"]:
        try:
            cdp = ctx.new_cdp_session(pg)
            cdp.send("DOM.enable")
            cdp.send("CSS.enable")
            doc = cdp.send("DOM.getDocument", {"depth": -1})
            ids = cdp.send("DOM.querySelectorAll", {"nodeId": doc["root"]["nodeId"], "selector": "[data-sc-t]"})["nodeIds"]
            for nid in ids:
                attrs = cdp.send("DOM.getAttributes", {"nodeId": nid})["attributes"]
                idx = int(dict(zip(attrs[::2], attrs[1::2])).get("data-sc-t", -1))
                for f in cdp.send("CSS.getPlatformFontsForNode", {"nodeId": nid}).get("fonts", []):
                    k = f["familyName"] + (" (web font)" if f.get("isCustomFont") else " (local)")
                    plat[k] = plat.get(k, 0) + int(f.get("glyphCount", 0))
                    if not f.get("isCustomFont") and len(local_fb) < 30:
                        local_fb.append({"element": data["marked"][idx] if 0 <= idx < len(data["marked"]) else "?",
                                         "font": f["familyName"], "glyphs": f.get("glyphCount")})
            cdp.detach()
        except Exception as e:
            rec["warnings"].append(f"platform-font query failed: {e}")
    pg.evaluate("document.querySelectorAll('[data-sc-t]').forEach(e => e.removeAttribute('data-sc-t'))")
    rec["platform_fonts"] = plat
    rec["local_fallback"] = local_fb
    # canvases
    canv = []
    loc = pg.locator("canvas")
    for c in data["canvases"]:
        if not c["visible"]:
            canv.append({**c, "checked": False})
            continue
        try:
            # 30 s x VLONTO_TIMEOUT_SCALE: the 3D legal network draws at about 1 fps in SwiftShader on CI runners, and a slow
            # runner (run 43473053998: pages 1.3-1.6x slower) took over 60 s for one frame
            png = loc.nth(c["index"]).screenshot(timeout=T_(30000))
            st = canvas_stats(png)
            cpath = outdir / "canvas" / f"{slug(page)}__{mode}__{w}x{h}__canvas{c['index']}.png"
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_bytes(png)
            canv.append({**c, **st, "checked": True, "crop": str(cpath.relative_to(outdir))})
            if not st["nonblank"]:
                rec["failures"].append(f"canvas: {c['element']} is blank (std {st['std']}, non-background {st['non_background_share']})")
        except Exception as e:
            rec["failures"].append(f"canvas: {c['element']} screenshot failed: {str(e).splitlines()[0][:200]}")
    rec["canvases"] = canv
    need = cfg.get("min_canvases", 0)
    if sum(1 for c in canv if c.get("nonblank")) < need:
        rec["failures"].append(f"canvas: expected >= {need} non-blank canvases")
    # full-page screenshot
    shot = outdir / "shots" / f"{slug(page)}__{mode}__{w}x{h}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    try:
        if data["docHeight"] > 16000:
            pg.screenshot(path=str(shot), clip={"x": 0, "y": 0, "width": w, "height": 16000}, full_page=True)
            rec["warnings"].append(f"screenshot truncated at 16000 px (page {data['docHeight']} px)")
        else:
            pg.screenshot(path=str(shot), full_page=True)
        rec["screenshot"] = str(shot.relative_to(outdir))
    except Exception as e:
        rec["warnings"].append(f"screenshot failed: {e}")
    # page checks
    po = data["pageOverflow"]
    rec["page_overflow"] = po
    if po["overflowPx"] > TOLX:
        culprits = "; ".join(f"{o['kind']} {o['element']} right={o['right']} '{o['text'][:40]}'" for o in po["offenders"][:3])
        zoom = f", mobile browser zoomed out to {po['innerWidth']} px" if po.get("zoomedOut") else ""
        rec["failures"].append(f"page_overflow: content {po['viewportWidth'] + po['overflowPx']} px wide > viewport {po['viewportWidth']} px{zoom} ({culprits})")
    rec["clipped_text"] = data["clipped"]
    for c in data["clipped"][:10]:
        rec["failures"].append(f"clipped_text: {c['element']} in {c['container']} '{c['text'][:50]}' (dx {c['dx']}, dy {c['dy']}, {c['rule']})")
    rec["text_overlap"] = data["overlaps"]
    for o in data["overlaps"][:10]:
        rec["failures"].append(f"text_overlap: '{o['a_text'][:30]}' ({o['a']}) x '{o['b_text'][:30]}' ({o['b']}) {o['w']}x{o['h']} px")
    rec["broken_words"] = data["brokenWords"]
    for w in data["brokenWords"][:10]:
        rec["failures"].append(f"broken_word: '{w['before']}|{w['after']}' in {w['element']} (word '{w['word'][:40]}', "
                               f"overflow-wrap {w['overflowWrap']}, word-break {w['wordBreak']})")
    rec["broken_images"] = data["brokenImages"]
    for b in data["brokenImages"]:
        rec["failures"].append(f"broken_image: {b['src']}")
    rec["mojibake"] = data["mojibake"]
    for s in data["mojibake"][:5]:
        rec["failures"].append(f"mojibake: ...{s}...")
    rec["combining_marks"] = data["combining"]
    if data["combining"]:
        rec["warnings"].append(f"text is not NFC: {data['combining']} combining mark(s), e.g. '{data['nfcSample']}' - "
                               "normalise data to NFC (fonts without mark positioning misplace decomposed diacritics)")
    # fonts
    faces = data["faces"]
    rec["font_faces"] = faces
    for f in faces:
        if f["status"] == "error":
            rec["failures"].append(f"fonts: @font-face {f['family']} {f['weight']} {f['style']} failed to load")
    loaded_fams = {f["family"].lower() for f in faces if f["status"] == "loaded"}
    declared = {f["family"].lower() for f in faces}
    missing_glyphs, decomposed, local_first = [], [], set()
    for g in data["groups"]:
        fams = parse_families(g["family"])
        first = fams[0].lower() if fams else ""
        if first in declared and first not in loaded_fams:
            rec["failures"].append(f"fonts: family '{fams[0]}' is used but no face of it loaded")
        web = [f for f in fams if f.lower() in reg.faces]
        if fams and fams[0].lower() not in reg.faces and fams[0].lower() not in GENERIC and web:
            local_first.add(g["family"])
        for ch in g["chars"]:
            if IGNORABLE.match(ch):
                continue
            cp = ord(ch)
            hit = next(((s, f) for f in web for s in [reg.support(f, cp)] if s), None)  # first family in stack order
            item = {"char": ch, "codepoint": f"U+{cp:04X}", "font_family": g["family"], "element": g["where"].get(ch, "")}
            if hit is None:
                missing_glyphs.append(item)
            elif hit[0] == "decomposed":
                decomposed.append({**item, "drawn_by": hit[1], "pieces": " + ".join(f"U+{ord(x):04X}" for x in unicodedata.normalize("NFD", ch))})
    rec["glyph_coverage"] = {"web_font_families": sorted({v[0]["family"] for v in reg.faces.values()}),
                             "groups": len(data["groups"]), "uncovered": missing_glyphs[:200], "decomposed": decomposed[:100]}
    if missing_glyphs:
        sample = ", ".join(f"{m['char']} {m['codepoint']} in {m['element']} [{m['font_family'][:40]}]" for m in missing_glyphs[:6])
        rec["failures"].append(f"glyph_coverage: {len(missing_glyphs)} character(s) not covered by any declared web font: {sample}")
    if decomposed:
        sample = ", ".join(f"{m['char']} {m['codepoint']} by {m['drawn_by']} as {m['pieces']} in {m['element']}" for m in decomposed[:4])
        rec["failures"].append(f"glyph_decomposition: {len(decomposed)} character(s) the first matching web font lacks and would "
                               f"draw from decomposed pieces (misplaced overlays); put a font that has them earlier: {sample}")
    if local_first:
        rec["warnings"].append(f"font stacks start with a non-web-font family (renders differently per machine): {sorted(local_first)[:3]}")
    if local_fb:
        msg = f"local_fallback: text drawn with non-web fonts: {sorted({x['font'] for x in local_fb})} e.g. {local_fb[0]['element']}"
        (rec["failures"] if args.strict_fonts else rec["warnings"]).append(msg)
    rec["webgl"] = data["webgl"]
    if cfg.get("expect_webgl") and (not data["webgl"] or "error" in data["webgl"]):
        rec["failures"].append(f"webgl: unavailable ({data['webgl']})")
    rec["timing_ms"] = data["timing"]
    rec["metrics"] = data["metrics"]
    rec["ready"] = data["ready"]
    rec["text_nodes"] = data["textNodes"]
    rec["title"] = data["title"]
    _finish(rec, console_err, console_warn, page_err, failed, bad_status, external)
    ctx.close()
    return rec


def _finish(rec, console_err, console_warn, page_err, failed, bad_status, external):
    rec["console_errors"] = console_err
    rec["console_warnings"] = console_warn[:50]
    rec["page_errors"] = page_err
    rec["failed_requests"] = failed + bad_status
    rec["external_requests"] = external
    for e in console_err[:10]:
        rec["failures"].append(f"console_error: {e}")
    for e in page_err[:10]:
        rec["failures"].append(f"page_error: {e}")
    for e in (failed + bad_status)[:10]:
        rec["failures"].append(f"failed_request: {e}")
    for e in external[:10]:
        if not rec.get("_allow_external"):
            rec["failures"].append(f"external_request: {e}")
    rec.pop("_allow_external", None)
    rec["ok"] = not rec["failures"]


def to_markdown(rep: dict) -> str:
    L = ["# site_check report", "",
         f"- root: `{rep['root']}`  ", f"- chrome: {rep['browser_version']} via `{rep['chrome']}`  ",
         f"- modes: {', '.join(rep['modes'])}; viewports: {', '.join(rep['viewports'])}  ",
         f"- result: **{'PASS' if rep['ok'] else 'FAIL'}** ({rep['summary']['failed_runs']} of {rep['summary']['runs']} runs failed, "
         f"{rep['summary']['lint_failures']} static-lint failures)", ""]
    L.append("| page | mode | viewport | result | console err | failed req | canvases non-blank | overflow px | clipped | overlaps | broken words | uncovered glyphs | load s |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for p in rep["pages"]:
        for r in p["runs"]:
            cv = r.get("canvases", [])
            L.append(f"| {r['page']} | {r['mode']} | {r['viewport']} | {'PASS' if r['ok'] else 'FAIL'} | {len(r.get('console_errors', []))} | "
                     f"{len(r.get('failed_requests', []))} | {sum(1 for c in cv if c.get('nonblank'))}/{len(cv)} | "
                     f"{max(0, r.get('page_overflow', {}).get('overflowPx', 0))} | {len(r.get('clipped_text', []))} | {len(r.get('text_overlap', []))} | "
                     f"{len(r.get('broken_words', []))} | "
                     f"{len(r.get('glyph_coverage', {}).get('uncovered', []))} | {r.get('load_s', '')} |")
    for p in rep["pages"]:
        fails = [l for l in p["lint"] if l["severity"] == "fail"]
        if fails or any(not r["ok"] for r in p["runs"]):
            L += ["", f"## {p['page']}", ""]
            for l in fails:
                L.append(f"- static_lint: {l['message']}")
            for r in p["runs"]:
                for f in r["failures"][:25]:
                    L.append(f"- [{r['mode']} {r['viewport']}] {f}")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--all", action="store_true", help="all *.html files directly under --root")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--out", type=Path, default=Path("site_check_out"))
    ap.add_argument("--modes", default="http,file")
    ap.add_argument("--viewports", default="1440x900,390x844")
    ap.add_argument("--settle-ms", type=int, default=1500)
    ap.add_argument("--nav-timeout-ms", type=int, default=60000)
    ap.add_argument("--ready-timeout-ms", type=int, default=60000)
    ap.add_argument("--chrome", type=Path, default=HERE / "chrome.sh")
    ap.add_argument("--allow-external", action="store_true")
    ap.add_argument("--strict-fonts", action="store_true", help="fail (not warn) when text is drawn with local fonts")
    ap.add_argument("--no-platform-fonts", action="store_true")
    ap.add_argument("--fail-on-warning", action="append", help="regex: console warnings that count as errors")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    if not root.is_dir():
        print(f"--root {root} is not a directory", file=sys.stderr)
        return 2
    cfgs = {}
    if a.config:
        for pc in json.loads(a.config.read_text())["pages"]:
            cfgs[pc["path"]] = pc
    pages = [p for p in a.pages.split(",") if p] or list(cfgs)
    if a.all:
        pages += [p.name for p in sorted(root.glob("*.html")) if p.name not in pages]
    if not pages:
        print("no pages given (--pages, --all or --config)", file=sys.stderr)
        return 2
    for p in pages:
        if not (root / p).is_file():
            print(f"page not found: {root / p}", file=sys.stderr)
            return 2
    modes = [m for m in a.modes.split(",") if m]
    vps = parse_viewports(a.viewports)
    a.out.mkdir(parents=True, exist_ok=True)
    srv = make_server(root)
    base_http = f"http://127.0.0.1:{srv.server_address[1]}/"
    from playwright.sync_api import sync_playwright
    rep = {"tool": "site_check.py", "root": str(root), "chrome": str(a.chrome), "modes": modes,
           "viewports": [f"{w}x{h}" for w, h in vps], "pages": []}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=str(a.chrome), headless=True)
        except Exception as e:
            print(f"cannot launch {a.chrome}: {e}", file=sys.stderr)
            return 2
        rep["browser_version"] = browser.version
        for page in pages:
            cfg = cfgs.get(page, {})
            lint, reg = lint_page(root, page, a.allow_external)
            prec = {"page": page, "lint": lint, "font_faces_declared": {k: [f["src"] for f in v] for k, v in reg.faces.items()},
                    "font_read_errors": reg.errors, "runs": []}
            for mode in modes:
                for vp in vps:
                    r = run_one(browser, root, page, mode, vp, base_http, cfg, a, reg, a.out)
                    if a.allow_external:
                        r["failures"] = [f for f in r["failures"] if not f.startswith("external_request")]
                        r["ok"] = not r["failures"]
                    prec["runs"].append(r)
                    print(f"[{'PASS' if r['ok'] else 'FAIL'}] {page} {mode} {r['viewport']} ({r.get('load_s')} s)"
                          + "".join(f"\n    - {f}" for f in r["failures"][:12]), flush=True)
            for l in lint:
                if l["severity"] == "fail":
                    print(f"[LINT] {page}: {l['message']}")
            rep["pages"].append(prec)
        browser.close()
    srv.shutdown()
    runs = [r for p in rep["pages"] for r in p["runs"]]
    lint_fail = sum(1 for p in rep["pages"] for l in p["lint"] if l["severity"] == "fail")
    rep["summary"] = {"pages": len(rep["pages"]), "runs": len(runs), "failed_runs": sum(1 for r in runs if not r["ok"]),
                      "lint_failures": lint_fail}
    rep["ok"] = rep["summary"]["failed_runs"] == 0 and lint_fail == 0
    (a.out / "site_check_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "site_check_report.md").write_text(to_markdown(rep), encoding="utf-8")
    print(f"RESULT: {'PASS' if rep['ok'] else 'FAIL'} - {rep['summary']}  report: {a.out / 'site_check_report.json'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

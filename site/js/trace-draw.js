/* VLOnto question traces - SVG drawing of one trace (classic script, no DOM access: the same code runs in the page and
   in the offline preview, scripts/site/trace_preview.py).

   The geometry is computed at build time by scripts/site/trace_layout.py: projected node positions (graph units), links,
   traced segments, floor shadows and, per view (card = the paper's Fig. 6 panel; wide / tall = the focus view in the
   manner of Fig. 1), a transform [a, tx, ty] and the call-outs (box, text lines, leader line). The card has its own
   composition: its view carries the node positions (n), floor shadows (s), drawing order (o) and link opacities (lo);
   nodes flagged as background there, and the links that touch them, get the class "bg" (a call-out may cover them,
   as in the paper). Colours are not in the markup: CSS classes and custom properties (css/site.css, "question traces")
   give the paper's class palette and the traced path (navy core over a pale-gold halo; light core on the dark theme),
   so a theme switch needs no redraw.

   VL.TraceDraw.svg(trace, view, opts) -> SVG string; opts: id (unique prefix), title, desc, nodeTitles (one <title>
   per node, focus view), lang ('en' | 'vi' | 'envi'; default: the page's language mode, js/i18n.js, else 'envi').
   The build-time call-outs hold Vietnamese and English lines; in EN or VI only that language's lines are drawn, centred
   in the same box (a call-out with lines in one language only keeps them). VL.TraceDraw.defs() -> the shared gradients
   (once per page). The file needs no DOM and no js/i18n.js (scripts/site/trace_preview.py runs it in V8). */
(function (root) {
  'use strict';
  var VL = root.VL = root.VL || {};
  var TD = VL.TraceDraw = {};
  TD.CLASSES = ['work', 'record', 'chapter', 'section', 'article', 'clause', 'point', 'term', 'question', 'answer', 'area', 'other_question'];
  /* sphere gradients: highlight to the upper left, class colour, darker rim; their stop colours are CSS tokens */
  TD.SPHERES = ['work', 'record', 'chapter', 'section', 'article', 'clause', 'point', 'term', 'question', 'answer', 'area'];

  function n1(x) { return String(Math.round(x * 10) / 10); }
  function esc(s) {
    return String(s == null ? '' : s).normalize('NFC').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  TD.esc = esc;
  /* cubic Bezier with vertical tangents at both ends (scripts/site/trace_layout.py curve()) */
  TD.curve = function (x1, y1, x2, y2) {
    if (y1 > y2) { var t = x1; x1 = x2; x2 = t; t = y1; y1 = y2; y2 = t; }
    var k = 0.45 * (y2 - y1);
    return 'M' + n1(x1) + ' ' + n1(y1) + 'C' + n1(x1) + ' ' + n1(y1 + k) + ' ' + n1(x2) + ' ' + n1(y2 - k) + ' ' + n1(x2) + ' ' + n1(y2);
  };

  TD.defs = function () {
    var g = TD.SPHERES.map(function (c) {
      return '<radialGradient id="trg-' + c + '" cx=".36" cy=".32" r=".74" fx=".33" fy=".28">' +
        '<stop offset="0" class="tgs-hi tgs-' + c + '"/><stop offset=".58" class="tgs-mid tgs-' + c + '"/>' +
        '<stop offset="1" class="tgs-rim tgs-' + c + '"/></radialGradient>';
    }).join('');
    return '<defs>' + g +
      '<radialGradient id="trg-oq" cx=".4" cy=".36" r=".7"><stop offset="0" class="tgs-hi tgs-question"/>' +
      '<stop offset="1" class="tgs-mid tgs-question"/></radialGradient>' +
      '<radialGradient id="trg-shadow"><stop offset="0" class="tgs-shadow"/><stop offset=".55" class="tgs-shadow-mid"/>' +
      '<stop offset="1" class="tgs-shadow-0"/></radialGradient></defs>';
  };

  /* trace = one entry of window.VLONTO["traces_<area>"].traces (geometry in trace.g); view = 'card' | 'wide' | 'tall' */
  function mode(opts) { return (opts && opts.lang) || (VL.lang ? VL.lang() : 'envi'); }
  /* the lines of a call-out [text, isEnglish, x, y] in a mode: EN or VI keeps that language's lines (or all of them
     when the call-out has no line in it) and moves them so their middle sits where the middle of all lines was */
  TD.lines = function (lines, m) {
    if (m !== 'en' && m !== 'vi') return lines;
    var want = m === 'en' ? 1 : 0, keep = lines.filter(function (ln) { return (ln[1] ? 1 : 0) === want; });
    if (!keep.length || keep.length === lines.length) return lines;
    function mid(ls) { return ls.reduce(function (s, ln) { return s + ln[3]; }, 0) / ls.length; }
    var dy = mid(lines) - mid(keep);
    return keep.map(function (ln) { return [ln[0], 0, ln[2], Math.round((ln[3] + dy) * 10) / 10, ln[1] ? 'en' : 'vi']; });
  };
  TD.svg = function (tr, view, opts) {
    opts = opts || {};
    var M0 = mode(opts);
    var G = tr.g, V = G.views[view], A = V.t[0], TX = V.t[1], TY = V.t[2], id = opts.id || 'tr';
    var NN = V.n || G.nodes, SH = V.s || G.shadows, ORD = V.o || G.order, LO = V.lo;
    var X = [], Y = [], R = [], BG = [];
    NN.forEach(function (n) { X.push(A * n[0] + TX); Y.push(A * n[1] + TY); R.push(A * n[2]); BG.push(n[4] ? 1 : 0); });
    var o = [];
    o.push('<svg xmlns="http://www.w3.org/2000/svg" class="tr-fig trv-' + view + '" viewBox="0 0 ' + V.w + ' ' + V.h + '"' +
      ' role="img" aria-labelledby="' + id + '-t ' + id + '-d" focusable="false" data-view="' + view + '">');
    o.push('<title id="' + id + '-t">' + esc(opts.title || '') + '</title><desc id="' + id + '-d">' + esc(opts.desc || '') + '</desc>');
    o.push('<g class="tr-shadows">');
    SH.forEach(function (s) {
      o.push('<ellipse cx="' + n1(A * s[0] + TX) + '" cy="' + n1(A * s[1] + TY) + '" rx="' + n1(A * s[2]) + '" ry="' + n1(A * s[3]) +
        '" opacity="' + s[4] + '"/>');
    });
    o.push('</g><g class="tr-links">');
    G.links.forEach(function (l, j) {
      o.push('<path class="tl tl-' + TD.CLASSES[l[2]] + (BG[l[0]] || BG[l[1]] ? ' bg' : '') + '" d="' +
        TD.curve(X[l[0]], Y[l[0]], X[l[1]], Y[l[1]]) + '" opacity="' + (LO ? LO[j] : l[3]) + '"/>');
    });
    o.push('</g><g class="tr-halo">');
    var core = [];
    G.trace.forEach(function (e) {
      var d = TD.curve(X[e[0]], Y[e[0]], X[e[1]], Y[e[1]]), s = e[2] === 2 ? ' s' : '';
      o.push('<path class="th2' + s + '" d="' + d + '"/><path class="th' + s + '" d="' + d + '"/>');
      core.push('<path class="tc' + s + '" d="' + d + '"/>');
    });
    o.push('</g><g class="tr-nodes">');
    ORD.forEach(function (k) {
      var n = tr.nodes[k], c = TD.CLASSES[n.c];
      o.push('<circle class="tn tn-' + c + (BG[k] ? ' bg' : '') + '" cx="' + n1(X[k]) + '" cy="' + n1(Y[k]) + '" r="' + n1(R[k]) +
        '" opacity="' + NN[k][3] + '"' +
        ' data-k="' + k + '"' + (opts.nodeTitles ? '><title>' + esc(TD.nodeTitle(n)) + '</title></circle>' : '/>'));
    });
    o.push('</g><g class="tr-core">' + core.join('') + '</g><g class="tr-callouts">');
    V.c.forEach(function (c) {
      var b = c.b, k = c.k;
      var pts = [];
      for (var i = 0; i + 1 < k.length; i += 2) pts.push(k[i] + ',' + k[i + 1]);
      o.push('<g class="tr-co" data-k="' + c.n + '"><polyline class="tr-lead" points="' + pts.join(' ') + '"/>' +
        '<rect class="tr-box" x="' + b[0] + '" y="' + b[1] + '" width="' + b[2] + '" height="' + b[3] + '"/>');
      TD.lines(c.l, M0).forEach(function (ln) {
        /* ln[4]: the language of a line kept in EN or VI (drawn in the first grey); else Vietnamese / English by ln[1] */
        var lg = ln[4] || (ln[1] ? 'en' : 'vi');
        o.push('<text class="' + (ln[1] ? 'tr-en' : 'tr-vi') + '" x="' + ln[2] + '" y="' + ln[3] + '"' + (lg === 'vi' ? ' lang="vi"' : (ln[4] ? ' lang="en"' : '')) + '>' + esc(ln[0]) + '</text>');
      });
      o.push('</g>');
    });
    o.push('</g></svg>');
    return o.join('');
  };

  /* tooltip of a node: class, label, provenance. The class names come from the dictionary (js/i18n-3d.js tdraw.cls.*)
     when the language layer is loaded; this table is the same pairs for runs without it (V8 previews) */
  TD.CLASS_LABEL = {
    work: ['Văn bản', 'Work'], record: ['Bản ghi', 'Record'], chapter: ['Chương', 'Chapter'], section: ['Mục', 'Section'],
    article: ['Điều', 'Article'], clause: ['Khoản', 'Clause'], point: ['Điểm', 'Point'], term: ['Thuật ngữ', 'Term'],
    question: ['Câu hỏi', 'Question'], answer: ['Trả lời', 'Answer'], area: ['Lĩnh vực', 'Area'],
    other_question: ['Câu hỏi khác', 'Other question']
  };
  /* class and label in the language mode (VL.T: "vi · en" in EN–VI, one language in EN or VI); without js/i18n.js the
     pairs of v1 */
  TD.nodeTitle = function (n) {
    var c = TD.CLASSES[n.c], cl = TD.CLASS_LABEL[c], p = n.p || [];
    var both = function (vi, en) { return vi === en || !en ? vi : (!vi ? en : vi + ' · ' + en); };
    var T = VL.T && VL.pair ? function (vi, en) { return VL.T(VL.pair(vi, en)); } : both;
    var k = 'tdraw.cls.' + c, cls = VL.T && VL.i18n && VL.i18n.has(k) ? VL.T(k) : T(cl[0], cl[1]);
    return cls + ': ' + T(n.vi, n.en) + (p.length ? ' (' + p.filter(Boolean).join(' · ') + ')' : '');
  };
})(typeof window !== 'undefined' ? window : this);

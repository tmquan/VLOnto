/* VLOnto question traces - SVG drawing of one trace (classic script, no DOM access: the same code runs in the page and
   in the offline preview, scripts/site/trace_preview.py).

   The geometry is computed at build time by scripts/site/trace_layout.py: projected node positions (graph units), links,
   traced segments, floor shadows and, per view (card = the paper's Fig. 6 panel; wide / tall = the focus view in the
   manner of Fig. 1), a transform [a, tx, ty] and the call-outs (box, text lines, leader line). Colours are not in the
   markup: CSS classes and custom properties (css/site.css, "question traces") give the paper's class palette and the
   traced path (navy core over a pale-gold halo; light core on the dark theme), so a theme switch needs no redraw.

   VL.TraceDraw.svg(trace, view, opts) -> SVG string; opts: id (unique prefix), title, desc, nodeTitles (one <title>
   per node, focus view). VL.TraceDraw.defs() -> the shared gradients (once per page). */
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
  TD.svg = function (tr, view, opts) {
    opts = opts || {};
    var G = tr.g, V = G.views[view], A = V.t[0], TX = V.t[1], TY = V.t[2], id = opts.id || 'tr';
    var X = [], Y = [], R = [];
    G.nodes.forEach(function (n) { X.push(A * n[0] + TX); Y.push(A * n[1] + TY); R.push(A * n[2]); });
    var o = [];
    o.push('<svg xmlns="http://www.w3.org/2000/svg" class="tr-fig trv-' + view + '" viewBox="0 0 ' + V.w + ' ' + V.h + '"' +
      ' role="img" aria-labelledby="' + id + '-t ' + id + '-d" focusable="false" data-view="' + view + '">');
    o.push('<title id="' + id + '-t">' + esc(opts.title || '') + '</title><desc id="' + id + '-d">' + esc(opts.desc || '') + '</desc>');
    o.push('<g class="tr-shadows">');
    G.shadows.forEach(function (s) {
      o.push('<ellipse cx="' + n1(A * s[0] + TX) + '" cy="' + n1(A * s[1] + TY) + '" rx="' + n1(A * s[2]) + '" ry="' + n1(A * s[3]) +
        '" opacity="' + s[4] + '"/>');
    });
    o.push('</g><g class="tr-links">');
    G.links.forEach(function (l) {
      o.push('<path class="tl tl-' + TD.CLASSES[l[2]] + '" d="' + TD.curve(X[l[0]], Y[l[0]], X[l[1]], Y[l[1]]) + '" opacity="' + l[3] + '"/>');
    });
    o.push('</g><g class="tr-halo">');
    var core = [];
    G.trace.forEach(function (e) {
      var d = TD.curve(X[e[0]], Y[e[0]], X[e[1]], Y[e[1]]), s = e[2] === 2 ? ' s' : '';
      o.push('<path class="th2' + s + '" d="' + d + '"/><path class="th' + s + '" d="' + d + '"/>');
      core.push('<path class="tc' + s + '" d="' + d + '"/>');
    });
    o.push('</g><g class="tr-nodes">');
    G.order.forEach(function (k) {
      var n = tr.nodes[k], c = TD.CLASSES[n.c];
      o.push('<circle class="tn tn-' + c + '" cx="' + n1(X[k]) + '" cy="' + n1(Y[k]) + '" r="' + n1(R[k]) + '" opacity="' + G.nodes[k][3] + '"' +
        ' data-k="' + k + '"' + (opts.nodeTitles ? '><title>' + esc(TD.nodeTitle(n)) + '</title></circle>' : '/>'));
    });
    o.push('</g><g class="tr-core">' + core.join('') + '</g><g class="tr-callouts">');
    V.c.forEach(function (c) {
      var b = c.b, k = c.k;
      var pts = [];
      for (var i = 0; i + 1 < k.length; i += 2) pts.push(k[i] + ',' + k[i + 1]);
      o.push('<g class="tr-co" data-k="' + c.n + '"><polyline class="tr-lead" points="' + pts.join(' ') + '"/>' +
        '<rect class="tr-box" x="' + b[0] + '" y="' + b[1] + '" width="' + b[2] + '" height="' + b[3] + '"/>');
      c.l.forEach(function (ln) {
        o.push('<text class="' + (ln[1] ? 'tr-en' : 'tr-vi') + '" x="' + ln[2] + '" y="' + ln[3] + '"' + (ln[1] ? '' : ' lang="vi"') + '>' + esc(ln[0]) + '</text>');
      });
      o.push('</g>');
    });
    o.push('</g></svg>');
    return o.join('');
  };

  /* tooltip of a node: class (VI · EN), label (VI · EN), provenance */
  TD.CLASS_LABEL = {
    work: ['Văn bản', 'Work'], record: ['Bản ghi', 'Record'], chapter: ['Chương', 'Chapter'], section: ['Mục', 'Section'],
    article: ['Điều', 'Article'], clause: ['Khoản', 'Clause'], point: ['Điểm', 'Point'], term: ['Thuật ngữ', 'Term'],
    question: ['Câu hỏi', 'Question'], answer: ['Trả lời', 'Answer'], area: ['Lĩnh vực', 'Area'],
    other_question: ['Câu hỏi khác', 'Other question']
  };
  TD.nodeTitle = function (n) {
    var c = TD.CLASSES[n.c], cl = TD.CLASS_LABEL[c], p = n.p || [];
    var lab = n.vi === n.en ? n.vi : n.vi + ' · ' + n.en;
    return cl[0] + ' · ' + cl[1] + ': ' + lab + (p.length ? ' (' + p.filter(Boolean).join(' · ') + ')' : '');
  };
})(typeof window !== 'undefined' ? window : this);

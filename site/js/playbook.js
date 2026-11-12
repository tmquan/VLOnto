/* VLOnto - playbook page. Renders window.VLONTO.playbook_html (data/playbook_html.js, written by the Playbook track)
   with the site styles and a generated table of contents. The data script is loaded only when data/site_files.js
   lists it, so the page never requests a missing file; otherwise a "not built yet" placeholder is shown. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'playbook';
  var body = VL.$('#pb-body'), actions = VL.$('#pb-actions');

  function sizeOf(f) { return f.bytes > 1048576 ? (Math.round(f.bytes / 104857.6) / 10) + ' MB' : Math.max(1, Math.round(f.bytes / 1024)) + ' KB'; }
  function renderActions() {
    var pdf = VL.fileListed('downloads/VLOnto-playbook.pdf'), md = VL.fileListed('downloads/playbook.md'), h = '';
    if (pdf) h += '<a class="btn btn-primary" href="downloads/VLOnto-playbook.pdf" download>' + VL.ICON.download + '<span>PDF · ' + sizeOf(pdf) + '</span></a>';
    if (md) h += '<a class="btn" href="downloads/playbook.md" download>' + VL.ICON.download + '<span>Markdown · ' + sizeOf(md) + '</span></a>';
    actions.innerHTML = h;
    M.playbookPdf = !!pdf;
  }
  function slug(s, used) {
    var b = VL.fold(s).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'section';
    var k = b, n = 2;
    while (used[k]) k = b + '-' + (n++);
    used[k] = 1;
    return k;
  }
  /* Break opportunities (<wbr>) after / _ . - = & ? # : , inside long tokens (paths, URLs, identifiers) outside <pre>,
     so they wrap at natural points on phones instead of overflowing or breaking between two letters. */
  function softBreaks(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), nodes = [], n;
    while ((n = walker.nextNode())) {
      if (/\S{24,}/.test(n.data) && !(n.parentElement && n.parentElement.closest('pre'))) nodes.push(n);
    }
    nodes.forEach(function (t) {
      var frag = document.createDocumentFragment();
      t.data.split(/(\S{24,})/).forEach(function (part, i) {
        if (!part) return;
        if (i % 2 === 0) { frag.appendChild(document.createTextNode(part)); return; }
        var pieces = part.replace(/([\/_.\-=&?#:,])/g, '$1\u0001').split('\u0001');
        pieces.forEach(function (q, j) {
          if (!q) return;
          frag.appendChild(document.createTextNode(q));
          if (j < pieces.length - 1) frag.appendChild(document.createElement('wbr'));
        });
      });
      t.parentNode.replaceChild(frag, t);
    });
    return nodes.length;
  }
  function render(pb) {
    var html = typeof pb === 'string' ? pb : (pb && (pb.html || pb.body)) || '';
    var wrap = VL.el('div', { 'class': 'playbook-layout' });
    var toc = VL.el('nav', { 'class': 'toc', 'aria-label': 'Contents' });
    var art = VL.el('article', { 'class': 'prose', lang: 'en' });
    art.innerHTML = VL.nfc(html);
    VL.$$('script, style', art).forEach(function (e) { e.remove(); });
    var first = art.querySelector('h1');
    if (first && /playbook/i.test(first.textContent)) first.remove();
    var used = {}, items = [];
    VL.$$('h2, h3', art).forEach(function (h) {
      if (!h.id) h.id = slug(h.textContent, used); else used[h.id] = 1;
      items.push('<li class="l' + h.tagName.slice(1) + '"><a href="#' + h.id + '">' + VL.esc(h.textContent) + '</a></li>');
    });
    VL.$$('a[href^="http"]', art).forEach(function (a) { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener'); });
    /* numbers with units and ISO dates stay on one line ("172.1 MB", "2021-01-01"); wide tables scroll in their frame */
    var NUMERIC = /^(?:[~<>≈]\s?)?[0-9][0-9.,\u00a0\u202f ]*(?:\s?(?:%|[kKMGT]i?B|B|kB|bytes|ms|s|min|h|fps|px|×))?$|^\d{4}-\d{2}-\d{2}$/;
    VL.$$('td, th', art).forEach(function (cell) {
      var t = cell.textContent.trim();
      if (t && t.length <= 24 && NUMERIC.test(t)) cell.classList.add('nw');
    });
    VL.$$('table', art).forEach(function (t) {
      if (t.parentElement && t.parentElement.classList.contains('table-wrap')) return;
      var w = VL.el('div', { 'class': 'table-wrap', style: 'margin:0 0 16px' });
      t.parentNode.insertBefore(w, t);
      w.appendChild(t);
    });
    /* collapsed on phones (98 entries would push the text far down), open on wide screens */
    var narrow = window.matchMedia('(max-width: 900px)').matches;
    toc.innerHTML = '<details' + (narrow ? '' : ' open') + '><summary>Contents · ' + items.length + ' sections</summary><ol>' + items.join('') + '</ol></details>';
    var softened = softBreaks(art) + softBreaks(toc);
    wrap.appendChild(toc);
    wrap.appendChild(art);
    body.innerHTML = '';
    body.appendChild(wrap);
    M.playbook = { present: true, headings: items.length, chars: art.textContent.length, softBreakNodes: softened };
    if (location.hash.length > 1) { var t = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (t) t.scrollIntoView(); }
  }
  function placeholder() {
    body.innerHTML = '<div class="card placeholder"><h2>The playbook has not been built yet</h2>' +
      '<p>This page shows the playbook once <span class="mono">data/playbook_html.js</span> exists in the site. It is written by the playbook build ' +
      '(Markdown → HTML for this page, Markdown → Typst → PDF for <span class="mono">downloads/VLOnto-playbook.pdf</span>); re-run ' +
      '<span class="mono">scripts/site/build_site.py</span> afterwards so the site lists the new files.</p>' +
      '<p style="margin-bottom:0">Meanwhile, the <a href="ontology.html">ontology documentation</a>, the <a href="dashboard.html">dashboard</a> and the ' +
      '<a href="downloads.html">downloads</a> describe what VLOnto contains.</p></div>';
    M.playbook = { present: false };
  }
  renderActions();
  var listed = VL.fileListed('data/playbook_html.js');
  var p = listed ? VL.loadScript('data/playbook_html.js').then(function () {
    var pb = window.VLONTO.playbook_html;
    if (pb) render(pb); else placeholder();
  }, function () { placeholder(); }) : Promise.resolve(placeholder());
  p.then(function () { return VL.fontsReady(); }).then(function () { VL.setReady(); });
})();

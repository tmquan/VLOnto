/* VLOnto - static text of the scene pages (index.html, traces.html) that needs more than the declarative data-i18n
   attributes of js/i18n.js: sentences with markup inside (a <kbd>, links, the paper's title), the bilingual notes of the
   traces page and the canvas' aria-roledescription. Content-pages track (docs/i18n.md); the scenes themselves (3D
   labels, legends, panels, lists, tabs) belong to js/ontology3d.js and js/traces3d.js. Loaded after those scripts and
   rebuilt in place on 'vl:lang'. Elements marked data-vl-text stay hidden while the page loads (css/site.css,
   content-pages section) until their text is in, so no wrong language flashes; at DOMContentLoaded they show anyway. */
(function () {
  'use strict';
  var VL = window.VL;
  if (!VL || !VL.i18n || !VL.esc) return;
  var esc = VL.esc, M = window.__VLONTO_METRICS = window.__VLONTO_METRICS || {};
  function langAttr(l) { return l && l !== VL.i18n.htmlLang() ? ' lang="' + l + '"' : ''; }
  function set(id, html) {
    var el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = html;
    el.setAttribute('data-vl-text', 'ok');
  }
  /* the four notes of the traces page: one language in EN and VI; in EN–VI the Vietnamese, then the English below it */
  var NOTES = ['traces.note.graph', 'traces.note.layout', 'traces.note.trace', 'traces.note.sources'];
  function render() {
    var traces = document.body.classList.contains('page-traces'), canvas = document.getElementById('canvas-host');
    if (!traces) {
      set('play-hint-desk', VL.UH('play.hint.desk', null, { html: { key: '<kbd>/</kbd>' } }));
      /* classes the paper names, as the playground draws them: Văn bản · Work, Điều · Article, Thuật ngữ · Term */
      var ex = ['work', 'article', 'term'].map(function (k) { var c = VL.PAPER_CLASS[k]; return VL.TH(VL.pair(c.vi, c.en)); }).join(', ');
      set('play-about', VL.UH('play.about.text', null, { html: { examples: ex,
        link: '<a href="ontology.html">' + esc(VL.U('play.ontologyPage')) + '</a>' } }));
      if (canvas) canvas.setAttribute('aria-roledescription', VL.U('play.canvas.role'));
    } else {
      VL.$$('#tr-notes li[data-note]').forEach(function (li) {
        var k = li.getAttribute('data-note');
        if (NOTES.indexOf(k) >= 0 && VL.i18n.has(k)) li.innerHTML = VL.TH(k, null, { sep: ' ' });
      });
      /* the paper's title stays English in every mode */
      set('tr-paper', VL.UH('traces.paper', null, { html: {
        title: '<a href="' + esc(VL.PAPER.url) + '" target="_blank" rel="noopener" data-paper-link="side"' + langAttr('en') + '>' + esc(VL.PAPER.title) + '</a>',
        release: '<span data-vl-release>' + esc(VL.releaseLabel()) + '</span>' } }));
      if (canvas) canvas.setAttribute('aria-roledescription', VL.U('traces.canvas.role'));
    }
    M.sceneTextLang = VL.lang();
  }
  render();
  document.addEventListener('vl:lang', function () { render(); M.sceneTextRenders = (M.sceneTextRenders || 0) + 1; });
})();

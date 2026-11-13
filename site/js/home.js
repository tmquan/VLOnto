/* VLOnto - about page (about.html): headline numbers (data/stats.js), tool cards, sources, modules, citation and
   attribution. Texts come from js/i18n-pages.js (about.*) in the language mode (docs/i18n.md): one language in EN and VI,
   pairs "Tiếng Việt · English" for content in EN–VI. Everything built here is rebuilt in place on 'vl:lang'. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'index';
  var S = window.VLONTO.stats || {}, OG = window.VLONTO.ontology_graph || { nodes: [], links: [] };
  var esc = VL.esc;
  function $(sel) { return VL.$(sel); }
  /* lang="…" where a text is not in the page language (html[lang]: 'vi' in VI, 'en' in EN and EN–VI) */
  function langAttr(l) { return l && l !== VL.i18n.htmlLang() ? ' lang="' + l + '"' : ''; }
  /* a key-figure card: the label in the mode's language; in EN–VI the Vietnamese label with the English gloss below */
  function kpi(v, key) {
    var l = VL.TL(key);
    return '<div class="kpi"><div class="v">' + v + '</div><div class="k"' + langAttr(l.primaryLang) + '>' + esc(l.primary) + '</div>' +
      (l.secondary ? '<div class="k-gloss"' + langAttr(l.secondaryLang) + '>' + esc(l.secondary) + '</div>' : '') + '</div>';
  }
  /* a pair of data labels as one string (VL.T) or, for a class name, the mode's label with the other as tooltip */
  function chip(n) {
    var vi = VL.lang() === 'vi', text = vi ? (n.label_vi || n.label_en) : n.label_en;
    var l = vi && n.label_vi ? 'vi' : 'en', tip = VL.lang() === 'envi' && n.label_vi ? ' title="' + esc(n.label_vi) + '"' : '';
    return '<a class="term-chip" href="index.html#class=' + encodeURIComponent(n.id) + '"' + langAttr(l) + tip + '>' + esc(text) + '</a>';
  }
  /* the definition of a module: the dictionary's (ontp.modDef.<id>, Vietnamese in VI) while its English is the data's */
  function moduleDef(id, en) {
    var e = VL.i18n.get('ontp.modDef.' + id);
    if (e && en && e.en === VL.nfc(en)) return { t: VL.U('ontp.modDef.' + id), l: VL.lang() === 'vi' ? 'vi' : 'en' };
    return { t: en || '', l: 'en' };
  }

  var TOOLS = [
    ['index.html', 'cube', 'index', true], ['network-3d.html', 'network', 'network'], ['sparql.html', 'code', 'sparql'],
    ['traces.html', 'trace', 'traces'], ['dashboard.html', 'chart', 'dashboard'], ['ontology.html', 'docs', 'ontology'],
    ['playbook.html', 'book', 'playbook'], ['downloads.html', 'download', 'downloads']
  ];
  var SRC = [['thuvienphapluat-vn-vbpl', 'vbpl'], ['thuvienphapluat-vn-hdpl', 'hdpl'], ['thuvienphapluat-vn-tnpl', 'tnpl'], ['thuvienphapluat-vn-htpl', 'htpl']];
  var classes = {}, defs = {};
  OG.nodes.forEach(function (n) { if (n.kind === 'class') (classes[n.module] = classes[n.module] || []).push(n); });
  (OG.modules || []).forEach(function (m) { defs[m.id] = m.definition_en; });

  function render() {
    $('#kpis').innerHTML = [
      kpi(VL.fmt(S.documents), 'about.kpi.documents'), kpi(VL.fmt(S.articles), 'about.kpi.articles'),
      kpi(VL.fmt(S.change_events), 'about.kpi.changes'), kpi(VL.fmt(S.legal_basis_links), 'about.kpi.basis'),
      kpi(VL.fmt(S.citation_links), 'about.kpi.citations'), kpi(VL.fmt(S.legal_questions), 'about.kpi.qa'),
      kpi(VL.fmt(S.legal_terms), 'about.kpi.terms'), kpi(VL.fmt(S.rdf_triples), 'about.kpi.triples')
    ].join('');
    $('#numbers-note').textContent = VL.U('about.numbersNote', { release: VL.releaseLabel(), date: S.build_date || '', asof: S.validity_as_of || '',
      n: VL.fmt(S.issuing_bodies), m: VL.fmt(S.legal_areas) });

    var vars = { network: { n: VL.fmt(S.documents) }, sparql: { n: VL.fmt(S.core_ttl_triples) } };
    $('#tools').innerHTML = TOOLS.map(function (t) {
      return '<a class="card tool-card' + (t[3] ? ' featured' : '') + '" href="' + t[0] + '"><span class="icon">' + VL.ICON[t[1]] + '</span>' +
        '<h3>' + VL.UH('about.tool.' + t[2]) + '</h3><p>' + VL.UH('about.tool.' + t[2] + '.text', vars[t[2]] || null) + '</p>' +
        '<span class="go">' + VL.UH('about.open') + '</span></a>';
    }).join('');

    $('#sources-text').innerHTML = VL.UH('about.sources.text', null, { html: { link: '<a href="traces.html">' + esc(VL.U('chrome.nav.traces')) + '</a>' } });
    var lic = S.sources || {};
    $('#sources').innerHTML = SRC.map(function (s) {
      var info = lic[s[0]] || {}, l = info.licence || '';
      return '<tr><td><a class="nowrap" href="https://huggingface.co/datasets/tmquan/' + s[0] + '" target="_blank" rel="noopener">' + esc(s[0]) + '</a>' +
        '<div class="sub mono">' + VL.UH('about.rev', { rev: (info.revision || '').slice(0, 10) }) + '</div></td><td>' + VL.UH('about.src.' + s[1]) + '</td>' +
        '<td class="col-opt nowrap">' + (l === 'other' ? VL.UH('about.sourceTerms') : esc(l.toUpperCase())) + '</td></tr>';
    }).join('');

    /* module cards: the module's name in the mode's language (EN–VI: Vietnamese with the English gloss below) */
    var envi = VL.lang() === 'envi';
    $('#modules').innerHTML = VL.MODULES.filter(function (m) { return m.id !== 'external'; }).map(function (m) {
      var cs = (classes[m.id] || []).slice(0, 6).map(chip).join(''), d = moduleDef(m.id, defs[m.id]);
      var hl = VL.lang() === 'en' ? 'en' : 'vi';
      return '<div class="card module-card"><div class="mod-head"><span class="swatch" style="background:' + m.v + '"></span>' +
        '<h3' + langAttr(hl) + '>' + esc(hl === 'en' ? m.en : m.vi) + '</h3></div>' +
        (envi ? '<p class="gloss"' + langAttr('en') + '>' + esc(m.en) + '</p>' : '') + '<p' + langAttr(d.l) + '>' + esc(d.t) + '</p>' +
        (cs ? '<div class="terms">' + cs + '</div>' : '') + '</div>';
    }).join('');

    $('#cite-lead').innerHTML = VL.UH('about.cite.lead', null, { html: {
      bib: '<a href="#paper">' + esc(VL.U('about.cite.bibAbove')) + '</a>', release: '<span data-vl-release>' + esc(VL.releaseLabel()) + '</span>' } });
    $('#cite-text').innerHTML = VL.UH('about.cite.textLine', null, { html: {
      title: '<em lang="en">VLOnto: Vietnamese Legal Ontology and Knowledge Graph</em>',
      version: '<span id="cite-version" data-vl-version>' + esc(VL.VERSION) + '</span>',
      code: '<a href="https://github.com/tmquan/VLOnto" target="_blank" rel="noopener">github.com/tmquan/VLOnto</a>',
      site: '<a href="https://tmquan.github.io/VLOnto/" target="_blank" rel="noopener">tmquan.github.io/VLOnto</a>' } });

    $('#lic-onto').innerHTML = VL.UH('about.lic.onto', null, { html: { ttl: '<code>vlonto.ttl</code>',
      cc: '<a href="https://creativecommons.org/licenses/by/4.0/" rel="license noopener" target="_blank">CC BY 4.0</a>' } });
    $('#lic-kg').innerHTML = VL.UH('about.lic.kg', null, { html: { a: '<code>hdpl</code>', b: '<code>tnpl</code>', c: '<code>htpl</code>' } });
    $('#lic-sw').innerHTML = VL.UH('about.lic.sw', null, { html: { link: '<a href="downloads.html#dl-vendor">' + esc(VL.U('about.downloadsPage')) + '</a>' } });

    var asof = S.validity_as_of || '2026-11-08', unk = S.validity && S.validity.unknown != null ? VL.fmt(S.validity.unknown) : '–';
    $('#disc-text').innerHTML = '<strong>' + VL.UH('about.disc.strong') + '</strong> ' +
      VL.UH('about.disc.text', null, { html: { date: '<span id="asof">' + esc(asof) + '</span>', n: '<span id="unknown-n">' + unk + '</span>' } });
    ['sources-text', 'cite-lead', 'cite-text', 'lic-onto', 'lic-kg', 'lic-sw', 'disc-text'].forEach(function (id) { $('#' + id).setAttribute('data-vl-text', 'ok'); });
    M.aboutLang = VL.lang();
  }
  render();
  $('#attr-en').textContent = VL.attribution('en');
  $('#attr-vi').textContent = VL.attribution('vi');
  $('#copy-bib').addEventListener('click', function () { VL.copy(VL.$('#bibtex').textContent, VL.$('#bibtex')); });
  /* the language switch: rebuild the texts in place (scroll position and focus stay where they are) */
  document.addEventListener('vl:lang', function () { render(); M.aboutLangRenders = (M.aboutLangRenders || 0) + 1; });

  VL.fontsReady().then(function () { VL.setReady(); });
})();

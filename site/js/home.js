/* VLOnto - home page: headline numbers (data/stats.js), tool cards, sources, modules, citation and attribution. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'index';
  var S = window.VLONTO.stats || {}, OG = window.VLONTO.ontology_graph || { nodes: [], links: [] };

  function kpi(v, k, vi) { return '<div class="kpi"><div class="v">' + v + '</div><div class="k">' + VL.esc(k) + '</div><div class="vi" lang="vi">' + VL.esc(vi) + '</div></div>'; }
  VL.$('#kpis').innerHTML = [
    kpi(VL.fmt(S.documents), 'legal documents', 'văn bản quy phạm pháp luật'),
    kpi(VL.fmt(S.articles), 'articles', 'điều'),
    kpi(VL.fmt(S.change_events), 'change events', 'thay thế, sửa đổi, bãi bỏ'),
    kpi(VL.fmt(S.legal_basis_links), 'legal-basis links', 'căn cứ pháp lý'),
    kpi(VL.fmt(S.citation_links), 'citation links', 'trích dẫn'),
    kpi(VL.fmt(S.legal_questions), 'legal Q&As', 'hỏi đáp pháp luật'),
    kpi(VL.fmt(S.legal_terms), 'legal terms', 'thuật ngữ pháp lý'),
    kpi(VL.fmt(S.rdf_triples), 'RDF triples', 'bộ ba RDF')
  ].join('');
  VL.$('#numbers-note').textContent = VL.releaseLabel() + ' (this release), built ' + (S.build_date || '') + '. Validity of documents derived as of ' +
    (S.validity_as_of || '') + '. ' + VL.fmt(S.issuing_bodies) + ' issuing bodies and ' + VL.fmt(S.legal_areas) + ' legal areas.';
  VL.$('#asof').textContent = S.validity_as_of || '2026-11-08';
  if (S.validity && S.validity.unknown != null) VL.$('#unknown-n').textContent = VL.fmt(S.validity.unknown);

  var tools = [
    ['index.html', 'cube', '3D ontology playground', 'Classes, properties, concept schemes and external alignments in an interactive 3D scene, with search, module filters and SPARQL CONSTRUCT results drawn in 3D.', true],
    ['network-3d.html', 'network', '3D legal network', 'All ' + VL.fmt(S.documents) + ' documents layered by legal force, with replacement, amendment, legal-basis and citation links and a validity panel.'],
    ['sparql.html', 'code', 'SPARQL playground', 'Ten bilingual example queries and a free editor over the core subset (' + VL.fmt(S.core_ttl_triples) + ' triples), running offline in WebAssembly.'],
    ['traces.html', 'trace', 'Question traces', 'For each of 27 legal areas, the 20 articles its answers cite most, each with one published question traced from the answer up to the law, all in one 3D graph drawn like the figures of the paper.'],
    ['dashboard.html', 'chart', 'Dashboard', 'Documents by type, year, issuer and area, validity, change relations, most-cited documents and articles, Q&As, terms and news.'],
    ['ontology.html', 'docs', 'Ontology documentation', 'Modules, alignments and the full pyLODE reference of every class and property, with Turtle, SHACL and JSON-LD downloads.'],
    ['playbook.html', 'book', 'Playbook', 'How VLOnto is built and how to use it: sources and licences, the ontology design, the pipeline, validation and the website.'],
    ['downloads.html', 'download', 'Downloads', 'Ontology, RDF core subset, site data, documentation and checksums, and how to rebuild the full graph from the four source datasets.']
  ];
  VL.$('#tools').innerHTML = tools.map(function (t) {
    return '<a class="card tool-card' + (t[4] ? ' featured' : '') + '" href="' + t[0] + '"><span class="icon">' + VL.ICON[t[1]] + '</span>' +
      '<h3>' + VL.esc(t[2]) + '</h3><p>' + VL.esc(t[3]) + '</p><span class="go">Open →</span></a>';
  }).join('');

  var SRC = [
    ['thuvienphapluat-vn-vbpl', 'Legal documents: identity, type, number, dates, issuer, area, status, structure, change, legal-basis and citation links (thuvienphapluat.vn).'],
    ['thuvienphapluat-vn-hdpl', 'Legal Q&As: identifiers, URLs, dates, areas and the documents and articles they cite (no question or answer text; the Traces page shows the titles of the questions it traces).'],
    ['thuvienphapluat-vn-tnpl', 'Legal terminology: term names in Vietnamese and English (machine-translated), areas, status and related terms (no definitions).'],
    ['thuvienphapluat-vn-htpl', 'Legal news: identifiers, URLs, categories, dates and the documents they mention (no titles or text).']
  ];
  var lic = S.sources || {};
  VL.$('#sources').innerHTML = SRC.map(function (s) {
    var l = (lic[s[0]] || {}).licence || '';
    return '<tr><td><a class="nowrap" href="https://huggingface.co/datasets/tmquan/' + s[0] + '" target="_blank" rel="noopener">' + VL.esc(s[0]) + '</a>' +
      '<div class="sub mono">rev ' + VL.esc(((lic[s[0]] || {}).revision || '').slice(0, 10)) + '</div></td><td>' + VL.esc(s[1]) + '</td>' +
      '<td class="col-opt nowrap">' + VL.esc(l === 'other' ? 'source terms' : l.toUpperCase()) + '</td></tr>';
  }).join('');

  var classes = {};
  OG.nodes.forEach(function (n) { if (n.kind === 'class') (classes[n.module] = classes[n.module] || []).push(n); });
  var defs = {};
  (OG.modules || []).forEach(function (m) { defs[m.id] = m.definition_en; });
  VL.$('#modules').innerHTML = VL.MODULES.filter(function (m) { return m.id !== 'external'; }).map(function (m) {
    var cs = (classes[m.id] || []).slice(0, 6).map(function (n) {
      return '<a class="term-chip" href="index.html#class=' + encodeURIComponent(n.id) + '">' + VL.esc(n.label_en) + '</a>';
    }).join('');
    return '<div class="card module-card"><div class="mod-head"><span class="swatch" style="background:' + m.v + '"></span><h3>' + VL.esc(m.en) + '</h3></div>' +
      '<p class="vi" lang="vi">' + VL.esc(m.vi) + '</p><p>' + VL.esc(defs[m.id] || '') + '</p>' + (cs ? '<div class="terms">' + cs + '</div>' : '') + '</div>';
  }).join('');

  VL.$('#attr-en').textContent = VL.attribution('en');
  VL.$('#attr-vi').textContent = VL.attribution('vi');
  VL.$('#copy-bib').addEventListener('click', function () { VL.copy(VL.$('#bibtex').textContent, VL.$('#bibtex')); });

  VL.fontsReady().then(function () { VL.setReady(); });
})();

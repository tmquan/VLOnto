/* VLOnto website - shared runtime (classic script; works from file:// and http://). Needs js/i18n.js (loaded in <head>).
   Header/nav and footer injection (texts from js/i18n.js: one language per mode, the EN · VI · EN–VI switch next to the
   theme toggle), the module palette used by every view and legend, labels of the validity and
   change-kind concepts (from vlonto.ttl), formatting, an accessible search combobox, lazy <script> loading,
   downloads (Blob URLs) and the page-ready flag used by tests (window.__VLONTO_READY / __VLONTO_METRICS). */
(function () {
  'use strict';
  var VL = window.VL = window.VL || {};
  window.VLONTO = window.VLONTO || {};
  var M = window.__VLONTO_METRICS = window.__VLONTO_METRICS || {};
  M.protocol = location.protocol;
  M.t0 = Math.round(performance.now());
  window.__VLONTO_READY = false;

  /* The release. VL.VERSION is the machine-readable version (stats.version of the v1 build); the site names the release
     only through VL.releaseLabel() ('VLOnto v1' for every 1.x.y). Static pages carry <span data-vl-release> and
     <span data-vl-version> placeholders that VL.chrome() fills in; scripts/site/build_site.py reads VL.VERSION from here. */
  VL.VERSION = '1.0.0';
  VL.releaseLabel = function () { return 'VLOnto v' + VL.VERSION.split('.')[0]; };
  /* ------------------------------------------------------------------ release scope
     The ontology defines every term, but a release's knowledge graph has data for only some of them. A term whose scope
     note says that it is populated from a later release ("Populated from VLOnto 2.0 ...", "... which are populated from
     VLOnto 2.0 ...") is left out of the views of this release (3D playground, its query overlay, the CONSTRUCT view);
     the ontology page and its pyLODE reference keep it, with that note. release: major version (default: this site's). */
  VL.laterRelease = function (note, release) {
    var m = /populated from VLOnto (\d+)/i.exec(String(note || ''));
    var r = release != null ? release : +VL.VERSION.split('.')[0];
    return m && +m[1] > r ? +m[1] : 0;
  };
  /* the ontology graph (data/ontology_graph.js) as this release shows it: without the terms of a later release, the links
     that touch them and external terms left without any link; modules whose terms all come later, with their release */
  VL.releaseScope = function (g) {
    var rel = +((/(\d+)/.exec(String(g.release || g.version || VL.VERSION)) || [0, 1])[1]);
    var hidden = {}, from = {}, linked = {}, deg = {}, gone = [];
    g.nodes.forEach(function (n) { var r = VL.laterRelease(n.scope_note_en, rel); if (r) { hidden[n.id] = true; from[n.id] = r; } });
    var links = g.links.filter(function (l) {
      linked[l.source] = linked[l.target] = true;
      if (hidden[l.source] || hidden[l.target] || VL.laterRelease(l.scope_note_en, rel)) { gone.push(l); return false; }
      deg[l.source] = (deg[l.source] || 0) + 1;
      deg[l.target] = (deg[l.target] || 0) + 1;
      return true;
    });
    g.nodes.forEach(function (n) { if (!hidden[n.id] && n.kind === 'external' && linked[n.id] && !deg[n.id]) hidden[n.id] = true; });
    var nodes = g.nodes.filter(function (n) { return !hidden[n.id]; }), kept = {}, later = {}, attrs = 0;
    nodes.forEach(function (n) { kept[n.module] = true; });
    /* datatype properties of a later release on the classes that stay (a copy of the node; the data stays as it is) */
    nodes = nodes.map(function (n) {
      var at = n.attributes || [], keep = at.filter(function (a) { return !VL.laterRelease(a.scope_note_en, rel); });
      if (keep.length === at.length) return n;
      var o = {};
      Object.keys(n).forEach(function (k) { o[k] = n[k]; });
      o.attributes = keep;
      attrs += at.length - keep.length;
      return o;
    });
    g.nodes.forEach(function (n) { if (from[n.id] && !kept[n.module]) later[n.module] = Math.min(later[n.module] || 99, from[n.id]); });
    return { release: rel, nodes: nodes, links: links, laterModules: later,
      hidden: g.nodes.filter(function (n) { return hidden[n.id]; }).map(function (n) { return n.id; }),
      hiddenProperties: gone.filter(function (l) { return l.type === 'property'; }).map(function (l) { return l.id; }), hiddenLinks: gone.length,
      hiddenAttributes: attrs };
  };
  /* the same scope in a SPARQL store (js/sparql-core.js context): the IRIs of the terms of a later release (scope note),
     of the resources typed by them and of the concepts of their schemes; cached on the context */
  VL.laterReleaseIris = function (ctx) {
    if (ctx.__later) return ctx.__later;
    var out = {}, terms = [], P = 'PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n';
    var r = VL.Sparql.run(ctx, P + 'SELECT ?t ?n WHERE { ?t skos:scopeNote ?n }');
    (r.rows || []).forEach(function (b) {
      if (b.t && b.t.type === 'uri' && !out[b.t.value] && VL.laterRelease(b.n && b.n.value)) { out[b.t.value] = true; terms.push(b.t.value); }
    });
    if (terms.length) {
      var r2 = VL.Sparql.run(ctx, P + 'SELECT DISTINCT ?x WHERE { VALUES ?h { ' + terms.map(function (t) { return '<' + t + '>'; }).join(' ') +
        ' } { ?x a ?h } UNION { ?x skos:inScheme ?h } UNION { ?x skos:topConceptOf ?h } }');
      (r2.rows || []).forEach(function (b) { if (b.x && b.x.type === 'uri') out[b.x.value] = true; });
    }
    ctx.__later = out;
    return out;
  };
  /* CONSTRUCT quads without those that name a term of a later release (subject, predicate or object) */
  VL.scopeQuads = function (ctx, quads) {
    var L = VL.laterReleaseIris(ctx), kept = [];
    function named(t) { return t && t.termType === 'NamedNode' && L[t.value]; }
    quads.forEach(function (q) { if (!named(q.subject) && !named(q.predicate) && !named(q.object)) kept.push(q); });
    return { quads: kept, hidden: quads.length - kept.length };
  };
  /* "Tư pháp (tòa án) · Judiciary: from v2" (envi), "Judiciary: from v2" (en), "Tư pháp (tòa án): từ v2" (vi) for each
     module of a later release (release scope above) */
  VL.laterModulesNote = function (later) {
    return VL.MODULES.filter(function (m) { return later[m.id]; }).map(function (m) {
      return VL.TH(VL.pair(VL.cap(m.vi) + (m.scope_vi ? ' (' + m.scope_vi + ')' : ''), VL.cap(m.en))) + ': ' +
        VL.esc(VL.U('common.fromRelease', { n: later[m.id] }));
    }).join('<br>');
  };
  VL.NS = {
    vlo: 'https://tmquan.github.io/VLOnto/ontology#',
    id: 'https://tmquan.github.io/VLOnto/id/'
  };
  VL.PREFIXES = [
    ['vlo', 'https://tmquan.github.io/VLOnto/ontology#'],
    ['doc', 'https://tmquan.github.io/VLOnto/id/document/'],
    ['vlid', 'https://tmquan.github.io/VLOnto/id/'],
    ['eli', 'http://data.europa.eu/eli/ontology#'],
    ['skos', 'http://www.w3.org/2004/02/skos/core#'],
    ['prov', 'http://www.w3.org/ns/prov#'],
    ['schema', 'https://schema.org/'],
    ['org', 'http://www.w3.org/ns/org#'],
    ['dcterms', 'http://purl.org/dc/terms/'],
    ['rdfs', 'http://www.w3.org/2000/01/rdf-schema#'],
    ['rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'],
    ['owl', 'http://www.w3.org/2002/07/owl#'],
    ['xsd', 'http://www.w3.org/2001/XMLSchema#'],
    ['vann', 'http://purl.org/vocab/vann/']
  ];

  /* index.html is the 3D ontology playground (the landing page); about.html is the overview; ontology-3d.html redirects;
     key = the navigation label in js/i18n.js, one language per mode ('Traces' in en and envi, 'Truy vết' in vi; in envi
     the Vietnamese is the link's tooltip); label = the English, for scripts and tests */
  VL.PAGES = [
    { href: 'index.html', label: '3D Ontology', key: 'chrome.nav.index' },
    { href: 'network-3d.html', label: '3D Legal Network', key: 'chrome.nav.network' },
    { href: 'sparql.html', label: 'SPARQL', key: 'chrome.nav.sparql' },
    { href: 'traces.html', label: 'Traces', key: 'chrome.nav.traces' },
    { href: 'dashboard.html', label: 'Dashboard', key: 'chrome.nav.dashboard' },
    { href: 'ontology.html', label: 'Ontology docs', key: 'chrome.nav.ontology' },
    { href: 'playbook.html', label: 'Playbook', key: 'chrome.nav.playbook' },
    { href: 'downloads.html', label: 'Downloads', key: 'chrome.nav.downloads' },
    { href: 'about.html', label: 'About', key: 'chrome.nav.about' }
  ];

  /* One module palette for every view, legend and chart (11 VLOnto modules + aligned external terms). */
  VL.MODULES = [
    { id: 'documents', en: 'documents', vi: 'văn bản', color: '#4F8EF7' },
    { id: 'provisions', en: 'provisions', vi: 'điều khoản', color: '#2EC4B6' },
    { id: 'validity-change', en: 'validity and change', vi: 'hiệu lực và thay đổi', color: '#FF8A3D' },
    { id: 'citation-basis', en: 'citation and legal basis', vi: 'trích dẫn và căn cứ', color: '#FFC83D' },
    { id: 'agents', en: 'agents', vi: 'chủ thể', color: '#A78BFA' },
    { id: 'judiciary', en: 'judiciary', vi: 'tư pháp', scope_vi: 'tòa án', color: '#F472B6' },
    { id: 'qa', en: 'legal Q&A', vi: 'hỏi đáp pháp luật', color: '#4ADE80' },
    { id: 'terminology', en: 'terminology', vi: 'thuật ngữ', color: '#B5E853' },
    { id: 'news', en: 'news', vi: 'tin tức', color: '#F87171' },
    { id: 'classification', en: 'classification', vi: 'phân loại', color: '#C9935F' },
    { id: 'provenance', en: 'provenance', vi: 'nguồn gốc', color: '#94A3B8' },
    { id: 'external', en: 'aligned external terms', vi: 'khái niệm ngoài được liên kết', color: '#DCE3EF' }
  ];
  VL.MODULE = {};
  VL.MODULES.forEach(function (m) { VL.MODULE[m.id] = m; m.v = 'var(--mod-' + m.id + ')'; });
  /* .color = resolved colour of the current theme (WebGL, canvas, ECharts); .v = CSS variable (DOM swatches switch live) */
  VL.moduleColor = function (id) { return (VL.MODULE[id] || VL.MODULE.provenance).color; };
  VL.moduleVar = function (id) { return (VL.MODULE[id] || VL.MODULE.provenance).v; };

  /* ValidityStatus and ChangeKind concepts (skos:prefLabel en/vi from vlonto.ttl); activeVi / passiveVi = the rdfs:label
     @vi of the change properties (vlo:replaces 'thay thế', vlo:replacedBy 'được thay thế bởi', ...). */
  VL.VALIDITY = {
    in_force: { en: 'in force', vi: 'còn hiệu lực', color: '#22C55E', inForce: true },
    in_force_amended: { en: 'in force, amended', vi: 'còn hiệu lực, đã được sửa đổi', color: '#A3E635', inForce: true },
    presumed_in_force_amended: { en: 'presumed in force, amended', vi: 'được cho là còn hiệu lực, đã được sửa đổi', color: '#2DD4BF', inForce: true },
    superseded: { en: 'superseded', vi: 'đã bị thay thế hoặc bãi bỏ', color: '#F97316', inForce: false },
    expired: { en: 'no longer in force', vi: 'hết hiệu lực', color: '#EF4444', inForce: false },
    not_yet_effective: { en: 'not yet in force', vi: 'chưa có hiệu lực', color: '#60A5FA', inForce: null },
    not_applicable: { en: 'no longer applicable', vi: 'không còn phù hợp', color: '#C084FC', inForce: false },
    unknown: { en: 'unknown', vi: 'chưa xác định', color: '#7C8BA8', inForce: null }
  };
  VL.VALIDITY_ORDER = ['in_force', 'in_force_amended', 'presumed_in_force_amended', 'not_yet_effective', 'superseded', 'expired', 'not_applicable', 'unknown'];
  VL.CHANGE = {
    replaced: { en: 'replaced', vi: 'thay thế', color: '#FF8A3D', active: 'replaces', passive: 'replaced by', activeVi: 'thay thế', passiveVi: 'được thay thế bởi' },
    amended: { en: 'amended', vi: 'sửa đổi, bổ sung', color: '#FACC15', active: 'amends', passive: 'amended by', activeVi: 'sửa đổi, bổ sung', passiveVi: 'được sửa đổi, bổ sung bởi' },
    repealed: { en: 'repealed', vi: 'bãi bỏ', color: '#EF4444', active: 'repeals', passive: 'repealed by', activeVi: 'bãi bỏ', passiveVi: 'bị bãi bỏ bởi' },
    partially_repealed: { en: 'partially repealed', vi: 'bãi bỏ một phần', color: '#FB7185', active: 'partially repeals', passive: 'partially repealed by', activeVi: 'bãi bỏ một phần', passiveVi: 'bị bãi bỏ một phần bởi' },
    partially_expired: { en: 'partially terminated', vi: 'hết hiệu lực một phần', color: '#C084FC', active: 'partially terminates', passive: 'partially terminated by', activeVi: 'làm hết hiệu lực một phần', passiveVi: 'bị làm hết hiệu lực một phần bởi' }
  };
  VL.EDGE = {
    basis: { en: 'legal basis', vi: 'căn cứ pháp lý', color: '#5B9BFF' },
    citation: { en: 'citation', vi: 'trích dẫn', qual: 'document pairs', qualVi: 'cặp văn bản', color: '#9AA8C7' }
  };
  VL.TYPE_COLORS = { HP: '#FFD166', BL: '#FF8A3D', L: '#EF476F', PL: '#F472B6', NQ: '#A78BFA', NQLT: '#8B7CF6', 'NĐ': '#4F8EF7', 'QĐ': '#22D3EE', TT: '#4ADE80', TTLT: '#B5E853' };

  /* The classes of the paper's figure legend (arXiv:2611.11426, Fig. 1), in its order and with its colours (css/site.css
     --cls-*; the same in both themes). The 3D views (paper style, js/paper3d.js) colour a node with its paper class where
     it has one, else with its module. Instances (records of the knowledge graph) of the document classes are records. */
  VL.PAPER_FONT = '"Libertinus Sans", "Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif';
  VL.PAPER_CLASSES = [
    { key: 'work', vi: 'Văn bản', en: 'Work', color: '#7dbe8e' },
    { key: 'record', vi: 'Bản ghi', en: 'Record', color: '#a3d3ae' },
    { key: 'chapter', vi: 'Chương', en: 'Chapter', color: '#6fb7b4' },
    { key: 'section', vi: 'Mục', en: 'Section', color: '#86c4bf' },
    { key: 'article', vi: 'Điều', en: 'Article', color: '#9ed2c9' },
    { key: 'clause', vi: 'Khoản', en: 'Clause', color: '#bde2d9' },
    { key: 'point', vi: 'Điểm', en: 'Point', color: '#d9efe9' },
    { key: 'term', vi: 'Thuật ngữ', en: 'Term', color: '#8db8e8' },
    { key: 'question', vi: 'Câu hỏi', en: 'Question', color: '#f4b183' },
    { key: 'answer', vi: 'Trả lời', en: 'Answer', color: '#f8d49b' },
    { key: 'intent', vi: 'Ý định', en: 'Intent', color: '#b9a3e3' },
    { key: 'area', vi: 'Lĩnh vực', en: 'Area', color: '#b9b9ce' }
  ];
  VL.PAPER_CLASS = {};
  VL.PAPER_CLASSES.forEach(function (c) { VL.PAPER_CLASS[c.key] = c; c.v = 'var(--cls-' + c.key + ')'; });
  var PAPER_OF = { Chapter: 'chapter', Section: 'section', Article: 'article', Clause: 'clause', Point: 'point', LegalTerm: 'term',
    LegalQuestion: 'question', LegalAnswer: 'answer', LegalArea: 'area' };
  ['LegalDocument', 'NormativeLegalDocument', 'Constitution', 'Code', 'Law', 'Ordinance', 'Resolution', 'JointResolution', 'Decree',
    'Decision', 'Circular', 'JointCircular'].forEach(function (w) { PAPER_OF[w] = 'work'; });
  /* paper class key of an ontology class (CURIE, IRI or local name), or null; instance = a record of the knowledge graph */
  VL.paperClassKey = function (cls, instance) {
    var k = PAPER_OF[String(cls || '').split(/[#:\/]/).pop()] || null;
    return k === 'work' && instance ? 'record' : k;
  };
  VL.cap = function (s) { s = VL.nfc(s); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; };
  /* document-type codes as ASCII custom-property names (--type-ND, --type-QD) */
  var TYPE_KEY = { HP: 'HP', BL: 'BL', L: 'L', PL: 'PL', NQ: 'NQ', NQLT: 'NQLT', 'NĐ': 'ND', 'QĐ': 'QD', TT: 'TT', TTLT: 'TTLT' };
  Object.keys(VL.VALIDITY).forEach(function (k) { VL.VALIDITY[k].v = 'var(--val-' + k + ')'; });
  Object.keys(VL.CHANGE).forEach(function (k) { VL.CHANGE[k].v = 'var(--chg-' + k + ')'; });
  Object.keys(VL.EDGE).forEach(function (k) { VL.EDGE[k].v = 'var(--edge-' + k + ')'; });
  VL.typeVar = function (code) { return TYPE_KEY[code] ? 'var(--type-' + TYPE_KEY[code] + ')' : 'var(--hue-slate)'; };

  /* The paper. Cite it by title, authors, arXiv link and BibTeX only: its graph numbers come from a different build,
     every number on this site is computed from this release (VL.releaseLabel()). */
  VL.PAPER = {
    title: 'Vietnamese Legal Ontology: Every legal answer, traced to the article that grounds it',
    authors: 'Khac-Hoai Nam Bui, Quan Tran Minh',
    short: 'Bui & Tran Minh (2026)',
    arxiv: '2611.11426',
    url: 'https://arxiv.org/abs/2611.11426',
    bibtex: '@misc{bui2026vietnamese,\n' +
      '  title         = {Vietnamese Legal Ontology: Every legal answer, traced to the article that grounds it},\n' +
      '  author        = {Bui, Khac-Hoai Nam and Tran Minh, Quan},\n' +
      '  year          = {2026},\n' +
      '  eprint        = {2611.11426},\n' +
      '  archivePrefix = {arXiv},\n' +
      '  primaryClass  = {cs.CL},\n' +
      '  url           = {https://arxiv.org/abs/2611.11426}\n' +
      '}',
    note: 'The approach is described in the paper above; numbers here are computed from the ' + VL.releaseLabel() + ' release and can differ from the paper\u2019s.'
  };

  /* ------------------------------------------------------------------ text helpers */
  VL.nfc = function (s) { return (s == null) ? '' : String(s).normalize('NFC'); };
  VL.esc = function (s) {
    return VL.nfc(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  };
  /* HTML for an IRI/URL that may wrap only after / # ? & = . _ - (never inside a word). */
  VL.wbr = function (s) {
    return VL.esc(s).replace(/(&amp;|[\/#?=._-])/g, '$1<wbr>');
  };
  var NF = new Intl.NumberFormat('en-US');
  VL.fmt = function (n) { return (n == null || n === '' || isNaN(n)) ? '–' : NF.format(n); };
  VL.compact = function (n) {
    if (n == null) return '–';
    if (n >= 1e6) return (Math.round(n / 1e5) / 10) + 'M';
    if (n >= 1e4) return Math.round(n / 1e3) + 'k';
    return NF.format(n);
  };
  VL.fold = function (s) {
    return VL.nfc(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
  };
  VL.short = function (s, n) {
    s = VL.nfc(s);
    if (s.length <= n) return s;
    var cut = s.slice(0, n);
    var sp = cut.lastIndexOf(' ');
    if (sp > n * 0.6) cut = cut.slice(0, sp);
    return cut.replace(/[\s,;:.\-–]+$/, '') + '…';
  };
  VL.shortIri = function (iri) {
    if (!iri) return '';
    for (var i = 0; i < VL.PREFIXES.length; i++) {
      var p = VL.PREFIXES[i];
      if (iri.indexOf(p[1]) === 0 && iri.length > p[1].length) return p[0] + ':' + iri.slice(p[1].length);
    }
    return iri;
  };
  VL.expandIri = function (curie) {
    var m = /^([a-z]+):(.*)$/.exec(curie || '');
    if (!m) return curie;
    for (var i = 0; i < VL.PREFIXES.length; i++) if (VL.PREFIXES[i][0] === m[1]) return VL.PREFIXES[i][1] + m[2];
    return curie;
  };
  VL.docIdFromIri = function (iri) {
    var m = /\/id\/document\/([^\/#]+)$/.exec(iri || '');
    return m ? m[1] : null;
  };
  VL.params = function () {
    var out = {};
    (location.hash || '').replace(/^#/, '').split('&').forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf('=');
      var k = decodeURIComponent(i < 0 ? kv : kv.slice(0, i));
      out[k] = i < 0 ? '' : decodeURIComponent(kv.slice(i + 1).replace(/\+/g, ' '));
    });
    return out;
  };
  VL.isMobile = function () { return window.matchMedia('(max-width: 760px)').matches; };
  VL.store = {
    get: function (k) { try { return window.localStorage.getItem('vlonto.' + k); } catch (e) { return null; } },
    set: function (k, v) { try { window.localStorage.setItem('vlonto.' + k, v); return true; } catch (e) { return false; /* storage blocked */ } }
  };

  /* ------------------------------------------------------------------ theme (light / dark)
     The inline <head> script picked the theme before first paint: ?theme=light|dark, else the stored choice
     (localStorage 'vlonto.theme'), else prefers-color-scheme. Here: the header toggle, live switching
     (data-theme on <html>, palettes re-read from the CSS custom properties, a 'vlonto-theme' event for the views),
     following the system setting while nothing was chosen, and keeping a chosen theme across pages where storage
     does not reach: under file:// (Firefox and Safari keep file storage per file) or with storage blocked, internal
     links carry ?theme=. Embedded documents (the pyLODE iframe) follow through postMessage. */
  var ROOT = document.documentElement;
  var themeFromUrl = (/[?&]theme=(light|dark)(?:&|$)/.exec(location.search) || [])[1] || null;
  var storageOK = (function () { try { var k = 'vlonto.__probe'; localStorage.setItem(k, '1'); localStorage.removeItem(k); return true; } catch (e) { return false; } })();
  function systemTheme() { try { return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; } catch (e) { return 'light'; } }
  function storedTheme() { var t = VL.store.get('theme'); return t === 'light' || t === 'dark' ? t : null; }
  var themeChosen = !!(themeFromUrl || storedTheme());
  if (ROOT.getAttribute('data-theme') !== 'light' && ROOT.getAttribute('data-theme') !== 'dark') {
    ROOT.setAttribute('data-theme', themeFromUrl || storedTheme() || systemTheme());   // inline head script missing
  }
  VL.theme = function () { return ROOT.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; };
  /* a custom property of the current theme; el = a scoped element (data-style="paper" on the CONSTRUCT view) */
  VL.tok = function (name, el) { return getComputedStyle(el || ROOT).getPropertyValue(name).trim(); };
  VL.tokNum = function (name, fb) { var v = parseFloat(VL.tok(name)); return isNaN(v) ? fb : v; };
  VL.hue = function (name) { return VL.tok('--hue-' + name) || '#888888'; };
  VL.alpha = function (color, a) {
    var c = String(color).trim(), m = /^#([0-9a-f]{6})$/i.exec(c);
    if (!m) { m = /^#([0-9a-f]{3})$/i.exec(c); if (m) m = [0, m[1].replace(/(.)/g, '$1$1')]; }
    if (!m) return c;
    var n = parseInt(m[1], 16);
    return 'rgba(' + (n >> 16) + ', ' + ((n >> 8) & 255) + ', ' + (n & 255) + ', ' + a + ')';
  };
  VL.areaColors = function () { var out = []; for (var i = 0; i < 12; i++) out.push(VL.tok('--area-' + i)); return out; };
  VL.refreshPalette = function () {
    var cs = getComputedStyle(ROOT);
    function t(n, fb) { var v = cs.getPropertyValue(n).trim(); return v || fb; }
    VL.MODULES.forEach(function (m) { m.color = t('--mod-' + m.id, m.color); });
    Object.keys(VL.VALIDITY).forEach(function (k) { VL.VALIDITY[k].color = t('--val-' + k, VL.VALIDITY[k].color); });
    Object.keys(VL.CHANGE).forEach(function (k) { VL.CHANGE[k].color = t('--chg-' + k, VL.CHANGE[k].color); });
    Object.keys(VL.EDGE).forEach(function (k) { VL.EDGE[k].color = t('--edge-' + k, VL.EDGE[k].color); });
    Object.keys(VL.TYPE_COLORS).forEach(function (k) { VL.TYPE_COLORS[k] = t('--type-' + TYPE_KEY[k], VL.TYPE_COLORS[k]); });
    M.palette = { theme: VL.theme(), documents: VL.MODULE.documents.color, in_force: VL.VALIDITY.in_force.color };
  };
  function carryTheme() { return !!themeFromUrl || (themeChosen && (location.protocol === 'file:' || !storageOK)); }
  /* add or replace theme=<t> in a URL's query, keeping its #hash */
  VL.withTheme = function (href, t) {
    var hash = '', i = href.indexOf('#');
    if (i >= 0) { hash = href.slice(i); href = href.slice(0, i); }
    var q = '', j = href.indexOf('?');
    if (j >= 0) { q = href.slice(j + 1); href = href.slice(0, j); }
    var parts = q ? q.split('&').filter(function (p) { return p && p.indexOf('theme=') !== 0; }) : [];
    parts.push('theme=' + t);
    return href + '?' + parts.join('&') + hash;
  };
  /* href for an internal page (scripts that navigate use this so the theme and the language travel like they do on
     links; js/i18n.js carries ?lang= on clicked links) */
  VL.href = function (h) {
    if (carryTheme()) h = VL.withTheme(h, VL.theme());
    if (VL.carryLang && VL.carryLang()) h = VL.withLang(h, VL.lang());
    return h;
  };
  var themeButtons = [];
  /* aria-label 'Dark theme' with aria-pressed (one language; English in envi), tooltip = the action (VL.T: the pair in
     envi, as the button shows no text) */
  function syncThemeButtons() {
    var dark = VL.theme() === 'dark';
    themeButtons.forEach(function (b) {
      b.setAttribute('aria-pressed', dark ? 'true' : 'false');
      b.setAttribute('aria-label', VL.U('chrome.theme.dark'));
      b.setAttribute('title', VL.T(dark ? 'chrome.theme.toLight' : 'chrome.theme.toDark'));
    });
  }
  function postTheme(win, t) {
    try { if (win) { win.postMessage({ type: 'vlonto-theme', theme: t }, '*'); M.themePosts = (M.themePosts || 0) + 1; } } catch (e) { /* cross-origin frame */ }
  }
  /* opts.store: remember the choice (toggle); opts.fromFrame: the change came from an embedded document */
  VL.setTheme = function (t, opts) {
    opts = opts || {};
    if (t !== 'light' && t !== 'dark') return;
    var changed = t !== VL.theme();
    ROOT.setAttribute('data-theme', t);
    ROOT.style.colorScheme = t;
    if (opts.store) {
      themeChosen = true;
      M.themeStored = VL.store.set('theme', t);
      if (themeFromUrl) {
        themeFromUrl = t;
        try { history.replaceState(history.state, '', VL.withTheme(location.href, t)); } catch (e) { /* file:// may refuse */ }
      }
    }
    VL.refreshPalette();
    syncThemeButtons();
    M.theme = t;
    VL.$$('iframe').forEach(function (f) { if (!opts.fromFrame) postTheme(f.contentWindow, t); });
    if (changed) {
      M.themeChanges = (M.themeChanges || 0) + 1;
      var ev;
      try { ev = new CustomEvent('vlonto-theme', { detail: { theme: t } }); } catch (e) { ev = document.createEvent('CustomEvent'); ev.initCustomEvent('vlonto-theme', false, false, { theme: t }); }
      window.dispatchEvent(ev);
    }
  };
  VL.toggleTheme = function () { VL.setTheme(VL.theme() === 'dark' ? 'light' : 'dark', { store: true }); };
  VL.themeButton = function () {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'vl-theme-btn';
    b.innerHTML = '<svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/>' +
      '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>' +
      '<svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M20.2 14.6A8.3 8.3 0 0 1 9.4 3.8a8.3 8.3 0 1 0 10.8 10.8z"/></svg>';
    b.addEventListener('click', VL.toggleTheme);
    themeButtons.push(b);
    syncThemeButtons();
    return b;
  };
  (function () {
    try {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var onSystem = function (e) { if (!themeChosen) VL.setTheme(e.matches ? 'dark' : 'light'); };
      if (mq.addEventListener) mq.addEventListener('change', onSystem); else if (mq.addListener) mq.addListener(onSystem);
    } catch (e) { /* no matchMedia */ }
    window.addEventListener('storage', function (e) {
      if (e.key === 'vlonto.theme' && (e.newValue === 'light' || e.newValue === 'dark')) { themeChosen = true; VL.setTheme(e.newValue); }
    });
    window.addEventListener('message', function (e) {
      var d = e.data;
      if (!d || (d.type !== 'vlonto-theme' && d.type !== 'vlonto-theme-request')) return;
      var fromChild = VL.$$('iframe').some(function (f) { return f.contentWindow === e.source; });
      if (!fromChild) return;
      /* an embedded document whose listener is now in place asks for the theme: a change made while it was still
         loading (before its script ran) would otherwise wait for its load event */
      if (d.type === 'vlonto-theme-request') { M.themeRequests = (M.themeRequests || 0) + 1; postTheme(e.source, VL.theme()); return; }
      if ((d.theme === 'light' || d.theme === 'dark') && d.theme !== VL.theme()) VL.setTheme(d.theme, { store: true, fromFrame: true });
    });
    /* internal links carry the theme where storage does not (see above) */
    document.addEventListener('click', function (e) {
      if (!carryTheme()) return;
      var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
      if (!a || a.hasAttribute('download')) return;
      var h = a.getAttribute('href');
      if (!h || /^(?:[a-z][a-z0-9+.\-]*:|\/\/|#)/i.test(h) || !/\.html(?:[?#]|$)/i.test(h)) return;
      a.setAttribute('href', VL.withTheme(h, VL.theme()));
    }, true);
  })();
  M.theme = VL.theme();
  M.themeSource = themeFromUrl ? 'url' : (storedTheme() ? 'storage' : 'system');
  M.storageOK = storageOK;
  VL.refreshPalette();

  /* ------------------------------------------------------------------ DOM helpers */
  VL.$ = function (sel, root) { return (root || document).querySelector(sel); };
  VL.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  VL.el = function (tag, attrs, html) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (attrs[k] == null || attrs[k] === false) return;
      if (k === 'class') e.className = attrs[k];
      else if (k === 'text') e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k] === true ? '' : attrs[k]);
    });
    if (html != null) e.innerHTML = html;
    return e;
  };
  VL.ICON = {
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" class="icon"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>',
    reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>',
    camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
    filter: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16l-6 8v6l-4-2v-4z"/></svg>',
    code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
    external: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 5h5v5M19 5l-8 8M18 14v5H5V6h5"/></svg>',
    cube: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/></svg>',
    network: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><circle cx="12" cy="10" r="1.6"/><path d="M6.8 7.2l3.8 2M17.2 7.2l-3.8 2M12 11.7v4"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 20h16M7 16v-5M12 16V7M17 16v-8"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 21H20v-3"/></svg>',
    docs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h7"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>',
    trace: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="5.5" cy="18.5" r="2.2"/><circle cx="12" cy="12" r="2.2"/><circle cx="18.5" cy="5.5" r="2.2"/><circle cx="18.5" cy="18.5" r="1.5"/><path d="M7.1 16.9l3.3-3.3M13.6 10.4l3.3-3.3M13.6 13.6l3.8 3.8"/></svg>',
    layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/></svg>'
  };
  var LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#2b55d0"/>' +
    '<g stroke="#cfdcff" stroke-width="1.6" stroke-linecap="round"><path d="M9 22L16 9.5L23 22Z" fill="none"/><path d="M16 9.5V17"/></g>' +
    '<circle cx="16" cy="9.5" r="3.3" fill="#FFD166"/><circle cx="9" cy="22" r="3" fill="#2EC4B6"/><circle cx="23" cy="22" r="3" fill="#FF8A3D"/><circle cx="16" cy="17.5" r="2.2" fill="#F472B6"/></svg>';

  /* ------------------------------------------------------------------ attribution (from docs/licence_policy.md section 4) */
  VL.meta = function () { return window.VLONTO.site_meta || {}; };
  VL.attribution = function (lang) {
    var m = VL.meta();
    var fb = 'VLOnto is derived from four datasets published on Hugging Face by TMQuan (source thuvienphapluat.vn). ' +
      'Extracted relations are produced automatically and may be wrong. ' +
      'VLOnto is not an official legal text and is not legal advice.';
    return VL.nfc(lang === 'vi' ? (m.attribution_vi || fb) : (m.attribution_en || fb));
  };

  /* ------------------------------------------------------------------ header / footer
     Built once per page by VL.chrome() and refreshed in place on 'vl:lang' (js/i18n.js), so focus stays where it is:
     brand, navigation, menu button, theme toggle and the language switch EN · VI · EN–VI (in the header next to the
     theme toggle; in the menu sheet on phones), then the footer or, on the full-screen scenes (opts.scene), the compact
     footbar. One language per mode; in envi the Vietnamese is the tooltip of the navigation links and buttons. */
  var chromeTop = null, footerEl = null, footerScene = false;
  function tipAttr(key, vars) { var t = VL.tip(key, vars); return t ? ' title="' + VL.esc(t) + '"' : ''; }
  function setTip(el, key, vars) { var t = VL.tip(key, vars); if (t) el.setAttribute('title', t); else el.removeAttribute('title'); }
  function headerText(top) {
    var nav = top.querySelector('.vl-nav');
    nav.setAttribute('aria-label', VL.U('chrome.nav.main'));
    VL.$$('a[data-nav-key]', nav).forEach(function (a) {
      var k = a.getAttribute('data-nav-key');
      a.textContent = VL.U(k);
      setTip(a, k);
    });
    var paper = nav.querySelector('a.ext');
    if (paper) {
      paper.querySelector('.vl-paper-label').textContent = VL.U('chrome.nav.paper');
      paper.querySelector('.sr-only').textContent = VL.U('chrome.nav.paperNewTab');
    }
    var brand = top.querySelector('.vl-brand');
    brand.setAttribute('aria-label', VL.U('chrome.brand.home'));
    brand.querySelector('.tag').textContent = VL.U('chrome.brand.tag');
    var mb = top.querySelector('.vl-menu-btn');
    mb.querySelector('.vl-menu-label').textContent = VL.U('chrome.menu');
    setTip(mb, 'chrome.menu');
    var lab = top.querySelector('#vl-lang-label');
    if (lab) lab.textContent = VL.U('chrome.lang.group');
  }
  function footerHtml(scene) {
    var S = window.VLONTO.stats || {}, cv = { short: VL.PAPER.short, arxiv: VL.PAPER.arxiv };
    var citeLink = '<a href="' + VL.PAPER.url + '" target="_blank" rel="noopener" data-paper-link="footer"' + tipAttr('chrome.cite', cv) + '>' +
      VL.esc(VL.U('chrome.cite', cv)) + '</a>';
    function link(href, key) { return '<a href="' + href + '"' + tipAttr(key) + '>' + VL.esc(VL.U(key)) + '</a>'; }
    if (scene) {
      return '<strong>' + VL.esc(VL.U('chrome.bar.notAdvice')) + '</strong>' +
        '<span class="grow">' + VL.esc(VL.U('chrome.bar.data')).replace(/\[(md|lg|xl):([^\]]*)\]/g, '<span class="fb-$1">$2</span>') + '</span>' +
        citeLink + link('about.html#licences', 'chrome.bar.attribution');
    }
    return '<div class="inner">' +
      '<div><h2>' + VL.esc(VL.U('chrome.foot.sources')) + '</h2><p>' + VL.esc(VL.attribution(VL.lang() === 'vi' ? 'vi' : 'en')) + '</p>' +
      '<p class="cite-line">' + citeLink + '</p></div>' +
      '<div><h2>' + VL.esc(VL.U('chrome.foot.notAdvice')) + '</h2><p class="disclaimer">' + VL.esc(VL.U('chrome.foot.disclaimer')) + '</p>' +
      '<p>' + VL.esc(VL.U('chrome.foot.validity', { date: S.validity_as_of || '2026-11-08' })) + '</p>' +
      '<p>' + VL.esc(VL.U('chrome.foot.licences')) + '</p></div>' +
      '<div class="meta">' + VL.esc(VL.releaseLabel()) + ' · ' + VL.esc(VL.U('chrome.foot.built', { date: S.build_date || '2026-11-11' })) +
      ' · ' + link('downloads.html', 'chrome.foot.downloads') + ' · ' + link('about.html#cite', 'chrome.foot.howToCite') +
      ' · ' + link('about.html#licences', 'chrome.foot.licencesLink') + '</div>' +
      '</div>';
  }
  document.addEventListener('vl:lang', function () {
    if (chromeTop) headerText(chromeTop);
    if (footerEl) footerEl.innerHTML = footerHtml(footerScene);
    syncThemeButtons();
    VL.$$('[data-vl-paper][data-filled]').forEach(function (el) { el.removeAttribute('data-filled'); });
    VL.paperBlocks(document);
    M.chromeLang = VL.lang();
  });
  VL.chrome = function (opts) {
    opts = opts || {};
    var here = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
    if (!/\.html$/.test(here)) here = 'index.html';
    var nav = VL.PAGES.map(function (p) {
      return '<a href="' + p.href + '" data-nav-key="' + p.key + '"' + (p.href === here ? ' aria-current="page"' : '') + '>' + VL.esc(p.label) + '</a>';
    }).join('') +
      '<a class="ext" href="' + VL.PAPER.url + '" target="_blank" rel="noopener" data-paper-link="nav" title="' +
      VL.esc(VL.PAPER.title) + ' (arXiv:' + VL.PAPER.arxiv + ')"><span class="vl-paper-label">Paper</span>' + VL.ICON.external +
      '<span class="sr-only"> (arXiv, opens in a new tab)</span></a>';
    var hdr = document.getElementById('vl-header');
    if (hdr) {
      hdr.outerHTML = '<header class="vl-header" id="vl-top">' +
        '<a class="vl-brand" href="index.html">' + LOGO +
        '<span><span class="name">VLOnto</span><br><span class="tag"></span></span></a>' +
        '<nav class="vl-nav" id="vl-nav">' + nav + '</nav>' +
        '<div class="vl-tools"><button class="vl-menu-btn" type="button" aria-expanded="false" aria-controls="vl-nav">' + VL.ICON.menu +
        '<span class="vl-menu-label">Menu</span></button></div></header>';
      var top = chromeTop = document.getElementById('vl-top');
      var btn = top.querySelector('.vl-menu-btn'), tools = top.querySelector('.vl-tools');
      tools.insertBefore(VL.langSwitch({ className: 'vl-lang-bar' }), btn);
      tools.insertBefore(VL.themeButton(), btn);
      /* phones: the language switch sits in the menu sheet, under the pages (css/site.css) */
      var row = VL.el('div', { 'class': 'vl-lang-row' }, '<span class="vl-lang-label" id="vl-lang-label"></span>');
      row.appendChild(VL.langSwitch({ labelledby: 'vl-lang-label', className: 'vl-lang-sheet' }));
      top.querySelector('.vl-nav').appendChild(row);
      headerText(top);
      btn.addEventListener('click', function () {
        var open = !top.classList.contains('open');
        top.classList.toggle('open', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) { var a = top.querySelector('.vl-nav a'); if (a) a.focus(); }
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && top.classList.contains('open')) { top.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); btn.focus(); }
      });
      document.addEventListener('click', function (e) {
        if (top.classList.contains('open') && !top.contains(e.target)) { top.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
      });
    }
    var ftr = document.getElementById('vl-footer');
    if (ftr) {
      footerScene = !!opts.scene;
      footerEl = document.createElement('footer');
      footerEl.className = footerScene ? 'vl-footbar' : 'vl-footer';
      footerEl.innerHTML = footerHtml(footerScene);
      ftr.parentNode.replaceChild(footerEl, ftr);
    }
    M.chromeLang = VL.lang();
    /* the release name and version wherever a page carries a placeholder */
    VL.$$('[data-vl-release]').forEach(function (e) { e.textContent = VL.releaseLabel(); });
    VL.$$('[data-vl-version]').forEach(function (e) { e.textContent = VL.VERSION; });
    VL.paperBlocks(document);
    /* embedded documents (pyLODE) follow this page's theme from their first load on */
    VL.$$('iframe').forEach(function (f) {
      f.addEventListener('load', function () { postTheme(f.contentWindow, VL.theme()); });
      postTheme(f.contentWindow, VL.theme());
    });
  };

  /* ------------------------------------------------------------------ fonts, ready flag, lazy scripts */
  VL.fontsReady = function () {
    if (VL._fonts) return VL._fonts;
    var list = ['400 16px "Be Vietnam Pro"', '500 16px "Be Vietnam Pro"', '600 16px "Be Vietnam Pro"', '700 16px "Be Vietnam Pro"', '400 13px "JetBrains Mono NL"'];
    /* the paper's figure font for the canvas labels of the 3D views (css/fonts-paper.css, linked by those pages only) */
    if (VL.$$('link[href$="fonts-paper.css"]').length) list.push('400 16px "Libertinus Sans"', '700 16px "Libertinus Sans"', 'italic 400 16px "Libertinus Sans"');
    var p = (document.fonts && document.fonts.load) ? Promise.all(list.map(function (f) { return document.fonts.load(f); })) : Promise.resolve();
    var timeout = new Promise(function (res) { setTimeout(res, 4000); });
    VL._fonts = Promise.race([p, timeout]).then(function () { M.fontsMs = Math.round(performance.now()); });
    return VL._fonts;
  };
  VL.setReady = function (extra) {
    if (extra) Object.keys(extra).forEach(function (k) { M[k] = extra[k]; });
    M.readyMs = Math.round(performance.now());
    window.__VLONTO_READY = true;
  };
  var scriptCache = {};
  VL.loadScript = function (src) {
    if (scriptCache[src]) return scriptCache[src];
    scriptCache[src] = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.async = false;
      s.onload = function () { resolve(); };
      s.onerror = function () { delete scriptCache[src]; reject(new Error('could not load ' + src)); };
      document.body.appendChild(s);
    });
    return scriptCache[src];
  };
  VL.fileListed = function (path) {
    var sf = window.VLONTO.site_files;
    if (!sf || !sf.files) return null;
    for (var i = 0; i < sf.files.length; i++) if (sf.files[i].path === path) return sf.files[i];
    return null;
  };

  /* ------------------------------------------------------------------ downloads, clipboard, toast */
  VL.downloadBlob = function (blob, name) {
    var url = URL.createObjectURL(blob);
    var a = VL.el('a', { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 1500);
  };
  VL.downloadText = function (text, name, mime) { VL.downloadBlob(new Blob([text], { type: mime || 'text/plain;charset=utf-8' }), name); };
  /* Copy text: Clipboard API, else execCommand('copy'), else select the shown text (selectEl) and say how to copy.
     Every path is caught (navigator.clipboard is missing or refuses under file:// in some browsers); M.lastCopy
     records the path for the tests: 'clipboard' | 'execCommand' | 'selected'. */
  VL.copy = function (text, selectEl) {
    var focused = document.activeElement;
    function selectShown() {
      M.lastCopy = 'selected';
      if (selectEl) {
        try {
          var r = document.createRange();
          r.selectNodeContents(selectEl);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(r);
        } catch (e) { /* no selection API */ }
        VL.toast(VL.U('common.selected'));
      } else {
        VL.toast(VL.U('common.noCopy'));
      }
    }
    function legacy() {
      var ok = false;
      try { ok = legacyCopy(text); } catch (e) { ok = false; }
      if (focused && focused.focus) { try { focused.focus(); } catch (e) { /* ignore */ } }
      if (ok) { M.lastCopy = 'execCommand'; VL.toast(VL.U('common.copied')); } else selectShown();
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(function () { M.lastCopy = 'clipboard'; VL.toast(VL.U('common.copied')); },
          function () { legacy(); }).catch(function () { selectShown(); });
      }
    } catch (e) { /* clipboard getter threw */ }
    legacy();
    return Promise.resolve();
  };
  function legacyCopy(text) {
    var ta = VL.el('textarea', { 'aria-hidden': 'true', tabindex: '-1', style: 'position:fixed;left:-9999px;top:0' });
    ta.value = text; document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  /* ------------------------------------------------------------------ the paper block
     variant 'card' (home page) or 'panel' (3D playground side panel); filled into [data-vl-paper] by VL.paperBlocks */
  var paperSeq = 0;
  VL.paperHtml = function (variant) {
    var P = VL.PAPER, id = 'bib-' + (++paperSeq), panel = variant === 'panel';
    var link = '<a class="paper-link" href="' + P.url + '" target="_blank" rel="noopener" data-paper-link="' + (panel ? 'panel' : 'card') + '">' +
      'arXiv:' + P.arxiv + VL.ICON.external + '<span class="sr-only">' + VL.esc(VL.U('common.newTab')) + '</span></a>';
    /* the paper's title stays English (lang="en") in every mode */
    var head = panel ?
      '<p class="paper-title" lang="en">' + VL.esc(P.title) + '</p>' :
      '<h3 class="paper-title" lang="en">' + VL.esc(P.title) + '</h3>';
    var about = head + '<p class="paper-meta">' + VL.esc(P.authors) + ' · 2026 · ' + link + ' (cs.CL)</p>' +
      '<p class="paper-note">' + VL.esc(VL.U('common.paper.note', { release: VL.releaseLabel() })) + '</p>';
    var cite = '<div class="cite-head">' + (panel ? '<span class="muted-small">BibTeX</span>' : '<h3>' + VL.esc(VL.U('common.paper.cite')) + '</h3>') +
      '<button class="btn btn-xs" type="button" data-copy-bib="' + id + '"' + tipAttr('common.copy') + '>' + VL.ICON.copy + VL.esc(VL.U('common.copy')) + '</button></div>' +
      '<pre class="code bibtex" id="' + id + '" tabindex="0" aria-label="' + VL.esc(VL.U('common.paper.bibAria')) + '">' + VL.esc(P.bibtex) + '</pre>';
    return panel ? '<div class="paper-box">' + about + cite + '</div>' : '<div class="paper-about">' + about + '</div><div class="paper-cite">' + cite + '</div>';
  };
  VL.paperBlocks = function (root) {
    VL.$$('[data-vl-paper]', root).forEach(function (el) {
      if (el.getAttribute('data-filled')) return;
      el.innerHTML = VL.paperHtml(el.getAttribute('data-vl-paper'));
      el.setAttribute('data-filled', '1');
    });
    VL.$$('[data-copy-bib]', root).forEach(function (b) {
      if (b.__bound) return;
      b.__bound = true;
      b.addEventListener('click', function () {
        var pre = document.getElementById(b.getAttribute('data-copy-bib'));
        VL.copy(VL.PAPER.bibtex, pre);
      });
    });
  };
  var toastEl = null, toastTimer = null;
  VL.toast = function (msg) {
    if (!toastEl) {
      toastEl = VL.el('div', { role: 'status', 'aria-live': 'polite', style: 'position:fixed;left:50%;bottom:52px;transform:translateX(-50%);z-index:200;' +
        'background:#111a30;color:#fff;border:1px solid #33416b;border-radius:9px;padding:8px 14px;font-size:13.5px;line-height:1.4;' +
        'box-shadow:0 10px 26px rgba(0,0,0,.35);max-width:calc(100vw - 32px);display:none' });
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.style.display = 'none'; }, 2200);
  };

  /* ------------------------------------------------------------------ accessible search combobox
     opts: input, list (ul), source(query) -> [{main, sub, kind, color, value}], onPick(item), max */
  VL.combobox = function (opts) {
    var input = opts.input, list = opts.list, items = [], active = -1, max = opts.max || 10;
    var lid = list.id || ('lb' + Math.random().toString(36).slice(2, 8));
    list.id = lid;
    list.setAttribute('role', 'listbox');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', lid);
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');
    function close() { list.classList.add('hidden'); input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); active = -1; }
    function render() {
      var q = input.value.trim();
      if (!q) { close(); return; }
      items = (opts.source(q) || []).slice(0, max);
      if (!items.length) {
        list.innerHTML = '<li class="empty" role="option" aria-disabled="true">' + VL.esc(VL.U('common.noMatch')) + '</li>';
      } else {
        list.innerHTML = items.map(function (it, i) {
          return '<li role="option" id="' + lid + '-' + i + '" aria-selected="false" data-i="' + i + '">' +
            (it.color ? '<span class="swatch" style="background:' + it.color + '"></span>' : '') +
            '<span><span class="s-main">' + VL.esc(it.main) + '</span>' + (it.sub ? '<br><span class="s-sub">' + VL.esc(it.sub) + '</span>' : '') + '</span>' +
            (it.kind ? '<span class="s-kind">' + VL.esc(it.kind) + '</span>' : '') + '</li>';
        }).join('');
      }
      list.classList.remove('hidden');
      input.setAttribute('aria-expanded', 'true');
      active = items.length ? 0 : -1;
      mark();
    }
    function mark() {
      VL.$$('li[role=option]', list).forEach(function (li, i) { li.setAttribute('aria-selected', i === active ? 'true' : 'false'); });
      if (active >= 0) { input.setAttribute('aria-activedescendant', lid + '-' + active); var li = document.getElementById(lid + '-' + active); if (li) li.scrollIntoView({ block: 'nearest' }); }
    }
    function pick(i) { var it = items[i]; if (!it) return; close(); if (opts.clearOnPick) input.value = ''; else input.value = it.main; opts.onPick(it); }
    input.addEventListener('input', render);
    input.addEventListener('focus', function () { if (input.value.trim()) render(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (list.classList.contains('hidden')) render(); else if (items.length) { active = (active + 1) % items.length; mark(); } }
      else if (e.key === 'ArrowUp') { e.preventDefault(); if (items.length) { active = (active - 1 + items.length) % items.length; mark(); } }
      else if (e.key === 'Enter') { e.preventDefault(); if (list.classList.contains('hidden')) render(); if (active >= 0) pick(active); }
      else if (e.key === 'Escape') { if (!list.classList.contains('hidden')) { e.stopPropagation(); close(); } }
    });
    list.addEventListener('mousedown', function (e) { e.preventDefault(); });
    list.addEventListener('click', function (e) { var li = e.target.closest('li[data-i]'); if (li) pick(+li.getAttribute('data-i')); });
    input.addEventListener('blur', function () { setTimeout(close, 120); });
    close();
    return { close: close, refresh: render, pickFirst: function () { render(); if (items.length) pick(0); } };
  };

  /* simple scorer for search: exact > prefix > word prefix > contains */
  VL.score = function (qf, hay) {
    if (!hay) return 0;
    if (hay === qf) return 100;
    if (hay.indexOf(qf) === 0) return 80;
    if ((' ' + hay).indexOf(' ' + qf) >= 0) return 60;
    if (hay.indexOf(qf) >= 0) return 40;
    return 0;
  };

  /* expose a stable test hook namespace */
  window.VLApp = window.VLApp || {};
})();

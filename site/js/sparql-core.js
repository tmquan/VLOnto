/* VLOnto website - SPARQL in the browser with the vendored Oxigraph (WebAssembly embedded in a classic script).
   Shared by sparql.html and the query mode of the 3D ontology playground (index.html). Data comes from data/vlonto_core_ttl.js and
   data/vlonto_ontology_ttl.js (window.VLONTO[...] strings), loaded on demand with <script> tags (no fetch).
   Text follows the language mode of js/i18n.js (dictionary js/i18n-3d.js, keys sqc.*): dataset names (S.dsLabel), error
   messages (S.errorText: the engine's own message stays as Oxigraph writes it) and the notes of the result tables. */
(function () {
  'use strict';
  var VL = window.VL;
  var S = VL.Sparql = {};
  var BASE_ID = 'https://tmquan.github.io/VLOnto/id/';
  var BASE_ONTO = 'https://tmquan.github.io/VLOnto/ontology';
  S.DATASETS = {
    core: { label: 'Core subset · vlonto-core.ttl', parts: [['vlonto_core_ttl', BASE_ID]] },
    ontology: { label: 'Ontology only · vlonto.ttl', parts: [['vlonto_ontology_ttl', BASE_ONTO]] },
    both: { label: 'Ontology + core subset', parts: [['vlonto_ontology_ttl', BASE_ONTO], ['vlonto_core_ttl', BASE_ID]] }
  };
  /* the name of a dataset in the language mode (label = the English, for scripts and tests) */
  S.dsLabel = function (k) { return VL.i18n && VL.i18n.has('sqc.ds.' + k) ? VL.U('sqc.ds.' + k) : (S.DATASETS[k] || {}).label; };

  /* Website-owned CONSTRUCT examples (graph results drawn in 3D). Expected triple counts on the core subset are
     checked by scripts/site/interaction_tests.py. */
  S.CONSTRUCT_EXAMPLES = [
    {
      id: 'c-land', title_en: 'Links of the 2024 Land Law', title_vi: 'Quan hệ của Luật Đất đai 2024',
      query: 'PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\n' +
        'CONSTRUCT { ?a ?p ?b }\nWHERE {\n  ?land vlo:documentNumber "31/2024/QH15" .\n' +
        '  VALUES ?p { vlo:replaces vlo:amends vlo:repeals vlo:partiallyRepeals vlo:legalBasis vlo:cites }\n' +
        '  { ?land ?p ?b . BIND(?land AS ?a) }\n  UNION\n  { ?a ?p ?land . BIND(?land AS ?b) }\n}'
    },
    {
      id: 'c-codes', title_en: 'Codes and the acts that replaced them', title_vi: 'Các bộ luật và văn bản thay thế',
      query: 'PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\n' +
        'CONSTRUCT { ?new vlo:replaces ?old }\nWHERE {\n  ?old a vlo:Code .\n  ?new vlo:replaces ?old .\n}'
    },
    {
      id: 'c-investment', title_en: 'Amendments of the 2020 Investment Law', title_vi: 'Các văn bản sửa đổi Luật Đầu tư 2020',
      query: 'PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\n' +
        'CONSTRUCT { ?by vlo:amends ?law }\nWHERE {\n  ?law vlo:documentNumber "61/2020/QH14" .\n  ?by vlo:amends ?law .\n}'
    },
    {
      id: 'c-labour', title_en: 'Labour Codes and the codes that replaced them', title_vi: 'Các Bộ luật Lao động và bộ luật thay thế',
      query: 'PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\n' +
        'CONSTRUCT { ?new vlo:replaces ?old }\nWHERE {\n  ?new vlo:replaces ?old .\n  ?old vlo:title ?t .\n' +
        '  FILTER(CONTAINS(LCASE(STR(?t)), "lao động"))\n}'
    },
    {
      id: 'c-classes', title_en: 'Class hierarchy of legal documents (ontology)', title_vi: 'Cây lớp văn bản pháp luật (bản thể)',
      query: 'PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n' +
        'CONSTRUCT { ?c rdfs:subClassOf ?super }\nWHERE {\n  ?c rdfs:subClassOf* vlo:LegalDocument .\n' +
        '  ?c rdfs:subClassOf ?super .\n  FILTER(isIRI(?super))\n}'
    }
  ];

  S.loadOxigraph = function () {
    var p = window.oxigraphReady ? Promise.resolve() : VL.loadScript('vendor/oxigraph/oxigraph.iife.min.js');
    return p.then(function () { return window.oxigraphReady; });
  };
  S.createStore = function (datasetKey) {
    var ds = S.DATASETS[datasetKey] || S.DATASETS.core;
    var t0 = performance.now();
    return S.loadOxigraph().then(function (ox) {
      return Promise.all(ds.parts.map(function (p) { return window.VLONTO[p[0]] ? null : VL.loadScript('data/' + p[0] + '.js'); }))
        .then(function () {
          var t1 = performance.now();
          var store = new ox.Store();
          /* the core Turtle contains a few decomposed (NFD) Vietnamese strings; normalise so NFC queries match */
          ds.parts.forEach(function (p) { store.load(String(window.VLONTO[p[0]]).normalize('NFC'), { format: 'text/turtle', base_iri: p[1] }); });
          return { store: store, ox: ox, dataset: datasetKey, triples: store.size, loadMs: Math.round(performance.now() - t0), parseMs: Math.round(performance.now() - t1) };
        });
    });
  };

  /* first query-form keyword outside IRIs, strings and comments */
  S.queryForm = function (q) {
    var i = 0, n = q.length;
    while (i < n) {
      var c = q[i];
      if (c === '#') { while (i < n && q[i] !== '\n') i++; continue; }
      if (c === '<') { var j = q.indexOf('>', i); if (j < 0 || /\s/.test(q.slice(i, j))) { i++; continue; } i = j + 1; continue; }
      if (c === '"' || c === "'") { var k = i + 1; while (k < n && q[k] !== c) { if (q[k] === '\\') k++; k++; } i = k + 1; continue; }
      if (/[A-Za-z]/.test(c)) {
        var m = /^[A-Za-z_][A-Za-z0-9_-]*/.exec(q.slice(i, i + 40))[0];
        var u = m.toUpperCase();
        if (u === 'SELECT' || u === 'CONSTRUCT' || u === 'ASK' || u === 'DESCRIBE') return u;
        i += m.length; continue;
      }
      i++;
    }
    return null;
  };

  /* an error as parts: line, col and the engine's own message (raw), so that S.errorText can write it in any mode;
     message = the English text (metrics, tests) */
  function niceError(e) {
    if (e && e.code === 'noForm') return { code: 'noForm', line: 1, col: 1, raw: e.message, message: 'Syntax error at line 1, column 1: ' + e.message };
    var msg = String(e && e.message ? e.message : e).replace(/^Error:\s*/, '');
    var m = /error at (\d+):(\d+):\s*(.*)$/i.exec(msg);
    if (m) return { message: 'Syntax error at line ' + m[1] + ', column ' + m[2] + ': ' + m[3], line: +m[1], col: +m[2], raw: m[3] };
    return { message: msg, raw: msg };
  }
  S.errorText = function (err) {
    if (!err) return '';
    if (!err.line || !VL.U) return err.message;
    return VL.U('sqc.syntax', { line: VL.fmt(err.line), col: VL.fmt(err.col), msg: err.code === 'noForm' ? VL.U('sqc.noForm') : err.raw });
  };

  /* run a query; returns {form, vars, rows, boolean, quads, ms, count, error} */
  S.run = function (ctx, q) {
    var form = S.queryForm(q);
    var t0 = performance.now();
    var res = { form: form || '?', ms: 0 };
    try {
      if (!form) { var nf = new Error('expected a SELECT, CONSTRUCT, ASK or DESCRIBE query'); nf.code = 'noForm'; throw nf; }
      if (form === 'SELECT') {
        var json = JSON.parse(ctx.store.query(q, { results_format: 'application/sparql-results+json' }));
        res.vars = json.head.vars || [];
        res.rows = json.results.bindings;
        res.count = res.rows.length;
      } else if (form === 'ASK') {
        res.boolean = !!ctx.store.query(q);
        res.count = 1;
      } else {
        res.quads = ctx.store.query(q);
        res.count = res.quads.length;
      }
    } catch (e) {
      res.error = niceError(e);
    }
    res.ms = Math.round((performance.now() - t0) * 10) / 10;
    return res;
  };

  function termFromQuad(t) {
    if (t.termType === 'NamedNode') return { type: 'uri', value: t.value };
    if (t.termType === 'BlankNode') return { type: 'bnode', value: t.value };
    var o = { type: 'literal', value: t.value };
    if (t.language) o['xml:lang'] = t.language;
    else if (t.datatype && t.datatype.value !== 'http://www.w3.org/2001/XMLSchema#string') o.datatype = t.datatype.value;
    return o;
  }
  S.quadRows = function (quads) {
    return quads.map(function (q) { return { s: termFromQuad(q.subject), p: termFromQuad(q.predicate), o: termFromQuad(q.object) }; });
  };
  var NUM_DT = /XMLSchema#(integer|decimal|double|float|long|int|nonNegativeInteger)$/;

  /* HTML for one term (opts.dark for the scene drawer) */
  S.termHtml = function (t) {
    if (!t) return '<span class="muted">–</span>';
    if (t.type === 'uri') {
      var doc = VL.docIdFromIri(t.value);
      var label = VL.shortIri(t.value);
      if (doc) return '<a class="iri" href="network-3d.html#doc=' + encodeURIComponent(doc) + '" title="' + VL.esc(t.value + ' ' + VL.U('sqc.openNetwork')) + '">' + VL.wbr(label) + '</a>';
      return '<span class="iri" title="' + VL.esc(t.value) + '">' + VL.wbr(label) + '</span>';
    }
    if (t.type === 'bnode') return '<span class="iri">_:' + VL.esc(t.value) + '</span>';
    var v = VL.esc(t.value);
    if (t.datatype && NUM_DT.test(t.datatype)) return v;
    if (t.datatype && /XMLSchema#(date|dateTime|anyURI|boolean)$/.test(t.datatype)) return '<span class="nowrap">' + v + '</span>';
    return v + (t['xml:lang'] ? ' <span class="lang">@' + VL.esc(t['xml:lang']) + '</span>' : '');
  };
  S.isNumeric = function (t) { return t && t.type === 'literal' && t.datatype && NUM_DT.test(t.datatype); };

  S.renderTable = function (host, res, opts) {
    opts = opts || {};
    var max = opts.max || 1000;
    var cls = opts.dark ? 'rt' : 'results';
    var vars = res.vars, rows = res.rows;
    if (res.quads) { vars = ['s', 'p', 'o']; rows = S.quadRows(res.quads); }
    if (!rows || !rows.length) { host.innerHTML = '<p class="muted">' + VL.UH('sqc.noRows') + '</p>'; return; }
    var h = '<table class="' + cls + '"><thead><tr>' + vars.map(function (v) { return '<th>?' + VL.esc(v) + '</th>'; }).join('') + '</tr></thead><tbody>';
    rows.slice(0, max).forEach(function (r) {
      h += '<tr>' + vars.map(function (v) {
        var t = r[v];
        return '<td' + (S.isNumeric(t) ? ' class="n"' : '') + '>' + S.termHtml(t) + '</td>';
      }).join('') + '</tr>';
    });
    h += '</tbody></table>';
    if (rows.length > max) h += '<p class="muted">' + VL.UH('sqc.showing', { max: VL.fmt(max), n: VL.fmt(rows.length) }) + '</p>';
    host.innerHTML = h;
  };

  S.toCSV = function (res) {
    var vars = res.vars, rows = res.rows;
    if (res.quads) { vars = ['s', 'p', 'o']; rows = S.quadRows(res.quads); }
    var q = function (s) { s = s == null ? '' : String(s); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    var out = [vars.map(q).join(',')];
    (rows || []).forEach(function (r) { out.push(vars.map(function (v) { return q(r[v] ? r[v].value : ''); }).join(',')); });
    return '\ufeff' + out.join('\r\n') + '\r\n';
  };

  /* labels and classes of IRIs (for drawing graph results): label = the English (or untagged) label, label_vi = the
     Vietnamese one (rdfs:label or skos:prefLabel @vi) where the dataset has it */
  S.describeIris = function (ctx, iris) {
    var out = {};
    iris = iris.filter(function (x) { return /^https?:/.test(x); }).slice(0, 400);
    if (!iris.length) return out;
    var values = iris.map(function (x) { return '<' + x.replace(/[<>"{}|\\^`\s]/g, '') + '>'; }).join(' ');
    var q = 'PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n' +
      'SELECT ?s ?num ?title ?label ?pref ?lvi ?pvi ?type WHERE { VALUES ?s { ' + values + ' }\n' +
      ' OPTIONAL { ?s vlo:documentNumber ?num } OPTIONAL { ?s vlo:title ?title }\n' +
      ' OPTIONAL { ?s rdfs:label ?label FILTER(LANG(?label) = "en" || LANG(?label) = "") }\n' +
      ' OPTIONAL { ?s skos:prefLabel ?pref FILTER(LANG(?pref) = "en") }\n' +
      ' OPTIONAL { ?s rdfs:label ?lvi FILTER(LANG(?lvi) = "vi") }\n OPTIONAL { ?s skos:prefLabel ?pvi FILTER(LANG(?pvi) = "vi") }\n OPTIONAL { ?s a ?type } }';
    try {
      var json = JSON.parse(ctx.store.query(q, { results_format: 'application/sparql-results+json' }));
      json.results.bindings.forEach(function (b) {
        var s = b.s.value, o = out[s] || (out[s] = { types: [] });
        if (b.num && !o.number) o.number = b.num.value;
        if (b.title && !o.title) o.title = b.title.value;
        if (b.label && !o.label) o.label = b.label.value;
        if (b.pref && !o.label) o.label = b.pref.value;
        if (b.lvi && !o.label_vi) o.label_vi = b.lvi.value;
        if (b.pvi && !o.label_vi) o.label_vi = b.pvi.value;
        if (b.type && o.types.indexOf(b.type.value) < 0) o.types.push(b.type.value);
      });
    } catch (e) { /* labels are optional */ }
    return out;
  };

  /* quads -> {nodes, links, literals} for 3d-force-graph; node ids are CURIEs/IRIs */
  S.quadsToGraph = function (ctx, quads, maxNodes) {
    maxNodes = maxNodes || 600;
    var nodes = {}, order = [], links = [], lits = {}, truncated = false;
    function key(t) { return t.termType === 'BlankNode' ? '_:' + t.value : VL.shortIri(t.value); }
    function ensure(t) {
      var k = key(t);
      if (!nodes[k]) {
        if (order.length >= maxNodes) { truncated = true; return null; }
        nodes[k] = { id: k, iri: t.termType === 'NamedNode' ? t.value : null, blank: t.termType === 'BlankNode' };
        order.push(k);
      }
      return k;
    }
    quads.forEach(function (q) {
      var s = ensure(q.subject);
      if (!s) return;
      if (q.object.termType === 'Literal') { (lits[s] = lits[s] || []).push([VL.shortIri(q.predicate.value), q.object.value, q.object.language]); return; }
      var o = ensure(q.object);
      if (!o) return;
      links.push({ source: s, target: o, pred: VL.shortIri(q.predicate.value), predIri: q.predicate.value });
    });
    var info = S.describeIris(ctx, order.map(function (k) { return nodes[k].iri; }).filter(Boolean));
    order.forEach(function (k) {
      var n = nodes[k], d = n.iri ? info[n.iri] : null;
      n.number = d && d.number; n.title = d && d.title; n.label = d && d.label; n.label_vi = d && d.label_vi; n.types = d ? d.types : [];
      (lits[k] || []).forEach(function (l) {
        if (l[0] === 'vlo:documentNumber' && !n.number) n.number = l[1];
        if (l[0] === 'vlo:title' && !n.title) n.title = l[1];
        if ((l[0] === 'rdfs:label' || l[0] === 'skos:prefLabel') && l[2] === 'vi') { if (!n.label_vi) n.label_vi = l[1]; }
        else if ((l[0] === 'rdfs:label' || l[0] === 'skos:prefLabel') && !n.label) n.label = l[1];
      });
    });
    return { nodes: order.map(function (k) { return nodes[k]; }), links: links, literals: lits, truncated: truncated };
  };
})();

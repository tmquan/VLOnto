/* VLOnto - SPARQL playground page: examples, editor, results table, CSV export, CONSTRUCT drawn in 3D, self-test.
   Text follows the language mode of js/i18n.js (docs/i18n.md; dictionary js/i18n-3d.js, keys sq.* and sqc.*): example
   titles, status lines, result titles and notes, the CONSTRUCT view's call-outs and legend, and the page's own numbers
   (VL.fmt; the full graph's size from VLONTO.stats); a mode change ('vl:lang') renders them again in place. */
(function () {
  'use strict';
  var VL = window.VL, S = VL.Sparql, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'sparql';
  var EX = ((window.VLONTO.sparql_examples || {}).queries) || [];
  var CX = S.CONSTRUCT_EXAMPLES;
  var qEl = VL.$('#query'), statusEl = VL.$('#status'), resultEl = VL.$('#result'), dsEl = VL.$('#dataset');
  var csvBtn = VL.$('#btn-csv'), titleEl = VL.$('#result-title');
  var stores = {}, last = null, current = { kind: 's', i: 0 };

  /* ------------------------------------------------------------------ examples
     Titles in the language mode: EN–VI as in v1 (the English title, the Vietnamese under it), EN or VI one language; the
     expected row count in the mode's number format. A mode change renders the list again and keeps the pressed one. */
  function exTitle(e) {
    var mode = VL.lang();
    if (mode === 'envi') return '<span class="t">' + VL.esc(e.title_en) + '</span><span class="v" lang="vi">' + VL.esc(e.title_vi) + '</span>';
    return '<span class="t">' + VL.UH(VL.pair(e.title_vi, e.title_en)) + '</span>';
  }
  function renderExamples() {
    var pressedKey = (VL.$('.ex-item[aria-pressed="true"]') || { getAttribute: function () { return null; } }).getAttribute('data-ex');
    VL.$('#ex-select').innerHTML = EX.map(function (e, i) {
      return '<button type="button" class="ex-item" data-ex="s' + i + '" aria-pressed="false">' + exTitle(e) +
        '<span class="m"><span class="badge">' + VL.UH('sq.ex.rows', { n: e.rows_on_core === 1 ? 1 : VL.fmt(e.rows_on_core) }) + '</span></span></button>';
    }).join('');
    VL.$('#ex-construct').innerHTML = CX.map(function (e, i) {
      return '<button type="button" class="ex-item" data-ex="c' + i + '" aria-pressed="false">' + exTitle(e) +
        '<span class="m"><span class="badge">CONSTRUCT · 3D</span></span></button>';
    }).join('');
    if (pressedKey) markExample(pressedKey);
  }
  function renderDatasets() {
    var keep = dsEl.value;
    dsEl.innerHTML = Object.keys(S.DATASETS).map(function (k) { return '<option value="' + k + '">' + VL.esc(S.dsLabel(k)) + '</option>'; }).join('');
    if (keep) dsEl.value = keep;
  }
  renderExamples();
  renderDatasets();
  function exampleQuery(key) { var i = +key.slice(1); return key[0] === 'c' ? CX[i].query : EX[i].query; }
  function markExample(key) {
    VL.$$('.ex-item').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-ex') === key ? 'true' : 'false'); });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.ex-item');
    if (!b) return;
    var key = b.getAttribute('data-ex');
    qEl.value = exampleQuery(key);
    markExample(key);
    current = { kind: key[0], i: +key.slice(1) };
    run();
    /* phones: the editor sits above the example list, so bring it back into view */
    if (window.matchMedia('(max-width: 960px)').matches) {
      var ed = VL.$('.editor-card');
      if (ed && ed.getBoundingClientRect().top < 0) ed.scrollIntoView({ block: 'start' });
    }
  });

  /* ------------------------------------------------------------------ store */
  function getStore(ds) {
    if (!stores[ds]) {
      setStatus(function () { return VL.U('sq.loadingDataset', { ds: S.dsLabel(ds) }); }, '');
      stores[ds] = S.createStore(ds).then(function (ctx) {
        M['store_' + ds] = { triples: ctx.triples, ms: ctx.loadMs };
        return ctx;
      }, function (e) { delete stores[ds]; throw e; });
    }
    return stores[ds];
  }
  /* the status line: msg is text or a function that writes it in the current mode, so a mode change renders the last
     status again */
  var lastStatus = null;
  function setStatus(msg, cls) {
    lastStatus = [msg, cls];
    statusEl.textContent = typeof msg === 'function' ? msg() : msg;
    statusEl.className = 'status-line' + (cls ? ' ' + cls : '');
  }
  function highlightError(err) {
    if (!err || !err.line) return;
    var lines = qEl.value.split('\n'), pos = 0;
    for (var i = 0; i < err.line - 1 && i < lines.length; i++) pos += lines[i].length + 1;
    var col = Math.max(0, (err.col || 1) - 1);
    qEl.focus();
    qEl.setSelectionRange(pos + col, Math.min(pos + (lines[err.line - 1] || '').length, pos + col + 12));
  }

  /* ------------------------------------------------------------------ run
     The result's title, status, table notes and ASK sentence are written by showResult(), which a mode change calls
     again with the same result (lastShown). */
  var lastShown = null;
  function nv(c) { return c === 1 ? 1 : VL.fmt(c); }
  function showResult(r) {
    lastShown = r;
    var res = r.res, ctx = r.ctx;
    function head() { return VL.U('sq.triplesLoaded', { n: VL.fmt(ctx.triples) }); }
    if (res.form === 'SELECT') {
      setStatus(function () { return VL.U('sq.status.rows', { n: nv(res.count), ms: VL.fmt(res.ms), head: head() }); }, 'ok');
      titleEl.textContent = VL.U('sq.title.rows', { n: nv(res.count) });
      S.renderTable(resultEl, res, { max: 1000 });
    } else if (res.form === 'ASK') {
      setStatus(function () { return VL.U('sq.status.ask', { v: res.boolean ? 'true' : 'false', ms: VL.fmt(res.ms) }); }, 'ok');
      titleEl.textContent = VL.U('sq.title.ask', { v: res.boolean ? 'true' : 'false' });
      resultEl.innerHTML = '<p style="padding:12px 14px;margin:0">' + VL.UH(res.boolean ? 'sq.ask.matches' : 'sq.ask.noMatch') + '</p>';
    } else {
      var view = r.view;
      setStatus(function () {
        var later = r.hidden ? VL.U('sq.later', { n: nv(r.hidden), v: +VL.VERSION.split('.')[0] + 1 }) : '';
        return VL.U('sq.status.construct', { n: nv(view.count), ms: VL.fmt(res.ms), head: head(), later: later });
      }, 'ok');
      titleEl.textContent = VL.U('sq.title.graph', { n: VL.fmt(view.count) });
      S.renderTable(resultEl, view, { max: 500 });
    }
  }
  function run() {
    var q = qEl.value;
    if (!q.trim()) { setStatus(function () { return VL.U('sq.empty'); }, 'err'); return Promise.resolve(null); }
    var ds = dsEl.value;
    setStatus(function () { return VL.U('sq.running'); }, '');
    return getStore(ds).then(function (ctx) {
      var res = S.run(ctx, q);
      last = res;
      M.lastQuery = { form: res.form, count: res.count, ms: res.ms, error: res.error ? res.error.message : null, dataset: ds };
      if (res.error) {
        lastShown = null;
        setStatus(function () { return S.errorText(res.error); }, 'err');
        highlightError(res.error);
        csvBtn.disabled = true;
        return res;
      }
      VL.$('#graph-wrap').classList.add('hidden');
      if (res.form === 'SELECT') {
        showResult({ res: res, ctx: ctx });
        csvBtn.disabled = !res.count;
      } else if (res.form === 'ASK') {
        showResult({ res: res, ctx: ctx });
        csvBtn.disabled = true;
      } else {
        /* release scope (js/common.js): triples that name a term populated from a later release are not shown */
        var sc = VL.scopeQuads(ctx, res.quads), view = res;
        M.lastQuery.hiddenLater = sc.hidden;
        if (sc.hidden) {
          view = {};
          Object.keys(res).forEach(function (k) { view[k] = res[k]; });
          view.quads = sc.quads;
          view.count = sc.quads.length;
          last = view;
        }
        showResult({ res: res, ctx: ctx, view: view, hidden: sc.hidden });
        csvBtn.disabled = !view.count;
        if (view.count) drawGraph(ctx, view);
      }
      return res;
    }).catch(function (e) { lastShown = null; setStatus(function () { return VL.U('sq.runError', { msg: e && e.message ? e.message : e }); }, 'err'); return null; });
  }
  VL.$('#btn-run').addEventListener('click', run);
  qEl.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      var s = qEl.selectionStart;
      qEl.value = qEl.value.slice(0, s) + '  ' + qEl.value.slice(qEl.selectionEnd);
      qEl.selectionStart = qEl.selectionEnd = s + 2;
    }
  });
  dsEl.addEventListener('change', function () { run(); });
  csvBtn.addEventListener('click', function () {
    if (!last) return;
    VL.downloadText(S.toCSV(last), 'vlonto-sparql-results.csv', 'text/csv;charset=utf-8');
  });

  /* ------------------------------------------------------------------ CONSTRUCT -> 3D
     Drawn like the figures of the paper (arXiv:2611.11426; js/paper3d.js), with the tokens of #graph-wrap
     (data-style="paper"): white figure ground, pastel spheres in the paper's class colours (records of the documents,
     articles, terms, ...) or else their module's colour, call-outs in Libertinus Sans on leader lines placed by the
     shared declutter (VL.Callouts), depth fade, and the paper's legend row. A small result (at most RESULT_TRACE_MAX
     links) is the traced answer (navy core over a pale-gold halo); a larger one keeps its links as thin lines in the
     colours of their predicates and traces the links of the hovered node, as the paper draws only the traced path dark. */
  var G = null, P = null, trace = null, fog = null, lights = null, legend = null, sceneR = 100, callouts = null, graphNote = null;
  function renderGraphNote() {
    if (!graphNote) return;
    VL.$('#graph-note').textContent = VL.U('sq.graphNote', { nodes: VL.fmt(graphNote.nodes), links: VL.fmt(graphNote.links) }) +
      (graphNote.truncated ? VL.U('sq.graphTruncated') : '') + VL.U('sq.graphHelp');
  }
  var RESULT_TRACE_MAX = 12, NODE_R = Math.cbrt(1.6) * 3 * 1.08, many = false, hoverNode = null, traceSet = new Set(), deg = {};
  var scope = VL.$('#graph-wrap');
  function readTheme() { P = VL.paperTheme(scope); }
  function load3d() {
    if (window.ForceGraph3D && VL.TraceLines) return Promise.resolve();
    return VL.loadScript('vendor/three/three.iife.min.js')
      .then(function () { return VL.loadScript('js/labels3d.js'); })
      .then(function () { return VL.loadScript('js/paper3d.js'); })
      .then(function () { return VL.loadScript('vendor/3d-force-graph/3d-force-graph.iife.min.js'); })
      .then(function () { return window.VLONTO.ontology_graph ? null : VL.loadScript('data/ontology_graph.js').catch(function () { return null; }); });
  }
  /* the ontology's own names of its classes ({vi, en} by CURIE, from data/ontology_graph.js): call-outs name a record's
     class in the language mode; without that file the class keeps its English local name */
  var CLASS_NAMES = null;
  function classNames() {
    if (CLASS_NAMES) return CLASS_NAMES;
    var og = window.VLONTO.ontology_graph;
    if (!og) return {};
    CLASS_NAMES = {};
    og.nodes.forEach(function (n) { if (n.kind === 'class') CLASS_NAMES[n.id] = VL.pair(n.label_vi || '', n.label_en || ''); });
    return CLASS_NAMES;
  }
  function lower1(s) { return s ? s.charAt(0).toLowerCase() + s.slice(1) : s; }
  function classModule(types) {
    var mods = { Constitution: 'documents', Code: 'documents', Law: 'documents', Ordinance: 'documents', Resolution: 'documents', JointResolution: 'documents',
      Decree: 'documents', Decision: 'documents', Circular: 'documents', JointCircular: 'documents', LegalChange: 'validity-change', IssuingBody: 'agents',
      LegalArea: 'classification', Precedent: 'judiciary', SourceDataset: 'provenance', EdgeSet: 'provenance', BuildActivity: 'provenance' };
    for (var i = 0; i < (types || []).length; i++) {
      var local = String(types[i]).split('#').pop();
      if (mods[local]) return mods[local];
    }
    return null;
  }
  /* paper class of a record (the first of its types that has one) and its English class name, "JointCircular" -> "joint circular" */
  function paperKeyOf(types) {
    for (var i = 0; i < (types || []).length; i++) { var k = VL.paperClassKey(types[i], true); if (k) return k; }
    return null;
  }
  /* the record's class as {vi, en}, in lower case as in a sentence ("joint circular", "thông tư liên tịch") */
  function className(types) {
    var t = (types || []).map(function (x) { return String(x); }).filter(function (x) { return x.indexOf(VL.NS.vlo) === 0; })[0];
    if (!t) return null;
    var local = t.split('#').pop(), cn = classNames()['vlo:' + local], en = local.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
    return VL.pair(cn && cn.vi ? lower1(cn.vi) : '', cn && cn.en ? cn.en.toLowerCase() : en);
  }
  /* a node's name in the mode: its number, else its label (English and the Vietnamese where the dataset has it), else
     its title, else its CURIE */
  function nodeName(n) { return n.number || (n.label || n.label_vi ? VL.U(VL.pair(n.label_vi || '', n.label || '')) : '') || (n.title ? VL.short(n.title, 26) : '') || VL.shortIri(n.iri || n.id); }
  function nodeColor(n) { return (n.pk && P.cls[n.pk]) || VL.tok('--mod-' + n.mod, scope) || VL.moduleColor(n.mod); }
  function rimHex(hex, f) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim()), v = m ? parseInt(m[1], 16) : 0x888888;
    return '#' + [v >> 16, (v >> 8) & 255, v & 255].map(function (c) { c = Math.round(c * f); return (c < 16 ? '0' : '') + c.toString(16); }).join('');
  }
  /* call-out in the language mode, in the paper's two greys: a term of the ontology by its name ("Tiếng Việt · English"
     in EN–VI, one language in EN or VI); a record by its number, label or title, then its class (EN or VI: one name;
     EN–VI: both, on one line when short, else the English under it) */
  function nodeLines(n) {
    M.labelsLang = VL.lang();
    if (!n.number && n.label_vi && n.label) return VL.paperLines(VL.short(n.label_vi, 30), VL.short(n.label, 30), P);
    var name = nodeName(n), first = [{ text: name, color: P.ink }];
    if (!n.cls) return [first];
    var t = VL.TL(n.cls);
    if (!t.secondary) return [first.concat([{ text: ' · ' + t.primary, color: P.ink2 }])];
    if (name.length + t.primary.length + t.secondary.length + 6 <= 34) return [first.concat([{ text: ' · ' + t.primary, color: P.ink2 }, { text: ' · ' + t.secondary, color: P.ink2 }])];
    return [first.concat([{ text: ' · ' + t.primary, color: P.ink2 }]), [{ text: t.secondary, color: P.ink2 }]];
  }
  function labelOpts(n) {
    var o = VL.paperCallout(P, false);
    o.lines = nodeLines(n);
    o.weight = '400';
    return o;
  }
  function styleNode(n) {
    if (!n.__rim) return;
    n.__rim.material.color.set(rimHex(nodeColor(n), P.dark ? 0.72 : 0.84));
  }
  /* the traced links: every link of a small result, else those of the hovered node (when it has at most
     RESULT_TRACE_MAX); the other links are thin lines in the colour of their predicate */
  function computeTraceSet() {
    var links = G ? G.graphData().links : [];
    traceSet = new Set();
    if (!many) links.forEach(function (l) { traceSet.add(l); });
    else if (hoverNode) {
      var ls = links.filter(function (l) { return l.source === hoverNode || l.target === hoverNode; });
      if (ls.length <= RESULT_TRACE_MAX) ls.forEach(function (l) { traceSet.add(l); });
    }
    M.constructLines = links.length - traceSet.size;
    M.constructMode = many ? 'lines' : 'trace';
  }
  function linkColor(l) {
    if (traceSet.has(l)) return P.core;
    var c = VL.predColor(l.pred, scope);
    return P.dark ? c : VL.shade(c, 0.9);
  }
  function linkWidth(l) { return traceSet.has(l) ? 0 : 0.55; }
  function refreshLinks() {
    if (!G) return;
    G.linkColor(G.linkColor());
    G.linkWidth(G.linkWidth());
    G.linkDirectionalArrowColor(G.linkDirectionalArrowColor());
  }
  function updateTrace() {
    if (!G || !trace) return;
    var paths = [];
    traceSet.forEach(function (l) { var pts = VL.linkPoints(l, 12); if (pts) paths.push(pts); });
    trace.setStyle(VL.traceStyle(P, paths.length > 60 ? 0.72 : 0.9));
    trace.setPaths(paths);
    M.constructTrace = trace.count();
  }
  function setHover(n) {
    if (n === hoverNode) return;
    hoverNode = n || null;
    M.constructHover = hoverNode ? hoverNode.id : null;
    if (many) { computeTraceSet(); refreshLinks(); updateTrace(); }
    if (callouts) callouts.schedule();
  }
  /* the nodes whose call-out always stays: the ends of the traced links and the hovered node */
  function isMust(n) {
    if (n === hoverNode) return true;
    var hit = false;
    traceSet.forEach(function (l) { if (l.source === n || l.target === n) hit = true; });
    return hit;
  }
  function updateFog() { if (G && fog) VL.fitFog(fog, G.camera().position.distanceTo(G.controls().target), sceneR); }
  /* legend entries: "Tiếng Việt · English" in EN–VI, one language in EN or VI */
  function bi(vi, en) { return VL.TH(VL.pair(VL.cap(vi || ''), VL.cap(en || ''))); }
  function biKey(k) { var e = VL.i18n.get(k) || { vi: '', en: k }; return bi(e.vi, e.en); }
  /* Vietnamese and English names of a predicate (the change, basis and citation names of the legal network) */
  function predName(k) {
    var ch = { replaces: 'replaced', amends: 'amended', repeals: 'repealed', partiallyRepeals: 'partially_repealed', partiallyExpires: 'partially_expired' }[k];
    if (ch && VL.CHANGE[ch]) return [VL.CHANGE[ch].vi, VL.CHANGE[ch].active];
    if (k === 'legalBasis') return [VL.EDGE.basis.vi, VL.EDGE.basis.en];
    if (k === 'cites') return [VL.EDGE.citation.vi, VL.EDGE.citation.en];
    if (k === 'subClassOf') { var e = VL.i18n.get('sq.lg.subclassOf') || {}; return [e.vi, e.en]; }
    return null;
  }
  function renderLegend(nodes) {
    if (!legend) return;
    var keys = {}, mods = {};
    nodes.forEach(function (n) { if (n.pk) keys[n.pk] = true; else mods[n.mod] = true; });
    var h = '<ul>' + VL.PAPER_CLASSES.filter(function (c) { return keys[c.key]; }).map(function (c) {
      return '<li><span class="swatch" style="background:' + c.v + '"></span>' + bi(c.vi, c.en) + '</li>';
    }).join('') + VL.MODULES.filter(function (m) { return mods[m.id]; }).map(function (m) {
      return '<li><span class="swatch" style="background:' + m.v + '"></span>' + bi(m.vi, m.en) + '</li>';
    }).join('') + '<li><span class="swatch trace" aria-hidden="true"></span>' + biKey(many ? 'sq.lg.hovered' : 'sq.lg.result') + '</li></ul>';
    if (many) {
      var preds = {};
      (G ? G.graphData().links : []).forEach(function (l) { preds[VL.predKind(l.pred)] = l.pred; });
      h += '<div class="legend-sub"><ul>' + Object.keys(preds).sort().map(function (k) {
        var c = VL.predColor(preds[k], scope), name = predName(k);
        return '<li><span class="swatch line" style="background:' + (P.dark ? c : VL.shade(c, 0.9)) + '"></span>' + (name ? bi(name[0], name[1]) : VL.esc(preds[k])) + '</li>';
      }).join('') + '</ul></div>';
    }
    legend.innerHTML = h;
  }
  /* theme switch: background, fog, light, node colours, call-outs, the traced result and the legend of the CONSTRUCT view */
  window.addEventListener('vlonto-theme', function () {
    if (!G) return;
    readTheme();
    G.backgroundColor(P.bg);
    if (fog) fog.color.set(P.bg);
    if (lights) { var L2 = VL.paperLights(P.dark); lights.ambient.intensity = L2.ambient.intensity; lights.directional.intensity = L2.directional.intensity; }
    G.graphData().nodes.forEach(function (n) {
      n.color = nodeColor(n);
      styleNode(n);
      if (n.__label) n.__label.setStyle(labelOpts(n));
    });
    G.nodeColor(G.nodeColor());
    refreshLinks();
    updateTrace();
    renderLegend(G.graphData().nodes);
    if (callouts) callouts.schedule();
    M.constructThemed = (M.constructThemed || 0) + 1;
  });
  function drawGraph(ctx, res) {
    var wrap = VL.$('#graph-wrap');
    wrap.classList.remove('hidden');
    var g = S.quadsToGraph(ctx, res.quads, 400);
    var nodes = g.nodes.map(function (n) {
      var isOnto = n.iri && n.iri.indexOf(VL.NS.vlo) === 0;
      var mod = classModule(n.types) || (isOnto ? 'documents' : 'provenance');
      return { id: n.id, iri: n.iri, number: n.number ? VL.nfc(n.number) : null, label: n.label ? VL.nfc(n.label) : null, label_vi: n.label_vi ? VL.nfc(n.label_vi) : null,
        title: n.title, mod: mod, pk: paperKeyOf(n.types), types: n.types };
    });
    var links = g.links.map(function (l) { return { source: l.source, target: l.target, pred: l.pred }; });
    graphNote = { nodes: nodes.length, links: links.length, truncated: g.truncated };
    renderGraphNote();
    M.constructDrawn = { nodes: nodes.length, links: links.length };
    return load3d().then(function () { return VL.fontsReady(); }).then(function () {
      var el = VL.$('#graph-view');
      readTheme();
      nodes.forEach(function (n) { n.color = nodeColor(n); n.cls = className(n.types); });
      if (!G) {
        G = new ForceGraph3D(el, { controlType: 'orbit', rendererConfig: { antialias: true, alpha: false } })
          .backgroundColor(P.bg).showNavInfo(false)
          .nodeRelSize(3).nodeVal(function () { return 1.6; })
          .nodeColor(function (n) { return n.color; })
          .nodeOpacity(0.95).nodeResolution(20)
          .nodeLabel(function (n) { return '<b>' + VL.esc(nodeName(n)) + '</b>' + (n.title ? '<br><span lang="vi">' + VL.esc(VL.short(n.title, 70)) + '</span>' : ''); })
          .nodeThreeObjectExtend(true)
          .nodeThreeObject(function (n) {
            var grp = new THREE.Group();
            /* the darker rim of the paper's spheres: a slightly larger back-face hull around the default sphere */
            var rim = new THREE.Mesh(new THREE.SphereGeometry(Math.cbrt(1.6) * 3 * 1.08, 20, 14),
              new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.BackSide, transparent: true, opacity: 0.95 }));
            n.__rim = rim;
            styleNode(n);
            grp.add(rim);
            var s = VL.TextSprite(nodeName(n), Object.assign({ px: 21 }, labelOpts(n)));
            s.layers.set(1);              // hidden until VL.Callouts places it
            s.fit(VL.spriteWpp(G.camera(), el.clientHeight));
            n.__label = s;
            grp.add(s);
            return grp;
          })
          .linkColor(linkColor)
          .linkOpacity(0.5).linkWidth(linkWidth)
          .linkDirectionalArrowLength(3.5).linkDirectionalArrowRelPos(1)
          .linkDirectionalArrowColor(linkColor)
          .onNodeHover(function (n) { setHover(n); })
          .linkLabel(function (l) { return VL.esc(l.pred); })
          .onNodeClick(function (n) { var d = VL.docIdFromIri(n.iri); if (d) location.href = VL.href('network-3d.html#doc=' + encodeURIComponent(d)); })
          .warmupTicks(100).cooldownTicks(80)
          .onEngineTick(function () { updateTrace(); cull(); })
          .onEngineStop(function () { updateTrace(); fit(); });
        lights = VL.paperLights(P.dark);
        G.lights([lights.ambient]);
        VL.attachCameraLight(G.scene(), G.camera(), lights.directional);
        fog = VL.paperFog(G.scene(), P.bg);
        trace = VL.TraceLines({ depthTest: true, renderOrder: 8 });
        G.scene().add(trace.object);
        legend = VL.el('div', { 'class': 'legend', id: 'construct-legend', 'aria-label': VL.U('sq.lg.aria') });
        el.appendChild(legend);
        callouts = VL.Callouts({
          camera: function () { return G.camera(); },
          size: function () { return { w: el.clientWidth, h: el.clientHeight }; },
          items: function () {
            return G.graphData().nodes.map(function (n) { return { id: n.id, sprite: n.__label, pri: (deg[n.id] || 0) + (n.pk ? 0.5 : 0), must: isMust(n), r: NODE_R }; });
          },
          ink: function () {
            var gd = G.graphData();
            return {
              discs: gd.nodes.filter(function (n) { return isFinite(n.x); }).map(function (n) { return { id: n.id, x: n.x, y: n.y, z: n.z, r: NODE_R }; }),
              paths: gd.links.map(function (l) { return VL.linkPoints(l, 6); }).filter(Boolean)
            };
          },
          ui: function () {
            if (!legend || legend.offsetParent === null) return [];
            var hr = el.getBoundingClientRect(), lr = legend.getBoundingClientRect();
            return [{ x0: lr.left - hr.left - 4, x1: lr.right - hr.left + 4, y0: lr.top - hr.top - 4, y1: lr.bottom - hr.top + 4 }];
          },
          leaderColor: function () { return P.leader; },
          metrics: M, key: 'callouts',
          onDone: function (st) { M.constructLabels = st.shown; updateFog(); }
        });
        G.controls().addEventListener('change', cull);
        window.addEventListener('resize', function () {
          G.width(el.clientWidth).height(el.clientHeight);
          var w = VL.spriteWpp(G.camera(), el.clientHeight);
          G.graphData().nodes.forEach(function (n) { if (n.__label) n.__label.fit(w); });
          cull();
        });
      }
      G.width(el.clientWidth).height(el.clientHeight);
      many = links.length > RESULT_TRACE_MAX;
      hoverNode = null;
      M.constructHover = null;
      deg = {};
      links.forEach(function (l) { deg[l.source] = (deg[l.source] || 0) + 1; deg[l.target] = (deg[l.target] || 0) + 1; });
      G.linkOpacity(many ? 0.92 : 0.5);
      G.graphData({ nodes: nodes, links: links });
      computeTraceSet();
      refreshLinks();
      updateTrace();
      renderLegend(nodes);
      if (callouts) callouts.forget();
      setTimeout(fit, 300);
    });
  }
  function fit() {
    if (!G) return;
    G.zoomToFit(400, 30);
    var bb = G.getGraphBbox && G.getGraphBbox();
    if (bb) sceneR = Math.max(20, 0.5 * Math.sqrt(Math.pow(bb.x[1] - bb.x[0], 2) + Math.pow(bb.y[1] - bb.y[0], 2) + Math.pow(bb.z[1] - bb.z[0], 2)));
    setTimeout(cull, 450);
  }
  /* call-out placement (js/paper3d.js VL.Callouts): throttled while the camera moves or the layout ticks */
  function cull() { if (G && callouts) callouts.schedule(); }

  /* ------------------------------------------------------------------ self-test over the examples (EX: 10 in v1) */
  var lastSelf = null;
  function exCell(x) {
    if (VL.lang() === 'envi') return VL.esc(x.title) + '<div class="sub" lang="vi">' + VL.esc(x.vi) + '</div>';
    return VL.UH(VL.pair(x.vi, x.title));
  }
  function renderSelfTest() {
    var r = lastSelf;
    if (!r) return;
    VL.$('#selftest-sum').textContent = VL.U('sq.selftest.sum', { p: VL.fmt(r.pass), n: VL.fmt(r.rows.length) });
    VL.$('#selftest').innerHTML = '<thead><tr><th class="num">#</th><th>' + VL.UH('sq.th.example') + '</th><th class="num">' + VL.UH('sq.th.expected') +
      '</th><th class="num">' + VL.UH('sq.th.rows') + '</th><th class="num col-opt">ms</th><th>' + VL.UH('sq.th.result') + '</th></tr></thead><tbody>' +
      r.rows.map(function (x) {
        return '<tr><td class="num">' + (x.i + 1) + '</td><td>' + exCell(x) + '</td><td class="num">' + VL.fmt(x.expected) +
          '</td><td class="num">' + (x.got == null ? '–' : VL.fmt(x.got)) + '</td><td class="num col-opt">' + VL.fmt(x.ms) + '</td><td>' +
          (x.ok ? '<span class="pass">' + VL.UH('sq.match') + '</span>' : '<span class="fail">✗ ' + (x.error ? VL.esc(x.error) : VL.UH('sq.different')) + '</span>') + '</td></tr>';
      }).join('') + '</tbody>';
    setStatus(function () {
      return (r.pass === r.rows.length ? '✓ ' : '✗ ') + VL.U('sq.selftest.status', { p: VL.fmt(r.pass), n: VL.fmt(r.rows.length), t: VL.fmt(r.ctx.triples) });
    }, r.pass === r.rows.length ? 'ok' : 'err');
  }
  function selfTest() {
    var card = VL.$('#selftest-card');
    card.classList.remove('hidden');
    setStatus(function () { return VL.U('sq.selftest.running', { n: VL.fmt(EX.length) }); }, '');
    return getStore('core').then(function (ctx) {
      var rows = EX.map(function (e, i) {
        var r = S.run(ctx, e.query);
        var ok = !r.error && r.count === e.rows_on_core;
        return { i: i, title: e.title_en, vi: e.title_vi, expected: e.rows_on_core, got: r.error ? null : r.count, ms: r.ms, ok: ok, error: r.error ? r.error.message : null };
      });
      var cons = CX.map(function (e) { var r = S.run(ctx, e.query); return { id: e.id, title: e.title_en, triples: r.error ? null : r.count, error: r.error ? r.error.message : null, ms: r.ms }; });
      var pass = rows.filter(function (r) { return r.ok; }).length;
      M.sparqlExamples = { total: rows.length, pass: pass, rows: rows, construct: cons };
      lastSelf = { rows: rows, pass: pass, ctx: ctx };
      renderSelfTest();
      return M.sparqlExamples;
    });
  }
  VL.$('#btn-all').addEventListener('click', function () { dsEl.value = 'core'; selfTest(); });
  window.VLApp.selfTest = selfTest;
  /* tests: hover a node of the CONSTRUCT view (id, or null to end the hover); its nodes and their link counts */
  window.VLApp.constructHover = function (id) {
    if (!G) return 0;
    setHover(id ? G.graphData().nodes.filter(function (n) { return n.id === id; })[0] || null : null);
    return M.constructTrace || 0;
  };
  /* the camera (position and orbit target, rounded): tests check that a language switch keeps it */
  function camState(cam, target) {
    if (!cam || !target) return null;
    return [cam.position.x, cam.position.y, cam.position.z, target.x, target.y, target.z].map(function (v) { return Math.round(v * 1000) / 1000; });
  }
  window.VLApp.constructCamera = function () { return G ? camState(G.camera(), G.controls().target) : null; };
  window.VLApp.constructNodes = function () { return G ? G.graphData().nodes.map(function (n) { return { id: n.id, links: deg[n.id] || 0 }; }) : []; };
  window.VLApp.run = function (q, ds) { if (ds) dsEl.value = ds; if (q != null) qEl.value = q; return run().then(function () { return M.lastQuery; }); };
  window.VLApp.runExample = function (key) { qEl.value = exampleQuery(key); markExample(key); return run().then(function () { return M.lastQuery; }); };

  /* ------------------------------------------------------------------ the page's own text that the declarative
     attributes cannot hold: numbers from the data in the mode's format (the examples' count, the full graph's triples
     from VLONTO.stats) and sentences with code or links inside */
  function code(x) { return '<code>' + VL.esc(x) + '</code>'; }
  function renderStatic() {
    var n = VL.fmt(EX.length), b = VL.$('#btn-all'), t = VL.tip('sq.runAll', { n: n });
    b.textContent = VL.U('sq.runAll', { n: n });
    if (t) b.setAttribute('title', t); else b.removeAttribute('title');
    VL.$('#selftest-title').textContent = VL.U('sq.selftest.h', { n: n });
    var pp = VL.$('#sq-paper');
    if (pp) pp.innerHTML = VL.UH('sq.paper', { release: VL.releaseLabel() }, { html: { title: '<a href="' + VL.esc(VL.PAPER.url) +
      '" target="_blank" rel="noopener" data-paper-link="side" lang="en">' + VL.esc(VL.PAPER.title) + '</a>' } });
    var st = window.VLONTO.stats || {}, meta = window.VLONTO.site_meta || {};
    var triples = st.rdf_triples || (meta.rdf_dump || {}).triples;
    var know = {
      'sq-know-typed': VL.UH('sq.know.typed', null, { html: { a: code('vlo:Law') + ', ' + code('vlo:Decree'), b: code('?d a vlo:LegalDocument'), c: code('vlo:documentNumber') } }),
      'sq-know-shortcut': VL.UH('sq.know.shortcut', null, { html: { a: code('vlo:replaces') + ', ' + code('vlo:amends'), b: code('vlo:legalBasis'), c: code('vlo:LegalChange') } }),
      'sq-know-limit': VL.UH('sq.know.limit', null, { html: { code: code('LIMIT') } }),
      'sq-know-full': VL.UH('sq.know.full', { n: VL.fmt(triples) }, { html: { link: '<a href="downloads.html#dl-full"' + (VL.tip('sq.downloadsPage') ? ' title="' + VL.esc(VL.tip('sq.downloadsPage')) + '"' : '') + '>' + VL.UH('sq.downloadsPage') + '</a>' } })
    };
    Object.keys(know).forEach(function (id) { var e = document.getElementById(id); if (e) e.innerHTML = know[id]; });
    M.sparqlFullTriples = triples || null;
  }
  renderStatic();
  /* language switch (js/i18n.js 'vl:lang'): examples, dataset menu, the page's own text, the result (title, table notes,
     status), the self-test table, and the CONSTRUCT view's call-outs, legend and note in the new mode; the query, the
     result and the camera stay */
  function applyLang() {
    M.langRenders = (M.langRenders || 0) + 1;
    var st = lastStatus;
    renderStatic();
    renderExamples();
    renderDatasets();
    if (lastShown) showResult(lastShown);
    if (lastSelf) renderSelfTest();
    if (st) setStatus(st[0], st[1]);
    renderGraphNote();
    if (G) {
      G.graphData().nodes.forEach(function (n) { if (n.__label) n.__label.setLines(nodeLines(n)); });
      renderLegend(G.graphData().nodes);
      if (legend) legend.setAttribute('aria-label', VL.U('sq.lg.aria'));
      if (callouts) callouts.schedule();
    } else M.labelsLang = VL.lang();
  }
  document.addEventListener('vl:lang', applyLang);

  /* ------------------------------------------------------------------ start */
  dsEl.value = 'core';
  var p = VL.params();
  if (p.q) { qEl.value = p.q; markExample(null); }
  else { qEl.value = EX.length ? EX[0].query : CX[0].query; markExample(EX.length ? 's0' : 'c0'); }
  VL.fontsReady().then(function () { return run(); }).then(function () {
    VL.setReady({ examples: EX.length, constructExamples: CX.length });
  });
})();

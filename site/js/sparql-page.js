/* VLOnto - SPARQL playground page: examples, editor, results table, CSV export, CONSTRUCT drawn in 3D, self-test. */
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

  /* ------------------------------------------------------------------ examples */
  VL.$('#ex-select').innerHTML = EX.map(function (e, i) {
    return '<button type="button" class="ex-item" data-ex="s' + i + '" aria-pressed="false"><span class="t">' + VL.esc(e.title_en) + '</span>' +
      '<span class="v" lang="vi">' + VL.esc(e.title_vi) + '</span><span class="m"><span class="badge">' + VL.fmt(e.rows_on_core) + ' row' + (e.rows_on_core === 1 ? '' : 's') + ' expected</span></span></button>';
  }).join('');
  VL.$('#ex-construct').innerHTML = CX.map(function (e, i) {
    return '<button type="button" class="ex-item" data-ex="c' + i + '" aria-pressed="false"><span class="t">' + VL.esc(e.title_en) + '</span>' +
      '<span class="v" lang="vi">' + VL.esc(e.title_vi) + '</span><span class="m"><span class="badge">CONSTRUCT · 3D</span></span></button>';
  }).join('');
  Object.keys(S.DATASETS).forEach(function (k) {
    dsEl.insertAdjacentHTML('beforeend', '<option value="' + k + '">' + VL.esc(S.DATASETS[k].label) + '</option>');
  });
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
      setStatus('Loading ' + S.DATASETS[ds].label + ' into Oxigraph…', '');
      stores[ds] = S.createStore(ds).then(function (ctx) {
        M['store_' + ds] = { triples: ctx.triples, ms: ctx.loadMs };
        return ctx;
      }, function (e) { delete stores[ds]; throw e; });
    }
    return stores[ds];
  }
  function setStatus(msg, cls) { statusEl.textContent = msg; statusEl.className = 'status-line' + (cls ? ' ' + cls : ''); }
  function highlightError(err) {
    if (!err || !err.line) return;
    var lines = qEl.value.split('\n'), pos = 0;
    for (var i = 0; i < err.line - 1 && i < lines.length; i++) pos += lines[i].length + 1;
    var col = Math.max(0, (err.col || 1) - 1);
    qEl.focus();
    qEl.setSelectionRange(pos + col, Math.min(pos + (lines[err.line - 1] || '').length, pos + col + 12));
  }

  /* ------------------------------------------------------------------ run */
  function run() {
    var q = qEl.value;
    if (!q.trim()) { setStatus('The query is empty. Choose an example or type a SPARQL query.', 'err'); return Promise.resolve(null); }
    var ds = dsEl.value;
    setStatus('Running…', '');
    return getStore(ds).then(function (ctx) {
      var res = S.run(ctx, q);
      last = res;
      M.lastQuery = { form: res.form, count: res.count, ms: res.ms, error: res.error ? res.error.message : null, dataset: ds };
      if (res.error) {
        setStatus(res.error.message, 'err');
        highlightError(res.error);
        csvBtn.disabled = true;
        return res;
      }
      var head = VL.fmt(ctx.triples) + ' triples loaded';
      VL.$('#graph-wrap').classList.add('hidden');
      if (res.form === 'SELECT') {
        setStatus('✓ ' + VL.fmt(res.count) + ' row' + (res.count === 1 ? '' : 's') + ' in ' + res.ms + ' ms · ' + head, 'ok');
        titleEl.textContent = 'Results · ' + VL.fmt(res.count) + ' row' + (res.count === 1 ? '' : 's');
        S.renderTable(resultEl, res, { max: 1000 });
        csvBtn.disabled = !res.count;
      } else if (res.form === 'ASK') {
        setStatus('✓ ASK → ' + (res.boolean ? 'true' : 'false') + ' in ' + res.ms + ' ms', 'ok');
        titleEl.textContent = 'Result · ' + (res.boolean ? 'true' : 'false');
        resultEl.innerHTML = '<p style="padding:12px 14px;margin:0">The pattern ' + (res.boolean ? 'matches' : 'does not match') + ' the dataset.</p>';
        csvBtn.disabled = true;
      } else {
        setStatus('✓ ' + VL.fmt(res.count) + ' triple' + (res.count === 1 ? '' : 's') + ' in ' + res.ms + ' ms · drawn in 3D below · ' + head, 'ok');
        titleEl.textContent = 'Graph result · ' + VL.fmt(res.count) + ' triples';
        S.renderTable(resultEl, res, { max: 500 });
        csvBtn.disabled = !res.count;
        if (res.count) drawGraph(ctx, res);
      }
      return res;
    }).catch(function (e) { setStatus('Could not run the query: ' + (e && e.message ? e.message : e), 'err'); return null; });
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
  var G = null, P = null, trace = null, fog = null, lights = null, legend = null, sceneR = 100, callouts = null;
  var RESULT_TRACE_MAX = 12, NODE_R = Math.cbrt(1.6) * 3 * 1.08, many = false, hoverNode = null, traceSet = new Set(), deg = {};
  var scope = VL.$('#graph-wrap');
  function readTheme() { P = VL.paperTheme(scope); }
  function load3d() {
    if (window.ForceGraph3D && VL.TraceLines) return Promise.resolve();
    return VL.loadScript('vendor/three/three.iife.min.js')
      .then(function () { return VL.loadScript('js/labels3d.js'); })
      .then(function () { return VL.loadScript('js/paper3d.js'); })
      .then(function () { return VL.loadScript('vendor/3d-force-graph/3d-force-graph.iife.min.js'); });
  }
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
  function className(types) {
    var t = (types || []).map(function (x) { return String(x); }).filter(function (x) { return x.indexOf(VL.NS.vlo) === 0; })[0];
    return t ? t.split('#').pop().replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase() : '';
  }
  function nodeColor(n) { return (n.pk && P.cls[n.pk]) || VL.tok('--mod-' + n.mod, scope) || VL.moduleColor(n.mod); }
  function rimHex(hex, f) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim()), v = m ? parseInt(m[1], 16) : 0x888888;
    return '#' + [v >> 16, (v >> 8) & 255, v & 255].map(function (c) { c = Math.round(c * f); return (c < 16 ? '0' : '') + c.toString(16); }).join('');
  }
  /* call-out: the record's number, label or title, then its class in English, in the paper's two greys */
  function labelOpts(n) {
    var o = VL.paperCallout(P, false);
    o.lines = [[{ text: n.label, color: P.ink }].concat(n.cls ? [{ text: ' · ' + n.cls, color: P.ink2 }] : [])];
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
  function bi(vi, en) { return '<span lang="vi">' + VL.esc(VL.cap(vi)) + '</span> · ' + VL.esc(VL.cap(en)); }
  /* Vietnamese and English names of a predicate (the change, basis and citation names of the legal network) */
  function predName(k) {
    var ch = { replaces: 'replaced', amends: 'amended', repeals: 'repealed', partiallyRepeals: 'partially_repealed', partiallyExpires: 'partially_expired' }[k];
    if (ch && VL.CHANGE[ch]) return [VL.CHANGE[ch].vi, VL.CHANGE[ch].active];
    if (k === 'legalBasis') return [VL.EDGE.basis.vi, VL.EDGE.basis.en];
    if (k === 'cites') return [VL.EDGE.citation.vi, VL.EDGE.citation.en];
    if (k === 'subClassOf') return ['lớp con của', 'subclass of'];
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
    }).join('') + '<li><span class="swatch trace" aria-hidden="true"></span>' + bi('đường truy vết', many ? 'links of the hovered node' : 'query result') + '</li></ul>';
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
      var label = n.number || n.label || (n.title ? VL.short(n.title, 26) : null) || VL.shortIri(n.iri || n.id);
      return { id: n.id, iri: n.iri, label: VL.nfc(label), title: n.title, mod: mod, pk: paperKeyOf(n.types), cls: className(n.types) };
    });
    var links = g.links.map(function (l) { return { source: l.source, target: l.target, pred: l.pred }; });
    VL.$('#graph-note').textContent = VL.fmt(nodes.length) + ' nodes and ' + VL.fmt(links.length) + ' links' + (g.truncated ? ' (truncated to 400 nodes)' : '') +
      '. Drag to rotate, scroll to zoom; document nodes open in the 3D legal network on click.';
    M.constructDrawn = { nodes: nodes.length, links: links.length };
    return load3d().then(function () { return VL.fontsReady(); }).then(function () {
      var el = VL.$('#graph-view');
      readTheme();
      nodes.forEach(function (n) { n.color = nodeColor(n); });
      if (!G) {
        G = new ForceGraph3D(el, { controlType: 'orbit', rendererConfig: { antialias: true, alpha: false } })
          .backgroundColor(P.bg).showNavInfo(false)
          .nodeRelSize(3).nodeVal(function () { return 1.6; })
          .nodeColor(function (n) { return n.color; })
          .nodeOpacity(0.95).nodeResolution(20)
          .nodeLabel(function (n) { return '<b>' + VL.esc(n.label) + '</b>' + (n.title ? '<br>' + VL.esc(VL.short(n.title, 70)) : ''); })
          .nodeThreeObjectExtend(true)
          .nodeThreeObject(function (n) {
            var grp = new THREE.Group();
            /* the darker rim of the paper's spheres: a slightly larger back-face hull around the default sphere */
            var rim = new THREE.Mesh(new THREE.SphereGeometry(Math.cbrt(1.6) * 3 * 1.08, 20, 14),
              new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.BackSide, transparent: true, opacity: 0.95 }));
            n.__rim = rim;
            styleNode(n);
            grp.add(rim);
            var s = VL.TextSprite(n.label, Object.assign({ px: 21 }, labelOpts(n)));
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
        legend = VL.el('div', { 'class': 'legend', id: 'construct-legend', 'aria-label': 'Legend of the CONSTRUCT view' });
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

  /* ------------------------------------------------------------------ self-test over the 10 examples */
  function selfTest() {
    var card = VL.$('#selftest-card');
    card.classList.remove('hidden');
    setStatus('Running the 10 examples on the core subset…', '');
    return getStore('core').then(function (ctx) {
      var rows = EX.map(function (e, i) {
        var r = S.run(ctx, e.query);
        var ok = !r.error && r.count === e.rows_on_core;
        return { i: i, title: e.title_en, vi: e.title_vi, expected: e.rows_on_core, got: r.error ? null : r.count, ms: r.ms, ok: ok, error: r.error ? r.error.message : null };
      });
      var cons = CX.map(function (e) { var r = S.run(ctx, e.query); return { id: e.id, title: e.title_en, triples: r.error ? null : r.count, error: r.error ? r.error.message : null, ms: r.ms }; });
      var pass = rows.filter(function (r) { return r.ok; }).length;
      M.sparqlExamples = { total: rows.length, pass: pass, rows: rows, construct: cons };
      VL.$('#selftest-sum').textContent = pass + ' / ' + rows.length + ' match rows_on_core';
      VL.$('#selftest').innerHTML = '<thead><tr><th class="num">#</th><th>Example</th><th class="num">Expected</th><th class="num">Rows</th><th class="num col-opt">ms</th><th>Result</th></tr></thead><tbody>' +
        rows.map(function (r) {
          return '<tr><td class="num">' + (r.i + 1) + '</td><td>' + VL.esc(r.title) + '<div class="sub" lang="vi">' + VL.esc(r.vi) + '</div></td><td class="num">' + VL.fmt(r.expected) +
            '</td><td class="num">' + (r.got == null ? '–' : VL.fmt(r.got)) + '</td><td class="num col-opt">' + r.ms + '</td><td>' +
            (r.ok ? '<span class="pass">✓ match</span>' : '<span class="fail">✗ ' + VL.esc(r.error || 'different') + '</span>') + '</td></tr>';
        }).join('') + '</tbody>';
      setStatus((pass === rows.length ? '✓ ' : '✗ ') + pass + ' of ' + rows.length + ' examples return the expected number of rows on the core subset (' + VL.fmt(ctx.triples) + ' triples).', pass === rows.length ? 'ok' : 'err');
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
  window.VLApp.constructNodes = function () { return G ? G.graphData().nodes.map(function (n) { return { id: n.id, links: deg[n.id] || 0 }; }) : []; };
  window.VLApp.run = function (q, ds) { if (ds) dsEl.value = ds; if (q != null) qEl.value = q; return run().then(function () { return M.lastQuery; }); };
  window.VLApp.runExample = function (key) { qEl.value = exampleQuery(key); markExample(key); return run().then(function () { return M.lastQuery; }); };

  /* ------------------------------------------------------------------ start */
  dsEl.value = 'core';
  var p = VL.params();
  if (p.q) { qEl.value = p.q; markExample(null); }
  else { qEl.value = EX.length ? EX[0].query : CX[0].query; markExample(EX.length ? 's0' : 'c0'); }
  VL.fontsReady().then(function () { return run(); }).then(function () {
    VL.setReady({ examples: EX.length, constructExamples: CX.length });
  });
})();

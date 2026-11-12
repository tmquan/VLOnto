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

  /* ------------------------------------------------------------------ CONSTRUCT -> 3D */
  var G = null;
  function labelStyle() {
    return { color: VL.tok('--label-fg') || '#ffffff', bg: VL.tok('--label-bg') || 'rgba(9, 14, 30, 0.8)', border: VL.tok('--label-border') || '' };
  }
  /* theme switch: background, node colours (module palette of the theme), labels and links of the CONSTRUCT view */
  window.addEventListener('vlonto-theme', function () {
    if (!G) return;
    G.backgroundColor(VL.tok('--scene-bg') || '#0a0f1e');
    var st = labelStyle();
    G.graphData().nodes.forEach(function (n) {
      n.color = VL.moduleColor(n.mod || 'provenance');
      if (n.__label) n.__label.setStyle(st);
    });
    G.nodeColor(G.nodeColor());
    G.linkColor(G.linkColor());
    M.constructThemed = (M.constructThemed || 0) + 1;
  });
  function load3d() {
    if (window.ForceGraph3D) return Promise.resolve();
    return VL.loadScript('vendor/three/three.iife.min.js')
      .then(function () { return VL.loadScript('js/labels3d.js'); })
      .then(function () { return VL.loadScript('vendor/3d-force-graph/3d-force-graph.iife.min.js'); });
  }
  var ONTO = window.VLONTO.ontology_graph;
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
  function drawGraph(ctx, res) {
    var wrap = VL.$('#graph-wrap');
    wrap.classList.remove('hidden');
    var g = S.quadsToGraph(ctx, res.quads, 400);
    var nodes = g.nodes.map(function (n) {
      var isOnto = n.iri && n.iri.indexOf(VL.NS.vlo) === 0;
      var mod = classModule(n.types) || (isOnto ? 'documents' : 'provenance');
      var label = n.number || n.label || (n.title ? VL.short(n.title, 26) : null) || VL.shortIri(n.iri || n.id);
      return { id: n.id, iri: n.iri, label: VL.nfc(label), title: n.title, mod: mod, color: VL.moduleColor(mod) };
    });
    var links = g.links.map(function (l) { return { source: l.source, target: l.target, pred: l.pred }; });
    VL.$('#graph-note').textContent = VL.fmt(nodes.length) + ' nodes and ' + VL.fmt(links.length) + ' links' + (g.truncated ? ' (truncated to 400 nodes)' : '') +
      '. Drag to rotate, scroll to zoom; document nodes open in the 3D legal network on click.';
    M.constructDrawn = { nodes: nodes.length, links: links.length };
    return load3d().then(function () { return VL.fontsReady(); }).then(function () {
      var el = VL.$('#graph-view');
      if (!G) {
        G = new ForceGraph3D(el, { controlType: 'orbit', rendererConfig: { antialias: true, alpha: false } })
          .backgroundColor(VL.tok('--scene-bg') || '#0a0f1e').showNavInfo(false)
          .nodeRelSize(3).nodeVal(function () { return 1.6; })
          .nodeColor(function (n) { return n.color; })
          .nodeLabel(function (n) { return '<b>' + VL.esc(n.label) + '</b>' + (n.title ? '<br>' + VL.esc(VL.short(n.title, 70)) : ''); })
          .nodeThreeObjectExtend(true)
          .nodeThreeObject(function (n) {
            var s = VL.TextSprite(n.label, Object.assign({ px: 22, weight: '600', cx: 0.5, cy: -0.3 }, labelStyle()));
            s.fit(VL.spriteWpp(G.camera(), el.clientHeight));
            n.__label = s;
            return s;
          })
          .linkColor(function () { return VL.tok('--o3d-link-result') || '#FFD166'; })
          .linkOpacity(0.7).linkWidth(0.6)
          .linkDirectionalArrowLength(3.5).linkDirectionalArrowRelPos(1)
          .linkLabel(function (l) { return VL.esc(l.pred); })
          .onNodeClick(function (n) { var d = VL.docIdFromIri(n.iri); if (d) location.href = VL.href('network-3d.html#doc=' + encodeURIComponent(d)); })
          .warmupTicks(100).cooldownTicks(80)
          .onEngineStop(function () { fit(); });
        G.controls().addEventListener('change', cull);
        window.addEventListener('resize', function () {
          G.width(el.clientWidth).height(el.clientHeight);
          var w = VL.spriteWpp(G.camera(), el.clientHeight);
          G.graphData().nodes.forEach(function (n) { if (n.__label) n.__label.fit(w); });
          cull();
        });
      }
      G.width(el.clientWidth).height(el.clientHeight);
      G.graphData({ nodes: nodes, links: links });
      setTimeout(fit, 300);
    });
  }
  function fit() {
    if (!G) return;
    G.zoomToFit(400, 30);
    setTimeout(cull, 450);
  }
  /* hide labels that would overlap another label or be cut by the canvas edge */
  function cull() {
    if (!G) return;
    var el = VL.$('#graph-view'), W = el.clientWidth, H = el.clientHeight, cam = G.camera(), v = new THREE.Vector3();
    var k = H / (2 * Math.tan(cam.fov * Math.PI / 360)), placed = [];
    G.graphData().nodes.forEach(function (n) {
      var s = n.__label;
      if (!s) return;
      s.getWorldPosition(v);
      v.project(cam);
      var sx = (v.x + 1) / 2 * W, sy = (1 - v.y) / 2 * H, w = s.scale.x * k, h = s.scale.y * k;
      var b = { x0: sx - w / 2, x1: sx + w / 2, y0: sy - 1.3 * h, y1: sy - 0.3 * h };
      var ok = v.z < 1 && b.x0 > 3 && b.x1 < W - 3 && b.y0 > 3 && b.y1 < H - 3 && !placed.some(function (p) { return !(b.x1 + 3 < p.x0 || b.x0 - 3 > p.x1 || b.y1 + 2 < p.y0 || b.y0 - 2 > p.y1); });
      s.layers.set(ok ? 0 : 1);
      if (ok) placed.push(b);
    });
  }

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

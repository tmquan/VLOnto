/* VLOnto - ontology page: figures, module overview, alignments, concept schemes, downloads and the pyLODE iframe. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'ontology';
  var S = window.VLONTO.stats || {}, OG = window.VLONTO.ontology_graph;
  var O = S.ontology || {};
  VL.$('#ver').textContent = OG.version || VL.VERSION;

  function size(path) { var f = VL.fileListed(path); return f ? ' · ' + (f.bytes > 1048576 ? (Math.round(f.bytes / 104857.6) / 10) + ' MB' : Math.round(f.bytes / 1024) + ' KB') : ''; }
  VL.$('#dl-buttons').innerHTML = [
    ['downloads/ontology/vlonto.ttl', 'vlonto.ttl', 'OWL (Turtle)'],
    ['downloads/ontology/vlonto-shapes.ttl', 'vlonto-shapes.ttl', 'SHACL shapes'],
    ['downloads/ontology/vlonto-context.jsonld', 'vlonto-context.jsonld', 'JSON-LD context']
  ].map(function (d) {
    return '<a class="btn" href="' + d[0] + '" download>' + VL.ICON.download + '<span>' + VL.esc(d[2]) + ' · <span class="mono">' + VL.esc(d[1]) + '</span>' + VL.esc(size(d[0])) + '</span></a>';
  }).join('') + '<a class="btn btn-primary" href="index.html">' + VL.ICON.cube + '<span>Open in 3D</span></a>';

  function kpi(v, k) { return '<div class="kpi"><div class="v">' + v + '</div><div class="k">' + VL.esc(k) + '</div></div>'; }
  VL.$('#onto-kpis').innerHTML = kpi(VL.fmt(O.classes), 'classes') + kpi(VL.fmt(O.object_properties), 'object properties') +
    kpi(VL.fmt(O.datatype_properties), 'datatype properties') + kpi(VL.fmt(O.concept_schemes), 'concept schemes') +
    kpi(VL.fmt(O.aligned_external_terms), 'aligned external terms') + kpi('11', 'modules');

  var byMod = {}, propsByMod = {};
  OG.nodes.forEach(function (n) { if (n.kind !== 'external') (byMod[n.module] = byMod[n.module] || []).push(n); });
  OG.links.forEach(function (l) { if (l.type === 'property') (propsByMod[l.module] = propsByMod[l.module] || []).push(l); });
  var defs = {};
  (OG.modules || []).forEach(function (m) { defs[m.id] = m.definition_en; });
  VL.$('#module-grid').innerHTML = VL.MODULES.filter(function (m) { return m.id !== 'external'; }).map(function (m) {
    var terms = (byMod[m.id] || []).map(function (n) {
      return '<a class="term-chip" href="index.html#class=' + encodeURIComponent(n.id) + '" title="' + VL.esc(n.label_vi || '') + '">' + VL.esc(n.label_en) + (n.kind === 'scheme' ? ' (scheme)' : '') + '</a>';
    }).join('');
    var props = (propsByMod[m.id] || []).map(function (l) { return '<span class="term-chip mono">' + VL.esc(l.id) + '</span>'; }).join('');
    var nCls = (byMod[m.id] || []).filter(function (n) { return n.kind === 'class'; }).length;
    return '<div class="card module-card"><div class="mod-head"><span class="swatch" style="background:' + m.v + '"></span><h3>' + VL.esc(m.en) + '</h3></div>' +
      '<p class="vi" lang="vi">' + VL.esc(m.vi) + '</p><p>' + VL.esc(defs[m.id] || '') + '</p>' +
      '<p class="muted" style="margin:0">' + nCls + ' class' + (nCls === 1 ? '' : 'es') + ' · ' + (propsByMod[m.id] || []).length + ((propsByMod[m.id] || []).length === 1 ? ' object property' : ' object properties') + ' drawn as links</p>' +
      (terms ? '<div class="terms">' + terms + '</div>' : '') + (props && !terms ? '<div class="terms">' + props + '</div>' : '') + '</div>';
  }).join('');

  var nodeById = {};
  OG.nodes.forEach(function (n) { nodeById[n.id] = n; });
  var ext = OG.nodes.filter(function (n) { return n.kind === 'external'; });
  VL.$('#align-table').innerHTML = '<thead><tr><th>External term</th><th>VLOnto terms aligned to it</th></tr></thead><tbody>' + ext.map(function (e) {
    var src = OG.links.filter(function (l) { return l.type === 'alignment' && l.target === e.id; }).map(function (l) {
      var n = nodeById[l.source];
      return n ? '<a class="term-chip" href="index.html#class=' + encodeURIComponent(n.id) + '">' + VL.esc(n.label_en) + '</a>' : '<span class="term-chip">' + VL.esc(l.source) + '</span>';
    });
    return '<tr><td><span class="nowrap">' + VL.esc(e.label_en) + '</span><div class="sub mono">' + VL.esc(e.id) + '</div></td><td><div class="terms" style="display:flex;flex-wrap:wrap;gap:5px">' + src.join('') + '</div></td></tr>';
  }).join('') + '</tbody>';

  var schemes = OG.nodes.filter(function (n) { return n.kind === 'scheme'; });
  VL.$('#scheme-table').innerHTML = '<thead><tr><th>Scheme</th><th class="num">Concepts</th><th class="col-desc">Definition</th></tr></thead><tbody>' + schemes.map(function (s) {
    return '<tr><td><span>' + VL.esc(s.label_en) + '</span><div class="sub" lang="vi">' + VL.esc(s.label_vi || '') + '</div></td><td class="num">' + VL.fmt(s.instances) +
      '</td><td class="col-desc">' + VL.esc(s.definition_en || '') + '</td></tr>';
  }).join('') + '</tbody>';

  var frame = VL.$('#doc-frame'), done = false;
  function ready() { if (!done) { done = true; VL.fontsReady().then(function () { VL.setReady({ iframe: true }); }); } }
  frame.addEventListener('load', ready);
  setTimeout(ready, 6000);
})();

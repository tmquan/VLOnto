/* VLOnto - ontology page: figures, module overview, alignments, concept schemes, downloads and the pyLODE iframe.
   The page follows the language mode (js/i18n-pages.js, ontp.*); the pyLODE reference stays English in every mode (in VI
   a one-line note says so, css/site.css). Everything built here is rebuilt in place on 'vl:lang'. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'ontology';
  var S = window.VLONTO.stats || {}, OG = window.VLONTO.ontology_graph;
  var O = S.ontology || {}, esc = VL.esc, VERSION = OG.version || VL.VERSION;
  function langAttr(l) { return l && l !== VL.i18n.htmlLang() ? ' lang="' + l + '"' : ''; }
  /* sizes in the mode's number format (VL.fmt) */
  function size(path) {
    var f = VL.fileListed(path);
    return f ? ' · ' + (f.bytes > 1048576 ? VL.fmt(Math.round(f.bytes / 104857.6) / 10) + ' MB' : VL.fmt(Math.round(f.bytes / 1024)) + ' KB') : '';
  }
  /* a term's label in the mode: Vietnamese in VI (the English where there is none, marked lang="en"), else English;
     in EN–VI the Vietnamese label is the chip's tooltip */
  function label(n) {
    if (VL.lang() === 'vi' && n.label_vi) return { t: n.label_vi, l: 'vi' };
    return { t: n.label_en || n.id, l: 'en' };
  }
  function chip(n, suffix) {
    var lb = label(n), tip = VL.lang() === 'envi' && n.label_vi ? ' title="' + esc(n.label_vi) + '"' : '';
    return '<a class="term-chip" href="index.html#class=' + encodeURIComponent(n.id) + '"' + tip + '><span' + langAttr(lb.l) + '>' + esc(lb.t) + '</span>' +
      (suffix ? esc(suffix) : '') + '</a>';
  }
  /* definitions (modules, concept schemes) come from the dictionary (Vietnamese in VI) while the dictionary's English is
     the data's English; otherwise the data's English stays (marked lang="en" in VI) */

  var byMod = {}, propsByMod = {}, defs = {}, nodeById = {};
  OG.nodes.forEach(function (n) { if (n.kind !== 'external') (byMod[n.module] = byMod[n.module] || []).push(n); nodeById[n.id] = n; });
  OG.links.forEach(function (l) { if (l.type === 'property') (propsByMod[l.module] = propsByMod[l.module] || []).push(l); });
  (OG.modules || []).forEach(function (m) { defs[m.id] = m.definition_en; });
  var ext = OG.nodes.filter(function (n) { return n.kind === 'external'; });
  var schemes = OG.nodes.filter(function (n) { return n.kind === 'scheme'; });

  function render() {
    VL.$('#onto-lead').innerHTML = VL.UH('ontp.lead', null, { html: {
      ns: '<span class="mono">https://tmquan.github.io/<wbr>VLOnto/<wbr>ontology#</span>', prefix: '<span class="mono nowrap">vlo:</span>',
      release: '<span data-vl-release>' + esc(VL.releaseLabel()) + '</span>', version: '<span id="ver">' + esc(VERSION) + '</span>' } });

    VL.$('#dl-buttons').innerHTML = [
      ['downloads/ontology/vlonto.ttl', 'vlonto.ttl', 'ontp.dl.owl'],
      ['downloads/ontology/vlonto-shapes.ttl', 'vlonto-shapes.ttl', 'ontp.dl.shacl'],
      ['downloads/ontology/vlonto-context.jsonld', 'vlonto-context.jsonld', 'ontp.dl.jsonld']
    ].map(function (d) {
      return '<a class="btn" href="' + d[0] + '" download>' + VL.ICON.download + '<span>' + VL.UH(d[2]) + ' · <span class="mono">' + esc(d[1]) + '</span>' +
        esc(size(d[0])) + '</span></a>';
    }).join('') + '<a class="btn btn-primary" href="index.html">' + VL.ICON.cube + '<span>' + VL.UH('ontp.open3d') + '</span></a>';

    function kpi(v, key) { return '<div class="kpi"><div class="v">' + v + '</div><div class="k">' + VL.UH(key) + '</div></div>'; }
    VL.$('#onto-kpis').innerHTML = kpi(VL.fmt(O.classes), 'ontp.kpi.classes') + kpi(VL.fmt(O.object_properties), 'ontp.kpi.objectProperties') +
      kpi(VL.fmt(O.datatype_properties), 'ontp.kpi.datatypeProperties') + kpi(VL.fmt(O.concept_schemes), 'ontp.kpi.conceptSchemes') +
      kpi(VL.fmt(O.aligned_external_terms), 'ontp.kpi.alignedTerms') + kpi(VL.fmt(11), 'ontp.kpi.modules');

    /* module cards: the module's name in the mode's language (EN–VI: Vietnamese with the English gloss below) */
    var envi = VL.lang() === 'envi';
    VL.$('#module-grid').innerHTML = VL.MODULES.filter(function (m) { return m.id !== 'external'; }).map(function (m) {
      var terms = (byMod[m.id] || []).map(function (n) { return chip(n, n.kind === 'scheme' ? VL.U('ontp.scheme') : ''); }).join('');
      var props = (propsByMod[m.id] || []).map(function (l) { return '<span class="term-chip mono">' + esc(l.id) + '</span>'; }).join('');
      var nCls = (byMod[m.id] || []).filter(function (n) { return n.kind === 'class'; }).length, nProps = (propsByMod[m.id] || []).length;
      var hl = VL.lang() === 'en' ? 'en' : 'vi', e = VL.i18n.get('ontp.modDef.' + m.id);
      var d = e && defs[m.id] && e.en === VL.nfc(defs[m.id]) ? { t: VL.U('ontp.modDef.' + m.id), l: VL.lang() === 'vi' ? 'vi' : 'en' }
        : { t: defs[m.id] || '', l: 'en' };
      return '<div class="card module-card"><div class="mod-head"><span class="swatch" style="background:' + m.v + '"></span><h3' + langAttr(hl) + '>' +
        esc(hl === 'en' ? m.en : m.vi) + '</h3></div>' + (envi ? '<p class="gloss"' + langAttr('en') + '>' + esc(m.en) + '</p>' : '') +
        '<p' + langAttr(d.l) + '>' + esc(d.t) + '</p>' +
        '<p class="muted" style="margin:0">' + VL.UH('ontp.nClasses', { n: nCls === 1 ? 1 : VL.fmt(nCls) }) + ' · ' +
        VL.UH('ontp.nProperties', { n: nProps === 1 ? 1 : VL.fmt(nProps) }) + '</p>' +
        (terms ? '<div class="terms">' + terms + '</div>' : '') + (props && !terms ? '<div class="terms">' + props + '</div>' : '') + '</div>';
    }).join('');

    /* alignments: the external vocabularies' terms have English labels only (lang="en" in VI) */
    VL.$('#align-table').innerHTML = '<thead><tr><th>' + VL.UH('ontp.th.external') + '</th><th>' + VL.UH('ontp.th.aligned') + '</th></tr></thead><tbody>' + ext.map(function (e) {
      var src = OG.links.filter(function (l) { return l.type === 'alignment' && l.target === e.id; }).map(function (l) {
        var n = nodeById[l.source];
        return n ? chip(n) : '<span class="term-chip">' + esc(l.source) + '</span>';
      });
      return '<tr><td><span class="nowrap"' + langAttr('en') + '>' + esc(e.label_en) + '</span><div class="sub mono">' + esc(e.id) + '</div></td>' +
        '<td><div class="terms" style="display:flex;flex-wrap:wrap;gap:5px">' + src.join('') + '</div></td></tr>';
    }).join('') + '</tbody>';

    /* concept schemes: the name in the mode's language (EN–VI: Vietnamese above the English), the definition */
    VL.$('#scheme-table').innerHTML = '<thead><tr><th>' + VL.UH('ontp.th.scheme') + '</th><th class="num">' + VL.UH('ontp.th.concepts') + '</th><th class="col-desc">' +
      VL.UH('ontp.th.definition') + '</th></tr></thead><tbody>' + schemes.map(function (s) {
        var local = s.id.split(':').pop(), e = VL.i18n.get('ontp.schemeDef.' + local), name;
        var d = e && s.definition_en && e.en === VL.nfc(s.definition_en) ? { t: VL.U('ontp.schemeDef.' + local), l: VL.lang() === 'vi' ? 'vi' : 'en' }
          : { t: s.definition_en || '', l: 'en' };
        if (VL.lang() === 'en' || !s.label_vi) name = '<span' + langAttr('en') + '>' + esc(s.label_en) + '</span>';
        else if (VL.lang() === 'vi') name = '<span>' + esc(s.label_vi) + '</span>';
        else name = '<span lang="vi">' + esc(s.label_vi) + '</span><div class="sub">' + esc(s.label_en) + '</div>';
        return '<tr><td>' + name + '</td><td class="num">' + VL.fmt(s.instances) + '</td><td class="col-desc"' + langAttr(d.l) + '>' + esc(d.t) + '</td></tr>';
      }).join('') + '</tbody>';

    VL.$('#ref-lead').innerHTML = VL.UH('ontp.ref.lead', null, { html: { ttl: '<span class="mono">vlonto.ttl</span>',
      link: '<a href="ontology/vlonto.html" target="_blank" rel="noopener">' + esc(VL.U('ontp.ref.open')) + '</a>' } });
    VL.$('#doc-frame').setAttribute('title', VL.U('ontp.ref.frame'));
    VL.$('#onto-lead').setAttribute('data-vl-text', 'ok');
    VL.$('#ref-lead').setAttribute('data-vl-text', 'ok');
    M.ontologyLang = VL.lang();
  }
  render();
  /* the language switch: rebuild in place (the iframe follows by itself through js/i18n.js postMessage) */
  document.addEventListener('vl:lang', function () { render(); M.ontologyLangRenders = (M.ontologyLangRenders || 0) + 1; });

  var frame = VL.$('#doc-frame'), done = false;
  function ready() { if (!done) { done = true; VL.fontsReady().then(function () { VL.setReady({ iframe: true }); }); } }
  frame.addEventListener('load', ready);
  setTimeout(ready, 6000);
})();

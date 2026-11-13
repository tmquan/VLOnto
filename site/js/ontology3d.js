/* VLOnto - 3D Ontology Playground (3d-force-graph over data/ontology_graph.js; SPARQL via js/sparql-core.js).
   Classes are spheres (size ~ log instance count), concept schemes octahedra, aligned external terms icosahedra.
   Drawn like the figures of the paper (arXiv:2611.11426, Fig. 1 and Fig. 6; js/paper3d.js): white figure ground, soft
   translucent spheres in the paper's class colours (Văn bản · Work, Điều · Article, Thuật ngữ · Term, ...) or else in
   the module colour, thin class-tinted links fading with depth, bilingual call-outs (Libertinus Sans, white box, thin
   grey leader) and the selection's chain and neighbourhood, or a CONSTRUCT result, as the traced path: a navy core over a
   pale-gold halo with everything else faded. Labels are canvas sprites (js/labels3d.js) drawn at a constant pixel size and
   culled in screen space so that no two labels overlap and no label is cut by the canvas edge or hidden under an overlay.
   Text follows the language mode of js/i18n.js (docs/i18n.md; dictionary js/i18n-3d.js, keys o3d.*): call-outs and legend
   in one language or as "Tiếng Việt · English" pairs, panel labels, status lines and the query drawer in one language; the
   per-view label toggle of v1 is gone. A mode change ('vl:lang') rebuilds them in place and keeps the camera, the
   selection, the query result and the filters. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome({ scene: true });
  M.page = 'ontology-3d';
  M.paperStyle = true;

  /* release scope (js/common.js VL.releaseScope): the terms populated from a later release (in v1 the judiciary module
     and vlo:Court) are left out of the playground; a note under the module chips says when they come */
  var OG0 = window.VLONTO.ontology_graph, SCOPE = VL.releaseScope(OG0), OG = {};
  Object.keys(OG0).forEach(function (k) { OG[k] = OG0[k]; });
  OG.nodes = SCOPE.nodes;
  OG.links = SCOPE.links;
  M.releaseScope = { release: SCOPE.release, hidden: SCOPE.hidden, hiddenProperties: SCOPE.hiddenProperties, hiddenLinks: SCOPE.hiddenLinks,
    laterModules: SCOPE.laterModules, nodes: OG.nodes.length, links: OG.links.length };
  var EXAMPLES = ((window.VLONTO.sparql_examples || {}).queries) || [];
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host');
  var panel = VL.$('#panel'), drawer = VL.$('#drawer'), legendEl = VL.$('#legend'), statusEl = VL.$('#status');
  /* the labels follow the global language mode (VL.lang()) */
  var state = {
    modules: {}, showExternal: true, showSchemes: true,
    links: { subClassOf: true, property: true, alignment: true, inScheme: true },
    particles: true, selected: null, selectedLink: null, view: 'ontology', cm: 'overlay', legendOpen: !VL.isMobile()
  };
  VL.MODULES.forEach(function (m) { if (!SCOPE.laterModules[m.id]) state.modules[m.id] = true; });

  /* ------------------------------------------------------------------ data */
  var nodes = OG.nodes.map(function (n) {
    var o = {};
    Object.keys(n).forEach(function (k) { o[k] = n[k]; });
    o.label_en = VL.nfc(n.label_en || n.id);
    o.label_vi = n.label_vi ? VL.nfc(n.label_vi) : null;
    o.definition_en = n.definition_en ? VL.nfc(n.definition_en) : null;
    o.definition_vi = n.definition_vi ? VL.nfc(n.definition_vi) : null;
    o.__r = radius(o);
    return o;
  });
  var byId = {};
  nodes.forEach(function (n) { byId[n.id] = n; });
  var links = OG.links.map(function (l, i) {
    var o = { key: 'L' + i };
    Object.keys(l).forEach(function (k) { o[k] = l[k]; });
    o.label_en = VL.nfc(l.label_en || '');
    o.label_vi = VL.nfc(l.label_vi || '');
    return o;
  });
  var linkByKey = {};
  links.forEach(function (l) { linkByKey[l.key] = l; });
  function sid(x) { return typeof x === 'object' ? x.id : x; }
  var outProps = {}, inProps = {}, subOf = {}, superOf = {}, alignOut = {}, alignIn = {}, schemeOf = {}, schemeMembers = {};
  function push(map, k, v) { (map[k] = map[k] || []).push(v); }
  links.forEach(function (l) {
    var s = sid(l.source), t = sid(l.target);
    if (l.type === 'property') { push(outProps, s, l); push(inProps, t, l); }
    else if (l.type === 'subClassOf') { push(subOf, s, t); push(superOf, t, s); }
    else if (l.type === 'alignment') { push(alignOut, s, l); push(alignIn, t, l); }
    else if (l.type === 'inScheme') { push(schemeOf, s, t); push(schemeMembers, t, s); }
  });
  /* parallel links and self-loops get their own curvature and rotation */
  (function () {
    var cnt = {}, idx = {};
    links.forEach(function (l) { var k = [sid(l.source), sid(l.target)].sort().join('|'); cnt[k] = (cnt[k] || 0) + 1; });
    links.forEach(function (l) {
      var s = sid(l.source), t = sid(l.target), k = [s, t].sort().join('|');
      var i = idx[k] = (idx[k] || 0) + 1, n = cnt[k];
      if (s === t) { l.curvature = 0.55 + 0.18 * (i - 1); l.rotation = (i - 1) * 2 * Math.PI / Math.max(1, n); }
      else if (n > 1) { l.curvature = 0.14 + 0.12 * Math.floor((i - 1) / 2); l.rotation = (i - 1) * 2 * Math.PI / n; }
      else { l.curvature = 0; l.rotation = 0; }
    });
  })();
  var baseData = { nodes: nodes, links: links };
  M.ontologyNodes = nodes.length;
  M.ontologyLinks = links.length;

  function radius(n) {
    if (n.inst) return 2.6;
    if (n.kind === 'external') return 3.4;
    if (n.kind === 'scheme') return 3.6 + 0.9 * Math.log10((n.instances || 0) + 1);
    return 3.4 + 1.9 * Math.log10((n.instances || 0) + 1);
  }
  /* paper class of a node (null when it has none): classes by their CURIE, records of the KG by their class */
  function paperKey(n) {
    if (n.inst) return n.cls ? VL.paperClassKey(n.cls, true) : null;
    return n.kind === 'class' ? VL.paperClassKey(n.id) : null;
  }
  function nodeColor(n) {
    var k = paperKey(n);
    return (k && P.cls[k]) || VL.moduleColor(n.module || 'provenance');
  }
  function nodeVar(n) { var k = paperKey(n); return k ? VL.PAPER_CLASS[k].v : VL.moduleVar(n.module || 'provenance'); }
  function kindKey(n) { return n.inst ? 'o3d.kind.instance' : ({ 'class': 'o3d.kind.class', external: 'o3d.kind.external', scheme: 'o3d.kind.scheme' }[n.kind] || null); }
  function kindLabel(n) { var k = kindKey(n); return k ? VL.U(k) : n.kind; }            // one language (tooltips, search)
  function kindHtml(n) { var k = kindKey(n); return k ? VL.TH(k) : VL.esc(n.kind); }    // a pair (panel badge)
  function namePair(n) { return VL.pair(n.label_vi || '', n.label_en || ''); }
  /* a data value of unknown language (a record's label, title or literal): marked lang="vi" when it is Vietnamese and
     the page is not, so screen readers read it in Vietnamese */
  var VI_TEXT = /[àáâãèéêìíòóôõùúýăđĩũơưạ-ỹ]/i;
  function dataHtml(s) { s = VL.nfc(String(s == null ? '' : s)); return VI_TEXT.test(s) && VL.i18n.htmlLang() !== 'vi' ? '<span lang="vi">' + VL.esc(s) + '</span>' : VL.esc(s); }
  /* the short name of a node in one language (chips, tooltips, search): EN and EN–VI English, VI Vietnamese */
  function labelText(n) {
    if (n.inst) return instShort(n);
    return VL.U(namePair(n));
  }
  function chipText(n) { return n.inst ? dataHtml(instShort(n)) : VL.UH(namePair(n)); }
  /* a record of a CONSTRUCT result: its number, else its label in the mode (the ontology's @vi label where there is
     one), else its title */
  function instShort(n) { return VL.short(n.number || (n.label || n.label_vi ? VL.U(VL.pair(n.label_vi || '', n.label || '')) : '') || n.title || n.id, 28); }
  /* call-out lines in the language mode (js/paper3d.js VL.paperLines): EN–VI "Tiếng Việt · English" on one line when
     short, else Vietnamese over English; EN or VI one line */
  function labelLines(n) {
    M.labelsLang = VL.lang();
    if (n.inst) {
      if (!n.number && (n.label || n.label_vi)) return VL.paperLines(VL.short(n.label_vi || '', 28), VL.short(n.label || '', 28), P);
      return [[{ text: instShort(n), color: P.ink }]];
    }
    return VL.paperLines(n.label_vi, n.label_en, P, { secondary: n.kind === 'external' });
  }

  /* ------------------------------------------------------------------ visibility */
  function nodeVisible(n) {
    if (!n) return false;
    if (n.inst) return true;
    if (n.kind === 'external') return state.showExternal;
    if (n.kind === 'scheme' && !state.showSchemes) return false;
    return state.modules[n.module] !== false;
  }
  function linkVisible(l) {
    if (l.type === 'result' || l.type === 'instance') return nodeVisible(nodeOf(l.source)) && nodeVisible(nodeOf(l.target));
    if (state.links[l.type] === false) return false;
    if (l.type === 'property' && state.modules[l.module] === false) return false;
    return nodeVisible(nodeOf(l.source)) && nodeVisible(nodeOf(l.target));
  }
  var current = { byId: byId };
  function nodeOf(x) { return typeof x === 'object' ? x : current.byId[x]; }

  /* ------------------------------------------------------------------ highlight state */
  /* hl.nodes / hl.links: the selection's neighbourhood and chain, or the CONSTRUCT result (everything else fades).
     hl.trace: the links drawn as the traced path (navy core over the gold halo) - all of them when there are few
     (hl.max), else only the chain up the hierarchy and the links to a hovered node, as in the paper, where only the
     traced path is dark; the other highlighted links stay thin lines in their own pastel colours. */
  var TRACE_ALL_MAX = 6, RESULT_TRACE_MAX = 12;
  var hl = { nodes: null, links: null, chain: null, max: TRACE_ALL_MAX, trace: null, traceNodes: null, hoverNode: null, hoverLinks: null };
  function hlActive() { return !!hl.nodes; }
  function inHl(l) { return !!hl.links && hl.links.has(l); }
  function setHighlight(nodeSet, linkSet, o) {
    o = o || {};
    hl.nodes = nodeSet;
    hl.links = linkSet;
    hl.chain = o.chain || null;
    hl.max = o.max || TRACE_ALL_MAX;
    hl.hoverNode = null;
    hl.hoverLinks = null;
    M.hoverTrace = 0;
    computeTrace();
    applyHighlight();
  }
  function computeTrace() {
    hl.trace = null;
    hl.traceNodes = new Set();
    if (!hl.links) return;
    if (hl.links.size <= hl.max) hl.trace = hl.links;
    else {
      hl.trace = new Set();
      if (hl.chain) hl.chain.forEach(function (l) { if (hl.links.has(l)) hl.trace.add(l); });
      if (hl.hoverLinks) hl.hoverLinks.forEach(function (l) { hl.trace.add(l); });
    }
    hl.trace.forEach(function (l) { hl.traceNodes.add(nodeOf(l.source)); hl.traceNodes.add(nodeOf(l.target)); });
    M.emphLinks = hl.links.size - hl.trace.size;
  }
  /* call-outs that always stay: the selected node, the nodes of the traced path and the hovered node */
  function isMust(n) { return state.selected === n || hl.hoverNode === n || (!!hl.traceNodes && hl.traceNodes.has(n)); }
  /* hovering a node of the highlight traces its links to the selection (for a CONSTRUCT result: its own links, when at
     most RESULT_TRACE_MAX) */
  function setHover(n) {
    var links = null;
    if (n && hl.links && hl.nodes && hl.nodes.has(n) && n !== state.selected) {
      var ls = [];
      hl.links.forEach(function (l) {
        var a = nodeOf(l.source), b = nodeOf(l.target);
        if (state.selected ? ((a === n && b === state.selected) || (b === n && a === state.selected)) : (a === n || b === n)) ls.push(l);
      });
      if (ls.length && ls.length <= RESULT_TRACE_MAX) links = new Set(ls);
    }
    var node = links ? n : null;
    if (node === hl.hoverNode) return;
    hl.hoverNode = node;
    hl.hoverLinks = links;
    M.hoverTrace = links ? links.size : 0;
    computeTrace();
    refreshLinkStyles();
    updateTrace();
    scheduleCull();
  }
  /* soft pastel sphere (lit from the upper left, js/paper3d.js), a rim 16 % darker drawn by a slightly larger back-face
     hull, and a pale-gold halo around the selected node; context outside the highlight fades towards the ground */
  function rimHex(hex, f) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim()), n = m ? parseInt(m[1], 16) : 0x888888;
    var c = [n >> 16, (n >> 8) & 255, n & 255].map(function (v) { return Math.round(v * f); });
    return '#' + c.map(function (v) { return (v < 16 ? '0' : '') + v.toString(16); }).join('');
  }
  function styleNode(n, on, sel) {
    var col = nodeColor(n), s = n.__r * (sel ? 1.3 : 1);
    var m = n.__mesh.material;
    m.color.set(col);
    m.opacity = on ? 0.95 : P.fade;
    m.depthWrite = on;
    n.__mesh.scale.setScalar(s);
    if (n.__rim) {
      n.__rim.material.color.set(rimHex(col, P.dark ? 0.72 : 0.84));
      n.__rim.material.opacity = on ? 0.95 : P.fade * 0.7;
      n.__rim.material.depthWrite = on;
      n.__rim.scale.setScalar(s * 1.07);
    }
    if (n.__halo) {
      n.__halo.visible = sel;
      n.__halo.material.color.set(P.halo);
      n.__halo.scale.setScalar(s * 1.34);
    }
    if (n.__label && n.__labSel !== sel) { n.__labSel = sel; n.__label.setStyle(labelOpts(n)); }
  }
  function applyHighlight() {
    current.nodes.forEach(function (n) {
      if (!n.__mesh) return;
      styleNode(n, !hl.nodes || hl.nodes.has(n), state.selected === n);
    });
    refreshLinkStyles();
    updateTrace();
    scheduleCull();
  }
  function refreshLinkStyles() {
    if (!graph) return;
    graph.linkColor(graph.linkColor());
    graph.linkDirectionalParticles(graph.linkDirectionalParticles());
    graph.linkDirectionalParticleColor(graph.linkDirectionalParticleColor());
    graph.linkWidth(graph.linkWidth());
    graph.linkDirectionalArrowColor(graph.linkDirectionalArrowColor());
  }
  /* the traced path (hl.trace) as a navy core over a pale-gold halo, at constant pixel width and following curved links;
     thinner for large small-result traces, never wider than VL.TRACE_W */
  var trace = null;
  function updateTrace() {
    if (!graph) return;
    if (!trace) { trace = VL.TraceLines({ depthTest: true, renderOrder: 8 }); graph.scene().add(trace.object); }
    var paths = [];
    if (hl.trace) hl.trace.forEach(function (l) {
      if (!linkVisible(l)) return;
      var pts = VL.linkPoints(l, 16);
      if (pts) paths.push(pts);
    });
    trace.setStyle(VL.traceStyle(P, paths.length > 150 ? 0.62 : (paths.length > 60 ? 0.8 : 1)));
    trace.setPaths(paths);
    M.traceLinks = paths.length;
    M.traceSegments = trace.count();
  }

  /* ------------------------------------------------------------------ labels: constant pixel size + screen-space culling */
  /* call-out heights in CSS px for one line (the text itself is about px / 1.68) */
  var labelPx = { 'class': 23, scheme: 22, external: 21, instance: 21 };
  var SELECTED_PX = 26;
  function worldPerPx() { return VL.spriteWpp(graph.camera(), host.clientHeight); }
  /* scene colours of the current theme (css/site.css: the paper style tokens, --scene-bg, --o3d-link-*) */
  var TH = {}, P = {};
  function readTheme() {
    P = VL.paperTheme();
    TH = {
      bg: P.bg,
      link: { subClassOf: VL.tok('--o3d-link-subclass'), alignment: VL.tok('--o3d-link-alignment'), inScheme: VL.tok('--o3d-link-inscheme'),
        instance: VL.tok('--o3d-link-instance'), result: VL.tok('--o3d-link-result') },
      linkDefault: VL.tok('--o3d-link-default') || '#b8bdc6', linkDim: VL.tok('--o3d-link-dim') || '#eceef2'
    };
    M.sceneBg = TH.bg;
    M.traceCore = P.core;
  }
  readTheme();
  /* call-out of a node: the paper's box and greys, its lines, a leader to the node; the selected node's call-out is
     pale gold with a border in the core colour */
  function labelOpts(n) {
    var o = VL.paperCallout(P, state.selected === n);
    o.lines = labelLines(n);
    o.weight = '400';
    return o;
  }
  function makeLabel(n) {
    var o = labelOpts(n);
    o.px = labelPx[n.inst ? 'instance' : n.kind] || 21;
    var s = VL.TextSprite(labelText(n), o);
    n.__labSel = state.selected === n;
    s.__basePx = s.__px;
    s.position.set(0, 0, 0);          // anchored at the node; VL.Callouts sets the box offset and the leader
    s.layers.set(1);                  // hidden until placed
    s.fit(worldPerPx());
    return s;
  }
  function resizeLabels() {
    var w = worldPerPx();
    current.nodes.forEach(function (n) {
      var s = n.__label;
      if (!s) return;
      s.__px = (state.selected === n) ? SELECTED_PX : s.__basePx;
      s.fit(w);
    });
  }
  function relabel() {
    current.nodes.forEach(function (n) { if (n.__label) n.__label.setLines(labelLines(n)); });
    M.labelsLang = VL.lang();
    scheduleCull();
  }
  function priority(n) {
    if (state.selected === n) return 1e12;
    var p = 0;
    if (hl.nodes && hl.nodes.has(n)) p += 1e9;
    if (n.inst) p += 5e6;
    if (n.kind === 'class') p += 1e6 + (n.instances || 0) / 10;
    else if (n.kind === 'scheme') p += 5e5 + (n.instances || 0) / 1e3;
    else p += 1e5;
    return p;
  }
  /* screen-space declutter shared with the legal network and the CONSTRUCT view (js/paper3d.js VL.Callouts): call-outs
     sit in clear space on thin leaders, never over a node or a link and never over each other; the selected node and
     the nodes of the traced path always keep theirs. Ink = every visible node disc and every link that is not faded. */
  var callouts = null;
  function nodeR(n) { return n.__r * (state.selected === n ? 1.3 * 1.34 : 1.07); }
  function calloutItems() {
    var out = [];
    current.nodes.forEach(function (n) {
      var s = n.__label;
      if (!s) return;
      var off = !nodeVisible(n) || !n.__obj || !isFinite(n.x) || (hlActive() && !hl.nodes.has(n));
      out.push({ id: n.id, sprite: s, pri: priority(n), must: !off && isMust(n), sel: !off && state.selected === n, r: nodeR(n), off: off });
    });
    return out;
  }
  function calloutInk() {
    var discs = [], paths = [];
    current.nodes.forEach(function (n) {
      if (nodeVisible(n) && n.__obj && isFinite(n.x)) discs.push({ id: n.id, x: n.x, y: n.y, z: n.z, r: nodeR(n) });
    });
    graph.graphData().links.forEach(function (l) {
      if (!linkVisible(l) || (hlActive() && !inHl(l))) return;
      var pts = VL.linkPoints(l, 6);
      if (pts) paths.push(pts);
    });
    return { discs: discs, paths: paths };
  }
  function scheduleCull() {
    if (!graph) return;
    if (!callouts) {
      callouts = VL.Callouts({
        camera: function () { return graph.camera(); },
        size: function () { return { w: host.clientWidth, h: host.clientHeight }; },
        items: calloutItems, ink: calloutInk, ui: obstacles,
        leaderColor: function () { return P.leader; },
        metrics: M, key: 'callouts',
        onDone: function (st) { M.labelsShown = st.shown; M.labelsHidden = st.hidden; updateFog(); }
      });
    }
    callouts.schedule();
  }
  function cullLabels() { if (graph) { scheduleCull(); callouts.run(); } }
  function obstacles() {
    var hr = host.getBoundingClientRect(), out = [];
    ['#legend', '#hint', '.stage-tools', '#status', '#panel'].forEach(function (sel) {
      var e = VL.$(sel, stage);
      if (!e || e.classList.contains('hidden') || e.offsetParent === null) return;
      var r = e.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      out.push({ x0: r.left - hr.left - 4, x1: r.right - hr.left + 4, y0: r.top - hr.top - 4, y1: r.bottom - hr.top + 4 });
    });
    return out;
  }

  /* ------------------------------------------------------------------ node objects */
  var GEO = null;
  function makeNode(n) {
    if (!GEO) GEO = { sphere: new THREE.SphereGeometry(1, 32, 20), ico: new THREE.IcosahedronGeometry(1, 0), oct: new THREE.OctahedronGeometry(1, 0) };
    var g = new THREE.Group();
    var flat = n.kind === 'external' || n.kind === 'scheme';
    var geo = n.kind === 'external' ? GEO.ico : (n.kind === 'scheme' ? GEO.oct : GEO.sphere);
    var mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: 0xffffff, transparent: true, opacity: 0.95, flatShading: flat }));
    mesh.renderOrder = 1;
    var rim = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.BackSide, transparent: true, opacity: 0.95 }));
    var halo = new THREE.Mesh(GEO.sphere, new THREE.MeshBasicMaterial({ color: 0xecc890, side: THREE.BackSide, transparent: true, opacity: 0.9, depthWrite: false }));
    halo.visible = false;
    g.add(halo);
    g.add(rim);
    g.add(mesh);
    n.__mesh = mesh;
    n.__rim = rim;
    n.__halo = halo;
    var lab = makeLabel(n);
    g.add(lab);
    n.__label = lab;
    n.__obj = g;
    styleNode(n, !hl.nodes || hl.nodes.has(n), state.selected === n);
    return g;
  }

  /* ------------------------------------------------------------------ link styling */
  /* thin links tinted by class, as in the paper: a subclass link takes the colour of the subclass, an object property
     the colour of its module; the highlighted ones lie under the traced path (core colour, hairline width) */
  function linkBaseColor(l) {
    if (l.type === 'property') return VL.moduleColor(l.module);
    if (l.type === 'subClassOf') { var s = nodeOf(l.source); return s ? rimHex(nodeColor(s), P.dark ? 1 : 0.9) : TH.link.subClassOf; }
    return TH.link[l.type] || TH.linkDefault;
  }
  function inTrace(l) { return hlActive() && !!hl.trace && hl.trace.has(l); }
  /* a highlighted link that is not traced: its own pastel (a CONSTRUCT result link: the colour of its predicate), a
     little deeper on the white ground so the thin line reads */
  function emphColor(l) {
    var c = l.type === 'result' ? VL.predColor(l.pred) : linkBaseColor(l);
    return P.dark ? c : rimHex(c, 0.9);
  }
  function linkColor(l) {
    if (inTrace(l)) return P.core;
    if (inHl(l)) return emphColor(l);
    if (hlActive()) return TH.linkDim;
    return linkBaseColor(l);
  }
  function linkWidth(l) {
    if (inTrace(l)) return 0;
    if (inHl(l)) return l.type === 'subClassOf' ? 1 : 0.8;
    if (l.type === 'subClassOf') return 0.6;
    if (l.type === 'property' || l.type === 'result') return 0.42;
    return 0;
  }
  function linkParticles(l) {
    if (!state.particles) return 0;
    if (hlActive() && !inTrace(l)) return 0;
    return (l.type === 'property' || l.type === 'result') ? 2 : 0;
  }
  function particleColor(l) { return inTrace(l) ? P.halo : linkBaseColor(l); }
  function linkTooltip(l) {
    var s = nodeOf(l.source), t = nodeOf(l.target);
    var name = l.type === 'result' ? VL.esc(l.pred) : (l.type === 'instance' ? VL.UH('o3d.instanceOf') : VL.UH(VL.pair(l.label_vi, l.label_en)));
    return '<b>' + name + '</b><br><span class="t-sub">' + (s ? chipText(s) : '') + ' → ' + (t ? chipText(t) : '') + '</span>';
  }
  function nodeTooltip(n) {
    if (n.inst) return '<b>' + (n.number ? VL.esc(n.number) : chipText(n)) + '</b>' + (n.title ? '<br><span class="t-sub" lang="vi">' + VL.esc(VL.short(n.title, 70)) + '</span>' : '');
    var m = VL.MODULE[n.module] || {};
    return '<b>' + VL.TH(namePair(n)) + '</b>' +
      '<br><span class="t-sub">' + VL.esc(kindLabel(n)) + ' · ' + (m.en ? VL.UH(m) : VL.esc(n.module)) +
      (n.instances != null ? ' · ' + VL.UH('o3d.tip.instances', { n: n.instances === 1 ? 1 : VL.fmt(n.instances) }) : '') + '</span>';
  }

  /* ------------------------------------------------------------------ layout forces
     Spread in 3D: each module (with terms in this release) has an anchor on a Fibonacci ellipsoid (200 x 150 x 200) that
     pulls its terms gently, external terms sit on a shell outside (r 340), classes repel strongly and links are long by
     kind (LAYOUT). The layout is deterministic: d3-force-3d's seeded random source, the data's order, and all its ticks
     run at load (300 warm-up ticks bring alpha below alphaMin, so the engine stops at its first frame: no ticks bound
     to a time limit), so every browser and machine draws the same graph. */
  var LAYOUT = {
    charge: { 'class': -220, scheme: -100, external: -100, instance: -20 },
    distance: { subClassOf: 42, inScheme: 48, alignment: 80, property: 112, instance: 22, result: 46 },
    strength: { subClassOf: 0.6, inScheme: 0.45, alignment: 0.28, property: 0.07, instance: 0.9, result: 0.5 },
    anchor: [200, 150], pull: 0.05, shell: 340, shellPull: 0.05, ticks: 300, alphaDecay: 0.0228, alphaMin: 0.001, velocityDecay: 0.4
  };
  var anchors = {};
  (function () {
    var present = {};
    OG.nodes.forEach(function (n) { present[n.module] = true; });
    var ids = VL.MODULES.map(function (m) { return m.id; }).filter(function (id) { return id !== 'external' && id !== 'citation-basis' && present[id]; });
    var N = ids.length, ax = LAYOUT.anchor[0], ay = LAYOUT.anchor[1];
    ids.forEach(function (id, i) {
      var k = i + 0.5, phi = Math.acos(1 - 2 * k / N), th = Math.PI * (1 + Math.sqrt(5)) * k;
      anchors[id] = { x: ax * Math.cos(th) * Math.sin(phi), y: ay * Math.cos(phi), z: ax * Math.sin(th) * Math.sin(phi) };
    });
  })();
  function clusterForce() {
    var ns = [];
    function f(alpha) {
      ns.forEach(function (n) {
        if (n.fx != null || n.inst) return;
        if (n.kind === 'external') {
          var r = Math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z) || 1, kk = (LAYOUT.shell - r) / r * LAYOUT.shellPull * alpha;
          n.vx += n.x * kk; n.vy += n.y * kk; n.vz += n.z * kk;
          return;
        }
        var a = anchors[n.module];
        if (!a) return;
        var k = LAYOUT.pull * alpha;
        n.vx += (a.x - n.x) * k; n.vy += (a.y - n.y) * k; n.vz += (a.z - n.z) * k;
      });
    }
    f.initialize = function (x) { ns = x; };
    return f;
  }

  /* ------------------------------------------------------------------ graph */
  var graph = null;
  current.nodes = nodes;
  function stageSize() { return { w: Math.max(50, host.clientWidth), h: Math.max(50, host.clientHeight) }; }
  function build() {
    var sz = stageSize();
    graph = new ForceGraph3D(host, { controlType: 'orbit', rendererConfig: { antialias: true, alpha: false, preserveDrawingBuffer: true } })
      .width(sz.w).height(sz.h)
      .backgroundColor(TH.bg)
      .showNavInfo(false)
      .nodeRelSize(1)
      .nodeVal(function (n) { return Math.pow(n.__r, 3); })
      .nodeLabel(nodeTooltip)
      .nodeThreeObject(makeNode)
      .nodeThreeObjectExtend(false)
      .nodeVisibility(nodeVisible)
      .linkVisibility(linkVisible)
      .linkColor(linkColor)
      .linkWidth(linkWidth)
      .linkOpacity(P.linkOpacity)
      .linkResolution(8)
      .linkCurvature('curvature')
      .linkCurveRotation('rotation')
      .linkDirectionalArrowLength(function (l) { return (l.type === 'property' || l.type === 'subClassOf' || l.type === 'result') ? 4.2 : 0; })
      .linkDirectionalArrowRelPos(1)
      .linkDirectionalArrowColor(linkColor)
      .linkDirectionalParticles(linkParticles)
      .linkDirectionalParticleWidth(1.7)
      .linkDirectionalParticleSpeed(0.0045)
      .linkDirectionalParticleColor(particleColor)
      .linkLabel(linkTooltip)
      .linkHoverPrecision(2.5)
      .onNodeClick(function (n) { select(n, true); })
      .onLinkClick(function (l) { selectLink(l); })
      .onBackgroundClick(function () { clearSelection(); })
      .onNodeHover(function (n) { host.style.cursor = n ? 'pointer' : ''; M.hover = n ? n.id : null; setHover(n); })
      .onLinkHover(function (l) { host.style.cursor = l ? 'pointer' : ''; })
      .onEngineTick(function () { if (hl.trace && hl.trace.size) updateTrace(); scheduleCull(); })
      .onEngineStop(onEngineStop)
      .warmupTicks(LAYOUT.ticks)
      .cooldownTicks(120)                // ticks after a reheat (a dragged node); the first layout ends in the warm-up
      .d3AlphaMin(LAYOUT.alphaMin)
      .d3AlphaDecay(LAYOUT.alphaDecay)
      .d3VelocityDecay(LAYOUT.velocityDecay);
    graph.d3Force('charge').strength(function (n) { return LAYOUT.charge[n.inst ? 'instance' : n.kind] || LAYOUT.charge.scheme; });
    graph.d3Force('link')
      .distance(function (l) { return LAYOUT.distance[l.type] || 80; })
      .strength(function (l) { return LAYOUT.strength[l.type] || 0.3; });
    M.layout = { ticks: LAYOUT.ticks, anchors: Object.keys(anchors).length, deterministic: true };
    graph.d3Force('cluster', clusterForce());
    /* the paper's light (upper left of the screen) and depth fade to the ground colour */
    lights = VL.paperLights(P.dark);
    graph.lights([lights.ambient]);
    VL.attachCameraLight(graph.scene(), graph.camera(), lights.directional);
    fog = VL.paperFog(graph.scene(), TH.bg);
    graph.graphData(baseData);
    current.nodes = nodes;
    current.byId = byId;
    graph.controls().addEventListener('change', scheduleCull);
    graph.controls().addEventListener('start', function () { hideHint(); });
    M.webglRenderer = rendererName();
    fitView(0);
    window.VLApp.graph = graph;
  }
  var lights = null, fog = null, sceneR = 200;
  function updateFog() {
    if (!graph || !fog) return;
    VL.fitFog(fog, graph.camera().position.distanceTo(graph.controls().target), sceneR);
  }
  function rendererName() {
    try {
      var gl = graph.renderer().getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    } catch (e) { return null; }
  }

  /* the camera frames every visible node (or the subset): looking along dir at the middle of their extents across the
     view, from the distance at which each node, with its radius and room for a leader, projects inside 90 % of the frame
     (80 % on a narrow stage, where call-outs need the sides) */
  function fitView(ms, subset) {
    var vis = (subset || current.nodes).filter(nodeVisible).filter(function (n) { return isFinite(n.x); });
    if (!vis.length) return;
    var cam = graph.camera(), sz = stageSize(), m = sz.w < 700 ? 0.8 : 0.9;
    var tv = Math.tan(cam.fov * Math.PI / 360), th = tv * sz.w / sz.h;
    var dir = new THREE.Vector3(0.32, 0.3, 1).normalize(), right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), dir).normalize();
    var up = new THREE.Vector3().crossVectors(dir, right), c = new THREE.Vector3(), v = new THREE.Vector3();
    vis.forEach(function (n) { c.x += n.x; c.y += n.y; c.z += n.z; });
    c.multiplyScalar(1 / vis.length);
    var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    vis.forEach(function (n) {
      v.set(n.x - c.x, n.y - c.y, n.z - c.z);
      var x = v.dot(right), y = v.dot(up);
      x0 = Math.min(x0, x - n.__r); x1 = Math.max(x1, x + n.__r); y0 = Math.min(y0, y - n.__r); y1 = Math.max(y1, y + n.__r);
    });
    c.addScaledVector(right, (x0 + x1) / 2).addScaledVector(up, (y0 + y1) / 2);
    var d = 10, R = 10;
    vis.forEach(function (n) {
      v.set(n.x - c.x, n.y - c.y, n.z - c.z);
      var x = v.dot(right), y = v.dot(up), z = v.dot(dir), r = n.__r + 8;
      d = Math.max(d, z + (Math.abs(x) + r) / (m * th), z + (Math.abs(y) + r) / (m * tv));
      R = Math.max(R, v.length() + n.__r + 12);
    });
    if (!subset) sceneR = R;
    graph.cameraPosition({ x: c.x + dir.x * d, y: c.y + dir.y * d, z: c.z + dir.z * d }, { x: c.x, y: c.y, z: c.z }, ms || 0);
    M.fit = { d: Math.round(d), R: Math.round(R), nodes: vis.length, margin: m };
    setTimeout(scheduleCull, (ms || 0) + 40);
  }
  function flyTo(n) {
    if (!isFinite(n.x)) return;
    var cam = graph.camera(), sz = stageSize();
    var vf = cam.fov * Math.PI / 180, aspect = sz.w / sz.h, hf = 2 * Math.atan(Math.tan(vf / 2) * aspect);
    var R = 70 + n.__r * 2;
    var d = R / Math.sin(Math.min(vf, hf) / 2);
    var t = graph.controls().target;
    var dir = new THREE.Vector3().subVectors(cam.position, t);
    if (dir.lengthSq() < 1) dir.set(0.3, 0.3, 1);
    dir.normalize();
    graph.cameraPosition({ x: n.x + dir.x * d, y: n.y + dir.y * d, z: n.z + dir.z * d }, { x: n.x, y: n.y, z: n.z }, 900);
    setTimeout(scheduleCull, 950);
  }

  var firstStop = true;
  function onEngineStop() {
    updateTrace();
    scheduleCull();
    if (!firstStop) return;
    firstStop = false;
    fitView(400);
    setTimeout(function () {
      var veil = VL.$('#veil');
      if (veil) veil.remove();
      cullLabels();
      showHint();
      applyHash();
      measureFps(1500).then(function (fps) {
        VL.setReady({ fps: fps, graphNodes: current.nodes.length, graphLinks: graph.graphData().links.length, webglRenderer: M.webglRenderer });
        status();
      });
    }, 480);
  }
  function measureFps(ms) {
    return new Promise(function (resolve) {
      var r = graph.renderer(), f0 = r.info.render.frame, t0 = performance.now();
      setTimeout(function () {
        var fps = Math.round((r.info.render.frame - f0) * 10000 / (performance.now() - t0)) / 10;
        M.fpsSamples = (M.fpsSamples || []).concat([fps]);
        resolve(fps);
      }, ms);
    });
  }
  window.VLApp.measureFps = measureFps;
  function status() {
    var vis = current.nodes.filter(nodeVisible).length;
    statusEl.textContent = VL.U('o3d.status', { vis: VL.fmt(vis), n: VL.fmt(current.nodes.length) }) + ' · ' + (M.fps ? VL.fmt(M.fps) + ' fps' : '');
    fitLegend();
  }
  /* legend above the status line where the two would meet (js/paper3d.js); the call-outs avoid the legend */
  function fitLegend() { if (VL.fitLegend(stage, legendEl, statusEl)) scheduleCull(); }

  /* ------------------------------------------------------------------ selection + panel */
  /* the selection's neighbourhood (incident links) plus its chain: the subclass links up to the top of its hierarchy,
     like the paper's trace from a point up to the law */
  function neighbourhood(n) {
    var ns = new Set([n]), ls = new Set(), up = {}, frontier = [n], seen = new Set([n]), chain = new Set();
    graph.graphData().links.forEach(function (l) {
      if (!linkVisible(l)) return;
      var s = nodeOf(l.source), t = nodeOf(l.target);
      if (s === n || t === n) { ls.add(l); ns.add(s); ns.add(t); }
      if ((l.type === 'subClassOf' || l.type === 'instance') && s) (up[s.id] = up[s.id] || []).push(l);
    });
    while (frontier.length) {
      var next = [];
      frontier.forEach(function (x) {
        (up[x.id] || []).forEach(function (l) {
          var t = nodeOf(l.target);
          ls.add(l);
          chain.add(l);
          if (t && !seen.has(t)) { seen.add(t); ns.add(t); next.push(t); }
        });
      });
      frontier = next;
    }
    M.highlightChain = seen.size - 1;
    return { nodes: ns, links: ls, chain: chain };
  }
  function select(n, fly) {
    if (!n) return;
    if (!nodeVisible(n)) {
      if (n.kind === 'external') { state.showExternal = true; VL.$('#show-external').checked = true; }
      else if (n.kind === 'scheme') { state.showSchemes = true; VL.$('#show-schemes').checked = true; }
      if (n.module && state.modules[n.module] === false) { state.modules[n.module] = true; renderChips(); }
      refreshVisibility();
    }
    state.selected = n;
    state.selectedLink = null;
    var nb = neighbourhood(n);
    setHighlight(nb.nodes, nb.links, { chain: nb.chain, max: TRACE_ALL_MAX });
    resizeLabels();
    openPanel(n.inst ? instancePanel(n) : nodePanel(n));
    if (fly !== false) flyTo(n);
    M.selected = n.id;
    M.panelTitle = n.inst ? (n.number || n.label || n.id) : n.label_en;
  }
  function selectLink(l) {
    state.selected = null;
    state.selectedLink = l;
    var s = nodeOf(l.source), t = nodeOf(l.target);
    setHighlight(new Set([s, t]), new Set([l]), { max: TRACE_ALL_MAX });
    resizeLabels();
    openPanel(linkPanel(l));
    M.selectedLink = l.id || l.key;
  }
  function clearSelection() {
    state.selected = null;
    state.selectedLink = null;
    setHighlight(view.resultSet ? view.resultSet.nodes : null, view.resultSet ? view.resultSet.links : null, { max: RESULT_TRACE_MAX });
    resizeLabels();
    closePanel();
  }
  function openPanel(html, keepScroll) {
    var st = panel.scrollTop;
    panel.innerHTML = html;
    panel.classList.remove('hidden');
    stage.classList.add('panel-open');
    if (VL.isMobile() && !keepScroll) setDrawer(false);
    relayout();
    panel.scrollTop = keepScroll ? st : 0;
  }
  function closePanel() {
    panel.classList.add('hidden');
    stage.classList.remove('panel-open');
    relayout();
  }
  function chip(id) {
    var n = current.byId[id] || byId[id];
    if (!n) return '<span class="plain">' + VL.esc(id) + '</span>';
    return '<button type="button" class="linkish" data-node="' + VL.esc(n.id) + '"><span class="swatch" style="background:' + nodeVar(n) + '"></span>' + chipText(n) + '</button>';
  }
  /* panel helpers: a section heading and a field label in one language (VL.UH), a control's Vietnamese tooltip in EN–VI */
  function section(k, vars, body) { return body ? '<h3>' + VL.UH(k, vars) + '</h3>' + body : ''; }
  function dtk(k) { return '<dt>' + VL.UH(k) + '</dt>'; }
  function tipAttr(x, vars) { var t = VL.tip(x, vars); return t ? ' title="' + VL.esc(t) + '"' : ''; }
  function closeBtn() { return '<button class="btn btn-xs panel-close" type="button" data-act="close" aria-label="' + VL.esc(VL.U('o3d.close')) + '"' + tipAttr('o3d.close') + '>' + VL.ICON.close + '</button>'; }
  function actBtn(attrs, k) { return '<button class="btn btn-xs" type="button" ' + attrs + tipAttr(k) + '>' + VL.UH(k) + '</button>'; }
  /* the name of a term: EN–VI as in v1 (the English heading, the Vietnamese under it), EN or VI one language */
  function titleHtml(en, vi) {
    if (VL.lang() !== 'envi') return '<h2>' + VL.UH(VL.pair(vi || '', en || '')) + '</h2>';
    return '<h2>' + VL.esc(en || vi) + '</h2>' + (vi && en ? '<p class="vi" lang="vi">' + VL.esc(vi) + '</p>' : '');
  }
  /* definitions: both in EN–VI (English first, as in v1), else the mode's language (the other one where it is missing) */
  function defsHtml(en, vi) {
    var mode = VL.lang(), h = '';
    if (mode !== 'vi' && en) h += '<p class="def">' + VL.esc(en) + '</p>';
    if (mode !== 'en' && vi) h += '<p class="def' + (mode === 'envi' ? ' vi-def' : '') + '" lang="vi">' + VL.esc(vi) + '</p>';
    if (mode === 'vi' && !vi && en) h += '<p class="def" lang="en">' + VL.esc(en) + '</p>';
    if (mode === 'en' && !en && vi) h += '<p class="def" lang="vi">' + VL.esc(vi) + '</p>';
    return h;
  }
  function nodePanel(n) {
    var m = VL.MODULE[n.module] || VL.MODULE.provenance;
    var pk = paperKey(n), pc = pk ? VL.PAPER_CLASS[pk] : null;
    var h = closeBtn();
    h += '<div class="panel-kind">' + (pc ? '<span class="badge" title="' + VL.esc(VL.U('o3d.paperColour')) + '"><span class="swatch" style="background:' + pc.v + '"></span>' + VL.TH(pc) + '</span>' : '') +
      '<span class="badge"><span class="swatch" style="background:' + VL.moduleVar(n.module || 'provenance') + '"></span>' + VL.TH(m) + '</span>' +
      '<span class="badge">' + kindHtml(n) + '</span></div>';
    h += titleHtml(n.label_en, n.label_vi);
    h += '<dl class="kv"><dt>IRI</dt><dd><span class="iri">' + VL.wbr(n.iri) + '</span></dd>' +
      '<dt>CURIE</dt><dd class="iri">' + VL.esc(n.id) + '</dd>';
    if (n.instances != null) h += dtk(n.kind === 'scheme' ? 'o3d.k.concepts' : 'o3d.k.instances') + '<dd>' + (n.kind === 'class' ? VL.UH('o3d.v.inKg', { n: VL.fmt(n.instances) }) : VL.fmt(n.instances)) + '</dd>';
    h += '</dl>';
    h += defsHtml(n.definition_en, n.definition_vi);
    var sup = (n.superclasses || []).filter(function (x) { return byId[x]; });
    var supOther = (n.superclasses || []).filter(function (x) { return !byId[x]; });
    h += section('o3d.h.superclasses', null, (sup.length || supOther.length) ? '<div class="chip-list">' + sup.map(chip).join('') + supOther.map(function (x) { return '<span class="plain">' + VL.esc(x) + '</span>'; }).join('') + '</div>' : '');
    h += section('o3d.h.subclasses', null, (superOf[n.id] || []).length ? '<div class="chip-list">' + superOf[n.id].map(chip).join('') + '</div>' : '');
    var al = (alignOut[n.id] || []);
    h += section('o3d.h.alignedWith', null, al.length ? '<ul class="plist">' + al.map(function (l) {
      return '<li><span class="p-arrow">' + VL.UH(VL.pair(l.label_vi, l.label_en)) + '</span> ' + chip(sid(l.target)) + '</li>'; }).join('') + '</ul>' : '');
    var ai = (alignIn[n.id] || []);
    h += section('o3d.h.alignedToIt', null, ai.length ? '<ul class="plist">' + ai.map(function (l) {
      return '<li>' + chip(sid(l.source)) + ' <span class="p-arrow">' + VL.UH(VL.pair(l.label_vi, l.label_en)) + '</span></li>'; }).join('') + '</ul>' : '');
    h += section('o3d.h.scheme', null, (schemeOf[n.id] || []).length ? '<div class="chip-list">' + schemeOf[n.id].map(chip).join('') + '</div>' : '');
    h += section('o3d.h.schemeMembers', null, (schemeMembers[n.id] || []).length ? '<div class="chip-list">' + schemeMembers[n.id].map(chip).join('') + '</div>' : '');
    var op = outProps[n.id] || [], ip = inProps[n.id] || [];
    h += section('o3d.h.outgoing', { n: VL.fmt(op.length) }, op.length ? '<ul class="plist">' + op.map(function (l) {
      return '<li><button type="button" class="linkish p-name" data-link="' + l.key + '">' + VL.UH(propName(l)) + '</button> <span class="p-arrow">→</span> ' + chip(sid(l.target)) +
        '<div class="muted-small mono">' + VL.esc(l.id || '') + '</div></li>'; }).join('') + '</ul>' : '');
    h += section('o3d.h.incoming', { n: VL.fmt(ip.length) }, ip.length ? '<ul class="plist">' + ip.map(function (l) {
      return '<li>' + chip(sid(l.source)) + ' <span class="p-arrow">→</span> <button type="button" class="linkish p-name" data-link="' + l.key + '">' + VL.UH(propName(l)) + '</button>' +
        '<div class="muted-small mono">' + VL.esc(l.id || '') + '</div></li>'; }).join('') + '</ul>' : '');
    var at = n.attributes || [];
    h += section('o3d.h.datatype', { n: VL.fmt(at.length) }, at.length ? '<ul class="plist">' + at.map(function (a) {
      return '<li><span class="p-name">' + VL.UH(VL.pair(a.label_vi || '', a.label_en || '')) + '</span> <span class="p-arrow">→</span> <span class="iri">' + VL.esc(VL.shortIri(a.range || '')) + '</span>' +
        '<div class="muted-small mono">' + VL.esc(a.id) + '</div></li>'; }).join('') + '</ul>' : '');
    var ex = n.examples || [];
    if (ex.length) {
      h += '<h3>' + VL.UH(n.kind === 'scheme' ? 'o3d.k.concepts' : 'o3d.h.examples') + '</h3><ul class="plist">' + ex.map(function (e) {
        var lab = e.label ? dataHtml(e.label) : (e.label_vi || e.label_en ? VL.UH(VL.pair(e.label_vi || '', e.label_en || '')) : VL.esc(e.iri));
        var doc = VL.docIdFromIri(e.iri);
        if (doc) return '<li><a href="network-3d.html#doc=' + encodeURIComponent(doc) + '">' + lab + '</a><div class="muted-small">' + VL.UH('o3d.opensNetwork') + '</div></li>';
        return '<li>' + lab + (e.notation ? ' <span class="muted-small mono">' + VL.esc(e.notation) + '</span>' : '') + '<div class="iri muted-small">' + VL.wbr(VL.shortIri(e.iri)) + '</div></li>';
      }).join('') + '</ul>';
    }
    h += '<div class="panel-actions">' + actBtn('data-act="focus"', 'o3d.focus') +
      actBtn('data-copy="' + VL.esc(n.iri) + '"', 'o3d.copyIri') +
      (n.kind === 'class' ? actBtn('data-act="query-class" data-cls="' + VL.esc(n.id) + '"', 'o3d.queryInstances') : '') + '</div>';
    return h;
  }
  function propName(l) { return VL.pair(l.label_vi || '', l.label_en || ''); }
  function linkPanel(l) {
    var s = nodeOf(l.source), t = nodeOf(l.target), h = closeBtn();
    if (l.type === 'property') {
      var m = VL.MODULE[l.module] || VL.MODULE.provenance;
      var iri = VL.expandIri(l.id);
      h += '<div class="panel-kind"><span class="badge"><span class="swatch" style="background:' + VL.moduleVar(l.module) + '"></span>' + VL.TH(m) + '</span><span class="badge">' + VL.TH('o3d.objectProperty') + '</span></div>';
      h += titleHtml(l.label_en, l.label_vi);
      h += '<dl class="kv"><dt>IRI</dt><dd><span class="iri">' + VL.wbr(iri) + '</span></dd>' + dtk('o3d.k.domain') + '<dd>' + chip(s.id) + '</dd>' + dtk('o3d.k.range') + '<dd>' + chip(t.id) + '</dd>';
      if (l.inverse_of) h += dtk('o3d.k.inverseOf') + '<dd class="iri">' + VL.esc(l.inverse_of) + '</dd>';
      if ((l.aligned_to || []).length) h += dtk('o3d.k.alignedTo') + '<dd class="iri">' + l.aligned_to.map(VL.esc).join(', ') + '</dd>';
      h += '</dl>';
      h += defsHtml(l.definition_en, l.definition_vi);
      h += '<div class="panel-actions">' + actBtn('data-copy="' + VL.esc(iri) + '"', 'o3d.copyIri') +
        actBtn('data-act="query-prop" data-prop="' + VL.esc(l.id) + '"', 'o3d.queryProperty') + '</div>';
      return h;
    }
    var kinds = { subClassOf: 'o3d.link.subClassOf', alignment: 'o3d.link.alignment', inScheme: 'o3d.link.inScheme', instance: 'o3d.instanceOf', result: 'o3d.link.result' };
    h += '<div class="panel-kind"><span class="badge">' + (kinds[l.type] ? VL.TH(kinds[l.type]) : VL.esc(l.type)) + '</span></div>';
    if (l.type === 'result') h += '<h2>' + VL.esc(l.pred) + '</h2>';
    else if (l.type === 'instance') h += '<h2>' + VL.UH('o3d.instanceOf') + '</h2>';
    else h += titleHtml(l.label_en, l.label_vi);
    h += '<dl class="kv">' + dtk('o3d.k.from') + '<dd>' + chip(s.id) + '</dd>' + dtk('o3d.k.to') + '<dd>' + chip(t.id) + '</dd>';
    if (l.predIri) h += dtk('o3d.k.predicate') + '<dd><span class="iri">' + VL.wbr(l.predIri) + '</span></dd>';
    h += '</dl>';
    var expl = { subClassOf: 'o3d.expl.subClassOf', alignment: 'o3d.expl.alignment', inScheme: 'o3d.expl.inScheme' }[l.type];
    if (expl) h += '<p class="def">' + VL.UH(expl) + '</p>';
    return h;
  }
  function instancePanel(n) {
    var h = closeBtn();
    var cls = n.cls ? current.byId[n.cls] || byId[n.cls] : null;
    var pk = paperKey(n), pc = pk ? VL.PAPER_CLASS[pk] : null;
    h += '<div class="panel-kind"><span class="badge"><span class="swatch" style="background:' + nodeVar(n) + '"></span>' +
      (pc ? VL.TH(pc) : VL.TH('o3d.kind.instance')) + '</span>' + (cls ? '<span class="badge">' + VL.UH(namePair(cls)) + '</span>' : '') + '</div>';
    h += '<h2>' + (n.number ? VL.esc(n.number) : (n.label || n.label_vi ? VL.UH(VL.pair(n.label_vi || '', n.label || '')) : VL.esc(n.id))) + '</h2>';
    if (n.title && n.title !== n.number) h += '<p class="vi" lang="vi">' + VL.esc(n.title) + '</p>';
    h += '<dl class="kv">' + (n.iri ? '<dt>IRI</dt><dd><span class="iri">' + VL.wbr(n.iri) + '</span></dd>' : '') + (cls ? dtk('o3d.k.class') + '<dd>' + chip(cls.id) + '</dd>' : '') + '</dl>';
    var lits = (view.literals || {})[n.id] || [];
    if (lits.length) h += '<h3>' + VL.UH('o3d.h.values') + '</h3><ul class="plist">' + lits.slice(0, 12).map(function (l) { return '<li><span class="p-arrow mono">' + VL.esc(l[0]) + '</span> ' + dataHtml(VL.short(l[1], 160)) + '</li>'; }).join('') + '</ul>';
    var doc = VL.docIdFromIri(n.iri);
    if (doc) h += '<div class="panel-actions"><a class="btn btn-xs" href="network-3d.html#doc=' + encodeURIComponent(doc) + '"' + tipAttr('o3d.openNetwork') + '>' + VL.UH('o3d.openNetwork') + '</a></div>';
    return h;
  }
  panel.addEventListener('click', function (e) {
    var b = e.target.closest('button, a');
    if (!b) return;
    if (b.hasAttribute('data-node')) { var n = current.byId[b.getAttribute('data-node')] || byId[b.getAttribute('data-node')]; if (n) select(n, true); }
    else if (b.hasAttribute('data-link')) { var l = linkByKey[b.getAttribute('data-link')]; if (l) selectLink(l); }
    else if (b.hasAttribute('data-copy')) VL.copy(b.getAttribute('data-copy'));
    else if (b.getAttribute('data-act') === 'close') clearSelection();
    else if (b.getAttribute('data-act') === 'focus' && state.selected) flyTo(state.selected);
    else if (b.getAttribute('data-act') === 'query-class') {
      openDrawer('PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n' +
        'SELECT ?s ?label WHERE {\n  ?s a ' + b.getAttribute('data-cls') + ' .\n  OPTIONAL { ?s vlo:title ?label }\n  OPTIONAL { ?s rdfs:label ?label }\n} LIMIT 50');
    } else if (b.getAttribute('data-act') === 'query-prop') {
      openDrawer('PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>\nCONSTRUCT { ?s ' + b.getAttribute('data-prop') + ' ?o }\nWHERE { ?s ' + b.getAttribute('data-prop') + ' ?o }\nLIMIT 60');
    }
  });

  /* ------------------------------------------------------------------ controls: chips, toggles, search, keys */
  function renderChips() {
    var counts = {};
    nodes.forEach(function (n) { if (n.kind !== 'external') counts[n.module] = (counts[n.module] || 0) + 1; });
    links.forEach(function (l) { if (l.type === 'property' && !counts[l.module]) counts[l.module] = 0; });
    var html = VL.MODULES.filter(function (m) { return m.id !== 'external' && !SCOPE.laterModules[m.id]; }).map(function (m) {
      var on = state.modules[m.id] !== false;
      var c = counts[m.id] || 0;
      /* a control: the module's name in one language, the Vietnamese as its tooltip in EN–VI */
      return '<button type="button" class="chip" data-mod="' + m.id + '" aria-pressed="' + on + '"' + tipAttr(m) + '>' +
        '<span class="swatch" style="background:' + m.v + '"></span>' + VL.UH(m) + (c ? ' · ' + VL.fmt(c) : '') + '</button>';
    }).join('');
    VL.$('#module-chips').innerHTML = html;
    var note = VL.$('#module-later'), text = VL.laterModulesNote(SCOPE.laterModules);
    if (!note && text) {
      note = VL.el('p', { 'class': 'side-note', id: 'module-later' });
      VL.$('#module-chips').insertAdjacentElement('afterend', note);
    }
    if (note) note.innerHTML = text;
  }
  VL.$('#module-chips').addEventListener('click', function (e) {
    var b = e.target.closest('[data-mod]');
    if (!b) return;
    var id = b.getAttribute('data-mod');
    state.modules[id] = state.modules[id] === false;
    b.setAttribute('aria-pressed', state.modules[id] ? 'true' : 'false');
    refreshVisibility();
  });
  VL.$('#mod-all').addEventListener('click', function () { Object.keys(state.modules).forEach(function (k) { state.modules[k] = true; }); renderChips(); refreshVisibility(); });
  VL.$('#mod-none').addEventListener('click', function () { Object.keys(state.modules).forEach(function (k) { state.modules[k] = false; }); renderChips(); refreshVisibility(); });
  VL.$('#show-external').addEventListener('change', function (e) { state.showExternal = e.target.checked; refreshVisibility(); });
  VL.$('#show-schemes').addEventListener('change', function (e) { state.showSchemes = e.target.checked; refreshVisibility(); });
  VL.$('#show-particles').addEventListener('change', function (e) { state.particles = e.target.checked; graph.linkDirectionalParticles(graph.linkDirectionalParticles()); });
  VL.$$('input[data-link]').forEach(function (cb) {
    cb.addEventListener('change', function () { state.links[cb.getAttribute('data-link')] = cb.checked; refreshVisibility(); });
  });
  function refreshVisibility() {
    if (!graph) return;
    graph.nodeVisibility(graph.nodeVisibility());
    graph.linkVisibility(graph.linkVisibility());
    if (state.selected && !nodeVisible(state.selected)) clearSelection();
    scheduleCull();
    status();
    M.visibleNodes = current.nodes.filter(nodeVisible).length;
  }
  /* the label language follows the global switch (js/i18n.js): v1's per-view label toggle (button[data-lang], in its own
     side section of index.html) is taken out of the page */
  VL.$$('button[data-lang]').forEach(function (b) {
    var sec = b.closest('.side-section');
    if (sec && sec.querySelectorAll('button').length === sec.querySelectorAll('button[data-lang]').length) sec.remove();
    else b.remove();
  });
  function counts() {
    VL.$('#cnt-external').textContent = VL.fmt(nodes.filter(function (n) { return n.kind === 'external'; }).length);
    VL.$('#cnt-schemes').textContent = VL.fmt(nodes.filter(function (n) { return n.kind === 'scheme'; }).length);
    ['subClassOf', 'property', 'alignment', 'inScheme'].forEach(function (t) {
      VL.$('#cnt-' + t).textContent = VL.fmt(links.filter(function (l) { return l.type === t; }).length);
    });
  }

  /* search: every name in both languages, IRI and CURIE are searched in every mode; a suggestion shows the name in the
     mode's language with the other one under it */
  var searchIndex = [];
  function buildSearch() {
    var vi = VL.lang() === 'vi';
    searchIndex = [];
    nodes.forEach(function (n) {
      var main = VL.U(namePair(n)), other = vi ? n.label_en : n.label_vi;
      searchIndex.push({ t: 'node', id: n.id, main: main, sub: [other !== main ? other : null, n.id].filter(Boolean).join(' · '), kind: kindLabel(n), color: nodeVar(n),
        hay: [VL.fold(n.label_en), VL.fold(n.label_vi || ''), VL.fold(n.id), VL.fold(n.id.split(':')[1] || ''), VL.fold(n.iri)], boost: n.kind === 'class' ? 3 : 1 });
    });
    links.forEach(function (l) {
      if (l.type !== 'property') return;
      var main = VL.U(propName(l)), other = vi ? l.label_en : l.label_vi;
      searchIndex.push({ t: 'link', key: l.key, main: main, sub: [other !== main ? other : null, l.id].filter(Boolean).join(' · '), kind: VL.U('o3d.kind.property'), color: VL.moduleVar(l.module),
        hay: [VL.fold(l.label_en), VL.fold(l.label_vi || ''), VL.fold(l.id || ''), VL.fold((l.id || '').split(':')[1] || '')], boost: 0 });
    });
  }
  buildSearch();
  function searchSource(q) {
    var qf = VL.fold(q.trim());
    if (!qf) return [];
    var out = [];
    searchIndex.forEach(function (e) {
      var s = 0;
      e.hay.forEach(function (h) { s = Math.max(s, VL.score(qf, h)); });
      if (s > 0) out.push([s + e.boost, e]);
    });
    out.sort(function (a, b) { return b[0] - a[0] || a[1].main.localeCompare(b[1].main); });
    return out.slice(0, 10).map(function (x) { return x[1]; });
  }
  function onPick(e) {
    if (e.t === 'node') select(byId[e.id], true);
    else selectLink(linkByKey[e.key]);
    if (VL.isMobile()) setSide(false);
  }
  VL.combobox({ input: VL.$('#onto-search'), list: VL.$('#onto-suggest'), source: searchSource, onPick: onPick });
  VL.combobox({ input: VL.$('#onto-search-m'), list: VL.$('#onto-suggest-m'), source: searchSource, onPick: onPick });
  window.VLApp.search = function (q) { var r = searchSource(q); if (r.length) onPick(r[0]); return r.map(function (x) { return x.main; }); };
  window.VLApp.select = function (id) { var n = current.byId[id] || byId[id]; if (n) select(n, true); return !!n; };
  /* tests: hover a node (id, or null to end the hover) as the pointer would; returns the number of traced hover links */
  window.VLApp.hover = function (id) { setHover(id ? (current.byId[id] || byId[id] || null) : null); return M.hoverTrace || 0; };
  /* tests: ids of the search suggestions for a query (nodes by id, links by property id or key) */
  window.VLApp.searchIds = function (q) {
    return searchSource(q).map(function (e) { return e.t === 'node' ? e.id : ((linkByKey[e.key] || {}).id || e.key); });
  };
  window.VLApp.screenPos = function (id) {
    var n = current.byId[id] || byId[id];
    if (!n || !graph) return null;
    var p = graph.graph2ScreenCoords(n.x, n.y, n.z), r = host.getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y, inside: p.x > 0 && p.y > 0 && p.x < r.width && p.y < r.height };
  };
  /* the camera (position and orbit target, rounded): tests check that a language switch keeps it */
  function camState(cam, target) {
    if (!cam || !target) return null;
    return [cam.position.x, cam.position.y, cam.position.z, target.x, target.y, target.z].map(function (v) { return Math.round(v * 1000) / 1000; });
  }
  window.VLApp.camera = function () { return graph ? camState(graph.camera(), graph.controls().target) : null; };
  window.VLApp.state = function () {
    return { selected: state.selected && state.selected.id, view: view.mode, nodes: graph.graphData().nodes.length, links: graph.graphData().links.length,
      panelOpen: !panel.classList.contains('hidden'), panelText: panel.textContent.slice(0, 400) };
  };

  function setSide(open) {
    app.classList.toggle('side-open', open);
    VL.$('#btn-side-m').setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  VL.$('#btn-side-m').addEventListener('click', function () { setSide(!app.classList.contains('side-open')); });
  VL.$('#btn-reset').addEventListener('click', resetView);
  VL.$('#btn-reset2').innerHTML = VL.ICON.reset;
  VL.$('#btn-reset2').addEventListener('click', resetView);
  VL.$('#btn-legend').innerHTML = VL.ICON.layers;
  VL.$('#btn-legend').addEventListener('click', function () { state.legendOpen = !state.legendOpen; renderLegend(); scheduleCull(); });
  VL.$('#btn-png').addEventListener('click', exportPng);
  VL.$('#btn-query').addEventListener('click', function () { setDrawer(!state.drawerOpen); });
  VL.$('#btn-query-m').addEventListener('click', function () { setSide(false); setDrawer(!state.drawerOpen); });
  function resetView() {
    clearSelection();
    fitView(700);
  }
  function exportPng() {
    var r = graph.renderer();
    r.render(graph.scene(), graph.camera());
    r.domElement.toBlob(function (b) { VL.downloadBlob(b, 'vlonto-ontology-3d.png'); VL.toast(VL.U('o3d.toast.png')); }, 'image/png');
  }
  window.VLApp.exportPng = function () { var r = graph.renderer(); r.render(graph.scene(), graph.camera()); return r.domElement.toDataURL('image/png').length; };

  function orbit(dAz, dPol, zoom) {
    var cam = graph.camera(), ctl = graph.controls(), t = ctl.target;
    var off = cam.position.clone().sub(t), sph = new THREE.Spherical().setFromVector3(off);
    sph.theta += dAz;
    sph.phi = Math.min(Math.PI - 0.05, Math.max(0.05, sph.phi + dPol));
    sph.radius *= zoom || 1;
    off.setFromSpherical(sph);
    cam.position.copy(t).add(off);
    cam.lookAt(t);
    ctl.update();
    scheduleCull();
  }
  host.addEventListener('keydown', function (e) {
    var k = e.key;
    if (k === 'ArrowLeft') orbit(-0.12, 0);
    else if (k === 'ArrowRight') orbit(0.12, 0);
    else if (k === 'ArrowUp') orbit(0, -0.1);
    else if (k === 'ArrowDown') orbit(0, 0.1);
    else if (k === '+' || k === '=') orbit(0, 0, 0.85);
    else if (k === '-' || k === '_') orbit(0, 0, 1.18);
    else return;
    e.preventDefault();
  });
  document.addEventListener('keydown', function (e) {
    var tag = (e.target && e.target.tagName) || '';
    var typing = /INPUT|TEXTAREA|SELECT/.test(tag);
    if (e.key === '/' && !typing) { e.preventDefault(); (VL.isMobile() ? VL.$('#onto-search-m') : VL.$('#onto-search')).focus(); }
    else if (e.key === 'Escape' && !typing) {
      if (!panel.classList.contains('hidden')) clearSelection();
      else if (state.drawerOpen) setDrawer(false);
      else if (app.classList.contains('side-open')) setSide(false);
    }
  });

  /* ------------------------------------------------------------------ legend + hint */
  var SHAPES = {
    'class': '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" fill="currentColor"/></svg>',
    scheme: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1.2L12.8 7 7 12.8 1.2 7z" fill="currentColor"/></svg>',
    external: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1.3l5 2.9v5.7L7 12.7 2 9.9V4.2z" fill="currentColor"/></svg>'
  };
  /* the paper's legend row: "Tiếng Việt · English" entries in EN–VI, one language in EN or VI; the paper's classes
     present in the view first, then the modules outside the paper's palette, then shapes, link kinds and the traced path */
  function bi(vi, en) { return VL.TH(VL.pair(VL.cap(vi || ''), VL.cap(en || ''))); }
  function biKey(k) { var e = VL.i18n.get(k) || { vi: '', en: k }; return bi(e.vi, e.en); }
  var FAMILY = { documents: 1, provisions: 1, qa: 1, terminology: 1, classification: 1 };   // modules coloured like a paper class
  function renderLegend() {
    var btn = VL.$('#btn-legend');
    btn.setAttribute('aria-expanded', state.legendOpen ? 'true' : 'false');
    legendEl.classList.toggle('hidden', !state.legendOpen);
    if (!state.legendOpen) { fitLegend(); return; }
    var keys = {}, mods = {};
    current.nodes.forEach(function (n) {
      if (!nodeVisible(n)) return;
      var k = paperKey(n);
      if (k) keys[k] = true;
      else mods[n.kind === 'external' ? 'external' : (n.module || 'provenance')] = true;
    });
    var cls = VL.PAPER_CLASSES.filter(function (c) { return keys[c.key]; });
    var other = VL.MODULES.filter(function (m) { return mods[m.id] && (!FAMILY[m.id] || m.id === 'external'); });
    var famOnly = VL.MODULES.filter(function (m) { return mods[m.id] && FAMILY[m.id]; });
    var h = '<ul class="lg-classes">' + cls.map(function (c) {
      return '<li><span class="swatch" style="background:' + c.v + '"></span>' + bi(c.vi, c.en) + '</li>';
    }).join('') + '<li><span class="swatch trace" aria-hidden="true"></span>' + biKey(view.mode !== 'ontology' ? 'o3d.lg.tracedResult' : 'o3d.lg.tracedPath') + '</li></ul>';
    if (other.length) {
      h += '<div class="legend-sub"><ul class="lg-modules">' + other.map(function (m) {
        return '<li><span class="swatch" style="background:' + m.v + '"></span>' + (m.id === 'external' ? biKey('o3d.lg.externalTerms') : bi(m.vi, m.en)) + '</li>';
      }).join('') + '</ul></div>';
    }
    h += '<div class="legend-sub"><ul class="lg-marks">' +
      '<li>' + SHAPES['class'] + biKey('o3d.lg.class') + '</li><li>' + SHAPES.scheme + biKey('o3d.lg.scheme') + '</li>' +
      '<li>' + SHAPES.external + biKey('o3d.lg.external') + '</li>' +
      '<li><span class="swatch line" style="background:linear-gradient(90deg,var(--cls-work),var(--cls-article),var(--cls-term))"></span>' + biKey('o3d.lg.subclassOf') + '</li>' +
      '<li><span class="swatch line" style="background:linear-gradient(90deg,var(--mod-validity-change),var(--mod-agents),var(--mod-documents))"></span>' + biKey('o3d.lg.property') + '</li>' +
      '<li><span class="swatch line" style="background:var(--o3d-link-alignment)"></span>' + biKey('o3d.lg.alignment') + '</li>' +
      '</ul>' + (famOnly.length ? '<p class="lg-note">' + VL.UH('o3d.lg.otherClasses', { list: famOnly.map(function (m) { return VL.U(m); }).join(', ') }) + '</p>' : '') + '</div>';
    legendEl.innerHTML = h;
    M.legendEntries = VL.$$('li', legendEl).length;
    fitLegend();
  }
  function showHint() {
    if (VL.store.get('hint-onto3d') === 'off') return;
    VL.$('#hint').classList.remove('hidden');
    scheduleCull();
  }
  function hideHint() {
    var h = VL.$('#hint');
    if (h && !h.classList.contains('hidden')) { h.classList.add('hidden'); scheduleCull(); }
  }
  VL.$('#hint-close').addEventListener('click', function () { hideHint(); VL.store.set('hint-onto3d', 'off'); });

  /* ------------------------------------------------------------------ theme switch (light / dark): background, node
     colours, label sprites and link colours change in place (no new layout); DOM swatches follow CSS variables */
  function applyTheme() {
    readTheme();
    if (!graph) return;
    graph.backgroundColor(TH.bg);
    if (fog) fog.color.set(TH.bg);
    if (lights) {
      var L2 = VL.paperLights(P.dark);
      lights.ambient.intensity = L2.ambient.intensity;
      lights.directional.intensity = L2.directional.intensity;
    }
    var seen = new Set();
    nodes.concat(current.nodes || []).forEach(function (n) {
      if (seen.has(n)) return;
      seen.add(n);
      if (n.__label) { n.__labSel = state.selected === n; n.__label.setStyle(labelOpts(n)); }
    });
    graph.linkOpacity(P.linkOpacity);
    applyHighlight();
    graph.linkDirectionalArrowColor(graph.linkDirectionalArrowColor());
    renderLegend();
    M.themeRenders = (M.themeRenders || 0) + 1;
  }
  window.addEventListener('vlonto-theme', applyTheme);

  /* ------------------------------------------------------------------ layout of the stage (panel / drawer docking) */
  function relayout() {
    if (!graph) return;
    requestAnimationFrame(function () {
      var sz = stageSize();
      graph.width(sz.w).height(sz.h);
      resizeLabels();
      VL.fitLegend(stage, legendEl, statusEl);
      scheduleCull();
    });
  }
  window.addEventListener('resize', relayout);

  /* ------------------------------------------------------------------ SPARQL query mode */
  var view = { mode: 'ontology', resultSet: null, literals: null };
  var ctxPromise = null;
  var qText = VL.$('#qd-text'), qStatus = VL.$('#qd-status'), qResult = VL.$('#qd-result'), qSel = VL.$('#qd-example');
  VL.$('#qd-close').innerHTML = VL.ICON.close;
  /* the example menu: group names and example titles in one language (EN and EN–VI English, VI Vietnamese); a mode
     change rebuilds it and keeps the chosen example */
  function fillExamples() {
    var keep = qSel.value;
    var h = '<optgroup label="' + VL.esc(VL.U('o3d.q.groupConstruct')) + '">' + VL.Sparql.CONSTRUCT_EXAMPLES.map(function (e, i) {
      return '<option value="c' + i + '">' + VL.UH(VL.pair(e.title_vi, e.title_en)) + '</option>'; }).join('') + '</optgroup>';
    h += '<optgroup label="' + VL.esc(VL.U('o3d.q.groupSelect')) + '">' + EXAMPLES.map(function (e, i) {
      return '<option value="s' + i + '">' + VL.UH(VL.pair(e.title_vi, e.title_en)) + '</option>'; }).join('') + '</optgroup>';
    qSel.innerHTML = h;
    if (keep) qSel.value = keep;
  }
  fillExamples();
  qText.value = VL.Sparql.CONSTRUCT_EXAMPLES[0].query;
  qSel.addEventListener('change', function () {
    var v = qSel.value, i = +v.slice(1);
    qText.value = v[0] === 'c' ? VL.Sparql.CONSTRUCT_EXAMPLES[i].query : EXAMPLES[i].query;
    setQStatus(function () { return VL.U('o3d.q.loaded'); }, '');
  });
  qText.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runQuery(); }
    if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey) {
      e.preventDefault();
      var s = qText.selectionStart;
      qText.value = qText.value.slice(0, s) + '  ' + qText.value.slice(qText.selectionEnd);
      qText.selectionStart = qText.selectionEnd = s + 2;
    }
  });
  VL.$$('[data-cm]').forEach(function (b) {
    b.addEventListener('click', function () {
      state.cm = b.getAttribute('data-cm');
      VL.$$('[data-cm]').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
    });
  });
  VL.$('#qd-run').addEventListener('click', runQuery);
  VL.$('#qd-back').addEventListener('click', backToOntology);
  VL.$('#qd-close').addEventListener('click', function () { setDrawer(false); });
  function minText() {
    var b = VL.$('#qd-min'), k = drawer.classList.contains('min') ? 'o3d.q.showEditor' : 'o3d.q.hideEditor', t = VL.tip(k);
    b.textContent = VL.U(k);
    if (t) b.setAttribute('title', t); else b.removeAttribute('title');
  }
  VL.$('#qd-min').addEventListener('click', function () {
    var min = !drawer.classList.contains('min');
    drawer.classList.toggle('min', min);
    stage.classList.toggle('drawer-min', min);
    minText();
    VL.$('#qd-min').setAttribute('aria-expanded', min ? 'false' : 'true');
    relayout();
  });
  /* status of the drawer: msg is text or a function that composes it in the current mode, so a mode change can render
     the last status again */
  var qLast = null;
  function setQStatus(msg, cls) {
    qLast = { msg: msg, cls: cls };
    qStatus.textContent = typeof msg === 'function' ? msg() : msg;
    qStatus.className = 'qd-status' + (cls ? ' ' + cls : '');
  }
  /* the last result table of the drawer, drawn again on a mode change (its notes are in the mode's language) */
  var qTable = null;
  function renderQTable(res, opts) { qTable = res ? [res, opts] : null; if (res) VL.Sparql.renderTable(qResult, res, opts); else qResult.innerHTML = ''; }
  function setDrawer(open) {
    state.drawerOpen = open;
    drawer.classList.toggle('hidden', !open);
    stage.classList.toggle('drawer-open', open);
    if (open && VL.isMobile()) { closePanel(); }
    if (open) ensureStore();
    relayout();
    M.drawerOpen = open;
  }
  function openDrawer(query) {
    setDrawer(true);
    if (drawer.classList.contains('min')) VL.$('#qd-min').click();
    qText.value = query;
    runQuery();
  }
  function ensureStore() {
    if (!ctxPromise) {
      setQStatus(function () { return VL.U('o3d.q.loading'); }, '');
      ctxPromise = VL.Sparql.createStore('both').then(function (ctx) {
        M.storeTriples = ctx.triples;
        M.storeLoadMs = ctx.loadMs;
        setQStatus(function () { return VL.U('o3d.q.ready', { n: VL.fmt(ctx.triples), ms: VL.fmt(ctx.loadMs) }); }, 'ok');
        return ctx;
      }, function (e) {
        setQStatus(function () { return VL.U('o3d.q.loadError', { msg: e.message }); }, 'err');
        ctxPromise = null;
        throw e;
      });
    }
    return ctxPromise;
  }
  function highlightError(err) {
    if (!err || !err.line) return;
    var lines = qText.value.split('\n'), pos = 0;
    for (var i = 0; i < err.line - 1 && i < lines.length; i++) pos += lines[i].length + 1;
    var col = Math.max(0, (err.col || 1) - 1);
    qText.focus();
    qText.setSelectionRange(pos + col, Math.min(pos + (lines[err.line - 1] || '').length, pos + col + 12));
  }
  function runQuery() {
    var q = qText.value;
    setQStatus(function () { return VL.U('o3d.q.running'); }, '');
    return ensureStore().then(function (ctx) {
      var res = VL.Sparql.run(ctx, q);
      M.lastQuery = { form: res.form, count: res.count, ms: res.ms, error: res.error ? res.error.message : null };
      if (res.error) { setQStatus(function () { return VL.Sparql.errorText(res.error); }, 'err'); highlightError(res.error); renderQTable(null); return res; }
      if (res.form === 'SELECT') {
        setQStatus(function () { return VL.U('o3d.q.select', { n: res.count === 1 ? 1 : VL.fmt(res.count), ms: VL.fmt(res.ms) }); }, 'ok');
        renderQTable(res, { dark: true, max: 300 });
      } else if (res.form === 'ASK') {
        setQStatus(function () { return VL.U('o3d.q.ask', { v: res.boolean ? 'true' : 'false', ms: VL.fmt(res.ms) }); }, 'ok');
        renderQTable(null);
      } else {
        drawConstruct(ctx, res);
      }
      return res;
    }).catch(function (e) { setQStatus(String(e && e.message || e), 'err'); });
  }
  window.VLApp.runQuery = function (q, mode) { if (mode) state.cm = mode; setDrawer(true); if (q != null) qText.value = q; return runQuery().then(function () { return M.lastQuery; }); };
  window.VLApp.constructExamples = VL.Sparql.CONSTRUCT_EXAMPLES;

  function drawConstruct(ctx, res) {
    var sc = VL.scopeQuads(ctx, res.quads);
    M.constructHiddenLater = sc.hidden;
    var g = VL.Sparql.quadsToGraph(ctx, sc.quads, 500);
    if (!g.nodes.length) {
      setQStatus(function () { return VL.U('o3d.q.none', { form: res.form, ms: VL.fmt(res.ms) }); }, 'ok');
      renderQTable(null);
      return;
    }
    var mode = state.cm;
    if (view.mode !== 'ontology') restoreBase(false);
    var add = {}, cnodes = [], clinks = [], resultNodes = new Set(), resultLinks = new Set();
    g.nodes.forEach(function (gn) {
      var base = byId[gn.id];
      if (base) {
        if (mode === 'overlay') { add[gn.id] = base; resultNodes.add(base); return; }
        var copy = {};
        Object.keys(base).forEach(function (k) { if (k.indexOf('__') !== 0 && ['x', 'y', 'z', 'vx', 'vy', 'vz', 'fx', 'fy', 'fz', 'index'].indexOf(k) < 0) copy[k] = base[k]; });
        copy.__r = radius(copy);
        add[gn.id] = copy; cnodes.push(copy); resultNodes.add(copy);
        return;
      }
      var cls = null;
      (gn.types || []).forEach(function (t) { var c = VL.shortIri(t); if (!cls && byId[c] && byId[c].kind === 'class') cls = c; });
      var module = cls ? byId[cls].module : ((gn.iri || '').indexOf(VL.NS.vlo) === 0 ? 'provenance' : 'documents');
      var node = { id: gn.id, inst: true, kind: 'instance', iri: gn.iri, cls: cls, module: module, color: VL.moduleColor(module),
        number: gn.number ? VL.nfc(gn.number) : null, title: gn.title ? VL.nfc(gn.title) : null, label: gn.label ? VL.nfc(gn.label) : null,
        label_vi: gn.label_vi ? VL.nfc(gn.label_vi) : null };
      node.__r = radius(node);
      add[gn.id] = node; cnodes.push(node); resultNodes.add(node);
    });
    g.links.forEach(function (l, i) {
      var lk = { key: 'R' + i, source: l.source, target: l.target, type: 'result', pred: l.pred, predIri: l.predIri, curvature: 0, rotation: 0 };
      clinks.push(lk); resultLinks.add(lk); linkByKey[lk.key] = lk;
    });
    var all = {}, data, seed = 0x2f6e2b1;
    /* result nodes start next to their class, jittered by a seeded generator (mulberry32): a query draws the same graph */
    function rnd() {
      seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    if (mode === 'overlay') {
      nodes.forEach(function (n) { n.fx = n.x; n.fy = n.y; n.fz = n.z; all[n.id] = n; });
      cnodes.forEach(function (n) {
        all[n.id] = n;
        if (n.cls && byId[n.cls]) { var c = byId[n.cls]; n.x = c.x + (rnd() - 0.5) * 20; n.y = c.y + (rnd() - 0.5) * 20; n.z = c.z + (rnd() - 0.5) * 20; }
      });
      var inst = [];
      cnodes.forEach(function (n, i) {
        if (n.cls && byId[n.cls]) { var lk = { key: 'I' + i, source: n.id, target: n.cls, type: 'instance', curvature: 0, rotation: 0 }; inst.push(lk); linkByKey[lk.key] = lk; resultNodes.add(byId[n.cls]); }
      });
      data = { nodes: nodes.concat(cnodes), links: links.concat(clinks, inst) };
    } else {
      cnodes.forEach(function (n) { all[n.id] = n; });
      data = { nodes: cnodes, links: clinks };
    }
    current.byId = all;
    current.nodes = data.nodes;
    view.mode = mode;
    view.literals = g.literals;
    view.resultSet = { nodes: resultNodes, links: resultLinks };
    state.selected = null;
    closePanel();
    graph.warmupTicks(mode === 'overlay' ? 160 : LAYOUT.ticks);       // every tick at once: no time-limited cool-down
    graph.graphData(data);
    setHighlight(resultNodes, resultLinks, { max: RESULT_TRACE_MAX });   // the result: traced when small, else thin lines + hover
    VL.$('#qd-back').classList.remove('hidden');
    renderLegend();
    setTimeout(function () { fitView(700, mode === 'overlay' ? Array.from(resultNodes) : null); }, 60);
    var lit = Object.keys(g.literals).reduce(function (a, k) { return a + g.literals[k].length; }, 0);
    setQStatus(function () {
      return VL.U('o3d.q.drawn', { form: res.form, n: VL.fmt(res.count), ms: VL.fmt(res.ms), nodes: VL.fmt(cnodes.length), links: VL.fmt(clinks.length), mode: VL.U('o3d.mode.' + mode) }) +
        (lit ? VL.U('o3d.q.literals', { n: VL.fmt(lit) }) : '') + (g.truncated ? VL.U('o3d.q.truncated') : '') + '.';
    }, 'ok');
    renderQTable(res, { dark: true, max: 200 });
    M.view = 'construct-' + mode;
    M.constructTriples = res.count;
    M.graphNodes = data.nodes.length;
    M.graphLinks = data.links.length;
    status();
  }
  function restoreBase(refit) {
    nodes.forEach(function (n) { delete n.fx; delete n.fy; delete n.fz; n.fx = undefined; n.fy = undefined; n.fz = undefined; });
    current.byId = byId;
    current.nodes = nodes;
    view.mode = 'ontology';
    view.resultSet = null;
    view.literals = null;
    state.selected = null;
    graph.warmupTicks(0);
    graph.graphData(baseData);
    setHighlight(null, null);
    renderLegend();
    VL.$('#qd-back').classList.add('hidden');
    if (refit) setTimeout(function () { fitView(700); }, 60);
    M.view = 'ontology';
    M.graphNodes = nodes.length;
    M.graphLinks = links.length;
    status();
  }
  function backToOntology() { closePanel(); restoreBase(true); setQStatus(function () { return VL.U('o3d.q.back'); }, ''); }
  window.VLApp.back = backToOntology;

  /* ------------------------------------------------------------------ hash (#class=vlo:Article) */
  function applyHash() {
    var p = VL.params();
    var id = p['class'] || p.term || p.node;
    if (id) {
      if (id.indexOf(':') < 0) id = 'vlo:' + id;
      if (byId[id]) select(byId[id], true);
    }
    if (p.query === '1') setDrawer(true);
  }
  window.addEventListener('hashchange', applyHash);

  /* ------------------------------------------------------------------ language switch (js/i18n.js 'vl:lang'): call-outs,
     legend, module chips, counts, search suggestions, the example menu, the drawer's status and table and the open
     panel are rendered again in the new mode; the camera, the selection, the query result and the filters stay */
  function applyLang() {
    M.langRenders = (M.langRenders || 0) + 1;
    buildSearch();
    renderChips();
    counts();
    renderLegend();
    fillExamples();
    minText();
    if (qLast) setQStatus(qLast.msg, qLast.cls);
    if (qTable) renderQTable(qTable[0], qTable[1]);
    if (graph) { relabel(); resizeLabels(); status(); } else M.labelsLang = VL.lang();
    if (!panel.classList.contains('hidden')) {
      if (state.selected) openPanel(state.selected.inst ? instancePanel(state.selected) : nodePanel(state.selected), true);
      else if (state.selectedLink) openPanel(linkPanel(state.selectedLink), true);
    }
  }
  document.addEventListener('vl:lang', applyLang);
  /* tests: the call-out lines of a node as drawn (text of each line), or null */
  window.VLApp.labelLines = function (id) {
    var n = current.byId[id] || byId[id];
    return n && n.__label ? n.__label.__opts.lines.map(function (ln) { return ln.map(function (p) { return p.text; }).join(''); }) : null;
  };

  /* ------------------------------------------------------------------ start */
  renderChips();
  counts();
  renderLegend();
  VL.fontsReady().then(function () {
    build();
  }).catch(function (e) {
    console.error(e);
    VL.$('#veil').innerHTML = '<div>' + VL.UH('o3d.startError', { msg: e.message }) + '</div>';
  });
})();

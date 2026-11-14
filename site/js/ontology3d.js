/* VLOnto - 3D Ontology Playground (three.js over data/ontology_graph.js; SPARQL via js/sparql-core.js).
   The ontology in the arrangement of the 3D legal network (js/network3d.js): translucent stacked planes, one for each
   level of the class hierarchy (computed at load from the subClassOf links among the classes of the release: the root
   classes on top, their subclasses on the plane below, theirs below that), then a plane of the concept schemes and, at
   the bottom, the external vocabularies the terms are aligned with. On every plane the terms sit in the band of their
   module (the module with the most links to the others in the middle of the front row), a subclass under its superclass,
   a concept scheme under its class and an external term under the classes aligned to it, so subclass links run nearly
   straight down. The layout depends on the data only: the same on every load, over http and file://.
   Links are curves drawn on the GPU like the network's (a cubic S-curve between planes, an arch within a plane, a petal
   for a term's link to itself, parallel links bowed apart; coarser on a software renderer), coloured by kind: subclass
   of, property (domain → range), alignment, in scheme. Classes are spheres (size ~ log instance count), concept schemes
   octahedra, external terms icosahedra, coloured by module (the paper's pastel palette) or by kind.
   Drawn like the figures of the paper (arXiv:2611.11426, Fig. 1 and Fig. 6; js/paper3d.js): white figure ground,
   bilingual call-outs (Libertinus Sans, white box, thin grey leader) placed in screen space so that no two overlap and
   none is cut by the canvas edge or hidden under an overlay, and the selection's chain and neighbourhood, or a CONSTRUCT
   result, as the traced path: a navy core over a pale-gold halo with everything else faded.
   Text follows the language mode of js/i18n.js (docs/i18n.md; dictionary js/i18n-3d.js, keys o3d.*): call-outs, plane
   names and legend in one language or as "Tiếng Việt · English" pairs, panel labels, status lines and the query drawer in
   one language. A mode change ('vl:lang') rebuilds them in place and keeps the camera, the selection, the query result
   and the filters. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome({ scene: true });
  M.page = 'ontology-3d';
  M.paperStyle = true;
  var PARAMS = VL.params();

  /* release scope (js/common.js VL.releaseScope): the terms populated from a later release (in v1 the judiciary module
     and vlo:Court) are left out of the playground; a note under the module chips says when they come */
  var OG0 = window.VLONTO.ontology_graph, SCOPE = VL.releaseScope(OG0), OG = {};
  Object.keys(OG0).forEach(function (k) { OG[k] = OG0[k]; });
  OG.nodes = SCOPE.nodes;
  OG.links = SCOPE.links;
  M.releaseScope = { release: SCOPE.release, hidden: SCOPE.hidden, hiddenProperties: SCOPE.hiddenProperties, hiddenLinks: SCOPE.hiddenLinks,
    laterModules: SCOPE.laterModules, nodes: OG.nodes.length, links: OG.links.length };
  var EXAMPLES = ((window.VLONTO.sparql_examples || {}).queries) || [];
  var app = VL.$('#app'), stage = VL.$('#stage'), host = VL.$('#canvas-host'), tip = VL.$('#tip');
  var panel = VL.$('#panel'), drawer = VL.$('#drawer'), legendEl = VL.$('#legend'), statusEl = VL.$('#status');
  /* the labels follow the global language mode (VL.lang()) */
  var state = {
    modules: {}, showExternal: true, showSchemes: true, planes: true, colorBy: 'module',
    links: { subClassOf: true, property: true, alignment: true, inScheme: true },
    particles: true, selected: null, selectedLink: null, view: 'ontology', cm: 'overlay', legendOpen: !VL.isMobile()
  };
  VL.MODULES.forEach(function (m) { if (!SCOPE.laterModules[m.id]) state.modules[m.id] = true; });
  M.colorBy = state.colorBy;

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
  M.ontologyNodes = nodes.length;
  M.ontologyLinks = links.length;
  /* the external vocabularies of the release, in the data's order (plane name, About text in js/scene-text.js) */
  var VOCAB = { eli: 'ELI', skos: 'SKOS', prov: 'PROV-O', org: 'ORG', schema: 'schema.org', dcterms: 'DCTERMS', foaf: 'FOAF', owl: 'OWL' };
  VL.playVocabs = [];
  nodes.forEach(function (n) {
    if (n.kind !== 'external') return;
    var p = n.id.split(':')[0], v = VOCAB[p] || p;
    if (VL.playVocabs.indexOf(v) < 0) VL.playVocabs.push(v);
  });

  function radius(n) {
    if (n.inst) return 2.6;
    if (n.kind === 'external') return 3.4;
    if (n.kind === 'scheme') return 3.6 + 0.9 * Math.log10((n.instances || 0) + 1);
    return 3.4 + 1.9 * Math.log10((n.instances || 0) + 1);
  }
  /* paper class of a node (null when it has none): classes by their CURIE, records of the KG by their class (the badge
     of the details panel) */
  function paperKey(n) {
    if (n.inst) return n.cls ? VL.paperClassKey(n.cls, true) : null;
    return n.kind === 'class' ? VL.paperClassKey(n.id) : null;
  }
  /* colour of a node: its module (the paper's pastels; external terms grey), or its kind (class, concept scheme,
     external term, instance of a CONSTRUCT result) */
  var KINDS = ['class', 'scheme', 'external', 'instance'];
  function kindOf(n) { return n.inst ? 'instance' : (n.kind === 'scheme' || n.kind === 'external' ? n.kind : 'class'); }
  function modOf(n) { return n.kind === 'external' ? 'external' : (n.module || 'provenance'); }
  function nodeColor(n) {
    if (state.colorBy === 'kind') return TH.kind[kindOf(n)] || TH.kind['class'];
    return VL.moduleColor(modOf(n));
  }
  function nodeVar(n) { return state.colorBy === 'kind' ? 'var(--o3d-kind-' + kindOf(n) + ')' : VL.moduleVar(modOf(n)); }
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
  var current = { byId: byId, nodes: nodes, links: links };
  function nodeOf(x) { return typeof x === 'object' ? x : current.byId[x]; }

  /* ------------------------------------------------------------------ layout: hierarchy planes, module bands
     planes (top to bottom): one per depth of the class hierarchy (the longest subclass path up to a root among the
     classes shown), then the concept schemes, then the external terms. Modules: weight = its roots + half its largest
     group on a lower plane; the hub (most links to other modules) sits in the middle of the front row, the others follow
     by their links to the hub, then weight, then palette order (VL.MODULES), alternately to its right and left round a
     cycle; the cycle is cut into a front and a back row of bands of the most even widths. Inside a band: the roots in
     short rows, every lower node under its anchor (superclasses / class of the scheme), siblings in rows of up to five;
     external terms under the centroid of the classes aligned to them (an isolated one in the middle); pairs closer than
     their radii plus LAY.pad move apart (fixed order and number of passes). Units: world units; node radii 2.6 to 14. */
  var LAY = { gap: 170, pad: 30, topPad: 44, rowMax: 5, topMax: 3, rowSep: 50, bandPad: 24, margin: 40, zig: 0.55, apron: 150, apronNarrow: 60 };
  function layoutPlanes(ns, ls) {
    var t0 = performance.now(), O = LAY, by = {};
    ns.forEach(function (n) { by[n.id] = n; });
    var parents = {}, alignTo = {}, schemeFor = {};
    ls.forEach(function (l) {
      var s = sid(l.source), t = sid(l.target);
      if (!by[s] || !by[t] || s === t) return;
      if (l.type === 'subClassOf') push(parents, s, t);
      else if (l.type === 'alignment') push(alignTo, t, s);
      else if (l.type === 'inScheme') push(schemeFor, t, s);
    });
    var depth = {}, busy = {};
    function dep(id) {
      if (depth[id] != null) return depth[id];
      if (busy[id]) return 0;
      busy[id] = true;
      var d = 0;
      (parents[id] || []).forEach(function (p) { if (by[p] && by[p].kind === 'class') d = Math.max(d, dep(p) + 1); });
      busy[id] = false;
      return (depth[id] = d);
    }
    var maxD = 0;
    ns.forEach(function (n) { if (n.kind === 'class') maxD = Math.max(maxD, dep(n.id)); });
    var planes = [];
    for (var d = 0; d <= maxD; d++) planes.push({ key: 'depth-' + d, kind: 'depth', depth: d, nodes: [] });
    var hasScheme = ns.some(function (n) { return n.kind === 'scheme'; }), hasExt = ns.some(function (n) { return n.kind === 'external'; });
    if (hasScheme) planes.push({ key: 'schemes', kind: 'scheme', depth: null, nodes: [] });
    if (hasExt) planes.push({ key: 'external', kind: 'external', depth: null, nodes: [] });
    var planeOf = {};
    ns.forEach(function (n) {
      var p = n.kind === 'class' ? depth[n.id] : n.kind === 'scheme' ? maxD + 1 : maxD + (hasScheme ? 2 : 1);
      planeOf[n.id] = p;
      planes[p].nodes.push(n);
    });
    function R(n) { return n.__r || 4; }
    /* module order */
    var canon = VL.MODULES.map(function (m) { return m.id; });
    function ci(m) { var i = canon.indexOf(m); return i < 0 ? 999 : i; }
    var present = {}, modW = {};
    ns.forEach(function (n) { if (n.kind !== 'external') present[n.module] = true; });
    var modList = Object.keys(present).sort(function (a, b) { return ci(a) - ci(b) || (a < b ? -1 : 1); });
    modList.forEach(function (m) {
      var top = planes[0].nodes.filter(function (n) { return n.module === m; }).length, low = 0;
      planes.forEach(function (pl, i) { if (i) low = Math.max(low, pl.nodes.filter(function (n) { return n.module === m; }).length); });
      modW[m] = top + 0.5 * low + 0.5;
    });
    var aff = {}, deg = {};
    ls.forEach(function (l) {
      var a = by[sid(l.source)], b = by[sid(l.target)];
      if (!a || !b || a.module === b.module || a.kind === 'external' || b.kind === 'external') return;
      aff[a.module + '|' + b.module] = (aff[a.module + '|' + b.module] || 0) + 1;
      aff[b.module + '|' + a.module] = (aff[b.module + '|' + a.module] || 0) + 1;
      deg[a.module] = (deg[a.module] || 0) + 1;
      deg[b.module] = (deg[b.module] || 0) + 1;
    });
    var hub = modList.slice().sort(function (a, b) { return (deg[b] || 0) - (deg[a] || 0) || modW[b] - modW[a] || ci(a) - ci(b); })[0];
    var rest = modList.filter(function (m) { return m !== hub; }).sort(function (a, b) {
      return (aff[b + '|' + hub] || 0) - (aff[a + '|' + hub] || 0) || modW[b] - modW[a] || ci(a) - ci(b);
    });
    var right = [], left = [];
    rest.forEach(function (m, i) { (i % 2 ? left : right).push(m); });
    /* local layout of every module: x across its band, z front (+) to back (-) */
    var loc = {};
    function grid(list, cx, cz, rowMax, P2, pad) {
      var k = list.length;
      if (!k) return;
      P2 = P2 || loc;
      var rmax = 0;
      list.forEach(function (n) { rmax = Math.max(rmax, R(n)); });
      var sp = 2 * rmax + (pad || O.pad), rows = Math.ceil(k / rowMax), per = Math.ceil(k / rows);
      list.forEach(function (n, i) {
        var r = Math.floor(i / per), c = i % per, inRow = Math.min(per, k - r * per);
        var u = (c - (inRow - 1) / 2) * sp, v = (r - (rows - 1) / 2) * sp * 0.9;
        if (rows === 1 && k > 2) v += (c % 2 ? -1 : 1) * sp * O.zig * 0.5;     // a light zig-zag: call-outs stack apart
        P2[n.id] = { x: cx + u, z: cz + v };
      });
    }
    function centroid(ids, P2) {
      var x = 0, z = 0, c = 0;
      ids.forEach(function (id) { if (P2[id]) { x += P2[id].x; z += P2[id].z; c++; } });
      return c ? { x: x / c, z: z / c } : null;
    }
    function under(list, anchorOf, rowMax, P2, fallback) {
      var spots = {}, keys = [];
      list.forEach(function (n) {
        var c = centroid(anchorOf(n), P2) || fallback;
        var key = Math.round(c.x) + ',' + Math.round(c.z);
        if (!spots[key]) { spots[key] = { c: c, list: [] }; keys.push(key); }
        spots[key].list.push(n);
      });
      keys.forEach(function (k) { grid(spots[k].list, spots[k].c.x, spots[k].c.z, rowMax, P2); });
    }
    function relax(list, P2, passes, pad) {
      for (var it = 0; it < passes; it++) {
        var moved = 0;
        for (var a = 0; a < list.length; a++) for (var b = a + 1; b < list.length; b++) {
          var A = P2[list[a].id], B = P2[list[b].id], dx = B.x - A.x, dz = B.z - A.z, dd = Math.sqrt(dx * dx + dz * dz);
          var need = R(list[a]) + R(list[b]) + (pad || O.pad);
          if (dd >= need) continue;
          var ux, uz;
          if (dd < 1e-6) { var ang = ((a * 7 + b * 13) % 360) * Math.PI / 180; ux = Math.cos(ang); uz = Math.sin(ang); }
          else { ux = dx / dd; uz = dz / dd; }
          var shift = (need - dd) / 2 + 0.01;
          A.x -= ux * shift; A.z -= uz * shift; B.x += ux * shift; B.z += uz * shift;
          moved++;
        }
        if (!moved) break;
      }
    }
    modList.forEach(function (m) {
      function mine(n) { return n.module === m; }
      grid(planes[0].nodes.filter(mine), 0, 0, O.topMax, loc, O.topPad);   // the top plane holds most call-outs: wider spacing
      for (var p = 1; p < planes.length; p++) {
        var pl = planes[p];
        if (pl.kind === 'external') continue;
        under(pl.nodes.filter(mine), function (n) { return pl.kind === 'depth' ? (parents[n.id] || []) : (schemeFor[n.id] || []); }, O.rowMax, loc, { x: 0, z: 0 });
      }
      planes.forEach(function (pl, k) { if (pl.kind !== 'external') relax(pl.nodes.filter(mine), loc, 300, k ? O.pad : O.topPad); });
    });
    /* bands: footprint of each module over all planes; front row = a run of the cycle round the hub */
    var fp = {};
    modList.forEach(function (m) {
      var f = { lo: Infinity, hi: -Infinity, zlo: Infinity, zhi: -Infinity };
      ns.forEach(function (n) {
        if (n.module !== m || !loc[n.id]) return;
        var q = loc[n.id], r = R(n);
        f.lo = Math.min(f.lo, q.x - r); f.hi = Math.max(f.hi, q.x + r); f.zlo = Math.min(f.zlo, q.z - r); f.zhi = Math.max(f.zhi, q.z + r);
      });
      f.w = f.hi - f.lo;
      fp[m] = f;
    });
    var bgap = O.pad + O.bandPad;
    function rowW(list) { var w = 0; list.forEach(function (m, i) { w += fp[m].w + (i ? bgap : 0); }); return w; }
    /* the split: rows of even widths with the hub near the middle of the front row */
    var best = null;
    for (var i = 0; i <= right.length; i++) for (var j = 0; j <= left.length; j++) {
      if (i + j === right.length + left.length && i + j > 0) continue;        // the back row keeps at least one module
      var lf = left.slice(0, j).reverse(), rt = right.slice(0, i);
      var front = lf.concat([hub], rt);
      var back = right.slice(i).concat(left.slice(j).reverse());               // the cycle runs right to left along the back
      var sc = Math.abs(rowW(front) - rowW(back)) + 0.5 * Math.abs((lf.length ? rowW(lf) + bgap : 0) - (rt.length ? rowW(rt) + bgap : 0)) + 0.01 * Math.abs(i - j);
      if (!best || sc < best.sc - 1e-9) best = { sc: sc, front: front, back: back.reverse() };
    }
    if (!modList.length) best = { front: [], back: [] };
    var zF = O.rowSep / 2, zB = -O.rowSep / 2;
    best.front.forEach(function (m) { zF = Math.max(zF, O.rowSep / 2 - fp[m].zlo); });
    best.back.forEach(function (m) { zB = Math.min(zB, -O.rowSep / 2 - fp[m].zhi); });
    var pos = {}, bands = {};
    [[best.front, zF, 'front'], [best.back, zB, 'back']].forEach(function (row) {
      var x = -rowW(row[0]) / 2;
      row[0].forEach(function (m) {
        var off = x - fp[m].lo;
        bands[m] = { x0: Math.round(x), x1: Math.round(x + fp[m].w), z: Math.round(row[1]), row: row[2] };
        ns.forEach(function (n) { if (n.module === m && loc[n.id]) pos[n.id] = { x: loc[n.id].x + off, z: loc[n.id].z + row[1] }; });
        x += fp[m].w + bgap;
      });
    });
    /* external terms: under the classes aligned to them */
    if (hasExt) {
      var ext = planes[planes.length - 1];
      under(ext.nodes, function (n) { return alignTo[n.id] || []; }, O.rowMax, pos, { x: 0, z: 0 });
    }
    ns.forEach(function (n) { if (!pos[n.id]) pos[n.id] = { x: 0, z: 0 }; });
    planes.forEach(function (pl, k) { relax(pl.nodes, pos, 400, k ? O.pad : O.topPad); });
    /* centre the extents; plane heights from the top */
    var x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
    ns.forEach(function (n) { var q = pos[n.id], r = R(n); x0 = Math.min(x0, q.x - r); x1 = Math.max(x1, q.x + r); z0 = Math.min(z0, q.z - r); z1 = Math.max(z1, q.z + r); });
    if (!isFinite(x0)) { x0 = z0 = -1; x1 = z1 = 1; }
    var cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, yTop = (planes.length - 1) * O.gap / 2;
    planes.forEach(function (pl, k) { pl.index = k; pl.y = yTop - k * O.gap; pl.count = pl.nodes.length; });
    var out = {};
    ns.forEach(function (n) {
      var q = pos[n.id];
      out[n.id] = { x: q.x - cx, y: planes[planeOf[n.id]].y, z: q.z - cz, plane: planeOf[n.id], depth: depth[n.id] != null ? depth[n.id] : null };
    });
    return { pos: out, planes: planes, depthMax: maxD, half: { x: (x1 - x0) / 2 + O.margin, z: (z1 - z0) / 2 + O.margin },
      front: best.front, back: best.back, hub: hub, bands: bands, ms: Math.round((performance.now() - t0) * 10) / 10 };
  }
  var LAYOUT = layoutPlanes(nodes, links);
  var PLANES = LAYOUT.planes;
  nodes.forEach(function (n) {
    var q = LAYOUT.pos[n.id];
    n.x = q.x; n.y = q.y; n.z = q.z;
    n.__plane = q.plane;
    n.__depth = q.depth;
  });
  M.layout = { kind: 'planes', planes: PLANES.length, gap: LAY.gap, hub: LAYOUT.hub, front: LAYOUT.front, back: LAYOUT.back,
    half: { x: Math.round(LAYOUT.half.x), z: Math.round(LAYOUT.half.z) }, ms: LAYOUT.ms, deterministic: true };
  M.nodeLayer = {};
  M.nodeDepth = {};
  nodes.forEach(function (n) { M.nodeLayer[n.id] = n.__plane; M.nodeDepth[n.id] = n.__depth; });
  function planeKey(pl) { return pl.key; }

  /* ------------------------------------------------------------------ curved links (the network's GPU curves)
     One instanced strip per link: S + 1 points (aT) run through a cubic Bezier from A to B with vertical tangents
     (k = 0.45 dy), lifted into an arch when both ends are on one plane (lift = min(BEND |AB|xz, LIFT_MAX), fading out as
     the height difference grows to a plane gap) - the curve of js/network3d.js. Parallel links between the same two
     terms bow apart sideways (aBow: the offset at the middle); a link from a term to itself is a petal rising above it
     (aLoop: direction angle, height, reach), the petals of one term in a fan behind it (away from the camera, so the
     space in front stays free for its call-out). Colour runs from the kind's colour
     at the source to 20 % toward the ground at the target (direction); aAlpha fades or hides a link (filters, highlight).
     curvePoint() is the same curve on the CPU (traced path, emphasised links, call-out ink, picking, particles, arrows). */
  var GAP = LAY.gap, BEND = 0.18, LIFT_MAX = 0.4 * GAP;
  var CURVES = PARAMS.curves !== '0', CURVE_FULL = PARAMS.curves === 'full', SOFT_GL = false;
  var FOG = { value: new THREE.Vector3(1, 1e6, 0) };
  var CV_VS = [
    'attribute float aT; attribute vec3 aA; attribute vec3 aB; attribute vec3 aBow; attribute vec3 aLoop;',
    'attribute vec3 aColA; attribute vec3 aColB; attribute float aAlpha;',
    'uniform float uBend; uniform float uLiftMax; uniform float uLayer; uniform vec3 uFog;',
    'varying vec3 vColor; varying float vAlpha; varying float vFog;',
    'void main() {',
    '  vAlpha = aAlpha;',
    '  if (aAlpha < 0.01) { vColor = vec3(0.0); vFog = 0.0; gl_Position = vec4(0.0, 0.0, 2.0, 1.0); return; }',
    '  vColor = mix(aColA, aColB, aT);',
    '  float t = aT; vec3 p;',
    '  if (aLoop.y > 0.0) {',
    '    float th = 3.14159265 * t, s1 = sin(th);',
    '    vec3 dir = vec3(cos(aLoop.x), 0.0, sin(aLoop.x)), side = vec3(-dir.z, 0.0, dir.x);',
    '    p = aA + dir * (aLoop.z * s1) + side * (0.5 * aLoop.z * sin(2.0 * th)) + vec3(0.0, aLoop.y * s1, 0.0);',
    '  } else {',
    '    vec3 d = aB - aA;',
    '    float k = 0.45 * d.y, lift = min(uBend * length(d.xz), uLiftMax) * clamp(1.0 - abs(d.y) / uLayer, 0.0, 1.0);',
    '    float u = 1.0 - t, w0 = u * u * u, w1 = 3.0 * u * u * t, w2 = 3.0 * u * t * t, w3 = t * t * t;',
    '    p = vec3((w0 + w1) * aA.x + (w2 + w3) * aB.x,',
    '      w0 * aA.y + w1 * (aA.y + k + lift) + w2 * (aB.y - k + lift) + w3 * aB.y,',
    '      (w0 + w1) * aA.z + (w2 + w3) * aB.z) + aBow * (4.0 * t * u);',
    '  }',
    '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
    '  vFog = clamp((-mv.z - uFog.x) / max(1.0, uFog.y - uFog.x), 0.0, 1.0) * uFog.z;',
    '  gl_Position = projectionMatrix * mv;',
    '}'].join('\n');
  var CV_FS = [
    'uniform float uOpacity; varying vec3 vColor; varying float vAlpha; varying float vFog;',
    'void main() {',
    '  if (vAlpha < 0.01) discard;',
    '  gl_FragColor = vec4(vColor, vAlpha * uOpacity * (1.0 - vFog));',
    '}'].join('\n');
  /* the shape of every link of a set: petals for links to the same term, bows for parallel links */
  function assignShapes(ls) {
    var cnt = {}, idx = {}, loops = {}, loopIdx = {};
    ls.forEach(function (l) {
      var s = sid(l.source), t = sid(l.target);
      if (s === t) loops[s] = (loops[s] || 0) + 1;
      else { var k = s < t ? s + '|' + t : t + '|' + s; cnt[k] = (cnt[k] || 0) + 1; }
    });
    ls.forEach(function (l) {
      var s = sid(l.source), t = sid(l.target);
      l.__loop = null;
      l.__bow = 0;
      if (s === t) {
        var i = loopIdx[s] = (loopIdx[s] || 0) + 1, n = loops[s];
        l.__loop = { i: i - 1, n: n };
      } else {
        var k = s < t ? s + '|' + t : t + '|' + s, m = cnt[k];
        if (m > 1) {
          var j = idx[k] = (idx[k] || 0) + 1;
          l.__bow = ((j - 1) - (m - 1) / 2) * 0.32 * (s < t ? 1 : -1);    // fraction of the link length, signed by direction
        }
      }
      l.__curve = l.__curve || { getPoints: function (n) { return curvePts(l, n); } };
    });
  }
  /* curve parameters of a link from the current node positions */
  function shapeOf(l) {
    var a = nodeOf(l.source), b = nodeOf(l.target);
    if (!a || !b || !isFinite(a.x) || !isFinite(b.x)) return null;
    var g = { ax: a.x, ay: a.y, az: a.z, bx: b.x, by: b.y, bz: b.z, bow: [0, 0, 0], loop: [0, 0, 0] };
    if (l.__loop) {
      var r = a.__r || 4, i = l.__loop.i, n = l.__loop.n;
      g.loop = [-Math.PI / 2 + (n > 1 ? (i / (n - 1) - 0.5) * 2.1 : 0), 2.1 * r + 7 + 3 * (i % 2), 1.5 * r + 5 + 2 * (i % 3)];   // a fan behind the term
      g.bx = a.x; g.by = a.y; g.bz = a.z;
    } else if (l.__bow) {
      var dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z, L = Math.sqrt(dx * dx + dy * dy + dz * dz), h = Math.sqrt(dx * dx + dz * dz);
      var sx = h > 1e-6 ? -dz / h : 1, sz = h > 1e-6 ? dx / h : 0;
      g.bow = [sx * l.__bow * L, 0, sz * l.__bow * L];
    }
    return g;
  }
  function curveAt(g, t) {
    if (g.loop[1] > 0) {
      var th = Math.PI * t, s1 = Math.sin(th), c = Math.cos(g.loop[0]), s = Math.sin(g.loop[0]), s2 = 0.5 * g.loop[2] * Math.sin(2 * th);
      return { x: g.ax + c * g.loop[2] * s1 - s * s2, y: g.ay + g.loop[1] * s1, z: g.az + s * g.loop[2] * s1 + c * s2 };
    }
    var dx = g.bx - g.ax, dy = g.by - g.ay, dz = g.bz - g.az, k = 0.45 * dy;
    var lift = Math.min(BEND * Math.sqrt(dx * dx + dz * dz), LIFT_MAX) * Math.max(0, Math.min(1, 1 - Math.abs(dy) / GAP));
    var u = 1 - t, w0 = u * u * u, w1 = 3 * u * u * t, w2 = 3 * u * t * t, w3 = t * t * t, bw = 4 * t * u;
    return { x: (w0 + w1) * g.ax + (w2 + w3) * g.bx + g.bow[0] * bw,
      y: w0 * g.ay + w1 * (g.ay + k + lift) + w2 * (g.by - k + lift) + w3 * g.by + g.bow[1] * bw,
      z: (w0 + w1) * g.az + (w2 + w3) * g.bz + g.bow[2] * bw };
  }
  function curvePts(l, n) {
    var g = shapeOf(l);
    if (!g) return null;
    if (!CURVES && !l.__loop) n = 1;
    var out = [];
    for (var i = 0; i <= n; i++) out.push(curveAt(g, i / n));
    return out;
  }
  /* segments per link: 16 (petals 18), 8 (10) on a software renderer unless #curves=full; #curves=0 straight */
  function segsFor(loop) {
    if (loop) return SOFT_GL && !CURVE_FULL ? 10 : 18;
    if (!CURVES) return 1;
    return SOFT_GL && !CURVE_FULL ? 8 : 16;
  }

  /* ------------------------------------------------------------------ highlight state */
  /* hl.nodes / hl.links: the selection's neighbourhood and chain, or the CONSTRUCT result (everything else fades).
     hl.trace: the links drawn as the traced path (navy core over the gold halo) - all of them when there are few
     (hl.max), else only the chain up the hierarchy and the links to a hovered node, as in the paper, where only the
     traced path is dark; the other highlighted links stay thin lines in their own colours. */
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
    var ls2 = null;
    if (n && hl.links && hl.nodes && hl.nodes.has(n) && n !== state.selected) {
      var ls = [];
      hl.links.forEach(function (l) {
        var a = nodeOf(l.source), b = nodeOf(l.target);
        if (state.selected ? ((a === n && b === state.selected) || (b === n && a === state.selected)) : (a === n || b === n)) ls.push(l);
      });
      if (ls.length && ls.length <= RESULT_TRACE_MAX) ls2 = new Set(ls);
    }
    var node = ls2 ? n : null;
    if (node === hl.hoverNode) return;
    hl.hoverNode = node;
    hl.hoverLinks = ls2;
    M.hoverTrace = ls2 ? ls2.size : 0;
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
    needsRender = true;
  }
  /* the traced path (hl.trace) as a navy core over a pale-gold halo, at constant pixel width and following the curves;
     thinner for large small-result traces, never wider than VL.TRACE_W */
  var trace = null, emph = null;
  function updateTrace() {
    if (!scene) return;
    var paths = [];
    if (hl.trace) hl.trace.forEach(function (l) {
      if (!linkVisible(l)) return;
      var pts = VL.linkPoints(l, l.__loop ? 18 : 16);
      if (pts) paths.push(pts);
    });
    trace.setStyle(VL.traceStyle(P, paths.length > 150 ? 0.62 : (paths.length > 60 ? 0.8 : 1)));
    trace.setPaths(paths);
    M.traceLinks = paths.length;
    M.traceSegments = trace.count();
    needsRender = true;
  }

  /* ------------------------------------------------------------------ labels: constant pixel size + screen-space culling */
  /* call-out heights in CSS px for one line (the text itself is about px / 1.68) */
  var labelPx = { 'class': 23, scheme: 22, external: 21, instance: 21 };
  var SELECTED_PX = 26, PLANE_PX = 21;
  function worldPerPx() { return VL.spriteWpp(camera, host.clientHeight); }
  /* scene colours of the current theme (css/site.css: the paper style tokens, --scene-bg, --net-plane*, --o3d-lt-*,
     --o3d-kind-*, --o3d-link-*) */
  var TH = {}, P = {};
  var LINK_TYPES = ['subClassOf', 'property', 'alignment', 'inScheme'];
  var LT_TOKEN = { subClassOf: '--o3d-lt-subclass', property: '--o3d-lt-property', alignment: '--o3d-lt-alignment', inScheme: '--o3d-lt-inscheme',
    instance: '--o3d-link-instance', result: '--o3d-link-result' };
  var LT_FALLBACK = { subClassOf: '#6e8fc4', property: '#e09a6a', alignment: '#9c9fa6', inScheme: '#b08fd0', instance: '#c9cdd3', result: '#ecc890' };
  var LT_KEY = { subClassOf: 'o3d.lt.subClassOf', property: 'o3d.lt.property', alignment: 'o3d.lt.alignment', inScheme: 'o3d.lt.inScheme',
    instance: 'o3d.instanceOf', result: 'o3d.link.result' };
  /* opacity of each kind of link (thin lines: the hierarchy reads first, alignments stay in the background) */
  var LT_ALPHA = { subClassOf: 0.92, property: 0.85, alignment: 0.5, inScheme: 0.75, instance: 0.75, result: 0.85 };
  function readTheme() {
    P = VL.paperTheme();
    TH = {
      dark: P.dark,
      bg: P.bg,
      plane: VL.tok('--net-plane') || '#c9ced6', planeOpacity: VL.tokNum('--net-plane-opacity', 0.14),
      planeLine: VL.tok('--net-plane-line') || '#d3d7dc', planeLineOpacity: VL.tokNum('--net-plane-line-opacity', 1),
      link: {}, kind: {},
      linkDim: VL.tok('--o3d-link-dim') || '#eceef2'
    };
    Object.keys(LT_TOKEN).forEach(function (k) { TH.link[k] = VL.tok(LT_TOKEN[k]) || LT_FALLBACK[k]; });
    KINDS.forEach(function (k) { TH.kind[k] = VL.tok('--o3d-kind-' + k) || '#9aa3ad'; });
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
    planeLabels.forEach(function (s) { s.fit(w); });
  }
  function relabel() {
    current.nodes.forEach(function (n) { if (n.__label) n.__label.setLines(labelLines(n)); });
    planeLabels.forEach(function (s) { s.setLines(planeLines(s.__plane)); });
    M.labelsLang = VL.lang();
    scheduleCull();
  }
  /* who keeps a call-out when space is short: the selection, the highlight, records of a result, then classes by their
     weight in the ontology - links in the release (the hub first), height in the hierarchy, then instance count -
     then concept schemes, then external terms */
  var DEGREE = {};
  links.forEach(function (l) { [sid(l.source), sid(l.target)].forEach(function (id) { DEGREE[id] = (DEGREE[id] || 0) + 1; }); });
  function priority(n) {
    if (state.selected === n) return 1e12;
    var p = 0;
    if (hl.nodes && hl.nodes.has(n)) p += 1e9;
    if (n.inst) p += 5e6;
    var lg = Math.log10((n.instances || 0) + 1);
    if (n.kind === 'class') p += 1e6 + 1e4 * Math.min(60, DEGREE[n.id] || 0) + 2e3 * (LAYOUT.depthMax - (n.__depth || 0)) + 100 * lg;
    else if (n.kind === 'scheme') p += 5e5 + 1e3 * (DEGREE[n.id] || 0) + 100 * lg;
    else p += 1e5 + 1e3 * (DEGREE[n.id] || 0);
    return p;
  }
  /* plane names: "Tầng 0 · Lớp gốc" over "Level 0 · Root classes" (EN–VI) or one line (EN, VI), on the plane at its
     front-left corner like the rank names of the legal network (the planes reach a label apron beyond the terms on that
     side), or at its back-left corner where an overlay (legend, hint, panel) covers the front one */
  var planeLabels = [];
  function planeLines(pl) {
    if (pl.kind === 'depth') return VL.paperTL(pl.depth === 0 ? 'o3d.plane.root' : 'o3d.plane.sub', { d: pl.depth }, P, { twoLines: true });
    if (pl.kind === 'scheme') return VL.paperTL('o3d.plane.schemes', null, P, { twoLines: true });
    return VL.paperTL('o3d.plane.external', null, P, { twoLines: true });
  }
  /* screen-space declutter shared with the legal network and the CONSTRUCT view (js/paper3d.js VL.Callouts): call-outs
     sit in clear space on thin leaders, never over a node or a link and never over each other; the selected node and
     the nodes of the traced path always keep theirs; plane names sit at the plane corner. Ink = every visible node disc
     and every link that is not faded. */
  var callouts = null, lastPlacement = '', labelGen = 0;
  function nodeR(n) { return n.__r * (state.selected === n ? 1.3 * 1.34 : 1.07); }
  function planeOffset(w) { return [w / 2 + 2, 0]; }
  function planeOffsetR(w) { return [-w / 2 - 2, 0]; }
  /* the hub: with nothing highlighted, the visible class with the most links keeps its call-out like a traced node */
  function hubNode() {
    var best = null;
    current.nodes.forEach(function (n) { if (!n.inst && n.kind === 'class' && nodeVisible(n) && (!best || (DEGREE[n.id] || 0) > (DEGREE[best.id] || 0))) best = n; });
    return best;
  }
  function calloutItems() {
    var out = [], hub = hlActive() ? null : hubNode();
    M.hubCallout = hub ? hub.id : null;
    current.nodes.forEach(function (n) {
      var s = n.__label;
      if (!s) return;
      var off = !nodeVisible(n) || !n.__obj || !isFinite(n.x) || (hlActive() && !hl.nodes.has(n));
      out.push({ id: n.id, sprite: s, pri: priority(n), must: !off && (isMust(n) || n === hub), sel: !off && state.selected === n, r: nodeR(n), off: off });
    });
    var ui = planeLabels.length ? obstacles().slice() : [], sz = stageSize(), ink = null;
    if (planeLabels.length) { camera.updateMatrixWorld(); ink = inkSegs(sz); }
    planeLabels.forEach(function (s) {
      var on = planeShown(s.__plane);
      if (on) placePlaneLabel(s, ui, sz, ink);
      /* with nothing highlighted a plane name with a clear spot at its plane is placed first (kept like a traced
         call-out); a name on a leader, or any name while something is selected, competes like any call-out */
      var keep = on && !hlActive() && s.__fixed;
      out.push({ id: 'plane-' + s.__plane.key, sprite: s, pri: (keep ? 3e9 : 3e6) - s.__plane.index, must: keep, sel: false, r: 0, fixed: s.__fixed ? (s.__side === 'R' ? planeOffsetR : planeOffset) : null, off: !on });
    });
    return out;
  }
  /* where a plane name goes: at the front-left corner (the network's place), box to its right over the label apron;
     where an overlay (legend, hint, panel, tools, status) or ink (a term, a link) is in the way, further back along the
     plane's left edge (a quarter, half, three quarters, the back-left corner), then along its right edge from the
     front-right corner (box to the left) - the first box clear of all of them and inside the canvas. Where there is none (a narrow stage, a tall legend) the name is an ordinary call-out on a leader
     from the first anchor clear of the overlays, so VL.Callouts finds it a clear place. */
  var PLANE_SPOTS = [['L', 0], ['L', 0.25], ['L', 0.5], ['L', 0.75], ['L', 1], ['R', 0], ['R', 0.25], ['R', 0.5], ['R', 0.75], ['R', 1]];
  function inkSegs(sz) {
    var discs = [], segs = [], ink = calloutInk(), tv = Math.tan(camera.fov * Math.PI / 360);
    ink.discs.forEach(function (d) { var q = toScreen(d.x, d.y, d.z, sz); if (q) discs.push({ x: q.x, y: q.y, r: d.r / (q.d * tv) * (sz.h / 2) }); });
    ink.paths.forEach(function (pts) {
      var prev = null;
      pts.forEach(function (p) { var q = toScreen(p.x, p.y, p.z, sz); if (q && prev) segs.push([prev.x, prev.y, q.x, q.y]); prev = q; });
    });
    return { discs: discs, segs: segs };
  }
  function boxHitsInk(b, ink) {
    if (ink.discs.some(function (d) { var cx = Math.max(b.x0, Math.min(d.x, b.x1)), cy = Math.max(b.y0, Math.min(d.y, b.y1)); return Math.hypot(cx - d.x, cy - d.y) < Math.max(d.r, 0) + 3; })) return true;   // VL.Callouts keeps 2 px from a node centre
    return ink.segs.some(function (g) { return segHitsBox(g, b); });
  }
  function segHitsBox(g, b) {
    var x0 = g[0], y0 = g[1], dx = g[2] - g[0], dy = g[3] - g[1], t0 = 0, t1 = 1, P2 = [-dx, dx, -dy, dy], Q = [x0 - b.x0 + 1, b.x1 + 1 - x0, y0 - b.y0 + 1, b.y1 + 1 - y0];
    for (var i = 0; i < 4; i++) {
      if (P2[i] === 0) { if (Q[i] < 0) return false; continue; }
      var t = Q[i] / P2[i];
      if (P2[i] < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
    }
    return true;
  }
  function placePlaneLabel(s, ui, sz, ink) {
    var R = planeRect(), y = s.__plane.y - 2, ss = s.screenSize ? s.screenSize() : { w: 140, h: 22 }, fixed = null, anchor = null;
    /* the margins of VL.Callouts: a box keeps 2 px from an overlay (3 here), an anchor must not be under one */
    function inUi(x0, y0, x1, y1, m) { return ui.some(function (u) { return x0 - m < u.x1 && u.x0 < x1 + m && y0 - m < u.y1 && u.y0 < y1 + m; }); }
    PLANE_SPOTS.some(function (c) {
      var x = c[0] === 'L' ? R.x0 : R.x1, z = R.z1 - c[1] * (R.z1 - R.z0), q = toScreen(x, y, z, sz);
      if (!q || q.x < 0 || q.y < 0 || q.x > sz.w || q.y > sz.h || inUi(q.x, q.y, q.x, q.y, 0)) return false;
      if (!anchor) anchor = { side: c[0], f: c[1], x: x, z: z };
      var b = c[0] === 'L' ? { x0: q.x + 2, x1: q.x + 2 + ss.w, y0: q.y - ss.h / 2, y1: q.y + ss.h / 2 } : { x0: q.x - 2 - ss.w, x1: q.x - 2, y0: q.y - ss.h / 2, y1: q.y + ss.h / 2 };
      if (b.x0 >= 5 && b.y0 >= 5 && b.x1 <= sz.w - 5 && b.y1 <= sz.h - 5 && !inUi(b.x0, b.y0, b.x1, b.y1, 3) && !boxHitsInk(b, ink)) { fixed = { side: c[0], f: c[1], x: x, z: z, box: b }; return true; }
      return false;
    });
    var pick = fixed || anchor || { side: 'L', f: 0, x: R.x0, z: R.z1 };
    if (fixed) ui.push({ x0: fixed.box.x0 - 2, y0: fixed.box.y0 - 2, x1: fixed.box.x1 + 2, y1: fixed.box.y1 + 2 });   // the next plane's name keeps clear of it
    s.__fixed = !!fixed;
    s.__side = pick.side;
    s.__corner = (pick.side === 'L' ? 'left' : 'right') + ' ' + pick.f + (fixed ? '' : ' (leader)');
    if (s.position.z !== pick.z || s.position.x !== pick.x || s.position.y !== y) s.position.set(pick.x, y, pick.z);
  }
  /* ink: every visible term, and the links that matter in the view - with a highlight its links; without one the
     subclass, property and result links (the long alignment and scheme curves run faint through the planes, as
     background like the network's faded cloud) */
  var BACKGROUND_LINK = { alignment: true, inScheme: true };
  function calloutInk() {
    var discs = [], paths = [];
    current.nodes.forEach(function (n) {
      if (nodeVisible(n) && n.__obj && isFinite(n.x)) discs.push({ id: n.id, x: n.x, y: n.y, z: n.z, r: nodeR(n) });
    });
    current.links.forEach(function (l) {
      if (!linkVisible(l) || (hlActive() ? !inHl(l) : BACKGROUND_LINK[l.type])) return;
      var pts = VL.linkPoints(l, l.__loop ? 8 : 6);
      if (pts) paths.push(pts);
    });
    return { discs: discs, paths: paths };
  }
  function scheduleCull() {
    if (!camera) return;
    if (!callouts) {
      callouts = VL.Callouts({
        camera: function () { return camera; },
        size: function () { return { w: host.clientWidth, h: host.clientHeight }; },
        items: calloutItems, ink: calloutInk, ui: obstacles,
        leaderColor: function () { return P.leader; },
        metrics: M, key: 'callouts',
        onDone: function (st) {
          M.labelsShown = st.shown;
          M.labelsHidden = st.hidden;
          updateFog();
          var sig = labelGen + '#' + st.placed.map(function (q) { return q.id + ':' + q.box.join(','); }).join('|');
          if (sig !== lastPlacement) { lastPlacement = sig; needsRender = true; }
        }
      });
    }
    callouts.schedule();
  }
  function cullLabels() { if (camera) { scheduleCull(); callouts.run(); } }
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
    mesh.renderOrder = 2;
    var rim = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.BackSide, transparent: true, opacity: 0.95 }));
    rim.renderOrder = 2;
    var halo = new THREE.Mesh(GEO.sphere, new THREE.MeshBasicMaterial({ color: 0xecc890, side: THREE.BackSide, transparent: true, opacity: 0.9, depthWrite: false }));
    halo.visible = false;
    halo.renderOrder = 2;
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
    g.__node = n;
    g.position.set(n.x, n.y, n.z);
    labelGen++;
    styleNode(n, !hl.nodes || hl.nodes.has(n), state.selected === n);
    return g;
  }
  function disposeNode(n) {
    if (!n.__obj) return;
    if (n.__obj.parent) n.__obj.parent.remove(n.__obj);
    [n.__mesh, n.__rim, n.__halo].forEach(function (o) { if (o && o.material) o.material.dispose(); });
    if (n.__label) n.__label.dispose();
    n.__obj = n.__mesh = n.__rim = n.__halo = n.__label = null;
  }

  /* ------------------------------------------------------------------ link styling */
  /* every link in the colour of its kind; a highlighted link that is not traced is drawn over it as a thin line of
     constant width in that colour, a little deeper on the white ground (a CONSTRUCT result link: the colour of its
     predicate); the traced ones lie under the traced path; the rest fade */
  function linkBaseColor(l) { return TH.link[l.type] || TH.link.property; }
  function inTrace(l) { return hlActive() && !!hl.trace && hl.trace.has(l); }
  function emphColor(l) {
    var c = l.type === 'result' ? VL.predColor(l.pred) : linkBaseColor(l);
    return P.dark ? c : rimHex(c, 0.9);
  }
  function hasArrow(l) { return l.type === 'property' || l.type === 'subClassOf' || l.type === 'result'; }
  function hasParticles(l) { return l.type === 'property' || l.type === 'result'; }
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

  /* ------------------------------------------------------------------ the scene (three.js, rendered on demand) */
  var renderer = null, scene = null, camera = null, controls = null, lights = null, fog = null;
  var nodeGroup = null, planeGroup = null, labelGroup = null, edgeObjs = [], arrows = null, particles = null;
  var needsRender = true, tween = null, frames = 0, measuring = 0, sceneR = 400;
  function stageSize() { return { w: Math.max(50, host.clientWidth), h: Math.max(50, host.clientHeight) }; }
  function rgb(hex) { return VL.rawColor(hex, new THREE.Color()).toArray(); }
  function initThree() {
    var sz = stageSize();
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(sz.w, sz.h);
    renderer.setClearColor(TH.bg, 1);
    host.appendChild(renderer.domElement);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, sz.w / sz.h, 5, 80000);
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.09;
    controls.screenSpacePanning = true;
    controls.rotateSpeed = 0.55;
    controls.zoomSpeed = 0.9;
    controls.minDistance = 30;
    controls.maxDistance = 12000;
    controls.addEventListener('change', function () { needsRender = true; scheduleCull(); });
    controls.addEventListener('start', function () { hideHint(); if (tween) { tween = null; M.flying = false; } });   // a drag ends a flight
    /* the paper's light (upper left of the screen) and depth fade to the ground colour */
    lights = VL.paperLights(P.dark);
    scene.add(lights.ambient);
    VL.attachCameraLight(scene, camera, lights.directional);
    fog = VL.paperFog(scene, TH.bg);
    planeGroup = new THREE.Group();
    nodeGroup = new THREE.Group();
    labelGroup = new THREE.Group();
    scene.add(planeGroup);
    scene.add(nodeGroup);
    scene.add(labelGroup);
    /* the highlighted links that are not traced (thin lines in their colours) and the traced path */
    emph = VL.ColorLines({ depthTest: true, renderOrder: 6, width: 1.5, opacity: 0.95 });
    trace = VL.TraceLines({ depthTest: true, renderOrder: 8 });
    scene.add(emph.object);
    scene.add(trace.object);
    try {
      var gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
      M.webglRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    } catch (e) { M.webglRenderer = null; }
    SOFT_GL = /swiftshader|llvmpipe|softpipe|software|basic render/i.test(M.webglRenderer || '');
    M.curveDetail = !CURVES ? 'straight' : SOFT_GL && !CURVE_FULL ? 'reduced' : 'full';
    window.VLApp.graph = { scene: scene, camera: camera, renderer: renderer, controls: controls };
    requestAnimationFrame(loop);
  }
  function particlesOn() { return !!(particles && particles.active > 0); }
  function loop(t) {
    requestAnimationFrame(loop);
    if (tween) stepTween(t);
    var moved = controls.update();
    var anim = particlesOn();
    if (anim) stepParticles(t);
    if (needsRender || moved || tween || measuring || anim) {
      updateFog();
      renderer.render(scene, camera);
      frames++;
      needsRender = false;
    }
  }
  function updateFog() {
    if (!camera || !fog) return;
    VL.fitFog(fog, camera.position.distanceTo(controls.target), sceneR);
    FOG.value.set(fog.near, fog.far, 1);
  }
  function curveMaterial() {
    return new THREE.ShaderMaterial({
      uniforms: { uOpacity: { value: 1 }, uFog: FOG, uBend: { value: BEND }, uLiftMax: { value: LIFT_MAX }, uLayer: { value: GAP } },
      vertexShader: CV_VS, fragmentShader: CV_FS, transparent: true, depthWrite: false, blending: THREE.NormalBlending
    });
  }
  /* the links of the scene: one instanced object for the links between two terms, one for the petals */
  function disposeEdges() {
    edgeObjs.forEach(function (eo) { scene.remove(eo.obj); eo.obj.geometry.dispose(); eo.obj.material.dispose(); });
    edgeObjs = [];
    if (arrows) { scene.remove(arrows.obj); arrows.obj.geometry.dispose(); arrows.obj.material.dispose(); arrows = null; }
    if (particles) { scene.remove(particles.obj); particles.obj.geometry.dispose(); particles.obj.material.dispose(); particles = null; }
  }
  function buildEdges() {
    disposeEdges();
    assignShapes(current.links);
    var stats = { links: 0, loops: 0, bows: 0, segments: 0, vertices: 0, byType: {} };
    [false, true].forEach(function (loopSet) {
      var ls = current.links.filter(function (l) { return !!l.__loop === loopSet; });
      if (!ls.length) return;
      var S = segsFor(loopSet), m = ls.length;
      var g = new THREE.InstancedBufferGeometry(), t = new Float32Array(S + 1), idx = new Uint16Array(2 * S);
      for (var i = 0; i <= S; i++) t[i] = i / S;
      for (var j = 0; j < S; j++) { idx[2 * j] = j; idx[2 * j + 1] = j + 1; }
      g.setAttribute('aT', new THREE.BufferAttribute(t, 1));
      g.setIndex(new THREE.BufferAttribute(idx, 1));
      var A = new Float32Array(3 * m), B = new Float32Array(3 * m), BW = new Float32Array(3 * m), LP = new Float32Array(3 * m);
      var CA = new Float32Array(3 * m), CB = new Float32Array(3 * m), AL = new Float32Array(m);
      ls.forEach(function (l, e) {
        var s = shapeOf(l);
        l.__ei = { set: loopSet ? 1 : 0, i: e };
        if (!s) { AL[e] = 0; return; }
        A[3 * e] = s.ax; A[3 * e + 1] = s.ay; A[3 * e + 2] = s.az;
        B[3 * e] = s.bx; B[3 * e + 1] = s.by; B[3 * e + 2] = s.bz;
        BW[3 * e] = s.bow[0]; BW[3 * e + 1] = s.bow[1]; BW[3 * e + 2] = s.bow[2];
        LP[3 * e] = s.loop[0]; LP[3 * e + 1] = s.loop[1]; LP[3 * e + 2] = s.loop[2];
        stats.byType[l.type] = (stats.byType[l.type] || 0) + 1;
        if (l.__bow) stats.bows++;
      });
      g.setAttribute('aA', new THREE.InstancedBufferAttribute(A, 3));
      g.setAttribute('aB', new THREE.InstancedBufferAttribute(B, 3));
      g.setAttribute('aBow', new THREE.InstancedBufferAttribute(BW, 3));
      g.setAttribute('aLoop', new THREE.InstancedBufferAttribute(LP, 3));
      g.setAttribute('aColA', new THREE.InstancedBufferAttribute(CA, 3));
      g.setAttribute('aColB', new THREE.InstancedBufferAttribute(CB, 3));
      g.setAttribute('aAlpha', new THREE.InstancedBufferAttribute(AL, 1));
      g.instanceCount = m;
      g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 1e5);
      var obj = new THREE.LineSegments(g, curveMaterial());
      obj.frustumCulled = false;
      obj.renderOrder = 1;
      scene.add(obj);
      edgeObjs[loopSet ? 1 : 0] = { obj: obj, links: ls, seg: S, m: m };
      stats.links += m;
      if (loopSet) stats.loops = m;
      stats.segments += m * S;
      stats.vertices += m * (S + 1);
    });
    stats.detail = M.curveDetail;
    stats.segs = { link: segsFor(false), loop: segsFor(true) };
    M.curves = stats;
    buildArrows();
    buildParticles();
    refreshLinkStyles();
  }
  /* arrowheads: small cones on the curve where it meets the target term (properties, subclass links, result triples) */
  function buildArrows() {
    var ls = current.links.filter(hasArrow);
    if (!ls.length) return;
    var cone = new THREE.ConeGeometry(1.5, 4.6, 10);
    cone.translate(0, -2.3, 0);                         // the tip at the origin
    var mat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, depthWrite: false });
    var obj = new THREE.InstancedMesh(cone, mat, ls.length);
    obj.frustumCulled = false;
    obj.renderOrder = 3;
    var place = [], up = new THREE.Vector3(0, 1, 0), q = new THREE.Quaternion(), dir = new THREE.Vector3(), mtx = new THREE.Matrix4(), one = new THREE.Vector3(1, 1, 1);
    ls.forEach(function (l, i) {
      var g = shapeOf(l), b = nodeOf(l.target);
      if (!g || !b) { place.push(null); return; }
      var rb = (b.__r || 3) * 1.07 + 0.8, t = 1, p = curveAt(g, 1);
      for (var k = 1; k <= 64; k++) {
        t = 1 - k / 64;
        p = curveAt(g, t);
        var dx = p.x - g.bx, dy = p.y - g.by, dz = p.z - g.bz;
        if (dx * dx + dy * dy + dz * dz >= rb * rb) break;
      }
      var p2 = curveAt(g, Math.min(1, t + 0.02));
      dir.set(p2.x - p.x, p2.y - p.y, p2.z - p.z);
      if (dir.lengthSq() < 1e-9) dir.set(0, -1, 0);
      dir.normalize();
      q.setFromUnitVectors(up, dir);
      mtx.compose(new THREE.Vector3(p.x, p.y, p.z).addScaledVector(dir, 0.4), q, one);
      place.push(mtx.clone());
      obj.setMatrixAt(i, mtx);
      obj.setColorAt(i, new THREE.Color(0xffffff));
    });
    obj.instanceMatrix.needsUpdate = true;
    scene.add(obj);
    arrows = { obj: obj, links: ls, place: place };
    M.arrows = ls.length;
  }
  /* direction particles: two dots running along each property link (and result triple), on top of the curves */
  function buildParticles() {
    var ls = current.links.filter(hasParticles);
    if (!ls.length) return;
    var n = 2 * ls.length, pos = new Float32Array(3 * n), col = new Float32Array(3 * n);
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    g.setDrawRange(0, 0);
    var mat = new THREE.PointsMaterial({ size: 3.6, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.95, depthWrite: false });
    var obj = new THREE.Points(g, mat);
    obj.frustumCulled = false;
    obj.renderOrder = 9;
    scene.add(obj);
    particles = { obj: obj, links: ls, run: [], active: 0, shapes: [] };
  }
  function stepParticles(t) {
    var pa = particles, pos = pa.obj.geometry.attributes.position.array, k = 0, sec = t / 1000;
    pa.run.forEach(function (r) {
      for (var j = 0; j < 2; j++) {
        var u = (sec * 0.27 + j * 0.5 + r.phase) % 1, p = curveAt(r.g, u);
        pos[3 * k] = p.x; pos[3 * k + 1] = p.y; pos[3 * k + 2] = p.z;
        k++;
      }
    });
    pa.obj.geometry.attributes.position.needsUpdate = true;
  }
  /* colours and opacities of every link, arrow and particle for the filters, the highlight and the theme */
  var _c = null;
  function refreshLinkStyles() {
    if (!scene) return;
    if (!_c) _c = new THREE.Color();
    var act = hlActive(), f = TH.dark ? 0.62 : 0.8, emphPaths = [], emphCols = [];
    edgeObjs.forEach(function (eo) {
      if (!eo) return;
      var g = eo.obj.geometry, CA = g.attributes.aColA.array, CB = g.attributes.aColB.array, AL = g.attributes.aAlpha.array;
      eo.links.forEach(function (l, e) {
        var vis = linkVisible(l), c0 = rgb(linkBaseColor(l));
        var c2 = TH.dark ? [c0[0] * f, c0[1] * f, c0[2] * f] : [1 - (1 - c0[0]) * f, 1 - (1 - c0[1]) * f, 1 - (1 - c0[2]) * f];
        var a = vis ? (LT_ALPHA[l.type] || 0.8) * P.linkOpacity / 0.72 : 0;
        if (vis && act) {
          if (inTrace(l)) a = 0;
          else if (inHl(l)) {
            a = 0;
            var pts = VL.linkPoints(l, l.__loop ? 18 : 16);
            if (pts) { emphPaths.push(pts); emphCols.push(emphColor(l)); }
          } else a *= 0.22;
        }
        CA[3 * e] = c0[0]; CA[3 * e + 1] = c0[1]; CA[3 * e + 2] = c0[2];
        CB[3 * e] = c2[0]; CB[3 * e + 1] = c2[1]; CB[3 * e + 2] = c2[2];
        AL[e] = Math.min(1, a);
      });
      g.attributes.aColA.needsUpdate = true;
      g.attributes.aColB.needsUpdate = true;
      g.attributes.aAlpha.needsUpdate = true;
    });
    emph.setPaths(emphPaths, emphCols);
    M.emphPaths = emphPaths.length;
    if (arrows) {
      var zero = new THREE.Matrix4().makeScale(0, 0, 0), shown = 0;
      arrows.links.forEach(function (l, i) {
        var vis = linkVisible(l) && !!arrows.place[i];
        arrows.obj.setMatrixAt(i, vis ? arrows.place[i] : zero);
        if (!vis) return;
        shown++;
        var col = inTrace(l) ? P.core : (act && inHl(l)) ? emphColor(l) : linkBaseColor(l);
        _c.set(col);
        if (act && !inHl(l)) _c.lerp(new THREE.Color(TH.bg), 0.8);
        arrows.obj.setColorAt(i, _c);
      });
      arrows.obj.instanceMatrix.needsUpdate = true;
      if (arrows.obj.instanceColor) arrows.obj.instanceColor.needsUpdate = true;
      M.arrowsShown = shown;
    }
    if (particles) {
      var col = particles.obj.geometry.attributes.color.array, k = 0;
      particles.run = [];
      particles.links.forEach(function (l, i) {
        if (!state.particles || !linkVisible(l) || (act && !inTrace(l))) return;
        var g = shapeOf(l);
        if (!g) return;
        _c.set(inTrace(l) ? P.halo : linkBaseColor(l));
        if (!P.dark && !inTrace(l)) _c.multiplyScalar(0.86);
        for (var j = 0; j < 2; j++) { col[3 * k] = _c.r; col[3 * k + 1] = _c.g; col[3 * k + 2] = _c.b; k++; }
        particles.run.push({ g: g, phase: (i * 0.137) % 1 });
      });
      particles.active = particles.run.length;
      particles.obj.geometry.setDrawRange(0, 2 * particles.run.length);
      particles.obj.geometry.attributes.color.needsUpdate = true;
      particles.obj.visible = particles.active > 0;
      if (particles.active) stepParticles(performance.now());
      M.particles = 2 * particles.active;
    }
    needsRender = true;
  }

  /* ------------------------------------------------------------------ hierarchy planes (like the legal-force layers) */
  function planeShown(pl) {
    if (!state.planes || view.mode === 'replace') return false;
    return current.nodes.some(function (n) { return !n.inst && n.__plane === pl.index && nodeVisible(n); });
  }
  /* the rectangle of every plane: the terms' extents plus a margin, and on the left a label apron (narrower on a narrow
     stage, where every pixel goes to the terms) */
  function planeRect() {
    var X = LAYOUT.half.x, Z = LAYOUT.half.z, ap = (host.clientWidth || 1000) >= 700 ? LAY.apron : LAY.apronNarrow;
    return { x0: -X - ap, x1: X, z0: -Z, z1: Z, apron: ap };
  }
  function buildPlanes() {
    while (planeGroup.children.length) {
      var o = planeGroup.children[0];
      planeGroup.remove(o);
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    }
    planeLabels.forEach(function (s) { labelGroup.remove(s); s.dispose(); });
    planeLabels = [];
    var R = planeRect();
    PLANES.forEach(function (pl) {
      var y = pl.y - 2;
      var plane = new THREE.Mesh(new THREE.PlaneGeometry(R.x1 - R.x0, R.z1 - R.z0),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(TH.plane), transparent: true, opacity: TH.planeOpacity, depthWrite: false, side: THREE.DoubleSide }));
      plane.rotation.x = -Math.PI / 2;
      plane.position.set((R.x0 + R.x1) / 2, y, (R.z0 + R.z1) / 2);
      plane.renderOrder = 0;
      plane.__plane = pl;
      planeGroup.add(plane);
      var pts = [new THREE.Vector3(R.x0, y, R.z0), new THREE.Vector3(R.x1, y, R.z0), new THREE.Vector3(R.x1, y, R.z1), new THREE.Vector3(R.x0, y, R.z1)];
      var outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: new THREE.Color(TH.planeLine), transparent: true, opacity: TH.planeLineOpacity }));
      outline.__plane = pl;
      planeGroup.add(outline);
      var o2 = VL.paperCallout(P, false);
      o2.lines = planeLines(pl);
      o2.px = PLANE_PX;
      o2.weight = '400';
      var s = VL.TextSprite(o2.lines[0].map(function (p) { return p.text; }).join(''), o2);
      s.__plane = pl;
      s.layers.set(1);
      s.position.set(R.x0, y, R.z1);
      if (camera) s.fit(worldPerPx());
      labelGroup.add(s);
      planeLabels.push(s);
    });
    labelGen++;
    refreshPlanes();
  }
  function refreshPlanes() {
    var shown = {};
    PLANES.forEach(function (pl) { shown[pl.index] = planeShown(pl); });
    planeGroup.children.forEach(function (o) { o.visible = !!shown[o.__plane.index]; });
    M.planes = PLANES.map(function (pl) {
      return { key: pl.key, kind: pl.kind, depth: pl.depth, y: pl.y, count: pl.count, shown: !!shown[pl.index] };
    });
    needsRender = true;
  }

  /* ------------------------------------------------------------------ the graph in the scene: base ontology or a
     CONSTRUCT view; node objects are made once per node and kept */
  function setScene() {
    var want = new Set(current.nodes);
    nodeGroup.children.slice().forEach(function (o) {
      if (want.has(o.__node)) return;
      nodeGroup.remove(o);
      if (o.__node.inst || o.__node.__copy) disposeNode(o.__node);
    });
    current.nodes.forEach(function (n) {
      if (!n.__obj) makeNode(n);
      n.__obj.position.set(n.x, n.y, n.z);
      if (n.__obj.parent !== nodeGroup) nodeGroup.add(n.__obj);
    });
    buildEdges();
    refreshVisibility();
  }
  function build() {
    /* the side column and the details panel: resizable on wide screens (js/common.js VL.columns); the page's own resize
       follows (renderer size, camera aspect, call-outs, legend; the camera's position and target stay) */
    window.VLApp.columns = VL.columns({ app: VL.$('#app'), side: VL.$('#side'), stage: VL.$('#stage'), panel: VL.$('#panel'),
      onResize: relayout, live: function () { return !SOFT_GL; } });
    initThree();
    buildPlanes();
    setScene();
    M.graphNodes = current.nodes.length;
    M.graphLinks = current.links.length;
    bindPointer();
    fitView(0);
    applyHighlight();
    requestAnimationFrame(function () {
      var veil = VL.$('#veil');
      if (veil) veil.remove();
      cullLabels();
      showHint();
      applyHash();
      measureFps(1500).then(function (fps) {
        VL.setReady({ fps: fps, graphNodes: current.nodes.length, graphLinks: current.links.length, webglRenderer: M.webglRenderer });
        status();
      });
    });
  }

  /* the camera frames every visible node (or the subset) and the hierarchy planes: the network's oblique view, looking
     at the middle of their extents across the view, from the distance at which each point, with its radius and room for
     a leader, projects inside 90 % of the frame (80 % on a narrow stage, where call-outs need the sides) */
  var VIEW_DIR = [0.18, 0.5, 1];
  /* the camera looking along dir at the middle of the points' extents across the view, from the distance at which each
     point, with its radius, projects inside the margin m of the frame */
  function framePoints(pts, dirV, m, ms, minD, centre) {
    var sz = stageSize(), tv = Math.tan(camera.fov * Math.PI / 360), th = tv * sz.w / sz.h;
    var dir = dirV.clone().normalize(), right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), dir).normalize();
    var up = new THREE.Vector3().crossVectors(dir, right), c = new THREE.Vector3(), v = new THREE.Vector3();
    if (centre) c.set(centre.x, centre.y, centre.z);             // a fixed centre (the selection stays in the middle)
    else {
      pts.forEach(function (p) { c.x += p.x; c.y += p.y; c.z += p.z; });
      c.multiplyScalar(1 / pts.length);
      var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      pts.forEach(function (p) {
        v.set(p.x - c.x, p.y - c.y, p.z - c.z);
        var x = v.dot(right), y = v.dot(up);
        x0 = Math.min(x0, x - p.r); x1 = Math.max(x1, x + p.r); y0 = Math.min(y0, y - p.r); y1 = Math.max(y1, y + p.r);
      });
      c.addScaledVector(right, (x0 + x1) / 2).addScaledVector(up, (y0 + y1) / 2);
    }
    var d = minD || 10, R = 10;
    pts.forEach(function (p) {
      v.set(p.x - c.x, p.y - c.y, p.z - c.z);
      var x = v.dot(right), y = v.dot(up), z = v.dot(dir);
      d = Math.max(d, z + (Math.abs(x) + p.r) / (m * th), z + (Math.abs(y) + p.r) / (m * tv));
      R = Math.max(R, v.length() + p.r);
    });
    moveCamera(new THREE.Vector3(c.x + dir.x * d, c.y + dir.y * d, c.z + dir.z * d), c.clone(), ms || 0);
    return { d: d, R: R, c: c };
  }
  /* the default view: every visible node (or the subset) and the hierarchy planes, from the network's oblique angle,
     inside 90 % of the frame (80 % on a narrow stage, where call-outs need the sides) */
  function fitView(ms, subset) {
    var vis = (subset || current.nodes).filter(nodeVisible).filter(function (n) { return isFinite(n.x); });
    if (!vis.length) return;
    var pts = vis.map(function (n) { return { x: n.x, y: n.y, z: n.z, r: n.__r + 8 }; });
    if (!subset) PLANES.forEach(function (pl) {
      if (!planeShown(pl)) return;
      var R2 = planeRect();
      [[R2.x0, R2.z0], [R2.x1, R2.z0], [R2.x1, R2.z1], [R2.x0, R2.z1]].forEach(function (c) { pts.push({ x: c[0], y: pl.y, z: c[1], r: 0 }); });
    });
    var m = stageSize().w < 700 ? 0.8 : 0.9;
    var f = framePoints(pts, new THREE.Vector3(VIEW_DIR[0], VIEW_DIR[1], VIEW_DIR[2]), m, ms);
    if (!subset) sceneR = f.R;
    M.fit = { d: Math.round(f.d), R: Math.round(f.R), nodes: vis.length, points: pts.length, margin: m };
    setTimeout(scheduleCull, (ms || 0) + 40);
  }
  /* a selected term: the camera turns to it, keeps it in the middle of the canvas (clear of the legend and the panel)
     and frames its highlighted neighbourhood with it - on a narrow stage (a phone, its panel over half the screen)
     only its chain up the hierarchy - from the current direction (never flatter than 14 degrees), at least as close as
     a view 70 units round it; margins 0.75 (0.68 on a narrow stage) leave room for the call-outs */
  function flyTo(n) {
    if (!isFinite(n.x)) return;
    var sz = stageSize(), set = [n], narrow = sz.w < 700;
    if (state.selected === n && hl.nodes) {
      if (narrow) { if (hl.chain) hl.chain.forEach(function (l) { var t = nodeOf(l.target); if (t && t !== n && nodeVisible(t) && set.indexOf(t) < 0) set.push(t); }); }
      else hl.nodes.forEach(function (x) { if (x !== n && nodeVisible(x) && isFinite(x.x)) set.push(x); });
    }
    var pts = set.map(function (x) { return { x: x.x, y: x.y, z: x.z, r: x.__r + 10 }; });
    var vf = camera.fov * Math.PI / 180, aspect = sz.w / sz.h, hf = 2 * Math.atan(Math.tan(vf / 2) * aspect);
    var minD = (70 + n.__r * 2) / Math.sin(Math.min(vf, hf) / 2);
    var dir = new THREE.Vector3().subVectors(camera.position, controls.target);
    if (dir.lengthSq() < 1) dir.set(VIEW_DIR[0], VIEW_DIR[1], VIEW_DIR[2]);
    dir.normalize();
    if (dir.y < 0.25) { dir.y = 0.25; dir.normalize(); }
    framePoints(pts, dir, narrow ? 0.68 : 0.75, 900, minD, n);
    M.flyFrame = set.length;
    setTimeout(scheduleCull, 950);
  }
  /* M.flying: true while the camera flies (reset, a selection, a CONSTRUCT result); tests read the camera after it */
  function moveCamera(pos, target, ms) {
    if (!ms) {
      tween = null;
      M.flying = false;
      camera.position.copy(pos); controls.target.copy(target); camera.lookAt(target); controls.update();
      needsRender = true;
      scheduleCull();
      return;
    }
    tween = { t0: null, ms: ms, p0: camera.position.clone(), p1: pos, q0: controls.target.clone(), q1: target };
    M.flying = true;
  }
  function stepTween(t) {
    if (tween.t0 == null) tween.t0 = t;
    var u = Math.min(1, (t - tween.t0) / tween.ms), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
    camera.position.lerpVectors(tween.p0, tween.p1, e);
    controls.target.lerpVectors(tween.q0, tween.q1, e);
    if (u >= 1) { tween = null; M.flying = false; scheduleCull(); }
  }
  /* frames drawn per second while every frame is rendered (the camera stays where it is) */
  function measureFps(ms) {
    return new Promise(function (resolve) {
      measuring++;
      var f0 = frames, t0 = performance.now();
      setTimeout(function () {
        measuring--;
        var fps = Math.round((frames - f0) * 10000 / (performance.now() - t0)) / 10;
        M.fpsSamples = (M.fpsSamples || []).concat([fps]);
        resolve(fps);
      }, ms);
    });
  }
  window.VLApp.measureFps = measureFps;
  function status() {
    var vn = current.nodes.filter(nodeVisible).length, vl = current.links.filter(linkVisible).length;
    statusEl.textContent = VL.U('o3d.status', { terms: VL.fmt(vn), links: VL.fmt(vl) }) + (M.fps ? ' · ' + VL.fmt(M.fps) + ' fps' : '');
    M.statusCounts = { terms: vn, links: vl };
    fitLegend();
  }
  /* legend above the status line where the two would meet (js/paper3d.js); the call-outs avoid the legend */
  function fitLegend() { if (VL.fitLegend(stage, legendEl, statusEl)) scheduleCull(); }

  /* ------------------------------------------------------------------ picking (screen space) + hover tooltip */
  var _p = null;
  function toScreen(x, y, z, sz) {
    if (!_p) _p = new THREE.Vector3();
    _p.set(x, y, z).applyMatrix4(camera.matrixWorldInverse);
    var depth = -_p.z;
    if (depth <= camera.near) return null;
    _p.applyMatrix4(camera.projectionMatrix);
    return { x: (_p.x + 1) / 2 * sz.w, y: (1 - _p.y) / 2 * sz.h, d: depth };
  }
  /* the term or link under a canvas point (CSS px): a placed call-out names its term; else the nearest term whose disc
     (plus 3 px) holds the point, the front one first; else a link within 5 px of its curve (highlighted links first) */
  function pickAt(cx, cy) {
    if (!camera) return null;
    camera.updateMatrixWorld();
    var sz = stageSize(), placed = (M.callouts && M.callouts.placed) || [];
    for (var i = placed.length - 1; i >= 0; i--) {
      var b = placed[i].box, n0 = current.byId[placed[i].id];
      if (n0 && nodeVisible(n0) && cx >= b[0] && cx <= b[2] && cy >= b[1] && cy <= b[3]) return { node: n0 };
    }
    var tv = Math.tan(camera.fov * Math.PI / 360), best = null, bestD = Infinity;
    current.nodes.forEach(function (n) {
      if (!nodeVisible(n) || !n.__obj || !isFinite(n.x)) return;
      var s = toScreen(n.x, n.y, n.z, sz);
      if (!s) return;
      var rpx = nodeR(n) / (s.d * tv) * (sz.h / 2), dd = Math.hypot(s.x - cx, s.y - cy);
      if (dd > Math.max(rpx + 3, 7)) return;
      var score = s.d - (hl.nodes && hl.nodes.has(n) ? 1e6 : 0);
      if (score < bestD) { bestD = score; best = n; }
    });
    if (best) return { node: best };
    var bestL = null, bestLD = 5.01;
    current.links.forEach(function (l) {
      if (!linkVisible(l)) return;
      var pts = VL.linkPoints(l, l.__loop ? 12 : 10);
      if (!pts) return;
      var prev = null, dmin = Infinity;
      pts.forEach(function (p) {
        var s = toScreen(p.x, p.y, p.z, sz);
        if (s && prev) dmin = Math.min(dmin, segDist(cx, cy, prev.x, prev.y, s.x, s.y));
        prev = s;
      });
      if (hlActive() && inHl(l)) dmin -= 1.5;
      if (dmin < bestLD) { bestLD = dmin; bestL = l; }
    });
    return bestL ? { link: bestL } : null;
  }
  function segDist(px, py, ax, ay, bx, by) {
    var dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L)) : 0;
    return Math.hypot(px - ax - t * dx, py - ay - t * dy);
  }
  var down = null, hoverRaf = 0;
  function bindPointer() {
    var cv = renderer.domElement;
    function local(e) { var r = host.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }   // the canvas fills the host
    cv.addEventListener('pointerdown', function (e) { down = { x: e.clientX, y: e.clientY }; });
    cv.addEventListener('pointerup', function (e) {
      if (!down) return;
      var moved = Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y);
      down = null;
      if (moved > 6) return;
      var q = local(e), hit = pickAt(q.x, q.y);
      tip.classList.add('hidden');
      if (hit && hit.node) select(hit.node, true);
      else if (hit && hit.link) selectLink(hit.link);
      else clearSelection();
    });
    cv.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch' || down) { tip.classList.add('hidden'); return; }
      if (hoverRaf) return;
      var x = e.clientX, y = e.clientY;
      hoverRaf = requestAnimationFrame(function () {
        hoverRaf = 0;
        var r = host.getBoundingClientRect(), hit = pickAt(x - r.left, y - r.top);
        var n = hit && hit.node ? hit.node : null;
        cv.style.cursor = hit ? 'pointer' : '';
        host.style.cursor = cv.style.cursor;
        M.hover = n ? n.id : null;
        setHover(n);
        if (!hit) { tip.classList.add('hidden'); return; }
        tip.innerHTML = n ? nodeTooltip(n) : linkTooltip(hit.link);
        tip.classList.remove('hidden');
        var hr = stage.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
        var lx = Math.min(hr.width - tw - 8, x - hr.left + 14), ly = y - hr.top + 14;
        if (ly + th > hr.height - 8) ly = y - hr.top - th - 10;
        tip.style.left = Math.max(8, lx) + 'px';
        tip.style.top = Math.max(8, ly) + 'px';
      });
    });
    cv.addEventListener('pointerleave', function () { tip.classList.add('hidden'); M.hover = null; setHover(null); });
  }

  /* ------------------------------------------------------------------ selection + panel */
  /* the selection's neighbourhood (incident links) plus its chain: the subclass links up to the top of its hierarchy,
     like the paper's trace from a point up to the law */
  function neighbourhood(n) {
    var ns = new Set([n]), ls = new Set(), up = {}, frontier = [n], seen = new Set([n]), chain = new Set();
    current.links.forEach(function (l) {
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

  /* ------------------------------------------------------------------ controls: colour, links, modules, terms, view */
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
  VL.$('#show-planes').addEventListener('change', function (e) { state.planes = e.target.checked; refreshPlanes(); scheduleCull(); });
  VL.$('#show-particles').addEventListener('change', function (e) { state.particles = e.target.checked; refreshLinkStyles(); });
  function pressed(sel, attr, val) { VL.$$(sel).forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute(attr) === String(val) ? 'true' : 'false'); }); }
  function setColorBy(mode) {
    state.colorBy = mode === 'kind' ? 'kind' : 'module';
    M.colorBy = state.colorBy;
    pressed('[data-color]', 'data-color', state.colorBy);
    current.nodes.forEach(function (n) { if (n.__mesh) styleNode(n, !hl.nodes || hl.nodes.has(n), state.selected === n); });
    buildSearch();
    renderLegend();
    needsRender = true;
    M.colorRenders = (M.colorRenders || 0) + 1;
  }
  VL.$$('[data-color]').forEach(function (b) { b.addEventListener('click', function () { setColorBy(b.getAttribute('data-color')); }); });
  /* LINKS: one check box per kind, its curve swatch in the kind's colour and the number of links */
  var SWATCH_PATH = 'M3 11C3 6.5 19 5.5 19 1';
  function curveSwatch(color) {
    return '<svg class="swatch-curve' + (color ? '' : ' trace') + '" viewBox="0 0 22 12" aria-hidden="true">' + (color ?
      '<path d="' + SWATCH_PATH + '" style="stroke:' + color + '"/>' :
      '<path class="halo" d="' + SWATCH_PATH + '"/><path class="core" d="' + SWATCH_PATH + '"/>') + '</svg>';
  }
  function ltVar(t) { return 'var(' + LT_TOKEN[t] + ')'; }
  function renderLinkToggles() {
    var cnt = {};
    links.forEach(function (l) { cnt[l.type] = (cnt[l.type] || 0) + 1; });
    VL.$('#link-toggles').innerHTML = LINK_TYPES.map(function (t) {
      return '<label class="check"' + tipAttr(LT_KEY[t]) + '><input type="checkbox" data-link="' + t + '"' + (state.links[t] !== false ? ' checked' : '') + '>' +
        curveSwatch(ltVar(t)) + '<span class="lbl">' + VL.esc(VL.cap(VL.U(LT_KEY[t]))) + '</span><span class="count" id="cnt-' + t + '">' + VL.fmt(cnt[t] || 0) + '</span></label>';
    }).join('');
  }
  VL.$('#link-toggles').addEventListener('change', function (e) {
    var t = e.target.getAttribute('data-link');
    if (!t) return;
    state.links[t] = e.target.checked;
    refreshVisibility();
  });
  function refreshVisibility() {
    M.visibleNodes = current.nodes.filter(nodeVisible).length;
    if (!scene) return;
    current.nodes.forEach(function (n) { if (n.__obj) n.__obj.visible = nodeVisible(n); });
    if (state.selected && !nodeVisible(state.selected)) clearSelection();
    else if (state.selected) { var nb = neighbourhood(state.selected); setHighlight(nb.nodes, nb.links, { chain: nb.chain, max: TRACE_ALL_MAX }); }
    else applyHighlight();
    refreshPlanes();
    renderLegend();
    scheduleCull();
    status();
  }
  function counts() {
    VL.$('#cnt-external').textContent = VL.fmt(nodes.filter(function (n) { return n.kind === 'external'; }).length);
    VL.$('#cnt-schemes').textContent = VL.fmt(nodes.filter(function (n) { return n.kind === 'scheme'; }).length);
    renderLinkToggles();
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
    if (!n || !camera || !n.__obj || !nodeVisible(n)) return null;
    camera.updateMatrixWorld();
    var r = host.getBoundingClientRect(), p = toScreen(n.x, n.y, n.z, stageSize());
    if (!p) return null;
    return { x: r.left + p.x, y: r.top + p.y, inside: p.x > 0 && p.y > 0 && p.x < r.width && p.y < r.height };
  };
  /* the camera (position and orbit target, rounded): tests check that a language switch keeps it */
  function camState(cam, target) {
    if (!cam || !target) return null;
    return [cam.position.x, cam.position.y, cam.position.z, target.x, target.y, target.z].map(function (v) { return Math.round(v * 1000) / 1000; });
  }
  window.VLApp.camera = function () { return camera ? camState(camera, controls.target) : null; };
  window.VLApp.state = function () {
    return { selected: state.selected && state.selected.id, view: view.mode, nodes: current.nodes.length, links: current.links.length,
      panelOpen: !panel.classList.contains('hidden'), panelText: panel.textContent.slice(0, 400), colorBy: state.colorBy };
  };
  /* tests: the layout (plane of every term, its depth, the planes) and the colour mode */
  window.VLApp.layout = function () {
    var out = { planes: M.planes || [], half: M.layout.half, nodes: {} };
    nodes.forEach(function (n) { out.nodes[n.id] = { x: n.x, y: n.y, z: n.z, plane: n.__plane, depth: n.__depth, kind: n.kind, module: n.module }; });
    return out;
  };
  window.VLApp.colorBy = function (mode) { if (mode) setColorBy(mode); return state.colorBy; };
  /* tests and offline previews: the scene as drawn - camera, terms (colour, opacity, halo), links as the polylines of
     their curves with the colours and opacity of their attributes, arrows, planes, the traced and emphasised paths */
  function hex3(a, i) { return '#' + [a[3 * i], a[3 * i + 1], a[3 * i + 2]].map(function (v) { var c = Math.round(Math.max(0, Math.min(1, v)) * 255); return (c < 16 ? '0' : '') + c.toString(16); }).join(''); }
  window.VLApp.sceneDump = function (seg) {
    if (!camera) return null;
    seg = seg || 16;
    camera.updateMatrixWorld();
    function P3(p) { return [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100, Math.round(p.z * 100) / 100]; }
    var out = { camera: { pos: camera.position.toArray(), target: controls.target.toArray(), fov: camera.fov, aspect: camera.aspect,
        view: camera.matrixWorldInverse.toArray(), proj: camera.projectionMatrix.toArray() },
      bg: TH.bg, fog: fog ? [fog.near, fog.far] : null, plane: { color: TH.plane, opacity: TH.planeOpacity, line: TH.planeLine, half: [LAYOUT.half.x, LAYOUT.half.z], rect: planeRect() },
      curveDetail: M.curveDetail, nodes: [], links: [], arrows: [], planes: [], trace: [], emph: [] };
    current.nodes.forEach(function (n) {
      if (!n.__mesh) return;
      out.nodes.push({ id: n.id, kind: kindOf(n), shape: n.inst ? 'instance' : n.kind, x: n.x, y: n.y, z: n.z, r: n.__mesh.scale.x, vis: !!(n.__obj && n.__obj.visible),
        color: '#' + n.__mesh.material.color.getHexString(), opacity: n.__mesh.material.opacity, rim: '#' + n.__rim.material.color.getHexString(),
        halo: n.__halo.visible ? '#' + n.__halo.material.color.getHexString() : null, haloR: n.__halo.scale.x });
    });
    edgeObjs.forEach(function (eo) {
      if (!eo) return;
      var at = eo.obj.geometry.attributes;
      eo.links.forEach(function (l, e) {
        var pts = curvePts(l, l.__loop ? Math.max(seg, 18) : seg);
        out.links.push({ key: l.key, type: l.type, id: l.id || null, source: sid(l.source), target: sid(l.target), loop: !!l.__loop, bow: l.__bow || 0,
          alpha: at.aAlpha.array[e], colA: hex3(at.aColA.array, e), colB: hex3(at.aColB.array, e), pts: pts ? pts.map(P3) : null });
      });
    });
    if (arrows) arrows.links.forEach(function (l, i) {
      var m = new THREE.Matrix4(), c = new THREE.Color(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
      arrows.obj.getMatrixAt(i, m);
      m.decompose(p, q, s);
      if (s.x < 1e-6) return;
      if (arrows.obj.instanceColor) arrows.obj.getColorAt(i, c);
      var d = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
      out.arrows.push({ key: l.key, tip: P3(p), dir: [d.x, d.y, d.z], color: '#' + c.getHexString() });
    });
    PLANES.forEach(function (pl) { var s2 = planeLabels[pl.index]; out.planes.push({ key: pl.key, kind: pl.kind, depth: pl.depth, y: pl.y, shown: planeShown(pl), corner: s2 ? s2.__corner || 'front-left' : null }); });
    if (hl.trace) hl.trace.forEach(function (l) { if (linkVisible(l)) { var p = curvePts(l, l.__loop ? 18 : 16); if (p) out.trace.push(p.map(P3)); } });
    if (hl.links) hl.links.forEach(function (l) {
      if (!linkVisible(l) || (hl.trace && hl.trace.has(l))) return;
      var p = curvePts(l, l.__loop ? 18 : 16);
      if (p) out.emph.push({ color: emphColor(l), pts: p.map(P3) });
    });
    out.traceStyle = { core: P.core, halo: P.halo, halo2: P.halo2, w: VL.TRACE_W };
    out.particles = particles ? 2 * particles.active : 0;
    return out;
  };
  window.VLApp.nodeColor = function (id) { var n = current.byId[id] || byId[id]; return n && n.__mesh ? '#' + n.__mesh.material.color.getHexString() : null; };

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
    renderer.render(scene, camera);
    renderer.domElement.toBlob(function (b) { VL.downloadBlob(b, 'vlonto-ontology-3d.png'); VL.toast(VL.U('o3d.toast.png')); }, 'image/png');
  }
  window.VLApp.exportPng = function () { renderer.render(scene, camera); return renderer.domElement.toDataURL('image/png').length; };

  function orbit(dAz, dPol, zoom) {
    if (!camera) return;
    tween = null;
    M.flying = false;
    var t = controls.target, off = camera.position.clone().sub(t), sph = new THREE.Spherical().setFromVector3(off);
    sph.theta += dAz;
    sph.phi = Math.min(Math.PI - 0.05, Math.max(0.05, sph.phi + dPol));
    sph.radius *= zoom || 1;
    off.setFromSpherical(sph);
    camera.position.copy(t).add(off);
    camera.lookAt(t);
    controls.update();
    needsRender = true;
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
    external: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1.3l5 2.9v5.7L7 12.7 2 9.9V4.2z" fill="currentColor"/></svg>',
    instance: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="3.6" fill="currentColor"/></svg>'
  };
  var KIND_LG = { 'class': 'o3d.lg.class', scheme: 'o3d.lg.scheme', external: 'o3d.lg.external', instance: 'o3d.kind.instance' };
  /* the paper's legend row: "Tiếng Việt · English" entries in EN–VI, one language in EN or VI. Colour by module: the
     modules in view (external terms last) and the shapes; colour by kind: the kinds in view, each shape in its colour.
     Then the kinds of link in view as curve swatches, and the traced path. */
  function bi(vi, en) { return VL.TH(VL.pair(VL.cap(vi || ''), VL.cap(en || ''))); }
  function biKey(k) { var e = VL.i18n.get(k) || { vi: '', en: k }; return bi(e.vi, e.en); }
  function renderLegend() {
    var btn = VL.$('#btn-legend');
    btn.setAttribute('aria-expanded', state.legendOpen ? 'true' : 'false');
    legendEl.classList.toggle('hidden', !state.legendOpen);
    if (!state.legendOpen) { fitLegend(); return; }
    var mods = {}, kinds = {}, types = {};
    current.nodes.forEach(function (n) { if (!nodeVisible(n)) return; mods[modOf(n)] = true; kinds[kindOf(n)] = true; });
    current.links.forEach(function (l) { if (linkVisible(l)) types[l.type] = true; });
    var h;
    if (state.colorBy === 'kind') {
      h = '<h3>' + biKey('o3d.lg.kinds') + '</h3><ul class="lg-kinds">' + KINDS.filter(function (k) { return kinds[k]; }).map(function (k) {
        return '<li><span class="lg-shape" style="color:var(--o3d-kind-' + k + ')">' + SHAPES[k] + '</span>' + biKey(KIND_LG[k]) + '</li>';
      }).join('') + '</ul>';
    } else {
      h = '<h3>' + biKey('o3d.lg.modules') + '</h3><ul class="lg-modules">' + VL.MODULES.filter(function (m) { return mods[m.id]; }).map(function (m) {
        return '<li><span class="swatch" style="background:' + m.v + '"></span>' + (m.id === 'external' ? biKey('o3d.lg.externalTerms') : bi(m.vi, m.en)) + '</li>';
      }).join('') + '</ul>';
      h += '<div class="legend-sub"><ul class="lg-marks">' + ['class', 'scheme', 'external'].filter(function (k) { return kinds[k]; }).map(function (k) {
        return '<li>' + SHAPES[k] + biKey(KIND_LG[k]) + '</li>';
      }).join('') + '</ul></div>';
    }
    h += '<div class="legend-sub"><ul class="lg-links">' + LINK_TYPES.concat(['instance', 'result']).filter(function (t) { return types[t]; }).map(function (t) {
      return '<li>' + curveSwatch(ltVar(t)) + biKey(LT_KEY[t]) + '</li>';
    }).join('') + '<li>' + curveSwatch(null) + biKey(view.mode !== 'ontology' ? 'o3d.lg.tracedResult' : 'o3d.lg.tracedPath') + '</li></ul></div>';
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

  /* ------------------------------------------------------------------ theme switch (light / dark): background, fog,
     lights, planes, node colours, link colours, label sprites and the legend change in place (the layout, the camera,
     the filters and the selection stay); DOM swatches follow CSS variables */
  function applyTheme() {
    readTheme();
    if (!renderer) return;
    renderer.setClearColor(TH.bg, 1);
    if (fog) fog.color.set(TH.bg);
    var L2 = VL.paperLights(P.dark);
    lights.ambient.intensity = L2.ambient.intensity;
    lights.directional.intensity = L2.directional.intensity;
    var seen = new Set();
    nodes.concat(current.nodes || []).forEach(function (n) {
      if (seen.has(n)) return;
      seen.add(n);
      if (n.__label) { n.__labSel = state.selected === n; n.__label.setStyle(labelOpts(n)); }
    });
    buildPlanes();
    applyHighlight();
    renderLegend();
    M.themeRenders = (M.themeRenders || 0) + 1;
  }
  window.addEventListener('vlonto-theme', applyTheme);

  /* ------------------------------------------------------------------ layout of the stage (panel / drawer docking) */
  var lastW = 0;
  function relayout() {
    if (!renderer) return;
    requestAnimationFrame(function () {
      var sz = stageSize();
      renderer.setSize(sz.w, sz.h);
      camera.aspect = sz.w / sz.h;
      camera.updateProjectionMatrix();
      if (lastW && (lastW >= 700) !== (sz.w >= 700)) buildPlanes();             // the label apron follows the stage width
      lastW = sz.w;
      resizeLabels();
      VL.fitLegend(stage, legendEl, statusEl);
      needsRender = true;
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


  /* records of a CONSTRUCT result: a disc (sunflower spiral, 7.5 units apart) hanging a third of a plane gap below their
     class; records of no class of the ontology in a disc below the bottom plane; discs at one height pushed apart (fixed
     order and number of passes, so a query draws the same scene every time) */
  function placeInstances(list) {
    var groups = {}, keys = [];
    list.forEach(function (n) {
      var k = n.cls && byId[n.cls] ? n.cls : '';
      if (!groups[k]) { groups[k] = []; keys.push(k); }
      groups[k].push(n);
    });
    var yLow = PLANES.length ? PLANES[PLANES.length - 1].y : 0, GOLD = Math.PI * (3 - Math.sqrt(5));
    keys.forEach(function (k) {
      var c = k ? byId[k] : null, cx = c ? c.x : 0, cy = c ? c.y - 0.35 * GAP : yLow - 0.5 * GAP, cz = c ? c.z : 0;
      groups[k].forEach(function (n, i) {
        var r = 7.5 * Math.sqrt(i + 0.5), a = i * GOLD;
        n.x = cx + r * Math.cos(a);
        n.y = cy;
        n.z = cz + r * Math.sin(a);
      });
    });
    var byY = {};
    list.forEach(function (n) { var k = Math.round(n.y); (byY[k] = byY[k] || []).push(n); });
    Object.keys(byY).forEach(function (k) {
      var ns = byY[k];
      for (var it = 0; it < 60; it++) {
        var moved = 0;
        for (var a = 0; a < ns.length; a++) for (var b = a + 1; b < ns.length; b++) {
          var A = ns[a], B = ns[b], dx = B.x - A.x, dz = B.z - A.z, dd = Math.sqrt(dx * dx + dz * dz), need = A.__r + B.__r + 2.5;
          if (dd >= need) continue;
          var ux, uz;
          if (dd < 1e-6) { var ang = ((a * 7 + b * 13) % 360) * Math.PI / 180; ux = Math.cos(ang); uz = Math.sin(ang); }
          else { ux = dx / dd; uz = dz / dd; }
          var sh = (need - dd) / 2 + 0.01;
          A.x -= ux * sh; A.z -= uz * sh; B.x += ux * sh; B.z += uz * sh;
          moved++;
        }
        if (!moved) break;
      }
    });
  }
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
        /* replace: a copy of the term at its place on its plane */
        var copy = {};
        Object.keys(base).forEach(function (k) { if (k.indexOf('__') !== 0) copy[k] = base[k]; });
        copy.__r = radius(copy);
        copy.__plane = base.__plane;
        copy.__depth = base.__depth;
        copy.__copy = true;
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
      var lk = { key: 'R' + i, source: l.source, target: l.target, type: 'result', pred: l.pred, predIri: l.predIri };
      clinks.push(lk); resultLinks.add(lk); linkByKey[lk.key] = lk;
    });
    placeInstances(cnodes.filter(function (n) { return n.inst; }));
    var all = {}, data;
    if (mode === 'overlay') {
      nodes.forEach(function (n) { all[n.id] = n; });
      cnodes.forEach(function (n) { all[n.id] = n; });
      var inst = [];
      cnodes.forEach(function (n, i) {
        if (n.cls && byId[n.cls]) { var lk = { key: 'I' + i, source: n.id, target: n.cls, type: 'instance' }; inst.push(lk); linkByKey[lk.key] = lk; resultNodes.add(byId[n.cls]); }
      });
      data = { nodes: nodes.concat(cnodes), links: links.concat(clinks, inst) };
    } else {
      cnodes.forEach(function (n) { all[n.id] = n; });
      data = { nodes: cnodes, links: clinks };
    }
    current.byId = all;
    current.nodes = data.nodes;
    current.links = data.links;
    view.mode = mode;
    view.literals = g.literals;
    view.resultSet = { nodes: resultNodes, links: resultLinks };
    state.selected = null;
    closePanel();
    setScene();
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
    M.instancesPlaced = cnodes.filter(function (n) { return n.inst; }).length;
    status();
  }
  function restoreBase(refit) {
    current.byId = byId;
    current.nodes = nodes;
    current.links = links;
    view.mode = 'ontology';
    view.resultSet = null;
    view.literals = null;
    state.selected = null;
    setScene();
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
     plane names, legend, link toggles, module chips, counts, search suggestions, the example menu, the drawer's status
     and table and the open panel are rendered again in the new mode; the camera, the selection, the query result and
     the filters stay */
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
    if (camera) { relabel(); resizeLabels(); status(); } else M.labelsLang = VL.lang();
    if (!panel.classList.contains('hidden')) {
      if (state.selected) openPanel(state.selected.inst ? instancePanel(state.selected) : nodePanel(state.selected), true);
      else if (state.selectedLink) openPanel(linkPanel(state.selectedLink), true);
    }
  }
  document.addEventListener('vl:lang', applyLang);
  /* tests: the call-out lines of a node (or of a plane: 'plane-depth-0', ...) as drawn (text of each line), or null */
  window.VLApp.labelLines = function (id) {
    var n = current.byId[id] || byId[id], s = n ? n.__label : null;
    if (!s) planeLabels.forEach(function (x) { if ('plane-' + x.__plane.key === id) s = x; });
    return s ? s.__opts.lines.map(function (ln) { return ln.map(function (p) { return p.text; }).join(''); }) : null;
  };

  /* ------------------------------------------------------------------ start */
  renderChips();
  counts();
  renderLegend();
  pressed('[data-color]', 'data-color', state.colorBy);
  VL.fontsReady().then(function () {
    build();
  }).catch(function (e) {
    console.error(e);
    VL.$('#veil').innerHTML = '<div>' + VL.UH('o3d.startError', { msg: e.message }) + '</div>';
  });
})();

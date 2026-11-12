// VLOnto playbook figures, drawn in Typst from data/figures.json (written by
// tools/gather_facts.py from the build reports). The PDF draws them natively: the pandoc
// Lua filter filters/typst-figures.lua replaces each figures/NAME.svg image by
// vlo-figure("NAME"). figures.typ exports the same drawings as SVG for playbook.md and
// the website, so every rendering of a figure comes from this file.
#import "style.typ": sans, mono, accent, accent-light, muted, rule-color

#let F = json("data/figures.json")
#let W = 170mm
#let palette = (rgb("#1d4f7a"), rgb("#4d93c9"), rgb("#e09a3c"), rgb("#6f9a3a"),
                rgb("#b9525e"), rgb("#8a6fb3"), rgb("#4aa39a"), rgb("#9a9a9a"))

#let fmt-int(n) = {
  let s = str(n)
  let out = ""
  let k = s.len()
  for (i, ch) in s.clusters().enumerate() {
    if i > 0 and calc.rem(k - i, 3) == 0 { out += "," }
    out += ch
  }
  out
}

#let swatch(c) = box(width: 7pt, height: 7pt, fill: c, baseline: 0.6pt)

// legend items wrap like words, so a long legend never runs past the figure width
#let legend(items) = block(width: W, {
  set text(font: sans, size: 7.6pt)
  set par(leading: 0.6em)
  items.map(it => box[#swatch(it.at(0))#h(3pt)#it.at(1)]).join(h(12pt))
})

#let bar(w, h, c) = box(rect(width: w, height: h, fill: c, stroke: none), baseline: 1.4pt)

// horizontal bars: labels right-aligned in their own column, value next to each bar
#let hbars(rows, labels, annots, color: accent, label-width: 62mm, annot-width: 26mm) = {
  let vmax = calc.max(..rows.map(r => r.value))
  let plot = W - label-width - 5pt
  let bar-max = plot - annot-width
  set text(font: sans, size: 8pt)
  grid(
    columns: (label-width, plot), column-gutter: 5pt, row-gutter: 3.6pt,
    align: (right + horizon, left + horizon),
    ..rows.enumerate().map(((i, r)) => {
      let w = bar-max * (r.value / vmax)
      if w < 0.6pt { w = 0.6pt }
      (labels.at(i), [#bar(w, 8pt, color)#h(4pt)#text(size: 7.4pt, fill: muted, annots.at(i))])
    }).flatten(),
  )
}

#let fig-doc-types() = {
  let rows = F.doc_types
  hbars(rows,
    rows.map(r => [#r.label_en #text(fill: muted)[· #r.label_vi]]),
    rows.map(r => [#r.value_fmt#h(4pt)#text(fill: luma(125), r.pct_fmt)]),
    label-width: 68mm)
}

#let fig-validity() = {
  let rows = F.validity
  hbars(rows, rows.map(r => r.label_en),
    rows.map(r => [#r.value_fmt#h(4pt)#text(fill: luma(125), r.pct_fmt)]),
    color: palette.at(1), label-width: 52mm)
}

// change events per year of their effective date, stacked by kind
#let fig-changes() = {
  let D = F.changes
  let years = D.years
  let n = years.len()
  let tick = 250
  let ymax = calc.ceil(D.max_total / tick) * tick
  let axis-w = 11mm
  let base = 7mm
  let h = 58mm
  let plot-w = W - axis-w - 1mm
  let slot = plot-w / n
  let bw = slot * 0.74
  let scale = h / ymax
  set text(font: sans, size: 7pt)
  block(width: W, height: h + base + 3mm, {
    for t in range(0, ymax + 1, step: tick) {
      let y = base + t * scale
      place(left + bottom, dx: axis-w, dy: -y,
            line(length: plot-w, stroke: if t == 0 { 0.6pt + luma(110) } else { 0.3pt + luma(218) }))
      if calc.rem(t, 2 * tick) == 0 {
        place(left + bottom, dy: -y + 3.2pt,
              box(width: axis-w - 2mm, align(right, text(fill: muted, fmt-int(t)))))
      }
    }
    for (i, y) in years.enumerate() {
      let acc = 0
      for (k, s) in D.kinds.enumerate() {
        let v = s.values.at(i)
        if v > 0 {
          place(left + bottom, dx: axis-w + i * slot + (slot - bw) / 2, dy: -(base + acc * scale),
                rect(width: bw, height: v * scale, fill: palette.at(k), stroke: none))
        }
        acc += v
      }
      if calc.rem(y, 5) == 0 {
        place(left + bottom, dx: axis-w + i * slot + slot / 2 - 5mm, dy: -0.5mm,
              box(width: 10mm, align(center, text(fill: muted, str(y)))))
      }
    }
  })
  v(2pt)
  legend(D.kinds.enumerate().map(((k, s)) => (palette.at(k), s.label_en)))
}

#let fig-modules() = {
  let rows = F.modules
  let parts = (("classes", "classes"), ("object_properties", "object properties"),
               ("datatype_properties", "datatype properties"),
               ("other", "annotation properties and concept schemes"))
  let total(r) = parts.map(p => r.at(p.at(0))).sum()
  let vmax = calc.max(..rows.map(total))
  let label-width = 46mm
  let plot = W - label-width - 5pt
  let bar-max = plot - 14mm
  set text(font: sans, size: 8pt)
  grid(
    columns: (label-width, plot), column-gutter: 5pt, row-gutter: 3.6pt,
    align: (right + horizon, left + horizon),
    ..rows.map(r => (
      r.label_en,
      [#for (k, p) in parts.enumerate() {
         let v = r.at(p.at(0))
         if v > 0 { bar(bar-max * (v / vmax), 8pt, palette.at(k)) }
       }#h(4pt)#text(size: 7.4pt, fill: muted, str(total(r)))],
    )).flatten(),
  )
  v(5pt)
  legend(parts.enumerate().map(((k, p)) => (palette.at(k), p.at(1))))
}

#let abox(title, body, fill: white) = block(
  width: 100%, inset: (x: 5pt, y: 4.5pt), radius: 3pt, fill: fill,
  stroke: 0.6pt + accent.lighten(35%),
  {
    set par(leading: 0.42em, spacing: 0.45em, justify: false)
    text(size: 7.7pt, weight: "semibold", title)
    if body != none { parbreak(); text(size: 6.9pt, fill: muted, body) }
  })

#let arrow = align(center + horizon, text(size: 12pt, fill: accent, sym.arrow.r))

#let fig-architecture() = {
  let A = F.architecture
  set text(font: sans)
  grid(
    columns: (35mm, 4.5mm, 1fr, 4.5mm, 1fr, 4.5mm, 1fr, 4.5mm, 1fr),
    align: horizon,
    stack(spacing: 2.2pt,
      align(center, text(size: 7.4pt, weight: "semibold", fill: accent)[Six source datasets]),
      ..A.sources.map(s => abox([#s.name · #s.what], [#s.n #s.unit]))),
    arrow,
    abox([Processed corpus], [vn-legal project: documents cleaned and scoped, #A.articles articles,
      validity map with #A.changes change relations, Q&A citation labels], fill: accent-light),
    arrow,
    abox([KG build], [python -m vlonto.cli all: build, export, core, validate, site,
      check-ontology, report (#A.checks checks pass)], fill: accent-light),
    arrow,
    stack(spacing: 2.2pt,
      abox([#A.tables parquet tables], [nodes and edges with method and evidence]),
      abox([RDF dumps], [#A.triples triples (N-Triples), core subset #A.core_triples triples]),
      abox([Ontology], [OWL, SHACL shapes, documentation])),
    arrow,
    stack(spacing: 2.2pt,
      abox([Website], [dashboard, 3D playgrounds, SPARQL in the browser], fill: accent-light),
      abox([Playbook], [Markdown, PDF, HTML], fill: accent-light),
      abox([Agent tools], [validity, citations, related provisions], fill: accent-light)),
  )
}

#let figure-names = ("architecture", "doc-types", "validity", "changes", "modules")

#let vlo-figure(name) = {
  if name == "architecture" { fig-architecture() }
  else if name == "doc-types" { fig-doc-types() }
  else if name == "validity" { fig-validity() }
  else if name == "changes" { fig-changes() }
  else if name == "modules" { fig-modules() }
  else { panic("unknown figure: " + name) }
}

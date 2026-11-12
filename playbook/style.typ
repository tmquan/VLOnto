// VLOnto playbook: page layout and typography.
// Fonts: only the vendored files in typst/fonts are used. Compile with
//   --font-path typst/fonts --ignore-system-fonts --ignore-embedded-fonts
// Noto Serif has no arrows or mathematical operators and would draw the not-equal sign as
// '=' plus a combining overlay, so U+2190-22FF always come from Noto Sans Math (the same
// routing as the website's serif stack). Hyphenation is off: no word is ever split.

#let math-symbols = (name: "Noto Sans Math", covers: regex("[\u{2190}-\u{21FF}\u{2200}-\u{22FF}]"))
#let sans = ("Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math")
#let serif = (math-symbols, "Noto Serif", "Noto Sans Symbols 2", "Noto Sans Math")
#let mono = ("JetBrains Mono NL", "Noto Sans Symbols 2", "Noto Sans Math")

#let accent = rgb("#1d4f7a")
#let accent-light = rgb("#dbe7f1")
#let muted = luma(85)
#let rule-color = luma(195)
#let code-fill = luma(246)

#let parse-date(s) = {
  let p = s.split("-").map(int)
  datetime(year: p.at(0), month: p.at(1), day: p.at(2))
}

#let title-page(title, subtitle, kicker, release, version, date, author, key-figures, licence, disclaimer) = {
  set text(font: sans)
  v(14mm)
  text(size: 9.5pt, weight: "semibold", fill: accent, tracking: 0.06em, upper(kicker))
  v(5mm)
  text(size: 32pt, weight: "bold", title)
  v(4mm)
  block(width: 100%, text(size: 13pt, fill: muted, subtitle))
  // related paper: title, authors, identifier and link from data/citation.json (no numbers)
  let paper = json("data/citation.json")
  v(3.5mm)
  block(width: 100%, text(size: 9.5pt, fill: muted, {
    "Related paper: "
    emph(paper.title)
    " (" + paper.short_authors + ", " + paper.year + "), "
    link(paper.url, text(fill: accent, "arXiv:" + paper.arxiv_id))
  }))
  v(8mm)
  grid(
    columns: (28mm, 1fr), row-gutter: 6pt,
    text(fill: muted)[Release], release + " (version " + version + ")",
    text(fill: muted)[Build date], date,
    text(fill: muted)[Author], author,
  )
  v(1fr)
  text(size: 8pt, fill: muted,
       "Key figures of VLOnto " + release + " (" + version + ", this release), knowledge-graph build of " + date)
  v(2.5mm)
  grid(
    columns: (1fr, 1fr, 1fr), column-gutter: 5mm, row-gutter: 5mm,
    ..key-figures.map(k => block(
      width: 100%, inset: (x: 9pt, y: 8pt), radius: 3pt, fill: accent-light,
      stack(spacing: 4pt, text(size: 15pt, weight: "bold", fill: accent, k.at(0)),
            text(size: 8pt, fill: muted, k.at(1))),
    )),
  )
  v(9mm)
  line(length: 100%, stroke: 0.5pt + rule-color)
  v(2mm)
  set par(leading: 0.55em, spacing: 0.7em)
  text(size: 8pt, fill: muted, licence)
  parbreak()
  text(size: 8pt, fill: muted, disclaimer)
  pagebreak()
}

#let playbook(
  title: [], subtitle: [], kicker: [], author: "", release: "", version: "", date: "", keywords: (),
  key-figures: (), licence: [], disclaimer: [], body,
) = {
  // pandoc line-wraps the template output, which can put a newline inside a keyword string
  set document(title: title, author: author, keywords: keywords.map(k => k.split().join(" ")),
               date: parse-date(date))
  set page(
    paper: "a4",
    margin: (top: 22mm, right: 20mm, bottom: 24mm, left: 20mm),
    header: context {
      let p = here().page()
      let chapters = query(heading.where(level: 1)).filter(h => h.location().page() <= p)
      if p > 1 and chapters.len() > 0 {
        set text(font: sans, size: 7.6pt, fill: muted)
        grid(columns: (auto, 1fr), column-gutter: 8mm, align: (left + bottom, right + bottom),
             [VLOnto playbook #release], chapters.last().body)
        v(-3pt)
        line(length: 100%, stroke: 0.4pt + rule-color)
      }
    },
    footer: context {
      if here().page() > 1 {
        set text(font: sans, size: 7.6pt, fill: muted)
        align(center, counter(page).display("1 / 1", both: true))
      }
    },
  )
  set text(font: serif, size: 9.8pt, lang: "en", hyphenate: false)
  set par(justify: false, leading: 0.62em, spacing: 0.95em)
  set list(indent: 0.3em, body-indent: 0.55em, spacing: 0.62em)
  set enum(indent: 0.3em, body-indent: 0.55em, spacing: 0.62em)
  show link: set text(fill: accent)
  show strong: set text(weight: "bold")

  // headings: numbers are part of the heading text; level 1 starts a page
  set heading(numbering: none)
  show heading: set text(font: sans)
  show heading.where(level: 1): set text(size: 18pt, weight: "bold", fill: accent)
  show heading.where(level: 1): set block(above: 2mm, below: 6mm)
  show heading.where(level: 1): it => { pagebreak(weak: true); it }
  show heading.where(level: 2): set text(size: 12.2pt, weight: "bold")
  show heading.where(level: 2): set block(above: 1.5em, below: 0.75em)
  show heading.where(level: 3): set text(size: 10.4pt, weight: "semibold")
  show heading.where(level: 3): set block(above: 1.3em, below: 0.65em)
  show heading.where(level: 4): set text(size: 9.8pt, weight: "semibold", fill: muted)

  // Vietnamese document and decision numbers (45/2019/QH14, 13/2000/TT-BLĐTBXH) never break
  show regex("\b\d{1,4}/\d{4}/[A-ZĐ][A-ZĐ0-9]*(-[A-ZĐ0-9]+)*"): box

  // code; Typst sets raw text at 0.8em by default, so 1.1em gives 0.88em of the text around it
  show raw: set text(font: mono)
  show raw.where(block: false): set text(size: 1.1em)
  show raw.where(block: true): set text(size: 7.9pt)
  show raw.where(block: true): set par(leading: 0.5em, justify: false)
  show raw.where(block: true): it => block(
    width: 100%, fill: code-fill, inset: (x: 7pt, y: 6pt), radius: 2pt, breakable: true, it)

  // tables (pandoc puts them in figures; let them break across pages)
  show figure.where(kind: table): set block(breakable: true)
  show figure.where(kind: table): set block(above: 1em, below: 1.1em)
  set table(
    inset: (x: 4.2pt, y: 3.4pt), stroke: none,
    fill: (x, y) => if y == 0 { luma(232) } else if calc.even(y) { luma(248) } else { none },
  )
  show table: set text(size: 8.3pt)
  show table: set par(leading: 0.48em, justify: false)
  show table: set align(left)  // pandoc wraps tables in align(center); cells start left
  show table.cell.where(y: 0): set text(font: sans, weight: "semibold", size: 7.9pt)

  // figures and quotes
  show figure.where(kind: image): set block(above: 1.3em, below: 1.3em)
  show figure.caption: set text(font: sans, size: 8pt, fill: muted)
  set figure(gap: 0.9em)
  show quote.where(block: true): it => block(
    width: 100%, above: 1.1em, below: 1.1em, inset: (left: 9pt, top: 3pt, bottom: 3pt),
    stroke: (left: 2pt + accent.lighten(45%)), it.body)

  title-page(title, subtitle, kicker, release, version, date, author, key-figures, licence, disclaimer)

  show outline.entry.where(level: 1): set text(font: sans, weight: "semibold")
  show outline.entry.where(level: 1): set block(above: 0.85em)
  outline(title: [Contents], depth: 2, indent: auto)

  body
}

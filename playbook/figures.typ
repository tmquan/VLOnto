// Standalone pages of the playbook figures (charts.typ).
//   --input fig=NAME  one figure, exported as SVG for playbook.md and the website
//   --input fig=all   every figure on its own page (PDF checked with tools/pdf_check.py)
#import "charts.typ": vlo-figure, figure-names, W
#set page(width: W + 8pt, height: auto, margin: 4pt, fill: white)
#set text(lang: "en")
#let which = sys.inputs.at("fig", default: "all")
#if which == "all" {
  for (i, n) in figure-names.enumerate() {
    if i > 0 { pagebreak() }
    vlo-figure(n)
  }
} else {
  vlo-figure(which)
}

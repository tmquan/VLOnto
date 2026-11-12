// pandoc template: pandoc in.md -s -t typst --template pandoc_template.typ -o doc.typ
// The body pandoc writes calls helpers that pandoc's own template defines (see: pandoc -D typst); they must live
// in the same file as the body, because definitions are not visible inside an included file.
// Note: pandoc substitutes every dollar-delimited name in this file, comments included.
#import "common.typ": template
#let horizontalrule = line(start: (25%, 0%), end: (75%, 0%), stroke: 0.5pt + luma(150))
#show: template.with(title: "$if(title)$$title$$else$VLOnto$endif$")

$body$

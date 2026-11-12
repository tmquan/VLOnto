// pandoc template of the VLOnto playbook:
//   pandoc playbook.md -t typst -s --template template.typ --metadata-file data/meta.json
// The body pandoc writes calls helpers defined here, so this stays a template (an included
// file could not see them). pandoc substitutes dollar-delimited names everywhere in this file.
#import "style.typ": *
#import "charts.typ": vlo-figure

#let horizontalrule = line(length: 100%, stroke: 0.5pt + rule-color)

#show terms.item: it => block(breakable: false)[
  #text(weight: "bold")[#it.term]
  #block(inset: (left: 1.5em, top: -0.4em))[#it.description]
]

$if(highlighting-definitions)$
$highlighting-definitions$

$endif$
#show: playbook.with(
  title: [$title$],
  subtitle: [$subtitle$],
  kicker: [$kicker$],
  author: "$author$",
  version: "$version$",
  date: "$date$",
  keywords: ($for(keywords)$"$keywords$", $endfor$),
  key-figures: ($for(keyfigures)$([$keyfigures.value$], [$keyfigures.label$]), $endfor$),
  licence: [$licence$],
  disclaimer: [$disclaimer$],
)

$body$

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

#show: playbook.with(
  title: [VLOnto playbook],
  subtitle: [Build, validate, query and use the Vietnamese legal
knowledge graph],
  kicker: [Vietnamese legal ontology and knowledge graph],
  author: "tmquan",
  version: "1.0.0",
  release: "v1",
  date: "2026-11-12",
  keywords: ("VLOnto", "Vietnamese law", "legal ontology", "knowledge
graph", "OWL", "SKOS", "ELI", "RDF", "SPARQL", "legal informatics", ),
  key-figures: (([40,816], [legal documents]), ([436,309], [articles
(Điều)]), ([15,035], [dated change events]), ([109,543], [legal Q&As
(metadata)]), ([6,963,753], [RDF triples]), ([20 / 20], [build checks
passed]), ),
  licence: [Ontology and documentation: CC BY 4.0, creator tmquan.
Knowledge-graph data: see the licence and attribution appendix.],
  disclaimer: [Not legal advice and not an official legal text.
Relations are extracted automatically and may be wrong; read the source
documents.],
)

= 1. Scope, audience and disclaimer
<scope-audience-and-disclaimer>
VLOnto is an OWL ontology of Vietnamese law and a knowledge graph built
with it from four public datasets of Vietnamese legal material. In
VLOnto v1 (version 1.0.0, this release), the graph connects 40,816 legal
documents and their 436,309 articles (#emph[Điều]) with the 15,035 dated
events that replaced, amended or repealed them, with 99,038 legal-basis
links and 268,563 citation links between documents, and with 109,543
published legal Q&As, 16,701 legal terms and 681 legal news items. The
build writes 21 parquet tables, a full RDF dump of 6,963,753 triples and
a browser-sized RDF subset of 49,846 triples. VLOnto is published as
code and a website: the GitHub repository holds the build code, the
ontology with SHACL shapes and documentation, a website with 3D
playgrounds and a SPARQL playground, and this playbook. The data stays
in the four source datasets, and the knowledge graph is built from them
on your own machine (section~2.2).

#strong[Court decisions join in v2.] VLOnto v1 is built from the four
thuvienphapluat.vn datasets only. The court datasets `anle-toaan-gov-vn`
and `cbba-toaan-gov-vn` (court decisions and precedents, with the
provisions they apply) are planned for VLOnto v2 (version 2.0.0); the
judiciary classes and properties stay in the ontology with a scope note
that says so (section~4.2). #emph[Bản án, quyết định của Tòa án và án lệ
sẽ được bổ sung trong VLOnto v2.]

#strong[Who this is for.] Engineers who build legal search, question
answering or agents over Vietnamese law and need structured validity,
citation and Q&A-usage data; legal-technology practitioners who want to
query that data without building it; and maintainers who rebuild and
release VLOnto. The playbook assumes working knowledge of Python and
SQL; SPARQL and OWL are introduced where they are used.

#strong[What it covers.] How to open the offline website and query the
files (section~2), how the data flows from the source datasets to the
outputs of the build (section~3), the ontology (section~4), how to
rebuild the graph (section~5) and how it was validated (section~6),
query recipes with their real results (section~7), how to use VLOnto
inside the Vietnamese legal assistant agent (section~8), the website
(section~9), reproducibility and maintenance (sections~10 and 11) and
the known limits (section~12). How to cite VLOnto is in section~1.1, and
the references follow section~12. The appendices are generated from the
ontology file, the data dictionary and the licence policy.

#strong[Where the numbers come from.] Every number in this playbook is
read from the build reports of 2026-11-12 by
`playbook/tools/gather_facts.py`, which also runs every query recipe and
code example against that build and stores their output;
`playbook/tools/render_md.py` then fills this text. No number is typed
by hand, so a rebuild of the graph followed by a rebuild of the playbook
updates all of them. All of them describe VLOnto v1 (1.0.0), this
release.

#quote(block: true)[
#strong[Not legal advice.] VLOnto is a research and engineering
resource. It is not an official legal text and not legal advice. Its
relations are extracted automatically from public sources and can be
wrong; the validity of 28,660 of the 40,816 documents (70.2%) is
unknown. Read the source document (every document, Q&A and term keeps
its source URL) and ask a qualified Vietnamese lawyer before relying on
any legal conclusion.
]

== 1.1 How to cite
<how-to-cite>
#block(sticky: true, width: 100%)[
The approach is described in the paper #emph[Vietnamese Legal Ontology:
Every legal answer, traced to the article that grounds it] (Bui and Tran
Minh, 2026,
#link("https://arxiv.org/abs/2611.11426")[arXiv:2611.11426]\; see
References). Numbers in this playbook are computed from the VLOnto v1
(1.0.0) release and can differ from the paper's. Cite the paper with
this BibTeX entry; the repository also has a `CITATION.cff` file:

]
```bibtex
@misc{bui2026vietnamese,
  title         = {Vietnamese Legal Ontology: Every legal answer, traced to the article
                   that grounds it},
  author        = {Bui, Khac-Hoai Nam and Tran Minh, Quan},
  year          = {2026},
  eprint        = {2611.11426},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2611.11426}
}
```

= 2. Quick start
<quick-start>
== 2.1 Open the offline playground
<open-the-offline-playground>
#block(sticky: true, width: 100%)[
The website is published at #link("https://tmquan.github.io/VLOnto/").
It also runs from a folder on disk, without a server and without network
access:

]
+ Clone the repository #link("https://github.com/tmquan/VLOnto") or
  download it as a ZIP file.
+ Double-click `site/index.html` in the repository folder: it opens the
  3D ontology playground as a `file://` URL. The overview of VLOnto,
  with the key counts of the build, is `site/about.html`.
+ The other pages are the legal-network playground, the SPARQL
  playground, the dashboard, the question traces, the ontology
  documentation, this playbook and the downloads page; section~9 lists
  every page with its file name.

All scripts, fonts and data are inside the folder; the pages load no
external resources. The site is checked with headless Chrome over
`file://` and `http://` (`tools/site_check.py`); Safari and Firefox are
not machine-tested, so open the site in them before relying on them
(section~12).

== 2.2 Get the code and the data
<get-the-code-and-the-data>
#block(sticky: true, width: 100%)[
VLOnto is published as code and a website, not as a data release. The
GitHub repository #link("https://github.com/tmquan/VLOnto") holds the
build code (`vlonto/`), the corpus pipeline (`pipeline/`), the ontology
(`ontology/`), this playbook (`playbook/`) and the website (`site/`),
which GitHub Pages serves at #link("https://tmquan.github.io/VLOnto/").
The data comes from the four source datasets on Hugging Face
(section~3): `python -m vlonto.cli all` builds the knowledge graph from
them on your machine (section~5) and writes the parquet tables to
`build/kg/` and the RDF dumps to `build/rdf/`. The build reads the
processed corpus of the vn-legal project (section~5.1), which
`pipeline/` produces from the source datasets (see
`pipeline/README.md`). The ontology and the browser subset need no
build: the website's downloads page offers them.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (33.62%, 12.07%, 54.31%),
    align: (left,right,left,),
    table.header([File], [Size], [Where to get it],),
    table.hline(),
    [`kg/*.parquet` (21 tables)], [27.9 MB], [local build, `build/kg/`],
    [`kg/data_dictionary.md`, `.json`], [44 kB], [local build,
    `build/kg/`\; the `.md` file also from the downloads page],
    [`rdf/vlonto-kg.nt.gz`], [48.2 MB], [local build, `build/rdf/`],
    [`rdf/vlonto-core.ttl`], [2.6 MB], [local build, `build/rdf/`\;
    downloads page],
    [`ontology/vlonto.ttl`], [122 kB], [repository, `ontology/`\;
    downloads page],
    [`ontology/vlonto-shapes.ttl`], [13 kB], [repository, `ontology/`\;
    downloads page],
    [`ontology/vlonto-context.jsonld`], [7 kB], [repository,
    `ontology/`\; downloads page],
    [`ontology/vlonto.html`], [680 kB], [repository, `ontology/`\; the
    website's ontology page],
  )]
  , kind: table
  )

]
Sizes are those of the reference build of 2026-11-12 (section~10.4).
`rdf/vlonto-kg.nt.gz` is the whole graph as gzip-compressed N-Triples;
`rdf/vlonto-core.ttl` is the subset the browser loads (section~9);
`ontology/` holds the OWL ontology, its SHACL shapes, a JSON-LD context
and the HTML documentation; `kg/` holds the tables documented in
Appendix~C. The downloads page also offers the website's JSON data, the
licence policy, the attribution text, the figures and this playbook as
PDF and Markdown. The local-only table `article_text` (436,309 rows of
article text) is written for local use only and is never shared
(Appendix~D).

== 2.3 Install the query libraries
<install-the-query-libraries>
#block(sticky: true, width: 100%)[
The examples use the versions of the build environment (Python 3.11.18):

]
```bash
pip install duckdb==2.0.0 polars==2.1.0 pyoxigraph==0.5.13
```

Run the examples in the build folder of a local build (`build/`, or
`$VLONTO_BUILD`), which contains `kg/` and `rdf/`. The SPARQL example of
section~2.6 needs only `rdf/vlonto-core.ttl`, which the website's
downloads page also offers.

== 2.4 SQL over the parquet tables with DuckDB
<sql-over-the-parquet-tables-with-duckdb>
#block(sticky: true, width: 100%)[
DuckDB reads parquet files in place; a table is its file name. Count
documents per validity class (`playbook/examples/quickstart_duckdb.py`):

]
```python
"""Count documents per validity class with DuckDB (run next to the kg/ folder)."""
import duckdb

con = duckdb.connect()
rows = con.execute("""
    SELECT validity, count(*) AS documents
    FROM 'kg/documents.parquet'
    GROUP BY validity
    ORDER BY documents DESC, validity
""").fetchall()
for validity, n in rows:
    print(f"{validity:<27}{n:>7,}")
```

#block(sticky: true, width: 100%)[
Output:

]
```text
unknown                     28,660
superseded                   5,167
presumed_in_force_amended    2,722
expired                      2,125
in_force                     1,511
in_force_amended               545
not_applicable                  47
not_yet_effective               39
```

== 2.5 DataFrames with polars
<dataframes-with-polars>
#block(sticky: true, width: 100%)[
Find the Labour Code by its number and list its first articles
(`playbook/examples/quickstart_polars.py`):

]
```python
"""Find a document by its number and list its first articles with polars."""
import polars as pl

docs = pl.read_parquet("kg/documents.parquet")
code = docs.filter(pl.col("doc_number") == "45/2019/QH14")
for row in code.select("doc_id", "title_vi", "issue_date", "validity").iter_rows():
    print(*row, sep=" | ")

articles = (
    pl.scan_parquet("kg/articles.parquet")
    .filter(pl.col("doc_id") == code["doc_id"][0])
    .sort("position")
    .select("article_no", "heading")
    .head(4)
    .collect()
)
for no, heading in articles.iter_rows():
    print(f"Điều {no}: {heading}")
```

#block(sticky: true, width: 100%)[
Output:

]
```text
333670 | Bộ luật Lao động | 2019-11-20 | in_force_amended
Điều 1: Phạm vi điều chỉnh
Điều 2: Đối tượng áp dụng
Điều 3: Giải thích từ ngữ
Điều 4: Chính sách của Nhà nước về lao động
```

== 2.6 SPARQL with pyoxigraph
<sparql-with-pyoxigraph>
#block(sticky: true, width: 100%)[
The browser subset loads into memory in a moment. List the codes
(#emph[bộ luật]) that are in force
(`playbook/examples/quickstart_sparql.py`):

]
```python
"""Load the browser-sized Turtle subset into pyoxigraph and run SPARQL."""
from pyoxigraph import RdfFormat, Store

store = Store()  # in memory
store.load(path="rdf/vlonto-core.ttl", format=RdfFormat.TURTLE)
print(f"{len(store):,} triples")

QUERY = """
PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?number ?title WHERE {
  ?code a vlo:Code ; vlo:title ?title ; vlo:isInForce true .
  OPTIONAL { ?code vlo:documentNumber ?number }
}
ORDER BY ?number
"""
for row in store.query(QUERY):
    number = row["number"].value if row["number"] else "-"
    print(number, row["title"].value)
```

#block(sticky: true, width: 100%)[
Output:

]
```text
49,846 triples
100/2015/QH13 Bộ luật Hình sự
101/2015/QH13 Bộ luật Tố tụng hình sự
45/2019/QH14 Bộ luật Lao động
74/2006/QH11 Bộ luật 74/2006/QH11
84/2007/QH11 Bộ luật 84/2007/QH11
91/2015/QH13 Bộ luật Dân sự
92/2015/QH13 Bộ luật Tố tụng dân sự
95/2015/QH13 Bộ luật Hàng hải Việt Nam
```

The subset holds the ontology and the 1,781 documents of the highest
legal-force ranks (constitution; codes, laws and national assembly
resolutions; ordinances and standing committee resolutions) with the 612
change events, 4,997 legal-basis edges and 6,198 document-level
citations among them. Questions about decrees, circulars, Q&As or terms
need the full dump, which is bulk-loaded into an on-disk store once
(`playbook/examples/load_full_dump.py`):

```python
"""Bulk-load the full N-Triples dump into an on-disk pyoxigraph store."""
import gzip

from pyoxigraph import RdfFormat, Store

store = Store("vlonto-store")  # RocksDB directory, created if missing
with gzip.open("rdf/vlonto-kg.nt.gz", "rb") as dump:
    store.bulk_load(dump, format=RdfFormat.N_TRIPLES)
store.optimize()
print(f"{len(store):,} triples in vlonto-store/")
```

#block(sticky: true, width: 100%)[
Output:

]
```text
6,963,753 triples in vlonto-store/
```

The build loaded the same dump into Oxigraph in 7.8 s (6,963,753
triples). Afterwards open the store with `Store("vlonto-store")` and
query it as above; section~7 runs every SPARQL recipe against this
store.

= 3. Architecture
<architecture>
#figure([#vlo-figure("architecture")],
  caption: [
    Data flow: the four source datasets, the processed corpus of the
    vn-legal project, the knowledge-graph build, the tables and RDF
    dumps it writes, and their uses.
  ]
)

#block(sticky: true, width: 100%)[
#strong[Source datasets.] Four datasets published on Hugging Face by
`tmquan` are the data home of VLOnto v1; each is at
`https://huggingface.co/datasets/tmquan/<dataset>` (the names in the
table are links), pinned to a fixed revision:

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (25.22%, 20%, 26.96%, 13.91%, 13.91%),
    align: (left,left,left,left,left,),
    table.header([Dataset], [Content], [Source], [Revision], [Licence],),
    table.hline(),
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-hdpl")[`thuvienphapluat-vn-hdpl`]], [legal
    Q&A], [thuvienphapluat.vn], [`e814ecbfa1a1`], [other],
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-htpl")[`thuvienphapluat-vn-htpl`]], [legal
    news], [thuvienphapluat.vn], [`043c8f2988e2`], [other],
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-tnpl")[`thuvienphapluat-vn-tnpl`]], [legal
    terminology], [thuvienphapluat.vn/tnpl], [`f94d1e24852f`], [other],
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-vbpl")[`thuvienphapluat-vn-vbpl`]], [legal
    documents], [thuvienphapluat.vn], [`705ade585384`], [cc-by-4.0],
  )]
  , kind: table
  )

]
The court datasets
#link("https://huggingface.co/datasets/tmquan/anle-toaan-gov-vn")[`anle-toaan-gov-vn`]
and
#link("https://huggingface.co/datasets/tmquan/cbba-toaan-gov-vn")[`cbba-toaan-gov-vn`]
are not read by VLOnto v1; they join in VLOnto v2.

#block(sticky: true, width: 100%)[
#strong[Processed corpus.] The vn-legal project (the data pipeline of
the Vietnamese legal assistant, section~8) downloads the pinned
revisions, cleans and scopes the documents, splits them into articles
and extracts the validity map from the text of newer documents (validity
rules v7). VLOnto reads its outputs instead of re-parsing the sources:

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (25%, 75%),
    align: (left,left,),
    table.header([Input], [File (vn-legal root R)],),
    table.hline(),
    [`chunks`], [`$R/data/chunks/chunks.parquet`],
    [`doc_struct`], [`$R/data/chunks/doc_struct.parquet`],
    [`docs_clean`], [`$R/data/clean/docs_clean.parquet`],
    [`gold_all`], [`$R/eval/gold_all.parquet`],
    [`relations`], [`$R/data/validity/relations.parquet`],
    [`validity`], [`$R/data/validity/validity.parquet`],
  )]
  , kind: table
  )

]
From the vbpl snapshot, 40,816 documents are in scope (the normative
documents kept by the cleaning step of vn-legal); the Q&As, terms and
news are read from the source snapshots directly.

#figure([#vlo-figure("doc-types")],
  caption: [
    In-scope legal documents by type: number and share of the 40,816
    documents.
  ]
)

#strong[Knowledge-graph build.] `python -m vlonto.cli all` (section~5)
resolves every reference to a document, article, clause or point, writes
the node and edge tables with the method and evidence of each edge,
exports RDF, validates, and writes the website data. 850,703 nodes and
556,287 edges are stored in the parquet tables.

#strong[Outputs.] The parquet tables are the primary form (fast,
columnar, with provenance columns); the RDF dump states the same facts
with the ontology's IRIs (6,963,753 triples); the core Turtle subset
serves the browser; the website and this playbook are generated from the
build reports. There is no separate data release: the tables and the
full dump are rebuilt from the source datasets, while the GitHub
repository and the website carry the code, the ontology, the core subset
and this playbook (section~2.2).

#strong[What is deliberately left out.] No article or document bodies,
no Q&A or news text, no glossary definitions and no person names are
published; titles, article headings (up to 200 characters) and
one-sentence evidence quotes (up to 300 characters) are kept as labels.
Text stays at the source URL that every record carries (Appendix~D). The
website's question traces page (section~9) is the one exception: it
shows the published title of each question it traces, with a short
English gloss, but not the full question and no answer text.

= 4. The ontology
<the-ontology>
VLOnto is an OWL 2 ontology in Turtle (`ontology/vlonto.ttl`, 2,061
triples) with 47 classes, 46 object properties, 35 datatype properties,
3 annotation properties and 13 SKOS concept schemes. Every VLOnto term
has an English and a Vietnamese label and an English definition (the
completeness check of section~6), and 47 of the 131 terms also have a
Vietnamese definition. Namespace:
`https://tmquan.github.io/VLOnto/ontology#` (prefix `vlo:`); instances:
`https://tmquan.github.io/VLOnto/id/` (prefix `vlid:`).

== 4.1 Modules
<modules>
Each term belongs to one of 11 thematic modules (annotation
`vlo:module`); the 3D ontology playground colours terms by module.

#figure([#vlo-figure("modules")],
  caption: [
    Number of VLOnto terms per module, by kind.
  ]
)

#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (16.24%, 14.53%, 38.46%, 10.26%, 10.26%, 10.26%),
    align: (left,left,left,right,right,right,),
    table.header([Module], [Vietnamese], [Scope], [Classes], [Object
      prop.], [Data prop.],),
    table.hline(),
    [`documents`], [văn bản], [Legal documents and their
    types.], [12], [1], [4],
    [`provisions`], [điều khoản], [Structural units of legal documents:
    parts, chapters, sections, articles, clauses, points and
    appendices.], [8], [3], [3],
    [`agents`], [chủ thể], [Public authorities that issue documents or
    decide cases.], [3], [1], [1],
    [`validity-change`], [hiệu lực và thay đổi], [Validity status of
    documents and the dated events that replace, amend, repeal or
    terminate them.], [3], [16], [10],
    [`citation-basis`], [trích dẫn và căn cứ], [Legal-basis and citation
    links between legal resources and from other works to legal
    resources.], [0], [5], [0],
    [`judiciary`], [tư pháp], [Court decisions, judgments, precedents
    and their classification. No data in VLOnto v1; populated from v2
    (section~4.2).], [8], [9], [4],
    [`qa`], [hỏi đáp pháp luật], [Published legal questions and their
    answers.], [2], [3], [1],
    [`terminology`], [thuật ngữ], [Legal terms organised as SKOS
    concepts.], [1], [1], [2],
    [`news`], [tin tức], [Legal news and policy articles that mention
    legal documents.], [2], [2], [0],
    [`classification`], [phân loại], [Concept schemes for legal areas,
    document types and legal-force ranks.], [3], [2], [1],
    [`provenance`], [nguồn gốc], [Source datasets, extraction methods,
    edge sets and build activities.], [5], [3], [9],
  )]
  , kind: table
  )

]
== 4.2 Key classes
<key-classes>
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 16.38%, 56.9%),
    align: (left,left,left,),
    table.header([Class], [Vietnamese], [Definition and superclasses],),
    table.hline(),
    [`vlo:LegalDocument`], [Văn bản pháp luật], [A document issued by a
    competent state body that has legal effect, identified by its type,
    number and issue date. Subclass of `eli:LegalResource`,
    `schema:Legislation`.],
    [`vlo:NormativeLegalDocument`], [Văn bản quy phạm pháp luật], [A
    legal document containing generally binding rules of conduct, issued
    in the form, order and procedure set out by the Law on Promulgation
    of Legal Normative Documents. Subclass of `vlo:LegalDocument`.],
    [`vlo:Provision`], [Đơn vị cấu trúc của văn bản], [A structural unit
    of a legal document, such as a part, chapter, section, article,
    clause, point or appendix. Subclass of
    `eli:LegalResourceSubdivision`.],
    [`vlo:Article`], [Điều], [The basic numbered unit of a legal
    document (Điều N), usually with a heading, divided into clauses.
    Subclass of `vlo:Provision`.],
    [`vlo:Clause`], [Khoản], [A numbered subdivision of an article
    (khoản 1, khoản 2, …). Subclass of `vlo:Provision`.],
    [`vlo:Point`], [Điểm], [A lettered subdivision of a clause (điểm a,
    điểm b, …). Subclass of `vlo:Provision`.],
    [`vlo:IssuingBody`], [Cơ quan ban hành], [A public authority that
    issues legal documents, identified in the knowledge graph by the
    issuer code used in document numbers (for example BTC for the
    Ministry of Finance). Subclass of `vlo:PublicAuthority`.],
    [`vlo:LegalChange`], [Sự kiện thay đổi hiệu lực văn bản], [A dated
    event in which an acting legal document replaces, amends, repeals,
    partially repeals or partially terminates an affected legal
    document. The event is reified so that its kind, effective date, the
    evidence sentence and the extraction method can be recorded; the
    direct shortcut properties (vlo:replaces, vlo:amends, …) carry the
    same information without the details. Subclass of `prov:Activity`.],
    [`vlo:ValidityStatus`], [Tình trạng hiệu lực], [The validity of a
    legal document as of the knowledge-graph date, combining the curated
    source status with text-extracted change relations (validity rules
    v7). It refines the ELI in-force concept with eight values. Subclass
    of `eli:InForce`, `skos:Concept`.],
    [`vlo:LegalQuestion`], [Câu hỏi pháp luật], [A published legal
    question from a legal Q&A service. The knowledge graph keeps its
    identifier, link, date and legal area, not its text. Subclass of
    `schema:Question`.],
    [`vlo:LegalAnswer`], [Câu trả lời pháp luật], [The published answer
    to a legal question; in the knowledge graph it carries the citations
    of legal documents and provisions found in the answer, not its text.
    Subclass of `schema:Answer`.],
    [`vlo:LegalTerm`], [Thuật ngữ pháp lý], [A term of Vietnamese legal
    language, organised as a SKOS concept with a Vietnamese preferred
    label, an English label (machine translation unless marked
    otherwise), a legal area, a status and related terms. Subclass of
    `skos:Concept`.],
    [`vlo:LegalArea`], [Lĩnh vực pháp luật], [A subject area of law used
    to classify documents, questions and terms, such as labour and wages
    or real estate. Subclass of `skos:Concept`.],
    [`vlo:SourceDataset`], [Bộ dữ liệu nguồn], [A published dataset,
    pinned to a revision, from which knowledge-graph records were
    derived; carries its licence and attribution text. Subclass of
    `prov:Entity`.],
    [`vlo:EdgeSet`], [Tập liên kết], [The set of all knowledge-graph
    links of one property produced from one source, described with its
    size, the extraction methods used and the build that generated it.
    Per-link methods are kept in the parquet edge tables. Subclass of
    `prov:Entity`.],
  )]
  , kind: table
  )

]
Documents are typed by 10 subclasses of `vlo:NormativeLegalDocument`,
one per document type, each linked to its concept in the document-type
scheme: `vlo:Constitution` (#emph[Hiến pháp]), `vlo:Code` (#emph[Bộ
luật]), `vlo:Law` (#emph[Luật]), `vlo:Ordinance` (#emph[Pháp lệnh]),
`vlo:Resolution` (#emph[Nghị quyết]), `vlo:JointResolution` (#emph[Nghị
quyết liên tịch]), `vlo:Decree` (#emph[Nghị định]), `vlo:Decision`
(#emph[Quyết định]), `vlo:Circular` (#emph[Thông tư]),
`vlo:JointCircular` (#emph[Thông tư liên tịch]). Structural units:
`vlo:Part`, `vlo:Chapter`, `vlo:Section` and `vlo:Appendix`.

#strong[Judiciary terms (v2).] The judiciary module keeps its 21 terms
in the ontology, among them `vlo:CourtDecision`, `vlo:Judgment`,
`vlo:CourtRuling`, `vlo:Precedent`, and the properties `vlo:decidedBy`,
`vlo:appliesProvision` and `vlo:citesCase` (Appendix~B.6). They, the
module's concept schemes and the class `vlo:Court` carry a scope note in
English and Vietnamese (26 terms, schemes and modules), which says that
they are populated from VLOnto v2; the module's note reads: #emph[The
terms of this module are populated from VLOnto 2.0 (court datasets
anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
graph has no court data.] (#emph[Các khái niệm của mô-đun này có dữ liệu
từ VLOnto 2.0 (các bộ dữ liệu tòa án anle-toaan-gov-vn và
cbba-toaan-gov-vn); đồ thị tri thức VLOnto 1.0.0 chưa có dữ liệu tòa
án.])

== 4.3 Key properties
<key-properties>
#figure(
  align(center)[#table(
    columns: (25.86%, 23.28%, 23.28%, 27.59%),
    align: (left,left,left,left,),
    table.header([Property], [Domain], [Range], [Sub-property of],),
    table.hline(),
    [`vlo:legalBasis`], [`vlo:LegalDocument`], [`vlo:LegalDocument`], [`eli:based_on`,
    `vlo:refersTo`],
    [`vlo:cites`], [`eli:LegalResource`], [`eli:LegalResource`], [`eli:cites`,
    `vlo:refersTo`],
    [`vlo:citesParentLaw`], [`eli:LegalResource`], [`eli:LegalResource`], [`vlo:cites`],
    [`vlo:replaces`], [`vlo:LegalDocument`], [`vlo:LegalDocument`], [`eli:repeals`,
    `vlo:changes`],
    [`vlo:amends`], [`vlo:LegalDocument`], [`vlo:LegalDocument`], [`eli:amends`,
    `vlo:changes`],
    [`vlo:repeals`], [`vlo:LegalDocument`], [`vlo:LegalDocument`], [`eli:repeals`,
    `vlo:changes`],
    [`vlo:partiallyRepeals`], [`vlo:LegalDocument`], [`vlo:LegalDocument`], [`vlo:changes`],
    [`vlo:partiallyTerminates`], [`vlo:LegalDocument`], [`vlo:LegalDocument`], [`vlo:changes`],
    [`vlo:actingDocument`], [`vlo:LegalChange`], [`vlo:LegalDocument`], [-],
    [`vlo:affectedDocument`], [`vlo:LegalChange`], [`vlo:LegalDocument`], [-],
    [`vlo:changeKind`], [`vlo:LegalChange`], [`vlo:ChangeKind`], [-],
    [`vlo:validityStatus`], [`vlo:LegalDocument`], [`vlo:ValidityStatus`], [`eli:in_force`],
    [`vlo:isPartOf`], [`vlo:Provision`], [`eli:LegalResource`], [`eli:is_part_of`],
    [`vlo:inDocument`], [`vlo:Provision`], [`vlo:LegalDocument`], [`eli:is_part_of`],
    [`vlo:issuedBy`], [`vlo:LegalDocument`], [`vlo:IssuingBody`], [`eli:passed_by`],
    [`vlo:answerCitesProvision`], [`vlo:LegalAnswer`], [`vlo:Provision`], [`schema:citation`,
    `vlo:refersTo`],
    [`vlo:answerCitesDocument`], [`vlo:LegalAnswer`], [`vlo:LegalDocument`], [`schema:citation`,
    `vlo:refersTo`],
    [`vlo:relatedTerm`], [`vlo:LegalTerm`], [`vlo:LegalTerm`], [`skos:related`],
    [`vlo:sourceDataset`], [-], [`vlo:SourceDataset`], [`dcterms:source`],
  )]
  , kind: table
  )

A change has two representations. The event (`vlo:LegalChange`) records
the acting and the affected document, the kind, the effective date, the
evidence sentence and the rule version; the shortcut triple
(`vlid:document/A vlo:replaces vlid:document/B`) makes simple queries
short. Citations point to the most specific target that was resolved: a
point, else a clause, else an article, else the document; `vlo:isPartOf`
links a point to its clause, a clause to its article and an article to
its chapter or document, and `vlo:inDocument` links every provision
directly to its document.

== 4.4 Alignments
<alignments>
#block(sticky: true, width: 100%)[
VLOnto reuses established vocabularies through sub-class and
sub-property axioms rather than redefining them: 62 alignment axioms to
42 external terms in 6 vocabularies. A tool that knows ELI, SKOS,
PROV-O, schema.org, ORG or DCTERMS can therefore read VLOnto data after
reasoning (the OWL-RL closure of the validation sample infers 4,752
`eli:LegalResource` instances, section~6).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (24.14%, 8.62%, 67.24%),
    align: (left,right,left,),
    table.header([Vocabulary], [Axioms], [Examples (VLOnto term → term
      it specialises)],),
    table.hline(),
    [DCMI Terms], [12], [`vlo:heading` → `dcterms:title`,
    `vlo:legalArea` → `dcterms:subject`, `vlo:provisionNumber` →
    `dcterms:identifier`, …],
    [ELI - European Legislation Identifier], [20], [`vlo:DocumentType` →
    `eli:ResourceType`, `vlo:LegalDocument` → `eli:LegalResource`,
    `vlo:Provision` → `eli:LegalResourceSubdivision`, …],
    [W3C Organization ontology], [1], [`vlo:PublicAuthority` →
    `org:Organization`],
    [PROV-O], [6], [`vlo:BuildActivity` → `prov:Activity`, `vlo:EdgeSet`
    → `prov:Entity`, `vlo:ExtractionMethod` → `prov:Plan`, …],
    [schema.org], [10], [`vlo:LegalAnswer` → `schema:Answer`,
    `vlo:LegalDocument` → `schema:Legislation`, `vlo:LegalNewsArticle` →
    `schema:NewsArticle`, …],
    [SKOS], [13], [`vlo:ChangeKind` → `skos:Concept`, `vlo:DocumentType`
    → `skos:Concept`, `vlo:ExtractionMethod` → `skos:Concept`, …],
  )]
  , kind: table
  )

]
The ELI terms used were checked against the ELI ontology itself: all 18
exist there (124 ELI terms defined). Appendix~B lists every axiom with
its term.

== 4.5 IRI scheme
<iri-scheme>
#block(sticky: true, width: 100%)[
Instance IRIs are built from the source identifiers, so they are stable
across rebuilds of the same source revisions:

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (24.14%, 45.69%, 30.17%),
    align: (left,left,left,),
    table.header([Node], [IRI pattern], [Note],),
    table.hline(),
    [document], [`vlid:document/<doc_id>`], [vbpl document id],
    [article], [`vlid:document/<doc_id>/dieu-<n>`], [appendix articles:
    `att<s>-dieu-<n>`],
    [clause, point], [`.../dieu-<n>/khoan-<k>/diem-<p>`], [created when
    an edge refers to them],
    [part, chapter, section,
    appendix], [`vlid:document/<doc_id>/chuong-iii/muc-3`], [structure
    path],
    [change event], [`vlid:change/<acting>-<kind>-<affected>`], [one per
    relation],
    [Q&A, answer], [`vlid:qa/<id>`, `vlid:qa/<id>/answer`], [hdpl id],
    [term, news item], [`vlid:term/<id>`, `vlid:news/<id>`], [tnpl and
    htpl ids],
    [area, issuer], [`vlid:area/<slug>`, `vlid:issuer/<code>`], [curated
    codes],
    [source, edge set, build], [`vlid:source/<dataset>`,
    `vlid:edgeset/<name>`], [provenance nodes],
  )]
  , kind: table
  )

]
The namespaces are under the website address
`https://tmquan.github.io/VLOnto/`. GitHub Pages serves static files
without content negotiation, so a client that dereferences an IRI gets a
web page or nothing, not RDF: load the Turtle file or the dump instead
of dereferencing IRIs.

== 4.6 Versioning
<versioning>
The ontology header carries `owl:versionInfo "1.0.0"`,
`owl:versionIRI <https://tmquan.github.io/VLOnto/ontology/1.0.0>`,
`owl:priorVersion <https://tmquan.github.io/VLOnto/ontology/0.1.0>`,
`dcterms:created` and `dcterms:modified` (2026-11-12) and the licence
`<https://creativecommons.org/licenses/by/4.0/>`. Release v1 is version
1.0.0 of the ontology and of the build. Every knowledge-graph build
records the same version and its validity date (`vlo:softwareVersion`
and `vlo:validityAsOf` on the build activity node). Proposed release
policy for the repository, semantic versioning: a patch release changes
labels, definitions or data only; a minor release adds classes or
properties; a major release renames or removes terms or changes the IRI
scheme. Each release keeps its version IRI, so data can state which
version it conforms to.

= 5. Building the knowledge graph
<building-the-knowledge-graph>
== 5.1 Prerequisites
<prerequisites>
The build runs on one machine with the processed corpus of the vn-legal
project (root `R`) and the pinned source snapshots in its Hugging Face
cache. It needs a Python environment with duckdb 2.0.0, igraph 1.0.0,
owlrl 7.6.2, polars 2.1.0, pyarrow 26.0.1, pylode 3.6.1, pyoxigraph
0.5.13, pyshacl 0.40.2, rdflib 7.6.0; these are the versions of the
reference build of VLOnto v1, which ran with Python 3.11.18 on macOS,
arm64 (`scripts/build_pdf.sh` looks for the environment at
`$V/envs/kg`). Paths default to the values in `vlonto/vlonto/config.py`
and can be overridden with the environment variables `R` (vn-legal
root), `V` (VLOnto root), `VLONTO_REPO` and `VLONTO_BUILD`.

== 5.2 Commands
<commands>
```bash
export R=/path/to/vnlegal V=/path/to/vlonto
cd $V/repo/vlonto
$V/envs/kg/bin/python -m vlonto.cli all            # every step below, in order
$V/envs/kg/bin/python -m vlonto.cli build          # or one step at a time
$V/envs/kg/bin/python -m vlonto.cli report         # regenerate kg_report.md only
```

Options: `--workers N` (worker processes of the RDF export),
`--core-max-rank N` (legal-force ranks in the browser subset),
`--no-article-text` (skip the local-only article text table) and
`--with-article-text` (copy article text into the articles table; a
licence decision before the tables are shared, Appendix~D). `layout`
recomputes only the 3D layout of the legal network. `--with-courts` (or
`VLONTO_INCLUDE_COURTS=1`) also reads the court datasets; it is for the
work on v2 and is not part of VLOnto v1.

== 5.3 Steps and expected output
<steps-and-expected-output>
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (14.78%, 33.91%, 39.13%, 12.17%),
    align: (left,left,left,right,),
    table.header([Step], [Writes], [Expected result], [Wall time],),
    table.hline(),
    [`build`], [`build/kg/*.parquet`, `build/kg_local/`], [40,816
    documents, 436,309 articles, 15,035 change events, 556,287
    edges], [33 s],
    [`export`], [`build/rdf/vlonto-kg.nt.gz`], [6,963,753 triples, 48.2
    MB], [7 s],
    [`core`], [`build/rdf/vlonto-core.ttl`], [49,846 triples, 1,781
    documents], [1.0 s],
    [`validate`], [`build/reports/validation.json`,
    `build/oxigraph/`], [32 integrity checks, 6,963,753 triples
    loaded], [36 s],
    [`site`], [`build/site_data/*.json`, `js/*.js`], [15 bundles and
    twins, all within 20 MB], [-],
    [`check-ontology`], [`build/reports/ontology_check.json`,
    `ontology/vlonto.html`], [131 terms checked, 971 documentation
    links], [-],
    [`report`], [`build/reports/kg_report.md`, `checks.json`], [20 of 20
    checks pass], [-],
  )]
  , kind: table
  )

]
Wall times are those of the reference build (macOS, arm64, 2026-11-12);
`-` means the step reports no time. The step reports are JSON files in
`build/reports/`\; `kg_report.md` collects them. A rebuild from the same
source revisions must reproduce every count in this playbook; the
reconciliation check (section~6.2) compares the main counts with the
data report of the vn-legal project automatically.

== 5.4 Node and edge tables
<node-and-edge-tables>
#figure(
  align(center)[#table(
    columns: (26.72%, 12.07%, 61.21%),
    align: (left,right,left,),
    table.header([Table], [Rows], [Content],),
    table.hline(),
    [`documents`], [40,816], [Legal documents (40,816 in-scope normative
    documents from vbpl, after cleaning).],
    [`articles`], [436,309], [Articles (Điều): one node per main-body or
    appendix article; parts of split articles joined. No text
    (licence).],
    [`structure`], [73,925], [Appendices, parts, chapters and sections
    of documents.],
    [`provisions_ref`], [48,031], [Clauses (khoản) and points (điểm)
    created because an edge refers to them.],
    [`issuers`], [57], [Issuing bodies identified by the symbol of the
    document number (curated table; unknown symbols get no node).],
    [`areas`], [51], [Legal areas (SKOS concepts) from vbpl/hdpl (27)
    and tnpl.],
    [`doc_types`], [10], [Document types (concepts of the ontology).],
    [`legal_force_ranks`], [6], [Legal-force ranks (concepts of the
    ontology).],
    [`changes`], [15,035], [Legal change events (validity relations v7),
    one per relation.],
    [`edges_change`], [15,035], [Shortcut edges acting document -\>
    affected document (one per change event).],
    [`edges_legal_basis`], [99,038], [Legal basis: citing document -\>
    basis document.],
    [`edges_citation`], [268,563], [vbpl citations (external,
    external\_mention, parent\_law, parent\_law\_mention) resolved to
    documents/articles.],
    [`qas`], [109,543], [Legal Q&As from hdpl: metadata only (no
    question or answer text).],
    [`edges_qa_article`], [34,869], [Q&A answer -\> article (+clause,
    point) from the gold resolver (gold\_all.parquet).],
    [`edges_qa_document`], [119,683], [Q&A answer -\> document cited by
    number.],
    [`terms`], [16,701], [Legal terms from tnpl (names only, no
    definitions).],
    [`edges_term_related`], [17,615], [Related terms.],
    [`news`], [681], [Legal news articles from htpl (no title or
    text).],
    [`edges_news_document`], [1,484], [News article -\> mentioned
    document.],
    [`news_categories`], [7], [News categories.],
    [`sources`], [4], [Source datasets of this build with revision,
    licence and policy (release v1: the four thuvienphapluat.vn
    datasets).],
  )]
  , kind: table
  )

Every edge table keeps a `method` column (how the edge was found:
`docnum-key`, `law-name-year`, `preamble-citation`, `answer-text-name`
and so on) and, where the source has one, the raw reference as written,
so that any edge can be traced and re-judged. The columns of every table
are listed in Appendix~C.

= 6. Validation
<validation>
== 6.1 The 20 build checks
<the-20-build-checks>
#block(sticky: true, width: 100%)[
`vlonto.cli validate`, `check-ontology` and `report` run 20 checks; 20
pass in the build of 2026-11-12.

]
#figure(
  align(center)[#table(
    columns: (5.17%, 37.93%, 7.76%, 49.14%),
    align: (right,left,left,left,),
    table.header([\#], [Check], [Result], [Evidence (as recorded by the
      build)],),
    table.hline(),
    [1], [Ontology completeness (en+vi labels, en definition, module for
    every VLOnto
    term)], [pass], [`0 problems; terms by kind {'class': 47, 'object_property': 46, 'datatype_property': 35, 'annotation_property': 3}`],
    [2], [Ontology has no dangling references], [pass], [`dangling=[]`],
    [3], [Ontology release metadata (owl:versionInfo 1.0.0,
    owl:versionIRI https:/\/tmquan.github.io/VLOnto/ontology/1.0.0,
    dcterms:modified = build date
    2026-11-12)], [pass], [`versionInfo 1.0.0, versionIRI https://tmquan.github.io/VLOnto/ontology/1.0.0, priorVersion https://tmquan.github.io/VLOnto/ontology/0.1.0, modified 2026-11-12; dcterms:source 4 datasets (match: True); judiciary terms with a v2 scope note 26/26`],
    [4], [ELI terms used by VLOnto exist in the ELI
    ontology], [pass], [`124 ELI terms defined; missing []`],
    [5], [OWL-RL on fixtures (expected inferences present, planted
    disjointness and functional clash
    detected)], [pass], [`27 expected inferences, missing []; negative: 2 inconsistencies`],
    [6], [SHACL on fixtures (positive conforms, all planted errors
    reported)], [pass], [`positive results 0; planted found ['bad-article:inDocument', 'bad-article:provisionNumber', 'bad-change:actingDocument', 'bad-change:evidenceText', 'bad-doc:documentType', 'bad-term:definition'], missed []`],
    [7], [pyLODE documentation renders with no broken internal
    links], [pass], [`680473 bytes, 971 internal links, broken 0`],
    [8], [Referential integrity of every parquet edge and foreign
    key], [pass], [`32 checks, orphans 0`],
    [9], [Reconciliation with the processed-corpus data
    report], [pass], [`21/21 items match`],
    [10], [Full RDF dump parses strictly and loads into
    Oxigraph], [pass], [`6,963,753 N-Triples lines written, 6,963,753 distinct triples loaded`],
    [11], [Per-class instance counts identical in parquet and
    RDF], [pass], [`20/20 classes match`],
    [12], [Every VLOnto instance IRI used as an object is typed in the
    dump], [pass], [`312,524 object IRIs, 0 untyped`],
    [13], [SHACL on a stratified sample of the KG (up to 150 nodes per
    class or
    kind)], [pass], [`3,066 nodes / 42,857 triples; violations 0`],
    [14], [OWL-RL closure of the KG sample is
    consistent], [pass], [`25,681 -> 91,886 triples; inconsistencies 0, sameAs between distinct nodes 0`],
    [15], [Release v1 scope: no court data (no court table, no
    court/decision/precedent node, no court-source statement); sources =
    the 4 thuvienphapluat
    datasets], [pass], [`court tables present []; typed court nodes in RDF {'Court': 0, 'CourtDecision': 0, 'Judgment': 0, 'CourtRuling': 0, 'Precedent': 0, 'JudicialDocument': 0}; dump lines mentioning court IRIs or court sources 0; source datasets ['thuvienphapluat-vn-vbpl', 'thuvienphapluat-vn-hdpl', 'thuvienphapluat-vn-tnpl', 'thuvienphapluat-vn-htpl']`],
    [16], [Spot checks: 10 random edges per edge type read and judged
    (criterion: at least 8 correct per 10 for every edge
    type)], [pass], [`127/130 judged correct, 1 judged wrong, 2 not verifiable from the record; edge types below the criterion: []`],
    [17], [Site bundles within 20 MB, each with a file:/\/ .js
    twin], [pass], [`15 files, 9 js twins, over 20 MB: []`],
    [18], [0 non-NFC strings in every published output (Unicode
    NFC)], [pass], [`0 non-NFC strings in 47 files {'kg': 21, 'rdf': 2, 'site_data': 16, 'ontology': 4, 'docs': 4}; kg_report.md and checks.json are written in NFC by the report step`],
    [19], [No link to a VLOnto Hugging Face dataset or Space in any
    published output (release = GitHub repository +
    website)], [pass], [`49 files scanned; forbidden hits: links to a Hugging Face VLOnto dataset 0, links to a Space 0, Space path segments 0, wording that calls a VLOnto document a card 0; kept: 44 links to the tmquan source datasets on Hugging Face (4 sources of this build, 2 planned for v2), 7 to the GitHub repository, 7 to the paper (arXiv:2611.11426)`],
    [20], [No absolute build-machine path or host name in any published
    output (paths relative to the VLOnto
    root)], [pass], [`49 files scanned; build-node home paths 0, build-node host names 0, macOS home paths 0`],
  )]
  , kind: table
  )

== 6.2 Reconciliation with the processed corpus
<reconciliation-with-the-processed-corpus>
#block(sticky: true, width: 100%)[
The build counts are compared item by item with the data report of the
vn-legal project; all 21 of 21 items match:

]
#figure(
  align(center)[#table(
    columns: (51.72%, 17.24%, 18.97%, 12.07%),
    align: (left,right,right,left,),
    table.header([Item], [Data report], [Knowledge graph], [Match],),
    table.hline(),
    [documents], [40,816], [40,816], [yes],
    [change relations (total)], [15,035], [15,035], [yes],
    [change relations: replaced], [6,321], [6,321], [yes],
    [change relations: amended], [4,678], [4,678], [yes],
    [change relations: partially\_repealed], [1,854], [1,854], [yes],
    [change relations: repealed], [1,674], [1,674], [yes],
    [change relations: partially\_expired], [508], [508], [yes],
    [validity: unknown], [28,660], [28,660], [yes],
    [validity: superseded], [5,167], [5,167], [yes],
    [validity: presumed\_in\_force\_amended], [2,722], [2,722], [yes],
    [validity: expired], [2,125], [2,125], [yes],
    [validity: in\_force], [1,511], [1,511], [yes],
    [validity: in\_force\_amended], [545], [545], [yes],
    [validity: not\_applicable], [47], [47], [yes],
    [validity: not\_yet\_effective], [39], [39], [yes],
    [main-body articles], [425,892], [425,892], [yes],
    [documents with main-body articles], [32,902], [32,902], [yes],
    [Q&As with gold article labels], [22,523], [22,523], [yes],
    [hdpl Q&As], [109,543], [109,543], [yes],
    [tnpl terms (rows minus not\_found
    placeholders)], [16,701], [16,701], [yes],
    [htpl news], [681], [681], [yes],
  )]
  , kind: table
  )

== 6.3 Integrity, RDF and SHACL/OWL-RL
<integrity-rdf-and-shaclowl-rl>
- #strong[Referential integrity.] 32 foreign-key checks over every edge
  table; 0 orphans.
- #strong[RDF.] The full dump parses strictly and loads into Oxigraph
  (6,963,753 distinct triples); per-class instance counts are identical
  in parquet and RDF for 20 classes; all 312,524 instance IRIs used as
  objects are typed (0 untyped).
- #strong[SHACL.] `ontology/vlonto-shapes.ttl` has 18 node shapes with
  90 property shapes. On fixtures, the positive file conforms and all 6
  planted errors are reported. On a sample of the graph stratified by
  class and kind (3,066 nodes, 42,857 triples) there are 0 violations.
- #strong[OWL-RL.] On fixtures, 27 expected inferences are all present
  and the planted disjointness and functional-property clashes are
  detected (2 inconsistencies). The closure of the graph sample grows
  from 25,681 to 91,886 triples with 0 inconsistencies and 0
  `owl:sameAs` links between distinct nodes.
- #strong[Ontology hygiene.] No dangling references; all 18 ELI terms
  used exist in the ELI ontology; the pyLODE documentation has 971
  internal links, 0 broken.

== 6.4 Spot checks of extracted edges
<spot-checks-of-extracted-edges>
#block(sticky: true, width: 100%)[
For each edge type and resolution method, edges were drawn at random
from the final build and judged by reading the numbers, titles, dates
and the raw reference stored with the edge: 127 of 130 judged correct, 1
wrong and 2 not verifiable from the record; every edge type met the
criterion of the spot-check entry in section~6.1. For VLOnto v1 the
samples are the edges judged for the previous release, except the change
events, which were drawn and judged again
(`docs/spot_check_review.json`).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (44.35%, 13.91%, 13.91%, 13.04%, 14.78%),
    align: (left,right,right,right,right,),
    table.header([Edge type], [Checked], [Correct], [Wrong], [Not
      verifiable],),
    table.hline(),
    [`changes`], [10], [10], [0], [0],
    [`legal_basis:parent-acts`], [10], [9], [1], [0],
    [`legal_basis:preamble-citation`], [10], [9], [0], [1],
    [`legal_basis:constitution-preamble`], [10], [10], [0], [0],
    [`citation:external`], [10], [10], [0], [0],
    [`citation:external_mention`], [10], [10], [0], [0],
    [`citation:parent_law`], [10], [10], [0], [0],
    [`citation:parent_law_mention`], [10], [10], [0], [0],
    [`document_issuer`], [10], [10], [0], [0],
    [`qa_article`], [10], [9], [0], [1],
    [`qa_document`], [10], [10], [0], [0],
    [`term_related`], [10], [10], [0], [0],
    [`news_document`], [10], [10], [0], [0],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
The notes on the edges that were not judged correct:

]
- `legal_basis:parent-acts`: \#7: the decree on administrative penalties
  for cybersecurity and personal data lists the Customs Law 54/2014/QH13
  among its basis acts in the source metadata (source error carried
  over).
- `legal_basis:preamble-citation`: \#9: Circular 18/2000/TT-BLĐTBXH
  mentions Circular 13/2000/TT-BLĐTBXH in its preamble; whether it is a
  legal basis or a cross-reference cannot be told from the record.
- `qa_article`: \#1: 'Điều~45 Khoản 3 Luật Đầu tư' is linked to the PPP
  Investment Law 64/2020/QH14 (gold label of the evaluation set; the
  truncated reference string cannot settle it).

A sample of 10 gives only coarse precision: with 10 of 10 correct, the
two-sided 95% lower confidence bound is about 69%. The samples catch
systematic errors (several rules were tightened after earlier samples of
the same day), not rare ones.

== 6.5 Precision of the validity relations
<precision-of-the-validity-relations>
#block(sticky: true, width: 100%)[
The 15,035 change events come from the validity map of the vn-legal
project (rules v7). On a fresh sample of 30 relations, judged from the
evidence sentence, 29 were correct (replaced or repealed 15/15, amended
10/10, partial 4/5; Wilson 95% interval 0.833 to 0.994), and all 3 known
replacements were found:

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (33.91%, 33.04%, 33.04%),
    align: (left,left,left,),
    table.header([Old act], [Replaced by], [From],),
    table.hline(),
    [10/2012/QH13], [45/2019/QH14], [2021-01-01],
    [45/2013/QH13], [31/2024/QH15], [2024-08-01],
    [58/2014/QH13], [41/2024/QH15], [2025-07-01],
  )]
  , kind: table
  )

]
These judgements were made by the build agent from the evidence
sentences, not by a lawyer.

#figure([#vlo-figure("changes")],
  caption: [
    Change events per year of their effective date, by kind, 1995 to
    2027: 14,903 of the 15,035 events; 99 earlier events and 33 events
    without an effective date are not shown.
  ]
)

== 6.6 Known limits of the validation
<known-limits-of-the-validation>
#figure([#vlo-figure("validity")],
  caption: [
    Validity classes of the 40,816 documents as of 2026-11-08 (validity
    rules v7).
  ]
)

- Validity is unknown for 28,660 documents (70.2%): the source has no
  status for them and no relation names them. Unknown is not "in force".
- Precision figures rest on small samples; recall is not measured for
  most edge types.
- SHACL and OWL-RL run on samples and fixtures; the full graph is
  validated by the integrity and RDF checks.

The complete list of limitations is in section~12.

= 7. Recipes
<recipes>
Each recipe answers one question twice: in SQL over the parquet tables
(DuckDB) and in SPARQL over the RDF. Every query below was run against
the build of 2026-11-12; the outputs are printed as they were returned
(long results are cut to their first rows). The SQL runs in the folder
that contains `kg/`\; the SPARQL runs on the full dump loaded as in
section~2.6, and the row count on the browser subset is given where the
subset can answer.

== 7.1 What replaced an act?
<what-replaced-an-act>
The Labour Code 10/2012/QH13 was replaced; the change event keeps the
operative sentence of the new code as evidence.

#block(sticky: true, width: 100%)[
SQL (`playbook/recipes/r1_replaced_by.sql`):

]
```sql
-- What replaced (or repealed) the Labour Code 10/2012/QH13?
SELECT n.doc_number AS new_number,
       n.title_vi   AS new_title,
       c.kind,
       c.effective_date
FROM 'kg/changes.parquet'   AS c
JOIN 'kg/documents.parquet' AS o ON o.doc_id = c.affected_doc_id
JOIN 'kg/documents.parquet' AS n ON n.doc_id = c.acting_doc_id
WHERE o.doc_number = '10/2012/QH13'
  AND c.kind IN ('replaced', 'repealed')
ORDER BY c.effective_date, new_number;
```

#block(sticky: true, width: 100%)[
Output (1 row):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (22.22%, 37.61%, 16.24%, 23.93%),
    align: (left,left,left,left,),
    table.header([new\_number], [new\_title], [kind], [effective\_date],),
    table.hline(),
    [45/2019/QH14], [Bộ luật Lao động], [replaced], [2021-01-01],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
SPARQL (`playbook/recipes/r1_replaced_by.rq`):

]
```sparql
PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
# What replaced the Labour Code 10/2012/QH13?
SELECT ?number ?date ?evidence WHERE {
  ?old vlo:documentNumber "10/2012/QH13" .
  ?change vlo:affectedDocument ?old ;
          vlo:changeKind vlo:change-replaced ;
          vlo:actingDocument ?new ;
          vlo:evidenceText ?evidence .
  OPTIONAL { ?change vlo:changeEffectiveDate ?date }
  ?new vlo:documentNumber ?number .
}
ORDER BY ?date ?number
```

#block(sticky: true, width: 100%)[
Output on the full dump (1 row; on the browser subset: 1 row):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (17.24%, 13.79%, 68.97%),
    align: (left,left,left,),
    table.header([number], [date], [evidence],),
    table.hline(),
    [45/2019/QH14], [2021-01-01], [Bộ luật Lao động số 10/2012/QH13 hết
    hiệu lực thi hành kể từ ngày Bộ luật này có hiệu lực.],
  )]
  , kind: table
  )

]
Use the kinds `replaced` and `repealed` for "no longer in force because
of X", and `amended`, `partially_repealed` and `partially_expired` for
"still in force, but changed" (recipe~7.2). The validity class of the
affected document (`documents.validity`) combines these events with the
status in the source.

== 7.2 Amendment history
<amendment-history>
#block(sticky: true, width: 100%)[
All change events that affect the Land Law 31/2024/QH15, oldest first:

]
#block(sticky: true, width: 100%)[
SQL (`playbook/recipes/r2_amendment_history.sql`):

]
```sql
-- Amendment history of the Land Law 31/2024/QH15: every change event
-- whose affected document is the law, oldest first.
SELECT c.effective_date,
       a.doc_number AS acting_number,
       a.doc_type_vi AS acting_type,
       c.kind
FROM 'kg/changes.parquet'   AS c
JOIN 'kg/documents.parquet' AS d ON d.doc_id = c.affected_doc_id
JOIN 'kg/documents.parquet' AS a ON a.doc_id = c.acting_doc_id
WHERE d.doc_number = '31/2024/QH15'
ORDER BY c.effective_date NULLS LAST, acting_number, c.kind;
```

#block(sticky: true, width: 100%)[
Output (8 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (22.22%, 25.64%, 22.22%, 29.91%),
    align: (left,left,left,left,),
    table.header([effective\_date], [acting\_number], [acting\_type], [kind],),
    table.hline(),
    [2024-08-01], [43/2024/QH15], [Luật], [amended],
    [2025-01-01], [58/2024/QH15], [Luật], [amended],
    [2025-07-01], [47/2024/QH15], [Luật], [amended],
    [2025-07-01], [84/2025/QH15], [Luật], [partially\_repealed],
    [2026-01-01], [146/2025/QH15], [Luật], [partially\_repealed],
    [2026-01-01], [147/2025/QH15], [Luật], [amended],
    [2026-01-01], [95/2025/QH15], [Luật], [amended],
    [2026-07-01], [130/2025/QH15], [Luật], [amended],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
SPARQL (`playbook/recipes/r2_amendment_history.rq`):

]
```sparql
PREFIX vlo:  <https://tmquan.github.io/VLOnto/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
# Amendment history of the Land Law 31/2024/QH15
SELECT ?date ?number ?kind WHERE {
  ?law vlo:documentNumber "31/2024/QH15" .
  ?change vlo:affectedDocument ?law ;
          vlo:actingDocument ?by ;
          vlo:changeKind ?k .
  ?k skos:prefLabel ?kind FILTER (lang(?kind) = "en")
  OPTIONAL { ?change vlo:changeEffectiveDate ?date }
  ?by vlo:documentNumber ?number .
}
ORDER BY ?date ?number ?kind
```

#block(sticky: true, width: 100%)[
Output on the full dump (8 rows; on the browser subset: 8 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (30.17%, 33.62%, 36.21%),
    align: (left,left,left,),
    table.header([date], [number], [kind],),
    table.hline(),
    [2024-08-01], [43/2024/QH15], [amended],
    [2025-01-01], [58/2024/QH15], [amended],
    [2025-07-01], [47/2024/QH15], [amended],
    [2025-07-01], [84/2025/QH15], [partially repealed],
    [2026-01-01], [146/2025/QH15], [partially repealed],
    [2026-01-01], [147/2025/QH15], [amended],
    [2026-01-01], [95/2025/QH15], [amended],
    [2026-07-01], [130/2025/QH15], [amended],
  )]
  , kind: table
  )

]
== 7.3 Legal-basis chain
<legal-basis-chain>
A circular rests on decrees and laws, which rest on the Constitution.
The SQL follows `edges_legal_basis` up to three steps and keeps the
shortest depth of each document; the SPARQL property path
`vlo:legalBasis+` follows the chain to any depth.

#block(sticky: true, width: 100%)[
SQL (`playbook/recipes/r3_legal_basis_chain.sql`):

]
```sql
-- Legal-basis chain of the enterprise accounting circular 99/2025/TT-BTC:
-- follow vlo:legalBasis edges up to three steps, keep the shortest depth.
WITH RECURSIVE chain(doc_id, depth, path) AS (
    SELECT doc_id, 0, [doc_id]
    FROM 'kg/documents.parquet'
    WHERE doc_number = '99/2025/TT-BTC'
  UNION ALL
    SELECT e.dst_doc_id, c.depth + 1, list_append(c.path, e.dst_doc_id)
    FROM chain AS c
    JOIN 'kg/edges_legal_basis.parquet' AS e ON e.src_doc_id = c.doc_id
    WHERE c.depth < 3 AND NOT list_contains(c.path, e.dst_doc_id)
)
SELECT min(c.depth) AS depth,
       coalesce(d.doc_number, '-') AS number,
       d.doc_type_vi AS type,
       d.title_vi AS title
FROM chain AS c
JOIN 'kg/documents.parquet' AS d USING (doc_id)
WHERE c.depth > 0
GROUP BY d.doc_number, d.doc_type_vi, d.title_vi
ORDER BY depth, number, title;
```

#block(sticky: true, width: 100%)[
Output (first 12 of 16 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (8.7%, 19.13%, 13.91%, 58.26%),
    align: (left,left,left,left,),
    table.header([depth], [number], [type], [title],),
    table.hline(),
    [1], [04/2007/QH12], [Luật], [Luật Thuế thu nhập cá nhân],
    [1], [15/2012/QH13], [Luật], [Luật Xử lý vi phạm hành chính],
    [1], [166/2025/NĐ-CP], [Nghị định], [Nghị định 166/2025/NĐ-CP sửa
    đổi, bổ sung một số điều của nghị định số 29/2025/nđ-cp ngày 24
    tháng 02 năm 2025 của Chính phủ quy định chức năng, nhiệm vụ, quyền
    hạn và cơ cấu tổ chức của bộ tài chính],
    [1], [22/2012/QH13], [Luật], [Luật Dự trữ quốc gia],
    [1], [29/2025/NĐ-CP], [Nghị định], [Nghị định 29/2025/NĐ-CP quy định
    chức năng, nhiệm vụ, quyền hạn và cơ cấu tổ chức của bộ tài chính],
    [1], [38/2019/QH14], [Luật], [Luật Quản lý thuế],
    [1], [54/2019/QH14], [Luật], [Luật Chứng khoán],
    [1], [67/2011/QH12], [Luật], [Luật Kiểm toán độc lập],
    [1], [88/2015/QH13], [Luật], [Luật Kế toán],
    [1], [89/2025/QH15], [Luật], [Luật Ngân sách Nhà nước],
    [2], [-], [Hiến pháp], [Hiến pháp Nước cộng hoà chủ nghiã xã hội
    Việt Nam năm 1992],
    [2], [-], [Hiến pháp], [Hiến pháp Nước cộng hòa xã hội chủ nghĩa
    Việt Nam năm 2013],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
SPARQL (`playbook/recipes/r3_legal_basis_chain.rq`):

]
```sparql
PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
# Every document reachable from 99/2025/TT-BTC by vlo:legalBasis (any depth)
SELECT DISTINCT ?number ?title WHERE {
  ?doc vlo:documentNumber "99/2025/TT-BTC" ;
       vlo:legalBasis+ ?basis .
  ?basis vlo:title ?title .
  OPTIONAL { ?basis vlo:documentNumber ?number }
}
ORDER BY ?number ?title
```

#block(sticky: true, width: 100%)[
Output on the full dump (first 8 of 16 rows; on the browser subset: 0
rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (22.41%, 77.59%),
    align: (left,left,),
    table.header([number], [title],),
    table.hline(),
    [-], [Hiến pháp Nước cộng hoà chủ nghiã xã hội Việt Nam năm 1992],
    [-], [Hiến pháp Nước cộng hòa xã hội chủ nghĩa Việt Nam năm 2013],
    [04/2007/QH12], [Luật Thuế thu nhập cá nhân],
    [15/2012/QH13], [Luật Xử lý vi phạm hành chính],
    [166/2025/NĐ-CP], [Nghị định 166/2025/NĐ-CP sửa đổi, bổ sung một số
    điều của nghị định số 29/2025/nđ-cp ngày 24 tháng 02 năm 2025 của
    Chính phủ quy định chức năng, nhiệm vụ, quyền hạn và cơ cấu tổ chức
    của bộ tài chính],
    [194/2025/QH15], [Nghị quyết 194/2025/QH15 về việc sửa đổi, bổ sung
    một số điều của hiến pháp năm 2013],
    [203/2025/QH15], [Nghị quyết 203/2025/QH15 sửa đổi, bổ sung một số
    điều của hiến pháp nước cộng hòa xã hội chủ nghĩa Việt Nam],
    [22/2012/QH13], [Luật Dự trữ quốc gia],
  )]
  , kind: table
  )

]
The browser subset returns no row here because a circular is outside it
(section~2.6). Amending resolutions of the Constitution appear because
the laws in the chain cite them as their basis.

== 7.4 Articles most cited in Q&A answers
<articles-most-cited-in-qa-answers>
#block(sticky: true, width: 100%)[
Q&A article edges link a published legal Q&A to the article, clause or
point that its answer cites (the evaluation labels of the vn-legal
project, section~7.5). Counting Q&As per article:

]
#block(sticky: true, width: 100%)[
SQL (`playbook/recipes/r4_qa_articles.sql`):

]
```sql
-- Articles cited by the largest number of published Q&A answers
-- (a Q&A whose answer cites several clauses of one article counts once).
SELECT d.doc_number,
       a.article_no,
       a.heading,
       count(DISTINCT e.qa_id) AS qas
FROM 'kg/edges_qa_article.parquet' AS e
JOIN 'kg/articles.parquet'  AS a ON a.article_id = e.dst_article_id
JOIN 'kg/documents.parquet' AS d ON d.doc_id = a.doc_id
GROUP BY a.article_id, d.doc_number, a.article_no, a.heading
ORDER BY qas DESC, d.doc_number, a.article_no
LIMIT 10;
```

#block(sticky: true, width: 100%)[
Output (10 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (17.09%, 11.11%, 53.85%, 17.95%),
    align: (left,left,left,right,),
    table.header([doc\_number], [article\_no], [heading], [qas],),
    table.hline(),
    [45/2019/QH14], [111], [Nghỉ hằng tuần], [166],
    [12/2022/NĐ-CP], [46], [Vi phạm của người lao động Việt Nam đi làm
    việc ở nước ngoài và một số đối tượng liên quan khác], [165],
    [45/2019/QH14], [112], [Nghỉ lễ, tết], [161],
    [45/2019/QH14], [169], [Tuổi nghỉ hưu], [155],
    [04/2007/QH12], [19], [-], [139],
    [65/2013/NĐ-CP], [3], [Thu nhập chịu thuế], [130],
    [38/2019/QH14], [44], [Thời hạn nộp hồ sơ khai thuế], [114],
    [67/2025/QH15], [9], [Các khoản chi được trừ và không được trừ khi
    xác định thu nhập chịu thuế], [113],
    [48/2024/QH15], [14], [Khấu trừ thuế giá trị gia tăng đầu
    vào], [109],
    [22/2021/TT-BGDĐT], [14], [-], [92],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
SPARQL (`playbook/recipes/r4_qa_articles.rq`):

]
```sparql
PREFIX vlo:  <https://tmquan.github.io/VLOnto/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
# Articles cited by the most Q&A answers; a clause or point target is
# rolled up to its article with vlo:isPartOf*.
SELECT ?label (COUNT(DISTINCT ?question) AS ?qas) WHERE {
  ?question vlo:hasAnswer ?answer .
  ?answer vlo:answerCitesProvision ?target .
  ?target vlo:isPartOf* ?article .
  ?article a vlo:Article ;
           rdfs:label ?label .
}
GROUP BY ?article ?label
ORDER BY DESC(?qas) ?label
LIMIT 10
```

#block(sticky: true, width: 100%)[
Output on the full dump (10 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (69.83%, 30.17%),
    align: (left,right,),
    table.header([label], [qas],),
    table.hline(),
    [Điều~111, 45/2019/QH14], [166],
    [Điều~46, 12/2022/NĐ-CP], [165],
    [Điều~112, 45/2019/QH14], [161],
    [Điều~169, 45/2019/QH14], [155],
    [Điều~19, 04/2007/QH12], [139],
    [Điều~3, 65/2013/NĐ-CP], [130],
    [Điều~44, 38/2019/QH14], [114],
    [Điều~9, 67/2025/QH15], [113],
    [Điều~14, 48/2024/QH15], [109],
    [Điều~14, 22/2021/TT-BGDĐT], [92],
  )]
  , kind: table
  )

]
The most cited article is Article~111 of 45/2019/QH14 (Bộ luật Lao
động), #emph[Nghỉ hằng tuần]. The SQL aggregates all 34,869 Q&A article
edges; the SPARQL query rolls clause and point targets up to their
article with `vlo:isPartOf*`, and both give the same ranking. These are
counts over the whole corpus of Q&As; the dashboard shows the same
ranking, and the question traces page (section~9) ranks the articles
within each legal area.

== 7.5 Q&As that cite an article
<qas-that-cite-an-article>
#block(sticky: true, width: 100%)[
The legal Q&A edges come from the evaluation labels of the vn-legal
project. Q&As whose answer cites Article~35 of the Labour Code
45/2019/QH14 (the employee's right to terminate a labour contract):

]
#block(sticky: true, width: 100%)[
SQL (`playbook/recipes/r5_qa_citing_article.sql`):

]
```sql
-- Legal Q&As whose answer cites Article 35 of the Labour Code 45/2019/QH14
-- (newest first; the text of the Q&A is at the source URL in qas.url).
SELECT q.qa_id,
       q.published_date,
       q.category,
       coalesce(e.clause, '-') AS clause,
       coalesce(e.point, '-') AS point
FROM 'kg/edges_qa_article.parquet' AS e
JOIN 'kg/qas.parquet' AS q USING (qa_id)
WHERE e.dst_article_id = (
    SELECT a.article_id
    FROM 'kg/articles.parquet' AS a
    JOIN 'kg/documents.parquet' AS d USING (doc_id)
    WHERE d.doc_number = '45/2019/QH14'
      AND a.article_no = '35' AND a.segment = 'main')
ORDER BY q.published_date DESC, q.qa_id, clause, point;
```

#block(sticky: true, width: 100%)[
Output (12 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (19.13%, 20.87%, 30.43%, 14.78%, 14.78%),
    align: (left,left,left,left,left,),
    table.header([qa\_id], [published\_date], [category], [clause], [point],),
    table.hline(),
    [138067111], [2025-11-11], [lao-dong-tien-luong], [-], [-],
    [138069781], [2025-11-10], [lao-dong-tien-luong], [-], [-],
    [138051569], [2025-05-27], [lao-dong-tien-luong], [-], [-],
    [138008514], [2024-03-14], [lao-dong-tien-luong], [1], [d],
    [138016134], [2024-01-01], [lao-dong-tien-luong], [1], [d],
    [138016080], [2023-12-23], [lao-dong-tien-luong], [1], [d],
    [138012879], [2023-11-27], [lao-dong-tien-luong], [1], [d],
    [138011230], [2023-10-05], [lao-dong-tien-luong], [1], [d],
    [138010737], [2023-09-25], [lao-dong-tien-luong], [1], [d],
    [138009959], [2023-09-09], [lao-dong-tien-luong], [-], [-],
    [138003325], [2023-04-18], [lao-dong-tien-luong], [1], [d],
    [138001400], [2023-03-14], [lao-dong-tien-luong], [1], [d],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
SPARQL (`playbook/recipes/r5_qa_citing_article.rq`):

]
```sparql
PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
# Q&As whose answer cites Article 35 of 45/2019/QH14 or one of its
# clauses or points (newest first)
SELECT DISTINCT ?id ?date WHERE {
  BIND (<https://tmquan.github.io/VLOnto/id/document/333670/dieu-35> AS ?art)
  ?target vlo:isPartOf* ?art .
  ?answer vlo:answerCitesProvision ?target .
  ?question vlo:hasAnswer ?answer ;
            vlo:sourceId ?id .
  OPTIONAL { ?question vlo:publishedDate ?date }
}
ORDER BY DESC(?date) ?id
```

#block(sticky: true, width: 100%)[
Output on the full dump (first 6 of 12 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (50%, 50%),
    align: (left,left,),
    table.header([id], [date],),
    table.hline(),
    [138067111], [2025-11-11],
    [138069781], [2025-11-10],
    [138051569], [2025-05-27],
    [138008514], [2024-03-14],
    [138016134], [2024-01-01],
    [138016080], [2023-12-23],
  )]
  , kind: table
  )

]
Only identifiers, dates and categories are published for Q&As; open
`qas.url` to read a question and its answer at the source.

== 7.6 Terms of a legal area
<terms-of-a-legal-area>
#block(sticky: true, width: 100%)[
Legal terms (#emph[thuật ngữ]) carry their Vietnamese name and an
English label whose provenance is recorded (`mt`: machine translation;
`site`: given by the source):

]
#block(sticky: true, width: 100%)[
SQL (`playbook/recipes/r6_terms_of_area.sql`):

]
```sql
-- Legal terms of the area 'Labour and wages', with the provenance of
-- the English label (mt = machine translation, site = from the source).
SELECT t.label_vi,
       coalesce(t.label_en, '-') AS label_en,
       coalesce(t.label_en_source, '-') AS en_source
FROM 'kg/terms.parquet' AS t
JOIN 'kg/areas.parquet' AS a USING (area_id)
WHERE a.label_en = 'Labour and wages'
ORDER BY t.label_vi, t.term_id;
```

#block(sticky: true, width: 100%)[
Output (first 10 of 246 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (43.97%, 42.24%, 13.79%),
    align: (left,left,left,),
    table.header([label\_vi], [label\_en], [en\_source],),
    table.hline(),
    [An toàn (trong khai thác mỏ lộ thiên)], [Safety (in open-pit
    mining)], [mt],
    [An toàn lao động], [Occupational safety], [mt],
    [Biên giới khai trường (trong khai thác mỏ lộ thiên)], [Mine
    boundary (in open-pit mining)], [mt],
    [Biên giới mỏ lộ thiên], [Pit limits], [site],
    [Buồng máy (của thang máy)], [Machine room], [site],
    [Bãi thải (trong khai thác mỏ lộ thiên)], [Waste dump], [site],
    [Bên nước ngoài tiếp nhận lao động], [Foreign receiving
    party], [mt],
    [Bên thuê lại lao động], [Labour re-hiring party], [mt],
    [Bảo hiểm thất nghiệp], [Unemployment insurance], [mt],
    [Bệnh nghề nghiệp], [Occupational disease], [mt],
  )]
  , kind: table
  )

]
#block(sticky: true, width: 100%)[
SPARQL (`playbook/recipes/r6_terms_of_area.rq`):

]
```sparql
PREFIX vlo:  <https://tmquan.github.io/VLOnto/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
# Legal terms of the area labelled 'Labour and wages' (vi, en)
SELECT ?vi ?en WHERE {
  ?area skos:prefLabel "Labour and wages"@en .
  ?term a vlo:LegalTerm ;
        vlo:legalArea ?area ;
        skos:prefLabel ?vi FILTER (lang(?vi) = "vi")
  OPTIONAL { ?term skos:prefLabel ?en FILTER (lang(?en) = "en") }
}
ORDER BY ?vi ?en
```

#block(sticky: true, width: 100%)[
Output on the full dump (first 6 of 246 rows):

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (50%, 50%),
    align: (left,left,),
    table.header([vi], [en],),
    table.hline(),
    [An toàn (trong khai thác mỏ lộ thiên)], [Safety (in open-pit
    mining)],
    [An toàn lao động], [Occupational safety],
    [Biên giới khai trường (trong khai thác mỏ lộ thiên)], [Mine
    boundary (in open-pit mining)],
    [Biên giới mỏ lộ thiên], [Pit limits],
    [Buồng máy (của thang máy)], [Machine room],
    [Bãi thải (trong khai thác mỏ lộ thiên)], [Waste dump],
  )]
  , kind: table
  )

]
== 7.7 The playground examples
<the-playground-examples>
#block(sticky: true, width: 100%)[
The SPARQL playground of the website offers 10 bilingual example
queries, all run on the browser subset (49,846 triples) during the
build:

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (37.93%, 7.76%, 54.31%),
    align: (left,right,left,),
    table.header([Example], [Rows], [First result],),
    table.hline(),
    [What replaced the 2012 Labour Code?], [1], [vlid:document/333670 ·
    45/2019/QH14 · 2021-01-01 · Bộ luật Lao động số 10/2012/QH13 hết
    hiệu lực thi hành kể từ ngày Bộ …],
    [Laws in force by area], [27], [Administrative apparatus · 57],
    [Codes and their validity], [30], [Bộ luật 20/2000/QH10 ·
    20/2000/QH10 · unknown],
    [Most amended laws], [20], [Luật Đầu tư · 61/2020/QH14 · 7],
    [Legal basis of the 2024 Land Law], [1], [vlid:document/215627 ·
    Hiến pháp Nước cộng hòa xã hội chủ nghĩa Việt Nam năm 2013],
    [Laws that cite the Civil Code 2015], [22], [vlid:document/621341 ·
    Luật Công nghiệp công nghệ số],
    [Change events by kind], [5], [amended · 257],
    [Documents issued by the Standing Committee of the National
    Assembly], [2], [PL · 145],
    [Superclasses of a Law (ontology)], [4], [vlo:LegalDocument],
    [Source datasets and licences], [4], [tmquan/thuvienphapluat-vn-vbpl
    · 705ade585384108ded5fc30f40a06fe110bdff22 · cc-by-4.0],
  )]
  , kind: table
  )

]
= 8. Using VLOnto with the Vietnamese legal assistant agent
<using-vlonto-with-the-vietnamese-legal-assistant-agent>
== 8.1 Where VLOnto fits
<where-vlonto-fits>
The companion guide #emph[Building a Vietnamese Legal Assistant Agent
with NVIDIA NeMo Helix and Nemotron 3.5] builds an agent that answers
questions about Vietnamese law from retrieved articles. Its retrieval
service exposes `POST /search`, `GET /article/{doc_number}/{article_no}`
and `GET /validity/{doc_number}`, and an MCP server gives the agent
three tools on top of it: `search_law`, `get_article` and
`check_validity`. A deterministic audit checks every citation of an
answer against the service. The guide's measurements show why validity
has to come from data: with a stale decree as context, 0 of 30 model
answers named the decree that replaced it, and questions about
superseded law were flagged 3 of 3 times with the tools against 0 of 3
without them.

#block(sticky: true, width: 100%)[
The validity data of that service and the change events of VLOnto come
from the same validity map (rules v7). VLOnto adds three things the
agent can use:

]
+ #strong[Validity as published, typed data.] Each change event has its
  kind, effective date, evidence sentence and rule version, and the
  documents carry the validity class; the parquet files are enough, no
  GPU service is needed.
+ #strong[The citation network around an article.] What an article
  cites, which documents cite it, and the legal basis of its act.
+ #strong[Usage signals.] How many published Q&As cite an article, and
  which other articles they cite together with it.

== 8.2 Three knowledge-graph tools
<three-knowledge-graph-tools>
`playbook/examples/vlonto_tools.py` implements the three functions over
the parquet tables with DuckDB. Each returns a dictionary; `to_text()`
renders it as the short text a tool returns to the model.

```python
"""Knowledge-graph tools for the Vietnamese legal assistant agent.

Three read-only functions over the VLOnto parquet tables (DuckDB, in process):

  check_validity(doc_number)                  validity, replacing acts and
                                              amendments with their evidence
  expand_citations(doc_number, article_no)    what an article cites, what cites
                                              it, how many Q&A answers cite it
  related_provisions(doc_number, article_no)  articles cited together with
                                              it in Q&A answers

Each function returns a plain dict; to_text() turns it into the short text an
agent tool returns to the model. Co-citation is a usage signal, not a statement
that two provisions are legally related. VLOnto v1 has no court decisions (they
join in v2), so the usage signals come from the published Q&As.
"""
import textwrap

import duckdb

TABLES = ("documents", "articles", "changes", "edges_citation",
          "edges_qa_article")
SUPERSEDING = ("replaced", "repealed")

# co-citation: articles cited in the same Q&A answers as article ?, scored by
# shared * ln(N / df) so that articles cited almost everywhere rank low
RELATED_SQL = """
WITH s AS (SELECT DISTINCT {unit} FROM {table} WHERE dst_article_id = ?),
co AS (SELECT e.dst_article_id AS aid, count(DISTINCT e.{unit}) AS shared
       FROM {table} e JOIN s USING ({unit})
       WHERE e.dst_article_id <> ?
       GROUP BY 1 HAVING count(DISTINCT e.{unit}) >= ?),
df AS (SELECT dst_article_id AS aid, count(DISTINCT {unit}) AS df
       FROM {table} WHERE dst_article_id IN (SELECT aid FROM co) GROUP BY 1),
n AS (SELECT count(DISTINCT {unit}) AS n FROM {table}
      WHERE dst_article_id IS NOT NULL)
SELECT d.doc_number, a.article_no, a.heading, co.shared, df.df,
       round(co.shared * ln(n.n / df.df), 1) AS score
FROM co JOIN df USING (aid) CROSS JOIN n
JOIN articles a ON a.article_id = co.aid
JOIN documents d ON d.doc_id = a.doc_id
ORDER BY score DESC, d.doc_number, a.article_no
LIMIT ?
"""


CITES_SQL = """
SELECT d.doc_number, t.article_no, sum(e.n_mentions) AS mentions
FROM edges_citation e
JOIN documents d ON d.doc_id = e.dst_doc_id
LEFT JOIN articles t ON t.article_id = e.dst_article_id
WHERE e.src_article_id = ?
GROUP BY ALL
ORDER BY mentions DESC, d.doc_number, t.article_no
LIMIT ?
"""

CITED_BY_SQL = """
SELECT DISTINCT d.doc_number, s.article_no, d.issue_date
FROM edges_citation e
JOIN documents d ON d.doc_id = e.src_doc_id
LEFT JOIN articles s ON s.article_id = e.src_article_id
WHERE e.dst_article_id = ?
ORDER BY d.issue_date DESC NULLS LAST, d.doc_number, s.article_no
"""


class VLOntoTools:
    def __init__(self, kg_dir="kg"):
        self.con = duckdb.connect()
        for t in TABLES:
            path = f"{kg_dir}/{t}.parquet"
            self.con.execute(
                f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{path}')")

    def _rows(self, sql, params=()):
        cur = self.con.execute(sql, list(params))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _count(self, table, unit, aid):
        sql = (f"SELECT count(DISTINCT {unit}) AS n FROM {table} "
               "WHERE dst_article_id = ?")
        return self._rows(sql, [aid])[0]["n"]

    def _article(self, doc_number, article_no):
        rows = self._rows(
            "SELECT a.article_id, a.heading FROM articles a "
            "JOIN documents d USING (doc_id) "
            "WHERE d.doc_number = ? AND a.article_no = ? "
            "AND a.segment = 'main' ORDER BY a.article_id",
            [doc_number, str(article_no)])
        if not rows:
            raise KeyError(f"{doc_number} Điều {article_no}: not in the graph")
        return rows[0]

    def check_validity(self, doc_number):
        docs = self._rows(
            "SELECT doc_id, title_vi, validity, in_force, expiry_date "
            "FROM documents WHERE doc_number = ? ORDER BY doc_id", [doc_number])
        if not docs:
            return {"doc_number": doc_number, "found": False}
        d = docs[0]
        events = self._rows(
            "SELECT c.kind, c.effective_date, a.doc_number AS by_number, "
            "c.evidence FROM changes c "
            "JOIN documents a ON a.doc_id = c.acting_doc_id "
            "WHERE c.affected_doc_id = ? "
            "ORDER BY c.effective_date NULLS LAST, by_number, c.kind",
            [d["doc_id"]])
        return {
            "doc_number": doc_number, "found": True, "title": d["title_vi"],
            "validity": d["validity"], "in_force": d["in_force"],
            "expiry_date": d["expiry_date"],
            "superseded_by": [e for e in events if e["kind"] in SUPERSEDING],
            "amended_by": [e for e in events if e["kind"] not in SUPERSEDING],
            "same_number_documents": len(docs),
        }

    def expand_citations(self, doc_number, article_no, limit=3):
        art = self._article(doc_number, article_no)
        aid = art["article_id"]
        cited_by = self._rows(CITED_BY_SQL, [aid])
        return {
            "article": f"{doc_number} Điều {article_no}",
            "heading": art["heading"],
            "cites": self._rows(CITES_SQL, [aid, limit]),
            "cited_by_count": len(cited_by),
            "cited_by": cited_by[:limit],
            "qas": self._count("edges_qa_article", "qa_id", aid),
        }

    def related_provisions(self, doc_number, article_no, limit=3,
                           min_shared=2):
        """Articles cited in the same Q&A answers, ranked by
        shared * ln(N / df): the number of shared Q&As weighted by how rare
        the other article is, so that articles cited in almost every answer
        do not dominate."""
        aid = self._article(doc_number, article_no)["article_id"]
        sql = RELATED_SQL.format(table="edges_qa_article", unit="qa_id")
        return {"article": f"{doc_number} Điều {article_no}",
                "in_qas": self._rows(sql, [aid, aid, min_shared, limit])}


def _wrap(text, indent="    ", width=78):
    return textwrap.fill(str(text), width=width, initial_indent=indent,
                         subsequent_indent=indent)


def _art(no):
    return f" Điều {no}" if no else ""


def to_text(result):
    """Render a tool result as the short text a tool returns to the model."""
    lines = []
    if "validity" in result:
        lines.append(f"{result['doc_number']} ({result['title']}): "
                     f"validity {result['validity']}, "
                     f"in force: {result['in_force']}")
        for e in result["superseded_by"]:
            lines.append(f"  {e['kind']} by {e['by_number']} "
                         f"from {e['effective_date']}")
            lines.append(_wrap(f"evidence: {e['evidence']}"))
        for e in result["amended_by"][-3:]:
            lines.append(f"  {e['kind']} by {e['by_number']} "
                         f"from {e['effective_date']}")
        hidden = len(result["amended_by"]) - 3
        if hidden > 0:
            lines.append(f"  ({hidden} earlier amendments not shown)")
    elif "cites" in result:
        lines.append(f"{result['article']}: {result['heading']}")
        for c in result["cites"]:
            lines.append(f"  cites {c['doc_number']}{_art(c['article_no'])}")
        lines.append(f"  cited by {result['cited_by_count']} documents or "
                     f"articles, newest first:")
        for c in result["cited_by"]:
            lines.append(f"    {c['doc_number']}{_art(c['article_no'])} "
                         f"(issued {c['issue_date']})")
        lines.append(f"  cited in {result['qas']:,} Q&A answers")
    else:
        lines.append(f"{result['article']}: provisions cited together with it")
        lines.append("  in Q&As (shared / all citing it / score):")
        for r in result["in_qas"]:
            head = textwrap.shorten(r["heading"] or "-", width=52,
                                    placeholder=" …")
            lines.append(f"    {r['doc_number']}{_art(r['article_no'])}: "
                         f"{head}")
            lines.append(f"      {r['shared']:,} / {r['df']:,} / "
                         f"{r['score']}")
    return "\n".join(lines)
```

#block(sticky: true, width: 100%)[
Calling the tools as an agent would (`playbook/examples/agent_demo.py`):

]
```python
"""Call the three VLOnto tools the way an agent tool server would."""
from vlonto_tools import VLOntoTools, to_text

kg = VLOntoTools("kg")
print(to_text(kg.check_validity("10/2012/QH13")))
print()
print(to_text(kg.expand_citations("45/2019/QH14", "35")))
print()
print(to_text(kg.related_provisions("45/2019/QH14", "169")))
```

#block(sticky: true, width: 100%)[
Output:

]
```text
10/2012/QH13 (Bộ luật Lao động): validity expired, in force: False
  replaced by 45/2019/QH14 from 2021-01-01
    evidence: Bộ luật Lao động số 10/2012/QH13 hết hiệu lực thi hành kể từ
    ngày Bộ luật này có hiệu lực.
  amended by 92/2015/QH13 from 2016-07-01
  partially_repealed by 92/2015/QH13 from 2016-07-01

45/2019/QH14 Điều 35: Quyền đơn phương chấm dứt hợp đồng lao động của người lao động
  cited by 2 documents or articles, newest first:
    374/2025/NĐ-CP Điều 25 (issued 2025-12-31)
    22/2022/TT-BCA (issued 2022-05-10)
  cited in 12 Q&A answers

45/2019/QH14 Điều 169: provisions cited together with it
  in Q&As (shared / all citing it / score):
    135/2020/NĐ-CP Điều 4: Tuổi nghỉ hưu trong điều kiện lao động bình thường
      20 / 20 / 140.5
    58/2014/QH13 Điều 54: Điều kiện hưởng lương hưu
      5 / 22 / 34.7
    41/2024/QH15 Điều 2: Đối tượng tham gia bảo hiểm xã hội bắt buộc và bảo …
      5 / 29 / 33.3
```

The first result is what the agent needs to answer a question asked
under the 2012 code: the act is no longer in force, the replacing act
and its effective date, and the sentence that says so. The second shows
how widely an article is used. The third ranks articles by the number of
Q&As that cite both, weighted by how rare the other article is; it is a
usage signal, not a legal relation, and Q&A article links are evaluation
labels whose spot check found 9 of 10 correct.

== 8.3 Plugging the tools into the agent
<plugging-the-tools-into-the-agent>
The following integration is a design that follows the guide's
architecture; it was not run against the live agent for this playbook.

- #strong[As MCP tools.] Register the three functions next to
  `search_law`, `get_article` and `check_validity` in the agent's MCP
  server, each returning `to_text(...)`. Install the server as a console
  script in the NeMo Helix environment, as the guide does for its own
  tools (stdio MCP servers start in the agent's workspace, so relative
  script paths fail). A minimal server with the `mcp` Python SDK:

```python
from mcp.server.fastmcp import FastMCP
from vlonto_tools import VLOntoTools, to_text

mcp = FastMCP("vlonto-kg")
kg = VLOntoTools("/data/vlonto/build/kg")    # kg/ folder of a local build


@mcp.tool()
def kg_check_validity(doc_number: str) -> str:
    """Validity, replacing acts and amendments of a Vietnamese legal document."""
    return to_text(kg.check_validity(doc_number))


@mcp.tool()
def kg_expand_citations(doc_number: str, article_no: str) -> str:
    """What an article cites, what cites it, and how many Q&As cite it."""
    return to_text(kg.expand_citations(doc_number, article_no))


@mcp.tool()
def kg_related_provisions(doc_number: str, article_no: str) -> str:
    """Articles cited together with this one in Q&A answers."""
    return to_text(kg.related_provisions(doc_number, article_no))


if __name__ == "__main__":
    mcp.run()
```

- #strong[In the retrieval service.] `GET /validity/{doc_number}` and
  `check_validity` read the same relations, so a deployment without the
  GPU-backed service can answer validity questions from the parquet
  files alone. Keep one source of truth per release: rebuild VLOnto
  whenever the validity map is regenerated (section~11).
- #strong[In the answer audit.] The audit parses each citation
  (`[45/2019/QH14, Điều 35]`) and checks that the article exists and
  that its act is in force. With VLOnto it can also append the amendment
  history of the act and flag citations of an act whose validity is
  unknown instead of treating them as current.
- #strong[In the prompt.] Keep the guide's rule: when a tool reports
  validity `unknown`, the agent says that validity is not confirmed
  rather than implying that the provision is current.

== 8.4 Cautions
<cautions>
- Validity is unknown for 70.2% of the documents; a missing change event
  does not mean that an act is in force.
- The change events are extracted from text with a precision of 29/30 on
  a sample (section~6.5); show the evidence sentence and the source URL
  with every validity claim.
- Citation and usage counts reflect the corpus (its coverage of
  documents and Q&As), not legal importance.

= 9. The website and the 3D playgrounds
<the-website-and-the-3d-playgrounds>
#block(sticky: true, width: 100%)[
The website is a set of static pages generated from the build's data
bundles. It is published at #link("https://tmquan.github.io/VLOnto/"),
which opens the 3D ontology playground, and it also opens from disk
(section~2.1).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (19.83%, 56.03%, 24.14%),
    align: (left,left,left,),
    table.header([Page], [What it shows], [Data],),
    table.hline(),
    [`index.html`], [The start page: the 3D ontology playground, the
    ontology as a 3D graph: 75 nodes (classes, concept schemes and the
    external terms they are aligned to) and 104 links (sub-class 24,
    property 40, scheme membership 13, alignment 27), coloured by
    module.], [`ontology_graph.json`],
    [`about.html`], [Overview of VLOnto with the key counts of the build
    and links to every view.], [`stats.json`],
    [`ontology-3d.html`], [Only a redirect to `index.html`, so that
    older links to the playground keep working.], [-],
    [`network-3d.html`], [The legal network: 40,816 documents in 3D with
    the legal-force rank as height, and their change (15,035),
    legal-basis (99,038) and citation (152,251 document pairs) links.
    Phones load a lighter bundle of 6,000
    documents.], [`legal_network.json`, `legal_network_lite.json`],
    [`sparql.html`], [A SPARQL editor that runs Oxigraph, compiled to
    WebAssembly, inside the page over the browser subset (49,846
    triples), with the 10 examples of
    section~7.7.], [`vlonto_core_ttl.js`, `sparql_examples.json`],
    [`dashboard.html`], [Charts of documents by type, year, issuer, area
    and validity; change events by kind and year; legal-basis methods
    and citation kinds; the most cited documents and articles; Q&As,
    terms and news.], [`dashboard.json`],
    [`traces.html`], [Question traces: for each of the 27 legal areas of
    the Q&As, the 20 articles that the most answers in the area cite,
    each traced from one question and its answer through the cited
    point, clause and article to the chapter and the law, highlighted
    like Figure~6 of the paper (540 traces). It shows question titles,
    never answer text.], [`data/traces/`],
    [`ontology.html`], [The ontology documentation generated by pyLODE
    from the Turtle file, with every class, property and concept
    scheme.], [`vlonto.html`],
    [`playbook.html`], [This playbook as HTML, with the PDF and the
    Markdown source as downloads.], [`playbook_html.js`],
    [`downloads.html`], [The files that need no build (section~2.2): the
    ontology, the core Turtle subset, the data dictionary, the website's
    JSON data, the licence policy and attribution, the figures and this
    playbook, with a checksum list.], [`downloads/`, `SHA256SUMS.txt`],
  )]
  , kind: table
  )

]
#strong[Offline use.] Every page is plain HTML with classic scripts: no
ES modules, no `fetch`, no server. Data bundles are JavaScript files
that assign the JSON to `window.VLONTO` (generated by
`tools/json2js.py`), the WebAssembly of Oxigraph is embedded in its
script, and the fonts are in the site folder, so the pages work from
`file://` without network access. Each bundle stays below 20 MB (15
files listed in `manifest.json` with size and sha256).

#strong[3D views.] The 3D views use three.js and 3d-force-graph with
text labels drawn as sprites. The legal-network positions are
precomputed in the build (`vlonto.cli layout`), so the page does not run
a force simulation on 40,816 nodes. Rendering speed depends on the
graphics hardware; the automated website checks render with a software
WebGL implementation, so their frame rates say nothing about a real GPU.

= 10. Reproducibility
<reproducibility>
== 10.1 Pinned tools and libraries
<pinned-tools-and-libraries>
#figure(
  align(center)[#table(
    columns: (31.9%, 30.17%, 37.93%),
    align: (left,left,left,),
    table.header([Component], [Version], [Used for],),
    table.hline(),
    [Typst], [0.15.1 (9dfd3a08)], [PDF of this playbook],
    [pandoc], [3.9], [Markdown to Typst and HTML],
    [Python (pinned toolchain)], [3.12.16], [website build and checks
    (tools/setup\_tools.sh)],
    [Python (reference build)], [3.11.18], [knowledge-graph build and
    playbook tools of VLOnto v1 (macOS, arm64)],
    [uv], [0.13.7], [Python environments],
    [Node.js / npm], [24.19.0 / 11.17.0], [vendored JavaScript build],
    [esbuild], [0.28.2], [browser bundles],
    [Chrome headless shell], [157.0.8103.50], [website checks],
    [three.js], [0.187.0], [3D rendering],
    [3d-force-graph], [1.80.2], [3D graphs],
    [three-spritetext], [1.10.0], [3D labels],
    [ECharts], [6.1.0], [dashboard charts],
    [Oxigraph (npm)], [0.5.13], [SPARQL in the browser],
    [JetBrains Mono], [2.304], [code font (NL variant)],
    [duckdb], [2.0.0], [knowledge-graph build],
    [igraph], [1.0.0], [knowledge-graph build],
    [owlrl], [7.6.2], [knowledge-graph build],
    [polars], [2.1.0], [knowledge-graph build],
    [pyarrow], [26.0.1], [knowledge-graph build],
    [pylode], [3.6.1], [knowledge-graph build],
    [pyoxigraph], [0.5.13], [knowledge-graph build],
    [pyshacl], [0.40.2], [knowledge-graph build],
    [rdflib], [7.6.0], [knowledge-graph build],
  )]
  , kind: table
  )

The fonts come from fixed commits of their repositories (Be Vietnam Pro,
Noto Serif, Noto Sans Math, Noto Sans Symbols 2) or a fixed release
(JetBrains Mono), and only these files are used for the PDF (16 font
files in `typst/fonts`).

== 10.2 Lock files
<lock-files>
- `tools/chrome-deps.conda.lock`: conda packages of the libraries Chrome
  needs on the node.
- `tools/requirements-web.lock`: hash-checked Python packages of the web
  and PDF environment.
- `tools/vendor.lock.json`: package, version, file, sha256 and licence
  of every vendored website file (98 files).
- `tools/versions.lock`: versions, download URLs and sha256 of the
  downloaded tools and fonts.

`tools/setup_tools.sh --check` verifies every pinned tool and exits with
an error on any drift; `tools/fetch_vendor.sh --check-repo` compares the
vendored files with `vendor.lock.json`.

== 10.3 Deterministic build of this playbook
<deterministic-build-of-this-playbook>
#block(sticky: true, width: 100%)[
The Markdown is generated, never edited by hand: `playbook.md.j2` +
`data/facts.json` → `playbook.md` → pandoc → `playbook.typ` → Typst →
PDF. `scripts/build_pdf.sh` runs the chain:

]
```bash
bash scripts/build_pdf.sh --facts       # 1. gather facts (needs the KG build)
bash scripts/build_pdf.sh               # 2. Markdown, SVG figures, Typst, PDF, HTML
bash scripts/build_pdf.sh --check       # 3. check the PDF, rebuild it twice
bash scripts/build_pdf.sh --check-files # 4. printed sizes and sha256 vs the files
bash scripts/build_pdf.sh --pdf-only    # Typst only, from the generated playbook.typ
```

`playbook/Makefile` offers the same steps as targets:
`make -C playbook facts`, `pdf`, `check`, `check-files` and `pdf-only`\;
`make -C playbook` runs `pdf`, `check` and `check-files`. `--facts`
loads the RDF dump into a new Oxigraph store for the recipes;
`REUSE_STORE=1` keeps the previous store and is only for runs on an
unchanged dump.

Typst runs with
`--font-path typst/fonts --ignore-system-fonts --ignore-embedded-fonts`,
so only the vendored fonts can be used, and with a fixed
`SOURCE_DATE_EPOCH` (the build date), so two builds of the same sources
are byte-identical. `--check` runs `tools/pdf_check.py`, which checks
that every font is embedded and vendored, that no glyph is missing, that
text stays inside the margins, that no lines overlap and that no page is
blank, and rebuilds the PDF twice to compare the bytes; it then runs
`playbook/tools/text_collisions.py`, which finds glyphs that run into
other text on the same baseline, such as a word wider than its table
cell. The generated `playbook.typ`, the figure data and the SVG figures
are kept in the repository, so the PDF can be rebuilt with Typst alone:
the GitHub Pages workflow (job `reproduce-pdf`) rebuilds it on Linux
with the pinned Typst release (`tools/fetch_typst.sh`, sha256-checked)
and compares it byte for byte with `site/downloads/VLOnto-playbook.pdf`,
and the preview workflow runs the same job on preview branches. The
figures are drawn by Typst from `data/figures.json` (`charts.typ`):
natively in the PDF and as SVG for the Markdown and the website.

== 10.4 Checksums of the reference build
<checksums-of-the-reference-build>
#block(sticky: true, width: 100%)[
`playbook/data/SHA256SUMS` records the sha256 of the outputs of the
reference build of 2026-11-12 that this playbook describes: the tables
and RDF dumps (paths relative to the build folder) and the ontology
files (relative to the repository). The first 16 hexadecimal digits are:

]
#figure(
  align(center)[#table(
    columns: (51.72%, 16.38%, 31.9%),
    align: (left,right,left,),
    table.header([File], [Size], [sha256 (prefix)],),
    table.hline(),
    [`kg/areas.parquet`], [7 kB], [`d2991b4c9328458f`],
    [`kg/articles.parquet`], [9.3 MB], [`1b4f587a82a88dc6`],
    [`kg/changes.parquet`], [1.3 MB], [`8ac8c354d628c083`],
    [`kg/data_dictionary.json`], [29 kB], [`a1cebf64f35c5dbd`],
    [`kg/data_dictionary.md`], [15 kB], [`1694da8bdfdd485d`],
    [`kg/doc_types.parquet`], [3 kB], [`4492320fcc76b562`],
    [`kg/documents.parquet`], [4.9 MB], [`9fa21cf00c273965`],
    [`kg/edges_change.parquet`], [230 kB], [`6c020502418fe78e`],
    [`kg/edges_citation.parquet`], [3.1 MB], [`680a38acc145bbd4`],
    [`kg/edges_legal_basis.parquet`], [667 kB], [`f243d3f950ca9e75`],
    [`kg/edges_news_document.parquet`], [12 kB], [`e8fc672c8674e61d`],
    [`kg/edges_qa_article.parquet`], [461 kB], [`12afaab65c4a4640`],
    [`kg/edges_qa_document.parquet`], [806 kB], [`8844ff35b0e289f3`],
    [`kg/edges_term_related.parquet`], [75 kB], [`b8d838592da46701`],
    [`kg/issuers.parquet`], [7 kB], [`93504e8c6f7326c5`],
    [`kg/legal_force_ranks.parquet`], [3 kB], [`ffe962e40c5851c9`],
    [`kg/news.parquet`], [31 kB], [`6696aed7dc3fe639`],
    [`kg/news_categories.parquet`], [3 kB], [`0fa3a472c5b03aa1`],
    [`kg/provisions_ref.parquet`], [1.0 MB], [`4f310ecb270f06de`],
    [`kg/qas.parquet`], [3.9 MB], [`c412cf700967d0e4`],
    [`kg/sources.parquet`], [5 kB], [`04bd4d6ee590815c`],
    [`kg/structure.parquet`], [1.6 MB], [`392381bc225cfbf8`],
    [`kg/terms.parquet`], [481 kB], [`9a4a119e87567e5e`],
    [`ontology/vlonto-context.jsonld`], [7 kB], [`a7d3f1b413e398a9`],
    [`ontology/vlonto-shapes.ttl`], [13 kB], [`8aec3dc3d0462985`],
    [`ontology/vlonto.html`], [680 kB], [`efc8c549794dd5fd`],
    [`ontology/vlonto.ttl`], [122 kB], [`5c376a367adcb77e`],
    [`rdf/vlonto-core.ttl`], [2.6 MB], [`c422b80209ecbcb9`],
    [`rdf/vlonto-kg.nt.gz`], [48.2 MB], [`4bae225735434342`],
  )]
  , kind: table
  )

The ontology files, `rdf/vlonto-core.ttl` and the data dictionary on the
website's downloads page are these files; check a download with
`sha256sum` against this list. `bash scripts/build_pdf.sh --check-files`
(`playbook/tools/check_files.py`) compares every size and sha256 printed
in this playbook, and the triple counts of section~5.3, with the files
of the build folder, the repository and the downloads page. A local
rebuild is checked by its counts (section~6.2) rather than by these
bytes: byte equality of rebuilt tables and dumps is not tested.

= 11. Maintenance runbook
<maintenance-runbook>
== 11.1 New revisions of the source datasets
<new-revisions-of-the-source-datasets>
+ Update the revision of each changed dataset in
  `vlonto/vlonto/config.py` (`SOURCES`) and in the vn-legal project, and
  download the new snapshots.
+ Re-run the vn-legal data pipeline: clean and scope, split into
  articles, extract the validity map, build the evaluation labels.
+ Run `python -m vlonto.cli all` (section~5) and read
  `build/reports/kg_report.md`: all checks must pass and the
  reconciliation items must match.
+ Compare `build/site_data/stats.json` with the previous release and
  explain every large change.
+ Draw new spot-check samples for the edge types whose extraction rules
  or inputs changed, judge them and record the verdicts in
  `docs/spot_check_review.json`\; then run
  `python -m vlonto.cli report`.
+ Re-check the licences of the dataset cards (`docs/licence_policy.md`)
  if a card changed.
+ Rebuild the website data and this playbook
  (`bash scripts/build_pdf.sh --facts` without `REUSE_STORE`,
  `bash scripts/build_pdf.sh`, `bash scripts/build_pdf.sh --check` and,
  once the website's downloads folder holds the new files,
  `bash scripts/build_pdf.sh --check-files`), and run
  `tools/site_check.py` on the website.

== 11.2 Re-running the validity rules
<re-running-the-validity-rules>
#block(sticky: true, width: 100%)[
The validity map belongs to the vn-legal project
(`$R/data/validity/relations.parquet` and
`$R/data/validity/validity.parquet`). To change the rules or the as-of
date:

]
+ Edit and re-run the rules there
  (`SAMPLE_SEED=31 $R/envs/data/bin/python $R/code/validity.py`, as in
  the guide) and keep the known-case checks passing.
+ Judge a fresh sample of relations and record the precision with the
  rule version.
+ Set `VALIDITY_AS_OF` in `vlonto/vlonto/config.py` and rebuild VLOnto:
  every change event records the rule version, and the build activity
  records the as-of date.
+ Rebuild the retrieval service of the agent from the same map, so that
  the agent and VLOnto agree.

== 11.3 Releasing
<releasing>
+ Set the version (`__version__`) and the release name (`RELEASE`, for
  example `v1`) in `vlonto/vlonto/__init__.py` and `BUILD_DATE` in
  `vlonto/vlonto/config.py` (or `VLONTO_BUILD_DATE`); update
  `owl:versionInfo`, `owl:versionIRI`, `owl:priorVersion` and
  `dcterms:modified` in `ontology/vlonto.ttl` following the policy of
  section~4.6.
+ Rebuild the graph, the website data and the playbook; all checks must
  pass.
+ Regenerate `playbook/data/SHA256SUMS`
  (`bash scripts/build_pdf.sh --facts`), refresh the website's downloads
  folder and its `SHA256SUMS.txt` (the GitHub Pages workflow checks that
  list with `sha256sum -c`), run
  `bash scripts/build_pdf.sh --check-files`, push the repository to
  #link("https://github.com/tmquan/VLOnto") so that GitHub Pages
  publishes the website at #link("https://tmquan.github.io/VLOnto/"),
  and tag the repository with the release name (`v1`). No data is
  uploaded: the source datasets stay the data home, and users build the
  knowledge graph locally.
+ Keep the ontology file of the previous version available; its version
  IRI must keep resolving.

= 12. Limitations and roadmap
<limitations-and-roadmap>
== 12.1 Limitations of the knowledge graph
<limitations-of-the-knowledge-graph>
#block(sticky: true, width: 100%)[
From the build report of 2026-11-12:

]
- Citation resolution to an in-scope document: external citations 83.1%,
  external mentions 68.7%, parent law 97.0%, parent-law mentions 99.0%;
  the rest cite documents outside the corpus or are too vague. When the
  citing document has no date, a law cited by name resolves to the only
  or latest version, which can be an older law of the same name
  (257/1998/TT-BGTVT linked to the 1987 Foreign Investment Law).
- Legal basis: errors in the source parent-acts metadata are carried
  over (1 of 10 sampled), and a document mentioned in a preamble can be
  a cross-reference rather than a legal basis (1 of 10 not decidable).
- Document issue dates: 144 source dates more than one year away from
  the year in the document number were set to null (kept in
  issue\_date\_source); 170 documents have no issue date.
- Validity: 28,660 of 40,816 documents have validity 'unknown' (validity
  pipeline as of 2026-11-08).
- Issuers: 57 curated issuing bodies; 1,750 documents have no issuer and
  1,204 only symbols without a curated code; joint issuers without a
  curated code are not linked.
- News: the source gives a publication date for only a small part of the
  news items (87 of 681).
- Glossary: English labels of terms are mostly machine-translated in the
  source; definitions are not republished (licence).
- Texts: article texts are not in the publishable tables (they stay in
  the build's local-only article-text table); no judgment text and no
  person names from court records are stored. Titles and article
  headings of public legal documents can name officials or award
  recipients (a pattern scan finds such names in 206 article headings
  and 6 document titles); they are kept as published by the source.
- Spot checks are small samples (10 per edge type); they catch
  systematic errors but give only coarse precision estimates.

== 12.2 Limitations of the website and this playbook
<limitations-of-the-website-and-this-playbook>
- The website is machine-checked only in Chromium (headless Chrome);
  Safari and Firefox behaviour under `file://` follows the same rules
  but must be checked by hand.
- The 3D views were tested with software WebGL; large graphs can be slow
  on weak graphics hardware, which is why phones get the lighter network
  bundle.
- The playbook's numbers are as good as the build reports; a fact that
  the reports do not contain is not stated.
- The agent integration of section~8.3 is a design; only the
  knowledge-graph tools themselves were run.

== 12.3 Roadmap
<roadmap>
+ Close the validity gap: add official validity sources and consolidated
  texts as evidence, and measure recall of the change events.
+ Measure precision with larger, stratified samples and with legal
  review, starting with Q&A article labels and legal-basis links.
+ VLOnto v2: add the court datasets `anle-toaan-gov-vn` and
  `cbba-toaan-gov-vn` (court decisions, precedents and the provisions
  they apply).
+ Resolve joint issuers that have no curated code.
+ Publish the agent tools as an MCP server package and evaluate them in
  the agent's test set.
+ Serve the RDF with content negotiation and a public SPARQL endpoint.

= References
<references>
- Khac-Hoai Nam Bui and Quan Tran Minh. #emph[Vietnamese Legal Ontology:
  Every legal answer, traced to the article that grounds it.]
  arXiv:2611.11426 \[cs.CL\], 2026.
  #link("https://arxiv.org/abs/2611.11426")

= Appendix A. Namespaces and prefixes
<appendix-a.-namespaces-and-prefixes>
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (16.38%, 83.62%),
    align: (left,left,),
    table.header([Prefix], [Namespace],),
    table.hline(),
    [`vlo:`], [`https://tmquan.github.io/VLOnto/ontology#`],
    [`vlid:`], [`https://tmquan.github.io/VLOnto/id/`],
    [`eli:`], [`http://data.europa.eu/eli/ontology#`],
    [`skos:`], [`http://www.w3.org/2004/02/skos/core#`],
    [`dcterms:`], [`http://purl.org/dc/terms/`],
    [`prov:`], [`http://www.w3.org/ns/prov#`],
    [`schema:`], [`https://schema.org/`],
    [`org:`], [`http://www.w3.org/ns/org#`],
    [`owl:`], [`http://www.w3.org/2002/07/owl#`],
    [`rdfs:`], [`http://www.w3.org/2000/01/rdf-schema#`],
    [`rdf:`], [`http://www.w3.org/1999/02/22-rdf-syntax-ns#`],
    [`xsd:`], [`http://www.w3.org/2001/XMLSchema#`],
    [`vann:`], [`http://purl.org/vocab/vann/`],
  )]
  , kind: table
  )

]
= Appendix B. Ontology reference
<appendix-b.-ontology-reference>
Generated from `ontology/vlonto.ttl` (version 1.0.0, 2,061 triples):
every class, property and concept scheme of VLOnto by module, with its
English and Vietnamese labels, its axioms, its English definition and,
where it has one, its English scope note.

== B.1 Module documents (#emph[văn bản])
<b.1-module-documents-văn-bản>
Legal documents and their types.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:Circular`] · Circular · #emph[Thông tư]. Subclass of
  `vlo:NormativeLegalDocument`. A normative document issued by a
  minister or the head of a ministerial-level agency, the Chief Justice
  of the Supreme People's Court, the Prosecutor General or the State
  Auditor General.
- #strong[`vlo:Code`] · Code · #emph[Bộ luật]. Subclass of
  `vlo:NormativeLegalDocument`. A comprehensive law adopted by the
  National Assembly that systematically regulates a whole field, such as
  the Civil Code or the Labour Code.
- #strong[`vlo:Constitution`] · Constitution · #emph[Hiến pháp].
  Subclass of `vlo:NormativeLegalDocument`. The fundamental law of the
  State, adopted by the National Assembly; it has the highest legal
  force.
- #strong[`vlo:Decision`] · Decision · #emph[Quyết định]. Subclass of
  `vlo:NormativeLegalDocument`. A normative decision issued by the Prime
  Minister, a minister or another competent head of a central body; only
  decisions numbered in the normative form N/YYYY/CODE are in scope.
- #strong[`vlo:Decree`] · Decree · #emph[Nghị định]. Subclass of
  `vlo:NormativeLegalDocument`. A normative document issued by the
  Government, usually detailing or implementing laws.
- #strong[`vlo:JointCircular`] · Joint circular · #emph[Thông tư liên
  tịch]. Subclass of `vlo:NormativeLegalDocument`. A circular issued
  jointly by two or more ministers, heads of ministerial-level agencies
  or judicial bodies.
- #strong[`vlo:JointResolution`] · Joint resolution · #emph[Nghị quyết
  liên tịch]. Subclass of `vlo:NormativeLegalDocument`. A resolution
  issued jointly by a state body and the central body of a
  socio-political organisation, for example the Standing Committee of
  the National Assembly or the Government together with the Presidium of
  the Viet Nam Fatherland Front.
- #strong[`vlo:Law`] · Law · #emph[Luật]. Subclass of
  `vlo:NormativeLegalDocument`. A statute adopted by the National
  Assembly.
- #strong[`vlo:LegalDocument`] · Legal document · #emph[Văn bản pháp
  luật]. Subclass of `eli:LegalResource`, `schema:Legislation`\;
  disjoint with `vlo:Provision`. A document issued by a competent state
  body that has legal effect, identified by its type, number and issue
  date.
- #strong[`vlo:NormativeLegalDocument`] · Normative legal document ·
  #emph[Văn bản quy phạm pháp luật]. Subclass of `vlo:LegalDocument`. A
  legal document containing generally binding rules of conduct, issued
  in the form, order and procedure set out by the Law on Promulgation of
  Legal Normative Documents.
- #strong[`vlo:Ordinance`] · Ordinance · #emph[Pháp lệnh]. Subclass of
  `vlo:NormativeLegalDocument`. A normative document adopted by the
  Standing Committee of the National Assembly on matters assigned by the
  National Assembly.
- #strong[`vlo:Resolution`] · Resolution · #emph[Nghị quyết]. Subclass
  of `vlo:NormativeLegalDocument`. A normative resolution issued by a
  collegial body such as the National Assembly, its Standing Committee,
  the Government or the Council of Judges of the Supreme People's Court.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:documentType`] · document type · #emph[loại văn bản].
  Sub-property of `eli:type_document`\; domain `vlo:LegalDocument`\;
  range `vlo:DocumentType`\; `owl:FunctionalProperty`. The type of a
  legal document as a concept of the DocumentType scheme.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:documentNumber`] · document number · #emph[số, ký hiệu
  văn bản]. Sub-property of `eli:id_local`\; domain
  `vlo:LegalDocument`\; range `xsd:string`. The official number and
  symbol of a legal document as printed in its header, for example
  45/2019/QH14.
- #strong[`vlo:documentNumberKey`] · document number key · #emph[khóa số
  văn bản]. domain `vlo:LegalDocument`\; range `xsd:string`. A
  normalised lookup key of the document number (ASCII, upper case,
  unified separators, Đ written as D), used to match citations to
  documents.
- #strong[`vlo:issueDate`] · issue date · #emph[ngày ban hành].
  Sub-property of `eli:date_document`\; domain `vlo:LegalDocument`\;
  range `xsd:date`. The date on which a legal document was adopted or
  signed.
- #strong[`vlo:title`] · title · #emph[tên văn bản]. Sub-property of
  `dcterms:title`\; range `rdfs:Literal`. The Vietnamese title of a
  legal document, including its type and, for sub-statutory acts, its
  number.

== B.2 Module provisions (#emph[điều khoản])
<b.2-module-provisions-điều-khoản>
Structural units of legal documents: parts, chapters, sections,
articles, clauses, points and appendices.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:Appendix`] · Appendix · #emph[Phụ lục]. Subclass of
  `vlo:Provision`. An attachment issued with a legal document, such as a
  regulation, charter or list promulgated by the document; it may
  contain its own articles.
- #strong[`vlo:Article`] · Article · #emph[Điều]. Subclass of
  `vlo:Provision`. The basic numbered unit of a legal document (Điều N),
  usually with a heading, divided into clauses.
- #strong[`vlo:Chapter`] · Chapter · #emph[Chương]. Subclass of
  `vlo:Provision`. A division of a legal document grouping sections or
  articles under a heading (Chương I, Chương II, …).
- #strong[`vlo:Clause`] · Clause · #emph[Khoản]. Subclass of
  `vlo:Provision`. A numbered subdivision of an article (khoản 1, khoản
  2, …).
- #strong[`vlo:Part`] · Part · #emph[Phần]. Subclass of `vlo:Provision`.
  A top-level division of a long legal document, grouping chapters (Phần
  thứ nhất, Phần thứ hai, …).
- #strong[`vlo:Point`] · Point · #emph[Điểm]. Subclass of
  `vlo:Provision`. A lettered subdivision of a clause (điểm a, điểm b,
  …).
- #strong[`vlo:Provision`] · Provision · #emph[Đơn vị cấu trúc của văn
  bản]. Subclass of `eli:LegalResourceSubdivision`. A structural unit of
  a legal document, such as a part, chapter, section, article, clause,
  point or appendix.
- #strong[`vlo:Section`] · Section · #emph[Mục]. Subclass of
  `vlo:Provision`. A division of a chapter grouping articles (Mục 1, Mục
  2, …).

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:hasPart`] · has part · #emph[gồm]. Sub-property of
  `eli:has_part`\; domain `eli:LegalResource`\; range `vlo:Provision`.
  Inverse of vlo:isPartOf: links a document or provision to a provision
  it immediately contains. Not materialised in the RDF dumps.
- #strong[`vlo:inDocument`] · in document · #emph[thuộc văn bản].
  Sub-property of `eli:is_part_of`\; domain `vlo:Provision`\; range
  `vlo:LegalDocument`\; `owl:FunctionalProperty`. Links a provision at
  any depth directly to the legal document that contains it.
- #strong[`vlo:isPartOf`] · is part of · #emph[thuộc]. Sub-property of
  `eli:is_part_of`\; domain `vlo:Provision`\; range
  `eli:LegalResource`\; inverse of `vlo:hasPart`. Links a provision to
  the unit that immediately contains it: a section, chapter, part,
  appendix, article, clause or the document itself.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:heading`] · heading · #emph[tên điều khoản]. Sub-property
  of `dcterms:title`\; domain `vlo:Provision`\; range `rdfs:Literal`.
  The heading of a provision as printed, cut at 200 characters (for
  example the article title or the chapter heading).
- #strong[`vlo:position`] · position · #emph[thứ tự]. domain
  `vlo:Provision`\; range `xsd:integer`. The 1-based order of a
  provision among the provisions of the same kind in its document,
  following the text.
- #strong[`vlo:provisionNumber`] · provision number · #emph[số hiệu điều
  khoản]. Sub-property of `dcterms:identifier`\; domain
  `vlo:Provision`\; range `xsd:string`. The number or letter of a
  provision within its parent: 35 or 5a for an article, 2 for a clause,
  a or đ for a point, III for a chapter, 1 for an appendix.

== B.3 Module agents (#emph[chủ thể])
<b.3-module-agents-chủ-thể>
Public authorities that issue documents or decide cases.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:Court`] · Court · #emph[Tòa án]. Subclass of
  `vlo:PublicAuthority`. A people's court or military court that decides
  cases; identified by its official name, for example Tòa án nhân dân
  tỉnh Cà Mau. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:IssuingBody`] · Issuing body · #emph[Cơ quan ban hành].
  Subclass of `vlo:PublicAuthority`. A public authority that issues
  legal documents, identified in the knowledge graph by the issuer code
  used in document numbers (for example BTC for the Ministry of
  Finance).
- #strong[`vlo:PublicAuthority`] · Public authority · #emph[Cơ quan nhà
  nước]. Subclass of `org:Organization`. A state organisation or office
  holder acting for the State, such as the National Assembly, the
  Government, a ministry, the Prime Minister or a court.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:issuedBy`] · issued by · #emph[cơ quan ban hành].
  Sub-property of `eli:passed_by`\; domain `vlo:LegalDocument`\; range
  `vlo:IssuingBody`. A body that issued a legal document; joint
  documents have several issuing bodies.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:issuerCode`] · issuer code · #emph[ký hiệu cơ quan ban
  hành]. domain `vlo:IssuingBody`\; range `xsd:string`. The abbreviation
  that identifies an issuing body in document numbers, written in ASCII
  upper case (for example BTC, BLDTBXH, TTG).

== B.4 Module validity and change (#emph[hiệu lực và thay đổi])
<b.4-module-validity-and-change-hiệu-lực-và-thay-đổi>
Validity status of documents and the dated events that replace, amend,
repeal or terminate them.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:ChangeKind`] · Change kind · #emph[Loại thay đổi].
  Subclass of `skos:Concept`. A kind of legal change: replaced, amended,
  repealed, partially repealed or partially terminated.
- #strong[`vlo:LegalChange`] · Legal change · #emph[Sự kiện thay đổi
  hiệu lực văn bản]. Subclass of `prov:Activity`. A dated event in which
  an acting legal document replaces, amends, repeals, partially repeals
  or partially terminates an affected legal document. The event is
  reified so that its kind, effective date, the evidence sentence and
  the extraction method can be recorded; the direct shortcut properties
  (vlo:replaces, vlo:amends, …) carry the same information without the
  details.
- #strong[`vlo:ValidityStatus`] · Validity status · #emph[Tình trạng
  hiệu lực]. Subclass of `eli:InForce`, `skos:Concept`. The validity of
  a legal document as of the knowledge-graph date, combining the curated
  source status with text-extracted change relations (validity rules
  v7). It refines the ELI in-force concept with eight values.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:actingDocument`] · acting document · #emph[văn bản tác
  động]. domain `vlo:LegalChange`\; range `vlo:LegalDocument`\;
  `owl:FunctionalProperty`. The legal document whose text makes the
  change (the newer act).
- #strong[`vlo:affectedDocument`] · affected document · #emph[văn bản bị
  tác động]. domain `vlo:LegalChange`\; range `vlo:LegalDocument`\;
  `owl:FunctionalProperty`. The legal document that is replaced,
  amended, repealed or terminated by the change.
- #strong[`vlo:amendedBy`] · amended by · #emph[được sửa đổi, bổ sung
  bởi]. domain `vlo:LegalDocument`\; range `vlo:LegalDocument`. Inverse
  of vlo:amends. Not materialised in the RDF dumps.
- #strong[`vlo:amends`] · amends · #emph[sửa đổi, bổ sung]. Sub-property
  of `eli:amends`, `vlo:changes`\; domain `vlo:LegalDocument`\; range
  `vlo:LegalDocument`\; inverse of `vlo:amendedBy`. The subject document
  amends or supplements some provisions of the object document (sửa đổi,
  bổ sung).
- #strong[`vlo:changeKind`] · change kind · #emph[loại thay đổi]. domain
  `vlo:LegalChange`\; range `vlo:ChangeKind`\; `owl:FunctionalProperty`.
  The kind of a legal change.
- #strong[`vlo:changedBy`] · changed by · #emph[bị thay đổi bởi]. domain
  `vlo:LegalDocument`\; range `vlo:LegalDocument`. Inverse of
  vlo:changes. Not materialised in the RDF dumps.
- #strong[`vlo:changes`] · changes · #emph[thay đổi]. Sub-property of
  `eli:changes`\; domain `vlo:LegalDocument`\; range
  `vlo:LegalDocument`\; inverse of `vlo:changedBy`. Shortcut for any
  legal change: the subject document replaces, amends, repeals,
  partially repeals or partially terminates the object document.
- #strong[`vlo:partiallyRepealedBy`] · partially repealed by · #emph[bị
  bãi bỏ một phần bởi]. domain `vlo:LegalDocument`\; range
  `vlo:LegalDocument`. Inverse of vlo:partiallyRepeals. Not materialised
  in the RDF dumps.
- #strong[`vlo:partiallyRepeals`] · partially repeals · #emph[bãi bỏ một
  phần]. Sub-property of `vlo:changes`\; domain `vlo:LegalDocument`\;
  range `vlo:LegalDocument`\; inverse of `vlo:partiallyRepealedBy`. The
  subject document repeals some articles, clauses, points or contents of
  the object document, which otherwise stays in force.
- #strong[`vlo:partiallyTerminatedBy`] · partially terminated by ·
  #emph[bị làm hết hiệu lực một phần bởi]. domain `vlo:LegalDocument`\;
  range `vlo:LegalDocument`. Inverse of vlo:partiallyTerminates. Not
  materialised in the RDF dumps.
- #strong[`vlo:partiallyTerminates`] · partially terminates · #emph[làm
  hết hiệu lực một phần]. Sub-property of `vlo:changes`\; domain
  `vlo:LegalDocument`\; range `vlo:LegalDocument`\; inverse of
  `vlo:partiallyTerminatedBy`. The subject document declares that some
  provisions of the object document cease to be in force (hết hiệu lực
  một phần).
- #strong[`vlo:repealedBy`] · repealed by · #emph[bị bãi bỏ bởi]. domain
  `vlo:LegalDocument`\; range `vlo:LegalDocument`. Inverse of
  vlo:repeals. Not materialised in the RDF dumps.
- #strong[`vlo:repeals`] · repeals · #emph[bãi bỏ]. Sub-property of
  `eli:repeals`, `vlo:changes`\; domain `vlo:LegalDocument`\; range
  `vlo:LegalDocument`\; inverse of `vlo:repealedBy`. The subject
  document repeals the object document as a whole without replacing it
  (bãi bỏ).
- #strong[`vlo:replacedBy`] · replaced by · #emph[được thay thế bởi].
  domain `vlo:LegalDocument`\; range `vlo:LegalDocument`. Inverse of
  vlo:replaces. Not materialised in the RDF dumps.
- #strong[`vlo:replaces`] · replaces · #emph[thay thế]. Sub-property of
  `eli:repeals`, `vlo:changes`\; domain `vlo:LegalDocument`\; range
  `vlo:LegalDocument`\; inverse of `vlo:replacedBy`. The subject
  document replaces the object document as a whole, which then ceases to
  be in force (thay thế).
- #strong[`vlo:validityStatus`] · validity status · #emph[tình trạng
  hiệu lực]. Sub-property of `eli:in_force`\; domain
  `vlo:LegalDocument`\; range `vlo:ValidityStatus`\;
  `owl:FunctionalProperty`. The validity of a legal document as of the
  build date of the knowledge graph.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:changeEffectiveDate`] · change effective date ·
  #emph[ngày thay đổi có hiệu lực]. domain `vlo:LegalChange`\; range
  `xsd:date`. The date from which a legal change takes effect, normally
  the effective date of the acting document.
- #strong[`vlo:effectiveDate`] · effective date · #emph[ngày có hiệu
  lực]. Sub-property of `eli:first_date_entry_in_force`\; domain
  `vlo:LegalDocument`\; range `xsd:date`. The date on which a legal
  document enters into force (source metadata first, then the
  commencement article).
- #strong[`vlo:evidenceText`] · evidence text · #emph[câu chứng cứ].
  domain `vlo:LegalChange`\; range `rdfs:Literal`. The operative
  sentence of the acting document from which the change was extracted,
  quoted in Vietnamese and cut at 300 characters.
- #strong[`vlo:expiryDate`] · expiry date · #emph[ngày hết hiệu lực].
  Sub-property of `eli:date_no_longer_in_force`\; domain
  `vlo:LegalDocument`\; range `xsd:date`. The date from which a legal
  document is no longer in force, from the source status or from the
  effective date of the replacing or repealing act.
- #strong[`vlo:isInForce`] · is in force · #emph[còn hiệu lực]. range
  `xsd:boolean`. True if the document or term is known to be in force,
  false if known not to be in force; absent when unknown.
- #strong[`vlo:mentionedDate`] · mentioned date · #emph[ngày được nêu].
  domain `vlo:LegalChange`\; range `xsd:date`. The issue date of the
  affected document as stated in the evidence sentence, when given; used
  to disambiguate numbers without a year.
- #strong[`vlo:ruleVersion`] · rule version · #emph[phiên bản bộ luật
  trích xuất]. domain `vlo:LegalChange`\; range `xsd:string`. The
  version of the extraction rules that produced a legal change (v7 in
  VLOnto 0.1.0).
- #strong[`vlo:sourceStatus`] · source status · #emph[tình trạng theo
  nguồn]. range `rdfs:Literal`. The validity status string as published
  by the source, in Vietnamese (for example 'Hết hiệu lực: 01/07/2025').
- #strong[`vlo:statusTextConflict`] · status-text conflict · #emph[mâu
  thuẫn trạng thái và văn bản]. domain `vlo:LegalDocument`\; range
  `xsd:boolean`. True when the source status says in force but an
  extracted relation says the document was replaced or repealed; such
  documents must be verified.
- #strong[`vlo:validityEvidenceSource`] · validity evidence source ·
  #emph[nguồn căn cứ hiệu lực]. domain `vlo:LegalDocument`\; range
  `xsd:string`. Which evidence determined the validity status: status,
  text, status+text or none.

#block(sticky: true, width: 100%)[
#strong[Annotation properties]

]
- #strong[`vlo:shortcutProperty`] · shortcut property · #emph[thuộc tính
  rút gọn]. Links a change kind to the direct document-to-document
  property that represents the same change.

#block(sticky: true, width: 100%)[
#strong[Concept schemes]

]
- #strong[`vlo:ChangeKindScheme`] · Change kinds · #emph[Loại thay đổi].
  The five kinds of legal change extracted by the validity rules v7.
  Concepts: amended; partially terminated; partially repealed; repealed;
  replaced.
- #strong[`vlo:ValidityStatusScheme`] · Validity statuses · #emph[Tình
  trạng hiệu lực]. The eight validity values computed by the validity
  rules v7 as of the knowledge-graph date. Concepts: no longer in force;
  in force; in force, amended; no longer applicable; not yet in force;
  presumed in force, amended; superseded; unknown.

== B.5 Module citation and legal basis (#emph[trích dẫn và căn cứ])
<b.5-module-citation-and-legal-basis-trích-dẫn-và-căn-cứ>
Legal-basis and citation links between legal resources and from other
works to legal resources.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:cites`] · cites · #emph[trích dẫn]. Sub-property of
  `eli:cites`, `vlo:refersTo`\; domain `eli:LegalResource`\; range
  `eli:LegalResource`. A legal document, or one of its articles, cites
  another legal document or a provision of it. Self-references and
  anaphoric references are not included.
- #strong[`vlo:citesParentLaw`] · cites parent law · #emph[trích dẫn
  luật gốc]. Sub-property of `vlo:cites`\; domain `eli:LegalResource`\;
  range `eli:LegalResource`. A citation that the source dataset marks as
  a reference to the parent law of the citing document, that is, the law
  the citing document details or implements.
- #strong[`vlo:isLegalBasisOf`] · is legal basis of · #emph[là căn cứ
  của]. domain `vlo:LegalDocument`\; range `vlo:LegalDocument`. Inverse
  of vlo:legalBasis. Not materialised in the RDF dumps.
- #strong[`vlo:legalBasis`] · legal basis · #emph[căn cứ pháp lý].
  Sub-property of `eli:based_on`, `vlo:refersTo`\; domain
  `vlo:LegalDocument`\; range `vlo:LegalDocument`\; inverse of
  `vlo:isLegalBasisOf`. The object document is a legal basis on which
  the subject document was issued, as listed in the 'Căn cứ …' recitals
  of its preamble or in the source's parent-acts field. The object never
  has a lower legal-force rank than the subject.
- #strong[`vlo:refersTo`] · refers to · #emph[dẫn chiếu]. Sub-property
  of `dcterms:references`. The most general VLOnto reference link: a
  work (legal document, provision, court decision, answer or news
  article) refers to a legal resource or judicial document. Specialised
  by the citation, basis, application and mention properties.

== B.6 Module judiciary (#emph[tư pháp])
<b.6-module-judiciary-tư-pháp>
Court decisions, judgments, precedents and their classification.
#emph[The terms of this module are populated from VLOnto 2.0 (court
datasets anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0
knowledge graph has no court data.] (#emph[Các khái niệm của mô-đun này
có dữ liệu từ VLOnto 2.0 (các bộ dữ liệu tòa án anle-toaan-gov-vn và
cbba-toaan-gov-vn); đồ thị tri thức VLOnto 1.0.0 chưa có dữ liệu tòa
án.])

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:CaseCategory`] · Case category · #emph[Loại vụ việc].
  Subclass of `skos:Concept`. The legal domain of a case: civil,
  criminal, administrative, commercial, labour, marriage and family,
  bankruptcy or economic. #emph[Scope: Its concepts are defined in the
  ontology; they classify court decisions, which are populated from
  VLOnto 2.0 (court datasets anle-toaan-gov-vn and cbba-toaan-gov-vn).
  VLOnto 1.0.0 has no court decisions.]
- #strong[`vlo:CourtDecision`] · Court decision · #emph[Bản án, quyết
  định của Tòa án]. Subclass of `vlo:JudicialDocument`\; disjoint with
  `vlo:Precedent`. A judgment or ruling issued by a court in a specific
  case, identified by its decision number (for example 38/2021/DS-PT),
  court and date. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:CourtLevel`] · Court level · #emph[Cấp Tòa án]. Subclass
  of `skos:Concept`. The level of a court in the court system: supreme,
  high, provincial, district or military. #emph[Scope: Its concepts are
  defined in the ontology; they classify court decisions, which are
  populated from VLOnto 2.0 (court datasets anle-toaan-gov-vn and
  cbba-toaan-gov-vn). VLOnto 1.0.0 has no court decisions.]
- #strong[`vlo:CourtRuling`] · Court ruling · #emph[Quyết định của Tòa
  án]. Subclass of `vlo:CourtDecision`. A decision of a court other than
  a judgment, for example recognising the parties' agreement or
  suspending a case. #emph[Scope: Populated from VLOnto 2.0 (court
  datasets anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0
  knowledge graph has no data for this term.]
- #strong[`vlo:InstanceLevel`] · Instance level · #emph[Cấp xét xử].
  Subclass of `skos:Concept`. The procedural stage at which a decision
  is made: first instance, appeal, cassation review or retrial review.
  #emph[Scope: Its concepts are defined in the ontology; they classify
  court decisions, which are populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn). VLOnto 1.0.0 has no court
  decisions.]
- #strong[`vlo:Judgment`] · Judgment · #emph[Bản án]. Subclass of
  `vlo:CourtDecision`\; disjoint with `vlo:CourtRuling`. A court
  decision that settles a case on its merits after a hearing (first
  instance, appeal, cassation or retrial). #emph[Scope: Populated from
  VLOnto 2.0 (court datasets anle-toaan-gov-vn and cbba-toaan-gov-vn);
  the VLOnto 1.0.0 knowledge graph has no data for this term.]
- #strong[`vlo:JudicialDocument`] · Judicial document · #emph[Văn bản
  của Tòa án]. Subclass of `schema:CreativeWork`\; disjoint with
  `vlo:LegalDocument`. A document produced in the judicial system: a
  court decision in a case or a published case-law precedent.
  #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:Precedent`] · Precedent · #emph[Án lệ]. Subclass of
  `vlo:JudicialDocument`. Reasoning or a ruling in a court decision that
  the Council of Judges of the Supreme People's Court has selected and
  the Chief Justice has published as a precedent for courts to follow;
  identified by its number, for example 04/2016/AL. #emph[Scope:
  Populated from VLOnto 2.0 (court datasets anle-toaan-gov-vn and
  cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge graph has no data for
  this term.]

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:appliesDocument`] · applies document · #emph[áp dụng văn
  bản]. Sub-property of `vlo:refersTo`\; domain `vlo:JudicialDocument`\;
  range `vlo:LegalDocument`. A court decision cites a legal document as
  a whole, or a provision of it that is not available as an article
  node. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:appliesPrecedent`] · applies precedent · #emph[áp dụng án
  lệ]. Sub-property of `vlo:citesCase`\; domain `vlo:JudicialDocument`\;
  range `vlo:Precedent`. A court decision cites a precedent by its
  number. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:appliesProvision`] · applies provision · #emph[áp dụng
  điều khoản]. Sub-property of `vlo:refersTo`\; domain
  `vlo:JudicialDocument`\; range `vlo:Provision`. A court decision cites
  an article, clause or point of a legal document as applied or relied
  on. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:caseCategory`] · case category · #emph[loại vụ việc].
  domain `vlo:JudicialDocument`\; range `vlo:CaseCategory`. The legal
  domain of the case decided or of the precedent. #emph[Scope: Populated
  from VLOnto 2.0 (court datasets anle-toaan-gov-vn and
  cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge graph has no data for
  this term.]
- #strong[`vlo:citesCase`] · cites case · #emph[viện dẫn bản án].
  Sub-property of `vlo:refersTo`\; domain `vlo:JudicialDocument`\; range
  `vlo:JudicialDocument`. A court decision refers to another court
  decision (for example the first-instance judgment under appeal) or to
  a precedent. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:courtLevel`] · court level · #emph[cấp Tòa án]. range
  `vlo:CourtLevel`. The level of the court that issued a decision, or of
  a court. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]
- #strong[`vlo:decidedBy`] · decided by · #emph[Tòa án ban hành].
  Sub-property of `dcterms:creator`\; domain `vlo:CourtDecision`\; range
  `vlo:Court`. The court that issued a court decision. #emph[Scope:
  Populated from VLOnto 2.0 (court datasets anle-toaan-gov-vn and
  cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge graph has no data for
  this term.]
- #strong[`vlo:instanceLevel`] · instance level · #emph[cấp xét xử].
  domain `vlo:CourtDecision`\; range `vlo:InstanceLevel`. The procedural
  stage at which a court decision was made. #emph[Scope: Populated from
  VLOnto 2.0 (court datasets anle-toaan-gov-vn and cbba-toaan-gov-vn);
  the VLOnto 1.0.0 knowledge graph has no data for this term.]
- #strong[`vlo:selectedFrom`] · selected from · #emph[được lựa chọn từ].
  Sub-property of `prov:wasDerivedFrom`\; domain `vlo:Precedent`\; range
  `vlo:CourtDecision`. The court decision whose reasoning or ruling was
  selected as the precedent. #emph[Scope: Populated from VLOnto 2.0
  (court datasets anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto
  1.0.0 knowledge graph has no data for this term.]

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:decisionCode`] · decision code · #emph[ký hiệu bản án,
  quyết định]. domain `vlo:CourtDecision`\; range `xsd:string`. The
  symbol part of a decision number that encodes case domain and stage,
  for example DS-PT (civil, appeal) or QĐST-HNGĐ (first-instance ruling,
  marriage and family). #emph[Scope: Populated from VLOnto 2.0 (court
  datasets anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0
  knowledge graph has no data for this term.]
- #strong[`vlo:decisionDate`] · decision date · #emph[ngày tuyên án, ra
  quyết định]. Sub-property of `dcterms:date`\; domain
  `vlo:CourtDecision`\; range `xsd:date`. The date on which a court
  decision was issued. #emph[Scope: Populated from VLOnto 2.0 (court
  datasets anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0
  knowledge graph has no data for this term.]
- #strong[`vlo:decisionNumber`] · decision number · #emph[số bản án,
  quyết định]. Sub-property of `dcterms:identifier`\; domain
  `vlo:CourtDecision`\; range `xsd:string`. The number of a court
  decision as issued, for example 38/2021/DS-PT. Numbers are unique only
  within one court. #emph[Scope: Populated from VLOnto 2.0 (court
  datasets anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0
  knowledge graph has no data for this term.]
- #strong[`vlo:precedentNumber`] · precedent number · #emph[số án lệ].
  Sub-property of `dcterms:identifier`\; domain `vlo:Precedent`\; range
  `xsd:string`. The national number of a precedent, for example
  04/2016/AL. #emph[Scope: Populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn); the VLOnto 1.0.0 knowledge
  graph has no data for this term.]

#block(sticky: true, width: 100%)[
#strong[Concept schemes]

]
- #strong[`vlo:CaseCategoryScheme`] · Case categories · #emph[Loại vụ
  việc]. Legal domains of cases as recorded by the court-decision
  datasets. Concepts: administrative; bankruptcy; civil; business and
  commercial; criminal; economic; labour; marriage and family.
  #emph[Scope: Its concepts are defined in the ontology; they classify
  court decisions, which are populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn). VLOnto 1.0.0 has no court
  decisions.]
- #strong[`vlo:CourtLevelScheme`] · Court levels · #emph[Cấp Tòa án].
  Levels of the Vietnamese court system as recorded by the
  court-decision datasets. Concepts: district court; High People's
  Court; military court; provincial court; Supreme People's Court.
  #emph[Scope: Its concepts are defined in the ontology; they classify
  court decisions, which are populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn). VLOnto 1.0.0 has no court
  decisions.]
- #strong[`vlo:InstanceLevelScheme`] · Instance levels · #emph[Cấp xét
  xử]. Procedural stages at which court decisions are made. Concepts:
  appeal; cassation review; first instance; retrial review. #emph[Scope:
  Its concepts are defined in the ontology; they classify court
  decisions, which are populated from VLOnto 2.0 (court datasets
  anle-toaan-gov-vn and cbba-toaan-gov-vn). VLOnto 1.0.0 has no court
  decisions.]

== B.7 Module legal Q&A (#emph[hỏi đáp pháp luật])
<b.7-module-legal-qa-hỏi-đáp-pháp-luật>
Published legal questions and their answers.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:LegalAnswer`] · Legal answer · #emph[Câu trả lời pháp
  luật]. Subclass of `schema:Answer`. The published answer to a legal
  question; in the knowledge graph it carries the citations of legal
  documents and provisions found in the answer, not its text.
- #strong[`vlo:LegalQuestion`] · Legal question · #emph[Câu hỏi pháp
  luật]. Subclass of `schema:Question`\; disjoint with
  `vlo:LegalAnswer`. A published legal question from a legal Q&A
  service. The knowledge graph keeps its identifier, link, date and
  legal area, not its text.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:answerCitesDocument`] · answer cites document · #emph[câu
  trả lời trích dẫn văn bản]. Sub-property of `schema:citation`,
  `vlo:refersTo`\; domain `vlo:LegalAnswer`\; range `vlo:LegalDocument`.
  A legal answer cites a legal document by its number.
- #strong[`vlo:answerCitesProvision`] · answer cites provision ·
  #emph[câu trả lời trích dẫn điều khoản]. Sub-property of
  `schema:citation`, `vlo:refersTo`\; domain `vlo:LegalAnswer`\; range
  `vlo:Provision`. A legal answer cites an article, clause or point of a
  legal document.
- #strong[`vlo:hasAnswer`] · has answer · #emph[có câu trả lời].
  Sub-property of `schema:acceptedAnswer`\; domain `vlo:LegalQuestion`\;
  range `vlo:LegalAnswer`\; `owl:FunctionalProperty`. Links a legal
  question to its published answer.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:publishedDate`] · published date · #emph[ngày đăng].
  Sub-property of `dcterms:issued`\; range `xsd:date`. The date on which
  a question, answer or news article was published by its source.

== B.8 Module terminology (#emph[thuật ngữ])
<b.8-module-terminology-thuật-ngữ>
Legal terms organised as SKOS concepts.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:LegalTerm`] · Legal term · #emph[Thuật ngữ pháp lý].
  Subclass of `skos:Concept`. A term of Vietnamese legal language,
  organised as a SKOS concept with a Vietnamese preferred label, an
  English label (machine translation unless marked otherwise), a legal
  area, a status and related terms.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:relatedTerm`] · related term · #emph[thuật ngữ liên
  quan]. Sub-property of `skos:related`\; domain `vlo:LegalTerm`\; range
  `vlo:LegalTerm`\; `owl:SymmetricProperty`. A legal term listed by the
  source as related to another term.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:englishLabelSource`] · English label source · #emph[nguồn
  nhãn tiếng Anh]. domain `vlo:LegalTerm`\; range `xsd:string`.
  Provenance of the English label of a term: 'mt' for machine
  translation, 'site' for an English name given by the source site.
- #strong[`vlo:translationModel`] · translation model · #emph[mô hình
  dịch]. domain `vlo:LegalTerm`\; range `xsd:string`. Identifier of the
  model that machine-translated the English label, as recorded by the
  source dataset.

#block(sticky: true, width: 100%)[
#strong[Concept schemes]

]
- #strong[`vlo:LegalTermScheme`] · Vietnamese legal terminology ·
  #emph[Thuật ngữ pháp lý Việt Nam]. The glossary of legal terms derived
  from the terminology dataset; populated by the knowledge graph.

== B.9 Module news (#emph[tin tức])
<b.9-module-news-tin-tức>
Legal news and policy articles that mention legal documents.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:LegalNewsArticle`] · Legal news article · #emph[Bài viết
  tin tức pháp luật]. Subclass of `schema:NewsArticle`. A news, policy
  or advice article about law published by a legal information portal;
  the knowledge graph keeps its identifier, link, date, category and the
  legal documents it mentions.
- #strong[`vlo:NewsCategory`] · News category · #emph[Chuyên mục tin
  tức]. Subclass of `skos:Concept`. A section of a legal news portal,
  such as new policies or real estate.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:mentionsDocument`] · mentions document · #emph[nhắc đến
  văn bản]. Sub-property of `schema:mentions`, `vlo:refersTo`\; domain
  `vlo:LegalNewsArticle`\; range `vlo:LegalDocument`. A news article
  mentions a legal document by its number.
- #strong[`vlo:newsCategory`] · news category · #emph[chuyên mục].
  domain `vlo:LegalNewsArticle`\; range `vlo:NewsCategory`. The section
  of the portal in which a news article was published.

#block(sticky: true, width: 100%)[
#strong[Concept schemes]

]
- #strong[`vlo:NewsCategoryScheme`] · News categories · #emph[Chuyên mục
  tin tức]. Sections of the legal news portal; populated by the
  knowledge graph.

== B.10 Module classification (#emph[phân loại])
<b.10-module-classification-phân-loại>
Concept schemes for legal areas, document types and legal-force ranks.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:DocumentType`] · Document type · #emph[Loại văn bản].
  Subclass of `eli:ResourceType`, `skos:Concept`. A type of legal
  document, such as law, decree or circular; used as the value of
  eli:type\_document.
- #strong[`vlo:LegalArea`] · Legal area · #emph[Lĩnh vực pháp luật].
  Subclass of `skos:Concept`. A subject area of law used to classify
  documents, questions and terms, such as labour and wages or real
  estate.
- #strong[`vlo:LegalForceRank`] · Legal-force rank · #emph[Thứ bậc hiệu
  lực pháp lý]. Subclass of `skos:Concept`. A level in the hierarchy of
  legal force of Vietnamese normative documents, from the Constitution
  (level 0, highest) to circulars and ministerial decisions (level 5,
  lowest). An act cannot replace, repeal or amend an act of a higher
  level.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:legalArea`] · legal area · #emph[lĩnh vực]. Sub-property
  of `dcterms:subject`\; range `vlo:LegalArea`. The legal area under
  which a document, question or term is classified by its source.
- #strong[`vlo:legalForceRank`] · legal-force rank · #emph[thứ bậc hiệu
  lực]. domain `vlo:LegalDocument`\; range `vlo:LegalForceRank`\;
  `owl:FunctionalProperty`. The level of a legal document in the
  hierarchy of legal force, derived from its type and issuer (rule 5 of
  the validity rules v7).

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:rankLevel`] · rank level · #emph[bậc]. domain
  `vlo:LegalForceRank`\; range `xsd:integer`. The numeric level of a
  legal-force rank: 0 is the highest (Constitution), 5 the lowest.

#block(sticky: true, width: 100%)[
#strong[Annotation properties]

]
- #strong[`vlo:typeConcept`] · type concept · #emph[khái niệm loại văn
  bản]. Links a VLOnto document class to the concept of the DocumentType
  scheme that represents the same document type, so that class
  membership and the eli:type\_document value can be kept in step.

#block(sticky: true, width: 100%)[
#strong[Concept schemes]

]
- #strong[`vlo:DocumentTypeScheme`] · Document types · #emph[Loại văn
  bản]. The ten types of normative legal documents in scope of VLOnto
  0.1.0. Concepts: Circular; Code; Constitution; Decision; Decree; Joint
  circular; Joint resolution; Law; Ordinance; Resolution.
- #strong[`vlo:LegalAreaScheme`] · Legal areas (documents and Q&A) ·
  #emph[Lĩnh vực pháp luật (văn bản và hỏi đáp)]. The 27 legal areas
  used by the document and Q&A datasets; populated by the knowledge
  graph.
- #strong[`vlo:LegalForceRankScheme`] · Legal-force ranks · #emph[Thứ
  bậc hiệu lực pháp lý]. Six levels of legal force used by the validity
  rules (rule 5) and as the vertical layer of the 3D legal network.
  Concepts: Constitution; Codes, laws and National Assembly resolutions;
  Ordinances and Standing Committee resolutions; Decrees, joint
  resolutions and other resolutions; Prime Minister decisions;
  Circulars, joint circulars and other decisions.
- #strong[`vlo:TermAreaScheme`] · Legal areas (terminology) · #emph[Lĩnh
  vực pháp luật (thuật ngữ)]. The legal areas used by the terminology
  dataset; areas with the same name as a document area are the same
  concept. Populated by the knowledge graph.

== B.11 Module provenance (#emph[nguồn gốc])
<b.11-module-provenance-nguồn-gốc>
Source datasets, extraction methods, edge sets and build activities.

#block(sticky: true, width: 100%)[
#strong[Classes]

]
- #strong[`vlo:BuildActivity`] · Build activity · #emph[Lần xây dựng đồ
  thị]. Subclass of `prov:Activity`. One run of the VLOnto build
  pipeline that generated the knowledge-graph tables and RDF dumps.
- #strong[`vlo:EdgeSet`] · Edge set · #emph[Tập liên kết]. Subclass of
  `prov:Entity`. The set of all knowledge-graph links of one property
  produced from one source, described with its size, the extraction
  methods used and the build that generated it. Per-link methods are
  kept in the parquet edge tables.
- #strong[`vlo:ExtractionMethod`] · Extraction method · #emph[Phương
  pháp trích xuất]. Subclass of `prov:Plan`, `skos:Concept`. A
  documented procedure that produced records or links of the knowledge
  graph, for example a rule set or a resolver strategy.
- #strong[`vlo:Module`] · Module · #emph[Mô-đun bản thể]. Subclass of
  `skos:Concept`. A thematic group of VLOnto terms, such as documents,
  provisions or judiciary.
- #strong[`vlo:SourceDataset`] · Source dataset · #emph[Bộ dữ liệu
  nguồn]. Subclass of `prov:Entity`. A published dataset, pinned to a
  revision, from which knowledge-graph records were derived; carries its
  licence and attribution text.

#block(sticky: true, width: 100%)[
#strong[Object properties]

]
- #strong[`vlo:edgeProperty`] · edge property · #emph[thuộc tính liên
  kết]. domain `vlo:EdgeSet`. The property used by all links of an edge
  set.
- #strong[`vlo:extractionMethod`] · extraction method · #emph[phương
  pháp trích xuất]. range `vlo:ExtractionMethod`. The extraction method
  that produced a legal change or the links of an edge set.
- #strong[`vlo:sourceDataset`] · source dataset · #emph[bộ dữ liệu
  nguồn]. Sub-property of `dcterms:source`\; range `vlo:SourceDataset`.
  The source dataset from which a knowledge-graph record was derived.

#block(sticky: true, width: 100%)[
#strong[Datatype properties]

]
- #strong[`vlo:attributionText`] · attribution text · #emph[lời ghi
  nguồn]. domain `vlo:SourceDataset`\; range `rdfs:Literal`. The
  attribution that must accompany material derived from the dataset.
- #strong[`vlo:datasetRevision`] · dataset revision · #emph[phiên bản bộ
  dữ liệu]. domain `vlo:SourceDataset`\; range `xsd:string`. The commit
  hash of the dataset revision that was used.
- #strong[`vlo:edgeCount`] · edge count · #emph[số liên kết]. domain
  `vlo:EdgeSet`\; range `xsd:integer`. The number of links in an edge
  set.
- #strong[`vlo:inclusionPolicy`] · inclusion policy · #emph[chính sách
  sử dụng]. domain `vlo:SourceDataset`\; range `rdfs:Literal`. What
  VLOnto takes from the dataset and what it leaves out, following the
  dataset licence.
- #strong[`vlo:licenceLabel`] · licence label · #emph[nhãn giấy phép].
  domain `vlo:SourceDataset`\; range `xsd:string`. The licence
  identifier given in the card of the source dataset, for example
  cc-by-4.0 or other.
- #strong[`vlo:softwareVersion`] · software version · #emph[phiên bản
  phần mềm]. domain `vlo:BuildActivity`\; range `xsd:string`. The
  version of the VLOnto build code used by a build activity.
- #strong[`vlo:sourceId`] · source identifier · #emph[mã trong nguồn].
  Sub-property of `dcterms:identifier`\; range `xsd:string`. The
  identifier of the record in its source dataset (for example the vbpl
  document id 333670 or the cbba doc\_name).
- #strong[`vlo:sourceUrl`] · source URL · #emph[đường dẫn nguồn].
  Sub-property of `schema:url`\; range `xsd:anyURI`. The web address of
  the record at its original publisher, where its full text can be read.
- #strong[`vlo:validityAsOf`] · validity as of · #emph[hiệu lực tính đến
  ngày]. domain `vlo:BuildActivity`\; range `xsd:date`. The reference
  date at which document validity was computed.

#block(sticky: true, width: 100%)[
#strong[Annotation properties]

]
- #strong[`vlo:module`] · module · #emph[mô-đun]. range `vlo:Module`.
  The thematic module of VLOnto to which a class, property or concept
  scheme belongs; used to group and colour terms in documentation and in
  the 3D ontology playground.

#block(sticky: true, width: 100%)[
#strong[Concept schemes]

]
- #strong[`vlo:ExtractionMethodScheme`] · Extraction methods ·
  #emph[Phương pháp trích xuất]. Procedures that produced VLOnto records
  and links; the notation is the value used in the method columns of the
  parquet edge tables. Concepts: answer text, name; answer text, number;
  case number and court; case number and date; article parser; citation
  field, name; Constitution in the preamble; court name; document-number
  key; document-number pattern; issuer code; law name and year;
  parent-acts field; preamble citation; precedent number; source
  metadata; unique document of type; validity rules v7.
- #strong[`vlo:ModuleScheme`] · VLOnto modules · #emph[Các mô-đun của
  VLOnto]. The eleven thematic modules of VLOnto. Concepts: agents;
  citation and legal basis; classification; documents; judiciary; news;
  provenance; provisions; legal Q&A; terminology; validity and change.

= Appendix C. Data dictionary
<appendix-c.-data-dictionary>
Generated from `kg/data_dictionary.json`. "Non-null" counts the rows
with a value. The table marked local-only is written by the build for
local use only and is never shared (Appendix~D).

== C.1 `documents` (40,816 rows)
<c.1-documents-40816-rows>
#block(sticky: true, width: 100%)[
Legal documents (40,816 in-scope normative documents from vbpl, after
cleaning).

]
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`doc_id`], [String], [40,816], [vbpl document id (primary key)],
    [`iri`], [String], [40,816], [VLOnto IRI],
    [`doc_type_vi`], [String], [40,816], [Vietnamese document type],
    [`doc_class`], [String], [40,816], [VLOnto class local name (Law,
    Decree, …)],
    [`doc_type_code`], [String], [40,816], [type notation (L, NĐ, TT,
    …)],
    [`doc_number`], [String], [40,215], [official number,
    e.g.~45/2019/QH14 (null for 601 documents)],
    [`doc_number_key`], [String], [40,215], [normalised lookup key],
    [`title_vi`], [String], [40,816], [Vietnamese title],
    [`title_core`], [String], [36,984], [title without the type word
    (used for name resolution)],
    [`issue_date`], [String], [40,502], [issue date (ISO); null when it
    is more than one year away from the year in the number],
    [`issue_date_check`], [String], [40,816], [ok, missing or
    year\_mismatch\_with\_number],
    [`issue_date_source`], [String], [144], [source issue date when it
    was rejected],
    [`year`], [Int64], [40,720], [issue year (from the number when the
    date was rejected)],
    [`effective_date`], [String], [22,076], [entry into force (metadata,
    then text)],
    [`effective_date_src`], [String], [22,076], [source of
    effective\_date],
    [`expiry_date`], [String], [7,256], [no longer in force from],
    [`status_raw`], [String], [4,356], [source status string
    (Vietnamese)],
    [`status_code`], [String], [4,356], [normalised source status],
    [`status_date`], [String], [2,207], [date in the status string],
    [`validity`], [String], [40,816], [validity v7 (8 values)],
    [`in_force`], [Boolean], [12,156], [true/false/null],
    [`status_text_conflict`], [Boolean], [40,816], [source says in force
    but text says superseded],
    [`validity_evidence`], [String], [40,816], [status / text /
    status+text / none],
    [`legal_force_rank`], [Int64], [40,816], [0 (Constitution) .. 5
    (circulars)],
    [`area_id`], [String], [40,816], [legal area slug],
    [`issuer_ids`], [List(String)], [40,816], [canonical issuer codes
    (joint documents have several)],
    [`issuer_method`], [String], [40,816], [issuer-code (symbol of the
    number), doc-type-rule (laws, codes, constitutions -\> QH;
    ordinances), source-metadata, code-unknown, none],
    [`issuer_codes_unmatched`], [List(String)], [40,816], [symbol parts
    of the number that are not a known issuer (kept for transparency, no
    node)],
    [`tier`], [Int64], [40,816], [vbpl tier (0 primary legislation, 1
    central decisions)],
    [`url`], [String], [40,816], [source URL (thuvienphapluat.vn)],
    [`n_chapters`], [Int64], [40,816], [chapters found by the parser],
    [`has_articles`], [Boolean], [40,816], [article structure parsed],
    [`source_dataset`], [String], [40,816], [source dataset],
    [`n_articles_main`], [UInt32], [40,816], [main-body articles],
    [`n_articles_appendix`], [UInt32], [40,816], [appendix articles],
  )]
  , kind: table
  )

== C.2 `articles` (436,309 rows)
<c.2-articles-436309-rows>
#block(sticky: true, width: 100%)[
Articles (Điều): one node per main-body or appendix article; parts of
split articles joined. No text (licence).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`article_id`], [String], [436,309], [\<doc\_id\>::dieu-\<n\> or
    \<doc\_id\>::att\<s\>-dieu-\<n\> (chunk unit id)],
    [`iri`], [String], [436,309], [VLOnto IRI],
    [`doc_id`], [String], [436,309], [document],
    [`article_no`], [String], [436,309], [article number as printed (5,
    5a)],
    [`segment`], [String], [436,309], [main or att\<s\> (appendix s)],
    [`heading`], [String], [349,840], [article heading (\<=200 chars)],
    [`parent_id`], [String], [436,309], [immediate parent (structure id
    or doc\_id)],
    [`parent_kind`], [String], [436,309], [Document/Appendix/Part/Chapter/Section],
    [`position`], [Int64], [436,309], [order of the article in its
    document],
    [`n_chunks`], [Int64], [436,309], [retrieval chunks of the article],
    [`chars`], [Int64], [436,309], [characters of text],
    [`chapter_heading`], [String], [315,885], [chapter heading],
    [`section_heading`], [String], [82,344], [section heading],
  )]
  , kind: table
  )

]
== C.3 `structure` (73,925 rows)
<c.3-structure-73925-rows>
#block(sticky: true, width: 100%)[
Appendices, parts, chapters and sections of documents.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`struct_id`], [String], [73,925], [\<doc\_id\>::\<path\>
    e.g.~333670::chuong-iii/muc-3],
    [`doc_id`], [String], [73,925], [document],
    [`kind`], [String], [73,925], [Appendix/Part/Chapter/Section],
    [`number`], [String], [73,925], [number token (iii, 3) or o\<k\>
    when not parsable],
    [`heading`], [String], [73,234], [heading (\<=200 chars)],
    [`parent_id`], [String], [73,925], [parent node],
    [`parent_kind`], [String], [73,925], [kind of parent],
    [`position`], [Int64], [73,925], [order among nodes of this kind in
    the document],
    [`iri`], [String], [73,925], [VLOnto IRI],
  )]
  , kind: table
  )

]
== C.4 `provisions_ref` (48,031 rows)
<c.4-provisions_ref-48031-rows>
#block(sticky: true, width: 100%)[
Clauses (khoản) and points (điểm) created because an edge refers to
them.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`prov_id`], [String], [48,031], [\<article\_id\>::khoan-\<k\>\[::diem-\<p\>\]
    or \<article\_id\>::diem-\<p\>],
    [`iri`], [String], [48,031], [VLOnto IRI],
    [`kind`], [String], [48,031], [Clause or Point],
    [`article_id`], [String], [48,031], [article],
    [`doc_id`], [String], [48,031], [document],
    [`clause`], [String], [47,957], [clause number],
    [`point`], [String], [12,555], [point letter],
    [`parent_id`], [String], [48,031], [article or clause],
    [`n_refs`], [Int64], [48,031], [edges that reference this
    provision],
  )]
  , kind: table
  )

]
== C.5 `issuers` (57 rows)
<c.5-issuers-57-rows>
#block(sticky: true, width: 100%)[
Issuing bodies identified by the symbol of the document number (curated
table; unknown symbols get no node).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`issuer_id`], [String], [57], [canonical ASCII code (BTC, TTG, QH,
    …)],
    [`iri`], [String], [57], [VLOnto IRI],
    [`label_vi`], [String], [57], [Vietnamese name],
    [`label_en`], [String], [57], [English name],
    [`kind`], [String], [57], [ministry, government, national-assembly,
    …],
    [`label_source`], [String], [57], [vlonto-table],
    [`code_aliases`], [List(String)], [57], [other symbols mapped to
    this body],
    [`n_documents`], [Int64], [57], [documents issued],
  )]
  , kind: table
  )

]
== C.6 `areas` (51 rows)
<c.6-areas-51-rows>
#block(sticky: true, width: 100%)[
Legal areas (SKOS concepts) from vbpl/hdpl (27) and tnpl.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`area_id`], [String], [51], [slug],
    [`iri`], [String], [51], [VLOnto IRI],
    [`label_vi`], [String], [51], [Vietnamese label],
    [`label_en`], [String], [51], [English label],
    [`label_en_source`], [String], [51], [vlonto (written for VLOnto) or
    tnpl-mt],
    [`schemes`], [List(String)], [51], [LegalAreaScheme and/or
    TermAreaScheme],
    [`n_documents`], [Int64], [51], [documents],
    [`n_qas`], [Int64], [51], [Q&As],
    [`n_terms`], [Int64], [51], [terms],
  )]
  , kind: table
  )

]
== C.7 `doc_types` (10 rows)
<c.7-doc_types-10-rows>
#block(sticky: true, width: 100%)[
Document types (concepts of the ontology).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`doc_type_vi`], [String], [10], [-],
    [`label_en`], [String], [10], [-],
    [`class`], [String], [10], [-],
    [`concept`], [String], [10], [-],
    [`notation`], [String], [10], [-],
    [`n_documents`], [Int64], [10], [-],
  )]
  , kind: table
  )

]
== C.8 `legal_force_ranks` (6 rows)
<c.8-legal_force_ranks-6-rows>
#block(sticky: true, width: 100%)[
Legal-force ranks (concepts of the ontology).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`rank`], [Int64], [6], [-],
    [`concept`], [String], [6], [-],
    [`label_en`], [String], [6], [-],
    [`label_vi`], [String], [6], [-],
    [`n_documents`], [Int64], [6], [-],
  )]
  , kind: table
  )

]
== C.9 `changes` (15,035 rows)
<c.9-changes-15035-rows>
#block(sticky: true, width: 100%)[
Legal change events (validity relations v7), one per relation.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`change_id`], [String], [15,035], [\<acting\>-\<kind\>-\<affected\>],
    [`iri`], [String], [15,035], [VLOnto IRI],
    [`acting_doc_id`], [String], [15,035], [acting (newer) document],
    [`affected_doc_id`], [String], [15,035], [affected document],
    [`kind`], [String], [15,035], [replaced/amended/repealed/partially\_repealed/partially\_expired],
    [`evidence`], [String], [15,035], [operative sentence (\<=300
    chars)],
    [`effective_date`], [String], [15,002], [effective date of the
    change],
    [`mentioned_date`], [String], [12,948], [date of the affected act in
    the sentence],
    [`acting_number`], [String], [14,913], [number of acting act],
    [`affected_number`], [String], [15,035], [number of affected act],
    [`affected_number_as_cited`], [String], [15,035], [number as
    written],
    [`method`], [String], [15,035], [validity-rules-v7],
    [`rule_version`], [String], [15,035], [v7],
  )]
  , kind: table
  )

]
== C.10 `edges_change` (15,035 rows)
<c.10-edges_change-15035-rows>
#block(sticky: true, width: 100%)[
Shortcut edges acting document -\> affected document (one per change
event).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`src_doc_id`], [String], [15,035], [acting document],
    [`dst_doc_id`], [String], [15,035], [affected document],
    [`kind`], [String], [15,035], [change kind],
    [`property`], [String], [15,035], [vlo property],
    [`change_id`], [String], [15,035], [event],
    [`method`], [String], [15,035], [validity-rules-v7],
  )]
  , kind: table
  )

]
== C.11 `edges_legal_basis` (99,038 rows)
<c.11-edges_legal_basis-99038-rows>
#block(sticky: true, width: 100%)[
Legal basis: citing document -\> basis document.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`src_doc_id`], [String], [99,038], [citing document],
    [`dst_doc_id`], [String], [99,038], [basis document],
    [`method`], [String], [99,038], [parent-acts, preamble-citation or
    constitution-preamble (first in this order when several apply)],
    [`methods`], [List(String)], [99,038], [all methods that found the
    edge],
    [`resolve_method`], [String], [99,038], [docnum-key or
    law-name-year],
    [`raw`], [String], [99,038], [reference as written],
  )]
  , kind: table
  )

]
== C.12 `edges_citation` (268,563 rows)
<c.12-edges_citation-268563-rows>
#block(sticky: true, width: 100%)[
vbpl citations (external, external\_mention, parent\_law,
parent\_law\_mention) resolved to documents/articles.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`src_doc_id`], [String], [268,563], [citing document],
    [`src_article_id`], [String], [133,431], [citing article when
    known],
    [`dst_doc_id`], [String], [268,563], [cited document],
    [`dst_article_id`], [String], [97,153], [cited article when given
    and present],
    [`clause`], [String], [56,649], [cited clause],
    [`point`], [String], [17,466], [cited point],
    [`kind`], [String], [268,563], [vbpl citation kind],
    [`n_mentions`], [UInt32], [268,563], [records merged into this
    edge],
    [`article_cited`], [String], [98,120], [article number written (even
    if absent)],
    [`source_location`], [String], [268,563], [where in the citing
    document],
    [`raw`], [String], [268,563], [citation as written (\<=200 chars)],
    [`method`], [String], [268,563], [docnum-key or law-name-year],
  )]
  , kind: table
  )

]
== C.13 `qas` (109,543 rows)
<c.13-qas-109543-rows>
#block(sticky: true, width: 100%)[
Legal Q&As from hdpl: metadata only (no question or answer text).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`qa_id`], [String], [109,543], [hdpl id],
    [`iri`], [String], [109,543], [question IRI],
    [`answer_iri`], [String], [109,543], [answer IRI],
    [`url`], [String], [109,543], [source URL],
    [`published_date`], [String], [109,543], [publication date],
    [`year`], [Int64], [109,543], [publication year],
    [`category`], [String], [109,482], [category slug],
    [`area_id`], [String], [109,482], [legal area],
    [`has_ad`], [Boolean], [109,543], [advertising flag of the source],
    [`n_citation_records`], [Int64], [109,543], [citation records],
    [`n_document_citations`], [Int64], [109,543], [document-level
    records],
    [`n_provision_citations`], [Int64], [109,543], [provision-level
    records],
    [`n_gold_articles`], [UInt32], [109,543], [articles linked (gold
    resolver)],
    [`n_documents_resolved`], [UInt32], [109,543], [documents linked by
    number],
  )]
  , kind: table
  )

]
== C.14 `edges_qa_article` (34,869 rows)
<c.14-edges_qa_article-34869-rows>
#block(sticky: true, width: 100%)[
Q&A answer -\> article (+clause, point) from the gold resolver
(gold\_all.parquet).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`qa_id`], [String], [34,869], [Q&A],
    [`dst_doc_id`], [String], [34,869], [document],
    [`dst_article_id`], [String], [34,869], [article],
    [`clause`], [String], [16,424], [clause],
    [`point`], [String], [3,221], [point],
    [`ref`], [String], [34,869], [reference as written],
    [`method`], [String], [34,869], [answer-text-number /
    answer-text-name / citation-field-name / unique-document-of-type],
    [`method_detail`], [String], [34,869], [gold method string],
  )]
  , kind: table
  )

]
== C.15 `edges_qa_document` (119,683 rows)
<c.15-edges_qa_document-119683-rows>
#block(sticky: true, width: 100%)[
Q&A answer -\> document cited by number.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`qa_id`], [String], [119,683], [Q&A],
    [`dst_doc_id`], [String], [119,683], [document],
    [`number_cited`], [String], [119,683], [number as written],
    [`law_type`], [String], [119,683], [law type],
    [`method`], [String], [119,683], [docnum-key],
  )]
  , kind: table
  )

]
== C.16 `terms` (16,701 rows)
<c.16-terms-16701-rows>
#block(sticky: true, width: 100%)[
Legal terms from tnpl (names only, no definitions).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`term_id`], [Int64], [16,701], [tnpl id],
    [`iri`], [String], [16,701], [VLOnto IRI],
    [`label_vi`], [String], [16,701], [Vietnamese term],
    [`label_en`], [String], [16,599], [English label],
    [`label_en_source`], [String], [16,599], [mt or site],
    [`translation_model`], [String], [15,426], [MT model],
    [`area_id`], [String], [16,700], [area slug],
    [`tnpl_area_id`], [Int64], [16,700], [tnpl area id],
    [`status_vi`], [String], [16,701], [status],
    [`in_force`], [Boolean], [16,701], [status as boolean],
    [`url`], [String], [16,701], [source URL],
  )]
  , kind: table
  )

]
== C.17 `edges_term_related` (17,615 rows)
<c.17-edges_term_related-17615-rows>
#block(sticky: true, width: 100%)[
Related terms.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`src_term_id`], [Int64], [17,615], [term],
    [`dst_term_id`], [Int64], [17,615], [related term],
    [`method`], [String], [17,615], [source-metadata],
  )]
  , kind: table
  )

]
== C.18 `news` (681 rows)
<c.18-news-681-rows>
#block(sticky: true, width: 100%)[
Legal news articles from htpl (no title or text).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`news_id`], [String], [681], [htpl id],
    [`iri`], [String], [681], [VLOnto IRI],
    [`url`], [String], [681], [source URL],
    [`category`], [String], [681], [category slug],
    [`published_date`], [String], [87], [date],
    [`year`], [Int64], [87], [year],
    [`n_numbers_found`], [Int64], [681], [document numbers found],
    [`n_documents_resolved`], [Int64], [681], [documents linked],
  )]
  , kind: table
  )

]
== C.19 `edges_news_document` (1,484 rows)
<c.19-edges_news_document-1484-rows>
#block(sticky: true, width: 100%)[
News article -\> mentioned document.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`news_id`], [String], [1,484], [news],
    [`dst_doc_id`], [String], [1,484], [document],
    [`number_found`], [String], [1,484], [number],
    [`method`], [String], [1,484], [docnum-regex],
  )]
  , kind: table
  )

]
== C.20 `news_categories` (7 rows)
<c.20-news_categories-7-rows>
#block(sticky: true, width: 100%)[
News categories.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`category`], [String], [7], [-],
    [`iri`], [String], [7], [-],
    [`label_vi`], [String], [7], [-],
    [`label_en`], [String], [7], [-],
    [`n_articles`], [Int64], [7], [-],
  )]
  , kind: table
  )

]
== C.21 `sources` (4 rows)
<c.21-sources-4-rows>
#block(sticky: true, width: 100%)[
Source datasets of this build with revision, licence and policy (release
v1: the four thuvienphapluat.vn datasets).

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`dataset`], [String], [4], [-],
    [`iri`], [String], [4], [-],
    [`revision`], [String], [4], [-],
    [`licence`], [String], [4], [-],
    [`publisher`], [String], [4], [-],
    [`content`], [String], [4], [-],
    [`repository`], [String], [4], [-],
    [`card_sha256`], [String], [4], [-],
  )]
  , kind: table
  )

]
== C.22 `article_text` (436,309 rows, local-only)
<c.22-article_text-436309-rows-local-only>
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (26.72%, 13.79%, 12.07%, 47.41%),
    align: (left,left,right,left,),
    table.header([Column], [Type], [Non-null], [Description],),
    table.hline(),
    [`article_id`], [String], [436,309], [-],
    [`text`], [String], [436,309], [-],
  )]
  , kind: table
  )

]
= Appendix D. Licences and attribution
<appendix-d.-licences-and-attribution>
#block(sticky: true, width: 100%)[
#strong[Sources.] Licence policy version 1.0.0 (release v1). Decided
2026-11-11 for 0.1.0 from the cards (`README.md`) of the source
datasets, downloaded at the pinned revisions below; revised 2026-11-12
for release v1, which is built from the four thuvienphapluat.vn datasets
only. The two court datasets (`anle-toaan-gov-vn`, `cbba-toaan-gov-vn`)
are planned for v2: v1 reads nothing from them, and their rules (policy
section~2.5) apply again when they are added (build switch
`VLONTO_INCLUDE_COURTS=1`). The policy is `docs/licence_policy.md`\; it
is a reading of the dataset cards by the build, not legal advice.

]
#block(breakable: false, width: 100%)[
#figure(
  align(center)[#table(
    columns: (43.97%, 19.83%, 36.21%),
    align: (left,left,left,),
    table.header([Dataset], [Card licence], [Original source],),
    table.hline(),
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-hdpl")[`tmquan/thuvienphapluat-vn-hdpl`]], [other], [thuvienphapluat.vn],
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-htpl")[`tmquan/thuvienphapluat-vn-htpl`]], [other], [thuvienphapluat.vn],
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-tnpl")[`tmquan/thuvienphapluat-vn-tnpl`]], [other], [thuvienphapluat.vn/tnpl],
    [#link("https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-vbpl")[`tmquan/thuvienphapluat-vn-vbpl`]], [cc-by-4.0], [thuvienphapluat.vn],
  )]
  , kind: table
  )

]
#strong[What the outputs contain.] The tables, the RDF dumps and the
website data hold metadata, titles, article and chapter headings (up to
200 characters), evidence sentences of change events (up to 300
characters), identifiers, URLs, dates, categories, term names and the
edges derived by VLOnto. They hold no article or document bodies, Q&A or
news text, glossary definitions or person names. The one exception is
the website's question traces page, which shows the published titles of
the questions it traces (section~9). The article text is kept in a
local-only table (`article_text`, 436,309 rows) that the build adds to
the articles table (`--with-article-text`) only if the owner decides
that sharing it is acceptable.

#block(sticky: true, width: 100%)[
#strong[Licence of the VLOnto outputs.]

]
- Ontology (`vlonto.ttl`, `vlonto-shapes.ttl`, documentation):
  #strong[CC BY 4.0], creator tmquan.
- Website Traces page data (`site/data/traces/`): VLOnto's traces,
  scores and drawings under #strong[CC BY 4.0]\; the titles of the 538
  traced questions it holds remain subject to the source terms of
  thuvienphapluat.vn (see policy section~2.2).
- Knowledge-graph tables and RDF dumps: VLOnto's own contributions
  (resolution, structure, derived edges, validity) are released under
  #strong[CC BY 4.0]\; records derived from the `other`-licensed sources
  (`hdpl`, `tnpl`, `htpl`) contain only identifiers, links, dates,
  categories, short labels and derived edges, and remain subject to the
  source terms of thuvienphapluat.vn.
- Every source dataset of the build is described in the graph as a
  `vlo:SourceDataset` with revision, licence IRI and attribution text,
  and every node carries `vlo:sourceDataset`. Release v1 describes the
  four thuvienphapluat.vn datasets; the court datasets appear from v2.

#block(sticky: true, width: 100%)[
#strong[Attribution] (use on the website, in the repository and in
derived work):

]
#quote(block: true)[
VLOnto is derived from four datasets published on Hugging Face by
TMQuan: `thuvienphapluat-vn-vbpl` (metadata CC BY 4.0; source
thuvienphapluat.vn), `thuvienphapluat-vn-hdpl`,
`thuvienphapluat-vn-tnpl` and `thuvienphapluat-vn-htpl` (source
thuvienphapluat.vn and thuvienphapluat.vn/tnpl/; only identifiers,
links, dates, categories, term names and derived links are used).
English term labels from `tnpl` are machine translations. Extracted
relations are produced automatically and may be wrong. VLOnto is not an
official legal text and is not legal advice.
]

#quote(block: true)[
VLOnto được xây dựng từ bốn bộ dữ liệu do TMQuan công bố trên Hugging
Face: `thuvienphapluat-vn-vbpl` (siêu dữ liệu theo CC BY 4.0; nguồn
thuvienphapluat.vn), `thuvienphapluat-vn-hdpl`,
`thuvienphapluat-vn-tnpl` và `thuvienphapluat-vn-htpl` (nguồn
thuvienphapluat.vn; chỉ dùng mã định danh, liên kết, ngày, lĩnh vực, tên
thuật ngữ và các liên kết suy ra). Tên tiếng Anh của thuật ngữ là bản
dịch máy. Các quan hệ được trích xuất tự động và có thể sai. VLOnto
không phải văn bản pháp luật chính thức và không phải tư vấn pháp lý.
]

#strong[Fonts and libraries.] The fonts of the PDF and the website are
under the SIL Open Font License 1.1 (licence files next to the fonts);
the vendored JavaScript libraries keep their own licences, listed per
file in `tools/vendor.lock.json`.

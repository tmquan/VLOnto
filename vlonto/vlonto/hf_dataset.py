"""Hugging Face dataset folder (not uploaded): $V/build/release/hf_dataset/

    kg/<table>.parquet (the publishable tables)   rdf/vlonto-kg.nt.gz, rdf/vlonto-core.ttl
    ontology/ (vlonto.ttl, vlonto-shapes.ttl, vlonto-context.jsonld, vlonto.html)
    docs/ (data_dictionary.md/.json, licence_policy.md, kg_report.md, checks.json)   README.md (dataset card)

kg_local/ (article text) is never copied. Node paths in the docs are replaced by relative ones. A content scan checks
that no table has a text/body column and counts person-name patterns. The README holds placeholders
<!-- OUTPUT:<name> --> that hf_snippets.py fills with the real output of the loading snippets, and writes SHA256SUMS.
"""
import glob
import json
import os
import re
import shutil
import time

import polars as pl

from . import config as C
from .nfc import nfc, nfc_obj

OUT = os.path.join(C.BUILD, "release", "hf_dataset")
REPO_ID = "tmquan/VLOnto"
SITE_URL = "https://tmquan.github.io/VLOnto/"
GITHUB_URL = "https://github.com/tmquan/VLOnto"
PAPER_TITLE = "Vietnamese Legal Ontology: Every legal answer, traced to the article that grounds it"
PAPER_AUTHORS = "Khac-Hoai Nam Bui, Quan Tran Minh"
PAPER_ARXIV = "2611.11426"
PAPER_URL = "https://arxiv.org/abs/2611.11426"
PAPER_BIBTEX = """@misc{bui2026vietnamese,
  title         = {Vietnamese Legal Ontology: Every legal answer, traced to the article that grounds it},
  author        = {Bui, Khac-Hoai Nam and Tran Minh, Quan},
  year          = {2026},
  eprint        = {2611.11426},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2611.11426}
}"""
RELEASE = f"VLOnto {C.VERSION} (this release)"
FORBIDDEN_COLUMNS = {"text", "body", "content", "markdown", "answer", "question", "definition", "summary", "vn_text", "en_text"}
# honorific + capitalised name (Ông Nguyễn Văn A); masked initials ('anh K', 'chị C') do not match (one capital letter only)
UP = "A-ZĐÂĂÊÔƠƯÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
LOW = "a-zđâăêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
NAME_RE = re.compile(rf"\b(?:[ÔôOo]ng|[Bb]à|[Aa]nh|[Cc]hị)\s+[{UP}][{LOW}]+(?:\s+[{UP}][{LOW}]+){{1,3}}")


def _sanitise(text):
    return (text.replace(f"(`V={C.V}`)", "").replace(C.KG_LOCAL, "kg_local").replace(C.KG, "kg")
                .replace(C.V, "$V").replace(C.R, "$R"))


def _mask(m):
    words = m.split()
    return " ".join([words[0]] + [w[0] + "." for w in words[1:]])


def content_scan(tables):
    rep = {"forbidden_columns": {}, "long_columns": {}, "name_pattern_hits": {}}
    for name, path in tables:
        df = pl.read_parquet(path)
        bad = sorted(set(df.columns) & FORBIDDEN_COLUMNS)
        if bad:
            rep["forbidden_columns"][name] = bad
        for c, dt in df.schema.items():
            if dt != pl.String:
                continue
            mx = df.select(pl.col(c).str.len_chars().max()).item() or 0
            if mx > 300:
                rep["long_columns"][f"{name}.{c}"] = int(mx)
            hits = df.filter(pl.col(c).str.contains(NAME_RE.pattern)).select(c)
            if hits.height:
                ex = [_mask(NAME_RE.search(v).group(0)) for v in hits[c].head(200).to_list() if NAME_RE.search(v)][:5]
                rep["name_pattern_hits"][f"{name}.{c}"] = {"rows": hits.height, "examples_masked": ex}
    return rep


def _dictionary(tables):
    js = json.load(open(os.path.join(C.KG, "data_dictionary.json"), encoding="utf-8"))
    keep = {n for n, _ in tables}
    out = {}
    md = ["# VLOnto knowledge-graph data dictionary", "",
          f"Version {C.VERSION}, built {C.BUILD_DATE}. Tables are parquet (zstd) files in `kg/`. The local-only article-text "
          "table of the build is not part of this dataset (licence policy).", "",
          "IRIs: documents `id/document/<doc_id>`, articles `id/document/<doc_id>/dieu-<n>`, clauses `.../khoan-<k>`, "
          "points `.../diem-<p>`, decisions `id/decision/<source>/<doc_name>`, courts `id/court/<slug>`, Q&As `id/qa/<id>` "
          "(answer `id/qa/<id>/answer`), terms `id/term/<id>`, news `id/news/<id>`, under https://tmquan.github.io/VLOnto/.", ""]
    for name, t in js.items():
        if name not in keep:
            continue
        path = os.path.join(OUT, "kg", name + ".parquet")
        t = dict(t, path=f"kg/{name}.parquet", bytes=os.path.getsize(path))
        out[name] = t
        md += [f"## `{name}` ({t['rows']:,} rows)", "", t["description"], "", "| Column | Type | Non-null | Description |", "|---|---|---|---|"]
        md += [f"| `{c['name']}` | {c['type']} | {c['non_null']:,} | {c['description']} |" for c in t["columns"]]
        md.append("")
    return out, "\n".join(md) + "\n"


def _yaml(tables, n_rows):
    size = next(lab for lim, lab in ((1e3, "n<1K"), (1e4, "1K<n<10K"), (1e5, "10K<n<100K"), (1e6, "100K<n<1M"), (1e7, "1M<n<10M"),
                                    (1e8, "10M<n<100M"), (1e9, "100M<n<1B")) if n_rows < lim)
    y = ["---", 'pretty_name: "VLOnto: Vietnamese Legal Ontology and Knowledge Graph"', "license: cc-by-4.0", "language:", "- vi", "- en",
         "tags:"] + [f"- {t}" for t in ("legal", "law", "knowledge-graph", "ontology", "rdf", "owl", "shacl", "linked-data", "vietnamese-law",
                                         "court-decisions", "legislation", "vietnam")]
    y += ["size_categories:", f"- {size}", "configs:"]
    for name, _ in tables:
        y += [f"- config_name: {name}", "  data_files:", "  - split: train", f"    path: kg/{name}.parquet"]
        if name == "documents":
            y.append("  default: true")
    y.append("---")
    return y


def _readme(tables, dd, n_rows, files, scan):
    lp = open(os.path.join(C.REPO, "docs", "licence_policy.md"), encoding="utf-8").read()
    attribution = lp[lp.index("## 4. Attribution text"):].split("\n", 1)[1].strip()
    review = json.load(open(os.path.join(C.REPO, "docs", "spot_check_review.json"), encoding="utf-8"))
    checks = json.load(open(os.path.join(C.REPORTS, "checks.json"), encoding="utf-8"))
    exp = json.load(open(os.path.join(C.REPORTS, "export_report.json"), encoding="utf-8"))
    core = json.load(open(os.path.join(C.REPORTS, "core_report.json"), encoding="utf-8"))
    ontc = json.load(open(os.path.join(C.REPORTS, "ontology_check.json"), encoding="utf-8"))
    kinds = ontc.get("completeness", {}).get("by_kind", {})
    mb = lambda b: f"{b / 1e6:,.1f} MB" if b >= 1e6 else f"{b / 1e3:,.1f} kB"
    L = _yaml(tables, n_rows) + [""]
    w = L.append
    w("# VLOnto: Vietnamese Legal Ontology and Knowledge Graph")
    w("")
    w("VLOnto is an OWL ontology and a knowledge graph of Vietnamese law. It links legal documents (Constitution, codes, laws, "
      "ordinances, decrees, circulars, decisions, resolutions), their articles, clauses and points, the changes between documents "
      "(replacement, amendment, repeal), legal-basis and citation links, court decisions with their courts (more than 1.5 million in "
      f"this release, VLOnto {C.VERSION}), the "
      "provisions they apply and the decisions or precedents they cite, legal Q&As, a legal glossary and legal news, each with its source "
      "and extraction method. The ontology reuses ELI (European Legislation Identifier) and SKOS and labels every term in English and Vietnamese.")
    w("")
    w(f"- Paper: *{PAPER_TITLE}*, {PAPER_AUTHORS}, arXiv:{PAPER_ARXIV}, {PAPER_URL}")
    w(f"- Website and interactive explorer: {SITE_URL}")
    w(f"- Code, ontology sources and build pipeline: {GITHUB_URL}")
    w("- Ontology namespace: `https://tmquan.github.io/VLOnto/ontology#` (prefix `vlo:`); instance IRIs under `https://tmquan.github.io/VLOnto/id/`")
    w(f"- Version {C.VERSION}, built {C.BUILD_DATE}; validity of documents as of {C.VALIDITY_AS_OF}.")
    w("")
    w(f"The approach is described in the paper above; numbers here are computed from the VLOnto {C.VERSION} release and can differ "
      "from the paper's.")
    w("")
    w("> **Licence.** VLOnto's own contributions (ontology, resolution, structure, derived links, validity) are released under "
      "**CC BY 4.0**. Records derived from the `thuvienphapluat-vn-hdpl`, `thuvienphapluat-vn-tnpl` and `thuvienphapluat-vn-htpl` "
      "datasets (tables `qas`, `edges_qa_article`, `edges_qa_document`, `terms`, `edges_term_related`, `news`, `edges_news_document`, "
      "`news_categories`) hold only identifiers, links, dates, categories, term names and derived links, and **remain subject to the "
      "terms of the source (thuvienphapluat.vn)**. No document or article body, Q&A or news text, glossary definition, judgment text "
      "or person name from the court records is included. VLOnto is not an official legal source and not legal advice.")
    w("")
    w("## Contents")
    w("")
    w(f"### Tables (`kg/`) — {RELEASE}: {len(tables)} parquet files, {n_rows:,} rows")
    w("")
    w("Each table is a configuration of this dataset (`load_dataset(\"" + REPO_ID + "\", \"<table>\")`). Full column descriptions: "
      "`docs/data_dictionary.md`.")
    w("")
    w("| Config / file | Rows | Description |")
    w("|---|---:|---|")
    for name, _ in tables:
        w(f"| `{name}` | {dd[name]['rows']:,} | {dd[name]['description']} |")
    w("")
    w(f"### RDF and ontology — {RELEASE}")
    w("")
    w("| File | Size | Content |")
    w("|---|---:|---|")
    w(f"| `rdf/vlonto-kg.nt.gz` | {mb(files['rdf/vlonto-kg.nt.gz'])} | The whole graph as N-Triples (gzip): {exp['triples_total']:,} triples, ontology included. |")
    w(f"| `rdf/vlonto-core.ttl` | {mb(files['rdf/vlonto-core.ttl'])} | Browser-sized Turtle subset: {core['triples']:,} triples (ontology, documents of legal-force rank <= {core['chosen_max_rank']} with their changes, legal basis and citations, issuers, areas, precedents, provenance). |")
    w(f"| `ontology/vlonto.ttl` | {mb(files['ontology/vlonto.ttl'])} | OWL ontology: {kinds.get('class', '-')} classes, {kinds.get('object_property', '-')} object properties, {kinds.get('datatype_property', '-')} datatype properties, SKOS concept schemes. |")
    w(f"| `ontology/vlonto-shapes.ttl` | {mb(files['ontology/vlonto-shapes.ttl'])} | SHACL shapes. |")
    w(f"| `ontology/vlonto-context.jsonld` | {mb(files['ontology/vlonto-context.jsonld'])} | JSON-LD context. |")
    w(f"| `ontology/vlonto.html` | {mb(files['ontology/vlonto.html'])} | Ontology documentation (pyLODE). |")
    w("")
    w("### Documentation (`docs/`)")
    w("")
    w("`data_dictionary.md` / `.json` (columns, types, non-null counts), `licence_policy.md` (what is republished from each source), "
      "`kg_report.md` (build and validation report, resolution rates, spot checks, limitations), `checks.json` (machine-readable "
      f"checks of {RELEASE}: {sum(1 for c in checks if c['result'] == 'pass')} of {len(checks)} pass). `SHA256SUMS` lists a checksum for every file.")
    w("")
    w("## Quick start")
    w("")
    w("The outputs below were produced by running the snippets on the build machine against a local copy of exactly these files "
      f"({RELEASE}; the `hf://` path / repository id replaced by the local folder).")
    w("")
    w("### DuckDB (no download needed)")
    w("")
    w("```python")
    w("import duckdb")
    w("base = \"hf://datasets/" + REPO_ID + "/kg\"")
    w("print(duckdb.sql(f\"\"\"")
    w("    SELECT doc_type_vi, COUNT(*) AS n")
    w("    FROM '{base}/documents.parquet'")
    w("    GROUP BY doc_type_vi ORDER BY n DESC LIMIT 5\"\"\"))")
    w("print(duckdb.sql(f\"\"\"")
    w("    SELECT c.court_kind, COUNT(*) AS decisions")
    w("    FROM '{base}/decisions.parquet' d JOIN '{base}/courts.parquet' c USING (court_id)")
    w("    GROUP BY c.court_kind ORDER BY decisions DESC\"\"\"))")
    w("```")
    w("")
    w("<!-- OUTPUT:duckdb -->")
    w("")
    w("### 🤗 Datasets (one configuration per table)")
    w("")
    w("```python")
    w("from datasets import load_dataset")
    w("courts = load_dataset(\"" + REPO_ID + "\", \"courts\", split=\"train\")")
    w("print(courts)")
    w("print(courts[0])")
    w("```")
    w("")
    w("<!-- OUTPUT:datasets -->")
    w("")
    w("### SPARQL with pyoxigraph over the full graph")
    w("")
    w("```python")
    w("import gzip")
    w("import pyoxigraph as ox")
    w("from huggingface_hub import hf_hub_download")
    w("")
    w("path = hf_hub_download(\"" + REPO_ID + "\", \"rdf/vlonto-kg.nt.gz\", repo_type=\"dataset\")")
    w("store = ox.Store(\"vlonto-store\")      # on-disk store; ox.Store() keeps the graph in memory")
    w("with gzip.open(path, \"rb\") as f:")
    w("    store.bulk_load(f, ox.RdfFormat.N_TRIPLES)")
    w("print(len(store), \"triples\")")
    w("query = \"\"\"PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>")
    w("SELECT ?number ?date WHERE {")
    w("  ?old vlo:documentNumber \"10/2012/QH13\" .        # Labour Code 2012")
    w("  ?change vlo:affectedDocument ?old ; vlo:changeKind vlo:change-replaced ; vlo:actingDocument ?new .")
    w("  OPTIONAL { ?change vlo:changeEffectiveDate ?date }")
    w("  ?new vlo:documentNumber ?number .")
    w("}\"\"\"")
    w("for row in store.query(query):")
    w("    print(\"replaced by\", row[\"number\"].value, \"effective\", row[\"date\"].value if row[\"date\"] else \"-\")")
    w("```")
    w("")
    w("<!-- OUTPUT:pyoxigraph -->")
    w("")
    w("## Licence and attribution")
    w("")
    w("Licence: CC BY 4.0 for VLOnto's contributions; records derived from `hdpl`, `tnpl` and `htpl` remain subject to the source "
      "terms (see the note above and `docs/licence_policy.md`). Please use this attribution text:")
    w("")
    w(attribution)
    w("")
    w(f"## Validation — {RELEASE}")
    w("")
    w("| Check | Result |")
    w("|---|---|")
    for c in checks:
        w(f"| {c['name']} | {c['result']} |")
    w("")
    w("Details and evidence: `docs/kg_report.md` and `docs/checks.json`.")
    w("")
    w(f"## Limitations — {RELEASE}")
    w("")
    for x in review.get("limitations", []):
        w(f"- {x}")
    w("")
    w("## Citation")
    w("")
    w(f"If you use VLOnto, please cite the paper ({PAPER_URL}):")
    w("")
    w("```bibtex")
    w(PAPER_BIBTEX)
    w("```")
    w("")
    w(f"To cite this dataset release (VLOnto {C.VERSION}):")
    w("")
    w("```bibtex")
    w("@misc{vlonto_2026,")
    w("  title        = {{VLOnto}: Vietnamese Legal Ontology and Knowledge Graph},")
    w("  author       = {TMQuan},")
    w("  year         = {2026},")
    w(f"  version      = {{{C.VERSION}}},")
    w("  howpublished = {\\url{https://huggingface.co/datasets/" + REPO_ID + "}},")
    w("  note         = {Ontology namespace https://tmquan.github.io/VLOnto/ontology\\#; code " + GITHUB_URL + "}")
    w("}")
    w("```")
    w("")
    return nfc("\n".join(L) + "\n")


def build_hf_dataset():
    t0 = time.time()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for d in ("kg", "rdf", "ontology", "docs"):
        os.makedirs(os.path.join(OUT, d))
    tables = [(os.path.basename(p)[:-8], p) for p in sorted(glob.glob(os.path.join(C.KG, "*.parquet")))]
    assert all(C.KG_LOCAL not in p for _, p in tables)
    for name, p in tables:
        shutil.copy2(p, os.path.join(OUT, "kg", name + ".parquet"))
    for fn in ("vlonto-kg.nt.gz", "vlonto-core.ttl"):
        shutil.copy2(os.path.join(C.RDF_DIR, fn), os.path.join(OUT, "rdf", fn))
    for fn in ("vlonto.ttl", "vlonto-shapes.ttl", "vlonto-context.jsonld", "vlonto.html"):
        shutil.copy2(os.path.join(C.REPO, "ontology", fn), os.path.join(OUT, "ontology", fn))
    dd, dd_md = _dictionary(tables)
    with open(os.path.join(OUT, "docs", "data_dictionary.json"), "w", encoding="utf-8") as f:
        json.dump(nfc_obj(dd), f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "docs", "data_dictionary.md"), "w", encoding="utf-8") as f:
        f.write(nfc(dd_md))
    for src, fn in ((os.path.join(C.REPO, "docs", "licence_policy.md"), "licence_policy.md"),
                    (os.path.join(C.REPORTS, "kg_report.md"), "kg_report.md"), (os.path.join(C.REPORTS, "checks.json"), "checks.json")):
        with open(os.path.join(OUT, "docs", fn), "w", encoding="utf-8") as f:
            f.write(nfc(_sanitise(open(src, encoding="utf-8").read())))
    n_rows = sum(dd[n]["rows"] for n, _ in tables)
    scan = content_scan([(n, os.path.join(OUT, "kg", n + ".parquet")) for n, _ in tables])
    files = {os.path.relpath(p, OUT): os.path.getsize(p) for p in glob.glob(os.path.join(OUT, "**", "*"), recursive=True) if os.path.isfile(p)}
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
        f.write(_readme(tables, dd, n_rows, files, scan))
    leftover = [p for p in glob.glob(os.path.join(OUT, "**", "*"), recursive=True) if os.path.isfile(p)
                and (os.path.abspath(C.V) in open(p, "rb").read().decode("utf-8", "ignore") if p.endswith((".md", ".json", ".ttl", ".jsonld", ".html")) else False)]
    rep = {"folder": OUT, "tables": len(tables), "rows": n_rows, "content_scan": scan, "files_with_node_paths": leftover,
           "wall_s": round(time.time() - t0, 1)}
    with open(os.path.join(C.REPORTS, "hf_dataset.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return rep

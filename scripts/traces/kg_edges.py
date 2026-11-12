#!/usr/bin/env python3
"""Derive the KG's Q&A -> article edges (edges_qa_article) from the rebuilt gold_all.parquet exactly as
vlonto/build_other.build_qa does, with the article table from vlonto/build_docs.build_articles.
Writes $TR/kg/{articles,structure,edges_qa_article,edges_qa_document,qas}.parquet and kg_edges_report.json.
Environment: TR (work folder), R (rebuilt corpus, read through vlonto.config), HF_LOCAL (downloaded shards)."""
import json, os, sys, time
import polars as pl
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("VLONTO_REPO_ROOT", os.path.dirname(os.path.dirname(HERE)))   # scripts/traces -> repository root
TR = os.environ["TR"]                                    # work folder: writes $TR/kg/
sys.path.insert(0, os.path.join(REPO, "vlonto"))
from vlonto import config as C
from vlonto import build_docs as BD
from vlonto import build_other as BO

def main():
    t0 = time.time(); rep = {}
    out = os.path.join(TR, "kg"); os.makedirs(out, exist_ok=True)
    arts, st, _ = BD.build_articles(None, rep, with_text=False)
    arts.write_parquet(os.path.join(out, "articles.parquet")); st.write_parquet(os.path.join(out, "structure.parquet"))
    d = pl.read_parquet(C.PROCESSED["docs_clean"], columns=["id", "doc_type", "doc_number", "doc_number_key", "title_core", "issue_date",
                                                            "effective_date_meta", "excluded_reason"]).filter(pl.col("excluded_reason").is_null())
    # build_documents: issue_date is dropped when it is > 1 year away from the year in the number; effective_date comes from
    # validity.py (not rebuilt here) -> the metadata effective date is used (DocResolver.by_number ignores it).
    rows = []
    import re
    for r in d.iter_rows(named=True):
        issue = r["issue_date"]; ny = re.search(r"/((?:19|20)\d{2})/", r["doc_number"] or "")
        if issue and ny and abs(int(issue[:4]) - int(ny.group(1))) > 1:
            issue = None
        rows.append({"doc_id": r["id"], "doc_type_vi": r["doc_type"], "doc_number": r["doc_number"], "doc_number_key": r["doc_number_key"],
                     "title_core": r["title_core"], "issue_date": issue, "effective_date": r["effective_date_meta"]})
    docs = pl.DataFrame(rows, infer_schema_length=None)
    C.snapshot = lambda name: os.environ["HF_LOCAL"] + "/" + name      # downloaded shards (same pinned revisions)
    qas, qa_art, qd = BO.build_qa(docs, arts, rep)
    qa_art.write_parquet(os.path.join(out, "edges_qa_article.parquet"))
    qd.write_parquet(os.path.join(out, "edges_qa_document.parquet"))
    qas.write_parquet(os.path.join(out, "qas.parquet"))
    rep["wall_s"] = round(time.time() - t0, 1)
    json.dump(rep, open(os.path.join(out, "kg_edges_report.json"), "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: rep[k] for k in ("articles_total", "articles_main", "qa", "gold_qas", "gold_edges_raw") if k in rep}, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()

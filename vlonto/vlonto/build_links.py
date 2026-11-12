"""Legal-basis and citation edges between in-scope documents, from the vbpl dataset.

Citation kinds kept: external, external_mention, parent_law, parent_law_mention (self and anaphora are skipped).
The citing side is the document, plus the citing main-body article when the source field names one
('khoản 2 Điều 5'). The cited side is resolved to a document by number (docnum_key) or by law type + name
(+ year), then to an article when 'dieu' is given and the article exists. Legal basis comes from the
parent_acts field and from citations located in the preamble, kept only when the cited document does not have
a lower legal-force rank and was not issued after the citing document. The Constitution carries no number, so the
source has no citation record for it: 'Căn cứ Hiến pháp ...' in the preamble (the text before Article 1) is linked
to the constitution named by year or amending resolution, else to the one in force on the citing document's date.
"""
import glob
import re
import time
import unicodedata
from collections import Counter

import polars as pl
import pyarrow.parquet as pq

from . import config as C
from .resolve import DocResolver, norm_article, norm_clause, norm_point

KINDS = ("external", "external_mention", "parent_law", "parent_law_mention")
SRC_ART = re.compile(r"Điều\s+(\d{1,4}[a-zđ]?)\b")


CONST_PAT = re.compile(r"căn\s+cứ\s+(?:vào\s+)?hiến\s+pháp([^;\n]{0,200})", re.I)
FIRST_ART = re.compile(r"\n\s*Điều\s+1\b|Điều\s+1\.")
CONST_YEAR = re.compile(r"năm\s+(1946|1959|1980|1992|2013)\b")
# resolutions amending a constitution -> year of the constitution they amend
CONST_AMENDED_BY = {"51/2001/QH10": "1992", "203/2025/QH15": "2013"}


def constitution_basis(docs, meta):
    """Legal-basis rows citing the Constitution from the preamble text of docs_clean."""
    consts = (docs.filter(pl.col("doc_type_vi") == "Hiến pháp").select("doc_id", "issue_date", "effective_date")
                  .filter(pl.col("issue_date").is_not_null()).sort("issue_date").to_dicts())
    st, rows = Counter(), []
    if not consts:
        return rows, st
    by_year = {c["issue_date"][:4]: c["doc_id"] for c in consts}
    pf = pq.ParquetFile(C.PROCESSED["docs_clean"])
    for batch in pf.iter_batches(columns=["id", "text"], batch_size=2000):
        for i, txt in zip(batch.column("id").to_pylist(), batch.column("text").to_pylist()):
            i = str(i)
            if i not in meta or not txt or meta[i]["doc_type_vi"] == "Hiến pháp":
                continue
            cut = FIRST_ART.search(txt)
            pre = unicodedata.normalize("NFC", txt[: cut.start()] if cut else txt[:3000])
            m = CONST_PAT.search(pre)
            if not m:
                continue
            st["preamble_mentions"] += 1
            tail = m.group(1)
            y = CONST_YEAR.search(tail)
            amend = next((v for k, v in CONST_AMENDED_BY.items() if k in tail), None)
            if y:
                target, how = by_year.get(y.group(1)), "year-in-text"
            elif amend:
                target, how = by_year.get(amend), "amending-resolution"
            else:
                at = meta[i]["issue_date"] or meta[i]["effective_date"]
                target, how = None, "in-force-at-issue-date"
                for c in consts:
                    start = c["effective_date"] or c["issue_date"]
                    if at and start <= at:
                        target = c["doc_id"]
            if target is None:
                st["unresolved"] += 1
                continue
            ti, si = meta[target]["issue_date"], meta[i]["issue_date"]
            if ti and si and ti > si:
                st["dropped_issued_later"] += 1
                continue
            st["kept:" + how] += 1
            rows.append({"src_doc_id": i, "dst_doc_id": target, "method": "constitution-preamble", "resolve_method": how,
                         "raw": C.cut(re.sub(r"\s+", " ", m.group(0)).strip(), 200)})
    return rows, st


def resolver_from_docs(docs):
    return DocResolver(docs.select("doc_id", "doc_type_vi", "doc_number", "doc_number_key", "title_core", "issue_date",
                                   "effective_date").rename({"doc_type_vi": "doc_type"}).to_dicts())


def build_links(docs, arts, rep):
    t0 = time.time()
    res = resolver_from_docs(docs)
    main_art = set(arts.filter(pl.col("segment") == "main").select("doc_id", "article_no").iter_rows())
    meta = {r["doc_id"]: r for r in docs.select("doc_id", "issue_date", "effective_date", "legal_force_rank", "doc_type_vi").iter_rows(named=True)}
    # version of a law cited by name: the one in force when the citing document takes effect (a circular signed on
    # 30 June that implements a law in force from 1 July cites the new law); falls back to the issue date
    anchor = {d: max(x for x in (m["issue_date"], m["effective_date"]) if x) if (m["issue_date"] or m["effective_date"]) else None
              for d, m in meta.items()}
    ins = list(meta)
    fs = sorted(glob.glob(f"{C.snapshot('thuvienphapluat-vn-vbpl')}/**/documents-*.parquet", recursive=True))
    rep["vbpl_files"] = len(fs)
    v = pl.concat([pl.read_parquet(f, columns=["id", "parent_acts", "citations"]).filter(pl.col("id").is_in(ins)) for f in fs])
    rep["vbpl_inscope_rows"] = v.height
    # ------------------------------------------------ citations
    c = v.select(pl.col("id").alias("src_doc_id"), "citations").explode("citations").unnest("citations")
    rep["citation_records_inscope"] = c.height
    rep["citation_records_by_kind"] = dict(Counter(c["kind"].to_list()))
    c = c.filter(pl.col("kind").is_in(KINDS))
    raw_by_kind, res_doc_by_kind, res_art_by_kind, reasons = Counter(), Counter(), Counter(), Counter()
    methods = Counter()
    rows = []
    for r in c.iter_rows(named=True):
        k = r["kind"]
        raw_by_kind[k] += 1
        src = r["src_doc_id"]
        at = (meta[src]["issue_date"], anchor[src])
        text = r["target"] or r["raw"]
        d, how, parsed = res.resolve_reference(text, at=at)
        if d is None and r["raw"] and r["raw"] != text:
            d, how, parsed = res.resolve_reference(r["raw"], at=at)
        if d is None:
            reasons[(k, how)] += 1
            continue
        if d == src:
            reasons[(k, "resolved_to_citing_document")] += 1
            continue
        res_doc_by_kind[k] += 1
        methods[(k, how)] += 1
        src_art = None
        if r["source"]:
            ms = SRC_ART.findall(r["source"])
            if ms:
                a = norm_article(ms[-1])
                if a and (src, a) in main_art:
                    src_art = f"{src}::dieu-{a}"
        dst_art, art_no = None, norm_article(r["dieu"])
        if art_no:
            if (d, art_no) in main_art:
                dst_art = f"{d}::dieu-{art_no}"
                res_art_by_kind[k] += 1
            else:
                reasons[(k, "article_not_in_document")] += 1
        rows.append({"src_doc_id": src, "src_article_id": src_art, "dst_doc_id": d, "dst_article_id": dst_art,
                     "article_cited": art_no, "clause": norm_clause(r["khoan"]) if dst_art else None,
                     "point": norm_point(r["diem"]) if dst_art else None, "kind": k, "source_location": r["source"],
                     "raw": C.cut(r["raw"], 200), "method": how})
    S = pl.Utf8
    cit = pl.DataFrame(rows, infer_schema_length=None, schema_overrides={"src_article_id": S, "dst_article_id": S, "article_cited": S,
                                                                        "clause": S, "point": S, "source_location": S, "raw": S})
    keys = ["src_doc_id", "src_article_id", "dst_doc_id", "dst_article_id", "clause", "point", "kind"]
    cit = (cit.group_by(keys, maintain_order=True)
              .agg(pl.len().alias("n_mentions"), pl.col("article_cited").first(), pl.col("source_location").first(),
                   pl.col("raw").first(), pl.col("method").first()))
    rep["citations"] = {
        "raw_records_by_kind": dict(raw_by_kind), "resolved_to_document_by_kind": dict(res_doc_by_kind),
        "resolved_to_article_by_kind": dict(res_art_by_kind),
        "resolution_rate_by_kind": {k: round(res_doc_by_kind[k] / raw_by_kind[k], 4) for k in raw_by_kind},
        "methods": {f"{a}|{b}": n for (a, b), n in methods.items()},
        "unresolved_reasons": {f"{a}|{b}": n for (a, b), n in sorted(reasons.items(), key=lambda x: -x[1])},
        "edges_after_dedupe": cit.height,
        "edges_document_level": int(cit["dst_article_id"].is_null().sum()),
        "edges_article_level": int(cit["dst_article_id"].is_not_null().sum()),
        "edges_with_citing_article": int(cit["src_article_id"].is_not_null().sum()),
        "distinct_document_pairs": cit.select("src_doc_id", "dst_doc_id").unique().height,
    }
    # ------------------------------------------------ legal basis
    basis = []
    pa = v.select(pl.col("id").alias("src_doc_id"), "parent_acts").explode("parent_acts").drop_nulls("parent_acts")
    pa_stats = Counter()
    for r in pa.iter_rows(named=True):
        src = r["src_doc_id"]
        pa_stats["raw"] += 1
        d, how, parsed = res.resolve_reference(r["parent_acts"], at=(meta[src]["issue_date"], anchor[src]))
        if d is None or d == src:
            pa_stats["unresolved:" + str(how if d is None else "self")] += 1
            continue
        pa_stats["resolved"] += 1
        basis.append({"src_doc_id": src, "dst_doc_id": d, "method": "parent-acts", "resolve_method": how, "raw": C.cut(r["parent_acts"], 200)})
    pre = cit.filter(pl.col("source_location") == "preamble")
    pre_stats = Counter()
    for r in pre.iter_rows(named=True):
        s, d = r["src_doc_id"], r["dst_doc_id"]
        pre_stats["preamble_citation_edges"] += 1
        ms, md = meta[s], meta[d]
        if md["legal_force_rank"] > ms["legal_force_rank"]:
            pre_stats["dropped_lower_rank"] += 1
            continue
        if ms["issue_date"] and md["issue_date"] and md["issue_date"] > ms["issue_date"]:
            pre_stats["dropped_issued_later"] += 1
            continue
        pre_stats["kept"] += 1
        basis.append({"src_doc_id": s, "dst_doc_id": d, "method": "preamble-citation", "resolve_method": r["method"], "raw": r["raw"]})
    crow, cst = constitution_basis(docs, meta)
    basis += crow
    b = pl.DataFrame(basis, infer_schema_length=None)
    b = (b.with_columns(pl.when(pl.col("method") == "parent-acts").then(0).otherwise(1).alias("_p"))
          .sort(["src_doc_id", "dst_doc_id", "_p"])
          .group_by(["src_doc_id", "dst_doc_id"], maintain_order=True)
          .agg(pl.col("method").first(), pl.col("method").unique().sort().alias("methods"), pl.col("resolve_method").first(), pl.col("raw").first()))
    rep["legal_basis"] = {"parent_acts": dict(pa_stats), "preamble": dict(pre_stats), "constitution": dict(cst), "edges": b.height,
                          "edges_by_method": dict(Counter(b["method"].to_list())),
                          "edges_found_by_both_methods": int(b.filter(pl.col("methods").list.len() > 1).height),
                          "citing_documents": int(b["src_doc_id"].n_unique())}
    rep["wall_links_s"] = round(time.time() - t0, 1)
    return cit, b

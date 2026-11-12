"""Legal Q&A (hdpl metadata + gold article edges + document edges), legal terms (tnpl) and legal news (htpl).

Licence policy: only identifiers, URLs, dates, categories/areas, term names (with translation provenance) and
derived edges are written. Question/answer/news text, term definitions and person names are never written."""
import glob
import re
import time
from collections import Counter

import polars as pl

from . import config as C
from . import vnlegal_text as VT
from .resolve import DocResolver, norm_article, norm_clause, norm_point

GOLD_METHOD = [("answer_text:number", "answer-text-number"), ("answer_text:", "answer-text-name"),
               ("citation_field:", "citation-field-name"), ("unique_document_of_type", "unique-document-of-type")]


def gold_method(m):
    for pre, out in GOLD_METHOD:
        if (m or "").startswith(pre):
            return out
    return "unknown"


def parse_dmy(s):
    if not s:
        return None
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if not m:
        return None
    try:
        import datetime
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except Exception:
        return None


def build_qa(docs, arts, rep):
    t0 = time.time()
    res = DocResolver(docs.select("doc_id", "doc_type_vi", "doc_number", "doc_number_key", "title_core", "issue_date",
                                  "effective_date").rename({"doc_type_vi": "doc_type"}).to_dicts())
    fs = sorted(glob.glob(f"{C.snapshot('thuvienphapluat-vn-hdpl')}/**/documents-*.parquet", recursive=True))
    h = pl.concat([pl.read_parquet(f, columns=["id", "url", "category", "area", "published_date", "citations", "content_flag_summary"]) for f in fs])
    rep["hdpl_rows"] = h.height
    rows, drows = [], []
    dstats = Counter()
    for r in h.iter_rows(named=True):
        pub = (r["published_date"] or "")[:10] or None
        cits = r["citations"] or []
        n_doc = n_prov = 0
        for c in cits:
            if c["kind"] == "document":
                n_doc += 1
                dstats["document_citation_records"] += 1
                if not c["id"]:
                    dstats["no_number"] += 1
                    continue
                th = c["law_type"] if c["law_type"] in C.DOC_TYPES else None
                d, how = res.by_number(c["id"], th, pub)
                if d:
                    dstats["resolved"] += 1
                    drows.append({"qa_id": r["id"], "dst_doc_id": d, "number_cited": c["id"], "law_type": c["law_type"], "method": how})
                else:
                    dstats["unresolved:" + how] += 1
            else:
                n_prov += 1
        area = C.slugify(r["area"]) if r["area"] else None
        rows.append({"qa_id": r["id"], "iri": C.iri_qa(r["id"]), "answer_iri": C.iri_answer(r["id"]), "url": r["url"],
                     "published_date": pub, "year": int(pub[:4]) if pub else None, "category": r["category"], "area_id": area,
                     "has_ad": bool((r["content_flag_summary"] or {}).get("has_ad")), "n_citation_records": len(cits),
                     "n_document_citations": n_doc, "n_provision_citations": n_prov})
    qas = pl.DataFrame(rows, infer_schema_length=None)
    qd = pl.DataFrame(drows, infer_schema_length=None).unique(subset=["qa_id", "dst_doc_id"], maintain_order=True)
    # gold article edges (resolved by the data track's gold resolver)
    g = pl.read_parquet(C.PROCESSED["gold_all"], columns=["qa_id", "published_date", "gold"])
    rep["gold_qas"] = g.height
    ge = g.select("qa_id", "gold").explode("gold").unnest("gold")
    rep["gold_edges_raw"] = ge.height
    main_art = set(arts.filter(pl.col("segment") == "main").select("doc_id", "article_no").iter_rows())
    arows, gstats = [], Counter()
    for r in ge.iter_rows(named=True):
        a = norm_article(r["article"])
        if not a or (r["doc_id"], a) not in main_art:
            gstats["article_missing"] += 1
            continue
        arows.append({"qa_id": r["qa_id"], "dst_doc_id": r["doc_id"], "dst_article_id": f"{r['doc_id']}::dieu-{a}",
                      "clause": norm_clause(r["clause"]), "point": norm_point(r["point"]), "ref": C.cut(r["ref"], 160),
                      "method": gold_method(r["method"]), "method_detail": r["method"]})
        gstats["kept"] += 1
    qa_art = pl.DataFrame(arows, infer_schema_length=None, schema_overrides={"clause": pl.Utf8, "point": pl.Utf8, "ref": pl.Utf8}).unique(subset=["qa_id", "dst_article_id", "clause", "point"], maintain_order=True)
    qas = qas.join(qa_art.group_by("qa_id").agg(pl.col("dst_article_id").n_unique().alias("n_gold_articles")), on="qa_id", how="left") \
             .join(qd.group_by("qa_id").len().rename({"len": "n_documents_resolved"}), on="qa_id", how="left") \
             .with_columns(pl.col("n_gold_articles").fill_null(0), pl.col("n_documents_resolved").fill_null(0))
    rep["qa"] = {"questions": qas.height, "document_citations": dict(dstats), "qa_document_edges": qd.height,
                 "gold": dict(gstats), "qa_article_edges": qa_art.height,
                 "qas_with_article_edge": int(qa_art["qa_id"].n_unique()),
                 "qa_article_edges_by_method": dict(Counter(qa_art["method"].to_list())),
                 "gold_qas_missing_from_hdpl": int(g.filter(~pl.col("qa_id").is_in(qas["qa_id"].to_list())).height),
                 "wall_s": round(time.time() - t0, 1)}
    return qas, qa_art, qd


def build_terms(rep):
    p = glob.glob(f"{C.snapshot('thuvienphapluat-vn-tnpl')}/**/*.parquet", recursive=True)
    p = [x for x in p if "embedding" not in x and "reduce" not in x]
    t = pl.read_parquet(p[0], columns=["term_id", "fetch_status", "source_url", "term_name_vi", "term_name_en", "term_name_source",
                                       "translation_model_id", "area_name_vi", "area_name_en", "area_id", "status_vi", "related_term_ids"])
    rep["tnpl_files"] = [x.split("/")[-1] for x in p]
    rep["tnpl_rows"] = t.height
    rep["tnpl_by_fetch_status"] = dict(Counter(t["fetch_status"].to_list()))
    t = t.filter((pl.col("fetch_status") == "ok") & (pl.col("term_name_vi").str.len_chars() > 0))
    ok = set(t["term_id"].to_list())
    rows, rel = [], []
    area_labels = {}
    for r in t.iter_rows(named=True):
        area = C.slugify(r["area_name_vi"]) if r["area_name_vi"] else None
        if area and area not in area_labels:
            area_labels[area] = (VT.nfc(r["area_name_vi"]), r["area_name_en"])
        st = r["status_vi"]
        rows.append({"term_id": r["term_id"], "iri": C.iri_term(r["term_id"]), "label_vi": VT.nfc(r["term_name_vi"]).strip(),
                     "label_en": (r["term_name_en"] or "").strip() or None, "label_en_source": r["term_name_source"],
                     "translation_model": r["translation_model_id"] if r["term_name_source"] == "mt" else None,
                     "area_id": area, "tnpl_area_id": r["area_id"], "status_vi": st,
                     "in_force": True if st == "Còn hiệu lực" else (False if st == "Hết hiệu lực" else None),
                     "url": r["source_url"]})
        for x in r["related_term_ids"] or []:
            if x in ok and x != r["term_id"]:
                rel.append({"src_term_id": r["term_id"], "dst_term_id": x, "method": "source-metadata"})
    terms = pl.DataFrame(rows, infer_schema_length=None)
    tr = pl.DataFrame(rel).unique(maintain_order=True)
    pairs = {tuple(sorted(x)) for x in tr.select("src_term_id", "dst_term_id").iter_rows()}
    rep["terms"] = {"terms": terms.height, "related_edges_directed": tr.height, "related_pairs_undirected": len(pairs),
                    "related_ids_not_in_terms": int(sum(len(r or []) for r in t["related_term_ids"].to_list()) - tr.height),
                    "label_en_source": dict(Counter(terms["label_en_source"].to_list())),
                    "areas": len(area_labels), "status": dict(Counter(terms["status_vi"].to_list()))}
    return terms, tr, area_labels


def build_news(docs, rep):
    res = DocResolver(docs.select("doc_id", "doc_type_vi", "doc_number", "doc_number_key", "title_core", "issue_date",
                                  "effective_date").rename({"doc_type_vi": "doc_type"}).to_dicts())
    p = [x for x in glob.glob(f"{C.snapshot('thuvienphapluat-vn-htpl')}/**/*.parquet", recursive=True) if "embedding" not in x and "reduce" not in x]
    n = pl.read_parquet(p[0], columns=["id", "url", "category", "published_date", "title", "body"])
    rows, edges, st = [], [], Counter()
    for r in n.iter_rows(named=True):
        pub = parse_dmy(r["published_date"])
        found = list(dict.fromkeys(VT.DOCNUM_ANY.findall((r["title"] or "") + "\n" + (r["body"] or ""))))
        k = 0
        for num in found:
            d, how = res.by_number(num, None, pub)
            st["mentions"] += 1
            if d:
                st["resolved"] += 1
                k += 1
                edges.append({"news_id": r["id"], "dst_doc_id": d, "number_found": num, "method": "docnum-regex"})
        rows.append({"news_id": r["id"], "iri": C.iri_news(r["id"]), "url": r["url"], "category": r["category"],
                     "published_date": pub, "year": int(pub[:4]) if pub else None, "n_numbers_found": len(found), "n_documents_resolved": k})
    news = pl.DataFrame(rows, infer_schema_length=None)
    ne = pl.DataFrame(edges).unique(subset=["news_id", "dst_doc_id"], maintain_order=True)
    rep["news"] = {"articles": news.height, "published_date_parsed": int(news["published_date"].is_not_null().sum()),
                   **dict(st), "edges": ne.height, "articles_with_edge": int(ne["news_id"].n_unique()),
                   "categories": dict(Counter(news["category"].to_list()))}
    return news, ne


def build_area_table(doc_areas, qas, terms, term_area_labels, rep):
    cnt_q = Counter(qas["area_id"].drop_nulls().to_list())
    cnt_t = Counter(terms["area_id"].drop_nulls().to_list())
    slugs = set(doc_areas) | set(cnt_q) | set(cnt_t)
    rows, unlabeled = [], []
    for s in sorted(slugs):
        vi, en = C.AREA_LABELS.get(s, (None, None))
        en_src = "vlonto"
        if not vi and s in term_area_labels:
            vi, en = term_area_labels[s][0], term_area_labels[s][1]
            en_src = "tnpl-mt"
        if not vi:
            unlabeled.append(s)
            vi, en = s, s
        schemes = []
        if doc_areas.get(s) or cnt_q.get(s):
            schemes.append("LegalAreaScheme")
        if cnt_t.get(s):
            schemes.append("TermAreaScheme")
        rows.append({"area_id": s, "iri": C.iri_area(s), "label_vi": vi, "label_en": en, "label_en_source": en_src,
                     "schemes": schemes, "n_documents": (doc_areas.get(s) or {}).get("n_documents", 0),
                     "n_qas": cnt_q.get(s, 0), "n_terms": cnt_t.get(s, 0)})
    areas = pl.DataFrame(rows, infer_schema_length=None)
    rep["areas"] = {"areas": areas.height, "in_legal_area_scheme": int(areas["schemes"].list.contains("LegalAreaScheme").sum()),
                    "in_term_area_scheme": int(areas["schemes"].list.contains("TermAreaScheme").sum()),
                    "in_both": int((areas["schemes"].list.len() == 2).sum()), "unlabeled": unlabeled}
    return areas

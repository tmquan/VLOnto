"""Facts of the trace drawn in the paper's Fig. 1 (Q&A #138008514), read from a VLOnto v1 build and the paper's data.

    python scripts/site/teaser/make_trace.py --kg <build root>/build/kg --paper-data <paper source>/data \
        --out scripts/site/teaser/trace_138008514.json

Inputs (read only): the v1 knowledge-graph tables documents, changes, structure, articles, provisions_ref, qas,
edges_qa_article and terms (parquet), and the paper's data/worked_example.json (arXiv:2611.11426, the source of Fig. 1
and Fig. 5), which carries the term definition the v1 tables do not keep (t:630 <-defines- 333670 Art. 3(1)).
Every fact is checked against both where both have it; the run stops on a mismatch. Licence: titles and identifiers
only (numbers, structure numbers, dates, ids, short bilingual class labels) - no article, answer or question text.
The output is committed, so the harness and CI never need the build root.
"""
import argparse, json, os, sys

import pyarrow.parquet as pq

QA, LAW, OLD = "138008514", "333670", "142187"


def table(kg, name, cols=None):
    return pq.read_table(os.path.join(kg, name + ".parquet"), columns=cols).to_pandas()


def one(df, what):
    if len(df) != 1:
        sys.exit(f"expected one row for {what}, got {len(df)}")
    return df.iloc[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kg", required=True)
    ap.add_argument("--paper-data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    docs = table(a.kg, "documents", ["doc_id", "doc_number", "doc_type_vi", "title_vi", "year", "effective_date", "expiry_date"])
    law = one(docs[docs.doc_id == LAW], "law")
    old = one(docs[docs.doc_id == OLD], "replaced law")
    assert law.doc_number == "45/2019/QH14" and old.doc_number == "10/2012/QH13", (law.doc_number, old.doc_number)
    ch = table(a.kg, "changes", ["change_id", "acting_doc_id", "affected_doc_id", "kind", "effective_date", "method"])
    rep = one(ch[(ch.acting_doc_id == LAW) & (ch.affected_doc_id == OLD) & (ch.kind == "replaced")], "replacement")
    st = table(a.kg, "structure", ["struct_id", "doc_id", "kind", "number", "parent_id"])
    st = st[st.doc_id == LAW].set_index("struct_id")
    art = table(a.kg, "articles", ["article_id", "doc_id", "article_no", "parent_id", "parent_kind"])
    art = art[art.doc_id == LAW].set_index("article_id")
    prov = table(a.kg, "provisions_ref", ["prov_id", "kind", "article_id", "clause", "point", "parent_id"]).set_index("prov_id")
    qas = table(a.kg, "qas", ["qa_id", "published_date", "area_id", "n_citation_records", "n_provision_citations",
                              "n_document_citations", "n_gold_articles"])
    qa = one(qas[qas.qa_id == QA], "Q&A")
    eqa = table(a.kg, "edges_qa_article", ["qa_id", "dst_doc_id", "dst_article_id", "clause", "point", "method"])
    cite = one(eqa[eqa.qa_id == QA], "Q&A citation edge")
    terms = table(a.kg, "terms", ["term_id", "label_vi", "label_en", "area_id"])
    terms = terms.set_index(terms.term_id.astype(str))
    we = json.load(open(os.path.join(a.paper_data, "worked_example.json"), encoding="utf-8"))

    # the cited provision and its parents in the v1 tables
    pt_id = "333670::dieu-35::khoan-1::diem-d"
    cl_id, ar_id = "333670::dieu-35::khoan-1", "333670::dieu-35"
    sec_id, chap_id = "333670::chuong-iii/muc-3", "333670::chuong-iii"
    assert (cite.dst_doc_id, cite.dst_article_id, str(cite.clause), str(cite.point)) == (LAW, ar_id, "1", "d"), cite.to_dict()
    assert prov.loc[pt_id, "parent_id"] == cl_id and prov.loc[cl_id, "parent_id"] == ar_id
    assert art.loc[ar_id, "article_no"] == "35" and art.loc[ar_id, "parent_id"] == sec_id
    assert st.loc[sec_id, "kind"] == "Section" and str(st.loc[sec_id, "number"]) == "3" and st.loc[sec_id, "parent_id"] == chap_id
    assert st.loc[chap_id, "kind"] == "Chapter" and st.loc[chap_id, "number"] == "iii" and st.loc[chap_id, "parent_id"] == LAW
    # the term branch: Art. 3(1) defines 'người lao động' (paper data; the v1 tables keep the clause, not the link)
    d3k1, d3, chap1 = "333670::dieu-3::khoan-1", "333670::dieu-3", "333670::chuong-i"
    assert prov.loc[d3k1, "parent_id"] == d3 and art.loc[d3, "parent_id"] == chap1 and st.loc[chap1, "parent_id"] == LAW
    tdef = {t["id"]: t for t in we["terms"]}
    assert ["vb:333670#d3.k1", "Người lao động ~ score 100"] in tdef["t:630"]["defined_by"], tdef["t:630"]["defined_by"]
    for tid in ("630", "641"):
        assert terms.loc[tid, "label_vi"] == tdef["t:" + tid]["vi"] and terms.loc[tid, "label_en"] == tdef["t:" + tid]["en"]
    # the paper's view of the same answer: 7 sources, one quoted word for word (Art. 35(1)(d)), dated 14 Mar 2024
    assert str(we["aid"]) == QA and we["date"].startswith(str(qa.published_date)[:10])
    quoted = [c for c in we["cites"] if c.get("status") == "validated" and c.get("kind") == "provision"]
    assert len(we["cites"]) == int(qa.n_citation_records) == 7 and [c["uid"] for c in quoted] == ["vb:333670#d35.k1.d"]
    assert we["work"]["key"] == "45/2019/QH14" and we["work"]["records"] == ["vb:333670", "vb:432162"]

    N = lambda i, cls, vi, en, trace, src: dict(id=i, cls=cls, vi=vi, en=en, trace=trace, source=src)
    nodes = [
        N(chap_id, "chapter", "Chương III", "Chapter III", True, "structure"),
        N(sec_id, "section", "Mục 3", "Section 3", True, "structure"),
        N(ar_id, "article", "Điều 35", "Article 35", True, "articles"),
        N(cl_id, "clause", "Khoản 1 Điều 35", "Art. 35(1)", True, "provisions_ref"),
        N(pt_id, "point", "Điểm d khoản 1 Điều 35", "Art. 35(1)(d)", True, "provisions_ref"),
        N("qa:" + QA + "/answer", "answer", "Trả lời", "Answer #" + QA, True, "qas"),
        N("qa:" + QA, "question", "Câu hỏi", "Question #" + QA, True, "qas"),
        N(chap1, "chapter", "Chương I", "Chapter I", False, "structure"),
        N(d3, "article", "Điều 3", "Article 3", False, "articles"),
        N(d3k1, "clause", "Khoản 1 Điều 3", "Art. 3(1)", False, "provisions_ref"),
        N("term:630", "term", terms.loc["630", "label_vi"], terms.loc["630", "label_en"], False, "terms"),
        N("term:641", "term", terms.loc["641", "label_vi"], terms.loc["641", "label_en"], False, "terms"),
    ]
    L = lambda s, t, rel, trace, src: dict(source=s, target=t, rel=rel, trace=trace, provenance=src)
    links = [
        L("doc:" + OLD, "doc:" + LAW, "replaced by", True, "changes " + rep.change_id),
        L("doc:" + LAW, chap_id, "contains", True, "structure"),
        L(chap_id, sec_id, "contains", True, "structure"),
        L(sec_id, ar_id, "contains", True, "articles.parent_id"),
        L(ar_id, cl_id, "contains", True, "provisions_ref.parent_id"),
        L(cl_id, pt_id, "contains", True, "provisions_ref.parent_id"),
        L("qa:" + QA + "/answer", pt_id, "cites", True, "edges_qa_article (" + cite.method + ")"),
        L("qa:" + QA, "qa:" + QA + "/answer", "answered by", True, "qas"),
        L("doc:" + LAW, chap1, "contains", False, "structure"),
        L(chap1, d3, "contains", False, "articles.parent_id"),
        L(d3, d3k1, "contains", False, "provisions_ref.parent_id"),
        L(d3k1, "term:630", "defines", False, "paper data/worked_example.json (definition match 100)"),
        L("qa:" + QA, "term:630", "mentions", False, "paper data/worked_example.json"),
        L("qa:" + QA, "term:641", "mentions", False, "paper data/worked_example.json"),
    ]
    out = dict(
        about="Trace of Q&A #138008514 for the paper's Fig. 1 (arXiv:2611.11426); identifiers and short bilingual labels only",
        sources=dict(kg="VLOnto v1 build tables (build/kg): documents, changes, structure, articles, provisions_ref, qas, "
                        "edges_qa_article, terms", paper="paper source data/worked_example.json (Fig. 1 and Fig. 5)"),
        qa=dict(id=QA, published=str(qa.published_date)[:10], area=qa.area_id, sources_cited=int(qa.n_citation_records),
                quoted_word_for_word="Art. 35(1)(d)"),
        law=dict(doc=LAW, number=law.doc_number, vi="Bộ luật Lao động 2019", en="Labor Code 2019",
                 effective=str(law.effective_date)[:10]),
        replaced=dict(doc=OLD, number=old.doc_number, vi="Bộ luật Lao động 2012", en="Labor Code 2012",
                      expired=str(old.expiry_date)[:10], change=rep.change_id, effective=str(rep.effective_date)[:10]),
        nodes=nodes, links=links)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"wrote {a.out}: {len(nodes)} nodes, {len(links)} links; law {law.doc_number}, replaced {old.doc_number}")


if __name__ == "__main__":
    main()

"""Step 4a: RDF export.

vlonto-kg.nt.gz  full N-Triples (ontology + all KG tables), streamed table by table: each part is built with
                 vectorised polars string expressions, written as its own gzip member and the members are
                 concatenated (a valid gzip stream); the full graph is never held in memory.
vlonto-core.ttl  browser-sized Turtle subset: ontology + documents of legal-force rank <= CORE_MAX_RANK with
                 their change events, legal-basis edges and document-level citations among themselves, plus
                 issuers, areas, precedents, source datasets, edge sets and the build activity.
"""
import gzip
import json
import multiprocessing as mp
import os
import re
import shutil
import time

import polars as pl

from . import config as C
from .nfc import nfc, str_normalize

VLO, ID = C.VLO, C.ID
RDF_TYPE = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
RDFS_LABEL = "<http://www.w3.org/2000/01/rdf-schema#label>"
RDFS_COMMENT = "<http://www.w3.org/2000/01/rdf-schema#comment>"
SKOS = "http://www.w3.org/2004/02/skos/core#"
XSD = "http://www.w3.org/2001/XMLSchema#"
PROV = "http://www.w3.org/ns/prov#"
DCT = "http://purl.org/dc/terms/"
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"


def P(local):
    return f"<{VLO}{local}>"


def esc(e):
    return (str_normalize(e.cast(pl.Utf8)).str.replace_all(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ")
             .str.replace_all("\\", "\\\\", literal=True).str.replace_all('"', '\\"', literal=True)
             .str.replace_all("\n", "\\n", literal=True).str.replace_all("\r", "\\r", literal=True))


def iri(e):
    return pl.concat_str([pl.lit("<"), e, pl.lit(">")])


def lit(e, lang=None, dt=None):
    tail = f"@{lang}" if lang else (f"^^<{XSD}{dt}>" if dt else "")
    return pl.concat_str([pl.lit('"'), esc(e), pl.lit('"' + tail)])


def tri(df, s, p, o, cond=None):
    """One N-Triples line per row where all parts are non-null (and cond holds)."""
    line = pl.concat_str([s, pl.lit(" " + p + " "), o, pl.lit(" .")])
    q = df.select(line.alias("l"))
    if cond is not None:
        q = df.select(line.alias("l"), cond.alias("c")).filter(pl.col("c")).select("l")
    return q.drop_nulls()["l"]


def concept(local):
    return pl.lit(f"<{VLO}{local}>")


def src(dataset):
    return pl.lit(f"<{C.iri_source(dataset)}>")


# ------------------------------------------------------------------ table -> lines
def lines_documents(df):
    s = iri(pl.col("iri"))
    lab = pl.when(pl.col("doc_number").is_not_null() & ~pl.col("title_vi").str.contains(pl.col("doc_number"), literal=True)) \
            .then(pl.concat_str([pl.col("title_vi"), pl.lit(" ("), pl.col("doc_number"), pl.lit(")")])).otherwise(pl.col("title_vi"))
    df = df.with_columns(lab.str.slice(0, 200).alias("_label"),
                         pl.col("doc_type_vi").replace_strict({k: v[1] for k, v in C.DOC_TYPES.items()}).alias("_dt"),
                         pl.col("validity").replace_strict(C.VALIDITY_CONCEPT, default="validity-unknown").alias("_val"))
    out = [tri(df, s, RDF_TYPE, iri(pl.lit(VLO) + pl.col("doc_class"))),
           tri(df, s, RDFS_LABEL, lit(pl.col("_label"), "vi")),
           tri(df, s, P("title"), lit(pl.col("title_vi"), "vi")),
           tri(df, s, P("documentNumber"), lit(pl.col("doc_number"))),
           tri(df, s, P("documentNumberKey"), lit(pl.col("doc_number_key"))),
           tri(df, s, P("documentType"), iri(pl.lit(VLO) + pl.col("_dt"))),
           tri(df, s, P("legalForceRank"), iri(pl.lit(VLO + "rank-") + pl.col("legal_force_rank").cast(pl.Utf8))),
           tri(df, s, P("validityStatus"), iri(pl.lit(VLO) + pl.col("_val"))),
           tri(df, s, P("isInForce"), lit(pl.col("in_force").cast(pl.Utf8).str.to_lowercase(), dt="boolean")),
           tri(df, s, P("issueDate"), lit(pl.col("issue_date"), dt="date"), pl.col("issue_date").str.contains(DATE_RE)),
           tri(df, s, P("effectiveDate"), lit(pl.col("effective_date"), dt="date"), pl.col("effective_date").str.contains(DATE_RE)),
           tri(df, s, P("expiryDate"), lit(pl.col("expiry_date"), dt="date"), pl.col("expiry_date").str.contains(DATE_RE)),
           tri(df, s, P("sourceStatus"), lit(pl.col("status_raw"), "vi")),
           tri(df, s, P("statusTextConflict"), pl.lit(f'"true"^^<{XSD}boolean>'), pl.col("status_text_conflict")),
           tri(df, s, P("validityEvidenceSource"), lit(pl.col("validity_evidence"))),
           tri(df, s, P("legalArea"), iri(pl.lit(ID + "area/") + pl.col("area_id"))),
           tri(df, s, P("sourceId"), lit(pl.col("doc_id"))),
           tri(df, s, P("sourceUrl"), lit(pl.col("url"), dt="anyURI")),
           tri(df, s, P("sourceDataset"), src("thuvienphapluat-vn-vbpl"))]
    iss = df.select("iri", "issuer_ids").explode("issuer_ids").drop_nulls()
    out.append(tri(iss, iri(pl.col("iri")), P("issuedBy"), iri(pl.lit(ID + "issuer/") + pl.col("issuer_ids").str.to_lowercase())))
    return out


def lines_articles(df):
    s = iri(pl.col("iri"))
    num = pl.col("doc_number").fill_null(pl.col("doc_title_short"))
    df = df.with_columns(pl.concat_str([pl.lit("Điều "), pl.col("article_no"),
                                        pl.when(pl.col("segment") != "main").then(pl.lit(" (") + pl.col("segment").str.replace("att", "phụ lục ") + pl.lit(")")).otherwise(pl.lit("")),
                                        pl.lit(", "), num]).alias("_label"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("Article"))),
            tri(df, s, RDFS_LABEL, lit(pl.col("_label"), "vi")),
            tri(df, s, P("provisionNumber"), lit(pl.col("article_no"))),
            tri(df, s, P("heading"), lit(pl.col("heading"), "vi")),
            tri(df, s, P("position"), lit(pl.col("position").cast(pl.Utf8), dt="integer")),
            tri(df, s, P("isPartOf"), iri(pl.col("parent_iri"))),
            tri(df, s, P("inDocument"), iri(pl.lit(ID + "document/") + pl.col("doc_id"))),
            tri(df, s, P("sourceDataset"), src("thuvienphapluat-vn-vbpl"))]


def lines_structure(df):
    s = iri(pl.col("iri"))
    word = pl.col("kind").replace_strict({"Appendix": "Phụ lục", "Part": "Phần", "Chapter": "Chương", "Section": "Mục"})
    df = df.with_columns(pl.concat_str([word, pl.lit(" "), pl.col("number").str.to_uppercase(), pl.lit(", "),
                                        pl.col("doc_number").fill_null(pl.col("doc_title_short"))]).alias("_label"))
    return [tri(df, s, RDF_TYPE, iri(pl.lit(VLO) + pl.col("kind"))),
            tri(df, s, RDFS_LABEL, lit(pl.col("_label"), "vi")),
            tri(df, s, P("provisionNumber"), lit(pl.col("number"))),
            tri(df, s, P("heading"), lit(pl.col("heading"), "vi")),
            tri(df, s, P("position"), lit(pl.col("position").cast(pl.Utf8), dt="integer")),
            tri(df, s, P("isPartOf"), iri(pl.col("parent_iri"))),
            tri(df, s, P("inDocument"), iri(pl.lit(ID + "document/") + pl.col("doc_id")))]


def lines_provisions_ref(df):
    s = iri(pl.col("iri"))
    lab = pl.when(pl.col("kind") == "Clause").then(pl.concat_str([pl.lit("khoản "), pl.col("clause"), pl.lit(" "), pl.col("article_label")])) \
            .otherwise(pl.concat_str([pl.lit("điểm "), pl.col("point"), pl.when(pl.col("clause").is_not_null()).then(pl.lit(" khoản ") + pl.col("clause")).otherwise(pl.lit("")),
                                      pl.lit(" "), pl.col("article_label")]))
    df = df.with_columns(lab.alias("_label"), pl.when(pl.col("kind") == "Clause").then(pl.col("clause")).otherwise(pl.col("point")).alias("_num"))
    return [tri(df, s, RDF_TYPE, iri(pl.lit(VLO) + pl.col("kind"))),
            tri(df, s, RDFS_LABEL, lit(pl.col("_label"), "vi")),
            tri(df, s, P("provisionNumber"), lit(pl.col("_num"))),
            tri(df, s, P("isPartOf"), iri(pl.col("parent_iri"))),
            tri(df, s, P("inDocument"), iri(pl.lit(ID + "document/") + pl.col("doc_id")))]


def lines_issuers(df):
    s = iri(pl.col("iri"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("IssuingBody"))), tri(df, s, RDFS_LABEL, lit(pl.col("label_vi"), "vi")),
            tri(df, s, RDFS_LABEL, lit(pl.col("label_en"), "en"), pl.col("label_source") == "vlonto-table"),
            tri(df, s, P("issuerCode"), lit(pl.col("issuer_id")))]


def lines_areas(df):
    s = iri(pl.col("iri"))
    out = [tri(df, s, RDF_TYPE, pl.lit(P("LegalArea"))), tri(df, s, f"<{SKOS}prefLabel>", lit(pl.col("label_vi"), "vi")),
           tri(df, s, f"<{SKOS}prefLabel>", lit(pl.col("label_en"), "en")), tri(df, s, RDFS_LABEL, lit(pl.col("label_vi"), "vi")),
           tri(df, s, RDFS_LABEL, lit(pl.col("label_en"), "en"))]
    sc = df.select("iri", "schemes").explode("schemes").drop_nulls()
    out.append(tri(sc, iri(pl.col("iri")), f"<{SKOS}inScheme>", iri(pl.lit(VLO) + pl.col("schemes"))))
    return out


def lines_changes(df):
    s = iri(pl.col("iri"))
    df = df.with_columns(pl.col("kind").replace_strict(C.CHANGE_CONCEPT).alias("_k"),
                         pl.col("kind").replace_strict(C.CHANGE_PROPERTY).alias("_p"),
                         pl.concat_str([pl.col("acting_number").fill_null(pl.col("acting_doc_id")), pl.lit(" "), pl.col("kind").str.replace("_", " "),
                                        pl.lit(" "), pl.col("affected_number").fill_null(pl.col("affected_doc_id"))]).alias("_label"))
    act = iri(pl.lit(ID + "document/") + pl.col("acting_doc_id"))
    aff = iri(pl.lit(ID + "document/") + pl.col("affected_doc_id"))
    out = [tri(df, s, RDF_TYPE, pl.lit(P("LegalChange"))), tri(df, s, RDFS_LABEL, lit(pl.col("_label"), "vi")),
           tri(df, s, P("actingDocument"), act), tri(df, s, P("affectedDocument"), aff),
           tri(df, s, P("changeKind"), iri(pl.lit(VLO) + pl.col("_k"))), tri(df, s, P("evidenceText"), lit(pl.col("evidence"), "vi")),
           tri(df, s, P("changeEffectiveDate"), lit(pl.col("effective_date"), dt="date"), pl.col("effective_date").str.contains(DATE_RE)),
           tri(df, s, P("mentionedDate"), lit(pl.col("mentioned_date"), dt="date"), pl.col("mentioned_date").str.contains(DATE_RE)),
           tri(df, s, P("extractionMethod"), pl.lit(P("method-validity-rules-v7"))), tri(df, s, P("ruleVersion"), lit(pl.col("rule_version"))),
           tri(df, s, P("sourceDataset"), src("thuvienphapluat-vn-vbpl"))]
    sh = pl.concat_str([act, pl.lit(" <" + VLO), pl.col("_p"), pl.lit("> "), aff, pl.lit(" .")])
    out.append(df.select(sh.alias("l")).unique(maintain_order=True)["l"])
    return out


def lines_edges_doc(df, prop):
    return [tri(df, iri(pl.lit(ID + "document/") + pl.col("src_doc_id")), P(prop), iri(pl.lit(ID + "document/") + pl.col("dst_doc_id")))]


def target_iri(df):
    """Most specific target: point > clause > article > document."""
    art = pl.lit(ID + "document/") + pl.col("dst_article_id").str.replace("::", "/")
    t = (pl.when(pl.col("dst_article_id").is_not_null() & pl.col("point").is_not_null() & pl.col("clause").is_not_null())
           .then(art + pl.lit("/khoan-") + pl.col("clause") + pl.lit("/diem-") + pl.col("point"))
           .when(pl.col("dst_article_id").is_not_null() & pl.col("point").is_not_null()).then(art + pl.lit("/diem-") + pl.col("point"))
           .when(pl.col("dst_article_id").is_not_null() & pl.col("clause").is_not_null()).then(art + pl.lit("/khoan-") + pl.col("clause"))
           .when(pl.col("dst_article_id").is_not_null()).then(art)
           .otherwise(pl.lit(ID + "document/") + pl.col("dst_doc_id")))
    return iri(t)


def lines_citations(df):
    subj = iri(pl.when(pl.col("src_article_id").is_not_null()).then(pl.lit(ID + "document/") + pl.col("src_article_id").str.replace("::", "/"))
               .otherwise(pl.lit(ID + "document/") + pl.col("src_doc_id")))
    prop = pl.when(pl.col("kind").str.starts_with("parent_law")).then(pl.lit(P("citesParentLaw"))).otherwise(pl.lit(P("cites")))
    l = pl.concat_str([subj, pl.lit(" "), prop, pl.lit(" "), target_iri(df), pl.lit(" .")])
    return [df.select(l.alias("l")).unique(maintain_order=True)["l"]]


def lines_courts(df):
    s = iri(pl.col("iri"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("Court"))), tri(df, s, RDFS_LABEL, lit(pl.col("label"), "vi")),
            tri(df, s, P("courtLevel"), iri(pl.lit(VLO) + pl.col("court_level").replace_strict(C.COURT_LEVEL_CONCEPT, default=None)))]


def lines_decisions(df):
    s = iri(pl.col("iri"))
    ds = pl.when(pl.col("source") == "anle").then(src("anle-toaan-gov-vn")).otherwise(src("cbba-toaan-gov-vn"))
    df = df.with_columns(pl.col("decision_number").fill_null(pl.col("doc_name")).alias("_label"))
    return [tri(df, s, RDF_TYPE, iri(pl.lit(VLO) + pl.col("decision_kind"))), tri(df, s, RDFS_LABEL, lit(pl.col("_label"), "vi")),
            tri(df, s, P("decisionNumber"), lit(pl.col("decision_number"))), tri(df, s, P("decisionCode"), lit(pl.col("decision_code"))),
            tri(df, s, P("decisionDate"), lit(pl.col("issued_date"), dt="date"), pl.col("issued_date").str.contains(DATE_RE)),
            tri(df, s, P("caseCategory"), iri(pl.lit(VLO) + pl.col("category").replace_strict(C.CASE_CONCEPT, default=None))),
            tri(df, s, P("instanceLevel"), iri(pl.lit(VLO) + pl.col("instance_level").replace_strict(C.INSTANCE_CONCEPT, default=None))),
            tri(df, s, P("courtLevel"), iri(pl.lit(VLO) + pl.col("court_level").replace_strict(C.COURT_LEVEL_CONCEPT, default=None))),
            tri(df, s, P("decidedBy"), iri(pl.lit(ID + "court/") + pl.col("court_id"))),
            tri(df, s, P("sourceId"), lit(pl.col("doc_name"))), tri(df, s, P("sourceUrl"), lit(pl.col("url"), dt="anyURI")),
            tri(df, s, P("sourceDataset"), ds)]


def lines_precedents(df):
    s = iri(pl.col("iri"))
    out = [tri(df, s, RDF_TYPE, pl.lit(P("Precedent"))), tri(df, s, RDFS_LABEL, lit(pl.lit("Án lệ số ") + pl.col("precedent_number"), "vi")),
           tri(df, s, P("precedentNumber"), lit(pl.col("precedent_number")))]
    sd = df.select("iri", "source_decision_ids").explode("source_decision_ids").drop_nulls()
    sd = sd.with_columns(pl.col("source_decision_ids").str.split_exact(":", 1).struct.rename_fields(["a", "b"]).alias("_x")).unnest("_x")
    out.append(tri(sd, iri(pl.col("iri")), P("selectedFrom"), iri(pl.lit(ID + "decision/") + pl.col("a") + pl.lit("/") + pl.col("b"))))
    return out


def dec_iri(col):
    x = pl.col(col).str.split_exact(":", 1)
    return iri(pl.lit(ID + "decision/") + x.struct.field("field_0") + pl.lit("/") + x.struct.field("field_1"))


def lines_decision_provision(df):
    prop = pl.when(pl.col("dst_article_id").is_not_null()).then(pl.lit(P("appliesProvision"))).otherwise(pl.lit(P("appliesDocument")))
    l = pl.concat_str([dec_iri("decision_id"), pl.lit(" "), prop, pl.lit(" "), target_iri(df), pl.lit(" .")])
    return [df.select(l.alias("l")).unique(maintain_order=True)["l"]]


def lines_decision_case(df):
    d = df.filter(pl.col("dst_kind") == "decision")
    p = df.filter(pl.col("dst_kind") == "precedent")
    return [tri(d, dec_iri("src_id"), P("citesCase"), dec_iri("dst_id")),
            tri(p, dec_iri("src_id"), P("appliesPrecedent"), iri(pl.lit(ID + "precedent/") + pl.col("dst_id")))]


def lines_qas(df):
    s, a = iri(pl.col("iri")), iri(pl.col("answer_iri"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("LegalQuestion"))), tri(df, s, RDFS_LABEL, lit(pl.lit("Hỏi đáp pháp luật ") + pl.col("qa_id"), "vi")),
            tri(df, s, P("sourceId"), lit(pl.col("qa_id"))), tri(df, s, P("sourceUrl"), lit(pl.col("url"), dt="anyURI")),
            tri(df, s, P("publishedDate"), lit(pl.col("published_date"), dt="date"), pl.col("published_date").str.contains(DATE_RE)),
            tri(df, s, P("legalArea"), iri(pl.lit(ID + "area/") + pl.col("area_id"))), tri(df, s, P("hasAnswer"), a),
            tri(df, s, P("sourceDataset"), src("thuvienphapluat-vn-hdpl")),
            tri(df, a, RDF_TYPE, pl.lit(P("LegalAnswer"))), tri(df, a, RDFS_LABEL, lit(pl.lit("Trả lời hỏi đáp ") + pl.col("qa_id"), "vi")),
            tri(df, a, P("sourceDataset"), src("thuvienphapluat-vn-hdpl"))]


def lines_qa_article(df):
    l = pl.concat_str([iri(pl.lit(ID + "qa/") + pl.col("qa_id") + pl.lit("/answer")), pl.lit(" " + P("answerCitesProvision") + " "), target_iri(df), pl.lit(" .")])
    return [df.select(l.alias("l")).unique(maintain_order=True)["l"]]


def lines_qa_document(df):
    return [tri(df, iri(pl.lit(ID + "qa/") + pl.col("qa_id") + pl.lit("/answer")), P("answerCitesDocument"), iri(pl.lit(ID + "document/") + pl.col("dst_doc_id")))]


def lines_terms(df):
    s = iri(pl.col("iri"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("LegalTerm"))), tri(df, s, f"<{SKOS}inScheme>", pl.lit(P("LegalTermScheme"))),
            tri(df, s, f"<{SKOS}prefLabel>", lit(pl.col("label_vi"), "vi")), tri(df, s, f"<{SKOS}prefLabel>", lit(pl.col("label_en"), "en")),
            tri(df, s, RDFS_LABEL, lit(pl.col("label_vi"), "vi")),
            tri(df, s, P("legalArea"), iri(pl.lit(ID + "area/") + pl.col("area_id"))),
            tri(df, s, P("isInForce"), lit(pl.col("in_force").cast(pl.Utf8).str.to_lowercase(), dt="boolean")),
            tri(df, s, P("sourceStatus"), lit(pl.col("status_vi"), "vi")),
            tri(df, s, P("englishLabelSource"), lit(pl.col("label_en_source")), pl.col("label_en").is_not_null()),
            tri(df, s, P("translationModel"), lit(pl.col("translation_model")), pl.col("label_en").is_not_null()),
            tri(df, s, P("sourceId"), lit(pl.col("term_id").cast(pl.Utf8))), tri(df, s, P("sourceUrl"), lit(pl.col("url"), dt="anyURI")),
            tri(df, s, P("sourceDataset"), src("thuvienphapluat-vn-tnpl"))]


def lines_term_related(df):
    return [tri(df, iri(pl.lit(ID + "term/") + pl.col("src_term_id").cast(pl.Utf8)), P("relatedTerm"), iri(pl.lit(ID + "term/") + pl.col("dst_term_id").cast(pl.Utf8)))]


def lines_news(df):
    s = iri(pl.col("iri"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("LegalNewsArticle"))), tri(df, s, RDFS_LABEL, lit(pl.lit("Tin pháp luật ") + pl.col("news_id"), "vi")),
            tri(df, s, P("sourceId"), lit(pl.col("news_id"))), tri(df, s, P("sourceUrl"), lit(pl.col("url"), dt="anyURI")),
            tri(df, s, P("publishedDate"), lit(pl.col("published_date"), dt="date"), pl.col("published_date").str.contains(DATE_RE)),
            tri(df, s, P("newsCategory"), iri(pl.lit(ID + "news-category/") + pl.col("category"))),
            tri(df, s, P("sourceDataset"), src("thuvienphapluat-vn-htpl"))]


def lines_news_categories(df):
    s = iri(pl.col("iri"))
    return [tri(df, s, RDF_TYPE, pl.lit(P("NewsCategory"))), tri(df, s, f"<{SKOS}inScheme>", pl.lit(P("NewsCategoryScheme"))),
            tri(df, s, f"<{SKOS}prefLabel>", lit(pl.col("label_vi"), "vi")), tri(df, s, f"<{SKOS}prefLabel>", lit(pl.col("label_en"), "en")),
            tri(df, s, RDFS_LABEL, lit(pl.col("label_vi"), "vi"))]


def lines_news_document(df):
    return [tri(df, iri(pl.lit(ID + "news/") + pl.col("news_id")), P("mentionsDocument"), iri(pl.lit(ID + "document/") + pl.col("dst_doc_id")))]


# ------------------------------------------------------------------ provenance nodes
POLICY = {
    "thuvienphapluat-vn-vbpl": "Metadata (CC BY 4.0), titles, article headings and short evidence quotes; no document bodies (card: bodies © thuvienphapluat.vn); no signer names.",
    "thuvienphapluat-vn-hdpl": "Identifiers, URLs, dates, categories/areas and derived citation edges only; no question or answer text; no author names.",
    "thuvienphapluat-vn-tnpl": "Term identifiers, Vietnamese names, English names with translation provenance, areas, status and related-term links; no definitions; no updated_by.",
    "thuvienphapluat-vn-htpl": "Identifiers, URLs, dates, categories and derived document-mention edges; no titles or text.",
    "anle-toaan-gov-vn": "Decision metadata, court institution names, precedent numbers and derived citation edges; no judgment text; no person names.",
    "cbba-toaan-gov-vn": "Decision metadata, court institution names and derived citation edges; no judgment text; no person names.",
}
ATTRIB = {
    "thuvienphapluat-vn-vbpl": "Derived from tmquan/thuvienphapluat-vn-vbpl (CC BY 4.0 metadata), source thuvienphapluat.vn.",
    "thuvienphapluat-vn-hdpl": "Derived from tmquan/thuvienphapluat-vn-hdpl, source thuvienphapluat.vn (content © thuvienphapluat.vn).",
    "thuvienphapluat-vn-tnpl": "Derived from tmquan/thuvienphapluat-vn-tnpl, source thuvienphapluat.vn/tnpl/; English labels are machine translations.",
    "thuvienphapluat-vn-htpl": "Derived from tmquan/thuvienphapluat-vn-htpl, source thuvienphapluat.vn.",
    "anle-toaan-gov-vn": "Derived from tmquan/anle-toaan-gov-vn (CC BY 4.0), source anle.toaan.gov.vn, Supreme People's Court of Viet Nam.",
    "cbba-toaan-gov-vn": "Derived from tmquan/cbba-toaan-gov-vn (CC BY 4.0), source congbobanan.toaan.gov.vn, Supreme People's Court of Viet Nam.",
}
EDGESETS = {  # table -> (property, source dataset, method column or fixed method)
    "edges_change": ("changes", "thuvienphapluat-vn-vbpl", "method"),
    "edges_legal_basis": ("legalBasis", "thuvienphapluat-vn-vbpl", "method"),
    "edges_citation": ("cites", "thuvienphapluat-vn-vbpl", "method"),
    "edges_decision_provision": ("appliesProvision", "cbba-toaan-gov-vn", "method"),
    "edges_decision_case": ("citesCase", "cbba-toaan-gov-vn", "method"),
    "edges_precedent_source": ("selectedFrom", "anle-toaan-gov-vn", "method"),
    "edges_qa_article": ("answerCitesProvision", "thuvienphapluat-vn-hdpl", "method"),
    "edges_qa_document": ("answerCitesDocument", "thuvienphapluat-vn-hdpl", "method"),
    "edges_term_related": ("relatedTerm", "thuvienphapluat-vn-tnpl", "method"),
    "edges_news_document": ("mentionsDocument", "thuvienphapluat-vn-htpl", "method"),
}


def lit_py(s, lang=None, dt=None):
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", nfc(str(s))).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{s}"' + (f"@{lang}" if lang else (f"^^<{XSD}{dt}>" if dt else ""))


def provenance_lines(kg):
    out = []
    b = f"<{C.iri_build()}>"
    out += [f"{b} {RDF_TYPE} {P('BuildActivity')} .", f"{b} {RDFS_LABEL} {lit_py('VLOnto build ' + C.VERSION + ' (' + C.BUILD_DATE + ')', 'en')} .",
            f"{b} {P('validityAsOf')} {lit_py(C.VALIDITY_AS_OF, dt='date')} .", f"{b} {P('softwareVersion')} {lit_py(C.VERSION)} .",
            f"{b} <{PROV}startedAtTime> {lit_py(C.BUILD_DATE + 'T00:00:00Z', dt='dateTime')} ."]
    srcs = pl.read_parquet(os.path.join(kg, "sources.parquet"))
    for r in srcs.iter_rows(named=True):
        s = f"<{r['iri']}>"
        out += [f"{s} {RDF_TYPE} {P('SourceDataset')} .", f"{s} {RDFS_LABEL} {lit_py('tmquan/' + r['dataset'], 'en')} .",
                f"{s} {P('datasetRevision')} {lit_py(r['revision'])} .", f"{s} {P('licenceLabel')} {lit_py(r['licence'])} .",
                f"{s} {P('attributionText')} {lit_py(ATTRIB[r['dataset']], 'en')} .", f"{s} {P('inclusionPolicy')} {lit_py(POLICY[r['dataset']], 'en')} .",
                f"{s} {P('sourceUrl')} {lit_py(r['repository'], dt='anyURI')} .", f"{b} <{PROV}used> {s} ."]
        if r["licence"] == "cc-by-4.0":
            out.append(f"{s} <{DCT}license> <{CC_BY}> .")
    for table, (prop, ds, mcol) in EDGESETS.items():
        p = os.path.join(kg, table + ".parquet")
        if not os.path.exists(p):
            continue
        df = pl.read_parquet(p)
        es = f"<{C.iri_edgeset(table)}>"
        out += [f"{es} {RDF_TYPE} {P('EdgeSet')} .", f"{es} {RDFS_LABEL} {lit_py(table, 'en')} .", f"{es} {P('edgeProperty')} {P(prop)} .",
                f"{es} {P('edgeCount')} {lit_py(df.height, dt='integer')} .", f"{es} <{PROV}wasGeneratedBy> {b} .",
                f"{es} {P('sourceDataset')} <{C.iri_source(ds)}> ."]
        if table in ("edges_decision_provision", "edges_decision_case"):
            out.append(f"{es} {P('sourceDataset')} <{C.iri_source('anle-toaan-gov-vn')}> .")
        counts = df.group_by(mcol).len().sort("len", descending=True).rows()
        for m, n in counts:
            if m:
                out.append(f"{es} {P('extractionMethod')} {P('method-' + m)} .")
        out.append(f"{es} {RDFS_COMMENT} {lit_py('links by method: ' + ', '.join(f'{m}={n}' for m, n in counts), 'en')} .")
    return out


# ------------------------------------------------------------------ parts
def _prep(name, kg):
    df = pl.read_parquet(os.path.join(kg, name + ".parquet"))
    if name in ("articles", "structure", "provisions_ref"):
        d = pl.read_parquet(os.path.join(kg, "documents.parquet"), columns=["doc_id", "doc_number", "title_vi"]).with_columns(
            pl.col("title_vi").str.slice(0, 60).alias("doc_title_short"))
        df = df.join(d.select("doc_id", "doc_number", "doc_title_short"), on="doc_id", how="left")
        if name in ("articles", "structure"):
            df = df.with_columns(pl.when(pl.col("parent_id").str.contains("::")).then(pl.lit(ID + "document/") + pl.col("parent_id").str.replace("::", "/"))
                                 .otherwise(pl.lit(ID + "document/") + pl.col("parent_id")).alias("parent_iri"))
        else:
            df = df.with_columns((pl.lit(ID + "document/") + pl.col("parent_id").str.replace_all("::", "/")).alias("parent_iri"),
                                 pl.concat_str([pl.lit("Điều "), pl.col("article_id").str.extract(r"dieu-(.+)$"), pl.lit(", "),
                                                pl.col("doc_number").fill_null(pl.col("doc_title_short"))]).alias("article_label"))
    return df


PARTS = [("documents", lines_documents), ("structure", lines_structure), ("articles", lines_articles),
         ("provisions_ref", lines_provisions_ref), ("issuers", lines_issuers), ("areas", lines_areas), ("changes", lines_changes),
         ("edges_legal_basis", lambda d: lines_edges_doc(d, "legalBasis")), ("edges_citation", lines_citations),
         ("courts", lines_courts), ("decisions", lines_decisions), ("precedents", lines_precedents),
         ("edges_decision_provision", lines_decision_provision), ("edges_decision_case", lines_decision_case),
         ("qas", lines_qas), ("edges_qa_article", lines_qa_article), ("edges_qa_document", lines_qa_document),
         ("terms", lines_terms), ("edges_term_related", lines_term_related), ("news_categories", lines_news_categories),
         ("news", lines_news), ("edges_news_document", lines_news_document)]


def _write_part(args):
    name, fn_name, kg, outdir = args
    fn = dict(PARTS)[name]
    t0 = time.time()
    df = _prep(name, kg)
    series = fn(df)
    path = os.path.join(outdir, f"part_{name}.nt.gz")
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        for s in series:
            if len(s):
                f.write("\n".join(str_normalize(s).to_list()))     # IRIs and literals in NFC
                f.write("\n")
                n += len(s)
    return name, n, round(time.time() - t0, 1)


def export_all(workers=12):
    t0 = time.time()
    kg, out = C.KG, C.RDF_DIR
    parts_dir = os.path.join(out, "parts")
    os.makedirs(parts_dir, exist_ok=True)
    rep = {"parts": {}}
    # ontology part
    from rdflib import Graph
    og = Graph().parse(os.path.join(C.REPO, "ontology", "vlonto.ttl"))
    onto_nt = nfc(og.serialize(format="nt"))
    with gzip.open(os.path.join(parts_dir, "part_00_ontology.nt.gz"), "wt", encoding="utf-8") as f:
        f.write(onto_nt if onto_nt.endswith("\n") else onto_nt + "\n")
    rep["parts"]["ontology"] = len(og)
    prov = provenance_lines(kg)
    with gzip.open(os.path.join(parts_dir, "part_01_provenance.nt.gz"), "wt", encoding="utf-8") as f:
        f.write(nfc("\n".join(prov) + "\n"))
    rep["parts"]["provenance"] = len(prov)
    jobs = [(name, name, kg, parts_dir) for name, _ in PARTS]
    with mp.get_context("spawn").Pool(min(workers, len(jobs))) as pool:
        for name, n, s in pool.imap_unordered(_write_part, jobs):
            rep["parts"][name] = n
            rep.setdefault("part_wall_s", {})[name] = s
            print(f"  part {name}: {n:,} triples ({s}s)", flush=True)
    full = os.path.join(out, "vlonto-kg.nt.gz")
    order = ["part_00_ontology.nt.gz", "part_01_provenance.nt.gz"] + [f"part_{n}.nt.gz" for n, _ in PARTS]
    with open(full, "wb") as w:
        for p in order:
            with open(os.path.join(parts_dir, p), "rb") as r:
                shutil.copyfileobj(r, w, 1 << 24)
    rep["triples_total"] = sum(rep["parts"].values())
    rep["nt_gz_bytes"] = os.path.getsize(full)
    rep["nt_gz_path"] = full
    rep["wall_s"] = round(time.time() - t0, 1)
    with open(os.path.join(C.REPORTS, "export_report.json"), "w") as f:
        json.dump(rep, f, indent=1)
    return rep


# ------------------------------------------------------------------ core subset
def core_subset(max_rank=None, max_triples=200_000):
    """Browser-sized Turtle: documents with rank <= max_rank and everything they need."""
    from rdflib import Graph
    t0 = time.time()
    kg = C.KG
    docs = pl.read_parquet(os.path.join(kg, "documents.parquet"))
    rep = {}
    ranks = [max_rank] if max_rank is not None else [2, 1]
    for mr in ranks:
        core = docs.filter(pl.col("legal_force_rank") <= mr)
        ids = core["doc_id"].to_list()
        ch = pl.read_parquet(os.path.join(kg, "changes.parquet")).filter(pl.col("acting_doc_id").is_in(ids) & pl.col("affected_doc_id").is_in(ids))
        lb = pl.read_parquet(os.path.join(kg, "edges_legal_basis.parquet")).filter(pl.col("src_doc_id").is_in(ids) & pl.col("dst_doc_id").is_in(ids))
        ci = (pl.read_parquet(os.path.join(kg, "edges_citation.parquet")).filter(pl.col("src_doc_id").is_in(ids) & pl.col("dst_doc_id").is_in(ids))
              .with_columns(pl.when(pl.col("kind").str.starts_with("parent_law")).then(pl.lit("citesParentLaw")).otherwise(pl.lit("cites")).alias("p"))
              .select("src_doc_id", "dst_doc_id", "p").unique().filter(pl.col("src_doc_id") != pl.col("dst_doc_id")))
        lines = []
        for fn, df in ((lines_documents, core), (lines_changes, ch)):
            for s in fn(df):
                lines += s.to_list()
        lines += lines_edges_doc(lb, "legalBasis")[0].to_list()
        for p in ("cites", "citesParentLaw"):
            lines += lines_edges_doc(ci.filter(pl.col("p") == p), p)[0].to_list()
        iss = pl.read_parquet(os.path.join(kg, "issuers.parquet"))
        areas = pl.read_parquet(os.path.join(kg, "areas.parquet"))
        prec = pl.read_parquet(os.path.join(kg, "precedents.parquet")).with_columns(pl.lit(None, dtype=pl.List(pl.Utf8)).alias("source_decision_ids"))
        for fn, df in ((lines_issuers, iss), (lines_areas, areas), (lines_precedents, prec)):
            for s in fn(df):
                lines += s.to_list()
        lines += provenance_lines(kg)
        n_inst = len(lines)
        rep[mr] = {"documents": core.height, "instance_triples": n_inst}
        if n_inst <= max_triples:
            break
    g = Graph()
    g.parse(os.path.join(C.REPO, "ontology", "vlonto.ttl"))
    n_onto = len(g)
    g.parse(data="\n".join(lines), format="nt")
    for pfx, ns in (("vlo", VLO), ("vlid", ID), ("skos", SKOS), ("xsd", XSD), ("prov", PROV), ("dcterms", DCT),
                    ("eli", "http://data.europa.eu/eli/ontology#"), ("schema", "https://schema.org/"), ("org", "http://www.w3.org/ns/org#")):
        g.bind(pfx, ns, override=True)
    for sub in ("document/", "issuer/", "area/", "change/", "precedent/", "source/", "edgeset/", "build/"):
        g.bind("vl" + sub.strip("/").replace("-", "")[:6], ID + sub, override=True)
    ttl = g.serialize(format="turtle")
    head = ("# VLOnto core subset " + C.VERSION + " (" + C.BUILD_DATE + "): ontology + documents of legal-force rank <= "
            f"{mr} (Constitution, codes, laws, National Assembly resolutions" + (", ordinances and Standing Committee resolutions" if mr >= 2 else "")
            + ") with their change events, legal-basis links and citations among themselves (article-level citations projected to "
            "document level), issuers, legal areas, precedents, source datasets, edge sets and the build activity. Full graph: vlonto-kg.nt.gz.\n")
    path = os.path.join(C.RDF_DIR, "vlonto-core.ttl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(nfc(head + ttl))
    rep["chosen_max_rank"] = mr
    rep["triples"] = len(g)
    rep["ontology_triples"] = n_onto
    rep["bytes"] = os.path.getsize(path)
    rep["documents"] = core.height
    rep["changes"] = ch.height
    rep["legal_basis_edges"] = lb.height
    rep["citation_edges_doc_level"] = ci.height
    rep["wall_s"] = round(time.time() - t0, 1)
    with open(os.path.join(C.REPORTS, "core_report.json"), "w") as f:
        json.dump(rep, f, indent=1, default=str)
    return rep


def js_string_twin(src_path, name, out_dir):
    """window.VLONTO[name] = "<file content>" for offline (file://) pages that cannot fetch()."""
    os.makedirs(out_dir, exist_ok=True)
    s = nfc(open(src_path, encoding="utf-8").read())
    out = os.path.join(out_dir, f"{name}.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.VLONTO = window.VLONTO || {};\nwindow.VLONTO[" + json.dumps(name) + "] = " + json.dumps(s, ensure_ascii=False) + ";\n")
    return out, os.path.getsize(out)

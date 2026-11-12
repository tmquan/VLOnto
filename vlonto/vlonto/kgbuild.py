"""Step 3: build the typed node and edge tables of the VLOnto knowledge graph ($V/build/kg/*.parquet).

Court tables (courts, decisions, precedents and their edges) are built only when config.INCLUDE_COURTS is on
(VLONTO_INCLUDE_COURTS=1); release v1 is built without them (court data is planned for v2).
"""
import glob
import hashlib
import json
import os
import time
from collections import Counter

import polars as pl

from . import config as C
from .build_docs import build_areas, build_articles, build_changes, build_documents, build_issuers
from .build_links import build_links
from .build_other import build_area_table, build_news, build_qa, build_terms

DESCRIPTIONS = {
    "documents": ("Legal documents (40,816 in-scope normative documents from vbpl, after cleaning).", {
        "doc_id": "vbpl document id (primary key)", "iri": "VLOnto IRI", "doc_type_vi": "Vietnamese document type",
        "doc_class": "VLOnto class local name (Law, Decree, ...)", "doc_type_code": "type notation (L, NĐ, TT, ...)",
        "doc_number": "official number, e.g. 45/2019/QH14 (null for 601 documents)", "doc_number_key": "normalised lookup key",
        "title_vi": "Vietnamese title", "title_core": "title without the type word (used for name resolution)",
        "issue_date": "issue date (ISO); null when it is more than one year away from the year in the number",
        "issue_date_check": "ok, missing or year_mismatch_with_number", "issue_date_source": "source issue date when it was rejected",
        "year": "issue year (from the number when the date was rejected)", "effective_date": "entry into force (metadata, then text)",
        "effective_date_src": "source of effective_date", "expiry_date": "no longer in force from",
        "status_raw": "source status string (Vietnamese)", "status_code": "normalised source status", "status_date": "date in the status string",
        "validity": "validity v7 (8 values)", "in_force": "true/false/null", "status_text_conflict": "source says in force but text says superseded",
        "validity_evidence": "status / text / status+text / none", "legal_force_rank": "0 (Constitution) .. 5 (circulars)",
        "area_id": "legal area slug", "issuer_ids": "canonical issuer codes (joint documents have several)",
        "issuer_method": "issuer-code (symbol of the number), doc-type-rule (laws, codes, constitutions -> QH; ordinances), source-metadata, code-unknown, none",
        "issuer_codes_unmatched": "symbol parts of the number that are not a known issuer (kept for transparency, no node)",
        "tier": "vbpl tier (0 primary legislation, 1 central decisions)", "url": "source URL (thuvienphapluat.vn)",
        "n_chapters": "chapters found by the parser", "has_articles": "article structure parsed",
        "source_dataset": "source dataset", "n_articles_main": "main-body articles", "n_articles_appendix": "appendix articles"}),
    "articles": ("Articles (Điều): one node per main-body or appendix article; parts of split articles joined. No text (licence).", {
        "article_id": "<doc_id>::dieu-<n> or <doc_id>::att<s>-dieu-<n> (chunk unit id)", "iri": "VLOnto IRI", "doc_id": "document",
        "article_no": "article number as printed (5, 5a)", "segment": "main or att<s> (appendix s)", "heading": "article heading (<=200 chars)",
        "parent_id": "immediate parent (structure id or doc_id)", "parent_kind": "Document/Appendix/Part/Chapter/Section",
        "position": "order of the article in its document", "n_chunks": "retrieval chunks of the article", "chars": "characters of text",
        "chapter_heading": "chapter heading", "section_heading": "section heading"}),
    "structure": ("Appendices, parts, chapters and sections of documents.", {
        "struct_id": "<doc_id>::<path> e.g. 333670::chuong-iii/muc-3", "doc_id": "document", "kind": "Appendix/Part/Chapter/Section",
        "number": "number token (iii, 3) or o<k> when not parsable", "heading": "heading (<=200 chars)", "parent_id": "parent node",
        "parent_kind": "kind of parent", "position": "order among nodes of this kind in the document", "iri": "VLOnto IRI"}),
    "provisions_ref": ("Clauses (khoản) and points (điểm) created because an edge refers to them.", {
        "prov_id": "<article_id>::khoan-<k>[::diem-<p>] or <article_id>::diem-<p>", "iri": "VLOnto IRI", "kind": "Clause or Point",
        "article_id": "article", "doc_id": "document", "clause": "clause number", "point": "point letter", "parent_id": "article or clause",
        "n_refs": "edges that reference this provision"}),
    "issuers": ("Issuing bodies identified by the symbol of the document number (curated table; unknown symbols get no node).", {
        "issuer_id": "canonical ASCII code (BTC, TTG, QH, ...)", "iri": "VLOnto IRI", "label_vi": "Vietnamese name", "label_en": "English name",
        "kind": "ministry, government, national-assembly, ...", "label_source": "vlonto-table", "code_aliases": "other symbols mapped to this body",
        "n_documents": "documents issued"}),
    "areas": ("Legal areas (SKOS concepts) from vbpl/hdpl (27) and tnpl.", {
        "area_id": "slug", "iri": "VLOnto IRI", "label_vi": "Vietnamese label", "label_en": "English label",
        "label_en_source": "vlonto (written for VLOnto) or tnpl-mt", "schemes": "LegalAreaScheme and/or TermAreaScheme",
        "n_documents": "documents", "n_qas": "Q&As", "n_terms": "terms"}),
    "doc_types": ("Document types (concepts of the ontology).", {}),
    "legal_force_ranks": ("Legal-force ranks (concepts of the ontology).", {}),
    "changes": ("Legal change events (validity relations v7), one per relation.", {
        "change_id": "<acting>-<kind>-<affected>", "iri": "VLOnto IRI", "acting_doc_id": "acting (newer) document",
        "affected_doc_id": "affected document", "kind": "replaced/amended/repealed/partially_repealed/partially_expired",
        "evidence": "operative sentence (<=300 chars)", "effective_date": "effective date of the change", "mentioned_date": "date of the affected act in the sentence",
        "acting_number": "number of acting act", "affected_number": "number of affected act", "affected_number_as_cited": "number as written",
        "method": "validity-rules-v7", "rule_version": "v7"}),
    "edges_change": ("Shortcut edges acting document -> affected document (one per change event).", {
        "src_doc_id": "acting document", "dst_doc_id": "affected document", "kind": "change kind", "property": "vlo property", "change_id": "event", "method": "validity-rules-v7"}),
    "edges_legal_basis": ("Legal basis: citing document -> basis document.", {
        "src_doc_id": "citing document", "dst_doc_id": "basis document", "method": "parent-acts, preamble-citation or constitution-preamble (first in this order when several apply)",
        "methods": "all methods that found the edge", "resolve_method": "docnum-key or law-name-year", "raw": "reference as written"}),
    "edges_citation": ("vbpl citations (external, external_mention, parent_law, parent_law_mention) resolved to documents/articles.", {
        "src_doc_id": "citing document", "src_article_id": "citing article when known", "dst_doc_id": "cited document",
        "dst_article_id": "cited article when given and present", "clause": "cited clause", "point": "cited point", "kind": "vbpl citation kind",
        "n_mentions": "records merged into this edge", "article_cited": "article number written (even if absent)", "source_location": "where in the citing document",
        "raw": "citation as written (<=200 chars)", "method": "docnum-key or law-name-year"}),
    "courts": ("Canonical courts named in decisions (source field or judgment header; anonymised and unparsable names dropped).", {
        "court_id": "slug of the canonical name", "iri": "VLOnto IRI", "label": "canonical court name",
        "court_kind": "supreme, high, military, provincial, district (huyện/quận/thị xã/thành phố thuộc tỉnh) or regional (khu vực, from 2025)",
        "court_level": "Supreme/High/Provincial/District/Military (regional courts: District)", "province": "province or centrally run city (null when never stated)",
        "head": "upper-case name phrase used to match case citations (province added for district names used in several provinces)", "n_decisions": "decisions",
        "n_from_header": "decisions whose court came from the header", "n_province_from_name": "decisions whose province was inferred from the same name elsewhere"}),
    "decisions": ("Court decisions from anle (1,844) and cbba (16 shards).", {
        "decision_id": "<source>:<doc_name>", "iri": "VLOnto IRI", "source": "anle or cbba", "doc_name": "source id",
        "decision_number": "e.g. 38/2021/DS-PT", "decision_code": "symbol, e.g. DS-PT", "number": "number part", "year_in_number": "year part",
        "decision_kind": "Judgment / CourtRuling / CourtDecision", "category": "case category", "instance_level": "procedural stage",
        "court_level": "court level (source, else inferred from the court name)", "court_id": "canonical court (null when masked/unparsable/ambiguous)",
        "court_method": "court-name:field or court-name:header (+province-from-name)", "court_note": "why court_id is null: masked, unparsed, ambiguous-without-province, regional-without-province",
        "issued_date": "decision date (null when the source date fails the checks)", "issued_date_check": "ok, missing, malformed, out_of_range, year_mismatch (vs year in the number), before_cited_document (earlier than the year of a cited law or decision), number_is_legislative (the source number is that of a cited law; number, code and date dropped)",
        "year": "decision year", "url": "source URL", "is_precedent_source": "selected as a precedent",
        "precedent_number": "precedent number if any", "n_law_citations": "law citation records in source", "n_case_citations": "case citation records in source",
        "n_law_edges": "applied-provision edges after resolution", "n_case_edges": "case edges after resolution"}),
    "precedents": ("Precedents (án lệ) by national number.", {
        "precedent_id": "NN-YYYY-al", "precedent_number": "NN/YYYY/AL", "source_decision_ids": "decisions selected as the precedent",
        "n_citing_decisions": "decisions citing it", "iri": "VLOnto IRI"}),
    "edges_decision_provision": ("Applied provisions: decision -> document / article (+clause, point).", {
        "decision_id": "decision", "dst_doc_id": "document", "dst_article_id": "article when present", "clause": "clause", "point": "point",
        "n_mentions": "records merged", "article_cited": "article written", "cit_kind": "provision or document", "law_type": "law type written",
        "ref": "reference as written (<=160)", "sentence_id": "source sentence id (pointer, no text)", "method": "docnum-key or law-name-year"}),
    "edges_decision_case": ("Case-to-case edges: decision -> decision or precedent.", {
        "src_id": "citing decision", "dst_id": "cited decision or precedent", "dst_kind": "decision or precedent", "cited_id": "number as written",
        "role": "role in source (first-instance, appellate, ...)", "method": "case-number-date, case-number-court or precedent-number"}),
    "edges_precedent_source": ("Precedent -> source decision (selected from).", {"src_id": "precedent", "dst_id": "decision", "method": "source-metadata"}),
    "qas": ("Legal Q&As from hdpl: metadata only (no question or answer text).", {
        "qa_id": "hdpl id", "iri": "question IRI", "answer_iri": "answer IRI", "url": "source URL", "published_date": "publication date",
        "year": "publication year", "category": "category slug", "area_id": "legal area", "has_ad": "advertising flag of the source",
        "n_citation_records": "citation records", "n_document_citations": "document-level records", "n_provision_citations": "provision-level records",
        "n_gold_articles": "articles linked (gold resolver)", "n_documents_resolved": "documents linked by number"}),
    "edges_qa_article": ("Q&A answer -> article (+clause, point) from the gold resolver (gold_all.parquet).", {
        "qa_id": "Q&A", "dst_doc_id": "document", "dst_article_id": "article", "clause": "clause", "point": "point", "ref": "reference as written",
        "method": "answer-text-number / answer-text-name / citation-field-name / unique-document-of-type", "method_detail": "gold method string"}),
    "edges_qa_document": ("Q&A answer -> document cited by number.", {
        "qa_id": "Q&A", "dst_doc_id": "document", "number_cited": "number as written", "law_type": "law type", "method": "docnum-key"}),
    "terms": ("Legal terms from tnpl (names only, no definitions).", {
        "term_id": "tnpl id", "iri": "VLOnto IRI", "label_vi": "Vietnamese term", "label_en": "English label", "label_en_source": "mt or site",
        "translation_model": "MT model", "area_id": "area slug", "tnpl_area_id": "tnpl area id", "status_vi": "status", "in_force": "status as boolean", "url": "source URL"}),
    "edges_term_related": ("Related terms.", {"src_term_id": "term", "dst_term_id": "related term", "method": "source-metadata"}),
    "news": ("Legal news articles from htpl (no title or text).", {
        "news_id": "htpl id", "iri": "VLOnto IRI", "url": "source URL", "category": "category slug", "published_date": "date",
        "year": "year", "n_numbers_found": "document numbers found", "n_documents_resolved": "documents linked"}),
    "edges_news_document": ("News article -> mentioned document.", {"news_id": "news", "dst_doc_id": "document", "number_found": "number", "method": "docnum-regex"}),
    "news_categories": ("News categories.", {}),
    "sources": ("Source datasets of this build with revision, licence and policy (release v1: the four thuvienphapluat.vn datasets).", {}),
}


def write(df, name, rep, local=False):
    from .nfc import nfc_df
    d = C.KG_LOCAL if local else C.KG
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".parquet")
    df, changed = nfc_df(df)          # every string column in Unicode NFC
    if changed:
        rep.setdefault("nfc_values_changed", {})[name] = changed
    df.write_parquet(path, compression="zstd")
    rep["files"][name] = {"rows": df.height, "bytes": os.path.getsize(path), "path": path, "columns": df.columns}
    print(f"  wrote {name}: {df.height:,} rows", flush=True)


def provisions_ref(edge_tables):
    rows = Counter()
    for df in edge_tables:
        sub = df.filter(pl.col("dst_article_id").is_not_null() & (pl.col("clause").is_not_null() | pl.col("point").is_not_null()))
        for a, k, p in sub.select("dst_article_id", "clause", "point").iter_rows():
            if k:
                rows[(a, k, None)] += 1
                if p:
                    rows[(a, k, p)] += 1
            elif p:
                rows[(a, None, p)] += 1
    out = []
    for (a, k, p), n in rows.items():
        doc = a.split("::")[0]
        if k and not p:
            pid, kind, parent = f"{a}::khoan-{k}", "Clause", a
        elif k and p:
            pid, kind, parent = f"{a}::khoan-{k}::diem-{p}", "Point", f"{a}::khoan-{k}"
        else:
            pid, kind, parent = f"{a}::diem-{p}", "Point", a
        out.append({"prov_id": pid, "iri": C.iri_prov_ref(pid), "kind": kind, "article_id": a, "doc_id": doc,
                    "clause": k, "point": p, "parent_id": parent, "n_refs": n})
    return pl.DataFrame(out, infer_schema_length=None)


def sources_table():
    rows = []
    for ds, s in C.SOURCES.items():
        card = os.path.join(C.BUILD, "cards", f"{ds}.README.md")
        sha = hashlib.sha256(open(card, "rb").read()).hexdigest() if os.path.exists(card) else None
        rows.append({"dataset": ds, "iri": C.iri_source(ds), "revision": s["revision"], "licence": s["licence"],
                     "publisher": s["publisher"], "content": s["kind"], "repository": f"https://huggingface.co/datasets/tmquan/{ds}",
                     "card_sha256": sha})
    return pl.DataFrame(rows)


def data_dictionary(rep):
    if C.INCLUDE_COURTS:
        scope = "Sources: " + ", ".join(f"`{k}`" for k in C.SOURCES) + " (court data included)."
    else:
        scope = (f"Release {C.RELEASE} sources: " + ", ".join(f"`{k}`" for k in C.SOURCES) + ". Court data ("
                 + ", ".join(f"`{k}`" for k in C.DEFERRED_SOURCES) + ") is planned for v2: the ontology keeps the judiciary "
                 "classes, but this build has no court, decision or precedent tables.")
    md = ["# VLOnto knowledge-graph data dictionary", "",
          f"Version {C.VERSION} (release {C.RELEASE}), built {C.BUILD_DATE}, document validity as of {C.VALIDITY_AS_OF}. "
          f"Tables are parquet (zstd) files in `{C.rel(C.KG)}`; "
          f"`{C.rel(C.KG_LOCAL)}` holds local-only tables that are not for publication (licence policy). "
          "Paths are relative to the VLOnto root.", "", scope, "",
          "IRIs: documents `id/document/<doc_id>`, articles `id/document/<doc_id>/dieu-<n>`, clauses `.../khoan-<k>`, "
          "points `.../diem-<p>`, " + ("decisions `id/decision/<source>/<doc_name>`, courts `id/court/<slug>`, " if C.INCLUDE_COURTS else "")
          + "Q&As `id/qa/<id>` (answer `id/qa/<id>/answer`), terms `id/term/<id>`, news `id/news/<id>`, under https://tmquan.github.io/VLOnto/.", ""]
    js = {}
    for name, f in rep["files"].items():
        desc, cols = DESCRIPTIONS.get(name, ("", {}))
        df = pl.read_parquet(f["path"])
        md.append(f"## `{name}` ({f['rows']:,} rows{', local only' if C.KG_LOCAL in f['path'] else ''})")
        md.append("")
        md.append(desc)
        md.append("")
        md.append("| Column | Type | Non-null | Description |")
        md.append("|---|---|---|---|")
        jcols = []
        for c, t in df.schema.items():
            nn = df.height - df[c].null_count()
            d = cols.get(c, "")
            md.append(f"| `{c}` | {t} | {nn:,} | {d} |")
            jcols.append({"name": c, "type": str(t), "non_null": nn, "description": d})
        md.append("")
        js[name] = {"path": C.rel(f["path"]), "rows": df.height, "bytes": os.path.getsize(f["path"]), "description": desc, "columns": jcols}
    os.makedirs(C.REPORTS, exist_ok=True)
    from .nfc import nfc, nfc_obj
    with open(os.path.join(C.KG, "data_dictionary.md"), "w", encoding="utf-8") as fh:
        fh.write(nfc("\n".join(md) + "\n"))
    with open(os.path.join(C.KG, "data_dictionary.json"), "w", encoding="utf-8") as fh:
        json.dump(nfc_obj(js), fh, ensure_ascii=False, indent=1)


def remove_stale_court_tables(rep):
    """A build without court data must not leave court tables of an earlier build in the output directory."""
    gone = []
    for name in C.COURT_TABLES:
        p = os.path.join(C.KG, name + ".parquet")
        if os.path.exists(p):
            os.remove(p)
            gone.append(name)
    rep["stale_court_tables_removed"] = gone
    return gone


def build_all(with_text=True):
    t0 = time.time()
    rep = {"version": C.VERSION, "release": C.RELEASE, "build_date": C.BUILD_DATE, "courts_included": C.INCLUDE_COURTS,
           "sources": list(C.SOURCES), "deferred_sources": list(C.DEFERRED_SOURCES), "files": {}}
    os.makedirs(C.KG, exist_ok=True)
    print("documents ...", flush=True)
    docs = build_documents(rep)
    issuers = build_issuers(docs, rep)
    arts, structs, txt = build_articles(docs, rep, with_text)
    na = arts.group_by("doc_id").agg((pl.col("segment") == "main").sum().alias("n_articles_main"),
                                      (pl.col("segment") != "main").sum().alias("n_articles_appendix"))
    docs = docs.join(na, on="doc_id", how="left").with_columns(pl.col("n_articles_main").fill_null(0), pl.col("n_articles_appendix").fill_null(0))
    doc_areas = build_areas(docs, rep)
    changes = build_changes(docs, rep)
    ec = changes.select(pl.col("acting_doc_id").alias("src_doc_id"), pl.col("affected_doc_id").alias("dst_doc_id"), "kind",
                        pl.col("kind").replace_strict(C.CHANGE_PROPERTY).alias("property"), "change_id", "method")
    print("links ...", flush=True)
    cit, basis = build_links(docs, arts, rep)
    if C.INCLUDE_COURTS:
        print("courts ...", flush=True)
        from .build_courts import build_courts
        dec, courts, precedents, law, case_edges, prec_src = build_courts(docs, arts, rep)
        court_tables = [(courts, "courts"), (dec, "decisions"), (precedents, "precedents"), (law, "edges_decision_provision"),
                        (case_edges, "edges_decision_case"), (prec_src, "edges_precedent_source")]
        law_edges = [law]
    else:
        print("courts: not built (VLONTO_INCLUDE_COURTS=0; court data is planned for v2)", flush=True)
        court_tables, law_edges = [], []
        remove_stale_court_tables(rep)
    print("qa, terms, news ...", flush=True)
    qas, qa_art, qa_doc = build_qa(docs, arts, rep)
    terms, term_rel, term_area_labels = build_terms(rep)
    news, news_edges = build_news(docs, rep)
    areas = build_area_table(doc_areas, qas, terms, term_area_labels, rep)
    pref = provisions_ref([cit, *law_edges, qa_art])
    rep["provisions_ref"] = dict(Counter(pref["kind"].to_list())) if pref.height else {}
    dt = pl.DataFrame([{"doc_type_vi": k, "label_en": C.DOC_TYPE_EN[k], "class": v[0], "concept": v[1], "notation": v[2],
                        "n_documents": int((docs["doc_type_vi"] == k).sum())} for k, v in C.DOC_TYPES.items()])
    rk = pl.DataFrame([{"rank": k, "concept": f"rank-{k}", "label_en": v[0], "label_vi": v[1],
                        "n_documents": int((docs["legal_force_rank"] == k).sum())} for k, v in C.RANK_LABELS.items()])
    nc = pl.DataFrame([{"category": k, "iri": C.iri_news_category(k), "label_vi": v[0], "label_en": v[1],
                        "n_articles": int((news["category"] == k).sum())} for k, v in C.NEWS_CATEGORY_LABELS.items()])
    print("writing ...", flush=True)
    tables = [(docs, "documents"), (arts, "articles"), (structs, "structure"), (pref, "provisions_ref"), (issuers, "issuers"),
              (areas, "areas"), (dt, "doc_types"), (rk, "legal_force_ranks"), (changes, "changes"), (ec, "edges_change"),
              (basis, "edges_legal_basis"), (cit, "edges_citation"), *court_tables, (qas, "qas"), (qa_art, "edges_qa_article"),
              (qa_doc, "edges_qa_document"), (terms, "terms"), (term_rel, "edges_term_related"), (news, "news"),
              (news_edges, "edges_news_document"), (nc, "news_categories"), (sources_table(), "sources")]
    for df, name in tables:
        write(df, name, rep)
    if txt is not None:
        write(txt, "article_text", rep, local=True)
    data_dictionary(rep)
    rep["wall_total_s"] = round(time.time() - t0, 1)
    os.makedirs(C.REPORTS, exist_ok=True)
    with open(os.path.join(C.REPORTS, "build_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1, default=str)
    print(f"build done in {rep['wall_total_s']} s", flush=True)
    return rep

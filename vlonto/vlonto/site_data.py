"""Step 5: statistics and compact data bundles for the website and the playbook ($V/build/site_data).

stats.json            headline numbers
dashboard.json        aggregates for the dashboard charts
ontology_graph.json   classes, external aligned terms and concept schemes with links (3D ontology playground)
legal_network.json    all documents with 3D coordinates + change/basis/citation edges (layout3d.py); _lite subset
sparql_examples.json  example queries with their result counts on vlonto-core.ttl
js/<name>.js          offline twins: window.VLONTO["<name>"] = <same JSON>; also vlonto_core_ttl.js and
                      vlonto_ontology_ttl.js holding the Turtle files as strings (no fetch() under file://)
manifest.json         files, sizes, sha256
"""
import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict

import polars as pl

from . import config as C
from .layout3d import main as layout_main, write_js_twin
from .export_rdf import js_string_twin

MAX_BYTES = 20 * 1024 * 1024


def T(name, cols=None):
    return pl.read_parquet(os.path.join(C.KG, name + ".parquet"), columns=cols)


def dump(obj, name):
    os.makedirs(C.SITE, exist_ok=True)
    p = os.path.join(C.SITE, name + ".json")
    from .nfc import nfc_obj
    with open(p, "w", encoding="utf-8") as f:
        json.dump(nfc_obj(json.loads(json.dumps(obj, default=str))), f, ensure_ascii=False, separators=(",", ":"))
    write_js_twin(p, name)
    return p


def desc(df, cnt, *keys):
    """Sort by a count column (descending), then by the key columns (ascending): polars group_by output order is
    not stable between runs, so ties would otherwise reorder (or swap the last entry of a top-n list) on every rebuild."""
    return df.sort([cnt, *keys], descending=[True] + [False] * len(keys), nulls_last=True)


def rows(df):
    return df.to_dicts()


def doc_label(dm, d):
    r = dm.get(d) or {}
    return {"id": d, "number": r.get("doc_number"), "title": C.cut(r.get("title_vi"), 90), "type": r.get("doc_type_code"),
            "year": r.get("year"), "validity": r.get("validity"), "url": r.get("url")}


def art_label(am, dm, a):
    r = am.get(a) or {}
    d = a.split("::")[0]
    dd = dm.get(d) or {}
    return {"id": a, "doc_id": d, "article": r.get("article_no"), "heading": r.get("heading"), "number": dd.get("doc_number"),
            "title": C.cut(dd.get("title_vi"), 70), "type": dd.get("doc_type_code")}


def stats_and_dashboard(build, export, core, validation):
    docs = T("documents")
    dm = {r["doc_id"]: r for r in docs.select("doc_id", "doc_number", "title_vi", "doc_type_code", "year", "validity", "url").iter_rows(named=True)}
    arts = T("articles", ["article_id", "article_no", "heading", "segment", "doc_id"])
    am = {r["article_id"]: r for r in arts.iter_rows(named=True)}
    ch, lb, ci = T("changes"), T("edges_legal_basis"), T("edges_citation")
    dec, dp, dc = T("decisions"), T("edges_decision_provision"), T("edges_decision_case")
    qas, qa_art, qa_doc = T("qas"), T("edges_qa_article"), T("edges_qa_document")
    terms, news, ne, areas, iss, courts, prec = T("terms"), T("news"), T("edges_news_document"), T("areas"), T("issuers"), T("courts"), T("precedents")
    files = build.get("files", {})
    n_nodes = sum(files[k]["rows"] for k in ("documents", "articles", "structure", "provisions_ref", "issuers", "areas", "changes", "courts",
                                             "decisions", "precedents", "qas", "terms", "news", "news_categories", "sources") if k in files) + qas.height
    n_edges = sum(files[k]["rows"] for k in files if k.startswith("edges_"))
    stats = {
        "name": "VLOnto", "version": C.VERSION, "build_date": C.BUILD_DATE, "validity_as_of": C.VALIDITY_AS_OF,
        "documents": docs.height, "documents_by_type": dict(Counter(docs["doc_type_vi"].to_list())),
        "articles": arts.height, "articles_main_body": int((arts["segment"] == "main").sum()), "articles_appendix": int((arts["segment"] != "main").sum()),
        "structure_nodes": dict(Counter(T("structure", ["kind"])["kind"].to_list())), "clause_point_nodes": dict(Counter(T("provisions_ref", ["kind"])["kind"].to_list())),
        "issuing_bodies": iss.height, "legal_areas": areas.height, "change_events": ch.height, "change_events_by_kind": dict(Counter(ch["kind"].to_list())),
        "legal_basis_links": lb.height, "citation_links": ci.height, "court_decisions": dec.height,
        "court_decisions_by_source": dict(Counter(dec["source"].to_list())), "courts": courts.height, "precedents": prec.height,
        "applied_provision_links": dp.height, "case_links": dc.height, "legal_questions": qas.height,
        "qa_article_links": qa_art.height, "qa_document_links": qa_doc.height, "legal_terms": terms.height,
        "term_links": T("edges_term_related").height, "news_articles": news.height, "news_document_links": ne.height,
        "validity": dict(Counter(docs["validity"].to_list())),
        "kg_nodes_parquet": n_nodes, "kg_edges_parquet": n_edges,
        "rdf_triples": export.get("triples_total"), "rdf_triples_loaded": (validation or {}).get("oxigraph", {}).get("triples_loaded"),
        "rdf_nt_gz_bytes": export.get("nt_gz_bytes"), "core_ttl_triples": core.get("triples"), "core_ttl_bytes": core.get("bytes"),
        "ontology": {"classes": None, "object_properties": None, "datatype_properties": None},
        "sources": {k: {"revision": v["revision"], "licence": v["licence"]} for k, v in C.SOURCES.items()},
    }
    # ---------------- dashboard
    db = {"version": C.VERSION, "generated": C.BUILD_DATE}
    d2 = docs.with_columns(pl.col("year").fill_null(-1))
    db["documents_by_type_year"] = rows(d2.group_by("doc_type_code", "year").len().sort("doc_type_code", "year").rename({"len": "n"}))
    il = {r["issuer_id"]: r for r in iss.iter_rows(named=True)}
    ex = docs.select("issuer_ids").explode("issuer_ids").drop_nulls()
    top_iss = desc(ex.group_by("issuer_ids").len(), "len", "issuer_ids").head(50)
    db["documents_by_issuer_top50"] = [{"issuer": a, "vi": il[a]["label_vi"], "en": il[a]["label_en"], "n": n} for a, n in top_iss.iter_rows()]
    al = {r["area_id"]: r for r in areas.iter_rows(named=True)}
    db["documents_by_area"] = [{"area": a, "vi": al.get(a, {}).get("label_vi"), "en": al.get(a, {}).get("label_en"), "n": n}
                               for a, n in desc(docs.group_by("area_id").len(), "len", "area_id").iter_rows() if a]
    db["validity_by_type"] = rows(docs.group_by("doc_type_code", "validity").len().sort("doc_type_code", "validity").rename({"len": "n"}))
    db["documents_by_rank"] = rows(docs.group_by("legal_force_rank").len().sort("legal_force_rank").rename({"len": "n"}))
    db["changes_by_kind_year"] = rows(ch.with_columns(pl.col("effective_date").str.slice(0, 4).cast(pl.Int32, strict=False).fill_null(-1).alias("year"))
                                      .group_by("kind", "year").len().sort("kind", "year").rename({"len": "n"}))
    db["legal_basis_by_method"] = rows(desc(lb.group_by("method").len(), "len", "method").rename({"len": "n"}))
    db["citations_by_kind"] = rows(desc(ci.group_by("kind").agg(pl.len().alias("edges"), pl.col("n_mentions").sum().alias("records"),
                                                             pl.col("dst_article_id").is_not_null().sum().alias("article_level")), "edges", "kind"))
    # most-cited documents and articles by source (distinct citing items)
    def top_docs(df, src_col, n=50):
        t = desc(df.group_by("dst_doc_id").agg(pl.col(src_col).n_unique().alias("citing")), "citing", "dst_doc_id").head(n)
        return [{**doc_label(dm, d), "citing": c} for d, c in t.iter_rows()]

    def top_arts(df, src_col, n=50):
        t = desc(df.filter(pl.col("dst_article_id").is_not_null()).group_by("dst_article_id").agg(pl.col(src_col).n_unique().alias("citing")),
                 "citing", "dst_article_id").head(n)
        return [{**art_label(am, dm, a), "citing": c} for a, c in t.iter_rows()]

    qa_docs = pl.concat([qa_doc.select("qa_id", "dst_doc_id"), qa_art.select("qa_id", "dst_doc_id")])
    db["most_cited_documents"] = {"vbpl_citations": top_docs(ci.filter(pl.col("src_doc_id") != pl.col("dst_doc_id")), "src_doc_id"),
                                  "qa": top_docs(qa_docs, "qa_id"), "court_decisions": top_docs(dp, "decision_id")}
    db["most_cited_articles"] = {"vbpl_citations": top_arts(ci, "src_doc_id"), "qa": top_arts(qa_art, "qa_id"), "court_decisions": top_arts(dp, "decision_id")}
    db["most_cited_documents_note"] = "citing = number of distinct citing documents / Q&As / court decisions"
    dec2 = dec.with_columns(pl.col("year").fill_null(-1), pl.col("category").fill_null("unknown"), pl.col("court_level").fill_null("unknown"),
                            pl.col("instance_level").fill_null("unknown"))
    db["decisions_by_category_year"] = rows(dec2.group_by("category", "year").len().sort("category", "year").rename({"len": "n"}))
    db["decisions_by_court_level"] = rows(desc(dec2.group_by("court_level").len(), "len", "court_level").rename({"len": "n"}))
    db["decisions_by_instance_level"] = rows(desc(dec2.group_by("instance_level").len(), "len", "instance_level").rename({"len": "n"}))
    db["decisions_by_kind_source"] = rows(desc(dec2.group_by("decision_kind", "source").len(), "len", "decision_kind", "source").rename({"len": "n"}))
    db["top_courts"] = rows(courts.select("court_id", "label", "court_level", "n_decisions").head(30))
    if "court_kind" in courts.columns:
        db["courts_by_kind"] = rows(desc(courts.group_by("court_kind").agg(pl.len().alias("courts"), pl.col("n_decisions").sum().alias("decisions")),
                                         "decisions", "court_kind"))
        db["decisions_by_province"] = rows(desc(courts.filter(pl.col("province").is_not_null()).group_by("province")
                                                .agg(pl.len().alias("courts"), pl.col("n_decisions").sum().alias("decisions")),
                                                "decisions", "province"))
        db["decisions_without_court"] = rows(desc(dec.filter(pl.col("court_id").is_null()).group_by("court_note").len()
                                                  .rename({"len": "n"}), "n", "court_note"))
    db["most_applied_precedents"] = rows(desc(prec, "n_citing_decisions", "precedent_number").select("precedent_number", "n_citing_decisions").head(30))
    db["case_links_by_method"] = rows(desc(dc.group_by("method").len(), "len", "method").rename({"len": "n"}))
    q2 = qas.with_columns(pl.col("year").fill_null(-1))
    db["qas_by_area_year"] = rows(q2.group_by("area_id", "year").len().sort("area_id", "year").rename({"len": "n"}))
    db["qa_article_links_by_method"] = rows(desc(qa_art.group_by("method").len(), "len", "method").rename({"len": "n"}))
    db["terms_by_area"] = [{"area": a, "vi": al.get(a, {}).get("label_vi"), "en": al.get(a, {}).get("label_en"), "n": n}
                           for a, n in desc(terms.group_by("area_id").len(), "len", "area_id").iter_rows()]
    db["terms_by_status"] = rows(desc(terms.group_by("status_vi").len(), "len", "status_vi").rename({"len": "n"}))
    db["news_by_category_month"] = rows(news.with_columns(pl.col("published_date").str.slice(0, 7).fill_null("unknown").alias("month"))
                                        .group_by("category", "month").len().sort("category", "month").rename({"len": "n"}))
    db["labels"] = {"areas": {r["area_id"]: {"vi": r["label_vi"], "en": r["label_en"]} for r in areas.iter_rows(named=True)},
                    "doc_types": {v[2]: {"vi": k, "en": C.DOC_TYPE_EN[k]} for k, v in C.DOC_TYPES.items()},
                    "ranks": {str(k): {"en": v[0], "vi": v[1]} for k, v in C.RANK_LABELS.items()},
                    "news_categories": {k: {"vi": v[0], "en": v[1]} for k, v in C.NEWS_CATEGORY_LABELS.items()}}
    return stats, db


def ontology_graph():
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import OWL, RDF, RDFS, SKOS
    g = Graph().parse(os.path.join(C.REPO, "ontology", "vlonto.ttl"))
    VLO = C.VLO
    pref = {VLO: "vlo:", "http://data.europa.eu/eli/ontology#": "eli:", "https://schema.org/": "schema:", str(SKOS): "skos:",
            "http://www.w3.org/ns/prov#": "prov:", "http://www.w3.org/ns/org#": "org:", "http://purl.org/dc/terms/": "dcterms:"}

    def cur(u):
        u = str(u)
        for k, v in pref.items():
            if u.startswith(k):
                return v + u[len(k):]
        return u

    def lab(s, lang):
        for p in (RDFS.label, SKOS.prefLabel):
            for o in g.objects(s, p):
                if isinstance(o, Literal) and o.language == lang:
                    return str(o)
        return None

    def defin(s, lang):
        for o in g.objects(s, SKOS.definition):
            if isinstance(o, Literal) and o.language == lang:
                return str(o)
        return None

    def module(s):
        m = g.value(s, URIRef(VLO + "module"))
        return str(g.value(m, SKOS.notation)) if m is not None else "external"

    counts = class_counts()
    examples = class_examples()
    nodes, links = {}, []
    classes = [s for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)]
    for s in classes:
        local = str(s)
        is_vlo = local.startswith(VLO)
        nodes[cur(s)] = {"id": cur(s), "iri": local, "kind": "class" if is_vlo else "external", "module": module(s) if is_vlo else "external",
                         "label_en": lab(s, "en"), "label_vi": lab(s, "vi"), "definition_en": defin(s, "en"), "definition_vi": defin(s, "vi"),
                         "superclasses": sorted(cur(o) for o in g.objects(s, RDFS.subClassOf) if isinstance(o, URIRef)),
                         "instances": counts.get(cur(s)), "examples": examples.get(cur(s), []), "attributes": []}
    for s in g.subjects(RDF.type, SKOS.ConceptScheme):
        concepts = sorted({c for c in g.subjects(SKOS.inScheme, s)}, key=str)
        nodes[cur(s)] = {"id": cur(s), "iri": str(s), "kind": "scheme", "module": module(s), "label_en": lab(s, "en"), "label_vi": lab(s, "vi"),
                         "definition_en": defin(s, "en"), "definition_vi": None, "superclasses": [],
                         "instances": counts.get(cur(s), len(concepts)),
                         "examples": [{"iri": str(c), "label_en": lab(c, "en"), "label_vi": lab(c, "vi"), "notation": str(g.value(c, SKOS.notation) or "")}
                                      for c in concepts][:12], "attributes": []}
    for s in classes:
        for o in g.objects(s, RDFS.subClassOf):
            if isinstance(o, URIRef) and cur(o) in nodes:
                links.append({"source": cur(s), "target": cur(o), "type": "subClassOf" if str(o).startswith(VLO) else "alignment",
                              "label_en": "subclass of", "label_vi": "lớp con của"})
    scheme_of = {"vlo:DocumentType": "vlo:DocumentTypeScheme", "vlo:ValidityStatus": "vlo:ValidityStatusScheme", "vlo:ChangeKind": "vlo:ChangeKindScheme",
                 "vlo:LegalForceRank": "vlo:LegalForceRankScheme", "vlo:CourtLevel": "vlo:CourtLevelScheme", "vlo:InstanceLevel": "vlo:InstanceLevelScheme",
                 "vlo:CaseCategory": "vlo:CaseCategoryScheme", "vlo:ExtractionMethod": "vlo:ExtractionMethodScheme", "vlo:LegalArea": "vlo:LegalAreaScheme",
                 "vlo:NewsCategory": "vlo:NewsCategoryScheme", "vlo:LegalTerm": "vlo:LegalTermScheme", "vlo:Module": "vlo:ModuleScheme"}
    for c, sch in scheme_of.items():
        if c in nodes and sch in nodes:
            links.append({"source": c, "target": sch, "type": "inScheme", "label_en": "concepts in scheme", "label_vi": "khái niệm thuộc hệ"})
    if "vlo:LegalArea" in nodes and "vlo:TermAreaScheme" in nodes:
        links.append({"source": "vlo:LegalArea", "target": "vlo:TermAreaScheme", "type": "inScheme", "label_en": "concepts in scheme", "label_vi": "khái niệm thuộc hệ"})
    n_obj = n_dat = 0
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        if not str(p).startswith(VLO):
            continue
        n_obj += 1
        dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        sup = sorted(cur(o) for o in g.objects(p, RDFS.subPropertyOf))
        item = {"id": cur(p), "label_en": lab(p, "en"), "label_vi": lab(p, "vi"), "definition_en": defin(p, "en"), "aligned_to": sup,
                "module": module(p), "inverse_of": cur(g.value(p, OWL.inverseOf)) if g.value(p, OWL.inverseOf) is not None else None}
        if dom is not None and rng is not None and cur(dom) in nodes and cur(rng) in nodes:
            links.append({"source": cur(dom), "target": cur(rng), "type": "property", **item})
        elif dom is not None and cur(dom) in nodes:
            nodes[cur(dom)]["attributes"].append({**item, "range": cur(rng) if rng is not None else None, "kind": "object"})
    for p in g.subjects(RDF.type, OWL.DatatypeProperty):
        if not str(p).startswith(VLO):
            continue
        n_dat += 1
        dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        item = {"id": cur(p), "label_en": lab(p, "en"), "label_vi": lab(p, "vi"), "definition_en": defin(p, "en"), "range": cur(rng) if rng is not None else None,
                "aligned_to": sorted(cur(o) for o in g.objects(p, RDFS.subPropertyOf)), "module": module(p), "kind": "datatype"}
        if dom is not None and cur(dom) in nodes:
            nodes[cur(dom)]["attributes"].append(item)
    modules = [{"id": str(g.value(m, SKOS.notation)), "label_en": lab(m, "en"), "label_vi": lab(m, "vi"), "definition_en": defin(m, "en")}
               for m in sorted(g.subjects(RDF.type, URIRef(VLO + "Module")), key=str)]
    out = {"name": "VLOnto ontology graph", "version": C.VERSION, "ontology_iri": "https://tmquan.github.io/VLOnto/ontology",
           "modules": modules + [{"id": "external", "label_en": "aligned external terms", "label_vi": "khái niệm ngoài được liên kết"}],
           "nodes": list(nodes.values()), "links": links,
           "counts": {"classes_vlo": sum(1 for n in nodes.values() if n["kind"] == "class"), "external": sum(1 for n in nodes.values() if n["kind"] == "external"),
                      "schemes": sum(1 for n in nodes.values() if n["kind"] == "scheme"), "object_properties": n_obj, "datatype_properties": n_dat,
                      "links": len(links)},
           "notes": "instances = number of knowledge-graph nodes of the class (including subclasses for LegalDocument, Provision, CourtDecision, JudicialDocument); examples are up to 5 instances."}
    return out


def class_counts():
    docs = T("documents", ["doc_class"])
    c = {f"vlo:{k}": v for k, v in Counter(docs["doc_class"].to_list()).items()}
    c["vlo:LegalDocument"] = c["vlo:NormativeLegalDocument"] = docs.height
    s = Counter(T("structure", ["kind"])["kind"].to_list())
    p = Counter(T("provisions_ref", ["kind"])["kind"].to_list())
    n_art = T("articles", ["article_id"]).height
    c.update({"vlo:Article": n_art, "vlo:Chapter": s.get("Chapter", 0), "vlo:Section": s.get("Section", 0), "vlo:Part": s.get("Part", 0),
              "vlo:Appendix": s.get("Appendix", 0), "vlo:Clause": p.get("Clause", 0), "vlo:Point": p.get("Point", 0)})
    c["vlo:Provision"] = n_art + sum(s.values()) + sum(p.values())
    dk = Counter(T("decisions", ["decision_kind"])["decision_kind"].to_list())
    c.update({"vlo:Judgment": dk.get("Judgment", 0), "vlo:CourtRuling": dk.get("CourtRuling", 0), "vlo:CourtDecision": sum(dk.values())})
    np_ = T("precedents", ["precedent_id"]).height
    c.update({"vlo:Precedent": np_, "vlo:JudicialDocument": sum(dk.values()) + np_})
    nq = T("qas", ["qa_id"]).height
    iss, crt = T("issuers", ["issuer_id"]).height, T("courts", ["court_id"]).height
    c.update({"vlo:LegalQuestion": nq, "vlo:LegalAnswer": nq, "vlo:LegalTerm": T("terms", ["term_id"]).height, "vlo:LegalNewsArticle": T("news", ["news_id"]).height,
              "vlo:IssuingBody": iss, "vlo:Court": crt, "vlo:PublicAuthority": iss + crt, "vlo:LegalArea": T("areas", ["area_id"]).height,
              "vlo:LegalChange": T("changes", ["change_id"]).height, "vlo:SourceDataset": 6, "vlo:EdgeSet": 10, "vlo:BuildActivity": 1,
              "vlo:NewsCategory": T("news_categories", ["category"]).height, "vlo:DocumentType": 10, "vlo:ValidityStatus": 8, "vlo:ChangeKind": 5,
              "vlo:LegalForceRank": 6, "vlo:CourtLevel": 5, "vlo:InstanceLevel": 4, "vlo:CaseCategory": 8, "vlo:Module": 11})
    c["vlo:LegalAreaScheme"] = int(T("areas", ["schemes"])["schemes"].list.contains("LegalAreaScheme").sum())
    c["vlo:TermAreaScheme"] = int(T("areas", ["schemes"])["schemes"].list.contains("TermAreaScheme").sum())
    c["vlo:LegalTermScheme"] = c["vlo:LegalTerm"]
    c["vlo:NewsCategoryScheme"] = c["vlo:NewsCategory"]
    return c


def class_examples():
    ex = {}
    docs = T("documents", ["iri", "doc_class", "title_vi", "doc_number", "legal_force_rank", "year"])
    for cls in docs["doc_class"].unique().to_list():
        sub = docs.filter(pl.col("doc_class") == cls).sort("year", descending=True, nulls_last=True).head(5)
        ex[f"vlo:{cls}"] = [{"iri": r["iri"], "label": C.cut(f"{r['title_vi']} ({r['doc_number']})" if r["doc_number"] else r["title_vi"], 90)} for r in sub.iter_rows(named=True)]
    key = docs.filter(pl.col("doc_number").is_in(["45/2019/QH14", "91/2015/QH13", "31/2024/QH15", "100/2015/QH13", "59/2020/QH14"]))
    ex["vlo:LegalDocument"] = ex["vlo:NormativeLegalDocument"] = [{"iri": r["iri"], "label": f"{r['title_vi']} ({r['doc_number']})"} for r in key.iter_rows(named=True)]
    arts = T("articles", ["iri", "article_id", "article_no", "heading"]).filter(pl.col("article_id").is_in(
        ["333670::dieu-35", "296215::dieu-357", "523642::dieu-252", "333670::dieu-220", "296215::dieu-468"]))
    ex["vlo:Article"] = [{"iri": r["iri"], "label": f"Điều {r['article_no']}. {C.cut(r['heading'], 70)}"} for r in arts.iter_rows(named=True)]
    for t, cls, labcol in (("changes", "vlo:LegalChange", "evidence"), ("issuers", "vlo:IssuingBody", "label_vi"), ("areas", "vlo:LegalArea", "label_vi"),
                           ("courts", "vlo:Court", "label"), ("precedents", "vlo:Precedent", "precedent_number"), ("terms", "vlo:LegalTerm", "label_vi"),
                           ("news_categories", "vlo:NewsCategory", "label_vi")):
        df = T(t).head(5)
        ex[cls] = [{"iri": r["iri"], "label": C.cut(str(r[labcol]), 90)} for r in df.iter_rows(named=True)]
    s = T("structure", ["iri", "kind", "heading"])
    for k in ("Chapter", "Section", "Part", "Appendix"):
        ex[f"vlo:{k}"] = [{"iri": r["iri"], "label": C.cut(r["heading"], 90)} for r in s.filter(pl.col("kind") == k).head(5).iter_rows(named=True)]
    p = T("provisions_ref", ["iri", "kind", "prov_id"]).sort("prov_id").head(2000)
    for k in ("Clause", "Point"):
        ex[f"vlo:{k}"] = [{"iri": r["iri"], "label": r["prov_id"]} for r in p.filter(pl.col("kind") == k).head(5).iter_rows(named=True)]
    d = T("decisions", ["iri", "decision_kind", "decision_number", "source"]).filter(pl.col("source") == "anle")
    for k in ("Judgment", "CourtRuling"):
        ex[f"vlo:{k}"] = [{"iri": r["iri"], "label": r["decision_number"]} for r in d.filter(pl.col("decision_kind") == k).head(5).iter_rows(named=True)]
    ex["vlo:CourtDecision"] = ex.get("vlo:Judgment", [])
    q = T("qas", ["iri", "answer_iri", "qa_id", "url"]).head(5)
    ex["vlo:LegalQuestion"] = [{"iri": r["iri"], "label": r["url"]} for r in q.iter_rows(named=True)]
    ex["vlo:LegalAnswer"] = [{"iri": r["answer_iri"], "label": f"answer {r['qa_id']}"} for r in q.iter_rows(named=True)]
    n = T("news", ["iri", "url"]).head(5)
    ex["vlo:LegalNewsArticle"] = [{"iri": r["iri"], "label": r["url"]} for r in n.iter_rows(named=True)]
    ex["vlo:SourceDataset"] = [{"iri": C.iri_source(k), "label": "tmquan/" + k} for k in list(C.SOURCES)[:5]]
    return ex


SPARQL_EXAMPLES = [
    ("What replaced the 2012 Labour Code?", "Văn bản nào thay thế Bộ luật Lao động 2012?", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?new ?number ?date ?evidence WHERE {
  ?old vlo:documentNumber "10/2012/QH13" .
  ?change vlo:affectedDocument ?old ; vlo:changeKind vlo:change-replaced ; vlo:actingDocument ?new ; vlo:evidenceText ?evidence .
  OPTIONAL { ?change vlo:changeEffectiveDate ?date }
  ?new vlo:documentNumber ?number .
}"""),
    ("Laws in force by area", "Số luật còn hiệu lực theo lĩnh vực", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?area (COUNT(?d) AS ?laws) WHERE {
  ?d a vlo:Law ; vlo:isInForce true ; vlo:legalArea ?a .
  ?a skos:prefLabel ?area FILTER(lang(?area) = "en")
} GROUP BY ?area ORDER BY DESC(?laws)"""),
    ("Codes and their validity", "Các bộ luật và tình trạng hiệu lực", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?title ?number ?status WHERE {
  ?d a vlo:Code ; vlo:title ?title ; vlo:validityStatus ?v .
  OPTIONAL { ?d vlo:documentNumber ?number }
  ?v skos:prefLabel ?status FILTER(lang(?status) = "en")
} ORDER BY ?title"""),
    ("Most amended laws", "Các luật được sửa đổi nhiều nhất", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?title ?number (COUNT(?by) AS ?amendments) WHERE {
  ?by vlo:amends ?d . ?d vlo:title ?title . OPTIONAL { ?d vlo:documentNumber ?number }
} GROUP BY ?title ?number ORDER BY DESC(?amendments) LIMIT 20"""),
    ("Legal basis of the 2024 Land Law", "Căn cứ pháp lý của Luật Đất đai 2024", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?basis ?title WHERE {
  ?d vlo:documentNumber "31/2024/QH15" ; vlo:legalBasis ?basis . ?basis vlo:title ?title .
}"""),
    ("Laws that cite the Civil Code 2015", "Các văn bản trích dẫn Bộ luật Dân sự 2015", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?citing ?title WHERE {
  ?code vlo:documentNumber "91/2015/QH13" .
  ?citing vlo:cites ?code ; vlo:title ?title .
} LIMIT 50"""),
    ("Change events by kind", "Số sự kiện thay đổi theo loại", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?kind (COUNT(?c) AS ?n) WHERE { ?c a vlo:LegalChange ; vlo:changeKind ?k . ?k skos:prefLabel ?kind FILTER(lang(?kind) = "en") }
GROUP BY ?kind ORDER BY DESC(?n)"""),
    ("Documents issued by the Standing Committee of the National Assembly", "Văn bản do Ủy ban Thường vụ Quốc hội ban hành", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?type (COUNT(?d) AS ?n) WHERE {
  ?d vlo:issuedBy ?b ; vlo:documentType ?t . ?b vlo:issuerCode "UBTVQH" . ?t <http://www.w3.org/2004/02/skos/core#notation> ?type
} GROUP BY ?type"""),
    ("Superclasses of a Law (ontology)", "Các lớp cha của Luật (bản thể)", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?super WHERE { vlo:Law rdfs:subClassOf+ ?super }"""),
    ("Source datasets and licences", "Bộ dữ liệu nguồn và giấy phép", """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?name ?revision ?licence WHERE { ?s a vlo:SourceDataset ; rdfs:label ?name ; vlo:datasetRevision ?revision ; vlo:licenceLabel ?licence }"""),
]


def sparql_examples():
    import pyoxigraph as ox
    st = ox.Store()
    with open(os.path.join(C.RDF_DIR, "vlonto-core.ttl"), "rb") as f:
        st.load(f, ox.RdfFormat.TURTLE)
    out = []
    for en, vi, q in SPARQL_EXAMPLES:
        t0 = time.time()
        try:
            sol = st.query(q)
            vars_ = [v.value for v in sol.variables]
            res = list(sol)
            first = [{v: (r[v].value if r[v] is not None else None) for v in vars_} for r in res[:3]]
            out.append({"title_en": en, "title_vi": vi, "query": q, "variables": vars_, "rows_on_core": len(res), "first_rows": first,
                        "ms": round(1000 * (time.time() - t0), 1)})
        except Exception as e:
            out.append({"title_en": en, "title_vi": vi, "query": q, "error": repr(e)})
    return {"dataset": "vlonto-core.ttl", "triples": len(st), "queries": out}


def build_site():
    t0 = time.time()
    rd = lambda n: json.load(open(os.path.join(C.REPORTS, n))) if os.path.exists(os.path.join(C.REPORTS, n)) else {}
    build, export, core, validation = rd("build_report.json"), rd("export_report.json"), rd("core_report.json"), rd("validation.json")
    stats, dash = stats_and_dashboard(build, export, core, validation)
    og = ontology_graph()
    stats["ontology"] = {"classes": og["counts"]["classes_vlo"], "object_properties": og["counts"]["object_properties"],
                         "datatype_properties": og["counts"]["datatype_properties"], "concept_schemes": og["counts"]["schemes"],
                         "aligned_external_terms": og["counts"]["external"]}
    dump(stats, "stats")
    dump(dash, "dashboard")
    dump(og, "ontology_graph")
    net = layout_main([])
    ex = sparql_examples()
    dump(ex, "sparql_examples")
    jsdir = os.path.join(C.SITE, "js")
    js_string_twin(os.path.join(C.RDF_DIR, "vlonto-core.ttl"), "vlonto_core_ttl", jsdir)
    js_string_twin(os.path.join(C.REPO, "ontology", "vlonto.ttl"), "vlonto_ontology_ttl", jsdir)
    man = []
    for root in (C.SITE, jsdir):
        for fn in sorted(os.listdir(root)):
            p = os.path.join(root, fn)
            if os.path.isfile(p) and fn != "manifest.json":
                b = open(p, "rb").read()
                man.append({"file": os.path.relpath(p, C.SITE), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "within_20MB": len(b) <= MAX_BYTES})
    with open(os.path.join(C.SITE, "manifest.json"), "w") as f:
        json.dump({"version": C.VERSION, "files": man, "note": "js/<name>.js twins assign window.VLONTO[name] for file:// use; "
                   "js/manifest.js is written after this list"}, f, indent=1)
    write_js_twin(os.path.join(C.SITE, "manifest.json"), "manifest")
    print(json.dumps({"files": [(m["file"], m["bytes"]) for m in man], "all_within_20MB": all(m["within_20MB"] for m in man),
                      "sparql": [(q["title_en"], q.get("rows_on_core"), q.get("error")) for q in ex["queries"]],
                      "wall_s": round(time.time() - t0, 1)}, ensure_ascii=False, indent=1), flush=True)

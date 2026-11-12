"""Step 4b: validation of the VLOnto knowledge graph.

1. Referential integrity of every edge table and every node reference (parquet level).
2. Count reconciliation with the data report of the vn-legal data track.
3. RDF: load vlonto-kg.nt.gz into an on-disk Oxigraph store (strict parse), SPARQL counts per class compared
   with the parquet node counts, and a streaming check that every vlid: IRI used as an object has an rdf:type.
4. SHACL on stratified samples of every class (pyshacl, each class in a subprocess with a time limit).
5. OWL-RL closure on a real sample (logical axioms of the ontology + sampled instances): no inconsistency.
6. Spot checks: 10 random edges per edge type with the evidence that produced them (no person names,
   no Q&A/news text), written to spot_checks.md for manual judgement.
7. Release scope: without court data (release v1) no court table exists and the dump has no court, decision or
   precedent node and no statement about the court source datasets.
Results: $V/build/reports/validation.json, spot_checks.md, spot_checks.json.
"""
import glob
import gzip
import json
import multiprocessing as mp
import os
import random
import re
import time
from collections import Counter

import polars as pl

from . import config as C

EXPECTED = {
    "documents": 40816,
    "relations_by_kind": {"replaced": 6321, "amended": 4678, "partially_repealed": 1854, "repealed": 1674, "partially_expired": 508},
    "relations_total": 15035,
    "validity": {"unknown": 28660, "superseded": 5167, "presumed_in_force_amended": 2722, "expired": 2125, "in_force": 1511,
                 "in_force_amended": 545, "not_applicable": 47, "not_yet_effective": 39},
    "main_body_articles": 425892, "documents_with_main_articles": 32902,
    "gold_qas": 22523, "hdpl_qas": 109543, "tnpl_rows": 17091, "tnpl_not_found": 390, "htpl": 681, "anle": 1844, "cbba_card_rows": 1542247,
}


def T(name):
    if name in C.COURT_TABLES and not C.INCLUDE_COURTS:
        raise RuntimeError(f"{name}: court tables are not part of this build (VLONTO_INCLUDE_COURTS=0)")
    return pl.read_parquet(os.path.join(C.KG, name + ".parquet"))


def n_rows(name, kind=None):
    """Rows of a node table (0 for a court table in a build without court data)."""
    if name in C.COURT_TABLES and not C.INCLUDE_COURTS:
        return 0
    df = T(name)
    return df.height if not kind else int((df["kind"] == kind).sum())


def orphans(values, universe):
    u = set(universe)
    bad = [v for v in values if v is not None and v not in u]
    return len(bad), bad[:5]


def referential_integrity():
    t0 = time.time()
    docs = set(T("documents")["doc_id"].to_list())
    arts = T("articles")
    art_ids = set(arts["article_id"].to_list())
    st = T("structure")
    st_ids = set(st["struct_id"].to_list())
    pref = T("provisions_ref")
    courts_on = C.INCLUDE_COURTS
    dec = set(T("decisions")["decision_id"].to_list()) if courts_on else set()
    prec = set(T("precedents")["precedent_id"].to_list()) if courts_on else set()
    qas = set(T("qas")["qa_id"].to_list())
    terms = set(T("terms")["term_id"].to_list())
    news = set(T("news")["news_id"].to_list())
    issuers = set(T("issuers")["issuer_id"].to_list())
    areas = set(T("areas")["area_id"].to_list())
    courts = set(T("courts")["court_id"].to_list()) if courts_on else set()
    changes = set(T("changes")["change_id"].to_list())
    checks = {}

    def chk(name, values, universe):
        n, ex = orphans(values, universe)
        checks[name] = {"checked": sum(1 for v in values if v is not None), "orphans": n, "examples": ex}

    d = T("documents")
    chk("documents.issuer_ids -> issuers", [x for l in d["issuer_ids"].to_list() for x in (l or [])], issuers)
    chk("documents.area_id -> areas", d["area_id"].to_list(), areas)
    chk("articles.doc_id -> documents", arts["doc_id"].to_list(), docs)
    chk("articles.parent_id -> structure|documents", arts["parent_id"].to_list(), st_ids | docs)
    chk("structure.doc_id -> documents", st["doc_id"].to_list(), docs)
    chk("structure.parent_id -> structure|documents", st["parent_id"].to_list(), st_ids | docs)
    chk("provisions_ref.article_id -> articles", pref["article_id"].to_list(), art_ids)
    chk("provisions_ref.parent_id -> articles|provisions_ref", pref["parent_id"].to_list(), art_ids | set(pref["prov_id"].to_list()))
    ch = T("changes")
    chk("changes.acting_doc_id -> documents", ch["acting_doc_id"].to_list(), docs)
    chk("changes.affected_doc_id -> documents", ch["affected_doc_id"].to_list(), docs)
    e = T("edges_change")
    chk("edges_change.src -> documents", e["src_doc_id"].to_list(), docs)
    chk("edges_change.dst -> documents", e["dst_doc_id"].to_list(), docs)
    chk("edges_change.change_id -> changes", e["change_id"].to_list(), changes)
    e = T("edges_legal_basis")
    chk("edges_legal_basis.src -> documents", e["src_doc_id"].to_list(), docs)
    chk("edges_legal_basis.dst -> documents", e["dst_doc_id"].to_list(), docs)
    e = T("edges_citation")
    chk("edges_citation.src_doc -> documents", e["src_doc_id"].to_list(), docs)
    chk("edges_citation.src_article -> articles", e["src_article_id"].to_list(), art_ids)
    chk("edges_citation.dst_doc -> documents", e["dst_doc_id"].to_list(), docs)
    chk("edges_citation.dst_article -> articles", e["dst_article_id"].to_list(), art_ids)
    bad = e.filter(pl.col("dst_article_id").is_not_null() & (pl.col("dst_article_id").str.split("::").list.first() != pl.col("dst_doc_id"))).height
    checks["edges_citation.dst_article in dst_doc"] = {"checked": int(e["dst_article_id"].is_not_null().sum()), "orphans": bad, "examples": []}
    if courts_on:
        e = T("decisions")
        chk("decisions.court_id -> courts", e["court_id"].to_list(), courts)
        e = T("edges_decision_provision")
        chk("edges_decision_provision.decision -> decisions", e["decision_id"].to_list(), dec)
        chk("edges_decision_provision.dst_doc -> documents", e["dst_doc_id"].to_list(), docs)
        chk("edges_decision_provision.dst_article -> articles", e["dst_article_id"].to_list(), art_ids)
        e = T("edges_decision_case")
        chk("edges_decision_case.src -> decisions", e["src_id"].to_list(), dec)
        chk("edges_decision_case.dst(decision) -> decisions", e.filter(pl.col("dst_kind") == "decision")["dst_id"].to_list(), dec)
        chk("edges_decision_case.dst(precedent) -> precedents", e.filter(pl.col("dst_kind") == "precedent")["dst_id"].to_list(), prec)
        e = T("edges_precedent_source")
        chk("edges_precedent_source.src -> precedents", e["src_id"].to_list(), prec)
        chk("edges_precedent_source.dst -> decisions", e["dst_id"].to_list(), dec)
    q = T("qas")
    chk("qas.area_id -> areas", q["area_id"].to_list(), areas)
    e = T("edges_qa_article")
    chk("edges_qa_article.qa -> qas", e["qa_id"].to_list(), qas)
    chk("edges_qa_article.dst_article -> articles", e["dst_article_id"].to_list(), art_ids)
    chk("edges_qa_article.dst_doc -> documents", e["dst_doc_id"].to_list(), docs)
    e = T("edges_qa_document")
    chk("edges_qa_document.qa -> qas", e["qa_id"].to_list(), qas)
    chk("edges_qa_document.dst -> documents", e["dst_doc_id"].to_list(), docs)
    tt = T("terms")
    chk("terms.area_id -> areas", tt["area_id"].to_list(), areas)
    e = T("edges_term_related")
    chk("edges_term_related.src -> terms", e["src_term_id"].to_list(), terms)
    chk("edges_term_related.dst -> terms", e["dst_term_id"].to_list(), terms)
    e = T("edges_news_document")
    chk("edges_news_document.news -> news", e["news_id"].to_list(), news)
    chk("edges_news_document.dst -> documents", e["dst_doc_id"].to_list(), docs)
    # clause/point nodes referenced by edges exist
    pids = set(pref["prov_id"].to_list())
    need = []
    for name in ("edges_citation", "edges_decision_provision", "edges_qa_article"):
        if name in C.COURT_TABLES and not courts_on:
            continue
        df = T(name).filter(pl.col("dst_article_id").is_not_null() & (pl.col("clause").is_not_null() | pl.col("point").is_not_null()))
        for a, k, p in df.select("dst_article_id", "clause", "point").iter_rows():
            need.append(f"{a}::khoan-{k}" + (f"::diem-{p}" if p else "") if k else f"{a}::diem-{p}")
    chk("edge clause/point targets -> provisions_ref", need, pids)
    total = sum(v["orphans"] for v in checks.values())
    return {"checks": checks, "total_orphans": total, "pass": total == 0, "wall_s": round(time.time() - t0, 1)}


def reconcile(build):
    out = []

    def row(item, expected, got, note=""):
        out.append({"item": item, "expected": expected, "kg": got, "diff": (got - expected) if isinstance(expected, int) and isinstance(got, int) else None,
                    "match": expected == got, "note": note})

    d = T("documents")
    row("documents", EXPECTED["documents"], d.height)
    ch = T("changes")
    kinds = Counter(ch["kind"].to_list())
    row("change relations (total)", EXPECTED["relations_total"], ch.height)
    for k, v in EXPECTED["relations_by_kind"].items():
        row(f"change relations: {k}", v, kinds.get(k, 0))
    val = Counter(d["validity"].to_list())
    for k, v in EXPECTED["validity"].items():
        row(f"validity: {k}", v, val.get(k, 0))
    a = T("articles")
    row("main-body articles", EXPECTED["main_body_articles"], int((a["segment"] == "main").sum()))
    row("documents with main-body articles", EXPECTED["documents_with_main_articles"], int(a.filter(pl.col("segment") == "main")["doc_id"].n_unique()))
    qa_art = T("edges_qa_article")
    row("Q&As with gold article labels", EXPECTED["gold_qas"], int(qa_art["qa_id"].n_unique()),
        "Q&As that keep at least one article edge after article-number normalisation")
    row("hdpl Q&As", EXPECTED["hdpl_qas"], T("qas").height)
    row("tnpl terms (rows minus not_found placeholders)", EXPECTED["tnpl_rows"] - EXPECTED["tnpl_not_found"], T("terms").height)
    row("htpl news", EXPECTED["htpl"], T("news").height)
    if C.INCLUDE_COURTS:
        dec = T("decisions")
        src = Counter(dec["source"].to_list())
        row("anle decisions", EXPECTED["anle"], src.get("anle", 0))
        row("cbba decisions (card: released rows)", EXPECTED["cbba_card_rows"], src.get("cbba", 0))
    return out


# ------------------------------------------------------------------ RDF
def load_oxigraph():
    import pyoxigraph as ox
    t0 = time.time()
    path = os.path.join(C.BUILD, "oxigraph")
    if os.path.exists(path):
        import shutil
        shutil.rmtree(path)
    st = ox.Store(path)
    nt = os.path.join(C.RDF_DIR, "vlonto-kg.nt.gz")
    with gzip.open(nt, "rb") as f:
        st.bulk_load(f, ox.RdfFormat.N_TRIPLES)
    st.optimize()
    n = len(st)
    return st, {"store": path, "triples_loaded": n, "load_s": round(time.time() - t0, 1)}


CLASS_TABLE = {  # class local name -> (table, filter) for count comparison
    "LegalDocument": ("documents", None), "Article": ("articles", None), "Chapter": ("structure", "Chapter"), "Section": ("structure", "Section"),
    "Part": ("structure", "Part"), "Appendix": ("structure", "Appendix"), "Clause": ("provisions_ref", "Clause"), "Point": ("provisions_ref", "Point"),
    "IssuingBody": ("issuers", None), "LegalArea": ("areas", None), "LegalChange": ("changes", None), "Court": ("courts", None),
    "CourtDecision": ("decisions", None), "Precedent": ("precedents", None), "LegalQuestion": ("qas", None), "LegalAnswer": ("qas", None),
    "LegalTerm": ("terms", None), "LegalNewsArticle": ("news", None), "NewsCategory": ("news_categories", None), "SourceDataset": ("sources", None),
}
SUBS = {"LegalDocument": ["Constitution", "Code", "Law", "Ordinance", "Resolution", "JointResolution", "Decree", "Decision", "Circular", "JointCircular"],
        "CourtDecision": ["Judgment", "CourtRuling", "CourtDecision"]}


def rdf_counts(st):
    out = {}
    q = "SELECT ?c (COUNT(?s) AS ?n) WHERE { ?s a ?c FILTER(STRSTARTS(STR(?c), '%s')) } GROUP BY ?c" % C.VLO
    by = {str(r["c"].value)[len(C.VLO):]: int(r["n"].value) for r in st.query(q)}
    for cls, (table, kind) in CLASS_TABLE.items():
        exp = n_rows(table, kind)
        got = sum(by.get(c, 0) for c in SUBS.get(cls, [cls]))
        out[cls] = {"parquet": exp, "rdf": got, "match": exp == got}
        if table in C.COURT_TABLES and not C.INCLUDE_COURTS:
            out[cls]["note"] = "court data not in this release (expected 0)"
    out["_rdf_type_counts"] = by
    preds = "SELECT ?p (COUNT(*) AS ?n) WHERE { ?s ?p ?o FILTER(STRSTARTS(STR(?p), '%s')) } GROUP BY ?p" % C.VLO
    out["_vlo_predicate_counts"] = {str(r["p"].value)[len(C.VLO):]: int(r["n"].value) for r in st.query(preds)}
    return out


def dangling_iris():
    """Every vlid: IRI used as an object must have an rdf:type somewhere in the dump."""
    t0 = time.time()
    typed, objs = set(), set()
    pat = re.compile(r'^<([^>]+)> <([^>]+)> <(' + re.escape(C.ID) + r'[^>]*)> \.$')
    rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    court_marks = tuple(f"<{C.ID}{x}/" for x in ("court", "decision", "precedent")) + tuple(f"<{C.iri_source(d)}>" for d in C.COURT_DATASETS) \
        + tuple(f"<{C.iri_edgeset(t)}>" for t in C.COURT_TABLES)
    court_lines, court_examples = 0, []
    n = 0
    with gzip.open(os.path.join(C.RDF_DIR, "vlonto-kg.nt.gz"), "rt", encoding="utf-8") as f:
        for line in f:
            n += 1
            if not C.INCLUDE_COURTS and any(m in line for m in court_marks):
                court_lines += 1
                if len(court_examples) < 5:
                    court_examples.append(line.strip()[:200])
            if line.startswith("<" + C.ID):
                s_end = line.find(">")
                s = line[1:s_end]
                if line.startswith(" <" + rdf_type + ">", s_end + 1):
                    typed.add(s)
            m = pat.match(line.rstrip("\n"))
            if m and m.group(2) != rdf_type:
                objs.add(m.group(3))
    missing = objs - typed
    return {"lines": n, "typed_vlid_subjects": len(typed), "vlid_objects": len(objs), "objects_without_type": len(missing),
            "examples": sorted(missing)[:10], "pass": not missing,
            "court_data_lines": court_lines if not C.INCLUDE_COURTS else None, "court_data_examples": court_examples,
            "wall_s": round(time.time() - t0, 1)}


def release_scope(rdf_counts_, dangling):
    """Release v1: no court table in build/kg, no court node or court-source statement in the dump."""
    if C.INCLUDE_COURTS:
        return {"courts_included": True, "pass": None, "note": "court data included; scope check not applicable"}
    present = [t for t in C.COURT_TABLES if os.path.exists(os.path.join(C.KG, t + ".parquet"))]
    by = rdf_counts_.get("_rdf_type_counts", {})
    typed = {c: by.get(c, 0) for c in ("Court", "CourtDecision", "Judgment", "CourtRuling", "Precedent", "JudicialDocument")}
    srcs = sorted(os.path.basename(p)[:-8] for p in glob.glob(os.path.join(C.KG, "*.parquet")))
    sources = T("sources")["dataset"].to_list()
    out = {"courts_included": False, "court_tables_present": present, "court_typed_nodes_in_rdf": typed,
           "court_data_lines_in_dump": dangling.get("court_data_lines"), "court_data_examples": dangling.get("court_data_examples"),
           "source_datasets": sources, "tables": srcs}
    out["pass"] = (not present and not any(typed.values()) and dangling.get("court_data_lines") == 0
                   and sorted(sources) == sorted(C.SOURCES))
    return out


def sample_graph(st, iris):
    """Triples of the sampled subjects plus the rdf:type of every object they point to."""
    import pyoxigraph as ox
    from rdflib import Graph
    g = Graph()
    for i in range(0, len(iris), 200):
        vals = " ".join(f"<{x}>" for x in iris[i:i + 200])
        q = ("CONSTRUCT { ?s ?p ?o . ?o a ?t } WHERE { VALUES ?s { %s } ?s ?p ?o . OPTIONAL { ?o a ?t } }" % vals)
        data = st.query(q).serialize(format=ox.RdfFormat.N_TRIPLES)
        g.parse(data=data.decode("utf-8") if isinstance(data, bytes) else data, format="nt")
    return g


def _shacl_worker(data_nt, shapes_path, onto_path, focus, q):
    """Validate the sample graph; only results whose focus node is a sampled node count.

    The sample graph also holds the rdf:type of every object the sampled nodes point to (needed for sh:class);
    those context nodes have no other triples, so results reported on them are dropped (counted separately).
    """
    from collections import Counter
    from rdflib import Graph, URIRef
    from pyshacl import validate
    from .ontology_tools import shacl_support
    try:
        d = Graph().parse(data=data_nt, format="nt")
        onto = Graph().parse(onto_path)
        d += shacl_support(onto)
        shapes = Graph().parse(shapes_path)
        t0 = time.time()
        conforms, rg, text = validate(d, shacl_graph=shapes, inference="none", abort_on_first=False, allow_warnings=True)
        SH = "http://www.w3.org/ns/shacl#"
        focus = set(focus)
        res, dropped = [], 0
        for r in rg.subjects(URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), URIRef(SH + "ValidationResult")):
            f = rg.value(r, URIRef(SH + "focusNode"))
            if str(f) not in focus:
                dropped += 1
                continue
            p = rg.value(r, URIRef(SH + "resultPath"))
            m = rg.value(r, URIRef(SH + "resultMessage"))
            sev = rg.value(r, URIRef(SH + "resultSeverity"))
            comp = rg.value(r, URIRef(SH + "sourceConstraintComponent"))
            v = rg.value(r, URIRef(SH + "value"))
            res.append({"focus": str(f), "path": str(p) if p else None, "component": str(comp).split("#")[-1] if comp else None,
                        "value": str(v)[:120] if v is not None else None, "message": str(m)[:200] if m else None,
                        "severity": str(sev).split("#")[-1]})
        viol = [x for x in res if x["severity"] == "Violation"]
        kinds = Counter(f"{(x['path'] or '').split('#')[-1].split('/')[-1]}|{x['component']}" for x in viol)
        q.put({"results_on_sampled_nodes": len(res), "results_on_context_nodes_dropped": dropped,
               "n_violations": len(viol), "violation_kinds": dict(kinds.most_common(40)), "violations": viol[:40],
               "seconds": round(time.time() - t0, 1)})
    except Exception as e:
        import traceback
        q.put({"error": repr(e), "trace": traceback.format_exc()[-1500:]})


def shacl_samples(st, n_per_class=150, seed=7, timeout_s=600):
    rnd = random.Random(seed)
    groups = {}
    docs = T("documents")
    for cls in sorted(docs["doc_class"].unique().to_list()):      # sorted: polars unique() order varies between runs
        groups[f"documents:{cls}"] = docs.filter(pl.col("doc_class") == cls)["iri"].to_list()
    groups["articles"] = T("articles")["iri"].to_list()
    s = T("structure")
    for k in sorted(s["kind"].unique().to_list()):
        groups[f"structure:{k}"] = s.filter(pl.col("kind") == k)["iri"].to_list()
    p = T("provisions_ref")
    for k in sorted(p["kind"].unique().to_list()):
        groups[f"provisions_ref:{k}"] = p.filter(pl.col("kind") == k)["iri"].to_list()
    for t in ("issuers", "areas", "changes", "courts", "precedents", "terms", "news", "news_categories", "sources"):
        if t in C.COURT_TABLES and not C.INCLUDE_COURTS:
            continue
        groups[t] = T(t)["iri"].to_list()
    if C.INCLUDE_COURTS:
        dec = T("decisions")
        for k in sorted(dec["decision_kind"].unique().to_list()):
            for srcname in ("anle", "cbba"):
                ids = dec.filter((pl.col("decision_kind") == k) & (pl.col("source") == srcname))["iri"].to_list()
                if ids:
                    groups[f"decisions:{srcname}:{k}"] = ids
    q = T("qas")
    groups["qas"] = q["iri"].to_list()
    groups["answers"] = q["answer_iri"].to_list()
    groups["edgesets"] = [C.iri_edgeset(x) for x in ("edges_change", "edges_legal_basis", "edges_citation", "edges_decision_provision", "edges_decision_case",
                                                      "edges_precedent_source", "edges_qa_article", "edges_qa_document", "edges_term_related", "edges_news_document")
                          if C.INCLUDE_COURTS or x not in C.COURT_TABLES]
    groups["build"] = [C.iri_build()]
    sample = {}
    for g, ids in groups.items():
        sample[g] = rnd.sample(ids, min(n_per_class, len(ids)))
    all_iris = [x for v in sample.values() for x in v]
    t0 = time.time()
    g = sample_graph(st, all_iris)
    data_nt = g.serialize(format="nt")
    os.makedirs(C.REPORTS, exist_ok=True)
    with open(os.path.join(C.REPORTS, "shacl_sample.nt"), "w", encoding="utf-8") as f:
        f.write(data_nt)
    ctx = mp.get_context("spawn")
    qq = ctx.Queue()
    pr = ctx.Process(target=_shacl_worker, args=(data_nt, os.path.join(C.REPO, "ontology", "vlonto-shapes.ttl"),
                                                 os.path.join(C.REPO, "ontology", "vlonto.ttl"), all_iris, qq))
    pr.start()
    import queue as _queue
    try:
        res = qq.get(timeout=timeout_s)  # read before join: a queued result must be consumed for the child to exit
    except _queue.Empty:
        res = {"error": f"timeout after {timeout_s}s or worker exit {pr.exitcode}"}
    pr.join(10)
    if pr.is_alive():
        pr.terminate()
        pr.join()
    res["sample_groups"] = {k: len(v) for k, v in sample.items()}
    res["sample_nodes"] = len(all_iris)
    res["sample_triples"] = len(g)
    res["wall_s"] = round(time.time() - t0, 1)
    res["pass"] = ("error" not in res) and res.get("n_violations") == 0
    return res, g


def owlrl_sample(g):
    from .ontology_tools import logical_axioms, load, ERRNS
    from rdflib import Graph, Literal
    from rdflib.namespace import OWL, RDF
    import owlrl
    t0 = time.time()
    onto = logical_axioms(load(os.path.join(C.REPO, "ontology", "vlonto.ttl")))
    data = Graph()
    for t in g:
        if not isinstance(t[2], Literal):
            data.add(t)
    data = data + onto
    n0 = len(data)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(data)
    errs = [str(o) for s in data.subjects(RDF.type, ERRNS.ErrorMessage) for o in data.objects(s, ERRNS.error)]
    same = [(str(a), str(b)) for a, b in data.subject_objects(OWL.sameAs) if a != b]
    nothing = [str(s) for s in data.subjects(RDF.type, OWL.Nothing)]
    eli = sum(1 for _ in data.subjects(RDF.type, __import__("rdflib").URIRef("http://data.europa.eu/eli/ontology#LegalResource")))
    return {"input_triples": n0, "closure_triples": len(data), "inconsistencies": errs[:10], "n_inconsistencies": len(errs),
            "sameAs_between_distinct": same[:10], "n_sameAs": len(same), "owl_nothing": nothing[:10],
            "inferred_eli_LegalResource": eli, "pass": not errs and not same and not nothing, "wall_s": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ spot checks
def spot_checks(seed=11, k=10):
    rnd = random.Random(seed)
    docs = T("documents").select("doc_id", "doc_number", "title_vi", "doc_type_vi", "issue_date")
    dm = {r["doc_id"]: r for r in docs.iter_rows(named=True)}
    arts = T("articles").select("article_id", "heading")
    am = dict(arts.iter_rows())
    courts_on = C.INCLUDE_COURTS
    if courts_on:
        dec = T("decisions").select("decision_id", "decision_number", "issued_date", "court_id", "category", "instance_level")
        decm = {r["decision_id"]: r for r in dec.iter_rows(named=True)}
        courts = dict(T("courts").select("court_id", "label").iter_rows())

    def skip_draws(n):
        """Without court data the court samples are not drawn; their random draws are still consumed so that every
        other edge type gets the same sample as in a build with court data (0.1.0: 2 decision-provision methods,
        3 case-link methods, 1 decision-court sample before the issuer sample, 1 precedent-source sample after it)."""
        for _ in range(n):
            rnd.randint(0, 10 ** 6)

    def dl(d):
        r = dm.get(d) or {}
        return f"{r.get('doc_number') or '-'} | {C.cut(r.get('title_vi'), 90)} | issued {r.get('issue_date')}"

    out = {}

    def pick(df, n=k):
        return df.sample(min(n, df.height), seed=rnd.randint(0, 10 ** 6)) if df.height else df

    e = pick(T("changes"))
    out["changes"] = [{"acting": dl(r["acting_doc_id"]), "kind": r["kind"], "affected": dl(r["affected_doc_id"]), "evidence": r["evidence"]}
                      for r in e.iter_rows(named=True)]
    lb = T("edges_legal_basis")
    for m in ("parent-acts", "preamble-citation", "constitution-preamble"):
        if m == "constitution-preamble":
            # separate random stream, so that adding this method left the samples of all other edge types unchanged
            e = lb.filter(pl.col("method") == m)
            e = e.sample(min(k, e.height), seed=1101) if e.height else e
        else:
            e = pick(lb.filter(pl.col("method") == m))
        out[f"legal_basis:{m}"] = [{"citing": dl(r["src_doc_id"]), "raw": r["raw"], "basis": dl(r["dst_doc_id"]), "resolve": r["resolve_method"]}
                                   for r in e.iter_rows(named=True)]
    ci = T("edges_citation")
    for kind in ("external", "external_mention", "parent_law", "parent_law_mention"):
        e = pick(ci.filter(pl.col("kind") == kind))
        out[f"citation:{kind}"] = [{"citing": dl(r["src_doc_id"]), "where": r["source_location"], "raw": r["raw"], "cited": dl(r["dst_doc_id"]),
                                    "cited_article": f"{r['dst_article_id']} {C.cut(am.get(r['dst_article_id']), 80)}" if r["dst_article_id"] else None,
                                    "method": r["method"]} for r in e.iter_rows(named=True)]
    if not courts_on:
        skip_draws(2 + 3 + 1)
    dp = T("edges_decision_provision") if courts_on else None
    for m in (("docnum-key", "law-name-year") if courts_on else ()):
        e = pick(dp.filter(pl.col("method") == m))
        out[f"decision_provision:{m}"] = [{"decision": f"{(decm.get(r['decision_id']) or {}).get('decision_number')} ({(decm.get(r['decision_id']) or {}).get('issued_date')})",
                                            "ref": r["ref"], "cited": dl(r["dst_doc_id"]),
                                            "cited_article": f"{r['dst_article_id']} {C.cut(am.get(r['dst_article_id']), 80)}" if r["dst_article_id"] else None}
                                           for r in e.iter_rows(named=True)]
    dc = T("edges_decision_case") if courts_on else None
    for m in (dc["method"].unique().to_list() if courts_on else []):
        e = pick(dc.filter(pl.col("method") == m))
        rows = []
        for r in e.iter_rows(named=True):
            s = decm.get(r["src_id"]) or {}
            if r["dst_kind"] == "decision":
                t = decm.get(r["dst_id"]) or {}
                rows.append({"citing": f"{s.get('decision_number')} {s.get('issued_date')} {courts.get(s.get('court_id'), '-')}",
                             "cited_as": r["cited_id"], "role": r["role"],
                             "resolved": f"{t.get('decision_number')} {t.get('issued_date')} {courts.get(t.get('court_id'), '-')} {t.get('category')} {t.get('instance_level')}"})
            else:
                rows.append({"citing": f"{s.get('decision_number')} {s.get('issued_date')}", "cited_as": r["cited_id"], "resolved": f"precedent {r['dst_id']}"})
        out[f"decision_case:{m}"] = rows
    # decision -> court: compare the canonical court with the court field of the source record
    if courts_on:
        import glob as _glob
        dfull = T("decisions").select("decision_id", "source", "doc_name", "decision_number", "court_id", "court_method", "court_note")
        e = pick(dfull.filter(pl.col("court_id").is_not_null() & (pl.col("source") == "cbba")))
        names = set(e["doc_name"].to_list())
        raw = {}
        for f in sorted(_glob.glob(f"{C.snapshot('cbba-toaan-gov-vn')}/documents-*.parquet")):
            part = pl.read_parquet(f, columns=["doc_name", "court"]).filter(pl.col("doc_name").cast(pl.Utf8).is_in(pl.Series(list(map(str, names)))))
            raw.update({str(a): b for a, b in part.iter_rows()})
        out["decision_court"] = [{"decision": r["decision_number"], "source_court_field": C.cut(raw.get(str(r["doc_name"])), 110),
                                  "method": r["court_method"], "court": courts.get(r["court_id"])} for r in e.iter_rows(named=True)]
    # document -> issuing body
    iss = dict(T("issuers").select("issuer_id", "label_vi").iter_rows())
    dd = T("documents").select("doc_number", "doc_type_vi", "title_vi", "issuer_ids", "issuer_method").filter(pl.col("issuer_ids").list.len() > 0)
    e = pick(dd)
    out["document_issuer"] = [{"document": f"{r['doc_number']} | {C.cut(r['title_vi'], 80)}", "issuers": ", ".join(iss.get(x, x) for x in r["issuer_ids"]),
                               "method": r["issuer_method"]} for r in e.iter_rows(named=True)]
    if courts_on:
        e = pick(T("edges_precedent_source"))
        out["precedent_source"] = [{"precedent": r["src_id"], "decision": f"{(decm.get(r['dst_id']) or {}).get('decision_number')} {(decm.get(r['dst_id']) or {}).get('issued_date')}"}
                                   for r in e.iter_rows(named=True)]
    else:
        skip_draws(1)
    qa = T("edges_qa_article")
    e = pick(qa)
    out["qa_article"] = [{"qa": r["qa_id"], "ref": r["ref"], "resolved": dl(r["dst_doc_id"]), "article": f"{r['dst_article_id']} {C.cut(am.get(r['dst_article_id']), 80)}",
                          "method": r["method"]} for r in e.iter_rows(named=True)]
    e = pick(T("edges_qa_document"))
    out["qa_document"] = [{"qa": r["qa_id"], "number_cited": r["number_cited"], "law_type": r["law_type"], "resolved": dl(r["dst_doc_id"])}
                          for r in e.iter_rows(named=True)]
    tm = dict(T("terms").select("term_id", "label_vi").iter_rows())
    e = pick(T("edges_term_related"))
    out["term_related"] = [{"term": tm.get(r["src_term_id"]), "related": tm.get(r["dst_term_id"])} for r in e.iter_rows(named=True)]
    e = pick(T("edges_news_document"))
    out["news_document"] = [{"news": r["news_id"], "number_found": r["number_found"], "resolved": dl(r["dst_doc_id"])} for r in e.iter_rows(named=True)]
    with open(os.path.join(C.REPORTS, "spot_checks.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    md = ["# Spot checks (10 random edges per edge type, seed %d)" % seed, ""]
    if not courts_on:
        md += [f"Release {C.RELEASE} ({C.VERSION}) has no court data, so the court edge types (decision_provision, decision_case, "
               "decision_court, precedent_source) are not sampled; the random draws they would use are skipped so that the other "
               "edge types get the same samples as a build with court data.", ""]
    for kname, rows in out.items():
        md.append(f"## {kname}")
        md.append("")
        for i, r in enumerate(rows, 1):
            md.append(f"{i}. " + " ‖ ".join(f"**{a}**: {b}" for a, b in r.items()))
        md.append("")
    with open(os.path.join(C.REPORTS, "spot_checks.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return {k: len(v) for k, v in out.items()}


def validate_all():
    t0 = time.time()
    rep = {"release": C.release_info()}
    build = json.load(open(os.path.join(C.REPORTS, "build_report.json")))
    print("referential integrity ...", flush=True)
    rep["referential_integrity"] = referential_integrity()
    print("  orphans:", rep["referential_integrity"]["total_orphans"], flush=True)
    rep["reconciliation"] = reconcile(build)
    print("spot checks ...", flush=True)
    rep["spot_checks"] = spot_checks()
    print("oxigraph load ...", flush=True)
    st, info = load_oxigraph()
    rep["oxigraph"] = info
    print("  ", info, flush=True)
    rep["rdf_counts"] = rdf_counts(st)
    print("dangling IRIs ...", flush=True)
    rep["dangling_iris"] = dangling_iris()
    print("  ", {k: v for k, v in rep["dangling_iris"].items() if k != "examples"}, flush=True)
    rep["release_scope"] = release_scope(rep["rdf_counts"], rep["dangling_iris"])
    print("release scope:", {k: v for k, v in rep["release_scope"].items() if k != "tables"}, flush=True)
    print("SHACL samples ...", flush=True)
    rep["shacl"], g = shacl_samples(st)
    print("  ", {k: v for k, v in rep["shacl"].items() if k not in ("violations", "sample_groups")}, flush=True)
    print("OWL-RL sample ...", flush=True)
    try:
        rep["owlrl_sample"] = owlrl_sample(g)
    except Exception as e:
        rep["owlrl_sample"] = {"error": repr(e)}
    print("  ", rep["owlrl_sample"], flush=True)
    rep["wall_s"] = round(time.time() - t0, 1)
    with open(os.path.join(C.REPORTS, "validation.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=str)
    print(f"validation done in {rep['wall_s']} s", flush=True)
    return rep

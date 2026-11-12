"""Ontology checks and documentation for VLOnto.

check_ontology(): parse vlonto.ttl and vlonto-shapes.ttl, check that every VLOnto class and property has
English and Vietnamese labels, an English definition and a module, find dangling references, verify the
ELI terms used against the ELI ontology (when a copy is available), run an OWL-RL closure on synthetic
fixtures (expected inferences present, expected inconsistency detected), run SHACL on the fixtures
(positive conforms, negative reports the planted errors), write pyLODE HTML and a JSON-LD context.
release_check(): the ontology header carries the release of the build (owl:versionInfo, owl:versionIRI,
dcterms:modified = build date, dcterms:source = the source datasets of the build) and every term of the judiciary
module (plus vlo:Court) has a scope note saying that it is populated from v2.
"""
import json
import os
import sys
import time
import traceback

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD, DCTERMS

VLO = Namespace("https://tmquan.github.io/VLOnto/ontology#")
VLID = Namespace("https://tmquan.github.io/VLOnto/id/")
T = Namespace("https://tmquan.github.io/VLOnto/id/test/")
ELI = Namespace("http://data.europa.eu/eli/ontology#")
SCHEMA = Namespace("https://schema.org/")
PROV = Namespace("http://www.w3.org/ns/prov#")
ONTO_IRI = URIRef("https://tmquan.github.io/VLOnto/ontology")
ERRNS = Namespace("http://www.daml.org/2002/03/agents/agent-ont#")


def load(*paths):
    g = Graph()
    for p in paths:
        g.parse(p, format="turtle")
    return g


def vlo_terms(g):
    kinds = {OWL.Class: "class", OWL.ObjectProperty: "object_property", OWL.DatatypeProperty: "datatype_property",
             OWL.AnnotationProperty: "annotation_property"}
    out = {}
    for k, name in kinds.items():
        for s in g.subjects(RDF.type, k):
            if isinstance(s, URIRef) and str(s).startswith(str(VLO)):
                out[s] = name
    return out


def completeness(g):
    """Every VLOnto class/property: rdfs:label @en and @vi, English skos:definition or rdfs:comment, vlo:module."""
    problems = []
    terms = vlo_terms(g)
    for s, kind in sorted(terms.items()):
        labels = {l.language for l in g.objects(s, RDFS.label) if isinstance(l, Literal)}
        defs_en = [d for p in (SKOS.definition, RDFS.comment) for d in g.objects(s, p) if isinstance(d, Literal) and d.language == "en"]
        mods = list(g.objects(s, VLO.module))
        miss = []
        if "en" not in labels: miss.append("label@en")
        if "vi" not in labels: miss.append("label@vi")
        if not defs_en: miss.append("definition@en")
        if not mods: miss.append("module")
        elif any((m, RDF.type, VLO.Module) not in g for m in mods): miss.append("module-not-a-Module")
        if miss:
            problems.append({"term": str(s), "kind": kind, "missing": miss})
    counts = {}
    for kind in terms.values():
        counts[kind] = counts.get(kind, 0) + 1
    return {"terms": len(terms), "by_kind": counts, "problems": problems}


def dangling(g):
    """IRIs used as subClassOf/subPropertyOf/domain/range/inverseOf targets or as types that are never declared."""
    declared = set(g.subjects(RDF.type, None))
    used = set()
    for p in (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range, OWL.inverseOf):
        for o in g.objects(None, p):
            if isinstance(o, URIRef):
                used.add(o)
    builtin = {str(XSD), str(RDFS), str(RDF), str(OWL)}
    out = [str(u) for u in used if u not in declared and not any(str(u).startswith(b) for b in builtin)]
    return sorted(out)


def eli_terms_used(g):
    return sorted({str(x) for t in g for x in t if isinstance(x, URIRef) and str(x).startswith(str(ELI))})


def eli_check(g, eli_path):
    used = eli_terms_used(g)
    if not eli_path or not os.path.exists(eli_path) or os.path.getsize(eli_path) < 1000:
        return {"available": False, "used": used}
    e = Graph()
    for fmt in ("xml", "turtle"):
        try:
            e.parse(eli_path, format=fmt)
            break
        except Exception:
            e = Graph()
    defined = {str(s) for s in e.subjects() if isinstance(s, URIRef) and str(s).startswith(str(ELI))}
    missing = [u for u in used if u not in defined]
    return {"available": True, "eli_triples": len(e), "eli_terms_defined": len(defined), "used": used, "missing_in_eli": missing}


LOGICAL = {RDF.type, RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range, OWL.inverseOf, OWL.disjointWith,
           OWL.members, RDF.first, RDF.rest, OWL.equivalentClass, OWL.equivalentProperty, OWL.propertyDisjointWith}


def logical_axioms(g):
    """Only the triples that OWL-RL rules use; annotations (labels, definitions) are dropped."""
    out = Graph()
    for t in g:
        if t[1] in LOGICAL and not isinstance(t[2], Literal):
            out.add(t)
    return out


SCHEMA_TYPES = {OWL.Class, RDFS.Class, RDF.Property, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty,
                OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.TransitiveProperty, OWL.SymmetricProperty,
                OWL.AsymmetricProperty, OWL.IrreflexiveProperty, OWL.ReflexiveProperty, OWL.Ontology,
                OWL.AllDisjointClasses, OWL.Restriction, RDFS.Datatype}


def shacl_support(onto):
    """Ontology triples that the shapes need when validating instance data.

    They are added to the data graph instead of using pyshacl's ont_graph option, which did not finish within
    60 s per shape on this ontology (pyshacl 0.40.2, diagnosis job J04). Kept: the named class hierarchy
    (rdfs:subClassOf, so that sh:targetClass and sh:class also cover subclasses) and every concept-scheme
    individual with its types, scheme and labels (so that sh:class vlo:DocumentType etc. can be checked).
    """
    out = Graph()
    for s, o in onto.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            out.add((s, RDFS.subClassOf, o))
    for s in set(onto.subjects(RDF.type, None)):
        if not isinstance(s, URIRef) or set(onto.objects(s, RDF.type)) & SCHEMA_TYPES:
            continue
        for p, o in onto.predicate_objects(s):
            if not isinstance(o, BNode):
                out.add((s, p, o))
    return out


def owlrl_check(onto, fixtures_dir):
    import owlrl
    res = {}
    onto = logical_axioms(onto)
    res["ontology_logical_triples"] = len(onto)
    g = Graph() + onto
    g.parse(os.path.join(fixtures_dir, "positive.ttl"), format="turtle")
    n0 = len(g)
    t0 = time.time()
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(g)
    res["positive"] = {"triples_before": n0, "triples_after": len(g), "seconds": round(time.time() - t0, 2)}
    expected = [
        (T["doc-new"], RDF.type, ELI.LegalResource), (T["doc-new"], RDF.type, SCHEMA.Legislation),
        (T["doc-new"], RDF.type, VLO.NormativeLegalDocument),
        (T["doc-new"], ELI.repeals, T["doc-old"]), (T["doc-new"], VLO.changes, T["doc-old"]), (T["doc-new"], ELI.changes, T["doc-old"]),
        (T["doc-old"], VLO.replacedBy, T["doc-new"]), (T["doc-old"], VLO.changedBy, T["doc-new"]),
        (T["doc-new"], ELI.based_on, T["doc-const"]), (T["doc-const"], VLO.isLegalBasisOf, T["doc-new"]),
        (T["art-5"], ELI.is_part_of, T["chapter-1"]), (T["chapter-1"], VLO.hasPart, T["art-5"]),
        (T["art-5"], RDF.type, ELI.LegalResourceSubdivision), (T["art-5"], ELI.cites, T["doc-const"]),
        (T["term-2"], VLO.relatedTerm, T["term-1"]), (T["term-1"], SKOS.related, T["term-2"]),
        (T["qa-1-answer"], SCHEMA.citation, T["art-5"]), (T["qa-1"], SCHEMA.acceptedAnswer, T["qa-1-answer"]),
        (T["dec-1"], RDF.type, VLO.CourtDecision), (T["dec-1"], VLO.citesCase, T["prec-1"]),
        (T["dec-1"], DCTERMS.references, T["art-5-k1"]), (T["change-1"], RDF.type, PROV.Activity),
        (T["doc-new"], ELI.type_document, VLO["doctype-law"]), (VLO["doctype-law"], RDF.type, ELI.ResourceType),
        (T["doc-new"], ELI.in_force, VLO["validity-in-force"]), (T["doc-new"], ELI.passed_by, T["issuer-1"]),
        (T["prec-1"], RDF.type, VLO.JudicialDocument),
    ]
    res["positive"]["expected_inferences"] = len(expected)
    res["positive"]["missing_inferences"] = [" ".join(x.n3() for x in t) for t in expected if t not in g]
    errs = [str(o) for s in g.subjects(RDF.type, ERRNS.ErrorMessage) for o in g.objects(s, ERRNS.error)]
    res["positive"]["inconsistencies"] = errs
    same = [(str(a), str(b)) for a, b in g.subject_objects(OWL.sameAs) if a != b and str(a).startswith(str(T))]
    res["positive"]["sameAs_between_test_nodes"] = same
    nothing = [str(s) for s in g.subjects(RDF.type, OWL.Nothing)]
    res["positive"]["owl_nothing_members"] = nothing
    # negative: planted disjointness violation and functional-property clash must be detected
    g2 = Graph() + onto
    g2.parse(os.path.join(fixtures_dir, "negative.ttl"), format="turtle")
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(g2)
    errs2 = [str(o) for s in g2.subjects(RDF.type, ERRNS.ErrorMessage) for o in g2.objects(s, ERRNS.error)]
    same2 = sorted({tuple(sorted((str(a), str(b)))) for a, b in g2.subject_objects(OWL.sameAs) if a != b and str(a).startswith(str(T))})
    res["negative"] = {"inconsistencies": errs2[:10], "n_inconsistencies": len(errs2), "sameAs_between_test_nodes": same2,
                       "disjointness_detected": any("bad-doc" in e for e in errs2),
                       "functional_clash_detected": any("bad-doc" in a and "bad-doc-2" in b or "bad-doc-2" in a and "bad-doc" in b for a, b in same2)}
    res["pass"] = (not res["positive"]["missing_inferences"] and not res["positive"]["inconsistencies"]
                   and not res["positive"]["sameAs_between_test_nodes"] and not nothing
                   and res["negative"]["disjointness_detected"] and res["negative"]["functional_clash_detected"])
    return res


def shacl_check(onto, shapes, fixtures_dir):
    from pyshacl import validate
    support = shacl_support(onto)
    res = {"support_triples": len(support), "mode": "data graph + shacl_support(ontology); no ont_graph, no inference"}
    for name in ("positive", "negative"):
        d = Graph().parse(os.path.join(fixtures_dir, f"{name}.ttl"), format="turtle")
        d += support
        t0 = time.time()
        conforms, rg, text = validate(d, shacl_graph=shapes, inference="none", abort_on_first=False,
                                      allow_warnings=True, meta_shacl=False, advanced=False, debug=False)
        SH = Namespace("http://www.w3.org/ns/shacl#")
        focus = sorted({str(o) for r in rg.subjects(RDF.type, SH.ValidationResult) for o in rg.objects(r, SH.focusNode)})
        paths = sorted({f"{str(f).split('/')[-1]}:{str(p).split('#')[-1]}" for r in rg.subjects(RDF.type, SH.ValidationResult)
                        for f in rg.objects(r, SH.focusNode) for p in rg.objects(r, SH.resultPath)})
        res[name] = {"conforms": bool(conforms), "n_results": len(list(rg.subjects(RDF.type, SH.ValidationResult))),
                     "focus_nodes": focus, "focus_path_pairs": paths, "seconds": round(time.time() - t0, 2)}
        if name == "positive" and not conforms:
            res[name]["text"] = text[:3000]
    planted = {"bad-doc:documentType", "bad-change:evidenceText", "bad-change:actingDocument", "bad-article:inDocument",
               "bad-article:provisionNumber", "bad-term:definition"}
    found = set(res["negative"]["focus_path_pairs"])
    res["negative"]["planted_errors_found"] = sorted(planted & found)
    res["negative"]["planted_errors_missed"] = sorted(planted - found)
    res["pass"] = res["positive"]["conforms"] and not res["negative"]["conforms"] and not res["negative"]["planted_errors_missed"]
    return res


def jsonld_context(onto):
    ctx = {"vlo": str(VLO), "vlid": str(VLID), "skos": str(SKOS), "rdfs": str(RDFS), "xsd": str(XSD),
           "dcterms": str(DCTERMS), "prov": str(PROV), "eli": str(ELI), "schema": str(SCHEMA),
           "id": "@id", "type": "@type", "label": {"@id": "rdfs:label", "@container": "@language"},
           "prefLabel": {"@id": "skos:prefLabel", "@container": "@language"}, "inScheme": {"@id": "skos:inScheme", "@type": "@id"}}
    for s in sorted(set(onto.subjects(RDF.type, OWL.ObjectProperty))):
        if str(s).startswith(str(VLO)):
            ctx[str(s)[len(str(VLO)):]] = {"@id": "vlo:" + str(s)[len(str(VLO)):], "@type": "@id"}
    for s in sorted(set(onto.subjects(RDF.type, OWL.DatatypeProperty))):
        if str(s).startswith(str(VLO)):
            local = str(s)[len(str(VLO)):]
            rng = onto.value(s, RDFS.range)
            entry = {"@id": "vlo:" + local}
            if rng is not None and str(rng).startswith(str(XSD)):
                entry["@type"] = "xsd:" + str(rng)[len(str(XSD)):]
            elif rng == RDFS.Literal:
                entry["@language"] = "vi"
            ctx[local] = entry
    return {"@context": ctx}


def docs_view(g):
    """Copy of the ontology arranged for pyLODE OntPub.

    OntPub treats every skos:ConceptScheme as an ontology header (it merges their titles into the page title and
    shows the last one's IRI), and it picks an arbitrary label when a term has labels in two languages (headings
    then read 'OrdinancePháp lệnh'). The view therefore drops the ConceptScheme typing, keeps the English
    rdfs:label/skos:prefLabel and moves Vietnamese labels to skos:altLabel (shown as 'Vietnamese label').
    Concept schemes and their concepts are rendered by concepts_section() instead.
    """
    d = Graph()
    for prefix, ns in g.namespace_manager.namespaces():
        d.bind(prefix, ns, override=True)
    for t in g:
        s, p, o = t
        if p == RDF.type and o == SKOS.ConceptScheme:
            d.add((s, RDF.type, OWL.NamedIndividual))
            continue
        if (s != ONTO_IRI and p in (RDFS.label, SKOS.prefLabel) and isinstance(o, Literal) and o.language == "vi"):
            d.add((s, SKOS.altLabel, o))
            continue
        d.add(t)
    return d


def _txt(g, s, p, lang):
    for o in g.objects(s, p):
        if isinstance(o, Literal) and o.language == lang:
            return str(o)
    return ""


def concepts_section(g):
    """HTML (pyLODE classes) listing every concept scheme of the ontology and its concepts, with anchors."""
    from html import escape as E
    schemes = sorted(set(g.subjects(RDF.type, SKOS.ConceptScheme)), key=str)
    out = ['<div class="section" id="concept-schemes">', "<h2>Concept schemes</h2>",
           "<p>Controlled vocabularies of VLOnto (SKOS). Schemes marked data-driven are filled by the knowledge graph "
           "build (legal areas, terms, news categories); the others are defined in the ontology.</p>"]
    for sc in schemes:
        local = str(sc).split("#")[-1]
        en = _txt(g, sc, RDFS.label, "en") or _txt(g, sc, SKOS.prefLabel, "en")
        vi = _txt(g, sc, RDFS.label, "vi") or _txt(g, sc, SKOS.prefLabel, "vi")
        df = _txt(g, sc, SKOS.definition, "en")
        members = sorted(set(g.subjects(SKOS.inScheme, sc)), key=lambda x: (str(g.value(x, SKOS.notation) or ""), str(x)))
        out.append(f'<div class="property entity" id="{E(local)}"><h3>{E(en)}</h3><table>')
        out.append(f"<tr><th>IRI</th><td><code>{E(str(sc))}</code></td></tr>")
        if vi:
            out.append(f"<tr><th>Vietnamese label</th><td>{E(vi)}</td></tr>")
        if df:
            out.append(f"<tr><th>Description</th><td><p>{E(df)}</p></td></tr>")
        if not members:
            out.append("<tr><th>Concepts</th><td>data-driven: concepts are created by the knowledge-graph build</td></tr>")
        out.append("</table>")
        if members:
            out.append('<table class="concepts"><tr><th>Concept</th><th>Notation</th><th>English</th><th>Vietnamese</th><th>Definition</th></tr>')
            for m in members:
                ml = str(m).split("#")[-1]
                note = g.value(m, SKOS.notation)
                out.append(f'<tr id="{E(ml)}"><td><code>vlo:{E(ml)}</code></td><td>{E(str(note)) if note is not None else ""}</td>'
                           f"<td>{E(_txt(g, m, SKOS.prefLabel, 'en'))}</td><td>{E(_txt(g, m, SKOS.prefLabel, 'vi'))}</td>"
                           f"<td>{E(_txt(g, m, SKOS.definition, 'en'))}</td></tr>")
            out.append("</table>")
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out), len(schemes), sum(1 for _ in g.subject_objects(SKOS.inScheme))


def make_docs(onto_path, out_html):
    """pyLODE 3 OntPub HTML documentation (docs view + post-processing, see docs_view())."""
    import re as _re
    info = {}
    try:
        from pylode import OntPub
    except Exception:
        from pylode.profiles.ontpub import OntPub  # type: ignore
    g = load(onto_path)
    od = OntPub(ontology=docs_view(g))
    html = od.make_html()
    # pyLODE has no description or source ontology for predicates outside its background vocabularies
    html = html.replace(' title="None. Defined in None"', "").replace('. Defined in None"', '"').replace(' title="None"', "")
    html = html.replace(">Alternative Label</a>", ">Vietnamese label</a>")
    title = str(g.value(ONTO_IRI, DCTERMS.title) or "VLOnto")
    for o in g.objects(ONTO_IRI, DCTERMS.title):
        if isinstance(o, Literal) and o.language == "en":
            title = str(o)
    html = _re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=_re.S)
    sec, n_schemes, n_members = concepts_section(g)
    html = html.replace('<div id="namespaces">', sec + '\n<div id="namespaces">', 1)
    html = html.replace('<a href="#namespaces">', '<a href="#concept-schemes">Concept schemes</a>\n</h4>\n</li>\n<li>\n<h4>\n<a href="#namespaces">', 1) \
        if '<a href="#namespaces">' in html else html
    from .nfc import nfc
    html = nfc(html)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    ids = set(_re.findall(r'\bid="([^"]+)"', html))
    hrefs = _re.findall(r'href="#([^"]+)"', html)
    missing = sorted({h for h in hrefs if h not in ids})
    info["bytes"] = os.path.getsize(out_html)
    info["title"] = title
    info["has_vietnamese"] = ("Văn bản" in html)
    info["concept_schemes"] = n_schemes
    info["concepts_listed"] = n_members
    info["internal_links"] = len(hrefs)
    info["broken_internal_links"] = missing[:20]
    info["n_broken_internal_links"] = len(missing)
    info["none_strings"] = html.count(">None<") + html.count('"None"')
    return info


def _runner(q, fn, args):
    try:
        q.put(fn(*args))
    except Exception as e:
        q.put({"error": repr(e), "trace": traceback.format_exc()[-2000:]})


def run_with_timeout(fn, args, timeout_s):
    """Run fn(*args) in a forked process; return its dict or a timeout record."""
    import multiprocessing as mp
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    p = ctx.Process(target=_runner, args=(q, fn, args))
    t0 = time.time()
    p.start()
    p.join(timeout_s)
    if p.is_alive():
        p.terminate()
        p.join()
        return {"error": f"timeout after {timeout_s}s", "pass": None}
    try:
        out = q.get(timeout=5)
    except Exception as e:
        out = {"error": f"no result: {e!r}"}
    out["wall_s"] = round(time.time() - t0, 1)
    return out


COURT_EXTRA_TERMS = (VLO.Court, VLO["module-judiciary"])


def court_terms(g):
    """Terms whose data comes from the court datasets: the judiciary module, vlo:Court and the module concept itself."""
    return sorted(set(g.subjects(VLO.module, VLO["module-judiciary"])) | set(COURT_EXTRA_TERMS), key=str)


def release_check(g):
    try:
        from . import config as C
    except ImportError:          # run as a script: no package context
        return {"available": False, "pass": None}
    vi, viri = g.value(ONTO_IRI, OWL.versionInfo), g.value(ONTO_IRI, OWL.versionIRI)
    prior, mod = g.value(ONTO_IRI, OWL.priorVersion), g.value(ONTO_IRI, DCTERMS.modified)
    srcs = sorted(str(o) for o in g.objects(ONTO_IRI, DCTERMS.source))
    want = sorted(f"https://huggingface.co/datasets/tmquan/{d}" for d in C.SOURCES)
    terms = court_terms(g)
    noted = [t for t in terms if any(isinstance(o, Literal) and o.language == "en" and "2.0" in str(o) for o in g.objects(t, SKOS.scopeNote))
             and any(isinstance(o, Literal) and o.language == "vi" for o in g.objects(t, SKOS.scopeNote))]
    out = {"available": True, "versionInfo": str(vi) if vi is not None else None, "versionIRI": str(viri) if viri is not None else None,
           "priorVersion": str(prior) if prior is not None else None, "modified": str(mod) if mod is not None else None,
           "expected": {"versionInfo": C.VERSION, "versionIRI": C.ONTOLOGY_VERSION_IRI, "modified": C.BUILD_DATE, "sources": want},
           "sources": srcs, "n_sources": len(srcs), "sources_match": srcs == want, "court_terms": len(terms), "scope_notes": len(noted),
           "court_terms_without_note": [str(t) for t in terms if t not in noted]}
    out["pass"] = (out["versionInfo"] == C.VERSION and out["versionIRI"] == C.ONTOLOGY_VERSION_IRI and out["modified"] == C.BUILD_DATE
                   and out["sources_match"] and len(noted) == len(terms))
    return out


def check_ontology(repo, outdir, eli_path=None):
    os.makedirs(outdir, exist_ok=True)
    onto_path = os.path.join(repo, "ontology", "vlonto.ttl")
    shapes_path = os.path.join(repo, "ontology", "vlonto-shapes.ttl")
    fixtures = os.path.join(repo, "vlonto", "tests", "fixtures")
    rep = {}
    t1 = time.time()
    onto = load(onto_path)
    shapes = load(shapes_path)
    print(f"parsed {len(onto)} + {len(shapes)} triples in {time.time() - t1:.1f}s", flush=True)
    rep["parse"] = {"ontology_triples": len(onto), "shapes_triples": len(shapes),
                    "ontology_iri_typed": (ONTO_IRI, RDF.type, OWL.Ontology) in onto,
                    "version": str(onto.value(ONTO_IRI, OWL.versionInfo)), "versionIRI": str(onto.value(ONTO_IRI, OWL.versionIRI))}
    t1 = time.time()
    rep["completeness"] = completeness(onto)
    print(f"completeness {time.time() - t1:.1f}s", flush=True)
    rep["dangling"] = dangling(onto)
    print(f"dangling {time.time() - t1:.1f}s", flush=True)
    rep["release"] = release_check(onto)
    print(f"release metadata pass={rep['release'].get('pass')}", flush=True)
    rep["eli"] = eli_check(onto, eli_path)
    print(f"eli {time.time() - t1:.1f}s", flush=True)
    print("parse/completeness/dangling/eli done", flush=True)
    t1 = time.time()
    rep["shacl"] = run_with_timeout(shacl_check, (onto, shapes, fixtures), int(os.environ.get("SHACL_TIMEOUT", "300")))
    print(f"shacl done {time.time() - t1:.1f}s pass={rep['shacl'].get('pass')}", flush=True)
    t1 = time.time()
    rep["owlrl"] = run_with_timeout(owlrl_check, (onto, fixtures), int(os.environ.get("OWLRL_TIMEOUT", "900")))
    print(f"owlrl done {time.time() - t1:.1f}s pass={rep['owlrl'].get('pass')}", flush=True)
    ctx = jsonld_context(onto)
    from .nfc import nfc_obj
    with open(os.path.join(repo, "ontology", "vlonto-context.jsonld"), "w", encoding="utf-8") as f:
        json.dump(nfc_obj(ctx), f, ensure_ascii=False, indent=1)
    rep["jsonld_context_terms"] = len(ctx["@context"])
    t1 = time.time()
    try:
        rep["pylode"] = make_docs(onto_path, os.path.join(repo, "ontology", "vlonto.html"))
    except Exception as e:
        rep["pylode"] = {"error": repr(e), "trace": traceback.format_exc()[-2000:]}
    print(f"pylode done {time.time() - t1:.1f}s", flush=True)
    rep["pass"] = (not rep["completeness"]["problems"] and not rep["dangling"] and rep["release"].get("pass") is not False
                   and (not rep["eli"].get("available") or not rep["eli"].get("missing_in_eli"))
                   and rep.get("owlrl", {}).get("pass") is True and rep.get("shacl", {}).get("pass") is True
                   and "error" not in rep.get("pylode", {}))
    with open(os.path.join(outdir, "ontology_check.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=str)
    return rep


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(int(os.environ.get("STACK_DUMP_S", "120")), repeat=True)
    r = check_ontology(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(json.dumps({k: (v if k in ("parse", "pass", "dangling", "jsonld_context_terms") else "...") for k, v in r.items()}, ensure_ascii=False))
    print("completeness problems:", len(r["completeness"]["problems"]), r["completeness"]["by_kind"])
    for p in r["completeness"]["problems"][:20]:
        print("  ", p)
    print("eli:", {k: v for k, v in r["eli"].items() if k != "used"})
    print("owlrl:", json.dumps(r.get("owlrl"), ensure_ascii=False)[:2500])
    print("shacl:", json.dumps(r.get("shacl"), ensure_ascii=False)[:2500])
    print("pylode:", r.get("pylode"))

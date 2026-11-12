#!/usr/bin/env python3
"""Collect every number, table and example output used by the VLOnto playbook.

Run on the build node with the knowledge-graph environment (polars, duckdb, rdflib, pyoxigraph):

    V=<VLOnto root> R=<vn-legal root> $V/envs/kg/bin/python playbook/tools/gather_facts.py \
        --data-report $V/build/playbook/inputs/data_report.md \
        --guide $V/build/playbook/inputs/vn_legal_agent_guide.md

Reads only files written by the KG build ($V/build/{kg,rdf,reports,site_data}), the ontology and docs
in the repo, the toolchain pins in repo/tools and the two reports given on the command line. Runs the
SQL recipes (DuckDB), the SPARQL recipes (pyoxigraph, on the browser subset and on the full dump) and
the Python examples, and captures their output. Writes, deterministically (sorted keys, NFC text):

    playbook/data/facts.json     every number and table the playbook prints, with input provenance
    playbook/data/figures.json   chart data for playbook/charts.typ
    playbook/data/SHA256SUMS     sha256 of the release files (release layout paths)
"""
import argparse
import datetime
import decimal
import glob
import hashlib
import importlib.metadata as md
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

V = Path(os.environ.get("V", Path(__file__).resolve().parents[3]))     # <V>/repo/playbook/tools
R = Path(os.environ.get("R", V.parent / "vnlegal"))
REPO, BUILD = V / "repo", V / "build"
KG, RDF, REPORTS, SITE = BUILD / "kg", BUILD / "rdf", BUILD / "reports", BUILD / "site_data"
PB = REPO / "playbook"
WORK = BUILD / "playbook" / "work"
sys.path.insert(0, str(REPO / "vlonto"))
from vlonto import config as C  # noqa: E402  (same paths, IRIs and source pins as the build)

PROV = {}       # input file -> sha256
TIMINGS = {}    # not written to facts.json (non-deterministic)
MAX_ROWS = 12

PREFIXES = [
    ("vlo", C.VLO), ("vlid", C.ID), ("eli", "http://data.europa.eu/eli/ontology#"),
    ("skos", "http://www.w3.org/2004/02/skos/core#"), ("dcterms", "http://purl.org/dc/terms/"),
    ("prov", "http://www.w3.org/ns/prov#"), ("schema", "https://schema.org/"),
    ("org", "http://www.w3.org/ns/org#"), ("owl", "http://www.w3.org/2002/07/owl#"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("xsd", "http://www.w3.org/2001/XMLSchema#"), ("vann", "http://purl.org/vocab/vann/"),
]


# ----------------------------------------------------------------------------- helpers
def rel(p):
    p = Path(p)
    for base, name in ((V, "$V"), (R, "$R")):
        try:
            return f"{name}/{p.resolve().relative_to(base.resolve())}"
        except ValueError:
            pass
    return p.name


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(p):
    p = Path(p)
    PROV[rel(p)] = sha256(p)
    return json.loads(p.read_text(encoding="utf-8"))


def read_text(p):
    p = Path(p)
    PROV[rel(p)] = sha256(p)
    return p.read_text(encoding="utf-8")


def machine_subs():
    """Absolute paths of this machine (build root, vn-legal root, home folder) and its host name,
    longest first, with the placeholders that replace them in the facts files."""
    import socket
    subs = {}
    for p, name in ((V, "$V"), (R, "$R"), (Path.home(), "~")):
        subs[str(p)] = subs[str(p.resolve())] = name
    host = socket.gethostname()
    subs[host] = subs[host.split(".")[0]] = "build-node"
    return sorted(subs.items(), key=lambda s: -len(s[0]))


def machine_leftovers(text):
    """Machine-specific strings still in a facts file: the host name, the user name, home folders."""
    import getpass
    import socket
    marks = {socket.gethostname(), socket.gethostname().split(".")[0], getpass.getuser()}
    if str(Path.home().parent) != "/":
        marks.add(str(Path.home().parent) + "/")
    found = sorted(m for m in marks if m and m in text)
    # paths of another machine or build folder that the substitutions could not map to $V or $R:
    # home-relative (~/...) and absolute paths under the usual home and temporary folders
    paths = r"(?<![\w$])~/[^\s\"']*|(?<![\w./:-])/(?:Users|home|localhome|private|var/folders)/[^\s\"']*"
    found += sorted(set(re.findall(paths, text)))[:5]
    return found


def scrub(x, subs):
    """Replace the machine-specific strings of machine_subs() in every string of a JSON value."""
    if isinstance(x, str):
        for old, new in subs:
            x = x.replace(old, new)
        return x
    if isinstance(x, dict):
        return {k: scrub(v, subs) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [scrub(v, subs) for v in x]
    return x


def nfc(x):
    if isinstance(x, str):
        return unicodedata.normalize("NFC", x)
    if isinstance(x, dict):
        return {nfc(k): nfc(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [nfc(v) for v in x]
    return x


def curie(u):
    s = str(u)
    for p, ns in PREFIXES:
        if s.startswith(ns):
            return f"{p}:{s[len(ns):]}"
    return s


def plain(v):
    """JSON-safe scalar for a DuckDB / pyoxigraph value."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(round(v, 4))
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return str(v)


def md_sections(text, level=2):
    """{heading: body} for '## ' (level 2) headings of a Markdown file."""
    out, cur, buf = {}, None, []
    mark = "#" * level + " "
    for line in text.splitlines():
        if line.startswith(mark):
            if cur is not None:
                out[cur] = "\n".join(buf).strip("\n")
            cur, buf = line[len(mark):].strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip("\n")
    return out


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout, r.stderr


# ----------------------------------------------------------------------------- build reports
def gather_reports():
    f = {}
    f["stats"] = read_json(SITE / "stats.json")
    f["build"] = read_json(REPORTS / "build_report.json")
    f["build"].pop("files", None)  # absolute paths; the data dictionary has the table list
    f["validation"] = read_json(REPORTS / "validation.json")
    ox = f["validation"].get("oxigraph") or {}
    if "store" in ox:   # absolute path of the machine that ran the build: keep only its place in the build folder
        ox["store"] = "$V/build/oxigraph" if str(ox["store"]).rstrip("/").endswith("/build/oxigraph") else None
    f["checks"] = read_json(REPORTS / "checks.json")
    f["ontology_check"] = read_json(REPORTS / "ontology_check.json")
    f["export"] = read_json(REPORTS / "export_report.json")
    f["export"].pop("nt_gz_path", None)
    f["core"] = read_json(REPORTS / "core_report.json")
    f["manifest"] = read_json(SITE / "manifest.json")
    f["sparql_examples"] = read_json(SITE / "sparql_examples.json")
    review = read_json(REPO / "docs" / "spot_check_review.json")
    rows = []
    for name, r in review["edge_types"].items():
        nv = r["checked"] - r["correct"] - r["wrong"]
        rows.append({"edge_type": name, "checked": r["checked"], "correct": r["correct"],
                     "wrong": r["wrong"], "not_verifiable": nv, "notes": r.get("notes", "")})
    f["spot_checks"] = {"method": review["method"], "release_note": review.get("release_note", ""), "rows": rows,
                        "checked": sum(r["checked"] for r in rows),
                        "correct": sum(r["correct"] for r in rows),
                        "wrong": sum(r["wrong"] for r in rows),
                        "not_verifiable": sum(r["not_verifiable"] for r in rows)}
    dd = read_json(KG / "data_dictionary.json")
    tables = []
    for name, t in dd.items():
        tables.append({"name": name, "rows": t["rows"], "bytes": t.get("bytes"),
                       "description": t.get("description", ""),
                       "local_only": "kg_local" in str(t.get("path", "")),
                       "columns": [{k: c.get(k) for k in ("name", "type", "non_null", "description")}
                                   for c in t["columns"]]})
    f["data_dictionary"] = tables
    dash = read_json(SITE / "dashboard.json")
    f["dashboard"] = {
        "keys": sorted(dash.keys()),
        "documents_by_issuer_top": dash["documents_by_issuer_top50"][:10],
        "documents_by_area": dash["documents_by_area"],
        "legal_basis_by_method": dash["legal_basis_by_method"],
        "citations_by_kind": dash["citations_by_kind"],
        "most_cited_documents": {k: v[:10] for k, v in dash["most_cited_documents"].items()},
        "most_cited_articles": {k: v[:10] for k, v in dash.get("most_cited_articles", {}).items()},
        "changes_by_kind_year": dash["changes_by_kind_year"],
    }
    kg_report = read_text(REPORTS / "kg_report.md")
    secs = md_sections(kg_report)
    lim = next((v for k, v in secs.items() if k.lower().endswith("limitations")), "")
    f["kg_limitations"] = [l[2:].strip() for l in lim.splitlines() if l.startswith("- ")]
    pol = read_text(REPO / "docs" / "licence_policy.md")
    psecs = md_sections(pol)
    attrib = next(v for k, v in psecs.items() if k.startswith("4."))
    quotes = [l[2:].strip() for l in attrib.splitlines() if l.startswith("> ")]
    outlic = next(v for k, v in psecs.items() if k.startswith("3."))
    f["licence"] = {"attribution_en": quotes[0], "attribution_vi": quotes[1],
                    "outputs": [l[2:].strip() for l in outlic.splitlines() if l.startswith("* ")],
                    "policy_version_line": pol.splitlines()[2].strip()}
    return f


# ----------------------------------------------------------------------------- ontology
def gather_ontology():
    from rdflib import BNode, Graph, Literal, URIRef
    from rdflib.namespace import OWL, RDF, RDFS, SKOS, DCTERMS
    path = REPO / "ontology" / "vlonto.ttl"
    PROV[rel(path)] = sha256(path)
    g = Graph()
    g.parse(path, format="turtle")
    VLO = C.VLO
    onto = URIRef(C.VLO.rstrip("#"))

    def lit(s, p, lang):
        vals = sorted(str(o) for o in g.objects(s, p) if isinstance(o, Literal) and o.language == lang)
        return vals[0] if vals else None

    def refs(s, p):
        out = []
        for o in g.objects(s, p):
            if isinstance(o, URIRef):
                out.append(curie(o))
            elif isinstance(o, BNode):
                members = list(g.items(g.value(o, OWL.unionOf))) if g.value(o, OWL.unionOf) else []
                if members:
                    out.append(" or ".join(sorted(curie(m) for m in members)))
                else:
                    out.append("(restriction)")
        return sorted(out)

    def module(s):
        m = g.value(s, URIRef(VLO + "module"))
        return str(g.value(m, SKOS.notation)) if m is not None else None

    kinds = [("class", OWL.Class), ("object_property", OWL.ObjectProperty),
             ("datatype_property", OWL.DatatypeProperty), ("annotation_property", OWL.AnnotationProperty)]
    chars = [OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.TransitiveProperty,
             OWL.SymmetricProperty, OWL.AsymmetricProperty, OWL.IrreflexiveProperty]
    terms = []
    for kind, t in kinds:
        for s in sorted({x for x in g.subjects(RDF.type, t) if str(x).startswith(VLO)}, key=str):
            sup = refs(s, RDFS.subClassOf) if kind == "class" else refs(s, RDFS.subPropertyOf)
            eq = refs(s, OWL.equivalentClass) + refs(s, OWL.equivalentProperty)
            terms.append({
                "kind": kind, "curie": curie(s), "local": str(s)[len(VLO):],
                "label_en": lit(s, RDFS.label, "en"), "label_vi": lit(s, RDFS.label, "vi"),
                "definition_en": lit(s, SKOS.definition, "en"),
                "definition_vi": lit(s, SKOS.definition, "vi"),
                "comment_en": lit(s, RDFS.comment, "en"), "module": module(s),
                "scope_note_en": lit(s, SKOS.scopeNote, "en"), "scope_note_vi": lit(s, SKOS.scopeNote, "vi"),
                "super": [x for x in sup if x != "(restriction)"],
                "restrictions": sup.count("(restriction)"), "equivalent": eq,
                "domain": refs(s, RDFS.domain), "range": refs(s, RDFS.range),
                "inverse": refs(s, OWL.inverseOf),
                "characteristics": sorted(curie(c) for c in chars if (s, RDF.type, c) in g),
                "disjoint": refs(s, OWL.disjointWith),
            })
    schemes = []
    for s in sorted({x for x in g.subjects(RDF.type, SKOS.ConceptScheme) if str(x).startswith(VLO)}, key=str):
        concepts = []
        for c in sorted(set(g.subjects(SKOS.inScheme, s)), key=str):
            concepts.append({"curie": curie(c), "notation": str(g.value(c, SKOS.notation) or ""),
                             "label_en": lit(c, SKOS.prefLabel, "en"),
                             "label_vi": lit(c, SKOS.prefLabel, "vi")})
        schemes.append({"curie": curie(s), "label_en": lit(s, RDFS.label, "en"),
                        "label_vi": lit(s, RDFS.label, "vi"),
                        "definition_en": lit(s, SKOS.definition, "en"), "module": module(s),
                        "scope_note_en": lit(s, SKOS.scopeNote, "en"), "scope_note_vi": lit(s, SKOS.scopeNote, "vi"),
                        "concepts": concepts})
    modules = []
    ms = next(x for x in schemes if x["curie"] == "vlo:ModuleScheme")
    for c in sorted(set(g.objects(URIRef(VLO + "ModuleScheme"), SKOS.hasTopConcept)), key=str):
        note = str(g.value(c, SKOS.notation))
        cnt = {k: sum(1 for t in terms if t["module"] == note and t["kind"] == k) for k, _ in kinds}
        cnt["concept_schemes"] = sum(1 for x in schemes if x["module"] == note)
        modules.append({"notation": note, "label_en": lit(c, SKOS.prefLabel, "en"),
                        "label_vi": lit(c, SKOS.prefLabel, "vi"),
                        "definition_en": lit(c, SKOS.definition, "en"),
                        "scope_note_en": lit(c, SKOS.scopeNote, "en"), "scope_note_vi": lit(c, SKOS.scopeNote, "vi"),
                        "counts": cnt})
    order = ["documents", "provisions", "agents", "validity-change", "citation-basis", "judiciary",
             "qa", "terminology", "news", "classification", "provenance"]
    modules.sort(key=lambda m: order.index(m["notation"]) if m["notation"] in order else 99)
    alignments = []
    for t in terms:
        for rel_name, targets in (("subClassOf" if t["kind"] == "class" else "subPropertyOf", t["super"]),
                                  ("equivalent", t["equivalent"])):
            for x in targets:
                if not x.startswith("vlo:") and ":" in x and not x.startswith("owl:"):
                    alignments.append({"term": t["curie"], "relation": rel_name, "external": x,
                                       "vocabulary": x.split(":")[0]})
    header = {
        "title_en": lit(onto, DCTERMS.title, "en"), "title_vi": lit(onto, DCTERMS.title, "vi"),
        "version": str(g.value(onto, OWL.versionInfo)), "version_iri": str(g.value(onto, OWL.versionIRI)),
        "license": str(g.value(onto, DCTERMS.license)), "created": str(g.value(onto, DCTERMS.created)),
        "modified": str(g.value(onto, DCTERMS.modified)),
        "prior_version": str(g.value(onto, OWL.priorVersion) or ""),
        "editorial_note_en": lit(onto, SKOS.editorialNote, "en"),
        "editorial_note_vi": lit(onto, SKOS.editorialNote, "vi"),
        "description_en": lit(onto, DCTERMS.description, "en"),
        "triples": len(g), "iri": str(onto), "namespace": VLO, "instance_base": C.ID,
    }
    shapes_path = REPO / "ontology" / "vlonto-shapes.ttl"
    PROV[rel(shapes_path)] = sha256(shapes_path)
    sg = Graph()
    sg.parse(shapes_path, format="turtle")
    SH = "http://www.w3.org/ns/shacl#"
    node_shapes = sorted({s for s in sg.subjects(RDF.type, URIRef(SH + "NodeShape"))}, key=str)
    shapes = {"triples": len(sg), "node_shapes": len(node_shapes),
              "property_shapes": len(set(sg.objects(None, URIRef(SH + "property")))),
              "targets": sorted({curie(o) for o in sg.objects(None, URIRef(SH + "targetClass"))})}
    by_kind = {k: sum(1 for t in terms if t["kind"] == k) for k, _ in kinds}
    return {"header": header, "terms": terms, "schemes": schemes, "modules": modules,
            "alignments": sorted(alignments, key=lambda a: (a["vocabulary"], a["term"], a["external"])),
            "by_kind": by_kind, "shapes": shapes,
            "prefixes": [{"prefix": p, "namespace": ns} for p, ns in PREFIXES]}, g


# ----------------------------------------------------------------------------- recipes and examples
RECIPES = [
    {"id": "r1", "title": "What replaced an act?", "base": "r1_replaced_by", "sparql_on": ["core", "full"]},
    {"id": "r2", "title": "Amendment history", "base": "r2_amendment_history", "sparql_on": ["core", "full"]},
    {"id": "r3", "title": "Legal-basis chain", "base": "r3_legal_basis_chain", "sparql_on": ["core", "full"]},
    {"id": "r4", "title": "Articles most cited in Q&A answers", "base": "r4_qa_articles", "sparql_on": ["full"]},
    {"id": "r5", "title": "Q&As citing an article", "base": "r5_qa_citing_article", "sparql_on": ["full"]},
    {"id": "r6", "title": "Terms of a legal area", "base": "r6_terms_of_area", "sparql_on": ["full"]},
]
EXAMPLES = ["quickstart_duckdb.py", "quickstart_polars.py", "quickstart_sparql.py",
            "load_full_dump.py", "agent_demo.py"]
SOURCE_ONLY = ["vlonto_tools.py"]  # imported (and so run) by agent_demo.py


def run_sql(con, sql):
    t0 = time.time()
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = [[plain(v) for v in r] for r in cur.fetchall()]
    return cols, rows, time.time() - t0


def run_sparql(store, q):
    t0 = time.time()
    res = store.query(q)
    cols = [v.value for v in res.variables]
    rows = []
    for sol in res:
        row = []
        for c in cols:
            t = sol[c]
            if t is None:
                row.append(None)
            elif type(t).__name__ == "NamedNode":
                row.append(curie(t.value))
            else:
                row.append(t.value)
        rows.append(row)
    return cols, rows, time.time() - t0


def gather_recipes(full_store):
    import duckdb
    from pyoxigraph import RdfFormat, Store
    con = duckdb.connect()
    core = Store()
    core.load(path=str(RDF / "vlonto-core.ttl"), format=RdfFormat.TURTLE)
    out = []
    for r in RECIPES:
        sql_path = PB / "recipes" / f"{r['base']}.sql"
        rq_path = PB / "recipes" / f"{r['base']}.rq"
        sql, rq = read_text(sql_path), read_text(rq_path)
        cols, rows, dt = run_sql(con, sql)
        TIMINGS[f"{r['id']}.sql"] = round(dt, 3)
        item = {"id": r["id"], "title": r["title"], "sql_file": f"recipes/{sql_path.name}",
                "rq_file": f"recipes/{rq_path.name}", "sql": sql, "sparql": rq,
                "sql_result": {"columns": cols, "rows": rows[:MAX_ROWS], "n_rows": len(rows)},
                "sparql_result": {}}
        for target in r["sparql_on"]:
            store = core if target == "core" else full_store
            if store is None:
                item["sparql_result"][target] = None
                continue
            c2, r2, dt2 = run_sparql(store, rq)
            TIMINGS[f"{r['id']}.rq.{target}"] = round(dt2, 3)
            item["sparql_result"][target] = {"columns": c2, "rows": r2[:MAX_ROWS], "n_rows": len(r2)}
        out.append(item)
        print(f"recipe {r['id']}: sql {len(rows)} rows; sparql "
              + ", ".join(f"{k}={v['n_rows'] if v else None}" for k, v in item["sparql_result"].items()),
              flush=True)
    return out


def gather_examples(reuse_store):
    out = {}
    env = dict(os.environ, PYTHONPATH=str(PB / "examples"), PYTHONHASHSEED="0")
    for name in EXAMPLES:
        path = PB / "examples" / name
        code = read_text(path)
        cache = WORK / f"{name}.out"
        if name == "load_full_dump.py" and reuse_store and (WORK / "vlonto-store").exists() and cache.exists():
            stdout = cache.read_text(encoding="utf-8")
        else:
            if name == "load_full_dump.py":
                shutil.rmtree(WORK / "vlonto-store", ignore_errors=True)
            t0 = time.time()
            rc, stdout, stderr = run([sys.executable, str(path)], cwd=WORK, env=env, timeout=1800)
            TIMINGS[name] = round(time.time() - t0, 1)
            if rc != 0:
                raise SystemExit(f"example {name} failed (exit {rc}):\n{stderr[-3000:]}")
            cache.write_text(stdout, encoding="utf-8")
        out[name] = {"file": f"examples/{name}", "code": code, "output": stdout.rstrip("\n")}
        print(f"example {name}: {len(stdout.splitlines())} lines", flush=True)
    for name in SOURCE_ONLY:
        out[name] = {"file": f"examples/{name}", "code": read_text(PB / "examples" / name),
                     "output": None}
    return out


# ----------------------------------------------------------------------------- other inputs
def gather_reports_external(data_report, guide):
    f = {}
    if data_report:
        t = read_text(data_report)
        m = re.search(r"v7 \(.*?\) \| (\d+)/(\d+) \((\d+)/(\d+), (\d+)/(\d+), (\d+)/(\d+)\)", t)
        w = re.search(r"Wilson 95% interval ([0-9]+\.[0-9]+)-([0-9]+\.[0-9]+)", t)
        known = re.search(r"Known cases \(all PASS\):\n\n(\|.*\n)+", t)
        known_rows = [l for l in known.group(0).splitlines() if l.startswith("| ") and "PASS" in l]
        f["data_report"] = {
            "file": rel(data_report),
            "validity_precision": {"correct": int(m.group(1)), "sampled": int(m.group(2)),
                                   "replaced_repealed": [int(m.group(3)), int(m.group(4))],
                                   "amended": [int(m.group(5)), int(m.group(6))],
                                   "partial": [int(m.group(7)), int(m.group(8))],
                                   "wilson_low": w.group(1), "wilson_high": w.group(2)},
            "known_cases_pass": len(known_rows),
            "known_cases": [[c.strip() for c in l.strip("|").split("|")][:3] for l in known_rows],
        }
    if guide:
        t = read_text(guide)
        p = re.search(r"superseded-law probes are flagged (\d+) of (\d+) with tools against (\d+) of (\d+) without", t)
        s = re.search(r"\*\*(\d+) of (\d+)\*\* answers named the replacing decree", t)
        j = re.search(r"judge correctness \(0.2\) rises from ([0-9.]+) \(model alone\) to ([0-9.]+) \(guarded agent\)", t)
        f["guide"] = {"file": rel(guide),
                      "probes_flagged_with_tools": [int(p.group(1)), int(p.group(2))],
                      "probes_flagged_without_tools": [int(p.group(3)), int(p.group(4))],
                      "stale_decree_named": [int(s.group(1)), int(s.group(2))],
                      "judge_model_alone": j.group(1), "judge_guarded_agent": j.group(2)}
    return f


def gather_pipeline_log():
    """Console lines of the last full 'vlonto.cli all' run, if its job log is still on disk.

    VLONTO_JOB_LOGS names a directory of <job>/stdout.log files; without it there is no pipeline log.
    """
    if not os.environ.get("VLONTO_JOB_LOGS"):
        return None
    jobs = Path(os.environ["VLONTO_JOB_LOGS"])
    best = None
    for log in sorted(glob.glob(str(jobs / "*" / "stdout.log"))):
        try:
            text = Path(log).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "== check-ontology" in text and "== build" in text and "done in" in text:
            mt = os.path.getmtime(log)
            if best is None or mt > best[0]:
                best = (mt, log, text)
    if best is None:
        return None
    lines = [l for l in best[2].splitlines()
             if l.startswith("== ") or l.startswith("done in") or l.startswith("ontology check pass")]
    return {"job": Path(best[1]).parent.name.split("-")[0], "lines": lines}


def gather_pins():
    pins = {}
    vl = read_text(REPO / "tools" / "versions.lock")
    pins["versions_lock"] = {m.group(1): m.group(2).strip().strip('"')
                             for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=(.*)$", vl, re.M)}
    req = read_text(REPO / "tools" / "requirements-web.lock")
    pins["web_env"] = dict(sorted(m.groups() for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==([^\s\\;]+)", req, re.M)))
    kg_pkgs = ["duckdb", "polars", "pyarrow", "pyoxigraph", "rdflib", "pyshacl", "owlrl", "pylode",
               "huggingface-hub", "igraph"]
    kg_env = {}
    for p in kg_pkgs:
        try:
            kg_env[p] = md.version(p)
        except md.PackageNotFoundError:   # not needed by the build (e.g. huggingface-hub: snapshots already on disk)
            pass
    # pyLODE: the release that wrote ontology/vlonto.html (it links its release page), which can differ from the
    # package installed here (pyLODE 3.6.1 needs Python >= 3.12; the v1 build ran it from a separate install)
    html = (REPO / "ontology" / "vlonto.html").read_text(encoding="utf-8")
    m = re.search(r"pyLODE/release/([0-9][0-9A-Za-z.]*)", html)
    if m:
        kg_env["pylode"] = m.group(1)
    pins["kg_env"] = kg_env
    pins["kg_python"] = sys.version.split()[0]
    import platform
    pins["platform"] = {"system": platform.system(), "machine": platform.machine()}
    rc, out, _ = run([str(V / "tools" / "typst" / "typst"), "--version"])
    pins["typst"] = out.strip()
    rc, out, _ = run([str(V / "envs" / "web" / "bin" / "pandoc"), "--version"])
    pins["pandoc"] = out.splitlines()[0].strip()
    fonts = []
    for p in sorted((REPO / "typst" / "fonts").glob("*.ttf")):
        fonts.append({"file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)})
    pins["typst_fonts"] = fonts
    vend = read_json(REPO / "tools" / "vendor.lock.json")
    entries = vend.get("files", vend) if isinstance(vend, dict) else vend
    pkgs = set()
    if isinstance(entries, list):
        for e in entries:
            if isinstance(e, dict) and e.get("package"):
                pkgs.add((e["package"], str(e.get("version", ""))))
    pins["vendor_packages"] = [{"package": a, "version": b} for a, b in sorted(pkgs)]
    pins["vendor_files"] = len(entries) if isinstance(entries, list) else None
    pins["lock_files"] = sorted(p.name for p in (REPO / "tools").iterdir()
                                if p.name.endswith((".lock", ".lock.json")))
    return pins


RELEASE = [("rdf/vlonto-kg.nt.gz", RDF / "vlonto-kg.nt.gz"), ("rdf/vlonto-core.ttl", RDF / "vlonto-core.ttl"),
           ("ontology/vlonto.ttl", REPO / "ontology" / "vlonto.ttl"),
           ("ontology/vlonto-shapes.ttl", REPO / "ontology" / "vlonto-shapes.ttl"),
           ("ontology/vlonto-context.jsonld", REPO / "ontology" / "vlonto-context.jsonld"),
           ("ontology/vlonto.html", REPO / "ontology" / "vlonto.html"),
           ("kg/data_dictionary.json", KG / "data_dictionary.json"),
           ("kg/data_dictionary.md", KG / "data_dictionary.md")]
# a code tarball of the build is listed only if the release step made one (the code itself is in the repository)
CODE_TARBALL = BUILD / "release" / f"vlonto-kg-code-{C.VERSION}.tar.gz"
if CODE_TARBALL.is_file():
    RELEASE.append((f"code/{CODE_TARBALL.name}", CODE_TARBALL))


def gather_checksums():
    files = list(RELEASE) + [(f"kg/{p.name}", p) for p in sorted(KG.glob("*.parquet"))]
    out = []
    for name, p in sorted(files):
        out.append({"path": name, "bytes": p.stat().st_size, "sha256": sha256(p)})
    return out


def gather_traces():
    """Counts of the website's question traces ($V/build/traces/index.json, one trace per most-asked article of each
    legal area), if the trace data is in the build folder; None otherwise. Counts only: no question or answer text."""
    p = BUILD / "traces" / "index.json"
    if not p.is_file():
        return None
    d = read_json(p)
    per_area = sorted({a["n_traces"] for a in d["areas"]})
    return {"areas": d["totals"]["areas"], "traces": d["totals"]["traces"],
            "traces_verified": d["totals"].get("traces_verified"), "per_area": per_area,
            "area_files": len(d["areas"])}


def summarize_json(path):
    d = read_json(path)
    s = {"bytes": path.stat().st_size, "keys": sorted(d.keys()) if isinstance(d, dict) else None}
    if isinstance(d, dict):
        s["lengths"] = {k: len(v) for k, v in d.items() if isinstance(v, (list, dict))}
        s["scalars"] = {k: v for k, v in d.items() if isinstance(v, (int, float, str)) and len(str(v)) < 80}
        for key in ("links", "edges"):
            if isinstance(d.get(key), list) and d[key] and isinstance(d[key][0], dict):
                kinds = {}
                for e in d[key]:
                    k = e.get("kind") or e.get("type") or e.get("rel")
                    kinds[str(k)] = kinds.get(str(k), 0) + 1
                s[f"{key}_by_kind"] = dict(sorted(kinds.items()))
        for key in ("fields", "edge_fields", "node_fields"):
            if isinstance(d.get(key), list):
                s[key] = d[key]
        if isinstance(d.get("edges"), dict):
            s["edges_by_kind"] = {k: len(v) for k, v in d["edges"].items() if isinstance(v, list)}
        for key in ("description", "subsetting", "layout", "notes", "counts", "modules"):
            v = d.get(key)
            if v is not None and len(json.dumps(v, ensure_ascii=False)) < 4000:
                s[key] = v
    return s


# ----------------------------------------------------------------------------- figures
def figure_data(facts, g):
    from rdflib import Literal, URIRef
    from rdflib.namespace import SKOS
    import polars as pl

    def pref_en(local):
        for o in g.objects(URIRef(C.VLO + local), SKOS.prefLabel):
            if isinstance(o, Literal) and o.language == "en":
                return str(o)
        return local

    st = facts["stats"]
    total = st["documents"]

    def share(n):
        p = 100 * n / total
        return "<0.1%" if p < 0.05 else f"{p:.1f}%"

    dt = pl.read_parquet(KG / "doc_types.parquet").sort(["n_documents", "doc_type_vi"], descending=[True, False])
    PROV[rel(KG / "doc_types.parquet")] = sha256(KG / "doc_types.parquet")
    doc_types = [{"label_vi": r["doc_type_vi"], "label_en": r["label_en"], "value": r["n_documents"],
                  "value_fmt": f"{r['n_documents']:,}", "pct_fmt": share(r["n_documents"])}
                 for r in dt.iter_rows(named=True)]
    val = sorted(st["validity"].items(), key=lambda kv: (-kv[1], kv[0]))
    vconcept = getattr(C, "VALIDITY_CONCEPT", {})
    validity = [{"key": k, "label_en": pref_en(vconcept.get(k, "")) if vconcept.get(k) else k.replace("_", " "),
                 "value": n, "value_fmt": f"{n:,}", "pct_fmt": share(n)} for k, n in val]
    kinds = ["replaced", "amended", "partially_repealed", "repealed", "partially_expired"]
    cconcept = getattr(C, "CHANGE_CONCEPT", {})
    y0 = 1995
    rows = facts["dashboard"]["changes_by_kind_year"]
    years = sorted({r["year"] for r in rows if r["year"] >= y0})
    series = {k: [sum(r["n"] for r in rows if r["kind"] == k and r["year"] == y) for y in years] for k in kinds}
    before = sum(r["n"] for r in rows if 0 < r["year"] < y0)
    unknown = sum(r["n"] for r in rows if r["year"] < 0)
    tot_year = [sum(series[k][i] for k in kinds) for i in range(len(years))]
    changes = {"years": years, "kinds": [{"key": k, "label_en": pref_en(cconcept[k]) if k in cconcept else k,
                                          "values": series[k]} for k in kinds],
               "max_total": max(tot_year), "before_first_year": before, "unknown_year": unknown,
               "first_year": years[0], "last_year": years[-1],
               "shown": sum(tot_year), "total": sum(r["n"] for r in rows)}
    mods = [{"label_en": m["label_en"], "notation": m["notation"],
             "classes": m["counts"]["class"], "object_properties": m["counts"]["object_property"],
             "datatype_properties": m["counts"]["datatype_property"],
             "other": m["counts"]["annotation_property"] + m["counts"]["concept_schemes"]}
            for m in facts["ontology"]["modules"]]
    # the source datasets of this build only (C.SOURCES: the court datasets are read only when the build includes them)
    # a build without court data (release v1) writes no court keys to stats.json; a v2 build writes them again
    by_src = st.get("court_decisions_by_source") or {}
    box = {
        "thuvienphapluat-vn-vbpl": ("vbpl", "legal documents", st["documents"], "documents in scope"),
        "thuvienphapluat-vn-hdpl": ("hdpl", "legal Q&A", st["legal_questions"], "Q&As"),
        "thuvienphapluat-vn-tnpl": ("tnpl", "legal terms", st["legal_terms"], "terms"),
        "thuvienphapluat-vn-htpl": ("htpl", "legal news", st["news_articles"], "news items"),
        "anle-toaan-gov-vn": ("anle", "precedents, decisions", by_src.get("anle", 0), "decisions"),
        "cbba-toaan-gov-vn": ("cbba", "court judgments", by_src.get("cbba", 0), "decisions"),
    }
    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}
    sources = [{"name": box[k][0], "what": box[k][1], "n": f"{box[k][2]:,}", "unit": box[k][3]} for k in C.SOURCES]
    arch = {
        "sources": sources,
        "sources_title": f"{words.get(len(sources), len(sources))} source datasets",
        "articles": f"{st['articles']:,}", "changes": f"{st['change_events']:,}",
        "tables": len([t for t in facts["data_dictionary"] if not t["local_only"]]),
        "triples": f"{st['rdf_triples']:,}", "core_triples": f"{st['core_ttl_triples']:,}",
        "checks": f"{sum(1 for c in facts['checks'] if c['result'] == 'pass')}/{len(facts['checks'])}",
    }
    return {"doc_types": doc_types, "validity": validity, "changes": changes, "modules": mods,
            "architecture": arch, "documents_total": f"{total:,}"}


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-report")
    ap.add_argument("--guide")
    ap.add_argument("--reuse-store", action="store_true", help="reuse work/vlonto-store if present")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    for name, target in (("kg", KG), ("rdf", RDF), ("ontology", REPO / "ontology")):
        link = WORK / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
    os.chdir(WORK)
    t0 = time.time()
    facts = gather_reports()
    onto, g = gather_ontology()
    facts["ontology"] = onto
    facts.update(gather_reports_external(a.data_report, a.guide))
    facts["pipeline_log"] = gather_pipeline_log()
    facts["pins"] = gather_pins()
    facts["checksums"] = gather_checksums()
    facts["site_bundles"] = {n: summarize_json(SITE / f"{n}.json")
                             for n in ("ontology_graph", "legal_network", "legal_network_lite")}
    facts["traces"] = gather_traces()
    facts["examples"] = gather_examples(a.reuse_store)
    from pyoxigraph import Store
    full = Store(str(WORK / "vlonto-store"))
    facts["recipes"] = gather_recipes(full)
    del full
    facts["config"] = {"version": C.VERSION, "release": getattr(C, "RELEASE", C.VERSION), "build_date": C.BUILD_DATE,
                       "validity_as_of": C.VALIDITY_AS_OF, "sources": C.SOURCES,
                       "courts_included": bool(getattr(C, "INCLUDE_COURTS", True)),
                       "deferred_sources": getattr(C, "DEFERRED_SOURCES", {}),
                       "namespace": C.VLO, "instance_base": C.ID,
                       "processed": {k: rel(v) for k, v in C.PROCESSED.items()}}
    figures = figure_data(facts, g)
    facts["provenance"] = dict(sorted(PROV.items()))
    subs = machine_subs()
    texts = {name: json.dumps(nfc(scrub(obj, subs)), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
             for name, obj in (("facts.json", facts), ("figures.json", figures))}
    left = {name: machine_leftovers(t) for name, t in texts.items() if machine_leftovers(t)}
    if left:
        raise SystemExit(f"gather_facts: machine-specific strings left after scrubbing: {left}")
    out = PB / "data"
    out.mkdir(parents=True, exist_ok=True)
    for name, t in texts.items():
        (out / name).write_text(t, encoding="utf-8")
    (out / "SHA256SUMS").write_text("".join(f"{c['sha256']}  {c['path']}\n" for c in facts["checksums"]),
                                    encoding="utf-8")
    (BUILD / "playbook" / "facts_timings.json").write_text(json.dumps(TIMINGS, indent=1, sort_keys=True) + "\n")
    print(f"facts.json {(out / 'facts.json').stat().st_size:,} bytes; figures.json; SHA256SUMS "
          f"({len(facts['checksums'])} files); {len(PROV)} inputs; {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

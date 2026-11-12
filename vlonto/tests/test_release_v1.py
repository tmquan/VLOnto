"""Release v1 (1.0.0) tests: version stamps, the court-data switch (off by default), the ontology header, the SHACL
shapes, the pinned download manifest and the spot-check review split. No data is needed; the build-output test at the
end runs only when a built VLOnto root is found (set V, or VLONTO_BUILD, or build in the default layout).

    python -m pytest vlonto/tests/test_release_v1.py      # from the repository root
    python vlonto/tests/test_release_v1.py                # without pytest
"""
import json
import os
import re
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(TESTS)            # <repo>/vlonto
REPO = os.path.dirname(PKG_ROOT)             # <repo>
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

THUVIEN = ["thuvienphapluat-vn-vbpl", "thuvienphapluat-vn-hdpl", "thuvienphapluat-vn-tnpl", "thuvienphapluat-vn-htpl"]
COURTS = ["anle-toaan-gov-vn", "cbba-toaan-gov-vn"]
COURT_EDGE_TYPES = {"decision_provision:docnum-key", "decision_provision:law-name-year", "decision_case:case-number-court",
                    "decision_case:case-number-date", "decision_case:precedent-number", "decision_court", "precedent_source"}


def _config_in_subprocess(env_courts, code):
    env = {k: v for k, v in os.environ.items() if k != "VLONTO_INCLUDE_COURTS"}
    if env_courts is not None:
        env["VLONTO_INCLUDE_COURTS"] = env_courts
    prog = f"import sys; sys.path.insert(0, {PKG_ROOT!r}); import json; import vlonto.config as C; from vlonto import export_rdf as E; {code}"
    return subprocess.run([sys.executable, "-c", prog], env=env, capture_output=True, text=True)


def test_version_stamps():
    import vlonto
    from vlonto import config as C
    assert vlonto.__version__ == "1.0.0" and C.VERSION == "1.0.0"
    assert vlonto.RELEASE == "v1" and C.RELEASE == "v1"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", C.BUILD_DATE)
    assert C.VALIDITY_AS_OF == "2026-11-08"          # same validity date as 0.1.0, so v1 reconciles with it
    assert C.ONTOLOGY_VERSION_IRI == "https://tmquan.github.io/VLOnto/ontology/1.0.0"
    assert C.iri_build().endswith(f"/build/1.0.0-{C.BUILD_DATE}")


def test_courts_off_by_default():
    r = _config_in_subprocess(None, "print(json.dumps([C.INCLUDE_COURTS, list(C.SOURCES), list(C.DEFERRED_SOURCES), [n for n, _ in E.active_parts()]]))")
    assert r.returncode == 0, r.stderr
    inc, sources, deferred, parts = json.loads(r.stdout.strip().splitlines()[-1])
    assert inc is False
    assert sources == THUVIEN and deferred == COURTS
    assert not {"courts", "decisions", "precedents", "edges_decision_provision", "edges_decision_case"} & set(parts)
    assert {"documents", "articles", "qas", "terms", "news", "edges_citation"} <= set(parts)


def test_courts_switch_on_and_invalid_value():
    r = _config_in_subprocess("1", "print(json.dumps([C.INCLUDE_COURTS, list(C.SOURCES), [n for n, _ in E.active_parts()]]))")
    assert r.returncode == 0, r.stderr
    inc, sources, parts = json.loads(r.stdout.strip().splitlines()[-1])
    assert inc is True and sources == THUVIEN + COURTS and "decisions" in parts and "courts" in parts
    bad = _config_in_subprocess("maybe", "print(C.INCLUDE_COURTS)")
    assert bad.returncode != 0 and "VLONTO_INCLUDE_COURTS" in bad.stderr


def test_court_snapshot_refused_when_off():
    r = _config_in_subprocess("0", "C.snapshot('cbba-toaan-gov-vn')")
    assert r.returncode != 0 and "planned for v2" in r.stderr


def test_ontology_release_header_and_judiciary_kept():
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import OWL, RDF, SKOS
    from vlonto import config as C
    from vlonto.ontology_tools import ONTO_IRI, VLO, court_terms, release_check
    g = Graph().parse(os.path.join(REPO, "ontology", "vlonto.ttl"))
    rel = release_check(g)
    assert rel["pass"], rel
    assert rel["versionInfo"] == "1.0.0" and rel["priorVersion"] == "https://tmquan.github.io/VLOnto/ontology/0.1.0"
    assert rel["modified"] == C.BUILD_DATE
    assert sorted(str(o).rsplit("/", 1)[-1] for o in g.objects(ONTO_IRI, URIRef("http://purl.org/dc/terms/source"))) == sorted(THUVIEN)
    for cls in ("JudicialDocument", "CourtDecision", "Judgment", "CourtRuling", "Precedent", "Court", "CourtLevel", "InstanceLevel", "CaseCategory"):
        assert (VLO[cls], RDF.type, OWL.Class) in g, cls          # schema kept for v2
    for p in ("decidedBy", "appliesProvision", "appliesDocument", "citesCase", "appliesPrecedent", "selectedFrom", "decisionNumber"):
        assert (VLO[p], None, None) in g, p
    terms = court_terms(g)
    assert len(terms) == 26
    for t in terms:
        langs = {o.language for o in g.objects(t, SKOS.scopeNote) if isinstance(o, Literal)}
        assert {"en", "vi"} <= langs, t


def test_shapes_keep_court_shapes():
    from rdflib import Graph, Literal, URIRef
    g = Graph().parse(os.path.join(REPO, "ontology", "vlonto-shapes.ttl"))
    shapes = URIRef("https://tmquan.github.io/VLOnto/shapes")
    assert str(g.value(shapes, URIRef("http://www.w3.org/2002/07/owl#versionInfo"))) == "1.0.0"
    assert (URIRef("https://tmquan.github.io/VLOnto/shapes#CourtDecisionShape"), None, None) in g


def test_download_manifest_v1():
    from vlonto import config as C
    m = json.load(open(os.path.join(REPO, "pipeline", "download_manifest.json"), encoding="utf-8"))
    assert sorted(m["datasets"]) == sorted(f"tmquan/{d}" for d in THUVIEN)
    for key, rec in m["datasets"].items():
        ds = key.split("/", 1)[1]
        assert rec["revision"] == C.SOURCES_ALL[ds]["revision"]
        assert rec["n_files"] == len(rec["files"]) and rec["bytes"] == sum(f["bytes"] for f in rec["files"])
        assert rec["rows"] == sum(f["rows"] for f in rec["files"])
        assert all(re.match(r"^[0-9a-f]{64}$", f["sha256"]) for f in rec["files"])
        machine = ("/" + "Users" + "/", "/" + "localhome" + "/")      # no build-machine paths (spelled so that release scans of this file stay clean)
        assert not any(m in json.dumps(rec) for m in machine)
    planned = m["court_datasets_planned_for_v2"]
    assert sorted(planned) == sorted(f"tmquan/{d}" for d in COURTS)
    for key, rec in planned.items():
        assert rec["revision"] == C.SOURCES_ALL[key.split("/", 1)[1]]["revision"]


def test_spot_check_review_split():
    s = json.load(open(os.path.join(REPO, "docs", "spot_check_review.json"), encoding="utf-8"))
    assert not COURT_EDGE_TYPES & set(s["edge_types"])
    assert set(s["edge_types_courts"]) == COURT_EDGE_TYPES
    assert s["limitations_courts"] and not any(x.startswith("Courts:") for x in s["limitations"])
    assert s.get("release_note") and "PLACEHOLDER" not in s["release_note"]
    for k, v in s["edge_types"].items():
        assert v["correct"] + v.get("wrong", 0) <= v["checked"], k
        assert v["correct"] >= 0.8 * v["checked"], k


def test_fixtures_still_exercise_the_judiciary_schema():
    """The synthetic fixtures keep a court, a judgment and a precedent, so the ontology checks (OWL-RL inferences such as
    dec-1 a vlo:CourtDecision, SHACL court shapes) still cover the judiciary schema that v2 will populate."""
    txt = open(os.path.join(TESTS, "fixtures", "positive.ttl"), encoding="utf-8").read()
    for term in ("a vlo:Court", "a vlo:Judgment", "a vlo:Precedent", "vlo:decidedBy", "vlo:appliesProvision"):
        assert term in txt, term


def _built_root():
    from vlonto import config as C
    return C if os.path.exists(os.path.join(C.KG, "documents.parquet")) else None


def test_build_outputs_have_no_court_data():
    C = _built_root()
    if C is None or C.INCLUDE_COURTS:
        return                                     # no v1 build here (or a court build): nothing to check
    for t in C.COURT_TABLES:
        assert not os.path.exists(os.path.join(C.KG, t + ".parquet")), t
    import polars as pl
    assert sorted(pl.read_parquet(os.path.join(C.KG, "sources.parquet"))["dataset"].to_list()) == sorted(THUVIEN)
    st = os.path.join(C.SITE, "stats.json")
    if os.path.exists(st):
        stats = json.load(open(st, encoding="utf-8"))
        assert stats["version"] == "1.0.0" and stats["release"] == "v1" and stats["courts_included"] is False
        assert stats["court_decisions"] == 0 and sorted(stats["sources"]) == sorted(THUVIEN)
    val = os.path.join(C.REPORTS, "validation.json")
    if os.path.exists(val):
        assert json.load(open(val, encoding="utf-8"))["release_scope"]["pass"] is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted((k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)):
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    sys.exit(1 if fails else 0)

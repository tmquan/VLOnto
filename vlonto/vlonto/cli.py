"""VLOnto build CLI.

    python -m vlonto.cli build            # step 3: KG parquet tables      -> $V/build/kg (+ kg_local)
    python -m vlonto.cli export           # step 4a: full N-Triples.gz     -> $V/build/rdf/vlonto-kg.nt.gz
    python -m vlonto.cli core             # step 4a: core Turtle subset    -> $V/build/rdf/vlonto-core.ttl
    python -m vlonto.cli validate         # step 4b: checks + kg_report.md -> $V/build/reports
    python -m vlonto.cli site             # step 5: stats, dashboard, ontology graph, legal network (+ .js twins)
    python -m vlonto.cli layout           # step 5: 3D legal-network layout only (re-runnable by the website track)
    python -m vlonto.cli check-ontology   # ontology checks (SHACL/OWL-RL fixtures) + pyLODE HTML + JSON-LD context
    python -m vlonto.cli report           # kg_report.md + checks.json from the JSON reports
    python -m vlonto.cli nfc              # Unicode NFC pass over the parquet tables and the ontology/docs text files
    python -m vlonto.cli nfc-check        # count non-NFC strings in every published output -> reports/nfc_check.json
    python -m vlonto.cli link-check       # no VLOnto Hugging Face link, no build-machine path/host in any output -> reports/link_check.json
    python -m vlonto.cli data-dictionary  # rewrite build/kg/data_dictionary.md/.json from the current tables (no rebuild)
    python -m vlonto.cli hf-dataset       # Hugging Face dataset folder (no upload) -> $V/build/release/hf_dataset
    python -m vlonto.cli all              # build, nfc, export, core, validate, site, check-ontology, nfc-check, link-check, report

Environment: R (processed corpus + HF cache), V (VLOnto root). Defaults: V = the directory that contains repo/,
R = <V>/../vnlegal (see config.py).
"""
import argparse
import json
import os
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vlonto", description="Build the VLOnto knowledge graph.")
    ap.add_argument("command", choices=["build", "nfc", "export", "core", "validate", "site", "layout", "check-ontology", "nfc-check",
                                        "link-check", "data-dictionary", "report", "hf-dataset", "all"])
    ap.add_argument("--nfc-out", default="nfc_check.json", help="report file name for nfc-check (in the reports directory)")
    ap.add_argument("--link-out", default="link_check.json", help="report file name for link-check (in the reports directory)")
    ap.add_argument("--no-article-text", action="store_true", help="do not write the local-only article text table")
    ap.add_argument("--with-article-text", action="store_true", help="also copy article text into the publishable articles table (licence decision)")
    ap.add_argument("--workers", type=int, default=17)
    ap.add_argument("--core-max-rank", type=int, default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    from . import config as C
    os.makedirs(C.REPORTS, exist_ok=True)
    cmds = (["build", "nfc", "export", "core", "validate", "site", "check-ontology", "nfc-check", "link-check", "report"]
            if a.command == "all" else [a.command])
    for cmd in cmds:
        print(f"== {cmd}", flush=True)
        if cmd == "build":
            from .kgbuild import build_all
            rep = build_all(with_text=not a.no_article_text)
            if a.with_article_text:
                import polars as pl
                arts = pl.read_parquet(os.path.join(C.KG, "articles.parquet"))
                txt = pl.read_parquet(os.path.join(C.KG_LOCAL, "article_text.parquet"))
                arts.join(txt, on="article_id", how="left").write_parquet(os.path.join(C.KG, "articles.parquet"), compression="zstd")
                print("article text added to the publishable articles table", flush=True)
        elif cmd == "export":
            from .export_rdf import export_all
            rep = export_all()
            print(json.dumps({k: v for k, v in rep.items() if k != "part_wall_s"}, indent=1), flush=True)
        elif cmd == "core":
            from .export_rdf import core_subset
            rep = core_subset(a.core_max_rank)
            print(json.dumps(rep, indent=1, default=str), flush=True)
        elif cmd == "validate":
            from .validate import validate_all
            validate_all()
        elif cmd == "site":
            from .site_data import build_site
            build_site()
        elif cmd == "layout":
            from .layout3d import main as layout_main
            layout_main([])
        elif cmd == "nfc":
            from .nfc import normalise_outputs
            r = normalise_outputs()
            print(json.dumps({"values_changed_total": r["values_changed_total"], "lines_changed_total": r["lines_changed_total"]}), flush=True)
        elif cmd == "nfc-check":
            from .nfc import check_outputs
            r = check_outputs(a.nfc_out)
            print(json.dumps({"files": r["n_files"], "total_non_nfc": r["total_non_nfc"], "pass": r["pass"],
                              "files_with_non_nfc": r["files_with_non_nfc"]}, ensure_ascii=False), flush=True)
        elif cmd == "link-check":
            from .linkcheck import check_links
            r = check_links(a.link_out)
            print(json.dumps({"files": r["n_files"], "totals": r["totals"], "pass": r["pass"],
                              "files_with_forbidden": r["files_with_forbidden"]}, ensure_ascii=False), flush=True)
        elif cmd == "data-dictionary":
            from .kgbuild import data_dictionary
            with open(os.path.join(C.REPORTS, "build_report.json"), encoding="utf-8") as f:
                data_dictionary(json.load(f))
            print(json.dumps({"written": [C.rel(os.path.join(C.KG, x)) for x in ("data_dictionary.md", "data_dictionary.json")]}), flush=True)
        elif cmd == "hf-dataset":
            from .hf_dataset import build_hf_dataset
            r = build_hf_dataset()
            print(json.dumps(r, ensure_ascii=False, indent=1), flush=True)
        elif cmd == "report":
            from .report import build_report
            print(json.dumps(build_report(), ensure_ascii=False, indent=1), flush=True)
        elif cmd == "check-ontology":
            from .ontology_tools import check_ontology
            r = check_ontology(C.REPO, C.REPORTS, os.path.join(C.BUILD, "ext", "eli.rdf"))
            print("ontology check pass:", r.get("pass"), flush=True)
    print(f"done in {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

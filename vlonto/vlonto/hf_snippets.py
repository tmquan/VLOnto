"""Run the loading snippets of the dataset card against the local folder, put their real output into README.md,
check the YAML front matter and Unicode NFC, and write SHA256SUMS.

Standalone (needs duckdb, datasets, pyoxigraph, pyyaml; not polars):
    python hf_snippets.py <hf_dataset folder> <scratch dir> <report.json> [previous report.json]

With a previous report, the stored snippet outputs are reused instead of running the snippets again (only when the data
files are unchanged; the caller checks that with the previous SHA256SUMS).
"""
import contextlib
import glob
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import time
import unicodedata

FOLDER, SCRATCH, REPORT = sys.argv[1], sys.argv[2], sys.argv[3]
REUSE = sys.argv[4] if len(sys.argv) > 4 else None
REPO_ID = "tmquan/VLOnto"
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")


def capture(fn):
    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue().rstrip("\n"), round(time.time() - t0, 1)


def snip_duckdb():
    import duckdb
    base = f"{FOLDER}/kg"
    print(duckdb.sql(f"""
    SELECT doc_type_vi, COUNT(*) AS n
    FROM '{base}/documents.parquet'
    GROUP BY doc_type_vi ORDER BY n DESC LIMIT 5"""))
    print(duckdb.sql(f"""
    SELECT c.court_kind, COUNT(*) AS decisions
    FROM '{base}/decisions.parquet' d JOIN '{base}/courts.parquet' c USING (court_id)
    GROUP BY c.court_kind ORDER BY decisions DESC"""))


def snip_datasets():
    from datasets import load_dataset
    courts = load_dataset(FOLDER, "courts", split="train", cache_dir=os.path.join(SCRATCH, "hf_cache"))
    print(courts)
    print(courts[0])


def snip_pyoxigraph():
    import pyoxigraph as ox
    path = os.path.join(FOLDER, "rdf", "vlonto-kg.nt.gz")
    store = ox.Store(os.path.join(SCRATCH, "vlonto-store"))
    with gzip.open(path, "rb") as f:
        store.bulk_load(f, ox.RdfFormat.N_TRIPLES)
    print(len(store), "triples")
    query = """PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?number ?date WHERE {
  ?old vlo:documentNumber "10/2012/QH13" .        # Labour Code 2012
  ?change vlo:affectedDocument ?old ; vlo:changeKind vlo:change-replaced ; vlo:actingDocument ?new .
  OPTIONAL { ?change vlo:changeEffectiveDate ?date }
  ?new vlo:documentNumber ?number .
}"""
    for row in store.query(query):
        print("replaced by", row["number"].value, "effective", row["date"].value if row["date"] else "-")


def main():
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH)
    os.makedirs(SCRATCH)
    rep = {"snippets": {}, "reused_from": REUSE}
    readme_path = os.path.join(FOLDER, "README.md")
    readme = open(readme_path, encoding="utf-8").read()
    prev = json.load(open(REUSE, encoding="utf-8"))["snippets"] if REUSE else {}
    for name, fn in (("duckdb", snip_duckdb), ("datasets", snip_datasets), ("pyoxigraph", snip_pyoxigraph)):
        if REUSE:
            out, secs, err = prev[name]["output"], prev[name]["seconds"], prev[name]["error"]
        else:
            try:
                out, secs = capture(fn)
                err = None
            except Exception as e:  # keep going; the error is reported and the placeholder stays
                out, secs, err = "", None, f"{type(e).__name__}: {e}"
        rep["snippets"][name] = {"output": out, "seconds": secs, "error": err, "reused": bool(REUSE)}
        print(f"== {name} ({secs}s) error={err}\n{out}\n", flush=True)
        if err is None:
            block = "Output:\n\n```text\n" + out + "\n```"
            readme = readme.replace(f"<!-- OUTPUT:{name} -->", block)
    readme = unicodedata.normalize("NFC", readme)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    rep["placeholders_left"] = readme.count("<!-- OUTPUT:")
    # YAML front matter
    import yaml
    front = readme.split("---", 2)[1]
    meta = yaml.safe_load(front)
    rep["yaml"] = {"pretty_name": meta.get("pretty_name"), "license": meta.get("license"), "language": meta.get("language"),
                   "tags": meta.get("tags"), "size_categories": meta.get("size_categories"), "n_configs": len(meta.get("configs", [])),
                   "default_config": [c["config_name"] for c in meta.get("configs", []) if c.get("default")],
                   "configs_missing_file": [c["config_name"] for c in meta.get("configs", [])
                                            if not os.path.exists(os.path.join(FOLDER, c["data_files"][0]["path"]))]}
    # NFC of every text file in the folder
    bad = {}
    for p in glob.glob(os.path.join(FOLDER, "**", "*"), recursive=True):
        if os.path.isfile(p) and p.endswith((".md", ".json", ".jsonld", ".ttl", ".html")):
            n = sum(1 for line in open(p, encoding="utf-8") if not line.isascii() and not unicodedata.is_normalized("NFC", line))
            if n:
                bad[os.path.relpath(p, FOLDER)] = n
    rep["text_files_with_non_nfc_lines"] = bad
    # checksums, sizes
    files = sorted(os.path.relpath(p, FOLDER) for p in glob.glob(os.path.join(FOLDER, "**", "*"), recursive=True)
                   if os.path.isfile(p) and os.path.basename(p) != "SHA256SUMS")
    lines = []
    for rel in files:
        h = hashlib.sha256()
        with open(os.path.join(FOLDER, rel), "rb") as f:
            for b in iter(lambda: f.read(1 << 24), b""):
                h.update(b)
        lines.append(f"{h.hexdigest()}  {rel}")
    with open(os.path.join(FOLDER, "SHA256SUMS"), "w") as f:
        f.write("\n".join(lines) + "\n")
    allf = files + ["SHA256SUMS"]
    rep["files"] = [{"file": rel, "bytes": os.path.getsize(os.path.join(FOLDER, rel))} for rel in allf]
    rep["n_files"] = len(allf)
    rep["total_bytes"] = sum(x["bytes"] for x in rep["files"])
    rep["sha256"] = {ln.split("  ", 1)[1]: ln.split("  ", 1)[0] for ln in lines}
    rep["readme_sha256"] = rep["sha256"].get("README.md")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("snippets", "files", "sha256")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

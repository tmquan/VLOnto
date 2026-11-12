"""Unicode NFC for every publishable output.

normalise_outputs()  rewrites the publishable parquet tables (string, list and struct columns) and the ontology, docs
                     and data-dictionary text files in NFC and reports how many values / lines changed per file.
check_outputs()      counts strings that are not NFC in every published output (parquet values, JSON values, text
                     lines) and records bytes and sha256 per file; writes reports/nfc_check.json (or another name).

The writers (kgbuild.write, export_rdf, site_data.dump, layout3d, report, ontology_tools) apply NFC as well, so a fresh
build is NFC by construction; these two functions are the explicit pass over existing files and the check.
"""
import glob
import gzip
import hashlib
import json
import os
import time
import unicodedata

import polars as pl

from . import config as C

FORM = "NFC"


def nfc(s):
    return unicodedata.normalize(FORM, s) if isinstance(s, str) and not unicodedata.is_normalized(FORM, s) else s


def nfc_obj(o):
    """Normalise every string (dict keys included) in a JSON-like object."""
    if isinstance(o, str):
        return nfc(o)
    if isinstance(o, dict):
        return {nfc(k): nfc_obj(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [nfc_obj(x) for x in o]
    return o


def count_obj(o):
    """Number of strings (dict keys included) that are not NFC."""
    if isinstance(o, str):
        return 0 if o.isascii() or unicodedata.is_normalized(FORM, o) else 1
    if isinstance(o, dict):
        return sum(count_obj(k) + count_obj(v) for k, v in o.items())
    if isinstance(o, (list, tuple)):
        return sum(count_obj(x) for x in o)
    return 0


def str_normalize(expr):
    """Polars expression (or Series) normalised to NFC; falls back to a Python map on old Polars versions."""
    try:
        return expr.str.normalize(FORM)
    except AttributeError:
        if isinstance(expr, pl.Series):
            return expr.map_elements(nfc, return_dtype=pl.String)
        return expr.map_elements(nfc, return_dtype=pl.String)


def _has_str(dt):
    if dt == pl.String:
        return True
    if isinstance(dt, (pl.List, pl.Array)):
        return _has_str(dt.inner)
    if isinstance(dt, pl.Struct):
        return any(_has_str(f.dtype) for f in dt.fields)
    return False


def _leaf_values(v):
    """Struct values come back as dicts: count only their values, not the field names."""
    if isinstance(v, dict):
        return sum(_leaf_values(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return sum(_leaf_values(x) for x in v)
    return count_obj(v) if isinstance(v, str) else 0


def _nfc_values(v):
    if isinstance(v, dict):
        return {k: _nfc_values(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_nfc_values(x) for x in v]
    return nfc(v)


def scan_df(df):
    """{column: number of non-NFC string values} for one table."""
    out = {}
    for name, dt in df.schema.items():
        if not _has_str(dt):
            continue
        if dt == pl.String:
            n = df.select((pl.col(name) != str_normalize(pl.col(name))).sum()).item() or 0
        else:
            n = sum(_leaf_values(v) for v in df[name].to_list())
        if n:
            out[name] = int(n)
    return out


def nfc_df(df):
    """(table with every string normalised to NFC, {column: values changed})."""
    counts = scan_df(df)
    if counts:
        cols = []
        for name in counts:
            dt = df.schema[name]
            if dt == pl.String:
                cols.append(str_normalize(pl.col(name)).alias(name))
            else:
                cols.append(pl.Series(name, [_nfc_values(v) for v in df[name].to_list()], dtype=dt))
        df = df.with_columns(cols)
    return df, counts


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def _text_lines_non_nfc(path):
    opener = gzip.open if path.endswith(".gz") else open
    n = 0
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.isascii() and not unicodedata.is_normalized(FORM, line):
                n += 1
    return n


def _js_payload(text):
    """The JSON value assigned by a js twin: 'window.VLONTO = ...;\\nwindow.VLONTO["name"] = <json>;'."""
    head = text.index("] = ") + 4
    return json.loads(text[head:].rstrip().rstrip(";"))


def published_files():
    """(relative label, absolute path, kind) for every publishable output of the KG track."""
    out = []
    for p in sorted(glob.glob(os.path.join(C.KG, "*.parquet"))):
        out.append((f"kg/{os.path.basename(p)}", p, "parquet"))
    for fn in ("vlonto-kg.nt.gz", "vlonto-core.ttl"):
        out.append((f"rdf/{fn}", os.path.join(C.RDF_DIR, fn), "text"))
    for p in sorted(glob.glob(os.path.join(C.SITE, "*.json"))):
        out.append((f"site_data/{os.path.basename(p)}", p, "json"))
    for p in sorted(glob.glob(os.path.join(C.SITE, "js", "*.js"))):
        out.append((f"site_data/js/{os.path.basename(p)}", p, "js"))
    for fn, kind in (("vlonto.ttl", "text"), ("vlonto-shapes.ttl", "text"), ("vlonto-context.jsonld", "json"), ("vlonto.html", "text")):
        out.append((f"ontology/{fn}", os.path.join(C.REPO, "ontology", fn), kind))
    for fn, kind in (("licence_policy.md", "text"), ("spot_check_review.json", "json")):
        out.append((f"docs/{fn}", os.path.join(C.REPO, "docs", fn), kind))
    for fn, kind in (("data_dictionary.md", "text"), ("data_dictionary.json", "json")):
        out.append((f"docs/{fn}", os.path.join(C.KG, fn), kind))
    return [x for x in out if os.path.exists(x[1])]


def check_outputs(name="nfc_check.json"):
    t0 = time.time()
    files = {}
    for label, path, kind in published_files():
        if kind == "parquet":
            cols = scan_df(pl.read_parquet(path))
            n, unit, extra = sum(cols.values()), "string values", {"columns": cols}
        elif kind == "json":
            n, unit, extra = count_obj(json.load(open(path, encoding="utf-8"))), "string values", {}
        elif kind == "js":
            n, unit, extra = count_obj(_js_payload(open(path, encoding="utf-8").read())), "string values", {}
        else:
            n, unit, extra = _text_lines_non_nfc(path), "lines", {}
        files[label] = {"path": C.rel(path), "non_nfc": int(n), "unit": unit, "bytes": os.path.getsize(path), "sha256": _sha256(path), **extra}
        print(f"  {label}: {n} non-NFC {unit}", flush=True)
    rep = {"form": FORM, "files": files, "n_files": len(files), "total_non_nfc": sum(f["non_nfc"] for f in files.values()),
           "files_with_non_nfc": [k for k, f in files.items() if f["non_nfc"]], "wall_s": round(time.time() - t0, 1)}
    rep["pass"] = rep["total_non_nfc"] == 0
    with open(os.path.join(C.REPORTS, name), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return rep


def normalise_outputs():
    """NFC pass over the existing parquet tables and the hand-written / generated text files."""
    t0 = time.time()
    rep = {"form": FORM, "tables": {}, "text_files": {}}
    for p in sorted(glob.glob(os.path.join(C.KG, "*.parquet"))):
        df = pl.read_parquet(p)
        h = df.height
        df, counts = nfc_df(df)
        if counts:
            assert df.height == h
            df.write_parquet(p, compression="zstd")
        rep["tables"][os.path.basename(p)] = {"rows": h, "values_changed": int(sum(counts.values())), "columns": counts}
        print(f"  {os.path.basename(p)}: {sum(counts.values())} values changed {counts}", flush=True)
    texts = [os.path.join(C.REPO, "ontology", f) for f in ("vlonto.ttl", "vlonto-shapes.ttl", "vlonto-context.jsonld", "vlonto.html")]
    texts += [os.path.join(C.REPO, "docs", f) for f in ("licence_policy.md", "spot_check_review.json")]
    texts += [os.path.join(C.KG, f) for f in ("data_dictionary.md", "data_dictionary.json")]
    for p in texts:
        if not os.path.exists(p):
            continue
        s = open(p, encoding="utf-8").read()
        n = sum(1 for line in s.splitlines() if not line.isascii() and not unicodedata.is_normalized(FORM, line))
        if n:
            with open(p, "w", encoding="utf-8") as f:
                f.write(unicodedata.normalize(FORM, s))
        rep["text_files"][os.path.relpath(p, C.V) if hasattr(C, "V") else p] = {"lines_changed": n}
        print(f"  {p}: {n} lines changed", flush=True)
    rep["values_changed_total"] = sum(t["values_changed"] for t in rep["tables"].values())
    rep["lines_changed_total"] = sum(t["lines_changed"] for t in rep["text_files"].values())
    rep["wall_s"] = round(time.time() - t0, 1)
    with open(os.path.join(C.REPORTS, "nfc_normalise.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return rep

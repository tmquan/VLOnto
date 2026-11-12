"""Scan every publishable output for links to resources that do not exist and for build-machine details
-> reports/link_check.json.

The release lives in the GitHub repository (https://github.com/tmquan/VLOnto) and on the website
(https://tmquan.github.io/VLOnto/). There is no VLOnto dataset or Space on Hugging Face (one was created and then
deleted on 2026-11-12), so no output may link to huggingface.co/datasets/tmquan/VLOnto or to a Space, and no text may
call anything a VLOnto "dataset card". Links to the six source datasets (huggingface.co/datasets/tmquan/<source>) are
expected; they are counted as information, together with links to the GitHub repository and the paper.
Published text must not carry absolute build-machine paths or host names either (paths are written relative to the
VLOnto root, e.g. build/kg); the path patterns below are written so that this source file does not match them.

Scanned: the 53 outputs of nfc.published_files() plus reports/kg_report.md and reports/checks.json when present.
"""
import gzip
import json
import os
import re
import time

import polars as pl

from . import config as C
from .nfc import _has_str, published_files

# patterns that must not occur (Python re and the Rust regex used by polars accept the same syntax here)
FORBIDDEN = {
    "hf_vlonto_dataset": r"(?i)(huggingface\.co|hf\.co)/datasets/tmquan/vlonto",
    "hf_space": r"(?i)(huggingface\.co|hf\.co)/spaces([^\w]|$)",
    "spaces_path": r"(?i)(^|[^\w])spaces/",
    "dataset_card_wording": r"(?i)dataset card",
}
FORBIDDEN_PATHS = {
    "node_home_path": r"/localhom[e]",
    "node_host_name": r"(?i)umb-b30[0]",
    "mac_home_path": r"/User[s]/[A-Za-z0-9._-]+/",
}
FORBIDDEN_LINKS = dict(FORBIDDEN)
FORBIDDEN = {**FORBIDDEN_LINKS, **FORBIDDEN_PATHS}
# information only
EXPECTED = {
    "source_dataset_links": r"(?i)huggingface\.co/datasets/tmquan/(thuvienphapluat-vn-(vbpl|hdpl|tnpl|htpl)|anle-toaan-gov-vn|cbba-toaan-gov-vn)",
    "github_repo_links": r"(?i)github\.com/tmquan/vlonto",
    "paper_links": r"arxiv\.org/abs/2611\.11426",
}
ALL = {**FORBIDDEN, **EXPECTED}
_RX = {k: re.compile(v) for k, v in ALL.items()}
_PREFILTER = ("huggingface", "hf.co", "spaces/", "card", "github.com", "arxiv.org", "localhom", "umb-b30", "/users/")
_PREFILTER_RX = r"(?i)huggingface|hf\.co|spaces/|card|github\.com|arxiv\.org|localhom|umb-b30|/users/"


def _scan_lines(lines):
    """({pattern: occurrences}, {pattern: [examples]}) over an iterable of (line number, text)."""
    counts, examples = {k: 0 for k in ALL}, {k: [] for k in FORBIDDEN}
    for no, line in lines:
        low = line.lower()
        if not any(p in low for p in _PREFILTER):
            continue
        for k, rx in _RX.items():
            for m in rx.finditer(line):
                counts[k] += 1
                if k in examples and len(examples[k]) < 3:
                    a = max(0, m.start() - 70)
                    examples[k].append({"line": no, "text": line[a:m.end() + 70].strip()})
    return counts, examples


def _scan_text(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return _scan_lines(enumerate(f, 1))


def _scan_parquet(path):
    """Counts are matching values (rows x columns); nested string columns are scanned as JSON text."""
    df = pl.read_parquet(path)
    counts, examples, cols = {k: 0 for k in ALL}, {k: [] for k in FORBIDDEN}, {}
    for name, dt in df.schema.items():
        if not _has_str(dt):
            continue
        if dt == pl.String:
            s = df[name]
        else:
            s = pl.Series(name, [json.dumps(v, ensure_ascii=False) if v is not None else None for v in df[name].to_list()],
                          dtype=pl.String)
        s = s.filter(s.str.contains(_PREFILTER_RX).fill_null(False))
        if s.len() == 0:
            continue
        for k, pat in ALL.items():
            hit = s.str.contains(pat).fill_null(False)
            n = int(hit.sum())
            if n:
                counts[k] += n
                cols.setdefault(name, {})[k] = n
                if k in examples:
                    for v in s.filter(hit).head(3 - len(examples[k])).to_list():
                        m = re.search(pat, v)
                        if m is None:
                            continue
                        a = max(0, m.start() - 70)
                        examples[k].append({"column": name, "text": v[a:m.end() + 70].strip()})
    return counts, examples, cols


def files_to_scan():
    out = [(label, path, kind) for label, path, kind in published_files()]
    for fn in ("kg_report.md", "checks.json"):
        p = os.path.join(C.REPORTS, fn)
        if os.path.exists(p):
            out.append((f"reports/{fn}", p, "text"))
    return out


def check_links(name="link_check.json"):
    t0 = time.time()
    files = {}
    for label, path, kind in files_to_scan():
        if kind == "parquet":
            counts, examples, cols = _scan_parquet(path)
            rec = {"unit": "string values", "counts": counts, "columns": cols}
        else:
            counts, examples = _scan_text(path)
            rec = {"unit": "occurrences", "counts": counts}
        rec["examples"] = {k: v for k, v in examples.items() if v}
        files[label] = rec
        bad = {k: counts[k] for k in FORBIDDEN if counts[k]}
        if bad:
            print(f"  {label}: {bad}", flush=True)
    totals = {k: sum(f["counts"][k] for f in files.values()) for k in ALL}
    rep = {"patterns": ALL, "forbidden": list(FORBIDDEN), "files": files, "n_files": len(files), "totals": totals,
           "files_with_forbidden": sorted(lbl for lbl, f in files.items() if any(f["counts"][k] for k in FORBIDDEN)),
           "wall_s": round(time.time() - t0, 1)}
    rep["pass_links"] = all(totals[k] == 0 for k in FORBIDDEN_LINKS)
    rep["pass_paths"] = all(totals[k] == 0 for k in FORBIDDEN_PATHS)
    rep["files_with_forbidden_links"] = sorted(lbl for lbl, f in files.items() if any(f["counts"][k] for k in FORBIDDEN_LINKS))
    rep["files_with_forbidden_paths"] = sorted(lbl for lbl, f in files.items() if any(f["counts"][k] for k in FORBIDDEN_PATHS))
    rep["pass"] = rep["pass_links"] and rep["pass_paths"]
    with open(os.path.join(C.REPORTS, name), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return rep

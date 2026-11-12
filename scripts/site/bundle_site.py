#!/usr/bin/env python3
"""bundle_site.py - zip site/ as VLOnto_site/ with README_OFFLINE.txt for offline review (deterministic zip, stdlib only).

    $W/python scripts/site/bundle_site.py --site site --out $V/build/site_bundle/VLOnto_site.zip [--report site_test_report.json]
Writes the zip, <zip>.sha256 and bundle.json (bytes, sha256, file count).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

DATE = (2026, 11, 11, 0, 0, 0)

README = """VLOnto website - offline review copy
====================================

VLOnto {version}: ontology and knowledge graph of Vietnamese law. Site built {build_date}; validity of documents
derived as of {asof}. {nfiles} files, {mb:.1f} MB.

How to open
-----------
1. Unzip VLOnto_site.zip anywhere, for example into ~/Documents/VLOnto_local/.
2. Double-click VLOnto_site/index.html (the 3D ontology playground, the start page). No server, no internet
   connection and no browser setting is needed; every page also works over http:// (for example on GitHub Pages).
3. Pages:
     index.html          3D ontology playground (classes, properties, schemes, alignments, SPARQL CONSTRUCT in 3D;
                         the paper and its BibTeX in the side panel)
     network-3d.html     3D legal network (40,816 documents by legal force; search e.g. 45/2019/QH14)
     sparql.html         SPARQL playground (Oxigraph WebAssembly, 10 bilingual examples, CSV export)
     dashboard.html      dashboard with linked filters
     ontology.html       ontology modules and the pyLODE reference documentation
     playbook.html       playbook (rendered from the playbook Markdown; PDF and Markdown downloads)
     downloads.html      every downloadable file with size and sha256; how to rebuild the full graph
     about.html          what VLOnto is, headline numbers of this release, the paper (BibTeX), how to cite, licences
     ontology-3d.html    old address of the playground; forwards to index.html (keeps #links working)
4. Light and dark theme: the sun/moon button in the header switches every page; the first visit follows the
   system setting. The choice is remembered (in this browser; when pages are opened from files it also travels on
   the links between pages, because some browsers keep file storage per file).
5. Paper: Bui and Tran Minh (2026), "Vietnamese Legal Ontology: Every legal answer, traced to the article that
   grounds it", arXiv:2611.11426 (https://arxiv.org/abs/2611.11426). Numbers on these pages are computed from the
   VLOnto release in this bundle and can differ from the paper's.

Tested
------
- Headless Chromium 157 (chrome-headless-shell 157.0.8103.50, Linux): every page opened as file:// and over http://,
  at 1440x900 and 390x844 (render checks, interaction tests and frame rates in site_test_report.md).
- WebGL was software-rendered (SwiftShader) during the tests; laptop GPUs are much faster.
- Not machine-tested: Safari and Firefox. The pages follow the rules that make file:// work in those browsers
  (classic scripts only, no fetch/XHR, data shipped as .js files, fonts embedded as data URIs, WebAssembly
  instantiated from bytes). Please open index.html and about.html in Chrome, Safari and Firefox before publishing.

Notes
-----
- On wide screens the 3D legal network loads all 40,816 documents (about 10 MB); phones start with a 6,000-document subset.
- No page loads anything from the internet. External links (sources on thuvienphapluat.vn, the six source datasets
  on Hugging Face, the paper on arXiv, the code on GitHub, licences) open only when clicked.
- VLOnto is not an official legal text and is not legal advice. Relations and validity are extracted automatically
  and may be wrong; read documents at their official source.
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    site = a.site.resolve()
    files = sorted(p for p in site.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(site).parts))
    total = sum(p.stat().st_size for p in files)
    stats = {}
    mj = site / "data" / "site_meta.js"
    prefix = '(window.VLONTO = window.VLONTO || {})["site_meta"] = '
    if mj.exists():
        txt = mj.read_text(encoding="utf-8").strip()
        if txt.startswith(prefix):
            stats = json.loads(txt[len(prefix):].rstrip(";"))
    if not stats.get("version"):
        sj = site / "downloads" / "data" / "stats.json"
        if sj.exists():
            stats = json.loads(sj.read_text(encoding="utf-8"))
    readme = README.format(version=stats.get("version") or "0.1.0", build_date=stats.get("build_date") or "", asof=stats.get("validity_as_of") or "",
                           nfiles=len(files) + 1, mb=total / 1048576)
    if not (site / "data" / "playbook_html.js").exists():
        readme = readme.replace("playbook (rendered from the playbook Markdown; PDF and Markdown downloads)", "playbook (placeholder: the playbook was not built yet)")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        def add(name: str, data: bytes):
            zi = zipfile.ZipInfo("VLOnto_site/" + name, date_time=DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
        add("README_OFFLINE.txt", readme.encode("utf-8"))
        for p in files:
            add(p.relative_to(site).as_posix(), p.read_bytes())
    tmp.replace(a.out)
    digest = sha256(a.out)
    (a.out.parent / (a.out.name + ".sha256")).write_text(f"{digest}  {a.out.name}\n", encoding="utf-8")
    (a.out.parent / "README_OFFLINE.txt").write_text(readme, encoding="utf-8")
    rep = {"path": a.out.name, "bytes": a.out.stat().st_size, "sha256": digest, "files": len(files) + 1, "site_bytes": total,
           "largest": sorted(({"path": p.relative_to(site).as_posix(), "bytes": p.stat().st_size} for p in files), key=lambda x: -x["bytes"])[:5]}
    (a.out.parent / "bundle.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

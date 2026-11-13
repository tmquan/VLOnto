#!/usr/bin/env python3
"""build_site.py - assemble the VLOnto static site in site/ (stdlib only; run from the repo root on the node).

    $W/python scripts/site/build_site.py --root $V --site site

Steps (idempotent; re-run after the KG or Playbook tracks change their outputs):
  1. data twins: copy $V/build/site_data/js/*.js to site/data/ (sha256 checked against the KG track's manifest.json)
  2. website data: convert $V/build/site_extra/*.json (derive_site_data.py) to site/data/*.js with tools/json2js.py
     question traces (traces.html): $V/build/traces/{index.json,<area>.json} (scripts/traces/) -> site/data/traces/*.js
     (index, graph.js = the 3D embedding of all traces, one file per area)
     with the build-time drawings (scripts/site/trace_site.py, trace_layout.py); without build/traces/index.json the
     page gets an index that says "no trace data in this build"
  3. downloads: ontology files, the core Turtle subset, the site JSON bundles, the data dictionary, the licence policy,
     ATTRIBUTION.txt, copies of repo/playbook/figures/*.svg in downloads/figures/ (playbook.md links them; the build
     fails if a linked figure is missing) and SHA256SUMS.txt (regenerated from every file in downloads/ on each run)
     under site/downloads/ (the Playbook track's files there are never touched)
  4. pyLODE documentation: site/ontology/vlonto.html = ontology/vlonto.html + viewport, web fonts and site styles
  5. site/data/site_files.js (every file of the site with bytes + sha256) and the static downloads.html
  6. checks: every file <= 50 MB, whole site <= 150 MB, text files are NFC, no file from build/kg_local
Never writes data/playbook_html.js, downloads/VLOnto-playbook.pdf or downloads/playbook.md (Playbook track).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
from pathlib import Path

PLAYBOOK_FILES = {"data/playbook_html.js", "downloads/VLOnto-playbook.pdf", "downloads/playbook.md"}
# The full graph is not published as a dataset: it is rebuilt from the source datasets with the code on GitHub.
# Release v1 reads the four thuvienphapluat.vn datasets; the court datasets (anle-, cbba-toaan-gov-vn) join in v2.
SOURCE_DATASETS = ["thuvienphapluat-vn-vbpl", "thuvienphapluat-vn-hdpl", "thuvienphapluat-vn-tnpl", "thuvienphapluat-vn-htpl"]
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
HF_SOURCE = "https://huggingface.co/datasets/tmquan/"
REPO_URL = "https://github.com/tmquan/VLOnto"
SITE_URL = "https://tmquan.github.io/VLOnto/"
TWINS = ["stats", "dashboard", "ontology_graph", "legal_network", "legal_network_lite", "sparql_examples", "manifest",
         "vlonto_core_ttl", "vlonto_ontology_ttl"]
MAX_FILE = 50 * 1024 * 1024
MAX_SITE = 150 * 1024 * 1024
TEXT_EXT = {".html", ".css", ".js", ".json", ".ttl", ".jsonld", ".md", ".txt"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return str(n)


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def site_version(site: Path | None = None) -> str:
    """The machine-readable release version: VL.VERSION in site/js/common.js, the one place the site sets it."""
    js = (site or Path(__file__).resolve().parents[2] / "site") / "js" / "common.js"
    m = re.search(r"VL\.VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'", js.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"cannot find VL.VERSION in {js}")
    return m.group(1)


def release_label(version: str | None = None) -> str:
    """The release as the site names it: 'VLOnto v1' for every 1.x.y (the rule of VL.releaseLabel in common.js)."""
    return "VLOnto v" + (version or site_version()).split(".")[0]


def attribution_texts(policy_md: str):
    """Section 4 of docs/licence_policy.md: the English and Vietnamese attribution paragraphs (block quotes)."""
    sec = policy_md.split("## 4.", 1)[1]
    quotes = re.findall(r"^> (.+)$", sec, re.M)
    if len(quotes) < 2:
        raise SystemExit("cannot find the two attribution block quotes in licence_policy.md section 4")
    clean = lambda s: unicodedata.normalize("NFC", s.replace("`", "").strip())
    return clean(quotes[0]), clean(quotes[1])


# Sets html[data-theme] before first paint: ?theme=light|dark, else the stored choice, else the system setting.
# The same line is in the <head> of every page of the site (checked by check_theme_head); js/common.js and
# js/doc-theme.js do the live switching.
THEME_HEAD = ("<script>/* theme before first paint: ?theme=, else stored choice, else system (css/site.css, js/common.js) */"
              "(function(d,w){var t=null,m=/[?&]theme=(light|dark)(?:&|$)/.exec(w.location.search);if(m)t=m[1];"
              "else{try{t=w.localStorage.getItem('vlonto.theme')}catch(e){}if(t!=='light'&&t!=='dark'){try{"
              "t=w.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}catch(e){t='light'}}}"
              "d.setAttribute('data-theme',t);d.style.colorScheme=t})(document.documentElement,window);</script>")

# The language layer (docs/i18n.md): js/i18n.js right after the theme line in the <head> of every page sets html[lang]
# and html[data-lang] (EN / VI / EN-VI) before first paint; the dictionaries are the first scripts at the end of <body>.
# The pyLODE reference loads it with data-doc-lang="en": the document stays English, its bar follows the mode.
I18N_HEAD = '<script src="js/i18n.js"></script>'
I18N_DOC_HEAD = '<script src="../js/i18n.js" data-doc-lang="en"></script>'
I18N_BODY = '<script src="js/i18n-3d.js"></script>\n<script src="js/i18n-pages.js"></script>'

# The paper (cite by title, authors, arXiv link and BibTeX only; numbers on the site are from this release).
PAPER_URL = "https://arxiv.org/abs/2611.11426"
PAPER_CITE = "Cite: Bui &amp; Tran Minh (2026), arXiv:2611.11426"


def check_lang_head(site: Path):
    """Every HTML page loads the language layer (docs/i18n.md): js/i18n.js once, right after the theme line, and the two
    dictionaries as the first scripts at the end of <body>; the redirect stub ontology-3d.html loads i18n.js and
    i18n-pages.js in its <head> only (it replaces itself while loading); the pyLODE reference loads i18n.js with
    data-doc-lang="en"."""
    bad = []
    pages = sorted(site.glob("*.html"))
    for p in pages:
        t = p.read_text(encoding="utf-8")
        ok = t.count(I18N_HEAD) == 1 and t.find(THEME_HEAD) + len(THEME_HEAD) + 1 == t.find(I18N_HEAD)
        if p.name == "ontology-3d.html":
            ok = ok and t.count('<script src="js/i18n-pages.js"></script>') == 1 and "i18n-3d.js" not in t
        else:
            body = t[t.find("<body"):]
            first = re.search(r'<script src="([^"]+)"', body)
            ok = ok and t.count(I18N_BODY) == 1 and first is not None and first.group(1) == "js/i18n-3d.js"
        if not ok:
            bad.append(p.relative_to(site).as_posix())
    docs = sorted((site / "ontology").glob("*.html"))
    bad += [p.relative_to(site).as_posix() for p in docs if p.read_text(encoding="utf-8").count(I18N_DOC_HEAD) != 1]
    if bad:
        raise SystemExit(f"pages without the language layer (js/i18n.js in <head>, dictionaries first in <body>): {bad}")
    return len(pages) + len(docs)


def check_theme_head(site: Path):
    """Every HTML page of the site sets the theme before first paint with the same inline script."""
    pages = sorted(site.glob("*.html")) + sorted((site / "ontology").glob("*.html"))
    bad = [p.relative_to(site).as_posix() for p in pages if p.read_text(encoding="utf-8").count(THEME_HEAD) != 1]
    if bad:
        raise SystemExit(f"pages without the theme head script (or with a different copy): {bad}")
    return len(pages)


def patch_pylode(src: str) -> str:
    """Add charset/viewport, the theme head script, the language layer (js/i18n.js with data-doc-lang="en": the
    reference stays English, its bar follows the site's EN / VI / EN-VI mode, with a Vietnamese note in VI), the site's
    embedded web fonts, a small responsive stylesheet, the back bar (theme toggle via js/doc-theme.js, paper link) and
    the citation line to the pyLODE page."""
    head_add = ('<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n' + THEME_HEAD + '\n'
                + I18N_DOC_HEAD + '\n'
                '<link rel="stylesheet" href="../css/fonts-web.css">\n<link rel="stylesheet" href="../css/pylode-site.css">\n')
    src = re.sub(r"<meta[^>]*charset[^>]*>", "", src, flags=re.I)
    src, n = re.subn(r"<head>", "<head>\n" + head_add, src, count=1, flags=re.I)
    if n != 1:
        raise SystemExit("pyLODE HTML has no <head>")
    bar = ('<div class="vl-doc-bar"><a href="../ontology.html" data-i18n="chrome.doc.back">&#8592; VLOnto ontology page</a>'
           '<span class="vl-doc-right"><span data-i18n="chrome.doc.generated">Documentation generated by pyLODE from vlonto.ttl</span>'
           '<span class="vl-doc-note" lang="vi">T\u00e0i li\u1ec7u tham chi\u1ebfu n\u00e0y ch\u1ec9 c\u00f3 b\u1eb1ng ti\u1ebfng Anh.</span>'
           f'<a class="vl-paper-link" href="{PAPER_URL}" target="_blank" rel="noopener" data-paper-link="doc-bar" data-i18n="chrome.doc.paper">'
           'Paper: arXiv:2611.11426</a></span></div>\n')
    src = re.sub(r"(<body[^>]*>)", r"\1\n" + bar.replace("\\", "\\\\"), src, count=1, flags=re.I)
    foot = (f'<footer class="vl-doc-foot"><a href="{PAPER_URL}" target="_blank" rel="noopener" data-paper-link="footer" data-i18n="chrome.doc.cite">'
            f'{PAPER_CITE}</a> · <a href="../about.html#licences" data-i18n="chrome.doc.licences">Licences and attribution</a></footer>\n'
            '<script src="../js/doc-theme.js"></script>\n')
    src, n = re.subn(r"(</body>)", foot.replace("\\", "\\\\") + r"\1", src, count=1, flags=re.I)
    if n != 1:
        raise SystemExit("pyLODE HTML has no </body>")
    # long IRIs in text nodes may wrap after / and # (never inside a word) on narrow screens
    src = re.sub(r">(https?://[^<\s]{24,})<", lambda m: ">" + re.sub(r"([/#])(?=[^/#])", r"\1<wbr>", m.group(1)) + "<", src)
    # pyLODE writes the English and Vietnamese titles into one text node ("...OntologyVLOnto: Bản thể ..."); split them
    src = re.sub(r"<h1>(VLOnto: [^<]*?)(VLOnto: [^<]+)</h1>", r'<h1>\1<br><span class="vl-h1-vi" lang="vi">\2</span></h1>', src, count=1)
    return unicodedata.normalize("NFC", src)


def site_files(site: Path):
    out = []
    for p in sorted(site.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            rel = p.relative_to(site).as_posix()
            if rel == "data/site_files.js":
                continue
            out.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p)})
    return out


DOWNLOAD_GROUPS = [
    ("ontology", "Ontology", "The VLOnto OWL ontology, its SHACL shapes and the JSON-LD context (CC BY 4.0)."),
    ("rdf", "RDF", "The core subset of the knowledge graph as Turtle: the ontology plus all documents of legal-force rank 0-2 "
                   "(Constitution, codes, laws, National Assembly resolutions, ordinances, Standing Committee resolutions) with their "
                   "change events, legal-basis links and citations among themselves. This is the dataset the SPARQL playground loads."),
    ("data", "Site data (JSON)", "The JSON bundles behind the website (statistics, dashboard aggregates, ontology graph, legal network, "
                                 "SPARQL examples). The pages load the same content as JavaScript files from data/."),
    ("docs", "Documentation", "Data dictionary of the knowledge-graph tables, the licence and inclusion policy and the attribution text."),
    ("playbook", "Playbook", "The VLOnto playbook: Markdown source, reproducible Typst PDF and the SVG figures that the Markdown links to "
                             "(keep figures/ next to playbook.md)."),
]
DESCRIPTIONS = {
    "downloads/ontology/vlonto.ttl": "OWL 2 ontology (Turtle): classes, properties, concept schemes, alignments",
    "downloads/ontology/vlonto-shapes.ttl": "SHACL shapes used to validate the knowledge graph",
    "downloads/ontology/vlonto-context.jsonld": "JSON-LD context for VLOnto terms",
    "downloads/rdf/vlonto-core.ttl": "Core subset of the knowledge graph (Turtle)",
    "downloads/data/stats.json": "Headline statistics",
    "downloads/data/dashboard.json": "Dashboard aggregates",
    "downloads/data/ontology_graph.json": "Ontology as a graph (3D ontology playground)",
    "downloads/data/legal_network.json": "All 40,816 documents with 3D layout and change, basis and citation edges",
    "downloads/data/legal_network_lite.json": "6,000-document subset of the legal network (mobile)",
    "downloads/data/sparql_examples.json": "The 10 bilingual SPARQL examples with their row counts on the core subset",
    "downloads/data/manifest.json": "Byte sizes and sha256 of the site data bundles (KG track)",
    "downloads/docs/data_dictionary.md": "Data dictionary of the knowledge-graph tables",
    "downloads/docs/licence_policy.md": "Source licences and inclusion policy",
    "downloads/docs/ATTRIBUTION.txt": "Attribution text (English and Vietnamese)",
    "downloads/SHA256SUMS.txt": "sha256 of every file in downloads/",
    "downloads/VLOnto-playbook.pdf": "Playbook, reproducible Typst PDF",
    "downloads/playbook.md": "Playbook, Markdown source",
}


def group_of(rel: str) -> str:
    if rel in ("downloads/VLOnto-playbook.pdf", "downloads/playbook.md") or rel.startswith("downloads/figures/"):
        return "playbook"
    parts = rel.split("/")
    return parts[1] if len(parts) > 2 else "docs"


def describe(rel: str) -> str:
    if rel.startswith("downloads/figures/"):
        return "Playbook figure (SVG), linked from playbook.md"
    return DESCRIPTIONS.get(rel, "")


def hash_cell(h: str) -> str:
    groups = " ".join(h[i:i + 16] for i in range(0, 64, 16))
    return f'<code class="hash" title="{h}">{groups}</code>'


# The page follows the site's language mode (docs/i18n.md): headings, table headers and fixed texts carry data-i18n keys
# of js/i18n-pages.js (dl.*); js/downloads.js writes the sentences with links and numbers, the descriptions (dl.desc.*,
# dl.kg.*: used while the dictionary's English is the text below, so a changed description stays correct in English) and
# every number and size in the mode's format (data-n, data-bytes; sizes as human() below). The English text stays in the
# markup: it is what shows without scripts; the parts js/downloads.js writes carry data-vl-text, hidden while the page
# loads (css/site.css) so no wrong language flashes.
GROUPED = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")   # a number written with thousands separators (40,816) -> data-n


def desc_cell(text: str, attr: str) -> str:
    """the description cell of a file or table row; attr = ' data-desc="..."' or ' data-kg="..."' (or '' for none)"""
    m = GROUPED.search(text) if attr else None
    n = f' data-n="{m.group(0).replace(",", "")}"' if m else ""
    return f'<td class="col-desc"{attr}{n}{" data-vl-text" if attr else ""}>{esc(text)}</td>'


def size_cell(n: int) -> str:
    return f'<td class="num" data-bytes="{n}">{esc(human(n))}</td>'


def files_head(desc: bool) -> str:
    return ('<div class="table-wrap"><table class="data files"><thead><tr><th data-i18n="dl.th.file">File</th>' +
            ('<th class="col-desc" data-i18n="dl.th.description">Description</th>' if desc else '') +
            '<th class="num" data-i18n="dl.th.size">Size</th><th class="col-hash" data-i18n="dl.th.sha256">SHA-256</th></tr></thead><tbody>')


def downloads_html(files, kg_tables, rdf_dump, stats, n_total=None) -> str:
    dl = [f for f in files if f["path"].startswith("downloads/")]
    body = []
    for key, title, text in DOWNLOAD_GROUPS:
        rows = [f for f in dl if group_of(f["path"]) == key]
        body.append(f'<section class="block" id="dl-{key}">\n<h2 data-i18n="dl.group.{key}.h">{esc(title)}</h2>\n'
                    f'<p class="lead-sm" data-i18n="dl.group.{key}.text">{esc(text)}</p>')
        if not rows:
            body.append('<p class="note" data-i18n="dl.notBuilt">Not built yet. The Playbook track writes downloads/playbook.md and '
                        'downloads/VLOnto-playbook.pdf; re-run scripts/site/build_site.py afterwards to list them here.</p></section>')
            continue
        body.append(files_head(True))
        for f in rows:
            name = f["path"].split("/")[-1]
            d = describe(f["path"])
            key_suffix = "figure" if f["path"].startswith("downloads/figures/") else f["path"][len("downloads/"):]
            body.append(f'<tr><td><a class="file-link" href="{esc(f["path"])}" download>{esc(name)}</a>'
                        f'<div class="sub mono">{esc(f["path"])}</div></td>'
                        + desc_cell(d, f' data-desc="{esc(key_suffix)}"' if d else '') + size_cell(f["bytes"]) +
                        f'<td class="col-hash">{hash_cell(f["sha256"])}'
                        f'<button class="btn btn-xs copy-hash" type="button" data-hash="{f["sha256"]}" data-i18n="dl.copy">Copy</button></td></tr>')
        body.append('</tbody></table></div></section>')
    # site data scripts + vendor
    data_js = [f for f in files if f["path"].startswith("data/")]
    body.append('<section class="block" id="dl-site-data">\n<h2 data-i18n="dl.data.h">Data scripts used by the pages</h2>\n'
                '<p class="lead-sm" id="dl-data-text" data-vl-text>The pages read their data from these JavaScript files (each sets one entry of '
                '<code>window.VLONTO</code>), so the site works offline from <code>file://</code> without a server.</p>' + files_head(False))
    for f in data_js:
        body.append(f'<tr><td class="mono nowrap">{esc(f["path"])}</td>' + size_cell(f["bytes"]) +
                    f'<td class="col-hash">{hash_cell(f["sha256"])}</td></tr>')
    body.append('</tbody></table></div></section>')
    vend = [f for f in files if f["path"].startswith("vendor/") and f["path"].endswith(".js")]
    body.append('<section class="block" id="dl-vendor">\n<h2 data-i18n="dl.vendor.h">Third-party libraries and fonts</h2>\n'
                '<p class="lead-sm" id="dl-vendor-text" data-vl-text>Vendored classic-script builds pinned and checksummed by the toolchain '
                '(<a href="vendor/THIRD_PARTY_LICENSES.md">third-party licences</a>). Fonts: Be Vietnam Pro, JetBrains Mono NL, '
                'Noto Sans Symbols 2, Noto Sans Math and Libertinus Sans (the paper\u2019s figure font, used by the 3D views; '
                '<a href="fonts/OFL-Libertinus.txt">OFL</a>) under the SIL Open Font License 1.1 '
                '(<a href="fonts/OFL-BeVietnamPro.txt">OFL</a>), embedded as data URIs in <code>fonts/embedded/</code>.</p>' + files_head(False))
    for f in vend:
        body.append(f'<tr><td class="mono nowrap">{esc(f["path"])}</td>' + size_cell(f["bytes"]) +
                    f'<td class="col-hash">{hash_cell(f["sha256"])}</td></tr>')
    body.append('</tbody></table></div></section>')
    # the full graph is not part of the site and not published as a dataset: it is rebuilt from the sources of this release
    srcs = "".join(f'<li><a class="mono nowrap" href="{HF_SOURCE}{s}" target="_blank" rel="noopener">tmquan/{esc(s)}</a></li>'
                   for s in SOURCE_DATASETS)
    body.append('<section class="block" id="dl-full">\n<h2 data-i18n="dl.full.h">Rebuild the full graph</h2>\n'
                f'<p class="lead-sm" id="dl-full-text" data-n="{len(SOURCE_DATASETS)}" data-vl-text>The complete knowledge graph is too large for this website and is not published as a separate '
                f'dataset. Rebuild it from the {NUMBER_WORDS.get(len(SOURCE_DATASETS), len(SOURCE_DATASETS))} public source datasets of this release with the code in the <a href="{REPO_URL}" target="_blank" '
                f'rel="noopener">GitHub repository</a> (see its README for the requirements); this site keeps its own downloads above.</p>'
                f'<pre class="code">git clone {REPO_URL}\ncd VLOnto\npython -m vlonto.cli all</pre>'
                f'<p class="lead-sm" style="margin-top:12px" data-i18n="dl.full.sources">Source datasets on Hugging Face, by TMQuan:</p><ul class="source-list">{srcs}</ul>'
                f'<p class="lead-sm" id="dl-full-tables" data-n="{len(kg_tables)}" data-vl-text>A rebuild writes {len(kg_tables)} parquet tables with a data dictionary and the full RDF dump; '
                f'rows and sizes below are those of this release (<span data-vl-release>{esc(release_label())}</span>); '
                'court decisions join in v2.</p>'
                '<div class="table-wrap"><table class="data files"><thead><tr><th data-i18n="dl.th.table">Table</th><th class="num" data-i18n="dl.th.rows">Rows</th>'
                '<th class="num" data-i18n="dl.th.size">Size</th><th class="col-desc" data-i18n="dl.th.description">Description</th></tr></thead><tbody>')
    for t in kg_tables:
        stem = t["file"].rsplit(".", 1)[0]
        body.append(f'<tr><td class="mono nowrap">{esc(t["file"])}</td><td class="num" data-n="{t["rows"]}">{t["rows"]:,}</td>'
                    + size_cell(t["bytes"]) + desc_cell(t["description"], f' data-kg="{esc(stem)}"' if t["description"] else '') + '</tr>')
    if rdf_dump:
        body.append(f'<tr><td class="mono nowrap">{esc(rdf_dump["file"])}</td><td class="num" data-triples="{rdf_dump["triples"]}">{rdf_dump["triples"]:,} triples</td>'
                    + size_cell(rdf_dump["bytes"]) + '<td class="col-desc" data-i18n="dl.full.rdf">Full knowledge graph as gzipped N-Triples</td></tr>')
    body.append('</tbody></table></div></section>')
    total = sum(f["bytes"] for f in files)
    n_files = n_total or len(files)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{THEME_HEAD}
{I18N_HEAD}
<title data-i18n="dl.page.title">Downloads · VLOnto</title>
<meta name="description" data-i18n-content="dl.page.description" content="Downloads of the VLOnto ontology, RDF core subset, site data and documentation with sizes and sha256.">
<link rel="stylesheet" href="css/fonts-web.css">
<link rel="stylesheet" href="css/site.css">
</head>
<body class="page-text page-downloads">
<a class="skip-link" href="#main" data-i18n="chrome.skip.content">Skip to content</a>
<div id="vl-header"></div>
<main id="main" class="page">
<header class="page-head">
<p class="eyebrow" data-i18n="dl.eyebrow">Downloads</p>
<h1 data-i18n="dl.h1">Downloads</h1>
<p class="lead" id="dl-lead" data-n="{n_files}" data-bytes="{total}" data-vl-text>Every file below is part of this site and opens offline. Sizes and SHA-256 checksums were computed when the
site was built ({n_files:,} files, {esc(human(total))} in total). Use <a href="downloads/SHA256SUMS.txt">SHA256SUMS.txt</a>
with <code>sha256sum -c</code> to verify a download.</p>
</header>
{chr(10).join(body)}
</main>
<div id="vl-footer"></div>
{I18N_BODY}
<script src="data/site_meta.js"></script>
<script src="js/common.js"></script>
<script src="js/downloads.js"></script>
</body>
</html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="VLOnto root ($V)")
    ap.add_argument("--site", type=Path, default=None, help="site folder (default $V/repo/site)")
    ap.add_argument("--extra", type=Path, default=None, help="derive_site_data.py output (default $V/build/site_extra)")
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args(argv)
    V = a.root.resolve()
    repo = V / "repo"
    site = (a.site or repo / "site").resolve()
    extra = (a.extra or V / "build" / "site_extra").resolve()
    sd = V / "build" / "site_data"
    rep = {"site": os.path.relpath(site, repo.resolve()), "steps": {}}   # relative: no node paths in reports

    # 1. data twins
    man = json.loads((sd / "manifest.json").read_text(encoding="utf-8"))
    want = {f["file"]: f["sha256"] for f in man["files"]}
    (site / "data").mkdir(parents=True, exist_ok=True)
    twins = []
    for name in TWINS:
        src = sd / "js" / f"{name}.js"
        h = sha256(src)
        key = f"js/{name}.js"
        # manifest.js is written after manifest.json lists it (KG track note), so it cannot carry its own final hash
        checked = key in want and name != "manifest"
        if checked and want[key] != h:
            raise SystemExit(f"sha256 mismatch for {src} vs manifest.json")
        copy(src, site / "data" / f"{name}.js")
        twins.append({"file": f"data/{name}.js", "bytes": src.stat().st_size, "sha256": h, "manifest_checked": checked})
    rep["steps"]["twins"] = twins

    # 2. website data -> js (tools/json2js.py, deterministic, --verify reloads in node)
    extra_js = []
    for src in sorted(extra.glob("*.json")):
        if src.name == "derive_report.json":
            continue
        out = site / "data" / (src.stem + ".js")
        cmd = [a.python, str(repo / "tools" / "json2js.py"), str(src), "-o", str(out), "--verify"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"json2js failed for {src}: {r.stdout}\n{r.stderr}")
        extra_js.append({"file": f"data/{out.name}", "bytes": out.stat().st_size})
    rep["steps"]["extra_js"] = extra_js

    # 2b. question traces -> site/data/traces/*.js (scripts/site/trace_site.py; stdlib, deterministic)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import trace_site
    tr_dir = V / "build" / "traces"
    rep["steps"]["traces"] = trace_site.build(tr_dir if (tr_dir / "index.json").exists() else None, site)

    # 3. downloads
    dl = site / "downloads"
    for sub in ("ontology", "rdf", "data", "docs"):
        if (dl / sub).exists():
            shutil.rmtree(dl / sub)
    for f in ("vlonto.ttl", "vlonto-shapes.ttl", "vlonto-context.jsonld"):
        copy(repo / "ontology" / f, dl / "ontology" / f)
    copy(V / "build" / "rdf" / "vlonto-core.ttl", dl / "rdf" / "vlonto-core.ttl")
    for f in ("stats", "dashboard", "ontology_graph", "legal_network", "legal_network_lite", "sparql_examples", "manifest"):
        copy(sd / f"{f}.json", dl / "data" / f"{f}.json")
    copy(V / "build" / "kg" / "data_dictionary.md", dl / "docs" / "data_dictionary.md")
    policy = (repo / "docs" / "licence_policy.md").read_text(encoding="utf-8")
    copy(repo / "docs" / "licence_policy.md", dl / "docs" / "licence_policy.md")
    en, vi = attribution_texts(policy)
    (dl / "docs" / "ATTRIBUTION.txt").write_text(f"VLOnto - attribution\n\n{en}\n\nVLOnto - ghi nhận nguồn\n\n{vi}\n", encoding="utf-8")
    # SVG figures that downloads/playbook.md links as figures/<name>.svg (website-owned copies of repo/playbook/figures)
    if (dl / "figures").exists():
        shutil.rmtree(dl / "figures")
    figs = sorted((repo / "playbook" / "figures").glob("*.svg")) if (repo / "playbook" / "figures").exists() else []
    for f in figs:
        copy(f, dl / "figures" / f.name)
    md = dl / "playbook.md"
    linked = sorted(set(re.findall(r"figures/([A-Za-z0-9_.-]+\.svg)", md.read_text(encoding="utf-8")))) if md.exists() else []
    missing = [n for n in linked if not (dl / "figures" / n).exists()]
    if missing:
        raise SystemExit(f"downloads/playbook.md links figures that are not in repo/playbook/figures: {missing}")
    rep["steps"]["playbook_figures"] = {"copied": [f.name for f in figs], "linked_from_md": linked}
    sums = []
    for p in sorted(dl.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            sums.append(f"{sha256(p)}  {p.relative_to(dl).as_posix()}")
    (dl / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    rep["steps"]["attribution"] = {"en": en[:80] + "...", "vi": vi[:80] + "..."}

    # 4. pyLODE documentation
    py = (repo / "ontology" / "vlonto.html").read_text(encoding="utf-8")
    (site / "ontology").mkdir(exist_ok=True)
    (site / "ontology" / "vlonto.html").write_text(patch_pylode(py), encoding="utf-8")

    # data for the pages: attribution + KG table list
    dd = json.loads((V / "build" / "kg" / "data_dictionary.json").read_text(encoding="utf-8"))
    raw = dd.get("tables", dd) if isinstance(dd, dict) else dd
    dd_tables = {}
    if isinstance(raw, dict):
        dd_tables = {k: v for k, v in raw.items() if isinstance(v, dict)}
    elif isinstance(raw, list):
        dd_tables = {(t.get("name") or t.get("table") or ""): t for t in raw if isinstance(t, dict)}
    md = (V / "build" / "kg" / "data_dictionary.md").read_text(encoding="utf-8")
    md_rows = {m.group(1): int(m.group(2).replace(",", "")) for m in re.finditer(r"^## `(\w+)` \(([\d,]+) rows", md, re.M)}
    md_desc = {m.group(1): m.group(2).strip() for m in re.finditer(r"^## `(\w+)`[^\n]*\n\n([^\n|#][^\n]*)", md, re.M)}
    tables = []
    for p in sorted((V / "build" / "kg").glob("*.parquet")):
        info = dd_tables.get(p.stem, {})
        rows = info.get("rows", info.get("n_rows", 0)) or md_rows.get(p.stem, 0)
        desc = (info.get("description") or md_desc.get(p.stem) or "").strip()
        tables.append({"file": p.name, "bytes": p.stat().st_size, "rows": int(rows or 0), "description": desc})
    stats = json.loads((sd / "stats.json").read_text(encoding="utf-8"))
    # the release the pages name (VL.VERSION in site/js/common.js) against the data they ship (stats.version)
    sv = site_version(site)
    rep["release"] = {"label": release_label(sv), "site_version": sv, "data_version": stats.get("version"),
                      "data_matches_site": stats.get("version") == sv}
    if stats.get("version") != sv:
        print(f"warning: the site names {release_label(sv)} ({sv}) but the site data is version {stats.get('version')}",
              file=sys.stderr)
    rdf = V / "build" / "rdf" / "vlonto-kg.nt.gz"
    rdf_dump = {"file": rdf.name, "bytes": rdf.stat().st_size, "triples": int(stats.get("rdf_triples") or 0)} if rdf.exists() else None
    # KG totals the 3D network relates its document-pair counts to (citation links are recorded at document and article level)
    dash = json.loads((sd / "dashboard.json").read_text(encoding="utf-8"))
    kg_counts = {k: stats.get(k) for k in ("documents", "change_events", "legal_basis_links", "citation_links")}
    art_level = sum(int(r.get("article_level") or 0) for r in dash.get("citations_by_kind") or [])
    kg_counts["citation_links_article_level"] = art_level or None
    meta = {"attribution_en": en, "attribution_vi": vi, "kg_tables": tables, "rdf_dump": rdf_dump, "kg_counts": kg_counts,
            "version": stats.get("version"), "build_date": stats.get("build_date"), "validity_as_of": stats.get("validity_as_of"),
            "playbook_present": (site / "data" / "playbook_html.js").exists(),
            "playbook_pdf_present": (site / "downloads" / "VLOnto-playbook.pdf").exists()}
    meta_js = "(window.VLONTO = window.VLONTO || {})[\"site_meta\"] = " + json.dumps(meta, ensure_ascii=False) + ";\n"
    (site / "data" / "site_meta.js").write_text(unicodedata.normalize("NFC", meta_js), encoding="utf-8")

    # 5. downloads.html (needs the file list; the page itself is listed by name only) + site_files.js
    files = site_files(site)
    # the count includes downloads.html itself and data/site_files.js, which are written after this listing
    n_total = len([f for f in files if f["path"] != "downloads.html"]) + 2
    (site / "downloads.html").write_text(unicodedata.normalize("NFC", downloads_html(files, tables, rdf_dump, stats, n_total)), encoding="utf-8")
    files = site_files(site)
    payload = {"generated_by": "scripts/site/build_site.py", "files": files,
               "playbook_present": meta["playbook_present"], "playbook_pdf_present": meta["playbook_pdf_present"]}
    (site / "data" / "site_files.js").write_text(
        "(window.VLONTO = window.VLONTO || {})[\"site_files\"] = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")

    # 6. checks
    rep["theme_head_pages"] = check_theme_head(site)
    rep["lang_head_pages"] = check_lang_head(site)
    import i18n_check   # the language layer's dictionaries and the keys the site uses (docs/i18n.md)
    rep["i18n"] = {k: v for k, v in i18n_check.check(site).items() if k != "errors"}
    files = site_files(site)
    total = sum(f["bytes"] for f in files) + (site / "data" / "site_files.js").stat().st_size
    big = [f for f in files if f["bytes"] > MAX_FILE]
    non_nfc, non_nfc_upstream = [], []
    upstream = {f"data/{n}.js" for n in TWINS} | {"data/playbook_html.js"}
    for f in files:
        p = site / f["path"]
        if p.suffix in TEXT_EXT and not f["path"].startswith(("vendor/", "fonts/")):
            t = p.read_text(encoding="utf-8", errors="replace")
            if unicodedata.normalize("NFC", t) != t:
                lines = [ln for ln in t.splitlines() if unicodedata.normalize("NFC", ln) != ln]
                entry = {"path": f["path"], "lines": len(lines), "example": lines[0][:160] if lines else ""}
                # verbatim copies of other tracks' outputs are reported, not changed (the pages normalise text to NFC)
                (non_nfc_upstream if (f["path"] in upstream or f["path"].startswith("downloads/")) else non_nfc).append(entry)
    rep["non_nfc_upstream"] = non_nfc_upstream
    kg_local = [f["path"] for f in files if "kg_local" in f["path"] or f["path"].endswith("article_text.parquet")]
    rep["files"] = len(files) + 1
    rep["total_bytes"] = total
    rep["largest"] = sorted(({"path": f["path"], "bytes": f["bytes"]} for f in files), key=lambda x: -x["bytes"])[:8]
    rep["over_50MB"] = big
    rep["non_nfc"] = non_nfc
    rep["kg_local_files"] = kg_local
    rep["playbook_present"] = meta["playbook_present"]
    rep["ok"] = not big and total <= MAX_SITE and not non_nfc and not kg_local
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:4000])
    out = V / "build" / "site_build_report.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

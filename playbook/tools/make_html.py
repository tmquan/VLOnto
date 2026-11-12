#!/usr/bin/env python3
"""Website hand-off of the playbook.

    $V/envs/web/bin/python playbook/tools/make_html.py --pdf $V/build/playbook/VLOnto-playbook.pdf \
        [--preview DIR]

1. pandoc playbook/playbook.md -> HTML fragment (pandoc heading ids, tables, code without
   syntax colouring). The h1 title is removed (the page that shows the fragment provides its
   own title); the lead line and the related-paper line under it stay at the top.
2. Every figure (figures/NAME.svg, compiled by scripts/build_pdf.sh with
   `typst compile --input fig=NAME --format svg playbook/figures.typ`; figures.typ draws the
   figure with the code in charts.typ) is embedded as an SVG data URI, so the page loads no
   extra file; tables are wrapped in <div class="vlo-table-wrap">
   (horizontal scrolling on phones); cells that hold a number, date or document number get
   class "vlo-nowrap"; long inline code gets <wbr> after '/' so it can wrap without breaking
   a word; external links open in a new tab.
3. tools/json2js.py --text writes site/data/playbook_html.js, which sets
   window.VLONTO["playbook_html"] to the HTML string (verified by reloading it in Node).
4. The PDF and playbook.md are copied to site/downloads/.
With --preview DIR a standalone page (site fonts, minimal CSS) is written for render checks.
"""
import argparse
import base64
import hashlib
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[2]
PB = REPO / "playbook"
V = REPO.parent
W = V / "envs" / "web" / "bin"
BUILD = V / "build" / "playbook"
NOWRAP = re.compile(r"^(?:[<>~]?[\d][\d.,:%+\-/]*%?|\d+/\d{4}/[\wĐđ\-]+|[0-9a-f]{16}|-)$")
PREVIEW_CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #fff; color: #1d2430; font-family: var(--vlo-font-serif);
       font-size: 16px; line-height: 1.55; }
main { max-width: 920px; margin: 0 auto; padding: 24px 20px 64px; }
h2, h3, h4 { font-family: var(--vlo-font-sans); color: #1d4f7a; line-height: 1.25; }
code, pre { font-family: var(--vlo-font-mono); }
code { font-size: 0.88em; }
pre { background: #f5f5f5; padding: 10px 12px; overflow-x: auto; font-size: 13px;
      line-height: 1.45; }
pre code { font-size: inherit; }
.vlo-table-wrap { overflow-x: auto; margin: 1em 0; }
table { border-collapse: collapse; font-size: 14px; }
th, td { border-bottom: 1px solid #ddd; padding: 4px 8px; vertical-align: top; text-align: left; }
th { font-family: var(--vlo-font-sans); background: #eef1f4; }
.vlo-nowrap { white-space: nowrap; }
figure { margin: 1.4em 0; }
figure img { max-width: 100%; height: auto; display: block; }
figcaption { font-family: var(--vlo-font-sans); font-size: 13px; color: #555; }
blockquote { margin: 1em 0; padding: 2px 14px; border-left: 3px solid #9cbad3; }
@media (max-width: 600px) {
  body { font-size: 15px; }
  pre { font-size: 11px; }
  table { font-size: 12.5px; }
}
"""


def pandoc_fragment(md_path):
    r = subprocess.run([str(W / "pandoc"), str(md_path), "-f", "markdown", "-t", "html5",
                        "--syntax-highlighting=none", "--wrap=none"],
                       capture_output=True, text=True, check=True)
    return r.stdout


def postprocess(html):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 is not None:
        h1.decompose()
    figures = 0
    for img in soup.find_all("img"):
        src = img.get("src", "")
        m = re.fullmatch(r"figures/([\w\-]+)\.svg", src)
        if not m:
            raise SystemExit(f"unexpected image source: {src}")
        data = (PB / "figures" / f"{m.group(1)}.svg").read_bytes()
        img["src"] = "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")
        img["class"] = img.get("class", []) + ["vlo-figure"]
        figures += 1
    for table in soup.find_all("table"):
        wrap = soup.new_tag("div", attrs={"class": "vlo-table-wrap"})
        table.wrap(wrap)
    nowrap = 0
    for cell in soup.find_all(["td", "th"]):
        text = cell.get_text(" ", strip=True)
        if NOWRAP.match(text):
            cell["class"] = cell.get("class", []) + ["vlo-nowrap"]
            nowrap += 1
    wbr = 0
    for code in soup.find_all("code"):
        if code.find_parent("pre") is not None:
            continue
        text = code.get_text()
        if len(text) > 28 and "/" in text:
            code.clear()
            parts = text.split("/")
            for i, part in enumerate(parts):
                code.append(part + ("/" if i < len(parts) - 1 else ""))
                if i < len(parts) - 1:
                    code.append(soup.new_tag("wbr"))
                    wbr += 1
    for a in soup.find_all("a"):
        if a.get("href", "").startswith(("http://", "https://")):
            a["target"] = "_blank"
            a["rel"] = "noopener noreferrer"
    ids = [t["id"] for t in soup.find_all(attrs={"id": True})]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise SystemExit(f"duplicate ids: {dup[:10]}")
    out = unicodedata.normalize("NFC", str(soup))
    for bad in ("<script", "src=\"figures/", "src=\"http"):
        if bad in out:
            raise SystemExit(f"fragment contains {bad!r}")
    return out, {"figures": figures, "nowrap_cells": nowrap, "wbr": wbr, "ids": len(ids),
                 "tables": len(soup.find_all("table")), "h2": len(soup.find_all("h2"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--preview")
    a = ap.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    frag, stats = postprocess(pandoc_fragment(PB / "playbook.md"))
    frag_path = BUILD / "playbook_fragment.html"
    frag_path.write_text(frag, encoding="utf-8")
    js = REPO / "site" / "data" / "playbook_html.js"
    js.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(W / "python"), str(REPO / "tools" / "json2js.py"), str(frag_path),
                        "--text", "--name", "playbook_html", "-o", str(js), "--verify",
                        "--node", str(W / "node")], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0 or "verify=OK" not in r.stdout:
        print(r.stderr, file=sys.stderr)
        raise SystemExit("json2js failed")
    dl = REPO / "site" / "downloads"
    dl.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.pdf, dl / "VLOnto-playbook.pdf")
    shutil.copyfile(PB / "playbook.md", dl / "playbook.md")
    if a.preview:
        pv = Path(a.preview)
        pv.mkdir(parents=True, exist_ok=True)
        if not (pv / "fonts").exists():
            shutil.copytree(REPO / "site" / "fonts", pv / "fonts")
        page = ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                "<title>VLOnto playbook (preview)</title>"
                "<link rel=\"stylesheet\" href=\"fonts/fonts.css\">"
                f"<style>{PREVIEW_CSS}</style></head>\n<body><main>\n<h1>VLOnto playbook</h1>\n"
                + frag + "\n</main></body></html>\n")
        (pv / "index.html").write_text(page, encoding="utf-8")
    sha = hashlib.sha256(js.read_bytes()).hexdigest()
    print(f"fragment {len(frag.encode()):,} bytes; {stats}; playbook_html.js "
          f"{js.stat().st_size:,} bytes sha256 {sha[:16]}")


if __name__ == "__main__":
    main()

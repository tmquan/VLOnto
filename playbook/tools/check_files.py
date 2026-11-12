#!/usr/bin/env python3
"""Compare every file size, sha256 and RDF triple count printed in the playbook with the files.

Run from the repository root on the build node, after `bash scripts/build_pdf.sh`, with the
knowledge-graph environment (pyoxigraph):

    $V/envs/kg/bin/python playbook/tools/check_files.py [--pdf FILE] [--report FILE]

It reads the generated playbook/playbook.md and checks
  * the File/Size table of section 2.2, the `export` and `core` rows of section 5.3 and the
    File/Size/sha256 table of section 10.4 against the files of the build folder ($V/build/kg,
    $V/build/rdf, $V/build/release) and of the repository (ontology/);
  * every copy of these files under site/downloads/ (same path, or the same file name in another
    folder, e.g. docs/data_dictionary.md): it must be the printed file, and each row of section 2.2
    that names the downloads page must have such a copy;
  * the triple counts printed for rdf/vlonto-kg.nt.gz (lines) and rdf/vlonto-core.ttl (parsed);
  * playbook/data/SHA256SUMS against the files, and the table of section 10.4 against SHA256SUMS;
  * the copies of this playbook that the build hands to the website (site/downloads/playbook.md,
    site/downloads/VLOnto-playbook.pdf).
Entries of site/downloads/SHA256SUMS.txt that do not match their files, and figures that differ from
site/downloads/figures/, are reported as warnings: the website build owns those files.
Exit status 1 if a printed value differs from a file.
"""
import argparse
import gzip
import hashlib
import os
import re
import sys
from pathlib import Path

V = Path(os.environ.get("V", Path(__file__).resolve().parents[3]))     # <V>/repo/playbook/tools
BUILD = V / "build"
TICKS = re.compile(r"`([^`]+)`")


def size(n):
    """Same rounding as the size() macro of playbook.md.j2."""
    if n >= 1_000_000:
        return "%.1f MB" % (n / 1_000_000)
    if n >= 1000:
        return "%.0f kB" % (n / 1000)
    return f"{n} B"


_SHA = {}


def sha256(p):
    p = Path(p)
    if p not in _SHA:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        _SHA[p] = h.hexdigest()
    return _SHA[p]


def count_nt_gz(p):
    n = 0
    with gzip.open(p, "rb") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith(b"#"):
                n += 1
    return n


def count_ttl(p):
    from pyoxigraph import RdfFormat, parse
    return sum(1 for _ in parse(path=str(p), format=RdfFormat.TURTLE))


# ----------------------------------------------------------------------------- playbook.md
def section(lines, title):
    """Lines of the section whose heading text starts with `title`, up to the next heading of the
    same or a higher level."""
    start = level = None
    fence = False
    for i, ln in enumerate(lines):
        if ln.startswith(("```", "~~~")):
            fence = not fence
        m = None if fence else re.match(r"^(#+) (.*)", ln)
        if not m:
            continue
        if start is None:
            if m.group(2).startswith(title):
                start, level = i, len(m.group(1))
        elif len(m.group(1)) <= level:
            return lines[start:i]
    if start is None:
        raise SystemExit(f"check_files: no section {title!r} in playbook.md")
    return lines[start:]


def first_table(lines, header0):
    """Body rows (lists of cells) of the first pipe table whose first header cell is `header0`."""
    for i, ln in enumerate(lines):
        if ln.startswith("|") and cells(ln)[0] == header0 and i + 1 < len(lines) \
                and set(lines[i + 1].replace("|", "").strip()) <= set(":- "):
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                rows.append(cells(row))
            return rows
    raise SystemExit(f"check_files: no table with first column {header0!r}")


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


# ----------------------------------------------------------------------------- files
def source(repo, path):
    """Printed path -> file of the build folder or of the repository."""
    top, rest = path.split("/", 1)
    if top in ("kg", "rdf"):
        return BUILD / path
    if top == "ontology":
        return repo / path
    if top == "code":
        return BUILD / "release" / rest
    raise SystemExit(f"check_files: no source folder for {path}")


def copies(dl, path):
    """Copies of a printed file under site/downloads: the same path, or the same file name."""
    direct = dl / path
    found = [direct] if direct.is_file() else []
    found += [q for q in sorted(dl.rglob(Path(path).name)) if q.is_file() and q != direct]
    return found


class Results:
    def __init__(self):
        self.rows, self.warnings = [], []

    def check(self, what, printed, actual, ok, note=""):
        self.rows.append((what, printed, actual, "PASS" if ok else "FAIL", note))
        return ok

    def warn(self, text):
        self.warnings.append(text)

    @property
    def failed(self):
        return [r for r in self.rows if r[3] == "FAIL"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--pdf", default=str(BUILD / "playbook" / "VLOnto-playbook.pdf"))
    ap.add_argument("--report", default=str(BUILD / "playbook" / "check_files.md"))
    a = ap.parse_args()
    repo = Path(a.repo)
    dl = repo / "site" / "downloads"
    md = (repo / "playbook" / "playbook.md").read_text(encoding="utf-8").splitlines()
    R = Results()
    quoted = {}                                   # printed path -> source file

    # section 10.4: File | Size | sha256 (prefix)
    rows104 = first_table(section(md, "10.4 "), "File")
    for c in rows104:
        path, prefix = TICKS.findall(c[0])[0], TICKS.findall(c[2])[0]
        src = source(repo, path)
        quoted[path] = src
        if not src.is_file():
            R.check(f"10.4 {path}", f"{c[1]}, {prefix}", "missing", False, str(src))
            continue
        R.check(f"10.4 {path} size", c[1], size(src.stat().st_size), size(src.stat().st_size) == c[1])
        R.check(f"10.4 {path} sha256", prefix, sha256(src)[:16],
                len(prefix) == 16 and sha256(src).startswith(prefix))

    # section 2.2: File | Size | Where to get it
    for c in first_table(section(md, "2.2 "), "File"):
        names = []
        for n in TICKS.findall(c[0]):
            names.append(str(Path(names[-1]).with_suffix(n)) if n.startswith(".") and names else n)
        files = []
        for n in names:
            src = source(repo, n)
            if "*" in n:
                matched = sorted(src.parent.glob(src.name))
                m = re.search(r"\((\d+) tables\)", c[0])
                if m:
                    R.check(f"2.2 {n} count", m.group(1), str(len(matched)), int(m.group(1)) == len(matched))
                files += matched
                quoted.update({f"{n.split('/')[0]}/{p.name}": p for p in matched})
            else:
                files.append(src)
                quoted[n] = src
        missing = [str(f) for f in files if not f.is_file()]
        total = sum(f.stat().st_size for f in files if f.is_file())
        R.check(f"2.2 {', '.join(names)} size", c[1], size(total), not missing and size(total) == c[1],
                f"missing {missing}" if missing else "")
        where = c[2]
        if "downloads page" in where:
            m = re.search(r"the `(\.\w+)` file", where)
            need = [n for n in names if not m or n.endswith(m.group(1))]
            for n in need:
                cp = copies(dl, n)
                R.check(f"2.2 {n} on the downloads page", "downloads page",
                        ", ".join(str(q.relative_to(dl)) for q in cp) or "no copy", bool(cp))
        else:
            for n in names:
                if "*" not in n and copies(dl, n):
                    R.warn(f"2.2 says {n} comes from the local build only, but site/downloads has a copy")

    # section 5.3: export and core rows
    rows53 = {c[0]: c for c in first_table(section(md, "5.3 "), "Step")}
    m = re.match(r"([\d,]+) triples, (.+)$", rows53["`export`"][2])
    nt = BUILD / "rdf" / "vlonto-kg.nt.gz"
    quoted.setdefault("rdf/vlonto-kg.nt.gz", nt)
    R.check("5.3 export size", m.group(2), size(nt.stat().st_size), size(nt.stat().st_size) == m.group(2))
    n_nt = count_nt_gz(nt)
    R.check("5.3 export triples (lines of rdf/vlonto-kg.nt.gz)", m.group(1), f"{n_nt:,}",
            int(m.group(1).replace(",", "")) == n_nt)
    m = re.match(r"([\d,]+) triples", rows53["`core`"][2])
    core = BUILD / "rdf" / "vlonto-core.ttl"
    quoted.setdefault("rdf/vlonto-core.ttl", core)
    n_core = count_ttl(core)
    R.check("5.3 core triples (rdf/vlonto-core.ttl parsed)", m.group(1), f"{n_core:,}",
            int(m.group(1).replace(",", "")) == n_core)

    # copies served by the website
    for path, src in sorted(quoted.items()):
        for q in copies(dl, path):
            rel = str(q.relative_to(dl))
            same = src.is_file() and sha256(q) == sha256(src)
            R.check(f"site/downloads/{rel} is the printed {path}", sha256(src)[:16] if src.is_file() else "-",
                    sha256(q)[:16], same, "" if same else "the website serves a different file")
            if not same and path == "rdf/vlonto-core.ttl":
                n = count_ttl(q)
                R.check(f"site/downloads/{rel} triples", f"{n_core:,}", f"{n:,}", n == n_core)

    # playbook/data/SHA256SUMS
    sums = {}
    for ln in (repo / "playbook" / "data" / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        h, p = ln.split(None, 1)
        sums[p.strip()] = h
    for p, h in sorted(sums.items()):
        src = source(repo, p)
        ok = src.is_file() and sha256(src) == h
        R.check(f"SHA256SUMS {p}", h[:16], sha256(src)[:16] if src.is_file() else "missing", ok)
    t104 = {TICKS.findall(c[0])[0] for c in rows104}
    want = {p for p in sums if not p.startswith("code/")}
    R.check("10.4 lists the files of SHA256SUMS (without code/)", f"{len(want)} files", f"{len(t104)} files",
            t104 == want, "; ".join(sorted(t104 ^ want)))

    # copies of this playbook handed to the website
    pdf = Path(a.pdf)
    for built, served in ((repo / "playbook" / "playbook.md", dl / "playbook.md"),
                          (pdf, dl / "VLOnto-playbook.pdf")):
        ok = served.is_file() and built.is_file() and sha256(served) == sha256(built)
        R.check(f"site/downloads/{served.name} is the built file", sha256(built)[:16] if built.is_file() else "missing",
                sha256(served)[:16] if served.is_file() else "missing", ok)

    # website-owned lists: warnings only
    lst = dl / "SHA256SUMS.txt"
    if lst.is_file():
        listed = set()
        for ln in lst.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            h, p = ln.split(None, 1)
            p = p.strip().lstrip("*").removeprefix("./")
            listed.add(p)
            f = dl / p
            if not f.is_file():
                R.warn(f"site/downloads/SHA256SUMS.txt lists {p}, which is missing")
            elif sha256(f) != h:
                R.warn(f"site/downloads/SHA256SUMS.txt: {p} listed {h[:16]}, file is {sha256(f)[:16]}")
        for f in sorted(dl.rglob("*")):
            r = str(f.relative_to(dl))
            if f.is_file() and r != "SHA256SUMS.txt" and r not in listed:
                R.warn(f"site/downloads/{r} is not listed in SHA256SUMS.txt")
    else:
        R.warn("site/downloads/SHA256SUMS.txt is missing")
    for svg in sorted((repo / "playbook" / "figures").glob("*.svg")):
        q = dl / "figures" / svg.name
        if not q.is_file():
            R.warn(f"site/downloads/figures/{svg.name} is missing")
        elif sha256(q) != sha256(svg):
            R.warn(f"site/downloads/figures/{svg.name} differs from playbook/figures/{svg.name}")
    page = repo / "site" / "ontology" / "vlonto.html"
    if page.is_file() and sha256(page) != sha256(repo / "ontology" / "vlonto.html"):
        R.warn("site/ontology/vlonto.html differs from ontology/vlonto.html (2.2 names the ontology page, "
               "not a byte copy)")

    fails = R.failed
    out = [f"# check_files: {len(R.rows)} checks, {len(fails)} failed, {len(R.warnings)} warnings", "",
           f"playbook.md sha256 `{sha256(repo / 'playbook' / 'playbook.md')}`", "",
           "| check | printed | file | result | note |", "|---|---|---|---|---|"]
    out += [f"| {w} | {p} | {f} | {r} | {n} |" for w, p, f, r, n in R.rows]
    out += ["", "## Warnings (website-owned files)", ""] + [f"- {w}" for w in R.warnings or ["none"]]
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text("\n".join(out) + "\n", encoding="utf-8")
    for w, p, f, r, n in fails:
        print(f"FAIL {w}: printed {p}, file {f} {n}".rstrip())
    for w in R.warnings:
        print(f"WARN {w}")
    print(f"check_files: {len(R.rows)} checks, {len(fails)} failed, {len(R.warnings)} warnings -> {a.report}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

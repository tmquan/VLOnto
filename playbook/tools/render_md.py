#!/usr/bin/env python3
"""Render playbook/playbook.md and playbook/data/meta.json from playbook.md.j2 + data/facts.json.

    $V/envs/web/bin/python playbook/tools/render_md.py [--check-only]

Every number in the playbook is read from data/facts.json (written by tools/gather_facts.py from
the build reports, the recipe runs and the example runs); the template only formats it.
Checks (exit 1 on failure): no undefined template variable (StrictUndefined); every line of a
code block <= 88 characters; text is NFC; no tab characters; no trailing spaces. The digits
typed literally in the template outside {{ }} and {% %} are listed in data/literal_numbers.txt
for review (section numbers, years inside names and identifiers in prose).
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import jinja2

PB = Path(__file__).resolve().parents[1]
MAX_CODE = 88
TABLE_WIDTH = 116  # characters of the separator line: > pandoc --columns, so widths are relative


class Md(str):
    """A string that is already Markdown (not escaped in table cells)."""


def num(x, digits=None):
    if x is None:
        return "-"
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        return f"{x:,.{digits if digits is not None else 1}f}"
    if isinstance(x, str) and re.fullmatch(r"-?\d+", x):
        return f"{int(x):,}"
    return str(x)


def pct(a, b, digits=1):
    return f"{100.0 * a / b:.{digits}f}%"


def esc(s):
    if isinstance(s, Md):
        return str(s)
    s = "-" if s is None else str(s)
    s = s.replace("\\", "\\\\")
    for ch in "|*_`[]<>$#~":
        s = s.replace(ch, "\\" + ch)
    return s.replace("\n", " ")


ID_COL = re.compile(r"(^|_)(id|year|no|number|depth)$")


def is_count(v):
    """An integer, or a string of digits as SPARQL returns counts."""
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d+", v) is not None)


def cell(v, col=""):
    if isinstance(v, Md):
        return str(v)
    if isinstance(v, bool) or v is None:
        return esc(num(v))
    if is_count(v) and not isinstance(v, float) and not ID_COL.search(col):
        return esc(num(v))
    return esc(v)


def codecell(s):
    """Inline code for a table cell: a fence longer than any backtick run, pipes escaped."""
    s = str(s).replace("\n", " ").replace("|", "\\|")
    fence = "`"
    while fence in s:
        fence += "`"
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return Md(f"{fence}{pad}{s}{pad}{fence}")


def table(header, rows, widths=None, align=None):
    """Pipe table; a separator longer than pandoc's --columns makes widths relative.
    Alignment is always explicit (l, r or c), so no cell inherits the centring of the figure."""
    k = len(header)
    widths = widths or [1] * k
    align = align or ["l"] * k
    tot = float(sum(widths))
    seps = []
    for w, a in zip(widths, align):
        d = max(4, round(TABLE_WIDTH * w / tot))
        seps.append({"r": "-" * (d - 1) + ":", "c": ":" + "-" * (d - 2) + ":"}.get(a, ":" + "-" * (d - 1)))
    out = ["| " + " | ".join(esc(h) for h in header) + " |", "|" + "|".join(seps) + "|"]
    for r in rows:
        out.append("| " + " | ".join(cell(v, header[i].lower()) for i, v in enumerate(r)) + " |")
    return "\n".join(out)


def result_table(res, widths=None, align=None, max_rows=None, rename=None):
    cols = list(res["columns"])
    rows = res["rows"][:max_rows] if max_rows else res["rows"]
    header = [(rename or {}).get(c, c) for c in cols]
    if align is None:
        align = ["r" if rows and not ID_COL.search(cols[i].lower())
                 and all(is_count(r[i]) for r in rows if r[i] is not None) else "l"
                 for i in range(len(cols))]
    return table(header, rows, widths, align)


def code(text, lang=""):
    text = unicodedata.normalize("NFC", str(text).rstrip("\n"))
    for i, line in enumerate(text.splitlines(), 1):
        if len(line) > MAX_CODE:
            raise ValueError(f"code line {i} has {len(line)} > {MAX_CODE} characters: {line[:60]}...")
        if "\t" in line:
            raise ValueError(f"tab in code line {i}")
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{lang}\n{text}\n{fence}"


def short(s, n):
    """Cut at the last space before n characters and mark the cut with an ellipsis."""
    s = str(s)
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:") + " …"


NBSP_RE = re.compile(r"\b(section|sections|Section|Appendix|appendix|recipe|Article|Điều|Figure) "
                     r"(?=\d|[A-D]\b)")


def tidy(text):
    """Outside fenced code: collapse runs of blank lines and keep 'section 9', 'Appendix D'
    together with a no-break space (not in headings, whose identifiers derive from the text).
    Code blocks are left exactly as the source files are."""
    out, in_code, fence, blank = [], False, "", 0
    for line in text.split("\n"):
        m = re.match(r"^(`{3,})", line)
        if m and (not in_code or m.group(1) == fence):
            in_code, fence = (not in_code), m.group(1)
            out.append(line)
            blank = 0
            continue
        if in_code:
            out.append(line)
            continue
        if not line.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        if not line.startswith("#"):
            parts = re.split(r"(`+[^`]*`+)", line)  # odd parts are inline code: left as written
            line = "".join(p if i % 2 else NBSP_RE.sub(lambda mm: mm.group(1) + "\u00a0", p)
                           for i, p in enumerate(parts))
        out.append(line.rstrip(" \t"))
    return "\n".join(out).rstrip("\n") + "\n"


def literal_numbers(template_text):
    """Digits typed in the template outside Jinja tags, with line numbers (for review)."""
    out = []
    for i, line in enumerate(template_text.splitlines(), 1):
        bare = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", " ", line)
        for m in re.finditer(r"\d[\d.,/:]*", bare):
            out.append(f"{i}: {m.group(0)}    | {line.strip()[:110]}")
    return out


def main():
    check_only = "--check-only" in sys.argv
    facts = json.loads((PB / "data" / "facts.json").read_text(encoding="utf-8"))
    figures = json.loads((PB / "data" / "figures.json").read_text(encoding="utf-8"))
    # the related paper (title, authors, identifier, link, BibTeX): editorial data, not a build fact
    cite = json.loads((PB / "data" / "citation.json").read_text(encoding="utf-8"))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PB)), undefined=jinja2.StrictUndefined,
                             keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True,
                             autoescape=False)
    env.filters.update(num=num, esc=esc, short=short)
    env.tests["match"] = lambda value, pattern: re.search(pattern, str(value)) is not None
    env.globals.update(num=num, pct=pct, table=table, result_table=result_table, code=code, Md=Md,
                       esc=esc, short=short, codecell=codecell)
    src = (PB / "playbook.md.j2").read_text(encoding="utf-8")
    text = env.from_string(src).render(f=facts, fig=figures, cite=cite)
    text = tidy(unicodedata.normalize("NFC", text))
    problems = []
    if "{{" in text or "{%" in text:
        problems.append("unrendered template tag in output")
    if "\t" in text:
        problems.append("tab character in output")
    in_code = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code and len(line) > MAX_CODE:
            problems.append(f"playbook.md line {i}: code line of {len(line)} characters")
    lits = literal_numbers(src)
    (PB / "data" / "literal_numbers.txt").write_text("\n".join(lits) + "\n", encoding="utf-8")
    if problems:
        print("\n".join(problems))
        return 1
    st, ver = facts["stats"], facts["config"]
    checks = facts["checks"]
    meta = {
        "subtitle": "Build, validate, query and use the Vietnamese legal knowledge graph",
        "kicker": "Vietnamese legal ontology and knowledge graph",
        "author": "tmquan",
        "version": ver["version"],
        "date": ver["build_date"],
        "lang": "en",
        "keywords": ["VLOnto", "Vietnamese law", "legal ontology", "knowledge graph", "OWL", "SKOS",
                     "ELI", "RDF", "SPARQL", "legal informatics"],
        "keyfigures": [
            {"value": num(st["documents"]), "label": "legal documents"},
            {"value": num(st["articles"]), "label": "articles (Điều)"},
            {"value": num(st["court_decisions"]), "label": "court decisions"},
            {"value": num(st["legal_questions"]), "label": "legal Q&As (metadata)"},
            {"value": num(st["rdf_triples"]), "label": "RDF triples"},
            {"value": f"{sum(1 for c in checks if c['result'] == 'pass')} / {len(checks)}",
             "label": "build checks passed"},
        ],
        "licence": ("Ontology and documentation: CC BY 4.0, creator tmquan. Knowledge-graph data: "
                    "see the licence and attribution appendix."),
        "disclaimer": ("Not legal advice and not an official legal text. Relations are extracted "
                       "automatically and may be wrong; read the source documents."),
    }
    if not check_only:
        (PB / "playbook.md").write_text(text, encoding="utf-8")
        (PB / "data" / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"playbook.md: {len(text.splitlines())} lines, {len(text.encode()):,} bytes; "
          f"{len(lits)} literal digit groups listed in data/literal_numbers.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())

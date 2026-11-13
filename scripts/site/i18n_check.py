#!/usr/bin/env python3
"""Static checks of the website's language layer (docs/i18n.md). Stdlib only; build_site.py runs it after its other
checks, and it runs on its own:

    python3 scripts/site/i18n_check.py [--root site] [--csv translations.csv] [--unused]

It reads the dictionaries - js/i18n.js (core: header, footer, theme and language controls, skip links), js/i18n-3d.js
(3D track) and js/i18n-pages.js (content-pages track) - and every literal key the site uses: data-i18n,
data-i18n-title / -aria / -placeholder / -alt / -content attributes in the pages (and in HTML that scripts write), and
VL.T / VL.U / VL.TH / VL.UH / VL.tip / VL.TL calls with a literal key ('net.rank.' + r counts as a prefix).

Errors (exit status 1): a dictionary that does not parse, a key defined twice, a field other than en / vi / k / en_one /
note, a kind other than ui / text / pair, an empty en or vi, a value that is not NFC, {placeholders} that differ between
en and vi (en_one may drop some), and a key the site uses that no dictionary defines (the page would show the key).
--unused lists the keys no page or script uses yet (not an error)."""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

DICTS = ("js/i18n.js", "js/i18n-3d.js", "js/i18n-pages.js")
FIELDS = {"en", "vi", "k", "en_one", "note"}
KINDS = {"ui", "text", "pair"}
ADD = re.compile(r"""(?:VL\.i18n\.add|\badd)\(\s*(['"])([\w.\-]+)\1\s*,\s*(?=\{)""")
USE_ATTR = re.compile(r"""data-i18n(?:-title|-aria|-placeholder|-alt|-content)?=\\?["']([\w.\-]+)\\?["']""")
USE_CALL = re.compile(r"""\bVL\.(?:T|U|TH|UH|tip|TL)\(\s*(['"])([\w.\-]+)\1""")
USE_LIT = re.compile(r"""['"]([a-z][a-z0-9]*(?:\.[A-Za-z0-9_]+)+)['"]""")   # 'chrome.nav.traces' passed around as data
PH = re.compile(r"\{(\w+)\}")
ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


class Parse:
    """the subset of JavaScript the dictionaries use: object and array literals of string literals ('a' + 'b' joins),
    identifier or quoted keys, comments. Objects come back as lists of (key, value, line) so duplicates stay visible."""

    def __init__(self, s: str, i: int):
        self.s, self.i = s, i

    def line(self) -> int:
        return self.s.count("\n", 0, self.i) + 1

    def fail(self, what: str):
        raise ValueError(f"line {self.line()}: {what}")

    def ws(self):
        s = self.s
        while True:
            while self.i < len(s) and s[self.i] in " \t\r\n":
                self.i += 1
            if s.startswith("/*", self.i):
                j = s.find("*/", self.i)
                if j < 0:
                    self.fail("unclosed comment")
                self.i = j + 2
            elif s.startswith("//", self.i):
                j = s.find("\n", self.i)
                self.i = len(s) if j < 0 else j
            else:
                return

    def peek(self) -> str:
        self.ws()
        if self.i >= len(self.s):
            self.fail("unexpected end of file")
        return self.s[self.i]

    def expect(self, c: str):
        if self.peek() != c:
            self.fail(f"expected {c!r}, found {self.s[self.i:self.i + 20]!r}")
        self.i += 1

    def string(self) -> str:
        s, q = self.s, self.s[self.i]
        i, out = self.i + 1, []
        while True:
            if i >= len(s) or s[i] == "\n":
                self.fail("unterminated string")
            c = s[i]
            if c == q:
                break
            if c == "\\":
                n = s[i + 1]
                if n == "u" and s[i + 2] == "{":
                    j = s.index("}", i)
                    out.append(chr(int(s[i + 3:j], 16)))
                    i = j + 1
                elif n == "u":
                    out.append(chr(int(s[i + 2:i + 6], 16)))
                    i += 6
                elif n == "x":
                    out.append(chr(int(s[i + 2:i + 4], 16)))
                    i += 4
                else:
                    out.append(ESC.get(n, n))
                    i += 2
                continue
            out.append(c)
            i += 1
        self.i = i + 1
        return "".join(out).encode("utf-16", "surrogatepass").decode("utf-16")

    def key(self) -> str:
        if self.peek() in "'\"":
            return self.string()
        m = re.compile(r"[A-Za-z_$][\w$]*").match(self.s, self.i)
        if not m:
            self.fail(f"expected a key, found {self.s[self.i:self.i + 20]!r}")
        self.i = m.end()
        return m.group(0)

    def value(self):
        c = self.peek()
        if c in "'\"":
            v = self.string()
            while self.peek() == "+":
                self.i += 1
                if self.peek() not in "'\"":
                    self.fail("only string literals can be joined with +")
                v += self.string()
            return v
        if c == "{":
            return self.obj()
        if c == "[":
            self.i += 1
            out = []
            while self.peek() != "]":
                out.append(self.value())
                if self.peek() == ",":
                    self.i += 1
            self.i += 1
            return out
        self.fail(f"expected a string, object or array, found {self.s[self.i:self.i + 20]!r}")

    def obj(self):
        self.expect("{")
        out = []
        while True:
            if self.peek() == "}":
                self.i += 1
                return out
            line = self.line()
            k = self.key()
            self.expect(":")
            out.append((k, self.value(), line))
            if self.peek() == ",":
                self.i += 1
            elif self.peek() != "}":
                self.fail(f"expected ',' or '}}' after {k!r}")


def read_dicts(site: Path):
    """[(file, owner, key, entry dict, line)] and the errors found while reading"""
    rows, errors = [], []
    for rel in DICTS:
        p = site / rel
        if not p.exists():
            errors.append(f"{rel}: missing")
            continue
        s = p.read_text(encoding="utf-8")
        found = 0
        for m in ADD.finditer(s):
            found += 1
            try:
                body = Parse(s, m.end()).obj()
            except (ValueError, IndexError) as ex:
                errors.append(f"{rel}: does not parse ({ex})")
                continue
            for key, val, line in body:
                if isinstance(val, list) and all(isinstance(v, str) for v in val):   # [en, vi, kind]
                    val = [(f, v, line) for f, v in zip(("en", "vi", "k"), val)]
                if not isinstance(val, list) or not all(isinstance(v, str) for _, v, _ in val):
                    errors.append(f"{rel}:{line}: {key}: the value is not an object of strings")
                    continue
                e = {}
                for f, v, _ in val:
                    if f in e:
                        errors.append(f"{rel}:{line}: {key}: field {f} given twice")
                    e[f] = v
                rows.append((rel, m.group(2), key, e, line))
        if not found:
            errors.append(f"{rel}: no VL.i18n.add('owner', {{...}}) call")
    return rows, errors


def check_entries(rows):
    errors, seen = [], {}
    for rel, owner, key, e, line in rows:
        where = f"{rel}:{line}: {key}"
        if key in seen:
            errors.append(f"{where}: defined twice (first in {seen[key]})")
        seen.setdefault(key, f"{rel}:{line}")
        bad = set(e) - FIELDS
        if bad:
            errors.append(f"{where}: unknown field(s) {sorted(bad)}")
        if e.get("k", "text") not in KINDS:
            errors.append(f"{where}: kind {e.get('k')!r} is not one of {sorted(KINDS)}")
        for f in ("en", "vi"):
            if not (e.get(f) or "").strip():
                errors.append(f"{where}: empty {f}")
        for f, v in e.items():
            if unicodedata.normalize("NFC", v) != v:
                errors.append(f"{where}: {f} is not NFC")
        en, vi = set(PH.findall(e.get("en", ""))), set(PH.findall(e.get("vi", "")))
        if en != vi:
            errors.append(f"{where}: placeholders differ: en {sorted(en)}, vi {sorted(vi)}")
        if "en_one" in e and not set(PH.findall(e["en_one"])) <= en:
            errors.append(f"{where}: en_one has placeholders that en does not have")
    return errors, set(seen)


def used_keys(site: Path, defined=frozenset()):
    """{key or prefix ending in '.': [file, ...]} for the literal keys the site's pages and scripts use. A string literal
    of a script that equals a defined key (a key passed around as data, e.g. the navigation's) counts as a use too."""
    use = {}
    files = sorted(site.glob("*.html")) + sorted((site / "ontology").glob("*.html")) + sorted((site / "js").glob("*.js"))
    for p in files:
        rel = p.relative_to(site).as_posix()
        if rel in DICTS:
            continue
        s = p.read_text(encoding="utf-8", errors="replace")
        for k in USE_ATTR.findall(s):
            use.setdefault(k, []).append(rel)
        for _, k in USE_CALL.findall(s):
            use.setdefault(k, []).append(rel)
        if rel.endswith(".js"):
            for k in USE_LIT.findall(s):
                if k in defined and rel not in use.get(k, []):
                    use.setdefault(k, []).append(rel)
    return use


def check(site: Path, unused: bool = False, csv_out: Path | None = None, raise_on_error: bool = True) -> dict:
    rows, errors = read_dicts(site)
    e2, defined = check_entries(rows)
    errors += e2
    use = used_keys(site, frozenset(defined))
    for k, where in sorted(use.items()):
        ok = any(d.startswith(k) for d in defined) if k.endswith(".") else k in defined
        if not ok:
            errors.append(f"{sorted(set(where))}: uses the key {k!r}, which no dictionary defines")
    prefixes = [k for k in use if k.endswith(".")]
    not_used = sorted(k for k in defined if k not in use and not any(k.startswith(p) for p in prefixes))
    owners = {}
    for rel, owner, *_ in rows:
        owners[owner] = owners.get(owner, 0) + 1
    rep = {"keys": len(defined), "owners": owners, "used": len(use), "unused": len(not_used), "errors": errors}
    if unused:
        rep["unused_keys"] = not_used
    if csv_out:
        with open(csv_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["key", "file", "owner", "kind", "en", "vi", "en_one", "used_in"])
            for rel, owner, key, e, line in rows:
                hits = sorted(set(use.get(key, []) + [f for p in prefixes if key.startswith(p) for f in use[p]]))
                w.writerow([key, rel, owner, e.get("k", "text"), e.get("en", ""), e.get("vi", ""), e.get("en_one", ""), " ".join(hits)])
    if errors and raise_on_error:
        raise SystemExit("language layer dictionaries (scripts/site/i18n_check.py):\n  " + "\n  ".join(errors))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default="site", help="the site directory (default: site)")
    ap.add_argument("--csv", type=Path, help="write key, file, owner, kind, en, vi, en_one, used_in to this CSV")
    ap.add_argument("--unused", action="store_true", help="list the keys no page or script uses yet")
    a = ap.parse_args(argv)
    rep = check(Path(a.root), unused=a.unused, csv_out=a.csv, raise_on_error=False)
    print(f"i18n: {rep['keys']} keys {rep['owners']}, {rep['used']} used in the site, {rep['unused']} not used yet")
    for k in rep.get("unused_keys", []):
        print("  not used:", k)
    for e in rep["errors"]:
        print("ERROR", e)
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

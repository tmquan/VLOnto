#!/usr/bin/env python3
"""scan_secrets.py - look for strings that secret scanners (e.g. GitHub push protection) would take for credentials.

Usage: python scan_secrets.py DIR [DIR ...] [--json OUT]
Large base64 blobs (embedded fonts, WebAssembly, data-URI figures) can contain such strings by coincidence; a hit can block
a git push. Matches are printed masked (first 4 and last 2 characters) with file, pattern and byte offset; exit code 1 if
anything matches. Read-only.
"""
import json
import re
import sys
from pathlib import Path

PATTERNS = {
    "aws_access_key_id": rb"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA|ABIA|ACCA)[A-Z0-9]{16}",
    "google_api_key": rb"AIza[0-9A-Za-z_\-]{35}",
    "github_token": rb"gh[pousr]_[A-Za-z0-9]{36}",
    "github_fine_grained_pat": rb"github_pat_[A-Za-z0-9_]{82}",
    "slack_token": rb"xox[abprs]-[A-Za-z0-9\-]{10,}",
    "stripe_live_key": rb"[rs]k_live_[0-9a-zA-Z]{24}",
    "private_key_block": rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "azure_storage_key": rb"AccountKey=[A-Za-z0-9+/=]{40,}",
}
RX = {k: re.compile(v) for k, v in PATTERNS.items()}


def mask(b: bytes) -> str:
    s = b.decode("ascii", "replace")
    return s[:4] + "…" + s[-2:] + f" ({len(s)} chars)"


def main(argv):
    out_json = None
    if "--json" in argv:
        i = argv.index("--json")
        out_json = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    hits = []
    n_files = 0
    for root in map(Path, argv):
        for p in sorted(x for x in root.rglob("*") if x.is_file()):
            n_files += 1
            data = p.read_bytes()
            for name, rx in RX.items():
                for m in rx.finditer(data):
                    # 'bounded' = not part of a longer run of letters/digits; scanners mostly flag bounded candidates,
                    # but unbounded ones are listed too because detectors differ
                    a, b = m.start(), m.end()
                    left = a == 0 or not chr(data[a - 1]).isalnum()
                    right = b >= len(data) or not chr(data[b]).isalnum()
                    hits.append({"file": str(p), "pattern": name, "offset": a, "bounded": bool(left and right), "masked": mask(m.group(0))})
    by_file = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)
    nb = sum(1 for h in hits if h["bounded"])
    print(f"scanned {n_files} files in {', '.join(argv)}: {len(hits)} match(es) ({nb} bounded) in {len(by_file)} file(s)")
    for f, hs in by_file.items():
        print(f"  {f}: " + "; ".join(f"{h['pattern']}{' [bounded]' if h['bounded'] else ''} @ {h['offset']} {h['masked']}" for h in hs[:6]) + (" …" if len(hs) > 6 else ""))
    if out_json:
        out_json.write_text(json.dumps({"files": n_files, "hits": hits}, indent=1), encoding="utf-8")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

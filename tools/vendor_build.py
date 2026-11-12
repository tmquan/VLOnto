#!/usr/bin/env python3
"""vendor_build.py - reproducible vendoring of web libraries and fonts for VLOnto (run via tools/fetch_vendor.sh).

Outputs (paths relative to the repo):
  site/vendor/three/three.iife.min.js                  esbuild IIFE -> window.THREE (+ OrbitControls, TrackballControls,
                                                        CSS2DRenderer, CSS2DObject)
  site/vendor/3d-force-graph/3d-force-graph.iife.min.js esbuild IIFE -> window.ForceGraph3D ('three' = window.THREE)
  site/vendor/three-spritetext/three-spritetext.min.js  upstream UMD from the npm tarball (uses window.THREE)
  site/vendor/echarts/echarts.min.js                   upstream UMD from the npm tarball -> window.echarts
  site/vendor/oxigraph/oxigraph.iife.min.js            esbuild IIFE -> window.oxigraph(+Ready); the wasm is embedded as
                                                        zlib (fflate) + lowercase base32 (a-z2-7), never base64
  site/vendor/licenses/*, THIRD_PARTY_LICENSES.md, README.md
  typst/fonts/*.ttf + OFL texts                        pinned upstream font files (sha256 in the lock)
  site/fonts/*.woff2, fonts.css, fonts-embedded.css, embedded/*.css, OFL texts
                                                        (+ web-only Latin + Vietnamese subsets of Libertinus Sans from
                                                        the Libertinus release zip, the figure font of the paper)
  tools/vendor.lock.json                               package, version, file, sha256, licence for every output
Steps: npm ci --ignore-scripts from tools/vendor-build/package-lock.json (npm verifies every tarball's sha512);
every lockfile integrity is compared with the npm registry metadata; top-level tarballs are downloaded again
and their sha512 checked independently; esbuild bundles; fonts fetched from fixed commits/tags. Every output is
scanned for credential-like patterns (CRED_PATTERNS: AWS key IDs, Google API keys, GitHub/HF/OpenAI/NVIDIA/Slack
tokens, PEM private keys) that secret scanners would flag; any match fails the build and --check-repo.
Modes: default  - rebuild in ROOT/build/vendor-stage, require byte-identical sha256 vs vendor.lock.json, then
                  sync into the repo (nothing in the repo changes if anything differs)
       --update-lock - update tools/vendor-build/package-lock.json from package.json (npm install
                  --package-lock-only on top of the existing lock, so unchanged pins keep their resolutions),
                  rebuild, sync, rewrite vendor.lock.json
       --check-repo  - only compare the files currently in the repo with vendor.lock.json (+ credential scan)
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VB = HERE / "vendor-build"
LOCK = HERE / "vendor.lock.json"
REGISTRY = "https://registry.npmjs.org"

# Patterns that GitHub push protection / Hugging Face secret scanning report. Random base64 can contain them by
# chance (the old base64 wasm in oxigraph.iife.min.js had 5 AWS-key-ID look-alikes), so no output may match.
CRED_PATTERNS = {
    "aws_access_key_id": rb"(?:AK|AS)IA[0-9A-Z]{16}",   # written so this file itself has no 4-letter AWS prefix
    "google_api_key": rb"AIza[0-9A-Za-z_\-]{35}",
    "github_token": rb"gh[pousr]_[A-Za-z0-9]{36}",
    "github_pat": rb"github_pat_[A-Za-z0-9_]{22,}",
    "huggingface_token": rb"hf_[A-Za-z0-9]{34}",
    "openai_style_key": rb"sk-[A-Za-z0-9_\-]{20,}",
    "nvidia_api_key": rb"nvapi-[A-Za-z0-9_\-]{20,}",
    "slack_token": rb"xox[baprs]-[A-Za-z0-9-]{10,}",
    "pem_private_key": rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}
CRED_RX = {k: re.compile(v) for k, v in CRED_PATTERNS.items()}


def credential_scan(paths) -> list[str]:
    hits = []
    for p in paths:
        data = Path(p).read_bytes()
        for name, rx in CRED_RX.items():
            for m in rx.finditer(data):
                hits.append(f"{p}: {name} at byte {m.start()}")
    return hits


def pins() -> dict:
    out = {}
    for line in (HERE / "versions.lock").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(\"[^\"]*\"|\S*)", line)
        if m:
            out[m.group(1)] = m.group(2).strip('"')
    return out


P = pins()
GF = f"https://raw.githubusercontent.com/google/fonts/{P['FONTS_GOOGLE_COMMIT']}"
NOTO = f"https://raw.githubusercontent.com/notofonts/notofonts.github.io/{P['FONTS_NOTO_COMMIT']}"
JB_ZIP = P["JETBRAINS_MONO_URL"]
OXIGRAPH_LICENSES = {
    "oxigraph-LICENSE-MIT.txt": f"https://raw.githubusercontent.com/oxigraph/oxigraph/v{P['NPM_OXIGRAPH']}/LICENSE-MIT",
    "oxigraph-LICENSE-APACHE.txt": f"https://raw.githubusercontent.com/oxigraph/oxigraph/v{P['NPM_OXIGRAPH']}/LICENSE-APACHE",
}
# (file in typst/fonts, source). "zip:" = member of the JetBrains Mono release zip.
FONT_FILES = [
    ("BeVietnamPro-Regular.ttf", f"{GF}/ofl/bevietnampro/BeVietnamPro-Regular.ttf"),
    ("BeVietnamPro-Italic.ttf", f"{GF}/ofl/bevietnampro/BeVietnamPro-Italic.ttf"),
    ("BeVietnamPro-Medium.ttf", f"{GF}/ofl/bevietnampro/BeVietnamPro-Medium.ttf"),
    ("BeVietnamPro-SemiBold.ttf", f"{GF}/ofl/bevietnampro/BeVietnamPro-SemiBold.ttf"),
    ("BeVietnamPro-Bold.ttf", f"{GF}/ofl/bevietnampro/BeVietnamPro-Bold.ttf"),
    ("BeVietnamPro-BoldItalic.ttf", f"{GF}/ofl/bevietnampro/BeVietnamPro-BoldItalic.ttf"),
    ("NotoSerif-Regular.ttf", f"{NOTO}/fonts/NotoSerif/hinted/ttf/NotoSerif-Regular.ttf"),
    ("NotoSerif-Italic.ttf", f"{NOTO}/fonts/NotoSerif/hinted/ttf/NotoSerif-Italic.ttf"),
    ("NotoSerif-Bold.ttf", f"{NOTO}/fonts/NotoSerif/hinted/ttf/NotoSerif-Bold.ttf"),
    ("NotoSerif-BoldItalic.ttf", f"{NOTO}/fonts/NotoSerif/hinted/ttf/NotoSerif-BoldItalic.ttf"),
    ("NotoSansSymbols2-Regular.ttf", f"{NOTO}/fonts/NotoSansSymbols2/hinted/ttf/NotoSansSymbols2-Regular.ttf"),
    ("NotoSansMath-Regular.ttf", f"{NOTO}/fonts/NotoSansMath/hinted/ttf/NotoSansMath-Regular.ttf"),
    ("JetBrainsMonoNL-Regular.ttf", "zip:fonts/ttf/JetBrainsMonoNL-Regular.ttf"),
    ("JetBrainsMonoNL-Italic.ttf", "zip:fonts/ttf/JetBrainsMonoNL-Italic.ttf"),
    ("JetBrainsMonoNL-Bold.ttf", "zip:fonts/ttf/JetBrainsMonoNL-Bold.ttf"),
    ("JetBrainsMonoNL-BoldItalic.ttf", "zip:fonts/ttf/JetBrainsMonoNL-BoldItalic.ttf"),
]
FONT_LICENSES = [
    ("OFL-BeVietnamPro.txt", f"{GF}/ofl/bevietnampro/OFL.txt"),
    ("OFL-Noto.txt", f"{NOTO}/fonts/LICENSE"),
    ("OFL-JetBrainsMono.txt", "zip:OFL.txt"),
]
# web subsets for the symbol fallbacks (Typst always gets the full fonts)
SUBSETS = {
    "NotoSansSymbols2-Regular.ttf": [(0x2190, 0x21FF), (0x2300, 0x23FF), (0x2460, 0x24FF), (0x25A0, 0x25FF),
                                     (0x2600, 0x26FF), (0x2700, 0x27BF), (0x2B00, 0x2BFF)],
    "NotoSansMath-Regular.ttf": [(0x00B1, 0x00B1), (0x00D7, 0x00D7), (0x00F7, 0x00F7), (0x2190, 0x21FF), (0x2200, 0x22FF),
                                 (0x2300, 0x23FF), (0x27C0, 0x27FF), (0x2900, 0x2AFF)],
}
# "VLOnto Math Symbols" = the Noto Sans Math subset restricted to arrows + mathematical operators. It comes first
# in the serif stack: Noto Serif lacks ≠ but has "=" and U+0338, and browsers (like HarfBuzz in Typst) then draw ≠
# by decomposition with a misplaced overlay instead of falling back. Typst uses the same routing via `covers`.
ROUTED = {"family": "VLOnto Math Symbols", "file": "NotoSansMath-Regular.ttf", "ranges": [(0x2190, 0x21FF), (0x2200, 0x22FF)]}
# Web-only faces (no Typst copy): Libertinus Sans, the figure font of the VLOnto paper (arXiv:2611.11426), for the
# labels, legends and panel headings of the 3D views. "libzip:" = member of the Libertinus release zip (sha256-pinned).
LIB_ZIP = P["LIBERTINUS_URL"]
LIB_DIR = f"Libertinus-{P['LIBERTINUS_VERSION']}"
WEB_FONT_FILES = [
    ("LibertinusSans-Regular.ttf", f"libzip:{LIB_DIR}/static/TTF/LibertinusSans-Regular.ttf"),
    ("LibertinusSans-Italic.ttf", f"libzip:{LIB_DIR}/static/TTF/LibertinusSans-Italic.ttf"),
    ("LibertinusSans-Bold.ttf", f"libzip:{LIB_DIR}/static/TTF/LibertinusSans-Bold.ttf"),
]
WEB_FONT_LICENSES = [("OFL-Libertinus.txt", f"libzip:{LIB_DIR}/OFL.txt")]
# Latin + Vietnamese: the Google Fonts "latin" and "vietnamese" subsets plus Latin Extended-A and the four arrows
LATIN_VI = [(0x0000, 0x00FF), (0x0100, 0x017F), (0x01A0, 0x01A1), (0x01AF, 0x01B0), (0x02BB, 0x02BC), (0x02C6, 0x02C6),
            (0x02DA, 0x02DA), (0x02DC, 0x02DC), (0x0300, 0x0304), (0x0308, 0x0309), (0x0323, 0x0323), (0x0329, 0x0329),
            (0x1EA0, 0x1EF9), (0x2000, 0x206F), (0x20AB, 0x20AC), (0x2122, 0x2122), (0x2190, 0x2193), (0x2212, 0x2212),
            (0x2215, 0x2215), (0xFEFF, 0xFEFF), (0xFFFD, 0xFFFD)]
SUBSETS.update({fname: LATIN_VI for fname, _ in WEB_FONT_FILES})
STACKS = {
    "--vlo-font-sans": '"Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif',
    "--vlo-font-serif": '"VLOnto Math Symbols", "Noto Serif", "Noto Sans Symbols 2", "Noto Sans Math", serif',
    "--vlo-font-mono": '"JetBrains Mono NL", "Noto Sans Symbols 2", "Noto Sans Math", monospace',
    "--vlo-font-paper": '"Libertinus Sans", "Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif',
}
EMBED_GROUPS = {"be-vietnam-pro": "Be Vietnam Pro", "noto-serif": "Noto Serif",
                "jetbrains-mono-nl": "JetBrains Mono NL",
                "symbols": ("Noto Sans Symbols 2", "Noto Sans Math", "VLOnto Math Symbols"),
                "libertinus-sans": "Libertinus Sans"}
# font section of site/vendor/THIRD_PARTY_LICENSES.md: (families, source, licence text in site/fonts)
FONT_NOTICES = [
    ("Be Vietnam Pro", f"google/fonts @ {P['FONTS_GOOGLE_COMMIT'][:8]}", "OFL-BeVietnamPro.txt"),
    ("Noto Serif, Noto Sans Symbols 2 (subset), Noto Sans Math (subset)",
     f"notofonts/notofonts.github.io @ {P['FONTS_NOTO_COMMIT'][:8]}", "OFL-Noto.txt"),
    ("JetBrains Mono NL", f"JetBrains Mono {P['JETBRAINS_MONO_VERSION']} release", "OFL-JetBrainsMono.txt"),
    ("Libertinus Sans (Regular, Italic, Bold; Latin + Vietnamese subset)",
     f"Libertinus {P['LIBERTINUS_VERSION']} release, github.com/alerque/libertinus", "OFL-Libertinus.txt"),
]


def font_notice_md() -> list[str]:
    md = ["", "## Web fonts in site/fonts", "",
          "SIL Open Font License 1.1. The woff2 files and the data-URI CSS in site/fonts/embedded are made by",
          "tools/fetch_vendor.sh (sources and sha256 in tools/vendor.lock.json).", "",
          "| family | source | licence text |", "|---|---|---|"]
    return md + [f"| {fam} | {src} | ../fonts/{lic} |" for fam, src, lic in FONT_NOTICES]


def log(*a):
    print(*a, flush=True)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def http_get(url: str, cache: Path | None = None, tries: int = 3) -> bytes:
    if cache and cache.exists():
        return cache.read_bytes()
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as r:
                data = r.read()
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
            return data
        except Exception as e:  # retry
            last = e
    raise SystemExit(f"download failed: {url}: {last}")


def run(cmd, cwd=None, env=None):
    log("  $", " ".join(map(str, cmd)))
    r = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if r.returncode != 0:
        log(r.stdout[-4000:], r.stderr[-4000:])
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}")
    return r.stdout


# ------------------------------------------------------------------------------------------------ npm
def npm_stage(work: Path, update_lock: bool) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    for f in ("package.json", "build.mjs"):
        shutil.copy2(VB / f, work / f)
    shutil.rmtree(work / "entries", ignore_errors=True)
    shutil.copytree(VB / "entries", work / "entries")
    lock_src = VB / "package-lock.json"
    if update_lock:
        # start from the existing lock so that unchanged pins keep their resolved versions; npm only adds or
        # changes what package.json changed (a fresh resolve could silently move transitive dependencies)
        if lock_src.exists():
            shutil.copy2(lock_src, work / "package-lock.json")
        else:
            (work / "package-lock.json").unlink(missing_ok=True)
        run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=work)
        shutil.copy2(work / "package-lock.json", lock_src)
        log("  wrote", lock_src.relative_to(REPO))
    elif lock_src.exists():
        shutil.copy2(lock_src, work / "package-lock.json")
    else:
        raise SystemExit("tools/vendor-build/package-lock.json is missing; run tools/fetch_vendor.sh --update-lock")
    shutil.rmtree(work / "node_modules", ignore_errors=True)
    run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=work)
    return json.loads((work / "package-lock.json").read_text())


def registry_check(lock: dict) -> list[dict]:
    items = [(k.split("node_modules/")[-1], v) for k, v in lock["packages"].items() if k]

    def one(item):
        name, v = item
        meta = json.loads(http_get(f"{REGISTRY}/{urllib.parse.quote(name, safe='@')}/{v['version']}"))
        reg = meta.get("dist", {}).get("integrity")
        return {"name": name, "version": v["version"], "license": v.get("license") or meta.get("license"),
                "integrity": v.get("integrity"), "registry_integrity_match": reg == v.get("integrity"),
                "resolved": v.get("resolved"), "optional": bool(v.get("optional")), "dev": bool(v.get("dev"))}

    with cf.ThreadPoolExecutor(16) as ex:
        res = list(ex.map(one, items))
    return sorted(res, key=lambda r: (r["name"], r["version"]))


def verified_tarball(entry: dict, cache_dir: Path) -> tarfile.TarFile:
    url = entry["resolved"]
    data = http_get(url, cache_dir / Path(urllib.parse.urlparse(url).path).name)
    algo, b64 = entry["integrity"].split("-", 1)
    got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if got != b64:
        raise SystemExit(f"INTEGRITY MISMATCH {entry['name']}@{entry['version']}: {algo} {got} != {b64}")
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


LIC_RE = re.compile(r"^(licen[cs]e|copying|notice)(\.(md|txt|markdown))?$", re.I)


def license_files(pkg_dir: Path) -> list[Path]:
    return sorted(p for p in pkg_dir.iterdir() if p.is_file() and LIC_RE.match(p.name))


# ------------------------------------------------------------------------------------------------ fonts
def font_meta(path: Path) -> dict:
    from fontTools.ttLib import TTFont
    f = TTFont(str(path), lazy=True)
    name = f["name"]
    fam = name.getDebugName(16) or name.getDebugName(1)
    sub = name.getDebugName(17) or name.getDebugName(2)
    italic = bool(f["OS/2"].fsSelection & 1) or bool(f["head"].macStyle & 2)
    return {"family": fam, "style_name": sub, "weight": int(f["OS/2"].usWeightClass), "italic": italic,
            "version": (name.getDebugName(5) or "").split(";")[0], "postscript_name": name.getDebugName(6)}


def to_woff2(src: Path, dst: Path, ranges=None) -> list[int]:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    if ranges is None:
        f = TTFont(str(src), recalcTimestamp=False)
        f.flavor = "woff2"
        f.save(str(dst))
        return sorted((f.getBestCmap() or {}).keys())
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.recalc_timestamp = False
    font = subset.load_font(str(src), opts)
    s = subset.Subsetter(opts)
    s.populate(unicodes=[cp for lo, hi in ranges for cp in range(lo, hi + 1)])
    s.subset(font)
    subset.save_font(font, str(dst), opts)
    return sorted((font.getBestCmap() or {}).keys())


def unicode_range(cps: list[int]) -> str:
    out, i = [], 0
    while i < len(cps):
        j = i
        while j + 1 < len(cps) and cps[j + 1] == cps[j] + 1:
            j += 1
        out.append(f"U+{cps[i]:04X}" if i == j else f"U+{cps[i]:04X}-{cps[j]:04X}")
        i = j + 1
    return ", ".join(out)


def font_face(meta: dict, src: str, urange: str | None, weight: str | None = None) -> str:
    # symbol-fallback subsets serve every weight; text-family subsets (Libertinus) pass their own weight
    weight = weight or ("100 900" if urange else str(meta["weight"]))
    lines = [f'  font-family: "{meta["family"]}";', f'  font-style: {"italic" if meta["italic"] else "normal"};',
             f"  font-weight: {weight};", "  font-display: swap;", f'  src: url("{src}") format("woff2");']
    if urange:
        lines.append(f"  unicode-range: {urange};")
    return "@font-face {\n" + "\n".join(lines) + "\n}\n"


def build_fonts(stage: Path, cache: Path) -> list[dict]:
    tdir, sdir = stage / "typst/fonts", stage / "site/fonts"
    tdir.mkdir(parents=True, exist_ok=True)
    (sdir / "embedded").mkdir(parents=True, exist_ok=True)
    zbytes = http_get(JB_ZIP, cache / Path(urllib.parse.urlparse(JB_ZIP).path).name)
    if sha256(zbytes) != P["JETBRAINS_MONO_SHA256"]:
        raise SystemExit(f"JetBrains Mono zip sha256 mismatch: {sha256(zbytes)}")
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    lzbytes = http_get(LIB_ZIP, cache / Path(urllib.parse.urlparse(LIB_ZIP).path).name)
    if sha256(lzbytes) != P["LIBERTINUS_SHA256"]:
        raise SystemExit(f"Libertinus zip sha256 mismatch: {sha256(lzbytes)}")
    lz = zipfile.ZipFile(io.BytesIO(lzbytes))
    wdir = stage / "web-font-src"          # sources of the web-only faces (not synced into the repo)
    wdir.mkdir(parents=True, exist_ok=True)
    entries = []

    def get(src: str, cache_name: str) -> bytes:
        if src.startswith("zip:"):
            return zf.read(src[4:])
        if src.startswith("libzip:"):
            return lz.read(src[7:])
        return http_get(src, cache / cache_name)

    def src_url(src: str) -> str:
        if src.startswith("zip:"):
            return JB_ZIP + "!" + src[4:]
        if src.startswith("libzip:"):
            return LIB_ZIP + "!" + src[7:]
        return src

    for fname, src in FONT_FILES:
        data = get(src, fname)
        (tdir / fname).write_bytes(data)
        m = font_meta(tdir / fname)
        entries.append({"file": f"typst/fonts/{fname}", "sha256": sha256(data), "bytes": len(data),
                        "source": src_url(src),
                        "package": m["family"], "version": m["version"], "licence": "OFL-1.1", "font": m})
    for fname, src in FONT_LICENSES:
        data = get(src, fname)
        for d in (tdir, sdir):
            (d / fname).write_bytes(data)
        entries.append({"file": f"typst/fonts/{fname}", "sha256": sha256(data), "bytes": len(data),
                        "source": src_url(src),
                        "package": fname.removesuffix(".txt"), "version": "", "licence": "OFL-1.1"})
        entries.append({"file": f"site/fonts/{fname}", "sha256": sha256(data), "bytes": len(data),
                        "source": "copy of typst/fonts/" + fname, "package": fname.removesuffix(".txt"),
                        "version": "", "licence": "OFL-1.1"})
    for fname, src in WEB_FONT_LICENSES:
        data = get(src, fname)
        (sdir / fname).write_bytes(data)
        entries.append({"file": f"site/fonts/{fname}", "sha256": sha256(data), "bytes": len(data),
                        "source": src_url(src), "package": fname.removesuffix(".txt"), "version": "",
                        "licence": "OFL-1.1"})
    web_src = {}
    for fname, src in WEB_FONT_FILES:
        data = get(src, fname)
        (wdir / fname).write_bytes(data)
        web_src[fname] = (src_url(src), sha256(data))
    # web fonts: woff2 (full for text families, subset for the symbol fallbacks and the web-only Libertinus Sans)
    faces_url, faces_by_family = [], {}
    for fname, _ in FONT_FILES + WEB_FONT_FILES:
        ttf = (wdir if fname in web_src else tdir) / fname
        m = font_meta(ttf)
        ranges = SUBSETS.get(fname)
        wname = fname.replace(".ttf", ".subset.woff2" if ranges else ".woff2")
        cps = to_woff2(ttf, sdir / wname, ranges)
        ur = unicode_range(cps) if ranges else None
        wt = str(m["weight"]) if fname in web_src else None
        faces_url.append(font_face(m, wname, ur, wt))
        data = (sdir / wname).read_bytes()
        datauri = "data:font/woff2;base64," + base64.b64encode(data).decode()
        faces_by_family.setdefault(m["family"], []).append(font_face(m, datauri, ur, wt))
        if fname in web_src:
            entries.append({"file": f"site/fonts/{wname}", "sha256": sha256(data), "bytes": len(data),
                            "source": f"fontTools subset of {web_src[fname][0]}", "source_sha256": web_src[fname][1],
                            "package": m["family"], "version": m["version"], "licence": "OFL-1.1",
                            "unicode_range": ur})
            continue
        entries.append({"file": f"site/fonts/{wname}", "sha256": sha256(data), "bytes": len(data),
                        "source": f"fontTools {'subset' if ranges else 'woff2'} of typst/fonts/{fname}",
                        "package": m["family"], "version": m["version"], "licence": "OFL-1.1",
                        "unicode_range": ur})
        if fname == ROUTED["file"]:
            rset = {cp for lo, hi in ROUTED["ranges"] for cp in range(lo, hi + 1)}
            rur = unicode_range([cp for cp in cps if cp in rset])
            alias = {**m, "family": ROUTED["family"]}
            faces_url.append(font_face(alias, wname, rur))
            faces_by_family.setdefault(ROUTED["family"], []).append(font_face(alias, datauri, rur))
    root_vars = ":root {\n" + "".join(f"  {k}: {v};\n" for k, v in STACKS.items()) + "}\n"
    head = ("/* generated by tools/fetch_vendor.sh - do not edit. Fonts under the SIL Open Font License 1.1\n"
            "   (OFL-*.txt). Use the stacks: font-family: var(--vlo-font-sans|serif|mono). */\n")
    css = head + "".join(faces_url) + root_vars
    (sdir / "fonts.css").write_text(css, encoding="utf-8")
    files = {"site/fonts/fonts.css": css}
    agg = [head.replace("*/", "   Embedded (data: URI) variant: works from file:// in any directory. */")]
    for slug, fam in EMBED_GROUPS.items():
        fams = fam if isinstance(fam, tuple) else (fam,)
        body = head + "".join(face for f in fams for face in faces_by_family.get(f, []))
        (sdir / "embedded" / f"{slug}.css").write_text(body, encoding="utf-8")
        files[f"site/fonts/embedded/{slug}.css"] = body
        agg.append(f'@import url("embedded/{slug}.css");\n')
    agg_css = "".join(agg) + root_vars
    (sdir / "fonts-embedded.css").write_text(agg_css, encoding="utf-8")
    files["site/fonts/fonts-embedded.css"] = agg_css
    for path, text in files.items():
        b = text.encode("utf-8")
        entries.append({"file": path, "sha256": sha256(b), "bytes": len(b), "source": "generated @font-face CSS",
                        "package": "fonts", "version": "", "licence": "OFL-1.1"})
    return entries


# ------------------------------------------------------------------------------------------------ main build
def build_all(root: Path, stage: Path, update_lock: bool, only: str | None) -> dict:
    cache = root / "downloads" / "vendor-cache"
    work = root / "build" / "vendor-build"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    result = {"schema": 1, "generated_by": "tools/fetch_vendor.sh (tools/vendor_build.py)", "tools": {},
              "npm_packages": [], "files": []}
    import fontTools
    result["tools"]["fonttools"] = fontTools.version
    try:
        import brotli
        result["tools"]["brotli"] = getattr(brotli, "__version__", "?")
    except ImportError:
        pass
    if only in (None, "npm"):
        log("== npm: install from lock")
        lock = npm_stage(work, update_lock)
        result["tools"]["node"] = run(["node", "--version"]).strip()
        result["tools"]["npm"] = run(["npm", "--version"]).strip()
        log("== npm: compare every lockfile integrity with the registry")
        pk = registry_check(lock)
        bad = [f"{p['name']}@{p['version']}" for p in pk if not p["registry_integrity_match"]]
        log(f"  {len(pk)} packages, {len(pk) - len(bad)} match the registry sha512" + (f"; MISMATCH: {bad}" if bad else ""))
        if bad:
            raise SystemExit("registry integrity mismatch")
        result["npm_packages"] = pk
        top = {p["name"]: p for p in pk if p["name"] in ("three", "3d-force-graph", "three-spritetext", "oxigraph", "echarts",
                                                         "esbuild", "fflate")}
        for name, want in (("three", P["NPM_THREE"]), ("3d-force-graph", P["NPM_3D_FORCE_GRAPH"]),
                           ("three-spritetext", P["NPM_THREE_SPRITETEXT"]), ("oxigraph", P["NPM_OXIGRAPH"]),
                           ("echarts", P["NPM_ECHARTS"]), ("esbuild", P["ESBUILD_VERSION"]), ("fflate", P["NPM_FFLATE"])):
            if top[name]["version"] != want:
                raise SystemExit(f"{name}: lock has {top[name]['version']}, versions.lock pins {want}")
        dup_three = [k for k in lock["packages"] if k.endswith("node_modules/three") and k != "node_modules/three"]
        if dup_three:
            raise SystemExit(f"nested three copies in the lock: {dup_three}")
        vend = stage / "site/vendor"
        lic = vend / "licenses"
        lic.mkdir(parents=True)
        log("== esbuild IIFE bundles")
        out = run(["node", "build.mjs", str(vend)], cwd=work)
        log("  " + out.strip().replace("\n", "\n  "))
        meta = json.loads((vend / "build-meta.json").read_text())
        (vend / "build-meta.json").unlink()
        result["tools"]["esbuild"] = meta["esbuild"]
        log("== upstream UMD files from sha512-verified tarballs")
        ups = {"three-spritetext": ["dist/three-spritetext.min.js"], "echarts": ["dist/echarts.min.js"]}
        for name, members in ups.items():
            tf = verified_tarball(top[name], cache)
            for mbr in members:
                data = tf.extractfile("package/" + mbr).read()
                dst = vend / name / Path(mbr).name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                result["files"].append({"file": f"site/vendor/{name}/{dst.name}", "sha256": sha256(data), "bytes": len(data),
                                        "package": name, "version": top[name]["version"], "licence": top[name]["license"],
                                        "source": f"{top[name]['resolved']} -> package/{mbr}",
                                        "tarball_integrity": top[name]["integrity"]})
        for name in ("three", "3d-force-graph", "oxigraph"):  # explicit check of the bundle roots too
            verified_tarball(top[name], cache)
        log("  tarball sha512 verified: three, 3d-force-graph, three-spritetext, oxigraph, echarts")
        bundle_pkgs = {"three/three.iife.min.js": ("three", meta["bundles"]["three"]["packages"]),
                       "3d-force-graph/3d-force-graph.iife.min.js": ("3d-force-graph", meta["bundles"]["3d-force-graph"]["packages"]),
                       "oxigraph/oxigraph.iife.min.js": ("oxigraph", meta["bundles"]["oxigraph"]["packages"]),
                       "three-spritetext/three-spritetext.min.js": ("three-spritetext", ["three-spritetext"]),
                       "echarts/echarts.min.js": ("echarts", ["echarts", "zrender", "tslib"])}
        vers = {p["name"]: p for p in pk}
        for rel, (main_pkg, pkgs) in bundle_pkgs.items():
            data = (vend / rel).read_bytes()
            entry = next((e for e in result["files"] if e["file"] == f"site/vendor/{rel}"), None)
            info = {"bundled_packages": [f"{n}@{vers[n]['version']} ({vers[n]['license']})" for n in pkgs if n in vers]}
            if main_pkg == "oxigraph" and rel.startswith("oxigraph/"):
                ew = meta["bundles"]["oxigraph"].get("embedded_wasm")
                if not ew:
                    raise SystemExit("oxigraph bundle: build.mjs did not report the embedded wasm")
                info["embedded_wasm"] = ew
                log(f"  oxigraph wasm {ew['wasm_bytes']:,} B -> deflated {ew['deflated_bytes']:,} B -> "
                    f"{ew['payload_chars']:,} lowercase base32 chars; bundle {len(data):,} B")
            if entry is None:
                result["files"].append({"file": f"site/vendor/{rel}", "sha256": sha256(data), "bytes": len(data),
                                        "package": main_pkg, "version": vers[main_pkg]["version"],
                                        "licence": vers[main_pkg]["license"],
                                        "source": f"esbuild {meta['esbuild']} IIFE (tools/vendor-build/build.mjs)", **info})
            else:
                entry.update(info)
        log("== licences")
        all_pkgs = sorted({n for _, (m, pkgs) in bundle_pkgs.items() for n in pkgs})
        rows = []
        for n in all_pkgs:
            v = vers.get(n)
            if not v:
                continue
            files = license_files(work / "node_modules" / n)
            texts = []
            for f in files:
                dst = lic / f"{n.replace('/', '__')}-{f.name}"
                if not f.name.lower().endswith((".txt", ".md")):
                    dst = dst.with_name(dst.name + ".txt")
                shutil.copy2(f, dst)
                texts.append(dst.name)
            if n == "oxigraph":
                for fname, url in OXIGRAPH_LICENSES.items():
                    (lic / fname).write_bytes(http_get(url, cache / fname))
                    texts.append(fname)
            rows.append((n, v["version"], v["license"], texts))
        md = ["# Third-party licences of site/vendor", "",
              "Generated by tools/fetch_vendor.sh. Each vendored file and the npm packages compiled into it:", ""]
        for rel, (main_pkg, pkgs) in bundle_pkgs.items():
            md.append(f"- `{rel}`: " + ", ".join(f"{n}@{vers[n]['version']}" for n in pkgs if n in vers))
        md += ["", "| package | version | licence | licence text |", "|---|---|---|---|"]
        for n, ver, l, texts in rows:
            md.append(f"| {n} | {ver} | {l} | {', '.join('licenses/' + t for t in texts) or '(none shipped; see npm metadata)'} |")
        md += font_notice_md()
        (vend / "THIRD_PARTY_LICENSES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        (vend / "README.md").write_text(VENDOR_README, encoding="utf-8")
        for p in sorted(lic.iterdir()) + [vend / "THIRD_PARTY_LICENSES.md", vend / "README.md"]:
            b = p.read_bytes()
            result["files"].append({"file": str(p.relative_to(stage)), "sha256": sha256(b), "bytes": len(b),
                                    "package": "licences", "version": "", "licence": "-", "source": "collected"})
    if only in (None, "fonts"):
        log("== fonts")
        result["files"] += build_fonts(stage, cache / "fonts")
    result["files"].sort(key=lambda e: e["file"])
    log("== credential-pattern scan of every output")
    hits = credential_scan(stage / e["file"] for e in result["files"])
    if hits:
        raise SystemExit("credential-like patterns in vendored outputs (secret scanners would flag them):\n  "
                         + "\n  ".join(hits[:20]))
    log(f"  0 matches in {len(result['files'])} files ({len(CRED_PATTERNS)} patterns)")
    return result


VENDOR_README = """# site/vendor - classic-script builds (work from file:// and http://)

Generated by `tools/fetch_vendor.sh`; checksums in `tools/vendor.lock.json`. Load order matters:

```html
<meta charset="utf-8">
<link rel="stylesheet" href="fonts/fonts.css">                        <!-- Be Vietnam Pro, Noto Serif, JetBrains Mono NL + symbol fallbacks -->
<script src="vendor/three/three.iife.min.js"></script>                 <!-- window.THREE (r187 + OrbitControls, TrackballControls, CSS2DRenderer) -->
<script src="vendor/three-spritetext/three-spritetext.min.js"></script> <!-- window.SpriteText, uses window.THREE -->
<script src="vendor/3d-force-graph/3d-force-graph.iife.min.js"></script> <!-- window.ForceGraph3D, uses window.THREE -->
<script src="vendor/echarts/echarts.min.js"></script>                  <!-- window.echarts (independent of THREE) -->
<script src="vendor/oxigraph/oxigraph.iife.min.js"></script>           <!-- window.oxigraph + window.oxigraphReady (Promise) -->
<script src="data/graph.js"></script>                                  <!-- window.VLONTO.graph (tools/json2js.py) -->
<script>
  const graph = new ForceGraph3D(document.getElementById('g')).graphData(window.VLONTO.graph)
    .nodeThreeObject(n => new SpriteText(n.label));        // SpriteText and the graph share one THREE
  oxigraphReady.then(ox => { const store = new ox.Store(); /* store.load(ttl, {format: 'text/turtle'}) */ });
</script>
```

Never use `type="module"`, import maps, `fetch()`/XHR, Workers from files or `WebAssembly.instantiateStreaming`:
Chrome blocks all of them for file:// pages. Keep HTML pages in the site root and assets in subfolders
(Firefox only loads file:// fonts from the page's folder or below).

`oxigraph/oxigraph.iife.min.js` carries the Oxigraph wasm as one lowercase string (zlib-deflated with fflate, then
RFC 4648 base32 in lower case without padding, alphabet a-z2-7). When the script loads it is decoded, inflated
(native `DecompressionStream('deflate')` where available, else the bundled fflate inflater) and instantiated from
bytes; `window.oxigraphTiming` reports the decode/inflate/instantiate times and the inflater used. A payload without
upper-case letters, '_' or '-' cannot contain the credential-like patterns (AWS access-key IDs, GitHub, Hugging Face,
OpenAI-style, NVIDIA or Slack tokens) that secret scanners flag in base64; `tools/fetch_vendor.sh` fails if any
vendored file contains one.
"""


def compare(new: dict, old: dict) -> list[str]:
    diffs = []
    o = {e["file"]: e for e in old.get("files", [])}
    n = {e["file"]: e for e in new.get("files", [])}
    for f in sorted(set(o) | set(n)):
        if f not in n:
            diffs.append(f"missing in rebuild: {f}")
        elif f not in o:
            diffs.append(f"new file not in lock: {f}")
        elif o[f]["sha256"] != n[f]["sha256"]:
            diffs.append(f"sha256 differs: {f}")
    op = {(p["name"], p["version"]): p["integrity"] for p in old.get("npm_packages", [])}
    np_ = {(p["name"], p["version"]): p["integrity"] for p in new.get("npm_packages", [])}
    if new.get("npm_packages") and op != np_:
        diffs.append("npm package set/integrity differs from the lock")
    return diffs


def check_repo(lock: dict) -> list[str]:
    bad = []
    for e in lock["files"]:
        p = REPO / e["file"]
        if not p.exists():
            bad.append(f"missing: {e['file']}")
        elif sha256(p.read_bytes()) != e["sha256"]:
            bad.append(f"modified: {e['file']}")
    present = [REPO / e["file"] for e in lock["files"] if (REPO / e["file"]).exists()]
    bad += [f"credential-like pattern: {h}" for h in credential_scan(present)]
    return bad


def sync(stage: Path, result: dict):
    for top in ("site/vendor", "site/fonts", "typst/fonts"):
        if (stage / top).exists():
            shutil.rmtree(REPO / top, ignore_errors=True)
            shutil.copytree(stage / top, REPO / top)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=REPO.parent)
    ap.add_argument("--update-lock", action="store_true")
    ap.add_argument("--check-repo", action="store_true")
    ap.add_argument("--only", choices=["npm", "fonts"])
    a = ap.parse_args(argv)
    if a.check_repo:
        bad = check_repo(json.loads(LOCK.read_text()))
        log("\n".join(bad) or f"repo files match {LOCK.name}; 0 credential-like patterns in them")
        return 1 if bad else 0
    stage = a.root / "build" / "vendor-stage"
    result = build_all(a.root, stage, a.update_lock, a.only)
    if a.update_lock:
        if a.only and LOCK.exists():  # merge partial rebuild into the existing lock
            old = json.loads(LOCK.read_text())
            keep = [e for e in old["files"] if not e["file"].startswith(
                ("site/vendor",) if a.only == "npm" else ("site/fonts", "typst/fonts"))]
            result["files"] = sorted(keep + result["files"], key=lambda e: e["file"])
            if a.only == "fonts":
                result["npm_packages"] = old.get("npm_packages", [])
                result["tools"] = {**old.get("tools", {}), **result["tools"]}
        sync(stage, result)
        LOCK.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"UPDATED {LOCK.relative_to(REPO)}: {len(result['files'])} files, {len(result['npm_packages'])} npm packages")
        return 0
    if not LOCK.exists():
        raise SystemExit("tools/vendor.lock.json missing: run with --update-lock first")
    old = json.loads(LOCK.read_text())
    if a.only:
        pref = ("site/vendor",) if a.only == "npm" else ("site/fonts", "typst/fonts")
        old = {**old, "files": [e for e in old["files"] if e["file"].startswith(pref)]}
        if a.only == "fonts":
            old["npm_packages"] = []
    diffs = compare(result, old)
    if diffs:
        log("REBUILD DIFFERS FROM vendor.lock.json (repo left untouched):\n  " + "\n  ".join(diffs[:50]))
        return 1
    sync(stage, result)
    log(f"VERIFIED: rebuild is byte-identical to vendor.lock.json ({len(result['files'])} files) and synced into the repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())

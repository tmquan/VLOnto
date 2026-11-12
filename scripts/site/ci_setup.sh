#!/usr/bin/env bash
# ci_setup.sh - install what the website checks need, from the repo's own pins, on a CI runner (GitHub Actions
# ubuntu-24.04) or any Linux x86_64 machine that has Python 3.12; the build node keeps using tools/setup_tools.sh.
#   ROOT/envs/web/            venv of the Python that runs this script, with the test packages of
#                             tools/requirements-web.lock (scripts/site/ci_requirements.py; exact versions, sha256-checked)
#   ROOT/tools/chrome/<ver>/  chrome-headless-shell $CHROME_VERSION of tools/versions.lock (sha256-checked), which
#                             tools/chrome.sh runs as on the node: vendored fonts only (typst/fonts), SwiftShader WebGL
# System libraries come from the OS. If ldd finds one missing, `playwright install-deps chromium` installs the
# distribution's packages (apt; needs sudo) - the node used conda-forge copies in ROOT/tools/chrome/lib instead.
# Ends with a smoke test: tools/chrome.sh --version must be the pinned version, and Playwright must launch it with WebGL.
# Usage:  bash scripts/site/ci_setup.sh ROOT        (PYTHON=python3.12 to choose the interpreter)
#   then: VLONTO_ROOT=ROOT VLONTO_PYTHON=ROOT/envs/web/bin/python bash scripts/site/ci_check.sh OUT
# On GitHub Actions it exports VLONTO_ROOT and VLONTO_PYTHON through $GITHUB_ENV, and writes the toolchain versions to
# $SITE_CHECK_OUT/ci/toolchain.json when SITE_CHECK_OUT is set.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
ROOT=${1:-${VLONTO_ROOT:-}}
if [ -z "$ROOT" ]; then echo "usage: ci_setup.sh ROOT" >&2; exit 2; fi
mkdir -p "$ROOT"
ROOT=$(cd "$ROOT" && pwd)
# shellcheck disable=SC1091
source "$REPO/tools/versions.lock"
PY=${PYTHON:-python3}
W=$ROOT/envs/web
export VLONTO_ROOT=$ROOT          # tools/chrome.sh runs ROOT/tools/chrome/$CHROME_VERSION/...
if [ ! -x "$REPO/tools/chrome.sh" ]; then   # Playwright starts the launcher itself (executable_path)
  echo "tools/chrome.sh is not executable (committed as mode 100644?); fix: git update-index --chmod=+x tools/chrome.sh" >&2
  exit 1
fi

echo "== Python env $W"
v=$("$PY" -c 'import sys; print(sys.version.split()[0])')
if [ "$v" = "$PYTHON_VERSION" ]; then echo "  [ok]   python $v (= tools/versions.lock)"
else echo "  [warn] python $v; tools/versions.lock pins $PYTHON_VERSION (the lock was resolved for 3.12)"; fi
rm -rf "$W"
"$PY" -m venv "$W"
"$W/bin/python" "$HERE/ci_requirements.py" --lock "$REPO/tools/requirements-web.lock" --out "$ROOT/requirements-test.lock" --check-imports
"$W/bin/python" -m pip install --disable-pip-version-check --no-input -q --require-hashes --no-deps -r "$ROOT/requirements-test.lock"
"$W/bin/python" -m pip check --disable-pip-version-check
pw=$("$W/bin/python" -c 'import importlib.metadata as m; print(m.version("playwright"))')
if [ "$pw" != "$PLAYWRIGHT_VERSION" ]; then echo "playwright $pw installed, tools/versions.lock pins $PLAYWRIGHT_VERSION" >&2; exit 1; fi
echo "  [ok]   playwright $pw (Python API; no browser download - the pinned chrome-headless-shell is used)"

echo "== chrome-headless-shell $CHROME_VERSION"
CH_HOME=$ROOT/tools/chrome/$CHROME_VERSION
CH=$CH_HOME/chrome-headless-shell-linux64/chrome-headless-shell
ZIP=$ROOT/downloads/chrome-headless-shell-linux64-$CHROME_VERSION.zip
mkdir -p "$ROOT/downloads" "$ROOT/tools/chrome/lib"     # lib/ stays empty here: chrome.sh puts it first on LD_LIBRARY_PATH
if ! { [ -f "$ZIP" ] && echo "$CHROME_SHA256  $ZIP" | sha256sum -c --status; }; then
  curl -fsSL --retry 3 --retry-delay 5 -o "$ZIP.part" "$CHROME_URL"
  got=$(sha256sum "$ZIP.part" | cut -d' ' -f1)
  if [ "$got" != "$CHROME_SHA256" ]; then
    echo "SHA256 MISMATCH for $CHROME_URL: got $got, want $CHROME_SHA256" >&2
    rm -f "$ZIP.part"; exit 1
  fi
  mv -f "$ZIP.part" "$ZIP"
fi
echo "  [ok]   zip sha256 $CHROME_SHA256"
rm -rf "$CH_HOME"; mkdir -p "$CH_HOME"; unzip -q "$ZIP" -d "$CH_HOME"
if [ ! -x "$CH" ]; then echo "chrome binary missing after unzip: $CH" >&2; exit 1; fi
missing_libs() { ldd "$CH" 2>&1 | grep 'not found' || true; }
M=$(missing_libs)
if [ -n "$M" ]; then
  echo "  chrome-headless-shell lacks system libraries:"; printf '%s\n' "$M" | sed 's/^/    /'
  echo "== playwright install-deps chromium (apt)"
  "$W/bin/python" -m playwright install-deps chromium
  M=$(missing_libs)
  if [ -n "$M" ]; then echo "still missing after install-deps:" >&2; printf '%s\n' "$M" >&2; exit 1; fi
fi
echo "  [ok]   ldd: every shared library of chrome-headless-shell resolves"
v=$("$REPO/tools/chrome.sh" --version 2>/dev/null | head -1 || true)
if [ "$v" != "Google Chrome for Testing $CHROME_VERSION" ]; then echo "tools/chrome.sh --version: '$v'" >&2; exit 1; fi
echo "  [ok]   $v (via tools/chrome.sh)"

echo "== smoke: Playwright launches tools/chrome.sh with WebGL"
"$W/bin/python" - "$REPO/tools/chrome.sh" "${SITE_CHECK_OUT:-}" "$PYTHON_VERSION" "$CHROME_VERSION" <<'EOF'
import importlib.metadata as md, json, os, platform, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
chrome, out, py_pin, chrome_pin = sys.argv[1:5]
GL = """() => { const c = document.createElement('canvas'), gl = c.getContext('webgl2') || c.getContext('webgl');
  if (!gl) return null; const e = gl.getExtension('WEBGL_debug_renderer_info');
  return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome, headless=True)
    version = b.version
    renderer = b.new_page().evaluate(GL)
    b.close()
print(f"  [{'ok' if renderer else 'FAIL'}]   browser {version}; WebGL renderer: {renderer}")
osr = dict(l.rstrip("\n").split("=", 1) for l in open("/etc/os-release") if "=" in l) if os.path.exists("/etc/os-release") else {}
info = {"python": platform.python_version(), "python_pinned": py_pin, "browser": version, "chrome_pinned": chrome_pin,
        "webgl_renderer": renderer, "os": osr.get("PRETTY_NAME", platform.platform()).strip('"'), "cpus": os.cpu_count(),
        "mem_gib": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1),
        "packages": {d.metadata["Name"]: d.version for d in sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower())}}
if out:
    Path(out, "ci").mkdir(parents=True, exist_ok=True)
    Path(out, "ci", "toolchain.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
sys.exit(0 if renderer else 1)
EOF

if [ -n "${GITHUB_ENV:-}" ]; then
  { echo "VLONTO_ROOT=$ROOT"; echo "VLONTO_PYTHON=$W/bin/python"; } >> "$GITHUB_ENV"
fi
echo "SETUP: OK  (root $ROOT; run: VLONTO_ROOT=$ROOT VLONTO_PYTHON=$W/bin/python bash scripts/site/ci_check.sh OUT)"

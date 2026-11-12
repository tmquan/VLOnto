#!/usr/bin/env bash
# setup_tools.sh - (re)create the VLOnto build toolchain from pinned versions + checksums (tools/versions.lock).
# Linux x86_64, no root. Everything lands under ROOT (default: the parent of the repo directory, i.e. $V):
#   ROOT/tools/uv/uv                 uv (release tarball, sha256-pinned)
#   ROOT/tools/python/               CPython $PYTHON_VERSION (uv-managed)
#   ROOT/envs/web/                   uv venv synced from requirements-web.lock (--require-hashes):
#                                    pandoc (pypandoc-binary; bin/pandoc symlink), node/npm (nodejs-wheel),
#                                    playwright (Python API only), fonttools, pymupdf, pypdfium2, ...
#   ROOT/tools/typst/typst           Typst CLI (static musl release, sha256-pinned)
#   ROOT/tools/chrome/<ver>/         chrome-headless-shell (Chrome for Testing, sha256-pinned)
#   ROOT/tools/chrome/lib/           8 shared libraries chrome lacks on the node, copied from a conda-forge
#                                    env (ROOT/tools/chrome-deps, created from chrome-deps.conda.lock)
#   ROOT/tools/micromamba/micromamba static micromamba used for that env
# Usage:  tools/setup_tools.sh [--check] [--force] [--root DIR]
#   --check   verify what is installed against the pins; never downloads (exit 1 on any drift)
#   --force   re-download and reinstall everything
# Then:   tools/fetch_vendor.sh   (web libraries + fonts; see tools/README.md)
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$HERE")
CHECK=0; FORCE=0; ROOT=${VLONTO_ROOT:-$(dirname "$REPO")}
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --force) FORCE=1 ;;
    --root) ROOT=$2; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
# shellcheck disable=SC1091
source "$HERE/versions.lock"
ROOT=$(mkdir -p "$ROOT" && cd "$ROOT" && pwd)
export VLONTO_ROOT=$ROOT   # so tools/chrome.sh (used in the final check) runs the binary installed under ROOT
DL=$ROOT/downloads; T=$ROOT/tools; W=$ROOT/envs/web
mkdir -p "$DL" "$T" "$ROOT/envs" "$ROOT/build"
export UV_CACHE_DIR=$ROOT/.uv-cache UV_PYTHON_INSTALL_DIR=$T/python UV_PYTHON_PREFERENCE=only-managed
FAIL=0
ok()  { printf '  [ok]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; FAIL=1; }
sha_ok() { [ -f "$1" ] && echo "$2  $1" | sha256sum -c --status; }
fetch() {  # fetch URL DEST SHA256 - download unless DEST already has the pinned checksum
  local url=$1 dest=$2 sha=$3
  if [ "$FORCE" = 0 ] && sha_ok "$dest" "$sha"; then return 0; fi
  if [ "$CHECK" = 1 ]; then bad "missing or wrong checksum: $dest"; return 1; fi
  curl -fsSL --retry 3 -o "$dest.part" "$url"
  if ! sha_ok "$dest.part" "$sha"; then
    echo "SHA256 MISMATCH for $url: got $(sha256sum "$dest.part" | cut -d' ' -f1), want $sha" >&2
    rm -f "$dest.part"; exit 1
  fi
  mv -f "$dest.part" "$dest"
}

echo "== uv $UV_VERSION"
UV_TGZ=$DL/uv-$UV_VERSION-x86_64-unknown-linux-gnu.tar.gz
fetch "$UV_URL" "$UV_TGZ" "$UV_SHA256" && ok "uv tarball sha256"
if [ "$CHECK" = 0 ] && { [ "$FORCE" = 1 ] || ! "$T/uv/uv" --version 2>/dev/null | grep -q "^uv $UV_VERSION "; }; then
  rm -rf "$T/uv"; mkdir -p "$T/uv"; tar -xzf "$UV_TGZ" -C "$T/uv" --strip-components=1
fi
UV=$T/uv/uv
if "$UV" --version 2>/dev/null | grep -q "^uv $UV_VERSION "; then ok "$("$UV" --version)"; else bad "uv $UV_VERSION not installed"; fi

echo "== Python $PYTHON_VERSION + env web"
if [ "$CHECK" = 0 ]; then
  "$UV" python install "$PYTHON_VERSION" >/dev/null 2>&1
  if [ "$FORCE" = 1 ] || ! "$W/bin/python" -c "import sys; assert sys.version.split()[0] == '$PYTHON_VERSION'" 2>/dev/null; then
    rm -rf "$W"; "$UV" venv -q --python "$PYTHON_VERSION" "$W"
  fi
  "$UV" pip sync -q --python "$W/bin/python" --require-hashes "$HERE/requirements-web.lock"
  PANDOC_BIN=$("$W/bin/python" -c 'import pypandoc; print(pypandoc.get_pandoc_path())')
  ln -sf "$PANDOC_BIN" "$W/bin/pandoc"
fi
if "$W/bin/python" -c "import sys; assert sys.version.split()[0] == '$PYTHON_VERSION'" 2>/dev/null; then ok "python $PYTHON_VERSION ($W)"; else bad "env web python is not $PYTHON_VERSION"; fi
if "$W/bin/python" - "$HERE/requirements-web.lock" <<'EOF'
import importlib.metadata as m, re, sys
want = dict(re.findall(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", open(sys.argv[1]).read(), re.M))
def ver(k):
    try:
        return m.version(k)
    except m.PackageNotFoundError:
        return None
drift = [f"{k}: installed {ver(k)} != locked {v}" for k, v in want.items() if ver(k) != v]
print("\n".join("    " + d for d in drift))
sys.exit(1 if drift else 0)
EOF
then ok "env web == requirements-web.lock ($(grep -cE '^[A-Za-z0-9_.-]+==' "$HERE/requirements-web.lock") packages, hash-checked)"; else bad "env web drifted from requirements-web.lock"; fi
v=$("$W/bin/pandoc" --version 2>/dev/null | head -1); [ "$v" = "pandoc $PANDOC_VERSION" ] && ok "$v" || bad "pandoc: '$v' != $PANDOC_VERSION"
v=$("$W/bin/node" --version 2>/dev/null); [ "$v" = "v$NODE_VERSION" ] && ok "node $v" || bad "node: '$v' != v$NODE_VERSION"
v=$("$W/bin/npm" --version 2>/dev/null); [ "$v" = "$NPM_VERSION" ] && ok "npm $v" || bad "npm: '$v' != $NPM_VERSION"

echo "== Typst $TYPST_VERSION"
TY_TAR=$DL/typst-v$TYPST_VERSION-x86_64-unknown-linux-musl.tar.xz
fetch "$TYPST_URL" "$TY_TAR" "$TYPST_SHA256" && ok "typst tarball sha256"
if [ "$CHECK" = 0 ] && { [ "$FORCE" = 1 ] || ! "$T/typst/typst" --version 2>/dev/null | grep -q "^typst $TYPST_VERSION "; }; then
  rm -rf "$T/typst"; mkdir -p "$T/typst"; tar -xJf "$TY_TAR" -C "$T/typst" --strip-components=1
fi
v=$("$T/typst/typst" --version 2>/dev/null || true); [ "$v" = "typst $TYPST_VERSION ($TYPST_COMMIT)" ] && ok "$v" || bad "typst: '$v'"

echo "== chrome-headless-shell $CHROME_VERSION"
CH_ZIP=$DL/chrome-headless-shell-linux64-$CHROME_VERSION.zip
fetch "$CHROME_URL" "$CH_ZIP" "$CHROME_SHA256" && ok "chrome zip sha256"
CH_HOME=$T/chrome/$CHROME_VERSION
CH=$CH_HOME/chrome-headless-shell-linux64/chrome-headless-shell
if [ "$CHECK" = 0 ] && { [ "$FORCE" = 1 ] || [ ! -x "$CH" ]; }; then
  rm -rf "$CH_HOME"; mkdir -p "$CH_HOME"; unzip -q "$CH_ZIP" -d "$CH_HOME"
fi
[ -x "$CH" ] && ok "binary $CH" || bad "chrome binary missing"

echo "== conda-forge libraries for chrome (micromamba $MICROMAMBA_VERSION)"
MM_BIN=$DL/micromamba-$MICROMAMBA_VERSION-linux-64
fetch "$MICROMAMBA_URL" "$MM_BIN" "$MICROMAMBA_SHA256" && ok "micromamba sha256"
MM=$T/micromamba/micromamba
DEPS=$T/chrome-deps
LIB=$T/chrome/lib
if [ "$CHECK" = 0 ]; then
  install -D -m 0755 "$MM_BIN" "$MM"
  export MAMBA_ROOT_PREFIX=$T/mamba-root
  if [ "$FORCE" = 1 ] || [ ! -d "$DEPS/conda-meta" ]; then
    rm -rf "$DEPS"
    "$MM" create -y -q -p "$DEPS" --file "$HERE/chrome-deps.conda.lock" >/dev/null
  fi
  rm -rf "$LIB"; mkdir -p "$LIB"
  for so in $CHROME_LIBS; do cp -L "$DEPS/lib/$so" "$LIB/$so"; done
fi
for so in $CHROME_LIBS; do [ -f "$LIB/$so" ] || bad "missing $LIB/$so"; done
# every package installed in chrome-deps must be the locked one: micromamba checks each downloaded archive against
# the md5 of the explicit lock and records it in conda-meta/<pkg>.json (archives are deleted after extraction)
NPKG=0; NPKGBAD=0
while read -r url; do
  f=${url%%#*}; f=${f##*/}; md5=${url##*#}; stem=${f%.conda}; stem=${stem%.tar.bz2}
  NPKG=$((NPKG + 1))
  got=$(grep -o '"md5": *"[0-9a-f]*"' "$DEPS/conda-meta/$stem.json" 2>/dev/null | head -1 | grep -o '[0-9a-f]\{32\}' || true)
  if [ "$got" != "$md5" ]; then NPKGBAD=$((NPKGBAD + 1)); bad "conda package $stem: installed md5 '${got:-none}' != locked $md5"; fi
done < <(grep '^https://' "$HERE/chrome-deps.conda.lock")
NINST=$(ls "$DEPS/conda-meta"/*.json 2>/dev/null | wc -l)
[ "$NPKGBAD" = 0 ] && [ "$NINST" = "$NPKG" ] && ok "chrome-deps env = the $NPKG packages of chrome-deps.conda.lock (md5 recorded at install)"
[ "$NINST" = "$NPKG" ] || bad "chrome-deps env has $NINST packages, lock lists $NPKG"
if [ -n "${CHROME_LIBS_SHA256// }" ]; then
  NBAD=0
  for pair in $CHROME_LIBS_SHA256; do
    so=${pair%%:*}; sha=${pair#*:}
    sha_ok "$LIB/$so" "$sha" || { bad "checksum $so"; NBAD=$((NBAD + 1)); }
  done
  [ "$NBAD" = 0 ] && ok "$(echo $CHROME_LIBS_SHA256 | wc -w) private libraries match CHROME_LIBS_SHA256"
else
  echo "  [info] CHROME_LIBS_SHA256 not pinned yet; current values:"
  printf '         %s\n' "$(cd "$LIB" && for so in $CHROME_LIBS; do printf '%s:%s ' "$so" "$(sha256sum "$so" | cut -d' ' -f1)"; done)"
fi
NF=$(LD_LIBRARY_PATH=$LIB ldd "$CH" 2>/dev/null | grep -c 'not found' || true)
[ "$NF" = 0 ] && ok "ldd: every shared library of chrome-headless-shell resolves" || bad "ldd: $NF libraries not found"
UNDEF=$(for so in $CHROME_LIBS; do LD_LIBRARY_PATH=$LIB ldd -r "$LIB/$so" 2>&1 | grep -cE 'undefined symbol|not found' || true; done | awk '{s += $1} END {print s + 0}')
[ "$UNDEF" = 0 ] && ok "ldd -r: no undefined symbols in the private libraries (system glib $(ls /usr/lib/x86_64-linux-gnu/libglib-2.0.so.0.* 2>/dev/null | sed 's/.*so.0.//'))" || bad "ldd -r: $UNDEF problems"
v=$("$HERE/chrome.sh" --version 2>/dev/null | head -1 || true)
[ "$v" = "Google Chrome for Testing $CHROME_VERSION" ] && ok "$v (via tools/chrome.sh)" || bad "chrome.sh --version: '$v'"

echo
if [ "$FAIL" = 0 ]; then echo "SETUP: OK  (root $ROOT)"; else echo "SETUP: FAILED (root $ROOT)"; fi
exit "$FAIL"

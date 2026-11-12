#!/usr/bin/env bash
# Download the Typst release pinned in tools/versions.lock, verify its sha256, install to DIR/typst.
#   bash tools/fetch_typst.sh DIR
set -euo pipefail
DIR=${1:?usage: fetch_typst.sh DIR}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOCK="$HERE/versions.lock"
get() { sed -n "s/^$1=//p" "$LOCK" | head -1; }
URL=$(get TYPST_URL); SHA=$(get TYPST_SHA256); VER=$(get TYPST_VERSION)
[ -n "$URL" ] && [ -n "$SHA" ] || { echo "fetch_typst.sh: TYPST_URL/TYPST_SHA256 missing in $LOCK" >&2; exit 2; }
mkdir -p "$DIR"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL --retry 3 -o "$TMP/typst.tar.xz" "$URL"
echo "$SHA  $TMP/typst.tar.xz" | sha256sum -c -
tar -xJf "$TMP/typst.tar.xz" -C "$TMP"
install -m 0755 "$(find "$TMP" -type f -name typst -perm -u+x | head -1)" "$DIR/typst"
"$DIR/typst" --version
echo "Typst $VER installed at $DIR/typst"

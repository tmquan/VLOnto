#!/bin/bash
# Build the VLOnto website in $V/repo/site (data derived from the KG tables, downloads, pyLODE copy, manifests).
# Usage (on the build node):  bash scripts/site/build.sh            # from the repo root
# Re-run after the KG track or the Playbook track changes its outputs. Never touches site/vendor, site/fonts or the
# Playbook track's files (site/data/playbook_html.js, site/downloads/VLOnto-playbook.pdf, site/downloads/playbook.md).
set -euo pipefail
# workspace root: the directory that holds repo/, build/, envs/ (default: two levels above the repo, i.e. repo/..)
V=${VLONTO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
W=$V/envs/web/bin
export PATH="$W:$PATH"          # node for json2js.py --verify
cd "$V/repo"
echo "== derive website data from build/kg (read-only)"
"$V/envs/kg/bin/python" scripts/site/derive_site_data.py --kg "$V/build/kg" --site-data "$V/build/site_data" --out "$V/build/site_extra"
echo "== assemble site/"
"$W/python" scripts/site/build_site.py --root "$V"
echo "== JavaScript syntax"
for f in site/js/*.js; do "$W/node" --check "$f"; done
echo "build OK"

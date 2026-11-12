#!/usr/bin/env bash
# fetch_vendor.sh - vendor the web libraries and fonts reproducibly (logic in tools/vendor_build.py).
#   * npm ci --ignore-scripts from tools/vendor-build/package-lock.json (npm checks every tarball's sha512),
#     then every lockfile integrity is compared with registry.npmjs.org metadata and the top-level tarballs
#     (three 0.187.0, 3d-force-graph 1.80.2, three-spritetext 1.10.0, oxigraph 0.5.13, echarts 6.1.0) are
#     downloaded again and their sha512 verified independently
#   * esbuild 0.28.2 (npm, run with node from envs/web) builds classic-script IIFE bundles:
#     three (window.THREE), 3d-force-graph (window.ForceGraph3D, sharing window.THREE),
#     oxigraph (window.oxigraph / window.oxigraphReady; the wasm is embedded zlib-deflated with fflate 0.8.3 and
#     encoded as lowercase base32 a-z2-7, never base64, so no credential-like pattern can occur in it);
#     three-spritetext and echarts are the upstream UMD files taken from the verified tarballs
#   * every output is scanned for credential-like patterns (AWS key IDs, GitHub/HF/Slack/... tokens, PEM keys);
#     a match fails the build and --check-repo
#   * fonts from fixed google/fonts + notofonts commits and the JetBrains Mono 2.304 release (sha256-pinned):
#     TTF -> typst/fonts, woff2 (+ symbol subsets) and @font-face CSS -> site/fonts
#   * writes/verifies tools/vendor.lock.json (package, version, file, sha256, licence of every output)
# Usage: tools/fetch_vendor.sh                 rebuild + require byte-identical output vs vendor.lock.json
#        tools/fetch_vendor.sh --update-lock   update package-lock.json from package.json (existing resolutions
#                                              kept), rebuild + rewrite vendor.lock.json (after changing a pin)
#        tools/fetch_vendor.sh --check-repo    only check the files in the repo against the lock
#        [--only npm|fonts]
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$HERE")
ROOT=${VLONTO_ROOT:-$(dirname "$REPO")}
W=$ROOT/envs/web/bin
if [ ! -x "$W/python" ] || [ ! -x "$W/node" ]; then echo "fetch_vendor.sh: $W missing - run tools/setup_tools.sh first" >&2; exit 2; fi
export PATH="$W:$PATH"
export npm_config_cache="$ROOT/.npm-cache" npm_config_update_notifier=false npm_config_fund=false npm_config_audit=false
exec "$W/python" "$HERE/vendor_build.py" --root "$ROOT" "$@"

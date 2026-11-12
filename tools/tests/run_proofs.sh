#!/usr/bin/env bash
# run_proofs.sh - rebuild and run the toolchain proofs into OUT (default ROOT/build/toolchain-proofs):
#   web/proof        webgl_test.html (2,000-node 3d-force-graph + SpriteText, shared THREE), oxigraph_test.html
#                    (SPARQL on embedded wasm), fonts_test.html / fonts_embedded_test.html - checked over http:// AND file://
#   web/sample_site  defects.html (deliberate defects -> must FAIL) and index.html (fixed -> must PASS)
#   typst            sample_bad.pdf (tofu + overflow -> must FAIL) and sample_ok.pdf (PASS + byte-identical rebuilds)
#   font_coverage.*  coverage of the vendored fonts and stacks
# Prints one EXPECT line per proof; exit 1 if any expectation is not met.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TOOLS=$(dirname "$HERE")
REPO=$(dirname "$TOOLS")
# shellcheck disable=SC1091
source "$TOOLS/versions.lock"
ROOT=${VLONTO_ROOT:-$(dirname "$REPO")}
W=$ROOT/envs/web/bin
PY=$W/python
export PATH=$W:$PATH
OUT=${1:-$ROOT/build/toolchain-proofs}
rm -rf "$OUT"; mkdir -p "$OUT/web" "$OUT/typst"
BAD=0
expect() {  # expect NAME WANT_RC GOT_RC
  if [ "$2" = "$3" ]; then echo "EXPECT ok   $1 (exit $3)"; else echo "EXPECT FAIL $1 (exit $3, wanted $2)"; BAD=1; fi
}

echo "== assemble web proof dirs (vendor/, fonts/ copied from the repo; data via json2js.py)"
for d in proof sample_site; do
  mkdir -p "$OUT/web/$d"
  cp -r "$HERE/web/$d/." "$OUT/web/$d/"
  cp -r "$REPO/site/vendor" "$OUT/web/$d/vendor"
  cp -r "$REPO/site/fonts" "$OUT/web/$d/fonts"
done
"$PY" "$HERE/web/make_test_data.py" "$OUT/web"
"$PY" "$TOOLS/json2js.py" "$OUT/web/proof/data_src/test_graph.json" -o "$OUT/web/proof/data/test_graph.js" --verify; expect json2js_graph 0 $?
"$PY" "$TOOLS/json2js.py" "$OUT/web/proof/data_src/sample.ttl" --text --name sample_ttl -o "$OUT/web/proof/data/sample_ttl.js" --verify; expect json2js_ttl 0 $?
"$PY" "$TOOLS/json2js.py" "$OUT/web/sample_site/data_src/stats.json" -o "$OUT/web/sample_site/data/stats.js" --verify; expect json2js_stats 0 $?
cp "$OUT/web/sample_site/data_src/stats.json" "$OUT/web/sample_site/data/stats.json"   # fetched by defects.html only

echo "== font coverage of the vendored fonts"
F=$REPO/typst/fonts; S=$REPO/site/fonts
"$PY" "$TOOLS/font_coverage.py" "$F"/*.ttf \
  --stack "sans (Typst/TTF)=$F/BeVietnamPro-Regular.ttf,$F/NotoSansSymbols2-Regular.ttf,$F/NotoSansMath-Regular.ttf" \
  --stack "sans bold (Typst/TTF)=$F/BeVietnamPro-Bold.ttf,$F/NotoSansSymbols2-Regular.ttf,$F/NotoSansMath-Regular.ttf" \
  --stack "serif (Typst/TTF, math routed)=$F/NotoSansMath-Regular.ttf{2190-21FF;2200-22FF},$F/NotoSerif-Regular.ttf,$F/NotoSansSymbols2-Regular.ttf,$F/NotoSansMath-Regular.ttf" \
  --stack "serif WITHOUT routing (shows the ≠ decomposition)=$F/NotoSerif-Regular.ttf,$F/NotoSansSymbols2-Regular.ttf,$F/NotoSansMath-Regular.ttf" \
  --stack "mono (Typst/TTF)=$F/JetBrainsMonoNL-Regular.ttf,$F/NotoSansSymbols2-Regular.ttf,$F/NotoSansMath-Regular.ttf" \
  --stack "sans (web woff2)=$S/BeVietnamPro-Regular.woff2,$S/NotoSansSymbols2-Regular.subset.woff2,$S/NotoSansMath-Regular.subset.woff2" \
  --stack "serif (web woff2, math routed)=$S/NotoSansMath-Regular.subset.woff2{2190-21FF;2200-22FF},$S/NotoSerif-Regular.woff2,$S/NotoSansSymbols2-Regular.subset.woff2,$S/NotoSansMath-Regular.subset.woff2" \
  --stack "mono (web woff2)=$S/JetBrainsMonoNL-Regular.woff2,$S/NotoSansSymbols2-Regular.subset.woff2,$S/NotoSansMath-Regular.subset.woff2" \
  --json "$OUT/font_coverage.json" --md "$OUT/font_coverage.md" --require-full > "$OUT/font_coverage.log"
expect font_coverage 0 $?

echo "== site_check: proof pages (http:// + file://, 1440x900 + 390x844)"
"$PY" "$TOOLS/site_check.py" --root "$OUT/web/proof" --config "$HERE/web/proof/pages.json" --out "$OUT/site_check_proof"
expect site_check_proof 0 $?
echo "== site_check: sample_site/defects.html (deliberate defects)"
"$PY" "$TOOLS/site_check.py" --root "$OUT/web/sample_site" --pages defects.html --out "$OUT/site_check_defects"
expect site_check_defects_must_fail 1 $?
echo "== site_check: sample_site/index.html (fixed)"
"$PY" "$TOOLS/site_check.py" --root "$OUT/web/sample_site" --pages index.html --out "$OUT/site_check_fixed"
expect site_check_fixed 0 $?

echo "== typst + pdf_check"
TY=$ROOT/tools/typst/typst
TFLAGS=(--root "$HERE/typst" --font-path "$REPO/typst/fonts" --ignore-system-fonts --ignore-embedded-fonts
        --creation-timestamp "$SOURCE_DATE_EPOCH_DEFAULT")
"$TY" compile "${TFLAGS[@]}" "$HERE/typst/sample_bad.typ" "$OUT/typst/sample_bad.pdf" 2> "$OUT/typst/sample_bad.typst.log"; expect typst_compile_bad 0 $?
"$TY" compile "${TFLAGS[@]}" "$HERE/typst/sample_ok.typ" "$OUT/typst/sample_ok.pdf" 2> "$OUT/typst/sample_ok.typst.log"; expect typst_compile_ok 0 $?
cat "$OUT/typst/sample_bad.typst.log" "$OUT/typst/sample_ok.typst.log"
printf '#!/usr/bin/env bash\nexec %q compile %s %q %q\n' "$TY" "$(printf '%q ' "${TFLAGS[@]}")" "$HERE/typst/sample_ok.typ" "$OUT/typst/rebuild.pdf" > "$OUT/typst/rebuild.sh"
"$PY" "$TOOLS/pdf_check.py" "$OUT/typst/sample_bad.pdf" --fonts "$REPO/typst/fonts" --margins 22mm,20mm,24mm,20mm --out "$OUT/pdf_check_bad"
expect pdf_check_bad_must_fail 1 $?
"$PY" "$TOOLS/pdf_check.py" "$OUT/typst/sample_ok.pdf" --fonts "$REPO/typst/fonts" --margins 22mm,20mm,24mm,20mm --out "$OUT/pdf_check_ok" \
  --rebuild-cmd "bash $OUT/typst/rebuild.sh" --rebuild-output "$OUT/typst/rebuild.pdf"
expect pdf_check_ok 0 $?

echo "== pandoc Markdown -> Typst body -> PDF"
PD=$W/pandoc
"$PD" --version | head -1
"$PD" -D typst > "$OUT/typst/pandoc_default_template.typ"
mkdir -p "$OUT/typst/pandoc"
cp "$HERE/typst/common.typ" "$OUT/typst/pandoc/"
"$PD" "$HERE/typst/pandoc_sample.md" -f markdown -s -t typst --template "$HERE/typst/pandoc_template.typ" \
  -M title="VLOnto — thử chuỗi Markdown → Typst" -o "$OUT/typst/pandoc/pandoc_doc.typ"; expect pandoc_md_to_typst 0 $?
"$TY" compile --root "$OUT/typst/pandoc" --font-path "$REPO/typst/fonts" --ignore-system-fonts --ignore-embedded-fonts \
  --creation-timestamp "$SOURCE_DATE_EPOCH_DEFAULT" "$OUT/typst/pandoc/pandoc_doc.typ" "$OUT/typst/pandoc_sample.pdf" 2> "$OUT/typst/pandoc.typst.log"
expect typst_compile_pandoc 0 $?
cat "$OUT/typst/pandoc.typst.log"
"$PY" "$TOOLS/pdf_check.py" "$OUT/typst/pandoc_sample.pdf" --fonts "$REPO/typst/fonts" --margins 22mm,20mm,24mm,20mm --out "$OUT/pdf_check_pandoc"
expect pdf_check_pandoc 0 $?

echo
if [ "$BAD" = 0 ]; then echo "PROOFS: all expectations met ($OUT)"; else echo "PROOFS: some expectations NOT met ($OUT)"; fi
exit "$BAD"

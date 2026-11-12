#!/bin/bash
# Test the VLOnto website: site_check (every page x http/file x desktop/mobile) + Playwright interaction tests,
# then merge both into build/site_tests/site_test_report.md|json.  Usage: bash scripts/site/check.sh  (repo root)
set -uo pipefail
# workspace root: the directory that holds repo/, build/, envs/ (default: the parent of the repo)
V=${VLONTO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
W=$V/envs/web/bin
export PATH="$W:$PATH"
cd "$V/repo"
B=$V/build
rm -rf "$B/site_check" "$B/site_check_light" "$B/site_check_dark" "$B/site_tests" "$B/site_contrast"
mkdir -p "$B/site_check_light" "$B/site_check_dark" "$B/site_tests/core" "$B/site_tests/theme" "$B/site_tests/gallery" "$B/site_contrast"
# six independent browser processes: site_check per theme (colour scheme emulated, tools/site_check.py unchanged),
# the interaction tests in three groups, and the contrast check
for T in light dark; do
  "$W/python" scripts/site/site_check_theme.py --color-scheme $T -- --root site --config scripts/site/site_check_pages.json \
    --out "$B/site_check_$T" > "$B/site_check_$T/site_check.log" 2>&1 &
  eval "PSC_$T=\$!"
done
"$W/python" scripts/site/interaction_tests.py --root site --out "$B/site_tests/core" --tests ${TESTS_CORE:-ontology,network,sparql,dashboard,simple} \
  > "$B/site_tests/core/interactions.log" 2>&1 &
PIC=$!
"$W/python" scripts/site/interaction_tests.py --root site --out "$B/site_tests/theme" --tests ${TESTS_THEME:-theme,paper} \
  > "$B/site_tests/theme/interactions.log" 2>&1 &
PIT=$!
"$W/python" scripts/site/interaction_tests.py --root site --out "$B/site_tests/gallery" --tests gallery --modes http \
  > "$B/site_tests/gallery/interactions.log" 2>&1 &
PIG=$!
"$W/python" scripts/site/contrast_check.py --root site --out "$B/site_contrast" > "$B/site_contrast/contrast.log" 2>&1 &
PCC=$!
wait $PSC_light; RC_L=$?
wait $PSC_dark; RC_D=$?
wait $PIC; RC_C=$?
wait $PIT; RC_T=$?
wait $PIG; RC_G=$?
wait $PCC; RC_X=$?
"$W/python" scripts/site/make_report.py --site-check light="$B/site_check_light" --site-check dark="$B/site_check_dark" \
  --tests "$B/site_tests/core" --tests "$B/site_tests/theme" --tests "$B/site_tests/gallery" --contrast "$B/site_contrast" \
  --build "$B/site_build_report.json" --out "$B/site_tests" ${BUNDLE_JSON:+--bundle $BUNDLE_JSON}
echo "site_check light $RC_L, dark $RC_D; interactions core $RC_C, theme $RC_T, gallery $RC_G; contrast $RC_X"
for f in "$B/site_check_light/site_check.log" "$B/site_check_dark/site_check.log"; do tail -n 2 "$f"; done
for g in core theme gallery; do tail -n 1 "$B/site_tests/$g/interactions.log"; done
tail -n 1 "$B/site_contrast/contrast.log"
exit $(( RC_L != 0 || RC_D != 0 || RC_C != 0 || RC_T != 0 || RC_G != 0 || RC_X != 0 ))

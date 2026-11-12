#!/usr/bin/env bash
# ci_check.sh - the website checks of scripts/site/check.sh (the node's release job) for a CI runner, or for any
# checkout that is not laid out as $V/{repo,build,envs}. Same scripts, same arguments, same output layout:
#   light, dark  tools/site_check.py through site_check_theme.py (colour scheme emulated): every page of
#                scripts/site/site_check_pages.json x http/file x 1440x900/390x844
#   core         interaction_tests.py --tests ontology,network,sparql,dashboard,simple,traces (http/file x both viewports)
#   theme        interaction_tests.py --tests theme,paper,paper_style
#   gallery      interaction_tests.py --tests gallery --modes http (review screenshots of every page, both themes)
#   contrast     contrast_check.py (WCAG AA; both themes x both viewports, http)
#   report       make_report.py -> OUT/site_tests/site_test_report.md|json
# Pages added to site_check_pages.json reach every check: site_check reads the file, and the interaction tests and the
# contrast check run through ci_pages.py, which appends new pages to their page lists.
# Usage:  VLONTO_ROOT=<ROOT of ci_setup.sh> VLONTO_PYTHON=<ROOT>/envs/web/bin/python bash scripts/site/ci_check.sh [OUT]
# Env:    CI_PARALLEL       browser processes at the same time (default 3 here; the preview workflow passes 1 on GitHub's 4-CPU runners)
#         CI_CHECK_TIMEOUT  time limit per check, coreutils syntax (default 120m; the check then exits 124)
#         TESTS_CORE, TESTS_THEME  as in check.sh;  SITE_BUILD_REPORT  site_build_report.json, if the site was built
# Output: OUT/{site_check_light,site_check_dark,site_tests/{core,theme,gallery},site_contrast} as $V/build/... on the
#         node, OUT/site_tests/site_test_report.md|json, OUT/ci/{rc/<check>,run.json,results.json,summary.md}
# Exit:   0 only when every check exits 0 and the merged report says PASS, else 1 (2 = usage error).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT=${1:-${SITE_CHECK_OUT:-$REPO/build/site_check_ci}}
PY=${VLONTO_PYTHON:-python3}
PAR=${CI_PARALLEL:-3}
TMO=${CI_CHECK_TIMEOUT:-120m}
CFG=scripts/site/site_check_pages.json
case "$PAR" in ''|*[!0-9]*|0) echo "CI_PARALLEL must be a positive integer, not '$PAR'" >&2; exit 2 ;; esac
cd "$REPO" || exit 2
mkdir -p "$OUT" && OUT=$(cd "$OUT" && pwd) || exit 2
rm -rf "$OUT/site_check_light" "$OUT/site_check_dark" "$OUT/site_tests" "$OUT/site_contrast" "$OUT/ci/rc"
rm -f "$OUT/ci/run.json" "$OUT/ci/results.json" "$OUT/ci/summary.md" "$OUT/ci/report.log"
mkdir -p "$OUT/site_check_light" "$OUT/site_check_dark" "$OUT/site_tests/core" "$OUT/site_tests/theme" \
  "$OUT/site_tests/gallery" "$OUT/site_contrast" "$OUT/ci/rc"
TO=()                                 # coreutils timeout; where it is missing (macOS) the checks run without a limit
if command -v timeout >/dev/null 2>&1; then TO=(timeout --kill-after=2m "$TMO"); fi

CHECKS=(core theme contrast light dark gallery)       # started in this order, CI_PARALLEL at a time
log_of() {
  case $1 in
    core|theme|gallery) echo "site_tests/$1/interactions.log" ;;
    contrast) echo "site_contrast/contrast.log" ;;
    light|dark) echo "site_check_$1/site_check.log" ;;
  esac
}
argv_of() {                                            # sets A = the command line of check $1
  case $1 in
    core) A=("$PY" scripts/site/ci_pages.py --config "$CFG" -- scripts/site/interaction_tests.py --root site
             --out "$OUT/site_tests/core" --tests "${TESTS_CORE:-ontology,network,sparql,dashboard,simple,traces}") ;;
    theme) A=("$PY" scripts/site/ci_pages.py --config "$CFG" -- scripts/site/interaction_tests.py --root site
              --out "$OUT/site_tests/theme" --tests "${TESTS_THEME:-theme,paper,paper_style}") ;;
    gallery) A=("$PY" scripts/site/ci_pages.py --config "$CFG" -- scripts/site/interaction_tests.py --root site
                --out "$OUT/site_tests/gallery" --tests gallery --modes http) ;;
    contrast) A=("$PY" scripts/site/ci_pages.py --config "$CFG" -- scripts/site/contrast_check.py --root site
                 --out "$OUT/site_contrast") ;;
    light|dark) A=("$PY" scripts/site/site_check_theme.py --color-scheme "$1" -- --root site --config "$CFG"
                   --out "$OUT/site_check_$1" --modes "http,file" --viewports "1440x900,390x844") ;;
  esac
}
now() { date -u +%H:%M:%S; }
start_check() {                                        # runs check $1 in the background; OUT/ci/rc/$1 = "exit seconds"
  local name=$1 log
  log=$(log_of "$name")
  argv_of "$name"
  echo "[$(now)] start $name: ${A[*]}"
  (
    t0=$(date +%s)
    ${TO[@]+"${TO[@]}"} "${A[@]}" > "$OUT/$log" 2>&1
    rc=$?
    echo "$rc $(( $(date +%s) - t0 ))" > "$OUT/ci/rc/$name.part" && mv -f "$OUT/ci/rc/$name.part" "$OUT/ci/rc/$name"
  ) &
}
# shellcheck disable=SC2329  # called by the trap below
cleanup() {                                            # cancelled: stop the checks (timeout forwards to its group)
  local p
  for p in $(jobs -p); do pkill -TERM -P "$p" 2>/dev/null; kill -TERM "$p" 2>/dev/null; done
}
trap 'cleanup; exit 143' TERM INT

T0=$(date +%s)
echo "[$(now)] ${#CHECKS[@]} checks, $PAR at a time, limit $TMO each ($( [ ${#TO[@]} -gt 0 ] && echo coreutils timeout || echo 'no timeout command: unlimited')); output $OUT"
next=0
reported=" "
while :; do
  finished=0
  for c in "${CHECKS[@]}"; do
    [ -f "$OUT/ci/rc/$c" ] || continue
    finished=$((finished + 1))
    case "$reported" in *" $c "*) continue ;; esac
    read -r rc secs < "$OUT/ci/rc/$c"
    echo "[$(now)] done  $c: exit $rc after $((secs / 60))m$((secs % 60))s"
    reported="$reported$c "
  done
  [ "$finished" -ge "${#CHECKS[@]}" ] && break
  while [ $((next - finished)) -lt "$PAR" ] && [ "$next" -lt "${#CHECKS[@]}" ]; do
    start_check "${CHECKS[$next]}"
    next=$((next + 1))
  done
  sleep 5
done
wait

echo "[$(now)] report"
"$PY" scripts/site/make_report.py --site-check light="$OUT/site_check_light" --site-check dark="$OUT/site_check_dark" \
  --tests "$OUT/site_tests/core" --tests "$OUT/site_tests/theme" --tests "$OUT/site_tests/gallery" --contrast "$OUT/site_contrast" \
  --build "${SITE_BUILD_REPORT:-$OUT/site_build_report.json}" --out "$OUT/site_tests" > "$OUT/ci/report.log" 2>&1
RC_R=$?
echo "$RC_R 0" > "$OUT/ci/rc/report"
cat "$OUT/ci/report.log"
"$PY" -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8")).get("ok") is True else 1)' \
  "$OUT/site_tests/site_test_report.json" 2>/dev/null
REPORT_OK=$?
WALL=$(( $(date +%s) - T0 ))
NAMES=$(printf '"%s", ' "${CHECKS[@]}")
printf '{"parallel": %s, "check_timeout": "%s", "timeout_command": %s, "wall_s": %s, "checks": [%s]}\n' \
  "$PAR" "$TMO" "$( [ ${#TO[@]} -gt 0 ] && echo true || echo false)" "$WALL" "${NAMES%, }" > "$OUT/ci/run.json"

FAIL=0
SUM=""
for c in "${CHECKS[@]}"; do
  rc=99                                                # 99: the check did not record an exit code
  if [ -f "$OUT/ci/rc/$c" ]; then read -r rc _ < "$OUT/ci/rc/$c"; fi
  [ "$rc" = 0 ] || FAIL=1
  SUM="$SUM $c $rc;"
done
if [ "$RC_R" != 0 ] || [ "$REPORT_OK" != 0 ]; then FAIL=1; fi
"$PY" scripts/site/ci_summary.py --out "$OUT" > "$OUT/ci/summary.log" 2>&1 || echo "ci_summary.py failed: see ci/summary.log"
echo "exit codes:$SUM report $RC_R (merged report $( [ "$REPORT_OK" = 0 ] && echo PASS || echo FAIL))"
for c in light dark; do tail -n 2 "$OUT/site_check_$c/site_check.log" 2>/dev/null; done
for g in core theme gallery; do tail -n 1 "$OUT/site_tests/$g/interactions.log" 2>/dev/null; done
tail -n 1 "$OUT/site_contrast/contrast.log" 2>/dev/null
echo "CI SITE CHECK: $( [ "$FAIL" = 0 ] && echo PASS || echo FAIL ) in $((WALL / 60))m$((WALL % 60))s (CI_PARALLEL=$PAR)"
exit "$FAIL"

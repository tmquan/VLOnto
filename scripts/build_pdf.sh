#!/usr/bin/env bash
# Build the VLOnto playbook: facts -> Markdown -> figures -> Typst -> PDF -> website hand-off.
#
#   bash scripts/build_pdf.sh --facts        gather data/facts.json from the KG build
#                                            (knowledge-graph env; bulk-loads the RDF dump)
#   bash scripts/build_pdf.sh                Markdown, SVG figures, playbook.typ, PDF, HTML
#   bash scripts/build_pdf.sh --check        tools/pdf_check.py (two byte-identical rebuilds)
#                                            and playbook/tools/text_collisions.py on the PDF
#   bash scripts/build_pdf.sh --check-files  playbook/tools/check_files.py: sizes, sha256 and triple
#                                            counts printed in playbook.md vs the build, the
#                                            repository and site/downloads (knowledge-graph env)
#   bash scripts/build_pdf.sh --pdf-only     Typst only, from the generated playbook.typ
#   options: --out FILE (PDF path)  --no-html  --preview DIR (standalone HTML page)
#
# Deterministic: the same sources give byte-identical outputs. Typst sees only the vendored
# fonts and SOURCE_DATE_EPOCH is the build date of the knowledge graph (data/meta.json).
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
V=${V:-$(dirname "$REPO")}
W=${W:-$V/envs/web/bin}
KGPY=${KGPY:-$V/envs/kg/bin/python}
TY=${TY:-$V/tools/typst/typst}
OUT=${OUT:-$V/build/playbook/VLOnto-playbook.pdf}
DATA_REPORT=${DATA_REPORT:-$V/build/playbook/inputs/data_report.md}
GUIDE=${GUIDE:-$V/build/playbook/inputs/vn_legal_agent_guide.md}
MODE=all
NOHTML=
PREVIEW=
while [ $# -gt 0 ]; do
  case "$1" in
    --facts) MODE=facts ;;
    --check) MODE=check ;;
    --check-files) MODE=files ;;
    --pdf-only) MODE=pdf ;;
    --no-html) NOHTML=1 ;;
    --out) OUT=$2; shift ;;
    --preview) PREVIEW=$2; shift ;;
    *) echo "build_pdf.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
cd "$REPO"
export LC_ALL=C.UTF-8 PYTHONHASHSEED=0

if [ "$MODE" = facts ]; then
  "$KGPY" playbook/tools/gather_facts.py --data-report "$DATA_REPORT" --guide "$GUIDE" \
      ${REUSE_STORE:+--reuse-store}
  exit 0
fi

if [ "$MODE" = check ]; then
  CK=$V/build/playbook/pdf_check
  rc=0
  "$W/python" tools/pdf_check.py "$OUT" --fonts typst/fonts --margins 22mm,20mm,24mm,20mm \
      --out "$CK" \
      --rebuild-cmd "bash scripts/build_pdf.sh --pdf-only --out $V/build/playbook/rebuild.pdf" \
      --rebuild-output "$V/build/playbook/rebuild.pdf" || rc=1
  "$W/python" playbook/tools/text_collisions.py "$OUT" --out "$CK/text_collisions.json" || rc=1
  exit $rc
fi

if [ "$MODE" = files ]; then
  "$KGPY" playbook/tools/check_files.py --pdf "$OUT" --report "$V/build/playbook/check_files.md"
  exit 0
fi

TYF=(--root playbook --font-path typst/fonts --ignore-system-fonts --ignore-embedded-fonts)
FIGS="architecture doc-types validity changes modules"

if [ "$MODE" = all ]; then
  "$W/python" playbook/tools/render_md.py
  mkdir -p playbook/figures "$V/build/playbook"
fi
BUILD_DATE=$(sed -n 's/^ *"date": "\([0-9-]*\)".*/\1/p' playbook/data/meta.json)
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(date -u -d "$BUILD_DATE" +%s)}

if [ "$MODE" = all ]; then
  for f in $FIGS; do
    "$TY" compile "${TYF[@]}" --input fig="$f" --format svg playbook/figures.typ \
        "playbook/figures/$f.svg"
  done
  "$TY" compile "${TYF[@]}" --input fig=all playbook/figures.typ "$V/build/playbook/figures.pdf"
  "$W/pandoc" playbook/playbook.md -f markdown -t typst -s \
      --template playbook/template.typ --metadata-file playbook/data/meta.json \
      --shift-heading-level-by=-1 --lua-filter playbook/filters/typst-figures.lua \
      -o playbook/playbook.typ
fi

mkdir -p "$(dirname "$OUT")"
"$TY" compile "${TYF[@]}" playbook/playbook.typ "$OUT"
echo "PDF: $OUT ($(stat -c %s "$OUT") bytes, SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH)"

if [ "$MODE" = all ] && [ -z "$NOHTML" ]; then
  "$W/python" playbook/tools/make_html.py --pdf "$OUT" ${PREVIEW:+--preview "$PREVIEW"}
fi

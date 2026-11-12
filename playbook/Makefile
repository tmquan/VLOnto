# VLOnto playbook: make targets around scripts/build_pdf.sh, from the repository root:
#   make -C playbook facts      gather data/facts.json from the knowledge-graph build
#   make -C playbook pdf        Markdown, SVG figures, playbook.typ, PDF, website hand-off
#   make -C playbook check      pdf_check (two byte-identical rebuilds) and text_collisions
#   make -C playbook check-files  printed sizes, sha256 and triple counts vs the files
#   make -C playbook pdf-only   Typst only, from the generated playbook.typ
#   make -C playbook            pdf, check, check-files
# Variables pass through the environment: V, W, TY, KGPY, OUT, REUSE_STORE=1 (reuse the store;
# never after a new RDF export, or the recipe outputs come from the old dump).
BUILD := bash $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../scripts/build_pdf.sh)

.PHONY: all facts pdf check check-files pdf-only

all: pdf check check-files

check-files:
	$(BUILD) --check-files

facts:
	$(BUILD) --facts

pdf:
	$(BUILD)

check:
	$(BUILD) --check

pdf-only:
	$(BUILD) --pdf-only

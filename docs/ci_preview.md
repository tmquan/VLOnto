# Browser tests on preview branches (`.github/workflows/preview.yml`)

The workflow `preview-site-check` runs the website's own browser checks — the checks of the build node's release job
(`scripts/site/check.sh`) — on GitHub Actions, so a change can be tested in headless Chrome before it is merged into
`main` and published by `pages.yml`. It only reads the repository (`permissions: contents: read`), never pushes and
never deploys.

## Trigger

| How | Command / place | Notes |
|---|---|---|
| Push to a preview branch | `git push origin HEAD:preview/<topic>` | Any branch matching `preview/**`. The pushed commit must contain `.github/workflows/preview.yml`. A newer push to the same branch cancels the running check of the older one. |
| By hand | Actions → *preview-site-check* → *Run workflow*, pick the branch and `parallel` | Needs the workflow file on the default branch (`main`) first; until then use the push trigger. |
| GitHub CLI | `gh workflow run preview.yml --ref preview/<topic> -f parallel=3` | Same as by hand. |
| REST API | `POST /repos/tmquan/VLOnto/actions/workflows/preview.yml/dispatches` with `{"ref": "preview/<topic>", "inputs": {"parallel": "3"}}` | Token with `actions: write`. |

`parallel` (manual runs only; pushes use 3) is the number of checks — browser processes — run at the same time.
The node started all six at once on a many-core machine; a GitHub-hosted runner has 4 vCPUs. Choose `1` to rule
out load-related timeouts (slow canvas selection, theme switches) when a run fails only under load.

Results: the run page shows the summary table; `gh run list --workflow preview.yml` lists runs and
`gh run download <run-id> -n site-check-<run-id>` fetches the artifact.

## What runs

1. `actions/checkout` (no stored credentials), then `actions/setup-python` with `PYTHON_VERSION` of `tools/versions.lock`
   (3.12.16; the node's version, from `actions/python-versions`).
2. `scripts/site/ci_setup.sh "$RUNNER_TEMP/vlonto"` installs the toolchain from the repository's pins:
   - the test-time part of `tools/requirements-web.lock`, written by `scripts/site/ci_requirements.py`: playwright 1.65.0
     with greenlet, pillow, beautifulsoup4 with soupsieve and typing-extensions, fonttools with brotli and zopfli,
     numpy — 10 of the 29 locked packages, versions and sha256 hashes copied unchanged, installed with
     `pip install --require-hashes --no-deps`, then `pip check`; the playwright version must equal `PLAYWRIGHT_VERSION`;
   - chrome-headless-shell `CHROME_VERSION` (157.0.8103.50) from `CHROME_URL`, refused unless its sha256 is `CHROME_SHA256`;
     it runs through `tools/chrome.sh` exactly as on the node (vendored fonts of `typst/fonts` only, SwiftShader WebGL);
   - system libraries: those of the Ubuntu 24.04 image; if `ldd` reports one missing, `playwright install-deps chromium`
     installs it with apt (the node, without root, used eight conda-forge libraries instead);
   - smoke test: `tools/chrome.sh --version` must print the pinned version, and Playwright must launch it with WebGL.
     Versions, CPUs and memory are written to `ci/toolchain.json`.
3. `scripts/site/ci_check.sh "$RUNNER_TEMP/site-check"` runs the six checks with the arguments of `check.sh`, three at a
   time by default (`parallel`), each limited to 120 minutes (`CI_CHECK_TIMEOUT`):

   | check | command | scope |
   |---|---|---|
   | light, dark | `site_check_theme.py --color-scheme <theme> -- --root site --config scripts/site/site_check_pages.json --modes http,file --viewports 1440x900,390x844` (runs `tools/site_check.py` unchanged) | every page of the config × http and file × desktop and mobile |
   | core | `interaction_tests.py --tests ontology,network,sparql,dashboard,simple` | http and file × both viewports |
   | theme | `interaction_tests.py --tests theme,paper` | http and file × both viewports |
   | gallery | `interaction_tests.py --tests gallery --modes http` | review screenshots of every page, both themes |
   | contrast | `contrast_check.py` | WCAG AA, every page × both themes × both viewports (http) |
   | report | `make_report.py` | merges the six into `site_tests/site_test_report.md` and `.json` |

4. The artifact is uploaded and the summary written even when a check fails (`if: always()`).

New pages are picked up from `scripts/site/site_check_pages.json`: `site_check` reads it, and the interaction tests and
the contrast check run through `scripts/site/ci_pages.py`, which appends the config's pages to `GALLERY`, `SITE_PAGES`
(pages with a `ready` condition outside `ontology/`) and contrast `PAGES`, leaving the scripts unchanged. With today's
config nothing is added, so the checks are exactly the node's. Page-specific behaviour still lives in
`interaction_tests.py`: `traces.html` is in the header navigation, so the about test expects 9 internal navigation links
(`len(internal) == 9`), and the Traces page has its own test (`traces`: one WebGL scene of all traces; tabs, lazy loading,
keyboard, a question selected in three areas with its trace pixels, call-outs and hop panel, node details, deep links and
the theme switch), which `check.sh` and `ci_check.sh` run by default; it is also one of the WebGL `SCENES` of the theme,
gallery and contrast checks.

## Runtime

Not measured yet: no browser can run where this workflow was written, so the first run sets the baseline (the summary
table and `ci/results.json` give minutes per check). Estimate for a 4-vCPU runner: setup 1–3 minutes (about 80 MB of
wheels, the Chrome zip, apt only if a library is missing); checks roughly 30–90 minutes with `parallel` 3, mostly in
the WebGL pages (SwiftShader renders on the CPU) and the contrast check's per-viewport captures; upload 1–2 minutes.
Limits: 120 minutes per check, 285 minutes for the check step, 300 minutes for the job.

## Artifact `site-check-<run id>` (kept 14 days)

```
ci/toolchain.json            Python, Playwright, Chrome and WebGL renderer, OS, CPUs, memory, installed packages
ci/rc/<check>                "<exit code> <seconds>" per check (and report)
ci/run.json                  parallel, per-check limit, wall time
ci/results.json              verdict and, per check: result, exit code, runs, failed runs, seconds, log
ci/summary.md                the job summary
ci/report.log, ci/summary.log
site_check_light/            site_check_report.json|md, site_check.log
  shots/<page>__<mode>__<WxH>.png                full-page screenshot of every run
  canvas/<page>__<mode>__<WxH>__canvas<i>.png    every canvas
site_check_dark/             the same in the dark theme
site_tests/site_test_report.md|json              merged report (make_report.py)
site_tests/core/             interactions.json, interactions.log, shots/<step>__<mode>__<WxH>.png
site_tests/theme/            the same, plus gallery/paper_*__<theme>__<WxH>.png (paper card and playground panel)
site_tests/gallery/          interactions.json, interactions.log, gallery/<page>__<theme>__<WxH>__top|full.png
site_contrast/               contrast.json, contrast_report.md, contrast.log
```

The layout matches `$V/build/` on the node. There is no `site_build_report.json`: CI tests the committed `site/` and
does not rebuild it, so the merged report has no "site:" line (set `SITE_BUILD_REPORT` to include one).

## PASS and FAIL

| part | fails when | exit code |
|---|---|---|
| setup | `tools/chrome.sh` not executable, a hash or sha256 mismatch, a dependency `pip check` rejects, a playwright version other than the pin, a library still missing after install-deps, the wrong Chrome version, or no WebGL | step fails; the checks do not run (summary: NOT RUN) |
| site_check light / dark | any run fails: page_load, failed_requests, external requests, console errors, blank canvases, page_overflow, clipped_text, text_overlap, broken_word, fonts, glyph_coverage, glyph_decomposition, mojibake, broken_images, or a static-lint failure | 1; 2 = setup error (missing page, browser did not launch) |
| interactions core / theme / gallery | any check of any test fails, or a test's page logged console errors, page errors, failed or external requests | 1 |
| contrast | text below 4.5:1 (3:1 for large text), a UI component or focus ring below 3:1 or drawn on less than 60% of its length, the theme not applied, no text checked, or the page could not be checked (an exception, e.g. ready not reached) | 1 |
| report | `make_report.py`'s verdict (site_check PASS with at least one run, interactions PASS, contrast not FAIL) | always 0 — `ci_check.sh` reads its `ok` |

Any check exits 124 when it reaches the per-check limit (summary: TIMEOUT). `ci_check.sh` exits 0 only when all six
exit 0 and the merged report says PASS; otherwise the job fails. The summary lists up to 60 failures, with the last log
lines for a check that stopped without writing results.

## Playbook PDF reproduction (job `reproduce-pdf`)

The workflow also runs the `reproduce-pdf` job of `pages.yml` on the same preview branch: `tools/fetch_typst.sh`
installs the Typst release pinned in `tools/versions.lock` (Linux musl build, sha256-checked),
`scripts/build_pdf.sh --pdf-only` rebuilds the playbook PDF from the committed `playbook/playbook.typ`, and `cmp`
compares it with `site/downloads/VLOnto-playbook.pdf`. The job fails on any byte difference and then uploads the
rebuilt PDF as the artifact `reproduce-pdf-<run id>`. It runs in a few minutes, independently of the browser checks, so a
PDF built on another machine (the v1 PDF was built on macOS with the macOS build of the same Typst release) is known to
match the Linux build before `main` publishes it.

## Differences from the node's release job

- Runner: GitHub-hosted ubuntu-24.04 (the standard runner for public repositories has 4 vCPUs and 16 GiB); frame rates in the report are lower
  (they are recorded, never asserted).
- Three checks at a time instead of six.
- Same Python version and the same locked versions of the packages the checks import; the build-only packages
  (pandoc, node, pymupdf, ...) are not installed.
- Same Chrome build, flags and fonts; system libraries from the runner image instead of conda-forge copies.
- No site build: `build_site.py`'s checks (file sizes, NFC) are not repeated; CI tests the committed `site/`.
- `TZ=UTC`; the locale is the runner's.

## Run it elsewhere (Linux x86_64 with Python 3.12)

```
bash scripts/site/ci_setup.sh /tmp/vlonto
VLONTO_ROOT=/tmp/vlonto VLONTO_PYTHON=/tmp/vlonto/envs/web/bin/python bash scripts/site/ci_check.sh /tmp/site-check
python3 scripts/site/ci_summary.py --out /tmp/site-check
```

On the build node, `scripts/site/check.sh` stays the tool.

## Files

- `.github/workflows/preview.yml` — the workflow (actions pinned to commit SHAs: checkout v7.0.1, setup-python v7.1.0,
  upload-artifact v7.0.2); jobs `site-check` and `reproduce-pdf`
- `scripts/site/ci_setup.sh` — toolchain installer and smoke test
- `scripts/site/ci_requirements.py` — test-time subset of `tools/requirements-web.lock`, import coverage check
- `scripts/site/ci_check.sh` — runs the checks and the report, decides PASS/FAIL
- `scripts/site/ci_pages.py` — adds the config's pages to the page lists of the interaction and contrast tests
- `scripts/site/ci_summary.py` — summary table, failure list, `ci/results.json`
- `tools/chrome.sh` — mode 100644 → 100755: Playwright starts it directly (`executable_path`), and the 0.1.0 commit
  had lost the executable bit, so a fresh clone could not launch the browser

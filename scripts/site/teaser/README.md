# Fig. 1 capture harness (not part of the site)

Renders the teaser figure of the paper *Vietnamese Legal Ontology: Every legal answer, traced to the article that grounds
it* (Bui and Tran Minh, arXiv:2611.11426) from the site's 3D legal network: all 40,816 documents layered by legal force,
their legal-basis and change links on the network's curves, and the trace of Q&A #138008514 - the Labor Code
45/2019/QH14 with its replacement chain 10/2012/QH13 > 45/2019/QH14, and the hops below the document level hung from
it: Chapter III > Section 3 > Article 35 > Clause 1 > Point d, the answer and the question, plus the term branch
(Art. 3(1) defines *người lao động*; the question mentions *người lao động* and *hợp đồng lao động*), as in the
paper's Fig. 5. The page under `scripts/` is never published (GitHub Pages serves `site/`).

| File | Role |
|---|---|
| `teaser_config.json` | camera (orthographic: azimuth, elevation, target, half height), viewport, captures (pixel ratio, colouring, labels), context fade, trace weights in points, the subtree's offsets from the Labor Code |
| `trace_138008514.json` | facts of the trace: identifiers and short bilingual labels only, with provenance (written by `make_trace.py`) |
| `make_trace.py` | reads a VLOnto v1 build (`build/kg` tables) and the paper's `data/worked_example.json`; checks every fact against both |
| `make_page.py` | writes `teaser.html` from `site/network-3d.html` (a `<base>` into `site/`, the capture stylesheet and scripts) and `teaser_data.js` (config + trace as a classic script); `--check` fails when they are out of date |
| `teaser-core.js` | pure geometry: the Labor Code's local frame, subtree positions, the camera pose and frustum, points <-> CSS px |
| `teaser.js` | the harness in the page; uses `VLApp.capture` (site/js/network3d.js) and the page's own trace and line objects |
| `teaser.css` | the canvas fills the viewport; chrome, side bar, panel, legend and hint hidden |
| `capture.py` | Playwright + the pinned chrome-headless-shell: one PNG per capture and `teaser_capture.json` |
| `test_core.js`, `test_harness.js` | node checks: the geometry against three.js; the harness against a stand-in page (no pixels) |
| `preview.py` | offline composition preview with matplotlib (camera, framing, clear space) and a draft of the vector layer |
| `summary.py` | job summary of a capture run |

## The page hook

`site/js/network3d.js` exposes `window.VLApp.capture` for this harness only: `get()` (scene, renderer, camera, controls,
data, theme, points, links, labels, chain, the links' curve `curvePts`), `setCamera(cam)`, `select(id)` (without the
camera flight) and `render()`. `updatePointScale` leaves `uScale` to a non-perspective camera, and `VL.spriteWpp`
(`site/js/labels3d.js`) sizes sprites for an orthographic camera. Nothing on the site calls them.

## Capture

- CI: push to `preview/teaser` (or `preview/teaser-<anything>`); `.github/workflows/teaser.yml` installs the pinned
  toolchain (`scripts/site/ci_setup.sh`), runs the checks, then `capture.py`, and uploads `teaser-<run id>`.
- Locally (Linux x86_64 with the toolchain): `bash scripts/site/ci_setup.sh ROOT`, then
  `VLONTO_ROOT=ROOT ROOT/envs/web/bin/python scripts/site/teaser/capture.py --out OUT`.

Every wait is on a page metric (`window.__VLONTO_READY`, the selection's `panelLoaded` and chain, frames), never a fixed
sleep; limits scale with `VLONTO_TIMEOUT_SCALE`. The PNG is the WebGL canvas read in the frame it was drawn
(`toDataURL`), at the capture's pixel ratio: 1600 x 716 CSS px = the paper's 508.392 x 227.52 pt box (aspect 2.2346
vs 2.2345), so one CSS px is 0.318 pt and the trace weights of `trace_pt` (core 1.6 pt, as in the published figure)
become CSS px. WebGL lines stay one device pixel wide, so the context links are finer at pixel ratio 3 than at 2.

## Preview

    python scripts/site/teaser/preview.py --out preview.png --json anchors.json --fonts <dir with LibertinusSans-Regular.otf>

draws the same geometry from `site/data/legal_network.js` (straight-segment approximation of the curves, flat discs) and
drafts the paper's vector layer: call-outs in Libertinus Sans 8.5 pt on thin leaders in the clear margins and a flat
legend, as in the published Fig. 1. `--color-by validity` shows the site's colouring (its legend needs four rows and collides with the bottom call-outs).

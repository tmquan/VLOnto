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
| `teaser-core.js` | pure geometry: the Labor Code's local frame, subtree positions, the camera pose and frustum, clipping planes around a depth range, the page's depth fade, points <-> CSS px |
| `teaser.js` | the harness in the page; uses `VLApp.capture` (site/js/network3d.js) and the page's own trace and line objects |
| `teaser.css` | the canvas fills the viewport; chrome, side bar, panel, legend and hint hidden |
| `capture.py` | Playwright + the pinned chrome-headless-shell: one PNG per capture, `teaser_capture.json` (with each capture's diagnostics and ink counts), `page.png`, `console.log`; fails on a blank capture |
| `test_core.js`, `test_harness.js` | node checks: the geometry against three.js; the harness against a stand-in page (three.js's OrbitControls with the page's limits, the page's frame loop and depth fade, a renderer that rasterises the points inside the clip volume) |
| `preview.py` | offline composition preview with matplotlib (camera, framing, clear space) and a draft of the vector layer |
| `summary.py` | job summary of a capture run |

## The page hook

`site/js/network3d.js` exposes `window.VLApp.capture` for this harness only: `get()` (scene, renderer, camera, controls,
data, theme, points, links, labels, chain, the links' curve `curvePts`), `setCamera(cam)`, `select(id)` (without the
camera flight) and `render()`. `updatePointScale` leaves `uScale` to a non-perspective camera, and `VL.spriteWpp`
(`site/js/labels3d.js`) sizes sprites for an orthographic camera. Nothing on the site calls them.

`setCamera` hands the camera to the page's OrbitControls, which keep it within `minDistance`..`maxDistance` (40..30000)
on every `update()`, and the page's frame loop calls `update()` on every frame. The figure's camera stands
`camera.distance` (60000) from the target, so `teaser.js` lifts both limits before the swap. Without that, the first
CI run (2026-11) had the camera pulled in to 30000 with near/far still at 52000..68000: the whole scene lay in front of
the near plane, and every capture came out uniformly white while the run reported success. An orthographic image does
not depend on the distance along the view axis, but the clipping planes, the depth fade and the points' scale do; so
before every capture `teaser.js` checks that the camera still looks along the configured direction at the configured
target, measures the scene's depth range in camera space (points, the links' lift, layer planes, subtree), puts near/far
around it (`TZ.clipPlanes`), sets the page's depth fade for the camera's distance as the page itself does
(`TZ.fog` = `updateFog`: from 0.4 R in front of the target to 1.9 R behind it, at most 0.6 in the light theme) and
the points' `uScale` for that distance.

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
The page's own frames run at pixel ratio 1; only the capture is rendered at its ratio.

A capture cannot pass blank. Right after the render, in the same task, the page reads the drawing buffer back
(`gl.readPixels`) and counts the pixels that differ from the background; `capture.py` counts them again on the PNG and
on `page.png`, and fails the run when any has fewer than `checks.min_ink_fraction` (1 %) or when the WebGL context was
lost. The first capture, `teaser_debug_pr1`, is a cheap pixel-ratio-1 check. Each capture's entry in
`teaser_capture.json` records the camera (type, position, target, distance, near/far, zoom, frustum, controls' limits),
the scene's depth range and whether it lies inside near..far, the scene fog (none) and the page's depth fade (near, far,
amount, colour and the fade at the scene's front, target and back), `renderer.info.render` (calls, triangles, points,
lines), the canvas (pixel and CSS size, rect, visibility, display, opacity, the element over its centre, the drawing
buffer, WebGL size limits, context state), both ink counts with their bounding box, and the context-loss events;
`console.log` has the page's console messages, page errors, crashes and failed requests, with times.

## Preview

    python scripts/site/teaser/preview.py --out preview.png --json anchors.json --fonts <dir with LibertinusSans-Regular.otf>

draws the same geometry from `site/data/legal_network.js` (straight-segment approximation of the curves, flat discs) and
drafts the paper's vector layer: call-outs in Libertinus Sans 8.5 pt on thin leaders in the clear margins and a flat
legend, as in the published Fig. 1. `--color-by validity` shows the site's colouring (its legend needs four rows and collides with the bottom call-outs).

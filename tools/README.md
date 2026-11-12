# VLOnto toolchain (`tools/`)

Pinned, tested build tools for the **Website** and **Playbook** tracks. Everything runs on the compute node
`the build node` (Ubuntu 26.04, x86_64, no root). All commands below assume:

```bash
V=/path/to/vlonto   # project root (= $VLONTO_ROOT, parent of the repo)
cd $V/repo                                                     # the future git tree of tmquan/VLOnto
W=$V/envs/web/bin                                              # python, node, npm, npx, pandoc, playwright
export PATH=$W:$PATH
```

## What is installed

| Tool | Version | Location | Pinned by |
|---|---|---|---|
| uv | 0.13.7 | `$V/tools/uv/uv` | release tarball sha256 (`versions.lock`) |
| CPython | 3.12.16 | `$V/tools/python/` | `uv python install` |
| env **web** | 29 packages | `$V/envs/web/` | `requirements-web.lock` (hash-checked `uv pip sync`) |
| pandoc | 3.9 | `$W/pandoc` (from pypandoc-binary 1.17) | lock |
| Node.js / npm | 24.19.0 / 11.17.0 | `$W/node`, `$W/npm`, `$W/npx` (nodejs-wheel 24.19.0) | lock |
| Playwright (Python API only) | 1.65.0 | env web | lock - no Playwright browsers are downloaded |
| fontTools+brotli, PyMuPDF, pypdfium2, Pillow, NumPy, Jinja2, markdown-it-py, BeautifulSoup | see lock | env web | lock |
| Typst | 0.15.1 (9dfd3a08) | `$V/tools/typst/typst` | sha256 |
| chrome-headless-shell | 157.0.8103.50 | `$V/tools/chrome/157.0.8103.50/` | sha256 (recorded on download) |
| 8 libraries Chrome lacks on the node | conda-forge | `$V/tools/chrome/lib/` | `chrome-deps.conda.lock` (md5) + per-file sha256 |
| micromamba | 2.10.0-0 | `$V/tools/micromamba/micromamba` | sha256 |
| esbuild | 0.28.2 | `$V/build/vendor-build/node_modules` | `vendor-build/package-lock.json` (sha512) |

rdflib / pyoxigraph / pySHACL / pyLODE belong to the Ontology KG track (`$V/envs/kg`), not to this env.
Every value above is printed and verified by `tools/setup_tools.sh --check`.

## 1. Create or verify the toolchain

```bash
tools/setup_tools.sh             # idempotent: downloads only what is missing, verifies every checksum/version
tools/setup_tools.sh --check     # verify only, never downloads; exit 1 on any drift
tools/setup_tools.sh --root DIR  # full install into another root (used to prove it re-creates from scratch)
tools/fetch_vendor.sh            # rebuild site/vendor + fonts; must be byte-identical to tools/vendor.lock.json
tools/fetch_vendor.sh --check-repo   # only compare the files in the repo with the lock
tools/fetch_vendor.sh --update-lock  # after changing a pin (versions.lock, vendor-build/package.json)
```

`fetch_vendor.sh` runs `npm ci --ignore-scripts` from the lock (npm verifies each tarball's sha512), compares
**every** lockfile integrity with registry.npmjs.org (68/68 match), downloads the five top-level tarballs again and
checks their sha512 itself, builds the bundles with esbuild, takes the two upstream UMD files from the verified
tarballs, collects licences, fetches the fonts from fixed commits and writes `vendor.lock.json`
(package, version, file, sha256, licence for all 93 outputs). Every output is scanned for credential-like patterns
(AWS access-key IDs, Google API keys, GitHub / Hugging Face / OpenAI-style / NVIDIA / Slack tokens, PEM private
keys) that GitHub push protection or Hugging Face secret scanning would flag; a match fails the build and
`--check-repo`. `--update-lock` updates `vendor-build/package-lock.json` on top of the existing lock, so unchanged
pins keep their resolved versions.

## 2. Pages must open from `file://` (Chrome, Safari, Firefox)

The user reviews the site by double-clicking `index.html` - no server, no browser flags. Chrome blocks ES modules,
`fetch()`/XHR of local files, Workers from files and `WebAssembly.instantiateStreaming` for `file://` pages, and
Firefox only loads `file://` fonts from the page's folder or below. Rules:

1. Classic `<script src>` only: no `type="module"`, no import maps, no dynamic `import()`.
2. No `fetch`/XHR: ship data as `data/<name>.js` made by `tools/json2js.py` (section 4).
3. All pages in the site root, assets in subfolders (`vendor/`, `fonts/`, `data/`, `css/`); relative URLs only
   (never `/x.js` or `//cdn...`); no external requests (everything vendored).
4. `<meta charset="utf-8">` in the first bytes of every page (data scripts inherit the page charset).
5. `#hash` routing instead of `history.pushState`; no service workers; no image textures loaded from files in
   WebGL (a `file://` image is cross-origin for WebGL in Chrome) - draw labels with SpriteText/canvas instead.
6. Normalise all text to **NFC** before writing data (`unicodedata.normalize("NFC", s)`); the legal corpus
   contains NFD text and JetBrains Mono NL has no mark positioning for decomposed diacritics.
7. Never break inside a word: no `overflow-wrap: anywhere` / `word-break: break-all` on table cells; keep document
   numbers, years and IDs `white-space: nowrap`, let prose wrap at spaces, and on phones (`max-width: 600px`) hide
   secondary columns such as IRIs (or use a stacked layout) instead of squeezing every column. Keep code lines short
   enough for 390 px (or shrink the code font there). site_check fails on mid-word breaks (`broken_word`).

Load order (from `site/vendor/README.md`, proven in `tools/tests/web/proof/webgl_test.html`):

```html
<meta charset="utf-8">
<link rel="stylesheet" href="fonts/fonts.css">
<script src="vendor/three/three.iife.min.js"></script>                   <!-- window.THREE: r187 + OrbitControls, TrackballControls, CSS2DRenderer, CSS2DObject -->
<script src="vendor/three-spritetext/three-spritetext.min.js"></script>   <!-- window.SpriteText (upstream UMD, uses window.THREE) -->
<script src="vendor/3d-force-graph/3d-force-graph.iife.min.js"></script>  <!-- window.ForceGraph3D (built with 'three' = window.THREE) -->
<script src="vendor/echarts/echarts.min.js"></script>                    <!-- window.echarts (upstream UMD) -->
<script src="vendor/oxigraph/oxigraph.iife.min.js"></script>             <!-- window.oxigraph + window.oxigraphReady (Promise) -->
<script src="data/graph.js"></script>                                    <!-- window.VLONTO.graph -->
```

*Shared THREE.* The upstream `3d-force-graph.min.js` UMD bundles its own private copy of three.js
(`global.ForceGraph3D = factory()`), while `three-spritetext`'s UMD binds to the global `THREE`
(`factory(global.THREE)`); mixing them gives two three.js instances. We therefore compile 3d-force-graph from its ESM
sources with esbuild and map `three` (and `three/webgpu`, imported by three-render-objects only for its optional
WebGPU renderer) to `window.THREE`. The proof page checks `graph.scene() instanceof THREE.Scene`,
`graph.camera() instanceof THREE.PerspectiveCamera` and `new SpriteText('x') instanceof THREE.Sprite` (all true, over
http:// and file://) and fails on the console warning "Multiple instances of Three.js".

*Oxigraph.* `oxigraph.iife.min.js` (2,550,203 bytes) embeds the 4,324,920-byte wasm as one lowercase string:
zlib-deflated with fflate 0.8.3 (pure JS, so the bytes do not depend on the CPU) to 1,577,243 bytes, then RFC 4648
base32 in lower case without padding (2,523,589 characters of `a-z2-7`). Base64 is not used because random base64
contains credential-like strings by chance (the previous 5.8 MB base64 build had 5 AWS-key-ID look-alikes). At load
the script decodes the string (about 13 ms), inflates it with the browser's `DecompressionStream('deflate')`
(Chrome 80+, Firefox 113+, Safari 16.4+; about 20 ms) or, where that is missing, with the bundled fflate inflater
(about 42 ms), and instantiates it with `WebAssembly.instantiate(bytes)`; `window.oxigraphTiming` reports the
times and the inflater used. End to end (navigation start to `oxigraphReady`, median of 9 loads at 1440x900 on the
node) the proof page is ready in 70 ms (file:// and http://), 90 ms on the fflate path, against 48-51 ms for the
old base64 build. Usage is unchanged:

```js
oxigraphReady.then(ox => {
  const store = new ox.Store();
  store.load(window.VLONTO.kg_ttl, { format: 'text/turtle', base_iri: 'https://tmquan.github.io/VLOnto/id/' });
  for (const row of store.query('SELECT ?s ?o WHERE { ?s ?p ?o } LIMIT 10')) console.log(row.get('s').value);
});
```

*Canvas text* (SpriteText labels, ECharts) is drawn once, so wait for the web font first:
`document.fonts.load('400 16px "Be Vietnam Pro"').then(start)`; set `sprite.fontFace` and ECharts
`textStyle.fontFamily` to `"Be Vietnam Pro"`. Canvas text is not visible to site_check's DOM checks, so look at the
screenshots: a camera distance that fits a label at 1440x900 cuts it off at 390x844 (the perspective camera keeps a
fixed vertical field of view), so scale the distance by the canvas aspect ratio as `webgl_test.html` does
(`k = max(1, 0.95 / (width / height))`, 1.62 on the 390x844 run).

## 3. Fonts (SIL OFL 1.1, licences next to the files)

| Role | Family (files) | Source |
|---|---|---|
| sans: UI, headings, web body | Be Vietnam Pro 1.002 - Regular, Italic, Medium, SemiBold, Bold, BoldItalic | google/fonts @ 5bb28733 |
| serif: long-form PDF body | Noto Serif 2.015 - Regular, Italic, Bold, BoldItalic | notofonts.github.io @ 4cf78353 |
| mono: code, IRIs | JetBrains Mono **NL** 2.304 (no ligatures: `<=`, `->` stay literal) - Regular, Italic, Bold, BoldItalic | JetBrains release v2.304 |
| fallback: ✓ ✗ dingbats | Noto Sans Symbols 2 2.008 | notofonts @ 4cf78353 |
| fallback: → ← ≤ ≥ ≠ ⇒, math | Noto Sans Math 3.000 (also the Typst math font) | notofonts @ 4cf78353 |

Why: Be Vietnam Pro is designed for Vietnamese stacked diacritics; Noto Serif covers all of Vietnamese; JetBrains
Mono NL is the only text family that covers all 18 required symbols. Coverage (fontTools, `font_coverage.py`): every
text family has 95/95 ASCII and 146/146 Vietnamese letters; Be Vietnam Pro lacks → ← ✓ ✗, Noto Serif lacks → ← ✓ ✗
≤ ≥, so each stack ends with Noto Sans Symbols 2 and Noto Sans Math. The 7 production stacks (sans, sans bold,
serif with math routing, mono as TTF; sans, serif with routing, mono as web woff2) cover 95/95 ASCII, 146/146
Vietnamese letters, 18/18 symbols and 11/11 extras (₫ « » ↔ ⇒ ≠ ± © ® ™ ½); the report keeps an unrouted serif stack
to show the detected decomposition (≠ by Noto Serif, 10/11 extras). Full table: `font_coverage.md` from run_proofs.

* Typst: `--font-path typst/fonts` (TTF). Web: `site/fonts/fonts.css` (woff2, symbol fonts subset to their blocks
  with matching `unicode-range`) or `site/fonts/fonts-embedded.css` (data: URIs, works from any folder).
* CSS stacks (defined in both CSS files): `font-family: var(--vlo-font-sans)` / `var(--vlo-font-serif)` / `var(--vlo-font-mono)`.
* Noto Serif lacks ≠ but has `=` and U+0338, so Chrome **and** Typst (HarfBuzz) draw ≠ from Noto Serif as
  `=` + combining overlay (seen as "=/") instead of falling back. Both sides therefore route arrows and operators
  (U+2190-21FF, U+2200-22FF) to Noto Sans Math first: on the web `--vlo-font-serif` starts with
  `"VLOnto Math Symbols"` (the Noto Sans Math subset with that `unicode-range`), in Typst a font entry with
  `covers`. site_check (`glyph_decomposition`), pdf_check and font_coverage.py flag such decomposed drawing.
* Typst stacks:

```typst
#let math-symbols = (name: "Noto Sans Math", covers: regex("[\u{2190}-\u{21FF}\u{2200}-\u{22FF}]"))
#let sans  = ("Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math")
#let serif = (math-symbols, "Noto Serif", "Noto Sans Symbols 2", "Noto Sans Math")
#let mono  = ("JetBrains Mono NL", "Noto Sans Symbols 2", "Noto Sans Math")
#set text(font: serif, lang: "vi")
#show heading: set text(font: sans)
#show raw: set text(font: mono)
#show math.equation: set text(font: "Noto Sans Math")
```

## 4. Site data: `tools/json2js.py`

```bash
$W/python tools/json2js.py build/kg/graph.json -o site/data/graph.js --verify          # window.VLONTO["graph"]
$W/python tools/json2js.py a.json b.json --out-dir site/data                           # one file per input
$W/python tools/json2js.py ontology.ttl --text --name ontology_ttl -o site/data/ontology_ttl.js
```

Output is deterministic: `(window.VLONTO = window.VLONTO || {})["graph"] = JSON.parse("...");` (UTF-8; `--ascii`
for \uXXXX escapes). `--verify` re-loads the file in Node and compares with the input. Files above 95 MB are refused
(GitHub's limit is 100 MB) - split them.

## 5. Headless Chrome: `tools/chrome.sh`

Wrapper around chrome-headless-shell with the private libraries, a generated fontconfig exposing only `typst/fonts`
(missing glyphs show up as missing instead of being covered by a system font), SwiftShader WebGL
(`--use-angle=swiftshader --enable-unsafe-swiftshader`, renderer "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device
(Subzero) ...))", WebGL 2.0) and `--no-sandbox`. It never adds `--allow-file-access-from-files`.

```bash
tools/chrome.sh --version
tools/chrome.sh --screenshot=$V/build/shot.png --window-size=1440,900 --virtual-time-budget=8000 file://$V/repo/site/index.html
```
Playwright: `p.chromium.launch(executable_path="$V/repo/tools/chrome.sh")`.

## 6. `tools/site_check.py` - render checks over http:// and file://

```bash
$W/python tools/site_check.py --root site --all --out $V/build/site_check            # every *.html in site/
$W/python tools/site_check.py --root site --pages index.html,graph.html --out $V/build/site_check
$W/python tools/site_check.py --root site --config site_check.json --out $V/build/site_check
```

Each page x {http://127.0.0.1 server, file://} x {1440x900, 390x844 mobile}. Failures: page load / ready timeout,
failed or blocked requests (CORS, file://, 4xx/5xx), requests outside the site root, console errors and page
errors, blank canvases (pixel std >= 2 and >= 1 % non-background), horizontal overflow against the device width,
clipped text, overlapping text, words broken inside (a line break between two letters/digits such as "N|ă|m" or
"20|24", typical of `overflow-wrap: anywhere` in a narrow table cell; breaks after `/ - . :` are allowed), fonts
that failed to load, characters no declared web font covers (cmaps read from
the real woff2/ttf/data: files, walked in stack order), characters the first matching font would draw by
decomposition, mojibake, broken images, and a static file:// lint of HTML/CSS/own JS. Warnings (not failures):
console warnings, non-NFC text, stacks starting with a local font, text drawn with local fonts (`--strict-fonts`
makes that a failure).
Writes `site_check_report.json`, `site_check_report.md`, `shots/*.png` (full page) and `canvas/*.png`.
Exit 0 = pass, 1 = failures, 2 = setup error. Page config (`--config`):
`{"pages": [{"path": "graph.html", "ready": "window.__VLONTO_READY === true", "min_canvases": 1,
"expect_webgl": true, "settle_ms": 1500, "fail_on_warning": ["Multiple instances of Three\\.js"]}]}`.
Pages may set `window.__VLONTO_READY = true` when drawn (waited for automatically) and `window.__VLONTO_METRICS = {...}`
(copied into the report). Intentional exceptions: `data-sc-allow="overlap|clip|overflow|wrap|all"` on an element.

## 7. Typst, pandoc, node

```bash
TY=$V/tools/typst/typst
SOURCE_DATE_EPOCH=1767225600 $TY compile --root playbook --font-path typst/fonts --ignore-system-fonts \
    --ignore-embedded-fonts playbook/playbook.typ $V/build/playbook.pdf
$W/pandoc playbook/playbook.md -f markdown -s -t typst --template playbook/template.typ -o playbook/playbook.typ
$W/pandoc -D typst                                                          # pandoc's own template, for its helpers
$W/node --version; $W/npm --version
```

* Always pass `--ignore-system-fonts --ignore-embedded-fonts` so only `typst/fonts` can be used (Typst otherwise falls
  back silently to its embedded Libertinus / New Computer Modern / DejaVu Sans Mono).
* Typst draws a missing glyph as an invisible-or-box `.notdef` **without any warning** - run pdf_check.
* Reproducible: `--creation-timestamp` / `SOURCE_DATE_EPOCH` fixes the date; the proof document rebuilds
  byte-identically. Other flags: `--pdf-standard a-2b|ua-1|...`, `--no-pdf-tags`, `--input k=v`, `--package-path`.
* Typst packages (`@preview/...`) are downloaded at compile time - avoid them or vendor them via `--package-path`.
* pandoc: use a pandoc **template** (proven: `tools/tests/typst/pandoc_template.typ` imports the font setup, defines
  `#let horizontalrule = line(...)` used by `---`, then `$body$`). Do not `#include` a pandoc body from a wrapper:
  Typst evaluates included files in their own scope, so the body cannot see the wrapper's helpers.

## 8. `tools/pdf_check.py` - PDF render checks

```bash
$W/python tools/pdf_check.py $V/build/playbook.pdf --fonts typst/fonts --margins 22mm,20mm,24mm,20mm \
    --out $V/build/pdf_check --rebuild-cmd "bash build_pdf.sh" --rebuild-output $V/build/playbook.pdf
```

Checks: fonts embedded; every font is one of `--fonts` (catches Typst fallbacks); no `.notdef` (tofu) glyph; every
character in the cmap of the font that drew it (and no precomposed letter drawn by decomposition); no empty glyph
outlines; no glyph outside the page or beyond the left/right margins (punctuation may hang by its own width, like
Typst's `overhang`); baselines inside top/bottom margins except header/footer zones, which keep `--edge` (5 mm) from
the paper edge; no overlapping text lines; images inside margins; no blank pages; with `--rebuild-cmd`, two rebuilds
must be byte-identical. Renders `pages/page-NNN.png` (`--dpi 110`) and `contact_sheet.png` - look at them.

## 9. Proofs: `tools/tests/run_proofs.sh`

```bash
bash tools/tests/run_proofs.sh $V/build/toolchain-proofs     # prints one EXPECT line per proof
```

| Proof | Expected |
|---|---|
| `json2js.py --verify` on graph JSON, Turtle text, stats JSON | exit 0 |
| `font_coverage.py --require-full` on the vendored fonts and 8 stacks | PASS |
| site_check on webgl_test, oxigraph_test, fonts_test, fonts_embedded_test (http + file, 2 viewports) | 16/16 PASS (final run: WebGL first frame 41-47 ms, 10-29 fps, shared THREE; Oxigraph ready 64-67 ms after navigation start, 8 rows; 0 broken words) |
| site_check on `sample_site/defects.html` (mobile overflow, clipped badge, overlap, CJK glyphs, ≠ decomposed by Noto Serif, missing image, words broken inside a too-narrow cell, ES module, fetch) | FAIL on all 4 runs (by design); module/fetch only under file:// |
| site_check on `sample_site/index.html` (the fixed page) | 4/4 PASS |
| pdf_check on `sample_bad.pdf` (tofu 法律, code line past the margin, label off the page) | FAIL (by design): 2 tofu glyphs, 32 glyphs out of bounds |
| pdf_check on `sample_ok.pdf` + 2 rebuilds | PASS, both rebuilds byte-identical to the checked PDF |
| pandoc Markdown -> Typst -> PDF + pdf_check | PASS |

## 10. Limits

* Rendering is tested in Chromium only. Firefox and Safari behaviour under `file://` is covered by the rules in
  section 2 (classic scripts, no fetch, fonts below the page folder or embedded, wasm from bytes) but not machine-tested.
  A best-effort Firefox 160.0 probe on the node did not run: libxul needs the GTK3 / cairo / pango / gdk-pixbuf stack
  (22 unresolved libraries) and building that conda-forge environment failed. Open the site in Firefox and Safari on
  the Mac before publishing.
* WebGL runs on SwiftShader (CPU): about 10 fps for 2,000 nodes at 1440x900; real GPUs are much faster.
* site_check cannot see text drawn into canvases (SpriteText, ECharts); check those in the screenshots.
* Chrome for Testing publishes no checksums; `CHROME_SHA256` is the value recorded at the first download.

"""Capture the paper's Fig. 1 from the 3D legal network in headless Chrome (the pinned chrome-headless-shell).

    python scripts/site/teaser/capture.py --out OUT [--chrome tools/chrome.sh] [--mode http|file] [--only NAME ...]

Serves the repository root over http (or opens the page from file://), loads scripts/site/teaser/teaser.html at the
viewport of teaser_config.json, waits for window.__TEASER.ready (the harness waits on the page's own metrics: no sleeps),
then for every capture of the config asks the page for a PNG of its WebGL canvas at that pixel ratio and colouring.
Writes OUT/<name>.png, OUT/teaser_capture.json (camera, selection, anchors in CSS px and figure points, the traced
paths, the harness's steps, page metrics and the PNGs' sha256), OUT/page.png (the viewport, for a quick look) and
OUT/console.log (the page's console messages, page errors, crashes and failed requests, with times, written as they
come). Every capture's entry carries the page's diagnostics (camera, clipping planes, depth fade, the scene's depth range,
draw counts, canvas, WebGL limits and context events) and two ink counts: the page's gl.readPixels right after the
render, and this script's count on the PNG. Exits non-zero when the harness reports an error, a PNG has the wrong size,
a capture or page.png is blank (fewer than checks.min_ink_fraction of the pixels differ from the page background), the
WebGL context was lost, or the page logs an error.
Waits scale with VLONTO_TIMEOUT_SCALE (CI: 4). Python: playwright (tools/requirements-web.lock) and Pillow.
"""
import argparse, base64, functools, hashlib, http.server, io, json, os, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCALE = max(1.0, float(os.environ.get("VLONTO_TIMEOUT_SCALE") or 1))


def ms(x):
    return int(x * SCALE)


def make_server(root):
    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript",
                          ".woff2": "font/woff2", ".json": "application/json", ".css": "text/css", ".html": "text/html"}

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def ink(im, bg):
    """fraction of pixels that differ from the background colour bg (any channel by more than 2), and their bbox"""
    from PIL import Image, ImageChops
    rgb = im.convert("RGB")
    d = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).split()
    m = ImageChops.lighter(ImageChops.lighter(d[0], d[1]), d[2]).point(lambda v: 255 if v > 2 else 0)
    n = m.histogram()[255]
    return dict(fraction=round(n / (rgb.size[0] * rgb.size[1]), 6), nonbg=n, total=rgb.size[0] * rgb.size[1], bbox_px=m.getbbox())


def hex_rgb(h):
    h = (h or "#ffffff").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--chrome", default=str(REPO / "tools" / "chrome.sh"))
    ap.add_argument("--mode", choices=["http", "file"], default="http")
    ap.add_argument("--only", nargs="*", help="capture names (default: all of teaser_config.json)")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    from PIL import Image
    cfg = json.loads((HERE / "teaser_config.json").read_text(encoding="utf-8"))
    names = a.only or [c["name"] for c in cfg["captures"]]
    vw, vh = cfg["viewport"]["width"], cfg["viewport"]["height"]
    min_ink = float((cfg.get("checks") or {}).get("min_ink_fraction", 0.01))
    a.out.mkdir(parents=True, exist_ok=True)
    errors, problems, t0 = [], [], time.time()
    logf = open(a.out / "console.log", "w", encoding="utf-8")

    def log(kind, text):
        line = "%8.1f s [%s] %s" % (time.time() - t0, kind, text)
        logf.write(line + "\n")
        logf.flush()
        if kind in ("error", "pageerror", "crash"):
            errors.append(line)

    srv = make_server(REPO) if a.mode == "http" else None
    q = "?ds=%s&theme=%s" % (cfg["page"]["dataset"], cfg["page"]["theme"])
    url = ("http://127.0.0.1:%d/scripts/site/teaser/teaser.html" % srv.server_address[1] if srv
           else (HERE / "teaser.html").as_uri()) + q
    result = dict(url=url.split("/scripts/")[-1], mode=a.mode, timeout_scale=SCALE, min_ink_fraction=min_ink, captures=[], ok=False)
    pg = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=a.chrome, headless=True)
            result["browser"] = browser.version
            ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1,
                                      color_scheme="dark" if cfg["page"]["theme"] == "dark" else "light")
            pg = ctx.new_page()

            def on_console(m):
                loc = m.location or {}
                where = (" (%s:%s)" % (loc.get("url", "").split("/")[-1], loc.get("lineNumber"))) if loc.get("url") else ""
                log(m.type, m.text + where)

            pg.on("console", on_console)
            pg.on("pageerror", lambda e: log("pageerror", str(e)))
            pg.on("crash", lambda _p: log("crash", "the page crashed"))
            pg.on("requestfailed", lambda r: log("requestfailed", "%s %s" % (r.url.split("/scripts/")[-1].split("/site/")[-1], r.failure)))
            pg.goto(url, wait_until="load", timeout=ms(180000))
            pg.wait_for_function("window.__TEASER && (window.__TEASER.ready === true || !!window.__TEASER.error)",
                                 timeout=ms(1800000), polling=500)
            err = pg.evaluate("window.__TEASER.error")
            if err:
                raise RuntimeError("harness: " + err)
            ready = pg.evaluate("window.__TEASER.steps.filter(s => s.step === 'scene ready')[0] || null")
            if ready:
                print("scene ready: %s" % json.dumps(ready.get("info"), ensure_ascii=False), flush=True)
            bg = hex_rgb((pg.evaluate("window.__VLONTO_METRICS && window.__VLONTO_METRICS.sceneBg") or "#ffffff"))
            for name in names:
                t1 = time.time()
                r = pg.evaluate("""([n, limit]) => Promise.race([window.__TEASER.capture(n),
                    new Promise((res, rej) => setTimeout(() => rej(new Error('capture ' + n + ' took over ' + limit + ' ms')), limit))])""",
                                [name, ms(240000)])
                png = base64.b64decode(r["url"].split(",", 1)[1])
                path = a.out / (name + ".png")
                path.write_bytes(png)
                im = Image.open(io.BytesIO(png))
                cap = next(c for c in cfg["captures"] if c["name"] == name)
                want = (round(vw * cap["pixelRatio"]), round(vh * cap["pixelRatio"]))
                k = ink(im, bg)
                d = r.get("diag") or {}
                entry = dict(name=name, file=path.name, size=list(im.size), bytes=len(png), sha256=hashlib.sha256(png).hexdigest(),
                             seconds=round(time.time() - t1, 1), ink_png=k["fraction"], ink_png_bbox_px=k["bbox_px"],
                             ink_readpixels=r.get("ink"), blank=bool(r.get("blank")) or k["fraction"] < min_ink, diag=d)
                result["captures"].append(entry)
                cam, fog, rd = d.get("camera") or {}, (d.get("fog") or {}).get("depth_fade") or {}, d.get("render") or {}
                sd = d.get("scene_depth") or {}
                print("captured %s %dx%d in %.0f s: ink %.2f %% (readPixels %.2f %%), %s draw calls, scene depth %.0f..%.0f in clip %.0f..%.0f,"
                      " fade %.0f..%.0f x%.2f" % (name, im.size[0], im.size[1], time.time() - t1, 100 * k["fraction"], 100 * (r.get("ink") or 0),
                                                  rd.get("calls"), sd.get("min") or 0, sd.get("max") or 0, cam.get("near") or 0, cam.get("far") or 0,
                                                  fog.get("near") or 0, fog.get("far") or 0, fog.get("amount") or 0), flush=True)
                if im.size != want:
                    problems.append("%s: %s px, expected %s" % (name, im.size, want))
                if entry["blank"]:
                    problems.append("%s is blank: %.4f %% of the pixels differ from the background (readPixels %.4f %%)"
                                    % (name, 100 * k["fraction"], 100 * (r.get("ink") or 0)))
            result["teaser"] = pg.evaluate("window.__TEASER.json")
            result["steps"] = pg.evaluate("window.__TEASER.steps")
            result["events"] = pg.evaluate("window.__TEASER.events")
            result["metrics"] = pg.evaluate("window.__VLONTO_METRICS")
            pg.screenshot(path=str(a.out / "page.png"))
            k = ink(Image.open(a.out / "page.png"), bg)
            result["page_png"] = dict(ink=k["fraction"], bbox_px=k["bbox_px"])
            if k["fraction"] < min_ink:
                problems.append("page.png is blank: %.4f %% of the pixels differ from the background" % (100 * k["fraction"]))
            if any(e.get("type") == "webglcontextlost" for e in result["events"] or []):
                problems.append("the WebGL context was lost: %s" % result["events"])
            browser.close()
        if errors:
            problems.append("page errors: %s" % errors[:5])
        if problems:
            raise RuntimeError("; ".join(problems))
        result["ok"] = True
    except Exception as e:                                         # report, then fail the job
        result["error"] = str(e)
        print("CAPTURE FAILED:", e, file=sys.stderr)
    finally:
        result["seconds"] = round(time.time() - t0, 1)
        (a.out / "teaser_capture.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        logf.close()
        if srv:
            srv.shutdown()
    print("CAPTURE: %s in %.0f s -> %s" % ("OK" if result["ok"] else "FAIL", result["seconds"], a.out))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()

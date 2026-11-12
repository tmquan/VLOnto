"""Capture the paper's Fig. 1 from the 3D legal network in headless Chrome (the pinned chrome-headless-shell).

    python scripts/site/teaser/capture.py --out OUT [--chrome tools/chrome.sh] [--mode http|file] [--only NAME ...]

Serves the repository root over http (or opens the page from file://), loads scripts/site/teaser/teaser.html at the
viewport of teaser_config.json, waits for window.__TEASER.ready (the harness waits on the page's own metrics: no sleeps),
then for every capture of the config asks the page for a PNG of its WebGL canvas at that pixel ratio and colouring.
Writes OUT/<name>.png, OUT/teaser_capture.json (camera, selection, anchors in CSS px and figure points, the traced
paths, the harness's steps, page metrics and the PNGs' sha256), OUT/page.png (the viewport, for a quick look) and
OUT/console.log. Exits non-zero when the harness reports an error, a PNG has the wrong size, or the page logs an error.
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
    a.out.mkdir(parents=True, exist_ok=True)
    log, errors, t0 = [], [], time.time()
    srv = make_server(REPO) if a.mode == "http" else None
    q = "?ds=%s&theme=%s" % (cfg["page"]["dataset"], cfg["page"]["theme"])
    url = ("http://127.0.0.1:%d/scripts/site/teaser/teaser.html" % srv.server_address[1] if srv
           else (HERE / "teaser.html").as_uri()) + q
    result = dict(url=url.split("/scripts/")[-1], mode=a.mode, timeout_scale=SCALE, captures=[], ok=False)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=a.chrome, headless=True)
            result["browser"] = browser.version
            ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1,
                                      color_scheme="dark" if cfg["page"]["theme"] == "dark" else "light")
            pg = ctx.new_page()
            pg.on("console", lambda m: log.append("[%s] %s" % (m.type, m.text)))
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(url, wait_until="load", timeout=ms(180000))
            pg.wait_for_function("window.__TEASER && (window.__TEASER.ready === true || !!window.__TEASER.error)",
                                 timeout=ms(1800000), polling=500)
            err = pg.evaluate("window.__TEASER.error")
            if err:
                raise RuntimeError("harness: " + err)
            for name in names:
                t1 = time.time()
                r = pg.evaluate("n => window.__TEASER.capture(n)", name)
                png = base64.b64decode(r["url"].split(",", 1)[1])
                path = a.out / (name + ".png")
                path.write_bytes(png)
                im = Image.open(io.BytesIO(png))
                cap = next(c for c in cfg["captures"] if c["name"] == name)
                want = (round(vw * cap["pixelRatio"]), round(vh * cap["pixelRatio"]))
                if im.size != want:
                    raise RuntimeError("%s: %s px, expected %s" % (name, im.size, want))
                result["captures"].append(dict(name=name, file=path.name, size=list(im.size), bytes=len(png),
                                               sha256=hashlib.sha256(png).hexdigest(), seconds=round(time.time() - t1, 1)))
                print("captured %s %dx%d in %.0f s" % (name, im.size[0], im.size[1], time.time() - t1), flush=True)
            result["teaser"] = pg.evaluate("window.__TEASER.json")
            result["steps"] = pg.evaluate("window.__TEASER.steps")
            result["metrics"] = pg.evaluate("window.__VLONTO_METRICS")
            pg.screenshot(path=str(a.out / "page.png"))
            browser.close()
        bad = [l for l in log if l.startswith("[error]")]
        if errors or bad:
            raise RuntimeError("page errors: %s" % (errors + bad)[:5])
        result["ok"] = True
    except Exception as e:                                         # report, then fail the job
        result["error"] = str(e)
        print("CAPTURE FAILED:", e, file=sys.stderr)
    finally:
        result["seconds"] = round(time.time() - t0, 1)
        (a.out / "teaser_capture.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (a.out / "console.log").write_text("\n".join(log + ["[pageerror] " + e for e in errors]) + "\n", encoding="utf-8")
        if srv:
            srv.shutdown()
    print("CAPTURE: %s in %.0f s -> %s" % ("OK" if result["ok"] else "FAIL", result["seconds"], a.out))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()

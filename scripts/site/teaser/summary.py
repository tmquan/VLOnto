"""Markdown summary of a Fig. 1 capture run (OUT/teaser_capture.json) for the GitHub job summary.

    python scripts/site/teaser/summary.py OUT [--append FILE]
"""
import json, sys
from pathlib import Path


def main():
    out = Path(sys.argv[1])
    f = out / "teaser_capture.json"
    lines = ["## Fig. 1 capture (scripts/site/teaser)", ""]
    if not f.exists():
        lines.append("No teaser_capture.json: the capture did not start.")
    else:
        r = json.loads(f.read_text(encoding="utf-8"))
        t = r.get("teaser") or {}
        lines.append("**%s** in %s s, %s, browser %s, timeout scale %s" % ("OK" if r.get("ok") else "FAIL", r.get("seconds"),
                     r.get("mode"), r.get("browser"), r.get("timeout_scale")))
        if r.get("error"):
            lines += ["", "Error: `%s`" % r["error"]]
        sel, page = t.get("selection") or {}, t.get("page") or {}
        if sel:
            lines += ["", "Selection %s, chain %s, %s neighbours; page: %s nodes, %s links, curves %s, %s fps, WebGL %s" % (
                sel.get("doc"), " > ".join(sel.get("chain") or []), sel.get("egoHop1"), page.get("nodes"), page.get("edges"),
                page.get("curves"), page.get("fps"), page.get("webglRenderer"))]
        if r.get("captures"):
            lines += ["", "| capture | size | ink PNG | ink readPixels | draw calls | scene depth in near..far | bytes | sha256 | s |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for c in r["captures"]:
                d = c.get("diag") or {}
                cam, sd, rd = d.get("camera") or {}, d.get("scene_depth") or {}, d.get("render") or {}
                depth = ("%.0f..%.0f in %.0f..%.0f" % (sd["min"], sd["max"], cam.get("near", 0), cam.get("far", 0))) if sd else "-"
                ink = lambda v: "-" if v is None else "%.2f %%" % (100 * v)
                lines.append("| %s%s | %dx%d | %s | %s | %s | %s | %d | `%s` | %s |" % (
                    c["name"], " **BLANK**" if c.get("blank") else "", c["size"][0], c["size"][1], ink(c.get("ink_png")),
                    ink(c.get("ink_readpixels")), rd.get("calls", "-"), depth, c["bytes"], c["sha256"][:16], c["seconds"]))
        if r.get("page_png"):
            lines += ["", "page.png ink: %.2f %%" % (100 * r["page_png"]["ink"])]
        if r.get("events"):
            lines += ["", "WebGL context events: %s" % r["events"]]
        if r.get("steps"):
            lines += ["", "Steps: " + "; ".join("%s %.0f s" % (s["step"], s["ms"] / 1000) for s in r["steps"])]
    text = "\n".join(lines) + "\n"
    if "--append" in sys.argv:
        with open(sys.argv[sys.argv.index("--append") + 1], "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main()

"""Offline composition preview of the paper's Fig. 1 capture (no browser): the build-time coordinates of
site/data/legal_network.js drawn with matplotlib through the camera of teaser_config.json, as teaser.js will draw them.

    python scripts/site/teaser/preview.py --out preview.png [--json anchors.json] [--fonts DIR] [--dpi 300]

What it mirrors from the page (site/js/network3d.js, js/paper3d.js, css/site.css; the light paper theme): positions
(x, z * ZS, y), layer planes, point sizes (by rank and degree), validity colours, link colours and opacities, the
links' cubic Bezier curves (constants checked against network3d.js), the selection's neighbourhood, the depth fade and
the traced chain; and from teaser.js: the orthographic camera, the faded context, the trace widths, and the trace
subtree hung from the Labor Code (the same frame and offsets as teaser-core.js). Points are flat discs with a rim and
lines have a fixed width, so the preview fixes the camera, framing and clear space, not the final look.
It also drafts the vector layer of the paper figure (call-outs on thin leaders in the clear margins, the flat legend;
Libertinus Sans 8.5 pt as in the published Fig. 1) and writes the anchors (figure points, origin top left).
Needs numpy and matplotlib (not part of the CI lock; the capture itself does not use this script).
"""
import argparse, json, math, os, re, sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import to_rgb

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SITE = os.path.join(REPO, "site")
ZS = 2.2
BASE = np.array([44, 22, 16, 11, 10, 9])                          # network3d.js buildScene: base size by rank
EDGE_OPACITY = {"replaced": .95, "amended": .9, "repealed": .92, "partially_repealed": .88, "partially_expired": .88,
                "basis": .2, "citation": .13}                      # light theme
KINDS = ["replaced", "amended", "repealed", "partially_repealed", "partially_expired"]
BEND, LAYER_GAP = 0.18, 150 * ZS
LIFT_MAX = 0.4 * LAYER_GAP
TRACE_W_CSS = {"core": 2.8, "halo": 6.4, "halo2": 9.2}            # paper3d.js TRACE_W (CSS px)


def js_twin(path, key):
    raw = open(path, encoding="utf-8").read()
    i = raw.index('window.VLONTO["%s"]' % key)
    return json.loads(raw[raw.index("=", i) + 1:].strip().rstrip(";"))


def check_page_constants():
    src = open(os.path.join(SITE, "js", "network3d.js"), encoding="utf-8").read()
    need = ["var ZS = 2.2;", "var BEND = 0.18, LAYER_GAP = 150 * ZS, LIFT_MAX = 0.4 * LAYER_GAP;",
            "base = [44, 22, 16, 11, 10, 9]", "2.6 * Math.log2(1 + D.degree[i])",
            "light: { replaced: 0.95, amended: 0.9, repealed: 0.92, partially_repealed: 0.88, partially_expired: 0.88, basis: 0.2, citation: 0.13 }",
            "float k = 0.45 * d.y, lift = min(uBend * length(d.xz), uLiftMax) * clamp(1.0 - abs(d.y) / uLayer, 0.0, 1.0);"]
    miss = [n for n in need if n not in src]
    if miss:
        sys.exit("network3d.js changed; update preview.py for: " + "; ".join(miss))


def tokens():
    css = re.sub(r"/\*.*?\*/", "", open(os.path.join(SITE, "css", "site.css"), encoding="utf-8").read(), flags=re.S)
    tok = {}
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if "paper" in sel and "dark" not in sel.replace(':not([data-theme="dark"])', ""):
            tok.update({k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)})
    return tok


def curve(A, B, n):
    """network3d.js curvePoint for arrays of endpoints A, B (m x 3): (m, n + 1, 3) points"""
    d = B - A
    k = 0.45 * d[:, 1]
    lift = np.minimum(BEND * np.hypot(d[:, 0], d[:, 2]), LIFT_MAX) * np.clip(1 - np.abs(d[:, 1]) / LAYER_GAP, 0, 1)
    t = np.linspace(0, 1, n + 1)[None, :]
    u = 1 - t
    w0, w1, w2, w3 = u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3
    x = (w0 + w1) * A[:, :1] + (w2 + w3) * B[:, :1]
    z = (w0 + w1) * A[:, 2:3] + (w2 + w3) * B[:, 2:3]
    y = w0 * A[:, 1:2] + w1 * (A[:, 1:2] + (k + lift)[:, None]) + w2 * (B[:, 1:2] - (k - lift)[:, None]) + w3 * B[:, 1:2]
    return np.stack([x, y, z], -1)


class Camera:
    """teaser-core.js: TZ.basis / TZ.toScreen, in figure points (origin top left)"""
    def __init__(self, cfg):
        c = cfg["camera"]
        a, e = math.radians(c["azimuth_deg"]), math.radians(c["elevation_deg"])
        self.back = np.array([math.cos(e) * math.sin(a), math.sin(e), math.cos(e) * math.cos(a)])
        self.right = np.array([math.cos(a), 0, -math.sin(a)])
        self.up = np.array([-math.sin(e) * math.sin(a), math.cos(e), -math.sin(e) * math.cos(a)])
        self.t = np.array(c["target"], float)
        self.hh = c["half_height"]
        self.W, self.H = cfg["figure"]["width_pt"], cfg["figure"]["height_pt"]
        vw, vh = cfg["viewport"]["width"], cfg["viewport"]["height"]
        self.hw = self.hh * vw / vh
        self.pt_per_world = self.H / (2 * self.hh) * (vh / vw) * (self.W / self.H) * (vw / vh) if False else self.W / (2 * self.hw)

    def screen(self, P):
        P = np.asarray(P, float)
        d = P - self.t
        sx, sy = d @ self.right, d @ self.up
        depth = -(d @ self.back)
        return np.stack([(sx / self.hw + 1) / 2 * self.W, (1 - sy / self.hh) / 2 * self.H, depth], -1)


def frame(L):
    out = np.array([L[0], 0, L[2]]) / math.hypot(L[0], L[2])
    return out, np.array([out[2], 0, -out[0]])


def subtree_positions(L, offsets):
    out, side = frame(L)
    return {k: L + out * o[0] + side * o[2] - np.array([0, o[1], 0]) for k, o in offsets.items()}


def shade(hex_, f):
    return tuple(min(1, max(0, c * f)) for c in to_rgb(hex_))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "teaser_config.json"))
    ap.add_argument("--trace", default=os.path.join(HERE, "trace_138008514.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    ap.add_argument("--fonts", help="directory with LibertinusSans-Regular.otf (else matplotlib's default sans)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--no-vector", action="store_true", help="only the capture layer (no call-outs, no legend)")
    ap.add_argument("--color-by", choices=["class", "validity"], help="override page.colorBy of the config")
    a = ap.parse_args()
    check_page_constants()
    cfg = json.load(open(a.config, encoding="utf-8"))
    if a.color_by:
        cfg["page"]["colorBy"] = a.color_by
    tr = json.load(open(a.trace, encoding="utf-8"))
    tok = tokens()
    net = js_twin(os.path.join(SITE, "data", "legal_network.js"), "legal_network")
    F = {f: i for i, f in enumerate(net["fields"])}
    rows = net["nodes"]
    N = len(rows)
    pos = np.array([[r[F["x"]], r[F["z"]] * ZS, r[F["y"]]] for r in rows], float)
    rank = np.array([r[F["rank"]] for r in rows])
    deg = np.array([r[F["degree"]] or 0 for r in rows], float)
    val = [net["validity"][r[F["validity"]]] if r[F["validity"]] is not None else "unknown" for r in rows]
    idx = {str(r[F["id"]]): i for i, r in enumerate(rows)}
    size = BASE[rank] + 2.6 * np.log2(1 + deg)
    extent = max(abs(x) for x in net["layout"]["x_y_range"])
    E = extent * 1.06
    zr = {int(k): v for k, v in net["layout"]["z_by_rank"].items()}
    kinds = net.get("change_kinds", KINDS)
    pairs = {k: [] for k in KINDS + ["basis", "citation"]}
    for e in net["edges"]["change"]:
        pairs[kinds[e[2]]].append(e[:2])
    pairs["basis"] = [e[:2] for e in net["edges"]["basis"]]
    pairs["citation"] = [e[:2] for e in net["edges"]["citation"]] if cfg["page"]["citation"] else []
    pairs = {k: np.array(v, int).reshape(-1, 2) for k, v in pairs.items()}
    full = N > 20000
    sel = idx[cfg["selection"]["doc"]]
    chain = [idx[c] for c in cfg["selection"]["chain"]]
    # the selection's neighbourhood (1 hop over the enabled kinds), as computeEgo
    ego = np.zeros(N, bool); ego[sel] = True
    for k, p in pairs.items():
        if len(p):
            m = (p[:, 0] == sel) | (p[:, 1] == sel)
            ego[p[m].ravel()] = True
    cam = Camera(cfg)
    S = cam.screen(pos)
    R = extent * 1.1

    def fog(depth):
        return np.clip((depth + 0.4 * R) / (2.3 * R), 0, 1) * 0.6

    W, H = cam.W, cam.H
    fig = plt.figure(figsize=(W / 72, H / 72), dpi=a.dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    css_pt = W / cfg["viewport"]["width"]                           # figure points per CSS px
    pr = cfg["captures"][0]["pixelRatio"]
    dev_pt = css_pt / pr                                            # figure points per device px of the capture
    fadeP, fadeE = cfg["fade"]["points"], cfg["fade"]["edges"]
    # layer planes (renderOrder 0) and their outlines
    planes = []
    for r_ in range(6):
        y = zr[r_] * ZS - 2
        planes.append(cam.screen(np.array([(-E, y, -E), (E, y, -E), (E, y, E), (-E, y, E)]))[:, :2])
    ax.add_collection(PolyCollection(planes, facecolors=[(*to_rgb(tok["--net-plane"]), float(tok["--net-plane-opacity"]))] * 6,
                                     edgecolors=[to_rgb(tok["--net-plane-line"])] * 6, linewidths=0.35, zorder=0))

    def links(k, z, segs):
        p = pairs[k]
        if not len(p):
            return
        col = tok["--edge-basis"] if k == "basis" else tok["--edge-citation"] if k == "citation" else tok["--chg-" + k]
        c0 = np.array(to_rgb(col)); c2 = 1 - (1 - c0) * 0.8
        pts = curve(pos[p[:, 0]], pos[p[:, 1]], segs)
        sp = cam.screen(pts.reshape(-1, 3)).reshape(len(p), segs + 1, 3)
        segs_xy = np.stack([sp[:, :-1, :2], sp[:, 1:, :2]], 2).reshape(-1, 2, 2)
        tmid = (np.arange(segs) + 0.5) / segs
        cols = c0[None, :] * (1 - tmid[:, None]) + c2[None, :] * tmid[:, None]
        cols = np.tile(cols, (len(p), 1))
        op = EDGE_OPACITY[k] * (0.55 if (k in ("basis", "citation") and full) else 1)
        egoE = np.repeat(((p[:, 0] == sel) | (p[:, 1] == sel)), segs)
        f = fog((sp[:, :-1, 2] + sp[:, 1:, 2]).reshape(-1) / 2)
        al = op * (1 - f) * np.where(egoE, 1.0, fadeE)
        ax.add_collection(LineCollection(segs_xy, colors=np.c_[cols, np.clip(al, 0, 1)], linewidths=dev_pt * 1.0, zorder=z))
    full_segs = lambda k: (8 if full else 10) if k in KINDS else (4 if full else 6)
    links("basis", 1, full_segs("basis"))
    if len(pairs["citation"]):
        links("citation", 1, full_segs("citation"))
    # points (renderOrder 2): far first; colour by validity; faded outside the neighbourhood; depth fade
    vc = np.array([to_rgb(tok["--cls-work"] if cfg["page"]["colorBy"] == "class" else tok["--val-" + v]) for v in val])
    f = fog(S[:, 2])
    alpha = np.where(ego, 1.0, fadeP)
    col = vc * 0.93
    col = 1 + (col - 1) * (1 - f[:, None])
    col = 1 + (col - 1) * alpha[:, None]
    uscale_pt = H / (2 * cam.hh)                                    # figure points per world unit
    d_pt = np.clip(size * uscale_pt, 2 * dev_pt, 56 * dev_pt)
    o = np.argsort(-S[:, 2])
    ax.scatter(S[o, 0], S[o, 1], s=d_pt[o] ** 2, c=col[o], edgecolors=np.clip(col[o] * 0.86, 0, 1), linewidths=0.12, zorder=2)
    for k in KINDS:
        links(k, 4, full_segs(k))
    # the selection's own links (egoLines: thin, link-type colour shaded 0.9, curved)
    n_ego = sum(int(((p[:, 0] == sel) | (p[:, 1] == sel)).sum()) for p in pairs.values() if len(p))
    w_ego = (1.1 if n_ego > 400 else 1.3 if n_ego > 120 else 1.6) * css_pt
    for k, p in pairs.items():
        if not len(p):
            continue
        m = (p[:, 0] == sel) | (p[:, 1] == sel)
        if not m.any():
            continue
        colk = tok["--edge-basis"] if k == "basis" else tok["--edge-citation"] if k == "citation" else tok["--chg-" + k]
        pts = curve(pos[p[m, 0]], pos[p[m, 1]], 12)
        sp = cam.screen(pts.reshape(-1, 3)).reshape(-1, 13, 3)[:, :, :2]
        ax.add_collection(LineCollection(sp, colors=[(*shade(colk, 0.9), 0.95)], linewidths=w_ego, zorder=5))
    tw = {k: v for k, v in cfg["trace_pt"].items()}
    core, halo, halo2 = tok.get("--paper-trace-core", "#2c3a47"), tok["--paper-trace-halo"], tok["--paper-trace-halo-2"]

    def trace(paths, z):
        for pl in paths:
            xy = cam.screen(pl)[:, :2]
            for w, c, dz in ((tw["halo2"], halo2, 0), (tw["halo"], halo, 0.1), (tw["core"], core, 0.2)):
                ax.plot(xy[:, 0], xy[:, 1], color=c, lw=w, solid_capstyle="round", solid_joinstyle="round", zorder=z + dz)
    # the replacement chain (chainCurve(chainIdx, 24))
    ch = np.concatenate([curve(pos[[chain[i]]], pos[[chain[i + 1]]], 24)[0][(1 if i else 0):] for i in range(len(chain) - 1)])
    trace([ch], 10)
    # the subtree: positions from the Labor Code, traced hops and thin branches, beads on top
    nodes = {n["id"]: n for n in tr["nodes"]}
    P = subtree_positions(pos[sel], cfg["subtree"]["offsets"])
    P["doc:" + tr["law"]["doc"]] = pos[sel]
    P["doc:" + tr["replaced"]["doc"]] = pos[idx[tr["replaced"]["doc"]]]
    segs = cfg["subtree"]["segments"]
    tpaths, thin = [], []
    for l in tr["links"]:
        if l["rel"] == "replaced by":
            continue
        c = curve(P[l["source"]][None, :], P[l["target"]][None, :], segs)[0]
        (tpaths if l["trace"] else thin).append((l, c))
    for l, c in thin:
        tgt = nodes.get(l["target"], {})
        hexc = tok["--cls-" + tgt.get("cls", "term")]
        xy = cam.screen(c)[:, :2]
        ax.plot(xy[:, 0], xy[:, 1], color=shade(hexc, 0.82), lw=1.3 * css_pt, zorder=6, solid_capstyle="round")
    trace([c for _, c in tpaths], 11)
    bead = cfg["subtree"]["bead_pt"]
    anchors = {}
    for nid, p in P.items():
        s = cam.screen(p[None, :])[0]
        if nid.startswith("doc:"):
            v = val[idx[nid[4:]]]
            fc = to_rgb(tok["--cls-work"] if cfg["page"]["colorBy"] == "class" else tok["--val-" + v])
            d = max(bead, float(size[idx[nid[4:]]] * uscale_pt))
        else:
            fc, d = to_rgb(tok["--cls-" + nodes[nid]["cls"]]), bead
        ax.scatter([s[0]], [s[1]], s=[d * d], c=[fc], edgecolors=[shade("#%02x%02x%02x" % tuple(int(x * 255) for x in fc), 0.8)],
                   linewidths=0.45, zorder=14)
        anchors[nid] = dict(x=round(float(s[0]), 2), y=round(float(s[1]), 2), r=round(d / 2, 2))
    # layer corners (for the layer names) and the stack's outline
    corners = {}
    for r_ in range(6):
        y = zr[r_] * ZS - 2
        c4 = cam.screen(np.array([(-E, y, -E), (E, y, -E), (E, y, E), (-E, y, E)]))
        corners[r_] = dict(left=c4[np.argmin(c4[:, 0]), :2].round(2).tolist(), right=c4[np.argmax(c4[:, 0]), :2].round(2).tolist())
    allxy = np.r_[np.concatenate(planes), S[:, :2]]
    stack = dict(x0=round(float(allxy[:, 0].min()), 2), x1=round(float(allxy[:, 0].max()), 2),
                 y0=round(float(allxy[:, 1].min()), 2), y1=round(float(allxy[:, 1].max()), 2))
    out = dict(figure=dict(width_pt=W, height_pt=H), camera=cfg["camera"], anchors=anchors, layer_corners=corners,
               stack_bbox=stack, ego_links=n_ego, ego_docs=int(ego.sum()) - 1)
    if not a.no_vector:
        out["callouts"] = draft_vector_layer(ax, fig, a, cfg, tr, tok, anchors, corners, net)
    fig.savefig(a.out, dpi=a.dpi, facecolor="white")
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(dict(stack_bbox=stack, ego_links=n_ego, ego_docs=out["ego_docs"], anchors=len(anchors)), ensure_ascii=False))


# ------------------------------------------------------------------ draft of the paper's vector layer (Phase C)
INK, INK2, BOX, LEAD = "#2b3036", "#666c73", "#d3d7dc", "#a2a8af"
FS, PAD, H1, H2, GAP = 8.5, 2.0, 13.87, 25.13, 4.6           # the published Fig. 1: 8.5 pt, 13.87 / 25.13 pt boxes
LEG_PITCH = 12.4
LEGEND_VALIDITY = {"in_force": ("Còn hiệu lực", "In force"), "in_force_amended": ("Còn hiệu lực, đã sửa đổi", "In force, amended"),
                   "presumed_in_force_amended": ("Có thể còn hiệu lực", "Presumed in force"),
                   "not_yet_effective": ("Chưa có hiệu lực", "Not yet in force"), "superseded": ("Đã bị thay thế", "Superseded"),
                   "expired": ("Hết hiệu lực", "No longer in force"), "not_applicable": ("Không còn phù hợp", "No longer applicable"),
                   "unknown": ("Chưa xác định", "Unknown")}


def pack(col, lo, hi):
    """1-D packing of boxes (want_y0, h) inside [lo, hi]: GAP apart, least movement"""
    ys = [max(lo, min(hi - h, y)) for y, h in col]
    for _ in range(50):
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + col[i - 1][1] + GAP)
        if ys and ys[-1] + col[-1][1] > hi:
            ys[-1] = hi - col[-1][1]
        for i in range(len(ys) - 2, -1, -1):
            ys[i] = min(ys[i], ys[i + 1] - col[i][1] - GAP)
        if ys and ys[0] < lo:
            ys[0] = lo
    return ys


def draft_vector_layer(ax, fig, a, cfg, tr, tok, anchors, corners, net):
    from matplotlib.textpath import TextToPath
    fp = None
    if a.fonts:
        f = os.path.join(a.fonts, "LibertinusSans-Regular.otf")
        if os.path.exists(f):
            fp = font_manager.FontProperties(fname=f, size=FS)
    fp = fp or font_manager.FontProperties(family="sans-serif", size=FS)
    t2p = TextToPath()
    tw = lambda s: t2p.get_text_width_height_descent(s, fp, ismath=False)[0] if s else 0.0
    W, H = cfg["figure"]["width_pt"], cfg["figure"]["height_pt"]
    law, old = tr["law"], tr["replaced"]
    placed = []

    def dims(vi, en, maxw):
        one = tw(vi + " · " + en) + 2 * PAD
        return (one, H1, True) if one <= maxw else (max(tw(vi), tw(en)) + 2 * PAD, H2, False)

    def draw_box(x0, y0, w, h, vi, en, single, anchor, attach, cid):
        ax.add_patch(plt.Rectangle((x0, y0), w, h, facecolor="white", edgecolor=BOX, linewidth=0.4, zorder=40))
        if single:
            ax.text(x0 + PAD, y0 + h / 2, vi + " · ", fontproperties=fp, color=INK, va="center", ha="left", zorder=41)
            ax.text(x0 + PAD + tw(vi + " · "), y0 + h / 2, en, fontproperties=fp, color=INK2, va="center", ha="left", zorder=41)
        else:
            ax.text(x0 + PAD, y0 + 6.6, vi, fontproperties=fp, color=INK, va="center", ha="left", zorder=41)
            ax.text(x0 + PAD, y0 + 18.4, en, fontproperties=fp, color=INK2, va="center", ha="left", zorder=41)
        if anchor is not None:
            ax.plot([attach[0], anchor[0]], [attach[1], anchor[1]], color=LEAD, lw=0.55, zorder=39)
        placed.append(dict(id=cid, box=[round(x0, 2), round(y0, 2), round(x0 + w, 2), round(y0 + h, 2)]))

    # the flat legend first (its rows fix the bottom of the call-out columns)
    entries = []
    if cfg["page"]["colorBy"] == "class":
        entries.append(("disc", tok["--cls-work"], "Văn bản", "Work"))
    else:
        for v in ["in_force", "in_force_amended", "presumed_in_force_amended", "not_yet_effective", "superseded", "expired",
                  "not_applicable", "unknown"]:
            entries.append(("disc", tok["--val-" + v]) + LEGEND_VALIDITY[v])
    entries += [("curve", tok["--edge-basis"], "Căn cứ pháp lý", "Legal basis"),
                ("changes", [tok["--chg-" + k] for k in KINDS], "Thay đổi", "Legal changes"),
                ("trace", None, "Đường truy vết", "Traced answer")]
    rows, x, row = [], 2.0, 0
    for e in entries:
        wl = 14 + tw(e[2] + " · " + e[3])
        if x + wl > W - 2:
            x, row = 2.0, row + 1
        rows.append((row, x) + e)
        x += wl + 10
    n_rows = row + 1
    for row, x, kind, colr, vi, en in rows:
        yc = H - (n_rows - row) * LEG_PITCH + LEG_PITCH / 2 - 1.5
        if kind == "disc":
            ax.add_patch(plt.Circle((x + 5, yc), 3.6, facecolor=colr, edgecolor=shade(colr, 0.8), linewidth=0.4, zorder=40))
        elif kind == "curve":
            tt = np.linspace(0, 1, 20)
            ax.plot(x + 10 * tt, yc + 3.0 - 6.0 * (3 * tt ** 2 - 2 * tt ** 3), color=colr, lw=1.2, solid_capstyle="round", zorder=40)
        elif kind == "changes":                                   # the five change kinds: five short S-curves side by side
            tt = np.linspace(0, 1, 12)
            for j, cj in enumerate(colr):
                ax.plot(x + 1.6 * j + 3.6 * tt, yc + 3.0 - 6.0 * (3 * tt ** 2 - 2 * tt ** 3), color=cj, lw=1.0, solid_capstyle="round", zorder=40)
        else:
            for w_, c_ in ((4.6, tok["--paper-trace-halo-2"]), (3.2, tok["--paper-trace-halo"]), (1.4, tok.get("--paper-trace-core", "#2c3a47"))):
                ax.plot([x, x + 10], [yc, yc], color=c_, lw=w_, solid_capstyle="round", zorder=40)
        ax.text(x + 14, yc, vi + " · ", fontproperties=fp, color=INK, va="center", ha="left", zorder=41)
        ax.text(x + 14 + tw(vi + " · "), yc, en, fontproperties=fp, color=INK2, va="center", ha="left", zorder=41)
    bottom = H - n_rows * LEG_PITCH - 3.0
    # left column: the law and the traced hops, in the order of their anchors' height
    items = [("doc:" + law["doc"], law["vi"], law["en"])] + [(n["id"], n["vi"], n["en"]) for n in tr["nodes"] if n["trace"]]
    items = [it for it in items if it[0] in anchors]
    items.sort(key=lambda it: anchors[it[0]]["y"])
    col = []
    for aid, vi, en in items:
        w, h, single = dims(vi, en, 150)
        col.append(dict(aid=aid, vi=vi, en=en, w=w, h=h, single=single, want=anchors[aid]["y"] - h / 2))
    ys = pack([(c["want"], c["h"]) for c in col], 1.5, bottom)
    for c, y0 in zip(col, ys):
        an = anchors[c["aid"]]
        draw_box(0.2, y0, c["w"], c["h"], c["vi"], c["en"], c["single"], (an["x"] - an["r"], an["y"]), (0.2 + c["w"], y0 + c["h"] / 2), c["aid"])
    # bottom row above the legend: the defining clause and the two terms, left to right, leaders up to their beads
    row_items = [(n["id"], n["vi"], n["en"]) for n in tr["nodes"] if not n["trace"] and n["cls"] in ("clause", "term")]
    row_items = sorted([it for it in row_items if it[0] in anchors], key=lambda it: anchors[it[0]]["x"])
    widths = [dims(vi, en, 400)[0] for _, vi, en in row_items]
    x0 = max(col[-1]["w"] + 0.2 + 2 * GAP, W - 0.2 - sum(widths) - GAP * (len(widths) - 1)) if row_items else 0
    x0 = min(x0, min(anchors[it[0]]["x"] for it in row_items) - widths[0] / 2) if row_items else 0
    x0 = max(x0, col[-1]["w"] + 0.2 + 2 * GAP)
    y0 = bottom - H1
    for (aid, vi, en), w in zip(row_items, widths):
        an = anchors[aid]
        draw_box(x0, y0, w, H1, vi, en, True, (an["x"], an["y"] + an["r"]), (min(max(an["x"], x0 + 6), x0 + w - 6), y0), aid)
        x0 += w + GAP
    # right column: the replaced code and three layer names at the planes' right corners
    right = [("doc:" + old["doc"], old["vi"], old["en"], (anchors["doc:" + old["doc"]]["x"], anchors["doc:" + old["doc"]]["y"]))]
    for r_, (vi, en) in {0: ("Hiến pháp", "Constitution"), 1: ("Bộ luật, luật", "Codes, laws"), 5: ("Thông tư", "Circulars")}.items():
        right.append(("rank-%d" % r_, vi, en, tuple(corners[r_]["right"])))
    rc = []
    for cid, vi, en, an in right:
        w, h, single = dims(vi, en, 112)                         # narrow: the boxes stay right of the planes' corners
        rc.append(dict(cid=cid, vi=vi, en=en, w=w, h=h, single=single, an=an, want=an[1] - h / 2))
    rc.sort(key=lambda c: c["want"])
    ys = pack([(c["want"], c["h"]) for c in rc], 1.5, bottom - H1 - GAP)
    for c, y0 in zip(rc, ys):
        x0 = W - 0.2 - c["w"]
        draw_box(x0, y0, c["w"], c["h"], c["vi"], c["en"], c["single"], c["an"], (x0, y0 + c["h"] / 2), c["cid"])
    return dict(boxes=placed, legend_rows=n_rows, legend_entries=len(entries), column_bottom=round(bottom, 2))


if __name__ == "__main__":
    main()

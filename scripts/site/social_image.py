#!/usr/bin/env python3
"""social_image.py - the link-preview image of the site (Open Graph / Twitter card, build_site.SOCIAL_IMAGE).

Crops a capture of the 3D legal network to the 1200 x 630 frame Facebook, LinkedIn and X show, centred on the drawing
with a margin above and below, and downsamples it (Lanczos) for crisp lines. The capture used for v1.1 is
teaser_class_pr3.png (4800 x 2148, light theme, colour by class, Labour Code 45/2019/QH14 selected) from the teaser
CI run 43336356396 (scripts/site/teaser), the same render as the paper's Fig. 1.

usage: python scripts/site/social_image.py <capture.png> site/img/vlonto-network-3d-social.png
needs: Pillow, numpy
"""
import sys

import numpy as np
from PIL import Image

W, H, PAD = 1200, 630, 60          # output size; margin (capture pixels) above and below the drawing


def main(src: str, out: str) -> int:
    im = Image.open(src)
    a = np.asarray(im.convert("RGBA"))
    ink = (a[..., 3] > 8) & (a[..., :3].min(axis=2) < 246)          # anything that is not the white page
    ys, xs = np.where(ink)
    y0, y1 = ys.min() - PAD, ys.max() + PAD
    h = y1 - y0
    w = round(h * W / H)
    x0 = (xs.min() + xs.max()) // 2 - w // 2
    if x0 < 0 or y0 < 0 or x0 + w > im.width or y1 > im.height:
        raise SystemExit(f"the {W}:{H} frame around the drawing does not fit in the capture ({im.width} x {im.height})")
    im.convert("RGB").crop((x0, y0, x0 + w, y1)).resize((W, H), Image.LANCZOS).save(out, optimize=True)
    print(f"{out}: {W} x {H} from the crop ({x0}, {y0}, {x0 + w}, {y1}) of {src}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))

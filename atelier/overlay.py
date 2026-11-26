"""Survey walls in red over the source plan image: the surveyor's alignment check.

    python -m atelier.overlay projects/sample        ->  projects/sample/out/overlay.png

Uses survey.json "calibration": two image points (a_px, b_px) and the same
points in plan mm (a_mm, b_mm). Image y runs down, plan y runs up; the mapping
is a similarity (scale + rotation + shift) solved from the two pairs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from PIL import Image  # noqa: E402

from atelier import geom  # noqa: E402
from atelier import theme as T  # noqa: E402
from atelier.draw import sans  # noqa: E402
from atelier.model import load  # noqa: E402


def mm_to_px_fn(cal):
    """Return f(x_mm, y_mm) -> (x_px, y_px) from the two calibration pairs."""
    pa, pb = complex(*cal["a_px"]), complex(*cal["b_px"])
    ma = complex(cal["a_mm"][0], -cal["a_mm"][1])     # flip y: plan up -> image down
    mb = complex(cal["b_mm"][0], -cal["b_mm"][1])
    k = (pb - pa) / (mb - ma)
    c = pa - k * ma

    def f(x, y):
        z = k * complex(x, -y) + c
        return z.real, z.imag
    return f


def overlay(root: Path, out: Path | None = None) -> Path | None:
    m = load(root, design=False)
    cal = m.calibration or {}
    img = cal.get("image")
    if not img or not cal.get("a_px") or not cal.get("b_px"):
        print(f"overlay skipped: {root}/survey.json has no calibration image "
              f"(calibration.image = {img!r}); nothing to check against")
        return None
    src = (root / img) if not Path(img).is_absolute() else Path(img)
    if not src.exists():
        print(f"overlay skipped: plan image not found: {src}")
        return None
    im = Image.open(src).convert("RGB")
    W, H = im.size
    f = mm_to_px_fn(cal)
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(im, extent=(0, W, H, 0), interpolation="nearest")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    lw = max(0.6, W / 3000)
    for w in m.walls:
        poly = geom.wall_polygon(w)
        for j in geom.wall_joints(m.walls):                   # centre-line corners, as the plans draw them
            if j.intersects(poly):
                poly = poly.union(j)
        if poly.geom_type != "Polygon":
            poly = poly.convex_hull
        pts = [f(*c) for c in poly.exterior.coords]
        path = MplPath(pts, [MplPath.MOVETO] + [MplPath.LINETO] * (len(pts) - 2) + [MplPath.CLOSEPOLY])
        ax.add_patch(PathPatch(path, facecolor=T.RED, edgecolor=T.RED, alpha=0.28, lw=0))
        ax.add_patch(PathPatch(path, facecolor="none", edgecolor=T.RED, lw=lw))
        cx, cy = f(*poly.centroid.coords[0])
        ax.text(cx, cy, w["id"], fontproperties=sans("legend", 600), color=T.RED, ha="center", va="center",
                fontsize=max(6, W / 400))
    ax.text(W * 0.01, H * 0.985, f"Survey walls (red) over {src.name} · calibration {str(cal['px_per_mm']) + ' px/mm · ' if cal.get('px_per_mm') else ''}{cal['a_mm']}→{cal['b_mm']} mm",
            fontproperties=sans("legend", 600), color=T.RED, fontsize=max(7, W / 330), va="bottom")
    out = out or (root / "out" / "overlay.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    print(f"overlay ✓ {out}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.overlay")
    ap.add_argument("project", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    a = ap.parse_args(argv)
    overlay(a.project, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

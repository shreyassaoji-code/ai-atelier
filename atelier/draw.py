"""Drawing primitives for A3 sheets.

Every colour, font, text size and page dimension comes from atelier.theme.
This module holds no colour values and no font names: fonts are found by
reading the family name inside each file in fonts/ and matching it against
the theme's FONT_SERIF / FONT_SANS tokens.

Page coordinates are millimetres, origin top-left, y pointing down.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import PathPatch, Polygon as MplPolygon, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from atelier import theme as T  # noqa: E402

MM = 1 / 25.4  # inches per mm
PT_PER_MM = 72 / 25.4

# Line weights in points (geometry, not branding).
LW_CUT = 0.6
LW_LINE = 0.35
LW_THIN = 0.25
LW_HAIR = 0.18

TRACK = " "  # hair space between letters of tracked caps

# --------------------------------------------------------------------------- fonts
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
_FONT_INDEX: dict[str, dict[int, Path]] = {}


def _index_fonts() -> None:
    for f in sorted(FONT_DIR.glob("*.[ot]tf")):
        tt = TTFont(f, lazy=True)
        name = tt["name"]
        fam = name.getDebugName(16) or name.getDebugName(1)
        _FONT_INDEX.setdefault(fam, {})[tt["OS/2"].usWeightClass] = f


def font(family: str, size: float, weight: int = 400) -> FontProperties:
    """FontProperties for a theme family token at a SIZES value, nearest weight."""
    if not _FONT_INDEX:
        _index_fonts()
    weights = _FONT_INDEX.get(family)
    if not weights:
        raise FileNotFoundError(
            f"No file in {FONT_DIR} declares the family named by the theme token; "
            "add the font files to fonts/."
        )
    w = min(weights, key=lambda k: abs(k - weight))
    fp = FontProperties(fname=str(weights[w]))
    fp.set_size(size)
    return fp


def serif(role: str, weight: int = 400) -> FontProperties:
    return font(T.FONT_SERIF, T.SIZES[role], weight)


def sans(role: str, weight: int = 400) -> FontProperties:
    return font(T.FONT_SANS, T.SIZES[role], weight)


def tracked(s: str) -> str:
    """Upper-case with letter-spacing (tracked caps)."""
    return TRACK.join(s.upper())


# --------------------------------------------------------------------------- sheet
class Sheet:
    """One A3 page, in mm, using theme page geometry."""

    def __init__(self) -> None:
        self.fig = plt.figure(figsize=(T.PAGE_W * MM, T.PAGE_H * MM), facecolor=T.PAPER)
        ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, T.PAGE_W)
        ax.set_ylim(T.PAGE_H, 0)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_facecolor(T.PAPER)
        self.ax = ax

    # -- text --------------------------------------------------------------
    def text(self, x, y, s, fp, color=None, ha="left", va="baseline", **kw):
        t = self.ax.text(x, y, s, fontproperties=fp, color=color or T.INK,
                         ha=ha, va=va, **kw)
        t.set_fontfeatures(["lnum"])  # lining figures: "01", not old-style "oI"
        return t

    def caps(self, x, y, s, color=None, role="caps_label", weight=500, **kw):
        """Tracked-caps label in the sans face."""
        return self.text(x, y, tracked(s), sans(role, weight), color or T.INK, **kw)

    def value(self, x, y, v, flagged=False, role="dim", **kw):
        """A measured value; flagged values are FLAG-coloured with a trailing *."""
        s = f"{v}*" if flagged else f"{v}"
        return self.text(x, y, s, sans(role, 500 if flagged else 400),
                         T.FLAG if flagged else T.INK, **kw)

    # -- lines and fills ---------------------------------------------------
    def line(self, pts, color=None, lw=LW_LINE, **kw):
        xs, ys = zip(*pts)
        self.ax.plot(xs, ys, color=color or T.INK, lw=lw, solid_capstyle="butt", **kw)

    def rule(self, x0, x1, y, color=None, lw=LW_HAIR):
        self.line([(x0, y), (x1, y)], color or T.HAIR, lw)

    def poly(self, pts, fill=None, edge=None, lw=LW_CUT, **kw):
        self.ax.add_patch(MplPolygon(pts, closed=True, facecolor=fill or "none",
                                     edgecolor=edge or "none", lw=lw, joinstyle="miter", **kw))

    def region(self, rings, fill=None):
        """Fill a polygon-with-holes as one compound path (no seams between parts).
        rings: list of (exterior_pts, [hole_pts, ...]) in page mm."""
        verts, codes = [], []
        for ext, holes in rings:
            for ring in [ext, *holes]:
                verts += list(ring) + [ring[0]]
                codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(ring) - 1) + [MplPath.CLOSEPOLY]
        col = fill or T.POCHE
        self.ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=col, edgecolor=col,
                                    lw=LW_HAIR, joinstyle="miter"))

    def swatch(self, x, y, w, h, fill=None, edge=None, lw=LW_THIN):
        self.ax.add_patch(Rectangle((x, y), w, h, facecolor=fill or "none",
                                    edgecolor=edge or "none", lw=lw))

    def dim(self, p1, p2, offset, v, flagged=False, ext_gap=1.2):
        """Linear dimension between page points p1, p2, offset (mm) to the left
        of the direction p1->p2 (negative offset = right). Text sits outside."""
        (x1, y1), (x2, y2) = p1, p2
        L = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        nx, ny = uy, -ux  # left normal in a y-down page
        a = (x1 + nx * offset, y1 + ny * offset)
        b = (x2 + nx * offset, y2 + ny * offset)
        sgn = 1 if offset >= 0 else -1
        for p, q in ((p1, a), (p2, b)):  # extension lines
            s = (p[0] + nx * ext_gap * sgn, p[1] + ny * ext_gap * sgn)
            e = (q[0] + nx * 1.2 * sgn, q[1] + ny * 1.2 * sgn)
            self.line([s, e], T.GREY, LW_HAIR)
        self.line([(a[0] - ux * 1.2, a[1] - uy * 1.2), (b[0] + ux * 1.2, b[1] + uy * 1.2)],
                  T.INK, LW_THIN)
        t = 0.9  # 45-degree architectural ticks
        for q in (a, b):
            dx, dy = (ux + nx) * t, (uy + ny) * t
            self.line([(q[0] - dx, q[1] - dy), (q[0] + dx, q[1] + dy)], T.INK, LW_LINE)
        mx, my = (a[0] + b[0]) / 2 + nx * 0.9 * sgn, (a[1] + b[1]) / 2 + ny * 0.9 * sgn
        ang = -math.degrees(math.atan2(uy, ux))
        if ang <= -90 or ang > 90:
            ang += 180
        self.value(mx, my, v, flagged, ha="center",
                   va="bottom" if sgn > 0 else "top", rotation=ang, rotation_mode="anchor")

    # -- sheet furniture ---------------------------------------------------
    def frame(self, title, project, sheet_no, sheet_total, subtitle=""):
        """Title band, legend-strip header and separators."""
        x0, y0, x1, y1 = T.DRAW
        self.text(x0, y0 - 12, title, serif("title", 500), T.ACCENT)
        if subtitle:
            self.caps(x0, y0 - 5, subtitle, T.GREY)
        self.rule(x0, T.RIGHT, y0 - 2)
        sep = (x1 + T.STRIP_X) / 2
        self.line([(sep, y0), (sep, y1)], T.HAIR, LW_HAIR)
        # sheet number block
        no = self.text(T.STRIP_X, y0 - 5, f"{sheet_no:02d}", serif("sheet_no", 500), T.ACCENT)
        self.fig.canvas.draw()
        bb = no.get_window_extent().transformed(self.ax.transData.inverted())
        self.text(bb.x1 + 1.5, y0 - 5, f"/ {sheet_total:02d}", sans("sheet_total"), T.GREY)
        self.text(T.STRIP_X, y0 + 7, project, serif("project", 500), T.INK)

    def legend(self, y, items):
        """items: (kind, label, style) drawn in the strip from y downwards."""
        self.caps(T.STRIP_X, y, "Legend", T.INK, role="legend_head", weight=600)
        y += 6
        sw = 7
        for kind, label, style in items:
            cx = T.STRIP_X
            if kind == "fill":
                self.swatch(cx, y - 2.2, sw, 2.6, fill=style)
            elif kind == "line":
                self.line([(cx, y - 0.9), (cx + sw, y - 0.9)], style, LW_LINE)
            elif kind == "text":
                txt, fp, col = style
                self.text(cx, y, txt, fp, col)
            self.text(cx + sw + 3, y, label, sans("legend"), T.INK)
            y += 5
        return y

    def save(self, pdf: Path | None = None, png: Path | None = None, dpi: int = 200):
        for p in (pdf, png):
            if p:
                p.parent.mkdir(parents=True, exist_ok=True)
                self.fig.savefig(p, dpi=dpi, facecolor=T.PAPER)
        plt.close(self.fig)

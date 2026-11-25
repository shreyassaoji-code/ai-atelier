"""Sheet symbols: north arrow, scale bar, numbered tags, level marker.

All sizes are page mm; colours and type from atelier.theme via draw helpers.
"""
from __future__ import annotations

import math

from atelier import theme as T
from atelier.draw import LW_HAIR, LW_THIN, Sheet, sans, serif


def north_arrow(sh: Sheet, x, y, r=5.0, angle_deg=0.0):
    """Circle with a half-filled needle; angle 0 = plan north is page up."""
    sh.circle(x, y, r, edge=T.INK, lw=LW_THIN)
    a = math.radians(angle_deg)
    ux, uy = math.sin(a), -math.cos(a)          # page: up is -y
    px, py = -uy, ux
    tip = (x + ux * r * 0.85, y + uy * r * 0.85)
    tail = (x - ux * r * 0.85, y - uy * r * 0.85)
    w = r * 0.32
    left = (x + px * w, y + py * w)
    right = (x - px * w, y - py * w)
    sh.region([([tip, left, tail], [])], fill=T.INK, edge=T.INK, lw=LW_HAIR, z=4)
    sh.region([([tip, right, tail], [])], fill=T.PAPER, edge=T.INK, lw=LW_HAIR, z=4)
    sh.text(x + ux * (r + 2.2), y + uy * (r + 2.2), "N", serif("legend_head", 600), T.INK,
            ha="center", va="center")


def scale_bar(sh: Sheet, x, y, scale: int, metres: int = 5, h=1.1):
    """Alternating blocks of 1 m at 1:scale, labelled 0 … metres m."""
    step = 1000 / scale
    for i in range(metres):
        sh.swatch(x + i * step, y, step, h, fill=T.INK if i % 2 == 0 else T.PAPER, edge=T.INK, lw=LW_HAIR)
    for i in (0, 1, metres):
        sh.text(x + i * step, y + h + 2.4, f"{i}" + (" m" if i == metres else ""), sans("dim"), T.GREY,
                ha="center")
    sh.text(x, y - 1.6, f"1:{scale}", sans("legend", 600), T.INK)


def number_tag(sh: Sheet, x, y, n, color=None, r=1.9):
    """Circled reference number (e.g. demolition item)."""
    c = color or T.FLAG
    sh.circle(x, y, r, edge=c, fill=T.PAPER, lw=LW_THIN)
    sh.text(x, y + 0.05, str(n), sans("dim", 600), c, ha="center", va="center")


def level_marker(sh: Sheet, x, y, label, flagged=False):
    """Plan level marker: small open triangle + level text, e.g. FFL -20."""
    s = 1.2
    sh.region([([(x - s, y - s), (x + s, y - s), (x, y)], [])], fill=T.PAPER, edge=T.INK, lw=LW_HAIR, z=4)
    sh.text(x + s + 0.8, y - 0.3, label + ("*" if flagged else ""), sans("dim", 500 if flagged else 400),
            T.FLAG if flagged else T.INK, va="center")

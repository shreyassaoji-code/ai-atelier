"""Drawing primitives (page) and the plan renderer (model -> page).

Colours, fonts, sizes and page geometry come only from atelier.theme. Fonts are
found by the family name stored inside each file in fonts/, matched against the
theme tokens, so this file holds no colour values and no font names.

Page coordinates: mm, origin top-left, y down.  Plan coordinates: mm, origin
bottom-left, y up (agents/SCHEMA.md). PlanView.P() converts plan -> page.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import Circle, PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402

from atelier import geom  # noqa: E402
from atelier import theme as T  # noqa: E402

MM = 1 / 25.4
PT = 72 / 25.4                 # points per mm

# Line weights (pt). Geometry, not brand.
LW_CUT = 0.5
LW_LINE = 0.35
LW_THIN = 0.22
LW_HAIR = 0.15
DASH = (0, (3.0, 1.6))
DOT = (0, (0.6, 1.2))
matplotlib.rcParams["hatch.linewidth"] = LW_HAIR
matplotlib.rcParams["pdf.fonttype"] = 42

TRACK = " "

# ------------------------------------------------------------------- fonts
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
_FONT_INDEX: dict[str, dict[int, Path]] = {}


def _index_fonts() -> None:
    for f in sorted(FONT_DIR.glob("*.[ot]tf")):
        tt = TTFont(f, lazy=True)
        name = tt["name"]
        fam = name.getDebugName(16) or name.getDebugName(1)
        _FONT_INDEX.setdefault(fam, {})[tt["OS/2"].usWeightClass] = f


def font(family: str, size: float, weight: int = 400) -> FontProperties:
    if not _FONT_INDEX:
        _index_fonts()
    weights = _FONT_INDEX.get(family)
    if not weights:
        raise FileNotFoundError(f"no file in {FONT_DIR} declares the theme's font family")
    w = min(weights, key=lambda k: abs(k - weight))
    fp = FontProperties(fname=str(weights[w]))
    fp.set_size(size)
    return fp


def serif(role: str, weight: int = 400) -> FontProperties:
    return font(T.FONT_SERIF, T.SIZES[role], weight)


def sans(role: str, weight: int = 400) -> FontProperties:
    return font(T.FONT_SANS, T.SIZES[role], weight)


def tracked(s: str) -> str:
    return TRACK.join(s.upper())


def text_width_mm(s: str, size_pt: float, k: float = 0.56) -> float:
    """Estimated advance width (mm), for layout decisions."""
    return len(s) * size_pt * k / PT


# ------------------------------------------------------------------- page canvas
class Sheet:
    """One A3 page in mm (theme page geometry)."""

    def __init__(self) -> None:
        self.fig = plt.figure(figsize=(T.PAGE_W * MM, T.PAGE_H * MM), facecolor=T.PAPER)
        ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, T.PAGE_W)
        ax.set_ylim(T.PAGE_H, 0)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_facecolor(T.PAPER)
        self.ax = ax

    def text(self, x, y, s, fp, color=None, ha="left", va="baseline", features=("lnum",), **kw):
        t = self.ax.text(x, y, s, fontproperties=fp, color=color or T.INK, ha=ha, va=va, **kw)
        t.set_fontfeatures(list(features))
        return t

    def caps(self, x, y, s, color=None, role="caps_label", weight=500, **kw):
        return self.text(x, y, tracked(s), sans(role, weight), color or T.INK, **kw)

    def smallcaps(self, x, y, s, role="project", color=None, weight=500, **kw):
        """Serif small caps (true smcp glyphs, not scaled capitals)."""
        return self.text(x, y, s, serif(role, weight), color or T.INK, features=("smcp", "lnum"), **kw)

    def value(self, x, y, v, flagged=False, role="dim", **kw):
        s = f"{v}*" if flagged else f"{v}"
        return self.text(x, y, s, sans(role, 500 if flagged else 400), T.FLAG if flagged else T.INK, **kw)

    def line(self, pts, color=None, lw=LW_LINE, dash=None, z=3, **kw):
        xs, ys = zip(*pts)
        self.ax.plot(xs, ys, color=color or T.INK, lw=lw, solid_capstyle="butt",
                     dash_capstyle="butt", linestyle=dash or "-", zorder=z, **kw)

    def rule(self, x0, x1, y, color=None, lw=LW_HAIR):
        self.line([(x0, y), (x1, y)], color or T.HAIR, lw)

    def region(self, rings, fill=None, edge=None, lw=LW_HAIR, hatch=None, dash=None, z=1):
        """Fill polygon(s)-with-holes as ONE compound path (no seams).
        rings: [(exterior_pts, [hole_pts, ...]), ...] in page mm."""
        verts, codes = [], []
        for ext, holes in rings:
            for ring in [ext, *holes]:
                ring = list(ring)
                if len(ring) < 3:
                    continue
                verts += ring + [ring[0]]
                codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(ring) - 1) + [MplPath.CLOSEPOLY]
        if not verts:
            return
        self.ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=fill or "none",
                                    edgecolor=edge or (fill or "none"), lw=lw, hatch=hatch,
                                    linestyle=dash or "-", joinstyle="miter", zorder=z))

    def swatch(self, x, y, w, h, fill=None, edge=None, lw=LW_THIN, hatch=None, dash=None):
        self.ax.add_patch(Rectangle((x, y), w, h, facecolor=fill or "none", edgecolor=edge or "none",
                                    lw=lw, hatch=hatch, linestyle=dash or "-"))

    def circle(self, x, y, r, edge=None, fill=None, lw=LW_THIN):
        self.ax.add_patch(Circle((x, y), r, facecolor=fill or "none", edgecolor=edge or T.INK, lw=lw))

    def save(self, pdf: Path | None = None, png: Path | None = None, dpi: int = 200):
        for p in (pdf, png):
            if p:
                p.parent.mkdir(parents=True, exist_ok=True)
                self.fig.savefig(p, dpi=dpi, facecolor=T.PAPER)
        plt.close(self.fig)


# ------------------------------------------------------------------- dimension chains
TICK = 0.8          # mm, half-length of the 45° tick
EXT_GAP = 1.6       # mm gap between the object and its extension line
EXT_OVER = 1.3      # mm extension line beyond the dimension line
TEXT_GAP = 0.7      # mm from dimension line to text


def dim_chain(sh: Sheet, a, u, n, coords, values, flags, ext_from=None):
    """Chained linear dimension on the page.

    a      page point of coordinate 0 on the dimension line
    u, n   page unit vectors: along the chain, and towards the text side
    coords page mm along u (sorted), one per dimension point
    values real mm per segment; flags per segment (flagged -> FLAG colour + *)
    ext_from  per point: page distance back along -n where the extension line starts
    """
    def at(c, off=0.0):
        return (a[0] + u[0] * c + n[0] * off, a[1] + u[1] * c + n[1] * off)

    sh.line([at(coords[0] - 1.4), at(coords[-1] + 1.4)], T.INK, LW_HAIR)
    d = ((u[0] + n[0]) * 0.7071, (u[1] + n[1]) * 0.7071)
    for i, c in enumerate(coords):
        if ext_from and ext_from[i] is not None:
            sh.line([at(c, -ext_from[i] + EXT_GAP), at(c, EXT_OVER)], T.GREY, LW_HAIR)
        p = at(c)
        sh.line([(p[0] - d[0] * TICK, p[1] - d[1] * TICK), (p[0] + d[0] * TICK, p[1] + d[1] * TICK)],
                T.INK, LW_LINE)
    ang = -math.degrees(math.atan2(u[1], u[0]))
    if ang <= -90 or ang > 90:
        ang += 180
    size = T.SIZES["dim"]
    row_h = size / PT + 0.5
    prev_end = {0: -1e9, 1: -1e9}
    for i in range(len(coords) - 1):
        c0, c1 = coords[i], coords[i + 1]
        s = f"{values[i]}{'*' if flags[i] else ''}"
        w = text_width_mm(s, size)
        mid = (c0 + c1) / 2
        level = 0
        if mid - w / 2 < prev_end[0] + 0.8 or (c1 - c0) < w + 0.6:
            level = 1 if mid - w / 2 >= prev_end[1] + 0.8 else 0
        prev_end[level] = mid + w / 2
        p = at(mid, TEXT_GAP + level * row_h)
        # anchor the text on the side nearest the dimension line
        toward_up = n[1] < 0 or (n[1] == 0 and n[0] < 0)
        sh.value(p[0], p[1], values[i], flags[i], ha="center",
                 va="bottom" if toward_up else "top", rotation=ang, rotation_mode="anchor")


# ------------------------------------------------------------------- plan renderer
class PlanView:
    """Maps plan mm into the sheet's drawing area at a fixed scale (1:scale)."""

    def __init__(self, sh: Sheet, bounds, scale: int, centre=None):
        self.sh, self.s, self.bounds = sh, scale, bounds
        x0, y0, x1, y1 = T.DRAW
        bx0, by0, bx1, by1 = bounds
        cx, cy = centre or ((x0 + x1) / 2, (y0 + y1) / 2)
        self.ox = cx - (bx0 + bx1) / 2 / scale
        self.oy = cy + (by0 + by1) / 2 / scale

    def P(self, x, y):
        return (self.ox + x / self.s, self.oy - y / self.s)

    def L(self, mm):
        return mm / self.s

    def rings(self, g):
        out = []
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.geom_type != "Polygon":
                continue
            out.append(([self.P(*c) for c in p.exterior.coords[:-1]],
                        [[self.P(*c) for c in i.coords[:-1]] for i in p.interiors]))
        return out

    def fill(self, g, fill=None, edge=None, lw=LW_HAIR, hatch=None, dash=None, z=2):
        if g is None or g.is_empty:
            return
        self.sh.region(self.rings(g), fill=fill, edge=edge, lw=lw, hatch=hatch, dash=dash, z=z)

    # ---- openings
    def opening(self, wall, op, color=None, dash=None, arc_color=None):
        k = op["kind"]
        c = color or T.INK
        lo, hi = geom.wall_offsets(wall)
        o0, o1 = op["offset"], op["offset"] + op["width"]

        def on(off, side):
            return self.P(*geom.point_on_wall(wall, off, side))

        if k in ("window", "ventilator"):           # triple line: two frame faces + glass
            mid = (lo + hi) / 2
            for side, lw in ((lo, LW_HAIR), (mid, LW_THIN), (hi, LW_HAIR)):
                self.sh.line([on(o0, side), on(o1, side)], c, lw, dash)
            for o in (o0, o1):
                self.sh.line([on(o, lo), on(o, hi)], c, LW_HAIR, dash)
        elif k == "opening":                          # head over: dotted on both faces
            for side in (lo, hi):
                self.sh.line([on(o0, side), on(o1, side)], arc_color or T.GREY, LW_HAIR, dash or DOT)
        elif k == "sliding_door":
            mid = (lo + hi) / 2
            q = (hi - lo) / 5
            L = op["width"]
            self.sh.line([on(o0, mid - q), on(o0 + L * 0.55, mid - q)], c, LW_CUT, dash)
            self.sh.line([on(o1 - L * 0.55, mid + q), on(o1, mid + q)], c, LW_CUT, dash)
            for o in (o0, o1):
                self.sh.line([on(o, lo), on(o, hi)], c, LW_HAIR, dash)
        else:                                         # hinged: leaf open at 90° + swing arc
            sp = geom.swing_polygon(wall, op)
            if sp is None:
                return
            f = geom.face_offset(wall, op["swing"])
            ux, uy, _ = geom.unit(wall["a"], wall["b"])
            nx, ny = geom.left_normal(ux, uy)
            sgn = 1 if op["swing"] == "left" else -1
            leaves = ([(o0, op["width"] / 2), (o1, op["width"] / 2)] if op["hinge"] == "both"
                      else [(o0 if op["hinge"] == "start" else o1, op["width"])])
            for hoff, r in leaves:
                hx, hy = geom.point_on_wall(wall, hoff, f)
                tip = (hx + nx * sgn * r, hy + ny * sgn * r)
                self.sh.line([self.P(hx, hy), self.P(*tip)], c, LW_CUT, dash)
            for g in getattr(sp, "geoms", [sp]):
                arc = [self.P(*p) for p in list(g.exterior.coords)[1:-1]]
                self.sh.line(arc, arc_color or (c if dash else T.GREY), LW_HAIR, dash)

    # ---- labels
    def label_box(self, room, cx, cy, extra=0):
        """Plan-mm box the label occupies when centred on (cx, cy)."""
        from shapely.geometry import box
        name = room.get("name", room["id"])
        hw = max(text_width_mm(name, T.SIZES["project"], 0.5), 16) / 2 * self.s
        top, bot = 4.8 * self.s, (4.2 + 3.0 * extra) * self.s
        return box(cx - hw, cy - bot, cx + hw, cy + top)

    def room_label(self, room, extra_lines=(), avoid=None):
        """Name (serif small caps); ID · area; extra (text, flagged) lines.
        `avoid` (plan geometry, e.g. door swings): the label shifts off it if it can."""
        poly = geom.room_polygon(room)
        p = geom.label_point(room)
        px, py = p.x, p.y
        if avoid is not None and not avoid.is_empty:
            inner = poly.buffer(-60)
            ok = lambda b: inner.contains(b) and not b.intersects(avoid)  # noqa: E731
            if not ok(self.label_box(room, px, py, len(extra_lines))):
                cands = sorted(((px + dx * k, py + dy * k) for k in range(1, 21)
                                for dx, dy in ((0, 100), (0, -100), (100, 0), (-100, 0),
                                               (71, 71), (-71, 71), (71, -71), (-71, -71))),
                               key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)
                for c in cands:
                    if ok(self.label_box(room, *c, len(extra_lines))):
                        px, py = c
                        break
        x, y = self.P(px, py)
        sh = self.sh
        sh.smallcaps(x, y - 1.0, room.get("name", room["id"]), ha="center")
        sh.text(x - 1.0, y + 3.0, room["id"], sans("dim", 600), T.ACCENT, ha="right")
        sh.text(x, y + 3.0, "·", sans("dim"), T.GREY, ha="center")
        sh.text(x + 1.0, y + 3.0, f"{poly.area / 1e6:.2f} m²", sans("dim"), T.GREY, ha="left")
        for i, (s, flagged) in enumerate(extra_lines):
            sh.text(x, y + 6.2 + i * 3.0, s + ("*" if flagged else ""), sans("dim", 500 if flagged else 400),
                    T.FLAG if flagged else T.GREY, ha="center")

    def tag(self, x_mm, y_mm, s, color=None, sub=None, sub_flag=False):
        x, y = self.P(x_mm, y_mm)
        self.sh.text(x, y, s, sans("dim", 600), color or T.GREY, ha="center", va="center")
        if sub:
            self.sh.text(x, y + 2.5, sub + ("*" if sub_flag else ""), sans("dim", 500 if sub_flag else 400),
                         T.FLAG if sub_flag else T.GREY, ha="center", va="center")

    # ---- dimensions
    def side_chains(self, side, tiers, offsets=(9.0, 16.0, 23.0)):
        """Chains outside one side ('S','N','W','E'). tiers: [[(coord_mm, flagged), ...], ...]
        nearest first; coord is the plan coordinate along that side."""
        bx0, by0, bx1, by1 = self.bounds
        k_used = 0
        for pts in tiers:
            pts = dedupe(pts)
            if len(pts) < 2:
                continue
            off = offsets[k_used]
            prev = offsets[k_used - 1] if k_used else 0
            k_used += 1
            if side == "S":
                a, u, n = (self.ox, self.P(0, by0)[1] + off), (1, 0), (0, 1)
            elif side == "N":
                a, u, n = (self.ox, self.P(0, by1)[1] - off), (1, 0), (0, -1)
            elif side == "W":
                a, u, n = (self.P(bx0, 0)[0] - off, self.oy), (0, -1), (-1, 0)
            else:
                a, u, n = (self.P(bx1, 0)[0] + off, self.oy), (0, -1), (1, 0)
            coords = [self.L(c) for c, _ in pts]
            vals = [int(round(pts[i + 1][0] - pts[i][0])) for i in range(len(pts) - 1)]
            fl = [pts[i][1] or pts[i + 1][1] for i in range(len(pts) - 1)]
            dim_chain(self.sh, a, u, n, coords, vals, fl, ext_from=[off - prev] * len(pts))

    def ray_chain(self, origin, direction, pts, normal=None):
        """Chain drawn along a plan ray (e.g. across a room). pts: [(t_mm, flagged)]."""
        pts = dedupe(pts)
        if len(pts) < 2:
            return
        ux, uy = direction
        nx, ny = normal or (-uy, ux)
        a = self.P(*origin)
        dim_chain(self.sh, a, (ux, -uy), (nx, -ny), [self.L(t) for t, _ in pts],
                  [int(round(pts[i + 1][0] - pts[i][0])) for i in range(len(pts) - 1)],
                  [pts[i][1] or pts[i + 1][1] for i in range(len(pts) - 1)])


def dedupe(pts, tol=1.0):
    out = []
    for c, f in sorted(pts):
        if out and abs(out[-1][0] - c) <= tol:
            out[-1] = (out[-1][0], out[-1][1] or f)
        else:
            out.append((c, f))
    return out


# ------------------------------------------------------------------- model queries
def envelope_bounds(walls):
    ext = [w for w in walls if w.get("kind") in ("external", "parapet")] or walls
    return geom.walls_union(ext).bounds


def side_points(m, walls, openings, rooms, side):
    """Dimension points for one side: [openings tier, rooms tier, overall tier]."""
    bx0, by0, bx1, by1 = envelope_bounds(walls)
    tmax = max((w["t"] for w in walls if w.get("kind") in ("external", "parapet")), default=230)
    axis = 0 if side in ("S", "N") else 1
    perp = 1 - axis
    lo, hi = (bx0, bx1) if axis == 0 else (by0, by1)
    edge_facing = {"S": "N", "N": "S", "W": "E", "E": "W"}[side]
    outer = {"S": by0, "N": by1, "W": bx0, "E": bx1}[side]

    def near(pt):
        return abs(pt[perp] - outer) <= tmax + 1

    ext_flag = any(m.is_flagged(w, "a") or m.is_flagged(w, "b") for w in walls
                   if w.get("kind") in ("external", "parapet"))
    overall = [(lo, ext_flag), (hi, ext_flag)]
    rooms_t = list(overall)
    for r in rooms:
        rf = m.is_flagged(r, "poly")
        for e in geom.room_edges(r, walls):
            if e.facing == edge_facing and near(e.a) and near(e.b):
                rooms_t += [(e.a[axis], rf), (e.b[axis], rf)]
    open_t = []
    by_id = {w["id"]: w for w in walls}
    for o in openings:
        w = by_id.get(o["wall"])
        if not w or w.get("kind") not in ("external", "parapet"):
            continue
        p0 = geom.point_on_wall(w, o["offset"])
        if not near(p0):
            continue
        p1 = geom.point_on_wall(w, o["offset"] + o["width"])
        of = m.is_flagged(o, "offset") or m.is_flagged(o, "width")
        open_t += [(p0[axis], of), (p1[axis], of)]
    if open_t:
        open_t += overall
    return [open_t, rooms_t, overall]


def ray_hit(origin, direction, obstacles, max_len=30000):
    """Distance along a plan ray to the first boundary of `obstacles`, or None."""
    ox, oy = origin
    dx, dy = direction
    ray = LineString([(ox, oy), (ox + dx * max_len, oy + dy * max_len)])
    hit = ray.intersection(obstacles)
    if hit.is_empty:
        return None
    pts = []
    for g in getattr(hit, "geoms", [hit]):
        pts += list(getattr(g, "coords", []))
    return min((Point(origin).distance(Point(p)) for p in pts), default=None)

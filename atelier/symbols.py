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


# =================================================================== furniture (top-down)
# Geometry is built in a local frame: a = across the front (right +), b = towards the
# front (+). Each kind returns a list of parts: (shapely polygon in local mm, role).
# Roles map to fills from texture.palette() in "present" mode; "line" mode outlines only.
from shapely.affinity import rotate as _rot, translate as _tr  # noqa: E402
from shapely.geometry import Point as _Pt, box as _box  # noqa: E402

from atelier import geom as _geom  # noqa: E402


def _rr(a0, b0, a1, b1, r=0.0):
    g = _box(a0, b0, a1, b1)
    if r > 0:
        r = min(r, (a1 - a0) / 2 - 1, (b1 - b0) / 2 - 1)
        g = g.buffer(-r, join_style=1).buffer(r, join_style=1)
    return g


def _circ(a, b, r):
    return _Pt(a, b).buffer(r, 32)


def furniture_parts(f):
    w, d = f["size"][0], f["size"][1]
    A, B = w / 2, d / 2
    k = f.get("kind", "other")
    P = []
    if k in ("sofa", "armchair"):
        arm, back = min(170, w * 0.18), min(190, d * 0.24)
        P.append((_rr(-A, -B, A, B, 60), "fabric_dk"))
        P.append((_rr(-A, -B, A, -B + back, 50), "fabric"))
        P.append((_rr(-A, -B, -A + arm, B, 50), "fabric"))
        P.append((_rr(A - arm, -B, A, B, 50), "fabric"))
        n = 3 if (k == "sofa" and w > 1600) else (2 if k == "sofa" else 1)
        span = (2 * A - 2 * arm) / n
        for i in range(n):
            a0 = -A + arm + i * span
            P.append((_rr(a0 + 12, -B + back + 10, a0 + span - 12, B - 25, 55), "cushion"))
        if k == "sofa":
            P.append((_rot(_rr(-A + arm + 40, -B + back - 60, -A + arm + 380, -B + back + 160, 70), -12), "throw"))
            P.append((_rot(_rr(A - arm - 380, -B + back - 60, A - arm - 40, -B + back + 160, 70), 10), "cushion"))
    elif k == "chair":
        P.append((_rr(-A + 20, -B + 60, A - 20, B - 10, 70), "wood_lt"))
        P.append((_rr(-A + 10, -B, A - 10, -B + 90, 40), "wood"))
    elif k in ("coffee_table", "dining_table", "console", "desk"):
        role = "wood_lt" if k != "desk" else "wood_lt"
        P.append((_rr(-A, -B, A, B, 40), role))
        P.append((_rr(-A + 35, -B + 35, A - 35, B - 35, 25), "inner"))
        if k == "desk":
            P.append((_rot(_rr(-170, -B + 90, 170, -B + 330, 12), 4), "metal"))
        if k == "coffee_table":
            P.append((_rot(_rr(-A * 0.45, -B * 0.35, -A * 0.05, B * 0.35, 15), 8), "cushion"))
    elif k == "side_table":
        r = min(A, B)
        P.append((_circ(0, 0, r), "wood_lt"))
        P.append((_circ(0, 0, r * 0.55), "inner"))
    elif k == "bed":
        P.append((_rr(-A, -B, A, B, 40), "wood"))
        P.append((_rr(-A + 30, -B + 70, A - 30, B - 30, 40), "linen"))
        P.append((_rr(-A + 30, -B + 600, A - 30, B - 30, 40), "cushion"))
        P.append((_rr(-A + 30, -B + 600, A - 30, -B + 700, 30), "linen"))
        P.append((_rr(-A + 30, B - 520, A - 30, B - 260, 20), "throw"))
        for s in (-1, 1):
            a0 = s * 25 if s > 0 else -A + 110
            a1 = A - 110 if s > 0 else -25
            P.append((_rr(a0, -B + 110, a1, -B + 470, 80), "linen"))
        P.append((_rr(-A, -B, A, -B + 60, 20), "wood"))
    elif k == "bedside":
        P.append((_rr(-A, -B, A, B, 30), "wood_lt"))
        P.append((_circ(0, -B * 0.1, min(A, B) * 0.42), "cushion"))
        P.append((_circ(0, -B * 0.1, min(A, B) * 0.12), "metal"))
    elif k == "rug":
        P.append((_rr(-A, -B, A, B, 10), "rug"))
        P.append((_rr(-A + 110, -B + 110, A - 110, B - 110, 6), "rug_line"))
        P.append((_rr(-A + 150, -B + 150, A - 150, B - 150, 4), "rug_line"))
    elif k == "plant":
        r = min(A, B)
        P.append((_circ(0, 0, r * 0.62), "stone"))
        for i in range(9):
            ang = i * 40.0 + 13
            leaf = _rot(_rr(-r * 0.16, 0, r * 0.16, r * 1.02, r * 0.15), ang, origin=(0, 0))
            P.append((leaf, "leaf" if i % 2 else "leaf_lt"))
        P.append((_circ(0, 0, r * 0.2), "leaf"))
    elif k == "tv":
        P.append((_rr(-A, -B, A, B, 5), "ink"))
    else:
        P.append((_rr(-A, -B, A, B, 30), "fabric"))
    return P


def _to_plan(f, g):
    """Local (a across, b to front) -> plan mm."""
    fx, fy = _geom.compass_to_vec(f.get("facing", "N"))
    ang = __import__("math").degrees(__import__("math").atan2(fy, fx)) - 90  # local +b = facing
    g = _rot(g, ang, origin=(0, 0))
    return _tr(g, *f["at"])


def furniture_footprint_page(pv, f):
    g = _to_plan(f, _rr(-f["size"][0] / 2, -f["size"][1] / 2, f["size"][0] / 2, f["size"][1] / 2))
    return [pv.P(*c) for c in g.exterior.coords[:-1]]


def draw_furniture(pv, f, mode="present"):
    """mode 'present': filled, shaded; 'line': outlines for marking plans."""
    from atelier.texture import hexc, mix, palette
    pal = palette()
    edge = hexc(mix(T.INK, T.PAPER, 0.35))
    for g, role in furniture_parts(f):
        gp = _to_plan(f, g)
        rings = pv.rings(gp)
        if mode == "line":
            if role in ("rug_line", "throw", "metal", "leaf_lt"):
                continue
            pv.sh.region(rings, fill="none", edge=T.INK if role != "inner" else T.GREY,
                         lw=LW_THIN if role != "inner" else LW_HAIR, z=6)
            continue
        if role == "inner":
            pv.sh.region(rings, fill="none", edge=edge, lw=LW_HAIR, z=6)
        elif role == "rug_line":
            pv.sh.region(rings, fill="none", edge=hexc(pal["rug_border"]), lw=LW_THIN, z=5)
        elif role == "ink":
            pv.sh.region(rings, fill=T.INK, z=6)
        else:
            z = 5 if f.get("kind") == "rug" else 6
            pv.sh.region(rings, fill=hexc(pal[role]), edge=edge, lw=LW_HAIR, z=z)


# =================================================================== joinery (top-down)
def joinery_modules(j, wall, room):
    """[(module, polygon_plan)] along the wall, on the room side."""
    side = _geom.room_side_of_wall(wall, room) or "left"
    f = _geom.face_offset(wall, side)
    dpt = j["depth"] * (1 if side == "left" else -1)
    out = []
    mods = (j.get("rows") or [{"modules": [{"w": j["width"], "type": "panel"}]}])[0]["modules"]
    o = j["offset"]
    from shapely.geometry import Polygon
    for md in mods:
        pts = [_geom.point_on_wall(wall, o, f), _geom.point_on_wall(wall, o + md["w"], f),
               _geom.point_on_wall(wall, o + md["w"], f + dpt), _geom.point_on_wall(wall, o, f + dpt)]
        out.append((md, Polygon(pts)))
        o += md["w"]
    return out


def draw_joinery(pv, j, wall, room, mode="present", label=False):
    from atelier.texture import hexc, mix, palette
    pal = palette()
    top = j.get("kind") in ("kitchen_base", "vanity")
    fill = hexc(pal["worktop"] if top else pal["joinery"])
    edge = hexc(mix(T.INK, T.PAPER, 0.35)) if mode == "present" else T.GREY
    whole = _geom.joinery_polygon(j, wall, room)
    pv.fill(whole, fill=fill if mode == "present" else T.PAPER, edge=edge, lw=LW_THIN, z=5)
    for md, poly in joinery_modules(j, wall, room):
        pv.fill(poly, fill="none", edge=edge, lw=LW_HAIR, z=6)
        c = poly.centroid
        mn = min(md["w"], j["depth"])
        if md["type"] == "sink":
            basin = c.buffer(mn * 0.32, 24) if j.get("kind") == "vanity" else \
                _box(c.x - mn * 0.33, c.y - mn * 0.28, c.x + mn * 0.33, c.y + mn * 0.28).buffer(30)
            pv.fill(basin, fill=hexc(pal["metal"]) if mode == "present" else "none", edge=edge, lw=LW_THIN, z=7)
        elif md["type"] == "hob":
            for dx in (-1, 1):
                for dy in (-1, 1):
                    pv.fill(_Pt(c.x + dx * mn * 0.2, c.y + dy * mn * 0.2).buffer(mn * 0.12, 20),
                            fill="none", edge=T.INK if mode == "present" else T.GREY, lw=LW_THIN, z=7)
        elif j.get("kind") == "wardrobe" and mode == "line":
            pass
    if j.get("kind") == "wardrobe":                 # hanging rail
        side = _geom.room_side_of_wall(wall, room) or "left"
        f = _geom.face_offset(wall, side) + (j["depth"] / 2) * (1 if side == "left" else -1)
        a = pv.P(*_geom.point_on_wall(wall, j["offset"] + 60, f))
        b = pv.P(*_geom.point_on_wall(wall, j["offset"] + j["width"] - 60, f))
        pv.sh.line([a, b], edge, LW_HAIR, (0, (2.0, 1.2)), z=7)
    if label:
        c = whole.centroid
        x, y = pv.P(c.x, c.y)
        pv.sh.text(x, y, j["id"], sans("dim", 600), T.GREY, ha="center", va="center", zorder=8)


# =================================================================== sanitary (top-down)
def sanitary_parts(s):
    w, d = s["size"][0], s["size"][1]
    A, B = w / 2, d / 2
    k = s.get("kind")
    P = []
    if k == "wc":
        P.append((_rr(-A, -B, A, -B + 180, 30), "worktop"))                       # cistern at the back
        bowl = _Pt(0, (-B + 180 + B) / 2 + 10).buffer(1, 32)
        from shapely.affinity import scale as _sc
        P.append((_sc(bowl, A * 0.85, (B * 2 - 180) / 2 * 0.95), "linen"))
    elif k in ("shower", "bathtub"):
        P.append((_rr(-A, -B, A, B, 20), "worktop"))
        P.append((_rr(-A + 40, -B + 40, A - 40, B - 40, 15), "inner"))
        P.append((_circ(0, 0, min(A, B) * 0.09), "metal"))
    elif k == "washing_machine":
        P.append((_rr(-A, -B, A, B, 30), "linen"))
        P.append((_circ(0, B * 0.05, min(A, B) * 0.62), "inner"))
    return P


def draw_sanitary(pv, s, mode="present"):
    from atelier.texture import hexc, mix, palette
    pal = palette()
    edge = hexc(mix(T.INK, T.PAPER, 0.35))
    for g, role in sanitary_parts(s):
        rings = pv.rings(_to_plan(s, g))
        if mode == "line":
            pv.sh.region(rings, fill="none", edge=T.INK if role != "inner" else T.GREY, lw=LW_THIN, z=6)
        elif role == "inner":
            pv.sh.region(rings, fill="none", edge=edge, lw=LW_HAIR, z=6)
        else:
            pv.sh.region(rings, fill=hexc(pal[role]), edge=edge, lw=LW_HAIR, z=6)

"""Joinery boards, one per joinery item: JN-01, JN-02, … (agents/STANDARDS.md §5b).

project.json lists them as "joinery:<joinery id>". Everything is drawn from the
item's data (modules, rows, finishes, handles, host wall); the internal fit is
the default fit of STANDARDS JB5b.5 (FIT below).
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Point

from atelier import geom
from atelier import theme as T
from atelier import texture as TX
from atelier.draw import DASH, LW_CUT, LW_HAIR, LW_LINE, LW_THIN, PlanView, Sheet, dim_chain, sans
from atelier.elev_detail import D as ED, Face, _module
from atelier.sheets import Frame, envelope_bounds, split_walls
from atelier.sheets_ceiling import _wrap

SCALES = (10, 15, 20, 25, 30, 40, 50)
# STANDARDS JB5b.3 / JB5b.5 defaults
FIT = dict(shelf_pitch=350, shelf=18, side=18, drawer_boxes=3, hang_drop=300, rail_below=50, ward_drawer=200,
           tap_hole=35, hob=(560, 490), sink_margin=75, overhang=20, wall_band=115)
TOP_KINDS = ("kitchen_base", "vanity")


def jn_number(m, jid):
    ids = [j["id"] for j in m.joinery]
    return f"JN-{ids.index(jid) + 1:02d}"


# ------------------------------------------------------------------ geometry of the item
class Item:
    def __init__(self, m, j):
        self.m, self.j = m, j
        self.room = m.room(j["room"])
        self.F = Face(m, {"id": j["id"], "room": j["room"], "wall": j["wall"]})
        mine = next(x for x in self.F.joinery() if x["j"]["id"] == j["id"])
        x0 = mine["xa"]
        self.W = j["width"]
        self.H = j.get("height", 850)
        self.Dp = j["depth"]
        self.top = j.get("kind") in TOP_KINDS
        self.gola = j.get("handles") == "gola"
        self.rows = j.get("rows") or [{"height": self.H, "modules": [{"w": self.W, "type": "panel"}]}]
        self.mods = [dict(md, xa=md["xa"] - x0, xb=md["xb"] - x0) for md in mine["mods"]]
        self.upper = [dict(md, xa=md["xa"] - x0, xb=md["xb"] - x0) for md in mine["upper"]]
        self.plinth = ED["plinth"]
        self.r1 = self.rows[0]["height"]
        self.work_top = self.r1 - (ED["worktop"] if self.top else 0)
        self.front_top = self.work_top - (ED["gola_h"] if self.gola else 0)
        self.sums = [(i + 1, sum(md["w"] for md in r["modules"]), self.W) for i, r in enumerate(self.rows)]

    def sums_ok(self):
        return all(a == b for _, a, b in self.sums)


class Canvas:
    """Duck-types elev_detail.Elev so the elevation module painter can be reused."""

    def __init__(self, sh, ox, oy, s):
        self.sh, self.ex0, self.ey0, self.s = sh, ox, oy, s

    def X(self, x):
        return self.ex0 + x / self.s

    def Z(self, z):
        return self.ey0 - z / self.s

    def Yp(self, y):                      # plan: depth from the wall, downwards on the page
        return self.ey0 + y / self.s

    def rect(self, xa, xb, za, zb, fill=None, edge=None, lw=LW_THIN, hatch=None, dash=None, z=4):
        self.sh.region([([(self.X(xa), self.Z(za)), (self.X(xb), self.Z(za)), (self.X(xb), self.Z(zb)),
                          (self.X(xa), self.Z(zb))], [])], fill=fill or "none", edge=edge or "none", lw=lw,
                       hatch=hatch, dash=dash, z=z)

    def prect(self, xa, xb, ya, yb, fill=None, edge=None, lw=LW_THIN, hatch=None, dash=None, z=4):
        self.sh.region([([(self.X(xa), self.Yp(ya)), (self.X(xb), self.Yp(ya)), (self.X(xb), self.Yp(yb)),
                          (self.X(xa), self.Yp(yb))], [])], fill=fill or "none", edge=edge or "none", lw=lw,
                       hatch=hatch, dash=dash, z=z)

    def line(self, pts, color=None, lw=LW_THIN, dash=None, z=5):
        self.sh.line([(self.X(x), self.Z(zz)) for x, zz in pts], color or T.INK, lw, dash, z=z)

    def pline(self, pts, color=None, lw=LW_THIN, dash=None, z=5):
        self.sh.line([(self.X(x), self.Yp(y)) for x, y in pts], color or T.INK, lw, dash, z=z)


def plan_depth(it: Item):
    """Real depth the plan needs: the item, its overhang, and the reach of door swings / drawers."""
    reach = 0
    if not it.top:
        for md in it.mods:
            w = md["xb"] - md["xa"]
            if md["type"] in ("shutter", "glass_shutter", "loft"):
                reach = max(reach, w)
            elif md["type"] == "drawer":
                reach = max(reach, 0.7 * it.Dp)
    return it.Dp + (FIT["overhang"] if it.top else 0) + reach


def choose_layout(it: Item, w=280, h=212):
    """Smallest scale (largest drawing) for which a layout fits. 'stack' = plan / front / internal
    one above the other; 'side' = plan over front, internal beside it."""
    Dp = plan_depth(it) + FIT["wall_band"] * 0.3
    for s in SCALES:
        if it.W / s <= w - 30 and (Dp + 2 * it.H) / s + 3 * 24 <= h:
            return s, "stack"
        if 2 * it.W / s + 70 <= w and (Dp + it.H) / s + 2 * 24 <= h:
            return s, "side"
    return SCALES[-1], "side"


# ------------------------------------------------------------------ the three views
def draw_plan(C: Canvas, it: Item):
    pal = TX.palette()
    W, Dp = it.W, it.Dp
    C.prect(-40, W + 40, -FIT["wall_band"] * 0.3, 0, fill=T.POCHE, z=3)                 # host wall
    if it.top:
        C.prect(0, W, 0, Dp + FIT["overhang"], fill=TX.hexc(pal["worktop"]), edge=T.INK, lw=LW_THIN, z=4)
        for md in it.mods[1:]:
            C.pline([(md["xa"], 0), (md["xa"], Dp)], T.GREY, LW_HAIR, DASH, z=5)
        for md in it.mods:
            cx, w = (md["xa"] + md["xb"]) / 2, md["xb"] - md["xa"]
            if md["type"] == "sink":
                bw = min(w - 2 * FIT["sink_margin"], 760)
                by0, by1 = 90, Dp - 100
                C.sh.region([([(C.X(cx - bw / 2), C.Yp(by0)), (C.X(cx + bw / 2), C.Yp(by0)),
                               (C.X(cx + bw / 2), C.Yp(by1)), (C.X(cx - bw / 2), C.Yp(by1))], [])],
                            fill=TX.hexc(pal["metal"]), edge=T.INK, lw=LW_THIN, z=6)
                C.sh.circle(C.X(cx), C.Yp((by0 + by1) / 2), 0.9, edge=T.INK, fill=T.PAPER, lw=LW_HAIR, z=7)
                C.sh.circle(C.X(cx), C.Yp(50), FIT["tap_hole"] / 2 / C.s + 0.15, edge=T.INK, fill=T.PAPER, lw=LW_THIN, z=7)
                C.sh.text(C.X(cx) + FIT["tap_hole"] / 2 / C.s + 1.2, C.Yp(50), f"tap hole Ø{FIT['tap_hole']}", sans("dim"), T.GREY,
                          va="center", zorder=8)
            elif md["type"] == "hob":
                hw, hd = FIT["hob"]
                hw = min(hw, w - 40)
                C.prect(cx - hw / 2, cx + hw / 2, (Dp - hd) / 2, (Dp + hd) / 2, fill=T.INK, edge=T.INK, z=6)
                for dx, dy, r in ((-0.25, -0.25, 70), (0.25, -0.25, 55), (-0.25, 0.25, 55), (0.25, 0.25, 90)):
                    C.sh.circle(C.X(cx + dx * hw), C.Yp(Dp / 2 + dy * hd), r / C.s, edge=T.PAPER, lw=LW_HAIR)
                    C.sh.ax.patches[-1].set_zorder(7)
                C.sh.text(C.X(cx), C.Yp((Dp + hd) / 2) + 2.2, f"hob cut-out {hw} × {hd}", sans("dim"), T.GREY,
                          ha="center", zorder=8)
        # worktop dims: overall, depth, cut-out centres
        cuts = sorted({0, W} | {round((md["xa"] + md["xb"]) / 2) for md in it.mods if md["type"] in ("sink", "hob")})
        if len(cuts) > 2:
            dim_chain(C.sh, (C.X(0), C.Yp(-FIT["wall_band"] * 0.3) - 6), (1, 0), (0, -1), [c / C.s for c in cuts],
                      [cuts[i + 1] - cuts[i] for i in range(len(cuts) - 1)], [False] * (len(cuts) - 1),
                      ext_from=[6] * len(cuts))
    else:
        C.prect(0, W, 0, Dp, fill=TX.hexc(pal["joinery"]), edge=T.INK, lw=LW_THIN, z=4)
        for md in it.mods[1:]:
            C.pline([(md["xa"], 0), (md["xa"], Dp)], T.GREY, LW_HAIR, z=5)
        for k, md in enumerate(it.mods):
            w = md["xb"] - md["xa"]
            if md["type"] in ("shutter", "glass_shutter", "loft"):
                hinge_left = k % 2 == 0
                hx, ox = (md["xa"], md["xb"]) if hinge_left else (md["xb"], md["xa"])
                r = w
                C.pline([(hx, Dp), (hx, Dp + r)], T.INK, LW_THIN, z=6)
                arc = [(hx + (ox - hx) * math.cos(math.radians(a)), Dp + r * math.sin(math.radians(a)))
                       for a in range(0, 91, 5)]
                C.pline(arc, T.GREY, LW_HAIR, z=6)
            elif md["type"] == "drawer":
                C.prect(md["xa"] + 20, md["xb"] - 20, Dp, Dp + 0.7 * Dp, edge=T.GREY, lw=LW_HAIR, dash=DASH, z=6)
    C.sh.text(C.X(-40) - 1, C.Yp(-FIT["wall_band"] * 0.15), "wall", sans("dim"), T.GREY, ha="right", va="center")
    dim_chain(C.sh, (C.X(W) + 6, C.Yp(0)), (0, 1), (1, 0),
              [0, (Dp + (FIT["overhang"] if it.top else 0)) / C.s],
              [Dp + (FIT["overhang"] if it.top else 0)], [False], ext_from=[6, 6])


def draw_front(C: Canvas, it: Item):
    pal = TX.palette()
    W = it.W
    C.rect(0, W, 0, it.plinth, fill=TX.hexc(TX.mix(T.MID, T.PAPER, 0.4)), edge=T.INK, lw=LW_HAIR, z=4)
    if it.gola:
        C.rect(0, W, it.front_top, it.work_top, fill=T.MID, edge=T.INK, lw=LW_HAIR, z=5)
    for k, md in enumerate(it.mods):
        _module(C, md, it.plinth, it.front_top, f"{it.j['id']}.{md['n']}", k, it.gola)
    z = it.r1
    for k, md in enumerate(it.upper):
        rh = it.rows[md["row"] - 1]["height"]
        _module(C, md, z, z + rh, f"{it.j['id']}.{md['n']}", k, it.gola)
    if it.top:
        C.rect(-FIT["overhang"] * 0, W, it.work_top, it.r1, fill=TX.hexc(pal["worktop"]), edge=T.INK, lw=LW_THIN, z=6)
    C.rect(0, W, 0, it.H, edge=T.INK, lw=LW_CUT, z=7)
    _chains(C, it)


def _chains(C, it):
    W = it.W
    xs = sorted({0, W} | {round(md["xa"]) for md in it.mods} | {round(md["xb"]) for md in it.mods})
    yb = C.Z(0)
    dim_chain(C.sh, (C.X(0), yb + 6), (1, 0), (0, 1), [x / C.s for x in xs], [xs[i + 1] - xs[i] for i in
              range(len(xs) - 1)], [False] * (len(xs) - 1), ext_from=[6] * len(xs))
    dim_chain(C.sh, (C.X(0), yb + 12), (1, 0), (0, 1), [0, W / C.s], [W], [False], ext_from=[12, 12])
    zs = sorted({0, it.plinth, it.H} | ({it.front_top, it.work_top} if it.top else set()) |
                {sum(r["height"] for r in it.rows[:i + 1]) for i in range(len(it.rows))})
    dim_chain(C.sh, (C.X(0) - 6, C.Z(0)), (0, -1), (-1, 0), [z / C.s for z in zs],
              [zs[i + 1] - zs[i] for i in range(len(zs) - 1)], [False] * (len(zs) - 1), ext_from=[6] * len(zs))


def fit_of(it, md, k, row=1):
    """Default internal fit (JB5b.5) as a short description."""
    t = md.get("type")
    if it.j.get("kind") == "wardrobe" and row == 1:
        return "hanging rail + shelf" if k % 2 == 0 else f"shelves @ {FIT['shelf_pitch']} + 2 drawers"
    return {"shutter": f"shelves @ {FIT['shelf_pitch']}", "glass_shutter": f"shelves @ {FIT['shelf_pitch']}",
            "drawer": f"{FIT['drawer_boxes']} drawer boxes", "sink": "sink bowl, trap, C/D points",
            "hob": "hob + 2 drawers", "loft": "1 shelf", "open": f"shelves @ {FIT['shelf_pitch']}",
            "filler": "filler panel", "appliance": "appliance space", "panel": "panel"}.get(t, t or "")


def draw_internal(C: Canvas, it: Item):
    pal = TX.palette()
    W = it.W
    carcass = TX.hexc(pal["wood_lt"])
    back = TX.hexc(TX.mix(T.PAPER, T.LIGHT, 0.6))
    C.rect(0, W, 0, it.plinth, fill=TX.hexc(TX.mix(T.MID, T.PAPER, 0.4)), edge=T.INK, lw=LW_HAIR, z=4)
    C.rect(0, W, it.plinth, it.H if not it.top else it.work_top, fill=back, edge=T.INK, lw=LW_THIN, z=3)
    sd = FIT["side"]

    def shelf(xa, xb, z):
        C.rect(xa + sd, xb - sd, z, z + FIT["shelf"], fill=carcass, edge=T.INK, lw=LW_HAIR, z=6)

    def body(mods, z0, z1, row):
        for k, md in enumerate(mods):
            xa, xb = md["xa"], md["xb"]
            C.rect(xa, xa + sd, z0, z1, fill=carcass, edge=T.INK, lw=LW_HAIR, z=5)
            C.rect(xb - sd, xb, z0, z1, fill=carcass, edge=T.INK, lw=LW_HAIR, z=5)
            shelf(xa - sd, xb + sd, z0)
            t = md.get("type")
            if it.j.get("kind") == "wardrobe" and row == 1:
                if k % 2 == 0:                                        # hanging
                    zs = z1 - FIT["hang_drop"]
                    shelf(xa, xb, zs)
                    zr = zs - FIT["rail_below"]
                    C.line([(xa + sd, zr), (xb - sd, zr)], T.INK, LW_LINE, z=7)
                    for x in (xa + sd + 8, xb - sd - 8):
                        C.sh.circle(C.X(x), C.Z(zr), 0.5, edge=T.INK, fill=T.MID, lw=LW_HAIR)
                    C.line([((xa + xb) / 2 - 120, zr - 40), ((xa + xb) / 2, zr - 900), ((xa + xb) / 2 + 120, zr - 40)],
                           T.GREY, LW_HAIR, DASH, z=6)
                else:
                    dz = z0 + FIT["shelf"]
                    for _ in range(2):
                        C.rect(xa + sd + 15, xb - sd - 15, dz + 10, dz + FIT["ward_drawer"] - 10, edge=T.INK,
                               lw=LW_HAIR, z=6)
                        dz += FIT["ward_drawer"]
                    z = dz + FIT["shelf_pitch"] - FIT["ward_drawer"]
                    while z < z1 - 150:
                        shelf(xa, xb, z)
                        z += FIT["shelf_pitch"]
            elif t == "drawer":
                n = FIT["drawer_boxes"]
                hh = (z1 - z0) / n
                for i in range(n):
                    C.rect(xa + sd + 15, xb - sd - 15, z0 + i * hh + 15, z0 + i * hh + hh * 0.72, edge=T.INK,
                           lw=LW_THIN, z=6)
            elif t == "sink":
                cx = (xa + xb) / 2
                C.rect(cx - (xb - xa) * 0.35, cx + (xb - xa) * 0.35, z1 - 220, z1, fill=TX.hexc(pal["metal"]),
                       edge=T.INK, lw=LW_THIN, z=6)
                C.line([(cx, z1 - 220), (cx, z1 - 330), (cx + 60, z1 - 330), (cx + 60, z1 - 260),
                        (cx + 60, z1 - 330), (cx + 60, 450), (xb - sd - 30, 450)], T.GREY, LW_LINE, z=7)
                for x, zc, col in ((cx - 100, 550, T.BLUE), (cx + 100, 550, T.FLAG), (xb - sd - 40, 450, T.GREY)):
                    if col == T.FLAG and it.room.get("type") not in ("bath", "toilet"):
                        continue
                    C.sh.circle(C.X(x), C.Z(zc), 0.9, edge=col, fill=col, lw=LW_HAIR)
                    C.sh.ax.patches[-1].set_zorder(8)
            elif t == "hob":
                C.rect(xa + sd, xb - sd, z1 - 60, z1, fill=T.INK, z=6)
                hh = (z1 - 60 - z0) / 2
                for i in range(2):
                    C.rect(xa + sd + 15, xb - sd - 15, z0 + i * hh + 15, z0 + i * hh + hh * 0.72, edge=T.INK,
                           lw=LW_THIN, z=6)
            elif t == "loft":
                shelf(xa, xb, (z0 + z1) / 2)
            elif t in ("shutter", "glass_shutter", "open"):
                z = z0 + FIT["shelf_pitch"]
                while z < z1 - 120:
                    shelf(xa, xb, z)
                    z += FIT["shelf_pitch"]
            C.sh.text(C.X((xa + xb) / 2), C.Z(z0 + 60), f"{it.j['id']}.{md['n']}", sans("dim", 600), T.GREY,
                      ha="center", va="center", zorder=8, path_effects=C.sh.halo(1.4))
        shelf(-sd, W + sd, z1 - FIT["shelf"])

    body(it.mods, it.plinth, it.work_top if it.top else it.r1, 1)
    z = it.r1
    for r_i, row in enumerate(it.rows[1:], 2):
        mods = [md for md in it.upper if md["row"] == r_i]
        body(mods, z, z + row["height"], r_i)
        z += row["height"]
    if it.top:
        C.rect(0, W, it.work_top, it.r1, fill=TX.hexc(pal["worktop"]), edge=T.INK, lw=LW_THIN, z=6)
    C.rect(0, W, 0, it.H, edge=T.INK, lw=LW_CUT, z=7)
    xs = sorted({0, W} | {round(md["xa"]) for md in it.mods} | {round(md["xb"]) for md in it.mods})
    dim_chain(C.sh, (C.X(0), C.Z(0) + 6), (1, 0), (0, 1), [x / C.s for x in xs],
              [xs[i + 1] - xs[i] for i in range(len(xs) - 1)], [False] * (len(xs) - 1), ext_from=[6] * len(xs))


# ------------------------------------------------------------------ strip: key plan, swatches
def key_plan(sh, m, it, x0, y0, w):
    b = envelope_bounds(m.walls)
    scale = 25 * math.ceil((b[2] - b[0]) / w / 25)
    pv = PlanView(sh, b, scale, centre=(x0 + w / 2, y0 + (b[3] - b[1]) / scale / 2))
    pv.fill(geom.room_polygon(it.room), fill=T.LIGHT, z=1)
    full, low = split_walls(m.walls)
    pv.fill(geom.walls_union(full), fill=T.GREY, z=2)
    pv.fill(geom.walls_union(low), fill=T.MID, z=2)
    jp = geom.joinery_polygon(it.j, m.wall(it.j["wall"]), it.room)
    pv.fill(jp, fill=T.INK, z=3)
    c = jp.centroid
    side = geom.room_side_of_wall(m.wall(it.j["wall"]), it.room) or "left"
    ux, uy, _ = geom.unit(m.wall(it.j["wall"])["a"], m.wall(it.j["wall"])["b"])
    nx, ny = geom.left_normal(ux, uy)
    sg = 1 if side == "left" else -1
    tail = (c.x + nx * sg * 1600, c.y + ny * sg * 1600)
    head = (c.x + nx * sg * (it.Dp / 2 + 150), c.y + ny * sg * (it.Dp / 2 + 150))
    sh.ax.annotate("", xy=pv.P(*head), xytext=pv.P(*tail),
                   arrowprops=dict(arrowstyle="-|>", lw=LW_THIN, color=T.FLAG, mutation_scale=6), zorder=5)
    return y0 + (b[3] - b[1]) / scale + 2, scale


def swatch_circles(sh, m, it, x0, y0):
    fin = {f["code"]: f for f in m.finishes}
    pal = TX.palette()
    items = []
    for code in (it.j.get("finish"), it.j.get("worktop")):
        if code and code in fin:
            items.append((code, fin[code]["name"].split(",")[0], fin[code]))
    h = it.j.get("handles", "bar")
    items.append(("H", {"gola": "Gola profile, aluminium", "bar": "Bar handle, brushed steel",
                        "knob": "Knob, brushed steel", "push": "Push-to-open"}[h], {"kind": "metal"}))
    r = 5.0
    for i, (code, name, f) in enumerate(items):
        cx, cy = x0 + r + i * 23, y0 + r
        kind = f.get("kind")
        if kind in ("stone", "tile", "wood"):
            arr = TX.floor_texture(f, {"pattern": "straight", "module": [800, 1600]}, (0, 0, 700, 700), 0.4, seed=5)
        else:
            tone = {"laminate": pal["joinery"], "paint": TX.mix(T.PAPER, T.LIGHT, 0.4), "metal": pal["metal"],
                    "fabric": pal["fabric"]}.get(kind, pal["joinery"])
            arr = np.ones((40, 40, 3)) * tone
        ring = [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 48)]
        sh.image(arr, cx - r, cy - r, cx + r, cy + r, clip_rings=[(ring, [])], z=4)
        sh.circle(cx, cy, r, edge=T.INK, lw=LW_THIN)
        sh.text(cx, cy + r + 2.6, code, sans("dim", 700), T.INK, ha="center")
        for k, ln in enumerate(_wrap(name, 14)[:2]):
            sh.text(cx, cy + r + 5.0 + k * 2.3, ln, sans("dim"), T.GREY, ha="center")
    return y0 + 2 * r + 11


# ------------------------------------------------------------------ the board
def board(m, no, total, jid):
    j = next(x for x in m.joinery if x["id"] == jid)
    it = Item(m, j)
    if not it.sums_ok():                                                 # JB5b.8: fail the build
        bad = ", ".join(f"row {r}: {a} ≠ {b}" for r, a, b in it.sums if a != b)
        raise ValueError(f"{jid}: module widths do not sum to the run length ({bad})")
    sh = Sheet()
    jn = jn_number(m, jid)
    kind = j.get("kind", "").replace("_", " ")
    s, lay = choose_layout(it)
    fr = Frame(sh, m, f"Joinery board {jn}", f"{jid} · {kind} · {it.room.get('name')} · 1:{s}", no, total, s)
    x0, y0, x1, y1 = T.DRAW
    left = x0 + 26
    band = FIT["wall_band"] * 0.3
    Dp = plan_depth(it)
    # plan
    py = y0 + 14 + band / s
    Cp = Canvas(sh, left, py, s)
    draw_plan(Cp, it)
    sh.caps(left, y0 + 4, f"Plan  ·  1:{s}", T.INK, role="legend_head", weight=600)
    # front
    fy = py + Dp / s + 24 + it.H / s
    Cf = Canvas(sh, left, fy, s)
    draw_front(Cf, it)
    sh.caps(left, fy - it.H / s - 4, f"Front elevation  ·  1:{s}", T.INK, role="legend_head", weight=600)
    # internal
    if lay == "stack":
        iy, ix = fy + 26 + it.H / s, left
    else:
        iy, ix = fy, left + it.W / s + 44
    Ci = Canvas(sh, ix, iy, s)
    draw_internal(Ci, it)
    sh.caps(ix, iy - it.H / s - 4, f"Internal elevation, doors removed  ·  1:{s}", T.INK, role="legend_head",
            weight=600)
    # strip
    fr.head("Key plan")
    fr.y, ks = key_plan(sh, m, it, T.STRIP_X, fr.y - 1, T.RIGHT - T.STRIP_X)
    sh.text(T.STRIP_X, fr.y + 1.2, f"1:{ks} · arrow = front elevation view", sans("dim"), T.GREY)
    fr.y += 5
    fr.rule()
    fr.head("Finishes")
    fr.y = swatch_circles(sh, m, it, T.STRIP_X, fr.y - 2)
    fr.rule()
    fin = {f["code"]: f for f in m.finishes}
    fr.head("Materials")
    mats = []
    jm = j.get("materials") or {}
    pairs = list(jm.items()) if isinstance(jm, dict) else [(None, c) for c in jm]
    seen = set()
    for role, code in pairs + [("worktop", j.get("worktop")), (None, j.get("finish"))]:
        if code in fin and code not in seen:
            seen.add(code)
            mats.append((code, (f"{role}: " if role else "") + fin[code]["name"], None))
    for p in j.get("parts", []):                            # the designer's part list
        code = p.get("code") or p.get("material")
        size = "×".join(str(v) for v in p.get("size", [])) if p.get("size") else ""
        mats.append((code or "·", " ".join(x for x in (p.get("name") or p.get("part", ""), size,
                                                         f"×{p['qty']}" if p.get("qty") else "") if x), None))
    if not any(str(c).startswith("HW") for c, _, _ in mats):
        mats.append(("H", {"gola": "Gola J-profile, aluminium, 30 × 50", "bar": "Bar handles, brushed steel",
                           "knob": "Knobs", "push": "Push-to-open"}[j.get("handles", "bar")], None))
    fr.lines(mats, indent=9, max_chars=52)
    fr.y += 1
    fr.head("Modules")
    rows = []
    for k, md in enumerate(it.mods):
        rows.append((f"{jid}.{md['n']}", f"{md['type']} {md['w']} · {fit_of(it, md, k)}", None))
    for k, md in enumerate(it.upper):
        rows.append((f"{jid}.{md['n']}", f"{md['type']} {md['w']} · {fit_of(it, md, k, md['row'])}", None))
    fr.lines(rows, indent=11, max_chars=50)
    fr.y += 1
    fr.head("Notes")
    sums = "; ".join(f"row {r}: Σ {a} = run {b} ✓" for r, a, b in it.sums)
    face_note = f"Run {it.W} on a {round(it.F.L)} wall face." if it.W <= it.F.L + 1 else \
        f"Run {it.W} is longer than the {round(it.F.L)} wall face!"
    own = [n if isinstance(n, str) else n.get("text", "") for n in j.get("notes", [])]
    std = [sums, face_note]
    if not own:
        std += ["Carcass 18 BWP ply, 6 back, plinth 100 recessed 60; soft-close hinges and full-extension runners.",
                "Internal fit is the Atelier default (STANDARDS JB5b.5): confirm with the client."]
    fr.lines([(str(i), t, None) for i, t in enumerate(own + std, 1)], max_chars=52)
    return sh

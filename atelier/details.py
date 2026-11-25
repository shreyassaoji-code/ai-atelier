"""Detail sheets DT-01 and DT-02 (agents/STANDARDS.md §5a).

DT-01: 1 cove (1:5) · 2 wall panel with LED reveal (1:5) · 3 skirting (1:5)
DT-02: 4 concealed flush door (1:5) · 5 worktop + gola + base unit (1:10) · 6 wardrobe section (1:10)

Sizes come from the data where it has them (see `_source_*`); the rest are the
defaults in DEF, recorded in STANDARDS D5a.5.
"""
from __future__ import annotations

import math
from collections import OrderedDict

from atelier import theme as T
from atelier import texture as TX
from atelier.draw import DASH, LW_HAIR, LW_LINE, LW_THIN, Sheet, dim_chain, sans
from atelier.sheets import Frame
from atelier.sheets_ceiling import _cove_detail, _wrap

# STANDARDS D5a.5 defaults (the only place these numbers live)
DEF = dict(plaster=12, brick=115, ground=25, ground_w=50, ground_cc=450, panel=18, reveal=20, leaf=40, gap=3,
           carcass=18, back=6, plinth_recess=60, gola_d=30, gola_h=50, bed=30, finish=20, slab=150, adhesive=3,
           skirting_t=12, overhang=20, rail=25, shelf=18)


# ------------------------------------------------------------------ materials (D5a.3)
def MATS():
    p = TX.palette()
    return OrderedDict(
        concrete=dict(fill=T.PAPER, hatch="//..", edge=T.GREY, name="RCC / concrete"),
        brick=dict(fill=TX.hexc(TX.mix(T.LIGHT, T.PAPER, 0.3)), hatch="////", edge=T.GREY, name="Brick masonry"),
        plaster=dict(fill=TX.hexc(TX.mix(T.LIGHT, T.PAPER, 0.5)), hatch="....", edge=T.GREY, name="Plaster / mortar"),
        gypsum=dict(fill=T.PAPER, hatch="...", edge=T.GREY, name="Gypsum board"),
        ply=dict(fill=TX.hexc(p["wood_lt"]), hatch="xxx", edge=T.GREY, name="BWP plywood"),
        mdf=dict(fill=TX.hexc(TX.mix(T.AMBER, T.PAPER, 0.6)), hatch="\\\\\\\\", edge=T.GREY, name="MDF"),
        timber=dict(fill=TX.hexc(p["oak"]), hatch="--", edge=T.GREY, name="Timber"),
        veneer=dict(fill=TX.hexc(p["oak_dark"]), hatch=None, edge=T.INK, name="Veneer / laminate"),
        stone=dict(fill=TX.hexc(p["worktop"]), hatch="..o", edge=T.GREY, name="Stone / quartz"),
        tile=dict(fill=TX.hexc(p["stone"]), hatch="--", edge=T.GREY, name="Tile"),
        aluminium=dict(fill=T.MID, hatch=None, edge=T.INK, name="Aluminium"),
        steel=dict(fill=T.GREY, hatch=None, edge=T.INK, name="Steel / GI"),
    )


class Det:
    """A detail canvas: x, z in real mm, origin at page (ox, oy), scale 1:s (z up)."""

    def __init__(self, sh, ox, oy, s):
        self.sh, self.ox, self.oy, self.s = sh, ox, oy, s
        self.used = []
        self.notes = []

    def X(self, x):
        return self.ox + x / self.s

    def Y(self, z):
        return self.oy - z / self.s

    def P(self, x, z):
        return (self.X(x), self.Y(z))

    def mat(self, pts, m, lw=LW_THIN, z=4):
        st = MATS()[m]
        if m not in self.used:
            self.used.append(m)
        self.sh.region([([self.P(*p) for p in pts], [])], fill=st["fill"], edge=st["edge"], lw=lw, hatch=st["hatch"], z=z)
        self.sh.region([([self.P(*p) for p in pts], [])], fill="none", edge=T.INK, lw=lw, z=z + 0.1)

    def rect(self, x0, x1, z0, z1, m, lw=LW_THIN, z=4):
        self.mat([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], m, lw, z)

    def line(self, pts, c=None, lw=LW_THIN, dash=None, z=6):
        self.sh.line([self.P(*p) for p in pts], c or T.INK, lw, dash, z=z)

    def brk(self, a, b):
        """Break line between real points a and b."""
        (x0, z0), (x1, z1) = a, b
        n = 6
        pts = []
        for i in range(n + 1):
            t = i / n
            off = (1.2 if i % 2 else -1.2) * self.s if 0 < i < n else 0
            dx, dz = x1 - x0, z1 - z0
            L = math.hypot(dx, dz) or 1
            pts.append((x0 + dx * t - dz / L * off, z0 + dz * t + dx / L * off))
        self.line(pts, T.GREY, LW_HAIR, z=8)

    def hdim(self, z, xs, below=True, off=5):
        xs = sorted(xs)
        a = self.P(xs[0], z)
        n = (0, 1) if below else (0, -1)
        dim_chain(self.sh, (self.X(0), a[1] + (off if below else -off)), (1, 0), n, [x / self.s for x in xs],
                  [round(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)], [False] * (len(xs) - 1),
                  ext_from=[off] * len(xs))

    def vdim(self, x, zs, left=True, off=5):
        zs = sorted(zs)
        b = self.P(x, 0)
        n = (-1, 0) if left else (1, 0)
        dim_chain(self.sh, (b[0] + (-off if left else off), self.Y(0)), (0, -1), n, [z / self.s for z in zs],
                  [round(zs[i + 1] - zs[i]) for i in range(len(zs) - 1)], [False] * (len(zs) - 1),
                  ext_from=[off] * len(zs))

    def note(self, x, z, text):
        self.notes.append((self.P(x, z), text))

    def callouts(self, col_x, top=None, bottom=None, wrap=22):
        """CAPS labels on leaders in a column at page x `col_x` (D5a.4)."""
        items = sorted(self.notes, key=lambda t: t[0][1])
        wrapped = [_wrap(t.upper(), wrap) for _, t in items]
        ys, nxt = [], top if top is not None else -1e9
        for (p, _), ln in zip(items, wrapped):
            y = max(p[1] - 0.8, nxt)
            ys.append(y)
            nxt = y + len(ln) * 2.3 + 1.4
        if bottom is not None and ys and ys[-1] + len(wrapped[-1]) * 2.3 > bottom:     # pull the column up
            shift = ys[-1] + len(wrapped[-1]) * 2.3 - bottom
            ys = [y - shift for y in ys]
        for ((px, py), _), y, ln in zip(items, ys, wrapped):
            self.sh.line([(px, py), (col_x - 2, y), (col_x - 0.6, y)], T.INK, LW_HAIR, z=12)
            self.sh.circle(px, py, 0.32, edge=T.INK, fill=T.INK, lw=LW_HAIR)
            self.sh.ax.patches[-1].set_zorder(12)
            for k, s_ in enumerate(ln):
                self.sh.text(col_x, y + 0.9 + k * 2.3, s_, sans("dim", 500), T.INK, va="center", zorder=12)


def place(sh, box, s, xr, zr, left=14):
    """A Det whose real extents xr (x min/max) and zr (z min/max) sit in `box`, centred vertically;
    the callout column is the last 24 mm of the box."""
    bx0, by0, bx1, by1 = box
    ox = bx0 + left - xr[0] / s
    oy = (by0 + by1) / 2 + (zr[0] + zr[1]) / 2 / s
    return Det(sh, ox, oy, s), bx1 - 21


def title(sh, x, y, n, sheet_id, text, scale, src=""):
    r = 4.2
    sh.circle(x + r, y, r, edge=T.INK, fill=T.PAPER, lw=LW_THIN)
    sh.line([(x, y), (x + 2 * r, y)], T.INK, LW_HAIR, z=6)
    sh.text(x + r, y - 1.9, str(n), sans("legend_head", 700), T.INK, ha="center", va="center", zorder=7)
    sh.text(x + r, y + 2.0, sheet_id, sans("dim", 600), T.INK, ha="center", va="center", zorder=7)
    sh.caps(x + 2 * r + 2.5, y - 0.4, text, T.INK, role="legend_head", weight=600)
    sh.text(x + 2 * r + 2.5, y + 3.4, f"1:{scale}" + (f"  ·  {src}" if src else ""), sans("dim"), T.GREY)


def material_key(fr, sh, used):
    st = MATS()
    items = []
    for m in used:
        s = st[m]
        items.append((s["name"], lambda x, y, w, h, s=s: sh.swatch(x, y, w, h, fill=s["fill"], edge=s["edge"],
                                                                   hatch=s["hatch"], lw=LW_HAIR)))
    fr.legend(items)


# ------------------------------------------------------------------ data sources
def _fin(m, code):
    return next((f for f in m.finishes if f["code"] == code), {}) if code else {}


def _src_panel(m):
    fw = next((w for w in m.wall_features if w.get("kind") in ("panelling", "fluted")), None)
    wall = m.wall(fw["wall"]) if fw else None
    return fw, wall


def _src_skirting(m):
    fl = max((f for f in m.floors if f.get("skirting")), key=lambda f: f["skirting"], default=None)
    return fl


def _src_door(m):
    o = next((o for o in m.openings if o["kind"] == "door" and m.wall(o["wall"]).get("kind") != "external"), None)
    return o, (m.wall(o["wall"]) if o else None)


def _src_join(m, kinds):
    return next((j for j in m.joinery if j.get("kind") in kinds), None)


# ------------------------------------------------------------------ DT-01
def d2_panel(sh, m, box, s=5):
    """2 · wall panel with LED reveal: plan section through a reveal between two panels."""
    fw, wall = _src_panel(m)
    t_wall = wall["t"] if wall else DEF["brick"]
    pl, gr, pn, rv = DEF["plaster"], DEF["ground"], DEF["panel"], DEF["reveal"]
    fin = _fin(m, fw.get("finish")) if fw else {}
    L0, L1 = -40, 220
    D, col = place(sh, box, s, (L0, L1 + 40), (-pl - gr - pn - 30, t_wall + 10))
    # wall (top of the drawing is the wall; the room is below: depth runs downwards on the page)
    D.rect(L0, L1, 0, t_wall, "brick")
    D.rect(L0, L1, -pl, 0, "plaster")
    for gx in (10, 160):
        D.rect(gx, gx + DEF["ground_w"], -pl - gr, -pl, "timber")
    zf = -pl - gr
    D.rect(L0, 90, zf - pn, zf, "mdf")
    D.rect(L0, 90, zf - pn - 1.5, zf - pn, "veneer", lw=LW_HAIR)
    D.rect(90 + rv, L1, zf - pn, zf, "mdf")
    D.rect(90 + rv, L1, zf - pn - 1.5, zf - pn, "veneer", lw=LW_HAIR)
    for x in range(L0 + 15, L1, 30):                            # flutes on the face
        if 84 <= x <= 96 + rv:
            continue
        D.line([(x - 6, zf - pn - 1.5), (x, zf - pn - 5), (x + 6, zf - pn - 1.5)], T.INK, LW_HAIR)
    D.rect(92, 108, zf - 14, zf - 2, "aluminium", lw=LW_HAIR)    # LED profile in the reveal
    D.line([(92, zf - 14.5), (108, zf - 14.5)], T.AMBER, LW_LINE, z=7)
    for x in (L0, L1):
        D.brk((x, t_wall + 8), (x, zf - pn - 10))
    D.hdim(zf - pn - 10, [90, 90 + rv], below=True, off=6)
    D.vdim(L1, [t_wall, 0, -pl, zf, zf - pn], left=False, off=6)
    D.note(150, t_wall * 0.6, f"{t_wall} brick wall {wall['id'] if wall else ''}")
    D.note(-20, -pl / 2, f"{pl} plaster")
    D.note(185, -pl - gr / 2, f"{DEF['ground']} × {DEF['ground_w']} timber ground @ {DEF['ground_cc']}")
    D.note(30, zf - pn / 2, f"{pn} MDF panel")
    D.note(170, zf - pn - 3, fin.get("name", "veneer face").split(",")[0] + (f" ({fw['finish']})" if fw else ""))
    D.note(100, zf - 8, f"{rv} reveal, aluminium LED profile, opal diffuser")
    D.callouts(col, wrap=18)
    return D, (fw["id"] + " · " + fw["room"]) if fw else "default"


def d3_skirting(sh, m, box, s=5):
    """3 · skirting: vertical section at the floor."""
    fl = _src_skirting(m)
    h = fl["skirting"] if fl else 100
    ff = _fin(m, fl["finish"]) if fl else {}
    t, pl = DEF["skirting_t"], DEF["plaster"]
    fin_t, bed = DEF["finish"], DEF["bed"]
    W = DEF["brick"]
    xl, xr_ = -70, 150
    D, col = place(sh, box, s, (xl, xr_ + 30), (-fin_t - bed - 60, 260))
    D.rect(xl, -pl, -fin_t - bed - 60, 260, "brick")
    D.rect(-pl, 0, h + 2, 260, "plaster")
    D.rect(-pl, 0, -fin_t, h + 2, "plaster")
    D.rect(xl, xr_, -fin_t - bed - 60, -fin_t - bed, "concrete")
    D.rect(0, xr_, -fin_t - bed, -fin_t, "plaster")
    D.rect(0, xr_, -fin_t, 0, "stone")
    D.rect(DEF["adhesive"], DEF["adhesive"] + t, 0, h, "stone")
    D.rect(0, DEF["adhesive"], 0, h, "plaster", lw=LW_HAIR)
    D.brk((xl - 6, 260), (60, 260))
    D.brk((xl, -fin_t - bed - 70), (xl, 270))
    D.brk((xr_, -fin_t - bed - 70), (xr_, 10))
    D.vdim(DEF["adhesive"] + t, [0, h], left=False, off=10)
    D.vdim(xr_, [-fin_t - bed, -fin_t, 0], left=False, off=6)
    D.hdim(h + 30, [0, DEF["adhesive"], DEF["adhesive"] + t], below=False, off=4)
    D.note(-45, 180, f"{W} brick wall")
    D.note(-pl / 2, 200, f"{pl} plaster + paint")
    D.note(DEF["adhesive"] + t / 2, h * 0.6,
           f"{h} × {t} skirting to match floor, adhesive fixed, top edge eased")
    D.note(100, -fin_t / 2, (ff.get("name", "floor finish").split(",")[0] + (f" ({fl['finish']})" if fl else "")))
    D.note(120, -fin_t - bed / 2, f"{bed} mortar bed")
    D.note(-30, -fin_t - bed - 30, "RCC slab")
    D.callouts(col, wrap=18)
    return D, (f"{fl['room']} · {fl['finish']} · skirting {h}" if fl else "default")


# ------------------------------------------------------------------ DT-02
def d4_door(sh, m, box, s=5):
    """4 · concealed flush door: plan section through the hinge jamb."""
    o, wall = _src_door(m)
    tw = wall["t"] if wall else DEF["brick"]
    pl, lf, g = DEF["plaster"], DEF["leaf"], DEF["gap"]
    xl, xr_ = -80, 130
    D, col = place(sh, box, s, (xl, xr_ + 12), (-tw - 2 * pl - 20, 60), left=12)
    # wall runs left of the jamb (x < 0); depth z: 0 = push face of plaster
    D.rect(xl, 0, -tw - pl, -pl, "brick")
    D.rect(xl, 0, -pl, 0, "plaster")
    D.rect(xl, 0, -tw - 2 * pl, -tw - pl, "plaster")
    D.mat([(0, 0), (14, 0), (14, -tw - 2 * pl), (0, -tw - 2 * pl), (0, -tw - 2 * pl + 3), (11, -tw - 2 * pl + 3),
           (11, -3), (0, -3)], "aluminium", lw=LW_HAIR)
    # leaf, flush with the push face, 3 shadow gap at the jamb
    x_l = 14 + g
    D.rect(x_l, xr_, -lf, 0, "ply")
    D.rect(x_l, xr_, -1, 0, "veneer", lw=LW_HAIR)
    D.rect(x_l, xr_, -lf, -lf + 1, "veneer", lw=LW_HAIR)
    D.rect(x_l + 6, x_l + 34, -lf + 8, -8, "steel", lw=LW_HAIR)     # concealed hinge body
    D.brk((xl, 8), (xl, -tw - 2 * pl - 8))
    D.brk((xr_, 8), (xr_, -lf - 8))
    rr = xr_ - x_l
    arc = [(x_l + rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a))) for a in range(0, 31, 3)]
    D.line(arc, T.GREY, LW_HAIR, DASH)
    D.hdim(-tw - 2 * pl - 4, [0, 14, x_l], below=True, off=6)
    D.vdim(xl, [-tw - 2 * pl, -tw - pl, -pl, 0], left=True, off=6)
    D.vdim(xr_, [-lf, 0], left=False, off=6)
    D.note(-50, -pl - tw / 2, f"{tw} brick wall {wall['id'] if wall else ''}")
    D.note(-30, -pl / 2, f"{pl} plaster both faces")
    D.note(7, -tw / 2, "Concealed aluminium frame, plastered in")
    D.note(x_l + 1.5, -lf / 2, f"{g} shadow gap")
    D.note(x_l + 20, -lf / 2, "Concealed hinge, 3-way adjustable")
    D.note(100, -lf / 2, f"{lf} flush leaf, laminate both faces")
    D.callouts(col, wrap=18)
    return D, (f"{o['id']} · {o['width']} clear · wall {wall['id']}" if o else "default")


def d5_base(sh, m, box, s=10):
    """5 · worktop + gola + base unit: vertical section through the run."""
    j = _src_join(m, ("kitchen_base",))
    H = j["rows"][0]["height"] if j else 850
    dp = j["depth"] if j else 600
    wt = _fin(m, j.get("worktop")) if j else {}
    mb = _fin(m, j.get("finish")) if j else {}
    wf = next((w for w in m.wall_features if j and w["wall"] == j["wall"] and w["room"] == j["room"]), None)
    pl, c, b = DEF["plaster"], DEF["carcass"], DEF["back"]
    pr, gd, gh = DEF["plinth_recess"], DEF["gola_d"], DEF["gola_h"]
    top_t = 40
    xl, xr_, ztop = -50, dp + 60, H + 700
    D, col = place(sh, box, s, (xl, xr_), (-60, ztop), left=16)
    D.rect(xl, -pl, -60, ztop, "brick")
    D.rect(-pl, 0, -20, ztop, "plaster")
    if wf:
        D.rect(0, 8, H, wf["z1"], "tile")
    D.rect(xl, xr_, -60, -30, "concrete")
    D.rect(0, xr_, -30, -10, "plaster")
    D.rect(0, xr_, -10, 0, "tile")
    D.rect(0, dp + DEF["overhang"], H - top_t, H, "stone")               # worktop (+ ply)
    D.rect(0, dp + DEF["overhang"], H - top_t, H - top_t / 2, "ply")
    D.rect(20, 20 + b, DEF["plinth"] if False else 100 + c, H - top_t - gh, "ply")   # back panel
    D.rect(20, dp - c, 100, 100 + c, "ply")                               # bottom
    D.rect(20 + b, dp - c, 430, 430 + c, "ply")                           # shelf
    D.rect(dp - c, dp, 100, H - top_t - gh, "mdf")                        # shutter
    D.rect(dp - c, dp, 100, H - top_t - gh, "veneer", lw=LW_HAIR)
    D.mat([(dp - gd - 2, H - top_t), (dp, H - top_t), (dp, H - top_t - 6), (dp - gd + 2, H - top_t - 6),
           (dp - gd + 2, H - top_t - gh + 4), (dp, H - top_t - gh + 4), (dp, H - top_t - gh),
           (dp - gd - 2, H - top_t - gh)], "aluminium", lw=LW_HAIR)       # gola J-profile
    D.rect(dp - pr - c, dp - pr, 0, 100, "ply")                           # plinth board
    D.brk((xl - 8, ztop), (dp + 40, ztop))
    D.brk((xr_, -70), (xr_, 30))
    D.vdim(xl, [0, 100, H - top_t - gh, H - top_t, H], left=True, off=6)
    D.hdim(-60, [0, dp - pr, dp, dp + DEF["overhang"]], below=True, off=6)
    D.note(-40, H + 500, f"{DEF['brick']} brick wall + {pl} plaster")
    if wf:
        D.note(4, (H + wf["z1"]) / 2, f"Backsplash tile ({wf['finish']})")
    D.note(dp * 0.45, H - top_t / 4, (wt.get("name", "worktop").split(",")[0] + (f" ({j['worktop']})" if j else "")))
    D.note(dp * 0.3, H - top_t * 0.75, "20 BWP ply sub-top")
    D.note(dp - gd / 2, H - top_t - gh / 2, f"Gola J-profile, aluminium, {gd} × {gh}")
    D.note(dp - c / 2, (H + 100) / 2, f"{c} shutter, " + (mb.get("name", "laminate").split(",")[-1].strip()
                                                         + (f" ({j['finish']})" if j and j.get("finish") else "")))
    D.note(dp * 0.5, 430 + c / 2, f"{c} BWP ply shelf")
    D.note(20 + b / 2, 300, f"{b} back panel")
    D.note(dp - pr - c / 2, 50, f"100 plinth, recessed {pr}")
    D.note(dp + 60, -5, "Floor tile on bed")
    D.callouts(col, wrap=18)
    return D, (f"{j['id']} · {j['room']} · {H} high, {dp} deep" if j else "default")


def d6_wardrobe(sh, m, box, s=10):
    """6 · wardrobe section, broken through the hanging zone."""
    j = _src_join(m, ("wardrobe",))
    H = j.get("height", 2400) if j else 2400
    dp = j["depth"] if j else 600
    rows = j.get("rows", [{"height": 1800}, {"height": 600}]) if j else [{"height": 1800}, {"height": 600}]
    r1 = rows[0]["height"]
    c = next((c for c in m.ceilings if j and c["room"] == j["room"]), None)
    fcl = c["z"] if c and c.get("z") else H
    mb = _fin(m, j.get("finish")) if j else {}
    cz, pl = DEF["carcass"], DEF["plaster"]
    lo, hi = 650, 1450                                                   # hidden by the break
    gapz = 90
    D, col = place(sh, box, s, (-50, dp + 40), (-40, fcl + 60 - (hi - lo) + 80), left=16)

    def Z(z):                                                            # compress the hanging zone
        return z if z <= lo else (lo + 80 if z < hi else z - (hi - lo) + 80)

    def R(x0_, x1_, z0, z1, mm):
        D.rect(x0_, x1_, Z(z0), Z(z1), mm)

    R(-50, -pl, -40, fcl + 60, "brick")
    R(-pl, 0, -10, fcl + 60, "plaster")
    R(-50, dp + 40, -40, -10, "concrete")
    R(0, dp + 40, -10, 0, "tile")
    R(0, dp, fcl, fcl + 12.5, "gypsum")
    R(20, dp - cz, 100, 100 + cz, "ply")                                 # bottom
    R(20, dp - cz, r1 - cz / 2, r1 + cz / 2, "ply")                      # loft shelf
    R(20, dp - cz, H - cz, H, "ply")                                     # top
    R(20, 20 + DEF["back"], 100, H, "ply")                               # back
    R(dp - cz, dp, 100, r1 - 2, "mdf")                                   # long shutter
    R(dp - cz, dp, r1 + 2, H, "mdf")                                     # loft shutter
    R(dp - cz, dp, H, fcl, "mdf")                                        # top filler to the ceiling
    R(dp - 60 - cz, dp - 60, 0, 100, "ply")                              # plinth
    rail_z = r1 - 120
    D.sh.circle(D.X(dp / 2), D.Y(Z(rail_z)), DEF["rail"] / 2 / s + 0.2, edge=T.INK, fill=T.MID, lw=LW_THIN)
    D.sh.ax.patches[-1].set_zorder(6)
    D.line([(dp / 2, Z(r1 - cz / 2)), (dp / 2, Z(rail_z) + 12)], T.INK, LW_HAIR)
    D.brk((-60, lo + 40), (dp + 30, lo + 40))
    D.line([(dp / 2, 300), (dp / 2, 500)], T.GREY, LW_HAIR, DASH)        # garment hint
    zs = [0, 100, r1, H, fcl] if fcl > H else [0, 100, r1, H]
    dim_chain(D.sh, (D.X(-50) - 6, D.Y(0)), (0, -1), (-1, 0), [Z(z) / s for z in zs],
              [zs[i + 1] - zs[i] for i in range(len(zs) - 1)], [False] * (len(zs) - 1), ext_from=[6] * len(zs))
    D.hdim(-40, [0, dp - 60, dp], below=True, off=6)
    D.note(-40, Z(H - 200), f"{DEF['brick']} brick wall + plaster")
    D.note(dp - cz / 2, Z(300), f"{cz} shutter, " + (mb.get("name", "laminate").split(",")[-1].strip()
                                                    + (f" ({j['finish']})" if j and j.get("finish") else "")))
    D.note(dp - cz / 2, Z(r1 + 300), "Loft shutter")
    D.note(dp / 2, Z(rail_z), f"{DEF['rail']} oval SS hanging rail")
    D.note(dp * 0.4, Z(r1), f"{cz} BWP ply fixed shelf")
    D.note(dp - cz / 2, Z((H + fcl) / 2), "Top filler to false ceiling" if fcl > H else "Top panel")
    D.note(dp * 0.3, Z(fcl + 6), f"False ceiling +{fcl}")
    D.note(dp - 60 - cz / 2, Z(50), "100 plinth, recessed 60")
    D.callouts(col, wrap=18)
    _ = gapz
    return D, (f"{j['id']} · {j['room']} · {H} high, ceiling +{fcl}" if j else "default")


# ------------------------------------------------------------------ sheets
def _sheet(m, no, total, sheet_id, items, weights=(1, 1, 1)):
    sh = Sheet()
    fr = Frame(sh, m, f"Details {sheet_id}", " · ".join(f"{n} {t}" for n, t, _, _ in items), no, total, None)
    x0, y0, x1, y1 = T.DRAW
    used = []
    bx = x0
    for k, (n, ttl, fn, sc) in enumerate(items):
        w = (x1 - x0) * weights[k] / sum(weights)
        box = (bx, y0 + 4, bx + w - 3, y1 - 22)
        if k:
            sh.line([(bx - 1.5, y0 + 6), (bx - 1.5, y1 - 4)], T.HAIR, LW_HAIR)
        if fn is None:                               # cove: reuse the 1:5 cove detail
            _cove_detail(sh, m, bx, (y0 + y1) / 2 - 52, bx + w - 4, (y0 + y1) / 2 + 52)
            src = "LD ceiling, first cove step"
            for mm in ("concrete", "gypsum", "aluminium", "steel"):
                if mm not in used:
                    used.append(mm)
        else:
            D, src = fn(sh, m, box, sc)
            used += [u for u in D.used if u not in used]
        title(sh, bx, y1 - 12, n, sheet_id, ttl, sc, src)
        bx += w
    material_key(fr, sh, used)
    fr.head("Notes")
    fr.lines([("1", "All dimensions in mm. Do not scale.", None),
              ("2", "Bubble numbers match the elevations: 1–3 on DT-01, 4–6 on DT-02.", None),
              ("3", "Sizes from the data are noted under each title; others are Atelier defaults "
                    "(STANDARDS D5a.5) to confirm with the joiner and site.", None)])
    return sh


def dt01(m, no, total):
    return _sheet(m, no, total, "DT-01", [(1, "Cove", None, 5), (2, "Wall panel with LED reveal", d2_panel, 5),
                                          (3, "Skirting", d3_skirting, 5)])


def dt02(m, no, total):
    return _sheet(m, no, total, "DT-02", [(4, "Concealed flush door", d4_door, 5),
                                          (5, "Worktop + gola + base unit", d5_base, 10),
                                          (6, "Wardrobe section", d6_wardrobe, 10)], weights=(0.9, 1.08, 1.02))


SHEET_DEFS = OrderedDict(dt01=(dt01, "Details DT-01", False), dt02=(dt02, "Details DT-02", False))

"""Ceiling plan (reflected) and ceiling sections with a 1:5 cove detail.

Data: design.json ceilings[] and views[] (sections), services.json (fittings).
Rules: agents/STANDARDS.md §3 (C3.n). Cove construction defaults: COVE below.
"""
from __future__ import annotations

import math
from collections import OrderedDict

from shapely.geometry import LineString, Point
from shapely.ops import polylabel, unary_union

from atelier import geom
from atelier import theme as T
from atelier.draw import DASH, LW_CUT, LW_HAIR, LW_LINE, LW_THIN, Sheet, dim_chain, sans, text_width_mm
from atelier.sheets import Frame, _plan_setup, envelope_bounds, fit_scale, split_walls
from atelier.sheets_services import draw_track, load_services, sym
from atelier.symbols import level_marker

# STANDARDS C3.10 (Atelier defaults) — the only place these numbers live.
COVE = dict(trough=150, upstand=75, board=12.5, section_cc=450, rod_cc=1200, slab=150,
            led="24 V LED strip, 2700 K", profile="aluminium LED profile with opal diffuser")
DASHDOT = (0, (6.0, 1.2, 0.8, 1.2))


def _ceil_of(m, rid):
    return next((c for c in m.ceilings if c["room"] == rid), None)


def _regions(r, c):
    """[(label, z, polygon)] for band, each step (innermost = core) and domes."""
    rp = geom.room_polygon(r)
    steps = [geom.step_polygon(r, s) for s in c.get("steps", [])]
    out = [("band", c["z"], rp.difference(unary_union(steps)) if steps else rp)]
    for i, (s, sp) in enumerate(zip(c.get("steps", []), steps)):
        inner = unary_union(steps[i + 1:]) if i + 1 < len(steps) else None
        reg = sp.difference(inner) if inner is not None and not inner.is_empty else sp
        name = "core" if i == len(steps) - 1 else "step"
        out.append((name, s["z"], reg))
    return out


def _biggest(g):
    return max(getattr(g, "geoms", [g]), key=lambda p: p.area)


# =================================================================== ceiling plan
def _tag(sh, x, y, text, z=12):
    w = text_width_mm(text, T.SIZES["dim"], 0.6) + 2.2
    h = 3.0
    sh.region([([(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)], [])],
              fill=T.PAPER, edge=T.INK, lw=LW_HAIR, z=z)
    sh.text(x, y + 0.05, text, sans("dim", 600), T.INK, ha="center", va="center", zorder=z + 1)


def _section_mark(sh, pv, v):
    (x0, y0), (x1, y1) = v["line"]
    p0, p1 = pv.P(x0, y0), pv.P(x1, y1)
    sh.line([p0, p1], T.INK, LW_HAIR, DASHDOT, z=13)
    lx, ly = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[v["look"]]     # page vector of the look
    for p in (p0, p1):
        r = 3.0
        sh.circle(p[0], p[1], r, edge=T.INK, fill=T.PAPER, lw=LW_THIN)
        sh.ax.patches[-1].set_zorder(14)
        sh.text(p[0], p[1] + 0.1, v["id"], sans("legend_head", 700), T.INK, ha="center", va="center", zorder=15)
        tip = (p[0] + lx * (r + 2.6), p[1] + ly * (r + 2.6))
        b1 = (p[0] + lx * r - ly * 1.7, p[1] + ly * r + lx * 1.7)
        b2 = (p[0] + lx * r + ly * 1.7, p[1] + ly * r - lx * 1.7)
        sh.region([([tip, b1, b2], [])], fill=T.INK, edge=T.INK, lw=LW_HAIR, z=14)


def _leaders(sh, pv, notes):
    """Notes in the margins beside the plan, leader to each target (C3.5)."""
    bx0, by0, bx1, by1 = pv.bounds
    left_x = pv.P(bx0, 0)[0] - 8
    right_x = pv.P(bx1, 0)[0] + 8
    midx = (bx0 + bx1) / 2
    sides = {"L": [], "R": []}
    for text, target in notes:
        sides["L" if target[0] < midx else "R"].append((text, target))
    for side, items in sides.items():
        items.sort(key=lambda t: -t[1][1])           # top of plan first
        used_y = []
        for text, target in items:
            tx, ty = pv.P(*target)
            y = ty
            while any(abs(y - u) < 4.2 for u in used_y):
                y += 4.2
            used_y.append(y)
            x = left_x if side == "L" else right_x
            ha = "right" if side == "L" else "left"
            elbow = (x + (3 if side == "L" else -3), y)
            sh.line([(tx, ty), elbow, (x, y)], T.INK, LW_HAIR, z=12)
            sh.circle(tx, ty, 0.45, edge=T.INK, fill=T.INK, lw=LW_HAIR)
            sh.ax.patches[-1].set_zorder(12)
            sh.caps(x + (-1 if side == "L" else 1), y + 0.9, text, T.INK, role="caps_label", weight=600, ha=ha,
                    zorder=12)


def _chain_across(pv, poly, edges_geom, y=None, x=None):
    """Chain on a horizontal (y given) or vertical (x given) line through `poly`:
    room faces + every crossing of `edges_geom`."""
    b = poly.bounds
    ln = LineString([(b[0] - 10, y), (b[2] + 10, y)]) if y is not None else LineString([(x, b[1] - 10), (x, b[3] + 10)])
    seg = ln.intersection(poly)
    parts = [g for g in getattr(seg, "geoms", [seg]) if g.geom_type == "LineString" and g.length > 0]
    if not parts:
        return
    probe = Point(x if x is not None else (b[0] + b[2]) / 2, y if y is not None else (b[1] + b[3]) / 2)
    part = min(parts, key=lambda g: g.distance(probe))
    a, e = part.coords[0], part.coords[-1]
    axis = 0 if y is not None else 1
    if a[axis] > e[axis]:
        a, e = e, a
    cuts = part.intersection(edges_geom) if edges_geom is not None else None
    ts = [0.0, e[axis] - a[axis]]
    for g in getattr(cuts, "geoms", [cuts]) if cuts is not None and not cuts.is_empty else []:
        for c in getattr(g, "coords", []):
            ts.append(c[axis] - a[axis])
    ts = sorted({round(t) for t in ts})
    direction = (1, 0) if axis == 0 else (0, 1)
    normal = (0, 1) if axis == 0 else (-1, 0)
    pv.ray_chain(a, direction, [(t, False) for t in ts], normal=normal)
    return LineString([a, e])


def ceiling_plan(m, no, total):
    sh, fr, pv, scale = _plan_setup(m, "Ceiling plan", "Reflected ceiling plan · levels mm above FFL · 1:{scale}",
                                    no, total)
    sv = load_services(m)
    full, low = split_walls(m.walls)
    ops = lambda ws: [o for o in m.openings if any(w["id"] == o["wall"] for w in ws)]  # noqa: E731
    pv.fill(geom.cut_walls(full, ops(full)), fill=T.POCHE, z=8)
    pv.fill(geom.cut_walls(low, ops(low)), fill=T.LIGHT, edge=T.GREY, lw=LW_HAIR, z=8)
    by_id = {w["id"]: w for w in m.walls}
    for o in m.openings:                                   # RCP: openings as head lines, no swings
        if o["kind"] in ("window", "ventilator"):
            pv.opening(by_id[o["wall"]], o, color=T.GREY)
        else:
            pv.opening(by_id[o["wall"]], dict(o, kind="opening"), arc_color=T.GREY)
    notes = []
    occ = []                                   # plan geometry already used (labels keep clear of it)
    for c in m.ceilings:
        r = m.room(c["room"])
        rp = geom.room_polygon(r)
        # outlines (C3.1)
        for s in c.get("steps", []):
            pv.fill(geom.step_polygon(r, s), fill="none", edge=T.INK, lw=LW_THIN, z=5)
        for d in c.get("domes", []):
            dp = geom.dome_polygon(d)
            pv.fill(dp, fill="none", edge=T.INK, lw=LW_THIN, z=5)
            pv.fill(Point(d["at"]).buffer(d["d"] / 2 - 25, 48), fill="none", edge=T.INK, lw=LW_HAIR, z=5)
        # level tags (C3.2)
        for name, z, reg in _regions(r, c):
            reg = _biggest(reg) if not reg.is_empty else None
            if reg is None or reg.area < 1e4:
                continue
            p = polylabel(reg, tolerance=10)
            if name != "band" and reg.buffer(-300).is_empty is False:
                p = polylabel(reg, tolerance=10)
            text = f"core +{z}" if name == "core" else f"+{z}"
            if name == "band":                       # put band tags near a corner of the band, clear of chains
                pts = [Point(rp.exterior.coords[i]) for i in range(len(rp.exterior.coords) - 1)]
                sw = min(pts, key=lambda q: (q.x + q.y))
                p = Point(sw.x + 380, sw.y + 230)
                if not reg.contains(p):
                    p = polylabel(reg, tolerance=10)
            x, y = pv.P(p.x, p.y)
            _tag(sh, x, y, text)
            occ.append(Point(p.x, p.y).buffer(pv.s * 5))
        for d in c.get("domes", []):
            x, y = pv.P(*d["at"])
            r_page = pv.L(d["d"] / 2)
            sh.text(x, y - r_page + 2.4, f"Ø{d['d']}", sans("dim", 600), T.INK, ha="center", zorder=12,
                    path_effects=sh.halo(1.8))
            _tag(sh, x, y + 4.2, f"dome +{d['z']}")
            occ.append(geom.dome_polygon(d))
        # chains (C3.3)
        steps = [geom.step_polygon(r, s) for s in c.get("steps", [])]
        if steps:
            edges = unary_union([sp.boundary for sp in steps])
            core = steps[-1]
            cb = core.bounds
            cy = cb[1] + (cb[3] - cb[1]) * 0.78
            cx = cb[0] + (cb[2] - cb[0]) * 0.12
            occ += [_chain_across(pv, rp, edges, y=cy), _chain_across(pv, rp, edges, x=cx)]
    # fittings (C3.6) from services.json
    for it in sv:
        k = it["kind"]
        if it["system"] == "lighting":
            if k == "cove":
                sh.line([pv.P(*p) for p in it["path"]], T.AMBER, LW_LINE, DASH, z=9)
                path = it["path"]
                seg = max(zip(path, path[1:]), key=lambda ab: math.dist(*ab))
                notes.append(("Provision for cove light", ((seg[0][0] + seg[1][0]) / 2, (seg[0][1] + seg[1][1]) / 2)))
            elif k == "fan":
                x, y = pv.P(*it["at"])
                R = pv.L(it.get("size", [1200])[0] / 2)
                sh.circle(x, y, R, edge=T.AMBER, lw=LW_THIN)
                sh.ax.patches[-1].set_linestyle(DASH)
                for a in (90, 210, 330):
                    ra = math.radians(a)
                    sh.line([(x + math.cos(ra) * 1.2, y - math.sin(ra) * 1.2),
                             (x + math.cos(ra) * (R - 0.8), y - math.sin(ra) * (R - 0.8))], T.AMBER, LW_LINE, z=9)
                sym(sh, "fan_hub", x, y, c=T.AMBER)
                sh.text(x + R * 0.72, y + R * 0.72, "fan 1200", sans("dim", 500), T.AMBER, zorder=11,
                        path_effects=sh.halo(1.6))
            elif k in ("track", "strip"):
                draw_track(sh, [pv.P(*p) for p in it["path"]], T.AMBER)
                a_, b_ = it["path"][0], it["path"][-1]
                notes.append(("Magnetic track", ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)))
            else:
                x, y = pv.P(*it["at"])
                sym(sh, k, x, y, c=T.AMBER)
        elif it["system"] == "ac":
            if k == "supply_grille":
                (a_, b_) = it["path"]
                pa, pb = pv.P(*a_), pv.P(*b_)
                L = math.dist(pa, pb) or 1
                nx, ny = -(pb[1] - pa[1]) / L * 0.6, (pb[0] - pa[0]) / L * 0.6
                for s_ in (-1, 1):
                    sh.line([(pa[0] + nx * s_, pa[1] + ny * s_), (pb[0] + nx * s_, pb[1] + ny * s_)], T.BLUE, LW_LINE, z=9)
                notes.append(("Linear slot diffuser", ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)))
            elif k == "return_grille":
                x, y = pv.P(*it["at"])
                sym(sh, "return_grille", x, y, c=T.BLUE)
    # downlight spacing chains (C3.4)
    for r in m.rooms:
        dls = [i for i in sv if i["kind"] == "downlight" and i["room"] == r["id"]]
        if len(dls) < 2:
            continue
        rp = geom.room_polygon(r)
        xs = sorted({i["at"][0] for i in dls})
        ys = sorted({i["at"][1] for i in dls})
        row_y = min(i["at"][1] for i in dls)
        col_x = min(i["at"][0] for i in dls)
        if len(xs) > 1:
            occ.append(_chain_across(pv, rp, unary_union([LineString([(x_, row_y - 5), (x_, row_y + 5)])
                                                          for x_ in xs]), y=row_y))
        if len(ys) > 1:
            occ.append(_chain_across(pv, rp, unary_union([LineString([(col_x - 5, y_), (col_x + 5, y_)])
                                                          for y_ in ys]), x=col_x))
    for v in m.views:
        if v.get("kind") == "section":
            _section_mark(sh, pv, v)
    # room names (+ the gypsum note when it fits inside), placed last, clear of everything above
    for it in sv:
        if it["system"] in ("lighting", "ac"):
            if it.get("path"):
                occ.append(LineString(it["path"]) if len(it["path"]) > 1 else Point(it["at"]))
            elif it["kind"] == "fan":                # sweep + its "fan 1200" label
                occ.append(Point(it["at"]).buffer(it.get("size", [1200])[0] / 2 + pv.s * 5))
            else:
                occ.append(Point(it["at"]).buffer(pv.s * 2.2))
    occ_u = unary_union([g.buffer(pv.s * 1.2) for g in occ if g is not None])
    for r in m.rooms:
        c = _ceil_of(m, r["id"])
        rp = geom.room_polygon(r)
        b = rp.bounds
        note = "Gypsum false ceiling" if c and c.get("z") else "No false ceiling"
        note_w = text_width_mm(note.upper(), T.SIZES["caps_label"], 0.8)
        inside = note_w + 3 < (b[2] - b[0]) / scale
        lines = [r.get("name", r["id"])] + ([note] if inside else [])
        w = max(text_width_mm(t.upper(), T.SIZES["caps_label"], 0.8) for t in lines) + 2
        px, py = pv.label_spot(r, occ_u, 1 if inside else 0, width_mm=w)
        x, y = pv.P(px, py)
        sh.caps(x, y - 0.6, r.get("name", r["id"]), T.GREY, role="caps_label", weight=600, ha="center", zorder=11,
                path_effects=sh.halo(2.0))
        if inside:
            sh.caps(x, y + 2.8, note, T.INK, role="caps_label", weight=600, ha="center", zorder=11,
                    path_effects=sh.halo(2.0))
        elif c and c.get("z"):
            band = _biggest(_regions(r, c)[0][2])
            notes.append(("Gypsum false ceiling", polylabel(band, tolerance=10).coords[0]))
    _leaders(sh, pv, notes)
    soff = m.levels.get("soffit")
    sflag = m.is_flagged(dict(m.levels), "soffit")
    fr.legend([
        ("Tray / step outline", lambda x, y, w, h: sh.swatch(x, y, w, h, edge=T.INK, lw=LW_THIN)),
        ("Level tag, mm above FFL", lambda x, y, w, h: _tag(sh, x + 3.6, y + h / 2, "+2550")),
        ("Cove light", lambda x, y, w, h: sh.line([(x, y + h / 2), (x + w, y + h / 2)], T.AMBER, LW_LINE, DASH)),
        ("Downlight", lambda x, y, w, h: sym(sh, "downlight", x + 3.5, y + h / 2, c=T.AMBER)),
        ("Pendant", lambda x, y, w, h: sym(sh, "pendant", x + 3.5, y + h / 2, c=T.AMBER)),
        ("Magnetic track", lambda x, y, w, h: draw_track(sh, [(x, y + h / 2), (x + w, y + h / 2)], T.AMBER)),
        ("Fan, true 1200 sweep", lambda x, y, w, h: (sh.circle(x + 3.5, y + h / 2, 2.2, edge=T.AMBER, lw=LW_HAIR),
                                                     sym(sh, "fan_hub", x + 3.5, y + h / 2, c=T.AMBER))),
        ("Linear slot diffuser / return", lambda x, y, w, h: sh.line([(x, y + h / 2), (x + w, y + h / 2)], T.BLUE,
                                                                     LW_LINE)),
        ("Section mark", lambda x, y, w, h: (sh.circle(x + 2.2, y + h / 2, 1.9, edge=T.INK, fill=T.PAPER),
                                             sh.text(x + 2.2, y + h / 2 + 0.1, "A", sans("dim", 700), T.INK,
                                                     ha="center", va="center"))),
    ])
    fr.head("Notes")
    fr.lines([("1", "Levels are mm above FFL to the underside of the finished ceiling.", None),
              ("2", "Slab soffit +" + str(soff) + ("*" if sflag else "") + ": verify on site before setting levels.",
               T.FLAG if sflag else None),
              ("3", "Cove trough, board and framing: see the 1:5 detail on the sections sheet.", None),
              ("4", "Downlights by rule R6.12; fittings and switching from services.json.", None)])
    return sh


# =================================================================== sections
def _section_profile(m, v, step=10):
    """Along the cut: rooms, walls, ceiling z(s). Returns dict with s-range and samples."""
    (x0, y0), (x1, y1) = v["line"]
    L = math.dist((x0, y0), (x1, y1))
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    line = LineString([(x0, y0), (x1, y1)])
    walls = []
    for w in m.walls:
        cut = line.intersection(geom.wall_polygon(w))
        for g in getattr(cut, "geoms", [cut]):
            if g.is_empty or g.geom_type != "LineString" or g.length < 1:
                continue
            s0 = min(math.dist((x0, y0), c) for c in g.coords)
            s1 = max(math.dist((x0, y0), c) for c in g.coords)
            ops = []
            for o in m.openings_on(w["id"]):
                if geom.opening_polygon(w, o, 0).buffer(1).intersects(g):
                    ops.append(o)
            walls.append((s0, s1, w, ops))
    walls.sort(key=lambda t: t[0])
    rooms = []
    for r in m.rooms:
        cut = line.intersection(geom.room_polygon(r))
        for g in getattr(cut, "geoms", [cut]):
            if g.is_empty or g.geom_type != "LineString" or g.length < 1:
                continue
            s0 = min(math.dist((x0, y0), c) for c in g.coords)
            s1 = max(math.dist((x0, y0), c) for c in g.coords)
            rooms.append((s0, s1, r))
    rooms.sort(key=lambda t: t[0])
    soffit = m.levels.get("soffit", 3000)
    prof = []
    for s0, s1, r in rooms:
        c = _ceil_of(m, r["id"])
        pts = []
        s = s0
        while s <= s1 + 0.1:
            p = (x0 + ux * s, y0 + uy * s)
            z = geom.ceiling_z_at(r, c, p) if c else soffit
            pts.append((s, z))
            s += step
        prof.append((r, c, pts))
    s_min = walls[0][0] if walls else 0
    s_max = walls[-1][1] if walls else L
    return dict(start=(x0, y0), u=(ux, uy), walls=walls, rooms=rooms, prof=prof, s_min=s_min, s_max=s_max,
                soffit=soffit)


def _draw_section(sh, m, v, scale, ox, base):
    """Draw one section with FFL at page y `base`; s_min at page x `ox`."""
    S = _section_profile(m, v)
    soffit = S["soffit"]
    sflag = m.is_flagged(dict(m.levels), "soffit")
    slab = COVE["slab"]
    X = lambda s: ox + (s - S["s_min"]) / scale   # noqa: E731
    Z = lambda z: base - z / scale                # noqa: E731
    xa, xb = X(S["s_min"]), X(S["s_max"])
    # slabs (hatched), floor line
    for z0, z1 in ((soffit, soffit + slab), (-slab, 0)):
        sh.region([([(xa, Z(z0)), (xb, Z(z0)), (xb, Z(z1)), (xa, Z(z1))], [])], fill=T.PAPER, edge=T.INK,
                  lw=LW_THIN, hatch="////", z=3)
    for s0, s1, r in S["rooms"]:
        f = r.get("ffl", 0)
        sh.line([(X(s0), Z(f)), (X(s1), Z(f))], T.INK, LW_LINE, z=5)
    # walls cut (with openings)
    for s0, s1, w, ops in S["walls"]:
        top = soffit
        holes = []
        for o in ops:
            lo_, hi_ = (o.get("sill", 0), o.get("head", 2100))
            if o["kind"] in ("door", "double_door", "sliding_door", "opening"):
                lo_ = 0
            holes.append((lo_, hi_))
        if w.get("kind") == "parapet":
            top = w.get("height", 1050)
        spans = [(0, top)]
        for lo_, hi_ in holes:
            nxt = []
            for a, b in spans:
                if hi_ <= a or lo_ >= b:
                    nxt.append((a, b))
                else:
                    if a < lo_:
                        nxt.append((a, lo_))
                    if hi_ < b:
                        nxt.append((hi_, b))
            spans = nxt
        for a, b in spans:
            sh.region([([(X(s0), Z(a)), (X(s1), Z(a)), (X(s1), Z(b)), (X(s0), Z(b))], [])], fill=T.POCHE, z=6)
        for lo_, hi_ in holes:                       # glass line in windows
            if lo_ > 0:
                xm = (X(s0) + X(s1)) / 2
                sh.line([(xm, Z(lo_)), (xm, Z(hi_))], T.INK, LW_HAIR, z=6)
    # false ceiling profile, cove lips, labels
    levels = {0: False, soffit: sflag}
    edges_s = []
    for r, c, pts in S["prof"]:
        if not c:
            continue
        sh.line([(X(s), Z(z)) for s, z in pts], T.INK, LW_CUT, z=7)
        for (sa, za), (sb, zb) in zip(pts, pts[1:]):
            if abs(zb - za) > 20 and abs(round(zb) - round(za)) in {abs(st["z"] - other) for st in c.get("steps", [])
                                                                     for other in [c["z"]] + [x["z"] for x in c["steps"]]}:
                edges_s.append((sb if zb > za else sa))
                hi_side = 1 if zb > za else -1
                lo_z = min(za, zb)
                u = min(COVE["upstand"], abs(zb - za) / 2)
                xl = X(sb if zb > za else sa) + hi_side * COVE["trough"] / scale
                sh.line([(xl, Z(lo_z)), (xl, Z(lo_z + u))], T.INK, LW_THIN, z=7)
                sh.circle(xl - hi_side * 0.9, Z(lo_z + 12), 0.45, edge=T.AMBER, fill=T.AMBER, lw=LW_HAIR)
        for _, z in pts:
            zr = round(z)
            if any(abs(zr - st["z"]) < 2 for st in c.get("steps", [])) or abs(zr - c["z"]) < 2:
                levels[zr] = False
        for d in c.get("domes", []):
            line = LineString([S["start"], (S["start"][0] + S["u"][0] * 1e5, S["start"][1] + S["u"][1] * 1e5)])
            if line.distance(Point(d["at"])) < 10:
                levels[d["z"]] = False
                # pendant from dome centre
                for lt in c.get("lights", []):
                    if lt.get("kind") == "pendant" and math.dist(lt["at"], d["at"]) < 10:
                        sd = (d["at"][0] - S["start"][0]) * S["u"][0] + (d["at"][1] - S["start"][1]) * S["u"][1]
                        sh.line([(X(sd), Z(d["z"])), (X(sd), Z(d["z"] - 900))], T.AMBER, LW_THIN, z=8)
                        sh.circle(X(sd), Z(d["z"] - 900) + 1.0, 1.4, edge=T.AMBER, fill=T.PAPER, lw=LW_THIN)
    for s0, s1, r in S["rooms"]:
        sh.caps((X(s0) + X(s1)) / 2, Z(1200), r.get("name", r["id"]), T.GREY, role="caps_label", weight=600,
                ha="center", zorder=9)
    # every level: chain at the left, tags at the right (C3.8)
    zs = sorted(levels)
    pts = [(z, levels[z]) for z in zs]
    coords = [-(z / scale) for z in zs]
    dim_chain(sh, (xa - 10, base), (0, -1), (-1, 0), [z / scale for z in zs],
              [zs[i + 1] - zs[i] for i in range(len(zs) - 1)], [pts[i + 1][1] or pts[i][1] for i in range(len(zs) - 1)],
              ext_from=[8.5] * len(zs))
    _ = coords
    _level_tags(sh, xb + 3, [(Z(z), "FFL ±0" if z == 0 else (f"soffit +{z}" if z == soffit else f"+{z}"),
                              levels[z]) for z in zs])
    # horizontal chain: wall faces and step edges along the cut
    hs = sorted({round(t) for s0, s1, _w, _o in S["walls"] for t in (s0, s1)} | {round(e) for e in edges_s})
    dim_chain(sh, (X(0) if False else xa - (S["s_min"] - S["s_min"]) / scale, base + 7), (1, 0), (0, 1),
              [(h - S["s_min"]) / scale for h in hs], [hs[i + 1] - hs[i] for i in range(len(hs) - 1)],
              [False] * (len(hs) - 1), ext_from=[7 + 0] * len(hs))
    return xa, xb, Z(soffit + slab)


def _spread(ys, gap):
    """Push label y positions apart by at least `gap`, keeping their order and mean."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for _ in range(50):
        moved = False
        for a_, b_ in zip(order, order[1:]):
            if out[b_] - out[a_] < gap:
                d = (gap - (out[b_] - out[a_])) / 2
                out[a_] -= d
                out[b_] += d
                moved = True
        if not moved:
            break
    return out


def _level_tags(sh, x, items):
    """items: [(page_y, text, flagged)]: triangle at the true level, text spread apart with a leader."""
    ys = _spread([y for y, _, _ in items], 2.6)
    for (y, text, fl), ty in zip(items, ys):
        s_ = 1.1
        sh.region([([(x - s_, y - s_), (x + s_, y - s_), (x, y)], [])], fill=T.PAPER, edge=T.INK, lw=LW_HAIR, z=8)
        sh.line([(x + s_ + 0.3, y - 0.4), (x + 3.2, ty), (x + 4.0, ty)], T.GREY, LW_HAIR, z=8)
        sh.text(x + 4.4, ty, text + ("*" if fl else ""), sans("dim", 500 if fl else 400), T.FLAG if fl else T.INK,
                va="center", zorder=9)


def _wrap(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur]


def _cove_detail(sh, m, x0, y0, x1, y1):
    """1:5 cove detail (C3.9) in the page box (x0, y0)-(x1, y1), from the first cove step in the data."""
    c = next((c for c in m.ceilings for s_ in c.get("steps", []) if s_.get("light") == "cove"), None)
    if not c:
        return
    st = next(s_ for s_ in c["steps"] if s_.get("light") == "cove")
    z1, z2 = c["z"], st["z"]
    soffit = m.levels.get("soffit", 3000)
    sflag = m.is_flagged(dict(m.levels), "soffit")
    sc = 5.0
    tr, bd, sl = COVE["trough"], COVE["board"], COVE["slab"]
    u = min(COVE["upstand"], (z2 - z1) / 2)
    left, right = -110, 210                               # real mm either side of the step edge
    lo, hi_cut = z1 - 50, z2 + 130                        # lower part drawn to scale
    s_lo, s_hi = soffit - 25, soffit + 45                 # sliver of slab above the break
    gap = 6.0
    xe = x0 + 14 - left / sc                              # page x of the step edge
    y_base = y1 - 9

    def Y(z):
        if z <= hi_cut + 1:
            return y_base - (z - lo) / sc
        return y_base - (hi_cut - lo) / sc - gap - (z - s_lo) / sc

    def X(x):
        return xe + x / sc

    def rect(xa_, xb_, za_, zb_, f=T.PAPER, e=T.INK, h=None, lw=LW_THIN):
        sh.region([([(X(xa_), Y(za_)), (X(xb_), Y(za_)), (X(xb_), Y(zb_)), (X(xa_), Y(zb_))], [])], fill=f, edge=e,
                  lw=lw, hatch=h, z=6)

    rect(left, tr, z1, z1 + bd, f=T.LIGHT)                         # band board + trough floor
    rect(tr - bd, tr, z1 + bd, z1 + u, f=T.LIGHT)                  # upstand lip
    rect(-bd, 0, z1 + bd, z2 + bd, f=T.LIGHT)                      # riser
    rect(0, right, z2, z2 + bd, f=T.LIGHT)                         # raised board
    rect(left, right, soffit, s_hi, h="////")                      # RCC slab (sliver)
    for xc, zc in ((-70, z1 + bd), (150, z2 + bd)):                # GI section + rod + cleat
        rect(xc - 22, xc + 22, zc, zc + 18, f=T.PAPER, lw=LW_HAIR)
        rect(xc - 5, xc + 5, zc + 18, zc + 40, f=T.MID, lw=LW_HAIR)
        sh.line([(X(xc), Y(zc + 40)), (X(xc), Y(hi_cut))], T.INK, LW_THIN, z=7)
        sh.line([(X(xc), Y(s_lo)), (X(xc), Y(soffit))], T.INK, LW_THIN, z=7)
        rect(xc - 14, xc + 14, soffit - 10, soffit, f=T.INK, lw=LW_HAIR)
    rect(18, 36, z1 + bd, z1 + bd + 14, f=T.MID, lw=LW_HAIR)       # LED profile
    sh.line([(X(16), Y(z1 + bd + 15)), (X(38), Y(z1 + bd + 15))], T.AMBER, LW_LINE, z=8)
    for k in range(5):
        a_ = math.radians(50 + k * 8)
        sx, sy = X(27), Y(z1 + bd + 16)
        sh.line([(sx, sy), (sx + math.cos(a_) * 7, sy - math.sin(a_) * 7)], T.AMBER, LW_HAIR, (0, (1, 1)), z=5)
    yb = Y(hi_cut) - gap / 2                                       # break line
    zz = [(X(left) - 1.5, yb)] + [(X(left) + (X(right) - X(left)) * i / 8, yb + (1.0 if i % 2 else -1.0))
                                  for i in range(1, 8)] + [(X(right) + 1.5, yb)]
    sh.line(zz, T.GREY, LW_HAIR, z=8)
    # dimensions
    dim_chain(sh, (X(0), Y(z1) + 4.5), (1, 0), (0, 1), [0, tr / sc], [tr], [False], ext_from=[4.5, 4.5])
    dim_chain(sh, (X(left) - 4, Y(z1)), (0, -1), (-1, 0), [0, u / sc, (z2 - z1) / sc],
              [round(u), round(z2 - z1 - u)], [False, False], ext_from=[3, 3, 3])
    # levels and callouts in one column to the right, each level with its target
    callouts = [
        (s_hi - 10, 120, f"RCC slab {sl}, assumed"),
        (soffit, 60, f"Soffit +{soffit}" + ("*" if sflag else "")),
        (soffit - 18, 150, f"Rod + anchor fastener @ {COVE['rod_cc']}"),
        (z2 + bd + 9, 172, f"GI ceiling section @ {COVE['section_cc']} c/c"),
        (z2 + bd / 2, 200, f"{COVE['board']} gypsum board"),
        (z1 + u - 8, tr - 6, f"Upstand lip {round(u)}"),
        (z1 + bd + 7, 36, COVE["profile"].capitalize()),
        (z1 + bd + 15, 22, COVE["led"]),
        (z2, 190, f"Step +{z2}"),
        (z1, -90, f"Band +{z1}"),
    ]
    tx = X(right) + 5
    wrapped = [_wrap(t.upper(), 19) for _, _, t in callouts]
    order = sorted(range(len(callouts)), key=lambda i: Y(callouts[i][0]))
    ys, nxt = [0.0] * len(callouts), -1e9
    for i in order:                                   # top-down, each below the one above it
        ys[i] = max(Y(callouts[i][0]) - 0.9, nxt)
        nxt = ys[i] + len(wrapped[i]) * 2.3 + 1.3
    for (z, x, text), ty, lines in zip(callouts, ys, wrapped):
        px, py = X(x), Y(z)
        flag = text.endswith("*")
        sh.line([(px, py), (tx - 2.0, ty), (tx - 0.6, ty)], T.INK, LW_HAIR, z=9)
        sh.circle(px, py, 0.32, edge=T.INK, fill=T.INK, lw=LW_HAIR)
        for k, ln in enumerate(lines):
            sh.text(tx, ty + 0.9 + k * 2.3, ln, sans("dim", 600 if flag else 500), T.FLAG if flag else T.INK,
                    va="center", zorder=9)


def sections(m, no, total):
    sh = Sheet()
    scale = fit_scale(envelope_bounds(m.walls))
    fr = Frame(sh, m, "Ceiling sections", f"Sections at 1:{scale} · cove detail at 1:5", no, total, scale)
    secs = [v for v in m.views if v.get("kind") == "section"]
    secs.sort(key=lambda v: -math.dist(*v["line"]))             # longest first (top)
    x0, y0, x1, y1 = T.DRAW
    soffit = m.levels.get("soffit", 3000)
    h = (soffit + COVE["slab"]) / scale
    bases = [y0 + 14 + h, y0 + 14 + h + 22 + h + 6]
    right_of_a = x0 + 140
    for i, v in enumerate(secs[:2]):
        base = bases[i]
        xa, xb, ytop = _draw_section(sh, m, v, scale, x0 + 30, base)
        if i == 1:
            right_of_a = xb + 20
        sh.caps(xa, base + 17, f"Section {v['id']}–{v['id']}  ·  1:{scale}  ·  looking {v['look']}", T.INK,
                role="legend_head", weight=600)
    dx0 = right_of_a + 8
    _cove_detail(sh, m, dx0, bases[0] + 34, x1, y1 - 6)
    sh.caps(dx0, y1 - 1, "Cove detail  ·  1:5", T.INK, role="legend_head", weight=600)
    soff = m.levels.get("soffit")
    sflag = m.is_flagged(dict(m.levels), "soffit")
    fr.legend([
        ("Wall, cut", lambda x, y, w, hh: sh.swatch(x, y, w, hh, fill=T.POCHE)),
        ("RCC slab", lambda x, y, w, hh: sh.swatch(x, y, w, hh, fill=T.PAPER, edge=T.INK, hatch="////")),
        ("False ceiling profile", lambda x, y, w, hh: sh.line([(x, y + hh / 2), (x + w, y + hh / 2)], T.INK, LW_CUT)),
        ("Cove lip / LED", lambda x, y, w, hh: (sh.line([(x + 3, y), (x + 3, y + hh)], T.INK, LW_THIN),
                                               sh.circle(x + 5, y + hh - 0.6, 0.45, edge=T.AMBER, fill=T.AMBER))),
        ("Level, mm above FFL", lambda x, y, w, hh: level_marker(sh, x + 1.5, y + hh / 2, "")),
    ])
    fr.head("Construction notes")
    fr.lines([
        ("1", f"False ceiling: {COVE['board']} gypsum board on GI ceiling sections @ {COVE['section_cc']} c/c, "
              f"suspended on rods @ {COVE['rod_cc']} c/c with anchor fasteners into the slab.", None),
        ("2", f"Cove: {COVE['trough']} trough on the raised side of each step, upstand lip, "
              f"{COVE['profile']}; {COVE['led']}. Driver accessible.", None),
        ("3", "Levels are mm above FFL to the underside of the finished ceiling; wet rooms have their own FFL.",
         None),
        ("4", f"Slab soffit +{soff}{'*' if sflag else ''} and slab {COVE['slab']} assumed: verify before fixing.",
         T.FLAG if sflag else None),
        ("5", "Access panel 600 × 600 below each ducted AC unit; coordinate diffusers and fittings with the "
              "ceiling plan.", None),
        ("6", "Joints taped, jointed and finished to a smooth paint-ready surface.", None),
    ], max_chars=56)
    return sh


SHEET_DEFS = OrderedDict(
    ceiling=(ceiling_plan, "Ceiling plan", True),
    sections=(sections, "Ceiling sections", True),
)
_ = (Point, polylabel)

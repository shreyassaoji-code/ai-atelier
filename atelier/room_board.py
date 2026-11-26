"""Room boards: one per bedroom, living room and kitchen (agents/STANDARDS.md §2a).

project.json lists them as "room:<room id>". A board has:
  - the room plan, cropped to the room (clipped to its polygon plus its own walls: nothing
    from neighbours), 1:40-1:75, with dimension chains, elevation markers and camera marks;
  - its two key elevations at 1:50 (atelier/views3d.key_walls) with CAPS call-outs and
    level markers;
  - three round 3D vignettes rendered from the data (atelier/render.py);
  - palette circles with finish codes; a legend with room data and furniture.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from PIL import Image
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from atelier import geom
from atelier import texture as TX
from atelier import theme as T
from atelier import views3d as V3
from atelier.draw import (DASH, LW_CUT, LW_HAIR, LW_LINE, LW_THIN, PlanView, Sheet, dim_chain, sans,
                          text_width_mm, tracked)
from atelier.elev_detail import D as ED, Face, _metres, _module, _mixer, _spread, _tile_size
from atelier.sheets import (RASTER_DPI, Frame, base_plan, floor_voids, split_walls, thresholds)
from atelier.sheets_ceiling import _wrap
from atelier.symbols import (_to_plan, draw_furniture, draw_joinery, draw_sanitary, furniture_footprint_page,
                             furniture_parts)

PLAN_SCALES = (40, 50, 60, 75)            # §2a: room plan 1:40 - 1:75
ES = 50                                    # §2a: key elevations 1:50
CALLOUT_W = 40                             # page mm left of an elevation for its call-outs
MARK_W = 25                                # page mm right of an elevation for its level markers
CH = (7.5, 13.5)                           # plan chain offsets (tier 1, tier 2) from the crop
TXT = 2.6                                  # dimension text height beyond its line
E_TITLE, E_FLOOR, E_CHAIN = 5.0, 50, 4.5   # elevation title band, floor band (mm real), chain below the floor
LETTERS = "ABC"


# ------------------------------------------------------------------ helpers
class Cv:
    """Elevation canvas at 1:ES (duck-types elev_detail.Elev for _module / _mixer)."""

    def __init__(self, sh, F, ex0, ey0, s=ES):
        self.sh, self.F, self.ex0, self.ey0, self.s = sh, F, ex0, ey0, s

    def X(self, x):
        return self.ex0 + x / self.s

    def Z(self, z):
        return self.ey0 - z / self.s

    def rect(self, xa, xb, za, zb, fill=None, edge=None, lw=LW_THIN, hatch=None, dash=None, z=4):
        self.sh.region([([(self.X(xa), self.Z(za)), (self.X(xb), self.Z(za)), (self.X(xb), self.Z(zb)),
                          (self.X(xa), self.Z(zb))], [])], fill=fill or "none", edge=edge or "none", lw=lw,
                       hatch=hatch, dash=dash, z=z)

    def line(self, pts, color=None, lw=LW_THIN, dash=None, z=5):
        self.sh.line([(self.X(x), self.Z(zz)) for x, zz in pts], color or T.INK, lw, dash, z=z)


def _artists(ax):
    return set(map(id, list(ax.patches) + list(ax.lines) + list(ax.collections) + list(ax.images) + list(ax.texts)))


def _clip_new(sh, before, rings, keep=()):
    """Clip every artist added since `before` to the page rings (the room crop)."""
    verts, codes = [], []
    for ext, holes in rings:
        for ring in [ext, *holes]:
            verts += list(ring) + [ring[0]]
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(ring) - 1) + [MplPath.CLOSEPOLY]
    patch = PathPatch(MplPath(verts, codes), transform=sh.ax.transData, facecolor="none", edgecolor="none")
    ax = sh.ax
    for a in list(ax.patches) + list(ax.lines) + list(ax.collections) + list(ax.images) + list(ax.texts):
        if id(a) not in before and id(a) not in keep:
            a.set_clip_path(patch)


def crop_region(m, room):
    """The room polygon plus the bodies of its own walls (to their thickness), nothing beyond."""
    rp = geom.room_polygon(room)
    parts = [rp]
    for w in m.walls:
        wp = geom.wall_polygon(w)
        if wp.distance(rp) < 5:
            parts.append(wp.intersection(rp.buffer(w["t"] + 2, join_style=2)))
    return unary_union(parts)


def _edge_cuts(m, e, walls):
    ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
    line = LineString([e.a, e.b])
    out = []
    for wid in walls:
        w = m.wall(wid)
        for o in m.openings_on(wid):
            pa, pb = geom.point_on_wall(w, o["offset"]), geom.point_on_wall(w, o["offset"] + o["width"])
            if line.distance(Point((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)) > w["t"] + 5:
                continue
            for p in (pa, pb):
                t = (p[0] - e.a[0]) * ux + (p[1] - e.a[1]) * uy
                if 0 < t < e.length:
                    out.append((p, m.is_flagged(o, "offset") or m.is_flagged(o, "width")))
    return out


def side_tiers(m, room, side):
    """Chains for one side of a room: tier 1 corners + opening jambs, tier 2 overall."""
    facing = {"S": "N", "N": "S", "W": "E", "E": "W"}[side]
    faces = geom.room_faces(room, m.walls)
    ax = 0 if side in ("S", "N") else 1
    t1 = []
    for e in geom.room_edges(room, m.walls):
        if e.facing != facing:
            continue
        t1 += [(e.a[ax], False), (e.b[ax], False)]
        t1 += [(p[ax], fl) for p, fl in _edge_cuts(m, e, sorted({f.wall for f in faces if f.n == e.n}))]
    b = geom.room_polygon(room).bounds
    lo, hi = (b[0], b[2]) if ax == 0 else (b[1], b[3])
    return sorted(set(t1)), [(lo, False), (hi, False)]


def _plan_size(m, room, s):
    """Exact page size: title band, N chain (1 tier), crop, S chains (2 tiers); W 2 tiers, E 1 tier."""
    b = crop_region(m, room).bounds
    return (CH[1] + TXT) + (b[2] - b[0]) / s + (CH[0] + TXT), \
        E_TITLE + (CH[0] + TXT) + (b[3] - b[1]) / s + (CH[1] + TXT)


def _elev_size(F, s=ES):
    w = CALLOUT_W + (F.t_left + F.L + F.t_right) / s + MARK_W
    h = E_TITLE + (F.soffit + ED["slab"] + E_FLOOR) / s + E_CHAIN + TXT
    return w, h


# ------------------------------------------------------------------ plan
def draw_plan(sh, m, room, scale, x0, y0, faces, cams):
    """Plan of `room` with its top-left at (x0, y0) on the page. Returns the page box used."""
    crop = crop_region(m, room)
    cb = crop.bounds
    w_pg, h_pg = (cb[2] - cb[0]) / scale, (cb[3] - cb[1]) / scale
    cx, cy = x0 + CH[1] + TXT + w_pg / 2, y0 + E_TITLE + CH[0] + TXT + h_pg / 2
    pv = PlanView(sh, cb, scale, centre=(cx, cy))
    sh.caps(x0, y0 + 3.2, f"Plan · 1:{scale}", T.INK, role="legend_head", weight=600)
    fin = {f["code"]: f for f in m.finishes}
    fl = next((x for x in m.floors if x["room"] == room["id"]), None)
    keep = set()
    floor = unary_union([geom.room_polygon(room)] + floor_voids(m).get(room["id"], []))
    if fl:
        poly = floor.buffer(30, join_style=2)
        b = poly.bounds
        arr = TX.floor_texture(fin[fl["finish"]], fl, b, RASTER_DPI / 25.4 / scale, seed=3)
        (px0, py1), (px1, py0) = pv.P(b[0], b[1]), pv.P(b[2], b[3])
        keep.add(id(sh.image(arr, px0, py0, px1, py1, clip_rings=pv.rings(floor), z=1)))
    mine = lambda xs: [x for x in xs if x.get("room") == room["id"]]  # noqa: E731
    casters = [furniture_footprint_page(pv, f) for f in mine(m.furniture) + mine(m.sanitary) if f.get("kind") != "rug"]
    for j in mine(m.joinery):
        g = geom.joinery_polygon(j, m.wall(j["wall"]), room)
        casters.append([pv.P(*c) for c in g.exterior.coords[:-1]])
    keep.add(id(sh.image(TX.soft_shadow(casters, T.PAGE_W, T.PAGE_H), 0, 0, T.PAGE_W, T.PAGE_H,
                         clip_rings=pv.rings(floor), z=2)))
    before = _artists(sh.ax) - keep
    for f in sorted(mine(m.furniture), key=lambda f: f.get("kind") != "rug"):
        draw_furniture(pv, f, "present")
    for j in mine(m.joinery):
        draw_joinery(pv, j, m.wall(j["wall"]), room, "present")
    for s_ in mine(m.sanitary):
        draw_sanitary(pv, s_, "present")
    base_plan(pv, m)
    thresholds(pv, m)
    _clip_new(sh, before | keep, pv.rings(crop))
    # dimension chains: corners + openings, then overall (S and W); corners + openings (N and E)
    for side in ("S", "W", "N", "E"):
        t1, t2 = side_tiers(m, room, side)
        same = [round(c) for c, _ in t1] == [round(c) for c, _ in t2]
        pv.side_chains(side, [t1, t2] if side in ("S", "W") and not same else [t1], offsets=CH)
    # furniture tags
    for f in mine(m.furniture):
        if f.get("kind") == "rug":
            continue
        x, y = pv.P(*f["at"])
        sh.text(x, y, f["id"], sans("dim", 600), T.INK, ha="center", va="center", zorder=14,
                path_effects=sh.halo(1.8))
    # elevation markers (§2a): number in a circle, pointer at the wall
    poly = geom.room_polygon(room)
    placed = []
    for k, f in enumerate(faces, 1):
        ux, uy = (f.b[0] - f.a[0]) / f.length, (f.b[1] - f.a[1]) / f.length
        nx, ny = -uy, ux
        q = marker_spot(m, room, f, cams, placed, scale)
        placed.append(q)
        p = pv.P(*q)
        r = 3.0
        tip = (p[0] - nx * (r + 2.6), p[1] + ny * (r + 2.6))
        side = (-ny * r * 0.8, -nx * r * 0.8)
        base0 = (p[0] - nx * r * 0.55 + side[0], p[1] + ny * r * 0.55 + side[1])
        base1 = (p[0] - nx * r * 0.55 - side[0], p[1] + ny * r * 0.55 - side[1])
        sh.region([([tip, base0, base1], [])], fill=T.INK, edge=T.INK, lw=LW_HAIR, z=15)
        sh.circle(p[0], p[1], r, edge=T.INK, fill=T.PAPER, lw=LW_THIN, z=16)
        sh.text(p[0], p[1] + 0.1, str(k), sans("legend_head", 700), T.INK, ha="center", va="center", zorder=17)
    # camera marks: view cone + letter, matching the vignettes
    for c, L in zip(cams, LETTERS):
        ex, ey = c["eye"][:2]
        yaw = math.atan2(c["target"][1] - ey, c["target"][0] - ex)
        half = math.atan(18 / c.get("lens", 20))
        rr = 7.0
        e = pv.P(ex, ey)
        pts = [e] + [(e[0] + rr * math.cos(a), e[1] - rr * math.sin(a)) for a in np.linspace(yaw - half, yaw + half, 9)]
        sh.region([(pts, [])], fill=T.LIGHT, edge=T.GREY, lw=LW_HAIR, z=13)
        sh.circle(e[0], e[1], 1.7, edge=T.INK, fill=T.INK, lw=LW_HAIR, z=14)
        sh.text(e[0], e[1] + 0.05, L, sans("dim", 700), T.PAPER, ha="center", va="center", zorder=15)
    return pv


def marker_spot(m, room, f, cams, placed, scale):
    """Elevation marker in front of its wall, clear of furniture, joinery, cameras and the other marker."""
    ux, uy = (f.b[0] - f.a[0]) / f.length, (f.b[1] - f.a[1]) / f.length
    nx, ny = -uy, ux
    inner = geom.room_polygon(room).buffer(-max(300, 5 * scale), join_style=2)
    stuff = [geom.furniture_polygon(x) for x in m.furniture if x["room"] == room["id"] and x.get("kind") != "rug"]
    stuff += [geom.joinery_polygon(j, m.wall(j["wall"]), room) for j in m.joinery if j["room"] == room["id"]]
    obst = unary_union(stuff) if stuff else None
    cam_pts = [Point(c["eye"][:2]) for c in cams]
    pts = [Point(p) for p in placed]
    clear = 6.0 * scale                                  # marker radius + pointer on the page, in plan mm
    cam_clear = 11.0 * scale                             # plus a camera's view cone
    best, best_sc = None, -1e9
    for d in (700, 950, 1200, 500, 1500, 1800):
        for lat in (0, 0.15, -0.15, 0.3, -0.3, 0.42, -0.42):
            t = f.length * (0.5 + lat)
            c = Point(f.a[0] + ux * t + nx * d, f.a[1] + uy * t + ny * d)
            if not inner.contains(c):
                continue
            gap = min([obst.distance(c) if obst else 1e9] + [p.distance(c) for p in pts])
            cgap = min([p.distance(c) for p in cam_pts] or [1e9])
            sc = min(gap, clear) * 10 + min(cgap, cam_clear) * 10 - d * 0.01 - abs(lat) * 300
            if sc > best_sc:
                best, best_sc = c, sc
    if best is None:
        mid = ((f.a[0] + f.b[0]) / 2, (f.a[1] + f.b[1]) / 2)
        best = Point(mid[0] + nx * 600, mid[1] + ny * 600)
    return (best.x, best.y)


# ------------------------------------------------------------------ elevation at 1:50
def _furn_near(m, F, room):
    line = LineString([F.f.a, F.f.b])
    out = []
    for f in m.furniture:
        if f["room"] != room["id"] or f.get("kind") == "rug":
            continue
        g = geom.furniture_polygon(f)
        dist = g.distance(line)
        if dist > 1200:
            continue
        xs = [F.x_of(p) for p in g.exterior.coords]
        xa, xb = max(min(xs), 0), min(max(xs), F.L)
        if xb - xa < 50:
            continue
        fx, fy = geom.compass_to_vec(f.get("facing", "N"))
        ux, uy = F.ux, F.uy
        frontal = abs(fx * ux + fy * uy) < 0.5           # seen from the front or the back
        out.append((dist, f, xa, xb, frontal))
    return sorted(out, key=lambda t: t[0])           # nearest the wall first (furthest from the viewer)


def _furniture_elev(C, f, xa, xb, frontal):
    pal = TX.palette()
    k, (w, d, h) = f.get("kind"), f["size"]
    fab, cus, oak, wood, lin_ = (TX.hexc(pal[n]) for n in ("fabric", "cushion", "oak", "wood", "linen"))
    R = lambda a, b, za, zb, fill: C.rect(a, b, za, zb, fill=fill, edge=T.INK, lw=LW_THIN, z=8)  # noqa: E731
    W = xb - xa
    if f.get("finish") == "velvet":
        fab = TX.hexc(pal["velvet"])
        cus = cus if k == "bed" else TX.hexc(pal["velvet"])
    elif f.get("finish") == "marble":
        oak = TX.hexc(pal["marble"])
    if k == "bed":
        if f.get("headboard") == "curved" and frontal:          # arched upholstered headboard behind
            hb = TX.hexc(pal["velvet_dk"] if f.get("finish") == "velvet" else pal["fabric_dk"])
            pts = [(C.X(xa - 20 + (W + 40) * t), C.Z(1030 + 120 * (1 - (2 * t - 1) ** 2))) for t in np.linspace(0, 1, 25)]
            C.sh.region([([(C.X(xa - 20), C.Z(300))] + pts + [(C.X(xb + 20), C.Z(300))], [])], fill=hb, edge=T.INK,
                        lw=LW_THIN, z=7.5)
        R(xa, xb, 80, 300, TX.hexc(pal["velvet_dk" if f.get("finish") == "velvet" else "fabric_dk"]))
        R(xa + 15, xb - 15, 300, h, lin_)
        if frontal:
            for a, b in ((xa + 60, xa + W / 2 - 30), (xa + W / 2 + 30, xb - 60)):
                C.sh.region([([(C.X(a), C.Z(h)), (C.X(b), C.Z(h)), (C.X(b - 40), C.Z(h + 140)),
                               (C.X(a + 40), C.Z(h + 140))], [])], fill=cus, edge=T.INK, lw=LW_THIN, z=8)
    elif k in ("sofa", "armchair"):
        arm = 160 if k == "sofa" else 120
        if frontal:
            R(xa, xb, 90, 420, fab)
            R(xa + arm, xb - arm, 420, h, fab)
            R(xa, xa + arm, 90, 600, fab)
            R(xb - arm, xb, 90, 600, fab)
        else:
            R(xa, xb, 90, 420, fab)
            back = (xa, xa + 180) if True else None
            R(back[0], back[1], 420, h, fab)
            R(xa, xb, 420, 600, cus)
        for x in (xa + 60, xb - 100):
            R(x, x + 40, 0, 90, wood)
    elif k in ("coffee_table", "dining_table", "desk", "console"):
        th = 40 if k == "dining_table" else 30
        R(xa, xb, h - th, h, oak)
        lg = 25 if k == "desk" else 50
        R(xa + (0 if k == "desk" else 70), xa + (0 if k == "desk" else 70) + lg, 0, h - th, oak)
        R(xb - (0 if k == "desk" else 70) - lg, xb - (0 if k == "desk" else 70), 0, h - th, oak)
    elif k == "side_table":
        R(xa, xb, h - 25, h, oak)
        mid = (xa + xb) / 2
        R(mid - 28, mid + 28, 15, h - 25, wood)
        R(xa + W * 0.22, xb - W * 0.22, 0, 15, wood)
    elif k == "chair":
        R(xa + 20, xa + 50, 0, 440, wood)
        R(xb - 50, xb - 20, 0, 440, wood)
        R(xa, xb, 440, 480, fab)
        R(xa + 20 if frontal else xa, xb - 20 if frontal else xa + 40, 480, h, wood)
    elif k == "bedside":
        R(xa, xb, 60, h, oak)
        C.line([(xa + 20, h - 160), (xb - 20, h - 160)], T.INK, LW_HAIR, z=9)
        mid = (xa + xb) / 2
        if f.get("lamp"):
            R(mid - 8, mid + 8, h, h + 300, TX.hexc(pal["metal"]))
            C.sh.region([([(C.X(mid - 150), C.Z(h + 300)), (C.X(mid + 150), C.Z(h + 300)),
                           (C.X(mid + 120), C.Z(h + 520)), (C.X(mid - 120), C.Z(h + 520))], [])],
                        fill=lin_, edge=T.INK, lw=LW_THIN, z=8)
    elif k == "bench":
        for x in (xa + 30, xb - 70):
            R(x, x + 40, 0, 180, wood)
        R(xa, xb, 180, h - 60, fab)
        R(xa + 10, xb - 10, h - 60, h, cus)
    elif k == "plant":
        mid = (xa + xb) / 2
        r = W / 2
        C.sh.region([([(C.X(mid - r * 0.7), C.Z(h * 0.32)), (C.X(mid + r * 0.7), C.Z(h * 0.32)),
                       (C.X(mid + r * 0.5), C.Z(0)), (C.X(mid - r * 0.5), C.Z(0))], [])],
                    fill=TX.hexc(pal["stone_dark"]), edge=T.INK, lw=LW_THIN, z=8)
        from matplotlib.patches import Ellipse
        C.sh.ax.add_patch(Ellipse((C.X(mid), C.Z(h * 0.68)), 2 * r * 1.1 / C.s, h * 0.72 / C.s,
                                  facecolor=TX.hexc(pal["leaf"]), edgecolor=T.INK, lw=LW_THIN, zorder=8))
    else:
        R(xa, xb, 0, h, oak)


def draw_elevation(sh, m, view, k, x0, y0, s=ES):
    """Key elevation k at 1:50 with its top-left at (x0, y0). Returns (width, height) used."""
    F = Face(m, view)
    room = F.room
    L, soff = F.L, F.soffit
    fin = {f["code"]: f for f in m.finishes}
    pal = TX.palette()
    ex0 = x0 + CALLOUT_W + F.t_left / s
    ey0 = y0 + E_TITLE + (soff + ED["slab"]) / s
    C = Cv(sh, F, ex0, ey0, s)
    cdef = next((c for c in m.ceilings if c["room"] == room["id"]), None)
    fcl = F.fcl
    top = fcl or soff
    looking = geom.vec_to_cardinal((F.f.b[1] - F.f.a[1]), -(F.f.b[0] - F.f.a[0]))
    # title: bubble k + caps
    sh.circle(x0 + 2.6, y0 + 2.2, 2.4, edge=T.INK, fill=T.PAPER, lw=LW_THIN, z=6)
    sh.text(x0 + 2.6, y0 + 2.3, str(k), sans("legend_head", 700), T.INK, ha="center", va="center", zorder=7)
    sh.caps(x0 + 7.5, y0 + 3.2, f"Elevation {k} · wall {view['wall']} · looking {looking} · 1:{s}", T.INK,
            role="legend_head", weight=600)
    # slab, floor, end walls
    C.rect(-F.t_left, L + F.t_right, soff, soff + ED["slab"], fill=T.PAPER, edge=T.INK, hatch="////", z=3)
    C.rect(-F.t_left, L + F.t_right, -E_FLOOR, 0, fill=T.PAPER, edge=T.INK, hatch="////", z=3)
    C.rect(-F.t_left, 0, 0, soff, fill=T.POCHE, z=9)
    C.rect(L, L + F.t_right, 0, soff, fill=T.POCHE, z=9)
    wall_code = room.get("wall_finish")
    C.rect(0, L, 0, top, fill=TX.hexc(TX.finish_tone(fin.get(wall_code, {"kind": "paint"}))), z=1)
    levels = [(0, "FFL", False)]
    calls = []
    if fcl:
        C.rect(0, L, fcl, soff, fill=T.LIGHT, z=2)
        C.line([(0, fcl), (L, fcl)], T.INK, LW_CUT, z=6)
        levels.append((fcl, "FCL", False))
        calls.append(("FC", f"Gypsum false ceiling {_metres(fcl)}", (L * 0.82, (fcl + soff) / 2)))
        poly = geom.room_polygon(room)
        for st in (cdef or {}).get("steps", []):                 # trays seen beyond the false ceiling line
            g = geom.step_polygon(room, st)
            xs = [F.x_of(p) for p in g.exterior.coords]
            xa, xb = max(min(xs), 0), min(max(xs), L)
            if xb - xa < 50:
                continue
            C.rect(xa, xb, fcl, st["z"], fill=T.PAPER, edge=T.GREY, lw=LW_HAIR, z=3)
            if st.get("light") == "cove":
                C.line([(xa + 60, fcl + 25), (xb - 60, fcl + 25)], T.AMBER, LW_LINE, z=4)
                if not any(c[0] == "COVE" for c in calls):
                    calls.append(("COVE", "Provision for cove light", (xa + 0.25 * (xb - xa), fcl + 25)))
            levels.append((st["z"], "Tray", False))
        for dm in (cdef or {}).get("domes", []):
            cx_ = F.x_of(dm["at"])
            r = dm["d"] / 2
            zs = geom.ceiling_z_at(room, {**cdef, "domes": []}, dm["at"])
            if cx_ + r < 0 or cx_ - r > L:
                continue
            pts = [(cx_ + r * math.cos(t), zs + (dm["z"] - zs) * math.sin(t)) for t in np.linspace(0, math.pi, 33)]
            C.line(pts, T.GREY, LW_HAIR, DASH, z=4)
            levels.append((dm["z"], "Dome", False))
            calls.append(("DOME", f"Dome Ø{dm['d']}", (cx_ - r * 0.5, zs + (dm["z"] - zs) * 0.85)))
        del poly
    levels.append((soff, "Soffit", F.sflag))
    # features (STANDARDS §4): shared drawing routine; call-outs per element
    from atelier import features as FT
    for wf in F.features():
        wf = dict(wf, z1=min(wf["z1"], top))                   # seen up to the false ceiling, not into the void
        f_ = fin.get(wf.get("finish"), {})
        FT.draw(C, m, wf, wf["xa"], wf["xb"], wf["z0"], wf["z1"])
        calls.append((f"{wf['id']} · {wf['finish']}", f_.get("name", wf.get("kind", "")),
                      (wf["xa"] + 0.14 * (wf["xb"] - wf["xa"]), wf["z0"] + 0.62 * (wf["z1"] - wf["z0"]))))
        levels.append((wf["z1"], wf["id"], False)) if wf["z1"] < top else None
    for g in getattr(m, "feature_walls", []):
        if g["room"] == room["id"] and g.get("wall") == view["wall"]:
            for ld in g.get("led", []):
                x = ld["u"] - F.x_from
                if 0 < x < L:
                    FT.draw_led(C, x, ld.get("z0", 0), min(ld.get("z1", top), top))
            FT.draw_pendants(C, g, F.x_from, top, L)
    # openings
    O = F.openings()
    glass = TX.hexc(TX.mix(T.BLUE, T.PAPER, 0.82))
    door = TX.hexc(TX.mix(T.PAPER, T.LIGHT, 0.45))
    for o in O:
        sill = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
        head = o.get("head", 2100)
        if o["kind"] in ("window", "ventilator", "sliding_door"):
            C.rect(o["xa"], o["xb"], sill, head, fill=TX.hexc(TX.mix(T.GREY, T.INK, 0.4)), edge=T.INK, lw=LW_LINE, z=5)
            C.rect(o["xa"] + 55, o["xb"] - 55, sill + 55, head - 55, fill=glass, edge=T.INK, lw=LW_HAIR, z=5)
            mid = (o["xa"] + o["xb"]) / 2
            C.rect(mid - 27, mid + 27, sill + 55, head - 55, fill=TX.hexc(TX.mix(T.GREY, T.INK, 0.4)), z=5)
            for a in (o["xa"] + 55, mid + 27):
                C.line([(a + 90, head - 230), (a + 330, head - 470)], T.PAPER, LW_THIN, z=5)
            if sill:
                C.rect(o["xa"] - 30, o["xb"] + 30, sill - 20, sill, fill=TX.hexc(pal["worktop"]), edge=T.INK,
                       lw=LW_HAIR, z=6)
            levels.append((sill, o["id"] + " sill", m.is_flagged(o, "sill"))) if sill else None
        elif o.get("concealed"):
            host = next((w for w in F.features() if w["id"] == o.get("concealed_in")), None)
            FT.draw_concealed(C, o["xa"], o["xb"], head, FT.tone_of(m, host) if host else TX.finish_tone({}))
        elif o["kind"] in ("door", "double_door"):
            C.rect(o["xa"], o["xb"], 0, head, fill=door, edge=T.INK, lw=LW_LINE, z=5)
            hx = o["xb"] - 80 if (o["xa"] + o["xb"]) / 2 < L / 2 else o["xa"] + 80
            C.line([(hx, 1000), (hx, 1140)], T.INK, LW_CUT, z=6)
        else:
            C.rect(o["xa"], o["xb"], 0, head, fill=TX.hexc(TX.mix(T.LIGHT, T.MID, 0.5)), edge=T.INK, lw=LW_LINE, z=5)
        sh.text(C.X((o["xa"] + o["xb"]) / 2), C.Z(head) - 1.2, o["id"], sans("dim", 600), T.GREY, ha="center",
                zorder=6)
        levels.append((head, "Head", m.is_flagged(o, "head")))
    # joinery (same build-up as the 1:25 elevation)
    J = F.joinery()
    for jj in J:
        j = jj["j"]
        H = j.get("height", 850)
        base = j.get("kind") in ("kitchen_base", "vanity")
        rows = j.get("rows") or [{"height": H}]
        r1 = rows[0]["height"]
        jtop = r1 - (ED["worktop"] if base else 0)
        C.rect(jj["xa"], jj["xb"], 0, ED["plinth"], fill=TX.hexc(TX.mix(T.MID, T.PAPER, 0.4)), edge=T.INK,
               lw=LW_HAIR, z=6)
        gola = j.get("handles") == "gola"
        front_top = jtop - (ED["gola_h"] if gola else 0)
        if gola:
            C.rect(jj["xa"], jj["xb"], front_top, jtop, fill=T.MID, edge=T.INK, lw=LW_HAIR, z=6)
        for kk, md in enumerate(jj["mods"]):
            _module(C, md, ED["plinth"], front_top, "", kk, gola)
            if md.get("type") == "sink":
                _mixer(C, (md["xa"] + md["xb"]) / 2, r1)
        if base:
            C.rect(jj["xa"] - 20 if jj["xa"] > 1 else jj["xa"], jj["xb"] + 20 if jj["xb"] < L - 1 else jj["xb"], jtop,
                   r1, fill=TX.hexc(pal["worktop"]), edge=T.INK, lw=LW_THIN, z=7)
        z = r1
        for kk, md in enumerate(jj["upper"]):
            row_h = rows[md["row"] - 1]["height"]
            _module(C, md, z, z + row_h, "", kk)
        code = " · ".join(c for c in (j["id"], j.get("finish"), j.get("worktop")) if c)
        name = fin.get(j.get("finish"), {}).get("name", j.get("kind", "").replace("_", " "))
        calls.append((code, name, (jj["xa"] + 0.3 * (jj["xb"] - jj["xa"]), min(H, 1600) * 0.55)))
        levels.append((r1, j["id"], False))
    # joinery on the adjoining walls, seen end-on at this face (carcass side + worktop)
    line = LineString([F.f.a, F.f.b])
    ends = []
    for j in m.joinery:
        if j["room"] != room["id"] or j["wall"] == view["wall"]:
            continue
        g = geom.joinery_polygon(j, m.wall(j["wall"]), room)
        if g.distance(line) > 60:
            continue
        xs = [F.x_of(p) for p in g.exterior.coords]
        xa, xb = max(min(xs), 0), min(max(xs), L)
        if xb - xa < 50:
            continue
        H = j.get("height", 850)
        base = j.get("kind") in ("kitchen_base", "vanity")
        C.rect(xa, xb, ED["plinth"], H - (ED["worktop"] if base else 0), fill=TX.hexc(TX.finish_tone(
            fin.get(j.get("finish"), {"kind": "laminate"}))), edge=T.INK, lw=LW_THIN, z=6)
        C.rect(xa, xb - 60, 0, ED["plinth"], fill=TX.hexc(TX.mix(T.MID, T.PAPER, 0.4)), edge=T.INK, lw=LW_HAIR, z=6)
        if base:
            C.rect(xa, xb, H - ED["worktop"], H, fill=TX.hexc(pal["worktop"]), edge=T.INK, lw=LW_THIN, z=7)
        ends.append((xa, xb))
        calls.append((f"{j['id']} end", "Joinery seen end-on", ((xa + xb) / 2, 450)))
    # skirting on bare wall (E5.10)
    fl = next((x for x in m.floors if x["room"] == room["id"]), {})
    sk = fl.get("skirting", 0)
    if sk:
        bare = [(0.0, L)]
        for blk in [(j["xa"], j["xb"]) for j in J] + ends + [(o["xa"], o["xb"]) for o in O
                                                     if o["kind"] not in ("window", "ventilator")]:
            nxt = []
            for a, b in bare:
                if blk[1] <= a or blk[0] >= b:
                    nxt.append((a, b))
                else:
                    if a < blk[0]:
                        nxt.append((a, blk[0]))
                    if blk[1] < b:
                        nxt.append((blk[1], b))
            bare = nxt
        for a, b in bare:
            if b - a > 20:
                C.rect(a, b, 0, sk, fill=TX.hexc(pal["wood_lt"]), edge=T.INK, lw=LW_HAIR, z=6)
    # furniture in front of the wall (silhouettes, nearest the wall first)
    for dist, f, xa, xb, frontal in _furn_near(m, F, room):
        _furniture_elev(C, f, xa, xb, frontal)
    # wall finish and floor call-outs
    if wall_code:
        free = [x for x in np.linspace(0.06, 0.94, 23) * L if not any(o["xa"] - 80 < x < o["xb"] + 80 for o in O)
                and not any(w_["xa"] - 80 < x < w_["xb"] + 80 for w_ in F.features() if w_["z1"] > 2000)]
        if free:
            calls.append((wall_code, fin.get(wall_code, {}).get("name", ""), (free[0], min(top - 250, 2300))))
    if fl.get("finish"):
        calls.append((fl["finish"], fin.get(fl["finish"], {}).get("name", ""), (L * 0.04, -45)))
    # call-outs: CAPS on leaders, in a column left of the elevation (§2a)
    xr = ex0 - F.t_left / s - 3
    ys = _spread([C.Z(t[2][1]) for t in calls], 6.6)
    ytop, ybot = y0 + E_TITLE + 2, C.Z(-E_FLOOR) - 1
    if ys and max(ys) > ybot:                         # keep the column inside the elevation's height
        shift = max(ys) - ybot
        ys = [y - shift for y in ys]
    ys = [max(y, ytop + i * 6.6) for i, y in enumerate(sorted(ys))]
    order = sorted(range(len(calls)), key=lambda i: C.Z(calls[i][2][1]))
    for i, y in zip(order, ys):
        code, name, (x, z) = calls[i]
        px, py = C.X(x), C.Z(z)
        sh.line([(px, py), (xr + 1.2, y - 0.9), (xr + 0.4, y - 0.9)], T.INK, LW_HAIR, z=12)
        sh.circle(px, py, 0.45, edge=T.INK, fill=T.INK, lw=LW_HAIR, z=12)
        sh.text(xr, y - 0.4, tracked(code), sans("dim", 700), T.INK, ha="right", zorder=12)
        short = name.split(",")[0]
        sh.text(xr, y + 2.1, tracked(short[:30]), sans("dim"), T.GREY, ha="right", zorder=12)
    # level markers (§2a)
    xm = C.X(L) + F.t_right / s + 3.5
    lv = {}
    for z, lab, fl_ in levels:
        if lab in ("FFL", "FCL", "Tray", "Dome", "Soffit"):
            if z not in lv:
                lv[z] = (lab, fl_)
    marks = sorted(lv.items(), key=lambda t: -t[0])
    yy = _spread([C.Z(z) for z, _ in marks], 2.9)
    for (z, (lab, fl_)), y in zip(marks, yy):
        sz = 1.0
        sh.region([([(xm - sz, C.Z(z) - sz), (xm + sz, C.Z(z) - sz), (xm, C.Z(z))], [])], fill=T.INK, edge=T.INK,
                  lw=LW_HAIR, z=8)
        sh.line([(xm - 3.0, C.Z(z)), (xm + 1.4, C.Z(z))], T.INK, LW_HAIR, z=8)
        txt = f"{tracked(lab)} {_metres(z)}" + ("*" if fl_ else "")
        sh.text(xm + 2.2, y + 0.2, txt, sans("dim", 600), T.FLAG if fl_ else T.INK, va="center", zorder=9)
    # chain: corners, openings, joinery (one tier) — sums to the face length
    yb = C.Z(-E_FLOOR) + E_CHAIN
    xs = {0, round(L)}
    for o in O:
        xs |= {round(o["xa"]), round(o["xb"])}
    for jj in J:
        xs |= {round(jj["xa"]), round(jj["xb"])}
    xs = sorted(x for x in xs if 0 <= x <= round(L))
    dim_chain(sh, (C.X(0), yb), (1, 0), (0, 1), [x / s for x in xs], [xs[i + 1] - xs[i] for i in range(len(xs) - 1)],
              [False] * (len(xs) - 1), ext_from=[yb - C.Z(0)] * len(xs))
    return F


# ------------------------------------------------------------------ vignettes, palette, legend
def vignette(sh, root, cam, letter, cx, cy, r):
    png = Path(root) / "out" / "renders" / f"{cam['id']}.png"
    ring = [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 96)]
    from atelier.render import is_current
    ok = png.exists() and is_current(Path(root), None, cam)
    if ok:
        arr = np.asarray(Image.open(png).convert("RGB")) / 255.0
        sh.image(arr, cx - r, cy - r, cx + r, cy + r, clip_rings=[(ring, [])], z=4)
        sh.circle(cx, cy, r, edge=T.INK, lw=LW_THIN, z=5)
    else:                                              # never pretend: an empty, labelled circle
        sh.circle(cx, cy, r, edge=T.GREY, fill=T.PAPER, lw=LW_THIN, z=5)
        sh.text(cx, cy - 1.5, tracked("render not produced"), sans("dim", 600), T.FLAG, ha="center", va="center",
                zorder=6)
        sh.text(cx, cy + 2.0, "run python -m atelier.render", sans("dim"), T.GREY, ha="center", va="center",
                zorder=6)
    sh.circle(cx - r * 0.72, cy - r * 0.72, 2.4, edge=T.INK, fill=T.INK, lw=LW_HAIR, z=6)
    sh.text(cx - r * 0.72, cy - r * 0.72 + 0.05, letter, sans("dim", 700), T.PAPER, ha="center", va="center",
            zorder=7)
    corner = cam.get("corner")
    cap = f"{letter} · from the {corner} corner, looking {cam.get('looking')}" if corner else \
        f"{letter} · camera {cam['id']}"
    sh.text(cx, cy + r + 3.4, cap, sans("dim"), T.GREY, ha="center")
    return ok


def room_codes(m, room):
    fl = next((x for x in m.floors if x["room"] == room["id"]), {})
    codes = [fl.get("finish"), room.get("wall_finish")]
    codes += [w.get("finish") for w in m.wall_features if w["room"] == room["id"]]
    for j in m.joinery:
        if j["room"] == room["id"]:
            codes += [j.get("finish"), j.get("worktop")]
    out = []
    for c in codes:
        if c and c not in out:
            out.append(c)
    return out


def palette_circles(sh, m, room, x0, y0, per_row=3):
    fin = {f["code"]: f for f in m.finishes}
    fl = next((x for x in m.floors if x["room"] == room["id"]), {})
    r, pitch = 5.2, 23.0
    codes = [c for c in room_codes(m, room) if c in fin]
    for i, code in enumerate(codes):
        f = fin[code]
        cx, cy = x0 + r + (i % per_row) * pitch, y0 + r + (i // per_row) * 21
        kind = f.get("kind")
        if kind in ("stone", "tile", "wood", "laminate", "veneer") and (code == fl.get("finish") or kind != "laminate"):
            flo = fl if code == fl.get("finish") else {"pattern": "straight",
                                                        "module": list(_tile_size(f.get("name")) or (800, 1600))}
            arr = TX.floor_texture(f, flo, (0, 0, 900, 900), 0.35, seed=5)
        else:
            arr = np.ones((40, 40, 3)) * TX.finish_tone(f)
        ring = [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 48)]
        sh.image(arr, cx - r, cy - r, cx + r, cy + r, clip_rings=[(ring, [])], z=4)
        sh.circle(cx, cy, r, edge=T.INK, lw=LW_THIN, z=5)
        sh.text(cx, cy + r + 2.6, code, sans("dim", 700), T.INK, ha="center")
        for k, ln in enumerate(_wrap(f["name"].split(",")[0], 15)[:2]):
            sh.text(cx, cy + r + 5.0 + k * 2.3, ln, sans("dim"), T.GREY, ha="center")
    rows = (len(codes) + per_row - 1) // per_row
    return y0 + rows * 21 + 1


def furniture_rows(m, room):
    groups = {}
    for f in m.furniture:
        if f["room"] != room["id"]:
            continue
        key = (f.get("label") or f.get("kind"), tuple(f["size"]))
        groups.setdefault(key, []).append(f["id"])
    rows = []
    for (label, size), ids in groups.items():
        ref = ids[0] if len(ids) == 1 else f"{ids[0]}–{ids[-1]}" if _consecutive(ids) else ",".join(ids)
        n = f" ×{len(ids)}" if len(ids) > 1 else ""
        rows.append((ref, f"{label}{n} · {size[0]}×{size[1]}×{size[2]}"))
    return rows


def _consecutive(ids):
    try:
        ns = [int(i.lstrip("F")) for i in ids]
    except ValueError:
        return False
    return ns == list(range(ns[0], ns[0] + len(ns)))


def room_data(m, room, sv):
    fin = {f["code"]: f for f in m.finishes}
    fl = next((x for x in m.floors if x["room"] == room["id"]), {})
    cdef = next((c for c in m.ceilings if c["room"] == room["id"]), None)
    rows = [("Area", f"{geom.room_area_m2(room):.1f} m²", False)]
    if fl:
        rows.append(("Floor", f"{fl['finish']} · {fl.get('pattern')} {fl['module'][0]}×{fl['module'][1]}", False))
        if fl.get("skirting"):
            rows.append(("Skirting", f"{fl['skirting']} high, bare wall only", False))
    if room.get("wall_finish"):
        rows.append(("Walls", f"{room['wall_finish']} · {fin.get(room['wall_finish'], {}).get('name', '')[:26]}", False))
    for w in m.wall_features:
        if w["room"] == room["id"]:
            rows.append((w["id"], f"{w['finish']} · {w['kind']} on {w['wall']}, {w['z0']}–{w['z1']}", False))
    if cdef and cdef.get("z"):
        lv = [cdef["z"]] + [st["z"] for st in cdef.get("steps", [])] + [d["z"] for d in cdef.get("domes", [])]
        rows.append(("Ceiling", "FCL " + " / ".join(f"+{z}" for z in lv), False))
    soff = m.levels.get("soffit", 3000)
    rows.append(("Soffit", f"+{soff}", m.is_flagged(dict(m.levels), "soffit")))
    ops = [o for o in m.openings if _opening_in_room(m, o, room)]
    for o in ops:
        if o["kind"] in ("window", "ventilator"):
            rows.append((o["id"], f"window {o['width']} wide, sill {o.get('sill')}", m.is_flagged(o, "sill")))
        else:
            rows.append((o["id"], f"{o['kind'].replace('_', ' ')} {o['width']} wide, head {o.get('head', 2100)}",
                         m.is_flagged(o, "head")))
    for j in m.joinery:
        if j["room"] == room["id"]:
            rows.append((j["id"], f"{j['kind'].replace('_', ' ')} {j['width']}×{j['depth']}×{j.get('height')}", False))
    lights = {}
    for it in sv:
        if it.get("room") == room["id"] and it.get("system") == "lighting":
            lights[it["kind"]] = lights.get(it["kind"], 0) + 1
    if lights:
        rows.append(("Lights", ", ".join(f"{n} {k}" for k, n in lights.items()), False))
    return rows


def _opening_in_room(m, o, room):
    w = m.wall(o["wall"])
    p = Point(geom.point_on_wall(w, o["offset"] + o["width"] / 2))
    return geom.room_polygon(room).buffer(w["t"] + 5).contains(p)


# ------------------------------------------------------------------ layout + sheet
def layout(m, room, faces):
    """Choose plan scale and arrangement (see STANDARDS RB2a.7). Returns a dict of page boxes."""
    x0, y0, x1, y1 = T.DRAW
    W, H = x1 - x0, y1 - y0 + 3            # dimension text may use the 3 mm above the disclaimer rule
    es = [_elev_size(Face(m, V3.elevation_view(room, f, k))) for k, f in enumerate(faces, 1)]
    EW = max(w for w, _ in es)
    EH = sum(h for _, h in es) + 1.5 * (len(es) - 1)
    cap = 6
    for s in PLAN_SCALES:                                         # A: [plan | elevations] over a row of 3
        pw, ph = _plan_size(m, room, s)
        if pw + EW + 6 <= W:
            top = max(ph, EH)
            dia = min(H - top - cap - 4, (W - 16) / 3, 74)
            if dia >= 44:
                return dict(kind="A", scale=s, plan=(x0, y0), elev=(x1 - EW, y0), es=es, dia=dia,
                            vig=[(x0 + W / 6 * (2 * i + 1), y0 + top + 2 + dia / 2) for i in range(3)])
    for s in PLAN_SCALES:                                         # B: [plan | 3 vignettes] over elevations
        pw, ph = _plan_size(m, room, s)
        if pw <= W and ph + EH + 1.5 <= H:
            room_w = W - pw - 4
            dia = min(ph - cap - 2, (room_w - 8) / 3, 70)
            if dia >= 36:
                xs = [x0 + pw + 4 + room_w / 3 * (i + 0.5) for i in range(3)]
                return dict(kind="B", scale=s, plan=(x0, y0), elev=(x0 + (W - EW) / 2, y0 + ph + 1.5), es=es, dia=dia,
                            vig=[(x, y0 + 4 + dia / 2) for x in xs])
            col = W - EW - 4                                      # C: plan over [elevations | vignette column]
            dia = min(col - 4, (EH - 3 * cap - 4) / 3, 70)
            if dia >= 36:
                return dict(kind="C", scale=s, plan=(x0, y0), elev=(x0, y0 + ph + 1.5), es=es, dia=dia,
                            vig=[(x1 - col / 2, y0 + ph + 4 + (dia + cap + 2) * (i + 0.5)) for i in range(3)])
    raise ValueError(f"room board {room['id']}: no layout fits at 1:{PLAN_SCALES[-1]}; split the room")


def board(m, no, total, rid):
    import json
    room = m.room(rid)
    faces = V3.key_walls(m, room)
    if len(faces) < 2:
        raise ValueError(f"room board {rid}: needs two walls that are not blank, found {len(faces)}")
    cams = V3.room_cameras(m, room)
    L = layout(m, room, faces)
    s = L["scale"]
    sh = Sheet()
    name = room.get("name", rid)
    fr = Frame(sh, m, f"Room board · {name}", f"{rid} · {geom.room_area_m2(room):.1f} m² · plan 1:{s} · elevations "
               f"1:{ES} · 3D vignettes", no, total, s)
    root = m.root
    draw_plan(sh, m, room, s, *L["plan"], faces, cams)
    ex, ey = L["elev"]
    for k, (f, (ew, eh)) in enumerate(zip(faces, L["es"]), 1):
        draw_elevation(sh, m, V3.elevation_view(room, f, k), k, ex, ey)
        ey += eh + 1.5
    r = L["dia"] / 2
    produced = [vignette(sh, root, c, LETTERS[i], cx, cy, r) for i, (c, (cx, cy)) in enumerate(zip(cams, L["vig"]))]
    # strip
    fr.head("Palette")
    fr.y = palette_circles(sh, m, room, T.STRIP_X, fr.y - 1.5) + 1
    fr.rule()
    sv_path = Path(root) / "services.json"
    sv = json.loads(sv_path.read_text())["items"] if sv_path.exists() else []
    fr.head("Room data")
    for k, v, flg in room_data(m, room, sv):
        sh.text(T.STRIP_X, fr.y, k, sans("legend", 600), T.INK)
        sh.text(T.STRIP_X + 13, fr.y, v + ("*" if flg else ""), sans("legend", 500 if flg else 400),
                T.FLAG if flg else T.INK)
        fr.y += 3.3
    fr.y += 1.2
    fr.rule()
    fr.head("Furniture")
    if not furniture_rows(m, room):
        sh.text(T.STRIP_X, fr.y, "None loose: joinery only (see JN boards).", sans("legend"), T.GREY)
        fr.y += 3.3
    for ref, txt in furniture_rows(m, room):
        sh.text(T.STRIP_X, fr.y, ref, sans("legend", 600), T.INK)
        sh.text(T.STRIP_X + 13, fr.y, txt[:44], sans("legend"), T.INK)
        fr.y += 3.3
    fr.y += 1.2
    fr.rule()
    note = ("Vignettes A–C: rendered from this data (Blender Cycles); camera marks on the plan. Indicative only."
            if all(produced) else "Vignettes marked 'render not produced' have no render yet.")
    fr.lines([("", note, None), ("*", "verify on site (see measured plan).", T.FLAG)], color=T.GREY,
             limit_y=T.DRAW[3] - 27)
    return sh

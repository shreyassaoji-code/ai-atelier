"""Feature walls as the reference interpreter writes them (agents/reference.md), and how they draw.

A feature wall in the interpreter's form:

    {"id": "FW1", "room": "MBR", "wall": "X4"  (or "edge": 4, the room edge, SCHEMA §2c),
     "items": [{"from": 0, "to": 985, "type": "mural", "backlit": true, "color": "sage", "code": "WF7",
                "depth": 40, "z0": 0, "z1": 2550}, …],          # u from the LEFT corner seen from inside
     "led": [985, 2785] or [{"u": 985, "z0": 0, "z1": 2550}],   # vertical LED reveals
     "pendants": [{"u": 835, "z": 1400, "d": 220, "length": 1150, "out": 300}],
     "ref": "refs/mbr.jpg", "note": "…"}

expand(m) turns each item into an engine wall feature (SCHEMA §2: wall, offset, width, z0, z1, kind,
finish) with the extras kept (tone, depth, backlit, panels, rounded, concealed, parent), and keeps
the whole wall in m.feature_walls for the Feature wall sheet. Doors inside a `concealed` item are
marked concealed; pendants become ceiling fittings of the room.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, Point

from atelier import geom
from atelier import texture as TX
from atelier import theme as T
from atelier.draw import DASH, LW_HAIR, LW_LINE, LW_THIN, sans

TYPES = ("mural", "upholstered", "fluted", "slats", "mirror", "lineart", "arch", "niche", "paint", "stone",
         "panelling", "cladding", "wallpaper", "tile", "headboard")
DEPTH = dict(mural=20, upholstered=60, fluted=25, slats=40, mirror=8, lineart=20, arch=40, niche=0, paint=2,
             stone=30, panelling=20, cladding=20, wallpaper=1, tile=10, headboard=60)      # (default) mm


def _frame(e):
    """Viewer's frame on an edge/face: u from the left corner (end b) towards a."""
    L = math.hypot(e.b[0] - e.a[0], e.b[1] - e.a[1])
    ux, uy = (e.a[0] - e.b[0]) / L, (e.a[1] - e.b[1]) / L
    return L, (lambda u: (e.b[0] + ux * u, e.b[1] + uy * u))


def _host(m, room, fw):
    """(edge-like object, [faces on it]) for a feature wall given by wall id or room edge index."""
    faces = geom.room_faces(room, m.walls)
    if fw.get("edge") is not None:
        e = next((x for x in geom.room_edges(room, m.walls) if x.n == fw["edge"]), None)
        return e, [f for f in faces if e and f.n == e.n]
    cands = [f for f in faces if f.wall == fw.get("wall")]
    if not cands:
        return None, []
    f = max(cands, key=lambda x: x.length)
    return f, [f]


def wall_u(m, fw):
    """Length L and point(u) of a feature wall's host, for drawing and checks."""
    room = m.room(fw["room"])
    e, _ = _host(m, room, fw)
    return _frame(e) if e else (0, None)


def expand(m):
    out, groups = [], []
    for fw in list(m.design.get("wall_features", [])):
        if "items" not in fw:
            out.append(fw)
            continue
        room = m.room(fw.get("room"))
        e, faces = _host(m, room, fw) if room else (None, [])
        if not e:
            m.override_errors.append(f"wall feature {fw.get('id')}: no wall {fw.get('wall') or fw.get('edge')!r} "
                                     f"in room {fw.get('room')!r}")
            continue
        L, P = _frame(e)
        cdef = next((c for c in m.ceilings if c["room"] == room["id"]), None)
        top = (cdef or {}).get("z") or m.levels.get("ceiling", 2750)
        g = dict(fw, L=round(L), wall=fw.get("wall") or (faces[0].wall if faces else None))
        g["items"] = [dict(it, z0=it.get("z0", 0), z1=it.get("z1", top), depth=it.get("depth", DEPTH.get(it.get("type"), 20)))
                      for it in fw["items"]]
        g["led"] = [dict(u=x) if not isinstance(x, dict) else x for x in fw.get("led", [])]
        groups.append(g)
        for i, it in enumerate(g["items"], 1):
            for f in faces:
                fl, fP = _frame(f)
                # overlap of the item with this face, in the host's u
                fa = _u_of(P, L, f.b)
                fb = _u_of(P, L, f.a)
                lo, hi = max(it["from"], min(fa, fb)), min(it["to"], max(fa, fb))
                if hi - lo < 1:
                    continue
                w = m.wall(f.wall)
                t0 = _t_on_wall(w, P(lo))
                t1 = _t_on_wall(w, P(hi))
                ent = {"id": f"{fw['id']}.{i}", "room": room["id"], "wall": f.wall, "offset": round(min(t0, t1)),
                       "width": round(abs(t1 - t0)), "z0": it["z0"], "z1": it["z1"], "kind": it.get("type", "paint"),
                       "finish": it.get("code"), "parent": fw["id"], "u0": lo, "u1": hi}
                for k in ("color", "depth", "backlit", "panels", "rounded", "concealed", "note", "flag"):
                    if k in it:
                        ent["tone" if k == "color" else k] = it[k]
                out.append(ent)
            if it.get("concealed"):
                for o in m.openings:
                    if o["kind"] in ("door", "double_door") and _opening_in(m, o, P, L, it):
                        o["concealed"] = True
                        o["concealed_in"] = f"{fw['id']}.{i}"
        for k, pd in enumerate(fw.get("pendants", []), 1):
            ux, uy = (P(1)[0] - P(0)[0]), (P(1)[1] - P(0)[1])
            nx, ny = uy, -ux                         # into the room: viewer faces the wall, u runs to the right
            base = P(pd["u"])
            at = [round(base[0] + nx * pd.get("out", 300)), round(base[1] + ny * pd.get("out", 300))]
            if cdef is not None:
                cdef.setdefault("lights", []).append({"kind": "pendant", "at": at, "z": pd.get("z"), "d": pd.get("d", 200),
                                                      "length": pd.get("length"), "source": fw["id"]})
            g.setdefault("pendant_at", []).append(at)
    m.design["wall_features"] = out
    m.feature_walls = groups


def _u_of(P, L, p):
    a, b = P(0), P(L)
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    return (p[0] - a[0]) * ux + (p[1] - a[1]) * uy


def _t_on_wall(w, p):
    ux, uy, _ = geom.unit(w["a"], w["b"])
    return (p[0] - w["a"][0]) * ux + (p[1] - w["a"][1]) * uy


def _opening_in(m, o, P, L, it):
    w = m.wall(o["wall"])
    pa, pb = geom.point_on_wall(w, o["offset"]), geom.point_on_wall(w, o["offset"] + o["width"])
    line = LineString([P(0), P(L)])
    if line.distance(Point((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)) > w["t"] + 5:
        return False
    ua, ub = sorted((_u_of(P, L, pa), _u_of(P, L, pb)))
    sill = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
    return ua < it["to"] - 1 and ub > it["from"] + 1 and sill < it["z1"] and o.get("head", 2100) > it["z0"]


def opening_clashes(m):
    """[(feature group, item, opening)] where an element covers an opening without concealing a door."""
    out = []
    for g in getattr(m, "feature_walls", []):
        L, P = wall_u(m, g)
        if not P:
            continue
        for it in g["items"]:
            for o in m.openings:
                if _opening_in(m, o, P, L, it):
                    ok = it.get("concealed") and o["kind"] in ("door", "double_door")
                    if not ok:
                        out.append((g, it, o))
    return out


# ------------------------------------------------------------------ drawing in elevation
def tone_of(m, wf):
    fin = next((f for f in m.finishes if f["code"] == wf.get("finish")), {})
    t = TX.named_tone(wf.get("tone")) if wf.get("tone") else None
    return t if t is not None else TX.finish_tone(fin or {"kind": "paint"})


def draw(C, m, wf, xa, xb, z0, z1):
    """One feature element on an elevation canvas C (X, Z, rect, line, sh). x from the left corner."""
    k = wf.get("kind")
    tone = tone_of(m, wf)
    fill = TX.hexc(tone)
    dark = TX.hexc(TX.mix(tone, T.INK, 0.3))
    led = TX.hexc(TX.mix(T.AMBER, T.PAPER, 0.35))
    W = xb - xa
    C.rect(xa, xb, z0, z1, fill=fill, edge=T.INK, lw=LW_HAIR, z=3)
    if k in ("fluted", "slats"):
        step = 60 if k == "fluted" else 90
        x = xa + step / 2
        pl = []
        while x < xb - 5:
            pl.append([(C.X(x), C.Z(z0)), (C.X(x), C.Z(z1))])
            if k == "slats":
                pl.append([(C.X(x + 40), C.Z(z0)), (C.X(x + 40), C.Z(z1))])
            x += step
        C.sh.lines(pl, dark, LW_HAIR, z=3)
    elif k in ("upholstered", "headboard"):
        n = wf.get("panels") or max(1, round(W / 450))
        for i in range(1, n):
            x = xa + W * i / n
            C.line([(x, z0), (x, z1)], T.INK, LW_THIN, z=4)
        if wf.get("rounded"):
            r = min(W / 2, 250)
            pts = [(xa + r - r * math.cos(t), z1 - r + r * math.sin(t)) for t in np.linspace(0, math.pi / 2, 10)]
            pts += [(xb - r + r * math.cos(t), z1 - r + r * math.sin(t)) for t in np.linspace(math.pi / 2, 0, 10)]
            C.rect(xa, xb, z1 - r, z1, fill=T.PAPER, z=3.5)      # clear the square corners
            C.sh.region([([(C.X(xa), C.Z(z1 - r))] + [(C.X(x), C.Z(z)) for x, z in pts] + [(C.X(xb), C.Z(z1 - r))],
                          [])], fill=fill, edge=T.INK, lw=LW_HAIR, z=3.6)
    elif k == "mirror":                                         # glints, clipped to the glass
        from shapely.geometry import box as _box
        glass = _box(xa, z0, xb, z1)
        for d in np.arange(0, W + (z1 - z0) * 0.3, 260):
            seg = LineString([(xa + d, z0), (xa + d - (z1 - z0) * 0.3, z1)]).intersection(glass)
            if not seg.is_empty and seg.length > 1:
                C.line(list(seg.coords), T.HAIR, LW_HAIR, z=3)
    elif k == "lineart":
        n = wf.get("panels") or max(1, round(W / 450))
        for i in range(n):
            a, b = xa + W * i / n, xa + W * (i + 1) / n
            if i:
                C.line([(a, z0), (a, z1)], T.INK, LW_HAIR, z=4)
            cx = (a + b) / 2
            stem = [(cx + 40 * math.sin(z / 260.0), z) for z in np.linspace(z0 + 300, z1 - 400, 24)]
            C.line(stem, dark, LW_HAIR, z=4)
            for zz in np.linspace(z0 + 600, z1 - 600, 4):
                C.line([(cx, zz), (cx + 110, zz + 90), (cx + 40, zz + 30)], dark, LW_HAIR, z=4)
                C.line([(cx, zz + 150), (cx - 110, zz + 240), (cx - 40, zz + 180)], dark, LW_HAIR, z=4)
    elif k == "mural":
        for i in range(5):                                       # a quiet tree: trunk and canopy
            C.line([(xa + W * 0.5 + 20 * math.sin(i), z0 + 150), (xa + W * (0.3 + 0.1 * i), z0 + (z1 - z0) * 0.6)],
                   dark, LW_HAIR, z=4)
        for i in range(9):
            cx, cz = xa + W * (0.2 + 0.075 * i), z0 + (z1 - z0) * (0.62 + 0.05 * math.sin(i * 1.7))
            pts = [(cx + 160 * math.cos(t), cz + 110 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 16)]
            C.line(pts, dark, LW_HAIR, z=4)
    elif k == "arch":
        m_ = min(W * 0.14, 160)
        r = (W - 2 * m_) / 2
        top = z1 - m_
        base = z0 + 400
        pts = [(xa + m_, base), (xa + m_, top - r)] + \
              [(xa + m_ + r - r * math.cos(t), top - r + r * math.sin(t)) for t in np.linspace(0, math.pi, 25)] + \
              [(xb - m_, base)]
        C.sh.region([([(C.X(x), C.Z(z)) for x, z in pts], [])], fill=TX.hexc(TX.mix(tone, T.PAPER, 0.25)),
                    edge=T.INK, lw=LW_THIN, z=4)
        inner = [(x + (6 if x < (xa + xb) / 2 else -6), z - 6) for x, z in pts[1:-1]]
        C.line(inner, led, LW_LINE, z=4.5)
    elif k == "niche":
        mz = 300
        n = max(1, int((z1 - z0 - mz) // 700))
        for i in range(n):
            za = z0 + mz + i * 700 + 120
            C.rect(xa + 50, xb - 50, za, za + 450, fill=TX.hexc(TX.mix(tone, T.INK, 0.25)), edge=T.INK, lw=LW_HAIR,
                   z=4)
            C.line([(xa + 60, za + 440), (xb - 60, za + 440)], led, LW_LINE, z=4.5)
    elif k in ("tile", "stone", "cladding", "panelling"):
        from atelier.elev_detail import _tile_size
        fin = next((f for f in m.finishes if f["code"] == wf.get("finish")), {})
        tw, th = _tile_size(fin.get("name")) or ((600, 1200) if k != "panelling" else (600, z1 - z0))
        z, row, pl = z0, 0, []
        while z < z1 - 1:
            pl.append([(C.X(xa), C.Z(z)), (C.X(xb), C.Z(z))])
            x = xa + (tw / 2 if row % 2 else 0)
            while x < xb:
                pl.append([(C.X(x), C.Z(z)), (C.X(x), C.Z(min(z + th, z1)))])
                x += tw
            z += th
            row += 1
        C.sh.lines(pl, T.HAIR, LW_HAIR, z=3)
    if wf.get("backlit"):                                      # glow line round a back-lit element
        C.rect(xa + 25, xb - 25, z0 + 25, z1 - 25, edge=led, lw=LW_LINE, dash=DASH, z=4.6)


def draw_led(C, x, z0, z1):
    C.line([(x, z0), (x, z1)], TX.hexc(TX.mix(T.AMBER, T.PAPER, 0.35)), LW_LINE, z=5.5)


def draw_concealed(C, xa, xb, head, tone):
    """A flush door hidden in panelling: the panel continues, the leaf is a thin shadow line."""
    C.rect(xa, xb, 0, head, fill=TX.hexc(tone), edge=T.INK, lw=LW_HAIR, dash=DASH, z=5)
    C.sh.text(C.X((xa + xb) / 2), C.Z(head / 2), "CONCEALED DOOR", sans("dim", 600), T.GREY, rotation=90,
              ha="center", va="center", zorder=6)


def draw_pendants(C, g, x_from, ceiling, L):
    """Pendants of a feature wall in elevation: cord from the ceiling, globe at its true size and drop."""
    glow = TX.hexc(TX.mix(T.PAPER, T.AMBER, 0.25))
    for pd in g.get("pendants", []):
        x = pd["u"] - x_from
        if not 0 < x < L:
            continue
        r = pd.get("d", 200) / 2
        zb = pd.get("z", ceiling - 1000)
        C.line([(x, zb + 2 * r), (x, ceiling)], T.INK, LW_HAIR, z=8)
        C.sh.circle(C.X(x), C.Z(zb + r), r / C.s, edge=T.INK, fill=glow, lw=LW_THIN, z=8.5)

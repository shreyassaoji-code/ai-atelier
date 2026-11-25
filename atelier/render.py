"""3D renders from the data (Blender `bpy`, Cycles on CPU).

    python -m atelier.render projects/sample                 # every camera of every board room
    python -m atelier.render projects/sample --camera V-KIT-1 --samples 32 --size 480

ONE model of the whole apartment is built from survey.json + design.json (+ services.json
for the light fittings), so a door, a wardrobe or a neighbouring room seen through an
opening is the same object in every view. Cameras come from atelier/views3d.py: design
cameras first, then the corner rule, level (pitch 0) so verticals stay vertical.

Colours are mixed from atelier/theme.py tokens by atelier/texture.py; floor images are the
same procedural textures as the presentation plan. Renders are cached by a hash of the data,
the camera and this code: out/renders/<camera>.png + renders.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import constrained_delaunay_triangles
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from atelier import geom
from atelier import texture as TX
from atelier import theme as T
from atelier import views3d as V3
from atelier.model import load

R = dict(size=600, samples=48, threshold=0.03, bounces=6, exposure=1.25,
         sun=(4.0, 35, 315), sky=2.2, downlight_w=14, cove_strength=5.0, pendant_w=25,
         parapet=1050, worktop=40, plinth=100, overhang=20, gap=3, front=18, trough=150, lip=75)


def lin(c):
    """sRGB (0..1) -> linear, for Blender colour inputs."""
    c = np.clip(np.asarray(c, float), 0, 1)
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)) + (1.0,)


# ------------------------------------------------------------------ geometry accumulator (mm)
class Mesh:
    """Triangles per material key; one Blender object per key at the end."""

    def __init__(self):
        self.parts = {}

    def _p(self, key):
        return self.parts.setdefault(key, ([], []))

    def poly(self, key, pts3):
        v, f = self._p(key)
        n = len(v)
        v.extend(pts3)
        f.append(tuple(range(n, n + len(pts3))))

    def prism(self, key, g, z0, z1, caps=True):
        if g is None or g.is_empty:
            return
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon" or p.area < 1:
                continue
            p = p.buffer(0)
            if caps:
                for t in constrained_delaunay_triangles(p).geoms:
                    c = list(t.exterior.coords)[:3]
                    self.poly(key, [(x, y, z1) for x, y in c])
                    self.poly(key, [(x, y, z0) for x, y in reversed(c)])
            for ring in [p.exterior, *p.interiors]:
                c = list(ring.coords)
                for (x0, y0), (x1, y1) in zip(c, c[1:]):
                    self.poly(key, [(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1)])

    def frame_box(self, key, F, u0, u1, v0, v1, z0, z1):
        """Box in a local frame F = (origin, u_dir, v_dir) (plan), z absolute."""
        (ox, oy), (ux, uy), (vx, vy) = F
        pts = [(ox + ux * u + vx * v, oy + uy * u + vy * v) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
        self.prism(key, Polygon(pts), z0, z1)

    def disc(self, key, c, r, z0, z1, seg=28):
        self.prism(key, Point(c).buffer(r, quad_segs=max(4, seg // 4)), z0, z1)

    def ellipsoid(self, key, c, rx, ry, rz, seg=14, ring=8, z_from=-1.0):
        v, f = self._p(key)
        n0 = len(v)
        rows = []
        for i in range(ring + 1):
            ph = math.pi * (z_from + (1 - z_from) * i / ring) / 2      # -pi/2 .. pi/2 (or from z_from)
            rows.append(len(v))
            for j in range(seg):
                th = 2 * math.pi * j / seg
                v.append((c[0] + rx * math.cos(ph) * math.cos(th), c[1] + ry * math.cos(ph) * math.sin(th),
                          c[2] + rz * math.sin(ph)))
        for i in range(ring):
            for j in range(seg):
                a, b = rows[i] + j, rows[i] + (j + 1) % seg
                f.append((a, b, b + seg, a + seg))
        del n0


def furn_frame(f, at=None):
    fx, fy = geom.compass_to_vec(f.get("facing", "N"))
    return (tuple(at or f["at"]), (fy, -fx), (fx, fy))        # u: across (right), v: towards the front


def wall_frame(wall, room):
    """Origin at the wall's a end on the room-side face; u along a->b, v into the room."""
    side = geom.room_side_of_wall(wall, room) or "left"
    ux, uy, _ = geom.unit(wall["a"], wall["b"])
    nx, ny = geom.left_normal(ux, uy)
    s = 1 if side == "left" else -1
    o = geom.point_on_wall(wall, 0, geom.face_offset(wall, side))
    return (o, (ux, uy), (nx * s, ny * s))


# ------------------------------------------------------------------ the scene, as data
class Scene:
    def __init__(self, m, root: Path, services):
        self.m, self.root, self.sv = m, root, services
        self.mesh = Mesh()
        self.mats = {}           # key -> spec dict
        self.lights = []         # dicts
        self.soffit = m.levels.get("soffit", 3000)
        self.fin = {f["code"]: f for f in m.finishes}
        self.pal = TX.palette()
        self.tex = root / "out" / "renders" / "tex"
        self.tex.mkdir(parents=True, exist_ok=True)

    # materials: specs only, created in Blender later
    def mat(self, key, **spec):
        self.mats.setdefault(key, spec)
        return key

    def finish_mat(self, code):
        f = self.fin.get(code, {"kind": "paint", "name": ""})
        kind = f.get("kind")
        tone = TX.finish_tone(f)
        if kind == "tile":
            ts = _tile_mm(f.get("name")) or (300, 600)
            img = self._tile_image(code, f, ts)
            return self.mat(f"fin-{code}", color=tone, rough=0.35, image=img, box=1.2)
        if kind in ("wood", "veneer"):
            return self.mat(f"fin-{code}", color=tone, rough=0.55, grain=True)
        if kind == "fabric":
            return self.mat(f"fin-{code}", color=tone, rough=0.9, sheen=True)
        if kind == "paint" and "lime" in (f.get("name") or "").lower():
            return self.mat(f"fin-{code}", color=tone, rough=0.85, mottle=True)
        if kind == "laminate":
            return self.mat(f"fin-{code}", color=tone, rough=0.55)
        if kind == "stone":
            return self.mat(f"fin-{code}", color=tone, rough=0.25)
        return self.mat(f"fin-{code}", color=tone, rough=0.8)

    def _tile_image(self, code, f, ts):
        p = self.tex / f"tile-{code}.png"
        if not p.exists():
            arr = TX.stone_tile((0, 0, 1200, 1200), 0.8, tile=(ts[0], ts[1]), grout=3, seed=11)
            Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).save(p)
        return str(p)

    # ---------------------------------------------------------- build
    def build(self):
        m = self.m
        self.mat("plaster", color=TX.finish_tone({"kind": "paint"}), rough=0.85)
        self.mat("ceiling", color=TX.mix(T.PAPER, T.LIGHT, 0.05), rough=0.9)
        self.walls()
        self.floors()
        for r in m.rooms:
            self.skins(r)
        self.openings()
        self.ceilings()
        self.features()
        for j in m.joinery:
            self.joinery(j)
        for f in m.furniture:
            self.furniture(f)
        for s in m.sanitary:
            self.sanitary(s)
        self.fittings()
        # outside: ground below the floor, so the horizon is not a void
        b = geom.walls_union(m.walls).bounds
        self.mat("ground", color=TX.mix(T.MID, T.GREEN, 0.25), rough=0.95)
        self.mesh.prism("ground", box(b[0] - 60000, b[1] - 60000, b[2] + 60000, b[3] + 60000), -9200, -9000)
        self.mesh.prism("ceiling", box(*geom.walls_union(m.walls).bounds), self.soffit, self.soffit + 150)

    def walls(self):
        m = self.m
        full = [w for w in m.walls if w.get("kind") != "parapet"]
        low = [w for w in m.walls if w.get("kind") == "parapet"]
        ops = [(m.wall(o["wall"]), o) for o in m.openings]
        holes = unary_union([geom.opening_polygon(w, o, extra=0) for w, o in ops])
        self.mesh.prism("plaster", geom.walls_union(full).difference(holes), 0, self.soffit)
        self.mesh.prism("plaster", geom.walls_union(low), 0, R["parapet"])
        wu = geom.walls_union(full)
        for w, o in ops:
            if w.get("kind") == "parapet":
                continue
            g = geom.opening_polygon(w, o, extra=0).intersection(wu)
            head = o.get("head", m.levels.get("lintel", 2100))
            self.mesh.prism("plaster", g, head, self.soffit)
            sill = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
            if sill > 0:
                self.mesh.prism("plaster", g, 0, sill)

    def floors(self):
        from atelier.sheets import floor_voids
        m = self.m
        flo = {f["room"]: f for f in m.floors}
        voids = floor_voids(m)
        for i, r in enumerate(m.rooms, 1):
            poly = unary_union([geom.room_polygon(r)] + voids.get(r["id"], []))
            fl = flo.get(r["id"])
            if not fl:
                self.mesh.prism("plaster", poly, -40, 0)
                continue
            f = self.fin[fl["finish"]]
            b = poly.buffer(30, join_style=2).bounds
            p = self.tex / f"floor-{r['id']}.png"
            k = min(0.45, 3600 / max(b[2] - b[0], b[3] - b[1]))
            arr = TX.floor_texture(f, fl, b, k, seed=i)
            Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).save(p)
            rough = {"stone": 0.22, "wood": 0.45, "tile": 0.4}.get(f.get("kind"), 0.5)
            key = self.mat(f"floor-{r['id']}", color=TX.finish_tone(f), rough=rough, image=str(p), plane=b)
            self.mesh.prism(key, poly, -40, 0)
        th = self.mat("threshold", color=self.pal["worktop"], rough=0.3)
        for o in m.openings:
            if o["kind"] in ("door", "double_door", "sliding_door", "opening"):
                self.mesh.prism(th, geom.opening_polygon(m.wall(o["wall"]), o, extra=0), -40, 0)

    def _face_cuts(self, f, room, walls=None):
        """Openings on a face (or a whole room edge) as (t0, t1, sill, head) along it from f.a."""
        m = self.m
        ux, uy = (f.b[0] - f.a[0]) / f.length, (f.b[1] - f.a[1]) / f.length
        line = geom.LineString([f.a, f.b])
        out = []
        for wid in (walls or [f.wall]):
            w = m.wall(wid)
            for o in m.openings_on(wid):
                pa = geom.point_on_wall(w, o["offset"])
                pb = geom.point_on_wall(w, o["offset"] + o["width"])
                mid = Point((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
                if line.distance(mid) > w["t"] + 5:          # an opening on a wall that only meets this edge end-on
                    continue
                ta = (pa[0] - f.a[0]) * ux + (pa[1] - f.a[1]) * uy
                tb = (pb[0] - f.a[0]) * ux + (pb[1] - f.a[1]) * uy
                ta, tb = sorted((ta, tb))
                if tb <= 0 or ta >= f.length:
                    continue
                sill = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
                out.append((max(ta, 0), min(tb, f.length), sill, o.get("head", 2100)))
        return sorted(out), (ux, uy)

    def _strip(self, key, f, cuts, u, t0, t1, z0, z1, d0, d1):
        """A layer on a face between t0..t1, z0..z1, depth d0..d1 into the room, with openings cut out."""
        ux, uy = u
        nx, ny = -uy, ux                      # room_faces run CCW: left normal points into the room
        F = (f.a, (ux, uy), (nx, ny))
        spans = [(t0, t1, z0, z1)]
        for ta, tb, sill, head in cuts:
            nxt = []
            for a, b, za, zb in spans:
                if tb <= a or ta >= b:
                    nxt.append((a, b, za, zb))
                    continue
                if a < ta:
                    nxt.append((a, ta, za, zb))
                if tb < b:
                    nxt.append((tb, b, za, zb))
                lo, hi = max(a, ta), min(b, tb)
                if sill > za:
                    nxt.append((lo, hi, za, min(sill, zb)))
                if head < zb:
                    nxt.append((lo, hi, max(head, za), zb))
            spans = nxt
        for a, b, za, zb in spans:
            if b - a > 1 and zb - za > 1:
                self.mesh.frame_box(key, F, a, b, d0, d1, za, zb)

    def skins(self, r):
        code = r.get("wall_finish")
        if not code:
            return
        key = self.finish_mat(code)
        fl = next((x for x in self.m.floors if x["room"] == r["id"]), {})
        sk = fl.get("skirting", 0)
        skm = self.mat("skirting", color=self.pal["wood_lt"], rough=0.5)
        jpolys = [geom.joinery_polygon(j, self.m.wall(j["wall"]), r).buffer(5) for j in self.m.joinery
                  if j["room"] == r["id"]]
        faces = geom.room_faces(r, self.m.walls)
        for f in geom.room_edges(r, self.m.walls):          # one layer per edge: no overlapping slivers
            walls = sorted({x.wall for x in faces if x.n == f.n})
            cuts, u = self._face_cuts(f, r, walls)
            self._strip(key, f, cuts, u, 0, f.length, 0, self.soffit, 0, 2)
            if sk:
                ux, uy = u
                spans = [(0, f.length)]
                blocks = [(ta, tb) for ta, tb, sill, _ in cuts if sill == 0]
                for jp in jpolys:                          # no skirting behind joinery (E5.10)
                    seg = jp.intersection(geom.LineString([f.a, f.b]).buffer(30))
                    if not seg.is_empty:
                        ts = [((x - f.a[0]) * ux + (y - f.a[1]) * uy) for x, y in seg.exterior.coords] \
                            if seg.geom_type == "Polygon" else []
                        if ts:
                            blocks.append((min(ts), max(ts)))
                for ta, tb in blocks:
                    spans = [s for a, b in spans for s in ((a, min(b, ta)), (max(a, tb), b)) if s[1] - s[0] > 1] \
                        if any(not (tb <= a or ta >= b) for a, b in spans) else spans
                for a, b in spans:
                    self._strip(skm, f, [], u, a, b, 0, sk, 2, 14)

    def openings(self):
        m = self.m
        frame = self.mat("frame", color=TX.mix(T.GREY, T.INK, 0.45), rough=0.4, metal=0.6)
        glass = self.mat("glass", color=TX.mix(T.BLUE, T.PAPER, 0.85), glass=True)
        door = self.mat("door", color=TX.mix(T.PAPER, T.LIGHT, 0.3), rough=0.6)
        metal = self.mat("metal", color=self.pal["metal"], rough=0.3, metal=0.9)
        sillm = self.mat("threshold", color=self.pal["worktop"], rough=0.3)
        for o in m.openings:
            w = m.wall(o["wall"])
            lo, hi = geom.wall_offsets(w)
            ux, uy, _ = geom.unit(w["a"], w["b"])
            nx, ny = geom.left_normal(ux, uy)
            F = (tuple(w["a"]), (ux, uy), (nx, ny))
            a, b = o["offset"], o["offset"] + o["width"]
            mid = (lo + hi) / 2
            head = o.get("head", 2100)
            if o["kind"] in ("window", "ventilator", "sliding_door"):
                sill = o.get("sill", 0) if o["kind"] != "sliding_door" else 0
                fw = 55
                for u0, u1, z0, z1 in ((a, b, sill, sill + fw), (a, b, head - fw, head), (a, a + fw, sill, head),
                                       (b - fw, b, sill, head), ((a + b) / 2 - fw / 2, (a + b) / 2 + fw / 2, sill, head)):
                    self.mesh.frame_box(frame, F, u0, u1, mid - 30, mid + 30, z0, z1)
                self.mesh.frame_box(glass, F, a + fw, b - fw, mid - 3, mid + 3, sill + fw, head - fw)
                if sill > 0:
                    side = 1 if (hi - mid) > 0 else -1
                    for r in m.rooms:
                        sd = geom.room_side_of_wall(w, r)
                        if sd and geom.room_polygon(r).buffer(300).contains(Point(geom.point_on_wall(w, (a + b) / 2))):
                            side = 1 if sd == "left" else -1
                            break
                    face = hi if side > 0 else lo
                    self.mesh.frame_box(sillm, F, a - 30, b + 30, min(face, face + side * 40),
                                        max(face, face + side * 40), sill - 20, sill)
                    del face
                self.lights.append(dict(kind="portal", F=F, a=a + fw, b=b - fw, z0=sill + fw, z1=head - fw,
                                        out=lo if w.get("kind") == "external" else None))
            elif o["kind"] in ("door", "double_door"):
                side = o.get("swing", "left")
                face = geom.face_offset(w, side)
                d0, d1 = sorted((face, face - 40 if side == "left" else face + 40))
                self.mesh.frame_box(door, F, a + 3, b - 3, d0, d1, 0, head - 3)
                hx = b - 70 if o.get("hinge") == "start" else a + 70
                dd = (d1 + 12) if side == "left" else (d0 - 12)
                self.mesh.frame_box(metal, F, hx - 8, hx + 8, min(dd, dd + 1), max(dd, dd + 1) + 10, 950, 1130)

    def ceilings(self):
        m = self.m
        led = self.mat("led", emit=TX.mix(T.AMBER, T.PAPER, 0.72), strength=R["cove_strength"])
        for r in m.rooms:
            cdef = next((c for c in m.ceilings if c["room"] == r["id"]), None)
            if not cdef or not cdef.get("z"):
                continue
            room = geom.room_polygon(r)
            levels = [(room, cdef["z"], None)]
            for st in cdef.get("steps", []):
                levels.append((geom.step_polygon(r, st), st["z"], st))
            domes = [(geom.dome_polygon(d), d) for d in cdef.get("domes", [])]
            for i, (g, z, st) in enumerate(levels):
                region = g
                if i + 1 < len(levels):
                    region = region.difference(levels[i + 1][0])
                for dp, d in domes:
                    if geom.ceiling_z_at(r, {**cdef, "domes": []}, (dp.centroid.x, dp.centroid.y)) == z:
                        region = region.difference(dp)
                self.mesh.prism("ceiling", region, z, self.soffit)
                if st and st.get("light") == "cove":          # trough + lip + LED on the lower level (C3.9)
                    zl = levels[i - 1][1]
                    inner = g.buffer(-R["trough"], join_style=2)
                    self.mesh.prism("ceiling", g.difference(inner), zl, zl + 13)
                    self.mesh.prism("ceiling", inner.buffer(12, join_style=2).difference(inner), zl, zl + R["lip"])
                    self.mesh.prism(led, g.difference(g.buffer(-30, join_style=2)), zl + 13, zl + 18)
            for dp, d in domes:
                zs = geom.ceiling_z_at(r, {**cdef, "domes": []}, d["at"])
                rad = d["d"] / 2
                self.mesh.ellipsoid("ceiling", (d["at"][0], d["at"][1], zs), rad, rad, d["z"] - zs, seg=48, ring=12,
                                    z_from=0.0)
                if d.get("light") == "cove":
                    self.mesh.prism("ceiling", dp.buffer(R["trough"]).difference(dp), zs - 13, zs)
                    self.mesh.prism(led, dp.buffer(R["trough"] - 20).difference(dp.buffer(R["trough"] - 45)),
                                    zs - 13 + 13 + 1, zs - 13 + 18 + 1)
                    self.mesh.prism("ceiling", dp.buffer(R["trough"]).difference(dp.buffer(R["trough"] - 12)),
                                    zs - 13 - R["lip"] + 13, zs - 13 + 13)

    def features(self):
        m = self.m
        for wf in m.wall_features:
            r = m.room(wf["room"])
            faces = [f for f in geom.room_faces(r, m.walls) if f.wall == wf["wall"]]
            if not faces:
                continue
            w = m.wall(wf["wall"])
            pa, pb = geom.point_on_wall(w, wf["offset"]), geom.point_on_wall(w, wf["offset"] + wf["width"])
            key = self.finish_mat(wf.get("finish"))
            for f in faces:
                cuts, u = self._face_cuts(f, r)
                ux, uy = u
                ta = (pa[0] - f.a[0]) * ux + (pa[1] - f.a[1]) * uy
                tb = (pb[0] - f.a[0]) * ux + (pb[1] - f.a[1]) * uy
                ta, tb = max(min(ta, tb), 0), min(max(ta, tb), f.length)
                if tb - ta < 20:
                    continue
                z0, z1 = wf["z0"], wf["z1"]
                k = wf.get("kind")
                if k == "fluted":
                    self._strip(key, f, cuts, u, ta, tb, z0, z1, 2, 14)
                    t = ta + 10
                    while t + 24 < tb:
                        self._strip(key, f, cuts, u, t, t + 24, z0, z1, 14, 26)
                        t += 32
                elif k == "headboard":
                    z = z0
                    while z < z1 - 1:
                        self._strip(key, f, cuts, u, ta, tb, z + 4, min(z + 196, z1), 2, 62)
                        z += 200
                elif k in ("tile", "stone", "cladding"):
                    self._strip(key, f, cuts, u, ta, tb, z0, z1, 2, 10)
                else:
                    self._strip(key, f, cuts, u, ta, tb, z0, z1, 2, 4)

    def joinery(self, j):
        m = self.m
        room, wall = m.room(j["room"]), m.wall(j["wall"])
        (ox, oy), (ux, uy), (vx, vy) = wall_frame(wall, room)
        F = ((ox, oy), (ux, uy), (vx, vy))
        z0 = j.get("z", 0)
        H, D = j.get("height", 850), j["depth"]
        a, b = j["offset"], j["offset"] + j["width"]
        fin = self.finish_mat(j["finish"]) if j.get("finish") else self.mat("carcass", color=self.pal["joinery"],
                                                                             rough=0.55)
        dark = self.mat("shadow", color=TX.mix(T.GREY, T.INK, 0.6), rough=0.7)
        metal = self.mat("metal", color=self.pal["metal"], rough=0.3, metal=0.9)
        top_kind = j.get("kind") in ("kitchen_base", "vanity")
        gola = j.get("handles") == "gola"
        handles = j.get("handles", "bar")
        rows = j.get("rows") or [{"height": H, "modules": [{"w": j["width"], "type": "panel"}]}]
        plinth = R["plinth"] if z0 == 0 and (top_kind or j.get("kind") in ("wardrobe", "tall_unit", "shoe_rack",
                                                                             "crockery", "tv_unit")) else 0
        r1 = rows[0]["height"]
        body_top = z0 + (r1 - R["worktop"] if top_kind else H)
        self.mesh.frame_box(dark, F, a, b, 0, D - 60, z0, z0 + plinth) if plinth else None
        self.mesh.frame_box(fin, F, a, b, 0, D - R["front"], z0 + plinth, body_top)
        if top_kind:
            wt = self.finish_mat(j["worktop"]) if j.get("worktop") else self.mat("worktop", color=self.pal["worktop"],
                                                                               rough=0.25)
            self.mesh.frame_box(wt, F, a, b, 0, D + R["overhang"], z0 + r1 - R["worktop"], z0 + r1)
        g = R["gap"]
        zr = z0
        for ri, row in enumerate(rows):
            rz0 = zr + (plinth if ri == 0 else 0)
            rz1 = zr + row["height"] - (R["worktop"] if (ri == 0 and top_kind) else 0)
            if ri == 0 and gola and top_kind:
                self.mesh.frame_box(dark, F, a, b, D - R["front"] - 25, D - R["front"], rz1 - 50, rz1)
                rz1 -= 50
            u = a
            for k, md in enumerate(row["modules"]):
                u1 = u + md["w"]
                ty = md.get("type")
                if ty == "open":
                    self.mesh.frame_box(dark, F, u + g, u1 - g, D - R["front"] - 4, D - R["front"], rz0 + g, rz1 - g)
                elif ty == "drawer":
                    hts = [180, (rz1 - rz0 - 180) / 2, (rz1 - rz0 - 180) / 2]
                    zz = rz1
                    for h in hts:
                        self.mesh.frame_box(fin, F, u + g, u1 - g, D - R["front"], D, zz - h + g, zz - g)
                        if not gola and handles != "push":
                            self.mesh.frame_box(metal, F, (u + u1) / 2 - 80, (u + u1) / 2 + 80, D, D + 22, zz - 60, zz - 48)
                        zz -= h
                else:
                    self.mesh.frame_box(fin, F, u + g, u1 - g, D - R["front"], D, rz0 + g, rz1 - g)
                    if not gola and handles not in ("push", "gola") and ty not in ("panel", "filler", "appliance"):
                        hx = u1 - 60 if k % 2 == 0 else u + 60
                        zc = rz1 - 300 if ri == 0 and not top_kind and (rz1 - rz0) > 1200 else (rz1 - 120 if top_kind
                                                                                               else (rz0 + rz1) / 2)
                        self.mesh.frame_box(metal, F, hx - 8, hx + 8, D, D + 25, zc - 150, zc + 150)
                if ri == 0 and top_kind and ty == "sink":
                    bw = min(md["w"] - 150, 760)
                    cu = (u + u1) / 2
                    zt = z0 + r1
                    self.mesh.frame_box(metal, F, cu - bw / 2, cu + bw / 2, 90, D - 100, zt - 180, zt + 1)
                    self.mesh.frame_box(dark, F, cu - bw / 2 + 12, cu + bw / 2 - 12, 102, D - 112, zt - 170, zt + 2)
                    (px, py) = (ox + ux * cu + vx * 50, oy + uy * cu + vy * 50)
                    self.mesh.disc(metal, (px, py), 22, zt, zt + 260, seg=16)
                    self.mesh.frame_box(metal, F, cu - 12, cu + 12, 40, 250, zt + 240, zt + 262)
                if ri == 0 and top_kind and ty == "hob":
                    zt = z0 + r1
                    hob = self.mat("hob", color=TX.mix(T.INK, T.GREY, 0.1), rough=0.08)
                    cu = (u + u1) / 2
                    self.mesh.frame_box(hob, F, cu - 290, cu + 290, 60, 580, zt, zt + 5)
                    for du, dv, rr in ((-140, 180, 100), (140, 180, 75), (-140, 420, 75), (140, 420, 100)):
                        (px, py) = (ox + ux * (cu + du) + vx * dv, oy + uy * (cu + du) + vy * dv)
                        self.mesh.disc(dark, (px, py), rr, zt + 5, zt + 6, seg=24)
                u = u1
            zr += row["height"]

    def furniture(self, f):
        k, (w, d, h) = f.get("kind"), f["size"]
        F = furn_frame(f)
        P = self.pal
        fab = self.mat("fabric", color=P["fabric"], rough=0.95, sheen=True)
        cus = self.mat("cushion", color=P["cushion"], rough=0.95, sheen=True)
        oak = self.mat("oak", color=P["oak"], rough=0.5, grain=True)
        wood = self.mat("wood", color=P["wood"], rough=0.5)
        lin_ = self.mat("linen", color=P["linen"], rough=0.95, sheen=True)
        B = self.mesh.frame_box
        hw, hd = w / 2, d / 2
        if k in ("sofa", "armchair"):
            arm = 160 if k == "sofa" else 120
            for su in (-hw + 60, hw - 100):
                for sv in (-hd + 60, hd - 100):
                    B(wood, F, su, su + 40, sv, sv + 40, 0, 90)
            B(fab, F, -hw, hw, -hd, hd, 90, 380)
            B(fab, F, -hw, hw, -hd, -hd + 180, 380, h)
            B(fab, F, -hw, -hw + arm, -hd, hd, 380, 600)
            B(fab, F, hw - arm, hw, -hd, hd, 380, 600)
            n = 3 if w > 1800 else 2 if w > 1100 else 1
            cw = (w - 2 * arm) / n
            for i in range(n):
                u0 = -hw + arm + i * cw
                B(cus, F, u0 + 6, u0 + cw - 6, -hd + 180, hd - 20, 380, 480)
                B(cus, F, u0 + 10, u0 + cw - 10, -hd + 180, -hd + 340, 480, h - 30)
        elif k in ("coffee_table", "dining_table", "desk", "console"):
            th = 40 if k == "dining_table" else 30
            B(oak, F, -hw, hw, -hd, hd, h - th, h)
            if k == "desk":
                B(oak, F, -hw, -hw + 25, -hd, hd, 0, h - th)
                B(oak, F, hw - 25, hw, -hd, hd, 0, h - th)
            else:
                ins = 70
                for su in (-hw + ins, hw - ins - 50):
                    for sv in (-hd + ins, hd - ins - 50):
                        B(oak, F, su, su + 50, sv, sv + 50, 0, h - th)
        elif k == "side_table":
            r = min(w, d) / 2
            self.mesh.disc(oak, F[0], r, h - 25, h, seg=32)
            self.mesh.disc(wood, F[0], 28, 15, h - 25, seg=12)
            self.mesh.disc(wood, F[0], r * 0.55, 0, 15, seg=24)
        elif k == "chair":
            for su in (-hw + 30, hw - 60):
                for sv in (-hd + 30, hd - 60):
                    B(wood, F, su, su + 30, sv, sv + 30, 0, 440)
            B(fab, F, -hw, hw, -hd, hd, 440, 480)
            B(wood, F, -hw + 20, hw - 20, -hd + 10, -hd + 40, 480, h)
        elif k == "bed":
            dk = self.mat("fabric_dk", color=P["fabric_dk"], rough=0.95, sheen=True)
            throw = self.mat("throw", color=P["throw"], rough=0.95, sheen=True)
            B(wood, F, -hw + 40, hw - 40, -hd + 40, hd - 40, 0, 80)
            B(dk, F, -hw, hw, -hd, hd, 80, 300)
            B(lin_, F, -hw + 15, hw - 15, -hd + 15, hd - 15, 300, h)
            B(lin_, F, -hw - 5, hw + 5, -hd + 520, hd + 5, h - 80, h + 25)
            B(throw, F, -hw - 8, hw + 8, hd - 520, hd - 180, h + 25, h + 40)
            for s0, s1 in ((-hw + 60, -30), (30, hw - 60)):
                self.mesh.ellipsoid(cus, (*_at(F, (s0 + s1) / 2, -hd + 260), h + 60), (s1 - s0) / 2, 170, 70, seg=16,
                                    ring=6)
        elif k == "bedside":
            B(oak, F, -hw, hw, -hd, hd, 60, h)
            B(wood, F, -hw + 20, hw - 20, -hd + 20, hd - 20, 0, 60)
            B(self.mat("shadow", color=TX.mix(T.GREY, T.INK, 0.6), rough=0.7), F, -hw + 20, hw - 20, hd, hd + 1,
              h - 160, h - 156)
            self.mesh.disc(self.mat("metal", color=P["metal"], rough=0.3, metal=0.9), F[0], 60, h, h + 320, seg=16)
            shade = self.mat("shade", color=P["linen"], rough=0.9, emit=TX.mix(T.AMBER, T.PAPER, 0.7), strength=0.45)
            self.mesh.disc(shade, F[0], 150, h + 300, h + 520, seg=28)
        elif k == "rug":
            rb = self.mat("rug_border", color=P["rug_border"], rough=1.0)
            rg = self.mat("rug", color=P["rug"], rough=1.0, sheen=True)
            B(rb, F, -hw, hw, -hd, hd, 0, 8)
            B(rg, F, -hw + 120, hw - 120, -hd + 120, hd - 120, 8, 12)
        elif k == "plant":
            pot = self.mat("pot", color=P["stone_dark"], rough=0.8)
            leaf = self.mat("leaf", color=P["leaf"], rough=0.7)
            r = min(w, d) / 2
            self.mesh.disc(pot, F[0], r * 0.7, 0, h * 0.32, seg=24)
            rng = np.random.default_rng(int(f["at"][0] + f["at"][1]))
            for _ in range(7):
                dx, dy = rng.uniform(-r * 0.45, r * 0.45, 2)
                zc = rng.uniform(h * 0.5, h * 0.85)
                rr = rng.uniform(r * 0.45, r * 0.75)
                self.mesh.ellipsoid(leaf, (F[0][0] + dx, F[0][1] + dy, zc), rr, rr, rr * 1.1, seg=10, ring=6)
        else:
            B(oak, F, -hw, hw, -hd, hd, 0, h)

    def sanitary(self, s):
        w, d = s["size"][:2]
        F = furn_frame(s)
        white = self.mat("ceramic", color=TX.mix(T.PAPER, T.LIGHT, 0.05), rough=0.15)
        B = self.mesh.frame_box
        if s.get("kind") == "wc":
            B(white, F, -w / 2 + 60, w / 2 - 60, -d / 2, d / 2 - 40, 0, 400)
            B(white, F, -w / 2, w / 2, -d / 2, -d / 2 + 180, 400, 780)
        elif s.get("kind") == "shower":
            B(white, F, -w / 2, w / 2, -d / 2, d / 2, 0, 30)
        else:
            B(white, F, -w / 2, w / 2, -d / 2, d / 2, 0, 850)

    def fittings(self):
        """Lights from services.json (rule-placed downlights) and design fittings (pendants, tracks)."""
        m = self.m
        warm = TX.mix(T.AMBER, T.PAPER, 0.72)
        rim = self.mat("trim", color=TX.mix(T.PAPER, T.LIGHT, 0.1), rough=0.4)
        bulb = self.mat("bulb", emit=warm, strength=12.0)
        for it in self.sv:
            if it.get("system") != "lighting":
                continue
            r = m.room(it["room"])
            cdef = next((c for c in m.ceilings if c["room"] == it["room"]), None)
            zc = geom.ceiling_z_at(r, cdef, it["at"]) if cdef else self.soffit
            if it["kind"] == "downlight":
                self.mesh.disc(rim, it["at"], 45, zc - 4, zc - 1, seg=20)
                self.mesh.disc(bulb, it["at"], 32, zc - 5, zc - 4, seg=20)
                self.lights.append(dict(kind="spot", at=(*it["at"], zc - 8), power=R["downlight_w"]))
            elif it["kind"] == "pendant":
                self._pendant(it["at"], zc, warm)
            elif it["kind"] == "track" and it.get("path"):
                self._track(it["path"], zc)

    def _pendant(self, at, zc, warm):
        metal = self.mat("metal", color=self.pal["metal"], rough=0.3, metal=0.9)
        glow = self.mat("globe", color=TX.mix(T.PAPER, T.AMBER, 0.15), emit=warm, strength=4.0)
        self.mesh.disc(metal, at, 4, zc - 900, zc, seg=8)
        self.mesh.ellipsoid(glow, (at[0], at[1], zc - 1000), 160, 160, 130, seg=24, ring=10)
        self.lights.append(dict(kind="point", at=(at[0], at[1], zc - 1000), power=R["pendant_w"], r=0.12))

    def _track(self, path, zc):
        dark = self.mat("track", color=TX.mix(T.INK, T.GREY, 0.2), rough=0.4)
        for (x0, y0), (x1, y1) in zip(path, path[1:]):
            g = geom.LineString([(x0, y0), (x1, y1)]).buffer(18, cap_style=2)
            self.mesh.prism(dark, g, zc - 40, zc)
            L = math.hypot(x1 - x0, y1 - y0)
            for t in (0.2, 0.5, 0.8):
                p = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                self.mesh.disc(dark, p, 30, zc - 160, zc - 40, seg=12)
                self.lights.append(dict(kind="spot", at=(*p, zc - 165), power=R["downlight_w"] * 0.8))
            del L


def _at(F, u, v):
    (ox, oy), (ux, uy), (vx, vy) = F
    return (ox + ux * u + vx * v, oy + uy * u + vy * v)


def _tile_mm(name):
    import re
    m_ = re.search(r"(\d+)\s*[x×]\s*(\d+)", name or "")
    if not m_:
        return None
    a, b = int(m_.group(1)), int(m_.group(2))
    return (max(a, b), min(a, b))


# ------------------------------------------------------------------ Blender
def _blender(scene: Scene):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bsc = bpy.context.scene
    mats = {}
    for key, sp in scene.mats.items():
        mt = bpy.data.materials.new(key)
        if mt.node_tree is None:
            mt.use_nodes = True
        nt = mt.node_tree
        pr = nt.nodes.get("Principled BSDF")
        out = nt.nodes.get("Material Output")
        if sp.get("glass"):
            nt.nodes.remove(pr)
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            gl = nt.nodes.new("ShaderNodeBsdfGlossy")
            gl.inputs["Roughness"].default_value = 0.02
            mx = nt.nodes.new("ShaderNodeMixShader")
            mx.inputs["Fac"].default_value = 0.12
            tr.inputs["Color"].default_value = lin(sp["color"])
            nt.links.new(tr.outputs[0], mx.inputs[1])
            nt.links.new(gl.outputs[0], mx.inputs[2])
            nt.links.new(mx.outputs[0], out.inputs["Surface"])
            mats[key] = mt
            continue
        if "color" in sp:
            pr.inputs["Base Color"].default_value = lin(sp["color"])
        pr.inputs["Roughness"].default_value = sp.get("rough", 0.6)
        pr.inputs["Metallic"].default_value = sp.get("metal", 0.0)
        if sp.get("sheen"):
            for nm in ("Sheen Weight", "Sheen"):
                if nm in pr.inputs:
                    pr.inputs[nm].default_value = 0.4
                    break
        if "emit" in sp:
            pr.inputs["Emission Color"].default_value = lin(sp["emit"])
            pr.inputs["Emission Strength"].default_value = sp.get("strength", 1.0)
            if "color" not in sp:
                pr.inputs["Base Color"].default_value = lin(sp["emit"])
        tc = None
        if sp.get("image") or sp.get("grain") or sp.get("mottle"):
            tc = nt.nodes.new("ShaderNodeTexCoord")
        if sp.get("image"):
            im = nt.nodes.new("ShaderNodeTexImage")
            im.image = bpy.data.images.load(sp["image"])
            mp = nt.nodes.new("ShaderNodeMapping")
            if sp.get("plane"):
                b = [v / 1000 for v in sp["plane"]]
                mp.inputs["Scale"].default_value = (1 / (b[2] - b[0]), 1 / (b[3] - b[1]), 1)
                mp.inputs["Location"].default_value = (-b[0] / (b[2] - b[0]), -b[1] / (b[3] - b[1]), 0)
            else:
                s_ = 1 / sp.get("box", 1.2)
                mp.inputs["Scale"].default_value = (s_, s_, s_)
                im.projection = "BOX"
                im.projection_blend = 0.15
            nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
            nt.links.new(mp.outputs[0], im.inputs["Vector"])
            nt.links.new(im.outputs["Color"], pr.inputs["Base Color"])
        if sp.get("grain") or sp.get("mottle"):
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = 3.0 if sp.get("mottle") else 40.0
            nz.inputs["Detail"].default_value = 6.0
            if sp.get("grain"):
                mp = nt.nodes.new("ShaderNodeMapping")
                mp.inputs["Scale"].default_value = (1.0, 1.0, 0.04)
                nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
                nt.links.new(mp.outputs[0], nz.inputs["Vector"])
            else:
                nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            c = np.array(sp["color"])
            ramp.color_ramp.elements[0].color = lin(c * (0.82 if sp.get("grain") else 0.93))
            ramp.color_ramp.elements[1].color = lin(np.clip(c * (1.08 if sp.get("grain") else 1.04), 0, 1))
            nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], pr.inputs["Base Color"])
        mats[key] = mt
    for key, (verts, faces) in scene.mesh.parts.items():
        me = bpy.data.meshes.new(key)
        me.from_pydata([(x / 1000, y / 1000, z / 1000) for x, y, z in verts], [], faces)
        me.validate()
        me.materials.append(mats[key])
        ob = bpy.data.objects.new(key, me)
        bsc.collection.objects.link(ob)
    # lights
    warm = lin(TX.mix(T.AMBER, T.PAPER, 0.72))[:3]
    for L in scene.lights:
        if L["kind"] == "spot":
            ld = bpy.data.lights.new("dl", "SPOT")
            ld.energy = L["power"]
            ld.spot_size = math.radians(100)
            ld.spot_blend = 0.6
            ld.shadow_soft_size = 0.03
            ld.color = warm
            ob = bpy.data.objects.new("dl", ld)
            ob.location = tuple(v / 1000 for v in L["at"])
            bsc.collection.objects.link(ob)
        elif L["kind"] == "point":
            ld = bpy.data.lights.new("pt", "POINT")
            ld.energy = L["power"]
            ld.shadow_soft_size = L.get("r", 0.05)
            ld.color = warm
            ob = bpy.data.objects.new("pt", ld)
            ob.location = tuple(v / 1000 for v in L["at"])
            bsc.collection.objects.link(ob)
        elif L["kind"] == "portal" and L["out"] is not None:
            (ox, oy), (ux, uy), (nx, ny) = L["F"]
            u = (L["a"] + L["b"]) / 2
            c = (ox + ux * u + nx * (L["out"] - 5), oy + uy * u + ny * (L["out"] - 5), (L["z0"] + L["z1"]) / 2)
            ld = bpy.data.lights.new("portal", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = (L["b"] - L["a"]) / 1000, (L["z1"] - L["z0"]) / 1000
            try:
                ld.cycles.is_portal = True
            except AttributeError:
                continue
            ob = bpy.data.objects.new("portal", ld)
            ob.location = tuple(v / 1000 for v in c)
            # area light emits along its local -Z: point it from outside (-n) towards inside (+n)
            import mathutils
            zdir = mathutils.Vector((-nx, -ny, 0))
            xdir = mathutils.Vector((ux, uy, 0))
            ydir = zdir.cross(xdir)
            ob.matrix_world = mathutils.Matrix((
                (xdir.x, ydir.x, zdir.x, ob.location.x), (xdir.y, ydir.y, zdir.y, ob.location.y),
                (xdir.z, ydir.z, zdir.z, ob.location.z), (0, 0, 0, 1)))
            bsc.collection.objects.link(ob)
    s_, el, az = R["sun"]
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = s_
    sun.angle = math.radians(1.5)
    sun.color = lin(TX.mix(T.PAPER, T.AMBER, 0.12))[:3]
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(90 - el), 0, math.radians(az))   # az 315: light travels NE (sun in the SW)
    bsc.collection.objects.link(so)
    wd = bpy.data.worlds.new("sky")
    if wd.node_tree is None:
        wd.use_nodes = True
    bg = wd.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = lin(TX.mix(T.BLUE, T.PAPER, 0.62))
    bg.inputs["Strength"].default_value = R["sky"]
    bsc.world = wd
    # render settings
    bsc.render.engine = "CYCLES"
    cy = bsc.cycles
    cy.device = "CPU"
    cy.samples = R["samples"]
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = R["threshold"]
    cy.use_denoising = True
    cy.max_bounces = R["bounces"]
    cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 3, 2, 4, 8
    cy.sample_clamp_indirect = 6.0
    cy.caustics_reflective = cy.caustics_refractive = False
    bsc.render.resolution_x = bsc.render.resolution_y = R["size"]
    bsc.render.image_settings.file_format = "PNG"
    try:
        bsc.view_settings.view_transform = "AgX"
        bsc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    bsc.view_settings.exposure = R["exposure"]
    return bpy, bsc


def _camera(bpy, bsc, cam):
    cd = bpy.data.cameras.new(cam["id"])
    cd.lens = cam.get("lens", 20)
    cd.sensor_width = 36
    cd.sensor_fit = "HORIZONTAL"
    cd.clip_start = 0.05
    ob = bpy.data.objects.new(cam["id"], cd)
    ex, ey, ez = cam["eye"]
    tx, ty = cam["target"][:2]
    yaw = math.atan2(ty - ey, tx - ex)
    ob.location = (ex / 1000, ey / 1000, ez / 1000)
    ob.rotation_euler = (math.pi / 2, 0, yaw - math.pi / 2)    # level: pitch 0, so verticals stay vertical
    bsc.collection.objects.link(ob)
    bsc.camera = ob
    return ob


# ------------------------------------------------------------------ cache + CLI
def scene_hash(root: Path):
    h = hashlib.sha1()
    for n in ("survey.json", "design.json", "services.json"):
        p = root / n
        if p.exists():
            h.update(p.read_bytes())
    for mod in ("render.py", "texture.py", "theme.py", "geom.py"):     # cameras are in each key
        h.update((Path(__file__).parent / mod).read_bytes())
    h.update(json.dumps(R, sort_keys=True).encode())
    return h.hexdigest()


def all_cameras(m):
    return [c for r in V3.board_rooms(m) for c in V3.room_cameras(m, r)]


def manifest(root: Path):
    p = root / "out" / "renders" / "renders.json"
    return json.loads(p.read_text()) if p.exists() else {}


def is_current(root: Path, m, cam):
    man = manifest(root)
    e = man.get(cam["id"])
    png = root / "out" / "renders" / f"{cam['id']}.png"
    return bool(e) and png.exists() and e.get("key") == _key(root, cam)


def _key(root, cam):
    return hashlib.sha1((scene_hash(root) + json.dumps(cam, sort_keys=True)).encode()).hexdigest()


def render(root: Path, only=None, force=False):
    m = load(root)
    sv = json.loads((root / "services.json").read_text())["items"] if (root / "services.json").exists() else []
    cams = [c for c in all_cameras(m) if not only or c["id"] in only]
    todo = [c for c in cams if force or not is_current(root, m, c)]
    out = root / "out" / "renders"
    out.mkdir(parents=True, exist_ok=True)
    if not todo:
        print(f"renders: {len(cams)} current, nothing to do")
        return 0
    sc = Scene(m, root, sv)
    sc.build()
    bpy, bsc = _blender(sc)
    man = manifest(root)
    for c in todo:
        t = time.time()
        _camera(bpy, bsc, c)
        bsc.render.filepath = str(out / f"{c['id']}.png")
        bpy.ops.render.render(write_still=True)
        man[c["id"]] = dict(c, key=_key(root, c), seconds=round(time.time() - t, 1), samples=R["samples"],
                            size=R["size"])
        (out / "renders.json").write_text(json.dumps(man, indent=1))
        print(f"render ✓ {c['id']}  {time.time() - t:.0f}s")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.render")
    ap.add_argument("project", type=Path)
    ap.add_argument("--camera", action="append")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--size", type=int)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.samples:
        R["samples"] = a.samples
    if a.size:
        R["size"] = a.size
    return render(a.project, a.camera, a.force)


if __name__ == "__main__":
    sys.exit(main())

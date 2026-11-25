"""Services by rule: writes projects/<name>/services.json (agents/STANDARDS.md §6).

    python -m atelier.services projects/            # every project
    python -m atelier.services projects/sample

Each rule R6.n is one function below. Generated items cite their rule; items from
services_overrides.json carry "source": "override". IDs are <PREFIX>-<room>-<nn>
and stay stable while the data does not change, so overrides can name them.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from atelier import geom
from atelier.model import Model, load

HABITABLE = {"living", "dining", "living_dining", "bedroom", "master_bedroom", "study"}
WET = {"bath", "toilet"}
AC_ROOMS = {"living", "living_dining", "bedroom", "master_bedroom", "study"}
FAN_ROOMS = {"living", "living_dining", "bedroom", "master_bedroom"}
DOORLIKE = {"door", "double_door", "sliding_door", "opening"}

PREFIX = {
    "switchboard": "SB", "switch_2way": "S2", "socket": "SK", "socket_usb": "SU", "double_socket": "DS",
    "lan": "LN", "tv_power": "TV", "worktop_socket": "WK", "db": "DB", "vdp": "VD", "router": "RT",
    "geyser_point": "GP", "ac_isolator": "AI", "wm_socket": "WM", "ip44_socket": "IP",
    "downlight": "DL", "fan": "FN", "cove": "CV", "exhaust": "EX",
    "pendant": "PD", "track": "TK", "chandelier": "CH", "spotlight": "SP", "strip": "ST",
    "cold": "CW", "hot": "HW", "waste": "WW", "soil": "SL", "floor_trap": "FT", "geyser": "GY", "hot_run": "HR",
    "split": "AC", "ducted": "AD", "odu": "OU", "supply_grille": "SG", "return_grille": "RG", "refrigerant": "RF",
}


class Builder:
    def __init__(self, m: Model):
        self.m = m
        self.items: list[dict] = []
        self.count = defaultdict(int)
        self.faces = {r["id"]: geom.room_faces(r, m.walls) for r in m.rooms}
        self.poly = {r["id"]: geom.room_polygon(r) for r in m.rooms}

    # ------------------------------------------------------------ helpers
    def add(self, system, kind, room, at, z, rule, **kw):
        key = (PREFIX[kind], room)
        self.count[key] += 1
        it = {"id": f"{PREFIX[kind]}-{room}-{self.count[key]:02d}", "system": system, "kind": kind,
              "room": room, "at": [round(at[0]), round(at[1])], "z": z, "rule": rule}
        it.update({k: v for k, v in kw.items() if v is not None})
        self.items.append(it)
        return it

    @staticmethod
    def into(face):
        """Compass degrees pointing into the room from a face (CCW room: left normal)."""
        ux, uy = (face.b[0] - face.a[0]) / face.length, (face.b[1] - face.a[1]) / face.length
        nx, ny = -uy, ux
        return round(math.degrees(math.atan2(nx, ny))) % 360

    @staticmethod
    def at_t(face, t):
        ux, uy = (face.b[0] - face.a[0]) / face.length, (face.b[1] - face.a[1]) / face.length
        return (face.a[0] + ux * t, face.a[1] + uy * t)

    @staticmethod
    def t_of(face, p):
        ux, uy = (face.b[0] - face.a[0]) / face.length, (face.b[1] - face.a[1]) / face.length
        return (p[0] - face.a[0]) * ux + (p[1] - face.a[1]) * uy

    def nearest_face(self, room, p):
        best = min(self.faces[room], key=lambda f: LineString([f.a, f.b]).distance(Point(p)))
        return best, min(max(self.t_of(best, p), 0), best.length)

    def blocked(self, room, face, margin=150):
        """Intervals along a face taken by openings, joinery and the end margins."""
        out = [(-1e9, margin), (face.length - margin, 1e9)]
        w = self.m.wall(face.wall)
        for o in self.m.openings_on(face.wall):
            t0, t1 = sorted((self.t_of(face, geom.point_on_wall(w, o["offset"])),
                             self.t_of(face, geom.point_on_wall(w, o["offset"] + o["width"]))))
            out.append((t0 - 100, t1 + 100))
        for j in self.m.joinery:
            if j["wall"] == face.wall and j["room"] == room:
                t0, t1 = sorted((self.t_of(face, geom.point_on_wall(w, j["offset"])),
                                 self.t_of(face, geom.point_on_wall(w, j["offset"] + j["width"]))))
                out.append((t0, t1))
        return out

    def free_stretches(self, room, face, margin=150):
        cuts = sorted(self.blocked(room, face, margin))
        free, cur = [], -1e9
        for a, b in cuts:
            if a > cur:
                free.append((max(cur, 0), min(a, face.length)))
            cur = max(cur, b)
        return [(a, b) for a, b in free if b - a > 1]

    def wall_device(self, system, kind, room, face, t, z, rule, **kw):
        t = min(max(t, 60), face.length - 60)
        return self.add(system, kind, room, self.at_t(face, t), z, rule, wall=face.wall, into=self.into(face), **kw)

    def rooms_of(self, types):
        return [r for r in self.m.rooms if r.get("type") in types]

    def room_touching(self, poly, exclude=None):
        return [r["id"] for r in self.m.rooms if r["id"] != exclude and poly.buffer(3).intersects(self.poly[r["id"]])]

    def face_on_wall(self, room, wall_id, near):
        cands = [f for f in self.faces[room] if f.wall == wall_id]
        if not cands:
            return None, None
        f = min(cands, key=lambda f: LineString([f.a, f.b]).distance(Point(near)))
        return f, self.t_of(f, near)

    # ------------------------------------------------------------ R6.1 / R6.2 switches
    def entry_of(self, r):
        rp = self.poly[r["id"]]
        best = None
        for o in self.m.openings:
            if o["kind"] not in DOORLIKE:
                continue
            w = self.m.wall(o["wall"])
            cut = geom.opening_polygon(w, o, 2)
            if not cut.buffer(3).intersects(rp):
                continue
            sp = geom.swing_polygon(w, o)
            score = 2 if (sp is not None and rp.contains(sp.centroid)) else 1
            if best is None or score > best[0]:
                best = (score, o)
        return best[1] if best else None

    def r6_1_switches(self):
        for r in self.m.rooms:
            if r.get("type") == "shaft":
                continue
            wet = r.get("type") in WET
            o = self.entry_of(r)
            if o is not None:
                w = self.m.wall(o["wall"])
                target = r["id"]
                if wet:
                    others = self.room_touching(geom.opening_polygon(w, o, 2), exclude=r["id"])
                    target = others[0] if others else r["id"]
                latch_end = o.get("hinge") != "end"
                off = o["offset"] + o["width"] + 150 if latch_end else o["offset"] - 150
                if not (60 < off < geom.wall_length(w) - 60):
                    off = o["offset"] - 150 if latch_end else o["offset"] + o["width"] + 150
                f, t = self.face_on_wall(target, w["id"], geom.point_on_wall(w, off))
                if f is None:
                    continue
                self.wall_device("switching", "switchboard", target, f, t, 1200, "R6.2" if wet else "R6.1",
                                 serves=r["id"])
                continue
            for v in self.m.voids:                     # removed wall stretch
                if not v.buffer(3).intersects(self.poly[r["id"]]):
                    continue
                for f in self.faces[r["id"]]:
                    for end, t in ((f.a, 150), (f.b, f.length - 150)):
                        if v.buffer(15).contains(Point(end)):
                            self.wall_device("switching", "switchboard", r["id"], f, t, 1200, "R6.1",
                                             serves=r["id"])
                            break
                    else:
                        continue
                    break
                break

    # ------------------------------------------------------------ R6.3 general sockets
    def r6_3_sockets(self):
        tv_walls = {(j["room"], j["wall"]) for j in self.m.joinery if j.get("kind") == "tv_unit"}
        for r in self.rooms_of(HABITABLE):
            for f in self.faces[r["id"]]:
                w = self.m.wall(f.wall)
                if f.length < 1800 or w.get("kind") == "parapet" or (r["id"], f.wall) in tv_walls:
                    continue
                free = [s for s in self.free_stretches(r["id"], f) if s[1] - s[0] >= 600]
                if free:
                    a, b = max(free, key=lambda s: s[1] - s[0])
                    self.wall_device("power", "socket", r["id"], f, (a + b) / 2, 300, "R6.3")

    # ------------------------------------------------------------ R6.4 / R6.5 bedside, desk
    def r6_4_bedside(self):
        for b in self.m.furniture:
            if b.get("kind") != "bedside":
                continue
            f, t = self.nearest_face(b["room"], b["at"])
            self.wall_device("power", "socket_usb", b["room"], f, t, 600, "R6.4")
            t2 = t + 230 if t + 230 < f.length - 60 else t - 230
            self.wall_device("switching", "switch_2way", b["room"], f, t2, 750, "R6.4")

    def r6_5_desk(self):
        for d in self.m.furniture:
            if d.get("kind") != "desk":
                continue
            f, t = self.nearest_face(d["room"], d["at"])
            self.wall_device("power", "double_socket", d["room"], f, t - 150, 850, "R6.5")
            self.wall_device("power", "lan", d["room"], f, t + 150, 850, "R6.5")

    # ------------------------------------------------------------ R6.6 TV
    def r6_6_tv(self):
        for j in self.m.joinery:
            if j.get("kind") != "tv_unit":
                continue
            w = self.m.wall(j["wall"])
            c = geom.point_on_wall(w, j["offset"] + j["width"] / 2)
            f, t = self.face_on_wall(j["room"], w["id"], c)
            self.wall_device("power", "tv_power", j["room"], f, t - 150, 1100, "R6.6")
            self.wall_device("power", "lan", j["room"], f, t + 150, 1100, "R6.6")

    # ------------------------------------------------------------ R6.7 worktop
    def r6_7_worktop(self):
        for j in self.m.joinery:
            if j.get("kind") != "kitchen_base":
                continue
            w = self.m.wall(j["wall"])
            mods, o = [], 0
            for md in j["rows"][0]["modules"]:
                mods.append((o, o + md["w"], md["type"]))
                o += md["w"]
            avoid = [(a - 150, b + 150) for a, b, ty in mods if ty in ("sink", "hob")]
            s = 450
            while s <= j["width"] - 150:
                if not any(a < s < b for a, b in avoid):
                    p = geom.point_on_wall(w, j["offset"] + s)
                    f, t = self.face_on_wall(j["room"], w["id"], p)
                    if f is not None:
                        self.wall_device("power", "worktop_socket", j["room"], f, t, 1100, "R6.7")
                    s += 900
                else:
                    s += 150
        return

    # ------------------------------------------------------------ R6.8 wet rooms, WM
    def r6_8_wet(self):
        for r in self.rooms_of(WET):
            rid = r["id"]
            shower = next((s for s in self.m.sanitary if s["room"] == rid and s["kind"] in ("shower", "bathtub")), None)
            ref = shower["at"] if shower else list(self.poly[rid].centroid.coords[0])
            f, t = self.nearest_face(rid, ref)
            self.wall_device("power", "geyser_point", rid, f, t, 2000, "R6.8", ip="IP44")
            self.wall_device("plumbing", "geyser", rid, f, t, 1800, "R6.8")
            vent = None
            for o in self.m.openings:
                if o["kind"] in ("ventilator", "window") and self.m.wall(o["wall"]).get("kind") == "external":
                    if geom.opening_polygon(self.m.wall(o["wall"]), o, 2).buffer(3).intersects(self.poly[rid]):
                        vent = o
                        break
            if vent:
                w = self.m.wall(vent["wall"])
                c = geom.point_on_wall(w, vent["offset"] + vent["width"] / 2)
                fv, tv = self.face_on_wall(rid, w["id"], c)
                self.wall_device("lighting", "exhaust", rid, fv, tv, 2100, "R6.8", ip="IP44", note=f"in {vent['id']}")
            else:
                c = self.poly[rid].centroid
                self.add("lighting", "exhaust", rid, (c.x, c.y), None, "R6.8", ip="IP44",
                         note="ceiling exhaust, ducted (no external wall)")
            for j in self.m.joinery:
                if j["room"] == rid and j.get("kind") == "vanity":
                    w = self.m.wall(j["wall"])
                    end = j["offset"] + j["width"] + 150
                    off = end if end < geom.wall_length(w) - 60 else j["offset"] - 150
                    fj, tj = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, off))
                    if fj is not None:
                        self.wall_device("power", "ip44_socket", rid, fj, tj, 1100, "R6.8", ip="IP44")
        for s in self.m.sanitary:
            if s["kind"] == "washing_machine":
                f, t = self.nearest_face(s["room"], s["at"])
                self.wall_device("power", "wm_socket", s["room"], f, t + 350, 1100, "R6.8", ip="IP44")

    # ------------------------------------------------------------ R6.9 entry
    def r6_9_entry(self):
        for o in self.m.openings:
            w = self.m.wall(o["wall"])
            if o["kind"] not in ("door", "double_door") or w.get("kind") != "external":
                continue
            rooms = self.room_touching(geom.opening_polygon(w, o, 2))
            if not rooms:
                continue
            rid = rooms[0]
            hinge_end = o.get("hinge") == "end"
            h_off = o["offset"] + o["width"] + 400 if hinge_end else o["offset"] - 400
            l_off = o["offset"] - 450 if hinge_end else o["offset"] + o["width"] + 450
            f, t = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, h_off))
            if f is not None:
                self.wall_device("power", "db", rid, f, t, 1500, "R6.9")
                self.wall_device("power", "router", rid, f, t - 450 if t > 600 else t + 450, 2100, "R6.9")
            f, t = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, l_off))
            if f is not None:
                self.wall_device("power", "vdp", rid, f, t, 1400, "R6.9")
            break

    # ------------------------------------------------------------ R6.10 AC
    def r6_10_ac(self):
        for r in self.rooms_of(AC_ROOMS):
            rid = r["id"]
            feats = [wf for wf in self.m.wall_features if wf["room"] == rid]
            ceil = next((c for c in self.m.ceilings if c["room"] == rid), None)
            tray = bool(ceil and ceil.get("steps"))
            ext = [f for f in self.faces[rid] if self.m.wall(f.wall).get("kind") == "external"]
            if not ext:
                continue
            if feats and tray:
                f = max(ext, key=lambda f: f.length)
                t = f.length / 2
                face_pt = self.at_t(f, t)
                step = geom.step_polygon(r, ceil["steps"][0])
                inset = max(300, min(900, step.exterior.distance(Point(face_pt))))
                ang = math.radians(self.into(f))
                ix, iy = math.sin(ang), math.cos(ang)
                unit = (face_pt[0] + ix * inset * 0.42, face_pt[1] + iy * inset * 0.42)
                odu = self._outside(f, t)
                self.add("ac", "ducted", rid, unit, None, "R6.10", size=[1000, round(inset * 0.6)], into=self.into(f),
                         odu=[round(odu[0]), round(odu[1])], note="concealed in ceiling drop")
                self.add("ac", "odu", rid, odu, 0, "R6.10", size=[900, 350], into=self.into(f))
                self.add("ac", "refrigerant", rid, unit, None, "R6.10",
                         path=[[round(unit[0]), round(unit[1])], [round(face_pt[0]), round(face_pt[1])],
                               [round(odu[0]), round(odu[1])]])
                if not step.is_empty:
                    cs = list(step.exterior.coords)
                    edges = [(cs[i], cs[i + 1]) for i in range(len(cs) - 1)]
                    a, b = min(edges, key=lambda e: LineString(e).distance(Point(unit)) - LineString(e).length * 1e-4)
                    L = math.dist(a, b)
                    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                    m0 = (a[0] + ux * L * 0.2, a[1] + uy * L * 0.2)
                    m1 = (a[0] + ux * L * 0.8, a[1] + uy * L * 0.8)
                    self.add("ac", "supply_grille", rid, ((m0[0] + m1[0]) / 2, (m0[1] + m1[1]) / 2), None, "R6.10",
                             path=[[round(m0[0]), round(m0[1])], [round(m1[0]), round(m1[1])]])
                ret = (unit[0] + ix * 0, unit[1] + iy * 0)
                rx, ry = self.at_t(f, min(t + 900, f.length - 400))
                self.add("ac", "return_grille", rid, (rx + ix * inset * 0.5, ry + iy * inset * 0.5), None, "R6.10",
                         size=[600, 300])
                _ = ret
                continue
            # split
            if feats:
                fw = feats[0]
                fwall = self.m.wall(fw["wall"])
                ffaces = [f for f in self.faces[rid] if f.wall == fwall["id"]]
                fdir = self.into(ffaces[0]) if ffaces else None
                cands = [f for f in self.faces[rid] if fdir is not None and abs(((self.into(f) - fdir) % 360) - 180) < 10]
            else:
                cands = []
            cands = cands or ext
            best = None
            for f in cands:
                for a, b in self.free_stretches(rid, f, 300):
                    if best is None or b - a > best[2] - best[1]:
                        best = (f, a, b)
            if not best:
                continue
            f, a, b = best
            t = (a + b) / 2
            unit = self.wall_device("ac", "split", rid, f, t, 2150, "R6.10", size=[900, 250])
            self.wall_device("power", "ac_isolator", rid, f, t + 600 if t + 600 < f.length - 60 else t - 600, 2200,
                             "R6.10")
            ef = min(ext, key=lambda e: LineString([e.a, e.b]).distance(Point(unit["at"])))
            # run along the unit's own face to its end nearest the external face, then along that face
            ends = [(150, self.at_t(f, 150)), (f.length - 150, self.at_t(f, f.length - 150))]
            _, along = min(ends, key=lambda e: LineString([ef.a, ef.b]).distance(Point(e[1])))
            et = min(max(self.t_of(ef, along), 300), ef.length - 300)
            odu = self._outside(ef, et)
            unit["odu"] = [round(odu[0]), round(odu[1])]
            self.add("ac", "odu", rid, odu, 0, "R6.10", size=[900, 350], into=self.into(ef))
            corner = self.at_t(ef, et)
            path = [unit["at"], [round(along[0]), round(along[1])]]
            if ef is not f:
                path.append([round(corner[0]), round(corner[1])])
            path.append([round(odu[0]), round(odu[1])])
            self.add("ac", "refrigerant", rid, unit["at"], None, "R6.10", path=path)

    def _outside(self, f, t):
        w = self.m.wall(f.wall)
        p = self.at_t(f, t)
        ang = math.radians(self.into(f))
        ix, iy = math.sin(ang), math.cos(ang)
        d = w["t"] + 450
        return (p[0] - ix * d, p[1] - iy * d)

    # ------------------------------------------------------------ R6.11 – R6.13 lighting
    def r6_11_fans(self):
        for r in self.rooms_of(FAN_ROOMS):
            c = self.poly[r["id"]].centroid
            self.add("lighting", "fan", r["id"], (c.x, c.y), None, "R6.11", size=[1200, 1200])

    def r6_12_downlights(self, pitch=1200):
        """Grid of `pitch`, centred on the room (or offset half a pitch if that fits more)."""
        for r in self.m.rooms:
            rid = r["id"]
            poly = self.poly[rid]
            ok_zone = poly.buffer(-500)
            j_polys = [geom.joinery_polygon(j, self.m.wall(j["wall"]), r) for j in self.m.joinery if j["room"] == rid]
            joinery = unary_union(j_polys) if j_polys else None
            fans = [Point(i["at"]) for i in self.items if i["room"] == rid and i["kind"] == "fan"]
            ceil = next((c for c in self.m.ceilings if c["room"] == rid), None) or {}
            steps = [geom.step_polygon(r, s_).boundary for s_ in ceil.get("steps", [])]
            domes = [geom.dome_polygon(d_) for d_ in ceil.get("domes", [])]
            pend = [Point(l_["at"]) for l_ in ceil.get("lights", []) if l_.get("at")]
            tracks = [LineString(l_["path"]) for l_ in ceil.get("lights", []) if l_.get("path")]
            c = poly.centroid
            x0, y0, x1, y1 = poly.bounds

            def grid(px, py):
                pts = []
                for i in range(math.floor((x0 - c.x) / pitch) - 1, math.ceil((x1 - c.x) / pitch) + 2):
                    for k in range(math.floor((y0 - c.y) / pitch) - 1, math.ceil((y1 - c.y) / pitch) + 2):
                        p = Point(c.x + px + i * pitch, c.y + py + k * pitch)
                        if ok_zone.is_empty or not ok_zone.contains(p):
                            continue
                        if joinery is not None and p.distance(joinery) < 450:
                            continue
                        if any(p.distance(f) < 700 for f in fans):
                            continue
                        if any(p.distance(s_) < 300 for s_ in steps):
                            continue
                        if any(p.distance(d_) < 300 for d_ in domes):
                            continue
                        if any(p.distance(q) < 500 for q in pend) or any(p.distance(t_) < 400 for t_ in tracks):
                            continue
                        pts.append(p)
                return pts
            h = pitch / 2
            best = max((grid(px, py) for px, py in ((0, 0), (h, 0), (0, h), (h, h))), key=len)
            ip = "IP44" if r.get("type") in WET else None
            for p in best:
                self.add("lighting", "downlight", rid, (p.x, p.y), None, "R6.12", ip=ip)
            if not best:
                lp = geom.label_point(r)
                self.add("lighting", "downlight", rid, (lp.x, lp.y), None, "R6.12", ip=ip,
                         note="room too small for the grid: one centred")

    def r6_13_cove(self):
        """Coves in the trough 75 inside each step edge (C3.10) and inside domes; design fittings copied."""
        for cdef in self.m.ceilings:
            r = self.m.room(cdef["room"])
            if not r:
                continue
            for s_ in cdef.get("steps", []):
                if s_.get("light", "cove") != "cove":
                    continue
                band = geom.step_polygon(r, s_).buffer(-75, join_style=2)
                if band.is_empty:
                    continue
                band = max(getattr(band, "geoms", [band]), key=lambda g: g.area)
                pts = [[round(x), round(y)] for x, y in band.exterior.coords]
                c = band.centroid
                self.add("lighting", "cove", r["id"], (c.x, c.y), None, "R6.13", path=pts, level=s_["z"])
            for d in cdef.get("domes", []):
                if d.get("light") == "cove":
                    ring = Point(d["at"]).buffer(d["d"] / 2 - 75, 48)
                    pts = [[round(x), round(y)] for x, y in ring.exterior.coords]
                    self.add("lighting", "cove", r["id"], d["at"], None, "R6.13", path=pts, note=f"in dome {d.get('id')}")
            for lt in cdef.get("lights", []):
                k = lt.get("kind")
                if k not in PREFIX:
                    continue
                at = lt.get("at") or [round(sum(p[0] for p in lt["path"]) / len(lt["path"])),
                                      round(sum(p[1] for p in lt["path"]) / len(lt["path"]))]
                self.add("lighting", k, r["id"], at, None, "design", path=lt.get("path"), note=lt.get("note"))

    # ------------------------------------------------------------ R6.14 plumbing
    def r6_14_plumbing(self):
        for j in self.m.joinery:
            if j.get("kind") not in ("kitchen_base", "vanity"):
                continue
            w = self.m.wall(j["wall"])
            o = j["offset"]
            for md in j["rows"][0]["modules"]:
                if md["type"] == "sink":
                    c = geom.point_on_wall(w, o + md["w"] / 2)
                    f, t = self.face_on_wall(j["room"], w["id"], c)
                    self.wall_device("plumbing", "cold", j["room"], f, t - 100, 550, "R6.14")
                    if self.m.room(j["room"]).get("type") in WET:
                        self.wall_device("plumbing", "hot", j["room"], f, t + 100, 550, "R6.14")
                    self.wall_device("plumbing", "waste", j["room"], f, t, 450, "R6.14")
                o += md["w"]
        for s in self.m.sanitary:
            f, t = self.nearest_face(s["room"], s["at"])
            if s["kind"] == "wc":
                self.wall_device("plumbing", "cold", s["room"], f, t + 250, 150, "R6.14")
                fx, fy = geom.compass_to_vec(s.get("facing", "N"))
                back = (s["at"][0] - fx * (s["size"][1] / 2 - 150), s["at"][1] - fy * (s["size"][1] / 2 - 150))
                self.add("plumbing", "soil", s["room"], back, 0, "R6.14")
            elif s["kind"] in ("shower", "bathtub"):
                self.wall_device("plumbing", "cold", s["room"], f, t - 100, 1000, "R6.14", note="mixer; head h2100")
                self.wall_device("plumbing", "hot", s["room"], f, t + 100, 1000, "R6.14", note="mixer")
                self.add("plumbing", "floor_trap", s["room"], s["at"], 0, "R6.14")
            elif s["kind"] == "washing_machine":
                self.wall_device("plumbing", "cold", s["room"], f, t - 150, 1000, "R6.14")
                self.wall_device("plumbing", "waste", s["room"], f, t + 50, 600, "R6.14")
        for g in [i for i in self.items if i["kind"] == "geyser"]:
            for h in [i for i in self.items if i["kind"] == "hot" and i["room"] == g["room"]]:
                self.add("plumbing", "hot_run", g["room"], g["at"], None, "R6.14", path=[g["at"], h["at"]])

    # ------------------------------------------------------------ switch control links
    def link_controls(self):
        light = defaultdict(list)
        for i in self.items:
            if i["system"] == "lighting":
                light[i["room"]].append(i)
        for sb in [i for i in self.items if i["kind"] == "switchboard"]:
            serves = sb.get("serves", sb["room"])
            ctl = [i["id"] for i in light.get(serves, [])]
            ctl += [i["id"] for i in self.items if i["kind"] == "geyser_point" and i["room"] == serves]
            sb["controls"] = ctl
        for s2 in [i for i in self.items if i["kind"] == "switch_2way"]:
            s2["controls"] = [i["id"] for i in light.get(s2["room"], []) if i["kind"] == "downlight"]

    def run(self):
        self.r6_11_fans()                 # fans first: downlights keep clear of them
        self.r6_12_downlights()
        self.r6_13_cove()
        self.r6_8_wet()
        self.r6_1_switches()
        self.r6_3_sockets()
        self.r6_4_bedside()
        self.r6_5_desk()
        self.r6_6_tv()
        self.r6_7_worktop()
        self.r6_9_entry()
        self.r6_10_ac()
        self.r6_14_plumbing()
        self.link_controls()
        return self.items


def apply_overrides(items, ov):
    """R6.15. Returns (items, report lines, errors)."""
    ids = {i["id"]: i for i in items}
    rep, errs = [], []
    for rid in ov.get("remove", []):
        if rid not in ids:
            errs.append(f"remove: unknown id {rid}")
            continue
        items = [i for i in items if i["id"] != rid]
        for i in items:
            if "controls" in i:
                i["controls"] = [c for c in i["controls"] if c != rid]
        rep.append(f"removed {rid}")
    ids = {i["id"]: i for i in items}
    for mv in ov.get("move", []):
        it = ids.get(mv.get("id"))
        if not it:
            errs.append(f"move: unknown id {mv.get('id')}")
            continue
        if "at" in mv:
            it["at"] = mv["at"]
        if "z" in mv:
            it["z"] = mv["z"]
        it["source"] = "override"
        rep.append(f"moved {it['id']} to {it['at']} z {it['z']}")
    for add in ov.get("add", []):
        if add.get("id") in ids:
            errs.append(f"add: id {add['id']} already exists")
            continue
        items.append(dict(add, source="override"))
        rep.append(f"added {add['id']}")
    return items, rep, errs


def build(root: Path) -> tuple[dict, list, list]:
    m = load(root)
    items = Builder(m).run()
    rep, errs = [], []
    ovp = root / "services_overrides.json"
    if ovp.exists():
        ov = json.loads(ovp.read_text())
        items, rep, errs = apply_overrides(items, ov)
        b = Builder(m)
        moved = {mv.get("id") for mv in ov.get("move", [])}
        for it in items:
            if it["id"] in moved and it.get("wall") and it["room"] in b.faces:
                f, t = b.nearest_face(it["room"], it["at"])
                p = b.at_t(f, t)
                it.update(at=[round(p[0]), round(p[1])], wall=f.wall, into=b.into(f))
    return {"schema": "atelier/services@1", "rules": "agents/STANDARDS.md §6",
            "sources": m.sources + (["services_overrides.json"] if ovp.exists() else []),
            "items": items}, rep, errs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.services")
    ap.add_argument("path", type=Path)
    a = ap.parse_args(argv)
    roots = [a.path] if (a.path / "survey.json").exists() else sorted(p.parent for p in a.path.glob("*/survey.json"))
    bad = 0
    for root in roots:
        data, rep, errs = build(root)
        out = root / "services.json"
        out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        by = defaultdict(int)
        for i in data["items"]:
            by[i["system"]] += 1
        print(f"{root}: {len(data['items'])} items → {out}")
        print("  " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
        for r in rep:
            print(f"  override: {r}")
        for e in errs:
            print(f"  ERROR {e}")
        bad += len(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

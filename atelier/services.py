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
    "media": "MD", "fridge_socket": "FR", "oven_16a": "OV", "microwave_socket": "MW", "dw_socket": "DW",
    "chimney_point": "CY", "ro_point": "RO", "mirror_light": "ML",
    "socket_16a": "PS", "wall_light": "WL", "mixer": "MX", "shower_head": "SH",   # data contract point types
}
KITCHEN_APPLIANCES = [          # (kind, words in a module label, height; STANDARDS R6.7a)
    ("fridge_socket", ("fridge", "refrigerator"), 300),
    ("oven_16a", ("oven",), 300),
    ("microwave_socket", ("microwave", "micro"), 1600),
    ("dw_socket", ("dishwasher", "dw"), 300),
]


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
                latch = o["offset"] + o["width"] + 150 if latch_end else o["offset"] - 150
                hinge = o["offset"] - 150 if latch_end else o["offset"] + o["width"] + 150
                L_w = geom.wall_length(w)
                tall = [(j["offset"], j["offset"] + j["width"]) for j in self.m.joinery
                        if j["wall"] == w["id"] and j["room"] == target and j.get("z", 0) < 1200 <
                        j.get("z", 0) + j.get("height", 850)]
                off = next((x for x in (latch, hinge) if 60 < x < L_w - 60 and not any(a - 60 < x < b + 60
                                                                                        for a, b in tall)), None)
                if off is None:
                    continue
                f, t = self.face_on_wall(target, w["id"], geom.point_on_wall(w, off))
                if f is None:
                    continue
                near = next((i for i in self.items if i["kind"] == "switchboard" and i["room"] == target and
                             Point(i["at"]).distance(Point(self.at_t(f, t))) < 400), None)
                if near is not None:                            # one board serves both rooms
                    if r["id"] != near.get("serves"):
                        near.setdefault("also_serves", []).append(r["id"])
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
            self.wall_device("power", "tv_power", j["room"], f, t, 1100, "R6.6", note="behind the TV")
            for dt, kind in ((-250, "double_socket"), (0, "lan"), (250, "media")):     # console devices
                self.wall_device("power", kind, j["room"], f, t + dt, 550, "R6.6")

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
            for o in self.m.openings_on(w["id"]):              # never on a window over the worktop
                if o["kind"] in ("window", "ventilator") and o.get("sill", 900) < 1250:
                    avoid.append((o["offset"] - j["offset"] - 100, o["offset"] + o["width"] - j["offset"] + 100))
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

    def r6_7a_kitchen(self):
        """Chimney over each hob, RO beside each kitchen sink; fridge / oven / microwave / DW at their
        labelled appliance modules, else at a default spot, flagged for the designer to confirm."""
        for r in self.rooms_of({"kitchen"}):
            rid = r["id"]
            runs = [j for j in self.m.joinery if j["room"] == rid and j.get("kind") in ("kitchen_base", "tall_unit",
                                                                                      "kitchen_wall")]
            mods = []
            for j in runs:
                w = self.m.wall(j["wall"])
                for row in j.get("rows", []):
                    o = j["offset"]
                    for md in row["modules"]:
                        mods.append((j, w, o, md))
                        o += md["w"]
            for j, w, o, md in mods:
                c = geom.point_on_wall(w, o + md["w"] / 2)
                f, t = self.face_on_wall(rid, w["id"], c)
                if f is None:
                    continue
                if md["type"] == "hob":
                    self.wall_device("power", "chimney_point", rid, f, t, 2200, "R6.7a", note="chimney over the hob")
                if md["type"] == "sink" and j.get("kind") == "kitchen_base":
                    wins = [(o["offset"] - 100, o["offset"] + o["width"] + 100) for o in self.m.openings_on(w["id"])
                            if o["kind"] in ("window", "ventilator") and o.get("sill", 900) < 1900]
                    s0 = o + md["w"] / 2
                    cand = [s0 + d for d in range(450, 3000, 50) for d in (d, -d)]
                    s1 = next((x for x in cand if 60 < x < geom.wall_length(w) - 60 and
                               not any(a < x < b for a, b in wins)), None)
                    if s1 is not None:
                        f1, t1 = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, s1))
                        if f1 is not None:
                            self.wall_device("power", "ro_point", rid, f1, t1, 1800, "R6.7a",
                                             note="RO purifier; cold from the sink")
            for kind, words, z in KITCHEN_APPLIANCES:
                hit = next(((j, w, o, md) for j, w, o, md in mods if any(
                    wd in f"{md.get('label', '')} {md['type']}".lower().split() or wd in str(md.get("label", "")).lower()
                    for wd in words)), None)
                if hit:
                    j, w, o, md = hit
                    f, t = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, o + md["w"] / 2))
                    if f is not None:
                        self._appliance(rid, kind, f, t, z, "R6.7a")
                    continue
                fr = next((x for x in self.m.furniture if x["room"] == rid and x.get("kind") == "fridge"), None)
                if kind == "fridge_socket" and fr:              # a fridge placed as furniture: socket behind it
                    f, t = self.nearest_face(rid, fr["at"])
                    if f is not None:
                        self._appliance(rid, kind, f, t, z, "R6.7a", note=f"behind fridge {fr['id']}")
                        continue
                self._appliance_default(rid, kind, z, mods)

        return

    def _appliance(self, rid, kind, f, t, z, rule, flag=False, note=None):
        fl = dict(flag=True) if flag else {}
        self.wall_device("power", kind, rid, f, t, z, rule, note=note, **fl)
        if kind == "dw_socket":                                  # DW: water and drain beside its socket
            self.wall_device("plumbing", "cold", rid, f, t - 120, 300, rule, note="dishwasher inlet", **fl)
            self.wall_device("plumbing", "waste", rid, f, t + 120, 300, rule, note="dishwasher drain", **fl)

    def _appliance_default(self, rid, kind, z, mods):
        if kind == "dw_socket":                              # beside the sink: the next base module becomes the DW
            sink = next(((j, w, o, md) for j, w, o, md in mods if md["type"] == "sink"), None)
            if not sink:
                return
            j, w, o, md = sink
            nxt = [(j2, w2, o2, m2) for j2, w2, o2, m2 in mods if j2 is j and m2["type"] in ("shutter", "drawer")
                   and (abs(o2 - (o + md["w"])) < 2 or abs(o2 + m2["w"] - o) < 2)]
            if not nxt:
                return
            j2, w2, o2, m2 = nxt[0]
            f, t = self.face_on_wall(rid, w2["id"], geom.point_on_wall(w2, o2 + m2["w"] / 2))
            if f is not None:
                self._appliance(rid, kind, f, t, z, "R6.7a", flag=True,
                                note=f"no dishwasher slot: module {j2['id']} {o2 - j2['offset']}-{o2 - j2['offset'] + m2['w']} "
                                     f"to become a 600 DW housing (confirm)")
            return
        # fridge / oven / microwave: the kitchen's longest free wall stretch (no joinery, no opening)
        best = None
        for f in self.faces[rid]:
            for a, b in self.free_stretches(rid, f, 300):
                if b - a >= 700 and (best is None or b - a > best[2] - best[1]):
                    best = (f, a, b)
        if not best:
            return
        f, a, b = best
        t = a + 350 if kind == "fridge_socket" else min(a + 1050, b - 300) + (-150 if kind == "oven_16a" else 150)
        self._appliance(rid, kind, f, t, z, "R6.7a", flag=True,
                        note=f"no {kind.split('_')[0]} slot in the joinery: default on the free wall (confirm)")

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
                    fm, tm = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, j["offset"] + j["width"] / 2))
                    if fm is not None:
                        self.wall_device("lighting", "mirror_light", rid, fm, tm, 1950, "R6.8", ip="IP44",
                                         note="over the vanity mirror")
        for s in self.m.sanitary:
            if s["kind"] == "washing_machine":
                f, t = self.nearest_face(s["room"], s["at"])
                self.wall_device("power", "wm_socket", s["room"], f, t + 350, 1100, "R6.8", ip="IP44")
                fx, fy = geom.compass_to_vec(s.get("facing", "N"))           # floor trap in front of the machine
                self.add("plumbing", "floor_trap", s["room"],
                         (s["at"][0] + fx * (s["size"][1] / 2 + 150), s["at"][1] + fy * (s["size"][1] / 2 + 150)), 0,
                         "R6.8", note="washing machine overflow")
        for r in self.rooms_of({"balcony"}):                             # balcony IP44 socket
            best = None
            for f in self.faces[r["id"]]:
                if self.m.wall(f.wall).get("kind") == "parapet":
                    continue
                for a, b in self.free_stretches(r["id"], f, 300):
                    if best is None or b - a > best[2] - best[1]:
                        best = (f, a, b)
            if best:
                f, a, b = best
                self.wall_device("power", "ip44_socket", r["id"], f, (a + b) / 2, 1100, "R6.8", ip="IP44")

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
                db = self.wall_device("power", "db", rid, f, t, 1800, "R6.9")
                wet = [r["id"] for r in self.m.rooms if r.get("type") in WET | {"kitchen", "balcony", "utility"}]
                if db is not None:                     # RCCB 30 mA on wet-room and socket circuits (R6.9)
                    db["protection"] = {"rccb_ma": 30, "wet_rooms": wet, "socket_circuits": True}
                self.wall_device("power", "router", rid, f, t - 450 if t > 600 else t + 450, 2100, "R6.9")
            f, t = self.face_on_wall(rid, w["id"], geom.point_on_wall(w, l_off))
            if f is not None:
                self.wall_device("power", "vdp", rid, f, t, 1450, "R6.9")
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
            fwalls = {wf["wall"] for wf in feats}
            ffaces = [f for f in self.faces[rid] if f.wall in fwalls]
            fdir = self.into(max(ffaces, key=lambda f: f.length)) if ffaces else None
            if feats and tray:
                f = max([e for e in ext if e.wall not in fwalls] or ext, key=lambda f: f.length)   # not the feature wall
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
                slot = self._slot_opposite(rid, r, step, fdir) if fdir is not None and not step.is_empty else None
                if slot is None and not step.is_empty:              # no opposite face: along the nearest step edge
                    cs = list(step.exterior.coords)
                    edges = [(cs[i], cs[i + 1]) for i in range(len(cs) - 1)]
                    a, b = min(edges, key=lambda e: LineString(e).distance(Point(unit)) - LineString(e).length * 1e-4)
                    L = math.dist(a, b)
                    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                    slot = ((a[0] + ux * L * 0.2, a[1] + uy * L * 0.2), (a[0] + ux * L * 0.8, a[1] + uy * L * 0.8))
                if slot:
                    m0, m1 = slot
                    self.add("ac", "supply_grille", rid, ((m0[0] + m1[0]) / 2, (m0[1] + m1[1]) / 2), None, "R6.10",
                             path=[[round(m0[0]), round(m0[1])], [round(m1[0]), round(m1[1])]],
                             note="linear slot diffuser in the band opposite the feature wall")
                ret = (unit[0] + ix * 0, unit[1] + iy * 0)
                rx, ry = self.at_t(f, min(t + 900, f.length - 400))
                self.add("ac", "return_grille", rid, (rx + ix * inset * 0.5, ry + iy * inset * 0.5), None, "R6.10",
                         size=[600, 300])
                _ = ret
                continue
            # split: never on a feature wall; not on the wall the bed faces (it would blow at the bed head)
            bed = next((b for b in self.m.furniture if b["room"] == rid and b.get("kind") == "bed"), None)
            foot = None
            if bed:
                bx, by = geom.compass_to_vec(bed.get("facing", "N"))
                foot = round(math.degrees(math.atan2(-bx, -by))) % 360     # inward normal of the foot wall
            ok = lambda f: f.wall not in fwalls and (foot is None or abs(((self.into(f) - foot + 180) % 360) - 180) > 30)  # noqa: E731
            cands = [f for f in ext if ok(f)] or [f for f in self.faces[rid] if ok(f)] or \
                [f for f in ext if f.wall not in fwalls] or ext
            best = None
            for f in cands:
                for a, b in self.free_stretches(rid, f, 300):
                    if best is None or b - a > best[2] - best[1]:
                        best = (f, a, b)
            if not best:
                continue
            f, a, b = best
            t = (a + b) / 2
            unit = self.wall_device("ac", "split", rid, f, t, 2300, "R6.10", size=[900, 250])
            self.wall_device("power", "ac_isolator", rid, f, t + 600 if t + 600 < f.length - 60 else t - 600, 2100,
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

    def _slot_opposite(self, rid, r, step, fdir):
        """Slot diffuser in the ceiling band on the face opposite the feature wall: from 20 % to 80 % of that
        face, midway between the face and the tray step edge."""
        opp = [f for f in self.faces[rid] if abs(((self.into(f) - fdir) % 360) - 180) < 10]
        if not opp:
            return None
        f = max(opp, key=lambda e: e.length)
        mid = self.at_t(f, f.length / 2)
        ang = math.radians(self.into(f))
        ix, iy = math.sin(ang), math.cos(ang)
        ray = LineString([mid, (mid[0] + ix * 5000, mid[1] + iy * 5000)])
        hit = ray.intersection(step.exterior)
        if hit.is_empty:
            return None
        band = min(Point(mid).distance(g) for g in getattr(hit, "geoms", [hit]))
        d = band / 2
        p0, p1 = self.at_t(f, f.length * 0.2), self.at_t(f, f.length * 0.8)
        return ((p0[0] + ix * d, p0[1] + iy * d), (p1[0] + ix * d, p1[1] + iy * d))

    def _outside(self, f, t):
        w = self.m.wall(f.wall)
        p = self.at_t(f, t)
        ang = math.radians(self.into(f))
        ix, iy = math.sin(ang), math.cos(ang)
        d = w["t"] + 450
        return (p[0] - ix * d, p[1] - iy * d)

    # ------------------------------------------------------------ R6.11 – R6.13 lighting
    def r6_11_fans(self):
        """BLDC 1200 fan centred in the room; in living rooms over the centre of the seating rug."""
        for r in self.rooms_of(FAN_ROOMS):
            c = self.poly[r["id"]].centroid
            at, note = (c.x, c.y), "BLDC, room centre"
            if r.get("type") in ("living", "living_dining"):
                seats = [f for f in self.m.furniture if f["room"] == r["id"] and f.get("kind") in ("sofa", "armchair")]
                rugs = [f for f in self.m.furniture if f["room"] == r["id"] and f.get("kind") == "rug"]
                if rugs and seats:
                    rug = min(rugs, key=lambda g: min(Point(g["at"]).distance(Point(s_["at"])) for s_ in seats))
                    at, note = tuple(rug["at"]), f"BLDC, over the seating rug {rug['id']}"
            self.add("lighting", "fan", r["id"], at, None, "R6.11", size=[1200, 1200], note=note)

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
                    ring = Point(d["at"]).buffer(d["d"] / 2 + 90, 48)          # ring cove round the dome
                    pts = [[round(x), round(y)] for x, y in ring.exterior.coords]
                    self.add("lighting", "cove", r["id"], d["at"], None, "R6.13", path=pts, note=f"ring cove r + 90 round dome {d.get('id')}")
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
            elif s["kind"] == "basin":                           # free-standing basin: as a vanity sink (R6.14)
                self.wall_device("plumbing", "cold", s["room"], f, t - 100, 550, "R6.14")
                self.wall_device("plumbing", "hot", s["room"], f, t + 100, 550, "R6.14")
                self.wall_device("plumbing", "waste", s["room"], f, t, 450, "R6.14")
            elif s["kind"] == "washing_machine":
                self.wall_device("plumbing", "cold", s["room"], f, t - 150, 1050, "R6.14", note="WM inlet")
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
            serves = [sb.get("serves", sb["room"])] + sb.get("also_serves", [])
            ctl = [i["id"] for r_ in serves for i in light.get(r_, [])]
            ctl += [i["id"] for i in self.items if i["kind"] == "geyser_point" and i["room"] in serves]
            sb["controls"] = ctl
        for s2 in [i for i in self.items if i["kind"] == "switch_2way"]:
            s2["controls"] = [i["id"] for i in light.get(s2["room"], []) if i["kind"] == "downlight"]

    def switch_spots(self):
        """Designer's switch_spots (open rooms): a switchboard at each spot, on the nearest wall face,
        replacing the rule's switchboards in that room."""
        spots = (getattr(self.m, "extras", {}) or {}).get("switch_spots") or []
        rooms = {s["room"] for s in spots if s.get("room") in self.faces}
        if not rooms:
            return
        self.items = [i for i in self.items if not (i["kind"] == "switchboard" and i["room"] in rooms)]
        for r in rooms:
            self.count[(PREFIX["switchboard"], r)] = 0
        for s in spots:
            if s.get("room") not in self.faces:
                continue
            f, t = self.nearest_face(s["room"], s["at"])
            self.wall_device("switching", "switchboard", s["room"], f, t, s.get("z", 1200), "design")

    def run(self):
        self.r6_11_fans()                 # fans first: downlights keep clear of them
        self.r6_12_downlights()
        self.r6_13_cove()
        self.r6_8_wet()
        self.r6_1_switches()
        self.switch_spots()
        self.r6_3_sockets()
        self.r6_4_bedside()
        self.r6_5_desk()
        self.r6_6_tv()
        self.r6_7_worktop()
        self.r6_7a_kitchen()
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
        from atelier.contract import overrides as _contract_ov
        ov = _contract_ov(json.loads(ovp.read_text()))
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


# ------------------------------------------------------------------ review checklist (agents/services.md)
APPLIANCE_INSIDE = {"fridge_socket", "oven_16a", "microwave_socket", "dw_socket", "chimney_point", "geyser_point",
                    "ac_isolator", "mirror_light", "exhaust", "geyser"}
IN_OPENING = {"exhaust"}                         # placed in its ventilator on purpose
CIRCULATION = {"living", "dining", "living_dining", "foyer", "passage"}
PLATE_W = {"double_socket": 146, "tv_power": 146, "db": 350, "vdp": 130, "router": 200}


def check(m, items):
    """The services review checklist as findings: (id, code, message, suggested move or None)."""
    out = []
    dev = [i for i in items if i.get("wall") and i.get("z") is not None and i["system"] in ("power", "switching",
                                                                                         "lighting")]
    b = Builder(m)

    def t_on(w, p):
        ux, uy, _ = geom.unit(w["a"], w["b"])
        return (p[0] - w["a"][0]) * ux + (p[1] - w["a"][1]) * uy

    def blocks(i):
        """[(t0, t1, z0, z1, why)] on the device's wall that it must keep clear of."""
        w = m.wall(i["wall"])
        res = []
        for o in (m.openings_on(w["id"]) if i["kind"] not in IN_OPENING else []):
            if o["kind"] in ("window", "ventilator", "sliding_door"):
                sill = o.get("sill", 0) if o["kind"] != "sliding_door" else 0
                res.append((o["offset"], o["offset"] + o["width"], sill - 75, o.get("head", 2100) + 75,
                            f"on window {o['id']}"))
        for j in m.joinery:
            if j["wall"] != w["id"] or j["room"] != i["room"]:
                continue
            z0, z1 = j.get("z", 0), j.get("z", 0) + j.get("height", 850)
            if i["kind"] not in APPLIANCE_INSIDE and not (i["kind"] == "worktop_socket" and i["z"] > z1 - 60):
                res.append((j["offset"], j["offset"] + j["width"], z0, z1, f"inside joinery {j['id']}"))
            if j.get("kind") == "tv_unit" and i["kind"] != "tv_power":
                c = j["offset"] + j["width"] / 2
                res.append((c - 650, c + 650, 750, 1450, f"behind the TV over {j['id']}"))
        stands = [f for f in m.furniture if f["room"] == i["room"] and f.get("kind") == "bedside"]
        for wf in m.wall_features:
            if wf["wall"] != w["id"] or wf["room"] != i["room"] or not wf.get("parent"):
                continue
            free = []                                            # nightstand zones (+150 beside) on this element
            for n in stands:
                g = geom.furniture_polygon(n)
                if g.distance(geom.LineString([w["a"], w["b"]])) < w["t"] + 400:
                    ts = [t_on(w, c) for c in g.exterior.coords]
                    free.append((min(ts) - 150, max(ts) + 150, 850))
            for j in m.joinery:                                  # TV console zone: just above the unit
                if j["wall"] == w["id"] and j.get("kind") == "tv_unit":
                    free.append((j["offset"], j["offset"] + j["width"], j.get("z", 0) + j.get("height", 450) + 250))
            t_i = t_on(w, i["at"])
            if any(a - 1 <= t_i <= bb + 1 and i["z"] <= zt for a, bb, zt in free):
                continue
            if i["kind"] == "tv_power" and any(j["wall"] == w["id"] and j.get("kind") == "tv_unit" for j in m.joinery):
                continue                                         # behind the TV itself
            res.append((wf["offset"], wf["offset"] + wf["width"], 301, wf["z1"],
                        f"on feature artwork {wf['id']} ({wf['kind']})"))
        return res

    def clear_spot(i, extra=()):
        w = m.wall(i["wall"])
        t0 = t_on(w, i["at"])
        bl = [x for x in blocks(i) if x[2] <= i["z"] <= x[3]] + list(extra)
        f, _ = b.nearest_face(i["room"], i["at"])
        lo = t_on(w, b.at_t(f, 0))
        hi = t_on(w, b.at_t(f, f.length))
        lo, hi = min(lo, hi) + 80, max(lo, hi) - 80
        for d in range(0, 4000, 30):
            for t in (t0 + d, t0 - d):
                if lo <= t <= hi and not any(a - 60 < t < c + 60 for a, c, *_ in bl):
                    p = geom.point_on_wall(w, t, geom.face_offset(w, geom.room_side_of_wall(w, m.room(i["room"]))
                                                                  or "left"))
                    return {"id": i["id"], "at": [round(p[0]), round(p[1])], "z": i["z"]}
        return None

    for i in dev:
        for a, c, z0, z1, why in blocks(i):
            t = t_on(m.wall(i["wall"]), i["at"])
            if a < t < c and z0 <= i["z"] <= z1:
                out.append((i["id"], "SV-CLASH", f"{i['id']} ({i['kind']}, h{i['z']}) {why}", clear_spot(i)))
                break
        for o in m.openings:                                     # behind a door swing
            if o["kind"] in ("door", "double_door") and o.get("swing") in ("left", "right"):
                sp = geom.swing_polygon(m.wall(o["wall"]), o)
                if sp.buffer(40).contains(geom.Point(i["at"])) and i["z"] < o.get("head", 2100):
                    out.append((i["id"], "SV-SWING", f"{i['id']} ({i['kind']}) is behind the swing of {o['id']}",
                                clear_spot(i, [(min(t_on(m.wall(i["wall"]), c) for c in sp.exterior.coords),
                                                max(t_on(m.wall(i["wall"]), c) for c in sp.exterior.coords), 0, 9999,
                                                "swing")]) if m.wall(i["wall"]) else None))
    by_wall = {}
    for i in dev:
        by_wall.setdefault((i["wall"], i["room"]), []).append(i)
    for (wid, rid), lst in by_wall.items():                     # plates closer than 120
        w = m.wall(wid)
        lst = sorted(lst, key=lambda i: t_on(w, i["at"]))
        for p, q in zip(lst, lst[1:]):
            gap = abs(t_on(w, q["at"]) - t_on(w, p["at"])) - (PLATE_W.get(p["kind"], 86) + PLATE_W.get(q["kind"], 86)) / 2
            if gap < 120 - 86 and abs(p["z"] - q["z"]) < 100:
                s_ = clear_spot(q, [(t_on(w, p["at"]) - 206, t_on(w, p["at"]) + 206, 0, 9999, "plate")])
                out.append((q["id"], "SV-OVERLAP", f"{q['id']} and {p['id']} plates overlap on {wid} "
                                                   f"(h{q['z']} / h{p['z']})", s_))
    for r in m.rooms:                       # every way in (from circulation or outside) has a switchboard near it
        if r.get("type") in ("bath", "toilet", "balcony", "shaft"):
            continue
        sbs = [i for i in items if i["kind"] == "switchboard" and i["room"] == r["id"]]
        for o in m.openings:
            if o["kind"] not in ("door", "double_door", "opening", "sliding_door"):
                continue
            w = m.wall(o["wall"])
            cut = geom.opening_polygon(w, o, 2).buffer(5)
            if not cut.intersects(geom.room_polygon(r)):
                continue
            other = [x for x in m.rooms if x["id"] != r["id"] and cut.intersects(geom.room_polygon(x))]
            entry = (not other and w.get("kind") == "external") or \
                any(x.get("type") in CIRCULATION for x in other) and r.get("type") not in CIRCULATION
            if not entry:
                continue
            c = geom.point_on_wall(w, o["offset"] + o["width"] / 2)
            if not any(geom.Point(sb["at"]).distance(geom.Point(c)) < o["width"] / 2 + 1200 for sb in sbs):
                out.append((o["id"], "SV-SWITCH", f"no switchboard of {r['id']} within reach of {o['id']} "
                                                  f"(add one at its latch side h1200, or a switch spot)", None))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.services")
    ap.add_argument("path", type=Path)
    ap.add_argument("--check", action="store_true", help="review checklist findings (agents/services.md)")
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
        if a.check:
            fs = check(load(root), data["items"])
            for pid, code, msg, mv in fs:
                print(f"  {code:10} {msg}")
                if mv:
                    print(f"             suggest move: {json.dumps(mv)}")
            print(f"  check: {len(fs)} finding(s)" + ("" if fs else " ✓"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

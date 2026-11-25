"""Validate project data before anything is drawn.

    python -m atelier.validate projects/sample
    python -m atelier.validate projects/sample --design alt.json
    python -m atelier.validate projects/            # every project under it

Exit status 1 if there is any ERROR.
"""
from __future__ import annotations

import argparse
import re
import sys
from itertools import combinations
from pathlib import Path

from shapely.ops import unary_union

from atelier import geom
from atelier.model import Model, load

AREA_TOL = 0.03       # computed vs printed area
MIN_CLASH = 100       # mm² of overlap that counts as a clash
DOORLIKE = {"door", "double_door", "sliding_door", "opening"}
LIGHTLIKE = {"window", "ventilator", "sliding_door"}
NO_DOOR_OK = {"shaft"}
NEEDS_LIGHT = {"living", "dining", "living_dining", "kitchen", "bedroom", "master_bedroom",
               "bath", "toilet", "study"}
SOFT = {"rug"}  # furniture that may sit under other furniture

ENUMS = {
    ("walls", "kind"): {"external", "internal", "partition", "parapet", "glass", "half"},
    ("walls", "align"): {"centre", "left", "right"},
    ("openings", "kind"): {"door", "double_door", "sliding_door", "opening", "window", "ventilator"},
    ("openings", "swing"): {"left", "right", "none"},
    ("openings", "hinge"): {"start", "end", "both", "none"},
    ("rooms", "type"): {"living", "dining", "living_dining", "kitchen", "bedroom", "master_bedroom",
                        "bath", "toilet", "utility", "balcony", "foyer", "passage", "study", "puja",
                        "store", "dress", "shaft"},
    ("furniture", "kind"): {"sofa", "armchair", "coffee_table", "side_table", "dining_table", "chair",
                            "bed", "bedside", "desk", "rug", "console", "tv", "plant", "other"},
    ("joinery", "kind"): {"wardrobe", "tv_unit", "kitchen_base", "kitchen_wall", "tall_unit", "vanity",
                          "shoe_rack", "crockery", "study_unit", "bookshelf", "puja_unit", "other"},
}
MODULE_TYPES = {"shutter", "glass_shutter", "drawer", "open", "loft", "appliance", "sink", "hob",
                "panel", "filler"}
MM_FIELDS = {
    "walls": ("a", "b", "t", "height"),
    "openings": ("offset", "width", "sill", "head"),
    "rooms": ("poly", "ffl"),
    "furniture": ("at", "size"),
    "joinery": ("offset", "width", "depth", "z", "height"),
}
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _ints(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (list, tuple)):
        return all(_ints(x) for x in v)
    return v is None or isinstance(v, int)


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def E(self, code, msg):
        self.errors.append((code, msg))

    def W(self, code, msg):
        self.warnings.append((code, msg))


def check(m: Model) -> Report:
    R = Report()
    lists = {"walls": m.walls, "openings": m.openings, "rooms": m.rooms,
             "furniture": m.furniture, "joinery": m.joinery}

    # ---- schema: ids, integers, enums, references --------------------------------
    seen = {}
    for kind, objs in lists.items():
        for o in objs:
            i = o.get("id")
            if not i or not ID_RE.match(str(i)):
                R.E("E-ID", f"{kind}: bad or missing id {i!r}")
            elif i in seen:
                R.E("E-ID", f"duplicate id {i} ({seen[i]} and {kind})")
            else:
                seen[i] = kind
            for f in MM_FIELDS.get(kind, ()):
                if f in o and not _ints(o[f]):
                    R.E("E-INT", f"{i}.{f} must be integer mm: {o[f]!r}")
            for (k, f), allowed in ENUMS.items():
                if k == kind and f in o and o[f] not in allowed:
                    R.E("E-ENUM", f"{i}.{f} = {o[f]!r} not in {sorted(allowed)}")
    for o in m.openings:
        if not m.wall(o.get("wall")):
            R.E("E-REF", f"opening {o['id']} on unknown wall {o.get('wall')!r}")
    for k in ("furniture", "joinery"):
        for o in lists[k]:
            if not m.room(o.get("room")):
                R.E("E-REF", f"{k} {o['id']} in unknown room {o.get('room')!r}")
            if k == "joinery" and not m.wall(o.get("wall")):
                R.E("E-REF", f"joinery {o['id']} on unknown wall {o.get('wall')!r}")
    if R.errors:
        return R  # geometry checks need valid references

    wpoly = {w["id"]: geom.wall_polygon(w) for w in m.walls}
    rpoly = {r["id"]: geom.room_polygon(r) for r in m.rooms}

    # ---- 1. overlapping walls ----------------------------------------------------
    for w1, w2 in combinations(m.walls, 2):
        a = wpoly[w1["id"]].intersection(wpoly[w2["id"]]).area
        if a > 1 and geom.is_parallel(w1, w2):
            R.E("E-WALL-OVERLAP", f"walls {w1['id']} and {w2['id']} overlap ({a / 1e6:.3f} m²)")

    # ---- 2. openings fit their wall, and don't overlap each other ----------------
    for o in m.openings:
        w = m.wall(o["wall"])
        L = geom.wall_length(w)
        if o["offset"] < 0 or o["offset"] + o["width"] > L + 0.5:
            R.E("E-OPENING-WIDTH",
                f"opening {o['id']} ({o['offset']}+{o['width']}) runs past wall {w['id']} (length {L:.0f})")
    for o1, o2 in combinations(m.openings, 2):
        if o1["wall"] == o2["wall"] and o1["offset"] < o2["offset"] + o2["width"] \
                and o2["offset"] < o1["offset"] + o1["width"]:
            R.E("E-OPENING-OVERLAP", f"openings {o1['id']} and {o2['id']} overlap on wall {o1['wall']}")

    # ---- rooms vs walls and each other -------------------------------------------
    walls_all = unary_union(list(wpoly.values()))
    for r in m.rooms:
        a = rpoly[r["id"]].intersection(walls_all).area
        if a > MIN_CLASH:
            R.E("E-ROOM-WALL", f"room {r['id']} polygon runs into wall bodies ({a / 1e6:.3f} m²)")
    for r1, r2 in combinations(m.rooms, 2):
        a = rpoly[r1["id"]].intersection(rpoly[r2["id"]]).area
        if a > MIN_CLASH:
            R.E("E-ROOM-OVERLAP", f"rooms {r1['id']} and {r2['id']} overlap ({a / 1e6:.3f} m²)")

    # ---- 3. furniture inside its room, no overlaps -------------------------------
    solid = {}
    for f in m.furniture:
        p = geom.furniture_polygon(f)
        if not rpoly[f["room"]].buffer(1).contains(p):
            R.E("E-FURN-OUTSIDE", f"furniture {f['id']} ({f.get('kind')}) is not inside room {f['room']}")
        if f.get("kind") not in SOFT:
            solid[f["id"]] = p
    for j in m.joinery:
        p = geom.joinery_polygon(j, m.wall(j["wall"]), m.room(j["room"]))
        if not rpoly[j["room"]].buffer(1).contains(p):
            R.E("E-JOINERY-OUTSIDE", f"joinery {j['id']} is not inside room {j['room']}")
        solid[j["id"]] = p
    for (i1, p1), (i2, p2) in combinations(solid.items(), 2):
        a = p1.intersection(p2).area
        if a > MIN_CLASH:
            R.E("E-FURN-OVERLAP", f"{i1} and {i2} overlap ({a / 1e6:.3f} m²)")

    # ---- 4. door swings ----------------------------------------------------------
    for o in m.openings:
        w = m.wall(o["wall"])
        sp = geom.swing_polygon(w, o)
        if sp is None:
            continue
        for i, p in solid.items():
            a = sp.intersection(p).area
            if a > MIN_CLASH:
                R.E("E-SWING-BLOCKED", f"door {o['id']} swing hits {i} ({a / 1e6:.3f} m²)")
        others = unary_union([p for k, p in wpoly.items() if k != w["id"]])
        a = sp.intersection(others).area
        if a > MIN_CLASH:
            R.W("W-SWING-WALL", f"door {o['id']} swing hits a wall ({a / 1e6:.3f} m²)")

    # ---- 5. joinery modules sum --------------------------------------------------
    for j in m.joinery:
        for n, row in enumerate(j.get("rows", []), 1):
            s = sum(md["w"] for md in row.get("modules", []))
            if s != j["width"]:
                R.E("E-JOINERY-SUM", f"joinery {j['id']} row {n}: modules sum {s} ≠ width {j['width']}")
            for md in row.get("modules", []):
                if md.get("type") not in MODULE_TYPES:
                    R.E("E-ENUM", f"joinery {j['id']} row {n}: module type {md.get('type')!r}")
        if j.get("rows") and "height" in j:
            h = sum(r["height"] for r in j["rows"])
            if h != j["height"]:
                R.E("E-JOINERY-SUM", f"joinery {j['id']}: row heights sum {h} ≠ height {j['height']}")

    # ---- 6. every room has a way in; habitable rooms have light/air --------------
    cuts = {o["id"]: geom.opening_polygon(m.wall(o["wall"]), o, extra=2) for o in m.openings}
    for r in m.rooms:
        rp = rpoly[r["id"]].buffer(3)
        touching = [o for o in m.openings if cuts[o["id"]].intersects(rp)]
        via_void = any(v.buffer(2).intersects(rp) for v in m.voids)  # demolished wall stretch
        if r.get("type") not in NO_DOOR_OK and not via_void \
                and not any(o["kind"] in DOORLIKE for o in touching):
            R.E("E-ROOM-NO-DOOR", f"room {r['id']} ({r.get('name')}) has no door or opening")
        if r.get("type") in NEEDS_LIGHT and not any(o["kind"] in LIGHTLIKE for o in touching):
            R.W("W-ROOM-NO-WINDOW", f"room {r['id']} ({r.get('name')}) has no window or ventilator")

    # ---- 7. computed vs printed area ---------------------------------------------
    for r in m.rooms:
        if r.get("area_printed"):
            calc = rpoly[r["id"]].area / 1e6
            d = abs(calc - r["area_printed"]) / r["area_printed"]
            if d > AREA_TOL:
                R.E("E-AREA", f"room {r['id']}: computed {calc:.2f} m² vs printed {r['area_printed']} m² "
                              f"({d:.1%} > {AREA_TOL:.0%})")
    return R


def run(root: Path, design: str | None) -> int:
    m = load(root, design)
    R = check(m)
    print(f"{root}  ({' + '.join(m.sources)})")
    print(f"ERRORS ({len(R.errors)})")
    for c, msg in R.errors:
        print(f"  {c:18} {msg}")
    print(f"WARNINGS ({len(R.warnings)})")
    for c, msg in R.warnings:
        print(f"  {c:18} {msg}")
    print(f"VERIFY ON SITE ({len(m.verify)})")
    for ref, fld, note in m.verify:
        print(f"  * {ref}{'.' + fld if fld else ''}  {note}")
    print(f"result: {len(R.errors)} errors, {len(R.warnings)} warnings\n")
    return len(R.errors)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.validate")
    ap.add_argument("path", type=Path)
    ap.add_argument("--design", help="design file in the project (default design.json)")
    a = ap.parse_args(argv)
    roots = [a.path] if (a.path / "survey.json").exists() else \
        sorted(p.parent for p in a.path.glob("*/survey.json"))
    if not roots:
        print(f"no survey.json found under {a.path}")
        return 2
    errors = sum(run(r, a.design) for r in roots)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

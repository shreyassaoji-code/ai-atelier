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

from shapely.geometry import LineString
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
    ("walls", "kind"): {"external", "internal", "load", "partition", "parapet", "glass", "half"},
    ("walls", "align"): {"centre", "left", "right"},
    ("openings", "kind"): {"door", "double_door", "sliding_door", "opening", "window", "ventilator"},
    ("openings", "swing"): {"left", "right", "none"},
    ("openings", "hinge"): {"start", "end", "both", "none"},
    ("rooms", "type"): {"living", "dining", "living_dining", "kitchen", "bedroom", "master_bedroom",
                        "bath", "toilet", "utility", "balcony", "foyer", "passage", "study", "puja",
                        "store", "dress", "shaft"},
    ("furniture", "kind"): {"sofa", "armchair", "coffee_table", "side_table", "dining_table", "chair",
                            "bed", "bedside", "bench", "desk", "rug", "console", "tv", "plant", "other"},
    ("sanitary", "kind"): {"wc", "shower", "bathtub", "washing_machine"},
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
    "sanitary": ("at", "size"),
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
             "furniture": m.furniture, "sanitary": m.sanitary, "joinery": m.joinery}

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
    for k in ("furniture", "sanitary", "joinery"):
        for o in lists[k]:
            if not m.room(o.get("room")):
                R.E("E-REF", f"{k} {o['id']} in unknown room {o.get('room')!r}")
            if k == "joinery" and not m.wall(o.get("wall")):
                R.E("E-REF", f"joinery {o['id']} on unknown wall {o.get('wall')!r}")
    # ---- structure: external and load-bearing walls are never removed -----------
    kinds = {w["id"]: w.get("kind") for w in m.survey_walls}
    for d in m.demolished:
        if d["kind"] == "wall" and kinds.get(d["id"]) in ("external", "load"):
            R.E("E-DEMOLISH-STRUCT", f"wall {d['id']} is {kinds[d['id']]}: it may not be demolished")
    for e in m.override_errors:
        R.E("E-REF", e)
    # ---- feature walls (agents/reference.md, STANDARDS §4) ------------------------
    from atelier import features as FT
    for g in m.feature_walls:
        its = sorted(g["items"], key=lambda i: i["from"])
        for it in its:
            if it.get("type") not in FT.TYPES:
                R.E("E-ENUM", f"wall feature {g['id']}: type {it.get('type')!r} not in {list(FT.TYPES)}")
            if not 0 <= it["from"] < it["to"] <= g["L"] + 1:
                R.E("E-FEATURE", f"wall feature {g['id']}: item {it.get('type')} {it['from']}-{it['to']} "
                                 f"runs off the {g['L']} wall")
        for a, b in zip(its, its[1:]):
            if b["from"] < a["to"] - 1 and b["z0"] < a["z1"] and a["z0"] < b["z1"]:
                R.E("E-FEATURE", f"wall feature {g['id']}: {a.get('type')} and {b.get('type')} overlap "
                                 f"({a['from']}-{a['to']} / {b['from']}-{b['to']})")
    for g, it, o in (FT.opening_clashes(m) if not R.errors else []):
        what = "a window" if o["kind"] not in ("door", "double_door") else "a door (set concealed: true to hide it)"
        R.E("E-FEATURE-OPENING", f"wall feature {g['id']}: {it.get('type')} {it['from']}-{it['to']} covers "
                                 f"{o['id']}, {what}")
    for g in (m.feature_walls if not R.errors else []):         # elements hidden behind tall joinery
        L, P = FT.wall_u(m, g)
        line = LineString([P(0), P(L)])
        for j in m.joinery:
            if j["room"] != g["room"] or j.get("z", 0) + j.get("height", 850) < 1200:
                continue
            jp = geom.joinery_polygon(j, m.wall(j["wall"]), m.room(j["room"]))
            if jp.distance(line) > 60:
                continue
            us = [FT._u_of(P, L, c) for c in jp.exterior.coords]
            ja, jb = min(us), max(us)
            for it in g["items"]:
                ov = min(jb, it["to"]) - max(ja, it["from"])
                if ov > 0.5 * (it["to"] - it["from"]):
                    R.W("W-FEATURE-HIDDEN", f"wall feature {g['id']}: {it.get('type')} {it['from']}-{it['to']} "
                                            f"is behind {j['id']} ({ja:.0f}-{jb:.0f})")
    for g in (m.feature_walls if not R.errors else []):         # bed / TV centred on its element
        L, P = FT.wall_u(m, g)
        line = LineString([P(0), P(L)])
        anchors = [f for f in m.furniture if f["room"] == g["room"] and f.get("kind") == "bed"
                   and geom.furniture_polygon(f).distance(line) < 400]
        anchors += [j for j in m.joinery if j["room"] == g["room"] and j.get("kind") == "tv_unit"
                    and j["wall"] == g.get("wall")]
        for a in anchors:
            c = geom.furniture_polygon(a).centroid if "at" in a else \
                geom.joinery_polygon(a, m.wall(a["wall"]), m.room(a["room"])).centroid
            u = FT._u_of(P, L, (c.x, c.y))
            host = next((it for it in g["items"] if it["from"] <= u <= it["to"]), None)
            if host and abs((host["from"] + host["to"]) / 2 - u) > 50:
                R.W("W-FEATURE-CENTRE", f"wall feature {g['id']}: {a['id']} centre at u={u:.0f}, its "
                                        f"{host.get('type')} element centre at {(host['from'] + host['to']) / 2:.0f}")
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
    for f in list(m.furniture) + list(m.sanitary):
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
        if j.get("handles", "bar") not in ("bar", "knob", "gola", "push"):
            R.E("E-ENUM", f"joinery {j['id']}: handles {j.get('handles')!r}")
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

    # ---- finish codes resolve -------------------------------------------------
    codes = {f.get("code") for f in m.finishes}
    for fl in m.floors:
        if fl.get("finish") not in codes:
            R.E("E-FINISH", f"floor in {fl.get('room')}: unknown finish {fl.get('finish')!r}")
        if not m.room(fl.get("room")):
            R.E("E-REF", f"floor finish for unknown room {fl.get('room')!r}")
    for wf in m.wall_features:
        if wf.get("finish") and wf["finish"] not in codes:
            R.E("E-FINISH", f"wall feature {wf.get('id')}: unknown finish {wf['finish']!r}")
        if not m.wall(wf.get("wall")):
            R.E("E-REF", f"wall feature {wf.get('id')} on unknown wall {wf.get('wall')!r}")
    for r in m.rooms:
        if r.get("wall_finish") and r["wall_finish"] not in codes:
            R.E("E-FINISH", f"room {r['id']}: unknown wall finish {r['wall_finish']!r}")
    for j in m.joinery:                                     # board, worktop and hardware codes
        mats = j.get("materials") or {}
        used = list(mats.values()) if isinstance(mats, dict) else list(mats)
        used += [j.get("finish"), j.get("worktop")] + [p.get("code") or p.get("material") for p in j.get("parts", [])]
        for c in used:
            if c and c not in codes:
                R.E("E-FINISH", f"joinery {j['id']}: unknown material code {c!r}")
    from atelier.texture import named_tone
    for f in m.finishes:
        if f.get("tone") and named_tone(f["tone"]) is None:
            R.W("W-TONE", f"finish {f['code']}: colour {f['tone']!r} has no known tone word; drawn in its kind's tone")
    for t in (m.extras.get("palette") or []):
        name = t.get("name") if isinstance(t, dict) else t
        if named_tone(name) is None:
            R.W("W-TONE", f"palette colour {name!r} has no known tone word")


    # ---- ceilings ---------------------------------------------------------------
    soffit = m.levels.get("soffit")
    light_kinds = {"downlight", "spotlight", "pendant", "chandelier", "strip", "track", "fan"}
    for c in m.ceilings:
        r = m.room(c.get("room"))
        if not r:
            R.E("E-REF", f"ceiling for unknown room {c.get('room')!r}")
            continue
        rp = rpoly[r["id"]]
        zs = [c.get("z")]
        for i, st in enumerate(c.get("steps", []), 1):
            sp = geom.step_polygon(r, st)
            if sp.is_empty:
                R.E("E-CEIL", f"ceiling {r['id']} step {i}: empty (inset too large?)")
                continue
            if not rp.buffer(1).contains(sp):
                R.E("E-CEIL", f"ceiling {r['id']} step {i}: area runs outside the room")
            if st.get("z") is not None and zs[-1] is not None and st["z"] <= zs[-1]:
                R.W("W-CEIL", f"ceiling {r['id']} step {i}: +{st['z']} is not above the level around it (+{zs[-1]})")
            if st.get("light") not in (None, "none", "cove", "profile"):
                R.E("E-ENUM", f"ceiling {r['id']} step {i}: light {st.get('light')!r}")
            zs.append(st.get("z"))
        for d in c.get("domes", []):
            if not rp.buffer(1).contains(geom.dome_polygon(d)):
                R.E("E-CEIL", f"dome {d.get('id')} in {r['id']} runs outside the room")
        for lt in c.get("lights", []):
            if lt.get("kind") not in light_kinds:
                R.E("E-ENUM", f"ceiling {r['id']}: light kind {lt.get('kind')!r}")
        tray = max([z for z in zs if z is not None], default=None)
        if soffit and tray and tray > soffit - 150:
            R.E("E-CEIL", f"ceiling {r['id']}: +{tray} leaves < 150 below the slab soffit +{soffit} (STANDARDS §3)")
        top = max([z for z in zs if z is not None] + [d["z"] for d in c.get("domes", [])], default=None)
        if soffit and top and top > soffit - 50:
            R.E("E-CEIL", f"ceiling {r['id']}: +{top} leaves < 50 below the slab soffit +{soffit}")
    for c in m.design_brief.get("ceilings", []):            # the brief's tray rules
        if c.get("type") == "tray":
            n = len(c.get("steps", []))
            if not 1 <= n <= 2:
                R.W("W-CEIL", f"ceiling {c.get('room')}: tray with {n} steps (brief: 1-2)")
            for st in c.get("steps", []):
                if not 350 <= st.get("band", 450) <= 600:
                    R.W("W-CEIL", f"ceiling {c.get('room')}: band {st.get('band')} outside 350-600 (brief)")
    for v in m.views:
        if v.get("kind") == "section":
            ln = v.get("line")
            if not ln or len(ln) != 2 or v.get("look") not in ("N", "E", "S", "W"):
                R.E("E-VIEW", f"section {v.get('id')}: needs line [[x,y],[x,y]] and look N/E/S/W")

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

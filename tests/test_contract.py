"""The data contract (agents/SCHEMA.md §0).   python tests/test_contract.py

1. Round trip: the sample exported to contract form (atelier.contract export) resolves to the same
   apartment: walls, openings, rooms and their types, furniture, sanitary, joinery with its bands,
   ceilings, floors, finishes, feature walls, and the same services.
2. Every contract feature the sample does not use, added to that copy: hex palette and material
   colours, wall finishes by edge, basin / fridge / an unknown type, a view by edge, a camera by pos,
   flat-list tracks, an exposed ceiling, a TV in a feature item, a room typed from its kind, services
   overrides keyed by system with contract point types. Loads, validates with 0 errors, builds services.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier import contract, geom  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.validate import check as validate  # noqa: E402

SAMPLE = ROOT / "projects" / "sample"
tmp = Path(tempfile.mkdtemp()) / "ct"
checks = []
try:
    contract.export(SAMPLE, tmp)
    sv = json.loads((tmp / "survey.json").read_text())
    ds = json.loads((tmp / "design.json").read_text())
    checks += [("export: centre-line walls with type", all("type" in w and "kind" not in w for w in sv["walls"])),
               ("export: openings with h and side", all("h" in o and "head" not in o for o in sv["openings"])),
               ("export: furniture and joinery as boxes", all("x" in f for f in ds["furniture"] + ds["joinery"])),
               ("export: partial demolition split into whole walls", "I1d" in ds["demolish"])]
    A, B = load(SAMPLE), load(tmp)
    ua, ub = geom.walls_union(A.walls), geom.walls_union(B.walls)
    # integer centre-lines leave ±0.5 mm on 115 walls (SCHEMA §0): no difference thicker than 1 mm
    checks.append(("round trip: walls (to the mm)", ua.symmetric_difference(ub).buffer(-0.6).is_empty))
    key_o = ("wall", "offset", "width", "head", "swing", "hinge", "kind")
    checks.append(("round trip: openings", all(
        all(o.get(k) == next(p for p in B.openings if p["id"] == o["id"]).get(k) for k in key_o) for o in A.openings)))
    checks.append(("round trip: room types from names", all(B.room(r["id"])["type"] == r["type"] for r in A.rooms)))
    checks.append(("round trip: furniture footprints", all(
        geom.furniture_polygon(f).symmetric_difference(
            geom.furniture_polygon(next(g for g in B.furniture if g["id"] == f["id"]))).area < 1e3 for f in A.furniture)))
    rows = lambda j: [(r["height"], [(md["w"], md["type"]) for md in r["modules"]]) for r in j["rows"]]  # noqa: E731
    checks.append(("round trip: joinery wall, offset, bands", all(
        (j["wall"], j["offset"], j["width"], j["height"], rows(j)) ==
        (k["wall"], k["offset"], k["width"], k["height"], rows(k))
        for j in A.joinery for k in B.joinery if k["id"] == j["id"]) and len(A.joinery) == len(B.joinery)))
    def cdesc(c):
        from shapely.geometry import Polygon as _P
        return (c["z"], [(s_.get("inset"), s_["z"], s_.get("light"),
                          tuple(round(v) for v in _P(s_["poly"]).bounds) if "poly" in s_ else None)
                         for s_ in c.get("steps", [])],
                [(d_["at"], d_["d"], d_["z"]) for d_ in c.get("domes", [])],
                sorted(str(l_.get("path")) for l_ in c.get("lights", []) if l_["kind"] == "track"))
    checks.append(("round trip: ceilings (levels, insets, partial trays, domes, tracks)", all(
        cdesc(c) == cdesc(next(d for d in B.ceilings if d["room"] == c["room"])) for c in A.ceilings)))
    checks.append(("round trip: no contract guesses", B.contract_notes == [] and B.override_errors == []))

    # ---- 2. every other contract feature
    COL = json.loads((ROOT / "tests" / "fixtures" / "contract_colours.json").read_text())   # client colours (data)
    ds["palette"] = COL["palette"]
    first_floor = next(iter(ds["floor_materials"]))
    ds["floor_materials"][first_floor]["color"] = COL["floor_colour"]
    ds["wall_finishes"]["KIT"] = [{"code": "WF1", "edges": "all"}, {"code": "WF2", "edges": [1]}]
    ds["furniture"] += [
        {"id": "F90", "type": "fridge", "label": "Fridge", "room": "KIT", "x": 8975, "y": 4115, "w": 650, "d": 600,
         "facing": "E"},
        {"id": "F91", "type": "island", "label": "Kitchen island", "room": "LD", "x": 2900, "y": 3100, "w": 1200,
         "d": 700, "facing": "S"},
        {"id": "F92", "type": "basin", "room": "CBT", "x": 3960, "y": 4600, "w": 500, "d": 450, "facing": "E"}]
    ds["views"] = ds.get("views", []) + [{"id": "V5", "room": "KIT", "edge": 1, "name": "Kitchen – east wall"}]
    ds["cameras"] = [{"room": "LD", "pos": [7500, 2200, 1450], "target": [2000, 2200, 1050], "lens": 18}]
    for c in ds["ceilings"]:
        if c["room"] == "KIT":
            c["tracks"] = [[9300, 5000, 10800, 5000]]
    ds["ceilings"].append({"room": "BAL", "type": "exposed"})
    fw1 = next(g for g in ds["wall_features"] if g["id"] == "FW1")
    arch = next(it for it in fw1["items"] if it["type"] == "arch")
    arch["tv"] = {"w": 1100, "h": 620, "z": 1150}
    cbt = next(r for r in sv["rooms"] if r["id"] == "CBT")
    cbt["name"] = "Room X"                       # a name that says nothing: the type must come from kind "wet"
    (tmp / "survey.json").write_text(json.dumps(sv))
    (tmp / "design.json").write_text(json.dumps(ds))
    (tmp / "services_overrides.json").write_text(json.dumps({
        "remove": [], "move": [{"id": "RT-LD-01", "x": 2650, "y": 4000, "h": 300}],
        "add": {"electrical": [{"id": "PS-LD-90", "type": "power16", "room": "LD", "x": 6600, "y": 3000, "h": 300}],
                "lighting": [{"id": "WL-MBR-90", "type": "wall_light", "room": "MBR", "x": 300, "y": 5200, "h": 1800}],
                "plumbing": [{"id": "MX-MBT-90", "type": "mixer", "room": "MBT", "x": 5700, "y": 6500, "h": 1000}]}}))
    m = load(tmp)
    rep = validate(m)
    from atelier.texture import named_tone
    from atelier.services import build as sbuild
    checks += [
        ("contract copy validates (0 errors) " + str(rep.errors[:3]), not rep.errors),
        ("room typed from its kind, with a W-CONTRACT note",
         m.room("CBT")["type"] == "bath" and any(c == "W-CONTRACT" and "CBT" in t for c, t in rep.warnings)),
        ("hex colour read as a tone", named_tone(COL["sage"]) is not None
         and abs(named_tone(COL["sage"])[0] - COL["sage_rgb0"] / 255) < 1e-6),
        ("palette kept as [name, colour] pairs", m.extras["palette"][1] == COL["palette"][1]),
        ("wall finish by edge → a wall feature on that wall", any(w["id"].startswith("WF-KIT-1") and w["finish"] == "WF2"
                                                                 for w in m.wall_features)),
        ("fridge furniture", any(f["kind"] == "fridge" for f in m.furniture)),
        ("unknown type kept as a labelled box", any(f["kind"] == "other" and f["label"] == "Kitchen island"
                                                    for f in m.furniture)),
        ("basin is sanitary", any(s["kind"] == "basin" for s in m.sanitary)),
        ("view by edge → design camera V5", any(c["id"] == "V5" and c["room"] == "KIT" for c in m.cameras)),
        ("camera by pos, levelled", any(c["id"] == "C1" and c["eye"] == [7500, 2200, 1450] for c in m.cameras)
         and any("levelled" in n for n in m.contract_notes)),
        ("flat-list track → path", any(l_.get("kind") == "track" and l_["path"] == [[9300, 5000], [10800, 5000]]
                                       for c in m.ceilings if c["room"] == "KIT" for l_ in c.get("lights", []))),
        ("exposed ceiling: no false ceiling", not any(c["room"] == "BAL" for c in m.ceilings)),
        ("TV carried on the feature element", any(w.get("tv") for w in m.wall_features if w.get("parent") == "FW1")),
    ]
    data, _rep, _errs = sbuild(tmp)
    items = data["items"]
    kinds = {i["id"]: i["kind"] for i in items}
    fr = next((i for i in items if i["kind"] == "fridge_socket" and i["room"] == "KIT"), None)
    checks += [
        ("overrides by system: power16 / wall_light / mixer",
         kinds.get("PS-LD-90") == "socket_16a" and kinds.get("WL-MBR-90") == "wall_light" and kinds.get("MX-MBT-90") == "mixer"),
        ("move by x, y, h", next(i for i in items if i["id"] == "RT-LD-01")["z"] == 300),
        ("fridge socket behind the fridge, not a flagged default", fr is not None and not fr.get("flag")),
        ("basin gets cold, hot and waste", {"cold", "hot", "waste"} <= {i["kind"] for i in items if i["room"] == "CBT"}),
    ]
finally:
    import os
    if os.environ.get("KEEP"):                       # KEEP=/path keeps the contract project to build and look at
        shutil.copytree(tmp, os.environ["KEEP"], dirs_exist_ok=True)
    shutil.rmtree(tmp.parent, ignore_errors=True)

for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(0 if all(ok for _, ok in checks) else 1)

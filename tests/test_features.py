"""Feature walls from the reference interpreter (agents/reference.md, STANDARDS §4).
python tests/test_features.py"""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier import geom  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.validate import check  # noqa: E402

SAMPLE = ROOT / "projects" / "sample"
D = json.loads((SAMPLE / "design.json").read_text())
tmp = Path(tempfile.mkdtemp())
for f in ("survey.json", "services_overrides.json"):
    shutil.copy(SAMPLE / f, tmp / f)


def model(design):
    (tmp / "design_T.json").write_text(json.dumps(design))
    return load(tmp, "design_T.json")


def codes(m):
    r = check(m)
    return [c for c, _ in r.errors], [c for c, _ in r.warnings]


checks = []
m = model(D)
e, w = codes(m)
checks.append((f"sample feature walls validate ({e})", not e and "W-FEATURE-HIDDEN" not in w))
fw2 = [x for x in m.wall_features if x.get("parent") == "FW2"]
mural = next(x for x in fw2 if x["kind"] == "mural")
p = geom.point_on_wall(m.wall(mural["wall"]), mural["offset"] + mural["width"] / 2)
checks.append(("u runs from the left corner seen from inside (MBR mural at the south end)", p[1] < 5200))
pend = [lt for c in m.ceilings if c["room"] == "MBR" for lt in c.get("lights", []) if lt.get("source") == "FW2"]
checks.append(("pendants become ceiling fittings over the nightstands",
               sorted(tuple(x["at"]) for x in pend) == [(430, 4950), (430, 7050)]))

# a door inside a panelled element: error unless concealed, then drawn concealed
wide = copy.deepcopy(D)
fw1 = next(x for x in wide["wall_features"] if x["id"] == "FW1")
fw1["items"].append({"from": 2440, "to": 3500, "type": "fluted", "code": "WF3", "color": "warm oak"})
e, _ = codes(model(wide))
checks.append(("a door under a panel without concealed is refused", "E-FEATURE-OPENING" in e))
fw1["items"][-1]["concealed"] = True
mc = model(wide)
e, _ = codes(mc)
d2 = next(o for o in mc.openings if o["id"] == "D2")
checks.append(("concealed: true hides the door instead", "E-FEATURE-OPENING" not in e and d2.get("concealed")))

# a window may never be covered
win = copy.deepcopy(D)
win["wall_features"].append({"id": "FW9", "room": "MBR", "wall": "X3",
                             "items": [{"from": 0, "to": 2500, "type": "slats", "code": "WF8", "concealed": True}]})
e, _ = codes(model(win))
checks.append(("a window under an element is refused even with concealed", "E-FEATURE-OPENING" in e))

# overlapping elements and elements off the wall
bad = copy.deepcopy(D)
fw2d = next(x for x in bad["wall_features"] if x["id"] == "FW2")
fw2d["items"][1]["from"] = 900
e, _ = codes(model(bad))
checks.append(("overlapping elements refused", "E-FEATURE" in e))
bad = copy.deepcopy(D)
next(x for x in bad["wall_features"] if x["id"] == "FW2")["items"][-1]["to"] = 3900
e, _ = codes(model(bad))
checks.append(("element past the wall end refused", "E-FEATURE" in e))

# hidden behind tall joinery, and off-centre bed
hid = copy.deepcopy(D)
fw3 = next(x for x in hid["wall_features"] if x["id"] == "FW3")
fw3["items"].insert(0, {"from": 0, "to": 560, "type": "mirror", "code": "WF9"})
fw3["items"][1]["from"] = 600
_, w = codes(model(hid))
checks.append(("element behind wardrobe J6 warned", "W-FEATURE-HIDDEN" in w))
off = copy.deepcopy(D)
up = next(x for x in off["wall_features"] if x["id"] == "FW2")["items"][1]
up["to"] = 2600
next(x for x in off["wall_features"] if x["id"] == "FW2")["items"][2]["from"] = 2600
_, w = codes(model(off))
checks.append(("bed off the centre of its element warned", "W-FEATURE-CENTRE" in w))

shutil.rmtree(tmp)
fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

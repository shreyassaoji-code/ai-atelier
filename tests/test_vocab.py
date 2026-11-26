"""The designer brief's vocabulary (agents/designer.md) reaches the engine.   python tests/test_vocab.py"""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier import geom, vocab  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.services import Builder  # noqa: E402
from atelier.symbols import furniture_parts  # noqa: E402
from atelier.texture import named_tone  # noqa: E402
from atelier.validate import check  # noqa: E402

SAMPLE = ROOT / "projects" / "sample"
BRIEF = json.loads((ROOT / "tests" / "fixtures" / "design_brief.json").read_text())
tmp = Path(tempfile.mkdtemp())
for f in ("survey.json", "services_overrides.json"):
    shutil.copy(SAMPLE / f, tmp / f)


def model(design):
    (tmp / "design_T.json").write_text(json.dumps(design))
    return load(tmp, "design_T.json")


checks = []
m = model(BRIEF)
rep = check(m)
checks.append((f"brief fixture validates ({[c for c, _ in rep.errors]})", not rep.errors))

# tray in the brief's form = the sample's engine ceiling
ref = next(c for c in load(SAMPLE).ceilings if c["room"] == "LD")
got = next(c for c in m.ceilings if c["room"] == "LD")
checks.append(("tray steps/band/core_h -> same levels and insets as the sample",
               got["z"] == ref["z"] and [(s["inset"], s["z"]) for s in got["steps"]] ==
               [(s["inset"], s["z"]) for s in ref["steps"]] and got["domes"][0]["z"] == ref["domes"][0]["z"]))
area = [[1000, 1000], [4000, 1000], [4000, 3000], [1000, 3000]]
c = vocab._ceiling({"room": "R", "type": "tray", "area": area, "steps": [{"band": 400, "z": 2550}], "core_h": 2650},
                   None)
checks.append(("area tray -> partial step polygon inset by the band",
               c["z"] == 2550 and c["steps"][0]["poly"][0] == [1400, 1400] and c["steps"][0]["light"] == "cove"))

# names, kinds, materials
checks.append(("floor material pattern words mapped", {f["pattern"] for f in m.floors} <= {"straight", "plank",
                                                                                          "herringbone"}))
checks.append(("joinery materials -> finish", next(j for j in m.joinery if j["id"] == "J3")["finish"] == "MB-1"))
checks.append(("nightstand -> bedside", all(f["kind"] != "nightstand" for f in m.furniture)))
checks.append(("opening_overrides applied", next(o for o in m.openings if o["id"] == "W1")["width"] == 1800))
checks.append(("camera wall -> room board view", any(v.get("kind") == "room_board" and v["room"] == "KIT"
                                                      for v in m.views)))
checks.append(("palette, style, summary kept", m.extras.get("palette") and m.extras.get("style")
               and m.extras.get("summary")))
checks.append(("named tones: known names mix, unknown is None", named_tone("deep olive") is not None
               and named_tone("cobalt") is None))

# lamps only where asked; velvet bed keeps its bedding
bs = {"kind": "bedside", "size": [450, 400, 500], "at": [0, 0]}
checks.append(("no lamp unless lamp:true", len(furniture_parts(bs)) == 1 and len(furniture_parts(dict(bs, lamp=True))) == 3))
bed = {"kind": "bed", "size": [1600, 2000, 450], "at": [0, 0], "finish": "velvet", "headboard": "curved"}
roles = [r for _, r in furniture_parts(bed)]
checks.append(("velvet bed: frame velvet, bedding not", "velvet_dk" in roles and "cushion" in roles))

# switch spots replace the rule's switchboards in that room
sbs = [i for i in Builder(m).run() if i["kind"] == "switchboard" and i["room"] == "LD"]
checks.append(("switch_spots place LD switchboards", len(sbs) == 2 and all(i["rule"] == "design" for i in sbs)))

# guards
bad = copy.deepcopy(BRIEF)
bad["demolish"] = bad.get("demolish", []) + [{"wall": "X2"}]
checks.append(("external wall demolition refused", "E-DEMOLISH-STRUCT" in [c for c, _ in check(model(bad)).errors]))
bad = copy.deepcopy(BRIEF)
bad["ceilings"][0]["core_h"] = 2900
checks.append(("tray level < 150 below slab refused", any(c == "E-CEIL" and "150" in msg
                                                          for c, msg in check(model(bad)).errors)))
bad = copy.deepcopy(BRIEF)
bad["opening_overrides"] = [{"id": "NOPE", "width": 900}]
checks.append(("override of a missing opening refused", "E-REF" in [c for c, _ in check(model(bad)).errors]))
bad = copy.deepcopy(BRIEF)
next(j for j in bad["joinery"] if j.get("materials"))["materials"]["hardware"] = "HW-9"
checks.append(("unknown joinery material code refused", "E-FINISH" in [c for c, _ in check(model(bad)).errors]))

shutil.rmtree(tmp)
fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

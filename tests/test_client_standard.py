"""Client standard (Xelion Labs) items added 2026-11-26.   python tests/test_client_standard.py

§2 album order and the axonometry / doors & windows / visualisations sheets; §6 heights
(WM inlet 1050, split IDU 2300, AC socket 2100) and RCCB on wet and socket circuits; §5 wall letters.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier.album import ORDER, page_names  # noqa: E402
from atelier.elev_detail import wall_letters  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.services import Builder  # noqa: E402

P = ROOT / "projects" / "sample"
m = load(P)
names = page_names(m, P)
pos = {k: i for i, k in enumerate(ORDER)}
checks = [
    ("new sheets in the album", all(n in names for n in ("axonometry", "doors_windows", "visualisations"))),
    ("client order: boards → axonometry → doors & windows → flooring",
     pos["room:*"] < pos["axonometry"] < pos["doors_windows"] < pos["flooring"]),
    ("client order: elevations → feature walls → furniture marking → DT → JN → visualisations",
     pos["elevation:*"] < pos["feature:*"] < pos["furniture"] < pos["dt01"] < pos["joinery:*"] < pos["visualisations"]),
]
S = json.loads((P / "services.json").read_text())["items"]
db = next(i for i in S if i["kind"] == "db")
wm_cold = [i for i in S if i["room"] == "BAL" and i["kind"] == "cold"]
checks += [
    ("WM inlet h1050", wm_cold and all(i["z"] == 1050 for i in wm_cold)),
    ("DB carries RCCB 30 mA on wet and socket circuits",
     db.get("protection", {}).get("rccb_ma") == 30 and db["protection"].get("socket_circuits")
     and {"MBT", "CBT", "KIT"} <= set(db["protection"]["wet_rooms"])),
]
# split rooms: a design without feature walls gets split units → IDU 2300, AC socket 2100
m2 = load(P)
m2.feature_walls = []
m2.wall_features = [w for w in m2.wall_features if not w.get("parent")]
b = Builder(m2)
b.run()
splits = [i for i in b.items if i["kind"] == "split"]
iso = [i for i in b.items if i["kind"] == "ac_isolator"]
checks += [
    ("split indoor unit h2300", splits and all(i["z"] == 2300 for i in splits)),
    ("AC socket h2100", iso and all(i["z"] == 2100 for i in iso)),
]
L = wall_letters(m, "KIT")
checks.append(("kitchen walls lettered A, B, C …", sorted(L.values())[:3] == ["A", "B", "C"]))
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(0 if all(ok for _, ok in checks) else 1)

"""Joinery boards (STANDARDS §5b).   python tests/test_boards.py"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
from atelier import boards as B  # noqa: E402
from atelier.model import load  # noqa: E402

m = load(ROOT / "projects" / "sample")
ids = [j["id"] for j in m.joinery]
items = {jid: B.Item(m, j) for jid, j in zip(ids, m.joinery)}

checks = [
    ("JN numbers follow data order", [B.jn_number(m, i) for i in ids] == [f"JN-{k:02d}" for k in range(1, len(ids) + 1)]),
    ("every item's module widths sum to its run (JB5b.8)", all(it.sums_ok() for it in items.values())),
]


def tiles(it):
    """Modules cover 0..W with no gap or overlap (order may run either way along the wall)."""
    sp = sorted((md["xa"], md["xb"]) for md in it.mods)
    return abs(sp[0][0]) < 1 and abs(sp[-1][1] - it.W) < 1 and all(abs(a[1] - b[0]) < 1 for a, b in zip(sp, sp[1:]))


checks.append(("modules tile 0..W on every board", all(tiles(it) for it in items.values())))

# wardrobe plan reserves the widest shutter swing
for it in items.values():
    if it.j.get("kind") == "wardrobe":
        widest = max((md["xb"] - md["xa"] for md in it.mods if md["type"] in ("shutter", "glass_shutter")), default=0)
        checks.append((f"{it.j['id']} plan depth includes shutter swing", B.plan_depth(it) >= it.Dp + widest))
        break

# a broken module width must stop the build
bad = copy.deepcopy(m)
j = next(x for x in bad.joinery if x.get("rows"))
j["rows"][0]["modules"][0]["w"] += 10
try:
    B.board(bad, 1, 1, j["id"])
    raised = False
except ValueError as e:
    raised = "do not sum" in str(e)
checks.append(("altered module width raises ValueError", raised))

fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

"""Details and bubble numbering (STANDARDS §5 E5.12, §5a).   python tests/test_details.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
from atelier import details as DT  # noqa: E402
from atelier import elev_detail as ED  # noqa: E402
from atelier.model import load  # noqa: E402

m = load(ROOT / "projects" / "sample")
fw, wall = DT._src_panel(m)
o, ow = DT._src_door(m)
checks = [
    ("detail 2 takes the fluted panel FW1", fw and fw["id"] == "FW1"),
    ("detail 3 takes the tallest skirting (100)", DT._src_skirting(m)["skirting"] == 100),
    ("detail 4 takes an internal door", o and ow.get("kind") != "external"),
    ("detail 5 takes the kitchen base run J3", DT._src_join(m, ("kitchen_base",))["id"] == "J3"),
    ("detail 6 takes a wardrobe", DT._src_join(m, ("wardrobe",))["kind"] == "wardrobe"),
    ("1-3 -> DT-01, 4-6 -> DT-02", all(ED.BUBBLE_SHEET[n] == ("DT-01" if n <= 3 else "DT-02") for n in range(1, 7))),
]

# which bubbles the kitchen sink wall gets: only 5 (worktop + gola + base unit)
seen = []
orig = ED._bubble
ED._bubble = lambda sh, x, y, n, target: seen.append(n)
view = next(v for v in m.views if v["id"] == "E-KIT-1")
from atelier.draw import Sheet  # noqa: E402
ED.draw_elevation(Sheet(), m, view, 40, 180)
ED._bubble = orig
checks.append(("sink wall bubbles = [5] (no cove, panel, skirting, door or wardrobe on it)", seen == [5]))
for n, ok in checks:
    print(("✓ " if ok else "✗ ") + n)
assert all(ok for _, ok in checks)
print(f"OK: {len(checks)} detail checks pass")

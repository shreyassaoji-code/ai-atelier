"""Room boards (STANDARDS §2a).   python tests/test_room_board.py"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
from shapely.geometry import Point  # noqa: E402

from atelier import geom  # noqa: E402
from atelier import room_board as RB  # noqa: E402
from atelier import views3d as V3  # noqa: E402
from atelier.model import load  # noqa: E402

m = load(ROOT / "projects" / "sample")
rooms = V3.board_rooms(m)
checks = [("boards for LD, KIT, MBR, BR2", sorted(r["id"] for r in rooms) == ["BR2", "KIT", "LD", "MBR"])]

for r in rooms:
    faces = V3.key_walls(m, r)
    checks.append((f"{r['id']}: two key walls", len(faces) == 2))
    checks.append((f"{r['id']}: no blank wall", all(not V3.is_blank(V3.wall_content(m, r, f)) for f in faces)))
    L = RB.layout(m, r, faces)
    checks.append((f"{r['id']}: plan scale 1:{L['scale']} in 1:40-1:75", L["scale"] in RB.PLAN_SCALES))
    cams = V3.room_cameras(m, r)
    inside = geom.room_polygon(r)
    checks.append((f"{r['id']}: 3 cameras inside the room, level", len(cams) == 3 and all(
        inside.contains(Point(c["eye"][:2])) and c["eye"][2] == c["target"][2] for c in cams)))
    # crop: nothing from neighbours, except the room's own walls
    crop = RB.crop_region(m, r)
    others = [o for o in m.rooms if o["id"] != r["id"]]
    leak = max(crop.intersection(geom.room_polygon(o)).area for o in others)
    checks.append((f"{r['id']}: crop holds no neighbouring floor (max {leak:.0f} mm²)", leak < 1.0))

kit = m.room("KIT")
first = V3.key_walls(m, kit)[0]
checks.append(("kitchen elevation 1 backs joinery", V3.wall_content(m, kit, first)["joinery"] > 0))

# named walls in views[] override the rule
m2 = copy.deepcopy(m)
m2.views.append({"id": "RB-MBR", "kind": "room_board", "room": "MBR", "walls": ["X3", "I1a"]})
checks.append(("views[] room_board walls are used", [f.wall for f in V3.key_walls(m2, m2.room("MBR"))] == ["X3", "I1a"]))

# a room whose walls are all blank fails instead of drawing a blank wall
m3 = copy.deepcopy(m)
for name in ("joinery", "wall_features", "furniture"):
    getattr(m3, name)[:] = [x for x in getattr(m3, name) if x.get("room") != "BR2"]
try:
    faces = V3.key_walls(m3, m3.room("BR2"))
    checks.append(("blank walls are never chosen", all(not V3.is_blank(V3.wall_content(m3, m3.room("BR2"), f))
                                                       for f in faces)))
except Exception as e:  # noqa: BLE001
    checks.append((f"blank walls are never chosen ({e})", False))

fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

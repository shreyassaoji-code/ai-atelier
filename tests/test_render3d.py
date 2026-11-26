"""White-model 3D (atelier/render3d.py).   python tests/test_render3d.py

Without Blender: the palette (white, oak, linen, dark, emission kept, floors keep their images),
axonometric framing, the plan section that becomes the dark cut tops, and the camera check
(moves a camera whose frame is filled by a near surface, keeps good ones, is stable once moved).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from shapely.geometry import Point  # noqa: E402

from atelier import geom  # noqa: E402
from atelier import render3d as R3  # noqa: E402
from atelier import views3d as V3  # noqa: E402
from atelier.frames import frame_file  # noqa: E402
from atelier.model import load  # noqa: E402

m = load(ROOT / "projects" / "sample")
checks = []
st = {k: R3.style(k, sp) for k, sp in {
    "plaster": {"color": (0.9, 0.9, 0.9)}, "oak": {"color": (0.85, 0.73, 0.56), "grain": True},
    "fabric": {"color": (0.5, 0.6, 0.5), "sheen": True}, "led": {"emit": (1, 0.9, 0.7), "strength": 5},
    "floor-MBR": {"color": (0.8, 0.7, 0.5), "image": "x.png", "plane": (0, 0, 1, 1)},
    "frame": {"color": (0.4, 0.4, 0.4), "metal": 0.6}, "ground": {"color": (0.5, 0.6, 0.4)}}.items()}
lum = {k: float(np.mean(v["color"])) for k, v in st.items()}
checks += [
    ("walls white", lum["plaster"] > 0.9),
    ("oak accent warm", st["oak"]["color"][0] > st["oak"]["color"][2] + 0.1),
    ("fabric becomes linen (no colour)", abs(st["fabric"]["color"][0] - st["fabric"]["color"][1]) < 0.06),
    ("cove LED keeps its emission", st["led"].get("strength") == 5),
    ("floors keep their image", st["floor-MBR"].get("image") == "x.png"),
    ("metal frames dark", lum["frame"] < 0.4),
    ("ground reads as paper", lum["ground"] > 0.85),
]
for r in V3.board_rooms(m):
    ax = R3.axo_camera(m, r)
    checks.append((f"axo {r['id']}: orthographic, looks down, file ax_{r['id']}.png",
                   ax["kind"] == "axo" and ax["eye"][2] > ax["target"][2] and frame_file(ax) == f"ax_{r['id']}.png"))
sec = R3.section_at(m, 1500)
door = next(o for o in m.openings if o["kind"] == "door")
win = next(o for o in m.openings if o["kind"] == "window" and o.get("sill", 900) < 1500)
j6 = next(j for j in m.joinery if j["id"] == "J6")
checks += [
    ("section: walls cut", sec.area > geom.walls_union(m.walls).area * 0.5),
    ("section: door opening left open", not sec.contains(geom.opening_polygon(m.wall(door["wall"]), door, extra=0).centroid)),
    ("section: window spanning the cut left open", not sec.contains(geom.opening_polygon(m.wall(win["wall"]), win, extra=0).centroid)),
    ("section: 2400 wardrobe capped", sec.contains(geom.joinery_polygon(j6, m.wall(j6["wall"]), m.room("BR2")).centroid)),
]
raw = {c["id"]: c for r in V3.board_rooms(m) for c in [dict(x) for x in V3.room_cameras(m, r)]}
br = raw["V-BR2-1"]
checks += [
    ("BR2-1 moved off the wardrobe end panel", bool(br.get("moved"))),
    ("moved camera passes the check (stable)", R3.check_camera(m, {k: v for k, v in br.items()
                                                                   if k not in ("moved", "moved_why")})[1] == 0),
    ("every corner camera inside its room",
     all(geom.room_polygon(m.room(c["room"])).buffer(-150).contains(Point(c["eye"][:2])) for c in raw.values())),
    ("good cameras untouched", sum(1 for c in raw.values() if c.get("moved")) <= 2),
]
far = dict(br, eye=[7800, 4300, 1350])          # tight against wardrobe J6's end, looking NW
c2, mv, why = R3.check_camera(m, far)
checks.append(("a camera against a unit is moved or refused", mv is None or bool(mv)))
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(0 if all(ok for _, ok in checks) else 1)

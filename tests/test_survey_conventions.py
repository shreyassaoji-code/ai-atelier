"""Surveyor conventions (agents/surveyor.md): centre-line walls split at junctions, px_per_mm
calibration, ceiling_height_flag.   python tests/test_survey_conventions.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shapely.geometry import box  # noqa: E402

from atelier import geom  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.overlay import mm_to_px_fn  # noqa: E402
from atelier.validate import check  # noqa: E402

W = lambda i, a, b, t, k="external": {"id": i, "a": a, "b": b, "t": t, "align": "centre", "kind": k}  # noqa: E731
survey = {
    "schema": "atelier/survey@1", "project": {"name": "t", "address": None, "source": "plan.png", "date": "2026-11-26"},
    "levels": {"ffl": 0, "ceiling": 2750, "soffit": 3000, "lintel": 2100, "sill": 900, "ceiling_height_flag": True},
    "calibration": {"image": "plan.png", "px_per_mm": 0.12, "origin_px": [60, 560]},
    "walls": [W("X1", [0, 0], [3000, 0], 230), W("X2", [3000, 0], [6000, 0], 230), W("X3", [6000, 0], [6000, 4000], 230),
              W("X4", [6000, 4000], [3000, 4000], 230), W("X5", [3000, 4000], [0, 4000], 230),
              W("X6", [0, 4000], [0, 0], 230), W("I1", [3000, 0], [3000, 4000], 150, "internal")],
    "openings": [{"id": "D1", "wall": "I1", "offset": 1500, "width": 900, "kind": "door", "swing": "left",
                  "hinge": "start", "head": 2100},
                 {"id": "W1", "wall": "X3", "offset": 1200, "width": 1500, "kind": "window", "swing": "none",
                  "hinge": "none", "sill": 900, "head": 2250, "flag": True},
                 {"id": "W2", "wall": "X6", "offset": 1200, "width": 1500, "kind": "window", "swing": "none",
                  "hinge": "none", "sill": 900, "head": 2250, "flag": True}],
    "rooms": [{"id": "A", "name": "A", "type": "living", "poly": [[115, 115], [2925, 115], [2925, 3885], [115, 3885]]},
              {"id": "B", "name": "B", "type": "bedroom", "poly": [[3075, 115], [5885, 115], [5885, 3885], [3075, 3885]]}],
    "flags": [],
}
tmp = Path(tempfile.mkdtemp())
(tmp / "survey.json").write_text(json.dumps(survey))
m = load(tmp, design=False)
checks = []
rep = check(m)
checks.append((f"centre-line walls split at junctions validate ({[c for c, _ in rep.errors]})", not rep.errors))
u = geom.walls_union(m.walls)
outer = box(-115, -115, 6115, 4115)
corner = box(-115, -115, 0, 0)
checks.append(("outer corners are filled", u.contains(corner.buffer(-1)) and abs(u.area - (
    outer.area - geom.room_polygon(m.rooms[0]).area - geom.room_polygon(m.rooms[1]).area)) < 50))
checks.append(("ceiling_height_flag flags the ceiling", m.is_flagged(dict(m.levels), "ceiling")))
f = mm_to_px_fn(m.calibration)
x, y = f(1000, 2000)
checks.append(("px_per_mm + origin_px maps plan to image", abs(x - (60 + 120)) < 1e-6 and abs(y - (560 - 240)) < 1e-6))
# face-aligned walls get no joints (the sample stays as drawn)
s = load(ROOT / "projects" / "sample", design=False)
checks.append(("face-aligned walls get no corner fill", geom.wall_joints(s.walls) == []))
shutil.rmtree(tmp)
fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

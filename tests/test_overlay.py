"""Overlay self-test.   python tests/test_overlay.py

The sample has no source image, so this test makes one: it renders the measured
sheet, calibrates it with two known points (the plan corners as drawn), and
overlays the survey walls. Red must sit on the black poche: the test measures
how much of each wall polygon covers dark pixels, then writes the overlay to
/tmp/overlay-test.png for a visual check.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from atelier import geom  # noqa: E402
from atelier.draw import PlanView, Sheet, envelope_bounds  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.overlay import mm_to_px_fn, overlay  # noqa: E402
from atelier.sheets import fit_scale, measured  # noqa: E402

DPI = 200
tmp = Path(tempfile.mkdtemp())
proj = tmp / "p"
shutil.copytree(ROOT / "projects" / "sample", proj, ignore=shutil.ignore_patterns("out"))

m = load(proj, design=False)
sh = measured(m, 1, 1)
sh.save(png=tmp / "p" / "plan.png", dpi=DPI)

# where the engine put two plan points on the page -> pixels
bounds = envelope_bounds(m.survey_walls)
pv = PlanView(Sheet(), bounds, fit_scale(bounds))
k = DPI / 25.4
a_mm, b_mm = [0, 0], [11400, 7800]
a_px = [round(c * k, 1) for c in pv.P(*a_mm)]
b_px = [round(c * k, 1) for c in pv.P(*b_mm)]
sv = json.loads((proj / "survey.json").read_text())
sv["calibration"] = {"image": "plan.png", "a_px": a_px, "b_px": b_px, "a_mm": a_mm, "b_mm": b_mm}
(proj / "survey.json").write_text(json.dumps(sv))

out = overlay(proj, Path("/tmp/overlay-test.png"))
assert out and out.exists()

# alignment: the inside of each full-height wall should be dark poche in the source image
img = Image.open(proj / "plan.png").convert("L")
f = mm_to_px_fn(sv["calibration"])
worst = 1.0
for w in m.survey_walls:
    if w["kind"] == "parapet":
        continue
    poly = geom.cut_walls([w], [o for o in m.survey_openings if o["wall"] == w["id"]]).buffer(-25)
    hits = total = 0
    minx, miny, maxx, maxy = poly.bounds
    step = 20
    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            from shapely.geometry import Point
            if poly.contains(Point(x, y)):
                px, py = f(x, y)
                total += 1
                hits += img.getpixel((int(px), int(py))) < 80
            x += step
        y += step
    if total:
        worst = min(worst, hits / total)
        print(f"  {w['id']:3} {hits / total:6.1%} of {total} samples on dark poche")
assert worst > 0.97, worst
print(f"OK: overlay aligned (worst wall {worst:.1%} on poche); image /tmp/overlay-test.png")

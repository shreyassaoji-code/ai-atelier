"""Ceiling geometry and validation (STANDARDS §3).   python tests/test_ceiling.py"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier import geom  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.validate import check  # noqa: E402

m = load(ROOT / "projects" / "sample")
ld, c = m.room("LD"), next(c for c in m.ceilings if c["room"] == "LD")
mbr, cm = m.room("MBR"), next(c for c in m.ceilings if c["room"] == "MBR")
z = lambda r, cc, p: round(geom.ceiling_z_at(r, cc, p))  # noqa: E731
cases = [
    ("LD band, 200 from the south wall", z(ld, c, (2000, 430)), 2550),
    ("LD step, 600 in", z(ld, c, (2000, 830)), 2650),
    ("LD core, 1500 in", z(ld, c, (2000, 1730)), 2720),
    ("LD dome apex at its centre", z(ld, c, (7000, 2300)), 2900),
    ("MBR partial tray (area) over the bed", z(mbr, cm, (1500, 6000)), 2650),
    ("MBR outside the partial tray", z(mbr, cm, (3300, 4400)), 2550),
]
for name, got, want in cases:
    print(("✓ " if got == want else "✗ ") + f"{name}: +{got} (want +{want})")
assert all(g == w for _, g, w in cases)

bad = copy.deepcopy(m)
bc = next(c for c in bad.design["ceilings"] if c["room"] == "MBR")
bc["steps"][0]["poly"] = [[600, 4600], [3500, 4600], [3500, 7200], [600, 7200]]   # runs into the dress room
codes = {c_ for c_, _ in check(bad).errors}
print(("✓ " if "E-CEIL" in codes else "✗ ") + "partial tray outside its room is rejected (E-CEIL)")
assert "E-CEIL" in codes
print("OK: ceiling levels and validation")

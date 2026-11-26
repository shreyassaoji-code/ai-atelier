"""Machine pre-check (agents/checker.md).   python tests/test_check.py

Runs on the sample, writes out/check.md; the engine-side sections (data, album, elevations, boards,
look) must be clean, and short faces that carry a wall point get an elevation.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier.check import run, write  # noqa: E402
from atelier.elev_detail import elevation_views  # noqa: E402
from atelier.model import load  # noqa: E402

P = ROOT / "projects" / "sample"
R = run(P)
out = write(P, R)
fails = [(s, t) for s, st, t in R.rows if st == "FAIL"]
engine = [f for f in fails if f[0].split()[0] in ("0", "2", "5", "5a", "5b", "7")]
checks = [
    ("check.md written", out.exists() and "Pre-check" in out.read_text()),
    ("no engine-side FAIL " + str(engine), not engine),
    ("LOOK items left for a person", any(st == "LOOK" for _, st, _ in R.rows)),
    ("595 face carrying SB-KIT-01 has an elevation", "E-KIT-I1b" in {v["id"] for v in elevation_views(load(P))}),
]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(0 if all(ok for _, ok in checks) else 1)

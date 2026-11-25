"""Validator self-test.   python tests/test_validate.py

1. The sample survey must validate with 0 errors.
2. tests/broken-design.json must trigger every error code listed below.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier.model import load  # noqa: E402
from atelier.validate import check  # noqa: E402

SAMPLE = ROOT / "projects" / "sample"
MUST_FIRE = {"E-WALL-OVERLAP", "E-OPENING-WIDTH", "E-FURN-OUTSIDE", "E-FURN-OVERLAP",
             "E-SWING-BLOCKED", "E-JOINERY-SUM", "E-ROOM-NO-DOOR", "E-AREA", "E-ENUM"}

clean = check(load(SAMPLE))
assert not clean.errors, clean.errors

# E-ENUM stops geometry checks, so test it separately from the geometry errors.
broken = check(load(SAMPLE, str(ROOT / "tests" / "broken-design.json")))
codes = {c for c, _ in broken.errors}
assert "E-ENUM" in codes, codes

import json, tempfile  # noqa: E401,E402
d = json.loads((ROOT / "tests" / "broken-design.json").read_text())
d["furniture"] = [f for f in d["furniture"] if f["kind"] != "throne"]
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
    json.dump(d, fh)
geo = check(load(SAMPLE, fh.name))
codes |= {c for c, _ in geo.errors}

missing = MUST_FIRE - codes
for c, msg in broken.errors + geo.errors:
    print(f"  {c:18} {msg}")
print("missing:", sorted(missing) or "none")
assert not missing, missing
print(f"OK: sample clean; all {len(MUST_FIRE)} error codes fire on the broken design")

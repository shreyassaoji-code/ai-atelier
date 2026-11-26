"""Machine pre-check (agents/checker.md).   python tests/test_check.py

Runs on the sample, writes out/check.md and out/check.json; the engine-side sections (data, album,
elevations, boards, look) must be clean; check.json validates, keeps the checker's own items and
verdict across a re-run, and the validator catches a bad file. Short faces carrying a point get a sheet.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier.check import run, validate_json, write, write_json  # noqa: E402
from atelier.elev_detail import elevation_views  # noqa: E402
from atelier.model import load  # noqa: E402

P = ROOT / "projects" / "sample"
m = load(P)
R = run(P)
md = write(P, R)
js = P / "out" / "check.json"
backup = js.read_text() if js.exists() else None
checks = []
try:
    if js.exists():
        js.unlink()
    write_json(P, R, m)
    n = len(R.pages)
    d = json.loads(js.read_text())
    engine = [i for i in R.items if i["sec"].split()[0] in ("0", "2", "5", "5a", "5b", "7")]
    checks += [
        ("check.md written", md.exists() and "Pre-check" in md.read_text()),
        ("no engine-side FAIL " + str([i["issue"] for i in engine]), not engine),
        ("LOOK items left for a person", bool(d["look"])),
        ("check.json validates", validate_json(js, n) == []),
        ("every must_fix has a page and a fix naming a field",
         all(i["sheet"] and ("." in i["fix"] or "design.json" in i["fix"]) for i in d["must_fix"])),
        ("flagged values listed under verify_on_site", any("ceiling" in v for v in d["verify_on_site"])),
        ("verdict is ready after fixes", d["verdict"] == "ready after fixes"),
    ]
    mine = {"sheet": 3, "issue": "W2 sill reads 900 on the plan", "fix": "survey.json openings W2.sill → 900"}
    d["must_fix"].append(mine)
    d["verdict"], d["verdict_by"] = "not ready", "checker"
    d["verify_on_site"].append("my own note")
    js.write_text(json.dumps(d))
    write_json(P, R, m)
    d2 = json.loads(js.read_text())
    checks += [
        ("checker's own item survives a re-run", mine in d2["must_fix"]),
        ("machine items are not duplicated", len(d2["must_fix"]) == len(d["must_fix"])),
        ("checker's verdict survives a re-run", d2["verdict"] == "not ready"),
        ("checker's verify note survives", "my own note" in d2["verify_on_site"]),
    ]
    bad = dict(d2, verdict="ready")
    bad["must_fix"] = d2["must_fix"] + [{"sheet": 999, "issue": "", "fix": "x"}]
    js.write_text(json.dumps(bad))
    errs = validate_json(js, n)
    checks += [
        ("validator: page out of range", any("999" in e for e in errs)),
        ("validator: empty issue", any("issue is empty" in e for e in errs)),
        ("validator: ready with must_fix", any("'ready'" in e for e in errs)),
    ]
finally:
    if backup is not None:
        js.write_text(backup)
    else:
        write_json(P, R, m)

checks.append(("595 face carrying SB-KIT-01 has an elevation",
               "E-KIT-I1b" in {v["id"] for v in elevation_views(m)}))
for n_, ok in checks:
    print(("ok   " if ok else "FAIL ") + n_)
sys.exit(0 if all(ok for _, ok in checks) else 1)

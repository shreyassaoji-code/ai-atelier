"""A designer's quick look at one design file, without touching the album.

    python -m atelier.preview projects/<name> design_<X>.json
        -> projects/<name>/out/preview_<X>.png           (layout: furniture + joinery plan)
           projects/<name>/out/preview_<X>_ceiling.png   (ceiling plan)
    python -m atelier.preview projects/<name>         every design_*.json in the project (for the judges)

The services (downlights, fans, coves) are worked out in memory for this design by the
STANDARDS §6 rules; services_overrides.json is not applied (it belongs to design.json).
Validation runs first and its result is printed; the PNGs are drawn even with errors so
the designer can see what is wrong.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from atelier.model import load
from atelier.services import Builder
from atelier.sheets import furniture_plan
from atelier.sheets_ceiling import ceiling_plan
from atelier.validate import check


def preview(root: Path, design: str, dpi: int = 150):
    m = load(root, design)
    if design not in m.sources:
        raise SystemExit(f"{design} not found in {root}")
    rep = check(m)
    for c, msg in rep.errors:
        print(f"  {c:18} {msg}")
    print(f"validate {'✓' if not rep.errors else '✗'} {len(rep.errors)} errors, {len(rep.warnings)} warnings")
    m.services_items = Builder(m).run()
    out = root / "out"
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(design).stem
    tag = stem.split("design_", 1)[1] if stem.startswith("design_") else stem
    made = []
    for name, fn in (("", furniture_plan), ("_ceiling", ceiling_plan)):
        png = out / f"preview_{tag}{name}.png"
        fn(m, 1, 1).save(None, png, dpi)
        made.append(png)
    for p in made:
        print(f"preview ✓ {p}")
    return 0 if not rep.errors else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.preview")
    ap.add_argument("project", type=Path)
    ap.add_argument("design", nargs="?", help="design file in the project, e.g. design_A.json (default: every design_*.json)")
    ap.add_argument("--dpi", type=int, default=150)
    a = ap.parse_args(argv)
    designs = [a.design] if a.design else sorted(p.name for p in a.project.glob("design_*.json"))
    if not designs:
        print(f"no design_*.json in {a.project}")
        return 2
    return max(preview(a.project, d, a.dpi) for d in designs)


if __name__ == "__main__":
    sys.exit(main())

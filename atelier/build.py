"""Build one project, or every project under a folder:

    python -m atelier.build projects/                      # every project: validate -> services -> 3D -> album
    python -m atelier.build projects/sample                # one project
    python -m atelier.build projects/sample --sheet ceiling --sheet room:KIT   # partial: those pages only
    --no-render   skip the 3D step (room boards use renders already cached, or show RENDER NOT PRODUCED)

Steps, in order; a step that fails stops that project:
  1 validate   atelier.validate: any error stops the build
  2 services   atelier.services: services.json from the STANDARDS §6 rules + services_overrides.json
  3 3D         atelier.render: vignettes for the room boards (cached by data + camera)
  4 album      atelier.album: pages in STANDARDS §2 order -> out/pages/NN.png + out/album.pdf

album.pdf is only ever replaced by a complete, checked build, or spliced page by page by a
partial build of the same album: a partial build never leaves it with fewer pages.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from atelier import album, services
from atelier.model import load
from atelier.validate import check


def build_project(root: Path, a) -> int:
    t0 = time.time()
    say = print if a.verbose else (lambda *x, **k: None)
    say(f"== {root}")
    m = load(root, a.design)
    rep = check(m)                                                     # 1 validate
    if rep.errors:
        for c, msg in rep.errors:
            print(f"  {c:18} {msg}")
        print(f"  validate ✗ {len(rep.errors)} errors: fix the data; nothing built")
        return 1
    say(f"  validate ✓ 0 errors, {len(rep.warnings)} warnings")
    data, _rep, errs = services.build(root)                            # 2 services
    if errs:
        for e in errs:
            print(f"  ERROR {e}")
        print("  services ✗ override errors; nothing built")
        return 1
    (root / "services.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"services ✓" + (f" {len(data['items'])} items" if a.verbose else ""))
    m = load(root, a.design)
    if a.no_render:                                                    # 3 3D
        say("3D skipped (--no-render)")
    else:
        import subprocess
        r = subprocess.run([sys.executable, "-m", "atelier.render", str(root)],
                           capture_output=not a.verbose, text=True)   # Blender prints from C: keep it out of the log
        if r.returncode == 0:
            print("3D ✓")
        else:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] if not a.verbose else []
            print(f"3D ✗ {tail[0] if tail else 'render failed'}: room boards will show RENDER NOT PRODUCED")
    try:                                                               # 4 album
        made, failed, verdict = album.build(m, root, a.sheet, a.dpi, log=say if not a.verbose else print)
    except ValueError as e:
        print(f"album ✗ {e}")
        return 1
    for i, name, e in failed:
        print(f"  page {i:02d} {name} FAILED: {e}")
    pdf = root / "out" / "album.pdf"
    if failed:
        print(f"album ✗ {verdict}")
    elif a.sheet:
        print(f"album ✓ {pdf} ({verdict})")
    else:
        print(f"album ✓ {pdf} ({len(m.album)} sheets)")
    say(f"  ({time.time() - t0:.0f}s)")
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.build")
    ap.add_argument("path", type=Path, help="a project folder, or a folder of projects")
    ap.add_argument("--sheet", action="append", help="page name(s) to build (partial build)")
    ap.add_argument("--design", help="design file (default design.json)")
    ap.add_argument("--no-render", "--norender", dest="no_render", action="store_true")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("-v", "--verbose", action="store_true", help="every step and page")
    a = ap.parse_args(argv)
    roots = [a.path] if (a.path / "survey.json").exists() else sorted(p.parent for p in a.path.glob("*/survey.json"))
    if not roots:
        print(f"no survey.json found under {a.path}")
        return 2
    return 1 if sum(build_project(r, a) for r in roots) else 0


if __name__ == "__main__":
    sys.exit(main())

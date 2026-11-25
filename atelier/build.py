"""Build sheets for a project.

    python -m atelier.build projects/sample                 # all sheets + album
    python -m atelier.build projects/sample --sheet plan    # one sheet
    --norender  skips 3D renders (none are wired in yet)
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from pypdf import PdfWriter


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--sheet", action="append", help="sheet module name(s) to build")
    ap.add_argument("--norender", action="store_true")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args(argv)

    proj = json.loads((a.project / "project.json").read_text())
    sheets = proj["sheets"]
    wanted = a.sheet or sheets
    out = a.project / "out" / "sheets"
    built = []
    for i, name in enumerate(sheets, 1):
        if name not in wanted:
            continue
        mod = importlib.import_module(f"atelier.sheets.{name}")
        sh = mod.build(a.project, i, len(sheets))
        pdf, png = out / f"{i:02d}-{name}.pdf", out / f"{i:02d}-{name}.png"
        sh.save(pdf, png, a.dpi)
        built.append(pdf)
        print(f"{name} ✓ {png}")
    if not a.sheet:
        w = PdfWriter()
        for p in built:
            w.append(str(p))
        album = a.project / "out" / "album.pdf"
        w.write(str(album))
        print(f"album ✓ {album} ({len(built)} sheets)")


if __name__ == "__main__":
    main()

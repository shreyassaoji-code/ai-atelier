"""Build a project's sheets from its data.

    python -m atelier.build projects/sample                      # all sheets + album
    python -m atelier.build projects/sample --sheet measured     # one sheet
    --norender  skips 3D renders (room boards then show only renders already cached)

Sheets are listed in projects/<name>/project.json ("sheets": [...]) and
defined in atelier/sheets.py. Data must pass atelier.validate first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pypdf import PdfWriter

from atelier.model import load
from atelier.draw import envelope_bounds
from atelier.registry import SHEET_DEFS, SHEETS
from atelier.sheets import fit_scale
from atelier.validate import check


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.build")
    ap.add_argument("project", type=Path)
    ap.add_argument("--sheet", action="append", help="sheet name(s) to build")
    ap.add_argument("--design", help="design file (default design.json)")
    ap.add_argument("--norender", action="store_true")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args(argv)

    m = load(a.project, a.design)
    rep = check(m)
    if rep.errors:
        for c, msg in rep.errors:
            print(f"  {c:18} {msg}")
        print(f"validate: {len(rep.errors)} errors; fix the data before building")
        return 1
    names = json.loads((a.project / "project.json").read_text())["sheets"]
    if not (a.project / "services.json").exists() and any(n in ("power", "lighting", "switching", "plumbing", "ac")
                                                            for n in names):
        print(f"services.json missing: run  python -m atelier.services {a.project}")
        return 1
    sc = fit_scale(envelope_bounds(m.walls))
    def info(n):
        if n.startswith("elevation:"):
            return (f"Elevation {n.split(':', 1)[1]}", "1:25")
        if n.startswith("room:"):
            from atelier.room_board import layout
            from atelier.views3d import key_walls
            r = m.room(n.split(":", 1)[1])
            return (f"Room board · {r.get('name', r['id'])}", f"1:{layout(m, r, key_walls(m, r))['scale']} / 1:50")
        if n.startswith("joinery:"):
            from atelier.boards import Item, choose_layout, jn_number
            jid = n.split(":", 1)[1]
            sc_ = choose_layout(Item(m, next(j for j in m.joinery if j["id"] == jid)))[0]
            return (f"Joinery board {jn_number(m, jid)} · {jid}", f"1:{sc_}")
        return (SHEET_DEFS[n][1], f"1:{sc}" if SHEET_DEFS[n][2] else "—")
    m.album = [(i, n, *info(n)) for i, n in enumerate(names, 1)]
    if any(n.startswith("room:") for n in names) and not a.norender:
        from atelier.render import render
        render(a.project)                        # cached: only cameras whose data changed are rendered
    out = a.project / "out" / "sheets"
    built = []
    for i, name in enumerate(names, 1):
        if a.sheet and name not in a.sheet:
            continue
        if name.startswith("elevation:"):
            from atelier.elev_detail import elevation_sheet
            sh = elevation_sheet(m, i, len(names), name.split(":", 1)[1])
        elif name.startswith("room:"):
            from atelier.room_board import board as room_board
            sh = room_board(m, i, len(names), name.split(":", 1)[1])
        elif name.startswith("joinery:"):
            from atelier.boards import board
            sh = board(m, i, len(names), name.split(":", 1)[1])
        else:
            sh = SHEETS[name](m, i, len(names))
        safe = name.replace(":", "-")
        pdf, png = out / f"{i:02d}-{safe}.pdf", out / f"{i:02d}-{safe}.png"
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
    return 0


if __name__ == "__main__":
    sys.exit(main())

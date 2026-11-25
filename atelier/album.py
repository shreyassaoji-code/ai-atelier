"""The album: every sheet in STANDARDS §2 order, numbered "NN / total".

    out/album.pdf      every page, vector, A3 landscape
    out/pages/NN.png   one raster preview per page (NN = page number)
    out/album.json     what is in album.pdf (page names, in order) - used to splice partial builds

A sheet name is a registry key ("measured") or a family with one page per data item:
"room:<room id>", "elevation:<view id>", "joinery:<joinery id>". projects/<name>/project.json
may hold {"exclude": [names]}; nothing else about the order is project-specific.

Safety: album.pdf is replaced only by a COMPLETE build in which every page was made, and
only after the merged file is checked (page count = album length, every page A3). A
partial build (--sheet) splices its pages into the existing album when that album was made
from the same page list; otherwise it leaves album.pdf alone. Writes go to a temporary file
first and replace album.pdf in one step.
"""
from __future__ import annotations

import json
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from atelier import theme as T
from atelier.registry import SHEET_DEFS, SHEETS

# STANDARDS §2: the album order. "family:*" expands to one page per item, in data order.
ORDER = ["cover", "contents", "measured", "dismantling", "partitions", "presentation", "furniture", "room:*",
         "flooring", "wall_finishes", "ceiling", "sections", "power", "lighting", "switching", "plumbing", "ac",
         "elevation:*", "dt01", "dt02", "joinery:*"]
MM_PT = 72 / 25.4
A3 = (T.PAGE_W * MM_PT, T.PAGE_H * MM_PT)


def _family(m, fam):
    if fam == "room":
        from atelier.views3d import board_rooms
        return [r["id"] for r in board_rooms(m)]
    if fam == "elevation":
        return [v["id"] for v in m.views if v.get("kind") == "elevation"]
    if fam == "joinery":
        return [j["id"] for j in m.joinery]
    raise KeyError(fam)


def page_names(m, root: Path):
    """The album's page names, in STANDARDS order, minus project.json "exclude"."""
    pj = root / "project.json"
    cfg = json.loads(pj.read_text()) if pj.exists() else {}
    excl = set(cfg.get("exclude", []))
    out = []
    for key in ORDER:
        if key.endswith(":*"):
            fam = key[:-2]
            out += [f"{fam}:{i}" for i in _family(m, fam)]
        else:
            out.append(key)
    return [n for n in out if n not in excl and n.split(":")[0] + ":*" not in excl]


def info(m, n):
    """(title, scale text) for the contents sheet."""
    if n.startswith("elevation:"):
        return (f"Elevation {n.split(':', 1)[1]}", "1:25")
    if n.startswith("joinery:"):
        from atelier.boards import Item, choose_layout, jn_number
        jid = n.split(":", 1)[1]
        sc = choose_layout(Item(m, next(j for j in m.joinery if j["id"] == jid)))[0]
        return (f"Joinery board {jn_number(m, jid)} · {jid}", f"1:{sc}")
    if n.startswith("room:"):
        from atelier.room_board import layout
        from atelier.views3d import key_walls
        r = m.room(n.split(":", 1)[1])
        return (f"Room board · {r.get('name', r['id'])}", f"1:{layout(m, r, key_walls(m, r))['scale']} / 1:50")
    from atelier.draw import envelope_bounds
    from atelier.sheets import fit_scale
    return (SHEET_DEFS[n][1], f"1:{fit_scale(envelope_bounds(m.walls))}" if SHEET_DEFS[n][2] else "—")


def make(m, no, total, name):
    if name.startswith("elevation:"):
        from atelier.elev_detail import elevation_sheet
        return elevation_sheet(m, no, total, name.split(":", 1)[1])
    if name.startswith("joinery:"):
        from atelier.boards import board
        return board(m, no, total, name.split(":", 1)[1])
    if name.startswith("room:"):
        from atelier.room_board import board
        return board(m, no, total, name.split(":", 1)[1])
    return SHEETS[name](m, no, total)


def check_pdf(path: Path, total: int):
    """Raise unless the PDF has `total` pages, all A3 landscape."""
    r = PdfReader(str(path))
    if len(r.pages) != total:
        raise ValueError(f"{path.name}: {len(r.pages)} pages, expected {total}")
    for i, p in enumerate(r.pages, 1):
        w, h = float(p.mediabox.width), float(p.mediabox.height)
        if abs(w - A3[0]) > 1 or abs(h - A3[1]) > 1:
            raise ValueError(f"{path.name} page {i}: {w:.1f} × {h:.1f} pt, not A3 landscape")


def _replace(tmp: Path, dst: Path):
    os.replace(tmp, dst)                     # one step: readers never see a half-written album


def build(m, root: Path, only=None, dpi=200, log=print):
    """Make the pages, then write (complete build) or splice (partial build) the album.
    Returns (pages made, pages failed, what happened to album.pdf)."""
    out = root / "out"
    stage, pages = out / ".stage", out / "pages"
    stage.mkdir(parents=True, exist_ok=True)
    pages.mkdir(parents=True, exist_ok=True)
    names = page_names(m, root)
    total = len(names)
    m.album = [(i, n, *info(m, n)) for i, n in enumerate(names, 1)]
    unknown = [n for n in (only or []) if n not in names]
    if unknown:
        raise ValueError(f"not in this album: {', '.join(unknown)} (pages: {', '.join(names)})")
    made, failed = [], []
    for i, name in enumerate(names, 1):
        if only and name not in only:
            continue
        try:
            sh = make(m, i, total, name)
            sh.save(stage / f"{i:02d}.pdf", pages / f"{i:02d}.png", dpi)
            made.append(i)
            log(f"  {i:02d} / {total:02d}  {name} ✓")
        except Exception as e:  # noqa: BLE001 - one bad sheet must not stop the others, nor reach album.pdf
            failed.append((i, name, e))
            log(f"  {i:02d} / {total:02d}  {name} FAILED: {e}")
            log("    " + traceback.format_exc().strip().splitlines()[-2].strip())
    album, man = out / "album.pdf", out / "album.json"
    tmp = out / "album.pdf.tmp"
    if failed:
        return made, failed, f"album.pdf left as it was ({len(failed)} page(s) failed)"
    if not only:                                                   # complete build
        w = PdfWriter()
        for i in range(1, total + 1):
            w.append(str(stage / f"{i:02d}.pdf"))
        w.write(str(tmp))
        check_pdf(tmp, total)
        _replace(tmp, album)
        man.write_text(json.dumps({"pages": names, "total": total, "built": datetime.now().isoformat(timespec="seconds")},
                                  indent=1) + "\n")
        for p in pages.glob("*.png"):                              # previews of pages that no longer exist
            if p.stem.isdigit() and int(p.stem) > total:
                p.unlink()
        legacy = out / "sheets"
        if legacy.is_dir():
            shutil.rmtree(legacy)
        return made, failed, f"album.pdf written ({total} pages)"
    # partial build: splice only into an album made from the same page list
    old = json.loads(man.read_text()) if man.exists() else None
    if not (album.exists() and old and old.get("pages") == names):
        why = "no complete album yet" if not album.exists() else "the page list changed since the last complete build"
        return made, failed, f"album.pdf left as it was ({why}); run a complete build"
    rd = PdfReader(str(album))
    if len(rd.pages) != total:
        return made, failed, "album.pdf left as it was (its page count does not match album.json)"
    w = PdfWriter()
    for i in range(1, total + 1):
        if i in made:
            w.add_page(PdfReader(str(stage / f"{i:02d}.pdf")).pages[0])
        else:
            w.add_page(rd.pages[i - 1])
    w.write(str(tmp))
    check_pdf(tmp, total)
    _replace(tmp, album)
    return made, failed, f"album.pdf updated: page(s) {', '.join(f'{i:02d}' for i in made)} replaced, {total} pages"

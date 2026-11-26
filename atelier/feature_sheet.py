"""Feature wall sheets (STANDARDS §4): one per feature wall the reference interpreter wrote.

    project album page "feature:<FW id>"

  - the wall in elevation at 1:25 (1:50 if it is too long), cropped to the feature plus 300 each
    side, with every element called out, LED reveals and pendants;
  - the 3D view of the wall rendered from the data (atelier/render.py camera V-<FW id>) beside the
    client's reference image (`ref`, from the project or refs/), so the mood can be compared;
  - an element schedule (left to right: u from-to, width, z, depth, type, code, colour, extras);
  - swatches of the element codes, the interpreter's note.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from atelier import features as FT
from atelier import theme as T
from atelier import texture as TX
from atelier.draw import DASH, LW_HAIR, LW_THIN, Sheet, sans, tracked
from atelier.elev_detail import Face
from atelier.room_board import _elev_size, draw_elevation
from atelier.sheets import Frame

ROOT = Path(__file__).resolve().parent.parent


def ref_path(m, g):
    r = g.get("ref")
    if not r:
        return None
    for p in (m.root / r, m.root / "refs" / Path(r).name, ROOT / r, ROOT / "refs" / Path(r).name):
        if p.exists():
            return p
    return None


def _picture(sh, path, x, y, w, h, caption, missing):
    if path is not None:
        im = Image.open(path).convert("RGB")
        iw, ih = im.size
        k = min(w / iw, h / ih)
        dw, dh = iw * k, ih * k
        x0, y0 = x + (w - dw) / 2, y + (h - dh) / 2
        sh.image(np.asarray(im) / 255.0, x0, y0, x0 + dw, y0 + dh, z=4)
        sh.region([([(x0, y0), (x0 + dw, y0), (x0 + dw, y0 + dh), (x0, y0 + dh)], [])], edge=T.INK, lw=LW_THIN, z=5)
    else:
        sh.region([([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], [])], fill=T.PAPER, edge=T.GREY, lw=LW_HAIR,
                  dash=DASH, z=4)
        sh.text(x + w / 2, y + h / 2 - 1, tracked(missing[0]), sans("dim", 600), T.FLAG, ha="center", va="center",
                zorder=6)
        sh.text(x + w / 2, y + h / 2 + 2.5, missing[1], sans("dim"), T.GREY, ha="center", va="center", zorder=6)
    sh.caps(x, y + h + 4, caption, T.GREY, role="legend_head")


def sheet(m, no, total, fid):
    g = next(x for x in m.feature_walls if x["id"] == fid)
    room = m.room(g["room"])
    u0 = min(it["from"] for it in g["items"])
    u1 = max(it["to"] for it in g["items"])
    view = {"id": f"{fid}-E", "kind": "elevation", "room": g["room"], "wall": g["wall"],
            "range": [max(0, u0 - 300), min(g["L"], u1 + 300)]}
    if view["range"] == [0, g["L"]]:
        view.pop("range")
    x0, y0, x1, y1 = T.DRAW
    scale = 25
    F = Face(m, view)
    ew, eh = _elev_size(F, scale)
    if ew > 232:
        scale = 50
        ew, eh = _elev_size(F, scale)
    sh = Sheet()
    fr = Frame(sh, m, f"Feature wall · {fid}", f"{room.get('name', room['id'])} · wall {g['wall']} · elevation 1:{scale} "
               f"· 3D view · reference", no, total, scale)
    draw_elevation(sh, m, view, 1, x0, y0, scale)
    # pictures: 3D view from the data, client's reference
    px = x0 + ew + 8
    pw = x1 - px
    ph = min(pw, (y1 - y0 - 30) / 2)
    cam = next((c for c in __import__("atelier.render", fromlist=["all_cameras"]).all_cameras(m)
                if c.get("feature") == fid), None)
    from atelier.frames import frame_file, picture_for
    png, viz = picture_for(m.root, m, cam) if cam else (None, None)
    _picture(sh, png, px, y0 + 2, pw, ph, viz or f"3D view from the data · {frame_file(cam) if cam else fid}",
             ("render not produced", "run python -m atelier.render"))
    _picture(sh, ref_path(m, g), px, y0 + ph + 12, pw, ph, "Client reference" + (f" · {Path(g['ref']).name}"
                                                                              if g.get("ref") else ""),
             ("no reference image on file", "copy it to refs/ and set ref on the feature"))
    # schedule
    ty = y0 + eh + 8
    sh.caps(x0, ty, "Elements, left to right (u from the left corner, seen from inside)", T.INK, role="legend_head",
            weight=600)
    cols = [("#", 0), ("Type", 8), ("u from–to", 30), ("Width", 56), ("z", 72), ("Depth", 94), ("Code", 108),
            ("Colour", 124), ("Notes", 152)]
    ty += 6
    for h, dx in cols:
        sh.caps(x0 + dx, ty, h, T.GREY)
    fin = {f["code"]: f for f in m.finishes}
    for i, it in enumerate(g["items"], 1):
        ty += 4.4
        extras = [k for k in ("backlit", "rounded", "concealed") if it.get(k)]
        if (it.get("panels") or 1) > 1:
            extras.insert(0, f"{it['panels']} panels")
        if it.get("concealed"):
            extras.append("door hidden in the panel")
        vals = [f"{fid}.{i}", it.get("type"), f"{it['from']}–{it['to']}", str(it["to"] - it["from"]),
                f"{it['z0']}–{it['z1']}", str(it.get("depth")), it.get("code") or "—", it.get("color") or "—",
                ", ".join(extras)]
        for (h, dx), v in zip(cols, vals):
            sh.text(x0 + dx, ty, str(v), sans("legend", 600 if h == "#" else 400), T.INK)
    if g.get("led"):
        ty += 5
        sh.text(x0, ty, "LED reveals at u = " + ", ".join(str(int(ld["u"])) for ld in g["led"]), sans("legend"), T.INK)
    for k, pd in enumerate(g.get("pendants", []), 1):
        ty += 4.4
        sh.text(x0, ty, f"Pendant {k}: u {pd['u']}, {pd.get('out', 300)} out from the wall, bottom +{pd.get('z')}, "
                        f"Ø{pd.get('d', 200)}, drop {pd.get('length', '—')}", sans("legend"), T.INK)
    # strip: swatches + note
    fr.head("Materials")
    codes = []
    for it in g["items"]:
        if it.get("code") and it["code"] not in codes:
            codes.append(it["code"])
    r, pitch = 5.0, 23
    for i, code in enumerate(codes):
        cx, cy = T.STRIP_X + r + (i % 3) * pitch, fr.y + r + (i // 3) * 22
        it = next(x for x in g["items"] if x.get("code") == code)
        tone = TX.named_tone(it.get("color")) if it.get("color") else None
        tone = tone if tone is not None else TX.finish_tone(fin.get(code, {}))
        sh.circle(cx, cy, r, edge=T.INK, fill=TX.hexc(tone), lw=LW_THIN, z=5)
        sh.text(cx, cy + r + 2.6, code, sans("dim", 700), T.INK, ha="center")
        from atelier.sheets import _wrap_words
        for k_, ln in enumerate(_wrap_words((fin.get(code, {}).get("name") or "").split(",")[0], 16)[:2]):
            sh.text(cx, cy + r + 5.0 + k_ * 2.3, ln, sans("dim"), T.GREY, ha="center")
    fr.y += ((len(codes) + 2) // 3) * 22 + 2
    fr.rule()
    fr.head("Interpreter's note")
    fr.lines([("", g.get("note") or "—", None)], color=T.INK, max_chars=48)
    fr.y += 2
    fr.lines([("", "Rules: STANDARDS §4. No element covers a window; a door inside a panelled zone is concealed.",
               None)], color=T.GREY, max_chars=48)
    return sh

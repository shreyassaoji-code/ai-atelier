"""Client standard §2 sheets: axonometry, doors & windows, visualisations.

Each is drawn from the data and from frames already on disk; nothing here invents an image.
"""
from __future__ import annotations

from collections import OrderedDict

from atelier import geom
from atelier import theme as T
from atelier.draw import DASH, LW_HAIR, LW_LINE, LW_THIN, Sheet, sans
from atelier.feature_sheet import _picture
from atelier.sheets import Frame, _table


def _grid(n, x0, y0, x1, y1, gap=8, cap=8):
    cols = 1 if n == 1 else 2 if n <= 4 else 3
    rows = -(-n // cols)
    w = (x1 - x0 - gap * (cols - 1)) / cols
    h = (y1 - y0 - (gap + cap) * (rows - 1) - cap) / rows
    s = min(w, h)
    return [(x0 + (i % cols) * (w + gap) + (w - s) / 2, y0 + (i // cols) * (s + gap + cap), s) for i in range(n)]


# ------------------------------------------------------------------ axonometry
def axonometry(m, no, total):
    from atelier.frames import frame_path
    from atelier.render import is_current
    from atelier.render3d import W3, axo_camera
    from atelier.views3d import board_rooms
    sh = Sheet()
    fr = Frame(sh, m, "Axonometry", f"White model · walls and tall joinery cut at +{W3['cut']} · "
               f"orthographic from the SW", no, total, None)
    x0, y0, x1, y1 = T.DRAW
    rooms = board_rooms(m)
    made = 0
    for r, (x, y, s) in zip(rooms, _grid(len(rooms), x0, y0 + 4, x1, y1)):
        cam = axo_camera(m, r)
        p = frame_path(m.root, cam)
        ok = p.exists() and is_current(m.root, m, cam)
        made += ok
        _picture(sh, p if ok else None, x, y, s, s, f"{r.get('name', r['id'])} · {r['id']} · axonometric",
                 ("render not produced", "run python -m atelier.render3d"))
    fr.head("Notes")
    fr.lines([("1", f"One model of the whole apartment, built from the data (atelier.render3d); each view is "
                    f"framed on its room. Walls and joinery taller than +{W3['cut']} are cut and shown dark.", None),
              ("2", "Ceilings and hanging lights are left out so the rooms read from above.", None),
              ("3", f"{made} of {len(rooms)} views rendered from the current data.", None if made == len(rooms)
               else T.FLAG)], color=T.GREY)
    return sh


# ------------------------------------------------------------------ doors & windows
def _rooms_of(m, o):
    w = m.wall(o["wall"])
    g = geom.opening_polygon(w, o, extra=0).buffer(5)
    return [r["id"] for r in m.rooms if geom.room_polygon(r).intersects(g)]


def _operation(o):
    k = o["kind"]
    if k in ("door", "double_door"):
        leaves = "pair of leaves" if k == "double_door" else "single leaf"
        return f"hinged, {leaves}, hinge at wall {o.get('hinge', '?')}, opens {o.get('swing', '?')}"
    if k == "sliding_door":
        return "sliding"
    if k == "opening":
        return "open, no leaf"
    return {"window": "window", "ventilator": "ventilator, top-hung"}.get(k, k)


def _icon(sh, o, x, y, s, flagged=lambda o, k: False):
    """Opening seen from inside at scale s (mm per page mm): frame, leaf lines, sill and head."""
    w = o["width"] / s
    lo = (o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0) / s
    hi = o.get("head", 2100) / s
    base = y
    X0, X1, Y0, Y1 = x, x + w, base - hi, base - lo
    sh.line([(X0, base), (X1, base)], T.GREY, LW_HAIR, DASH)                     # FFL
    sh.region([([(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)], [])], edge=T.INK, lw=LW_LINE, z=4)
    k = o["kind"]
    if k in ("door", "double_door"):
        hx = X0 if o.get("hinge") == "start" else X1
        mx = (X0 + X1) / 2
        if k == "double_door":
            for a, b in ((X0, mx), (X1, mx)):
                sh.line([(b, Y0), (a, (Y0 + Y1) / 2), (b, Y1)], T.GREY, LW_THIN, DASH)
            sh.line([(mx, Y0), (mx, Y1)], T.INK, LW_THIN)
        else:
            ox = X1 if hx == X0 else X0
            sh.line([(ox, Y0), (hx, (Y0 + Y1) / 2), (ox, Y1)], T.GREY, LW_THIN, DASH)    # opening diagonals
    elif k == "sliding_door":
        mx = (X0 + X1) / 2
        sh.line([(mx, Y0), (mx, Y1)], T.INK, LW_THIN)
        cy = (Y0 + Y1) / 2
        sh.line([(mx - w * 0.3, cy), (mx - 1, cy)], T.GREY, LW_THIN)
        sh.line([(mx + 1, cy), (mx + w * 0.3, cy)], T.GREY, LW_THIN)
    elif k in ("window", "ventilator"):
        i = 0.6
        sh.region([([(X0 + i, Y0 + i), (X1 - i, Y0 + i), (X1 - i, Y1 - i), (X0 + i, Y1 - i)], [])],
                  edge=T.INK, lw=LW_HAIR, fill=T.LIGHT, z=4)
        if w > 12:
            sh.line([((X0 + X1) / 2, Y0 + i), ((X0 + X1) / 2, Y1 - i)], T.INK, LW_THIN)
        sh.line([(X0 - 0.8, Y1 + 0.5), (X1 + 0.8, Y1 + 0.5)], T.INK, LW_LINE)                       # sill
    sh.text((X0 + X1) / 2, base + 3.2, f"{o['width']}", sans("dim"), T.INK, ha="center")
    fh = flagged(o, "head") or flagged(o, "sill")
    hgt = o.get("head", 2100) - (o.get("sill", 0) if k in ("window", "ventilator") else 0)
    sh.text(X1 + 1, (Y0 + Y1) / 2, f"{hgt}" + ("*" if fh else ""), sans("dim"), T.FLAG if fh else T.INK, va="center")
    if k in ("window", "ventilator") and o.get("sill"):
        fs = flagged(o, "sill")
        sh.line([(X1 + 0.6, Y1 + 0.5), (X1 + 0.6, base)], T.GREY, LW_HAIR)
        sh.text(X1 + 1.2, (Y1 + base) / 2, f"sill {o['sill']}" + ("*" if fs else ""), sans("dim"),
                T.FLAG if fs else T.GREY, va="center")
    return w


def doors_windows(m, no, total):
    sh = Sheet()
    fr = Frame(sh, m, "Doors and windows", "Schedule and types · types at 1:50, seen from inside", no, total, None)
    x0, y0, x1, y1 = T.DRAW
    order = {"door": 0, "double_door": 0, "sliding_door": 1, "opening": 2, "window": 3, "ventilator": 4}
    ops = sorted(m.openings, key=lambda o: (order.get(o["kind"], 9), o["id"]))
    rows = []
    for o in ops:
        def v(k, val=None):
            val = o.get(k) if val is None else val
            return (str(val), "flag" if m.is_flagged(o, k) else "")
        hgt = o.get("head", 2100) - (o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0)
        rows.append([(o["id"], "id"), o["kind"].replace("_", " "), " / ".join(_rooms_of(m, o)), o["wall"],
                     str(o["width"]), (str(hgt), "flag" if m.is_flagged(o, "head") or m.is_flagged(o, "sill") else ""),
                     v("sill", o.get("sill", 0)) if o["kind"] in ("window", "ventilator") else "—",
                     v("head", o.get("head", 2100)), _operation(o), "new" if o.get("_new") else "existing"])
    sh.caps(x0, y0 + 6, "Schedule", T.INK, role="legend_head", weight=600)
    ty = _table(sh, x0, y0 + 14, [(12, "left"), (24, "left"), (24, "left"), (12, "left"), (14, "right"),
                                    (16, "right"), (14, "right"), (14, "right"), (6, "left"), (100, "left"),
                                    (22, "left")],
                ["ID", "Type", "Rooms", "Wall", "Width", "Height", "Sill", "Head", "", "Operation", "Status"],
                [r[:8] + [""] + r[8:] for r in rows], row_h=min(4.6, (y1 - y0 - 110) / max(len(rows), 1)))
    # types: one icon per distinct (kind, width, height, sill)
    types = OrderedDict()
    for o in ops:
        key = (o["kind"], o["width"], o.get("head", 2100), o.get("sill", 0), o.get("hinge"))
        types.setdefault(key, []).append(o["id"])
    sh.caps(x0, ty + 8, "Types · 1:50 · width × height in mm", T.INK, role="legend_head", weight=600)
    x, base, s = x0 + 2, ty + 8 + 12 + 2400 / 50, 50
    for key, ids in types.items():
        o = next(op for op in ops if op["id"] == ids[0])
        if x + o["width"] / s + 14 > x1:
            x, base = x0 + 2, base + 2400 / s + 16
            if base > y1:
                break
        w = _icon(sh, o, x, base, s, m.is_flagged)
        sh.text(x + w / 2, base - o.get("head", 2100) / s - 2, ", ".join(ids), sans("dim", 600), T.ACCENT,
                ha="center")
        x += max(w, 14) + 12
    fr.head("Notes")
    fr.lines([("1", "Width = clear structural opening; height from FFL (doors) or from the sill (windows).", None),
              ("2", "Hinge 'start' / 'end' = the end of the wall line it sits on (survey.json); doors are "
                    "drawn as seen from the room on the wall's left.", None),
              ("3", "Leaves, frames, hardware and glazing to the door / window schedule of the contractor.", None),
              ("*", "Not read from the plan: verify on site before ordering.", T.FLAG)], color=T.GREY)
    return sh


# ------------------------------------------------------------------ visualisations
def visualisations(m, no, total):
    from atelier.frames import frame_file, frame_path, viz_status
    from atelier.render import is_current
    from atelier.render3d import cameras
    sh = Sheet()
    cams = [c for c in cameras(m, True) if c.get("feature")]
    for c in cameras(m):
        if c.get("kind") != "axo" and not any(x["room"] == c["room"] for x in cams):
            cams.append(c)
    cams = cams[:6]
    vz = [viz_status(m.root, m, c) for c in cams]
    n_viz = sum(1 for _, _, st in vz if st == "ok")
    fr = Frame(sh, m, "Visualisations", ("Photoreal visualisations from the image service" if n_viz else
                                         "No photoreal visualisation produced yet · white-model frames shown"),
               no, total, None)
    x0, y0, x1, y1 = T.DRAW
    for c, (vp, ve, st), (x, y, s) in zip(cams, vz, _grid(len(cams), x0, y0 + 4, x1, y1)):
        room = m.room(c["room"]).get("name", c["room"])
        what = f"{c['feature']} feature wall" if c.get("feature") else "corner view"
        if st == "ok":
            _picture(sh, vp, x, y, s, s, f"{room} · {what} · AI visualisation of {frame_file(c)}", ("", ""))
        else:
            p = frame_path(m.root, c)
            ok = p.exists() and is_current(m.root, m, c)
            _picture(sh, p if ok else None, x, y, s, s, f"{room} · {what} · white model, not photoreal",
                     ("render not produced", "run python -m atelier.render3d"))
    fr.head("Notes")
    fr.lines([("1", "Photoreal images come only from the image service (Magnific), with these Blender frames as "
                    "the reference (agents/visualiser.md); layouts are never invented.", None),
              ("2", f"{n_viz} of {len(cams)} views have a current visualisation." +
               ("" if n_viz else " None has been produced; the album keeps the white-model views."),
               None if n_viz == len(cams) else T.FLAG)], color=T.GREY)
    return sh


SHEET_DEFS = OrderedDict(
    axonometry=(axonometry, "Axonometry", False),
    doors_windows=(doors_windows, "Doors and windows", False),
    visualisations=(visualisations, "Visualisations", False),
)

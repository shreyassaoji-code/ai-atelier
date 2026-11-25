"""Measured plan sheet: cut walls, openings, room IDs, chained dimensions.

Colours, fonts and sizes come only from atelier.theme (via draw.py helpers).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from shapely.geometry import box
from shapely.ops import unary_union

from atelier import theme as T
from atelier.draw import LW_LINE, LW_THIN, Sheet, sans, serif

TITLE = "Measured plan"
SCALES = (20, 25, 50, 75, 100, 200)
DIM_MARGIN = 26  # mm of page reserved round the plan for dimension chains


def _fit_scale(w_mm, h_mm):
    x0, y0, x1, y1 = T.DRAW
    aw, ah = x1 - x0 - 2 * DIM_MARGIN, y1 - y0 - 2 * DIM_MARGIN
    for s in SCALES:
        if w_mm / s <= aw and h_mm / s <= ah:
            return s
    return SCALES[-1]


def _rings(geom):
    polys = getattr(geom, "geoms", [geom])
    for p in polys:
        yield list(p.exterior.coords), [list(i.coords) for i in p.interiors]


def build(project_dir: Path, sheet_no: int = 1, sheet_total: int = 1) -> Sheet:
    project = json.loads((project_dir / "project.json").read_text())
    plan = json.loads((project_dir / "plan.json").read_text())

    fx0, fy0, fx1, fy1 = plan["footprint"]
    scale = _fit_scale(fx1 - fx0, fy1 - fy0)
    x0, y0, x1, y1 = T.DRAW
    ox = (x0 + x1) / 2 - (fx0 + fx1) / 2 / scale
    oy = (y0 + y1) / 2 + (fy0 + fy1) / 2 / scale

    def P(x, y):  # plan mm (y up) -> page mm (y down)
        return (ox + x / scale, oy - y / scale)

    sh = Sheet()
    sh.frame(TITLE, project["name"], sheet_no, sheet_total,
             subtitle=f"Existing condition · scale 1:{scale} · A3")

    # ---- cut walls: footprint minus rooms minus openings --------------------
    rooms = unary_union([box(*r["rect"]) for r in plan["rooms"]])
    cuts = unary_union([box(*o["cut"]) for o in plan["doors"] + plan["windows"]])
    walls = box(*plan["footprint"]).difference(rooms).difference(cuts)
    walls = walls.buffer(0)
    sh.region([([P(*c) for c in ext], [[P(*c) for c in h] for h in holes])
               for ext, holes in _rings(walls)], T.POCHE)

    # ---- windows: jambs + two glass lines -----------------------------------
    for w in plan["windows"]:
        a, b, c, d = w["cut"]
        horizontal = (c - a) > (d - b)
        if horizontal:
            for f in (0.38, 0.62):
                yy = b + (d - b) * f
                sh.line([P(a, yy), P(c, yy)], T.INK, LW_THIN)
            sh.line([P(a, b), P(c, b)], T.MID, LW_THIN)
            sh.line([P(a, d), P(c, d)], T.MID, LW_THIN)
        else:
            for f in (0.38, 0.62):
                xx = a + (c - a) * f
                sh.line([P(xx, b), P(xx, d)], T.INK, LW_THIN)
            sh.line([P(a, b), P(a, d)], T.MID, LW_THIN)
            sh.line([P(c, b), P(c, d)], T.MID, LW_THIN)

    # ---- doors: leaf open at 90 degrees + swing arc ---------------------------
    for dr in plan["doors"]:
        hx, hy = dr["hinge"]
        cx, cy = dr["close"]
        sx, sy = dr["swing"]
        r = math.hypot(cx - hx, cy - hy)
        lx, ly = hx + sx * r, hy + sy * r
        sh.line([P(hx, hy), P(lx, ly)], T.INK, LW_LINE)
        a0 = math.atan2(cy - hy, cx - hx)
        a1 = math.atan2(ly - hy, lx - hx)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        arc = [P(hx + r * math.cos(a0 + da * i / 40), hy + r * math.sin(a0 + da * i / 40))
               for i in range(41)]
        sh.line(arc, T.GREY, LW_THIN)

    # ---- room labels ----------------------------------------------------------
    for rm in plan["rooms"]:
        a, b, c, d = rm["rect"]
        px, py = P((a + c) / 2, (b + d) / 2)
        area = (c - a) * (d - b) / 1e6
        sh.text(px, py - 3.0, rm["id"], serif("project", 600), T.ACCENT, ha="center")
        sh.caps(px, py + 2.0, rm["name"], T.INK, ha="center")
        sh.text(px, py + 5.6, f"{area:.1f} m²", sans("dim"), T.GREY, ha="center")

    # ---- dimension chains -------------------------------------------------
    D = plan["dims"]
    top_y, left_x, right_x = fy1, fx0, fx1
    for d in D.get("top", []):
        sh.dim(P(d["to"], top_y), P(d["from"], top_y), -8, d["to"] - d["from"], d.get("flag", False))
    if "overall_top" in D:
        d = D["overall_top"]
        sh.dim(P(d["to"], top_y), P(d["from"], top_y), -16, d["to"] - d["from"], d.get("flag", False))
    for d in D.get("left", []):
        sh.dim(P(left_x, d["to"]), P(left_x, d["from"]), -8, d["to"] - d["from"], d.get("flag", False))
    for d in D.get("right", []):
        sh.dim(P(right_x, d["from"]), P(right_x, d["to"]), -8, d["to"] - d["from"], d.get("flag", False))

    # ---- legend strip -------------------------------------------------------
    y = sh.legend(y0 + 22, [
        ("fill", "Cut wall", T.POCHE),
        ("line", "Door leaf and swing", T.INK),
        ("line", "Window frame", T.MID),
        ("text", "Room ID", ("L1", serif("project", 600), T.ACCENT)),
        ("text", "Verify on site", ("000*", sans("legend", 500), T.FLAG)),
    ])
    sh.rule(T.STRIP_X, T.RIGHT, y + 1)
    sh.caps(T.STRIP_X, y + 7, "Notes", T.INK, role="legend_head", weight=600)
    notes = ["All dimensions in mm, finished face", "to finished face.",
             "Values marked * to be verified", "on site before production.",
             f"Measured {project.get('measured', '')}."]
    for i, n in enumerate(notes):
        sh.text(T.STRIP_X, y + 13 + i * 4.2, n, sans("legend"), T.INK)
    sh.caps(T.STRIP_X, y1, f"Scale 1:{scale} at A3", T.GREY)
    return sh

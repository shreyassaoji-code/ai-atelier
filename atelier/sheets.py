"""A3 sheet frame and the plan sheets: measured, dismantling, partitions.

Every value drawn comes from the model (survey.json + design.json). Nothing
here is hard-coded per project.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from atelier import geom
from atelier import theme as T
from atelier.draw import (DASH, LW_HAIR, LW_LINE, LW_THIN, PlanView, Sheet, envelope_bounds, ray_hit,
                          sans, serif, side_points, text_width_mm)
from atelier.symbols import north_arrow, number_tag, scale_bar

DISCLAIMER = "Drafted with AI - not for construction until checked and signed"
SCALES = (20, 25, 50, 75, 100, 200)
DIM_MARGIN = 30          # page mm kept clear round the plan for dimension chains
LINE = 3.6               # strip line pitch (mm)


# =================================================================== frame
class Frame:
    """Draws the fixed sheet furniture and manages the legend strip cursor."""

    def __init__(self, sh: Sheet, m, title: str, subtitle: str, no: int, total: int, scale: int):
        self.sh, self.m, self.scale = sh, m, scale
        x0, y0, x1, y1 = T.DRAW
        # title band
        sh.text(x0, y0 - 12, title, serif("title", 500), T.ACCENT)
        sh.caps(x0, y0 - 5, subtitle, T.GREY)
        sh.rule(x0, T.RIGHT, y0 - 2)
        sep = (x1 + T.STRIP_X) / 2
        sh.line([(sep, y0), (sep, y1)], T.HAIR, LW_HAIR)
        # sheet number
        num = f"{no:02d}"
        sh.text(T.STRIP_X, y0 - 5, num, serif("sheet_no", 500), T.ACCENT)
        nx = T.STRIP_X + text_width_mm(num, T.SIZES["sheet_no"], 0.44) + 1.0
        sh.text(nx, y0 - 5, f"/ {total:02d}", sans("sheet_total"), T.GREY)
        # project fields
        p = m.project
        self.y = y0 + 8
        sh.text(T.STRIP_X, self.y, p.get("name") or "—", serif("project", 500), T.INK)
        self.y += 4.6
        sub = " · ".join(s for s in (p.get("address"), p.get("date")) if s) or "—"
        sh.text(T.STRIP_X, self.y, sub, sans("legend"), T.GREY)
        self.y += 4.2
        self.rule()
        for k, v in (("Drawing", title), ("Scale", f"1:{scale} at A3" if scale else "—"),
                     ("Issued", date.today().isoformat()), ("Data", " + ".join(m.sources))):
            self.field(k, v)
        self.y += 1.2
        self.rule()
        # bottom: checked / signed, north arrow, scale bar
        yb = y1
        for i, k in enumerate(("Checked", "Signed")):
            xx = T.STRIP_X + i * 36
            sh.caps(xx, yb - 24, k, T.GREY)
            sh.line([(xx, yb - 18.5), (xx + 31, yb - 18.5)], T.INK, LW_HAIR)
        if scale:
            north_arrow(sh, T.STRIP_X + 5.2, yb - 5.6)
            step = 1000 / scale
            metres = max(1, min(5, int((T.RIGHT - T.STRIP_X - 18) // step)))
            scale_bar(sh, T.STRIP_X + 16, yb - 7.0, scale, metres)
        # disclaimer band
        sh.rule(x0, T.RIGHT, y1 + 5)
        sh.text(x0, y1 + 11, DISCLAIMER, sans("legend", 600), T.FLAG)
        sh.text(T.RIGHT, y1 + 11, "All dimensions in mm", sans("legend"), T.GREY, ha="right")

    # ---- strip helpers
    def rule(self):
        self.sh.rule(T.STRIP_X, T.RIGHT, self.y)
        self.y += 5.2

    def field(self, k, v):
        self.sh.caps(T.STRIP_X, self.y, k, T.GREY)
        self.sh.text(T.STRIP_X + 17, self.y, v, sans("legend"), T.INK)
        self.y += LINE + 0.4

    def head(self, s, color=None):
        self.sh.caps(T.STRIP_X, self.y, s, color or T.INK, role="legend_head", weight=600)
        self.y += 4.6

    def legend(self, items):
        """items: (label, draw_fn(x, y_top, w, h)) — the fn draws a 7×2.6 mm sample."""
        self.head("Legend")
        for label, fn in items:
            fn(T.STRIP_X, self.y - 2.3, 7.0, 2.6)
            self.sh.text(T.STRIP_X + 10, self.y, label, sans("legend"), T.INK)
            self.y += LINE + 0.6
        self.y += 1.0
        self.rule()

    def lines(self, rows, color=None, max_chars=58, limit_y=None, indent=7):
        """Wrapped text rows: (prefix, text, prefix_color)."""
        limit_y = limit_y or T.DRAW[3] - 30
        for prefix, txt, pc in rows:
            words, cur, first = txt.split(), "", True
            chunks = []
            for wd in words:
                if len(cur) + len(wd) + 1 > max_chars:
                    chunks.append(cur)
                    cur = wd
                else:
                    cur = f"{cur} {wd}".strip()
            chunks.append(cur)
            for c in chunks:
                if self.y > limit_y:
                    self.sh.text(T.STRIP_X, self.y, "…", sans("legend"), T.GREY)
                    return
                if first and prefix:
                    self.sh.text(T.STRIP_X, self.y, prefix, sans("legend", 600), pc or T.INK)
                self.sh.text(T.STRIP_X + (indent if prefix else 0), self.y, c, sans("legend"), color or T.INK)
                self.y += LINE
                first = False

    def verify_list(self):
        """'Verify on site': every flagged value in the model, grouped."""
        self.head("Verify on site", T.FLAG)
        groups: OrderedDict = OrderedDict()
        notes = []
        for ref, fld, note in self.m.verify:
            if fld and ref in ("levels", "calibration"):
                groups.setdefault(ref, []).append(fld)
            elif fld:
                groups.setdefault(fld, []).append(ref)
            else:
                notes.append((ref, note))
        rows = [("*", f"{fld}: {' '.join(refs)}", T.FLAG) for fld, refs in groups.items()]
        rows += [("*", f"{ref}: {note}", T.FLAG) for ref, note in notes]
        self.lines(rows)


# legend sample painters ------------------------------------------------------
def lg_fill(sh, fill, edge=None, hatch=None, dash=None):
    return lambda x, y, w, h: sh.swatch(x, y, w, h, fill=fill, edge=edge, lw=LW_THIN, hatch=hatch, dash=dash)


def lg_line(sh, color, lw=LW_LINE, dash=None):
    return lambda x, y, w, h: sh.line([(x, y + h / 2), (x + w, y + h / 2)], color, lw, dash)


def lg_window(sh):
    def f(x, y, w, h):
        for yy, lw in ((y, LW_HAIR), (y + h / 2, LW_THIN), (y + h, LW_HAIR)):
            sh.line([(x, yy), (x + w, yy)], T.INK, lw)
    return f


def lg_text(sh, s, color, weight=500):
    return lambda x, y, w, h: sh.text(x, y + h - 0.2, s, sans("dim", weight), color)


# =================================================================== shared plan helpers
def fit_scale(bounds):
    x0, y0, x1, y1 = T.DRAW
    aw, ah = x1 - x0 - 2 * DIM_MARGIN, y1 - y0 - 2 * DIM_MARGIN
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    return next((s for s in SCALES if w / s <= aw and h / s <= ah), SCALES[-1])


def split_walls(walls):
    full = [w for w in walls if w.get("kind") != "parapet"]
    low = [w for w in walls if w.get("kind") == "parapet"]
    return full, low


def outward_tag_point(wall, op, gap):
    """Point outside an external wall (body on the left of a->b), `gap` mm beyond the outer face."""
    mid = op["offset"] + op["width"] / 2
    lo, _ = geom.wall_offsets(wall)
    return geom.point_on_wall(wall, mid, lo - gap)


def draw_tags(pv: PlanView, m, walls, openings):
    """Opening codes: windows outside with sill; doors on the side away from the swing."""
    by_id = {w["id"]: w for w in walls}
    for o in openings:
        w = by_id.get(o["wall"])
        if not w:
            continue
        mid = o["offset"] + o["width"] / 2
        if w.get("kind") in ("external", "parapet"):
            x, y = outward_tag_point(w, o, pv.s * 3.2)
            sub, sf = None, False
            if o["kind"] in ("window", "ventilator") and "sill" in o:
                sub, sf = f"sill {o['sill']}", m.is_flagged(o, "sill")
            pv.tag(x, y, o["id"], sub=sub, sub_flag=sf)
        elif o["kind"] not in ("opening",):
            side = "right" if o.get("swing") == "left" else "left"
            f = geom.face_offset(w, side)
            off = pv.s * 2.6 * (1 if side == "left" else -1)
            pv.tag(*geom.point_on_wall(w, mid, f + off), o["id"])


def swings(walls, openings):
    by_id = {w["id"]: w for w in walls}
    polys = [geom.swing_polygon(by_id[o["wall"]], o) for o in openings if o["wall"] in by_id]
    return unary_union([p for p in polys if p is not None])


def room_extras(m, r):
    out = []
    if r.get("ffl"):
        out.append((f"FFL {r['ffl']:+d}".replace("+", "+").replace("-", "−"), m.is_flagged(r, "ffl")))
    return out


def all_side_dims(pv, m, walls, openings, rooms, sides=("S", "E", "N", "W"), tiers=(0, 1, 2)):
    for s in sides:
        t = side_points(m, walls, openings, rooms, s)
        pv.side_chains(s, [t[i] for i in tiers])


# =================================================================== sheets
def measured(m, no, total):
    walls, openings, rooms = m.survey_walls, m.survey_openings, m.rooms_survey
    bounds = envelope_bounds(walls)
    scale = fit_scale(bounds)
    sh = Sheet()
    fr = Frame(sh, m, "Measured plan", f"Existing condition · scale 1:{scale}", no, total, scale)
    pv = PlanView(sh, bounds, scale)
    full, low = split_walls(walls)
    pv.fill(geom.cut_walls(full, [o for o in openings if any(w["id"] == o["wall"] for w in full)]),
            fill=T.POCHE, z=2)
    pv.fill(geom.cut_walls(low, [o for o in openings if any(w["id"] == o["wall"] for w in low)]),
            fill=T.LIGHT, edge=T.INK, lw=LW_THIN, z=2)
    by_id = {w["id"]: w for w in walls}
    for o in openings:
        pv.opening(by_id[o["wall"]], o)
    sw = swings(walls, openings)
    for r in rooms:
        pv.room_label(r, room_extras(m, r), avoid=sw)
    draw_tags(pv, m, walls, openings)
    all_side_dims(pv, m, walls, openings, rooms)
    fr.legend([
        ("Wall, cut", lg_fill(sh, T.POCHE)),
        ("Parapet, below cut", lg_fill(sh, T.LIGHT, T.INK)),
        ("Door leaf and swing", lg_line(sh, T.INK, LW_LINE)),
        ("Window: frame, glass, frame", lg_window(sh)),
        ("Opening, no shutter", lg_line(sh, T.GREY, LW_HAIR, (0, (0.6, 1.2)))),
        ("Room ID · clear area", lg_text(sh, "MBR", T.ACCENT, 600)),
        ("Not read from the plan", lg_text(sh, "2100*", T.FLAG)),
    ])
    fr.verify_list()
    return sh


def dismantling(m, no, total):
    walls, openings, rooms = m.survey_walls, m.survey_openings, m.rooms_survey
    bounds = envelope_bounds(walls)
    scale = fit_scale(bounds)
    sh = Sheet()
    fr = Frame(sh, m, "Dismantling plan", f"Existing to be removed · scale 1:{scale}", no, total, scale)
    pv = PlanView(sh, bounds, scale)
    full, low = split_walls(walls)
    gone_walls = unary_union([d["poly"] for d in m.demolished if d["kind"] == "wall"]) \
        if any(d["kind"] == "wall" for d in m.demolished) else None
    cut = geom.cut_walls(full, [o for o in openings if any(w["id"] == o["wall"] for w in full)])
    keep = cut.difference(gone_walls) if gone_walls is not None else cut
    pv.fill(keep, fill=T.POCHE, z=2)
    pv.fill(geom.cut_walls(low, [o for o in openings if any(w["id"] == o["wall"] for w in low)]),
            fill=T.LIGHT, edge=T.INK, lw=LW_THIN, z=2)
    if gone_walls is not None:
        pv.fill(gone_walls, fill=T.PAPER, edge=T.FLAG, lw=LW_LINE, hatch="////", dash=DASH, z=3)
    removed = {d["id"] for d in m.demolished if d["kind"] == "opening"}
    by_id = {w["id"]: w for w in walls}
    for o in openings:
        if o["id"] in removed:
            pv.opening(by_id[o["wall"]], o, color=T.FLAG, dash=DASH, arc_color=T.FLAG)
        else:
            pv.opening(by_id[o["wall"]], o)
    sw = swings(walls, openings)
    for r in rooms:
        pv.room_label(r, avoid=sw)
    # numbered items + extent dimensions
    items = []
    notes_by = {}
    for d in m.design_raw.get("demolish", []):
        notes_by[d.get("opening") or d.get("wall")] = d.get("note", "")
    numbered = [d for d in m.demolished if not d.get("host")]
    for i, d in enumerate(numbered, 1):
        w = by_id[d["wall"]]
        side = "right"
        f = geom.face_offset(w, side)
        along = geom.unit(w["a"], w["b"])
        L = geom.wall_length(w)
        o_mid = (d.get("from", 0) + d.get("to", 0)) / 2 if d["kind"] == "wall" else \
            d["opening"]["offset"] + d["opening"]["width"] / 2
        px, py = pv.P(*geom.point_on_wall(w, o_mid, f - pv.s * 4.5))
        number_tag(sh, px, py, i)
        with_it = [x["id"] for x in m.demolished if x.get("host") and x["wall"] == d["id"]]
        what = (f"Wall {d['id']}: remove {int(d['to'] - d['from'])} mm"
                + (f" incl. {', '.join(with_it)}" if with_it else "") if d["kind"] == "wall"
                else f"{d['opening']['kind'].replace('_', ' ').capitalize()} {d['id']}: remove leaf and frame")
        note = notes_by.get(d["id"], "")
        items.append((str(i), f"{what}. {note}".strip() if note else what, T.FLAG))
        if d["kind"] == "wall":
            origin = geom.point_on_wall(w, 0, f - pv.s * 9)
            pv.ray_chain(origin, (along[0], along[1]),
                         [(0, False), (d["from"], False), (d["to"], False), (L, False)],
                         normal=geom.left_normal(along[0], along[1]))
    all_side_dims(pv, m, walls, openings, rooms, tiers=(2,))
    fr.legend([
        ("Existing wall to remain", lg_fill(sh, T.POCHE)),
        ("Wall to be dismantled", lg_fill(sh, T.PAPER, T.FLAG, "////", DASH)),
        ("Door or frame to be removed", lg_line(sh, T.FLAG, LW_LINE, DASH)),
        ("Item reference", lambda x, y, w, h: number_tag(sh, x + 2, y + h / 2, 1)),
    ])
    fr.head("Items to dismantle")
    fr.lines(items)
    fr.y += 2
    fr.lines([("", f"Unverified survey values ({len(m.verify)}): see the measured plan.", None)], color=T.GREY)
    return sh


def partitions(m, no, total):
    walls, openings, rooms = m.walls, m.openings, m.rooms
    bounds = envelope_bounds(walls)
    scale = fit_scale(bounds)
    sh = Sheet()
    fr = Frame(sh, m, "Partition plan", f"New walls and openings · scale 1:{scale}", no, total, scale)
    pv = PlanView(sh, bounds, scale)
    old = [w for w in walls if not w.get("_new")]
    new = [w for w in walls if w.get("_new")]
    full, low = split_walls(old)
    ops_on = lambda ws: [o for o in openings if any(w["id"] == o["wall"] for w in ws)]  # noqa: E731
    pv.fill(geom.cut_walls(full, ops_on(full)), fill=T.MID, z=2)
    pv.fill(geom.cut_walls(low, ops_on(low)), fill=T.LIGHT, edge=T.GREY, lw=LW_THIN, z=2)
    if new:
        pv.fill(geom.cut_walls(new, ops_on(new)), fill=T.PAPER, edge=T.INK, lw=LW_LINE, hatch="//////", z=3)
    for inf in m.infills:
        pv.fill(inf["poly"], fill=T.PAPER, edge=T.INK, lw=LW_LINE, hatch="//////", z=3)
    by_id = {w["id"]: w for w in walls}
    for o in openings:
        pv.opening(by_id[o["wall"]], o, color=T.INK if o.get("_new") else T.GREY)
    sw = swings(walls, openings)
    for r in rooms:
        pv.room_label(r, avoid=sw)
    # dimensions locating every new wall and new opening
    rows = []
    placed = []                      # plan geometry of chains already drawn
    labels = [geom.label_point(r) for r in rooms]
    for o in [o for o in openings if o.get("_new")]:
        w = by_id[o["wall"]]
        ux, uy, L = geom.unit(w["a"], w["b"])
        side = o["swing"] if o.get("swing") in ("left", "right") else "left"
        sgn = 1 if side == "left" else -1
        f = geom.face_offset(w, side) + 20 * sgn
        others = unary_union([geom.wall_polygon(x) for x in walls if x["id"] != w["id"]])
        p0 = geom.point_on_wall(w, o["offset"], f)
        p1 = geom.point_on_wall(w, o["offset"] + o["width"], f)
        back = ray_hit(p0, (-ux, -uy), others)
        fwd = ray_hit(p1, (ux, uy), others)
        if back is not None and fwd is not None:
            nx, ny = geom.left_normal(ux, uy)
            line_off = f + sgn * pv.s * 6
            start = geom.point_on_wall(w, o["offset"] - back, line_off)
            pts = [(0, False), (back, False), (back + o["width"], False), (back + o["width"] + fwd, False)]
            pv.ray_chain(start, (ux, uy), pts, normal=(nx * sgn, ny * sgn))
            placed.append(LineString([start, geom.point_on_wall(w, o["offset"] + o["width"] + fwd, line_off)]))
        rows.append((o["id"], f"New {o['kind'].replace('_', ' ')} {o['width']} wide in wall {o['wall']}.", T.INK))
    for w in new:
        ux, uy, L = geom.unit(w["a"], w["b"])
        nx, ny = geom.left_normal(ux, uy)
        lo, hi = geom.wall_offsets(w)
        others = unary_union([geom.wall_polygon(o) for o in walls if o["id"] != w["id"]])

        def clearance(fr):           # distance from a candidate chain position to what is already there
            pt = Point(geom.point_on_wall(w, L * fr))
            obstacles = [pt.distance(p) for p in labels] + [pt.distance(g) for g in placed]
            obstacles.append(pt.distance(others))
            return min(obstacles)
        best = max((0.15, 0.3, 0.5, 0.7, 0.85), key=clearance)
        back = ray_hit(geom.point_on_wall(w, L * best, lo - 1), (-nx, -ny), others)
        fwd = ray_hit(geom.point_on_wall(w, L * best, hi + 1), (nx, ny), others)
        clear = 7 * pv.s                          # keep chains 7 page-mm clear of room labels
        halves = {}
        for name, d, sgn, base in (("back", back, -1, lo - 1), ("fwd", fwd, 1, hi + 1)):
            if d is None:
                continue
            seg = LineString([geom.point_on_wall(w, L * best, base),
                              geom.point_on_wall(w, L * best, base + sgn * d)])
            halves[name] = min(seg.distance(p) for p in labels) >= clear
        if not any(halves.values()) and halves:   # keep at least one side: the clearer one
            halves[max(halves, key=lambda k: back if k == "back" else fwd)] = True
        if halves.get("back") or halves.get("fwd"):
            t = hi - lo
            b0 = back + 1 if halves.get("back") else 0
            start = geom.point_on_wall(w, L * best, lo - b0)
            pts = [(0, False), (b0, False), (b0 + t, False)] if halves.get("back") else [(0, False), (t, False)]
            if halves.get("fwd"):
                pts.append((pts[-1][0] + fwd + 1, False))
            pv.ray_chain(start, (nx, ny), pts, normal=(ux, uy))
            placed.append(LineString([start, geom.point_on_wall(w, L * best, lo - b0 + pts[-1][0])]))
        rows.append((w["id"], f"{w.get('kind', '').capitalize()} {w['t']} mm, {int(L)} long. {w.get('note', '')}",
                     T.INK))
    for inf in m.infills:
        rows.append((inf["id"], f"Infill old opening in wall {inf['wall']} to match wall.", T.INK))
    all_side_dims(pv, m, walls, openings, rooms, tiers=(2,))
    fr.legend([
        ("Existing wall", lg_fill(sh, T.MID)),
        ("New partition or infill", lg_fill(sh, T.PAPER, T.INK, "//////")),
        ("New door or opening", lg_line(sh, T.INK, LW_LINE)),
        ("Existing door", lg_line(sh, T.GREY, LW_LINE)),
    ])
    fr.head("New construction")
    fr.lines(rows)
    fr.y += 2
    fr.lines([("", f"Unverified survey values ({len(m.verify)}): see the measured plan.", None)], color=T.GREY)
    return sh


# (see the second half of this file)


# =================================================================== presentation & schedules
import math  # noqa: E402

from atelier import texture as TX  # noqa: E402
from atelier.symbols import (draw_furniture, draw_joinery, draw_sanitary,  # noqa: E402
                             furniture_footprint_page, furniture_parts, _to_plan)

RASTER_DPI = 240


def base_plan(pv, m, wall_fill=None, opening_color=None, z=8, parapet_edge=None):
    """Final walls (cut for openings) + openings, drawn above everything on the floor."""
    walls, openings = m.walls, m.openings
    full, low = split_walls(walls)
    ops_on = lambda ws: [o for o in openings if any(w["id"] == o["wall"] for w in ws)]  # noqa: E731
    pv.fill(geom.cut_walls(full, ops_on(full)), fill=wall_fill or T.POCHE, z=z)
    pv.fill(geom.cut_walls(low, ops_on(low)), fill=T.LIGHT, edge=parapet_edge or T.INK, lw=LW_THIN, z=z)
    by_id = {w["id"]: w for w in walls}
    for o in openings:
        pv.opening(by_id[o["wall"]], o, color=opening_color)


def floor_voids(m):
    """Demolished wall stretches get the floor of the first room they touch."""
    out = {}
    for v in m.voids:
        for r in m.rooms:
            if v.buffer(2).intersects(geom.room_polygon(r)):
                out.setdefault(r["id"], []).append(v.buffer(1))
                break
    return out


def thresholds(pv, m):
    """Stone threshold in every door-type opening."""
    by_id = {w["id"]: w for w in m.walls}
    for o in m.openings:
        if o["kind"] in ("door", "double_door", "sliding_door", "opening") and o["wall"] in by_id:
            pv.fill(geom.opening_polygon(by_id[o["wall"]], o, extra=0), fill=TX.hexc(TX.palette()["worktop"]),
                    edge=TX.hexc(TX.mix(T.INK, T.PAPER, 0.55)), lw=LW_HAIR, z=7)


def _plan_setup(m, title, subtitle, no, total):
    bounds = envelope_bounds(m.walls)
    scale = fit_scale(bounds)
    sh = Sheet()
    fr = Frame(sh, m, title, subtitle.format(scale=scale), no, total, scale)
    return sh, fr, PlanView(sh, bounds, scale), scale


def _finish_maps(m):
    return {f["code"]: f for f in m.finishes}, {f["room"]: f for f in m.floors}


def _caps_label(pv, room, avoid, sub=None):
    name = room.get("name", room["id"])
    w = text_width_mm(name.upper(), T.SIZES["legend_head"], 0.78) + 4
    px, py = pv.label_spot(room, avoid, 0, width_mm=w)
    x, y = pv.P(px, py)
    pv.sh.caps(x, y, name, T.INK, role="legend_head", weight=600, ha="center", zorder=12,
               path_effects=pv.sh.halo(2.6))
    if sub:
        pv.sh.text(x, y + 3.2, sub, sans("dim"), T.GREY, ha="center", zorder=12, path_effects=pv.sh.halo(2.2))


def presentation(m, no, total):
    sh, fr, pv, scale = _plan_setup(m, "Presentation plan", "Furnished layout · scale 1:{scale}", no, total)
    fin, flo = _finish_maps(m)
    k = RASTER_DPI / 25.4 / scale
    voids_for = floor_voids(m)
    for i, r in enumerate(m.rooms, 1):
        fl = flo.get(r["id"])
        if not fl:
            continue
        poly = unary_union([geom.room_polygon(r)] + voids_for.get(r["id"], [])).buffer(30, join_style=2)
        b = poly.bounds
        arr = TX.floor_texture(fin[fl["finish"]], fl, b, k, seed=i)
        (x0, y1), (x1, y0) = pv.P(b[0], b[1]), pv.P(b[2], b[3])
        sh.image(arr, x0, y0, x1, y1, clip_rings=pv.rings(poly), z=1)
    # soft shadows from furniture, joinery and walls, clipped to the floors
    casters = [furniture_footprint_page(pv, f) for f in list(m.furniture) + list(m.sanitary) if f.get("kind") != "rug"]
    for j in m.joinery:
        g = geom.joinery_polygon(j, m.wall(j["wall"]), m.room(j["room"]))
        casters.append([pv.P(*c) for c in g.exterior.coords[:-1]])
    full, _ = split_walls(m.walls)
    casters += [(ext, [list(h) for h in holes]) for ext, holes in pv.rings(geom.cut_walls(full, m.openings))]
    floor_rings = pv.rings(unary_union([geom.room_polygon(r) for r in m.rooms]))
    sh.image(TX.soft_shadow(casters, T.PAGE_W, T.PAGE_H), 0, 0, T.PAGE_W, T.PAGE_H, clip_rings=floor_rings, z=2)
    for f in sorted(m.furniture, key=lambda f: f.get("kind") != "rug"):
        draw_furniture(pv, f, "present")
    for j in m.joinery:
        draw_joinery(pv, j, m.wall(j["wall"]), m.room(j["room"]), "present")
    for s_ in m.sanitary:
        draw_sanitary(pv, s_, "present")
    base_plan(pv, m)
    thresholds(pv, m)
    avoid = unary_union([_to_plan(f, furniture_parts(f)[0][0]) for f in list(m.furniture) + list(m.sanitary)
                         if f.get("kind") != "rug"]
                        + [geom.joinery_polygon(j, m.wall(j["wall"]), m.room(j["room"])) for j in m.joinery]
                        + [swings(m.walls, m.openings)])
    for r in m.rooms:
        _caps_label(pv, r, avoid, f"{geom.room_area_m2(r):.1f} m²")
    # legend: floor finishes as real swatches
    items = []
    for code in sorted({fl["finish"] for fl in m.floors}):
        f = fin[code]
        fl = next(x for x in m.floors if x["finish"] == code)

        def swatch(x, y, w, h, f=f, fl=fl):
            kk = 60 / (w * 1.0)                      # ~1.2 m of material in the swatch
            arr = TX.floor_texture(f, fl, (0, 0, w * 170, h * 170), kk * 0.0 + 0.4 / 1, seed=7)
            sh.image(arr, x, y, x + w, y + h, z=4)
            sh.swatch(x, y, w, h, edge=T.HAIR, lw=LW_HAIR)
        items.append((f"{code}  {f['name'].split(',')[0]}", swatch))
    fr.legend(items)
    fr.head("Notes")
    fr.lines([("", "Furniture, finishes and textures are indicative; see the flooring, wall finish and "
               "furniture sheets for codes and sizes.", None)], color=T.GREY)
    return sh


def cover(m, no, total):
    sh = Sheet()
    fr = Frame(sh, m, "Interior working drawings", f"Drawing album · {total} sheets", no, total, None)
    x0, y0, x1, y1 = T.DRAW
    p = m.project
    sh.text(x0, y0 + 30, p.get("name") or "—", serif("sheet_no", 500), T.INK)
    sh.caps(x0, y0 + 40, f"{len(m.rooms)} rooms · {sum(geom.room_area_m2(r) for r in m.rooms):.1f} m² carpet",
            T.GREY, role="legend_head")
    env = envelope_bounds(m.walls)
    carpet = sum(geom.room_area_m2(r) for r in m.rooms)
    built = (env[2] - env[0]) * (env[3] - env[1]) / 1e6
    rows = [("Address", p.get("address") or "—"), ("Date", p.get("date") or "—"),
            ("Rooms", str(len(m.rooms))), ("Carpet area", f"{carpet:.2f} m²"),
            ("Built-up area", f"{built:.2f} m² (outer faces)"), ("Sheets", str(total)),
            ("Data", " + ".join(m.sources))]
    y = y0 + 60
    for k_, v in rows:
        sh.caps(x0, y, k_, T.GREY)
        sh.text(x0 + 30, y, v, sans("legend"), T.INK)
        y += 6
    # key plan
    scale = 75
    cx = (x0 + 110 + x1) / 2
    pv = PlanView(sh, env, scale, centre=(cx, (y0 + y1) / 2))
    base_plan(pv, m, z=3)
    for r in m.rooms:
        px, py = pv.label_spot(r)
        x, yy = pv.P(px, py)
        sh.text(x, yy + 1.2, r["id"], sans("dim", 600), T.ACCENT, ha="center")
    north_arrow(sh, pv.P(env[2], env[3])[0] + 10, pv.P(env[2], env[3])[1] + 6)
    sh.caps(cx, pv.P(0, env[1])[1] + 10, f"Key plan · 1:{scale}", T.GREY, ha="center")
    fr.head("Album")
    fr.lines([("", "Drawn by the AI Atelier engine from survey and design data. Values marked * were not "
               "read from the plan and must be verified on site.", None)], color=T.INK)
    return sh


def _table(sh, x, y, cols, header, rows, row_h=4.6):
    """cols: [(width_mm, align)], rows: [[(text, style), ...]] style in {'', 'id', 'flag', 'strong', 'grey'}."""
    xs = [x]
    for w_, _ in cols:
        xs.append(xs[-1] + w_)
    for i, h in enumerate(header):
        al = cols[i][1]
        tx = xs[i] if al == "left" else xs[i + 1] - 1
        sh.caps(tx, y, h, T.GREY, ha=al)
    sh.rule(x, xs[-1], y + 1.6, T.INK, LW_HAIR)
    y += 1.6 + row_h
    for row in rows:
        for i, cell in enumerate(row):
            t, st = cell if isinstance(cell, tuple) else (cell, "")
            al = cols[i][1]
            tx = xs[i] if al == "left" else xs[i + 1] - 1
            color = {"id": T.ACCENT, "flag": T.FLAG, "grey": T.GREY}.get(st, T.INK)
            wgt = 600 if st in ("id", "strong", "flag") else 400
            sh.text(tx, y, t + ("*" if st == "flag" else ""), sans("legend", wgt), color, ha=al)
        sh.rule(x, xs[-1], y + 1.6, T.HAIR, LW_HAIR)
        y += row_h
    return y


def contents(m, no, total):
    sh = Sheet()
    fr = Frame(sh, m, "Contents and room schedule", "Sheet index · rooms, areas and finishes", no, total, None)
    x0, y0, x1, y1 = T.DRAW
    sh.caps(x0, y0 + 8, "Sheet index", T.INK, role="legend_head", weight=600)
    rows = [[(f"{i:02d}", "id"), title, sc] for i, _n, title, sc in m.album]
    _table(sh, x0, y0 + 18, [(12, "left"), (62, "left"), (20, "right")], ["No", "Title", "Scale"], rows)
    fin, flo = _finish_maps(m)
    tx = x0 + 112
    sh.caps(tx, y0 + 8, "Room schedule", T.INK, role="legend_head", weight=600)
    ceil = m.levels.get("ceiling")
    cflag = m.is_flagged(dict(m.levels), "ceiling")
    rows, tot = [], 0.0
    for r in m.rooms:
        a = geom.room_area_m2(r)
        tot += a
        walls_codes = [r.get("wall_finish")] + sorted({wf["finish"] for wf in m.wall_features if wf["room"] == r["id"]})
        ffl = r.get("ffl", 0)
        rows.append([(r["id"], "id"), r.get("name", ""), r.get("type", "").replace("_", " "),
                     f"{a:.2f}", (f"{ffl:+d}".replace("-", "−") if ffl else "±0", "flag" if m.is_flagged(r, "ffl") else ""),
                     flo.get(r["id"], {}).get("finish", "—"), ", ".join(c for c in walls_codes if c) or "—",
                     (str(ceil), "flag" if cflag else "")])
    rows.append([("", ""), ("Total carpet area", "strong"), "", (f"{tot:.2f}", "strong"), "", "", "", ""])
    _table(sh, tx, y0 + 18, [(12, "left"), (32, "left"), (28, "left"), (16, "right"), (14, "right"),
                              (16, "right"), (32, "right"), (16, "right")],
           ["ID", "Room", "Type", "m²", "FFL", "Floor", "Walls", "Ceiling"], rows)
    fr.head("Abbreviations")
    fr.lines([("FFL", "Finished floor level, mm from main floor", None), ("FL-n", "Floor finish", None),
              ("WFn", "Wall finish", None), ("Fn", "Loose furniture item", None),
              ("Jn", "Joinery item", None), ("*", "Not read from the plan: verify on site", T.FLAG)])
    return sh


# ---- flooring ------------------------------------------------------------------
def _rot_pt(x, y, deg, o=(0, 0)):
    a = math.radians(deg)
    x, y = x - o[0], y - o[1]
    return (o[0] + x * math.cos(a) - y * math.sin(a), o[1] + x * math.sin(a) + y * math.cos(a))


def floor_pattern_lines(room, fl, fin, poly=None):
    """Vector laying pattern for one room, clipped to it (plan mm polylines)."""
    from shapely.geometry import LineString as LS, Polygon as Poly
    from shapely.affinity import rotate
    poly = poly if poly is not None else geom.room_polygon(room)
    c = poly.centroid
    mod = fl.get("module") or [600, 600]
    pat = fl.get("pattern", "straight")
    kind = fin.get("kind")
    ang = fl.get("angle", 0)
    big = rotate(poly, -ang, origin=c)                 # work in the laying frame
    bx0, by0, bx1, by1 = big.bounds
    lines = []
    if kind in ("wood", "laminate", "veneer") and pat in ("herringbone", "chevron"):
        n = max(2, round(mod[1] / mod[0]))
        W = mod[0]
        hb = rotate(poly, -(45 + ang), origin=(0, 0))
        ux0, uy0, ux1, uy1 = [v / W for v in hb.bounds]
        planks = []
        for kk in range(int(uy0) - n - 2, int(uy1) + 2):
            for mm_ in range(int((ux0 - kk - n) // (2 * n)) - 1, int((ux1 - kk) // (2 * n)) + 2):
                bx = kk + 2 * n * mm_
                planks.append(Poly([(bx, kk), (bx + n, kk), (bx + n, kk + 1), (bx, kk + 1)]))
                planks.append(Poly([(bx, kk + 1), (bx + 1, kk + 1), (bx + 1, kk + 1 + n), (bx, kk + 1 + n)]))
        for pl in planks:
            g = rotate(Poly([(x * W, y * W) for x, y in pl.exterior.coords]), 45 + ang, origin=(0, 0))
            g = g.boundary.intersection(poly)
            for part in getattr(g, "geoms", [g]):
                if part.length > 0:
                    lines.append(list(part.coords))
        return lines
    if kind in ("wood", "laminate", "veneer"):
        pw, pl_ = mod[0], mod[1]
        y = by0 - (by0 % pw)
        row = 0
        while y <= by1:
            seg = rotate(LS([(bx0 - 10, y), (bx1 + 10, y)]), ang, origin=c).intersection(poly)
            for part in getattr(seg, "geoms", [seg]):
                if part.length > 0:
                    lines.append(list(part.coords))
            off = ((row * 0.37) % 1.0) * pl_
            x = bx0 - (bx0 % pl_) - off
            while x <= bx1:
                j = rotate(LS([(x, y), (x, y + pw)]), ang, origin=c).intersection(poly)
                for part in getattr(j, "geoms", [j]):
                    if part.length > 0:
                        lines.append(list(part.coords))
                x += pl_
            y += pw
            row += 1
        return lines
    # tiles and slabs: grid; 'centre' puts a joint cross on the room centre
    tx, ty = mod[0], mod[1]
    ox = c.x if fl.get("start") == "centre" else bx0
    oy = c.y if fl.get("start") == "centre" else by0
    x = ox - math.ceil((ox - bx0) / tx) * tx
    while x <= bx1:
        seg = rotate(LS([(x, by0 - 10), (x, by1 + 10)]), ang, origin=c).intersection(poly)
        for part in getattr(seg, "geoms", [seg]):
            if part.length > 0:
                lines.append(list(part.coords))
        x += tx
    y = oy - math.ceil((oy - by0) / ty) * ty
    while y <= by1:
        seg = rotate(LS([(bx0 - 10, y), (bx1 + 10, y)]), ang, origin=c).intersection(poly)
        for part in getattr(seg, "geoms", [seg]):
            if part.length > 0:
                lines.append(list(part.coords))
        y += ty
    return lines


def flooring(m, no, total):
    sh, fr, pv, scale = _plan_setup(m, "Flooring plan", "Floor finishes and laying · scale 1:{scale}", no, total)
    fin, flo = _finish_maps(m)
    voids_for = floor_voids(m)
    for r in m.rooms:
        fl = flo.get(r["id"])
        if not fl:
            continue
        fpoly = unary_union([geom.room_polygon(r)] + voids_for.get(r["id"], []))
        lines = floor_pattern_lines(r, fl, fin[fl["finish"]], fpoly)
        sh.lines([[pv.P(*p) for p in ln] for ln in lines], T.MID, LW_HAIR, z=1)
        # start / direction marks
        c = geom.room_polygon(r).centroid
        f = fin[fl["finish"]]
        if f.get("kind") in ("wood", "laminate", "veneer") and fl.get("pattern") not in ("herringbone", "chevron"):
            a = math.radians(fl.get("angle", 0))
            L = 450
            p0 = pv.P(c.x - math.cos(a) * L, c.y - math.sin(a) * L - 650)
            p1 = pv.P(c.x + math.cos(a) * L, c.y + math.sin(a) * L - 650)
            sh.ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="<|-|>", lw=LW_THIN, color=T.INK,
                                                               mutation_scale=5), zorder=9)
        elif fl.get("start") == "centre" and f.get("kind") not in ("wood", "laminate", "veneer"):
            x, y = pv.P(c.x, c.y - 650)
            sh.circle(x, y, 1.1, edge=T.INK, fill=T.PAPER, lw=LW_THIN)
            sh.line([(x - 1.8, y), (x + 1.8, y)], T.INK, LW_HAIR, z=9)
            sh.line([(x, y - 1.8), (x, y + 1.8)], T.INK, LW_HAIR, z=9)
    base_plan(pv, m, opening_color=T.GREY)
    sw = swings(m.walls, m.openings)
    for r in m.rooms:
        fl = flo.get(r["id"])
        extra = []
        if fl:
            mod = fl.get("module") or []
            full = f"{fl['finish']} · {fl.get('pattern')} {mod[0]}×{mod[1]}" if mod else fl["finish"]
            b = geom.room_polygon(r).bounds
            room_w_page = (b[2] - b[0]) / scale
            fits = text_width_mm(full, T.SIZES["dim"], 0.6) + 3 < room_w_page
            extra.append((full if fits else fl["finish"], False, True))
            if fl.get("skirting"):
                extra.append((f"skirting {fl['skirting']}", False))
        if r.get("ffl"):
            extra.append((f"FFL {r['ffl']:+d}".replace("-", "−"), m.is_flagged(r, "ffl")))
        pv.room_label(r, extra, avoid=sw)
    rows = []
    for code in sorted({fl["finish"] for fl in m.floors}):
        f = fin[code]
        rooms_ = " ".join(fl["room"] for fl in m.floors if fl["finish"] == code)
        rows.append((code, f"{f['name']}. Rooms: {rooms_}.", T.INK))
    fr.legend([
        ("Laying joints", lg_line(sh, T.MID, LW_HAIR)),
        ("Plank direction", lambda x, y, w, h: sh.ax.annotate(
            "", xy=(x + w, y + h / 2), xytext=(x, y + h / 2),
            arrowprops=dict(arrowstyle="<|-|>", lw=LW_THIN, color=T.INK, mutation_scale=5))),
        ("Tile joint centred on room", lambda x, y, w, h: (sh.circle(x + 3, y + h / 2, 1.1, edge=T.INK, fill=T.PAPER),
                                                           sh.line([(x + 1.2, y + h / 2), (x + 4.8, y + h / 2)], T.INK, LW_HAIR, z=9))),
        ("Unverified level", lg_text(sh, "FFL −20*", T.FLAG, 600)),
    ])
    fr.head("Floor finish schedule")
    fr.lines(rows)
    return sh


# ---- wall finishes ---------------------------------------------------------------
edge_pieces = geom.room_faces


def wf_colours(codes):
    cyc = [TX.mix(T.MID, T.PAPER, 0.15), TX.mix(T.BLUE, T.PAPER, 0.35), TX.mix(T.GREEN, T.PAPER, 0.25),
           TX.mix(T.AMBER, T.PAPER, 0.15), TX.mix(T.BLUE, T.INK, 0.25), TX.mix(T.GREEN, T.INK, 0.3),
           TX.mix(T.GREY, T.PAPER, 0.1)]
    return {c: TX.hexc(cyc[i % len(cyc)]) for i, c in enumerate(sorted(codes))}


def _tag_box(sh, x, y, text, sub=None, z=11):
    w = text_width_mm(text, T.SIZES["dim"], 0.62) + 2.4
    h = 3.2
    sh.region([([(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)], [])],
              fill=T.PAPER, edge=T.INK, lw=LW_HAIR, z=z)
    sh.text(x, y + 0.05, text, sans("dim", 600), T.INK, ha="center", va="center", zorder=z + 1)
    if sub:
        sh.text(x, y + h / 2 + 2.0, sub, sans("dim"), T.GREY, ha="center", va="center", zorder=z + 1,
                path_effects=sh.halo(2.0))


def wall_finishes(m, no, total):
    sh, fr, pv, scale = _plan_setup(m, "Wall finish plan", "Wall finishes by face · scale 1:{scale}", no, total)
    fin, _ = _finish_maps(m)
    codes = {r.get("wall_finish") for r in m.rooms if r.get("wall_finish")} | {w["finish"] for w in m.wall_features}
    col = wf_colours(codes)
    base_plan(pv, m, opening_color=T.GREY)
    band = 1.15 * scale            # plan mm: band centre 1.15 page-mm inside the face
    for r in m.rooms:
        default = r.get("wall_finish")
        feats = [wf for wf in m.wall_features if wf["room"] == r["id"]]
        for e in edge_pieces(r, m.walls):
            w = m.wall(e.wall)
            ux, uy = (e.b[0] - e.a[0]) / e.length, (e.b[1] - e.a[1]) / e.length
            nx, ny = -uy, ux                             # inward (CCW room)
            def t_of(p):
                return (p[0] - e.a[0]) * ux + (p[1] - e.a[1]) * uy
            cuts = []
            for o in m.openings_on(w["id"]):
                t0, t1 = sorted((t_of(geom.point_on_wall(w, o["offset"])),
                                 t_of(geom.point_on_wall(w, o["offset"] + o["width"]))))
                cuts.append((t0, t1))
            spans = [(0.0, e.length, default, None)]
            for wf in feats:
                if wf["wall"] != w["id"]:
                    continue
                t0, t1 = sorted((t_of(geom.point_on_wall(w, wf["offset"])),
                                 t_of(geom.point_on_wall(w, wf["offset"] + wf["width"]))))
                t0, t1 = max(t0, 0), min(t1, e.length)
                if t1 - t0 < 1:
                    continue
                new = []
                for a0, a1, code, src in spans:
                    if a1 <= t0 or a0 >= t1:
                        new.append((a0, a1, code, src))
                        continue
                    if a0 < t0:
                        new.append((a0, t0, code, src))
                    new.append((max(a0, t0), min(a1, t1), wf["finish"], wf))
                    if a1 > t1:
                        new.append((t1, a1, code, src))
                spans = new
            for a0, a1, code, src in spans:
                pieces = [(a0, a1)]
                for c0, c1 in cuts:
                    nxt = []
                    for p0, p1 in pieces:
                        if c1 <= p0 or c0 >= p1:
                            nxt.append((p0, p1))
                        else:
                            if p0 < c0:
                                nxt.append((p0, c0))
                            if c1 < p1:
                                nxt.append((c1, p1))
                    pieces = nxt
                for p0, p1 in pieces:
                    if p1 - p0 < 40 or not code:
                        continue
                    A = (e.a[0] + ux * p0 + nx * band, e.a[1] + uy * p0 + ny * band)
                    B = (e.a[0] + ux * p1 + nx * band, e.a[1] + uy * p1 + ny * band)
                    sh.line([pv.P(*A), pv.P(*B)], col[code], 3.2, z=6)
                if src is not None:
                    mid = (a0 + a1) / 2
                    tp = (e.a[0] + ux * mid + nx * band * 4.2, e.a[1] + uy * mid + ny * band * 4.2)
                    _tag_box(sh, *pv.P(*tp), code, f"z {src['z0']}–{src['z1']}")
    sw = swings(m.walls, m.openings)
    feats_zone = unary_union([Point(*geom.point_on_wall(m.wall(wf["wall"]), wf["offset"] + wf["width"] / 2)).buffer(9 * scale)
                              for wf in m.wall_features] + [sw])
    for r in m.rooms:
        pv.room_label(r, [(f"walls {r.get('wall_finish') or '—'}", False, True)], avoid=feats_zone)
    items = []
    for c in sorted(codes):
        items.append((f"{c}  {fin[c]['name']}", lambda x, y, w, h, c=c: sh.line(
            [(x, y + h / 2), (x + w, y + h / 2)], col[c], 3.2)))
    fr.legend(items)
    fr.head("Notes")
    fr.lines([("", "Band on each face shows its finish. Tagged faces are features, with height range "
               "z in mm above FFL; all other faces take the room's wall finish.", None)], color=T.GREY)
    return sh


# ---- furniture marking -----------------------------------------------------------
def furniture_plan(m, no, total):
    sh, fr, pv, scale = _plan_setup(m, "Furniture plan", "Loose furniture marking · scale 1:{scale}", no, total)
    base_plan(pv, m, wall_fill=T.POCHE, opening_color=T.GREY)
    for j in m.joinery:
        draw_joinery(pv, j, m.wall(j["wall"]), m.room(j["room"]), "line", label=True)
    for f in sorted(m.furniture, key=lambda f: f.get("kind") != "rug"):
        draw_furniture(pv, f, "line")
    for s_ in m.sanitary:
        draw_sanitary(pv, s_, "line")
    placed = []
    r_tag = 2.1
    for f in m.furniture:
        cands = [(0, 0), (0.3, 0.3), (-0.3, 0.3), (0.3, -0.3), (-0.3, -0.3), (0.38, 0), (-0.38, 0), (0, 0.38), (0, -0.38)]
        fx, fy = geom.compass_to_vec(f.get("facing", "N"))
        rx, ry = fy, -fx
        best = None
        for ca, cb in cands:
            x_ = f["at"][0] + ca * f["size"][0] * rx + cb * f["size"][1] * fx
            y_ = f["at"][1] + ca * f["size"][0] * ry + cb * f["size"][1] * fy
            px, py = pv.P(x_, y_)
            if all(math.hypot(px - a, py - b) > 2 * r_tag + 0.6 for a, b in placed):
                best = (px, py)
                break
        best = best or pv.P(*f["at"])
        placed.append(best)
        sh.circle(*best, r_tag, edge=T.INK, fill=T.PAPER, lw=LW_THIN)
        sh.ax.patches[-1].set_zorder(10)
        sh.text(best[0], best[1] + 0.05, f["id"], sans("dim", 600), T.INK, ha="center", va="center", zorder=11)
    occupied = unary_union([_to_plan(f, furniture_parts(f)[0][0]) for f in m.furniture]
                           + [geom.joinery_polygon(j, m.wall(j["wall"]), m.room(j["room"])) for j in m.joinery]
                           + [swings(m.walls, m.openings)])
    for r in m.rooms:
        _caps_label(pv, r, occupied)
    rows = [(f["id"], f"{f.get('label') or f['kind']} · {f['size'][0]}×{f['size'][1]}×{f['size'][2]} · {f['room']}", T.INK)
            for f in m.furniture]
    fr.legend([
        ("Loose furniture", lg_line(sh, T.INK, LW_THIN)),
        ("Joinery (see joinery sheets)", lg_fill(sh, T.PAPER, T.GREY)),
        ("Item reference", lambda x, y, w, h: (sh.circle(x + 2.2, y + h / 2, r_tag, edge=T.INK, fill=T.PAPER),
                                              sh.text(x + 2.2, y + h / 2 + 0.05, "F1", sans("dim", 600), T.INK,
                                                      ha="center", va="center"))),
    ])
    fr.head("Furniture schedule  (W × D × H mm)")
    fr.lines(rows)
    return sh


SHEET_DEFS = OrderedDict(
    cover=(cover, "Cover", False),
    contents=(contents, "Contents and room schedule", False),
    measured=(measured, "Measured plan", True),
    dismantling=(dismantling, "Dismantling plan", True),
    partitions=(partitions, "Partition plan", True),
    presentation=(presentation, "Presentation plan", True),
    flooring=(flooring, "Flooring plan", True),
    wall_finishes=(wall_finishes, "Wall finish plan", True),
    furniture=(furniture_plan, "Furniture plan", True),
)

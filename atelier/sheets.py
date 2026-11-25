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
        for k, v in (("Drawing", title), ("Scale", f"1:{scale} at A3"),
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

    def lines(self, rows, color=None, max_chars=58, limit_y=None):
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
                self.sh.text(T.STRIP_X + 7, self.y, c, sans("legend"), color or T.INK)
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


SHEETS = OrderedDict(measured=measured, dismantling=dismantling, partitions=partitions)

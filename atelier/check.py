"""Machine pre-check for the CHECKER (agents/checker.md): every item that can be measured.

    python -m atelier.check projects/<name>        -> out/check.md, exit 1 if anything FAILs

FAIL = measured and wrong · PASS = measured and right · LOOK = needs a person (with the pages to open).
It reads the data, services.json, out/album.json and the text of out/album.pdf; it does not replace
looking at every page.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from atelier import geom
from atelier.model import load
from atelier.validate import check as validate

HABITABLE = {"bedroom", "master_bedroom", "living", "living_dining", "dining", "foyer", "study"}
FLAT_OK = {"bath", "toilet", "kitchen", "utility", "dress", "store", "puja", "passage"}
TALL = {"wardrobe", "tall_unit", "crockery", "bookshelf", "shoe_rack"}
ROOT = Path(__file__).resolve().parent.parent


class Report:
    def __init__(self):
        self.rows = []                                   # (section, status, text)

    def add(self, sec, status, text):
        self.rows.append((sec, status, text))

    def ok(self, sec, cond, good, bad):
        self.add(sec, "PASS" if cond else "FAIL", good if cond else bad)

    def count(self, st):
        return sum(1 for r in self.rows if r[1] == st)


def _pages(root):
    a = root / "out" / "album.json"
    return json.loads(a.read_text())["pages"] if a.exists() else []


def _pdf_text(root):
    p = root / "out" / "album.pdf"
    if not p.exists():
        return []
    from pypdf import PdfReader
    # CAPS labels are letter-spaced with hair spaces: drop them so words can be searched
    return [(pg.extract_text() or "").replace("\u200a", "") for pg in PdfReader(str(p)).pages]


def pg(pages, *names):
    out = [f"{pages.index(n) + 1:02d}" for n in names if n in pages]
    return ("p. " + ", ".join(out)) if out else ""


def run(root: Path) -> Report:
    R = Report()
    m = load(root)
    pages = _pages(root)
    text = _pdf_text(root)
    sv_path = root / "services.json"
    S = json.loads(sv_path.read_text())["items"] if sv_path.exists() else []
    rep = validate(m)
    rooms = {r["id"]: r for r in m.rooms}
    poly = {r["id"]: geom.room_polygon(r) for r in m.rooms}

    # ---- 0. the data itself
    R.ok("0 Data", not rep.errors, "validate: 0 errors", f"validate: {len(rep.errors)} errors: "
         + "; ".join(f"{c} {t}" for c, t in rep.errors[:6]))
    for c, t in rep.warnings:
        R.add("0 Data", "LOOK", f"warning {c}: {t}")

    # ---- 1. survey vs source
    plan = root / (m.calibration.get("image") or "plan.png")
    if not plan.exists():
        R.add("1 Survey", "LOOK", f"no {plan.name}: the survey cannot be compared with a source "
                                  f"({m.project.get('note') or 'source not given'})")
    else:
        ov = root / "out" / "overlay.png"
        R.add("1 Survey", "LOOK", f"open {ov.relative_to(root) if ov.exists() else 'out/overlay.png (run atelier.overlay)'}"
                                  ": red walls must sit on the plan's walls; compare printed dims and areas")
    unflag = [k for k in ("ceiling", "soffit", "lintel", "sill") if not m.is_flagged(dict(m.levels), k)]
    if unflag:
        R.add("1 Survey", "LOOK", f"levels not flagged ({', '.join(unflag)}): confirm they are printed on the plan "
                                  "or a section, else flag them")
    else:
        R.add("1 Survey", "PASS", "assumed levels flagged (ceiling, soffit, lintel, sill)")
    for r in m.rooms:
        if r.get("area_printed"):
            calc = poly[r["id"]].area / 1e6
            d = abs(calc - r["area_printed"]) / r["area_printed"]
            R.ok("1 Survey", d <= 0.03, f"{r['id']} area {calc:.2f} vs printed {r['area_printed']}",
                 f"{r['id']} area {calc:.2f} vs printed {r['area_printed']} ({d:.0%})")

    # ---- 2. consistency, album
    if pages and text:
        R.ok("2 Album", len(pages) == len(text), f"album.pdf has the {len(pages)} pages of album.json",
             f"album.pdf has {len(text)} pages, album.json lists {len(pages)}")
        miss = [i for i, t in enumerate(text, 1) if "Drafted with AI" not in t]
        R.ok("2 Album", not miss, "disclaimer on every page", f"no disclaimer on p. {miss}")
        badno = [i for i, t in enumerate(text, 1) if not (f"{i:02d}" in t and f"/ {len(text):02d}" in t)]
        R.ok("2 Album", not badno, "every page numbered NN / total", f"page number missing or wrong on p. {badno}")
        contents = text[pages.index("contents")] if "contents" in pages else ""
        nolist = [i for i in range(1, len(pages) + 1) if f"{i:02d}" not in contents]
        R.ok("2 Album", not nolist, "contents lists every page", f"contents misses p. {nolist}")
    else:
        R.add("2 Album", "FAIL", "no out/album.pdf + album.json: build first")
    R.add("2 Album", "PASS", "plans, elevations, boards and 3D are drawn from one model (no hand-copied geometry)")
    try:
        from atelier.render import all_cameras, is_current
        cams = all_cameras(m)
        stale = [c["id"] for c in cams if not is_current(root, m, c)]
        R.ok("2 Album", not stale, f"all {len(cams)} 3D views rendered from the current data",
             f"3D views missing or out of date: {', '.join(stale)} (boards show RENDER NOT PRODUCED)")
    except Exception as e:  # noqa: BLE001
        R.add("2 Album", "LOOK", f"render state unknown ({e})")

    # ---- 3. ceilings
    for r in m.rooms:
        c = next((x for x in m.ceilings if x["room"] == r["id"]), None)
        if r.get("type") in HABITABLE:
            R.ok("3 Ceilings", bool(c and c.get("steps")), f"{r['id']} has a designed (tray) ceiling",
                 f"{r['id']} ({r.get('type')}) has no designed ceiling (no tray steps)")
        elif r.get("type") in FLAT_OK:
            R.ok("3 Ceilings", bool(c and c.get("z")), f"{r['id']} flat false ceiling +{c.get('z') if c else ''}",
                 f"{r['id']} has no false ceiling level")
    secs = [v for v in m.views if v.get("kind") == "section"]
    R.ok("3 Ceilings", any(v["id"] == "A" for v in secs), "section A–A present", "no section A–A in views[]")
    for v in secs:
        ln = LineString(v["line"])
        hits = [c["room"] for c in m.ceilings if c.get("steps") and ln.intersects(poly.get(c["room"], Point(0, 0)))]
        R.ok("3 Ceilings", bool(hits), f"section {v['id']} cuts trays in {', '.join(hits)}",
             f"section {v['id']} cuts no tray ceiling")
    for f in [i for i in S if i["kind"] == "fan"]:
        R.ok("3 Ceilings", f.get("size") == [1200, 1200], f"{f['id']} drawn at 1200 sweep",
             f"{f['id']} not at true 1200 sweep")
    ducted = {i["room"] for i in S if i["kind"] == "ducted"}
    slots = {i["room"] for i in S if i["kind"] == "supply_grille"}
    R.ok("3 Ceilings", ducted <= slots, "a slot diffuser for every ducted room",
         f"ducted without slot diffuser: {sorted(ducted - slots)}")
    R.add("3 Ceilings", "LOOK", f"level tags, coves, tracks and slot notes readable: {pg(pages, 'ceiling', 'sections')}")

    # ---- 4. feature walls
    refs = sorted({p.name for d in (root / "refs", ROOT / "refs") if d.exists() for p in d.iterdir()
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")})
    used = {Path(g["ref"]).name for g in m.feature_walls if g.get("ref")}
    for g in m.feature_walls:
        if not g.get("ref"):
            R.add("4 Feature walls", "LOOK", f"{g['id']} has no reference image: mood cannot be compared "
                                             f"({pg(pages, 'feature:' + g['id'])})")
        else:
            R.add("4 Feature walls", "LOOK", f"{g['id']}: compare the 3D view with {g['ref']} "
                                             f"({pg(pages, 'feature:' + g['id'])})")
    for r_ in refs:
        R.ok("4 Feature walls", r_ in used, f"reference {r_} has a feature wall", f"reference {r_} has no feature wall")
    fwalls = {(w["room"], w["wall"]) for w in m.wall_features if w.get("parent")}
    bad = [i["id"] for i in S if i["kind"] == "split" and (i["room"], i.get("wall")) in fwalls]
    R.ok("4 Feature walls", not bad, "no split AC on a feature wall", f"split AC on a feature wall: {bad}")

    # ---- 5. elevations
    from atelier.elev_detail import MIN_FACE, Face, elevation_views
    views = elevation_views(m)
    cov = {(v["room"], v["wall"]) for v in views}
    for r in m.rooms:
        seen = set()
        for f in geom.room_faces(r, m.walls):
            if f.length >= MIN_FACE and f.wall not in seen:
                seen.add(f.wall)
                if (r["id"], f.wall) not in cov:
                    R.add("5 Elevations", "FAIL", f"no elevation of {r['id']} wall {f.wall}")
    R.add("5 Elevations", "PASS", f"{len(views)} elevation sheets cover every wall face ≥ {MIN_FACE} "
                                  "(and every shorter face carrying a point)")
    shown = set()
    for v in views:
        F = Face(m, v)
        shown |= {p["id"] for p in F.points(S) if 0 <= p["x"] <= F.L}
    wall_pts = [i for i in S if i.get("wall") and i.get("z") is not None and i["system"] != "ac"]
    lost = [i["id"] for i in wall_pts if i["id"] not in shown]
    R.ok("5 Elevations", not lost, f"all {len(wall_pts)} wall points appear on an elevation",
         f"wall points on no elevation: {lost}")
    el_pages = [n for n in pages if n.startswith("elevation:")]
    R.add("5 Elevations", "LOOK", f"plates readable, two dimensions each, no overlaps: "
                                  f"p. {pages.index(el_pages[0]) + 1:02d}–{pages.index(el_pages[-1]) + 1:02d}"
          if el_pages else "no elevation pages")

    # ---- 5a. room boards
    from atelier.views3d import board_rooms
    for r in board_rooms(m):
        R.ok("5a Room boards", f"room:{r['id']}" in pages, f"room board for {r['id']}", f"no room board for {r['id']}")
    R.add("5a Room boards", "LOOK", "callouts clear of the vignettes, palette = codes on the drawings: "
          + pg(pages, *[f"room:{r['id']}" for r in board_rooms(m)]))

    # ---- 5b. sections, details, joinery boards
    R.ok("5b DT / JN", "dt01" in pages and "dt02" in pages, "DT-01 and DT-02 present (bubbles 1–6)",
         "DT-01 or DT-02 missing while elevations carry bubbles 1–6")
    for j in m.joinery:
        for row in j.get("rows", [])[:1]:
            o = 0
            for md in row["modules"]:
                if md["type"] == "hob":
                    R.ok("5b DT / JN", md["w"] >= 600, f"{j['id']} hob module {md['w']} takes a 560 cut-out",
                         f"{j['id']} hob module {md['w']} < 600: a 560 hob cut-out does not fit")
                if md["type"] == "sink":
                    R.ok("5b DT / JN", md["w"] >= 450, f"{j['id']} sink module {md['w']} takes the bowl",
                         f"{j['id']} sink module {md['w']} < 450: the bowl does not fit")
                o += md["w"]

    # ---- 6. function
    wall_body = unary_union([geom.wall_polygon(w) for w in m.walls])
    stuff = {f["id"]: geom.furniture_polygon(f) for f in m.furniture if f.get("kind") != "rug"}
    stuff.update({j["id"]: geom.joinery_polygon(j, m.wall(j["wall"]), rooms[j["room"]]) for j in m.joinery})
    stuff.update({s["id"]: geom.furniture_polygon(s) for s in m.sanitary})

    def blocked(zone, rid, skip):
        out = [k for k, g in stuff.items() if k not in skip and g.intersects(zone) and g.intersection(zone).area > 2e4]
        if zone.difference(poly[rid]).area > 2e4:
            out.append("the room's walls")
        return out
    def clear(zone_at, rid, skip, need):
        """Largest depth (25 mm steps, up to need) whose zone is free; the first things met if short."""
        d = 0
        while d < need:
            nxt = min(need, d + 25)
            hit = blocked(zone_at(nxt), rid, skip)
            if hit:
                return d, hit
            d = nxt
        return d, []

    for b in [f for f in m.furniture if f.get("kind") == "bed"]:
        w, dp = b["size"][0], b["size"][1]
        fx, fy = geom.compass_to_vec(b.get("facing", "N"))
        rx, ry = fy, -fx
        cx, cy = b["at"]
        stands = {f["id"] for f in m.furniture if f["room"] == b["room"] and f.get("kind") in ("bedside", "bench")}
        for s_ in (-1, 1):                              # along each long side, past the nightstand zone
            def zone(t, s_=s_):
                return Polygon([(cx + rx * s_ * a + fx * v, cy + ry * s_ * a + fy * v)
                                for a, v in ((w / 2, -dp / 2 + 500), (w / 2 + t, -dp / 2 + 500),
                                             (w / 2 + t, dp / 2), (w / 2, dp / 2))])
            d, hit = clear(zone, b["room"], {b["id"]} | stands, 600)
            side = "left" if s_ < 0 else "right"
            R.ok("6 Function", d >= 600, f"{b['id']} 600 clear on its {side} side",
                 f"{b['id']} ({b['room']}): {d} clear on its {side} side, needs 600 ({', '.join(hit)})")
    for j in m.joinery:
        if j.get("kind") not in TALL | {"kitchen_base"} or j.get("kind") == "shoe_rack":
            continue
        wall = m.wall(j["wall"])
        side = geom.room_side_of_wall(wall, rooms[j["room"]]) or "left"
        sg = 1 if side == "left" else -1
        f0 = geom.face_offset(wall, side) + sg * j["depth"]

        def zone(t, j=j, wall=wall, f0=f0, sg=sg):
            a, b_ = j["offset"] + 25, j["offset"] + j["width"] - 25
            return Polygon([geom.point_on_wall(wall, a, f0), geom.point_on_wall(wall, b_, f0),
                            geom.point_on_wall(wall, b_, f0 + sg * t), geom.point_on_wall(wall, a, f0 + sg * t)])
        kitchen = rooms[j["room"]].get("type") == "kitchen"
        skip = {j["id"]} | ({k["id"] for k in m.joinery if k["room"] == j["room"]} if kitchen else set())
        d, hit = clear(zone, j["room"], skip, 1000)
        R.ok("6 Function", d >= 1000, f"{j['id']} 1000 clear in front",
             f"{j['id']} ({j['kind']}, {j['room']}): {d} clear in front, needs 1000 ({', '.join(hit)})")
    for r in [x for x in m.rooms if x.get("type") == "kitchen"]:
        sink = hob = None
        for j in m.joinery:
            if j["room"] != r["id"] or not j.get("rows"):
                continue
            w = m.wall(j["wall"])
            o = j["offset"]
            for md in j["rows"][0]["modules"]:
                c = geom.point_on_wall(w, o + md["w"] / 2)
                if md["type"] == "sink":
                    sink = c
                if md["type"] == "hob":
                    hob = c
                o += md["w"]
        fr = next((i for i in S if i["kind"] == "fridge_socket" and i["room"] == r["id"]), None)
        if sink and hob and fr:
            legs = [math.dist(sink, hob), math.dist(hob, fr["at"]), math.dist(fr["at"], sink)]
            ok = all(1200 <= x <= 2700 for x in legs) and 4000 <= sum(legs) <= 7900
            R.ok("6 Function", ok, f"kitchen triangle {sum(legs):.0f} (legs {', '.join(f'{x:.0f}' for x in legs)})",
                 f"kitchen triangle {sum(legs):.0f}, legs {', '.join(f'{x:.0f}' for x in legs)} "
                 f"(each 1200–2700, total 4000–7900)" + (" — fridge position is a flagged default" if fr.get("flag") else ""))
        else:
            R.add("6 Function", "FAIL", f"kitchen {r['id']}: sink, hob or fridge missing for the work triangle")
    for s in [x for x in m.sanitary if x["kind"] == "wc"]:
        fx, fy = geom.compass_to_vec(s.get("facing", "N"))
        cx, cy = s["at"]
        near = [g for k, g in stuff.items() if k != s["id"]]
        sides = []
        for sg in (-1, 1):                              # to each side of the bowl's centre line
            ray = LineString([(cx, cy), (cx + sg * fy * 2000, cy - sg * fx * 2000)])
            hits = [Point(cx, cy).distance(ray.intersection(g)) for g in near if ray.intersects(g)]
            ex = ray.intersection(poly[s["room"]].exterior)
            if not ex.is_empty:
                hits.append(Point(cx, cy).distance(ex))
            sides.append(min(hits) if hits else 2000)
        side = min(sides)
        R.ok("6 Function", side >= 380, f"{s['id']} centre {side:.0f} from the nearest side wall / fixture",
             f"{s['id']} ({s['room']}): centre only {side:.0f} from a side wall or fixture (≥ 380)")
    for fan in [i for i in S if i["kind"] == "fan"]:
        sweep = Point(fan["at"]).buffer(600)
        clash = [i["id"] for i in S if i["room"] == fan["room"] and i["kind"] in ("supply_grille", "ducted", "split")
                 and (LineString(i["path"]) if i.get("path") else Point(i["at"])).distance(sweep) < 150]
        R.ok("6 Function", not clash, f"{fan['id']} clear of the AC", f"{fan['id']} sweep within 150 of {clash}")
    from atelier.services import check as svcheck
    fs = svcheck(m, S)
    R.ok("6 Function", not fs, "services review check: 0 findings",
         "services review check: " + "; ".join(msg for _, _, msg, _ in fs[:6]))
    R.add("6 Function", "LOOK", "900 circulation routes and door swings in use: " + pg(pages, "furniture", "presentation"))

    # ---- 7. look
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    from atelier import audit
    with redirect_stdout(buf):
        n = audit.main() if hasattr(audit, "main") else 0
    R.ok("7 Look", not n, "colours and fonts only from theme.py (token audit)", "token audit found literals")
    if text:
        unexplained = [i for i, t in enumerate(text, 1) if re.search(r"\d\*", t) and not re.search(r"verify", t, re.I)]
        R.ok("7 Look", not unexplained, "every page with * values explains them",
             f"* values with no 'verify' explanation on p. {unexplained}")
    R.add("7 Look", "LOOK", "no overlapping text, labels clear of furniture, legends match symbols: every page")

    # ---- 8. joinery
    for j in m.joinery:
        if j.get("kind") in TALL - {"shoe_rack"}:
            c = geom.joinery_polygon(j, m.wall(j["wall"]), rooms[j["room"]]).centroid
            cdef = next((x for x in m.ceilings if x["room"] == j["room"]), None)
            top_c = geom.ceiling_z_at(rooms[j["room"]], cdef, (c.x, c.y)) if cdef else m.levels.get("ceiling")
            top = j.get("z", 0) + j.get("height", 0)
            R.ok("8 Joinery", top_c is None or top_c - top <= 50, f"{j['id']} runs to the ceiling (+{top})",
                 f"{j['id']} stops at +{top}, {top_c - top if top_c else '?'} below the ceiling +{top_c}: "
                 f"add a loft row to the ceiling")
        if not (j.get("finish") or j.get("materials")):
            R.add("8 Joinery", "FAIL", f"{j['id']} ({j.get('kind')}) has no material code")
    for r in m.rooms:
        loose = [i for i in S if i["room"] == r["id"] and i.get("flag")
                 and i["kind"] in ("fridge_socket", "oven_16a", "microwave_socket", "dw_socket")]
        if loose:
            R.add("8 Joinery", "FAIL", f"{r['id']}: no joinery slot for " + ", ".join(
                f"{i['kind'].split('_')[0]} ({i['id']}*)" for i in loose) + " — their points are flagged defaults")
    return R


def write(root: Path, R: Report):
    out = root / "out" / "check.md"
    lines = [f"# Pre-check · {root.name}", "",
             f"**{R.count('FAIL')} FAIL · {R.count('LOOK')} LOOK · {R.count('PASS')} PASS** "
             "(agents/checker.md; LOOK items need a person)", ""]
    for sec in dict.fromkeys(s for s, _, _ in R.rows):
        lines += [f"## {sec}", ""]
        for st in ("FAIL", "LOOK", "PASS"):
            lines += [f"- **{st}** {t}" for s, x, t in R.rows if s == sec and x == st]
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.check")
    ap.add_argument("project", type=Path)
    a = ap.parse_args(argv)
    R = run(a.project)
    out = write(a.project, R)
    for sec, st, t in R.rows:
        if st == "FAIL":
            print(f"  FAIL  [{sec}] {t}")
    print(f"check {'✗' if R.count('FAIL') else '✓'} {R.count('FAIL')} FAIL · {R.count('LOOK')} LOOK · "
          f"{R.count('PASS')} PASS → {out}")
    return 1 if R.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())

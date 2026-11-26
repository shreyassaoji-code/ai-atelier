"""Services sheets: power, lighting, switching, plumbing, AC.

Drawn from projects/<name>/services.json (written by atelier.services). Colours
follow STANDARDS §1: INK for power and switches, AMBER for lighting, BLUE cold
water / refrigerant, FLAG hot water, GREEN waste and drainage.
"""
from __future__ import annotations

import json
import math
from collections import OrderedDict

from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from shapely.ops import unary_union

from atelier import geom
from atelier import theme as T
from atelier.draw import DASH, LW_HAIR, LW_LINE, LW_THIN, sans
from atelier.sheets import _plan_setup, split_walls
from atelier.symbols import _to_plan, draw_joinery, draw_sanitary, furniture_parts

OFF = 2.4      # page mm a wall device sits into the room from the face
LBL = 3.2      # further page mm for its height label

NAMES = {
    "socket": "Socket", "socket_usb": "Socket + USB", "double_socket": "Double socket", "lan": "LAN point",
    "tv_power": "TV power", "worktop_socket": "Worktop socket", "db": "Distribution board", "vdp": "Video door phone",
    "router": "Router", "geyser_point": "Geyser power", "ac_isolator": "AC isolator", "wm_socket": "Washing machine",
    "ip44_socket": "Socket IP44", "downlight": "Downlight", "fan": "Fan 1200 sweep", "cove": "Cove light",
    "exhaust": "Exhaust fan", "pendant": "Pendant", "track": "Magnetic track", "chandelier": "Chandelier",
    "spotlight": "Spotlight", "strip": "LED strip", "switchboard": "Switchboard", "switch_2way": "2-way switch", "cold": "Cold water",
    "hot": "Hot water", "waste": "Waste", "soil": "Soil (WC)", "floor_trap": "Floor trap", "geyser": "Geyser",
    "hot_run": "Hot water run", "split": "Split AC", "ducted": "Ducted AC (concealed)", "odu": "Outdoor unit",
    "supply_grille": "Linear slot diffuser", "return_grille": "Return grille", "refrigerant": "Refrigerant / drain route",
    "media": "Media / HDMI point", "fridge_socket": "Fridge socket", "oven_16a": "Oven 16A",
    "microwave_socket": "Microwave socket", "dw_socket": "Dishwasher 16A", "chimney_point": "Chimney point",
    "ro_point": "RO purifier point", "mirror_light": "Mirror light IP44",
    "socket_16a": "Power socket 16A", "wall_light": "Wall light", "mixer": "Mixer", "shower_head": "Shower head",
}
CODE_SYMBOL = {"socket_16a": "16A", "wall_light": "WL", "mixer": "MX", "shower_head": "SH",
               "media": "M", "fridge_socket": "F", "oven_16a": "O", "microwave_socket": "MW", "dw_socket": "DW",
               "chimney_point": "CH", "ro_point": "RO"}


def load_services(m):
    if getattr(m, "services_items", None) is not None:      # preview: computed in memory for that design
        return m.services_items
    p = m.root / "services.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: run  python -m atelier.services {m.root}")
    return json.loads(p.read_text())["items"]


# ------------------------------------------------------------------ geometry on the page
def into_vec(deg):
    a = math.radians(deg or 0)
    return math.sin(a), -math.cos(a)          # page: y down


def place(pv, it):
    """Page point of the symbol (wall devices stand off the face into the room)."""
    x, y = pv.P(*it["at"])
    if it.get("wall") and it.get("into") is not None:
        vx, vy = into_vec(it["into"])
        return x + vx * OFF, y + vy * OFF, vx, vy
    return x, y, 0.0, 0.0


# ------------------------------------------------------------------ symbols (page mm)
def sym(sh, kind, x, y, vx=0.0, vy=-1.0, c=None, z=9):
    """Draw one service symbol centred at (x, y)."""
    c = c or T.INK
    circ = lambda r, f=T.PAPER, e=c, lw=LW_THIN: sh.circle(x, y, r, edge=e, fill=f, lw=lw)  # noqa: E731
    tx = lambda s, cc=c, dx=0, dy=0: sh.text(x + dx, y + dy + 0.05, s, sans("dim", 700), cc,  # noqa: E731
                                            ha="center", va="center", zorder=z + 1)

    def box(w, h, f=T.PAPER, e=c, hatch=None, dash=None):
        sh.region([([(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2),
                     (x - w / 2, y + h / 2)], [])], fill=f, edge=e, lw=LW_THIN, hatch=hatch, dash=dash, z=z)

    def pins(r=1.15):
        px, py = -vy, vx
        for s in (-1, 1):
            sh.circle(x + px * s * r * 0.42, y + py * s * r * 0.42, 0.16, edge=c, fill=c, lw=LW_HAIR)

    if kind in ("socket", "worktop_socket"):
        circ(1.15); pins()
        if kind == "worktop_socket":
            sh.line([(x - 1.5 * -vy, y - 1.5 * vx), (x + 1.5 * -vy, y + 1.5 * vx)], c, LW_LINE, z=z)
    elif kind in ("ip44_socket", "wm_socket", "geyser_point"):
        circ(1.55, lw=LW_LINE); circ(1.0); pins(1.0)
    elif kind == "socket_usb":
        circ(1.15); pins()
        sh.region([([(x - 0.5, y + 0.35), (x + 0.5, y + 0.35), (x, y + 0.95)], [])], fill=c, edge=c, z=z + 1)
    elif kind == "double_socket":
        px, py = -vy, vx
        for s in (-1, 1):
            sh.circle(x + px * s * 1.15, y + py * s * 1.15, 1.1, edge=c, fill=T.PAPER, lw=LW_THIN)
            sh.circle(x + px * s * 1.15, y + py * s * 1.15, 0.2, edge=c, fill=c, lw=LW_HAIR)
    elif kind == "lan":
        sh.region([([(x - 1.2, y + 0.9), (x + 1.2, y + 0.9), (x, y - 1.2)], [])], fill=c, edge=c, lw=LW_HAIR, z=z)
    elif kind == "tv_power":
        box(3.2, 2.2); tx("TV")
    elif kind == "db":
        box(4.0, 2.4, f=c); tx("DB", T.PAPER)
    elif kind == "vdp":
        box(2.8, 2.4); tx("V")
    elif kind == "router":
        box(2.8, 2.4); tx("R")
    elif kind == "ac_isolator":
        circ(1.15)
        sh.line([(x - 0.8, y - 0.8), (x + 0.8, y + 0.8)], c, LW_THIN, z=z + 1)
        sh.line([(x - 0.8, y + 0.8), (x + 0.8, y - 0.8)], c, LW_THIN, z=z + 1)
    elif kind == "downlight":
        circ(1.05)
        sh.line([(x - 1.45, y), (x + 1.45, y)], c, LW_HAIR, z=z + 1)
        sh.line([(x, y - 1.45), (x, y + 1.45)], c, LW_HAIR, z=z + 1)
    elif kind == "exhaust":
        box(3.0, 3.0); circ(1.1)
        for a in (0, 120, 240):
            r = math.radians(a)
            sh.line([(x, y), (x + math.cos(r) * 1.0, y + math.sin(r) * 1.0)], c, LW_THIN, z=z + 1)
    elif kind in ("pendant", "chandelier"):
        circ(1.7, f=T.PAPER, lw=LW_LINE); circ(0.8, f=c)
    elif kind == "fan_hub":
        circ(1.0, f=c)
    elif kind == "switchboard":
        box(2.6, 1.7, f=c)
    elif kind == "switch_2way":
        circ(1.0, f=c)
        sh.line([(x + 0.7, y - 0.7), (x + 1.9, y - 1.9)], c, LW_THIN, z=z)
        sh.line([(x - 0.7, y + 0.7), (x - 1.9, y + 1.9)], c, LW_THIN, z=z)
    elif kind in ("cold", "hot"):
        circ(1.05, f=c, e=c)
    elif kind == "waste":
        circ(1.1, lw=LW_LINE)
        sh.circle(x, y, 0.35, edge=c, fill=c, lw=LW_HAIR)
    elif kind == "soil":
        circ(1.6, f=c)
    elif kind == "floor_trap":
        box(2.4, 2.4)
        sh.line([(x - 1.2, y - 1.2), (x + 1.2, y + 1.2)], c, LW_HAIR, z=z + 1)
        sh.line([(x - 1.2, y + 1.2), (x + 1.2, y - 1.2)], c, LW_HAIR, z=z + 1)
    elif kind == "geyser":
        circ(1.9, f=T.PAPER, e=c, lw=LW_LINE); tx("G", c)
    elif kind == "return_grille":
        box(3.2, 1.8, hatch="||||")
    elif kind in CODE_SYMBOL:                                   # appliance / media points: boxed code
        box(3.0 if len(CODE_SYMBOL[kind]) > 1 else 2.4, 2.2,
            f=T.PAPER if kind not in ("oven_16a", "dw_socket") else T.LIGHT); tx(CODE_SYMBOL[kind])
    elif kind == "mirror_light":
        px, py = -vy, vx
        sh.line([(x - px * 1.8, y - py * 1.8), (x + px * 1.8, y + py * 1.8)], c, LW_LINE, z=z)
        for k in (-1, 0, 1):
            sh.line([(x + px * k * 1.2, y + py * k * 1.2), (x + px * k * 1.2 + vx * 0.9, y + py * k * 1.2 + vy * 0.9)],
                    c, LW_HAIR, z=z)
    else:
        circ(1.0)


_PLACED: list = []


def _box(lx, ly, ha, s):
    from atelier.draw import text_width_mm
    w = text_width_mm(s, T.SIZES["dim"], 0.55)
    x0 = lx - w / 2 if ha == "center" else (lx if ha == "left" else lx - w)
    return (x0, ly - 0.9, x0 + w, ly + 0.9)


def _hits(b):
    return any(not (b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3]) for o in _PLACED)


def draw_track(sh, pts, c):
    """Magnetic track: double line with heads at intervals."""
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L * 0.45, (x1 - x0) / L * 0.45
    for s_ in (-1, 1):
        sh.line([(x0 + nx * s_, y0 + ny * s_), (x1 + nx * s_, y1 + ny * s_)], c, LW_THIN, z=9)
    n = max(2, int(L / 9))
    for i in range(n):
        t = (i + 0.5) / n
        sh.circle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 0.75, edge=c, fill=c, lw=LW_HAIR)


def label(sh, x, y, vx, vy, s, color=None, flag=False):
    if not s:
        return
    lx, ly = (x + vx * LBL, y + vy * LBL) if (vx or vy) else (x + 2.4, y - 2.0)
    ha = "center" if (vx or vy) else "left"
    if abs(vx) > 0.7:
        ha = "left" if vx > 0 else "right"
        lx = x + vx * (LBL - 1.0)
    for k in range(6):                       # step away from the wall until it is clear
        b = _box(lx, ly, ha, s)
        if not _hits(b):
            break
        if abs(vx) > 0.7:
            ly += 2.1 * (1 if k % 2 == 0 else -1) * (k // 2 + 1)
        else:
            lx_, ly_ = lx, ly
            ly = ly_ + (vy or 1) * 2.1
            lx = lx_
    _PLACED.append(_box(lx, ly, ha, s))
    sh.text(lx, ly, s + ("*" if flag else ""), sans("dim", 500), T.FLAG if flag else (color or T.GREY),
            ha=ha, va="center", zorder=11, path_effects=sh.halo(1.6))


def h_label(it):
    parts = []
    if it.get("z") not in (None, 0) and it.get("wall"):
        parts.append(f"h{it['z']}")
    if it.get("ip"):
        parts.append(it["ip"])
    if it.get("source") == "override":
        parts.append("ovr")
    return " ".join(parts)


# ------------------------------------------------------------------ base and legend
def services_base(pv, m, ceilings=False, items=()):
    _PLACED.clear()
    full, low = split_walls(m.walls)
    ops = lambda ws: [o for o in m.openings if any(w["id"] == o["wall"] for w in ws)]  # noqa: E731
    pv.fill(geom.cut_walls(full, ops(full)), fill=T.MID, z=8)
    pv.fill(geom.cut_walls(low, ops(low)), fill=T.LIGHT, edge=T.GREY, lw=LW_HAIR, z=8)
    by_id = {w["id"]: w for w in m.walls}
    for o in m.openings:
        pv.opening(by_id[o["wall"]], o, color=T.GREY, arc_color=T.HAIR)
    for f in m.furniture:
        if f.get("kind") == "rug":
            continue
        g = _to_plan(f, furniture_parts(f)[0][0])
        pv.fill(g, fill="none", edge=T.HAIR, lw=LW_HAIR, z=3)
    for j in m.joinery:
        pv.fill(geom.joinery_polygon(j, by_id[j["wall"]], m.room(j["room"])), fill="none", edge=T.HAIR,
                lw=LW_HAIR, z=3)
    if ceilings:
        for cdef in m.ceilings:
            r = m.room(cdef["room"])
            for s in cdef.get("steps", []):
                pv.fill(geom.step_polygon(r, s), fill="none", edge=T.GREY, lw=LW_HAIR, dash=DASH, z=3)
            for d in cdef.get("domes", []):
                pv.fill(geom.dome_polygon(d), fill="none", edge=T.GREY, lw=LW_HAIR, dash=DASH, z=3)
    from shapely.geometry import Point
    occ = unary_union([Point(*i["at"]).buffer(pv.s * 3.0) for i in items]
                      + [Point(*i["at"]).buffer(i.get("size", [1200])[0] / 2 + pv.s) for i in items
                         if i["kind"] == "fan"]
                      + [Point(*p).buffer(pv.s * 1.5) for i in items for p in i.get("path", [])])
    for r in m.rooms:
        from atelier.draw import text_width_mm
        px, py = pv.label_spot(r, occ if not occ.is_empty else None, 0,
                               width_mm=text_width_mm(r.get("name", "").upper(), T.SIZES["caps_label"], 0.8) + 2)
        x, y = pv.P(px, py)
        pv.sh.caps(x, y, r.get("name", r["id"]), T.GREY, role="caps_label", weight=600, ha="center",
                   zorder=4, path_effects=pv.sh.halo(2.0))


def legend_items(sh, kinds, color_of, heights):
    items = []
    for k in kinds:
        c = color_of(k)
        h = heights.get(k)
        name = NAMES.get(k, k) + (f" · {h}" if h else "")
        if k in ("cove", "hot_run", "refrigerant", "supply_grille"):
            dash = DASH if k != "supply_grille" else None
            items.append((name, lambda x, y, w, hh, c=c, dash=dash: sh.line(
                [(x, y + hh / 2), (x + w, y + hh / 2)], c, LW_LINE, dash)))
        elif k in ("split", "ducted", "odu"):
            items.append((name, lambda x, y, w, hh, c=c, k=k: sh.swatch(
                x, y, w, hh, fill=T.LIGHT if k == "odu" else T.PAPER, edge=c, lw=LW_THIN,
                dash=DASH if k == "ducted" else None)))
        elif k == "fan":
            items.append((name, lambda x, y, w, hh, c=c: (sh.circle(x + 3.5, y + hh / 2, 2.2, edge=c, lw=LW_HAIR),
                                                          sym(sh, "fan_hub", x + 3.5, y + hh / 2, c=c))))
        else:
            items.append((name, lambda x, y, w, hh, c=c, k=k: sym(sh, k, x + 3.5, y + hh / 2, c=c)))
    return items


def typical_heights(items):
    hs = {}
    for it in items:
        if it.get("z") not in (None, 0) and it.get("wall") and it.get("source") != "override":
            hs.setdefault(it["kind"], set()).add(it["z"])
    return {k: "h" + "/".join(str(v) for v in sorted(s)) for k, s in hs.items()}


def schedule_rows(items, kinds):
    rows = []
    for k in kinds:
        n = sum(1 for i in items if i["kind"] == k)
        if n:
            rows.append((str(n), NAMES.get(k, k), None))
    ov = [i["id"] for i in items if i.get("source") == "override"]
    if ov:
        rows.append(("ovr", "Overridden: " + ", ".join(ov), T.FLAG))
    fl = [i["id"] for i in items if i.get("flag") and i["kind"] in kinds]
    if fl:
        rows.append(("*", "Default position, confirm with the designer: " + ", ".join(fl), T.FLAG))
    return rows


def _finish(fr, sh, items, kinds, color_of, title):
    kinds = [k for k in kinds if any(i["kind"] == k for i in items)]
    fr.legend(legend_items(sh, kinds, color_of, typical_heights(items)))
    fr.head(title)
    fr.lines(schedule_rows(items, kinds))
    fr.y += 2
    fr.lines([("", "Generated by rule (STANDARDS §6) from the design, then services_overrides.json. "
               "Heights hNNN in mm above FFL to the device centre.", None)], color=T.GREY)


def _draw_points(sh, pv, items, color_of):
    for it in items:
        x, y, vx, vy = place(pv, it)
        sym(sh, it["kind"], x, y, vx or 0.0, vy or -1.0, color_of(it["kind"]))
        label(sh, x, y, vx, vy, h_label(it), flag=bool(it.get("flag")))


# ------------------------------------------------------------------ the five sheets
POWER_KINDS = ["socket", "double_socket", "socket_usb", "lan", "tv_power", "worktop_socket", "ip44_socket",
               "wm_socket", "geyser_point", "ac_isolator", "db", "vdp", "router"]
LIGHT_KINDS = ["downlight", "pendant", "track", "fan", "cove", "exhaust"]
PLUMB_KINDS = ["cold", "hot", "waste", "soil", "floor_trap", "geyser", "hot_run"]
AC_KINDS = ["split", "ducted", "odu", "supply_grille", "return_grille", "refrigerant"]


def power(m, no, total):
    sh, fr, pv, _ = _plan_setup(m, "Power plan", "Sockets, data and boards · scale 1:{scale}", no, total)
    items = [i for i in load_services(m) if i["system"] == "power"]
    services_base(pv, m, items=items)
    _draw_points(sh, pv, items, lambda k: T.INK)
    _finish(fr, sh, items, POWER_KINDS, lambda k: T.INK, "Power schedule")
    for db in [i for i in items if i["kind"] == "db" and i.get("protection")]:
        p = db["protection"]
        fr.y += 1
        fr.lines([("RCCB", f"{db['id']}: RCCB {p['rccb_ma']} mA on the wet-room circuits ("
                   + ", ".join(p["wet_rooms"]) + ")" + (" and on every socket circuit" if p.get("socket_circuits")
                                                         else "") + " (R6.9).", None)])
    return sh


def _lighting_layer(sh, pv, items, faint=False):
    a = T.AMBER
    for it in items:
        k = it["kind"]
        if k == "cove":
            sh.line([pv.P(*p) for p in it["path"]], a, LW_LINE if not faint else LW_THIN, DASH, z=9)
        elif k in ("track", "strip"):
            draw_track(sh, [pv.P(*p) for p in it["path"]], a)
        elif k == "fan":
            x, y = pv.P(*it["at"])
            sh.circle(x, y, pv.L(it.get("size", [1200])[0] / 2), edge=a, lw=LW_HAIR)
            sh.ax.patches[-1].set_linestyle(DASH)
            sym(sh, "fan_hub", x, y, c=a)
        else:
            x, y, vx, vy = place(pv, it)
            sym(sh, k, x, y, vx or 0.0, vy or -1.0, a)
            if not faint:
                label(sh, x, y, vx, vy, h_label(it), flag=bool(it.get("flag")))


def lighting(m, no, total):
    sh, fr, pv, _ = _plan_setup(m, "Lighting plan", "Fittings on the reflected ceiling · scale 1:{scale}", no, total)
    items = [i for i in load_services(m) if i["system"] == "lighting"]
    services_base(pv, m, ceilings=True, items=items)
    _lighting_layer(sh, pv, items)
    _finish(fr, sh, items, LIGHT_KINDS, lambda k: T.AMBER, "Lighting schedule")
    return sh


def _curve(sh, p0, p1, color, bend=0.22):
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    cx, cy = mx - dy * bend, my + dx * bend
    path = MplPath([p0, (cx, cy), p1], [MplPath.MOVETO, MplPath.CURVE3, MplPath.CURVE3])
    sh.ax.add_patch(PathPatch(path, facecolor="none", edgecolor=color, lw=LW_HAIR, linestyle=(0, (2.2, 1.2)),
                              zorder=7))


def switching(m, no, total):
    sh, fr, pv, _ = _plan_setup(m, "Switching plan", "Switches and what they control · scale 1:{scale}", no, total)
    allit = load_services(m)
    by_id = {i["id"]: i for i in allit}
    lights = [i for i in allit if i["system"] == "lighting"]
    sw = [i for i in allit if i["system"] == "switching"]
    services_base(pv, m, ceilings=True, items=lights + sw)
    _lighting_layer(sh, pv, lights, faint=True)
    for s in sw:
        x, y, vx, vy = place(pv, s)
        targets = [by_id[c] for c in s.get("controls", []) if c in by_id]
        pts = []
        for t in targets:
            if t["kind"] in ("cove", "track", "strip"):
                pts.append(pv.P(*t["path"][0]))
            elif t["kind"] == "geyser_point":
                tx_, ty_, _, _ = place(pv, t)
                pts.append((tx_, ty_))
            else:
                tx_, ty_, _, _ = place(pv, t)
                pts.append((tx_, ty_))
        cur = (x, y)
        rest = pts[:]
        while rest:                                   # chain: nearest next fitting
            nxt = min(rest, key=lambda p: math.dist(cur, p))
            _curve(sh, cur, nxt, T.INK)
            rest.remove(nxt)
            cur = nxt
        sym(sh, s["kind"], x, y, vx or 0.0, vy or -1.0, T.INK)
        n = len(s.get("controls", []))
        label(sh, x, y, vx, vy, f"h{s['z']}" + (f" · {n}" if s["kind"] == "switchboard" else ""))
    kinds = ["switchboard", "switch_2way"]
    items = sw
    fr.legend(legend_items(sh, kinds, lambda k: T.INK, typical_heights(items))
              + [("Controls (chain to each fitting)", lambda x, y, w, h: _curve(sh, (x, y + h), (x + w, y), T.INK)),
                 ("Fittings: see lighting plan", lambda x, y, w, h: sym(sh, "downlight", x + 3.5, y + h / 2,
                                                                      c=T.AMBER))])
    fr.head("Switch schedule")
    rows = []
    for s in sw:
        serves = " + ".join([s.get("serves", s["room"])] + s.get("also_serves", []))
        rows.append((s["id"], f"{'2-way' if s['kind'] == 'switch_2way' else 'board'} in {s['room']}"
                              f"{' for ' + serves if serves != s['room'] else ''}: {len(s.get('controls', []))} fittings",
                     None))
    fr.lines(rows, indent=14)
    fr.y += 2
    fr.lines([("", "Wet-room switches sit outside the room (R6.2). The number by a board is how many fittings "
               "it controls.", None)], color=T.GREY)
    return sh


def plumbing(m, no, total):
    sh, fr, pv, _ = _plan_setup(m, "Plumbing plan", "Water supply and drainage points · scale 1:{scale}", no, total)
    items = [i for i in load_services(m) if i["system"] == "plumbing"]
    services_base(pv, m, items=items)
    for s in m.sanitary:
        draw_sanitary(pv, s, "line")
    by_id = {w["id"]: w for w in m.walls}
    for j in m.joinery:
        if j.get("kind") in ("kitchen_base", "vanity"):
            draw_joinery(pv, j, by_id[j["wall"]], m.room(j["room"]), "line")
    col = {"cold": T.BLUE, "hot": T.FLAG, "hot_run": T.FLAG, "geyser": T.FLAG,
           "waste": T.GREEN, "soil": T.GREEN, "floor_trap": T.GREEN}
    for it in items:
        if it["kind"] == "hot_run":
            a = place(pv, {**it, "at": it["path"][0], "wall": True, "into": None})[:2]
            sh.line([pv.P(*p) for p in it["path"]], T.FLAG, LW_THIN, DASH, z=8)
            _ = a
    _draw_points(sh, pv, [i for i in items if i["kind"] != "hot_run"], lambda k: col.get(k, T.INK))
    _finish(fr, sh, items, PLUMB_KINDS, lambda k: col.get(k, T.INK), "Plumbing schedule")
    return sh


def ac(m, no, total):
    sh, fr, pv, _ = _plan_setup(m, "Air-conditioning plan", "Indoor and outdoor units · scale 1:{scale}", no, total)
    items = [i for i in load_services(m) if i["system"] == "ac"]
    services_base(pv, m, ceilings=True, items=items)
    for it in items:
        k = it["kind"]
        if k == "refrigerant":
            sh.line([pv.P(*p) for p in it["path"]], T.BLUE, LW_THIN, DASH, z=8)
        elif k == "supply_grille":
            a, b = it["path"]
            pa, pb = pv.P(*a), pv.P(*b)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            L = math.hypot(dx, dy)
            nx, ny = -dy / L * 0.6, dx / L * 0.6
            for s in (-1, 1):
                sh.line([(pa[0] + nx * s, pa[1] + ny * s), (pb[0] + nx * s, pb[1] + ny * s)], T.BLUE, LW_LINE, z=9)
        elif k in ("split", "ducted", "odu"):
            w, d = it.get("size", [900, 300])
            ang = (it.get("into") or 0)
            fx, fy = math.sin(math.radians(ang)), math.cos(math.radians(ang))
            rx, ry = fy, -fx
            cx, cy = it["at"]
            if k == "split":
                cx, cy = cx + fx * d / 2, cy + fy * d / 2
            pts = [pv.P(cx + sa * w / 2 * rx + sb * d / 2 * fx, cy + sa * w / 2 * ry + sb * d / 2 * fy)
                   for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            sh.region([(pts, [])], fill=T.LIGHT if k == "odu" else T.PAPER, edge=T.INK, lw=LW_THIN,
                      dash=DASH if k == "ducted" else None, z=9)
            x, y = pv.P(cx, cy)
            sh.text(x, y + 0.05, {"split": "AC", "ducted": "AC", "odu": "ODU"}[k], sans("dim", 700), T.INK,
                    ha="center", va="center", zorder=10)
            if k == "split":
                sh.text(x, y + 3.4, f"top h{it['z']}", sans("dim", 500), T.GREY, ha="center", zorder=11,
                        path_effects=sh.halo(1.6))
            if k == "ducted":
                sh.text(x, y + 3.4, "in ceiling drop", sans("dim", 500), T.GREY, ha="center", zorder=11,
                        path_effects=sh.halo(1.6))
        elif k == "return_grille":
            x, y = pv.P(*it["at"])
            sym(sh, "return_grille", x, y, c=T.BLUE)
    _finish(fr, sh, items, AC_KINDS, lambda k: T.BLUE if k in ("refrigerant", "supply_grille", "return_grille")
            else T.INK, "AC schedule")
    fr.lines([("", "Ducted where the room has a feature wall and a tray ceiling; split otherwise (R6.10).",
               None)], color=T.GREY)
    return sh


SHEET_DEFS = OrderedDict(
    power=(power, "Power plan", True),
    lighting=(lighting, "Lighting plan", True),
    switching=(switching, "Switching plan", True),
    plumbing=(plumbing, "Plumbing plan", True),
    ac=(ac, "Air-conditioning plan", True),
)
_ = unary_union

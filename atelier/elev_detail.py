"""Interior elevations at 1:25, one wall face per view (agents/STANDARDS.md §5).

A view is `design.json → views[]` with kind "elevation", `room` and `wall`; the
elevation shows that wall's face in that room, seen from inside, x from the
viewer's left corner. Sheets are listed in project.json as "elevation:<view id>".
"""
from __future__ import annotations

import math
import re

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from atelier import geom
from atelier import theme as T
from atelier import texture as TX
from atelier.draw import DASH, LW_CUT, LW_HAIR, LW_LINE, LW_THIN, PlanView, Sheet, dim_chain, sans, text_width_mm
from atelier.sheets import Frame, envelope_bounds, split_walls
from atelier.sheets_services import load_services

S = 25                                       # 1:25
# STANDARDS E5.2 / E5.7 defaults (the only place these numbers live)
D = dict(plinth=100, worktop=30, drawer_top=180, gap=3, slab=150, floor_slab=100, gola_h=50,
         plate={"socket": (86, 86, "6A"), "worktop_socket": (86, 86, "16A"), "double_socket": (146, 86, "6A×2"),
                "socket_usb": (86, 86, "USB"), "lan": (86, 86, "DATA"), "tv_power": (146, 86, "TV"),
                "ip44_socket": (100, 110, "IP44"), "wm_socket": (100, 110, "16A IP44"),
                "geyser_point": (100, 110, "16A IP44"), "ac_isolator": (86, 86, "20A"), "db": (350, 450, "DB"),
                "vdp": (130, 200, "VDP"), "router": (200, 150, "RTR"), "switch_2way": (86, 86, "2W")},
         pipe={"cold": (30, "C"), "hot": (30, "H"), "waste": (50, "D"), "soil": (110, "WC")})
BUBBLE_SHEET = {1: "DT-01", 2: "DT-01", 3: "DT-01", 4: "DT-02", 5: "DT-02", 6: "DT-02"}


# ------------------------------------------------------------------ the face and what is on it
class Face:
    def __init__(self, m, view):
        self.m, self.view = m, view
        self.room = m.room(view["room"])
        faces = [f for f in geom.room_faces(self.room, m.walls) if f.wall == view["wall"]]
        if not faces:
            raise ValueError(f"view {view['id']}: wall {view['wall']} has no face in room {view['room']}")
        self.f = max(faces, key=lambda f: f.length)
        self.L = self.f.length
        self.wall = m.wall(view["wall"])
        a, b = self.f.a, self.f.b
        self.ux, self.uy = (b[0] - a[0]) / self.L, (b[1] - a[1]) / self.L
        self.full_L = self.L
        self.x_from = 0.0                                  # this part starts this far from the wall's left corner
        self.cut_left = self.cut_right = False
        if view.get("range"):                              # part of a long wall: x range from the left corner
            xa, xb = view["range"]
            ta, tb = self.L - xb, self.L - xa              # x = L - t, t measured from face end a
            pa = (a[0] + self.ux * ta, a[1] + self.uy * ta)
            pb = (a[0] + self.ux * tb, a[1] + self.uy * tb)
            self.cut_right, self.cut_left = ta > 1, xa > 1
            self.f = geom.Edge(self.f.n, pa, pb, xb - xa, self.f.facing, self.f.wall)
            self.L, self.x_from = xb - xa, xa
        cdef = next((c for c in m.ceilings if c["room"] == self.room["id"]), None)
        self.soffit = m.levels.get("soffit", 3000)
        self.sflag = m.is_flagged(dict(m.levels), "soffit")
        self.fcl = cdef["z"] if cdef and cdef.get("z") else None
        self.t_left = 0 if self.cut_left else self._end_thickness(self.f.b, (self.ux, self.uy))   # viewer's left = end b
        self.t_right = 0 if self.cut_right else self._end_thickness(self.f.a, (-self.ux, -self.uy))
        self.parapet = self.wall.get("kind") == "parapet"

    def x_of(self, p):
        """Plan point -> x from the viewer's left corner."""
        t = (p[0] - self.f.a[0]) * self.ux + (p[1] - self.f.a[1]) * self.uy
        return self.L - t

    def x_on_wall(self, off):
        return self.x_of(geom.point_on_wall(self.wall, off))

    def _end_thickness(self, p, d):
        seg = LineString([(p[0] - d[0] * 2, p[1] - d[1] * 2), (p[0] + d[0] * 600, p[1] + d[1] * 600)])
        others = unary_union([geom.wall_polygon(w) for w in self.m.walls if w["id"] != self.wall["id"]])
        hit = seg.intersection(others)
        return round(hit.length) if not hit.is_empty else 0

    def end_height(self, side):
        """Height of the wall cut at the left / right end: parapets stop at their height."""
        p, d = (self.f.b, (self.ux, self.uy)) if side == "left" else (self.f.a, (-self.ux, -self.uy))
        seg = LineString([(p[0] - d[0] * 2, p[1] - d[1] * 2), (p[0] + d[0] * 600, p[1] + d[1] * 600)])
        hs = [w.get("height", PARAPET_H) if w.get("kind") == "parapet" else self.soffit
              for w in self.m.walls if w["id"] != self.wall["id"] and seg.intersects(geom.wall_polygon(w))]
        return max(hs) if hs else self.soffit

    def points(self, items):
        out = []
        line = LineString([self.f.a, self.f.b])
        for i in items:
            if i.get("room") != self.room["id"] or i.get("wall") != self.wall["id"] or i.get("z") is None:
                continue
            if line.distance(Point(i["at"])) > 10:
                continue
            out.append(dict(i, x=self.x_of(i["at"])))
        return sorted(out, key=lambda i: i["x"])

    def joinery(self):
        out = []
        for j in self.m.joinery:
            if j["wall"] != self.wall["id"] or j["room"] != self.room["id"]:
                continue
            mods, o = [], j["offset"]
            for k, md in enumerate((j.get("rows") or [{"modules": [{"w": j["width"], "type": "panel"}]}])[0]["modules"], 1):
                xa, xb = sorted((self.x_on_wall(o), self.x_on_wall(o + md["w"])))
                mods.append(dict(md, n=k, xa=xa, xb=xb))
                o += md["w"]
            upper = []
            for r_i, row in enumerate((j.get("rows") or [])[1:], 2):
                o = j["offset"]
                for k, md in enumerate(row["modules"], 1):
                    xa, xb = sorted((self.x_on_wall(o), self.x_on_wall(o + md["w"])))
                    upper.append(dict(md, n=f"{r_i}.{k}", xa=xa, xb=xb, row=r_i))
                    o += md["w"]
            xa, xb = sorted((self.x_on_wall(j["offset"]), self.x_on_wall(j["offset"] + j["width"])))
            if xb <= 1 or xa >= self.L - 1:
                continue
            out.append(dict(j=j, mods=mods, upper=upper, xa=xa, xb=xb))
        return out

    def openings(self):
        out = []
        for o in self.m.openings_on(self.wall["id"]):
            xa, xb = sorted((self.x_on_wall(o["offset"]), self.x_on_wall(o["offset"] + o["width"])))
            if xb < 0 or xa > self.L:
                continue
            out.append(dict(o, xa=max(xa, 0), xb=min(xb, self.L)))
        return out

    def features(self):
        out = []
        for wf in self.m.wall_features:
            if wf["wall"] == self.wall["id"] and wf["room"] == self.room["id"]:
                xa, xb = sorted((self.x_on_wall(wf["offset"]), self.x_on_wall(wf["offset"] + wf["width"])))
                if xb <= 1 or xa >= self.L - 1:                # on another part of a split wall
                    continue
                out.append(dict(wf, xa=max(xa, 0), xb=min(xb, self.L)))
        return out


# ------------------------------------------------------------------ every wall of every room (E5.1)
MIN_FACE = 600            # shorter faces are wall-junction slivers
MAX_PART = 4600           # longest wall stretch one 1:25 sheet holds beside its tags and markers
PARAPET_H = 1050          # (default) parapet height when the wall has no `height`


def _split_points(F, n):
    """n-1 break positions near equal parts, moved onto clear wall (no joinery, opening or service point)."""
    busy = [(j["xa"] - 120, j["xb"] + 120) for j in F.joinery()] + \
           [(o["xa"] - 120, o["xb"] + 120) for o in F.openings()] + \
           [(p["x"] - 250, p["x"] + 250) for p in F.points(load_services(F.m))]
    out = []
    for k in range(1, n):
        want = F.L * k / n
        cands = [want + d for d in range(0, int(F.L / 2), 50) for d in (d, -d)]
        x = next((c for c in cands if 300 < c < F.L - 300 and not any(a < c < b for a, b in busy)), want)
        out.append(round(x))
    return out


def elevation_views(m):
    """Every elevation sheet: design views[] of kind elevation first (in their room's place), then each
    remaining wall face of every room. Faces longer than MAX_PART become parts -p1, -p2 … with match lines."""
    data = [v for v in m.views if v.get("kind") == "elevation"]
    used = {(v["room"], v["wall"]) for v in data}
    out = []
    for r in m.rooms:
        seen = set()
        for f in geom.room_faces(r, m.walls):
            if f.wall in seen:
                continue
            best = max((x for x in geom.room_faces(r, m.walls) if x.wall == f.wall), key=lambda x: x.length)
            if best.length < MIN_FACE:
                continue
            seen.add(f.wall)
            v = next((d for d in data if d["room"] == r["id"] and d["wall"] == f.wall), None) or \
                {"id": f"E-{r['id']}-{f.wall}", "kind": "elevation", "room": r["id"], "wall": f.wall, "scale": 25,
                 "title": f"{r.get('name', r['id'])} · wall {f.wall}", "auto": True}
            out += _parts(m, v)
    for d in data:                                     # data views on faces the loop did not reach
        if not any(o["id"].startswith(d["id"]) for o in out):
            out += _parts(m, d)
    del used
    return out


def _parts(m, v):
    F = Face(m, v)
    if F.L <= MAX_PART:
        return [v]
    n = -(-int(F.L) // MAX_PART)
    xs = [0] + _split_points(F, n) + [round(F.L)]
    base = v.get("title") or v["id"]
    return [dict(v, id=f"{v['id']}-p{k}", range=[xs[k - 1], xs[k]], part=(k, n),
                 title=f"{base} · part {k} of {n}") for k in range(1, n + 1)]


# ------------------------------------------------------------------ drawing helpers
class Elev:
    s = S                                          # scale denominator (features.draw_pendants)

    def __init__(self, sh, F: Face, ex0, ey0):
        self.sh, self.F, self.ex0, self.ey0 = sh, F, ex0, ey0

    def X(self, x):
        return self.ex0 + x / S

    def Z(self, z):
        return self.ey0 - z / S

    def rect(self, xa, xb, za, zb, fill=None, edge=None, lw=LW_THIN, hatch=None, dash=None, z=4):
        self.sh.region([([(self.X(xa), self.Z(za)), (self.X(xb), self.Z(za)), (self.X(xb), self.Z(zb)),
                          (self.X(xa), self.Z(zb))], [])], fill=fill or "none", edge=edge or "none", lw=lw,
                       hatch=hatch, dash=dash, z=z)

    def line(self, pts, color=None, lw=LW_THIN, dash=None, z=5):
        self.sh.line([(self.X(x), self.Z(zz)) for x, zz in pts], color or T.INK, lw, dash, z=z)


def _tile_size(name):
    m_ = re.search(r"(\d+)\s*[x×]\s*(\d+)", name or "")
    if not m_:
        return None
    a, b = int(m_.group(1)), int(m_.group(2))
    return (max(a, b), min(a, b))          # laid horizontally: long side along the wall


def _swing(E, xa, xb, za, zb, hinge_left):
    """Shutter swing: dashed lines from the opening-side corners to the middle of the hinge side."""
    hx, ox = (xa, xb) if hinge_left else (xb, xa)
    E.line([(ox, za), (hx, (za + zb) / 2), (ox, zb)], T.GREY, LW_HAIR, (0, (2.0, 1.2)), z=6)


def _handle_v(E, x, za, zb):
    E.line([(x, za), (x, zb)], T.INK, LW_LINE, z=6)


def _module(E, md, z0, z1, label, idx, gola=False):
    """One joinery module front between z0 and z1."""
    xa, xb = md["xa"], md["xb"]
    g = D["gap"]
    E.rect(xa + g, xb - g, z0 + g, z1 - g, fill=TX.hexc(TX.palette()["joinery"]), edge=T.INK, lw=LW_THIN, z=4)
    ty = md.get("type")
    w = xb - xa
    if ty == "drawer":
        top = D["drawer_top"]
        cuts = [z1 - top, z0 + (z1 - top - z0) / 2]
        for c in cuts:
            E.line([(xa + g, c), (xb - g, c)], T.INK, LW_THIN, z=6)
        if not gola:
            for zt in (z1, cuts[0], cuts[1]):
                E.line([(xa + w * 0.38, zt - 45), (xb - w * 0.38, zt - 45)], T.INK, LW_LINE, z=6)
    elif ty in ("shutter", "loft", "glass_shutter"):
        hinge_left = idx % 2 == 0
        _swing(E, xa + g, xb - g, z0 + g, z1 - g, hinge_left)
        hx = xb - 60 if hinge_left else xa + 60
        if not gola:
            _handle_v(E, hx, z1 - 60, z1 - 200) if ty != "loft" else _handle_v(E, hx, z0 + 60, z0 + 200)
    elif ty == "sink":
        mid = (xa + xb) / 2
        E.line([(mid, z0 + g), (mid, z1 - g)], T.INK, LW_THIN, z=6)
        _swing(E, xa + g, mid - 1, z0 + g, z1 - g, True)
        _swing(E, mid + 1, xb - g, z0 + g, z1 - g, False)
        if not gola:
            _handle_v(E, mid - 50, z1 - 60, z1 - 200)
            _handle_v(E, mid + 50, z1 - 60, z1 - 200)
    elif ty == "hob":
        for k in range(4):
            cx = xa + w * (0.2 + 0.2 * k)
            E.sh.circle(E.X(cx), E.Z(z1 - 60), 18 / S, edge=T.INK, lw=LW_HAIR)
        _swing(E, xa + g, xb - g, z0 + g, z1 - 120, idx % 2 == 0)
    elif ty == "appliance":
        E.rect(xa + 30, xb - 30, z0 + 30, z1 - 30, edge=T.INK, lw=LW_HAIR, z=6)
    E.sh.text(E.X((xa + xb) / 2), E.Z(z0 + 90), label, sans("dim", 600), T.GREY, ha="center", va="center",
              zorder=7, path_effects=E.sh.halo(1.4))


def _plate(E, kind, x, z, label_override=None):
    w, h, lab = D["plate"].get(kind, (86, 86, kind[:3].upper()))
    lab = label_override or lab
    E.rect(x - w / 2, x + w / 2, z - h / 2, z + h / 2, fill=T.PAPER, edge=T.INK, lw=LW_THIN, z=8)
    if "IP44" in lab:
        E.rect(x - w / 2 + 8, x + w / 2 - 8, z - h / 2 + 8, z + h / 2 - 8, edge=T.INK, lw=LW_HAIR, z=8)
    fits = text_width_mm(lab, T.SIZES["dim"], 0.5) < w / S - 0.4
    if fits:
        E.sh.text(E.X(x), E.Z(z), lab, sans("dim", 600), T.INK, ha="center", va="center", zorder=9)
    else:
        E.sh.text(E.X(x), E.Z(z - h / 2) + 1.6, lab, sans("dim", 600), T.INK, ha="center", va="center", zorder=9,
                  path_effects=E.sh.halo(1.4))
    return w, h


def _pipe(E, kind, x, z):
    d, lab = D["pipe"][kind]
    col = {"cold": T.BLUE, "hot": T.FLAG, "waste": T.GREY, "soil": T.GREY}[kind]
    E.sh.circle(E.X(x), E.Z(z), d / 2 / S + 0.35, edge=col, fill=col if kind != "waste" else T.PAPER, lw=LW_LINE)
    E.sh.ax.patches[-1].set_zorder(8)
    E.sh.text(E.X(x) + d / 2 / S + 0.9, E.Z(z) - 0.9, lab, sans("dim", 700), col, va="center", zorder=9)
    return d, d


def _mixer(E, x, z_top):
    """Sink mixer above the worktop: body, spout arc."""
    E.rect(x - 25, x + 25, z_top, z_top + 220, fill=TX.hexc(TX.palette()["metal"]), edge=T.INK, lw=LW_HAIR, z=8)
    r = 90                                                     # spout: up from the body, arcing over to the bowl
    pts = [(x + r - r * math.cos(math.radians(a)), z_top + 220 + 1.3 * r * math.sin(math.radians(a)))
           for a in range(0, 181, 10)]
    E.line(pts, T.INK, LW_LINE, z=8)


def _bubble(sh, x, y, n, target):
    r = 3.3
    sh.line([target, (x, y)], T.INK, LW_HAIR, z=12)
    sh.circle(target[0], target[1], 0.35, edge=T.INK, fill=T.INK, lw=LW_HAIR)
    sh.circle(x, y, r, edge=T.INK, fill=T.PAPER, lw=LW_THIN)
    sh.ax.patches[-1].set_zorder(13)
    sh.line([(x - r, y), (x + r, y)], T.INK, LW_HAIR, z=14)
    sh.text(x, y - 1.5, str(n), sans("legend_head", 700), T.INK, ha="center", va="center", zorder=14)
    sh.text(x, y + 1.55, BUBBLE_SHEET[n], sans("dim", 600), T.INK, ha="center", va="center", zorder=14)


def _metres(z):
    return ("±" if z == 0 else "+" if z > 0 else "−") + f"{abs(z) / 1000:.3f}"


def _spread(ys, gap):
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out, nxt = list(ys), -1e9
    for i in order:
        out[i] = max(out[i], nxt)
        nxt = out[i] + gap
    return out


# ------------------------------------------------------------------ the elevation
def draw_elevation(sh, m, view, ex0, ey0):
    F = Face(m, view)
    E = Elev(sh, F, ex0, ey0)
    L, soff = F.L, F.soffit
    fin = {f["code"]: f for f in m.finishes}
    pal = TX.palette()
    items = load_services(m)
    pts = F.points(items)
    J = F.joinery()
    O = F.openings()
    FW = F.features()
    floor = next((fl for fl in m.floors if fl["room"] == F.room["id"]), {})
    wall_code = F.room.get("wall_finish")
    top_fc = F.fcl or soff

    # slabs, end walls (E5.11), false ceiling
    E.rect(-F.t_left, L + F.t_right, soff, soff + D["slab"], fill=T.PAPER, edge=T.INK, hatch="////", z=3)
    E.rect(-F.t_left, L + F.t_right, -D["floor_slab"], 0, fill=T.PAPER, edge=T.INK, hatch="////", z=3)
    E.rect(-F.t_left, 0, 0, F.end_height("left"), fill=T.POCHE, z=9)
    E.rect(L, L + F.t_right, 0, F.end_height("right"), fill=T.POCHE, z=9)
    if F.fcl:
        E.rect(0, L, F.fcl, soff, fill=T.LIGHT, z=2)
        E.line([(0, F.fcl), (L, F.fcl)], T.INK, LW_CUT, z=6)
    E.line([(0, 0), (L, 0)], T.INK, LW_CUT, z=6)
    for x, cut in ((0, F.cut_left), (L, F.cut_right)):          # match lines where a long wall is split
        if cut:
            zz = [-D["floor_slab"], soff * 0.45, soff * 0.47, soff * 0.53, soff * 0.55, soff + D["slab"]]
            dx = [0, 0, -60, 60, 0, 0]
            E.line([(x + d, z_) for d, z_ in zip(dx, zz)], T.INK, LW_THIN, z=10)
            sh.text(E.X(x) + (1.6 if x == 0 else -1.6), E.Z(soff * 0.25), "MATCH LINE", sans("dim", 600), T.GREY,
                    rotation=90, ha="center", va="center", zorder=10)
    if F.parapet:                                               # open above a parapet
        ph = F.wall.get("height", PARAPET_H)
        pfl = "height" not in F.wall
        E.rect(0, L, ph, top_fc, fill=TX.hexc(TX.mix(T.BLUE, T.PAPER, 0.86)), z=2)
        E.line([(0, ph), (L, ph)], T.INK, LW_CUT, z=6)
        sh.text(E.X(L / 2), E.Z(ph) - 2.0, f"OPEN ABOVE PARAPET +{ph}" + ("*" if pfl else ""), sans("dim", 600),
                T.FLAG if pfl else T.GREY, ha="center", zorder=7)

    # wall features (STANDARDS §4): one drawing routine for every element type
    from atelier import features as FT
    for wf in FW:
        FT.draw(E, m, wf, wf["xa"], wf["xb"], wf["z0"], min(wf["z1"], top_fc))
    for g in getattr(m, "feature_walls", []):                   # LED reveals at joints
        if g["room"] == F.room["id"] and g.get("wall") == F.wall["id"]:
            for ld in g.get("led", []):
                x = ld["u"] - F.x_from
                if 0 < x < L:
                    FT.draw_led(E, x, ld.get("z0", 0), min(ld.get("z1", top_fc), top_fc))
            FT.draw_pendants(E, g, F.x_from, top_fc, L)
    # openings
    for o in O:
        sill = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
        head = o.get("head", 2100)
        if o.get("concealed"):                                  # flush door hidden in the panelling
            host = next((w for w in FW if w["id"] == o.get("concealed_in")), None)
            FT.draw_concealed(E, o["xa"], o["xb"], head, FT.tone_of(m, host) if host else TX.finish_tone({}))
            E.sh.text(E.X((o["xa"] + o["xb"]) / 2), E.Z(head) - 1.4, o["id"], sans("dim", 600), T.GREY,
                      ha="center", zorder=6)
            continue
        E.rect(o["xa"], o["xb"], sill, head, fill=T.PAPER, edge=T.INK, lw=LW_LINE, z=5)
        if o["kind"] in ("window", "ventilator"):
            E.rect(o["xa"] + 50, o["xb"] - 50, sill + 50, head - 50, edge=T.INK, lw=LW_HAIR, z=5)
            mid = (o["xa"] + o["xb"]) / 2
            E.line([(mid, sill + 50), (mid, head - 50)], T.INK, LW_HAIR, z=5)
            for xa_, xb_ in ((o["xa"] + 50, mid), (mid, o["xb"] - 50)):
                E.line([(xa_ + 80, head - 250), (xa_ + 280, head - 450)], T.HAIR, LW_HAIR, z=5)
            E.line([(o["xa"] - 30, sill), (o["xb"] + 30, sill)], T.INK, LW_LINE, z=5)
            E.sh.text(E.X(mid), E.Z(head) - 1.4, o["id"], sans("dim", 600), T.GREY, ha="center", zorder=6)
        else:
            E.sh.text(E.X((o["xa"] + o["xb"]) / 2), E.Z(head) - 1.4, o["id"], sans("dim", 600), T.GREY,
                      ha="center", zorder=6)

    # skirting only on bare wall (E5.10)
    sk = floor.get("skirting", 0)
    bare = []
    if sk:
        bare = [(0.0, L)]
        for blk in [(j["xa"], j["xb"]) for j in J] + [(o["xa"], o["xb"]) for o in O
                                                     if o["kind"] not in ("window", "ventilator")]:
            nxt = []
            for a, b in bare:
                if blk[1] <= a or blk[0] >= b:
                    nxt.append((a, b))
                else:
                    if a < blk[0]:
                        nxt.append((a, blk[0]))
                    if blk[1] < b:
                        nxt.append((blk[1], b))
            bare = nxt
        for a, b in bare:
            if b - a > 20:
                E.rect(a, b, 0, sk, fill=TX.hexc(pal["wood_lt"]), edge=T.INK, lw=LW_HAIR, z=5)

    # joinery (E5.7)
    sink_x = []
    for jj in J:
        j = jj["j"]
        H = j.get("height", 850)
        base = j.get("kind") in ("kitchen_base", "vanity")
        rows = j.get("rows") or [{"height": H}]
        r1 = rows[0]["height"]
        top = r1 - (D["worktop"] if base else 0)
        E.rect(jj["xa"], jj["xb"], 0, D["plinth"], fill=TX.hexc(TX.mix(T.MID, T.PAPER, 0.4)), edge=T.INK,
               lw=LW_HAIR, z=4)
        gola = j.get("handles") == "gola"
        front_top = top - (D["gola_h"] if gola else 0)
        if gola:                                       # continuous aluminium gola recess under the worktop
            E.rect(jj["xa"], jj["xb"], front_top, top, fill=T.MID, edge=T.INK, lw=LW_HAIR, z=5)
            E.line([(jj["xa"], front_top + D["gola_h"] * 0.55), (jj["xb"], front_top + D["gola_h"] * 0.55)],
                   T.INK, LW_HAIR, z=6)
        for k, md in enumerate(jj["mods"]):
            _module(E, md, D["plinth"], front_top, f"{j['id']}.{md['n']}", k, gola)
            if md.get("type") == "sink":
                sink_x.append((md["xa"] + md["xb"]) / 2)
                E.rect(md["xa"] + 0.15 * (md["xb"] - md["xa"]), md["xb"] - 0.15 * (md["xb"] - md["xa"]),
                       top - 220, top, edge=T.GREY, lw=LW_HAIR, dash=DASH, z=7)
        if base:
            E.rect(jj["xa"] - 20, jj["xb"] + 20 if jj["xb"] < L - 1 else jj["xb"], top, r1,
                   fill=TX.hexc(pal["worktop"]), edge=T.INK, lw=LW_THIN, z=6)
        z = r1
        for k, md in enumerate(jj["upper"]):
            row_h = rows[md["row"] - 1]["height"]
            _module(E, md, z, z + row_h, f"{j['id']}.{md['n']}", k)
        for x in sink_x:
            _mixer(E, x, r1)

    # points: plates and pipes at true size and height (E5.2/5.3), red drops (E5.5), heights (E5.4)
    placed_text = []
    for i, p in enumerate(pts):
        x, z = p["x"], p["z"]
        if p["system"] == "plumbing" and p["kind"] in D["pipe"]:
            w, h = _pipe(E, p["kind"], x, z)
        else:
            label = None
            if p["kind"] == "switchboard":
                n = len(p.get("controls", []))
                wmm = 86 if n <= 2 else 146 if n <= 4 else 206 if n <= 6 else 266
                D["plate"]["switchboard"] = (wmm, 86, f"{max(2, min(8, n * 2 // 2 * 1))}M SW")
            w, h = _plate(E, p["kind"], x, z, label)
            E.line([(x, top_fc), (x, z + h / 2)], T.FLAG, LW_THIN, z=7)
        # height from FFL: dimension just left of the point
        dx = x - w / 2 - 70
        E.line([(dx, 0), (dx, z)], T.INK, LW_HAIR, z=7)
        for zz in (0, z):
            E.line([(dx - 25, zz - 25), (dx + 25, zz + 25)], T.INK, LW_THIN, z=7)
        ty = E.Z(z) + 4.0
        while any(abs(ty - t_) < 2.6 and abs(E.X(dx) - xx) < 3 for xx, t_ in placed_text):
            ty += 2.8
        placed_text.append((E.X(dx), ty))
        sh.text(E.X(dx) - 0.7, ty, str(z), sans("dim", 500), T.INK, rotation=90, ha="right", va="center",
                zorder=9, path_effects=sh.halo(1.4))

    # chains (E5.4 / E5.13): points from the left corner, modules, overall
    yb = E.Z(-D["floor_slab"])
    px = sorted({0, round(L)} | {round(p["x"]) for p in pts})
    if len(px) > 2:
        dim_chain(sh, (E.X(0), yb + 7), (1, 0), (0, 1), [x / S for x in px], [px[i + 1] - px[i] for i in
                  range(len(px) - 1)], [False] * (len(px) - 1), ext_from=[7 + (ey0 - yb) + 0] * len(px))
        sh.caps(E.X(0) - 2, yb + 8.2, "Points", T.GREY, ha="right")
    mx = {0, round(L)}
    for jj in J:
        mx |= {round(md["xa"]) for md in jj["mods"]} | {round(md["xb"]) for md in jj["mods"]}
    mx = sorted(x for x in mx if 0 <= x <= round(L))
    tier = 14
    if len(mx) > 2:
        dim_chain(sh, (E.X(0), yb + tier), (1, 0), (0, 1), [x / S for x in mx], [mx[i + 1] - mx[i] for i in
                  range(len(mx) - 1)], [False] * (len(mx) - 1), ext_from=[7] * len(mx))
        sh.caps(E.X(0) - 2, yb + tier + 1.2, "Modules", T.GREY, ha="right")
        tier += 7
    ox_ = sorted({0, round(L)} | {round(v) for o in O for v in (o["xa"], o["xb"])})
    if len(ox_) > 2:
        dim_chain(sh, (E.X(0), yb + tier), (1, 0), (0, 1), [x / S for x in ox_], [ox_[i + 1] - ox_[i] for i in
                  range(len(ox_) - 1)], [False] * (len(ox_) - 1), ext_from=[7] * len(ox_))
        sh.caps(E.X(0) - 2, yb + tier + 1.2, "Openings", T.GREY, ha="right")
        tier += 7
    dim_chain(sh, (E.X(0), yb + tier), (1, 0), (0, 1), [0, L / S], [round(L)], [False], ext_from=[7, 7])
    sh.caps(E.X(0) - 2, yb + tier + 1.2, "Overall", T.GREY, ha="right")

    # level chain + markers (E5.9 / E5.13)
    lv = {0: False, soff: F.sflag}
    if J:
        lv[D["plinth"]] = False
        for jj in J:
            lv[jj["j"].get("rows", [{"height": 850}])[0]["height"]] = False
    for wf in FW:
        lv[wf["z1"]] = False
    for o in O:
        if o["kind"] in ("window", "ventilator"):
            lv[o.get("sill", 900)] = False
        lv[o.get("head", 2100)] = False
    if F.fcl:
        lv[F.fcl] = False
    zs = sorted(lv)
    xr = E.X(L) + F.t_right / S + 6
    dim_chain(sh, (xr, E.Z(0)), (0, -1), (1, 0), [z / S for z in zs], [zs[i + 1] - zs[i] for i in range(len(zs) - 1)],
              [lv[zs[i + 1]] or lv[zs[i]] for i in range(len(zs) - 1)], ext_from=[F.t_right / S + 6] * len(zs))
    marks = [(0, "FFL ±0.000", False)]
    if F.fcl:
        marks.append((F.fcl, f"FCL {_metres(F.fcl)}", False))
    marks.append((soff, f"SOFFIT {_metres(soff)}", F.sflag))
    xm = xr + 9
    ys = _spread([E.Z(z) for z, _, _ in sorted(marks, key=lambda t: -t[0])], 3.0)
    for (z, txt, fl), y in zip(sorted(marks, key=lambda t: -t[0]), ys):
        s_ = 1.1
        sh.region([([(xm - s_, E.Z(z) - s_), (xm + s_, E.Z(z) - s_), (xm, E.Z(z))], [])], fill=T.INK, edge=T.INK,
                  lw=LW_HAIR, z=8)
        sh.line([(xm - 4, E.Z(z)), (xm + 1.5, E.Z(z))], T.INK, LW_HAIR, z=8)
        sh.text(xm + 2.2, y - 0.6, txt + ("*" if fl else ""), sans("dim", 600), T.FLAG if fl else T.INK,
                va="center", zorder=9)

    # vertical code rail (height zones) and horizontal code rail (zones along the wall)  (E5.8)
    xl = E.X(-F.t_left) - 16
    zones = []
    if J:
        jj = max(J, key=lambda t: t["xb"] - t["xa"])
        zones += [(0, D["plinth"], "PLINTH"), (D["plinth"], jj["j"]["rows"][0]["height"], jj["j"]["id"])]
        zlo = jj["j"]["rows"][0]["height"]
    else:
        zones += [(0, sk, "SK")] if sk else []
        zlo = sk
    fwz = max(FW, key=lambda t: t["xb"] - t["xa"]) if FW else None
    if fwz and fwz["z0"] <= zlo + 1:
        zones.append((zlo, fwz["z1"], f"{fwz['id']} {fwz['finish']}"))
        zlo = fwz["z1"]
    zones.append((zlo, top_fc, wall_code or "—"))
    if F.fcl:
        zones.append((F.fcl, soff, "FC VOID"))
    for za, zb, code in zones:
        sh.region([([(xl, E.Z(za)), (xl + 5, E.Z(za)), (xl + 5, E.Z(zb)), (xl, E.Z(zb))], [])], fill=T.PAPER,
                  edge=T.INK, lw=LW_HAIR, z=8)
        if (zb - za) / S > text_width_mm(code, T.SIZES["dim"], 0.62) + 1:
            sh.text(xl + 2.5, (E.Z(za) + E.Z(zb)) / 2, code, sans("dim", 600), T.INK, rotation=90, ha="center",
                    va="center", zorder=9)
    yr = yb + tier + 6
    hz = [(0, L, wall_code or "—")]
    for fz in FW:
        hz = [(a, b, c) for a, b, c in hz if b <= fz["xa"] or a >= fz["xb"]] + \
             [(max(a, fz["xa"]), min(b, fz["xb"]), f"{fz['id']} {fz['finish']}") for a, b, c in hz
              if not (b <= fz["xa"] or a >= fz["xb"])] + \
             [(a, fz["xa"], c) for a, b, c in hz if a < fz["xa"] < b] + [(fz["xb"], b, c) for a, b, c in hz
                                                                         if a < fz["xb"] < b]
    for o in O:
        if o["kind"] in ("window", "ventilator"):
            hz.append((o["xa"], o["xb"], o["id"]))
    hz = sorted({(round(a), round(b), c) for a, b, c in hz if b - a > 1})
    for k, (a, b, c) in enumerate(hz):
        row = 1 if c.startswith("W") and len(c) <= 3 else 0
        y = yr + row * 5.2
        sh.region([([(E.X(a), y), (E.X(b), y), (E.X(b), y + 4.4), (E.X(a), y + 4.4)], [])], fill=T.PAPER,
                  edge=T.INK, lw=LW_HAIR, z=8)
        if (b - a) / S > text_width_mm(c, T.SIZES["dim"], 0.62) + 1:
            sh.text((E.X(a) + E.X(b)) / 2, y + 2.25, c, sans("dim", 600), T.INK, ha="center", va="center", zorder=9)
    sh.caps(E.X(0) - 2, yr + 3.0, "Codes", T.GREY, ha="right")

    # material tags with leaders (E5.6)
    tags = []
    if wall_code:
        tags.append((wall_code, fin.get(wall_code, {}).get("name", ""), (L * 0.18, (zlo + top_fc) / 2 + 300)))
    for fz in FW:
        tags.append((f"{fz['id']} · {fz['finish']}", fin.get(fz["finish"], {}).get("name", ""),
                     (fz["xa"] + 0.12 * (fz["xb"] - fz["xa"]), (fz["z0"] + fz["z1"]) / 2)))
    for jj in J:
        j = jj["j"]
        if j.get("worktop"):
            tags.append((j["worktop"], fin.get(j["worktop"], {}).get("name", ""),
                         (jj["xa"] + 0.08 * (jj["xb"] - jj["xa"]), j["rows"][0]["height"] - 15)))
        if j.get("finish"):
            m0 = jj["mods"][0]
            tags.append((j["finish"], fin.get(j["finish"], {}).get("name", ""), ((m0["xa"] + m0["xb"]) / 2 + 120, 450)))
    if floor.get("finish"):
        tags.append((floor["finish"], fin.get(floor["finish"], {}).get("name", ""), (L * 0.5, -40)))
    xt = xm + 30
    tys = _spread([E.Z(t[2][1]) for t in tags], 7.4)
    for (code, name, (x, z)), ty in sorted(zip(tags, tys), key=lambda t: t[1]):
        sh.line([(E.X(x), E.Z(z)), (xt - 3, ty), (xt - 1, ty)], T.INK, LW_HAIR, z=11)
        sh.circle(E.X(x), E.Z(z), 0.4, edge=T.INK, fill=T.INK, lw=LW_HAIR)
        sh.ax.patches[-1].set_zorder(11)
        w = text_width_mm(code, T.SIZES["dim"], 0.62) + 2.4
        sh.region([([(xt - 1, ty - 1.6), (xt - 1 + w, ty - 1.6), (xt - 1 + w, ty + 1.6), (xt - 1, ty + 1.6)], [])],
                  fill=T.PAPER, edge=T.INK, lw=LW_HAIR, z=11)
        sh.text(xt - 1 + w / 2, ty + 0.05, code, sans("dim", 700), T.INK, ha="center", va="center", zorder=12)
        short = name.split(",")[0]
        sh.text(xt, ty + 3.6, short[:30], sans("dim"), T.GREY, va="center", zorder=12)

    # detail bubbles (E5.12): only where the element is on this wall
    targets = {}
    cdef = next((c for c in m.ceilings if c["room"] == F.room["id"]), None)
    if cdef and any(st_.get("light") == "cove" for st_ in cdef.get("steps", [])) and F.fcl:
        targets[1] = (L * 0.30, F.fcl)
    pan = next((wf for wf in FW if wf.get("kind") in ("panelling", "fluted")), None)
    if pan:
        targets[2] = ((pan["xa"] + pan["xb"]) / 2, (pan["z0"] + pan["z1"]) / 2)
    if sk and bare:
        a_, b_ = max(bare, key=lambda t: t[1] - t[0])
        if b_ - a_ > 20:
            targets[3] = ((a_ + b_) / 2, sk / 2)
    door = next((o for o in O if o["kind"] in ("door", "double_door")), None)
    if door:
        targets[4] = (door["xa"] + 20, 1000)
    base_j = next((jj for jj in J if jj["j"].get("kind") in ("kitchen_base", "vanity")), None)
    if base_j:
        wt = base_j["j"]["rows"][0]["height"]
        targets[5] = (base_j["xa"] + 0.25 * (base_j["xb"] - base_j["xa"]), wt - 25)
    ward = next((jj for jj in J if jj["j"].get("kind") == "wardrobe"), None)
    if ward:
        targets[6] = ((ward["xa"] + ward["xb"]) / 2, 1200)
    offs = {1: (7, -9), 2: (-9, -10), 3: (8, -9), 4: (-9, -9), 5: (-7, -16), 6: (9, -10)}
    for n, (x, z) in sorted(targets.items()):
        tx, tz = E.X(x), E.Z(z)
        ox, oy = offs[n]
        _bubble(sh, tx + ox, tz + oy, n, (tx, tz))

    return F, pts, J, O, FW, [t[0] for t in tags]


# ------------------------------------------------------------------ the sheet
def key_plan(sh, m, F, x0, y0, w):
    b = envelope_bounds(m.walls)
    scale = 25 * math.ceil((b[2] - b[0]) / w / 25)
    pv = PlanView(sh, b, scale, centre=(x0 + w / 2, y0 + (b[3] - b[1]) / scale / 2))
    pv.fill(geom.room_polygon(F.room), fill=T.LIGHT, z=1)
    full, low = split_walls(m.walls)
    pv.fill(geom.walls_union(full), fill=T.GREY, z=2)
    pv.fill(geom.walls_union(low), fill=T.MID, z=2)
    a, bb = pv.P(*F.f.a), pv.P(*F.f.b)
    sh.line([a, bb], T.INK, 2.2, z=4)
    c = geom.label_point(F.room)
    cx, cy = pv.P(c.x, c.y)
    mx, my = (a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2
    sh.ax.annotate("", xy=(cx + (mx - cx) * 0.75, cy + (my - cy) * 0.75), xytext=(cx, cy),
                   arrowprops=dict(arrowstyle="-|>", lw=LW_THIN, color=T.INK, mutation_scale=6), zorder=5)
    # mark the viewer's left corner
    sh.circle(bb[0], bb[1], 0.8, edge=T.INK, fill=T.PAPER, lw=LW_THIN)
    sh.ax.patches[-1].set_zorder(6)
    return y0 + (b[3] - b[1]) / scale + 2, scale


def elevation_sheet(m, no, total, view_id):
    view = next(v for v in elevation_views(m) if v.get("id") == view_id)
    sh = Sheet()
    room = m.room(view["room"])
    title = f"Elevation {view_id}"
    fr = Frame(sh, m, title, f"{view.get('title') or room.get('name', room['id'])} · 1:{S}", no, total, S)
    x0, y0, x1, y1 = T.DRAW
    F = Face(m, view)
    ex0 = x0 + 30 + F.t_left / S
    ey0 = y0 + 10 + (F.soffit + D["slab"]) / S
    F, pts, J, O, FW, codes = draw_elevation(sh, m, view, ex0, ey0)
    looking = geom.vec_to_cardinal((F.f.b[1] - F.f.a[1]), -(F.f.b[0] - F.f.a[0]))   # outward normal: the way the viewer looks
    sh.caps(ex0, y0 + 4, f"{view_id}  ·  {room.get('name')} · wall {view['wall']}  ·  looking {looking}  ·  1:{S}",
            T.INK, role="legend_head", weight=600)

    # points schedule (E5.13)
    xs = ex0 + F.L / S + F.t_right / S + 72
    xs = min(xs, x1 - 66)
    ys = ey0 + 34
    sh.caps(xs, ys, "Points schedule", T.INK, role="legend_head", weight=600)
    cols = [(xs, "ID"), (xs + 19, "Type"), (xs + 46, "h"), (xs + 58, "x")]
    for cx, hd in cols:
        sh.caps(cx, ys + 6, hd, T.GREY)
    sh.rule(xs, x1, ys + 7.6, T.INK)
    y = ys + 11.5
    for p in pts:
        kind = p["kind"].replace("_", " ")
        sh.text(cols[0][0], y, p["id"], sans("dim", 600), T.INK)
        sh.text(cols[1][0], y, kind[:16] + (" " + p["ip"] if p.get("ip") else ""), sans("dim"), T.INK)
        sh.text(cols[2][0] + 8, y, str(p["z"]), sans("dim"), T.INK, ha="right")
        sh.text(cols[3][0] + 8, y, str(round(p["x"])), sans("dim"), T.INK, ha="right")
        sh.rule(xs, x1, y + 1.4)
        y += 3.6

    # finish key with swatches (E5.8)
    fin = {f["code"]: f for f in m.finishes}
    used = []
    for c in codes:
        for part in c.replace("·", " ").split():
            if part in fin and part not in used:
                used.append(part)
    kx, ky = x0, y1 - 22
    sh.caps(kx, ky - 3, "Finish key", T.INK, role="legend_head", weight=600)
    floor = next((fl for fl in m.floors if fl["room"] == room["id"]), {})
    for i, code in enumerate(used):
        f = fin[code]
        sx = kx + i * 46
        arr = TX.floor_texture(f, floor if code == floor.get("finish") else {"pattern": "straight",
                               "module": [_tile_size(f.get("name")) or (600, 600)][0]}, (0, 0, 900, 600), 0.5, seed=3)
        if f.get("kind") in ("paint", "fabric", "laminate"):
            import numpy as np
            tone = {"paint": TX.mix(T.PAPER, T.LIGHT, 0.4), "fabric": TX.palette()["fabric"],
                    "laminate": TX.palette()["joinery"]}[f["kind"]]
            arr = np.ones((60, 90, 3)) * tone
        sh.image(arr, sx, ky, sx + 12, ky + 8, z=4)
        sh.swatch(sx, ky, 12, 8, edge=T.INK, lw=LW_HAIR)
        sh.text(sx + 14, ky + 2.6, code, sans("dim", 700), T.INK)
        for k, ln in enumerate([f["name"][:26], f["name"][26:52]]):
            if ln:
                sh.text(sx + 14, ky + 5.4 + k * 2.4, ln.strip(), sans("dim"), T.GREY)

    # strip: key plan, legend, bubbles
    fr.head("Key plan")
    fr.y, kscale = key_plan(sh, m, F, T.STRIP_X, fr.y - 1, T.RIGHT - T.STRIP_X)
    sh.text(T.STRIP_X, fr.y + 1.5, f"1:{kscale} · thick line = this wall, ○ = left corner", sans("dim"), T.GREY)
    fr.y += 6
    fr.rule()
    fr.legend([
        ("Socket / plate, true size", lambda x, y, w, h: sh.swatch(x + 2, y - 0.4, 3.4, 3.4, fill=T.PAPER, edge=T.INK)),
        ("Hot · Cold · Drain", lambda x, y, w, h: [sh.circle(x + 1.2 + k * 2.6, y + h / 2, 0.95, edge=c_, fill=c_)
                                                   for k, c_ in enumerate((T.FLAG, T.BLUE, T.GREY))]),
        ("Wiring drop from ceiling", lambda x, y, w, h: sh.line([(x + 3, y - 0.5), (x + 3, y + h + 0.5)], T.FLAG,
                                                                LW_THIN)),
        ("Shutter swing, apex at hinge", lambda x, y, w, h: sh.line([(x + w, y), (x, y + h / 2), (x + w, y + h)],
                                                                    T.GREY, LW_HAIR, (0, (2.0, 1.2)))),
        ("Detail bubble → DT sheet", lambda x, y, w, h: (sh.circle(x + 2.5, y + h / 2, 2.2, edge=T.INK, fill=T.PAPER),
                                                        sh.line([(x + 0.3, y + h / 2), (x + 4.7, y + h / 2)], T.INK,
                                                                LW_HAIR))),
    ])
    fr.head("Detail references")
    fr.lines([("1–3", "DT-01: 1 cove, 2 wall panel with LED reveal, 3 skirting", None),
              ("4–6", "DT-02: 4 concealed flush door, 5 worktop + gola + base unit, 6 wardrobe", None),
              ("", "Heights are mm above FFL to the device centre; x from the left corner.", None)], indent=9)
    return sh

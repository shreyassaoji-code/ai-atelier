"""Which walls and which camera views a room board shows (STANDARDS §2a).

Pure geometry, no drawing and no Blender: used by the room board (atelier/room_board.py)
and by the renderer (atelier/render.py), so both always agree.

Data first: a `views[]` entry of kind "room_board" for the room may name the two walls
(`walls: [id, id]`), and `cameras[]` entries for the room are used before any automatic
camera. Everything else here is a rule, written once.
"""
from __future__ import annotations

import math

from shapely.geometry import box, LineString, Point

from atelier import geom

BOARD_TYPES = ("living", "living_dining", "kitchen", "bedroom", "master_bedroom")
MIN_FACE = 600            # faces shorter than this are junction slivers, never an elevation
NEAR_WALL = 700           # furniture within this of a face "belongs" to that wall
CAM = dict(eye_z=1350, lens=20, corner=520, clear=250, step=200, reach=1600, look=3000, near=1300)


def octant(vx, vy):
    deg = math.degrees(math.atan2(vx, vy)) % 360
    return ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[int(((deg + 22.5) % 360) // 45)]


def board_rooms(m):
    return [r for r in m.rooms if r.get("type") in BOARD_TYPES]


def _faces(m, room):
    """Longest face per wall in the room (a wall can touch a room in two stretches)."""
    best = {}
    for f in geom.room_faces(room, m.walls):
        if f.length >= MIN_FACE and (f.wall not in best or f.length > best[f.wall].length):
            best[f.wall] = f
    return list(best.values())


def wall_content(m, room, f):
    """What stands on a face: joinery length, feature area, openings, furniture against it."""
    line = LineString([f.a, f.b])
    j_len = sum(j["width"] for j in m.joinery if j["room"] == room["id"] and j["wall"] == f.wall)
    feat = sum(w["width"] * (w["z1"] - w["z0"]) / 1e6 for w in m.wall_features
               if w["room"] == room["id"] and w["wall"] == f.wall)
    ops = [o for o in m.openings_on(f.wall)
           if line.distance(Point(geom.point_on_wall(m.wall(f.wall), o["offset"] + o["width"] / 2))) < 300]
    furn = [x for x in m.furniture if x["room"] == room["id"] and x.get("kind") != "rug"
            and geom.furniture_polygon(x).distance(line) <= NEAR_WALL]
    return dict(joinery=j_len, feature=feat, openings=len(ops),
                windows=sum(o["kind"] in ("window", "sliding_door") for o in ops), furniture=len(furn))


def _score(c):
    return c["joinery"] / 1000 * 3 + c["feature"] * 1.5 + c["windows"] * 1.2 + c["openings"] * 0.6 + c["furniture"]


def is_blank(c):
    return not (c["joinery"] or c["feature"] or c["openings"] or c["furniture"])


def key_walls(m, room):
    """The two walls the board elevates, best first. Kitchens: the first backs joinery.
    Never a blank wall (no joinery, feature, opening or furniture)."""
    faces = _faces(m, room)
    named = next((v.get("walls") for v in m.views if v.get("kind") == "room_board" and v.get("room") == room["id"]
                  and v.get("walls")), None)
    chosen = []
    if named:                                            # data first (a camera wall may name only one)
        by = {f.wall: f for f in faces}
        chosen = [by[w] for w in named if w in by][:2]
        if len(chosen) == 2:
            return chosen
    scored = [(f, wall_content(m, room, f)) for f in faces]
    scored = [(f, c) for f, c in scored if not is_blank(c)]
    if room.get("type") == "kitchen":
        jw = sorted([t for t in scored if t[1]["joinery"]], key=lambda t: (-t[1]["joinery"], -t[0].length))
        rest = sorted([t for t in scored if t not in jw], key=lambda t: -_score(t[1]))
        order = jw + rest
    else:
        order = sorted(scored, key=lambda t: (-_score(t[1]), -t[0].length))
    return (chosen + [f for f, _ in order if f not in chosen])[:2]


def elevation_view(room, f, k):
    return {"id": f"{room['id']}-{k}", "kind": "elevation", "room": room["id"], "wall": f.wall, "scale": 50}


# ------------------------------------------------------------------ cameras
WALL_NEAR = 1600          # a wall this close, well inside the frame, fills a side of the picture
PENDANT_CLEAR = 700       # no eye within this of a pendant hanging near eye level: it would fill the lens
PENDANT = 9999
WALL = 9998               # obstacle height marking a wall sample: only counts when it is really close            # obstacle height marking a pendant: its penalty adds to the others (it glares)


def _obstacles(m, room):
    out = [(geom.furniture_polygon(x), x["size"][2] if len(x["size"]) > 2 else 900)
           for x in m.furniture if x["room"] == room["id"] and x.get("kind") != "rug"]
    out += [(geom.joinery_polygon(j, m.wall(j["wall"]), room), j.get("z", 0) + j.get("height", 850))
            for j in m.joinery if j["room"] == room["id"]]
    edge = geom.room_polygon(room).exterior            # bare wall right in front of the lens fills the frame
    for k in range(0, int(edge.length), 200):
        q = edge.interpolate(k)
        out.append((box(q.x - 1, q.y - 1, q.x + 1, q.y + 1), WALL))
    for c in m.ceilings:                               # pendants hanging into eye level fill the lens up close
        if c["room"] == room["id"]:
            for l_ in c.get("lights", []):
                if l_.get("kind") == "pendant" and l_.get("z", 2000) < CAM["eye_z"] + 600:
                    out.append((Point(l_["at"]).buffer(l_.get("d", 200) / 2 + 50), PENDANT))
    return out


def _blockers(m, room):
    out = [geom.furniture_polygon(x) for x in list(m.furniture) + list(m.sanitary)
           if x["room"] == room["id"] and x.get("kind") != "rug"]
    out += [geom.joinery_polygon(j, m.wall(j["wall"]), room) for j in m.joinery if j["room"] == room["id"]]
    out += [Point(l_["at"]).buffer(PENDANT_CLEAR - 150) for c in m.ceilings if c["room"] == room["id"]
            for l_ in c.get("lights", []) if l_.get("kind") == "pendant" and l_.get("z", 2000) < CAM["eye_z"] + 600]
    return out                                         # (eye positions keep 150 from these)


def _targets(m, room):
    """Things worth seeing, with weights: joinery and feature walls first, then furniture and windows."""
    t = []
    for j in m.joinery:
        if j["room"] == room["id"]:
            c = geom.joinery_polygon(j, m.wall(j["wall"]), room).centroid
            t.append(((c.x, c.y), 3.0))
    for w in m.wall_features:
        if w["room"] == room["id"]:
            t.append((geom.point_on_wall(m.wall(w["wall"]), w["offset"] + w["width"] / 2), 3.0))
    for x in m.furniture:
        if x["room"] == room["id"]:
            t.append((tuple(x["at"]), 0.4 if x.get("kind") == "rug" else 1.0))
    rp = geom.room_polygon(room).buffer(300)
    for o in m.openings:
        if o["kind"] in ("window", "sliding_door"):
            p = geom.point_on_wall(m.wall(o["wall"]), o["offset"] + o["width"] / 2)
            if rp.contains(Point(p)):
                t.append((p, 1.2))
    return t


def _near_penalty(eye, yaw, lens, obstacles):
    """Things closer than NEAR_CAM to the lens inside the view: tall ones block the frame, low ones crowd it."""
    half = math.atan(18 / lens)
    pen = glare = 0.0
    for g, h in obstacles:
        for x, y in list(g.exterior.coords)[:-1] + [(g.centroid.x, g.centroid.y)]:
            dx, dy = x - eye[0], y - eye[1]
            d = math.hypot(dx, dy)
            a = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
            if h == WALL and (d > WALL_NEAR or abs(a) > half * 0.8):
                continue
            if d < CAM["near"] and abs(a) <= half:
                v = (3.0 if h > 1000 else 1.6) * (1 - d / CAM["near"]) + 0.8
                if h == PENDANT:
                    glare = max(glare, v)
                else:
                    pen = max(pen, v)
    return pen + glare


def _view_score(poly, eye, yaw, targets, lens, obstacles=()):
    half = math.atan(18 / lens) * 0.85
    s = -_near_penalty(eye, yaw, lens, obstacles)
    for (x, y), w in targets:
        dx, dy = x - eye[0], y - eye[1]
        d = math.hypot(dx, dy)
        if d < 900:
            continue
        a = math.atan2(dy, dx) - yaw
        a = (a + math.pi) % (2 * math.pi) - math.pi
        if abs(a) <= half:
            s += w
    ray = LineString([eye, (eye[0] + math.cos(yaw) * 15000, eye[1] + math.sin(yaw) * 15000)])
    free = ray.intersection(poly)
    seg = free.geoms[0] if hasattr(free, "geoms") else free
    return s + min(seg.length, 7000) / 2500


def _eye_options(v, bx, by, d0, inner, blk):
    out = []
    d = d0
    while d <= CAM["reach"]:
        e = (v[0] + bx * d, v[1] + by * d)
        if inner.contains(Point(e)) and not any(b.buffer(150).contains(Point(e)) for b in blk):
            out.append(e)
        d += 300
    return out or [(v[0] + bx * d0, v[1] + by * d0)]


def checked(m, cam):
    """The camera as rendered: atelier.render3d.check_camera's fix applied (moved / blocked recorded),
    so plans, boards, the check and the renderer all use one position."""
    from atelier.render3d import check_camera
    c2, mv, why = check_camera(m, cam)
    if mv is None:
        return dict(cam, blocked=why)
    return dict(c2, moved=list(mv), moved_why=why) if mv else c2


def room_cameras(m, room, n=3):
    """n eye-level cameras: data cameras first, then the best corners (level view, so verticals stay straight)."""
    out = [dict(c, auto=False) for c in m.cameras if c.get("room") == room["id"]][:n]
    poly = geom.room_polygon(room)
    inner = poly.buffer(-CAM["clear"])
    blk = _blockers(m, room)
    targets = _targets(m, room)
    obstacles = _obstacles(m, room)
    pts = list(poly.exterior.coords)[:-1]
    cands = []
    for i, v in enumerate(pts):
        p, q = pts[i - 1], pts[(i + 1) % len(pts)]
        ax_, ay_ = p[0] - v[0], p[1] - v[1]
        bx_, by_ = q[0] - v[0], q[1] - v[1]
        if ax_ * by_ - ay_ * bx_ > 0:               # CCW polygon: reflex vertex, no corner view
            continue
        la, lb = math.hypot(ax_, ay_), math.hypot(bx_, by_)
        bx, by = ax_ / la + bx_ / lb, ay_ / la + by_ / lb
        lbis = math.hypot(bx, by)
        bx, by = bx / lbis, by / lbis
        d = CAM["corner"]
        eye = None
        while d <= CAM["reach"]:
            e = (v[0] + bx * d, v[1] + by * d)
            if inner.contains(Point(e)) and not any(b.buffer(150).contains(Point(e)) for b in blk):
                eye = e
                break
            d += CAM["step"]
        if eye is None:
            continue
        base = math.atan2(by, bx)
        best = None
        for e in _eye_options(v, bx, by, d, inner, blk):          # a step further in can clear a near object
            for k_ in (-25, -15, -5, 5, 15, 25, 0):
                a = base + math.radians(k_)
                sc = _view_score(poly, e, a, targets, CAM["lens"], obstacles)
                if best is None or sc > best[0]:
                    best = (sc, e, a)
        sc, eye, yaw = best
        cands.append((sc, v, eye, yaw))
    bb = poly.bounds
    k = len(out)
    picked = []
    while cands and len(out) < n:                 # best first, then views that look a different way
        def eff(t):
            pen = 1.0
            for _, _, e2, y2 in picked:
                dy = abs((t[3] - y2 + math.pi) % (2 * math.pi) - math.pi)
                if dy < math.radians(50):
                    pen *= 0.45
            return t[0] * pen
        best = max(cands, key=eff)
        cands.remove(best)
        picked.append(best)
        sc, v, eye, yaw = best
        k += 1
        tx, ty = eye[0] + math.cos(yaw) * CAM["look"], eye[1] + math.sin(yaw) * CAM["look"]
        out.append({"id": f"V-{room['id']}-{k}", "room": room["id"], "eye": [round(eye[0]), round(eye[1]), CAM["eye_z"]],
                    "target": [round(tx), round(ty), CAM["eye_z"]], "lens": CAM["lens"], "auto": True,
                    "corner": octant((v[0] - (bb[0] + bb[2]) / 2) / (bb[2] - bb[0]), (v[1] - (bb[1] + bb[3]) / 2) / (bb[3] - bb[1])),
                    "looking": octant(math.cos(yaw), math.sin(yaw))})
    return [checked(m, c) for c in out]


def feature_camera(m, g):
    """A level camera facing a feature wall square-on from across the room (Feature wall sheet)."""
    from atelier import features as FT
    L, P = FT.wall_u(m, g)
    poly = geom.room_polygon(m.room(g["room"]))
    a, b = P(0), P(L)
    vx, vy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    nx, ny = vy, -vx                                         # into the room
    u0 = min(it["from"] for it in g["items"])
    u1 = max(it["to"] for it in g["items"])
    mid = P((u0 + u1) / 2)                                   # centre on the feature, not the whole wall
    depth = LineString([mid, (mid[0] + nx * 20000, mid[1] + ny * 20000)]).intersection(poly).length
    d = max(1200, min(depth - 350, 4200))
    lens = 20 if (u1 - u0) > 1.35 * d else 24
    eye = (mid[0] + nx * d, mid[1] + ny * d)
    return checked(m, {"id": f"V-{g['id']}", "room": g["room"], "eye": [round(eye[0]), round(eye[1]), CAM["eye_z"]],
            "target": [round(mid[0]), round(mid[1]), CAM["eye_z"]], "lens": lens, "auto": True,
            "feature": g["id"], "looking": octant(-nx, -ny)})

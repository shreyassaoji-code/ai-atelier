"""Shapely helpers. Plan mm, origin bottom-left, x east, y north (agents/SCHEMA.md)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

ARC_STEPS = 24
CARDINAL = {"N": 0, "E": 90, "S": 180, "W": 270}


# ------------------------------------------------------------------ vectors
def unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return dx / L, dy / L, L


def left_normal(ux, uy):
    return -uy, ux  # y-up plan: left of direction (ux, uy)


def compass_to_vec(facing) -> tuple[float, float]:
    """'N'/'E'/'S'/'W' or compass degrees (0 = N, 90 = E) -> unit vector (x east, y north)."""
    deg = CARDINAL[facing] if isinstance(facing, str) else float(facing)
    r = math.radians(deg)
    return math.sin(r), math.cos(r)


def vec_to_cardinal(vx, vy) -> str:
    deg = math.degrees(math.atan2(vx, vy)) % 360
    return "NESW"[int(((deg + 45) % 360) // 90)]


# ------------------------------------------------------------------ walls
def wall_offsets(wall) -> tuple[float, float]:
    """Signed distances (left-normal) of the wall's two faces from its line a->b."""
    t = wall["t"]
    return {"centre": (-t / 2, t / 2), "left": (0, t), "right": (-t, 0)}[wall.get("align", "centre")]


def wall_polygon(wall) -> Polygon:
    """Wall body: exactly from a to b (no end extension), thickness by align."""
    a, b = wall["a"], wall["b"]
    ux, uy, _ = unit(a, b)
    nx, ny = left_normal(ux, uy)
    lo, hi = wall_offsets(wall)
    pts = [(a[0] + nx * lo, a[1] + ny * lo), (b[0] + nx * lo, b[1] + ny * lo),
           (b[0] + nx * hi, b[1] + ny * hi), (a[0] + nx * hi, a[1] + ny * hi)]
    return orient(Polygon(pts))


def wall_length(wall) -> float:
    return unit(wall["a"], wall["b"])[2]


def point_on_wall(wall, offset, side_offset=0.0):
    a = wall["a"]
    ux, uy, _ = unit(a, wall["b"])
    nx, ny = left_normal(ux, uy)
    return (a[0] + ux * offset + nx * side_offset, a[1] + uy * offset + ny * side_offset)


def face_offset(wall, side: str) -> float:
    """Signed left-normal offset of the face on `side` ('left' or 'right')."""
    lo, hi = wall_offsets(wall)
    return hi if side == "left" else lo


def walls_union(walls):
    return unary_union([wall_polygon(w) for w in walls])


# ------------------------------------------------------------------ openings
def opening_polygon(wall, op, extra=1.0) -> Polygon:
    """The cut through the wall body (slightly over-thick so it cuts cleanly)."""
    lo, hi = wall_offsets(wall)
    o0, o1 = op["offset"], op["offset"] + op["width"]
    pts = [point_on_wall(wall, o0, lo - extra), point_on_wall(wall, o1, lo - extra),
           point_on_wall(wall, o1, hi + extra), point_on_wall(wall, o0, hi + extra)]
    return orient(Polygon(pts))


def cut_walls(walls, openings):
    """Walls union minus all opening cuts."""
    by_id = {w["id"]: w for w in walls}
    cuts = [opening_polygon(by_id[o["wall"]], o) for o in openings if o["wall"] in by_id]
    return walls_union(walls).difference(unary_union(cuts)) if cuts else walls_union(walls)


def hinge_point(wall, op):
    side = op["swing"]
    off = op["offset"] if op["hinge"] in ("start", "both") else op["offset"] + op["width"]
    return point_on_wall(wall, off, face_offset(wall, side))


def swing_polygon(wall, op) -> Polygon | None:
    """Area swept by the leaf (quarter circle per leaf) on the swing side, or None."""
    if op.get("swing", "none") == "none" or op.get("hinge", "none") == "none":
        return None
    a = wall["a"]
    ux, uy, _ = unit(a, wall["b"])
    nx, ny = left_normal(ux, uy)
    side = op["swing"]
    sgn = 1 if side == "left" else -1
    f = face_offset(wall, side)
    leaves = []
    if op["hinge"] == "both":
        half = op["width"] / 2
        leaves = [(op["offset"], +1, half), (op["offset"] + op["width"], -1, half)]
    elif op["hinge"] == "start":
        leaves = [(op["offset"], +1, op["width"])]
    else:
        leaves = [(op["offset"] + op["width"], -1, op["width"])]
    polys = []
    for off, along, r in leaves:
        hx, hy = point_on_wall(wall, off, f)
        # closed leaf lies along the wall (direction along*u); open leaf along sgn*n
        a0 = math.atan2(uy * along, ux * along)
        a1 = math.atan2(ny * sgn, nx * sgn)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        pts = [(hx, hy)] + [(hx + r * math.cos(a0 + da * i / ARC_STEPS),
                             hy + r * math.sin(a0 + da * i / ARC_STEPS)) for i in range(ARC_STEPS + 1)]
        polys.append(Polygon(pts))
    return unary_union(polys)


# ------------------------------------------------------------------ rooms
def room_polygon(room) -> Polygon:
    return orient(Polygon(room["poly"]), sign=1.0)  # counter-clockwise


def label_point(room):
    """Where a room's label goes: the centroid when it is (nearly) as deep inside
    the room as the pole of inaccessibility, otherwise the pole (L-shapes)."""
    from shapely.ops import polylabel
    poly = room_polygon(room)
    pole = polylabel(poly, tolerance=10)
    c = poly.centroid
    depth = lambda p: poly.exterior.distance(p) if poly.contains(p) else -1  # noqa: E731
    return c if depth(c) >= 0.9 * depth(pole) else pole


def room_area_m2(room) -> float:
    return room_polygon(room).area / 1e6


def room_at(point, rooms):
    """id of the room containing point (x, y), or None."""
    p = Point(point)
    for r in rooms:
        if room_polygon(r).buffer(0.5).contains(p):
            return r["id"]
    return None


@dataclass
class Edge:
    n: int            # 1-based, counter-clockwise
    a: tuple
    b: tuple
    length: float
    facing: str       # cardinal direction the wall face looks into the room from (inward normal)
    wall: str | None  # id of the wall whose face this edge lies on


def room_edges(room, walls=()) -> list[Edge]:
    """Edges numbered 1.. counter-clockwise, edge 1 starting at the south-west-most
    vertex (min y, then min x). Each edge is matched to the wall whose face it lies on."""
    pts = list(room_polygon(room).exterior.coords)[:-1]
    k = min(range(len(pts)), key=lambda i: (pts[i][1], pts[i][0]))
    pts = pts[k:] + pts[:k]
    edges = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        ux, uy, L = unit(a, b)
        nx, ny = left_normal(ux, uy)  # CCW polygon: left normal points inside
        seg = LineString([a, b])
        host = None
        for w in walls:
            if wall_polygon(w).buffer(1).contains(seg):
                host = w["id"]
                break
        edges.append(Edge(i + 1, a, b, L, vec_to_cardinal(nx, ny), host))
    return edges


def room_side_of_wall(wall, room) -> str | None:
    """'left' or 'right': which side of the wall faces the room."""
    L = wall_length(wall)
    rp = room_polygon(room).buffer(2)
    for side in ("left", "right"):
        f = face_offset(wall, side)
        f += 5 if side == "left" else -5
        for frac in (0.5, 0.25, 0.75, 0.1, 0.9):
            if rp.contains(Point(point_on_wall(wall, L * frac, f))):
                return side
    return None


# ------------------------------------------------------------------ furniture / joinery
def furniture_polygon(f) -> Polygon:
    """Box footprint: width across the front, depth along the facing direction."""
    (cx, cy), (w, d) = f["at"], f["size"][:2]
    fx, fy = compass_to_vec(f.get("facing", "N"))
    rx, ry = fy, -fx  # right of facing
    hw, hd = w / 2, d / 2
    pts = [(cx + sx * hw * rx + sy * hd * fx, cy + sx * hw * ry + sy * hd * fy)
           for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return orient(Polygon(pts))


def joinery_polygon(j, wall, room) -> Polygon:
    side = room_side_of_wall(wall, room) or "left"
    f = face_offset(wall, side)
    d = j["depth"] * (1 if side == "left" else -1)
    o0, o1 = j["offset"], j["offset"] + j["width"]
    pts = [point_on_wall(wall, o0, f), point_on_wall(wall, o1, f),
           point_on_wall(wall, o1, f + d), point_on_wall(wall, o0, f + d)]
    return orient(Polygon(pts))


def is_parallel(w1, w2, tol_deg=1.0) -> bool:
    a1 = math.atan2(w1["b"][1] - w1["a"][1], w1["b"][0] - w1["a"][0])
    a2 = math.atan2(w2["b"][1] - w2["a"][1], w2["b"][0] - w2["a"][0])
    d = abs((math.degrees(a1 - a2) + 90) % 180 - 90)
    return d < tol_deg


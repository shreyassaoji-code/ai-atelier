"""White-model 3D frames (Blender as a Python module, headless).

    python -m atelier.render3d projects/<name>              axonometric + corner views of every board room
    python -m atelier.render3d projects/<name> --features   feature-wall views + cameras named in the design
    options: --engine workbench (default, fast) | eevee | cycles · --size N · --force · --camera ID

Geometry is the one model of `atelier.render.Scene`, built from the resolved data: walls with the openings
cut, floors with their flooring images, tray ceilings with cove LED strips, joinery with shutter / drawer
gaps, furniture, sanitary and every feature-wall item. This module re-dresses it as an architectural white
model on warm paper: white walls, oak and linen accents, emissive coves, dark cut tops on the axonometrics.

Frames: out/renders/ax_<room>.png, cam_<room>-<n>.png, fw_<feature>.png, fw_<view>.png, listed in
renders.json (cache) and cameras.json (agents/visualiser.md). Every camera is checked against the
walls before it is used; an eye inside a wall, a fixture or too close to a surface is pulled back
towards its target, and the move is printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point

from atelier import geom
from atelier import texture as TX
from atelier import theme as T
from atelier import views3d as V3
from atelier.model import load
from atelier.render import Scene, lin

W3 = dict(wb_light="FLAT", wb_studio="Default", size=1000, cut=1500, axo_el=48, axo_az=225, margin=700, near=600, close=1300, close_rays=1, step=100, samples=32)
FLOORS = ("floor-", "threshold", "ground")
ABOVE = ("ceiling", "globe", "bulb", "track", "led")    # ceilings and hanging lights: never in an axonometric
SMOOTH = ("globe", "bulb", "cushion", "shade", "pot", "ceramic", "leaf")   # curved forms, shaded smooth


# ------------------------------------------------------------------ the white-model palette
def style(key, sp):
    """Scene material spec -> white-model spec (colour + roughness, emission kept)."""
    white = TX.mix(T.PAPER, T.LIGHT, 0.12)
    oak = TX.mix(T.AMBER, T.PAPER, 0.55)
    linen = TX.mix(T.LIGHT, T.MID, 0.35)
    dark = TX.mix(T.INK, T.GREY, 0.25)
    out = {"rough": sp.get("rough", 0.7)}
    if key == "ground":                                 # the land under the model reads as paper
        out.update(color=TX.mix(T.PAPER, T.LIGHT, 0.15), rough=1.0)
    elif "emit" in sp:                                  # coves, bulbs, globes, lamp shades
        out.update(emit=sp["emit"], strength=sp.get("strength", 1.0), color=sp.get("color", sp["emit"]))
    elif key.startswith(FLOORS):
        out.update(color=sp["color"], image=sp.get("image"), plane=sp.get("plane"))
    elif sp.get("glass"):
        out.update(color=TX.mix(T.BLUE, T.PAPER, 0.8), glass=True)
    elif sp.get("grain") or key in ("oak", "skirting", "wood"):
        tone = np.asarray(sp["color"])
        out.update(color=oak if tone.mean() > 0.55 else TX.mix(oak, T.INK, 0.35), rough=0.55)
    elif sp.get("sheen") or key in ("rug", "rug_border"):
        out.update(color=TX.mix(linen, T.MID, 0.4) if key.startswith("rug") else linen, rough=0.95)
    elif key in ("leaf",):
        out.update(color=TX.mix(T.GREEN, T.PAPER, 0.55))
    elif sp.get("metal", 0) > 0.5 or key in ("frame", "track", "hob", "niche_back", "shadow") or key.startswith("mirror"):
        out.update(color=dark, rough=0.3 if key.startswith("mirror") else 0.5)
    else:
        out.update(color=white, rough=0.85)
    return out


# ------------------------------------------------------------------ cameras
def axo_camera(m, room):
    """Orthographic view from the SW, over walls cut at W3['cut'], framed on the room."""
    poly = geom.room_polygon(room)
    c = poly.centroid
    az, el = math.radians(W3["axo_az"]), math.radians(W3["axo_el"])
    d = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))   # from target to eye
    right = (-math.sin(az), math.cos(az), 0)
    up = (-math.sin(el) * math.cos(az), -math.sin(el) * math.sin(az), math.cos(el))
    up = tuple(-x for x in up) if up[2] < 0 else up
    pts = [(x, y, z) for x, y in poly.buffer(W3["margin"], join_style=2).exterior.coords for z in (0, W3["cut"])]
    us = [p[0] * right[0] + p[1] * right[1] for p in pts]
    vs = [p[0] * up[0] + p[1] * up[1] + p[2] * up[2] for p in pts]
    scale = max(max(us) - min(us), max(vs) - min(vs)) * 1.04
    # aim at the middle of the projected box, not the centroid, so the room sits centred in the frame
    du = (max(us) + min(us)) / 2 - (c.x * right[0] + c.y * right[1])
    dv = (max(vs) + min(vs)) / 2 - (c.x * up[0] + c.y * up[1])
    tx, ty, tz = c.x + right[0] * du + up[0] * dv, c.y + right[1] * du + up[1] * dv, up[2] * dv
    dist = 30000
    return {"id": f"AX-{room['id']}", "room": room["id"], "kind": "axo", "ortho": round(scale),
            "eye": [round(tx + d[0] * dist), round(ty + d[1] * dist), round(tz + d[2] * dist)],
            "target": [round(tx), round(ty), round(tz)], "cut": W3["cut"], "auto": True}


def _fov_clearance(poly, tall, x, y, yaw, lens):
    """Distances from (x, y) to the first wall or tall object along 13 rays spread across the horizontal
    field of view (outermost 8 % of each side left out: a corner wall grazing the frame edge is fine)."""
    half = math.atan(18 / lens)
    edge = poly.exterior
    out = []
    for k in range(-6, 7):
        a = yaw + half * 0.92 * k / 6
        ray = LineString([(x, y), (x + math.cos(a) * 20000, y + math.sin(a) * 20000)])
        best = 1e9
        for g in [edge] + [t.exterior for t in tall]:
            hit = ray.intersection(g)
            if not hit.is_empty:
                best = min(best, Point(x, y).distance(hit))
        out.append(best)
    return out


def check_camera(m, cam):
    """A perspective eye must be inside the room, clear of fixtures, and see no wall or tall unit
    (≥ 1500 high) closer than W3['near'] anywhere across the frame. If it does, the nearest eye position
    that clears it (forward towards the target or sideways, up to 1.2 m) is used. Returns
    (cam, moved_mm, why) – moved None when nothing clears it."""
    if cam.get("kind") == "axo":
        return cam, 0, ""
    room = m.room(cam["room"])
    poly = geom.room_polygon(room)
    solid = [geom.furniture_polygon(f) for f in m.furniture if f["room"] == room["id"] and f.get("kind") != "rug"]
    solid += [geom.joinery_polygon(j, m.wall(j["wall"]), room) for j in m.joinery if j["room"] == room["id"]]
    solid += [geom.furniture_polygon(s) for s in m.sanitary if s["room"] == room["id"]]
    tall = [geom.joinery_polygon(j, m.wall(j["wall"]), room) for j in m.joinery
            if j["room"] == room["id"] and j.get("z", 0) + j.get("height", 0) >= 1500]
    tall += [geom.furniture_polygon(f) for f in m.furniture
             if f["room"] == room["id"] and len(f["size"]) > 2 and f["size"][2] >= 1500]
    ex, ey, ez = cam["eye"]
    tx, ty = cam["target"][:2]
    yaw = math.atan2(ty - ey, tx - ex)
    ux, uy = math.cos(yaw), math.sin(yaw)
    inner = poly.buffer(-150)

    def bad(x, y, yaw=yaw):
        p = Point(x, y)
        if not inner.contains(p):
            return "outside the room or inside a wall"
        if any(g.buffer(60).contains(p) for g in solid):
            return "inside furniture or joinery"
        ds = _fov_clearance(poly, tall, x, y, yaw, cam.get("lens", 20))
        if min(ds) < W3["near"]:
            return f"a wall or tall unit {min(ds):.0f} from the lens inside the frame"
        close = sum(1 for d in ds if d < W3["close"])
        if close > W3["close_rays"]:
            return f"{close} of 13 sight lines end within {W3['close']} (a near surface fills the frame)"
        return None
    why = bad(ex, ey)
    if why is None:
        return cam, 0, ""
    opts = sorted(((f * W3["step"], s * W3["step"], r) for f in range(0, 13) for s in range(-12, 13)
                   for r in (0, -5, 5, -10, 10, -15, 15)),
                  key=lambda o: math.hypot(o[0], o[1]) + abs(o[2]) * 30)       # 1° of turn ~ 30 mm of move
    for f, s_, r in opts:
        x, y = ex + ux * f - uy * s_, ey + uy * f + ux * s_
        y2 = yaw + math.radians(r)
        if bad(x, y, y2) is None:
            L = math.hypot(tx - ex, ty - ey)
            c = dict(cam, eye=[round(x), round(y), ez],
                     target=[round(x + math.cos(y2) * L), round(y + math.sin(y2) * L), cam["target"][2]])
            if cam.get("looking"):
                c["looking"] = V3.octant(math.cos(y2), math.sin(y2))
            return c, (round(math.hypot(f, s_)), r), why
    return cam, None, why


def cameras(m, features=False):
    out = []
    if features:
        out += [dict(c) for c in __import__("atelier.render", fromlist=["all_cameras"]).all_cameras(m)
                if c.get("feature")]
        out += [dict(c, auto=False) for c in m.cameras]
    else:
        for r in V3.board_rooms(m):
            out.append(axo_camera(m, r))
            out += [c for c in V3.room_cameras(m, r) if c.get("auto", True)]
    return out


# ------------------------------------------------------------------ cache
def key(root: Path, cam, engine):
    h = hashlib.sha1()
    for f in ("survey.json", "design.json", "services.json", "services_overrides.json"):
        p = root / f
        if p.exists():
            h.update(p.read_bytes())
    for mod in ("render.py", "render3d.py", "texture.py", "theme.py", "geom.py"):
        h.update((Path(__file__).parent / mod).read_bytes())
    h.update(json.dumps([cam, engine, W3], sort_keys=True).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ Blender
def _material(bpy, key, sp, engine):
    mt = bpy.data.materials.new(key)
    col = lin(sp.get("color", (0.9, 0.9, 0.9)))
    mt.diffuse_color = col[:3] + ((0.3,) if sp.get("glass") else (1.0,))
    mt.roughness = sp.get("rough", 0.7)
    if engine == "workbench":
        return mt
    if mt.node_tree is None:
        mt.use_nodes = True
    nt = mt.node_tree
    pr = nt.nodes.get("Principled BSDF")
    pr.inputs["Base Color"].default_value = col
    pr.inputs["Roughness"].default_value = sp.get("rough", 0.7)
    if sp.get("glass"):
        pr.inputs["Alpha"].default_value = 0.25
        try:
            mt.surface_render_method = "BLENDED"
        except AttributeError:
            pass
    if "emit" in sp:
        pr.inputs["Emission Color"].default_value = lin(sp["emit"])
        pr.inputs["Emission Strength"].default_value = sp.get("strength", 1.0)
    if sp.get("image"):
        im = nt.nodes.new("ShaderNodeTexImage")
        im.image = bpy.data.images.load(sp["image"])
        uv = nt.nodes.new("ShaderNodeUVMap")
        nt.links.new(uv.outputs[0], im.inputs["Vector"])
        nt.links.new(im.outputs["Color"], pr.inputs["Base Color"])
    return mt


def _image_node_for_workbench(bpy, mt, sp):
    if mt.node_tree is None:
        mt.use_nodes = True
    nt = mt.node_tree
    im = nt.nodes.new("ShaderNodeTexImage")
    im.image = bpy.data.images.load(sp["image"])
    nt.nodes.active = im
    pr = nt.nodes.get("Principled BSDF")
    if pr:
        nt.links.new(im.outputs["Color"], pr.inputs["Base Color"])


def build(sc: Scene, engine):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bsc = bpy.context.scene
    specs = {k: style(k, sp) for k, sp in sc.mats.items()}
    mats = {}
    for k, sp in specs.items():
        mats[k] = _material(bpy, k, sp, engine)
        if engine == "workbench" and sp.get("image"):
            _image_node_for_workbench(bpy, mats[k], sp)
    cutm = _material(bpy, "cut", {"color": TX.mix(T.INK, T.GREY, 0.08), "rough": 0.9}, engine)
    objs = {}
    for k, (verts, faces) in sc.mesh.parts.items():
        me = bpy.data.meshes.new(k)
        me.from_pydata([(x / 1000, y / 1000, z / 1000) for x, y, z in verts], [], faces)
        me.validate()
        me.materials.append(mats[k])
        sp = specs[k]
        if sp.get("plane"):                              # floor images: planar UVs over the room's bounds
            b = sp["plane"]
            uvl = me.uv_layers.new(name="UV")
            for poly in me.polygons:
                for li in poly.loop_indices:
                    x, y, _ = me.vertices[me.loops[li].vertex_index].co
                    uvl.data[li].uv = ((x * 1000 - b[0]) / (b[2] - b[0]), (y * 1000 - b[1]) / (b[3] - b[1]))
        if k.startswith(SMOOTH):
            for poly in me.polygons:
                poly.use_smooth = True
        ob = bpy.data.objects.new(k, me)
        bsc.collection.objects.link(ob)
        objs[k] = ob
    paper = lin(TX.mix(T.PAPER, T.LIGHT, 0.15))
    wd = bpy.data.worlds.new("paper")
    wd.color = paper[:3]
    bsc.world = wd
    if engine != "workbench":
        if wd.node_tree is None:
            wd.use_nodes = True
        bg = wd.node_tree.nodes.get("Background")
        bg.inputs["Color"].default_value = paper
        bg.inputs["Strength"].default_value = 0.9
        sun = bpy.data.lights.new("sun", "SUN")
        sun.energy = 2.2
        sun.angle = math.radians(12)                     # soft shadows
        sun.color = lin(TX.mix(T.PAPER, T.AMBER, 0.15))[:3]
        so = bpy.data.objects.new("sun", sun)
        so.rotation_euler = (math.radians(50), 0, math.radians(315))
        bsc.collection.objects.link(so)
        warm = lin(TX.mix(T.AMBER, T.PAPER, 0.72))[:3]
        for Lt in sc.lights:
            if Lt["kind"] in ("spot", "point"):
                ld = bpy.data.lights.new("l", "SPOT" if Lt["kind"] == "spot" else "POINT")
                ld.energy = Lt["power"]
                ld.color = warm
                ld.shadow_soft_size = 0.1
                if Lt["kind"] == "spot":
                    ld.spot_size = math.radians(110)
                    ld.spot_blend = 0.8
                ob = bpy.data.objects.new("l", ld)
                ob.location = tuple(v / 1000 for v in Lt["at"])
                bsc.collection.objects.link(ob)
    r = bsc.render
    r.image_settings.file_format = "PNG"
    if engine == "workbench":
        r.engine = "BLENDER_WORKBENCH"
        sh = bsc.display.shading
        sh.light = W3["wb_light"]
        sh.use_world_space_lighting = True
        try:
            sh.studio_light = W3["wb_studio"]
        except TypeError:
            pass
        sh.color_type = "TEXTURE"                        # floor images; plain materials show their colour
        sh.show_shadows = True
        sh.shadow_intensity = 0.28
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.cavity_ridge_factor, sh.cavity_valley_factor = 0.0, 1.0
        sh.curvature_ridge_factor, sh.curvature_valley_factor = 0.0, 0.7
        sh.show_object_outline = False
        sh.show_specular_highlight = False
        bsc.display.light_direction = (0.35, -0.45, 0.82)
        bsc.display.shadow_shift = 0.08
        bsc.display.render_aa = "16"
    elif engine == "eevee":
        r.engine = "BLENDER_EEVEE"
        try:
            bsc.eevee.taa_render_samples = W3["samples"]
            bsc.eevee.use_shadows = True
        except AttributeError:
            pass
    else:
        r.engine = "CYCLES"
        bsc.cycles.device = "CPU"
        bsc.cycles.samples = W3["samples"]
        bsc.cycles.use_denoising = True
    try:
        bsc.view_settings.view_transform = "Standard" if engine == "workbench" else "AgX"
    except TypeError:
        pass
    return bpy, bsc, objs, cutm


def section_at(m, z):
    """Plan section at height z: walls (minus openings spanning z) and joinery taller than z."""
    from shapely.ops import unary_union
    full = [w for w in m.walls if w.get("kind") != "parapet" or w.get("height", 1050) > z]
    holes = []
    for o in m.openings:
        w = m.wall(o["wall"])
        lo = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
        hi = o.get("head", m.levels.get("lintel", 2100))
        if lo < z < hi:
            holes.append(geom.opening_polygon(w, o, extra=0))
    walls = geom.walls_union(full).difference(unary_union(holes)) if holes else geom.walls_union(full)
    tall = [geom.joinery_polygon(j, m.wall(j["wall"]), m.room(j["room"])) for j in m.joinery
            if j.get("z", 0) + j.get("height", 0) > z]
    return unary_union([walls] + tall)


def cut_model(bpy, objs, cutm, z, m):
    """Axonometric: slice everything at z, drop what is above, and lay the plan section at z as dark caps."""
    import bmesh
    from atelier.render import Mesh
    zz = z / 1000
    for k, ob in list(objs.items()):
        if k.startswith(FLOORS):
            continue
        me = ob.data
        zs = [v.co.z for v in me.vertices]
        if not zs:
            continue
        if min(zs) >= zz or k.startswith(ABOVE):
            bpy.data.objects.remove(ob)
            del objs[k]
            continue
        if max(zs) <= zz:
            continue
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, zz),
                               plane_no=(0, 0, 1), clear_outer=True)
        bm.to_mesh(me)
        bm.free()
    caps = Mesh()
    caps.prism("cut", section_at(m, z), z, z + 4)
    verts, faces = caps.parts["cut"]
    me = bpy.data.meshes.new("cut")
    me.from_pydata([(x / 1000, y / 1000, zv / 1000) for x, y, zv in verts], [], faces)
    me.validate()
    me.materials.append(cutm)
    ob = bpy.data.objects.new("cut", me)
    bpy.context.scene.collection.objects.link(ob)
    objs["cut"] = ob


def place_camera(bpy, bsc, cam, size):
    import mathutils
    cd = bpy.data.cameras.new(cam["id"])
    ob = bpy.data.objects.new(cam["id"], cd)
    eye = mathutils.Vector([v / 1000 for v in cam["eye"]])
    tgt = mathutils.Vector([v / 1000 for v in cam["target"]])
    ob.location = eye
    if cam.get("kind") == "axo":
        cd.type = "ORTHO"
        cd.ortho_scale = cam["ortho"] / 1000
        cd.clip_start, cd.clip_end = 1, 80
        ob.rotation_euler = (tgt - eye).to_track_quat("-Z", "Y").to_euler()
    else:
        cd.lens = cam.get("lens", 20)
        cd.sensor_width = 36
        cd.sensor_fit = "HORIZONTAL"
        cd.clip_start = 0.05
        yaw = math.atan2(tgt.y - eye.y, tgt.x - eye.x)
        ob.rotation_euler = (math.pi / 2, 0, yaw - math.pi / 2)     # level: verticals stay vertical
    bsc.collection.objects.link(ob)
    bsc.camera = ob
    w, h = cam.get("res", (size, size))
    bsc.render.resolution_x, bsc.render.resolution_y = w, h
    return ob


# ------------------------------------------------------------------ run
def _ref_ratio(m, cam):
    """Feature views take the client's reference image proportions when there is one."""
    if not cam.get("feature"):
        return None
    from atelier.feature_sheet import ref_path
    g = next((x for x in m.feature_walls if x["id"] == cam["feature"]), None)
    p = ref_path(m, g) if g else None
    if not p:
        return None
    from PIL import Image
    w, h = Image.open(p).size
    return w / h


def render(root: Path, features=False, engine="workbench", size=None, force=False, only=None, log=print):
    from atelier.frames import frame_path, write_cameras
    from atelier.render import manifest
    root = Path(root)
    m = load(root)
    sv = json.loads((root / "services.json").read_text())["items"] if (root / "services.json").exists() else []
    size = size or W3["size"]
    cams = []
    for c in cameras(m, features):
        c2 = V3.checked(m, c) if c.get("kind") != "axo" else c
        if c2.get("blocked"):
            log(f"camera ✗ {c['id']}: {c2['blocked']}; no nearby position clears it – skipped")
            continue
        if c2.get("moved"):
            log(f"camera ↺ {c['id']}: {c2['moved_why']}; eye moved {c2['moved'][0]} mm, turned {c2['moved'][1]}°")
        rr = _ref_ratio(m, c2)
        if rr:
            c2["res"] = (size, round(size / rr)) if rr >= 1 else (round(size * rr), size)
        cams.append(c2)
    if only:
        cams = [c for c in cams if c["id"] in only]
    out = root / "out" / "renders"
    out.mkdir(parents=True, exist_ok=True)
    man = manifest(root)
    todo = [c for c in cams if force or man.get(c["id"], {}).get("key") != key(root, c, engine)
            or not frame_path(root, c).exists()]
    if not todo:
        write_cameras(m, root)
        log(f"render3d: {len(cams)} frames current, nothing to do")
        return 0
    sc = Scene(m, root, sv)
    sc.build()
    axo = [c for c in todo if c.get("kind") == "axo"]
    persp = [c for c in todo if c.get("kind") != "axo"]
    for group, cut in ((persp, False), (axo, True)):
        if not group:
            continue
        bpy, bsc, objs, cutm = build(sc, engine)
        if cut:
            cut_model(bpy, objs, cutm, W3["cut"], m)
        for c in group:
            t = time.time()
            place_camera(bpy, bsc, c, size)
            bsc.render.filepath = str(frame_path(root, c))
            bpy.ops.render.render(write_still=True)
            man[c["id"]] = dict(c, key=key(root, c, engine), engine=engine, style="white",
                                seconds=round(time.time() - t, 1), size=size)
            (out / "renders.json").write_text(json.dumps(man, indent=1))
            log(f"render3d ✓ {c['id']} → {frame_path(root, c).name}  {time.time() - t:.1f}s")
    write_cameras(m, root)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.render3d")
    ap.add_argument("project", type=Path, help="a project folder, or a folder of projects")
    ap.add_argument("--features", action="store_true", help="feature-wall views + cameras named in the design")
    ap.add_argument("--engine", choices=("workbench", "eevee", "cycles"), default="workbench")
    ap.add_argument("--size", type=int)
    ap.add_argument("--camera", action="append")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    roots = [a.project] if (a.project / "survey.json").exists() else \
        sorted(p for p in a.project.iterdir() if (p / "survey.json").exists())
    for r in roots:
        render(r, a.features, a.engine, a.size, a.force, a.camera)
    return 0


if __name__ == "__main__":
    sys.exit(main())

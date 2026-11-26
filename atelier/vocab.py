"""The designer brief's vocabulary (agents/designer.md) -> the engine's schema (agents/SCHEMA.md).

Applied once, on load (atelier/model.py), so a design written in either vocabulary draws the
same. Everything the brief adds that the engine does not draw from (palette, style, summary,
switch spots, joinery parts and notes) is kept on the model for the sheets that show it.

Brief                                   Engine
-------------------------------------   ----------------------------------------------------------
ceilings[] type "tray", steps[{band,    z = first level; one step per further level, inset by the
  z|h}], core_h, area, features[],        running band from the room (or from `area`: partial tray,
  tracks[]                                written as step `poly`); light "cove" unless given; features
                                          kind "dome" -> domes[]; tracks -> lights[] kind "track"
ceilings[] type "flat", z|h             z
opening_overrides[{id, …}]              fields replace those of the existing opening (after demolition)
floors[{room, material|finish}]         floors[{room, finish}], pattern/module from the material
floor_materials / finish_materials /    finishes[] (code, kind, name, tone = colour NAME), floor
  feature_materials [{code, …, colour}]   pattern words: tile->straight, planks->plank
wall_finishes [{room, code}] or {room:   rooms[].wall_finish
  code}
joinery materials {role: code} | [codes] finish = shutter / front / first MB code; materials kept
furniture kind "nightstand", "bench"     "bedside", "bench"; headboard / finish / lamp kept as given
views[{room, wall}] (camera wall)        views[{kind: "room_board", room, walls: [wall]}]
notes ["text", …]                        notes[{id: Nn, applies: "all", text}]
"""
from __future__ import annotations

import copy

from shapely.geometry import Polygon

PATTERN = {"tile": "straight", "tiles": "straight", "planks": "plank", "plank": "plank", "straight": "straight",
           "herringbone": "herringbone", "chevron": "chevron", "brick": "brick", "diagonal": "diagonal"}
KIND_ALIAS = {"nightstand": "bedside", "bed_bench": "bench", "ottoman": "bench"}


def _lvl(d, *keys):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def _material_kind(mat):
    if mat.get("kind"):
        return mat["kind"]
    words = f"{mat.get('name', '')} {mat.get('pattern', '')}".lower()
    for kw, kind in (("marble", "stone"), ("granite", "stone"), ("quartz", "stone"), ("stone", "stone"),
                     ("oak", "wood"), ("walnut", "wood"), ("teak", "wood"), ("wood", "wood"), ("plank", "wood"),
                     ("herringbone", "wood"), ("veneer", "veneer"), ("laminate", "laminate"), ("tile", "tile"),
                     ("velvet", "fabric"), ("fabric", "fabric"), ("boucle", "fabric"), ("leather", "fabric"),
                     ("brass", "metal"), ("bronze", "metal"), ("steel", "metal"), ("metal", "metal"),
                     ("mirror", "mirror"), ("glass", "glass"), ("wallpaper", "wallpaper"), ("paint", "paint"),
                     ("lime", "paint"), ("plaster", "paint")):
        if kw in words:
            return kind
    return "paint"


def _finish(mat):
    f = {"code": mat["code"], "kind": _material_kind(mat), "name": mat.get("name") or mat["code"]}
    tone = mat.get("colour") or mat.get("color") or mat.get("tone")
    if tone:
        f["tone"] = tone
    for k in ("maker", "ref", "flag", "note"):
        if k in mat:
            f[k] = mat[k]
    return f


def _ceiling(c, room_poly):
    if not c.get("type"):
        return c                                            # already engine form
    out = {k: v for k, v in c.items() if k not in ("type", "steps", "core_h", "area", "features", "tracks", "h")}
    out["room"] = c["room"]
    if c["type"] == "flat":
        out["z"] = _lvl(c, "z", "h")
        lights = list(c.get("lights", [])) + [{"kind": "track", "path": t["path"] if isinstance(t, dict) else t}
                                               for t in c.get("tracks", [])]
        if lights:
            out["lights"] = lights
        return out
    steps = c.get("steps") or []
    levels = [_lvl(s, "z", "h") for s in steps] + ([c["core_h"]] if c.get("core_h") is not None else [])
    bands = [s.get("band", 450) for s in steps]
    base = _lvl(c, "z", "h") if _lvl(c, "z", "h") is not None else (levels[0] if levels else None)
    out["z"] = base
    area = Polygon(c["area"]) if c.get("area") else None
    eng, prev, cum = [], base, 0
    for k, z in enumerate(levels):
        if k > 0:
            cum += bands[k - 1]
        if z is None or z == prev:
            continue
        light = (steps[k].get("light") if k < len(steps) else c.get("core_light")) or "cove"
        if area is not None:
            g = area.buffer(-cum, join_style=2) if cum else area
            if g.is_empty:
                break
            eng.append({"poly": [[round(x), round(y)] for x, y in list(g.exterior.coords)[:-1]], "z": z, "light": light})
        else:
            eng.append({"inset": cum, "z": z, "light": light})
        prev = z
    out["steps"] = eng + [s for s in c.get("steps", []) if "inset" in s or "poly" in s]
    domes = list(c.get("domes", []))
    for i, f in enumerate(c.get("features", []), 1):
        if f.get("kind", "dome") == "dome":
            domes.append({"id": f.get("id", f"DM-{c['room']}-{i}"), "at": f["at"], "d": f["d"],
                          "z": _lvl(f, "z", "h", "apex"), "light": f.get("light", "cove")})
    if domes:
        out["domes"] = domes
    lights = list(c.get("lights", []))
    for t in c.get("tracks", []):
        lights.append({"kind": "track", "path": t["path"] if isinstance(t, dict) else t})
    if lights:
        out["lights"] = lights
    return out


def normalise(ds: dict, room_polys: dict) -> tuple[dict, dict]:
    """Return (design in engine schema, extras the engine keeps on the model)."""
    d = copy.deepcopy(ds)
    extras = {k: d.pop(k) for k in ("palette", "style", "summary", "switch_spots", "concept") if k in d}
    # finishes from the brief's material lists
    fins = {f["code"]: f for f in d.get("finishes", [])}
    for key in ("floor_materials", "finish_materials", "feature_materials", "materials"):
        for mat in d.pop(key, []) or []:
            fins.setdefault(mat["code"], _finish(mat))
    d["finishes"] = list(fins.values())
    flo_mats = {f["code"]: f for f in ds.get("floor_materials", [])}
    floors = []
    for fl in d.get("floors", []):
        fl = dict(fl)
        code = fl.pop("material", None) or fl.get("finish")
        fl["finish"] = code
        mat = flo_mats.get(code, {})
        fl.setdefault("pattern", PATTERN.get(str(mat.get("pattern", "straight")).lower(), mat.get("pattern")))
        if mat.get("module"):
            fl.setdefault("module", mat["module"])
        fl["pattern"] = PATTERN.get(str(fl.get("pattern")).lower(), fl.get("pattern"))
        floors.append(fl)
    d["floors"] = floors
    # wall finishes per room
    wf = d.pop("wall_finishes", None)
    if wf:
        pairs = wf.items() if isinstance(wf, dict) else [(x["room"], x.get("code") or x.get("finish")) for x in wf]
        rooms = {r["id"]: r for r in d.setdefault("rooms", [])}
        for rid, code in pairs:
            if rid in rooms:
                rooms[rid]["wall_finish"] = code
            else:
                d["rooms"].append({"id": rid, "wall_finish": code})
    # ceilings
    d["ceilings"] = [_ceiling(c, room_polys.get(c.get("room"))) for c in d.get("ceilings", [])]
    # furniture kinds
    for f in d.get("furniture", []):
        f["kind"] = KIND_ALIAS.get(f.get("kind"), f.get("kind"))
    # joinery materials -> finish
    for j in d.get("joinery", []):
        mats = j.get("materials")
        if mats and not j.get("finish"):
            if isinstance(mats, dict):
                j["finish"] = mats.get("shutter") or mats.get("front") or mats.get("shutters") or next(
                    (v for v in mats.values() if str(v).startswith("MB")), None)
            else:
                j["finish"] = next((v for v in mats if str(v).startswith("MB")), None)
        if j.get("finish") is None:
            j.pop("finish", None)
    # camera walls
    views = []
    for v in d.get("views", []):
        if not v.get("kind") and v.get("room") and v.get("wall"):
            views.append({"id": v.get("id", f"CW-{v['room']}"), "kind": "room_board", "room": v["room"],
                          "walls": [v["wall"]]})
        else:
            views.append(v)
    d["views"] = views
    # notes as plain strings
    notes = []
    for i, n in enumerate(d.get("notes", []), 1):
        notes.append({"id": f"N{i}", "applies": "all", "text": n} if isinstance(n, str) else n)
    d["notes"] = notes
    return d, extras

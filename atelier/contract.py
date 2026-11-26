"""The data contract (agents/SCHEMA.md §0) -> the engine's resolved form.

Agents write the contract: centre-line walls with `type`, openings with `h` and `side`, rooms with
`kind`, furniture and joinery as axis-aligned boxes (`x, y` lower-left, `w` along x, `d` along y),
material dicts, wall finishes and views by room edge, services overrides keyed by system. The engine
draws from its resolved form (wall `kind`, opening `head` / `swing`, room `type`, furniture `at` /
`size`, joinery on a wall with `offset`, …). This module translates on load (atelier/model.py); a
file already in the resolved form passes through untouched, so both read the same.

    python -m atelier.contract export projects/<name> OUT/   write a project's data in contract form

Every guess the translation has to make (a room type read from its name, a unit with no wall
behind it, a contract type the engine does not draw) is reported in `notes` and printed by
`atelier.validate` as W-CONTRACT.
"""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

# ------------------------------------------------------------------ vocabularies
WALL_TYPE = {"external": "external", "partition": "internal", "internal": "internal", "load": "load",
             "parapet": "parapet", "glass": "glass", "half": "half"}
WALL_TYPE_OUT = {"external": "external", "internal": "partition", "partition": "partition", "load": "load",
                 "parapet": "parapet", "glass": "partition", "half": "partition"}
OPENING_KIND = {"door": "door", "entrance": "door", "balcony_door": "door", "double_door": "double_door",
                "sliding_door": "sliding_door", "opening": "opening", "window": "window", "ventilator": "ventilator"}
LEAF = ("door", "double_door")
# room type from its name (first match wins), then from its kind
ROOM_NAME = [("master bed", "master_bedroom"), ("master bath", "bath"), ("master toilet", "toilet"),
             ("living", "living_dining"), ("lounge", "living"), ("drawing", "living"), ("family", "living"),
             ("dining", "dining"), ("kitchen", "kitchen"), ("bed", "bedroom"), ("guest", "bedroom"),
             ("kids", "bedroom"), ("bath", "bath"), ("toilet", "toilet"), ("wc", "toilet"), ("powder", "toilet"),
             ("wash", "utility"), ("utility", "utility"), ("laundry", "utility"), ("balcony", "balcony"),
             ("deck", "balcony"), ("terrace", "balcony"), ("foyer", "foyer"), ("entr", "foyer"),
             ("lobby", "foyer"), ("passage", "passage"), ("corridor", "passage"), ("study", "study"),
             ("office", "study"), ("puja", "puja"), ("pooja", "puja"), ("mandir", "puja"), ("store", "store"),
             ("dress", "dress"), ("walk-in", "dress"), ("wardrobe", "dress"), ("shaft", "shaft"), ("duct", "shaft")]
ROOM_KIND = {"wet": "bath", "kitchen": "kitchen", "circulation": "passage", "balcony": "balcony", "dry": "bedroom"}
ROOM_KIND_OUT = {"bath": "wet", "toilet": "wet", "utility": "wet", "kitchen": "kitchen", "passage": "circulation",
                 "foyer": "circulation", "balcony": "balcony", "shaft": "circulation"}
# furniture: contract type -> (list, engine kind, default height)
FURN = {"bed": ("furniture", "bed", 450), "nightstand": ("furniture", "bedside", 500),
        "sofa": ("furniture", "sofa", 800), "armchair": ("furniture", "armchair", 800),
        "coffee_table": ("furniture", "coffee_table", 400), "side_table": ("furniture", "side_table", 550),
        "dining_table": ("furniture", "dining_table", 750), "chair": ("furniture", "chair", 850),
        "desk": ("furniture", "desk", 750), "rug": ("furniture", "rug", 10), "plant": ("furniture", "plant", 1200),
        "bench": ("furniture", "bench", 450), "tv_unit": ("furniture", "console", 450),
        "island": ("furniture", "other", 900), "fridge": ("furniture", "fridge", 1800),
        "console": ("furniture", "console", 800), "tv": ("furniture", "tv", 700),
        "wc": ("sanitary", "wc", 400), "basin": ("sanitary", "basin", 850), "shower": ("sanitary", "shower", 0),
        "bathtub": ("sanitary", "bathtub", 550), "washing_machine": ("sanitary", "washing_machine", 850)}
FURN_OUT = {"bedside": "nightstand", "console": "console", "other": "other"}
JOINERY_NAME = [("wardrobe", "wardrobe"), ("tv", "tv_unit"), ("media", "tv_unit"), ("vanity", "vanity"),
                ("basin", "vanity"), ("shoe", "shoe_rack"), ("crockery", "crockery"), ("bar", "crockery"),
                ("study", "study_unit"), ("desk", "study_unit"), ("book", "bookshelf"), ("puja", "puja_unit"),
                ("mandir", "puja_unit"), ("tall", "tall_unit"), ("kitchen", "kitchen_base")]
# contract part / module type -> (engine module type, label to add)
MODULE = {"door": ("shutter", None), "drawers": ("drawer", None), "drawer": ("drawer", None), "open": ("open", None),
          "shelf": ("open", None), "sink": ("sink", None), "hob": ("hob", None), "hood": ("appliance", "Hood"),
          "oven": ("appliance", "Oven"), "appliance": ("appliance", None), "fridge": ("appliance", "Fridge"),
          "dishwasher": ("appliance", "Dishwasher"), "panel": ("panel", None), "mirror": ("panel", "Mirror"),
          "none": ("filler", None), "loft": ("loft", None), "glass": ("glass_shutter", None)}
MODULE_OUT = {"shutter": "door", "glass_shutter": "door", "drawer": "drawers", "open": "open", "loft": "door",
              "appliance": "appliance", "sink": "sink", "hob": "hob", "panel": "panel", "filler": "none"}
FEATURE_TYPE = {"plain": "paint"}
# services overrides: contract system -> engine system; contract point type -> engine kind
SYSTEM = {"electrical": "power", "lighting": "lighting", "switches": "switching", "plumbing": "plumbing",
          "hvac": "ac"}
POINT = {"socket": "socket", "socket_double": "double_socket", "socket_usb": "socket_usb", "power16": "socket_16a",
         "socket_ip": "ip44_socket", "tv": "tv_power", "data": "lan", "vdp": "vdp", "db": "db", "exhaust": "exhaust",
         "switch": "switchboard", "downlight": "downlight", "pendant": "pendant", "wall_light": "wall_light",
         "strip": "strip", "fan": "fan", "cold": "cold", "hot": "hot", "drain": "waste", "drain_wc": "soil",
         "mixer": "mixer", "shower_head": "shower_head", "floor_trap": "floor_trap", "ac_indoor": "split",
         "ac_ducted": "supply_grille"}
COMPASS = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}


# ------------------------------------------------------------------ detection
def is_contract_survey(sv):
    return any("type" in w and "kind" not in w for w in sv.get("walls", [])) or \
        any("h" in o and "head" not in o for o in sv.get("openings", [])) or \
        any("kind" in r and "type" not in r for r in sv.get("rooms", [])) or \
        "ceiling_height" in sv.get("levels", {})


def is_contract_design(ds):
    return any("x" in f and "w" in f for f in ds.get("furniture", []) + ds.get("joinery", [])) or \
        isinstance(ds.get("materials"), dict) or isinstance(ds.get("floors"), dict) or \
        isinstance(ds.get("floor_materials"), dict) or \
        any("edge" in v for v in ds.get("views", []) if isinstance(v, dict)) or \
        any("pos" in c for c in ds.get("cameras", []))


# ------------------------------------------------------------------ survey
def _wall(w, notes):
    if "kind" in w:
        return w
    out = {k: v for k, v in w.items() if k not in ("type", "h")}
    out["kind"] = WALL_TYPE.get(w.get("type", "partition"), "internal")
    if w.get("type") not in WALL_TYPE:
        notes.append(f"wall {w.get('id')}: type {w.get('type')!r} read as a partition")
    if w.get("h"):
        out["height"] = w["h"]
    out.setdefault("align", "centre")
    if out.get("flag") is False:
        out.pop("flag")
    return out


def _opening(o, notes):
    if "head" in o and "h" not in o:
        return o
    k = o.get("kind", "door")
    out = {k2: v for k2, v in o.items() if k2 not in ("h", "side")}
    out["kind"] = OPENING_KIND.get(k, "opening")
    if k not in OPENING_KIND:
        notes.append(f"opening {o.get('id')}: kind {k!r} read as an opening")
    if k == "entrance":
        out["entrance"] = True
        out.setdefault("note", "Main entrance")
    if k == "balcony_door":
        out.setdefault("note", "Balcony door")
    sill = o.get("sill", 0) or 0
    out["sill"] = sill
    out["head"] = sill + o.get("h", 2100)          # contract h = height of the opening, from its sill
    if out["kind"] in LEAF:
        out["swing"] = "left" if o.get("side", 1) >= 0 else "right"
        out["hinge"] = o.get("hinge", "start") if out["kind"] == "door" else "both"
    else:
        out["swing"], out["hinge"] = "none", "none"
    fl = o.get("flag")
    if fl is True:
        out["flag"] = ["head", "sill"] if out["kind"] in ("window", "ventilator") else ["head"]
    elif fl is False:
        out.pop("flag", None)
    return out


def room_type(r):
    name = str(r.get("name", "")).lower()
    for kw, t in ROOM_NAME:
        if kw in name:
            return t, True
    return ROOM_KIND.get(r.get("kind"), "bedroom"), False


def _room(r, notes):
    if "type" in r:
        return r
    out = {k: v for k, v in r.items() if k != "kind"}
    t, by_name = room_type(r)
    out["type"] = t
    if not by_name:
        notes.append(f"room {r.get('id')} ({r.get('name')!r}): type {t!r} taken from kind {r.get('kind')!r}")
    if r.get("kind") == "wet" and t not in ("bath", "toilet", "utility"):
        notes.append(f"room {r.get('id')}: kind 'wet' but the name reads as {t!r}")
    return out


def survey(sv):
    """Contract survey.json -> engine form (returns a new dict with "_contract_notes")."""
    if not is_contract_survey(sv):
        return sv
    s = copy.deepcopy(sv)
    notes = []
    lv = dict(s.get("levels", {}))
    if "ceiling_height" in lv:
        h = lv.pop("ceiling_height")
        lv.setdefault("soffit", h)
        lv.setdefault("ceiling", h)
        if lv.pop("ceiling_height_flag", False):
            lv["flag"] = sorted(set(lv.get("flag") or []) | {"soffit", "ceiling"})
    s["levels"] = lv
    s["walls"] = [_wall(w, notes) for w in s.get("walls", [])]
    s["openings"] = [_opening(o, notes) for o in s.get("openings", [])]
    s["rooms"] = [_room(r, notes) for r in s.get("rooms", [])]
    s["flags"] = [dict({k: v for k, v in f.items() if k != "text"}, note=f.get("text", f.get("note", "")),
                       id=f.get("id", f"Q{i}")) for i, f in enumerate(s.get("flags", []), 1)]
    s["_contract_notes"] = notes
    return s


# ------------------------------------------------------------------ design
def _hex_ok(c):
    return isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c) is not None


def _materials(d, notes):
    """Contract material dicts -> vocab lists ({code, name, pattern, module, colour})."""
    for key in ("materials", "finish_materials", "feature_materials", "floor_materials"):
        v = d.get(key)
        if isinstance(v, dict):
            out = []
            for code, mat in v.items():
                if isinstance(mat, str):
                    out.append({"code": code, "name": mat})
                else:
                    m2 = dict(mat, code=code)
                    if "color" in m2:
                        m2["colour"] = m2.pop("color")
                    out.append(m2)
            d[key] = out


def _faces_on(walls, axis, line, lo, hi, tol=45):
    """Walls whose face lies on the line (axis 'x': a horizontal line y=line spanning x lo..hi)."""
    hits = []
    for w in walls:
        (ax, ay), (bx, by) = w["a"], w["b"]
        t = w.get("t", 115)
        al = w.get("align", "centre")
        offs = {"centre": (-t / 2, t / 2), "left": (0, t), "right": (-t, 0)}[al]
        if axis == "x" and abs(ay - by) < 1:
            ux = 1 if bx > ax else -1                   # left normal of (ux,0) is (0,ux)
            faces = [ay + ux * o for o in offs]
            if min(abs(f - line) for f in faces) <= tol and min(ax, bx) < hi - 50 and max(ax, bx) > lo + 50:
                hits.append(w)
        elif axis == "y" and abs(ax - bx) < 1:
            uy = 1 if by > ay else -1                   # left normal of (0,uy) is (-uy,0)
            faces = [ax - uy * o for o in offs]
            if min(abs(f - line) for f in faces) <= tol and min(ay, by) < hi - 50 and max(ay, by) > lo + 50:
                hits.append(w)
    return hits


def _modules_band(mods, z0, z1):
    out = []
    for md in mods:
        parts = md.get("parts")
        if parts:
            acc = 0
            part = parts[-1]
            for p in parts:                               # parts stack from the bottom up
                if acc <= z0 < acc + p["h"]:
                    part = p
                    break
                acc += p["h"]
        else:
            part = md
        t = part.get("type", "door")
        et, lab = MODULE.get(t, ("panel", t))
        label = part.get("label") or md.get("label") or lab
        if et == "shutter" and label and "loft" in str(label).lower():
            et = "loft"
        e = {"w": md["w"], "type": et}
        if label:
            e["label"] = label
        if part.get("n") or md.get("n"):
            e["n"] = part.get("n") or md.get("n")
        out.append(e)
    return out


def _bands(row):
    cuts = {0, row["h"]}
    for md in row["modules"]:
        acc = 0
        for p in md.get("parts", [])[:-1]:
            acc += p["h"]
            if 0 < acc < row["h"]:
                cuts.add(acc)
    cuts = sorted(cuts)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def _joinery_kind(name, rows):
    n = str(name or "").lower()
    for kw, k in JOINERY_NAME:
        if kw in n:
            if k == "kitchen_base" and rows and rows[0].get("z", 0) >= 1000:
                return "kitchen_wall"
            return k
    types = {p.get("type") for r in rows for md in r["modules"] for p in (md.get("parts") or [md])}
    if types & {"sink", "hob"}:
        return "kitchen_base"
    if rows and rows[0].get("z", 0) >= 1000:
        return "kitchen_wall"
    return "other"


def _joinery(j, walls, notes):
    """One contract joinery box -> engine items (vertically adjacent rows with the same run and depth merge
    into one item with bands; others become their own item, ids J1, J1-2, …)."""
    if "x" not in j:
        return [j], []
    f = j.get("facing", "N")
    run_x = f in ("N", "S")
    x0, y0, w, d = j["x"], j["y"], j["w"], j["d"]
    back = (y0 if f == "N" else y0 + d) if run_x else (x0 if f == "E" else x0 + w)
    run0, run_len = (x0, w) if run_x else (y0, d)
    full_depth = d if run_x else w
    rows = j.get("rows") or [{"z": 0, "h": 850, "depth": full_depth, "start": 0,
                              "modules": [{"w": run_len, "type": "door"}]}]
    # group rows: same start/run/depth and touching in z -> one item
    groups = []
    for r in sorted(rows, key=lambda r: r.get("z", 0)):
        rl = sum(md["w"] for md in r["modules"])
        key = (r.get("start", 0), rl, r.get("depth", full_depth))
        g = groups[-1] if groups else None
        if g and g["key"] == key and g["z1"] == r.get("z", 0):
            g["rows"].append(r)
            g["z1"] += r["h"]
        else:
            groups.append({"key": key, "rows": [r], "z0": r.get("z", 0), "z1": r.get("z", 0) + r["h"]})
    mats = j.get("materials") or {}
    out, extras = [], []
    for gi, g in enumerate(groups):
        start, rl, depth = g["key"]
        lo, hi = run0 + start, run0 + start + rl
        cands = _faces_on(walls, "x" if run_x else "y", back, lo, hi)
        jid = j["id"] if gi == 0 else f"{j['id']}-{gi + 1}"
        if not cands:
            notes.append(f"joinery {jid}: no wall face behind it ({'y' if run_x else 'x'}={back}); drawn as a "
                         f"free-standing box")
            cx = x0 + w / 2
            cy = y0 + d / 2
            extras.append({"id": jid, "room": j.get("room"), "kind": "other", "at": [round(cx), round(cy)],
                           "size": [w, d, g["z1"]] if run_x else [d, w, g["z1"]], "facing": f,
                           "label": j.get("name") or jid})
            continue
        wall = max(cands, key=lambda w_: min(max(w_["a"][0 if run_x else 1], w_["b"][0 if run_x else 1]), hi)
                   - max(min(w_["a"][0 if run_x else 1], w_["b"][0 if run_x else 1]), lo))
        a = wall["a"][0 if run_x else 1]
        sgn = 1 if wall["b"][0 if run_x else 1] > a else -1
        s0, s1 = (lo - a) * sgn, (hi - a) * sgn
        bands = []
        for r in g["rows"]:
            mods = r["modules"] if sgn > 0 else list(reversed(r["modules"]))
            for b0, b1 in _bands(r):
                bands.append({"height": b1 - b0, "modules": _modules_band(mods, b0, b1)})
        item = {"id": jid, "room": j.get("room"), "kind": _joinery_kind(j.get("name"), g["rows"]),
                "wall": wall["id"], "offset": round(min(s0, s1)), "width": round(abs(s1 - s0)), "depth": depth,
                "z": g["z0"], "height": g["z1"] - g["z0"], "rows": bands}
        if j.get("name"):
            item["label"] = j["name"]
        if len(groups) > 1:
            item["group"] = j["id"]
        if mats:
            item["materials"] = mats
        wt = j.get("worktop")
        if wt and gi == 0:
            if isinstance(wt, dict):
                item["worktop_t"] = wt.get("t", 30)
                code = mats.get("worktop") if isinstance(mats, dict) else None
                if code:
                    item["worktop"] = code
            else:
                item["worktop"] = wt
        for k in ("notes", "parts", "handles", "flag"):
            if k in j:
                item[k] = j[k]
        out.append(item)
    return out, extras


def _furniture(f, notes):
    if "x" not in f:
        return "furniture", f
    t = f.get("type") or f.get("kind") or "other"
    lst, kind, h = FURN.get(t, ("furniture", "other", 750))
    if t not in FURN:
        notes.append(f"furniture {f.get('id')}: type {t!r} is not drawn by the engine; shown as a labelled box")
    facing = f.get("facing", "N")
    w, d = f["w"], f["d"]
    size = [w, d] if facing in ("N", "S") else [d, w]        # engine: width across the front, depth along facing
    out = {k: v for k, v in f.items() if k not in ("x", "y", "w", "d", "type", "h")}
    out.update(kind=kind, at=[round(f["x"] + w / 2), round(f["y"] + d / 2)], size=size + [f.get("h", h)],
               facing=facing)
    if t not in FURN:
        out["label"] = f.get("label") or t
    return lst, out


def _ceiling(c):
    if c.get("type") == "exposed":
        return None
    c = dict(c)
    if c.get("tracks"):
        c["tracks"] = [[[t[0], t[1]], [t[2], t[3]]] if isinstance(t, (list, tuple)) and len(t) == 4
                       and not isinstance(t[0], (list, tuple)) else t for t in c["tracks"]]
    if c.get("area") and len(c["area"]) == 4 and not isinstance(c["area"][0], (list, tuple)):
        x0, y0, x1, y1 = c["area"]
        c["area"] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    feats = []
    for i, fe in enumerate(c.get("features", []), 1):
        if "at" in fe:
            feats.append(fe)
        else:
            feats.append({"id": fe.get("id", f"DM-{c['room']}-{i}"), "kind": fe.get("kind", "dome"),
                          "at": [fe["x"], fe["y"]], "d": 2 * fe.get("r", 750), "h": fe.get("h"),
                          "light": fe.get("light", "cove")})
    if feats:
        c["features"] = feats
    return c


def _feature_wall(g):
    g = copy.deepcopy(g)
    for it in g.get("items", []):
        it["type"] = FEATURE_TYPE.get(it.get("type"), it.get("type"))
        if "round" in it:
            it["rounded"] = it.pop("round")
    for p in g.get("pendants", []):
        if "h" in p and "length" not in p:
            p["length"] = p.pop("h")
    return g


def design(ds, sv_engine):
    """Contract design -> the vocabulary atelier.vocab understands (and engine-form joinery / furniture)."""
    if not is_contract_design(ds):
        return ds
    d = copy.deepcopy(ds)
    notes = []
    extras = {}
    if "brief" in d:
        extras["brief"] = d.pop("brief")
    d["new_walls"] = [_wall(w, notes) for w in d.get("new_walls", [])]
    d["new_openings"] = [_opening(o, notes) for o in d.get("new_openings", [])]
    d["rooms"] = [_room(r, notes) for r in d.get("rooms", [])]
    dem = d.get("demolish", [])
    d["demolish"] = [x if isinstance(x, dict) else {"wall": x} for x in dem] + \
        [{"opening": o} for o in d.pop("demolish_openings", [])]
    # walls standing after the redesign (for joinery placement)
    gone = {x["wall"] for x in d["demolish"] if "wall" in x}
    walls = [w for w in sv_engine.get("walls", []) if w["id"] not in gone] + d["new_walls"]
    _materials(d, notes)
    # floors {room: code}
    if isinstance(d.get("floors"), dict):
        d["floors"] = [{"room": r, "material": c} for r, c in d["floors"].items()]
    # wall finishes {room: [{code, edges}]}
    wfin = d.get("wall_finishes")
    if isinstance(wfin, dict):
        whole, extra_fw = {}, []
        for rid, lst in wfin.items():
            for e in (lst if isinstance(lst, list) else [{"code": lst, "edges": "all"}]):
                if e.get("edges", "all") == "all":
                    whole[rid] = e["code"]
                else:
                    for k in e["edges"]:
                        extra_fw.append({"id": f"WF-{rid}-{k}", "room": rid, "edge": k, "code": e["code"]})
        d["wall_finishes"] = whole
        if extra_fw:
            extras["edge_finishes"] = extra_fw
    # furniture, sanitary
    furn, san = [], list(d.get("sanitary", []))
    for f in d.get("furniture", []):
        lst, f2 = _furniture(f, notes)
        (san if lst == "sanitary" else furn).append(f2)
    # joinery
    jn = []
    for j in d.get("joinery", []):
        items, boxes = _joinery(j, walls, notes)
        jn += items
        furn += boxes
    d["furniture"], d["sanitary"], d["joinery"] = furn, san, jn
    # ceilings
    d["ceilings"] = [c2 for c2 in (_ceiling(c) for c in d.get("ceilings", [])) if c2 is not None]
    # views by edge -> resolved after load (need geometry); cameras with pos
    views = []
    for v in d.get("views", []):
        if isinstance(v, dict) and "edge" in v and "kind" not in v:
            extras.setdefault("edge_views", []).append(v)
        else:
            views.append(v)
    d["views"] = views
    cams = []
    for i, c in enumerate(d.get("cameras", []), 1):
        if "pos" in c:
            cams.append({"id": c.get("id", f"C{i}"), "room": c["room"], "eye": list(c["pos"]),
                         "target": list(c["target"]), "lens": c.get("lens", 20)})
            if len(c["pos"]) > 2 and len(c["target"]) > 2 and c["pos"][2] != c["target"][2]:
                notes.append(f"camera C{i}: tilted target levelled (verticals stay vertical, STANDARDS RB2a.6)")
        else:
            cams.append(c)
    d["cameras"] = cams
    d["wall_features"] = [_feature_wall(g) for g in d.get("wall_features", [])]
    d.setdefault("_contract_extras", {}).update(extras)
    d["_contract_notes"] = notes
    return d


def resolve(m):
    """After load: contract views by room edge -> design cameras (fw_<id>.png), edge wall finishes ->
    wall features."""
    from atelier import features as FT
    from atelier import geom
    from atelier.views3d import feature_camera
    ex = getattr(m, "contract_extras", {}) or {}
    for v in ex.get("edge_views", []):
        room = m.room(v["room"])
        if room is None:
            m.override_errors.append(f"view {v.get('id')}: no room {v['room']!r}")
            continue
        g = {"id": v["id"], "room": v["room"], "edge": v["edge"]}
        L, _ = FT.wall_u(m, g)
        if not L:
            m.override_errors.append(f"view {v.get('id')}: room {v['room']} has no edge {v['edge']}")
            continue
        cam = feature_camera(m, dict(g, items=[{"from": 0, "to": L}]))
        cam = {k: x for k, x in cam.items() if k not in ("feature", "auto")}
        cam.update(id=v["id"], name=v.get("name"), edge=v["edge"])
        m.design.setdefault("cameras", []).append(cam)
    for e in ex.get("edge_finishes", []):
        room = m.room(e["room"])
        edges = geom.room_edges(room, m.walls) if room else []
        hit = [f for f in geom.room_faces(room, m.walls) if any(x.n == e["edge"] and f.n == x.n for x in edges)] \
            if room else []
        if not hit:
            m.override_errors.append(f"wall finish {e['id']}: room {e['room']} has no edge {e['edge']}")
            continue
        for k, f in enumerate(hit):
            w = m.wall(f.wall)
            p0 = geom.Point(f.a)
            a = w["a"]
            t0 = math.hypot(f.a[0] - a[0], f.a[1] - a[1])
            t1 = math.hypot(f.b[0] - a[0], f.b[1] - a[1])
            del p0
            m.design.setdefault("wall_features", []).append({"id": f"{e["id"]}{'' if k == 0 else chr(97 + k)}", "room": e["room"],
                                    "wall": f.wall, "offset": round(min(t0, t1)), "width": round(abs(t1 - t0)),
                                    "z0": 0, "z1": m.levels.get("ceiling", 2750), "kind": "paint",
                                    "finish": e["code"]})


# ------------------------------------------------------------------ services overrides
def overrides(ov):
    """Contract services_overrides.json -> engine form."""
    if not (isinstance(ov.get("add"), dict) or any("x" in mv for mv in ov.get("move", []))):
        return ov
    out = {"remove": list(ov.get("remove", [])), "move": [], "add": []}
    for mv in ov.get("move", []):
        e = {"id": mv["id"]}
        if "x" in mv:
            e["at"] = [mv["x"], mv["y"]]
        if "h" in mv:
            e["z"] = mv["h"]
        out["move"].append(e)
    for sysk, items in (ov.get("add") or {}).items():
        for it in items:
            kind = POINT.get(it.get("type"), it.get("type"))
            e = {"id": it["id"], "system": SYSTEM.get(sysk, sysk), "kind": kind, "room": it.get("room"),
                 "at": [it["x"], it["y"]], "z": it.get("h"), "wall": it.get("wall")}
            if "x2" in it:
                e["path"] = [[it["x"], it["y"]], [it["x2"], it["y2"]]]
            if it.get("note"):
                e["note"] = it["note"]
            out["add"].append(e)
    return out


# ------------------------------------------------------------------ export (engine -> contract)
def export(root, out_dir):
    """Write a project's survey / design / overrides in contract form (for migration and round trips)."""
    from atelier import geom
    from atelier.model import load
    root, out_dir = Path(root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sv = json.loads((root / "survey.json").read_text())
    m = load(root)

    def wall_out(w):
        t = w.get("t", 115)
        a, b = list(w["a"]), list(w["b"])
        al = w.get("align", "centre")
        if al != "centre":                                       # contract walls are centre-lines
            ux, uy = (b[0] - a[0]), (b[1] - a[1])
            L = math.hypot(ux, uy)
            nx, ny = -uy / L, ux / L
            s = t / 2 if al == "left" else -t / 2
            a = [round(a[0] + nx * s), round(a[1] + ny * s)]
            b = [round(b[0] + nx * s), round(b[1] + ny * s)]
        o = {"id": w["id"], "a": a, "b": b, "t": t, "type": WALL_TYPE_OUT.get(w.get("kind"), "partition"),
             "h": w.get("height")}
        if w.get("flag"):
            o["flag"] = True
        return o

    def opening_out(o):
        k = "entrance" if o.get("entrance") or str(o.get("note", "")).lower().startswith("main entr") else o["kind"]
        sill = o.get("sill", 0) if o["kind"] in ("window", "ventilator") else 0
        e = {"id": o["id"], "wall": o["wall"], "offset": o["offset"], "width": o["width"], "kind": k,
             "h": o.get("head", 2100) - sill, "sill": sill}
        if o["kind"] in LEAF:
            e["side"] = 1 if o.get("swing") == "left" else -1
            e["hinge"] = o.get("hinge", "start")
        if o.get("flag"):
            e["flag"] = True
        if o.get("note") and k != "entrance":
            e["note"] = o["note"]
        return e

    def room_out(r):
        e = {"id": r["id"], "name": r.get("name", r["id"]), "poly": r["poly"],
             "kind": ROOM_KIND_OUT.get(r.get("type"), "dry")}
        for k in ("ffl", "flag", "area_printed"):
            if k in r:
                e[k] = r[k]
        return e

    # the contract demolishes whole walls only: split a partly demolished survey wall where the cut is
    ds = json.loads((root / "design.json").read_text())
    walls_sv, open_sv, dem_walls = [], [dict(o) for o in sv["openings"]], []
    from atelier.model import _split_wall
    for w in sv["walls"]:
        cut = next((x for x in ds.get("demolish", []) if x.get("wall") == w["id"] and "from" in x), None)
        if not cut:
            walls_sv.append(w)
            if any(x.get("wall") == w["id"] for x in ds.get("demolish", [])):
                dem_walls.append(w["id"])
            continue
        o0, o1 = cut["from"], cut["to"]
        keep = _split_wall(w, o0, o1)
        mid = dict(w, id=f"{w['id']}d", a=[round(c) for c in geom.point_on_wall(w, o0)],
                   b=[round(c) for c in geom.point_on_wall(w, o1)])
        for k in keep:
            k.pop("_parent", None)
            k.pop("_from", None)
        pieces = keep[:1] + [mid] + keep[1:]
        walls_sv += pieces
        dem_walls.append(mid["id"])
        starts = {pieces[0]["id"]: 0, mid["id"]: o0}
        if len(keep) > 1:
            starts[keep[1]["id"]] = o1
        for o in open_sv:
            if o["wall"] != w["id"]:
                continue
            host = keep[0]["id"] if o["offset"] + o["width"] <= o0 else (
                mid["id"] if o["offset"] < o1 else keep[-1]["id"])
            o["wall"], o["offset"] = host, o["offset"] - starts[host]

    lv = dict(sv.get("levels", {}))
    sv_out = {"project": sv.get("project", {}), "levels": {"ceiling_height": lv.get("soffit", 2750),
                                                           "ceiling_height_flag": "soffit" in (lv.get("flag") or [])},
              "calibration": sv.get("calibration", {}),
              "walls": [wall_out(w) for w in walls_sv], "openings": [opening_out(o) for o in open_sv],
              "rooms": [room_out(r) for r in sv["rooms"]],
              "flags": [{"text": f.get("note", ""), "ref": f.get("ref")} for f in sv.get("flags", [])]}
    (out_dir / "survey.json").write_text(json.dumps(sv_out, indent=1, ensure_ascii=False) + "\n")

    rooms = {r["id"]: r for r in m.rooms}

    def box(poly):
        x0, y0, x1, y1 = poly.bounds
        return round(x0), round(y0), round(x1 - x0), round(y1 - y0)

    furn = []
    for f in m.furniture:
        x, y, w, d = box(geom.furniture_polygon(f))
        e = {"id": f["id"], "type": FURN_OUT.get(f["kind"], f["kind"]), "label": f.get("label", ""),
             "room": f["room"], "x": x, "y": y, "w": w, "d": d, "facing": f.get("facing", "N")}
        if len(f.get("size", [])) > 2:
            e["h"] = f["size"][2]
        for k in ("headboard", "finish", "lamp"):
            if k in f:
                e[k] = f[k]
        furn.append(e)
    for s in m.sanitary:
        x, y, w, d = box(geom.furniture_polygon(dict(s, size=list(s["size"][:2]))))
        furn.append({"id": s["id"], "type": s["kind"], "room": s["room"], "x": x, "y": y, "w": w, "d": d,
                     "facing": s.get("facing", "N")})
    jn = []
    for j in m.joinery:
        wall = m.wall(j["wall"])
        x, y, w, d = box(geom.joinery_polygon(j, wall, rooms[j["room"]]))
        side = geom.room_side_of_wall(wall, rooms[j["room"]]) or "left"
        ux, uy, _ = geom.unit(wall["a"], wall["b"])
        nx, ny = geom.left_normal(ux, uy)
        if side == "right":
            nx, ny = -nx, -ny
        facing = "N" if ny > 0.5 else "S" if ny < -0.5 else "E" if nx > 0.5 else "W"
        rev = (ux < -0.5) or (uy < -0.5)
        rows, z = [], j.get("z", 0)
        for band in j["rows"]:
            mods = []
            for md in (reversed(band["modules"]) if rev else band["modules"]):
                t = MODULE_OUT.get(md["type"], "panel")
                lab = md.get("label") or ("Loft" if md["type"] == "loft" else None)
                if md["type"] == "appliance" and lab and lab.lower() in ("hood", "oven", "fridge", "dishwasher"):
                    t = lab.lower()
                e = {"w": md["w"], "type": t}
                if lab:
                    e["label"] = lab
                if md.get("n"):
                    e["n"] = md["n"]
                mods.append(e)
            rows.append({"z": z, "h": band["height"], "depth": j["depth"], "start": 0, "modules": mods})
            z += band["height"]
        mats = dict(j.get("materials") or {})
        if j.get("finish") and not mats:
            mats = {"fronts": j["finish"]}
        if j.get("worktop") and isinstance(mats, dict):
            mats["worktop"] = j["worktop"]
        e = {"id": j["id"], "name": j.get("label") or j["kind"].replace("_", " ").capitalize(), "room": j["room"],
             "x": x, "y": y, "w": w, "d": d, "facing": facing, "materials": mats, "rows": rows}
        if j.get("worktop"):
            e["worktop"] = {"z": j.get("z", 0) + j["height"], "t": j.get("worktop_t", 30), "from": 0}
        jn.append(e)
    def ceiling_out(c):
        """Engine ceiling -> contract: flat {h, tracks}, or tray {h, steps [{band, h}], core_h, area, features}."""
        if c.get("type"):
            return c
        z0 = c.get("z")
        lights = [l_ for l_ in c.get("lights", []) if l_.get("kind") != "track"]
        tracks = [[*l_["path"][0], *l_["path"][-1]] for l_ in c.get("lights", []) if l_.get("kind") == "track"]
        steps = c.get("steps", [])
        if not steps and not c.get("domes"):
            e = {"room": c["room"], "type": "flat", "h": z0}
        else:
            e = {"room": c["room"], "type": "tray", "h": z0}
            st, prev_inset = [], 0
            if steps and "poly" in steps[0]:                     # partial tray: area = the first step's outline
                from shapely.geometry import Polygon as _Poly
                b = _Poly(steps[0]["poly"]).bounds
                e["area"] = [round(v) for v in b]
                st.append({"band": 0, "h": z0})
                for k in range(1, len(steps)):
                    b2 = _Poly(steps[k]["poly"]).bounds
                    st.append({"band": round(b2[0] - b[0]), "h": steps[k - 1]["z"], "light": steps[k - 1].get("light")})
            else:
                levels = [z0] + [s_["z"] for s_ in steps]
                for k, s_ in enumerate(steps):
                    st.append({"band": s_["inset"] - prev_inset, "h": levels[k],
                               "light": steps[k - 1].get("light") if k else None})
                    prev_inset = s_["inset"]
            for s_ in st:
                if s_.get("light") is None:
                    s_.pop("light", None)
            e["steps"] = st
            if steps:
                e["core_h"] = steps[-1]["z"]
                if steps[-1].get("light"):
                    e["core_light"] = steps[-1]["light"]
            if c.get("domes"):
                e["features"] = [{"id": d_["id"], "x": d_["at"][0], "y": d_["at"][1], "r": d_["d"] // 2,
                                  "h": d_["z"], "light": d_.get("light", "cove")} for d_ in c["domes"]]
        if tracks:
            e["tracks"] = tracks
        if lights:
            e["lights"] = lights
        return e

    fins = {f["code"]: f for f in m.finishes}
    floor_codes = {f["finish"] for f in m.floors}
    out = {"concept": ds.get("concept", "A"), "style": (m.extras or {}).get("style", ""),
           "summary": (m.extras or {}).get("summary", ""), "palette": (m.extras or {}).get("palette", []),
           "demolish": dem_walls,
           "demolish_openings": [x["opening"] for x in ds.get("demolish", []) if "opening" in x],
           "new_walls": [wall_out(w) for w in ds.get("new_walls", [])],
           "new_openings": [opening_out(o) for o in ds.get("new_openings", [])],
           "opening_overrides": ds.get("opening_overrides", []),
           "rooms": [room_out(r) for r in m.rooms if any(x["id"] == r["id"] for x in ds.get("rooms", []))
                     and r.get("poly")],
           "furniture": furn, "joinery": jn,
           "materials": {c: f.get("name", c) for c, f in fins.items()
                         if c not in floor_codes and not c.startswith(("WF", "FW"))},
           "floor_materials": {c: {"name": fins[c].get("name", c), "pattern": next(
               (fl.get("pattern") for fl in m.floors if fl["finish"] == c), "tile"), "module": next(
               (fl.get("module") for fl in m.floors if fl["finish"] == c and fl.get("module")), None)}
               for c in floor_codes if c in fins},
           "floors": {fl["room"]: fl["finish"] for fl in m.floors},
           "finish_materials": {c: {"name": f.get("name", c)} for c, f in fins.items() if c.startswith("WF")},
           "wall_finishes": {r["id"]: [{"code": r["wall_finish"], "edges": "all"}] for r in m.rooms
                             if r.get("wall_finish")},
           "ceilings": [ceiling_out(c) for c in ds.get("ceilings", [])],
           "views": [v for v in ds.get("views", [])],
           "cameras": [], "wall_features": ds.get("wall_features", []),
           "notes": [n["text"] if isinstance(n, dict) else n for n in ds.get("notes", [])]}
    (out_dir / "design.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for f in ("services_overrides.json", "project.json"):
        if (root / f).exists():
            (out_dir / f).write_text((root / f).read_text())
    return out_dir


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) == 3 and a[0] == "export":
        print(f"contract ✓ {export(a[1], a[2])}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

"""Load a project and merge survey.json + design.json into one model.

    from atelier.model import load
    m = load("projects/sample")                 # survey + design.json if present
    m = load("projects/sample", "alt.json")     # survey + another design file
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from atelier import geom

DESIGN_LISTS = ("furniture", "joinery", "ceilings", "wall_features", "floors",
                "finishes", "views", "cameras", "notes")


@dataclass
class Model:
    root: Path
    project: dict
    levels: dict
    calibration: dict
    walls: list
    openings: list
    rooms: list
    flags: list
    design: dict = field(default_factory=dict)
    verify: list = field(default_factory=list)   # [(ref, field, note)]
    sources: list = field(default_factory=list)

    # ---- lookups
    def wall(self, wid):
        return next((w for w in self.walls if w["id"] == wid), None)

    def room(self, rid):
        return next((r for r in self.rooms if r["id"] == rid), None)

    def openings_on(self, wid):
        return [o for o in self.openings if o["wall"] == wid]

    def __getattr__(self, name):  # furniture, joinery, ceilings, … from the design
        if name in DESIGN_LISTS:
            return self.__dict__["design"].get(name, [])
        raise AttributeError(name)

    def is_flagged(self, obj, fld=None) -> bool:
        f = obj.get("flag")
        if f is True:
            return True
        return bool(fld and isinstance(f, list) and fld in f)


def _read(p: Path) -> dict:
    return json.loads(p.read_text())


def _split_wall(w, o0, o1):
    """Remove the stretch o0..o1 (offsets) from wall w; return the remaining parts."""
    L = geom.wall_length(w)
    parts = []
    for i, (s, e) in enumerate(((0, o0), (o1, L))):
        if e - s > 0.5:
            nw = copy.deepcopy(w)
            nw["id"] = f'{w["id"]}{"ab"[i]}'
            nw["a"] = [round(c) for c in geom.point_on_wall(w, s)]
            nw["b"] = [round(c) for c in geom.point_on_wall(w, e)]
            nw["_parent"], nw["_from"] = w["id"], s
            parts.append(nw)
    return parts


def _collect_flags(kind, objs, file_flag, out):
    for o in objs:
        f = o.get("flag")
        ref = o.get("id") or o.get("room") or o.get("code") or kind
        if file_flag or f is True:
            out.append((ref, None, o.get("note", f"{kind} unverified")))
        elif isinstance(f, list):
            for fld in f:
                out.append((ref, fld, o.get("note", "")))


def load(root, design: str | None = None) -> Model:
    root = Path(root)
    sv = _read(root / "survey.json")
    ff = sv.get("flag") is True
    m = Model(root=root, project=sv.get("project", {}), levels=dict(sv.get("levels", {})),
              calibration=sv.get("calibration", {}), walls=copy.deepcopy(sv.get("walls", [])),
              openings=copy.deepcopy(sv.get("openings", [])), rooms=copy.deepcopy(sv.get("rooms", [])),
              flags=list(sv.get("flags", [])), sources=["survey.json"])
    for kind in ("walls", "openings", "rooms"):
        _collect_flags(kind[:-1], getattr(m, kind), ff, m.verify)
    for name in ("levels", "calibration"):
        _collect_flags(name, [dict(getattr(m, name), id=name)], ff, m.verify)
    for q in m.flags:
        m.verify.append((q.get("ref") or q.get("id"), None, q.get("note", "")))

    dpath = root / (design or "design.json")
    if design and not dpath.exists():
        dpath = Path(design)
    if not dpath.exists():
        return m
    ds = _read(dpath)
    m.sources.append(dpath.name)
    dff = ds.get("flag") is True

    # demolition
    for d in ds.get("demolish", []):
        if "opening" in d:
            m.openings = [o for o in m.openings if o["id"] != d["opening"]]
        elif "wall" in d:
            w = m.wall(d["wall"])
            if w is None:
                continue
            m.walls.remove(w)
            if "from" in d:
                parts = _split_wall(w, d["from"], d["to"])
                m.walls += parts
                keep = []
                for o in m.openings:
                    if o["wall"] != w["id"]:
                        keep.append(o)
                        continue
                    if o["offset"] + o["width"] <= d["from"]:
                        keep.append(dict(o, wall=parts[0]["id"]) if parts and parts[0]["_from"] == 0 else o)
                    elif o["offset"] >= d["to"] and parts:
                        p = parts[-1]
                        keep.append(dict(o, wall=p["id"], offset=o["offset"] - p["_from"]))
                m.openings = keep
            else:
                m.openings = [o for o in m.openings if o["wall"] != w["id"]]

    m.walls += copy.deepcopy(ds.get("new_walls", []))
    m.openings += copy.deepcopy(ds.get("new_openings", []))
    for r in ds.get("rooms", []):
        cur = m.room(r["id"])
        if cur:
            cur.update(copy.deepcopy(r))
        else:
            m.rooms.append(copy.deepcopy(r))
    m.design = {k: copy.deepcopy(ds.get(k, [])) for k in DESIGN_LISTS}
    for k in ("new_walls", "new_openings", "rooms", *DESIGN_LISTS):
        _collect_flags(k, ds.get(k, []), dff, m.verify)
    return m

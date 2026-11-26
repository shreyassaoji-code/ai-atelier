"""Blender frames for the VISUALISER (agents/visualiser.md) and the visualisations it brings back.

    out/renders/fw_<feature>.png   feature-wall views          (fw_<V>.png for a camera named in views/cameras)
    out/renders/cam_<room>-<n>.png corner views of the rooms   (feed the round vignettes on the room boards)
    out/renders/cameras.json       every frame: file, room, ratio, reference, materials and the prompt
    out/renders/viz.json           written by the visualiser: [{"file", "caption", "room_name"}]
    out/renders/viz_<id>_<n>.png   its images; <id> = camera id, frame name or feature id

A visualisation is used on the boards only while it is newer than its frame and the frame is current
(the data has not changed since); otherwise the album falls back to the Blender view. This module is
not part of the render cache key, so changing it never forces a re-render.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROMPT = ("Photorealistic luxury interior photograph of this exact room. Keep the camera angle, perspective, walls, "
          "windows, doors, wall panelling and every furniture position exactly as in the first reference. "
          "Match the mood, lighting and materials of the second reference. {room}, {style}. Materials: {materials}. "
          "Warm 2700K cove light, soft daylight, restrained styling. No people, no text, no watermark.")
DEFAULT_STYLE = "contemporary luxury"


def frame_file(cam: dict) -> str:
    """File name of a camera's Blender frame."""
    if cam.get("feature"):
        return f"fw_{cam['feature']}.png"
    if not cam.get("auto", True):                     # a camera the design names: fw_<V>
        return f"fw_{cam['id']}.png"
    return f"cam_{re.sub(r'^V-', '', cam['id'])}.png"


def frame_path(root, cam) -> Path:
    return Path(root) / "out" / "renders" / frame_file(cam)


def _name(fin, code):
    f = fin.get(code)
    return f"{code} {f['name']}" if f and f.get("name") else code


def materials(m, cam) -> list[str]:
    """Floor, feature-wall / wall finishes, joinery fronts and worktops of the camera's room."""
    fin = {f["code"]: f for f in m.finishes}
    rid = cam["room"]
    room = m.room(rid)
    out = []
    fl = next((x for x in m.floors if x["room"] == rid), None)
    if fl and fl.get("finish"):
        out.append("floor " + _name(fin, fl["finish"]))
    feats = [g for g in m.feature_walls if g["room"] == rid and (not cam.get("feature") or g["id"] == cam["feature"])]
    for g in feats:
        for code in dict.fromkeys(i.get("code") for i in g["items"] if i.get("code")):
            out.append(f"{g['id']} " + _name(fin, code))
    if room.get("wall_finish"):
        out.append("walls " + _name(fin, room["wall_finish"]))
    for j in m.joinery:
        if j["room"] == rid:
            if j.get("finish"):
                out.append(f"{j.get('kind', 'joinery').replace('_', ' ')} fronts " + _name(fin, j["finish"]))
            if j.get("worktop"):
                out.append("worktop " + _name(fin, j["worktop"]))
    return list(dict.fromkeys(out))


def entries(m, root=None) -> list[dict]:
    from atelier.feature_sheet import ref_path
    from atelier.render import R, all_cameras, is_current
    root = Path(root or m.root)
    style = (getattr(m, "extras", {}) or {}).get("style")
    out = []
    for c in all_cameras(m):
        room = m.room(c["room"])
        g = next((x for x in m.feature_walls if x["id"] == c.get("feature")), None)
        ref = ref_path(m, g) if g else None
        mats = materials(m, c)
        rn = room.get("name", room["id"])
        what = f"{g['id']} feature wall" if g else f"from the {c.get('corner')} corner" if c.get("corner") else c["id"]
        out.append({
            "id": c["id"], "file": frame_file(c), "kind": "feature" if g else "room", "room": c["room"],
            "room_name": rn, "feature": c.get("feature"),
            "rendered": bool(frame_path(root, c).exists() and is_current(root, m, c)),
            "ratio": "1:1", "size": [R["size"], R["size"]],
            "reference": str(ref.relative_to(root)) if ref and ref.is_relative_to(root) else (str(ref) if ref else None),
            "style": style or DEFAULT_STYLE, "style_flag": not style,
            "materials": mats,
            "caption": f"{c['id']} · {rn} – {what}",
            "prompt": PROMPT.format(room=rn, style=style or DEFAULT_STYLE, materials="; ".join(mats) or "as drawn"),
        })
    return out


def write_cameras(m, root=None) -> Path:
    root = Path(root or m.root)
    p = root / "out" / "renders" / "cameras.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"frames": entries(m, root)}, indent=1, ensure_ascii=False) + "\n")
    return p


# ------------------------------------------------------------------ visualisations
VIZ_RE = re.compile(r"^viz_(.+)_(\d+)\.(png|jpe?g|webp)$", re.I)


def viz_list(root) -> list[dict]:
    p = Path(root) / "out" / "renders" / "viz.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    return d if isinstance(d, list) else d.get("viz", [])


def _matches(key, cam):
    return key in (cam["id"], Path(frame_file(cam)).stem, cam.get("feature"), re.sub(r"^V-", "", cam["id"]))


def viz_status(root, m, cam) -> tuple[Path | None, dict | None, str]:
    """(path, entry, state) of the first visualisation of this camera. state: none / missing / stale / ok."""
    from atelier.render import is_current
    root = Path(root)
    for e in viz_list(root):
        mt = VIZ_RE.match(Path(e.get("file", "")).name)
        if not mt or not _matches(mt.group(1), cam):
            continue
        p = root / "out" / "renders" / Path(e["file"]).name
        if not p.exists():
            return p, e, "missing"
        fr = frame_path(root, cam)
        if not (fr.exists() and is_current(root, m, cam)) or p.stat().st_mtime < fr.stat().st_mtime:
            return p, e, "stale"                       # the frame (the data) changed after the visualisation
        return p, e, "ok"
    return None, None, "none"


def picture_for(root, m, cam):
    """What the boards show for a camera: (path, label) – the visualisation when it is current, else the
    Blender frame when current, else (None, None)."""
    from atelier.render import is_current
    p, e, st = viz_status(root, m, cam)
    if st == "ok":
        return p, f"AI visualisation of frame {frame_file(cam)}" + (f" · {e['caption']}" if e.get("caption") else "")
    fr = frame_path(root, cam)
    if fr.exists() and is_current(Path(root), m, cam):
        return fr, None
    return None, None

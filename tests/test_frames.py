"""Frames for the visualiser and the visualisations it returns (agents/visualiser.md).   python tests/test_frames.py

Names, cameras.json with filled prompts, and the album's rule: a visualisation is shown only while it is
newer than a current frame; listed-but-missing or unmatched files are caught by the pre-check.
Needs the sample's frames rendered (python -m atelier.render projects/sample).
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier import frames as FR  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.render import all_cameras  # noqa: E402

P = ROOT / "projects" / "sample"
REN = P / "out" / "renders"
m = load(P)
cams = all_cameras(m)
fw = next(c for c in cams if c.get("feature") == "FW2")
room = next(c for c in cams if c["id"] == "V-MBR-2")
checks = [
    ("feature frame fw_FW2.png", FR.frame_file(fw) == "fw_FW2.png"),
    ("corner frame cam_MBR-2.png", FR.frame_file(room) == "cam_MBR-2.png"),
    ("named camera fw_<id>.png", FR.frame_file({"id": "V1", "room": "LD", "auto": False}) == "fw_V1.png"),
]
FR.write_cameras(m)
cj = json.loads((REN / "cameras.json").read_text())["frames"]
e = next(x for x in cj if x["id"] == "V-FW2")
checks += [
    ("cameras.json lists every camera", len(cj) == len(cams)),
    ("prompt filled: room, materials, no placeholders",
     "Master bedroom" in e["prompt"] or e["room_name"] in e["prompt"]) ,
    ("prompt has the feature's finishes", "WF7" in e["prompt"] and "<" not in e["prompt"]),
    ("default style flagged", e["style_flag"] is True),
    ("all frames rendered and current", all(x["rendered"] for x in cj)),
]

viz_json = REN / "viz.json"
backup = viz_json.read_text() if viz_json.exists() else None
img = REN / "viz_FW2_1.png"
try:
    shutil.copy(REN / FR.frame_file(fw), img)
    os.utime(img, (FR.frame_path(P, fw).stat().st_mtime + 10,) * 2)
    viz_json.write_text(json.dumps([{"file": img.name, "caption": "FW2 · Master bedroom – headboard wall",
                                     "room_name": "Master bedroom"}]))
    p, label = FR.picture_for(P, m, fw)
    checks.append(("current visualisation used, captioned as AI", p == img and label.startswith("AI visualisation")))
    os.utime(img, (FR.frame_path(P, fw).stat().st_mtime - 10,) * 2)
    p, label = FR.picture_for(P, m, fw)
    checks.append(("older than its frame: Blender view instead", p == FR.frame_path(P, fw) and label is None))
    from atelier.check import run
    viz_json.write_text(json.dumps([{"file": "viz_NOPE_1.png", "caption": "x", "room_name": "y"},
                                    {"file": "viz_FW1_1.png", "caption": "x", "room_name": "y"}]))
    rows = [t for s, st, t in run(P).rows if s.startswith("9") and st == "FAIL"]
    checks += [("pre-check: unmatched name", any("NOPE" in t for t in rows)),
               ("pre-check: listed but missing", any("viz_FW1_1" in t and "not on disk" in t for t in rows))]
finally:
    img.unlink(missing_ok=True)
    if backup is None:
        viz_json.unlink(missing_ok=True)
    else:
        viz_json.write_text(backup)

for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(0 if all(ok for _, ok in checks) else 1)

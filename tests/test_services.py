"""STANDARDS §6 checks against the generated services.json.   python tests/test_services.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shapely.geometry import Point  # noqa: E402

from atelier import geom  # noqa: E402
from atelier.model import load  # noqa: E402
from atelier.services import build  # noqa: E402

P = ROOT / "projects" / "sample"
m = load(P)
S = build(P)[0]["items"]
by = lambda k: [i for i in S if i["kind"] == k]  # noqa: E731
wet = {r["id"] for r in m.rooms if r["type"] in ("bath", "toilet")}

# R6.7: worktop sockets >= 150 from any sink/hob module (measured along the run)
near = []
for j in m.joinery:
    if j.get("kind") != "kitchen_base":
        continue
    w = m.wall(j["wall"])
    o = j["offset"]
    for md in j["rows"][0]["modules"]:
        if md["type"] in ("sink", "hob"):
            a = Point(geom.point_on_wall(w, o))
            b = Point(geom.point_on_wall(w, o + md["w"]))
            from shapely.geometry import LineString
            seg = LineString([a, b])
            for s in by("worktop_socket"):
                d = seg.distance(Point(s["at"]))
                if d < 150 - 1 and s["room"] == j["room"]:
                    near.append((s["id"], round(d)))
        o += md["w"]

fans = {i["room"]: Point(i["at"]) for i in by("fan")}
def _split_without_feature():
    from atelier.model import load as _load
    from atelier.services import Builder as _B
    mm = _load(ROOT / "projects" / "sample")
    mm.design["wall_features"] = [w for w in mm.design["wall_features"] if w["room"] != "BR2"]
    mm.feature_walls = [g for g in mm.feature_walls if g["room"] != "BR2"]
    its = _B(mm).run()
    return any(i["kind"] == "split" and i["room"] == "BR2" for i in its) and \
        not any(i["kind"] == "ducted" and i["room"] == "BR2" for i in its)


checks = [
    ("R6.1 boards at h1200", all(i["z"] == 1200 for i in by("switchboard"))),
    ("R6.2 wet-room boards outside", all(i["room"] not in wet for i in by("switchboard") if i.get("serves") in wet)),
    ("R6.3 sockets h300", all(i["z"] == 300 for i in by("socket"))),
    ("R6.4 one socket+USB h600 per bedside", len(by("socket_usb")) == sum(f["kind"] == "bedside" for f in m.furniture)),
    ("R6.4 one 2-way h750 per bedside", all(i["z"] == 750 for i in by("switch_2way"))
     and len(by("switch_2way")) == sum(f["kind"] == "bedside" for f in m.furniture)),
    ("R6.5 desk LAN h850", any(i["z"] == 850 for i in by("lan"))),
    ("R6.6 TV power + LAN h1100", by("tv_power") and all(i["z"] == 1100 for i in by("tv_power"))),
    ("R6.7 worktop h1100, >=150 from sink/hob", all(i["z"] == 1100 for i in by("worktop_socket")) and not near),
    ("R6.8 wet power/lighting IP44", all(i.get("ip") == "IP44" for i in S if i["room"] in wet
                                         and i["system"] in ("power", "lighting"))),
    ("R6.9 one DB, VDP, router", all(len(by(k)) == 1 for k in ("db", "vdp", "router"))),
    ("R6.10 ducted where feature wall + tray (LD, MBR, BR2)", {i["room"] for i in by("ducted")} == {"LD", "MBR", "BR2"}
     and not {i["room"] for i in by("split")} & {"LD", "MBR", "BR2"}),
    ("R6.10 split without a feature wall (BR2 variant)", _split_without_feature()),
    ("R6.11 one fan per bedroom/living", sorted(i["room"] for i in by("fan")) == ["BR2", "LD", "MBR"]),
    ("R6.12 downlights >= 700 from fan", all(Point(d["at"]).distance(fans[d["room"]]) >= 700
                                            for d in by("downlight") if d["room"] in fans)),
    ("R6.13 one cove per cove step and cove dome", len(by("cove")) ==
     sum(sum(1 for s_ in c.get("steps", []) if s_.get("light") == "cove")
         + sum(1 for d_ in c.get("domes", []) if d_.get("light") == "cove") for c in m.ceilings)),
    ("R6.13 design fittings copied", {i["kind"] for i in S if i.get("rule") == "design"} >= {"pendant", "track"}),
    ("R6.12 downlights clear of domes, pendants, tracks", all(
        all(Point(d["at"]).distance(geom.dome_polygon(dm)) >= 300 for c in m.ceilings if c["room"] == d["room"]
            for dm in c.get("domes", []))
        for d in by("downlight"))),
    ("R6.15 overrides applied", any(i.get("source") == "override" for i in S)
     and not any(i["id"] == "SK-BR2-02" for i in S)),
]
for n, ok in checks:
    print(("✓ " if ok else "✗ ") + n)
if near:
    print("  too close:", near)
assert all(ok for _, ok in checks)
print(f"OK: {len(checks)} §6 checks pass")

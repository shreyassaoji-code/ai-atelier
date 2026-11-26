"""Judges' score files (agents/judge.md).   python tests/test_scores.py"""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atelier.scores import panel  # noqa: E402

tmp = Path(tempfile.mkdtemp())
for x in "ABC":
    (tmp / f"design_{x}.json").write_text("{}")


def card(judge, b, f, s, li, bu, winner="A"):
    sc = {}
    for i, x in enumerate("ABC"):
        v = dict(brief=b - i, function=f - i, storage=s, light=li, build=bu)
        sc[x] = dict(v, total=sum(v.values()), why=f"{judge} on {x}")
    return {"judge": judge, "scores": sc, "winner": winner, "must_fix": ["J2 blocks window W5 – shorten to 1800"]}


good = [card("Client", 16, 15, 14, 15, 16), card("Architect", 15, 17, 13, 14, 18), card("Developer", 17, 14, 15, 16, 15)]
checks = []


def run(cards):
    for p in tmp.glob("scores_*.json"):
        p.unlink()
    for i, c in enumerate(cards, 1):
        (tmp / f"scores_{i}.json").write_text(json.dumps(c))
    lines = []
    code, lead = panel(tmp, lines.append)
    return code, lead, "\n".join(lines)


code, lead, txt = run(good)
checks.append(("three valid cards pass, leader A", code == 0 and lead == "A"))
bad = copy.deepcopy(good)
bad[1]["scores"]["B"]["total"] = 99
code, _, txt = run(bad)
checks.append(("wrong total refused", code == 1 and "sum to" in txt))
bad = copy.deepcopy(good)
bad[0]["scores"]["C"]["light"] = 21
code, _, txt = run(bad)
checks.append(("score above 20 refused", code == 1 and "0-20" in txt))
bad = copy.deepcopy(good)
bad[2]["must_fix"] = []
code, _, txt = run(bad)
checks.append(("empty must_fix refused", code == 1 and "must_fix" in txt))
bad = copy.deepcopy(good)
bad[0]["winner"] = "D"
code, _, txt = run(bad)
checks.append(("unknown winner refused", code == 1 and "winner" in txt))
odd = copy.deepcopy(good)
odd[1]["winner"] = "C"
code, _, txt = run(odd)
checks.append(("winner not top total is a warning, not an error", code == 0 and "not this judge's top" in txt))

shutil.rmtree(tmp)
fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

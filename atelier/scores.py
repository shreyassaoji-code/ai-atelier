"""Check the judges' score files and add them up (agents/judge.md).

    python -m atelier.scores projects/<name>

Reads every scores_*.json in the project. Each must give, for every design_<X>.json in the
project, the five rubric scores as integers 0-20, `total` = their sum and a non-empty `why`;
`winner` must be one of the designs and `must_fix` a non-empty list of strings. Errors stop
(exit 1); warnings (winner not the judge's own top total, a 90+ score) are printed.
Then the panel: each design's total per judge, the sum, and the leader.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RUBRIC = ("brief", "function", "storage", "light", "build")


def check_file(path: Path, letters):
    err, warn = [], []
    try:
        d = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path.name}: not valid JSON ({e})"], [], None
    sc = d.get("scores") or {}
    if not d.get("judge"):
        err.append(f"{path.name}: missing 'judge'")
    for x in letters:
        s = sc.get(x)
        if not isinstance(s, dict):
            err.append(f"{path.name}: no scores for {x}")
            continue
        for k in RUBRIC:
            v = s.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 20:
                err.append(f"{path.name}: {x}.{k} = {v!r}, need an integer 0-20")
        if all(isinstance(s.get(k), int) for k in RUBRIC) and s.get("total") != sum(s[k] for k in RUBRIC):
            err.append(f"{path.name}: {x}.total = {s.get('total')!r}, the five scores sum to {sum(s[k] for k in RUBRIC)}")
        if not str(s.get("why") or "").strip():
            err.append(f"{path.name}: {x}.why is empty")
        if isinstance(s.get("total"), int) and s["total"] >= 90:
            warn.append(f"{path.name}: {x} scores {s['total']} (90+ should be rare)")
    for x in sc:
        if x not in letters:
            err.append(f"{path.name}: scores for {x!r}, but there is no design_{x}.json")
    win = d.get("winner")
    if win not in letters:
        err.append(f"{path.name}: winner {win!r} is not one of {', '.join(letters)}")
    elif not err:
        top = max(letters, key=lambda x: sc[x]["total"])
        if sc[win]["total"] < sc[top]["total"]:
            warn.append(f"{path.name}: winner {win} ({sc[win]['total']}) is not this judge's top total "
                        f"({top}, {sc[top]['total']}): say why in must_fix")
    mf = d.get("must_fix")
    if not isinstance(mf, list) or not mf or not all(isinstance(x, str) and x.strip() for x in mf):
        err.append(f"{path.name}: must_fix needs at least one concrete fix (list of strings)")
    return err, warn, d


def panel(root: Path, out=print):
    letters = sorted(p.stem.split("design_", 1)[1] for p in root.glob("design_*.json"))
    files = sorted(root.glob("scores_*.json"))
    if not letters or not files:
        out(f"nothing to check in {root}: {len(letters)} designs, {len(files)} score files")
        return 2, None
    errs, warns, data = [], [], []
    for p in files:
        e, w, d = check_file(p, letters)
        errs += e
        warns += w
        if not e:
            data.append(d)
    for e in errs:
        out(f"  ERROR {e}")
    for w in warns:
        out(f"  warn  {w}")
    if errs:
        out(f"scores ✗ {len(errs)} errors")
        return 1, None
    out("design  " + "  ".join(f"{d['judge'][:10]:>10}" for d in data) + "       sum")
    sums = {}
    for x in letters:
        tot = [d["scores"][x]["total"] for d in data]
        sums[x] = sum(tot)
        out(f"{x:6}  " + "  ".join(f"{t:>10}" for t in tot) + f"  {sums[x]:>8}")
    lead = max(letters, key=lambda x: (sums[x], sum(d["winner"] == x for d in data)))
    votes = sum(d["winner"] == lead for d in data)
    out(f"scores ✓ leader {lead} ({sums[lead]} of {100 * len(data)}; picked by {votes} of {len(data)} judges)")
    return 0, lead


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m atelier.scores")
    ap.add_argument("project", type=Path)
    a = ap.parse_args(argv)
    return panel(a.project)[0]


if __name__ == "__main__":
    sys.exit(main())

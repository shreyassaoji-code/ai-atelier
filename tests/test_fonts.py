"""Fonts are drawn through cached subsets (atelier/draw.py).   python tests/test_fonts.py

No character the sheets use may be lost: every character in the built sample album that the original
font has must be in its subset, and the family names (what the theme matches on) are kept.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fontTools.ttLib import TTFont  # noqa: E402

from atelier import draw  # noqa: E402

draw.font(draw.T.FONT_SANS, 9)                       # builds the index (and the subsets)
pdf = ROOT / "projects" / "sample" / "out" / "album.pdf"
chars = set("±×Ø²·–—→↔▼▲✓Σ°′″…‘’“”€₹√≤≥½¼¾")       # always needed, built album or not
if pdf.exists():
    from pypdf import PdfReader
    for p in PdfReader(str(pdf)).pages:
        chars |= set(p.extract_text() or "")
chars = {c for c in chars if not c.isspace()}
checks = []
for fam, weights in draw._FONT_INDEX.items():
    for w, sub in weights.items():
        orig = next(f for f in draw.FONT_DIR.glob("*.[ot]tf") if TTFont(f, lazy=True)["OS/2"].usWeightClass == w
                    and (TTFont(f, lazy=True)["name"].getDebugName(16) or TTFont(f, lazy=True)["name"].getDebugName(1)) == fam)
        oc, sc = TTFont(orig)["cmap"].getBestCmap(), TTFont(sub)["cmap"].getBestCmap()
        lost = sorted(c for c in chars if ord(c) in oc and ord(c) not in sc)
        checks.append((f"{sub.name}: no used character lost {''.join(lost)}", not lost))
        sn = TTFont(sub)["name"]
        checks.append((f"{sub.name}: family name kept", (sn.getDebugName(16) or sn.getDebugName(1)) == fam))
        checks.append((f"{sub.name}: smaller than the original", sub.stat().st_size < orig.stat().st_size))
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(0 if all(ok for _, ok in checks) else 1)

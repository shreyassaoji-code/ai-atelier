"""Album order, numbering and PDF safety (STANDARDS §2).   python tests/test_album.py

Pages are stubbed with blank A3 sheets so the safety rules are tested fast; the real
sheets are covered by the full build.
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
from pypdf import PdfReader  # noqa: E402

from atelier import album as A  # noqa: E402
from atelier.draw import Sheet  # noqa: E402
from atelier.model import load  # noqa: E402

checks = []

# 1 the code order is the STANDARDS §2 table
md = (ROOT / "agents" / "STANDARDS.md").read_text()
sec = md.split("## 2. Album structure", 1)[1].split("## 2a.", 1)[0]
table = [k for _, _, k in sorted((int(n), a, k) for n, a, k in re.findall(r"^\| (\d+)([a-z]?) \| `([^`]+)` \|", sec, re.M))]
checks.append(("album.ORDER matches STANDARDS §2", table == A.ORDER))

tmp = Path(tempfile.mkdtemp())
proj = tmp / "p"
proj.mkdir()
for f in ("survey.json", "design.json", "services_overrides.json", "project.json"):
    shutil.copy(ROOT / "projects" / "sample" / f, proj / f)
shutil.copy(ROOT / "projects" / "sample" / "services.json", proj / "services.json")
m = load(proj)
names = A.page_names(m, proj)
checks.append(("families expand in data order", [n for n in names if n.startswith("joinery:")] ==
               [f"joinery:{j['id']}" for j in m.joinery]))
checks.append(("room boards follow the presentation plan (client §2)", names.index("room:LD") == names.index("presentation") + 1))

# stub pages: blank A3 sheets carrying their number (and a switch to make one fail)
FAIL = set()


def stub(m_, no, total, name):
    if name in FAIL:
        raise RuntimeError("stub failure")
    sh = Sheet()
    sh.text(20, 20, f"{no:02d} / {total:02d} {name}", None)
    return sh


A.make = stub
A.info = lambda m_, n: (n, "—")
quiet = lambda *a, **k: None  # noqa: E731
total = len(names)
pdf = proj / "out" / "album.pdf"

# 2 complete build: every page, A3, numbered pages and previews
made, failed, verdict = A.build(m, proj, None, dpi=20, log=quiet)
r = PdfReader(str(pdf))
checks.append((f"complete build writes {total} pages", len(r.pages) == total and not failed))
checks.append(("every page is A3 landscape", all(abs(float(p.mediabox.width) - A.A3[0]) < 1 for p in r.pages)))
checks.append(("pages/NN.png for every page", all((proj / "out" / "pages" / f"{i:02d}.png").exists()
                                                  for i in range(1, total + 1))))
checks.append(("contents numbering is NN of total", m.album[6][0] == 7 and len(m.album) == total))

# 3 partial build splices, keeping every page
before = pdf.read_bytes()
made, failed, verdict = A.build(m, proj, ["ceiling"], dpi=20, log=quiet)
r = PdfReader(str(pdf))
i = names.index("ceiling") + 1
checks.append(("partial build keeps all pages", len(r.pages) == total))
checks.append(("partial build replaced only its page", made == [i] and pdf.read_bytes() != before
               and "ceiling" in r.pages[i - 1].extract_text()))

# 4 a failing page never touches album.pdf
before = pdf.read_bytes()
FAIL.add("sections")
made, failed, verdict = A.build(m, proj, None, dpi=20, log=quiet)
checks.append(("a failed page leaves album.pdf as it was", failed and pdf.read_bytes() == before))
made, failed, verdict = A.build(m, proj, ["sections"], dpi=20, log=quiet)
checks.append(("a failed partial page leaves album.pdf as it was", failed and pdf.read_bytes() == before))
FAIL.clear()

# 5 page list changed since the last complete build: a partial build does not splice
(proj / "project.json").write_text('{"exclude": ["dt02"]}')
m = load(proj)
made, failed, verdict = A.build(m, proj, ["ceiling"], dpi=20, log=quiet)
checks.append(("partial build of a changed album leaves album.pdf alone",
               pdf.read_bytes() == before and len(PdfReader(str(pdf)).pages) == total))
# ... while a complete build of the new list is allowed (it is the whole album)
made, failed, verdict = A.build(m, proj, None, dpi=20, log=quiet)
checks.append(("complete build of the new list writes it", len(PdfReader(str(pdf)).pages) == total - 1))
checks.append(("no stale preview past the end", not (proj / "out" / "pages" / f"{total:02d}.png").exists()))

# 6 an unknown page name is refused before anything is written
try:
    A.build(m, proj, ["nonsense"], dpi=20, log=quiet)
    checks.append(("unknown page refused", False))
except ValueError:
    checks.append(("unknown page refused", True))

shutil.rmtree(tmp)
fail = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("ok   " if ok else "FAIL ") + n)
sys.exit(1 if fail else 0)

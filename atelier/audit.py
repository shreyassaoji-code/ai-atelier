"""Token audit: no hex colour or font name may appear outside atelier/theme.py.

Data is not styling: the data contract (agents/SCHEMA.md) lets agents give client colours as "#RRGGBB"
(palette, material and feature colours). Colour values are therefore allowed in project data
(projects/**/*.json), test fixtures (tests/fixtures/**/*.json) and the fenced ```json examples of
agents/SCHEMA.md. Everything else – code, docs, styles – is audited for colours; font names everywhere.

    python -m atelier.audit          # exit 1 and list offenders if any

Font names are read from the theme itself, so renaming a font in theme.py
automatically updates what the audit looks for.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from atelier import theme as T

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "atelier" / "theme.py"
SKIP_DIRS = {".git", "fonts", "out", "__pycache__"}
TEXT_EXT = {".py", ".md", ".json", ".sh", ".txt", ".toml", ".cfg", ".yml", ".yaml", ".css", ".html", ".svg"}

HEX = re.compile(r"(?<![\w&])#(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


def _font_patterns():
    pats = []
    for name in (T.FONT_SERIF, T.FONT_SANS):
        pats.append(re.compile(r"\b" + re.escape(name) + r"\b"))
        first = name.split()[0]
        if first != name:  # the first word of a multi-word family counts too
            pats.append(re.compile(r"\b" + re.escape(first) + r"\b"))
    return pats


def scan():
    fonts = _font_patterns()
    hits = []
    for f in sorted(ROOT.rglob("*")):
        if f == THEME or not f.is_file() or f.suffix not in TEXT_EXT:
            continue
        if SKIP_DIRS & set(f.relative_to(ROOT).parts):
            continue
        rel = f.relative_to(ROOT)
        data_file = f.suffix == ".json" and rel.parts[0] in ("projects",) or \
            (f.suffix == ".json" and rel.parts[:2] == ("tests", "fixtures"))
        in_json = False
        for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            if rel == Path("agents/SCHEMA.md") and line.strip().startswith("```"):
                in_json = line.strip() == "```json"
            if not (data_file or in_json):
                for m in HEX.finditer(line):
                    hits.append((rel, n, "colour", m.group()))
            for p in fonts:
                for m in p.finditer(line):
                    hits.append((f.relative_to(ROOT), n, "font", m.group()))
    return hits


if __name__ == "__main__":
    hits = scan()
    for path, n, kind, s in hits:
        print(f"{path}:{n}: {kind} literal {s!r}")
    print(f"token audit: {len(hits)} literal(s) outside atelier/theme.py")
    sys.exit(1 if hits else 0)

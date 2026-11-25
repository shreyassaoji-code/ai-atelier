# AI Atelier

One floor-plan image in → a full interior working-drawing album (PDF, ~55 A3 sheets) + 3D out.

**AI agents write data (JSON). A Python engine draws everything from it. The AI never draws.**

```
plan image ──► agents (surveyor, designer, services, …) ──► projects/<name>/*.json
                                                              │
                                   atelier/ (Python engine) ◄─┘
                                          │
                                          ├─► out/album.pdf   (A3 sheets)
                                          └─► out/3d          (Blender via bpy)
```

## Structure

- `agents/`: agent briefs and shared standards (STANDARDS, SCHEMA, TEAM, surveyor, designer, judge, reference, services, checker, visualiser)
- `atelier/`: the Python engine, the only code that draws
- `fonts/`: fonts used on the sheets
- `projects/sample/`: sample project

## Setup

```bash
pip install --break-system-packages -r requirements.txt   # bpy needs Python 3.13
python -c "import shapely, matplotlib, pypdf, PIL, numpy, bpy"
```

Rules for working in this repo are in `CLAUDE.md`.

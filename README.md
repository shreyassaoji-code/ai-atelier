# AI Atelier

One floor-plan image in → a full interior working-drawing album (PDF, A3 sheets – 74 for the sample 2BHK) + 3D out.

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

## Commands

```bash
python -m atelier.overlay  projects/<p>                   # survey over your plan (needs plan.png + calibration)
python -m atelier.validate projects/<p>                   # data checks, want 0 errors
python -m atelier.preview  projects/<p> design_A.json     # what the judges see (any design_<X>.json, or design.json)
python -m atelier.services projects/<p>                   # rules engine for points (services.json)
python -m atelier.build    projects/<p>                   # services, 3D, full album
python -m atelier.build    projects/<p> --no-render       # fast, skips 3D
python -m atelier.render3d projects/<p> --features        # feature-wall views (+ design `views` / cameras)
python -m atelier.build    projects/<p> --sheet room:KIT --no-render   # one page, spliced into the album
python -m atelier.check    projects/<p>                   # machine pre-check → out/check.md, out/check.json
```

Measured on the sample (74 sheets, 2 CPU cores, 2026-11-26): `validate` 1 s, `services` 1 s, `preview` 3 s,
`build --no-render` 61 s, `build` 61 s when the 3D frames are current. A frame is rendered again only when
the data, the engine or its camera changed: the sample's 19 white-model frames take 235 s (about 12 s each).
`overlay` needs the plan image: the sample has none, so it says so and skips.

Output per project: `out/album.pdf` (vector, A3, pages in STANDARDS §2 order, numbered `NN / NN`) and
`out/pages/NN.png`. `album.pdf` is only replaced by a complete, checked build; a partial build splices
its pages in or leaves the album alone, so it never loses pages.

Rules for working in this repo are in `CLAUDE.md`.

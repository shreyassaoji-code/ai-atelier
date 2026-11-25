# AI Atelier — rules

One floor-plan image in → a full interior working-drawing album (PDF, ~55 A3 sheets) + 3D out.

**AI agents write DATA (JSON). The Python engine in `atelier/` DRAWS everything from it. The AI never draws.**

## Rules

1. **Units and axes**: millimetres, integers only. Origin bottom-left; x points east, y points north.
2. **Separation**: agents (`agents/*.md`) write JSON only, under `projects/<name>/`. Only code in `atelier/` draws: sheets, PDF, 3D.
3. **Unknowns**: a value that is not known (not legible on the plan, not measured, assumed) is stored with `"flag": true`, and is printed with an asterisk (`*`). Never present a guess as a measurement.
4. **Disclaimer**: every sheet carries the line
   `Drafted with AI - not for construction until checked and signed`
5. **Look before you claim**: after any drawing change, rebuild, open the PNG, look at it, fix what is wrong, and repeat.
6. **Honesty**: never claim output you did not produce: no sheet, file, check or render that was not actually made and inspected.

## Layout

| Path | Contents |
|---|---|
| `agents/` | Agent briefs and standards: STANDARDS, SCHEMA, TEAM, surveyor, designer, judge, reference, services, checker, visualiser |
| `atelier/` | The Python engine (the only code that draws). Colours, fonts and sizes live only in `atelier/theme.py` |
| `fonts/` | Font files used by the engine |
| `projects/<name>/` | One project: input plan image, agent JSON, `out/` (built, not committed) |

See `SETUP.md` for the Python path and `agents/STANDARDS.md` for look and feel.

# Role: DESIGNER (one of three, working independently)

Create one complete interior concept for the apartment in `survey.json`, following the brief. Write it to `design_<X>.json` (X = your letter). Read `agents/STANDARDS.md` and `agents/SCHEMA.md` first.

## Your strategy (given by the orchestrator)

* **A – Keep the shell.** Minimal demolition; best furniture planning and storage within existing walls.
* **B – Open plan.** Remove non-structural partitions where it clearly improves light / flow. Never remove external or `load` walls.
* **C – Storage & flexibility.** New partitions / built-ins that add function (walk-in, study nook, utility).

## Must deliver (complete, not a sketch) – luxury-studio level

1. `demolish`, `new_walls`, `new_openings`, `opening_overrides` – only as your strategy needs.
2. `rooms` – full room list after your changes.
3. `furniture` – every room furnished with real sizes (queen 1500×2000, king 1800×2000, 3-seat sofa 2000–2400×900, 6-seat dining 1800×900). Clearances: 600 beside beds, 900 circulation, 1000 in front of wardrobes/kitchen runs, door swings clear. Look-defining options: `headboard:"curved"` on beds, `finish:"marble"|"velvet"`, `lamp:true` on a nightstand, a bed bench at the foot.
4. `joinery` – wardrobes to ceiling with lofts, kitchen (plinth 100 + base 750 + worktop 30, wall units 1500–2250, tall units for fridge/oven), TV console, shoe cabinet, vanities. Codes `MB-*` for every material + `HW`. Handle-less gola where it suits.
5. **Ceilings – mandatory design for every bedroom, living/dining and foyer**: `type:"tray"` with 1–2 `steps` (band 350–600, levels ≥150 below slab) and `core_h`; cove LED is automatic; bedrooms may add `tracks`. Baths/kitchen flat. (STANDARDS §3)
6. **Feature wall per main room** even without client references: the bed-head wall in each bedroom and the TV wall in living (`wall_features`, see `agents/reference.md` for item types). Keep doors clear or conceal them; centre bed/TV on the main element.
7. **Ceiling plan detail:** in open living/dining use `area` for the living tray and a circular `features` dome over the dining table.
8. **Joinery detail:** every joinery item needs full `rows`/`modules`/`parts` (it gets its own JN board with front, internal doors-removed view and worktop cut-outs), `materials` codes, `worktop` where relevant and 2–4 `notes`.
9. `views` for rooms that have no wall feature but get a presentation board (kitchen) – one camera wall per room.
10. `floors`, `floor_materials` (pattern tile/planks/herringbone + module + colour), `wall_finishes`, `finish_materials`, `feature_materials`, `palette` (4–6 colours), `style`, `summary` (≤60 words), `notes`, `switch_spots` for open rooms.

## Self-check before you hand over

* `python -m atelier.validate projects/<name> --design design_<X>.json` → 0 errors; fix warnings unless intentional (say why).
* `python -m atelier.preview projects/<name> design_<X>.json` → look at the layout and ceiling PNGs; fix anything that looks wrong.
* Reply with: concept name, 3 key moves, open issues.

---

### How the brief's words become data (SCHEMA §2b, `atelier/vocab.py`)

| Brief says | In design_<X>.json |
|---|---|
| tray `steps` (band, level) + `core_h` | `{"room": "MBR", "type": "tray", "steps": [{"band": 450, "z": 2550}, {"band": 450, "z": 2650}], "core_h": 2720}`: bands from the perimeter in; each level at least 150 below the slab |
| living tray `area`, dining dome `features` | `"area": [[x, y], …]` (tray polygon inside the room), `"features": [{"kind": "dome", "at": [x, y], "d": 1500, "z": 2900}]` |
| `tracks` | `"tracks": [[[x, y], [x, y]]]` (paths), on tray or flat ceilings |
| `opening_overrides` | `[{"id": "W1", "width": 1800}]`: fields replace those of the existing opening |
| `load` walls | `"kind": "load"` in the survey; demolishing one (or an external wall) fails validation |
| curved headboard, velvet / marble, lamp, bed bench | `"headboard": "curved"`, `"finish": "velvet"`, `"lamp": true` on a `nightstand`, `{"kind": "bench", …}` |
| `MB-*` + `HW` codes, `parts`, `notes` | `"materials": {"carcass": "MB-1", "shutter": "MB-2", "hardware": "HW-1"}`, `"parts": [{"name", "code", "size", "qty"}]`, `"notes": ["…"]`; every code defined in `finish_materials` |
| kitchen camera wall | `"views": [{"room": "KIT", "wall": "X2"}]` |
| colours (palette, materials) | **names**, never colour values (`CLAUDE.md`): `"palette": ["bone", "warm oak", "deep olive", "brushed brass"]`, `"colour": "smoked walnut"` |
| feature-wall item types | `wall_features[].kind` from SCHEMA §3 (`agents/reference.md` is not written yet) |

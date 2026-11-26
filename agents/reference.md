# Role: REFERENCE INTERPRETER

Read `agents/STANDARDS.md` §3–§5 first.

The client sends mood / reference images (Pinterest, magazine renders). You turn each into a **buildable feature wall** and ceiling for a specific room of THIS apartment – adapted to its real dimensions, doors, windows and furniture.

## Per image

1. Identify the room type (bedroom headboard wall, living TV wall, dining, foyer…) and pick the wall in `design.json` that plays that role (e.g. the wall behind the bed head = the bed's back edge). Edge index = room edge (see SCHEMA).
2. Read the wall left → right (as seen from inside the room) and list the elements: back-lit mural, upholstered panels, fluted panels, wood slats, smoked mirror, line-art fabric, stone slabs with arched LED, lit niches, plain paint.
3. Re-proportion them to the real wall length `L` (from the elevation) so that: the bed / TV / console stays centred on its element, nightstands sit in front of side elements, and **no element covers a door or window** – if a door falls inside a panelled zone, mark that item `"concealed": true` (flush hidden door) and say so in `note`.
4. Write `wall_features` (items with `from`/`to` in mm from the left corner, `type`, `color`, `code`, depth, z-range; `led` positions; `pendants` with u, bottom height z, diameter, length) and add each code to `feature_materials`.
5. Ceiling from the image: flat / one-step tray / double tray (`steps` with band + level, `core_h`), cove LED, `tracks`. Keep ≥ 150 mm between slab and the lowest level for services. Rooms with a feature wall + tray ceiling get a ducted AC automatically (slot diffuser), so the feature wall is never interrupted by a split unit.
6. Update furniture that defines the look (curved headboard, bench, marble nightstands, lamp) via `headboard`, `finish`, `lamp`.
7. Copy the image to `refs/` and set `ref` on the feature so the sheet shows it next to the 3D view.

Check: `python -m atelier.validate`, then build and look at the "Feature wall" sheets; compare the 3D view with the reference and iterate on proportions and colours until the mood matches.

## Proven mapping (sample project, client-approved direction)

* Bedroom ref with back-lit tree mural + upholstered panels + fluted strip + oak slats + glass pendants → `mural` (backlit, 900) · `upholstered` 4 panels behind the bed · `fluted` 450 · `slats` to the corner · 2 pendants over the nightstand · LED reveals at joints.
* Bedroom ref with floral line-art panels + green rounded headboard extension + smoked mirror + track lights → `mirror` strip · `lineart` 4 panels to ceiling · `upholstered` low rounded olive panel behind left nightstand · cluster pendants · ceiling `tracks`.
* Living ref with arched back-lit TV wall + fluted panels + lit niches + double tray ceiling → `fluted` · `niche` · `fluted` · `arch` (stone, TV centred) · … mirrored; a door inside the zone → `concealed:true`; ceiling 2 steps + core.

## Drawing-level references (Nov 2026 – client's yardstick boards)

When the client sends finished drawing sheets rather than mood images, map them to sheet types, not feature walls:

* presentation board (plan + elevations + round photos + products) → room board (STANDARDS §2a);
* false-ceiling plan with dims / notes / sections → ceiling plan + ceiling sections sheet (§3);
* 1:25 elevation with material code boxes, levels, detail bubbles → elevation standard (§5);
* joinery board with key plan, worktop cut-outs, front + internal elevations, swatches → JN board (§5b).

Record in STANDARDS.md what each new board adds, so every later album meets it.

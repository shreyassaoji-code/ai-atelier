# AI Atelier — Standards

## 1. Look and feel

All visual decisions live in **`atelier/theme.py`**. It is the only file in the project that may contain a colour value or a font name; everything else refers to tokens by name (`from atelier import theme as T`, then `T.ACCENT`, `T.SIZES["title"]`, …). `python -m atelier.audit` enforces this and must report 0 literals before any commit.

**Re-branding** means editing `theme.py` only, then rebuilding. No other file changes.

### Colour tokens

| Token | Use |
|---|---|
| `PAPER` | Sheet background, warm paper. Also the fill for anything that must read as "no ink". |
| `INK` | Text, linework, dimension lines. |
| `POCHE` | Cut walls (solid fill). |
| `GREY` | Secondary text: subtitles, areas, sheet total, extension lines, door swing arcs. |
| `MID` | Existing walls on the partition plan (so new work reads first); laying joints on the flooring plan. |
| `LIGHT` | Parapets and low walls below the cut plane. |
| `HAIR` | Hairline rules: title-band rule, strip separator. |
| `ACCENT` | Bronze. Sheet title, sheet number (incl. the numbers in the sheet index), room IDs. Never a material or code colour. |
| `FLAG` (alias `RED`) | Terracotta. Values to verify on site, always with a trailing `*`; the disclaimer line; items to dismantle (dashed outline + hatch, numbered tags); survey walls on the overlay; hot-water runs and wiring drops on services sheets. |
| `BLUE`, `GREEN`, `AMBER` | Services and category colours; wall-finish code bands (`sheets.wf_colours`); base hues for material tints. |

### Material tints (presentation plan)

Floor textures and furniture fills are **mixed at run time from the tokens above** by `atelier/texture.py` (`palette()`), never typed as colour values. `ACCENT` and `FLAG` are never mixed into materials. Changing a token in `theme.py` re-tints every material that uses it.

| Material | Mixed from |
|---|---|
| Oak (planks, herringbone, furniture wood) | `AMBER` with `PAPER` / `INK` |
| Stone tile, worktops, thresholds | `LIGHT`, `MID`, `GREY` |
| Marble | `PAPER`, `LIGHT`, veins `GREY`/`INK` |
| Upholstery, linen | `MID`, `LIGHT`, `PAPER` |
| Rugs | `BLUE`; throws and plants `GREEN` |

### Type tokens

| Token | Use |
|---|---|
| `FONT_SERIF` | Sheet title, sheet number, project name, room names (true small caps, `smcp`). Lining figures. |
| `FONT_SANS` | Everything else: room ID · area line, tracked-caps labels (incl. room names on the presentation and furniture plans), legend, notes, tables, dimensions, opening and item tags. |

Font files live in `fonts/`. Code finds them by the family name stored inside each file, matched against `FONT_SERIF` / `FONT_SANS`. Code never uses a file name or a family name directly.

### Size tokens: `SIZES` (points)

| Key | Use |
|---|---|
| `title` | Sheet title (`FONT_SERIF`, `ACCENT`). |
| `sheet_no` | Sheet number in the strip (`FONT_SERIF`, `ACCENT`); project name on the cover (`FONT_SERIF`, `INK`). |
| `sheet_total` | "/ NN" beside it (`FONT_SANS`, `GREY`). |
| `project` | Project name; room names on plans (`FONT_SERIF` small caps). |
| `legend_head` | Strip and table headings (tracked caps); room names on presentation and furniture plans (tracked caps, 600, `PAPER` halo). |
| `legend` | Legend entries and notes. |
| `caps_label` | Tracked-caps labels: subtitles, field labels (Drawing, Scale…). |
| `dim` | Dimension values, room ID · area, opening tags, FFL lines, scale-bar figures. |

### Page geometry tokens (mm, origin top-left)

| Token | Use |
|---|---|
| `PAGE_W`, `PAGE_H` | A3 landscape page. |
| `DRAW` | `(x0, y0, x1, y1)` drawing area. The title band sits above `y0`. |
| `STRIP_X`, `RIGHT` | Left and right edges of the legend strip. |

### Conventions

- **Tracked caps**: labels are upper-case with hair-space tracking (`draw.tracked`, `Sheet.caps`).
- **Flagged values**: anything not yet verified on site is drawn with `Sheet.value(..., flagged=True)`. It appears in `FLAG` with a trailing `*`, and the legend explains the `*`.
- Line weights are geometry, not brand, and live in `draw.py` (`LW_CUT`, `LW_LINE`, `LW_THIN`, `LW_HAIR`).
- Sheet builders (`atelier/sheets.py`) draw only through `atelier.draw` / `atelier.symbols` and `theme` tokens.
- Every sheet: title band, sheet number `NN / NN`, project fields, Checked / Signed lines, and the line `Drafted with AI - not for construction until checked and signed`. Plan sheets also: legend, north arrow, scale bar.
- Plans: walls cut solid (`POCHE`) with openings cut out; door = leaf at 90° + `GREY` hairline swing arc; window = triple line (frame, glass, frame); opening without shutter = dotted head lines.
- Measured plan: three dimension chains per side (openings, rooms + walls, overall); flagged values in `FLAG` with `*`; full "verify on site" list in the strip.
- Presentation plan: procedural floor per room from `floors[]` + `finishes[]`; soft shadows offset to the bottom-right; furniture in fills; room names in tracked caps with area; no dimensions; legend shows floor swatches.
- Code sheets: flooring `FL-n` (laying joints, direction arrow for planks, joint-centre mark for tiles), wall finishes `WFn` (a band on every face, tags with z range for features), furniture `Fn` (outlines, circled tags, W × D × H schedule).

## 3. Ceilings

Source: brief of 2026-11-25. Values marked **(default)** are Atelier defaults, not from the brief; confirm per project.

| Rule | Requirement (tick or fail) |
|---|---|
| C3.1 | Ceiling plan shows every tray outline (steps, partial trays) and every dome, drawn from `design.json → ceilings[]`. |
| C3.2 | One level tag per area: band `+zzzz`, each step `+zzzz`, the innermost step tagged `core +zzzz`; domes tagged `dome +apex`. Levels are mm above FFL. |
| C3.3 | Every room with steps has a dimension chain across it in x and in y, through the core: wall face → each step edge → wall face. |
| C3.4 | Every room with 2+ downlights has a chain giving the downlight spacing in x and in y, from the wall faces. |
| C3.5 | Notes with leaders: `GYPSUM FALSE CEILING` per room with a false ceiling; `PROVISION FOR COVE LIGHT` per cove; `MAGNETIC TRACK` per track; `LINEAR SLOT DIFFUSER` per AC supply grille. |
| C3.6 | Fittings: downlights, pendants, tracks, domes with diameter `Ø…`, fans drawn at their true sweep (1200) centred, AC supply and return diffusers. |
| C3.7 | Section marks `A–A`, `B–B` from `views[]` (kind `section`): cut line, letter at both ends, arrow in the `look` direction. |
| C3.8 | Sections sheet: each section at the plan scale with walls cut, floor, false ceiling profile and slab; a vertical chain giving **every** level in it (FFL 0, each ceiling level, dome apex, slab soffit) plus level tags. |
| C3.9 | A **1:5** cove detail: RCC slab, suspension rod, GI channel, 12.5 gypsum board, upstand lip, aluminium LED profile with diffuser; dimensioned trough and step heights. |
| C3.10 | Cove geometry **(default)**: trough **150** wide on the raised side of the step edge; upstand **75** or half the step, whichever is less; board **12.5**; GI ceiling section @ **450** c/c; rods @ **1200** c/c; slab **150**; LED **24 V, 2700 K** in aluminium profile with opal diffuser. |
| C3.11 | The slab soffit comes from `levels.soffit`; when flagged it prints with `*` on both sheets. |

## 6. Engineering defaults (services)

`python -m atelier.services projects/` writes `projects/<name>/services.json` from these rules, then applies `services_overrides.json`. Every generated item carries `"rule": "R6.n"`. Heights `hNNN` are mm from FFL to the centre of the device unless stated. Source: brief of 2026-11-25. Values marked **(default)** were not in the brief; they are Atelier defaults and must be confirmed.

| Rule | Requirement (tick or fail) |
|---|---|
| R6.1 | One switchboard per room at **h1200**, **150** from the latch-side jamb of the room's entry door, on the room side. Rooms without a door: at the jamb of their opening or removed-wall stretch. |
| R6.2 | Wet rooms (bath, toilet): switchboard **outside** the room, latch side, h1200. All wet-room devices **IP44**. |
| R6.3 | General sockets **h300**: one per wall face ≥ **1800** long in living, dining, bedrooms and study, at the centre of the longest free stretch (≥ 600, clear of openings and joinery). **(default spacing)** |
| R6.4 | Each bedside: socket + USB at **h600** and a **2-way** switch at **h750**, on the wall behind it; the 2-way switches the room's downlights with the door switch. |
| R6.5 | Each desk: double socket + LAN at **h850** on the wall behind it. |
| R6.6 | Each TV unit: TV power (double socket) + LAN at **h1100** **(default height)**, centred on the unit. |
| R6.7 | Kitchen worktop: socket at **h1100** every **~900** along each base run, none within **150** of a sink or hob module. |
| R6.8 | Wet rooms: geyser point at **h2000** **(default)** on the wall nearest the shower; exhaust in the external ventilator, or ceiling exhaust when the room has no external wall; IP44 socket at **h1100** beside the vanity. Washing machine: IP44 socket **h1100**. |
| R6.9 | Main entry: DB at **h1500** **(default)** on the hinge side, **400** from the jamb; VDP at **h1400** **(default)** on the latch side beyond the switch; router at **h2100** **(default)** beside the DB. |
| R6.10 | AC in living and bedrooms: **ducted** if the room has a feature wall **and** a stepped (tray) ceiling; otherwise **split**. Split: indoor unit top at **h2150** **(default)** on the face opposite the feature wall (or the longest external face), centred on its longest free stretch; outdoor unit outside the nearest external wall. Ducted: unit in the ceiling drop next to an external wall, linear supply along the step, return grille by the unit. AC isolator at **h2200** **(default)** beside a split unit. |
| R6.11 | One **1200** sweep fan centred (polygon centroid) in each bedroom and living room. |
| R6.12 | Downlights on a **1200** grid **(default pitch)** centred on the room, at least **500** from walls, **450** from joinery, **700** from the fan, **300** from ceiling step edges and domes, **500** from pendants, **400** from tracks. |
| R6.13 | One cove light along each ceiling step with `light: cove`, in its trough **75** inside the step edge (C3.10), and one inside each dome with `light: cove`. Design fittings (`ceilings[].lights[]`: pendants, tracks) are copied into `services.json` so they are switched. |
| R6.14 | Plumbing **(default heights)**: basin and sink cold/hot **h550**, waste **h450**; WC cold **h150**, soil at floor; shower mixer **h1000**, head **h2100**, floor trap at its centre; washing machine cold **h1000**, waste **h600**; hot water runs from each geyser to its room's mixers. |
| R6.15 | `services_overrides.json` is applied last: `remove` (ids), `move` (id + new `at`/`z`), `add` (full items). An override naming an unknown id is an error. |

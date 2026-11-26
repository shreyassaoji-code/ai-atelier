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

## 2. Album structure

Source: brief of 2026-11-25. The order is kept in `atelier/album.py` (`ORDER`); `tests/test_album.py` fails if this table and the code disagree. Families (`room:`, `elevation:`, `joinery:`) give one page per item, in data order.

| # | Key | Sheet | One page per |
|---|---|---|---|
| 1 | `cover` | Cover | album |
| 2 | `contents` | Contents and room schedule | album |
| 3 | `measured` | Measured plan | album |
| 4 | `dismantling` | Dismantling plan | album |
| 5 | `partitions` | Partition plan | album |
| 6 | `presentation` | Presentation plan | album |
| 7 | `furniture` | Furniture plan | album |
| 8 | `room:*` | Room boards (§2a) | bedroom, living, kitchen |
| 8a | `feature:*` | Feature wall sheets (§4) | feature wall written by the reference interpreter |
| 9 | `flooring` | Flooring plan | album |
| 10 | `wall_finishes` | Wall finish plan | album |
| 11 | `ceiling` | Ceiling plan | album |
| 12 | `sections` | Ceiling sections | album |
| 13 | `power` | Power plan | album |
| 14 | `lighting` | Lighting plan | album |
| 15 | `switching` | Switching plan | album |
| 16 | `plumbing` | Plumbing plan | album |
| 17 | `ac` | Air-conditioning plan | album |
| 18 | `elevation:*` | Elevations (§5) | `views[]` of kind `elevation` |
| 19 | `dt01` | Details DT-01 (§5a) | album |
| 20 | `dt02` | Details DT-02 (§5a) | album |
| 21 | `joinery:*` | Joinery boards (§5b) | `joinery[]` item |

| Rule | Requirement (tick or fail) |
|---|---|
| A2.1 | Pages follow the table above; `project.json → exclude` may only leave pages out, never reorder them. |
| A2.2 | Every page is numbered `NN / NN` (page / total) and the contents sheet lists every page with its title and scale. |
| A2.3 | `out/album.pdf` is vector, A3 landscape, one page per sheet; `out/pages/NN.png` is the preview of page NN. |
| A2.4 | `album.pdf` is replaced only by a complete build in which every page was made and the merged file checked (page count, A3). A partial build splices its pages into an album made from the same page list, or leaves `album.pdf` untouched. A build never leaves `album.pdf` with fewer pages than its page list. |
| A2.5 | `python -m atelier.build projects/` runs validate → services → 3D → album for every project; `--no-render` skips 3D. |

## 2a. Room boards (RB sheets)

Source: brief of 2026-11-25. **(default)** = Atelier default, not from the brief.

| Rule | Requirement (tick or fail) |
|---|---|
| RB2a.1 | One board per room of type `bedroom`, `master_bedroom`, `living`, `living_dining`, `kitchen`; listed in project.json as `room:<id>`. |
| RB2a.2 | Room plan cropped to the room: clipped to the room polygon plus the bodies of its own walls, nothing from a neighbouring room; scale the largest of **1:40 / 1:50 / 1:60 / 1:75** that fits. Floor texture, furniture with `F` tags, joinery, doors. |
| RB2a.3 | Plan chains: corners and opening jambs on every side; overall on S and W (omitted where it repeats tier 1). Elevation markers 1 and 2 (number in a circle, pointer at the wall), clear of furniture, joinery and camera marks. |
| RB2a.4 | Two key elevations at **1:50**, from `views[]` kind `room_board` (`walls: [id, id]`) when given, otherwise by rule: a wall's content = joinery length ×3/m + feature area ×1.5/m² + windows ×1.2 + openings ×0.6 + furniture within **700** **(default)**; the two highest. **Never a blank wall** (no joinery, feature, opening or furniture): the board fails instead. **Kitchen: elevation 1 is the wall with the most joinery.** |
| RB2a.5 | Each elevation: CAPS call-outs on leaders in a column left of it (wall finish, features, joinery with board/worktop codes, joinery seen end-on, false ceiling, cove, dome, floor); level markers right of it (FFL, FCL, tray, dome, soffit; flagged with `*`); furniture against the wall as silhouettes; one chain (corners, openings, joinery) summing to the face length. |
| RB2a.6 | Three round 3D vignettes A–C from `atelier/render.py`: ONE model of the whole apartment from the data; cameras from `cameras[]` first, else the best convex corners **(default: eye 1350, lens 20 mm, level so verticals stay vertical)**, each looking a different way; camera marks with view cones on the plan. A missing or out-of-date render is drawn as an empty circle marked RENDER NOT PRODUCED, never as a placeholder picture. |
| RB2a.7 | Palette circles with codes (floor, walls, features, joinery board and worktop); legend: room data (area, floor, skirting, walls, features, ceiling levels, soffit, each opening, joinery, light counts; flagged values with `*`) and furniture grouped by type with W×D×H. |
| RB2a.8 | Layout: [plan \| elevations] over a row of vignettes; else [plan \| vignettes] over the elevations; else plan over [elevations \| vignette column]. If none fits at 1:75 the build fails. |

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
| C3.12 | Every false-ceiling level (base, steps, core) is at least **150** below the slab soffit (`E-CEIL`); domes may rise to 50 below. Trays have **1–2** steps with bands **350–600** (designer brief; `W-CEIL` otherwise). Bedrooms, living/dining and foyer get a tray; baths and kitchen are flat. |

## 4. Feature walls

Source: brief of 2026-11-26 (`agents/reference.md`). **(default)** = Atelier default.

| Rule | Requirement (tick or fail) |
|---|---|
| FW4.1 | Each feature wall is written by the reference interpreter as `wall_features[]` with `items` (SCHEMA §2c) on the wall that plays the role: the bed's back edge in a bedroom, the TV wall in living. |
| FW4.2 | Elements run left → right from the left corner as seen from inside, within the wall length `L`, without overlapping (`E-FEATURE`). Types: `mural` `upholstered` `fluted` `slats` `mirror` `lineart` `arch` `niche` `paint` `stone` (and `panelling` `cladding` `wallpaper` `tile` `headboard`). Depths **(default)**: upholstered 60, slats 40, arch 40, fluted 25, mural 20, lineart 20, mirror 8, paint 2. |
| FW4.3 | **No element covers a window.** A door inside a panelled element is a flush concealed door (`concealed: true` on the element): drawn as CONCEALED DOOR in the panel's finish, never left as a visible door in a panelled zone (`E-FEATURE-OPENING`). |
| FW4.4 | The bed or TV stays centred on its element (± 50, `W-FEATURE-CENTRE`); nightstands stand in front of the side elements. No element is hidden behind tall joinery (`W-FEATURE-HIDDEN`). |
| FW4.5 | Light: LED reveals at the joints listed in `led`; a `backlit` element glows at its edges; an `arch` carries an LED line round the arch; `niche`s are lit at the top. Pendants (`u`, `out` **300 (default)**, bottom `z`, `d`, drop) become ceiling fittings of the room. |
| FW4.6 | The ceiling of the room follows §3 (≥ 150 below the slab); a room with a feature wall and a tray ceiling gets ducted AC with a slot diffuser (R6.10), so no split unit interrupts the wall. |
| FW4.7 | One **Feature wall sheet** per feature wall: the wall at **1:25** (1:50 if too long) cropped to the feature + 300, every element called out with its code; the 3D view of the wall rendered from the data beside the client's reference image (`ref`); an element schedule (u, width, z, depth, type, code, colour, extras); swatches; the interpreter's note. A missing render or reference is shown as an empty, labelled frame. |
| FW4.8 | Colours are names (`"color": "sage"`), mixed from theme tokens; codes are added to `feature_materials` / `finishes`. |

## 5. Elevation detail (1:25)

Source: brief of 2026-11-25. No reference sheet received yet: layout to be matched to the studio's kitchen sink wall. **(default)** = Atelier default.

| Rule | Requirement (tick or fail) |
|---|---|
| E5.1 | Every wall face of every room at **1:25**, viewed from inside the room; x measured from the viewer's **left corner**. One row of elevations per sheet. Sheets come from `views[]` (kind `elevation`) first, then one per remaining wall face of every room (`E-<room>-<wall>`); faces under **600** are junction slivers and skipped **(default)**. A face longer than **4600** **(default: what one sheet holds beside its tags)** is split into parts `-p1`, `-p2`… at clear wall (no joinery, opening or service point within 250), with MATCH LINE breaks. Parapet walls are drawn to their `height` (**1050** **(default)**, flagged `*`) and open above; end walls are cut at their own height. |
| E5.2 | Every service point on the face drawn as a **real plate at true size and height** **(default plates: 86 × 86 single, 146 × 86 double/TV, 100 × 110 IP44, DB 350 × 450, VDP 130 × 200)**; label inside: 6A / 16A / DATA / TV / IP44 / VDP / DB. |
| E5.3 | Plumbing: **H** red (`FLAG`), **C** blue (`BLUE`), **D** drain grey (`GREY`), WC soil, mixer above each sink, shower head. |
| E5.4 | Each point dimensioned **twice**: height from FFL to its centre, and a chain from the left corner. |
| E5.5 | A red (`FLAG`) wiring drop from the false ceiling to every electrical point. |
| E5.6 | Material tags with leaders: wall finish `WFn`, feature wall `FWn`, joinery board `MBn`, worktop `WTn`, floor `FL-n`. |
| E5.7 | Joinery modules numbered `J<n>.<module>` in data order; shutters show the swing (dashed, apex at the hinge), drawers their fronts, plinth **100** and worktop **30** (designer brief: plinth 100 + base 750 + worktop 30); sinks show bowl and mixer, hobs and appliances their outline. |
| E5.8 | Vertical code rail (height zones) and horizontal code rail (zones along the wall); finish key with swatches of every code on the sheet. |
| E5.9 | Level markers in metres: `FFL ±0.000`, `FCL +x.xxx`, `SOFFIT +x.xxx` (flagged with `*` when unverified). |
| E5.10 | Skirting drawn **only** on bare wall (not behind joinery, not across openings), at the floor's `skirting` height. |
| E5.11 | Walls cut at both ends in poche, at their real thickness. |
| E5.12 | Detail bubbles, only where the element is on that wall: **1** cove (room has a cove step), **2** wall panel with LED reveal (panelling/fluted feature), **3** skirting (bare wall) → **DT-01**; **4** concealed flush door (door opening), **5** worktop + gola + base unit (kitchen base / vanity), **6** wardrobe section (wardrobe) → **DT-02**. |
| E5.13 | Chains: a vertical level chain, a horizontal module chain and an overall dimension; a room key plan marking the wall and view direction; a points schedule (id, type, height, x). |

### 5a. Details (DT sheets)

| Rule | Requirement (tick or fail) |
|---|---|
| D5a.1 | **DT-01**: 1 cove (1:5), 2 wall panel with LED reveal (1:5), 3 skirting (1:5). **DT-02**: 4 concealed flush door (1:5), 5 worktop + gola + base unit (1:10), 6 wardrobe section (1:10). |
| D5a.2 | Each detail is titled by its bubble (number over sheet), a CAPS title and its scale; numbers match the elevation bubbles (E5.12). |
| D5a.3 | Every material is hatched from one table (concrete, brick, plaster, gypsum, ply, MDF, timber, veneer/laminate, quartz/stone, tile, aluminium, steel); each sheet carries a material key. |
| D5a.4 | Every layer is dimensioned in mm; labels are CAPS on leaders, in a column beside the detail. |
| D5a.5 | Sizes come from the data where it has them (cove levels, skirting height, door width and wall, joinery height/depth/rows, worktop and board codes, ceiling level over a wardrobe); the rest are **(default)**: plaster 12, brick 115, timber ground 25 × 50 @ 450, panel 18, LED reveal 20, door leaf 40, shadow gap 3, carcass 18, back 6, plinth recess 60, gola 30 × 50, floor bed 30. |

### 5b. Joinery boards (JN sheets)

| Rule | Requirement (tick or fail) |
|---|---|
| JB5b.1 | One board per `joinery[]` item, numbered `JN-01…` in data order, titled with the item id, kind and room. |
| JB5b.2 | Key plan with the item filled and an arrow giving the front-elevation view direction. |
| JB5b.3 | Plan: worktop items show the worktop with cut-outs (sink bowl + tap hole Ø35, hob cut-out 560 × 490 **(default)**); other items show door swings and drawer pull-outs. |
| JB5b.4 | Front elevation: modules numbered `J<n>.<m>`, handles or gola as in `handles`, appliances (hob, sink) drawn; module chain, overall width and a height chain. |
| JB5b.5 | Internal elevation with doors removed **(default fit)**: shutter → shelves @ 350; drawer → 3 drawer boxes; sink → bowl, trap, C/D points; hob → hob body + 2 drawers; loft → 1 shelf; open → shelves; wardrobe modules alternate hanging (rail 50 below the shelf, shelf at the row top − 300) and shelves @ 350 with 2 drawers. |
| JB5b.6 | Swatch circles for every finish code on the item (board `MBn`, worktop `WTn`) and its handles. |
| JB5b.7 | Panels: materials (code, name), modules (number, type, width, internal fit), notes. |
| JB5b.8 | Σ module widths = run length, per row; the board prints the check and fails the build if it does not hold. |

## 6. Engineering defaults (services)

`python -m atelier.services projects/` writes `projects/<name>/services.json` from these rules, then applies `services_overrides.json`. Every generated item carries `"rule": "R6.n"`. Heights `hNNN` are mm from FFL to the centre of the device unless stated. Source: brief of 2026-11-25. Values marked **(default)** were not in the brief; they are Atelier defaults and must be confirmed.

| Rule | Requirement (tick or fail) |
|---|---|
| R6.1 | One switchboard per room at **h1200**, **150** from the latch-side jamb of the room's entry door, on the room side; if tall joinery takes the latch side, at the hinge-side jamb. One board serves two rooms when their entries meet (within 400). Rooms without a door: at the jamb of their opening or removed-wall stretch; open-plan rooms may name `switch_spots` (designer). |
| R6.2 | Wet rooms (bath, toilet): switchboard **outside** the room, latch side, h1200. All wet-room devices **IP44**. |
| R6.3 | General sockets **h300**: one per wall face ≥ **1800** long in living, dining, bedrooms and study, at the centre of the longest free stretch (≥ 600, clear of openings and joinery). **(default spacing)** |
| R6.4 | Each bedside: socket + USB at **h600** and a **2-way** switch at **h750**, on the wall behind it; the 2-way switches the room's downlights with the door switch. |
| R6.5 | Each desk: double socket + LAN at **h850** on the wall behind it. |
| R6.6 | TV wall (services brief): TV point **h1100** behind the TV, centred on the TV unit; double socket, LAN and media (HDMI conduit) at **h550** above the console, 250 apart. |
| R6.7 | Kitchen worktop: socket at **h1100** every **~900** along each base run, none within **150** of a sink or hob module. |
| R6.7a | Kitchen (services brief): chimney point **h2200** over each hob; RO point **h1800** beside the kitchen sink, clear of windows; fridge **h300**, oven **16A h300**, microwave **h1600**, dishwasher **16A h300** with cold and drain **h300** **(default heights)** at the modules labelled for them; with no such module, a default on the kitchen's longest free wall (fridge, oven / microwave) or the base module next to the sink (DW), each **flagged** for the designer. Worktop sockets never on a window. |
| R6.8 | Wet rooms: geyser **16A** point at **h2000** on the wall nearest the shower; exhaust in the external ventilator, or ceiling exhaust when the room has no external wall; IP44 socket at **h1100** beside the vanity; **mirror light** IP44 at **h1950** over each vanity. Washing machine: IP44 16A socket **h1100**, cold inlet h1000, drain h600 (R6.14) and a floor trap in front of it. Balcony: one IP44 socket h1100 on its longest free non-parapet wall. |
| R6.9 | Main entry (services brief): DB at **h1800** on the hinge side, **400** from the jamb; VDP at **h1450** on the latch side beyond the switch; router at **h2100** beside the DB. |
| R6.10 | AC in living and bedrooms: **ducted** (`ac_ducted`) if the room has a feature wall **and** a tray ceiling; otherwise **split**. Ducted: unit above the ceiling by an external wall that is **not** the feature wall, outdoor unit outside it; **linear slot diffuser in the ceiling band opposite the feature wall** (20–80 % of that face, midway between wall and step); return grille by the unit. Split: never on a feature wall, never on the wall the bed faces (it would blow at the bed head); external walls first; indoor unit top **h2150** **(default)** centred on the longest free stretch; isolator **h2200** **(default)** beside it; outdoor unit outside the nearest external wall. |
| R6.11 | One **BLDC 1200** sweep fan per bedroom and living room: centred in the room (polygon centroid); in living rooms over the centre of the seating rug (the rug nearest a sofa or armchair). |
| R6.12 | Downlights on a **1200** grid **(default pitch)** centred on the room, at least **500** from walls, **450** from joinery, **700** from the fan, **300** from ceiling step edges and domes, **500** from pendants, **400** from tracks. |
| R6.13 | One cove light along each ceiling step with `light: cove`, in its trough **75** inside the step edge (C3.10), and a **ring cove at r + 90** round each dome with `light: cove`. Design fittings (`ceilings[].lights[]`: pendants, tracks, feature-wall pendants) are copied into `services.json` so they are switched. |
| R6.14 | Plumbing **(default heights)**: basin and sink cold/hot **h550**, waste **h450**; WC cold **h150**, soil at floor; shower mixer **h1000**, head **h2100**, floor trap at its centre; washing machine cold **h1000**, waste **h600**; hot water runs from each geyser to its room's mixers. |
| R6.16 | `python -m atelier.services projects/<name> --check` reports the services review checklist (`agents/services.md`): a point behind a door swing, inside joinery, on a window, behind the TV, or on feature-wall artwork above the skirting zone (h300) outside the nightstand / TV-console zones (`SV-CLASH`, `SV-SWING`); plates closer than 120 (`SV-OVERLAP`); a way in from circulation or outside with no switchboard within reach (`SV-SWITCH`). Each finding suggests a `move` for `services_overrides.json`. |
| R6.15 | `services_overrides.json` is applied last: `remove` (ids), `move` (id + new `at`/`z`), `add` (full items). An override naming an unknown id is an error. |

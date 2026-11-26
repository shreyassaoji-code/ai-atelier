# AI Atelier — data schema

Agents write these files; `atelier/` reads them. Nothing else is input to the engine.

```
projects/<name>/survey.json    existing condition, read from the plan image (surveyor)
projects/<name>/design.json    proposed interior (designer, services, …)
```

## 0. Conventions (apply to every file)

| Rule | Value |
|---|---|
| Units | millimetres, **integers only** (areas in m² are the only decimals) |
| Origin | bottom-left of the plan; **x → east, y → north**; z up from FFL 0 |
| Points | `[x, y]`; polygons are lists of points, **counter-clockwise**, not closed (no repeat of first point) |
| IDs | unique within the merged model; `^[A-Za-z][A-Za-z0-9_-]*$` |
| Wall offsets | distance in mm along a wall's line from its point `a` towards `b` |
| Left / right | relative to a wall's direction, looking from `a` to `b` |
| Facing | `"N" "E" "S" "W"` or integer compass degrees (0 = N, 90 = E) |
| Unknowns | `"flag": true` flags the whole object; `"flag": ["field", …]` flags only those fields. A root `"flag": true` flags the whole file. Flagged values print with `*` and are listed under "verify on site". |
| Notes | any object may carry `"note": "…"` (free text, shown in the verify-on-site list when flagged) |

## 1. survey.json

| Key | Type | Meaning |
|---|---|---|
| `schema` | `"atelier/survey@1"` | |
| `project` | object | `name`, `address`, `source` (plan image file or `null`), `date` (`YYYY-MM-DD`) |
| `levels` | object | `ffl` (0), `ceiling` (finished ceiling), `soffit` (slab underside), `lintel` (door/window head), `sill` (default window sill). `ceiling_height_flag: true` (here or at the root) = `"ceiling"` in `flag` |
| `calibration` | object | `image` (default `plan.png`), then **either** `px_per_mm` + `origin_px` (image pixel of plan `[0, 0]`; plan not rotated) **or** `a_px`, `b_px` (two image points) + `a_mm`, `b_mm` (the same points in plan mm; allows rotation). `image: null` for hand-made plans. |
| `walls[]` | object | `id`, `a`, `b` (ends of the wall body), `t` (thickness), `align`, `kind`, `height` (optional, default `levels.soffit`) |
| `openings[]` | object | `id`, `wall`, `offset` (to the near jamb), `width`, `kind`, `swing`, `hinge`, `sill`, `head` |
| `rooms[]` | object | `id`, `name`, `type`, `poly` (clear internal polygon, face of plaster), `ffl` (optional, default 0), `area_printed` (m², optional: as printed on the plan) |
| `flags[]` | object | site queries not tied to one value: `id`, `ref` (object id or `null`), `note` |

**Walls**: `align` says where the line `a→b` sits in the wall body:
`centre` (body ±t/2 either side), `left` (body lies to the left of the line, so the line is the body's right-hand face), `right` (body lies to the right). An external wall drawn counter-clockwise along its outer face is therefore `left`. The surveyor writes centre-lines (`centre`, split at every junction, origin on the bottom-left corner's centre-line); face lines (`left` / `right`) are equally valid. The body is exactly from `a` to `b`: walls are not extended at the ends, except that where centre-line walls share an end point the engine fills the corner with a square of each wall's thickness (`geom.wall_joints`).

**Openings**: the leaf swings to the `swing` side of the host wall; `hinge` is the jamb at `offset` (`start`) or at `offset + width` (`end`). The hinge point lies on the face of the swing side.

## 2. design.json

| Key | Type | Meaning |
|---|---|---|
| `schema` | `"atelier/design@1"` | |
| `based_on` | string | survey file name |
| `demolish[]` | object | `{"wall": id}` whole wall, `{"wall": id, "from": o, "to": o}` part (offsets), or `{"opening": id}` (opening infilled) |
| `new_walls[]` | wall | as survey walls |
| `new_openings[]` | opening | as survey openings; `wall` may be a new wall |
| `rooms[]` | object | by `id`: overrides survey rooms (any field), or adds a new room (needs `poly`). Design-only field: `wall_finish` (finish code for every wall face of the room unless a `wall_features[]` entry covers it) |
| `sanitary[]` | object | `id`, `room`, `kind`, `at` (centre), `size` `[w, d]`, `facing` (like furniture; validated the same way) |
| `furniture[]` | object | `id`, `room`, `kind`, `at` (centre of box), `size` `[w, d, h]` (w across the front, d front-to-back), `facing` (direction the front faces), `label` |
| `joinery[]` | object | `id`, `room`, `kind`, `wall` (host), `offset`, `width`, `depth`, `z` (bottom, default 0), `height`, `rows[]` (bottom to top), optional `finish` (board code `MBn`), `worktop` (code `WTn`), `handles` (`bar` `knob` `gola` `push`, default `bar`) |
| `joinery[].rows[]` | object | `height`, `modules[]`: `{"w", "type", "label"}`. **Σ module w = joinery width**, **Σ row heights = height** |
| `ceilings[]` | object | `room`, `z` (lowest false-ceiling level, mm above FFL; omit `ceilings` entry = no false ceiling), `steps[]`, `domes[]`, `lights[]` |
| `ceilings[].steps[]` | object | a raised area: `inset` (mm in from the room polygon: full tray) **or** `poly` (any area inside the room: partial tray), `z` (its level), `light` (`none` `cove` `profile`). Steps nest: list outer before inner; a point takes the `z` of the last step containing it. |
| `ceilings[].domes[]` | object | `id`, `at` (centre), `d` (diameter), `z` (apex level), `light` (`none` `cove`). The dome springs from the level around it. |
| `ceilings[].lights[]` | object | design fittings (downlights are placed by rule, STANDARDS §6): `kind`, `at` (pendant, chandelier, spotlight) or `path` (track, strip), `note` |
| `wall_features[]` | object | `id`, `room`, `wall`, `offset`, `width`, `z0`, `z1`, `kind`, `finish` |
| `floors[]` | object | `room`, `finish`, `pattern`, `module` `[w, l]` (plank or tile; mm), `start`, `skirting` (height), `angle` (optional, degrees anticlockwise from east; planks run along it) |
| `finishes[]` | object | `code` (`FL-n` floors, `WFn` walls, `MBn` / `MB-n` joinery boards, `WTn` / `WT-n` worktops, `HW-n` hardware), `kind`, `name`, `maker`, `ref` (catalogue code), optional `tone` (a colour NAME, §2b). No colour values: material tones are mixed from `atelier/theme.py` tokens by `atelier/texture.py`. |
| `views[]` | object | `id`, `kind`, `room` (optional), `wall` (elevations), `scale` (e.g. 25 for 1:25), `title`; sections also `line` `[[x, y], [x, y]]` (cut line) and `look` (`N` `E` `S` `W`: direction the viewer looks); elevations `room` + `wall` (the face of that wall in that room); room boards `room` + optional `walls` `[id, id]` (the two key elevations; omit to let STANDARDS RB2a.4 choose) |
| `cameras[]` | object | `id`, `room`, `eye` `[x,y,z]`, `target` `[x,y,z]`, `lens` (mm, 35 mm equivalent). Room boards use up to three per room before the corner rule (STANDARDS RB2a.6); give `target` z = `eye` z for a level view. |
| `notes[]` | object | `id`, `applies` (`"all"`, room id or view id), `text` |

**Merge** (`atelier/model.py`): survey walls − `demolish` + `new_walls`; survey openings − openings on removed wall parts − demolished openings + `new_openings`; survey rooms updated or extended by design `rooms`.

## 2b. Designer vocabulary (agents/designer.md)

Designers may write a design in the brief's words; `atelier/vocab.py` turns it into §2 on load, so both forms draw the same.

| Brief key | Meaning | Becomes (§2) |
|---|---|---|
| `ceilings[]` `type: "tray"` | `steps[]` `{band, z}` (or `h`) from the perimeter inward, then `core_h`; optional `area` (partial tray polygon), `features[]` `{kind: "dome", at, d, z}`, `tracks[]` (paths) | `z` = first level; one step per further level, `inset` = running band (or `poly` = `area` inset by it); `light: "cove"` unless given; `domes[]`; `lights[]` kind `track` |
| `ceilings[]` `type: "flat"` | `z` (or `h`), optional `tracks[]` | `z`, `lights[]` |
| `opening_overrides[]` | `{id, …fields}` | the existing opening's fields are replaced (after demolition) |
| `floors[]` `{room, material}` + `floor_materials[]` `{code, name, pattern (tile / planks / herringbone …), module, colour}` | | `floors[]` `{room, finish, pattern, module}`, `finishes[]` with `tone` |
| `wall_finishes` `{room: code}` or `[{room, code}]` + `finish_materials[]`, `feature_materials[]` `{code, kind, name, colour}` | | `rooms[].wall_finish`, `finishes[]` with `tone` |
| `joinery[].materials` `{role: code}` or `[codes]`; `parts[]` `{name, code, size, qty}`; `notes[]` | codes `MB-n` boards, `WT-n` worktops, `HW-n` hardware, all in the material lists | `finish` = `shutter` / `front` / first `MB`; parts and notes print on the JN board |
| `furniture[].kind` `nightstand`, `bench` (`bed_bench`, `ottoman`) | options `headboard: "curved"` (beds), `finish: "velvet" \| "marble"`, `lamp: true` (nightstands; no lamp otherwise) | `bedside`, `bench`; options drawn on plans, elevations and renders |
| `views[]` `{room, wall}` (no kind) | the camera wall of a room board | `{kind: "room_board", room, walls: [wall]}`; the second wall by rule |
| `palette[]`, `style`, `summary`, `concept` | named colours (4–6), style line, ≤ 60 words, concept name | kept on the model; printed on the cover |
| `switch_spots[]` `{room, at, z?}` | switch positions in open rooms | switchboards there (rule `design`), replacing the rule's in that room |
| `notes[]` as strings | | `{id: Nn, applies: "all", text}` |

**Colours are names, never values** (`CLAUDE.md`): "warm oak", "deep olive", "bone", "smoked bronze". `texture.named_tone` mixes them from `theme.py` tokens (base words: white/ivory/bone, cream/linen, beige/sand/stone, marble, grey/ash, charcoal/black, oak/honey, walnut/smoked, brass/bronze/gold, terracotta/rust, sage/olive/green, blue/navy/slate, blush/rose; modifiers light/pale, dark/deep, warm, cool, muted). A name with no known word draws in its kind's tone and raises `W-TONE`.

## 2c. Feature walls in the interpreter's form (agents/reference.md, STANDARDS §4)

```json
{"id": "FW2", "room": "MBR", "wall": "X4",
 "items": [{"from": 0, "to": 985, "type": "mural", "code": "WF7", "color": "sage", "backlit": true},
           {"from": 985, "to": 2785, "type": "upholstered", "code": "WF4", "color": "warm linen", "panels": 4, "z1": 1350}],
 "led": [985, 2785],
 "pendants": [{"u": 835, "z": 1300, "d": 220, "length": 1250, "out": 200}],
 "ref": "refs/mbr-mood.jpg", "note": "…"}
```

| Field | Meaning |
|---|---|
| `wall` or `edge` | host: a wall id (its longest face in the room), or a **room edge index**: edges are numbered 1, 2, … counter-clockwise, edge 1 starting at the room polygon's south-west-most vertex (`geom.room_edges`); an edge may span several walls |
| `items[]` | `from`, `to`: mm from the **left corner as seen from inside the room**; `type` (STANDARDS FW4.2); `code` (finish); `color` (a colour name, §2b); optional `depth`, `z0` (0), `z1` (the room's ceiling level), `backlit`, `panels`, `rounded`, `concealed` (doors inside become flush concealed doors), `note` |
| `led[]` | `u` (or `{u, z0, z1}`): vertical LED reveals |
| `pendants[]` | `u`, `out` (mm into the room, default 300), `z` (bottom), `d` (diameter), `length` (drop) |
| `ref` | the client's reference image, in the project or `refs/` |

On load (`atelier/features.py`) each item becomes an engine wall feature (§2 `wall_features`: wall, offset, width, z0, z1, kind = type, finish = code, plus tone, depth, backlit, panels, rounded, concealed, parent); pendants become the room's ceiling fittings.

## 3. Enums (complete lists)

| Field | Values |
|---|---|
| `wall.kind` | `external` `internal` `load` (load-bearing internal: never demolished) `partition` `parapet` `glass` `half` |
| `wall.align` | `centre` `left` `right` |
| `opening.kind` | `door` `double_door` `sliding_door` `opening` `window` `ventilator` |
| `opening.swing` | `left` `right` `none` (sliding doors, openings, windows) |
| `opening.hinge` | `start` `end` `both` (double doors) `none` |
| `room.type` | `living` `dining` `living_dining` `kitchen` `bedroom` `master_bedroom` `bath` `toilet` `utility` `balcony` `foyer` `passage` `study` `puja` `store` `dress` `shaft` |
| `furniture.kind` | `sofa` `armchair` `coffee_table` `side_table` `dining_table` `chair` `bed` `bedside` `bench` `desk` `rug` `console` `tv` `plant` `other` |
| `sanitary.kind` | `wc` `shower` `bathtub` `washing_machine` |
| `joinery.kind` | `wardrobe` `tv_unit` `kitchen_base` `kitchen_wall` `tall_unit` `vanity` `shoe_rack` `crockery` `study_unit` `bookshelf` `puja_unit` `other` |
| `module.type` | `shutter` `glass_shutter` `drawer` `open` `loft` `appliance` `sink` `hob` `panel` `filler` |
| `step.light` | `none` `cove` `profile` |
| `light.kind` | `downlight` `spotlight` `pendant` `chandelier` `strip` `track` `fan` (`track` = magnetic track, with `path`) |
| `wall_feature.kind` | `mural` `upholstered` `fluted` `slats` `mirror` `lineart` `arch` `niche` `paint` `stone` `panelling` `cladding` `wallpaper` `tile` `headboard` |
| `floor.pattern` | `straight` `brick` `diagonal` `herringbone` `chevron` `plank` |
| `floor.start` | `centre` `door` `corner` |
| `finish.kind` | `tile` `stone` `wood` `laminate` `veneer` `paint` `wallpaper` `fabric` `metal` `glass` `mirror` `gypsum` |
| `view.kind` | `plan` `furniture_plan` `rcp` `floor_plan` `electrical` `plumbing` `elevation` `section` `detail` `room_board` `joinery_board` `render` |

## 3a. services.json (written by `atelier.services`, not by agents) and services_overrides.json (written by agents)

`services.json`: `{"schema": "atelier/services@1", "rules": "agents/STANDARDS.md §6", "items": [...]}`. Each item:
`id` (stable: `<PREFIX>-<room>-<nn>`), `system` (`power` `lighting` `switching` `plumbing` `ac`), `kind`, `room`, `at` `[x, y]` (on the wall face for wall devices), `z` (mm, or `null` for ceiling items), `wall` (host wall id or `null`), `rule` (`R6.n`) or `source: "override"`, optional `ip`, `controls` (ids, switches only), `path` (polyline, cove and pipe runs), `size`, `odu` (outdoor unit point), `note`, `flag` (a default the designer must confirm), `also_serves` (switchboards serving a second room).

| `kind` per system | Values |
|---|---|
| power | `socket` `socket_usb` `double_socket` `lan` `media` `tv_power` `worktop_socket` `db` `vdp` `router` `geyser_point` `ac_isolator` `wm_socket` `ip44_socket` `fridge_socket` `oven_16a` `microwave_socket` `dw_socket` `chimney_point` `ro_point` |
| lighting | `downlight` `fan` `cove` `exhaust` `mirror_light` `pendant` `track` |
| switching | `switchboard` `switch_2way` |
| plumbing | `cold` `hot` `waste` `soil` `floor_trap` `geyser` `hot_run` |
| ac | `split` `ducted` (the brief's `ac_ducted`) `odu` `supply_grille` (linear slot diffuser) `return_grille` `refrigerant` |

`services_overrides.json`: `{"remove": [id, ...], "move": [{"id", "at", "z"}], "add": [item, ...]}`.

## 3b. scores_<N>.json (written by each judge, agents/judge.md)

`{"judge": "Architect", "scores": {"A": {"brief", "function", "storage", "light", "build", "total", "why"}, "B": {…}, "C": {…}}, "winner": "A", "must_fix": ["…"]}`: one entry per `design_<X>.json` in the project; each rubric score an integer **0–20**, `total` their sum, `why` text; `winner` one of the designs; `must_fix` at least one concrete fix for the winner. `python -m atelier.scores projects/<name>` checks every file and prints the panel (totals per judge, sum, leader).

## 4. Example: survey.json (one room, abridged)

```json
{
  "schema": "atelier/survey@1",
  "project": {"name": "Example", "address": null, "source": "plan.png", "date": "2026-11-25"},
  "levels": {"ffl": 0, "ceiling": 2750, "soffit": 3000, "lintel": 2100, "sill": 900, "flag": ["ceiling", "soffit"]},
  "calibration": {"image": "plan.png", "a_px": [112, 940], "b_px": [1508, 940], "a_mm": [0, 0], "b_mm": [11400, 0]},
  "walls": [
    {"id": "X1", "a": [0, 0], "b": [4000, 0], "t": 230, "align": "left", "kind": "external"},
    {"id": "X2", "a": [4000, 0], "b": [4000, 3500], "t": 230, "align": "left", "kind": "external"},
    {"id": "X3", "a": [4000, 3500], "b": [0, 3500], "t": 230, "align": "left", "kind": "external"},
    {"id": "X4", "a": [0, 3500], "b": [0, 0], "t": 230, "align": "left", "kind": "external"}
  ],
  "openings": [
    {"id": "D1", "wall": "X1", "offset": 600, "width": 900, "kind": "door", "swing": "left", "hinge": "start", "sill": 0, "head": 2100},
    {"id": "W1", "wall": "X3", "offset": 1000, "width": 1500, "kind": "window", "swing": "none", "hinge": "none", "sill": 900, "head": 2100, "flag": ["sill"]}
  ],
  "rooms": [
    {"id": "R1", "name": "Bedroom", "type": "bedroom", "poly": [[230, 230], [3770, 230], [3770, 3270], [230, 3270]], "area_printed": 10.8}
  ],
  "flags": [{"id": "Q1", "ref": "X2", "note": "Possible column in east wall: confirm on site"}]
}
```

## 5. Example: design.json (abridged)

```json
{
  "schema": "atelier/design@1",
  "based_on": "survey.json",
  "demolish": [{"opening": "W1"}],
  "new_walls": [{"id": "N1", "a": [2400, 230], "b": [2400, 1400], "t": 75, "align": "right", "kind": "partition"}],
  "new_openings": [],
  "rooms": [{"id": "R1", "name": "Guest bedroom"}],
  "furniture": [{"id": "F1", "room": "R1", "kind": "bed", "at": [1500, 2270], "size": [1500, 2000, 450], "facing": "S", "label": "Queen bed"}],
  "joinery": [{"id": "J1", "room": "R1", "kind": "wardrobe", "wall": "X2", "offset": 1300, "width": 1800, "depth": 600, "z": 0, "height": 2700,
               "rows": [{"height": 2100, "modules": [{"w": 600, "type": "shutter"}, {"w": 600, "type": "drawer"}, {"w": 600, "type": "shutter"}]},
                        {"height": 600, "modules": [{"w": 900, "type": "loft"}, {"w": 900, "type": "loft"}]}]}],
  "ceilings": [{"room": "R1", "z": 2550, "steps": [{"inset": 450, "z": 2650, "light": "cove"}], "lights": [{"kind": "downlight", "at": [1000, 1000]}]}],
  "wall_features": [{"id": "WF1", "room": "R1", "wall": "X3", "offset": 400, "width": 2200, "z0": 0, "z1": 1200, "kind": "headboard", "finish": "FIN-W01"}],
  "floors": [{"room": "R1", "finish": "FIN-F01", "pattern": "plank", "module": [200, 1200], "start": "door", "skirting": 100}],
  "finishes": [{"code": "FIN-F01", "kind": "wood", "name": "Oak engineered plank", "maker": null, "ref": null},
               {"code": "FIN-W01", "kind": "fabric", "name": "Upholstered panel", "maker": null, "ref": null}],
  "views": [{"id": "E1", "kind": "elevation", "room": "R1", "wall": "X3", "scale": 25, "title": "Bedroom: bed wall"}],
  "cameras": [{"id": "C1", "room": "R1", "eye": [3400, 500, 1500], "target": [1200, 2800, 1100], "lens": 24}],
  "notes": [{"id": "N1", "applies": "all", "text": "All dimensions in mm."}]
}
```

# Data contract (all agents read this)

Units: **millimetres**. Origin bottom-left of the apartment, **x → east, y → north**. All coordinates are integers. Each project lives in `projects/<name>/` and holds four JSON files. Drawings, 3D and renders are generated from them – agents never draw.

## survey.json — Surveyor

```json
{
 "project": {"name","code","address","client","designer","date","source"},
 "levels": {"ceiling_height": 2750, "ceiling_height_flag": true},
 "calibration": {"image": "plan.png", "px_per_mm": 0.08, "origin_px": [112, 940]},
 "walls": [{"id":"E1","a":[0,0],"b":[11400,0],"t":230,"type":"external|partition|load|parapet","h":null,"flag":false}],
 "openings": [{"id":"D1","wall":"E1","offset":7000,"width":2400,
               "kind":"door|entrance|window|ventilator|balcony_door|sliding_door|opening",
               "h":2100,"sill":0,"side":1,"hinge":"start|end","flag":true}],
 "rooms": [{"id":"R1","name":"Master bedroom","poly":[[115,4258],[3743,4258],...],"kind":"dry|wet|kitchen|circulation|balcony"}],
 "flags": [{"text":"Ceiling height assumed – verify","ref":"levels"}]
}
```

* Walls are **centre-lines** `a→b` with thickness `t`. Split a wall wherever another wall meets it (T-junctions) or wherever demolition may later apply.
* `offset` = distance from `wall.a` along the wall to the first jamb of the opening.
* The wall's **left normal** (rotate a→b by +90°) is side `+1`. `side` = which side a door leaf swings into. `hinge:"start"` = hinge at the jamb nearer `wall.a`.
* Rooms are **clear internal polygons** (wall faces = centre-line ± t/2), counter-clockwise preferred.
* `flag:true` on anything not legible on the source plan (dimension guessed, typical value used). These print in red with `*`.
* `calibration` maps mm → image pixels: `px = origin_px.x + x*px_per_mm`, `py = origin_px.y - y*px_per_mm`. Used by `python -m atelier.overlay` to check walls against the source image.

## design.json — Designers (one per concept), then the winner is copied to `design.json`

```json
{
 "concept":"A", "style":"Warm minimalism", "summary":"one paragraph", "brief":["Q1 → answer", "Q2 → answer"],
 "palette":[["Warm white","#EDE6DB"], ...],
 "demolish":["I7"], "demolish_openings":[],
 "new_walls":[{"id":"N1","a":[..],"b":[..],"t":100,"type":"partition","h":2600,"material":"..."}],
 "new_openings":[{"id":"D8","wall":"N1", ...same as openings}],
 "opening_overrides":[{"id":"D3","hinge":"end"}],
 "rooms":[ ...full room list after the redesign (same format as survey)... ],
 "switch_spots":{"R3":[5300,4343]},
 "furniture":[{"id":"F1","type":"bed","label":"Queen bed 1800×2000","room":"R1","x":115,"y":5370,"w":2100,"d":1800,"facing":"E",
               "headboard":"curved", "finish":"marble|velvet", "lamp":true}],
 "joinery":[{"id":"J1","name":"Wardrobe – master","room":"R1","x":600,"y":4258,"w":2400,"d":600,"facing":"N",
             "materials":{"fronts":"MB-1","carcass":"MB-5","handles":"MB-7"},
             "worktop":{"z":850,"t":30,"from":0},
             "rows":[{"z":0,"h":2700,"depth":600,"start":0,"modules":[
                {"w":800,"parts":[{"h":2100,"type":"door","label":"Long hanging"},{"h":600,"type":"door","label":"Loft"}]},
                {"w":800,"type":"drawers","n":3}]}],
             "notes":["..."]}],
 "materials":{"MB-1":"Oak veneer ...","HW":"hardware note"},
 "floor_materials":{"FL-1":{"name":"...","pattern":"tile|planks|herringbone","color":"#D9BE95","module":[600,120]}},
 "floors":{"R1":"FL-1"},
 "finish_materials":{"WF-1":{"name":"...","color":"#EDE6DB"}},
 "wall_finishes":{"R1":[{"code":"WF-1","edges":"all"},{"code":"WF-5","edges":[3]}]},
 "ceilings":[{"room":"R3","type":"flat|tray|exposed","h":2600,
              "steps":[{"band":600,"h":2550},{"band":500,"h":2650}],"core_h":2720,"tracks":[[x1,y1,x2,y2]],"material":"",
              "area":[x0,y0,x1,y1], "features":[{"x":..,"y":..,"r":750,"h":2900}]}],
 "views":[{"id":"V5","room":"R5","edge":1,"name":"Kitchen – sink wall"}],
 "cameras":[{"room":"R3","pos":[x,y,1450],"target":[x,y,1050],"lens":18}],
 "wall_features":[{"id":"FW1","room":"R1","edge":3,"name":"Master bedroom – headboard wall","ref":"ref_master.jpg","z1":2600,
   "items":[{"from":0,"to":900,"type":"mural|upholstered|fluted|slats|mirror|lineart|arch|niche|plain","code":"FW1","color":"#EFE2CC",
             "depth":60,"z0":0,"z1":2600,"panels":4,"pitch":45,"shelves":5,"backlit":true,"round":false,"concealed":false,
             "tv":{"w":1450,"h":820,"z":1250}}],
   "led":[900], "pendants":[{"u":3080,"z":1350,"d":90,"h":320}], "note":"..."}],
 "feature_materials":{"FW-1":"Back-lit printed fabric panel ..."},
 "notes":["general notes printed on sheet 2"]
}
```

* **Furniture & joinery footprints are axis-aligned boxes**: `x,y` lower-left, `w` along x, `d` along y. `facing` = N/S/E/W, the direction the *front* looks (foot of the bed, seat of the sofa, cabinet doors). The *back* sits on the opposite side – put it on the wall face.
* Furniture `type` values the engine draws: bed, nightstand, sofa, armchair, coffee_table, side_table, dining_table, chair, desk, rug, plant, wc, basin, shower, fridge, washing_machine, bench, tv_unit, island. Unknown types draw as a labelled box.
* Joinery: modules in a row are listed along the back line in increasing x (for N/S facing) or increasing y (for E/W facing). Module widths of a row must sum to the run length (`w` for N/S facing, `d` for E/W). Part / module types: door, drawers (n), open, shelf, sink, hob (use label "Hob"), hood, oven, appliance, fridge, dishwasher, panel, mirror, none (gap, e.g. over a window).
* Ceilings: `area` limits the tray to part of the room (the rest stays at the first step level); `features` adds a circular dome / cove (radius r, level h) with its own cove LED ring – the services engine keeps downlights out of it.
* `views`: extra 3D feature-camera views for rooms without a wall feature (kitchen, study). They render to `out/renders/fw_<id>.png` and supply the circular vignettes of that room's presentation board.
* Room edges are numbered from the polygon's first vertex in counter-clockwise order (rect starting lower-left: 0 = south, 1 = east, 2 = north, 3 = west).

## services.json — generated by `python -m atelier.services`; edited only via services_overrides.json

```json
{"remove":["E12"], "move":[{"id":"E07","x":3743,"y":6900,"h":1100}],
 "add":{"electrical":[{"id":"E90","type":"socket_double","room":"R3","x":...,"y":...,"h":300,"note":"Floor lamp"}],
        "lighting":[], "switches":[], "plumbing":[], "hvac":[]}}
```

HVAC types: `ac_indoor` (split, wall unit) and `ac_ducted` (x1,y1,x2,y2 slot diffuser in the ceiling band) – the engine chooses ducted automatically for rooms with a feature wall + tray ceiling. Point types – electrical: socket, socket_double, socket_usb, power16, socket_ip, tv, data, vdp, db, exhaust, switch. Lighting: downlight, pendant, wall_light, strip (x,y,x2,y2, shape line|rect), fan. Plumbing: cold, hot, drain, drain_wc, mixer, shower_head, floor_trap.

### How the engine reads the contract (`atelier/contract.py`, applied on load)

| Contract | Resolved form (sections below) |
|---|---|
| wall `type` partition / external / load / parapet, `h` | `kind` internal / external / load / parapet, `height`; `align` centre |
| opening `h` | the opening's own height: `head = sill + h` |
| `side` +1 / −1 | `swing` left / right of the wall's a→b line; windows, openings, sliding doors: none |
| `entrance`, `balcony_door` | `door` (the entrance keeps `entrance: true` for the DB / VDP rule R6.9) |
| room `kind` | room `type` read from the **name** first (master bed → master_bedroom, living, kitchen, bath, toilet, balcony, dress, foyer, study, puja …), else from `kind` (wet → bath, kitchen, circulation → passage, balcony, dry → bedroom) – the latter is reported as **W-CONTRACT** |
| `levels.ceiling_height` (+ flag) | `levels.soffit` and `levels.ceiling` (+ flags) |
| furniture box `x, y, w, d, facing` | `at` (centre), `size` [across the front, along facing, height]; heights by type unless `h` is given; wc / basin / shower / bathtub / washing_machine → `sanitary[]` |
| joinery box + `rows` | one item on the wall whose face lies behind the box (`wall`, `offset` from wall.a, `width`, `depth`, `z`, `height`); rows that touch in z with the same `start`, run and `depth` merge into one item whose `parts` become horizontal bands; a row at its own height or depth (wall units) becomes its own item `J1-2`; `kind` from `name`; no wall behind it → a labelled box + W-CONTRACT |
| part types | door → shutter (label "Loft" → loft), drawers → drawer, open / shelf → open, hood / oven / fridge / dishwasher → appliance with that label, mirror → panel, none → filler |
| `materials` / `floor_materials` / `finish_materials` / `feature_materials` dicts | finishes; `#RRGGBB` colours are used as given |
| `floors {room: code}`, `wall_finishes {room: [{code, edges}]}` | floors[]; `edges: "all"` → the room's wall finish, an edge list → a full-height finish on that wall |
| ceiling `tracks [x1,y1,x2,y2]`, `area [x0,y0,x1,y1]`, `features {x,y,r,h}`, `exposed` | track paths, a partial-tray outline, domes; `exposed` → no false ceiling |
| `views {id, room, edge}` | a design camera square-on to that edge, frame `fw_<id>.png`, first vignette of the room board |
| `cameras {room, pos, target, lens}` | a design camera; a tilted target is levelled (verticals stay vertical, RB2a.6) and reported |
| wall feature item `plain`, `round`, `tv`, pendant `h` | `paint`, `rounded`, a TV panel centred on the item, pendant `length` |
| overrides `move {x, y, h}`, `add {system: [...]}` | `at`, `z`; systems → power / lighting / switching / plumbing / ac; power16 → socket_16a, socket_ip → ip44_socket, tv → tv_power, data → lan, switch → switchboard, drain → waste, drain_wc → soil, ac_indoor → split, ac_ducted → supply_grille |

Integers: a centre-line wall of odd thickness (115) has faces at ±57.5; room polygons may overlap it by up to 1 mm on average (not an E-ROOM-WALL). `python -m atelier.contract export projects/<name> OUT/` writes any project in contract form.

---

# Engine reference — the resolved form

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

## 3c. out/check.json (drafted by `atelier.check`, completed by the checker, agents/checker.md)

| field | type | rule |
|---|---|---|
| `must_fix[]`, `should_fix[]` | object | `sheet` (album page number, or null when no single page), `issue`, `fix` (the JSON field to change and, when known, to what); `"by": "machine"` marks the pre-check's items, which a re-run replaces |
| `verify_on_site[]` | string | every flagged value (survey, design, services defaults) plus the checker's own |
| `verdict` | enum | `ready` · `ready after fixes` · `not ready`; `verdict_by: "checker"` keeps it across re-runs. `ready` needs an empty `must_fix` |
| `look[]` | string | written by the machine: what it could not measure, with pages |

Check with `python -m atelier.check projects/<name> --validate`.

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

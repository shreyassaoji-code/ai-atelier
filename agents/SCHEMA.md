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
| `finishes[]` | object | `code` (`FL-n` floors, `WFn` walls, `MBn` joinery boards, `WTn` worktops), `kind`, `name`, `maker`, `ref` (catalogue code). No colour values: material tones are mixed from `atelier/theme.py` tokens by `atelier/texture.py`. |
| `views[]` | object | `id`, `kind`, `room` (optional), `wall` (elevations), `scale` (e.g. 25 for 1:25), `title`; sections also `line` `[[x, y], [x, y]]` (cut line) and `look` (`N` `E` `S` `W`: direction the viewer looks); elevations `room` + `wall` (the face of that wall in that room); room boards `room` + optional `walls` `[id, id]` (the two key elevations; omit to let STANDARDS RB2a.4 choose) |
| `cameras[]` | object | `id`, `room`, `eye` `[x,y,z]`, `target` `[x,y,z]`, `lens` (mm, 35 mm equivalent). Room boards use up to three per room before the corner rule (STANDARDS RB2a.6); give `target` z = `eye` z for a level view. |
| `notes[]` | object | `id`, `applies` (`"all"`, room id or view id), `text` |

**Merge** (`atelier/model.py`): survey walls − `demolish` + `new_walls`; survey openings − openings on removed wall parts − demolished openings + `new_openings`; survey rooms updated or extended by design `rooms`.

## 3. Enums (complete lists)

| Field | Values |
|---|---|
| `wall.kind` | `external` `internal` `partition` `parapet` `glass` `half` |
| `wall.align` | `centre` `left` `right` |
| `opening.kind` | `door` `double_door` `sliding_door` `opening` `window` `ventilator` |
| `opening.swing` | `left` `right` `none` (sliding doors, openings, windows) |
| `opening.hinge` | `start` `end` `both` (double doors) `none` |
| `room.type` | `living` `dining` `living_dining` `kitchen` `bedroom` `master_bedroom` `bath` `toilet` `utility` `balcony` `foyer` `passage` `study` `puja` `store` `dress` `shaft` |
| `furniture.kind` | `sofa` `armchair` `coffee_table` `side_table` `dining_table` `chair` `bed` `bedside` `desk` `rug` `console` `tv` `plant` `other` |
| `sanitary.kind` | `wc` `shower` `bathtub` `washing_machine` |
| `joinery.kind` | `wardrobe` `tv_unit` `kitchen_base` `kitchen_wall` `tall_unit` `vanity` `shoe_rack` `crockery` `study_unit` `bookshelf` `puja_unit` `other` |
| `module.type` | `shutter` `glass_shutter` `drawer` `open` `loft` `appliance` `sink` `hob` `panel` `filler` |
| `step.light` | `none` `cove` `profile` |
| `light.kind` | `downlight` `spotlight` `pendant` `chandelier` `strip` `track` `fan` (`track` = magnetic track, with `path`) |
| `wall_feature.kind` | `panelling` `fluted` `cladding` `wallpaper` `paint` `tile` `stone` `mirror` `niche` `headboard` |
| `floor.pattern` | `straight` `brick` `diagonal` `herringbone` `chevron` `plank` |
| `floor.start` | `centre` `door` `corner` |
| `finish.kind` | `tile` `stone` `wood` `laminate` `veneer` `paint` `wallpaper` `fabric` `metal` `glass` `mirror` `gypsum` |
| `view.kind` | `plan` `furniture_plan` `rcp` `floor_plan` `electrical` `plumbing` `elevation` `section` `detail` `room_board` `joinery_board` `render` |

## 3a. services.json (written by `atelier.services`, not by agents) and services_overrides.json (written by agents)

`services.json`: `{"schema": "atelier/services@1", "rules": "agents/STANDARDS.md §6", "items": [...]}`. Each item:
`id` (stable: `<PREFIX>-<room>-<nn>`), `system` (`power` `lighting` `switching` `plumbing` `ac`), `kind`, `room`, `at` `[x, y]` (on the wall face for wall devices), `z` (mm, or `null` for ceiling items), `wall` (host wall id or `null`), `rule` (`R6.n`) or `source: "override"`, optional `ip`, `controls` (ids, switches only), `path` (polyline, cove and pipe runs), `size`, `odu` (outdoor unit point), `note`.

| `kind` per system | Values |
|---|---|
| power | `socket` `socket_usb` `double_socket` `lan` `tv_power` `worktop_socket` `db` `vdp` `router` `geyser_point` `ac_isolator` `wm_socket` `ip44_socket` |
| lighting | `downlight` `fan` `cove` `exhaust` |
| switching | `switchboard` `switch_2way` |
| plumbing | `cold` `hot` `waste` `soil` `floor_trap` `geyser` `hot_run` |
| ac | `split` `ducted` `odu` `supply_grille` `return_grille` `refrigerant` |

`services_overrides.json`: `{"remove": [id, ...], "move": [{"id", "at", "z"}], "add": [item, ...]}`.

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

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

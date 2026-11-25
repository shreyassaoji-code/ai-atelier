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
| `MID` | Window frame and sill lines. |
| `LIGHT` | Light tints and backgrounds of panels. |
| `HAIR` | Hairline rules: title-band rule, strip separator. |
| `ACCENT` | Bronze. Sheet titles, sheet number, room IDs. Nothing else. |
| `FLAG` (alias `RED`) | Terracotta. Values to verify on site, always with a trailing `*`; also hot-water runs and wiring drops on services sheets. |
| `BLUE`, `GREEN`, `AMBER` | Services and category colours (cold water, drainage/planting, lighting and similar). |

### Type tokens

| Token | Use |
|---|---|
| `FONT_SERIF` | Sheet title, sheet number, project name, room IDs. Lining figures. |
| `FONT_SANS` | Everything else: tracked-caps labels, legend, notes, dimensions. |

Font files live in `fonts/`. Code finds them by the family name stored inside each file, matched against `FONT_SERIF` / `FONT_SANS`. Code never uses a file name or a family name directly.

### Size tokens: `SIZES` (points)

| Key | Use |
|---|---|
| `title` | Sheet title (`FONT_SERIF`, `ACCENT`). |
| `sheet_no` | Sheet number in the strip (`FONT_SERIF`, `ACCENT`). |
| `sheet_total` | "/ NN" beside it (`FONT_SANS`, `GREY`). |
| `project` | Project name; room IDs on plans (`FONT_SERIF`). |
| `legend_head` | Strip headings: LEGEND, NOTES (tracked caps). |
| `legend` | Legend entries and notes. |
| `caps_label` | Tracked-caps labels: subtitles, room names, scale note. |
| `dim` | Dimension values and room areas. |

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
- Sheet modules (`atelier/sheets/*.py`) draw only through `atelier.draw` helpers and `theme` tokens.

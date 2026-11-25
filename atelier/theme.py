"""Design tokens: the only place colours, fonts and sizes are defined."""
PAPER = "#F7F4EE" # sheet background
INK, POCHE = "#2A2826", "#2A2826" # text, linework, cut walls
GREY, MID, LIGHT, HAIR = "#8C867C", "#C9C1B4", "#E6E0D5", "#BDB4A6"
ACCENT = "#9C7A54" # bronze: titles, room IDs
FLAG = RED = "#B0533C" # verify-on-site *, hot water, wiring drops
BLUE, GREEN, AMBER = "#4F7396", "#6F7F5C", "#C4934A"
FONT_SERIF = "Cormorant Garamond" # files in fonts/
FONT_SANS = "Inter"
SIZES = dict(title=21, sheet_no=30, sheet_total=9, project=9.5,
legend_head=5.4, legend=5.2, caps_label=4.4, dim=4.4)
PAGE_W, PAGE_H = 420, 297 # A3 landscape, mm
DRAW = (16, 36, 328, 276) # drawing area
STRIP_X, RIGHT = 336, 406 # legend strip

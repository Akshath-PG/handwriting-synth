"""Geometry of the template page. Everything is defined in millimetres on an A4 sheet and
converted to pixels at 300 dpi (2480 x 3508) after the photo has been straightened."""
MM = 300.0 / 25.4
PAGE_W, PAGE_H = 2480, 3508

# four black squares used to straighten the photo: (centre x, centre y, side) in mm. TL is the big one.
MARKERS = {'TL': (13, 13, 15), 'TR': (197, 13, 9), 'BR': (197, 284, 9), 'BL': (13, 284, 9)}

GX0, GY0 = 14, 28          # top-left of the grid
COLS, ROWS = 7, 8
CW, CH = 26, 30            # one box
LABEL_H = 6                # strip at the top of a box that holds the printed label
BASE = 15.0                # baseline is this far below the writing area top
PER_PAGE = COLS * ROWS


def px(v):
    return int(round(v * MM))


def marker_centres_px():
    return [(MARKERS[k][0] * MM, MARKERS[k][1] * MM) for k in ('TL', 'TR', 'BR', 'BL')]


def cell_mm(i):
    r, c = divmod(i, COLS)
    return GX0 + c * CW, GY0 + r * CH, CW, CH


def write_rect_px(i, inset=1.0):
    """(x0, y0, x1, y1) of the area a character may occupy."""
    x, y, w, h = cell_mm(i)
    return px(x + inset), px(y + LABEL_H + 0.5), px(x + w - inset), px(y + h - inset)


def baseline_px(i):
    x, y, w, h = cell_mm(i)
    return px(y + LABEL_H + BASE)

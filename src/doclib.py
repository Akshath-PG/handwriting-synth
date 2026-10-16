import math, os, cv2, numpy as np
from hw_render import *
from PIL import Image
from imgio import imwrite

OUTP = D + 'pages/'
os.makedirs(OUTP, exist_ok=True)
CAPPX = 46
S0 = CAPPX / CAP
LEFT, RIGHT = 330, 2380
PITCH = 98
TOPY = 280
BOTTOM = 3280


class Doc:
    def __init__(self):
        self.n = 0
        self.files = []
        self.page = None
        self.new_page(first=True)

    # ---------- pages ----------
    def new_page(self, first=False):
        if self.page is not None:
            self.finish()
        self.n += 1
        self.page = Page(seed=10 + self.n)
        self.pen = Pen(self.page, cap=CAPPX, jitter=1.0, seed=100 + self.n)
        self.page.pencil_line(285, 110, 285, 3420, width=2)
        self.y = TOPY if not first else 330

    def finish(self):
        pen = self.pen
        self.pen.run(str(self.n), 2300, 3440, S0 * 0.8)
        out = np.clip(self.page.img, 0, 255).astype(np.uint8)
        path = OUTP + 'page_%02d.jpg' % self.n
        imwrite(path, cv2.cvtColor(out, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
        self.files.append(path)
        self.page = None

    def close(self):
        self.finish()
        ims = []
        for f in self.files:
            with Image.open(f) as im:
                ims.append(im.convert('RGB'))
        return ims

    def need(self, h):
        if self.y + h > BOTTOM:
            self.new_page()

    # ---------- text ----------
    def wob(self):
        return math.sin(self.y / 260.0) * 4 + self.pen.r.gauss(0, 2)

    def line(self, text, x=None, scale=1.0, raw=False, dy=0):
        x = LEFT if x is None else x
        self.pen.run(text, x + self.pen.r.gauss(0, 3), self.y + self.wob() + dy, S0 * scale, raw=raw)

    def para(self, text, indent=0, prefix=None, scale=1.0, after=10, pitch=PITCH, raw=False, hang=None):
        pen = self.pen
        maxw = RIGHT - LEFT - indent - 20
        lines = pen.wrap(text, maxw, S0 * scale, raw)
        for i, ln in enumerate(lines):
            self.need(pitch)
            if i == 0 and prefix:
                self.pen.run(prefix, LEFT + indent - 85 if hang is None else LEFT + hang, self.y + self.wob(), S0 * scale)
            self.pen.run(ln, LEFT + indent + self.pen.r.gauss(0, 3), self.y + self.wob(), S0 * scale, raw=raw)
            self.y += pitch * scale
        self.y += after

    def bullet(self, text, indent=100, mark='-', scale=1.0, after=8):
        self.para(text, indent=indent, prefix=mark, scale=scale, after=after, hang=indent - 70)

    def numbered(self, n, text, indent=110, after=8):
        self.para(text, indent=indent, prefix='%d.' % n, after=after, hang=indent - 90)

    def head(self, text, scale=1.3, after=40, underline=True):
        self.need(PITCH * 2.2)
        self.y += 30
        w = self.pen.width(text, S0 * scale)
        self.pen.run(text, LEFT, self.y + self.wob(), S0 * scale)
        if underline:
            self.page.line(LEFT, self.y + 20, LEFT + w, self.y + 20 + self.pen.r.gauss(0, 2), width=4)
        self.y += PITCH * 1.1 + after - 10

    def subhead(self, text, after=14):
        self.head(text, scale=1.12, after=after)

    def label(self, text, after=0):
        """underlined run-in label such as 'Eq.1: self-loops.'"""
        self.need(PITCH * 3.2)
        w = self.pen.width(text, S0)
        self.pen.run(text, LEFT, self.y + self.wob(), S0)
        self.page.line(LEFT, self.y + 18, LEFT + w, self.y + 18 + self.pen.r.gauss(0, 1.5), width=3)
        self.y += PITCH + after

    # ---------- formulas ----------
    def formula(self, text, extra=0, center=True, scale=1.0, above=50, below=60):
        self.need(PITCH + above + below + extra)
        self.y += above
        w = self.pen.width(text, S0 * scale)
        x = (LEFT + RIGHT) / 2 - w / 2 if center else LEFT + 120
        x = max(x, LEFT)
        self.pen.run(text, x, self.y + self.wob(), S0 * scale)
        self.y += PITCH * 0.8 + below + extra

    # ---------- tables ----------
    def table(self, colw, rows, scale=0.88, header=True, pad=26, rowmin=84):
        pen = self.pen
        s = S0 * scale
        total = sum(colw)
        x0 = LEFT
        # prepare wrapped cells
        wrapped = []
        for r in rows:
            cells = []
            for ci, c in enumerate(r):
                cells.append(pen.wrap(c, colw[ci] - 2 * pad, s))
            wrapped.append(cells)
        cp = PITCH * 0.84 * scale / 0.88
        heights = [max(max(len(c) for c in cells) * cp + 30, rowmin) for cells in wrapped]
        need = sum(heights) + 40
        if need < 1700:
            self.need(need)
        self.y += 10
        top = self.y
        ycur = top
        for ri, cells in enumerate(wrapped):
            hrow = heights[ri]
            if ycur + hrow > BOTTOM and ri > 0:
                # close the table on this page, continue on the next
                self._table_grid(x0, top, colw, ycur)
                self.new_page()
                ycur = self.y
                top = ycur
            for ci, lines in enumerate(cells):
                cx = x0 + sum(colw[:ci]) + pad
                for li, ln in enumerate(lines):
                    self.pen.run(ln, cx, ycur + 20 + 0.78 * cp + li * cp + self.pen.r.gauss(0, 2), s)
            ycur += hrow
            if ri == 0 and header:
                self.page.line(x0, ycur, x0 + total, ycur, width=5, wobble=0.6)
            elif ri < len(wrapped) - 1:
                self.page.line(x0, ycur, x0 + total, ycur, width=2, wobble=0.6)
        self._table_grid(x0, top, colw, ycur)
        self.y = ycur + 90

    def _table_grid(self, x0, top, colw, bottom):
        total = sum(colw)
        self.page.line(x0, top, x0 + total, top, width=4, wobble=0.6)
        self.page.line(x0, bottom, x0 + total, bottom, width=4, wobble=0.6)
        xx = x0
        self.page.line(xx, top, xx, bottom, width=4, wobble=0.6)
        for w in colw:
            xx += w
            self.page.line(xx, top, xx, bottom, width=3, wobble=0.6)

    # ---------- code ----------
    def code(self, lines, cap=40, pitch=80, indent_px=64, raw=True):
        pen = self.pen
        s = cap / CAP
        for ln in lines:
            sp = len(ln) - len(ln.lstrip(' '))
            lvl = sp / 4.0
            text = ln.strip()
            maxw = RIGHT - LEFT - lvl * indent_px - 10
            parts = pen.wrap(text, maxw, s, raw=raw) if text else ['']
            for pi, part in enumerate(parts):
                self.need(pitch)
                xx = LEFT + 10 + lvl * indent_px + (2 * indent_px * 0.5 if pi else 0)
                if part:
                    self.pen.run(part, xx + self.pen.r.gauss(0, 2), self.y + self.wob() * 0.6, s, raw=raw)
                self.y += pitch if (part or text == '') else pitch
            if not text:
                self.y -= pitch * 0.35
        self.y += 20

    # ---------- drawing helpers ----------
    def wbox(self, x, y, w, h, wob=1.6, width=4):
        P = self.page
        P.line(x, y, x + w, y, width=width, wobble=wob)
        P.line(x + w, y, x + w, y + h, width=width, wobble=wob)
        P.line(x + w, y + h, x, y + h, width=width, wobble=wob)
        P.line(x, y + h, x, y, width=width, wobble=wob)

    def arrow(self, x0, y0, x1, y1, width=4):
        P = self.page
        P.line(x0, y0, x1, y1, width=width, wobble=1.0)
        ang = math.atan2(y1 - y0, x1 - x0)
        for da in (2.7, -2.7):
            P.line(x1, y1, x1 + 32 * math.cos(ang + da), y1 + 32 * math.sin(ang + da), width=width, wobble=0.4)

    def center_text(self, lines, cx, cy, scale=0.78, pitch=62):
        pen = self.pen
        n = len(lines)
        for i, t in enumerate(lines):
            w = pen.width(t, S0 * scale)
            yy = cy - (n - 1) * pitch / 2 + i * pitch + 0.34 * CAPPX * scale * 1.0 + 8
            self.pen.run(t, cx - w / 2, yy, S0 * scale)

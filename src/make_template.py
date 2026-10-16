"""Generate the universal handwriting template (PDF, A4, N pages).

Each box holds ONE character. Four black squares in the page corners let calibrate.py straighten
any phone photo of the page automatically.
"""
import os, sys
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import charset, layout as L

from config import ROOT
FONT_CANDIDATES = [os.path.join(ROOT, 'assets', 'fonts', 'DejaVuSans.ttf'),
                   '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                   '/usr/share/fonts/dejavu/DejaVuSans.ttf',
                   '/Library/Fonts/Arial Unicode.ttf', 'C:/Windows/Fonts/arial.ttf',
                   'C:/Windows/Fonts/seguisym.ttf']


def _font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont('LBL', p))
            return 'LBL', set(pdfmetrics.getFont('LBL').face.charToGlyph.keys())
    return 'Helvetica', set(range(32, 127))


def make(out):
    font, have = _font()
    pages = charset.pages(L.PER_PAGE)
    c = canvas.Canvas(out, pagesize=(210 * 72 / 25.4, 297 * 72 / 25.4))
    mm = 72 / 25.4
    H = 297

    def Y(y):
        return (H - y) * mm

    for pi, chars in enumerate(pages):
        # corner markers
        c.setFillGray(0)
        for k, (cx, cy, s) in L.MARKERS.items():
            c.rect((cx - s / 2) * mm, Y(cy + s / 2), s * mm, s * mm, stroke=0, fill=1)
        c.setFillGray(0.25)
        c.setFont(font, 11)
        c.drawString(26 * mm, Y(11), 'handwriting-synth template   page %d of %d' % (pi + 1, len(pages)))
        c.setFont(font, 7)
        c.setFillGray(0.4)
        c.drawString(26 * mm, Y(15.5), 'Write ONE character per box with your normal pen. Sit letters on the faint baseline; keep the')
        c.drawString(26 * mm, Y(18.5), 'whole character inside its box. Natural size, natural slant. Do not touch the black squares.')
        c.drawString(26 * mm, Y(22.5), 'Photograph the page flat, in even light, with all 4 black squares visible. Keep page order.')
        c.setFont(font, 7)
        c.drawString(26 * mm, Y(284.5), 'Pages: %d   |   photos must be passed to "handwrite.py calibrate" in page order' % len(pages))
        for i, ch in enumerate(chars):
            x, y, w, h = L.cell_mm(i)
            c.setStrokeGray(0.80)
            c.setLineWidth(0.4)
            c.rect(x * mm, Y(y + h), w * mm, h * mm, stroke=1, fill=0)
            # label strip
            c.setStrokeGray(0.80)
            c.line(x * mm, Y(y + L.LABEL_H), (x + w) * mm, Y(y + L.LABEL_H))
            c.setFillGray(0.45)
            if ord(ch) in have:
                c.setFont(font, 10)
                c.drawString((x + 1.5) * mm, Y(y + 4.4), ch)
            cap = charset.caption(ch)
            c.setFont(font if font != 'Helvetica' else 'Helvetica', 5)
            c.setFillGray(0.5)
            tag = cap if (ord(ch) < 128 or ord(ch) in have) else 'U+%04X' % ord(ch)
            if ord(ch) > 127 and ord(ch) not in have:
                tag = 'U+%04X %s' % (ord(ch), cap)
            c.drawString((x + 7) * mm, Y(y + 4.0), tag[:17])
            # baseline and guide lines
            by = y + L.LABEL_H + L.BASE
            c.setStrokeGray(0.88)
            c.setLineWidth(0.3)
            c.line((x + 1) * mm, Y(by), (x + w - 1) * mm, Y(by))
            c.setDash(1, 1.5)
            c.line((x + 1) * mm, Y(by - 8), (x + w - 1) * mm, Y(by - 8))
            c.line((x + 1) * mm, Y(by - 4), (x + w - 1) * mm, Y(by - 4))
            c.setDash()
        c.showPage()
    c.save()
    return len(pages), len(charset.ALL)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'handwriting_template.pdf'
    n, k = make(out)
    print('wrote', out, '-', n, 'pages,', k, 'characters')

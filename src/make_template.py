"""Draw a template PDF (A4) from a plan (see plan.py).

The universal template holds ONE character per box for 174 characters. A document template holds the characters,
words and letter groups that document needs, in the chosen handwriting style, and a box for every figure with a
faint copy to trace over. Four black corner squares let calibrate.py straighten any phone photo of a page, and the
row of small squares at the bottom tells it which page it is looking at.
"""
import os, sys
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import charset, layout as L, plan as PL, styles

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


def _fit(c, font, size, text, maxw_pt):
    while size > 4 and pdfmetrics.stringWidth(text, font, size) > maxw_pt:
        size -= 0.5
    return size


def make(out, plan=None, figs=None):
    """Write the template PDF. plan=None -> the universal template. figs: {key: figure dict} for trace guides."""
    import figures as FG
    plan = plan or PL.universal_plan()
    figs = figs or {}
    font, have = _font()
    c = canvas.Canvas(out, pagesize=(210 * 72 / 25.4, 297 * 72 / 25.4))
    c.setTitle('handwriting-synth template')
    mm = 72 / 25.4
    H = 297
    npages = len(plan['pages'])
    style = styles.STYLES.get(plan.get('style'), styles.STYLES['print'])

    def Y(y):
        return (H - y) * mm

    def drawable(t):
        return all(ord(ch) in have for ch in t)

    for pi, cells in enumerate(plan['pages']):
        c.setFillGray(0)
        for k, (cx, cy, s) in L.MARKERS.items():
            c.rect((cx - s / 2) * mm, Y(cy + s / 2), s * mm, s * mm, stroke=0, fill=1)
        # page code
        for (x, y, s), bit in zip(PL.code_squares_mm(), PL.code_bits(pi, plan['id'])):
            c.setStrokeGray(0.55)
            c.setLineWidth(0.3)
            c.setFillGray(0)
            c.rect((x - s / 2) * mm, Y(y + s / 2), s * mm, s * mm, stroke=0 if bit else 1, fill=bit)
        c.setFillGray(0.25)
        c.setFont(font, 11)
        title = 'handwriting-synth template   page %d of %d' % (pi + 1, npages)
        if plan.get('source'):
            title = '%s   %s style  ·  page %d of %d' % (plan['source'][:40], style['name'], pi + 1, npages)
        c.drawString(26 * mm, Y(11), title)
        c.setFont(font, 7)
        c.setFillGray(0.4)
        if plan['id'] == 0:
            c.drawString(26 * mm, Y(15.5), 'Write ONE character per box with your normal pen. Sit letters on the faint baseline; keep the')
            c.drawString(26 * mm, Y(18.5), 'whole character inside its box. Natural size, natural slant. Do not touch the black squares.')
        else:
            c.drawString(26 * mm, Y(15.5), 'Use a dark pen. Write on the faint baseline at your natural size and slant, inside each box.')
            c.drawString(26 * mm, Y(18.5), 'Do not touch the black squares or the small squares at the bottom of the page.')
        c.drawString(26 * mm, Y(22.5), 'Photograph each page flat, in even light, with all 4 black squares visible.')
        c.setFont(font, 7)
        c.drawString(26 * mm, Y(284.5), 'Pages: %d   |   photos can be given in any order' % npages)
        for cell in cells:
            x, y, w, h = cell['r']
            k = cell['k']
            if k == 'note':
                c.setFillGray(0.3)
                c.setFont(font, 7.5)
                words, lines = cell['t'].split(' '), ['']
                for wd in words:
                    t2 = (lines[-1] + ' ' + wd).strip()
                    if pdfmetrics.stringWidth(t2, font, 7.5) > w * mm and lines[-1]:
                        lines.append(wd)
                    else:
                        lines[-1] = t2
                for li, ln in enumerate(lines[:2]):
                    c.drawString(x * mm, Y(y + 3.4 + li * 3.6), ln)
                continue
            c.setStrokeGray(0.80)
            c.setLineWidth(0.4)
            c.rect(x * mm, Y(y + h), w * mm, h * mm, stroke=1, fill=0)
            c.line(x * mm, Y(y + cell['lh']), (x + w) * mm, Y(y + cell['lh']))
            t = cell['t']
            if k == 'figure':
                fig = figs.get(cell.get('key'))
                c.setFillGray(0.35)
                c.setFont(font, 7.5)
                c.drawString((x + 1.5) * mm, Y(y + 5.4), '%s: trace over the grey drawing (or draw your own). Leave it empty to '
                                                            'let the app sketch it for you.' % t)
                if fig is not None:
                    iw, ih = (w - 4) * L.MM, (h - cell['lh'] - 4) * L.MM
                    guide = FG.trace_guide(fig.get('full', fig['img']), iw, ih)
                    from PIL import Image
                    c.drawImage(ImageReader(Image.fromarray(guide)), (x + 2) * mm, Y(y + h - 2),
                                (w - 4) * mm, (h - cell['lh'] - 4) * mm)
                continue
            # label strip: what to write
            c.setFillGray(0.45)
            if k == 'char':
                if drawable(t):
                    c.setFont(font, 10)
                    c.drawString((x + 1.5) * mm, Y(y + 4.4), t)
                cap = 'again' if cell.get('alt') else charset.caption(t)
                if ord(t) > 127 and not drawable(t):
                    cap = 'U+%04X %s' % (ord(t), cap)
                c.setFont(font, 5)
                c.setFillGray(0.5)
                c.drawString((x + 7) * mm, Y(y + 4.0), cap[:17])
            else:
                lab = t + ('   (again)' if cell.get('alt') else '')
                c.setFont(font, _fit(c, font, 9, lab, (w - 3) * mm))
                c.drawString((x + 1.5) * mm, Y(y + 4.4), lab)
            # baseline and guide lines
            by = y + cell['lh'] + cell['b']
            c.setStrokeGray(0.88)
            c.setLineWidth(0.3)
            c.line((x + 1) * mm, Y(by), (x + w - 1) * mm, Y(by))
            c.setDash(1, 1.5)
            c.line((x + 1) * mm, Y(by - 8), (x + w - 1) * mm, Y(by - 8))
            c.line((x + 1) * mm, Y(by - 4), (x + w - 1) * mm, Y(by - 4))
            c.setDash()
            if cell.get('dots'):                         # cursive: where the joining strokes start and end
                c.setFillGray(0.80)
                for dx in (2.6, w - 2.6):
                    c.circle((x + dx) * mm, Y(by - 0.3), 0.45 * mm, stroke=0, fill=1)
        c.showPage()
    c.save()
    return npages, sum(1 for _, cell in PL.cells(plan, ('char',)) if not cell.get('alt'))


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'handwriting_template.pdf'
    n, k = make(out)
    print('wrote', out, '-', n, 'pages,', k, 'characters')

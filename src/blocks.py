"""Render a list of document blocks as handwritten pages.

block = ('h1', text) | ('h2', text) | ('h3', text) | ('p', text) | ('bullet', text, level) | ('num', n, text)
      | ('table', rows) | ('code', [lines]) | ('formula', text) | ('pagebreak',)
"""
import sys
from doclib import *
import hw_render
from normalize import clean


def col_widths(rows, total=RIGHT - LEFT - 20, minw=170):
    ncol = max(len(r) for r in rows)
    mx = [4] * ncol
    for r in rows:
        for i, c in enumerate(r):
            mx[i] = max(mx[i], min(len(c), 60))
    ws = [max(minw, total * m / float(sum(mx))) for m in mx]
    k = total / sum(ws)
    return [int(w * k) for w in ws]


def render(blocks, out_pdf, markup=False, log=print):
    Pen.MARKUP = markup
    lib = hw_render.LIB
    dropped_all = set()

    def C(t):
        t2, d = clean(t, lib)
        dropped_all.update(d)
        return t2

    d = Doc()
    for b in blocks:
        k = b[0]
        if k == 'h1':
            d.head(C(b[1]))
        elif k == 'h2':
            d.subhead(C(b[1]))
        elif k == 'h3':
            d.label(C(b[1]))
        elif k == 'p':
            d.para(C(b[1]))
        elif k == 'bullet':
            lvl = b[2] if len(b) > 2 else 0
            d.bullet(C(b[1]), indent=100 + 70 * lvl, mark='-' if lvl == 0 else '·')
        elif k == 'num':
            d.numbered(b[1], C(b[2]))
        elif k == 'formula':
            Pen.MARKUP = True
            d.formula(C(b[1]))
            Pen.MARKUP = markup
        elif k == 'code':
            d.code([C(l) if l.strip() else '' for l in b[1]], raw=True)
        elif k == 'table':
            rows = [[C(c) for c in r] + [''] * (max(len(x) for x in b[1]) - len(r)) for r in b[1]]
            d.table(col_widths(rows), rows)
        elif k == 'pagebreak':
            d.new_page()
    ims = d.close()
    ims[0].save(out_pdf, save_all=True, append_images=ims[1:], resolution=300)
    log('wrote %s (%d pages)' % (out_pdf, len(ims)))
    if dropped_all:
        log('skipped %d character(s) your library cannot draw: %s' % (len(dropped_all), ' '.join(sorted(dropped_all))))
    return len(ims), dropped_all

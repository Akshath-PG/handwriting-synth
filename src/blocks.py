"""Render a list of document blocks as handwritten pages.

block = ('h1', text) | ('h2', text) | ('h3', text) | ('p', text) | ('bullet', text, level) | ('num', n, text)
      | ('table', rows) | ('code', [lines]) | ('formula', text) | ('figure', figure dict) | ('pagebreak',)
"""
import sys
from doclib import *
import hw_render, styles
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


def render(blocks, out_pdf, markup=False, log=print, human='subtle', seed=1):
    """human: 'off' | 'subtle' | 'natural' - how many human imperfections to add (see humanize.py)."""
    Pen.MARKUP = markup
    lib = hw_render.LIB
    caps = styles.get(hw_render.STYLE)['caps']
    dropped_all = set()
    nfig = mine = 0
    nform = [0, 0]

    def C(t, keep=''):
        if caps:
            t = styles.upper_text(t)
        t2, d = clean(t, lib, keep)
        dropped_all.update(d)
        return t2

    MK = '\\{}^_'                         # maths markup syntax: never dropped, the renderer interprets it

    d = Doc(human=human, seed=seed)
    for b in blocks:
        k = b[0]
        if k == 'h1':
            d.head(C(b[1], MK if markup else ''))
        elif k == 'h2':
            d.subhead(C(b[1], MK if markup else ''))
        elif k == 'h3':
            d.label(C(b[1], MK if markup else ''))
        elif k == 'p':
            d.para(C(b[1], MK if markup else ''))
        elif k == 'bullet':
            lvl = b[2] if len(b) > 2 else 0
            d.bullet(C(b[1], MK if markup else ''), indent=100 + 70 * lvl, mark='-' if lvl == 0 else '·')
        elif k == 'num':
            d.numbered(b[1], C(b[2], MK if markup else ''))
        elif k == 'formula':
            Pen.MARKUP = True
            import plan
            mine_f = hw_render.FORMULAS.get(plan.formula_key(b[1].strip()))
            d.formula(C(b[1], MK), own=mine_f)
            nform[0] += 1
            nform[1] += mine_f is not None
            Pen.MARKUP = markup
        elif k == 'code':
            d.code([C(l) if l.strip() else '' for l in b[1]], raw=True)
        elif k == 'table':
            rows = [[C(c) for c in r] + [''] * (max(len(x) for x in b[1]) - len(r)) for r in b[1]]
            d.table(col_widths(rows), rows)
        elif k == 'figure':
            fig = dict(b[1])
            fig['labels'] = [(C(t),) + tuple(rest) for t, *rest in fig.get('labels', [])]
            own = hw_render.FIGS.get(fig['key'])
            d.figure(fig, own)
            nfig += 1
            mine += own is not None
        elif k == 'pagebreak':
            d.new_page()
    ims = d.close()
    ims[0].save(out_pdf, save_all=True, append_images=ims[1:], resolution=300)
    log('wrote %s (%d pages)' % (out_pdf, len(ims)))
    if nform[1]:
        log('equations: %d of %d written from your template' % (nform[1], nform[0]))
    if nfig:
        log('figures: %d drawn by you (from the template), %d sketched automatically' % (mine, nfig - mine))
    if dropped_all:
        log('skipped %d character(s) your library cannot draw: %s' % (len(dropped_all), ' '.join(sorted(dropped_all))))
    return len(ims), dropped_all

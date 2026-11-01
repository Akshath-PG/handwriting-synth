"""What goes where on a template. Both make_template.py (drawing) and calibrate.py (cutting) read a plan, so any
template - the universal 174-character one or one made for a particular document - is handled the same way.

plan = {version, id, style, source, summary, pages: [[cell, ...], ...]}
cell = {k: 'char' | 'word' | 'sentence' | 'formula' | 'figure' | 'note',  t: text (formula: its markup),  r: [x, y, w, h] mm,  lh: label strip height mm,
        b: baseline, mm below the top of the writing area,  alt: 0/1 (second sample),  dots: cursive entry/exit dots,
        key: figure key,  hint: label text}

Each page also carries a small row of squares (the page code): which page of which template it is, so photos can be
uploaded in any order and photos of a different template are refused.
"""
import json, os, zlib
import charset, layout as L, styles

VERSION = 3
TOP, BOTTOM, LEFT_MM, RIGHT_MM = L.GY0, 277.0, L.GX0, L.GX0 + L.COLS * L.CW       # usable area (mm)
WIDTH_MM = RIGHT_MM - LEFT_MM
ROW_H = L.CH

# page code: 12 squares on the bottom edge. [sync=1, 5 bits page index, 5 bits template id, parity]
CODE_X0, CODE_Y, CODE_PITCH, CODE_SIDE, CODE_BITS = 120.0, 284.0, 4.4, 3.0, 12
MAX_PAGES = 31
MAX_FORMULAS = 12


def code_bits(page_index, tpl_id):
    bits = [1] + [(page_index >> i) & 1 for i in range(5)] + [(tpl_id >> i) & 1 for i in range(5)]
    bits.append(sum(bits) % 2)
    return bits


def decode_bits(bits):
    """-> (page_index, tpl_id) or None if the squares do not form a valid code."""
    if len(bits) != CODE_BITS or bits[0] != 1 or sum(bits[:-1]) % 2 != bits[-1]:
        return None
    return sum(b << i for i, b in enumerate(bits[1:6])), sum(b << i for i, b in enumerate(bits[6:11]))


def code_squares_mm():
    return [(CODE_X0 + i * CODE_PITCH, CODE_Y, CODE_SIDE) for i in range(CODE_BITS)]


# ------------------------------------------------------------------ cell geometry (mm -> px on the 300 dpi page)
def write_rect_px(c, inset=1.0):
    x, y, w, h = c['r']
    return L.px(x + inset), L.px(y + c['lh'] + 0.5), L.px(x + w - inset), L.px(y + h - inset)


def baseline_px(c):
    x, y, w, h = c['r']
    return L.px(y + c['lh'] + c['b'])


def _char(t, x, y, alt=0, dots=False):
    return dict(k='char', t=t, r=[x, y, L.CW, L.CH], lh=L.LABEL_H, b=L.BASE, alt=alt, dots=dots)


# ------------------------------------------------------------------ plans
def universal_plan():
    """The original 4-page template with all 174 characters (print style)."""
    pages = []
    for chars in charset.pages(L.PER_PAGE):
        cells = []
        for i, ch in enumerate(chars):
            x, y, w, h = L.cell_mm(i)
            cells.append(_char(ch, x, y))
        pages.append(cells)
    return dict(version=VERSION, id=0, style='print', source='', summary={}, pages=pages)


class _Flow:
    def __init__(self):
        self.pages, self.cells, self.x, self.y, self.row_h = [], [], LEFT_MM, TOP, 0.0

    def page(self):
        if self.cells:
            self.pages.append(self.cells)
        self.cells, self.x, self.y, self.row_h = [], LEFT_MM, TOP, 0.0

    def newline(self, gap=0.0):
        if self.x > LEFT_MM:
            self.y += self.row_h + gap
        self.x, self.row_h = LEFT_MM, 0.0

    def place(self, w, h):
        if self.x + w > RIGHT_MM + 0.01:
            self.newline()
        if self.y + h > BOTTOM:
            self.page()
        x, y = self.x, self.y
        self.x += w
        self.row_h = max(self.row_h, h)
        return x, y

    def note(self, text):
        self.newline(2.0)
        if self.y + 9 + ROW_H > BOTTOM:
            self.page()
        self.cells.append(dict(k='note', t=text, r=[LEFT_MM, self.y, WIDTH_MM, 8.0], lh=0, b=0))
        self.y += 9.0

    def done(self):
        self.newline()
        if self.cells:
            self.pages.append(self.cells)
        return self.pages


def word_width_mm(word):
    return min(max(14.0 + 6.4 * len(word), 30.0), WIDTH_MM)


def document_plan(st, source=''):
    """Template for one document. st = study.study(...) result."""
    import study
    sty = styles.get(st['style'])
    chars = st['chars']
    base = (charset.UPPER + charset.DIGITS + list('.,-()')) if sty['caps'] else list(charset.REQUIRED)
    need = list(dict.fromkeys(base + [c for c in charset.ALL if c in chars] + sorted(c for c in chars if c not in charset.ALL)))
    if sty['caps']:
        need = [c for c in need if not (c.isalpha() and c.islower() and c.upper() != c)]
    letters = [c for c, n in chars.most_common() if c.isalnum()]
    alts = letters[:sty['alts']]
    words = study.pick_words(st['words'], sty['words'])
    frags = study.pick_fragments(st['words'], words, sty['frags'])
    twice = words[:max(sty['words'] // 5, 0)]
    figs = st['figures']

    f = _Flow()
    f.note('LETTERS, DIGITS AND SYMBOLS used in your document.  ' + sty['char_hint'])
    cursive = st['style'] == 'cursive'
    for c in need:
        x, y = f.place(L.CW, L.CH)
        f.cells.append(_char(c, x, y, dots=cursive and c.isalpha() and c.islower()))
    for c in alts:
        x, y = f.place(L.CW, L.CH)
        f.cells.append(_char(c, x, y, alt=1, dots=cursive and c.isalpha() and c.islower()))
    if words or frags:
        f.note('WORDS your document uses most.  ' + sty['word_hint'])
        for w, alt in [(w, 0) for w in words] + [(w, 1) for w in twice] + [(g, 0) for g in frags]:
            x, y = f.place(word_width_mm(w), L.CH)
            f.cells.append(dict(k='word', t=w, r=[x, y, word_width_mm(w), L.CH], lh=L.LABEL_H, b=L.BASE, alt=alt))
    lines = study.pick_lines(st.get('prose', []), set(need), st['words'], sty['sentences'])
    if lines:
        f.note('SENTENCES from your document. Write each one naturally, as fast and as neatly as you normally would, '
               'on the line. This shows how you really space, slant and join your writing.')
        for t in lines:
            x, y = f.place(WIDTH_MM, L.CH + 2)
            f.cells.append(dict(k='sentence', t=t, r=[x, y, WIDTH_MM, L.CH + 2], lh=L.LABEL_H, b=L.BASE + 1))
    forms = st.get('formulas', [])[:MAX_FORMULAS]
    if forms:
        f.note('EQUATIONS in your document. Write each one as you would by hand (fractions, powers, symbols as you '
               'normally write them), sitting on the line.')
        for t in forms:
            txt = study.readable_formula(t)
            tall = any(k in t for k in ('\\f{', '\\S{', '\\M{'))
            w = min(max(24.0 + 4.6 * len(txt), 50.0), WIDTH_MM)
            h = 46.0 if tall else 34.0
            x, y = f.place(w, h)
            f.cells.append(dict(k='formula', t=t, label=txt, key=formula_key(t), r=[x, y, w, h], lh=L.LABEL_H,
                                b=(h - L.LABEL_H) * (0.62 if tall else 0.6)))
    for i, fig in enumerate(figs):
        f.newline(3.0)
        ih, iw = fig['img'].shape[:2]
        w = WIDTH_MM
        h = w * ih / float(iw) + 8.0
        if h > BOTTOM - TOP:
            h = BOTTOM - TOP
            w = (h - 8.0) * iw / float(ih)
        x, y = f.place(w, h)
        f.cells.append(dict(k='figure', t='Figure %d' % (i + 1), key=fig['key'], r=[x, y, w, h], lh=8.0, b=0,
                            labels=bool(fig.get('labels'))))
        f.newline(2.0)
    pages = f.done()
    if len(pages) > MAX_PAGES:
        raise ValueError('this document would need a %d-page template (max %d); split it into parts' % (len(pages), MAX_PAGES))
    summary = dict(chars=len(need), alts=len(alts), words=len(words) + len(twice), fragments=len(frags), figures=len(figs),
                   sentences=len(lines), formulas=len(forms), pages=len(pages), nwords=st['nwords'])
    body = json.dumps([[(c['k'], c['t']) for c in p] for p in pages], ensure_ascii=False)
    tid = zlib.crc32((st['style'] + body).encode('utf-8')) % 31 + 1
    return dict(version=VERSION, id=tid, style=st['style'], source=os.path.basename(source), summary=summary,
                pages=pages, wordlist=words, fragments=frags)


def formula_key(text):
    import hashlib
    return 'f:' + hashlib.sha1(''.join(text.split()).encode('utf-8')).hexdigest()[:14]


def cells(plan, kinds=('char', 'word', 'figure', 'sentence', 'formula')):
    for pi, page in enumerate(plan['pages']):
        for c in page:
            if c['k'] in kinds:
                yield pi, c


def save(plan, path):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=0)


def load(path):
    if not path:
        return universal_plan()
    with open(path, encoding='utf-8') as fh:
        p = json.load(fh)
    if p.get('version') != VERSION:
        raise ValueError('%s is not a template description made by this version' % path)
    return p


def manifest_path(pdf_path):
    return os.path.splitext(pdf_path)[0] + '.json'

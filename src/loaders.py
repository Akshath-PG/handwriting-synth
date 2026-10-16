"""Read .txt/.md, .docx and .pdf files into document blocks."""
import re, os, collections


# ------------------------------------------------------------------ text / markdown
def load_text(path):
    lines = open(path, encoding='utf-8-sig').read().split('\n')
    blocks, buf, code, incode, table = [], [], [], False, []

    def flush():
        nonlocal buf, table
        if buf:
            blocks.append(('p', ' '.join(buf))); buf = []
        if table:
            rows = [r for r in table if not re.match(r'^\s*\|?[\s:|-]+\|?\s*$', '|'.join(r))]
            blocks.append(('table', rows)); table = []
    for ln in lines:
        s = ln.strip()
        if s.startswith('```'):
            if incode:
                blocks.append(('code', code)); code = []
            else:
                flush()
            incode = not incode
            continue
        if incode:
            code.append(ln.rstrip()); continue
        if not s:
            flush(); continue
        if s.startswith('|') and s.endswith('|'):
            if buf:
                flush()
            table.append([c.strip() for c in s.strip('|').split('|')]); continue
        if table:
            flush()
        m = re.match(r'^(#{1,6})\s+(.*)', s)
        if m:
            flush(); blocks.append(('h1' if len(m.group(1)) == 1 else 'h2' if len(m.group(1)) == 2 else 'h3', m.group(2)))
        elif re.match(r'^[-*•]\s+', s):
            flush(); lvl = (len(ln) - len(ln.lstrip())) // 2
            blocks.append(('bullet', re.sub(r'^[-*•]\s+', '', s), lvl))
        elif re.match(r'^\d+[.)]\s+', s):
            flush(); n, t = re.split(r'[.)]\s+', s, 1); blocks.append(('num', int(n), t))
        elif s.startswith('$$') and s.endswith('$$') and len(s) > 4:
            flush(); blocks.append(('formula', s[2:-2].strip()))
        else:
            buf.append(s)
    flush()
    return blocks


# ------------------------------------------------------------------ docx
def load_docx(path):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    D = docx.Document(path)
    blocks = []
    mono = ('courier', 'consolas', 'mono', 'menlo', 'monaco')
    num = 0
    for el in D.element.body.iterchildren():
        tag = el.tag.split('}')[1]
        if tag == 'tbl':
            t = Table(el, D)
            rows = [[c.text.strip().replace('\n', ' ') for c in r.cells] for r in t.rows]
            if rows:
                blocks.append(('table', rows))
            num = 0
        elif tag == 'p':
            p = Paragraph(el, D)
            text = p.text.strip('\n')
            if not text.strip():
                continue
            st = (p.style.name or '').lower()
            fonts = [(r.font.name or '').lower() for r in p.runs if r.text.strip()]
            if st.startswith('heading 1') or st == 'title':
                blocks.append(('h1', text.strip())); num = 0
            elif st.startswith('heading 2') or st == 'subtitle':
                blocks.append(('h2', text.strip())); num = 0
            elif st.startswith('heading'):
                blocks.append(('h3', text.strip())); num = 0
            elif 'list bullet' in st:
                blocks.append(('bullet', text.strip(), 1 if '2' in st else 0))
            elif 'list number' in st:
                num += 1; blocks.append(('num', num, text.strip()))
            elif 'code' in st or (fonts and all(any(m in f for m in mono) for f in fonts)):
                if blocks and blocks[-1][0] == 'code':
                    blocks[-1][1].append(text)
                else:
                    blocks.append(('code', [text]))
            else:
                blocks.append(('p', text.strip())); num = 0
    return blocks


# ------------------------------------------------------------------ pdf
BULLET = re.compile(r'^([•●▪◦\-–*])\s+')
NUMBER = re.compile(r'^(\d{1,2})[.)]\s+')
MONO = ('mono', 'courier', 'consolas', 'menlo', 'code')


def _parse_lines(fp):
    """Group the characters of a pdfplumber page into text lines with font info."""
    lines = {}
    for ch in fp.chars:
        lines.setdefault(round(ch['top'] / 3), []).append(ch)
    rows = []
    for key in sorted(lines):
        cs = sorted(lines[key], key=lambda c: c['x0'])
        if rows and abs(cs[0]['top'] - rows[-1]['top']) < 2.5:          # superscript sharing a line
            rows[-1]['chars'] = sorted(rows[-1]['chars'] + cs, key=lambda c: c['x0'])
            continue
        rows.append(dict(top=cs[0]['top'], chars=cs))
    parsed = []
    for r in rows:
        cs = r['chars']
        text, last = '', None
        for c in cs:
            if last is not None and c['x0'] - last['x1'] > 0.25 * c['size']:
                text += ' '
            text += c['text']
            last = c
        sizes = [round(c['size'], 1) for c in cs]
        font = collections.Counter(c['fontname'] for c in cs).most_common(1)[0][0].lower()
        if text.strip():
            parsed.append(dict(text=text.strip(), size=max(set(sizes), key=sizes.count), x0=cs[0]['x0'], top=r['top'],
                               bottom=max(c['bottom'] for c in cs), mono=any(m in font for m in MONO),
                               bold=any(m in font for m in ('bold', 'black', 'heavy')), cw=cs[0]['size'] * 0.6))
    return parsed


def _real_table(t, pg):
    rows = t.extract()
    if len(rows) < 2 or len(rows[0]) < 2:
        return False
    if (t.bbox[3] - t.bbox[1]) > 0.8 * pg.height:                 # page-sized frame, not a table
        return False
    good = sum(1 for r in rows if sum(1 for c in r if c and c.strip()) >= 2)
    return good >= 0.6 * len(rows) and max(len(c or '') for r in rows for c in r) < 220


def _join(a, b):
    return a + b if a.endswith('-') else a + ' ' + b


def load_pdf(path, log=print):
    import pdfplumber
    blocks, skipped_images = [], 0
    with pdfplumber.open(path) as pdf:
        cnt = collections.Counter()
        for pg in pdf.pages:
            for ch in pg.chars:
                if not any(m in ch['fontname'].lower() for m in MONO):
                    cnt[round(ch['size'], 1)] += 1
        body = cnt.most_common(1)[0][0] if cnt else 11
        # pass 1: lines per page; drop running headers/footers (same text on many pages near the top/bottom)
        pages = []
        for pg in pdf.pages:
            skipped_images += len(pg.images)
            tables = [t for t in pg.find_tables() if _real_table(t, pg)]
            boxes = [t.bbox for t in tables]

            def keep(o, boxes=boxes):
                if o.get('object_type') != 'char':
                    return True
                cx, cy = (o['x0'] + o['x1']) / 2, (o['top'] + o['bottom']) / 2
                return not any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1 for b in boxes)
            parsed = _parse_lines(pg.filter(keep) if boxes else pg)
            pages.append((pg, tables, parsed))
        seen = collections.Counter()
        for pg, _, parsed in pages:
            for p in parsed:
                if p['top'] < 0.1 * pg.height or p['bottom'] > 0.9 * pg.height:
                    seen[re.sub(r'\d+', '#', p['text'])] += 1
        need = max(2, int(0.5 * len(pages)))
        for pg, tables, parsed in pages:
            parsed[:] = [p for p in parsed if not ((p['top'] < 0.1 * pg.height or p['bottom'] > 0.9 * pg.height)
                                                    and seen[re.sub(r'\d+', '#', p['text'])] >= need)]
        lefts = collections.Counter(round(p['x0']) for _, _, pr in pages for p in pr
                                    if not p['mono'] and abs(p['size'] - body) < 0.3)
        body_left = lefts.most_common(1)[0][0] if lefts else 0
        # pass 2: group lines into blocks
        for pg, tables, parsed in pages:
            items = []
            for t in tables:
                rows = [[(c or '').replace('\n', ' ').strip() for c in r] for r in t.extract()]
                rows = [r for r in rows if any(r)]
                if rows:
                    items.append((t.bbox[1], ('table', rows)))
            i = 0
            while i < len(parsed):
                p = parsed[i]
                if p['mono']:
                    j = i
                    while j < len(parsed) and parsed[j]['mono']:
                        j += 1
                    grp = parsed[i:j]
                    base = min(q['x0'] for q in grp)
                    items.append((p['top'], ('code', [' ' * int(round((q['x0'] - base) / max(q['cw'], 1))) + q['text'] for q in grp])))
                    i = j
                    continue
                if p['size'] >= body * 1.45 or (p['bold'] and p['size'] >= body * 1.25):
                    kind = 'h1'
                elif p['size'] >= body * 1.12 or (p['bold'] and len(p['text']) < 70 and p['size'] >= body * 0.98):
                    kind = 'h2'
                else:
                    kind = 'p'
                if kind != 'p':
                    txt, j = p['text'], i + 1
                    while j < len(parsed) and parsed[j]['size'] == p['size'] and not parsed[j]['mono'] \
                            and parsed[j]['top'] - parsed[j - 1]['bottom'] < 0.6 * p['size']:
                        txt = _join(txt, parsed[j]['text']); j += 1
                    items.append((p['top'], (kind, txt)))
                    i = j
                    continue
                m1, m2 = BULLET.match(p['text']), NUMBER.match(p['text'])
                txt, j = p['text'][(m1 or m2).end():] if (m1 or m2) else p['text'], i + 1
                while j < len(parsed) and not parsed[j]['mono'] and parsed[j]['size'] < body * 1.12 \
                        and not BULLET.match(parsed[j]['text']) and not NUMBER.match(parsed[j]['text']) \
                        and parsed[j]['top'] - parsed[j - 1]['bottom'] <= 0.65 * p['size'] \
                        and abs(parsed[j]['x0'] - p['x0']) < 6:
                    txt = _join(txt, parsed[j]['text']); j += 1
                if m1 or p['x0'] > body_left + 8:
                    items.append((p['top'], ('bullet', txt, 0)))
                elif m2:
                    items.append((p['top'], ('num', int(m2.group(1)), txt)))
                else:
                    items.append((p['top'], ('p', txt)))
                i = j
            items.sort(key=lambda t: t[0])
            blocks += [b for _, b in items]
    out = []
    for b in blocks:                                  # glue code blocks split by a page break
        if out and b[0] == 'code' and out[-1][0] == 'code':
            out[-1] = ('code', out[-1][1] + b[1])
        else:
            out.append(b)
    out = [latex_block(b) for b in out]
    if skipped_images:
        log('note: %d picture(s)/diagram(s) in the PDF cannot be rewritten by hand and were skipped' % skipped_images)
    return out


# ------------------------------------------------------------------ LaTeX-looking code -> handwriting maths
LATEX_HINT = re.compile(r'\\(tilde|hat|frac|sum|sqrt|begin|mathbb|mathbf|mathrm|left|qquad|times|cdot|in|Delta)\b')
SYM = {'times': '×', 'cdot': '·', 'in': '∈', 'to': '→', 'rightarrow': '→', 'leftarrow': '←', 'Rightarrow': '⇒',
       'Leftrightarrow': '⇔', 'le': '≤', 'leq': '≤', 'ge': '≥', 'geq': '≥', 'neq': '≠', 'approx': '≈', 'cong': '≅',
       'Delta': 'Δ', 'Sigma': 'Σ', 'sigma': 'σ', 'phi': 'φ', 'varphi': 'φ', 'lambda': 'λ', 'alpha': 'α', 'beta': 'β',
       'theta': 'θ', 'mu': 'μ', 'pi': 'π', 'omega': 'ω', 'infty': '∞', 'forall': '∀', 'exists': '∃', 'emptyset': '∅',
       'cup': '∪', 'cap': '∩', 'subset': '⊂', 'partial': '∂', 'nabla': '∇', 'pm': '±', 'ldots': '…', 'dots': '…',
       'deg': 'deg', 'max': 'max', 'min': 'min', 'ReLU': 'ReLU', 'top': 'ᵀ', 'mid': '|', 'quad': ' ', 'qquad': '  ',
       ',': ' ', ';': ' ', '!': '', ':': ' ', ' ': ' ', 'left': '', 'right': '', 'lVert': '||', 'rVert': '||', '|': '||'}
BB = {'R': 'ℝ', 'N': 'ℕ', 'Z': 'ℤ', 'Q': 'ℚ', 'C': 'ℂ'}


def _grab(s, i):
    """s[i] == '{' -> (inner, index after the matching '}')"""
    d, j = 1, i + 1
    while j < len(s) and d:
        d += (s[j] == '{') - (s[j] == '}')
        j += 1
    return s[i + 1:j - 1], j


def latex_to_markup(s):
    out, i = [], 0

    def arg(i):
        while i < len(s) and s[i] == ' ':
            i += 1
        if i < len(s) and s[i] == '{':
            g, j = _grab(s, i)
            return latex_to_markup(g), j
        if i < len(s):
            return s[i], i + 1
        return '', i
    while i < len(s):
        c = s[i]
        if c == '\\':
            m = re.match(r'\\([A-Za-z]+|.)', s[i:])
            if not m:
                i += 1; continue
            cmd = m.group(1); i += m.end()
            if cmd in ('tilde', 'widetilde'):
                g, i = arg(i); out.append('\\t{%s}' % g)
            elif cmd in ('hat', 'widehat'):
                g, i = arg(i); out.append('\\h{%s}' % g)
            elif cmd == 'frac':
                a, i = arg(i); b, i = arg(i); out.append('\\f{%s}{%s}' % (a, b))
            elif cmd == 'sqrt':
                g, i = arg(i); out.append('\\r{%s}' % g)
            elif cmd in ('mathbf', 'mathrm', 'text', 'mathit', 'operatorname', 'boldsymbol'):
                g, i = arg(i); out.append(g)
            elif cmd == 'mathbb':
                g, i = arg(i); out.append(BB.get(g, g))
            elif cmd == 'sum':
                lo = hi = ''
                while i < len(s) and s[i] in '_^ ':
                    if s[i] == ' ':
                        i += 1; continue
                    t = s[i]; g, i = arg(i + 1)
                    if t == '_': lo = g
                    else: hi = g
                out.append('\\S{%s}{%s}' % (lo, hi))
            elif cmd == 'begin' or cmd == 'end':
                env, i = arg(i)
                if cmd == 'begin':
                    e = s.find('\\end{' + env + '}', i)
                    body = s[i:e if e >= 0 else len(s)]
                    rows = [','.join(latex_to_markup(x.strip()) for x in r.split('&')) for r in re.split(r'\\\\', body) if r.strip()]
                    out.append('[\\M{%s}]' % ';'.join(rows) if False else '\\M{%s}' % ';'.join(rows))
                    i = e + len('\\end{' + env + '}') if e >= 0 else len(s)
            elif cmd == '\\':
                out.append(' ')
            elif cmd in SYM:
                out.append(SYM[cmd])
            else:
                out.append(cmd if len(cmd) > 1 else cmd)
            continue
        if c in '^_' and i + 1 < len(s) and s[i + 1] != '{':
            out.append('%s{%s}' % (c, s[i + 1])); i += 2; continue
        if c == '^' or c == '_':
            g, j = _grab(s, i + 1)
            out.append('%s{%s}' % (c, latex_to_markup(g))); i = j; continue
        if c == '~':
            out.append(' ')
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def latex_block(b):
    if b[0] == 'code' and LATEX_HINT.search(' '.join(b[1])):
        return ('formula', re.sub(r'\s+', ' ', latex_to_markup(' '.join(l.strip() for l in b[1]))).strip())
    return b


def load(path, log=print):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        bl = load_pdf(path, log)
        return bl, False
    if ext == '.docx':
        return load_docx(path), False
    if ext in ('.txt', '.md', '.markdown'):
        return load_text(path), True        # markup (^{} _{} \f{}{} ...) allowed
    raise SystemExit('unsupported file type %s (use .pdf .docx .md .txt)' % ext)

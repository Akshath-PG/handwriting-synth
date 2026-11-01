"""Study a document before making its template: which characters, words and letter groups it uses, and its figures."""
import collections, re, unicodedata
import charset, styles

WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
MARKUP_CMD = re.compile(r'\\[A-Za-z]')


PROSE = []


def _texts(blocks, markup):
    """Every piece of text the renderer will write (and, separately, the code lines), plus the glyphs maths markup
    draws."""
    out, extra, code = [], set(), []
    for b in blocks:
        k = b[0]
        if k in ('h1', 'h2', 'h3', 'p'):
            out.append(b[1])
        elif k == 'bullet':
            out.append(b[1]); out.append('-' if (len(b) < 3 or b[2] == 0) else '·')
        elif k == 'num':
            out.append('%d. %s' % (b[1], b[2]))
        if k in ('p', 'bullet'):
            PROSE.append(b[1])
        elif k == 'num':
            PROSE.append(b[2])
        elif k == 'code':
            out += b[1]
            code += b[1]
        elif k == 'table':
            out += [c for r in b[1] for c in r]
        elif k == 'formula':
            t = b[1]
            extra |= {'√'} if '\\r{' in t else set()
            extra |= {'Σ'} if '\\S{' in t else set()
            extra |= {'^'} if '\\h{' in t else set()
            extra |= {'~'} if '\\t{' in t else set()
            out.append(MARKUP_CMD.sub('', t).replace('{', '').replace('}', '').replace('^', '').replace('_', ''))
        elif k == 'figure':
            out += [lb[0] for lb in b[1].get('labels', [])]
    if markup:
        out = [MARKUP_CMD.sub('', t) if ('\\' in t) else t for t in out]
    return out, extra, code


def _drawable(c):
    if c.isspace():
        return False
    cat = unicodedata.category(c)
    return cat[0] in 'LNPS' and not unicodedata.combining(c)


def study(blocks, markup, style):
    """Return a summary dict used by plan.document_plan()."""
    st = styles.get(style)
    del PROSE[:]
    texts, extra, code = _texts(blocks, markup)
    prose = [MARKUP_CMD.sub('', t) if markup else t for t in PROSE]
    code = set(code)
    formulas = list(dict.fromkeys(b[1].strip() for b in blocks if b[0] == 'formula' and b[1].strip()))
    if st['caps']:
        texts = [styles.upper_text(t) for t in texts]
    chars = collections.Counter()
    for t in texts:
        for c in t:
            if _drawable(c):
                if c not in charset.ALL:                    # drop accents if the base letter is enough
                    base = ''.join(b for b in unicodedata.normalize('NFKD', c) if not unicodedata.combining(b))
                    if base and all(b in charset.ALL for b in base) and not c.isalpha():
                        c = base
                chars[c] += 1
    for c in extra:
        chars[c] += 1
    words = collections.Counter()
    for t in texts:
        if t in code:                                   # code is written letter by letter, even in cursive
            continue
        for w in WORD.findall(t):
            if 2 <= len(w) <= 14 and (w.islower() or (w[0].isupper() and w[1:].islower())):
                words[w] += 1
    figs = [b[1] for b in blocks if b[0] == 'figure']
    nwords = sum(len(WORD.findall(t)) for t in texts)
    if st['caps']:
        prose = [styles.upper_text(t) for t in prose]
    return dict(style=style, chars=chars, words=words, figures=figs, nwords=nwords, prose=prose, formulas=formulas,
                nblocks=sum(1 for b in blocks if b[0] != 'pagebreak'))


def pick_lines(prose, allowed, words, n, maxlen=34):
    """n short lines of the document's own text (whole words, at most maxlen characters) to write as sample
    sentences: ones full of the document's frequent words and of many different letters."""
    if n <= 0:
        return []
    allowed = set(allowed) | {' '}
    cands = []
    for t in prose:
        for sent in re.split(r'(?<=[.!?;:])\s+', t):
            toks = sent.split()
            i = 0
            while i < len(toks):
                line = []
                j = i
                while j < len(toks) and len(' '.join(line + [toks[j]])) <= maxlen:
                    line.append(toks[j]); j += 1
                if len(line) >= 4:
                    txt = ' '.join(line)
                    if all(c in allowed for c in txt) and sum(c.isalpha() for c in txt) >= 0.7 * len(txt.replace(' ', '')):
                        cands.append(txt)
                i = max(j, i + 1)
    chosen, seen_letters, seen = [], set(), set()
    while cands and len(chosen) < n:
        def score(tx):
            ws = [w.strip('.,;:!?()').lower() for w in tx.split()]
            return (sum(words.get(w, 0) ** 0.5 for w in ws) + 2.0 * len(set(tx.lower()) - seen_letters - {' '})
                    - 3.0 * len(set(ws) & seen))
        best = max(cands, key=score)
        cands.remove(best)
        chosen.append(best)
        seen_letters |= set(best.lower())
        seen |= {w.strip('.,;:!?()').lower() for w in best.split()}
    if not chosen:
        pangram = 'The quick brown fox jumps over the lazy dog'
        if all(c in allowed for c in pangram):
            chosen = [pangram[:maxlen].rsplit(' ', 1)[0]]
    return chosen


def readable_formula(t):
    """Maths markup -> something a person can read on the template: \\f{a}{b} -> (a)/(b), x^{2} -> x^2 ..."""
    rules = [(r'\\f\{([^{}]*)\}\{([^{}]*)\}', r'(\1)/(\2)'), (r'\\S\{([^{}]*)\}\{([^{}]*)\}', r'Σ[\1..\2]'),
             (r'\\r\{([^{}]*)\}', r'√(\1)'), (r'\\h\{([^{}]*)\}', r'\1̂'), (r'\\t\{([^{}]*)\}', r'\1̃'),
             (r'\\M\{([^{}]*)\}', r'[\1]'), (r'\^\{([^{}]*)\}', r'^\1'), (r'_\{([^{}]*)\}', r'_\1')]
    for _ in range(6):
        t0 = t
        for a, b in rules:
            t = re.sub(a, b, t)
        if t == t0:
            break
    return re.sub(r'\s+', ' ', t).strip()


def pick_words(words, n):
    """The n words worth writing as a whole: frequent and not too short (count x letters covered)."""
    if n <= 0:
        return []
    cand = [(c * (len(w) - 0.5), w) for w, c in words.items() if c >= 2 and len(w) >= 2]
    cand.sort(key=lambda t: (-t[0], t[1]))
    return [w for _, w in cand[:n]]


def pick_fragments(words, chosen, n):
    """Frequent 2-3 letter groups (th, he, ing ...) in the words that are NOT written whole."""
    if n <= 0:
        return []
    chosen = set(chosen)
    grams = collections.Counter()
    for w, c in words.items():
        if w in chosen:
            continue
        lw = w if w.islower() else w[1:] if w[1:].islower() else ''
        for k in (3, 2):
            for i in range(len(lw) - k + 1):
                grams[lw[i:i + k]] += c * (k - 1)
    out = []
    for g, c in grams.most_common():
        if len(out) >= n:
            break
        if c < 3 or g in chosen or any(g in o for o in out if len(o) > len(g)):
            continue
        out.append(g)
    return out

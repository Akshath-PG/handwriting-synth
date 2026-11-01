"""Study a document before making its template: which characters, words and letter groups it uses, and its figures."""
import collections, re, unicodedata
import charset, styles

WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
MARKUP_CMD = re.compile(r'\\[A-Za-z]')


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
    texts, extra, code = _texts(blocks, markup)
    code = set(code)
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
    return dict(style=style, chars=chars, words=words, figures=figs, nwords=nwords,
                nblocks=sum(1 for b in blocks if b[0] != 'pagebreak'))


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

"""Learn how YOU write running text, from the sample sentences on your template.

Single letters written in boxes are neater, more upright and more evenly spaced than real writing. The sentences show
the real thing, so they are measured and the measurements drive the renderer and the human-imperfection model:

  slant        how much more (or less) you lean in a sentence than in single letters      -> extra shear
  word_gap     space between words, in x-heights                                         -> word spacing
  gap_sd       how uneven that spacing is                                                -> spacing jitter
  base_sd      how far words wander above / below the line, in x-heights                 -> word height jitter
  size_sd      how much the size of words varies                                         -> word size jitter
  slope, slope_sd  how much lines run up or down (degrees)                                -> line slope
  join         how often you join neighbouring letters (0..1)                            -> joins
  letter_gap   space between separate letters inside a word, in x-heights                -> letter spacing

Every word of a sentence is also cut out and kept as a sample of that word, written in context ('natural').
Nothing here is a black box: each number is a measurement with a sensible range, and anything that cannot be measured
reliably keeps the default.
"""
import math
import cv2, numpy as np

DEFAULTS = dict(slant=0.0, word_gap=None, gap_sd=0.13, base_sd=None, size_sd=0.018, slope=0.0, slope_sd=0.2,
                join=None, letter_gap=None)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def slant_of(mask):
    """Shear (dx per px upwards) that makes the strokes most upright: the writer's slant, sign: >0 leans right."""
    m = mask.astype(np.float32)
    if m.sum() < 30:
        return None
    h, w = m.shape
    best, best_s = -1, 0.0
    for s in np.arange(-0.7, 0.71, 0.025):
        M = np.float32([[1, s, -s * h], [0, 1, 0]])          # moves the top left when s > 0: undoes a right lean
        pad = int(abs(s) * h) + 2
        big = cv2.copyMakeBorder(m, 0, 0, pad, pad, cv2.BORDER_CONSTANT, value=0)
        M[0, 2] += 0
        sh = cv2.warpAffine(big, M, (big.shape[1], h))
        col = sh.sum(axis=0)
        score = float((col ** 2).sum())
        if score > best:
            best, best_s = score, s
    return float(best_s)


def core_band(mask):
    """(top, baseline) rows of the x-height band of a word / letter image: rows holding a good share of ink."""
    rows = mask.sum(axis=1).astype(np.float32)
    if rows.max() <= 0:
        return None
    on = np.nonzero(rows >= 0.3 * rows.max())[0]
    return int(on.min()), int(on.max())


def _intervals(mask, bridge=2):
    col = cv2.dilate(mask.astype(np.uint8), np.ones((1, 2 * bridge + 1), np.uint8)).max(axis=0) > 0
    out, start = [], None
    for x, v in enumerate(col):
        if v and start is None:
            start = x
        elif not v and start is not None:
            out.append([start, x - 1]); start = None
    if start is not None:
        out.append([start, len(col) - 1])
    return out


def split_words(mask, n, xh):
    """Column ranges of the n words in a written line, or None if the gaps do not clearly show n words."""
    iv = _intervals(mask)
    if len(iv) < n:
        return None
    gaps = [(iv[i + 1][0] - iv[i][1], i) for i in range(len(iv) - 1)]
    if n == 1:
        return [(iv[0][0], iv[-1][1])]
    order = sorted(gaps, reverse=True)
    cut = order[:n - 1]
    rest = order[n - 1:]
    if cut[-1][0] < 0.22 * xh:                             # not even a space
        return None
    if rest and cut[-1][0] < 1.25 * rest[0][0]:            # word gaps not clearly bigger than gaps inside words
        return None
    idx = sorted(i for _, i in cut)
    words, s0 = [], iv[0][0]
    for i in idx:
        words.append((s0, iv[i][1]))
        s0 = iv[i + 1][0]
    words.append((s0, iv[-1][1]))
    return words


def _components(mask, min_share=0.04):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    tot = float(st[1:, 4].sum()) if n > 1 else 0.0
    return sum(1 for i in range(1, n) if tot and st[i, 4] >= min_share * tot)


def _set_line(text, lib):
    """Mask of text set from single-letter glyphs, side by side on one baseline (for comparing slant)."""
    gs = [lib[c] for c in text if c in lib and len(c) == 1]
    if not gs:
        return np.zeros((4, 4), bool)
    up = max(g['alpha'].shape[0] - max(g.get('below', 0), 0) for g in gs) + 4
    dn = max(max(g.get('below', 0), 0) for g in gs) + 8
    W = sum(g['alpha'].shape[1] for g in gs) + 4 * len(gs)
    out = np.zeros((int(up + dn), int(W)), bool)
    x = 0
    for g in gs:
        a = g['alpha'] > 70
        rows = np.nonzero(a.any(axis=1))[0]
        if len(rows) == 0:
            continue
        top = int(up - (rows.max() - g.get('below', 0)) - 1)
        top = max(min(top, out.shape[0] - a.shape[0]), 0)
        out[top:top + a.shape[0], x:x + a.shape[1]] |= a[:out.shape[0] - top]
        x += a.shape[1] + 4
    return out


def learn(lines, glyph_lib, style):
    """lines: [(text, alpha uint8 of the whole written strip, baseline row in that image)].
    glyph_lib: the letters learned from the boxes. Returns (model dict, {word: [samples]}, report lines)."""
    lower = [c for c in 'acemnorsuvwxz' if c in glyph_lib]
    xs = []
    for c in lower:
        cb = core_band(glyph_lib[c]['alpha'] > 70)
        if cb:
            xs.append(cb[1] - cb[0] + 1)
    if not xs:                                              # block capitals: use capital height
        xs = [glyph_lib[c]['h'] for c in 'ABCDEFGHIKLMNOPRSTUVWXYZ' if c in glyph_lib]
    if not xs or not lines:
        return dict(DEFAULTS), {}, []
    xh_glyph = float(np.median(xs))

    words_out, gaps, base_res, sizes, slopes, slants, joins, lgaps = {}, [], [], [], [], [], [], []
    rejected = 0
    for text, alpha, base in lines:
        mask = alpha > 70
        toks = text.split()
        sp = split_words(mask, len(toks), xh_glyph)
        sv, sg = slant_of(mask), slant_of(_set_line(text, glyph_lib))
        if sv is not None and sg is not None:          # like with like: the same text built from your letters
            slants.append(sv - sg)
        if not sp:
            continue
        info = []
        for tok, (a, b) in zip(toks, sp):
            wm = mask[:, a:b + 1]
            cb = core_band(wm)
            if not cb:
                continue
            info.append((tok, a, b, cb))
        if len(info) != len(toks):
            continue
        xhs = [cb[1] - cb[0] + 1 for _, _, _, cb in info]
        xh_line = float(np.median(xhs))
        if not (0.4 * xh_glyph < xh_line < 2.5 * xh_glyph):
            continue
        # spacing, size, baseline
        gaps += [(info[i + 1][1] - info[i][2]) / xh_line for i in range(len(info) - 1)]
        sizes += [x / xh_line for x in xhs]
        cx = np.array([(a + b) / 2.0 for _, a, b, _ in info])
        by = np.array([cb[1] for _, _, _, cb in info], float)
        if len(info) >= 3:
            k, c0 = np.polyfit(cx, by, 1)
            slopes.append(math.degrees(math.atan(k)))
            base_res += list((by - (k * cx + c0)) / xh_line)
        # joins and letter gaps
        for tok, a, b, cb in info:
            letters = sum(ch.isalpha() for ch in tok)
            if letters >= 3 and tok.isalpha():
                comps = _components(mask[:, a:b + 1])
                joins.append(clamp(1 - (comps - 1) / float(letters - 1), 0, 1))
                iv = _intervals(mask[:, a:b + 1], bridge=1)
                lgaps += [(iv[i + 1][0] - iv[i][1]) / xh_line for i in range(len(iv) - 1)]
        # the words themselves, scaled to the size of your single letters
        k = clamp(xh_glyph / xh_line, 0.6, 1.7)
        for tok, a, b, cb in info:
            if len(tok) < 2 or not any(ch.isalpha() for ch in tok):
                continue
            # the cut-out must be about as wide as the word set from your letters: a word that ran off the box,
            # or a mismatch between words and gaps, is not kept
            exp = sum(glyph_lib[ch]['w'] for ch in tok if ch in glyph_lib) * (0.8 if style in ('cursive', 'semi') else 1.0)
            if exp <= 0 or not (0.75 < (b - a + 1) * k / exp < 1.35):
                rejected += 1
                continue
            pad = 4
            a0, b0 = max(a - pad, 0), min(b + pad, alpha.shape[1] - 1)
            sub = alpha[:, a0:b0 + 1]
            rows = np.nonzero((sub > 70).any(axis=1))[0]
            if len(rows) == 0:
                continue
            t0, t1 = max(rows.min() - pad, 0), min(rows.max() + pad, sub.shape[0] - 1)
            crop = sub[t0:t1 + 1]
            crop = cv2.resize(crop, (max(int(crop.shape[1] * k), 1), max(int(crop.shape[0] * k), 1)), interpolation=cv2.INTER_AREA)
            m2 = crop > 70
            ys, xs2 = np.nonzero(m2)
            if len(ys) == 0:
                continue
            base_row = (cb[1] - t0) * k
            g = dict(alpha=crop, h=int(ys.max() - ys.min() + 1), w=int(xs2.max() - xs2.min() + 1), pad=pad,
                     below=float(ys.max() - base_row), word=True, natural=True)
            words_out.setdefault(tok, []).append(g)

    m = dict(DEFAULTS)
    rep = []
    if rejected:
        rep.append('%d word(s) from the sentences were not clear enough to reuse' % rejected)
    if slants:
        m['slant'] = clamp(0.7 * float(np.median(slants)), -0.12, 0.12)       # conservative: 70 % of the difference
        rep.append('slant in sentences %+.1f° compared with your single letters' % math.degrees(math.atan(m['slant'])))
    if len(gaps) >= 3:
        m['word_gap'] = clamp(float(np.median(gaps)), 0.5, 2.6)
        m['gap_sd'] = clamp(float(np.std(gaps)) / max(float(np.mean(gaps)), 1e-3), 0.05, 0.4)
        rep.append('word spacing %.2f x-heights (±%d %%)' % (m['word_gap'], 100 * m['gap_sd']))
    if len(base_res) >= 4:
        r = np.array(base_res)
        m['base_sd'] = clamp(1.4826 * float(np.median(np.abs(r - np.median(r)))), 0.01, 0.12)
        rep.append('words wander ±%.0f %% of an x-height around the line' % (100 * m['base_sd']))
    if len(sizes) >= 4:
        med = float(np.median(sizes))
        m['size_sd'] = clamp(1.4826 * float(np.median(np.abs(np.array(sizes) - med))), 0.01, 0.045)   # robust spread
        rep.append('word size varies ±%.0f %%' % (100 * m['size_sd']))
    if slopes:
        m['slope'] = clamp(float(np.median(slopes)), -1.0, 1.0)
        m['slope_sd'] = clamp(float(np.std(slopes)) if len(slopes) > 1 else 0.2, 0.08, 0.6)
        rep.append('lines run %+.2f° (±%.2f°)' % (m['slope'], m['slope_sd']))
    if len(joins) >= 3 and style != 'caps':
        j = float(np.mean(joins))
        m['join'] = clamp(j, 0.6, 1.0) if style == 'cursive' else clamp(j, 0.1, 0.9) if style == 'semi' else None
        if m['join'] is not None:
            rep.append('you join %d %% of neighbouring letters' % round(100 * m['join']))
    if len(lgaps) >= 5 and style in ('print', 'caps'):
        m['letter_gap'] = clamp(float(np.median(lgaps)), 0.02, 0.6)
        rep.append('letters %.2f x-heights apart' % m['letter_gap'])
    return m, words_out, rep

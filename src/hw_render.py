import os, pickle, cv2, numpy as np, random, math, re

from config import D, U
import config, humanize, styles

# $HW_LIB is read now, not when config was first imported (the command line sets it after importing config)
LIB_PATH = os.environ.get('HW_LIB') or config.LIB

P = pickle.load(open(LIB_PATH, 'rb'))
LIB = P['lib']
CAP = P['cap']          # cap height in library px
# handwriting style: $HW_STYLE overrides the style the library was made with
STYLE = os.environ.get('HW_STYLE') or P.get('style') or 'print'
JOIN = styles.get(STYLE)['joins']
FIGS = P.get('figures', {})                         # your own drawings of figures, by figure key

INK = np.array([36, 52, 128], np.float32)           # RGB

# every sample of every glyph / word: the first one plus second samples ('alts')
SAMPLES = {k: [g] + list(g.get('alts', [])) for k, g in LIB.items()}


def _bbox(a):
    ys, xs = np.where(a > 70)
    if len(ys) == 0:
        ys, xs = np.where(a > 0)
    m = dict(t=float(ys.min()), b=float(ys.max()), l=float(xs.min()), r=float(xs.max()))
    m['h'] = m['b'] - m['t'] + 1
    m['w'] = m['r'] - m['l'] + 1
    return m


SMETA = {k: [_bbox(g['alpha']) for g in gs] for k, gs in SAMPLES.items()}
META = {k: v[0] for k, v in SMETA.items()}          # first sample (kept for older callers)
# words and letter groups learned from a document template (cursive / semi-cursive)
UNITS = {k for k in LIB if len(k) > 1}
MAXU = max([len(k) for k in UNITS] or [1])


def _median(keys, f, default):
    v = [f(k) for k in keys if k in META]
    return float(np.median(v)) if v else default


XH = _median('acmnorsuvz', lambda c: META[c]['h'], 0.62 * CAP)
DESC = float(np.mean([META[c]['h'] - XH for c in 'gpqy' if c in META])) if any(c in META for c in 'gpqy') else 0.35 * CAP

# vertical anchor rules (units: library px, positive = up from baseline)
CENTER = {'-': .33, '–': .33, '−': .33, '+': .40, '/': .40, '\\': .40, '(': .38, ')': .38, '[': .38, ']': .38,
          '{': .38, '}': .38, '|': .38, '<': .35, '>': .35, '=': .35, '@': .42, '~': .30, '·': .30, '×': .30,
          '←': .32, '→': .32, '⇒': .32, '⇔': .32, '≅': .33, '≈': .33, '≤': .33, '≥': .33, '⁻': .70, '_': -.08,
          '∈': .33, '*': .85, '%': .50, '&': .50}
TOP = {'"': 1.0, "'": 1.0, '^': 1.05, ',': 0.10, ';': 0.55, '²': 1.05, 'ᵀ': 1.05, '√': 1.05}
FALLBACK = {'‘': "'", '’': "'", '“': '"', '”': '"', '—': '–', '≠': '=', '′': "'", '≡': '='}


def set_ink(rgb):
    """Change the ink colour (RGB 0-255). Modifies INK in place so every module sees it."""
    INK[:] = np.array(rgb, np.float32)


def anchor_top_above(ch, var=0):
    """px above baseline of the ink top (library scale)."""
    m = SMETA[ch][var] if ch in SMETA else META[ch]
    below = SAMPLES[ch][var].get('below') if ch in SAMPLES else LIB[ch].get('below')
    if below is not None:                      # library made by calibrate.py: baseline is known
        if abs(below) < 0.08 * CAP and (ch.isalnum() or ch in '.,'):
            below = 0.0 if ch not in ',' else below
        return m['h'] - below
    if ch in CENTER:
        return CENTER[ch] * CAP + m['h'] / 2.0
    if ch in TOP:
        return TOP[ch] * CAP
    if ch in 'gpqy':
        return XH
    if ch in 'fj':
        return m['h'] - DESC
    if ch == 'Y':
        return m['h'] - 0.25 * CAP
    return m['h']


def _compute_join_points():
    """Where a pen stroke would enter (left) and leave (right) each sample, near the writing line."""
    widths = []
    for ch, gs in SAMPLES.items():
        for var, g in enumerate(gs):
            a = g['alpha']
            m = SMETA[ch][var]
            mask = (a > 128).astype(np.uint8)
            ys, xs = np.where(mask > 0)
            if len(ys) == 0:
                ys, xs = np.where(a > 0)
            base = m['t'] + anchor_top_above(ch, var)
            zone = (ys >= base - 1.15 * XH) & (ys <= base + 0.30 * XH)
            if zone.sum() < 5:
                zone = np.ones_like(ys, bool)
            zx, zy = xs[zone], ys[zone]
            # joins run along the bottom of the x-height band (where cursive lead-in / lead-out strokes are)
            low = (zy >= base - 0.5 * XH) & (zy <= base + 0.12 * XH)
            lx, ly = (zx[low], zy[low]) if low.sum() >= 3 else (zx, zy)
            xl = lx.min()
            sel = lx <= xl + 3
            m['entry'] = (float(lx[sel].mean()), float(ly[sel].mean()))
            xr = lx.max()
            sel = lx >= xr - 3
            m['exit'] = (float(lx[sel].mean()), float(ly[sel].mean()))
            m['exit_out'] = float(zx.max() - xr)              # ink that sticks out right of the exit point
            if var == 0 and len(ch) == 1 and ch.isalpha() and ch.isascii():
                cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                per = sum(cv2.arcLength(c, True) for c in cnts)
                if per > 0:
                    widths.append(2.0 * mask.sum() / per)
    return float(np.median(widths)) if widths else 0.08 * CAP


STROKE = _compute_join_points()


class Page:
    def __init__(self, W=2480, H=3508, seed=1):
        self.W, self.H = W, H
        self.img = np.ones((H, W, 3), np.float32) * 250
        rng = np.random.default_rng(seed)
        noise = cv2.GaussianBlur(rng.normal(0, 1.0, (H, W)).astype(np.float32), (0, 0), 1.5)
        self.img += noise[..., None] * 1.2
        # soft paper vignette
        yy, xx = np.mgrid[0:H, 0:W]
        v = 1 - 0.018 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        self.img *= v[..., None]
        self.rng = random.Random(seed)

    def blit(self, alpha, x, y, strength=0.96):
        h, w = alpha.shape
        x, y = int(round(x)), int(round(y))
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.W), min(y + h, self.H)
        if x1 <= x0 or y1 <= y0:
            return
        a = (alpha[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32) / 255.0 * strength)[..., None]
        reg = self.img[y0:y1, x0:x1]
        self.img[y0:y1, x0:x1] = reg * (1 - a) + INK[None, None, :] * a

    def line(self, x0, y0, x1, y1, width=3, color=(60, 60, 130), wobble=1.2, strength=0.9):
        n = max(int(math.hypot(x1 - x0, y1 - y0) / 25), 2)
        xs = np.linspace(x0, x1, n)
        ys = np.linspace(y0, y1, n)
        pts = []
        for i, (a, b) in enumerate(zip(xs, ys)):
            pts.append((a + self.rng.gauss(0, wobble), b + self.rng.gauss(0, wobble)))
        mask = np.zeros((self.H, self.W), np.uint8)
        pts_i = np.array(pts, np.int32).reshape(-1, 1, 2)
        cv2.polylines(mask, [pts_i], False, 255, width, cv2.LINE_AA)
        a = (mask.astype(np.float32) / 255.0 * strength)[..., None]
        self.img = self.img * (1 - a) + INK[None, None, :] * a

    def pencil_line(self, x0, y0, x1, y1, width=2, gray=170):
        mask = np.zeros((self.H, self.W), np.uint8)
        cv2.line(mask, (int(x0), int(y0)), (int(x1), int(y1)), 255, width, cv2.LINE_AA)
        a = (mask.astype(np.float32) / 255.0 * 0.45)[..., None]
        self.img = self.img * (1 - a) + np.array([gray, gray, gray + 8], np.float32)[None, None, :] * a

    def rotate(self, deg):
        """Turn the finished sheet by a fraction of a degree (a page is never perfectly square on the desk)."""
        if abs(deg) < 1e-3:
            return
        M = cv2.getRotationMatrix2D((self.W / 2.0, self.H / 2.0), deg, 1.0)
        self.img = cv2.warpAffine(self.img, M, (self.W, self.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    def save(self, path):
        out = np.clip(self.img, 0, 255).astype(np.uint8)
        from imgio import imwrite
        imwrite(path, cv2.cvtColor(out, cv2.COLOR_RGB2BGR))


class Pen:
    """Draws handwriting with the user's glyphs. cap = target cap height in page px.

    Text is split into words; a word is written with the fewest learned units (whole words and letter groups from a
    document template, else single letters). In cursive / semi-cursive, neighbouring lowercase letters are joined with
    a pen stroke from the exit point of one to the entry point of the next. A humanize.Hand adds the small, bounded
    imperfections of a real writer."""

    def __init__(self, page, cap=70, jitter=1.0, seed=3, hand=None):
        self.p = page
        self.cap = cap
        self.j = jitter
        self.r = random.Random(seed)
        self.hand = hand or humanize.Hand('off')
        self.slope = 0.0           # dy/dx of the line being written (set per line by the layout)
        self.salt = 0              # paragraph id: keeps per-word randomness identical between measuring and drawing
        self.slips = False         # crossed-out slips are only allowed while writing running text
        self.plain = False         # True: letter by letter, never joined (code)
        self._depth = 0
        self.last = None

    # ---- raw glyph ----
    def glyph_w(self, ch, s, var=0):
        ch = FALLBACK.get(ch, ch)
        if ch not in SMETA:
            return 0.0
        return SMETA[ch][min(var, len(SMETA[ch]) - 1)]['w'] * s

    def draw_glyph(self, ch, x, base, s, dry=False, rot=None, tint=1.0, var=0, shear0=0.0):
        """Draw one sample (letter, word or letter group) with its ink box starting at x. Returns its width."""
        ch = FALLBACK.get(ch, ch)
        if ch not in LIB:
            return 0.0
        var = min(var, len(SAMPLES[ch]) - 1)
        m = SMETA[ch][var]
        wpx = m['w'] * s
        if dry:
            return wpx
        a = SAMPLES[ch][var]['alpha']
        r = self.r
        long_unit = len(ch) > 1
        sc = s * (1 + r.gauss(0, (0.012 if long_unit else 0.025) * self.j))
        ang = rot if rot is not None else r.gauss(0, (0.5 if long_unit else 1.4) * self.j)
        shear = shear0 + r.gauss(0, (0.012 if long_unit else 0.025) * self.j)
        h0, w0 = a.shape
        resized = cv2.resize(a, (max(int(w0 * sc), 1), max(int(h0 * sc), 1)), interpolation=cv2.INTER_AREA)
        top_above = anchor_top_above(ch, var) * s
        ink_t = m['t'] * sc
        ink_l = m['l'] * sc
        pad = 14 + int(0.06 * h0 * sc)
        big = cv2.copyMakeBorder(resized, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        cx, cy = ink_l + pad, ink_t + m['h'] * sc + pad
        M = cv2.getRotationMatrix2D((cx, cy), -ang, 1.0)
        M[0, 1] += shear
        M[0, 2] -= shear * cy
        warped = cv2.warpAffine(big, M, (big.shape[1], big.shape[0]), flags=cv2.INTER_LINEAR)
        px = x - ink_l - pad
        py = (base - top_above) - ink_t - pad
        self.p.blit(warped, px, py, strength=0.95 * tint)

        def mp(pt):
            X = pt[0] * sc + pad
            Y = pt[1] * sc + pad
            return (px + M[0, 0] * X + M[0, 1] * Y + M[0, 2], py + M[1, 0] * X + M[1, 1] * Y + M[1, 2])

        self.last = dict(entry=mp(m['entry']), exit=mp(m['exit']), sc=sc)
        return wpx

    def connector(self, p0, p3, sc, tint=1.0):
        dx = p3[0] - p0[0]
        if dx < 2.0:
            return
        dy = p3[1] - p0[1]
        k = max(dx * 0.45, 3.0)
        p1 = (p0[0] + k, p0[1] + min(max(dy * 0.05, -0.12 * dx), 0.12 * dx) - 0.06 * dx)
        p2 = (p3[0] - k, p3[1] + 0.0)
        ts = np.linspace(0, 1, 24)
        pts = []
        for t in ts:
            x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
            y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1]
            pts.append((x, y))
        x0 = int(min(p[0] for p in pts)) - 6
        y0 = int(min(p[1] for p in pts)) - 6
        x1 = int(max(p[0] for p in pts)) + 6
        y1 = int(max(p[1] for p in pts)) + 6
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if w <= 0 or h <= 0 or w > 600 or h > 600:
            return
        mask = np.zeros((h, w), np.uint8)
        pi = np.array([(int(round((px - x0) * 8)), int(round((py - y0) * 8))) for px, py in pts], np.int32).reshape(-1, 1, 2)
        sw = max(int(round(STROKE * sc * 0.8)), 2)
        cv2.polylines(mask, [pi // 1], False, 255, sw, cv2.LINE_AA, shift=3)
        mask = cv2.GaussianBlur(mask, (0, 0), 0.6)
        self.p.blit(mask, x0, y0, strength=0.9 * tint)

    # ---- layout helpers ----
    def space(self, s):
        return 0.66 * CAP * s

    def joinable(self, a, b):
        """Can the pen run on from letter a into letter b?"""
        return JOIN > 0 and not self.plain and a.isalpha() and b.isalpha() and a.islower() and b.islower()

    def gap(self, a, b, s):
        base = 0.045 * CAP * s
        if a in '.,:;·' or b in '.,:;':
            base *= 0.6
        if a in '(([{' or b in ')])}':
            base *= 0.5
        return base

    def segment(self, tok):
        """Split a word into the fewest learned units (whole words / letter groups first, else letters)."""
        if not UNITS or len(tok) < 2 or self.plain:
            return list(tok)
        n = len(tok)
        best = [0] + [10 ** 9] * n
        back = [0] * (n + 1)
        for i in range(n):
            if best[i] >= 10 ** 9:
                continue
            for L in range(min(MAXU, n - i), 0, -1):
                if L > 1 and tok[i:i + L] not in UNITS:
                    continue
                if best[i] + 1 < best[i + L]:
                    best[i + L], back[i + L] = best[i] + 1, i
        out, j = [], n
        while j > 0:
            out.append(tok[back[j]:j])
            j = back[j]
        return out[::-1]

    # ---- markup ----
    @staticmethod
    def grab(text, i):
        """text[i] == '{'; returns (content, index after the matching '}')"""
        depth = 1
        j = i + 1
        while j < len(text) and depth:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            j += 1
        return text[i + 1:j - 1], j

    MARKUP = True          # set False to treat ^ _ \\ { } literally (converted PDF/Word text)

    def parse(self, text, raw=False):
        raw = raw or not Pen.MARKUP
        out = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if raw:
                out.append(('ch', c))
                i += 1
                continue
            if c in '^_' and i + 1 < n and text[i + 1] == '{':
                g, j = self.grab(text, i + 1)
                out.append(('sup' if c == '^' else 'sub', g))
                i = j
            elif c == '\\' and i + 2 < n and text[i + 1] in 'ht' and text[i + 2] == '{':
                g, j = self.grab(text, i + 2)
                out.append(('hat' if text[i + 1] == 'h' else 'tilde', g))
                i = j
            elif c == '\\' and i + 2 < n and text[i + 1] == 'f' and text[i + 2] == '{':
                g1, j = self.grab(text, i + 2)
                g2, j = self.grab(text, j)
                out.append(('frac', (g1, g2)))
                i = j
            elif c == '\\' and i + 2 < n and text[i + 1] == 'S' and text[i + 2] == '{':
                g1, j = self.grab(text, i + 2)
                g2, j = self.grab(text, j)
                out.append(('sum', (g1, g2)))
                i = j
            elif c == '\\' and i + 2 < n and text[i + 1] == 'r' and text[i + 2] == '{':
                g, j = self.grab(text, i + 2)
                out.append(('sqrt', g))
                i = j
            elif c == '\\' and i + 2 < n and text[i + 1] == 'M' and text[i + 2] == '{':
                g, j = self.grab(text, i + 2)
                out.append(('mat', g))
                i = j
            else:
                out.append(('ch', c))
                i += 1
        return out

    def _units(self, units, x, base, s, dry, color, prev, rng, hw):
        """Write units side by side, joining them where the style allows. Returns (end x, last character)."""
        exit_x = exit_pt = None
        for u in units:
            key = FALLBACK.get(u, u)
            if key not in SMETA:
                continue
            var = rng.randrange(len(SAMPLES[key])) if len(SAMPLES[key]) > 1 else 0
            m = SMETA[key][var]
            joined = exit_x is not None and self.joinable(prev, key[0]) and rng.random() < JOIN
            if joined:
                xl = max(exit_x + 0.07 * CAP * s - (m['entry'][0] - m['l']) * s, x + 0.01 * CAP * s)
            else:
                if prev and prev != ' ':
                    x += self.gap(prev, key[0], s)
                xl = x
            if not dry:
                self.draw_glyph(key, xl, base + hw.dy * CAP * s, s, tint=color * hw.tint, var=var, shear0=hw.shear,
                                rot=(hw.rot if len(key) > 1 else None) if self.hand.level else None)
                if joined and exit_pt is not None and self.last:
                    self.connector(exit_pt, self.last['entry'], self.last['sc'], tint=color * hw.tint)
                exit_pt = self.last['exit'] if self.last else None
            exit_x = xl + (m['exit'][0] - m['l']) * s
            x = xl + m['w'] * s
            prev = key[-1]
        return x, prev

    def token(self, tok, x, base, s, dry, color, prev, key):
        """Write one word (a run of non-space characters)."""
        rng = humanize.word_rng(self.salt, key)
        hw = self.hand.word(rng, sum(c.isalpha() for c in tok))
        s2 = s * hw.k
        if hw.mistake and self.slips:
            wrong = humanize.typo(tok, rng)
            if wrong:
                xs = x
                if prev and prev != ' ':
                    xs += self.gap(prev, wrong[0], s2)
                x, _ = self._units(self.segment(wrong), x, base, s2, dry, color, prev, rng, hw)
                if not dry:
                    yy = base - 0.42 * XH * s2 + hw.dy * CAP * s
                    for k in range(1 + (rng.random() < 0.4)):
                        dy = (k * 0.22 - 0.1) * XH * s2
                        self.p.line(xs - 4, yy + dy + self.r.gauss(0, 2), x + 4, yy + dy + self.r.gauss(0, 2),
                                    width=max(int(round(STROKE * s2)), 2), wobble=0.8)
                x += self.space(s) * 0.85
                prev = ' '
        return self._units(self.segment(tok), x, base, s2, dry, color, prev, rng, hw)

    def run(self, text, x, base, s=1.0, dry=False, color=1.0, raw=False):
        """Draw markup string starting at x. Returns end x."""
        items = self.parse(text, raw)
        top = self._depth == 0
        slope = self.slope if top else 0.0
        x0 = x
        self._depth += 1
        try:
            return self._run(items, x, x0, base, slope, s, dry, color)
        finally:
            self._depth -= 1

    def _run(self, items, x, x0, base0, slope, s, dry, color):
        prev = ''
        seen = []
        i = 0
        while i < len(items):
            kind, pay = items[i]
            base = base0 + (x - x0) * slope
            if kind == 'ch':
                if pay == ' ':
                    seen.append(' ')
                    x += self.space(s) * self.hand.space(humanize.word_rng(self.salt, ''.join(seen), 'sp'))
                    prev = ' '
                    i += 1
                    continue
                j, tok = i, ''
                while j < len(items) and items[j][0] == 'ch' and items[j][1] != ' ':
                    tok += items[j][1]
                    j += 1
                seen.append(tok)
                x, prev = self.token(tok, x, base, s, dry, color, prev, ''.join(seen))
                i = j
                continue
            i += 1
            seen.append('\x00')
            if kind in ('sup', 'sub'):
                s2 = s * 0.62
                dy = -0.55 * CAP * s if kind == 'sup' else 0.28 * CAP * s
                x += 0.04 * CAP * s
                x = self.run(pay, x, base + dy, s2, dry=dry, color=color)
                prev = 'x'
            elif kind in ('hat', 'tilde'):
                w = self.glyph_w(pay, s)
                if prev and prev != ' ':
                    x += self.gap(prev, pay, s)
                self.draw_glyph(pay, x, base, s, dry=dry, tint=color)
                acc = '^' if kind == 'hat' else '~'
                aw = self.glyph_w(acc, s * 0.55)
                if not dry:
                    self.draw_glyph(acc, x + (w - aw) / 2.0, base - 1.02 * CAP * s, s * 0.55, tint=color)
                x += w
                prev = pay
            elif kind == 'frac':
                a, b = pay
                s2 = s * 0.78
                wa = self.run(a, 0, 0, s2, dry=True)
                wb = self.run(b, 0, 0, s2, dry=True)
                w = max(wa, wb) + 0.25 * CAP * s
                x += 0.08 * CAP * s
                bar = base - 0.30 * CAP * s
                if not dry:
                    self.run(a, x + (w - wa) / 2, bar - 0.20 * CAP * s, s2, color=color)
                    self.run(b, x + (w - wb) / 2, bar + 0.20 * CAP * s + 0.78 * CAP * s, s2, color=color)
                    self.p.line(x, bar, x + w, bar + self.r.gauss(0, 1), width=3, wobble=0.6)
                x += w + 0.08 * CAP * s
                prev = 'x'
            elif kind == 'sum':
                lo, hi = pay
                ss = s * 1.2
                ws = self.glyph_w('Σ', ss)
                wl = self.run(lo, 0, 0, s * 0.55, dry=True) if lo else 0
                wh = self.run(hi, 0, 0, s * 0.55, dry=True) if hi else 0
                w = max(ws, wl, wh)
                x += 0.06 * CAP * s
                if not dry:
                    self.draw_glyph('Σ', x + (w - ws) / 2, base, ss, tint=color)
                    if hi:
                        self.run(hi, x + (w - wh) / 2, base - 1.25 * CAP * s - 0.08 * CAP * s, s * 0.55, color=color)
                    if lo:
                        self.run(lo, x + (w - wl) / 2, base + 0.12 * CAP * s + 0.55 * CAP * s, s * 0.55, color=color)
                x += w + 0.06 * CAP * s
                prev = 'x'
            elif kind == 'sqrt':
                wr = self.glyph_w('√', s * 0.9)
                x += 0.05 * CAP * s
                if not dry:
                    self.draw_glyph('√', x, base, s * 0.9, tint=color)
                x += wr * 0.75
                xs = x
                x = self.run(pay, x, base, s, dry=dry, color=color)
                if not dry:
                    self.p.line(xs - 4, base - 1.08 * CAP * s, x + 4, base - 1.08 * CAP * s, width=3, wobble=0.5)
                prev = 'x'
            elif kind == 'mat':
                rows = [r_.split(',') for r_ in pay.split(';')]
                nr = len(rows)
                nc = max(len(r_) for r_ in rows)
                s2 = s * 0.9
                cw = [0.0] * nc
                for r_ in rows:
                    for ci, e in enumerate(r_):
                        cw[ci] = max(cw[ci], self.run(e.strip(), 0, 0, s2, dry=True))
                colgap = 0.55 * CAP * s
                bw = 0.28 * CAP * s
                total = sum(cw) + colgap * (nc - 1) + 2 * bw
                pitch = 1.40 * CAP * s2
                centre = base - 0.36 * CAP * s
                x += 0.1 * CAP * s
                if not dry:
                    top_y = centre - nr * pitch / 2 + 0.05 * pitch
                    bot_y = centre + nr * pitch / 2 - 0.05 * pitch
                    for sgn, bx in ((1, x), (-1, x + total)):
                        self.p.line(bx + sgn * bw * 0.7, top_y, bx, top_y, width=3, wobble=0.5)
                        self.p.line(bx, top_y, bx, bot_y, width=3, wobble=0.6)
                        self.p.line(bx, bot_y, bx + sgn * bw * 0.7, bot_y, width=3, wobble=0.5)
                    for ri, r_ in enumerate(rows):
                        cy = centre + (ri - (nr - 1) / 2.0) * pitch
                        xx = x + bw
                        for ci, e in enumerate(r_):
                            e = e.strip()
                            we = self.run(e, 0, 0, s2, dry=True)
                            self.run(e, xx + (cw[ci] - we) / 2, cy + 0.5 * CAP * s2, s2, color=color)
                            xx += cw[ci] + colgap
                x += total + 0.1 * CAP * s
                prev = 'x'
        return x

    def width(self, text, s=1.0, raw=False):
        return self.run(text, 0, 0, s, dry=True, raw=raw)

    def wrap(self, text, maxw, s=1.0, raw=False):
        words = text.split(' ')
        lines, cur = [], ''
        for w in words:
            t = (cur + ' ' + w).strip()
            if self.width(t, s, raw) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

"""Small, bounded human imperfections, so a page reads as written by a person rather than typeset in a font.

Every effect is clamped: the eye notices that lines are not perfectly straight, words lean a little differently and
the ink is not perfectly even, but nothing ever overlaps or becomes hard to read.

levels
  off      only the per-letter jitter the renderer always applies
  subtle   (default) + line slope and margin drift, per-word size / slant / height / ink variation, uneven word
           spacing, each page a fraction of a degree off square, ink level varies from page to page
  natural  + now and then a slip of the pen that is crossed out and written again (about one per page)

All decisions that change the WIDTH of a word are drawn from a random generator seeded by the text itself
(word_rng), so measuring a line (for wrapping) and drawing it always agree.
"""
import math, random, zlib

LEVELS = {'off': 0, 'none': 0, 'subtle': 1, 'natural': 2}
SIMILAR = {'a': 'o', 'o': 'a', 'e': 'c', 'c': 'e', 'n': 'm', 'm': 'n', 'u': 'v', 'v': 'u', 'i': 'l', 'l': 'i',
           'r': 'n', 'h': 'n', 'b': 'd', 'd': 'b', 't': 'f', 'f': 't', 's': 'z', 'g': 'q', 'q': 'g', 'p': 'q'}
MISTAKE_RATE = 1 / 300.0


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def level_of(name):
    if isinstance(name, int):
        return clamp(name, 0, 2)
    if name not in LEVELS:
        raise ValueError('unknown imperfection level %r (off, subtle, natural)' % name)
    return LEVELS[name]


def word_rng(*parts):
    return random.Random(zlib.crc32('\x1f'.join(str(p) for p in parts).encode('utf-8')))


class Word:
    __slots__ = ('k', 'shear', 'tint', 'dy', 'rot', 'mistake')

    def __init__(self, k=1.0, shear=0.0, tint=1.0, dy=0.0, rot=0.0, mistake=False):
        self.k, self.shear, self.tint, self.dy, self.rot, self.mistake = k, shear, tint, dy, rot, mistake


PLAIN = Word()


class Hand:
    def __init__(self, level='subtle', seed=0):
        self.level = level_of(level)
        self.r = random.Random(seed * 7919 + 13)
        self.margin = 0.0
        self.trend = self.page_rot = self.slant = 0.0
        self.ink = 1.0
        self.new_page()

    # ---- once per page: the sheet is not perfectly square, the hand settles into a slightly different angle
    def new_page(self):
        if not self.level:
            return
        g = self.r.gauss
        self.trend = clamp(g(0, 0.14), -0.3, 0.3)          # degrees: lines on this page tend to run up / down
        self.page_rot = clamp(g(0, 0.18), -0.4, 0.4)        # degrees: whole page slightly rotated
        self.slant = clamp(g(0, 0.012), -0.025, 0.025)      # extra shear for this page
        self.ink = clamp(g(0.97, 0.02), 0.92, 1.0)          # how freely the pen flows today
        self.margin = clamp(g(0, 6), -12, 12)

    # ---- once per written line
    def line(self):
        """-> (x offset px, slope dy/dx). The left margin wanders a little and no line is perfectly level."""
        if not self.level:
            return 0.0, 0.0
        g = self.r.gauss
        self.margin = clamp(0.75 * self.margin + g(0, 5), -16, 16)
        deg = clamp(self.trend + g(0, 0.2), -0.6, 0.6)
        return self.margin, math.tan(math.radians(-deg))

    # ---- once per word (rng = word_rng(text...), so the same word in the same place always gets the same values)
    def word(self, rng, letters=0):
        if not self.level:
            return PLAIN
        g = rng.gauss
        return Word(k=1 + clamp(g(0, 0.018), -0.04, 0.04),
                    shear=self.slant + clamp(g(0, 0.018), -0.045, 0.045),
                    tint=clamp(g(0.97, 0.03), 0.86, 1.0) * self.ink,
                    dy=clamp(g(0, 0.022), -0.055, 0.055),       # x CAP: word sits a bit above / below the line
                    rot=clamp(g(0, 0.5), -1.2, 1.2),
                    mistake=self.level >= 2 and letters >= 4 and rng.random() < MISTAKE_RATE)

    def space(self, rng):
        """factor for one word space"""
        if not self.level:
            return 1.0
        return 1 + clamp(rng.gauss(0, 0.13), -0.3, 0.35)


def typo(word, rng):
    """A plausible slip: two letters swapped or a similar-looking letter, noticed a letter or two later."""
    if len(word) < 4 or not word.isalpha():
        return None
    i = rng.randrange(1, len(word) - 1)
    if rng.random() < 0.5 and word[i] != word[i + 1]:
        wrong = word[:i] + word[i + 1] + word[i] + word[i + 2:]
    else:
        c = word[i]
        sub = SIMILAR.get(c.lower())
        if not sub:
            return None
        wrong = word[:i] + (sub.upper() if c.isupper() else sub) + word[i + 1:]
    return wrong[:min(len(wrong), i + 1 + rng.randint(0, 1))]

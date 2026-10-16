"""The characters the template asks for, in order. Calibration uses the same list."""
import unicodedata

LOWER = list("abcdefghijklmnopqrstuvwxyz")
UPPER = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS = list("0123456789")
ASCII_PUNCT = list("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
TYPOGRAPHY = list("·×÷–−…°±≠")                       # middle dot, times, divide, en dash, minus, ellipsis, degree, +-, not equal
MATH = list("≈≤≥∈∉⊂⊆∪∩∅∀∃∏∫∂∇√∞→←↔⇒⇔∝≅≡∧∨¬∴")
SUPER = list("²³⁺⁻ⁿᵀ")
SETS = list("ℝℕℤℚℂ")
GREEK_LOWER = list("αβγδεζηθλμνξπρστφχψω")
GREEK_UPPER = list("ΓΔΘΛΞΠΣΦΨΩ")

# characters that must exist for the renderer to measure x-height, descenders and capitals
REQUIRED = LOWER + UPPER + DIGITS + list(".,-()")

ALL = LOWER + UPPER + DIGITS + ASCII_PUNCT + TYPOGRAPHY + MATH + SUPER + SETS + GREEK_LOWER + GREEK_UPPER

# captions printed in the corner of a box where the shape alone is ambiguous
CAPTIONS = {
    'l': 'lowercase L', 'I': 'capital i', 'O': 'capital o', '0': 'zero', 'o': 'lowercase o',
    '1': 'one', '`': 'backtick', "'": 'apostrophe', '"': 'quote', '.': 'full stop', ',': 'comma',
    '-': 'hyphen', '–': 'en dash', '−': 'minus', '_': 'underscore', '|': 'vertical bar',
    '·': 'middle dot', '×': 'times', '÷': 'divide', 'x': 'lowercase x', 'S': 'capital s',
    's': 'lowercase s', 'v': 'lowercase v', 'V': 'capital v', 'w': 'lowercase w', 'W': 'capital w',
    'z': 'lowercase z', 'Z': 'capital z', 'c': 'lowercase c', 'C': 'capital c', 'u': 'lowercase u',
    'U': 'capital u', 'p': 'lowercase p', 'P': 'capital p', 'k': 'lowercase k', 'K': 'capital k',
    'ε': 'epsilon', 'ρ': 'rho', 'ν': 'nu', 'υ': 'upsilon', 'ʋ': '', 'φ': 'phi', 'χ': 'chi',
}


def caption(ch):
    if ch in CAPTIONS and CAPTIONS[ch]:
        return CAPTIONS[ch]
    if ord(ch) > 127:
        return unicodedata.name(ch, 'U+%04X' % ord(ch)).lower().replace('greek ', '').replace(' letter', '').replace('mathematical ', '')[:17]
    return ''


def pages(per_page):
    return [ALL[i:i + per_page] for i in range(0, len(ALL), per_page)]

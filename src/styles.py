"""The handwriting styles a user can choose from.

joins   - probability that two neighbouring lowercase letters are joined by a pen stroke
words   - how many of the document's most frequent words the template asks for (written joined-up, as a whole)
frags   - how many frequent letter groups (th, ing, ...) the template asks for
alts    - how many of the most frequent characters get a second box (so repeated letters are not identical)
caps    - write everything in capital letters
"""

STYLES = {
    'print': dict(
        name='Print', label='Print (separate letters)',
        desc='Every letter written on its own, like most people write notes.',
        joins=0.0, words=0, frags=0, alts=14, caps=False,
        char_hint='Write ONE character per box, on its own, the way you normally print it.',
        word_hint=''),
    'cursive': dict(
        name='Cursive', label='Cursive (joined-up)',
        desc='Joined-up "running" writing: letters in a word are connected.',
        joins=1.0, words=40, frags=24, alts=8, caps=False,
        char_hint='Write each letter in cursive WITH its joining strokes: start at the left dot, finish at the right dot.',
        word_hint='Write each word joined-up, in one go, exactly as you would inside a sentence.'),
    'semi': dict(
        name='Semi-cursive', label='Semi-cursive (some letters joined)',
        desc='A mix: most letters are separate but some run into the next one.',
        joins=0.45, words=20, frags=0, alts=10, caps=False,
        char_hint='Write ONE character per box, the way you write it inside a word.',
        word_hint='Write each word the way you normally do, joining letters where you usually join them.'),
    'caps': dict(
        name='Block capitals', label='Block capitals (ALL CAPS)',
        desc='Everything in capital letters, like on forms and engineering drawings.',
        joins=0.0, words=0, frags=0, alts=12, caps=True,
        char_hint='Write ONE capital letter, digit or symbol per box.',
        word_hint=''),
}
DEFAULT = 'print'
ORDER = ['print', 'cursive', 'semi', 'caps']


def get(style):
    if style not in STYLES:
        raise ValueError('unknown handwriting style %r (choose from %s)' % (style, ', '.join(ORDER)))
    return STYLES[style]


def lib_name(style):
    """File name of the saved library for a style (print keeps the original name lib.pkl)."""
    return 'lib.pkl' if style in (None, '', 'print') else 'lib_%s.pkl' % style


def upper_text(text):
    """Upper-case text but leave maths markup commands (\\f{ \\S{ ...) alone."""
    out, i = [], 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            out.append(text[i:i + 2]); i += 2
            continue
        out.append(text[i].upper()); i += 1
    return ''.join(out)

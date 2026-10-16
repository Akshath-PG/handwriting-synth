"""Clean text before it is drawn, and report characters the user's library cannot draw."""
import re, unicodedata

LIGS = {'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl', ' ': ' ', ' ': ' ', '​': '',
        ' ': ' ', ' ': ' ', '−': '−', '‐': '-', '‑': '-', '‒': '–', '―': '–',
        '‘': "'", '’': "'", '“': '"', '”': '"', '—': '–', '•': '-', '●': '-', '▪': '-', '◦': '-',
        '﻿': '', '­': '', '≠': '≠'}


def clean(text, lib=None):
    """Return (text, dropped) where dropped is a set of characters that cannot be drawn."""
    out, dropped = [], set()
    for ch in text:
        ch = LIGS.get(ch, ch)
        for c in ch:
            if c in '\n ' or lib is None or c in lib or c in "'\"":
                out.append(c)
                continue
            if unicodedata.combining(c):
                continue
            if c == '\t':
                out.append('    ')
                continue
            base = unicodedata.normalize('NFKD', c)
            base = ''.join(b for b in base if not unicodedata.combining(b))
            if base and all((b in lib) for b in base):
                out.append(base)
            else:
                dropped.add(c)
    return ''.join(out), dropped

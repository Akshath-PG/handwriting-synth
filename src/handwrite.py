#!/usr/bin/env python3
"""handwrite.py - make documents in your own handwriting.

  python3 handwrite.py template   [-o template.pdf]           print this, fill it in, photograph each page
  python3 handwrite.py calibrate  p1.jpg p2.jpg ... [-o lib.pkl] [--debug DIR]
  python3 handwrite.py convert    input.(pdf|docx|md|txt) [-o out.pdf] [--lib lib.pkl] [--ink blue|black|#RRGGBB]
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import ROOT, D

INKS = {'blue': (36, 52, 128), 'black': (25, 25, 30), 'blue-black': (30, 38, 80), 'red': (150, 30, 30), 'green': (20, 90, 50)}


def ink_rgb(s):
    if s in INKS:
        return INKS[s]
    s = s.lstrip('#')
    if len(s) == 6:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    raise SystemExit('unknown ink %r' % s)


def main():
    for stream in (sys.stdout, sys.stderr):          # Windows consoles/pipes may not be UTF-8
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('template'); t.add_argument('-o', '--out', default=os.path.join(ROOT, 'assets', 'handwriting_template.pdf'))
    c = sub.add_parser('calibrate'); c.add_argument('photos', nargs='+'); c.add_argument('-o', '--out', default=os.path.join(D, 'lib.pkl'))
    c.add_argument('--debug'); c.add_argument('--threshold', type=float, default=0.72)
    v = sub.add_parser('convert'); v.add_argument('input'); v.add_argument('-o', '--out')
    v.add_argument('--lib', default=None, help='glyph library (default: work/lib.pkl, else the bundled sample)'); v.add_argument('--ink', default='blue')
    v.add_argument('--markup', action='store_true', help='force maths markup on for any input type')
    a = ap.parse_args()

    if a.cmd == 'template':
        import make_template
        n, k = make_template.make(a.out)
        print('wrote %s: %d pages, %d characters. Print it, fill every box, photograph each page in order.' % (a.out, n, k))
    elif a.cmd == 'calibrate':
        import calibrate
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        try:
            calibrate.calibrate(a.photos, a.out, a.debug, a.threshold)
        except calibrate.CalibrationError as e:
            sys.exit('calibration failed: %s' % e)
        print('library saved to', a.out)
    else:
        if a.lib:
            if not os.path.exists(a.lib):
                sys.exit('no glyph library at %s - run "handwrite.py calibrate" first' % a.lib)
            os.environ['HW_LIB'] = os.path.abspath(a.lib)
        import hw_render, blocks, loaders
        hw_render.set_ink(ink_rgb(a.ink))
        bl, markup = loaders.load(a.input)
        if not any(b[0] != 'pagebreak' for b in bl):
            sys.exit('No text was found in this file. If it is a scanned PDF or only pictures, it cannot be converted.')
        out = a.out or os.path.splitext(a.input)[0] + '_handwritten.pdf'
        blocks.render(bl, out, markup=markup or a.markup)


if __name__ == '__main__':
    main()

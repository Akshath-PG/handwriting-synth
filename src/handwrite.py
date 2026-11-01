#!/usr/bin/env python3
"""handwrite.py - make documents in your own handwriting.

  python3 handwrite.py template   [--doc FILE --style cursive] [-o template.pdf]
        no --doc : the universal template (174 characters, print style)
        --doc    : a template made for that document: its characters, its most used words (cursive / semi-cursive),
                   a second sample of its most used letters and a box to trace each figure. A description of the
                   boxes is saved next to it (template.json); calibrate needs it.
  python3 handwrite.py calibrate  p1.jpg p2.jpg ... [--template template.json] [-o lib.pkl] [--debug DIR]
  python3 handwrite.py convert    input.(pdf|docx|md|txt) [-o out.pdf] [--style cursive] [--lib lib.pkl]
                                  [--ink blue|black|#RRGGBB] [--human off|subtle|natural]

  styles: print, cursive, semi (semi-cursive), caps (block capitals)
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import ROOT, D
import styles

INKS = {'blue': (36, 52, 128), 'black': (25, 25, 30), 'blue-black': (30, 38, 80), 'red': (150, 30, 30), 'green': (20, 90, 50)}
SAMPLE = os.path.join(ROOT, 'examples', 'sample_library.pkl')


def ink_rgb(s):
    if s in INKS:
        return INKS[s]
    s = s.lstrip('#')
    if len(s) == 6:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    raise SystemExit('unknown ink %r' % s)


def default_lib(style):
    """Your saved library for this style, else your print library, else the bundled sample."""
    for name in (styles.lib_name(style), styles.lib_name('print')):
        p = os.path.join(D, name)
        if os.path.exists(p):
            return p
    return SAMPLE


def make_template(doc, style, out, log=print):
    import make_template, plan as PL
    if not doc:
        n, k = make_template.make(out)
        PL.save(PL.universal_plan(), PL.manifest_path(out))
        log('wrote %s: %d pages, %d characters. Print it, fill every box, photograph each page.' % (out, n, k))
        return PL.universal_plan()
    import loaders, study
    bl, markup = loaders.load(doc, log=lambda m: None)
    if not any(b[0] != 'pagebreak' for b in bl):
        raise SystemExit('No text was found in this file. If it is a scanned PDF or only pictures, it cannot be converted.')
    st = study.study(bl, markup, style)
    try:
        p = PL.document_plan(st, doc)
    except ValueError as e:
        raise SystemExit(str(e))
    figs = {f['key']: f for f in st['figures']}
    make_template.make(out, p, figs)
    PL.save(p, PL.manifest_path(out))
    sm = p['summary']
    log('studied %s: about %d words, %d different characters, %d figure(s)' % (os.path.basename(doc), sm['nwords'], len(st['chars']), sm['figures']))
    log('wrote %s (%s style): %d page(s) with %d characters, %d second samples, %d words / letter groups, %d figure box(es)'
        % (out, styles.get(style)['name'], sm['pages'], sm['chars'], sm['alts'], sm['words'] + sm['fragments'], sm['figures']))
    log('box description saved to %s (pass it to "calibrate --template")' % PL.manifest_path(out))
    return p


def main():
    for stream in (sys.stdout, sys.stderr):          # Windows consoles/pipes may not be UTF-8
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('template'); t.add_argument('-o', '--out', default=None)
    t.add_argument('--doc', help='make the template for this document (.pdf .docx .md .txt)')
    t.add_argument('--style', default='print', choices=styles.ORDER)
    c = sub.add_parser('calibrate'); c.add_argument('photos', nargs='+'); c.add_argument('-o', '--out', default=None)
    c.add_argument('--template', help='the .json saved next to a document template (default: universal template)')
    c.add_argument('--debug'); c.add_argument('--threshold', type=float, default=0.72)
    c.add_argument('--fresh', action='store_true', help='do not keep glyphs from your earlier library of the same style')
    c.add_argument('--merge', default=None, help='earlier library to keep glyphs from (default: the output file)')
    v = sub.add_parser('convert'); v.add_argument('input'); v.add_argument('-o', '--out')
    v.add_argument('--lib', default=None, help='glyph library (default: your library for --style, else the bundled sample)')
    v.add_argument('--style', default=None, choices=styles.ORDER, help='handwriting style (default: the library\'s own)')
    v.add_argument('--ink', default='blue')
    v.add_argument('--human', default='subtle', choices=['off', 'subtle', 'natural'],
                   help='human imperfections: off, subtle (default), natural (adds rare crossed-out slips)')
    v.add_argument('--seed', type=int, default=1, help='change to get a differently written copy')
    v.add_argument('--markup', action='store_true', help='force maths markup on for any input type')
    a = ap.parse_args()

    if a.cmd == 'template':
        out = a.out or (os.path.join(ROOT, 'assets', 'handwriting_template.pdf') if not a.doc else
                        os.path.splitext(a.doc)[0] + '_template_%s.pdf' % a.style)
        make_template(a.doc, a.style, out)
    elif a.cmd == 'calibrate':
        import calibrate, plan as PL
        try:
            p = PL.load(a.template)
        except (OSError, ValueError) as e:
            sys.exit('calibration failed: cannot read the template description: %s' % e)
        p0 = p
        p, _ = calibrate.choose_plan(a.photos, p)
        if p is not p0:
            print('these photos show the universal template, so it is used instead of %s' % os.path.basename(a.template))
        out = a.out or os.path.join(D, styles.lib_name(p.get('style')))
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        tmp = out + '.new'
        try:
            calibrate.calibrate(a.photos, tmp, a.debug, a.threshold, plan=p, merge=None if a.fresh else (a.merge or out))
        except calibrate.CalibrationError as e:
            sys.exit('calibration failed: %s' % e)
        os.replace(tmp, out)
        print('library saved to', out)
    else:
        lib = a.lib or default_lib(a.style or 'print')
        if not os.path.exists(lib):
            sys.exit('no glyph library at %s - run "handwrite.py calibrate" first' % lib)
        os.environ['HW_LIB'] = os.path.abspath(lib)
        if a.style:
            os.environ['HW_STYLE'] = a.style
        import hw_render, blocks, loaders
        hw_render.set_ink(ink_rgb(a.ink))
        bl, markup = loaders.load(a.input)
        if not any(b[0] != 'pagebreak' for b in bl):
            sys.exit('No text was found in this file. If it is a scanned PDF or only pictures, it cannot be converted.')
        out = a.out or os.path.splitext(a.input)[0] + '_handwritten.pdf'
        print('style: %s, library: %s' % (styles.get(hw_render.STYLE)['name'], os.path.basename(lib)))
        blocks.render(bl, out, markup=markup or a.markup, human=a.human, seed=a.seed)


if __name__ == '__main__':
    main()

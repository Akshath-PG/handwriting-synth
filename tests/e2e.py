"""Cross-platform end-to-end test (Windows, macOS, Linux). No handwriting needed.

  1. universal template -> fake phone photos -> calibrate -> convert .md / .docx / .pdf
  2. cursive template made for a document with a chart -> fake photos in shuffled order (page codes) ->
     calibrate (words + traced chart) -> convert with the 'natural' human imperfections
Runs inside folders whose names contain spaces and accents, with a legacy console encoding, to catch the usual
Windows problems.   usage: python tests/e2e.py
"""
import os, subprocess, sys, tempfile, shutil
import pypdfium2 as pdfium
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, 'src', 'handwrite.py')


def run(args, env=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([sys.executable] + args, capture_output=True, env=e)
    out = (p.stdout + p.stderr).decode('utf-8', 'replace')
    print('$', ' '.join(os.path.basename(a) for a in args[:3]), '->', p.returncode)
    if p.returncode:
        print(out)
        sys.exit('FAILED: ' + ' '.join(args))
    return out


def pages(pdf):
    assert os.path.getsize(pdf) > 10000, pdf
    return len(pdfium.PdfDocument(pdf))


def main():
    tmp = tempfile.mkdtemp(prefix='hw ünï ')
    home = os.path.join(tmp, 'my hömé')
    env = {'HW_HOME': home, 'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0'}
    run([HW, 'template', '-o', os.path.join(tmp, 'template.pdf')], env)
    assert pages(os.path.join(tmp, 'template.pdf')) == 4
    photos = os.path.join(tmp, 'phötos')
    run([os.path.join(ROOT, 'tests', 'simulate_photos.py'), os.path.join(tmp, 'template.pdf'),
         os.path.join(ROOT, 'examples', 'sample_library.pkl'), photos], env)
    lib = os.path.join(home, 'lib.pkl')
    out = run([HW, 'calibrate'] + [os.path.join(photos, 'photo_%d.jpg' % i) for i in (1, 2, 3, 4)] +
              ['-o', lib, '--debug', os.path.join(tmp, 'dbg')], env)
    assert 'glyphs: 118 of 174' in out, out
    for src, name in (('examples/demo.md', 'md'), ('tests/sample.docx', 'docx'), ('examples/source_assignment.pdf', 'pdf')):
        o = os.path.join(tmp, name + '.pdf')
        run([HW, 'convert', os.path.join(ROOT, src), '-o', o, '--lib', lib], env)
        n = pages(o)
        print('  %s -> %d page(s)' % (name, n))
        assert n >= 1
    # ---- 2. a template made for one document, in cursive
    doc = os.path.join(ROOT, 'tests', 'figure_doc.md')
    tpl = os.path.join(tmp, 'doc template.pdf')
    out = run([HW, 'template', '--doc', doc, '--style', 'cursive', '-o', tpl], env)
    assert '1 figure box' in out, out
    assert os.path.exists(os.path.join(tmp, 'doc template.json'))
    n = pages(tpl)
    photos2 = os.path.join(tmp, 'phötos 2')
    run([os.path.join(ROOT, 'tests', 'simulate_photos.py'), tpl, os.path.join(ROOT, 'examples', 'sample_library.pkl'),
         photos2, '2', '--shuffle'], env)
    out = run([HW, 'calibrate'] + [os.path.join(photos2, 'photo_%d.jpg' % i) for i in range(1, n + 1)] +
              ['--template', os.path.join(tmp, 'doc template.json')], env)
    assert os.path.exists(os.path.join(home, 'lib_cursive.pkl')), out
    assert 'words / letter groups' in out and '1 drawings' in out, out
    if n > 1:
        assert 'page order' in out, out
    o = os.path.join(tmp, 'cursive.pdf')
    out = run([HW, 'convert', doc, '-o', o, '--style', 'cursive', '--human', 'natural'], env)
    assert '1 drawn by you' in out, out
    print('  cursive document template (%d pages) -> %d page(s)' % (n, pages(o)))
    # photos of the universal template are recognised even when a document template is given
    out = run([HW, 'calibrate'] + [os.path.join(photos, 'photo_%d.jpg' % i) for i in (1, 2, 3, 4)] +
              ['--template', os.path.join(tmp, 'doc template.json'), '-o', os.path.join(tmp, 'again.pkl')], env)
    assert 'universal template' in out and 'glyphs: 118 of 174' in out, out
    shutil.rmtree(tmp, ignore_errors=True)
    print('E2E OK')


if __name__ == '__main__':
    main()

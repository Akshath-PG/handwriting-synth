"""Handwriting Synth - the point-and-click app.

Starts a small web page on your own computer (nothing is uploaded anywhere) and opens it in your browser:
  1. upload the document   2. choose a handwriting style   3. get a template made for that document, print + fill it
  4. upload photos of it   5. get the document back, handwritten
"""
import os, sys, json, shutil, subprocess, threading, time, uuid, webbrowser, socket, pickle
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---- "--cli ..." lets the packaged app call itself for the heavy work (keeps every job isolated)
if '--cli' in sys.argv:
    i = sys.argv.index('--cli')
    sys.argv = [sys.argv[0]] + sys.argv[i + 1:]
    import handwrite
    handwrite.main()
    sys.exit(0)

from flask import Flask, request, jsonify, send_file, abort, Response
from werkzeug.utils import secure_filename
from config import D, FROZEN, ROOT
import styles

HOME = D.rstrip(os.sep)
PHOTOS, UPLOADS, OUTS, DEBUG, PROJECT = [os.path.join(HOME, n) for n in ('photos', 'uploads', 'outputs', 'debug', 'project')]
for p in (PHOTOS, UPLOADS, OUTS, DEBUG, PROJECT):
    os.makedirs(p, exist_ok=True)
LIBFILE = os.path.join(HOME, 'lib.pkl')
PROJ_JSON = os.path.join(PROJECT, 'project.json')
TPL_PDF, TPL_JSON = os.path.join(PROJECT, 'template.pdf'), os.path.join(PROJECT, 'template.json')
ALLOWED = {'.pdf', '.docx', '.md', '.txt'}
IMAGES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tif', '.tiff'}
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 400 * 1024 * 1024
JOBS, LOCK = {}, threading.Lock()


def run_cli(args, timeout=1800):
    cmd = [sys.executable, '--cli'] if FROZEN else [sys.executable, os.path.abspath(__file__), '--cli']
    env = dict(os.environ, HW_HOME=HOME, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    env.pop('HW_LIB', None)
    env.pop('HW_STYLE', None)
    extra = {'creationflags': 0x08000000} if sys.platform == 'win32' else {}      # no console flash on Windows
    p = subprocess.run(cmd + args, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env,
                       timeout=timeout, **extra)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def friendly(msg):
    m = msg.strip().splitlines()
    for line in reversed(m):
        if line.startswith('calibration failed:'):
            return line.replace('calibration failed:', '').strip()
    return (m[-1] if m else 'Something went wrong.')


def lib_path(style):
    return os.path.join(HOME, styles.lib_name(style))


def project():
    try:
        with open(PROJ_JSON, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def coverage(style):
    """What the saved library of this style still lacks for the current project's template."""
    if not os.path.exists(TPL_JSON) or not os.path.exists(lib_path(style)):
        return None
    try:
        tpl = json.load(open(TPL_JSON, encoding='utf-8'))
        P = pickle.load(open(lib_path(style), 'rb'))
    except Exception:
        return None
    lib, figs = P.get('lib', {}), P.get('figures', {})
    cells = [c for pg in tpl['pages'] for c in pg]
    chars = [c['t'] for c in cells if c['k'] == 'char' and not c.get('alt') and c['t'] not in lib]
    words = [c['t'] for c in cells if c['k'] == 'word' and not c.get('alt') and c['t'] not in lib]
    nfig = sum(1 for c in cells if c['k'] == 'figure' and c.get('key') not in figs)
    return dict(chars=chars, words=len(words), figures=nfig)


@app.get('/')
def index():
    return Response(PAGE, mimetype='text/html')


@app.get('/api/state')
def state():
    pr = project()
    return jsonify(has_library=os.path.exists(LIBFILE), home=HOME,
                   libs={s: os.path.exists(lib_path(s)) for s in styles.ORDER},
                   styles=[dict(id=s, label=styles.STYLES[s]['label'], desc=styles.STYLES[s]['desc']) for s in styles.ORDER],
                   project=pr, coverage=coverage(pr['style']) if pr else None)


@app.get('/template.pdf')
def template():
    """The universal template (all 174 characters, print style)."""
    out = os.path.join(HOME, 'handwriting_template.pdf')
    code, log = run_cli(['template', '-o', out])
    if code:
        abort(500, log)
    return send_file(out, as_attachment=True, download_name='handwriting_template.pdf')


@app.post('/api/study')
def study():
    """Upload the document + choose a style -> a template made for this document."""
    f = request.files.get('doc')
    style = request.form.get('style', 'print')
    if style not in styles.STYLES:
        return jsonify(ok=False, error='Please choose a handwriting style.')
    pr = project()
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED:
            return jsonify(ok=False, error='This file type is not supported. Use PDF, Word (.docx), .md or .txt.')
        name = secure_filename(f.filename) or ('document' + ext)
        src = os.path.join(UPLOADS, name)
        f.save(src)
        for x in request.files.getlist('extra'):         # pictures a Markdown / text file refers to
            xn = secure_filename(x.filename or '')
            if xn and os.path.splitext(xn)[1].lower() in IMAGES:
                x.save(os.path.join(UPLOADS, xn))
    elif pr and os.path.exists(pr.get('doc', '')):
        src, name = pr['doc'], pr['name']
    else:
        return jsonify(ok=False, error='Please choose your document first.')
    with LOCK:
        code, log = run_cli(['template', '--doc', src, '--style', style, '-o', TPL_PDF])
    if code or not os.path.exists(TPL_JSON):
        return jsonify(ok=False, error=friendly(log))
    tpl = json.load(open(TPL_JSON, encoding='utf-8'))
    pr = dict(doc=src, name=name, style=style, template_id=tpl['id'], summary=tpl['summary'],
              words=tpl.get('wordlist', [])[:12])
    json.dump(pr, open(PROJ_JSON, 'w', encoding='utf-8'))
    return jsonify(ok=True, project=pr, coverage=coverage(style), template='/project/template.pdf?t=%d' % time.time())


@app.get('/project/template.pdf')
def project_template():
    pr = project()
    if not pr or not os.path.exists(TPL_PDF):
        abort(404)
    stem = os.path.splitext(pr['name'])[0]
    return send_file(TPL_PDF, as_attachment=True, download_name='%s_template_%s.pdf' % (stem, pr['style']))


@app.get('/project/template.json')
def project_template_json():
    if not os.path.exists(TPL_JSON):
        abort(404)
    return send_file(TPL_JSON, mimetype='application/json')


@app.post('/api/calibrate')
def calibrate():
    files = request.files.getlist('photos')
    if not files:
        return jsonify(ok=False, error='Please choose your photos first.')
    shutil.rmtree(PHOTOS, ignore_errors=True)
    os.makedirs(PHOTOS)
    paths = []
    for i, f in enumerate(files):
        p = os.path.join(PHOTOS, 'photo_%02d%s' % (i + 1, os.path.splitext(f.filename or '.jpg')[1].lower() or '.jpg'))
        f.save(p)
        paths.append(p)
    shutil.rmtree(DEBUG, ignore_errors=True)
    args = ['calibrate'] + paths + ['--debug', DEBUG]
    if project() and os.path.exists(TPL_JSON) and request.form.get('universal') != '1':
        args += ['--template', TPL_JSON]
    with LOCK:
        code, log = run_cli(args)
    if code:
        return jsonify(ok=False, error=friendly(log))
    missing, learned, saved = '', '', ''
    for line in log.splitlines():
        if line.startswith('empty boxes'):
            missing = line.split(':', 1)[1].strip()
        elif line.startswith('also learned:'):
            learned = line.split(':', 1)[1].strip()
        elif line.startswith('library saved to'):
            saved = line.split('to', 1)[1].strip()
    style = 'print'
    for s in styles.ORDER:
        if os.path.basename(saved) == styles.lib_name(s):
            style = s
    warns = [l[9:] for l in log.splitlines() if l.startswith('warning: ')]
    return jsonify(ok=True, missing=missing, warnings=warns, learned=learned, style=style,
                   style_label=styles.STYLES[style]['label'],
                   sheet='/file/debug/glyph_sheet.png?t=%d' % time.time())


@app.post('/api/convert')
def convert():
    f = request.files.get('doc')
    pr = project()
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED:
            return jsonify(ok=False, error='This file type is not supported. Use PDF, Word (.docx), .md or .txt.')
        name = secure_filename(f.filename) or ('document' + ext)
        src = os.path.join(UPLOADS, name)
        f.save(src)
    elif pr and os.path.exists(pr.get('doc', '')):
        src, name = pr['doc'], pr['name']
    else:
        return jsonify(ok=False, error='Please choose a file first.')
    style = request.form.get('style') or (pr or {}).get('style') or 'print'
    if style not in styles.STYLES:
        style = 'print'
    human = request.form.get('human', 'subtle')
    if human not in ('off', 'subtle', 'natural'):
        human = 'subtle'
    stem = os.path.splitext(name)[0]
    out = os.path.join(OUTS, stem + '_handwritten.pdf')
    ink = request.form.get('ink', 'blue')
    use_sample = request.form.get('sample') == '1'
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = dict(state='running', msg='', out=None)

    def work():
        args = ['convert', src, '-o', out, '--ink', ink, '--style', style, '--human', human]
        if use_sample:
            args += ['--lib', os.path.join(ROOT, 'examples', 'sample_library.pkl')]
        with LOCK:
            code, log = run_cli(args)
        if code or not os.path.exists(out):
            JOBS[jid] = dict(state='error', msg=friendly(log), out=None)
            return
        prev = os.path.join(OUTS, stem + '_preview.jpg')
        pg = os.path.join(HOME, 'pages', 'page_01.jpg')
        if os.path.exists(pg):
            shutil.copy(pg, prev)
        notes = [l for l in log.splitlines() if l.startswith(('skipped', 'figures:', 'style:'))]
        JOBS[jid] = dict(state='done', msg=' · '.join(notes), out=os.path.basename(out), preview=os.path.basename(prev))
    threading.Thread(target=work, daemon=True).start()
    return jsonify(ok=True, job=jid)


@app.get('/api/job/<jid>')
def job(jid):
    return jsonify(JOBS.get(jid, dict(state='error', msg='Unknown job')))


@app.get('/file/<path:rel>')
def file(rel):
    p = os.path.realpath(os.path.join(HOME, rel))
    if not p.startswith(os.path.realpath(HOME)) or not os.path.isfile(p):
        abort(404)
    return send_file(p, as_attachment=rel.endswith('.pdf') and rel.startswith('outputs'))


def free_port(start=8765):
    for p in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return 0


def main():
    port = free_port()
    url = 'http://127.0.0.1:%d' % port
    print('Handwriting Synth is running at', url)
    print('Keep this window open while you use it. Close it to quit.')
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=port, threaded=True)


PAGE = open(os.path.join(HERE, 'app_page.html'), encoding='utf-8').read() if os.path.exists(os.path.join(HERE, 'app_page.html')) \
    else open(os.path.join(ROOT, 'app_page.html'), encoding='utf-8').read()

if __name__ == '__main__':
    main()

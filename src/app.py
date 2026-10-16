"""Handwriting Synth - the point-and-click app.

Starts a small web page on your own computer (nothing is uploaded anywhere) and opens it in your browser:
  1. download + print the template   2. upload photos of it   3. drop a document, get it back handwritten
"""
import os, sys, shutil, subprocess, threading, time, uuid, webbrowser, socket
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

HOME = D.rstrip(os.sep)
PHOTOS, UPLOADS, OUTS, DEBUG = [os.path.join(HOME, n) for n in ('photos', 'uploads', 'outputs', 'debug')]
for p in (PHOTOS, UPLOADS, OUTS, DEBUG):
    os.makedirs(p, exist_ok=True)
LIBFILE = os.path.join(HOME, 'lib.pkl')
ALLOWED = {'.pdf', '.docx', '.md', '.txt'}
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 400 * 1024 * 1024
JOBS, LOCK = {}, threading.Lock()


def run_cli(args, timeout=1800):
    cmd = [sys.executable, '--cli'] if FROZEN else [sys.executable, os.path.abspath(__file__), '--cli']
    env = dict(os.environ, HW_HOME=HOME, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    env.pop('HW_LIB', None)
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


@app.get('/')
def index():
    return Response(PAGE, mimetype='text/html')


@app.get('/api/state')
def state():
    return jsonify(has_library=os.path.exists(LIBFILE), home=HOME)


@app.get('/template.pdf')
def template():
    out = os.path.join(HOME, 'handwriting_template.pdf')
    code, log = run_cli(['template', '-o', out])
    if code:
        abort(500, log)
    return send_file(out, as_attachment=True, download_name='handwriting_template.pdf')


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
    with LOCK:
        code, log = run_cli(['calibrate'] + paths + ['-o', LIBFILE + '.new', '--debug', DEBUG])
    if code:
        return jsonify(ok=False, error=friendly(log))
    os.replace(LIBFILE + '.new', LIBFILE)
    missing = ''
    for line in log.splitlines():
        if line.startswith('empty boxes'):
            missing = line.split(':', 1)[1].strip()
    warns = [l[9:] for l in log.splitlines() if l.startswith('warning: ')]
    return jsonify(ok=True, missing=missing, warnings=warns, sheet='/file/debug/glyph_sheet.png?t=%d' % time.time())


@app.post('/api/convert')
def convert():
    f = request.files.get('doc')
    if not f or not f.filename:
        return jsonify(ok=False, error='Please choose a file first.')
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return jsonify(ok=False, error='This file type is not supported. Use PDF, Word (.docx), .md or .txt.')
    name = secure_filename(f.filename) or ('document' + ext)
    src = os.path.join(UPLOADS, name)
    f.save(src)
    stem = os.path.splitext(name)[0]
    out = os.path.join(OUTS, stem + '_handwritten.pdf')
    ink = request.form.get('ink', 'blue')
    use_sample = request.form.get('sample') == '1' or not os.path.exists(LIBFILE)
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = dict(state='running', msg='', out=None)

    def work():
        args = ['convert', src, '-o', out, '--ink', ink]
        if not use_sample:
            args += ['--lib', LIBFILE]
        else:
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
        skipped = [l for l in log.splitlines() if l.startswith('skipped') or l.startswith('note:')]
        JOBS[jid] = dict(state='done', msg=' '.join(skipped), out=os.path.basename(out), preview=os.path.basename(prev))
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

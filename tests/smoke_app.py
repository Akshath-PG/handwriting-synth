"""Start the PACKAGED app and drive it like a user would.   usage: python tests/smoke_app.py PATH_TO_APP_EXECUTABLE
(from source: python tests/smoke_app.py python3 src/app.py)

  1. universal template -> 4 photos -> learn -> convert md / docx / pdf
  2. upload a document + choose cursive -> its own template -> photos in any order -> learn -> convert"""
import os, subprocess, sys, tempfile, time
import requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))


def main(*exe):
    home = tempfile.mkdtemp(prefix='hw ünï ')                      # fake user profile with accents + spaces
    env = dict(os.environ, HOME=home, USERPROFILE=home, PYTHONIOENCODING='cp1252')
    env.pop('HW_HOME', None)
    log = open(os.path.join(home, 'app.log'), 'wb')
    proc = subprocess.Popen(list(exe), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = None
    try:
        for _ in range(90):
            for port in range(8765, 8805):
                try:
                    if requests.get('http://127.0.0.1:%d/api/state' % port, timeout=1).ok:
                        base = 'http://127.0.0.1:%d' % port
                        break
                except Exception:
                    pass
            if base:
                break
            time.sleep(1)
        assert base, 'app did not start'
        print('app is up at', base)
        tpl = os.path.join(home, 'template.pdf')
        r = requests.get(base + '/template.pdf')
        assert r.status_code == 200 and r.content[:4] == b'%PDF', 'template download failed'
        open(tpl, 'wb').write(r.content)
        import simulate_photos
        photos = os.path.join(home, 'photos')
        simulate_photos.main(tpl, os.path.join(ROOT, 'examples', 'sample_library.pkl'), photos)
        files = [('photos', open(os.path.join(photos, 'photo_%d.jpg' % i), 'rb')) for i in (1, 2, 3, 4)]
        r = requests.post(base + '/api/calibrate', files=files).json()
        assert r['ok'], r
        print('calibrated; empty boxes:', len(r['missing'].split()))
        def convert(files, data):
            r = requests.post(base + '/api/convert', files=files, data=data).json()
            assert r['ok'], r
            for _ in range(300):
                j = requests.get(base + '/api/job/' + r['job']).json()
                if j['state'] != 'running':
                    break
                time.sleep(2)
            assert j['state'] == 'done', j
            d = requests.get(base + '/file/outputs/' + j['out'])
            assert d.status_code == 200 and d.content[:4] == b'%PDF', 'download failed'
            return j, d

        for src in ('examples/demo.md', 'tests/sample.docx', 'examples/source_assignment.pdf'):
            j, d = convert({'doc': open(os.path.join(ROOT, src), 'rb')}, {'ink': 'black', 'style': 'print'})
            print(src, 'OK', len(d.content), 'bytes')

        # ---- 2. document -> cursive template made for it -> photos in any order -> handwritten
        doc = os.path.join(ROOT, 'tests', 'figure_doc.md')
        r = requests.post(base + '/api/study', files=[('doc', open(doc, 'rb')), ('extra', open(os.path.join(ROOT, 'tests', 'chart.png'), 'rb'))],
                          data={'style': 'cursive'}).json()
        assert r['ok'], r
        sm = r['project']['summary']
        assert sm['figures'] == 1 and sm['words'] > 0, sm
        print('studied: %(pages)d page template, %(chars)d chars, %(words)d words, %(figures)d figure' % sm)
        tpl2 = os.path.join(home, 'doc_template.pdf')
        t = requests.get(base + '/project/template.pdf')
        assert t.status_code == 200 and t.content[:4] == b'%PDF', 'document template download failed'
        open(tpl2, 'wb').write(t.content)
        open(os.path.join(home, 'doc_template.json'), 'wb').write(requests.get(base + '/project/template.json').content)
        photos2 = os.path.join(home, 'photos2')
        simulate_photos.main(tpl2, os.path.join(ROOT, 'examples', 'sample_library.pkl'), photos2, 2, shuffle=True)
        files = [('photos', open(os.path.join(photos2, f), 'rb')) for f in sorted(os.listdir(photos2))]
        r = requests.post(base + '/api/calibrate', files=files).json()
        assert r['ok'] and r['style'] == 'cursive' and r['model'], r
        print('learned cursive:', r['learned'])
        st = requests.get(base + '/api/state').json()
        assert st['libs']['cursive'] and st['coverage'] is not None, st
        j, d = convert({}, {'ink': 'blue', 'human': 'natural'})
        assert '1 drawn by you' in j['msg'], j
        print('cursive document OK', len(d.content), 'bytes;', j['msg'])
        print('SMOKE OK')
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()
        log.close()
        if 'base' in dir() and base is None:
            print(open(os.path.join(home, 'app.log'), 'rb').read().decode('utf-8', 'replace'))


if __name__ == '__main__':
    main(*sys.argv[1:])

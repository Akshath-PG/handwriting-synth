"""Start the PACKAGED app and drive it like a user would.   usage: python tests/smoke_app.py PATH_TO_APP_EXECUTABLE"""
import os, subprocess, sys, tempfile, time
import requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))


def main(exe):
    home = tempfile.mkdtemp(prefix='hw ünï ')                      # fake user profile with accents + spaces
    env = dict(os.environ, HOME=home, USERPROFILE=home, PYTHONIOENCODING='cp1252')
    env.pop('HW_HOME', None)
    log = open(os.path.join(home, 'app.log'), 'wb')
    proc = subprocess.Popen([exe], env=env, stdout=log, stderr=subprocess.STDOUT)
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
        for src in ('examples/demo.md', 'tests/sample.docx', 'examples/source_assignment.pdf'):
            r = requests.post(base + '/api/convert', files={'doc': open(os.path.join(ROOT, src), 'rb')}, data={'ink': 'black'}).json()
            assert r['ok'], r
            for _ in range(300):
                j = requests.get(base + '/api/job/' + r['job']).json()
                if j['state'] != 'running':
                    break
                time.sleep(2)
            assert j['state'] == 'done', j
            d = requests.get(base + '/file/outputs/' + j['out'])
            assert d.status_code == 200 and d.content[:4] == b'%PDF', 'download failed'
            print(src, 'OK', len(d.content), 'bytes')
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
    main(sys.argv[1])

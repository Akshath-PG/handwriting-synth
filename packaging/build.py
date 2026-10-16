"""Build the double-clickable app with PyInstaller:   python packaging/build.py
Output: dist/HandwritingSynth/  (Windows: HandwritingSynth.exe, macOS/Linux: HandwritingSynth)
PyInstaller can only build for the operating system it runs on; the GitHub Actions workflow builds all three."""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sep = os.pathsep
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'HandwritingSynth',
        '--paths', os.path.join(ROOT, 'src'),
        '--add-data', os.path.join(ROOT, 'src', 'app_page.html') + sep + '.',
        '--add-data', os.path.join(ROOT, 'examples', 'sample_library.pkl') + sep + 'examples',
        '--add-data', os.path.join(ROOT, 'assets', 'fonts') + sep + os.path.join('assets', 'fonts'),
        '--collect-all', 'cv2', '--collect-all', 'pdfminer', '--collect-all', 'pdfplumber', '--collect-data', 'docx', '--collect-data', 'reportlab',
        '--hidden-import', 'handwrite', '--hidden-import', 'make_template', '--hidden-import', 'calibrate',
        '--hidden-import', 'loaders', '--hidden-import', 'blocks', '--hidden-import', 'hw_render', '--hidden-import', 'doclib',
        *sum([['--exclude-module', m] for m in ('matplotlib', 'pandas', 'scipy', 'tkinter', 'IPython', 'pytest', 'sympy', 'numba')], []),
        '--distpath', os.path.join(ROOT, 'dist'), '--workpath', os.path.join(ROOT, 'build'), '--specpath', os.path.join(ROOT, 'build')]
# (macOS: a plain folder like Linux. A .app bundle moves OpenCV's files apart and breaks its loader.)
args.append(os.path.join(ROOT, 'src', 'app.py'))
print(' '.join(args))
sys.exit(subprocess.call(args))

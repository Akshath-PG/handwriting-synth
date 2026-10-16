"""Central paths.

* ROOT  - where the code, examples/ and assets/ live (the repo folder, or the unpacked app bundle)
* D     - where YOUR generated data goes (glyph library, output pages): $HW_HOME, else <repo>/work,
          else ~/HandwritingSynth when running as a packaged app
"""
import os, sys

FROZEN = getattr(sys, 'frozen', False)
ROOT = getattr(sys, '_MEIPASS', None) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_home = os.environ.get('HW_HOME') or (os.path.join(os.path.expanduser('~'), 'HandwritingSynth') if FROZEN else os.path.join(ROOT, 'work'))
os.makedirs(_home, exist_ok=True)
D = _home + os.sep                                  # generated data (glyph library, pages)
U = os.path.join(ROOT, 'samples') + os.sep          # photos used by the legacy prototype
_own = os.path.join(D, 'lib.pkl')
_sample = os.path.join(ROOT, 'examples', 'sample_library.pkl')
# glyph library used by the renderer: $HW_LIB, else your own lib.pkl, else the bundled sample library
LIB = os.environ.get('HW_LIB') or (_own if os.path.exists(_own) else _sample)

"""Image read/write that also works for Windows user names with accents or spaces
(cv2.imread/imwrite fail on non-ASCII paths on Windows; numpy file I/O does not)."""
import cv2, numpy as np


def imread(path, flags=cv2.IMREAD_COLOR):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, flags) if data.size else None


def imwrite(path, img, params=None):
    ext = '.' + path.rsplit('.', 1)[-1].lower()
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok:
        raise IOError('cannot encode image for ' + path)
    buf.tofile(path)
    return True

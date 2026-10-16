import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src" if "legacy" not in __file__ else ".."))
import cv2, numpy as np, os, json

from config import D, U
files = {'p1': 'p1_upper_A-D', 'p2': 'p2_lower_upper', 'p3': 'p3_digits_punct', 'p4': 'p4_symbols', 'eq': 'eq_sample', 'code': 'code_sample'}

lower = list("abcdefghijklmnopqrstuvwxyz")
upper = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
digits = list("0123456789")
punct = list("!\"%&'()*+,-./:;<=>?@[\\]^_{|}~") + ["·", "×", "–", "−", "…"]
symbols = ["Â", "Ã", "Δ", "Σ", "φ", "σ", "λ", "∂", "←", "→", "⇒", "⇔", "∀", "∃", "∅",
           "∈", "√", "≅", "≈", "≤", "≥", "²", "ᵀ", "⁻"]
chars = lower + upper + digits + punct + symbols
pages = [chars[i:i + 30] for i in range(0, len(chars), 30)]
page_key = {'p1': 0, 'p2': 1, 'p3': 2, 'p4': 3}
roi = {'p1': (800, 320, 1420, 2250), 'p2': (150, 100, 880, 2450),
       'p3': (560, 0, 1440, 2400), 'p4': (150, 150, 1000, 2400)}


def ink_mask(im):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    bg = cv2.dilate(g, np.ones((31, 31), np.uint8))
    bg = cv2.GaussianBlur(bg, (0, 0), 15)
    ratio = g.astype(float) / np.maximum(bg, 1)
    return ratio


def comps_for(k):
    im = cv2.imread(U + files[k] + '.jpg')
    ratio = ink_mask(im)
    x0, y0, x1, y1 = roi[k]
    m = np.zeros(ratio.shape, np.uint8)
    m[y0:y1, x0:x1] = ((ratio[y0:y1, x0:x1] < 0.72) * 255).astype(np.uint8)
    grp = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    n, lab, st, cen = cv2.connectedComponentsWithStats(grp)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        sub = m[y:y + h, x:x + w] * (lab[y:y + h, x:x + w] == i)
        inkpx = int((sub > 0).sum())
        if inkpx < 60:
            continue
        ys, xs = np.where(sub > 0)
        out.append(dict(x=int(x + xs.min()), y=int(y + ys.min()), x2=int(x + xs.max()), y2=int(y + ys.max()), ink=inkpx,
                        id=int(i)))
    return im, ratio, m, lab, out


if __name__ == '__main__':
    summary = {}
    for k in ['p1', 'p2', 'p3', 'p4']:
        im, ratio, m, lab, cs = comps_for(k)
        print(k, len(cs), 'expected', len(pages[page_key[k]]))
        summary[k] = cs
        vis = cv2.cvtColor(255 - m, cv2.COLOR_GRAY2BGR)
        for c in cs:
            cv2.rectangle(vis, (c['x'], c['y']), (c['x2'], c['y2']), (0, 0, 255), 3)
        cv2.imwrite(D + f'chk_{k}.png', cv2.resize(vis, None, fx=0.4, fy=0.4))
    json.dump(summary, open(D + 'comps.json', 'w'))

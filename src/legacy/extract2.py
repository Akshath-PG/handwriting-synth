import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src" if "legacy" not in __file__ else ".."))
import cv2, numpy as np, json
from extract import *

OUTD = D + 'glyphs/'
import os
os.makedirs(OUTD, exist_ok=True)


def runs_from_profile(prof, gap):
    on = prof > 0
    runs = []
    i = 0
    n = len(prof)
    while i < n:
        if on[i]:
            j = i
            last = i
            while j < n and (on[j] or j - last <= gap):
                if on[j]:
                    last = j
                j += 1
            runs.append([i, last])
            i = last + 1
        else:
            i += 1
    return runs


def fit_runs(runs, prof, want):
    runs = [r[:] for r in runs]
    while len(runs) > want:
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        i = int(np.argmin(gaps))
        runs[i] = [runs[i][0], runs[i + 1][1]]
        del runs[i + 1]
    while len(runs) < want:
        hs = [r[1] - r[0] for r in runs]
        i = int(np.argmax(hs))
        a, b = runs[i]
        lo = a + (b - a) // 4
        hi = b - (b - a) // 4
        cut = lo + int(np.argmin(prof[lo:hi]))
        runs[i:i + 1] = [[a, cut - 1], [cut, b]]
    return runs


def extract_page(k, exclude=None):
    im, ratio, m, lab, cs = comps_for(k)
    x0, y0, x1, y1 = roi[k]
    # drop obvious border/noise components (very wide or very tall flat strips)
    mm = m.copy()
    for c in cs:
        w = c['x2'] - c['x']
        h = c['y2'] - c['y']
        if w > 500 or h > 700 or (c['ink'] > 20000):
            mm[c['y']:c['y2'] + 1, c['x']:c['x2'] + 1] = 0
    n2, l2, st2, _ = cv2.connectedComponentsWithStats((mm > 0).astype(np.uint8), connectivity=8)
    for i in range(1, n2):
        if st2[i][4] < 45:
            mm[l2 == i] = 0
    xp = (mm > 0).sum(axis=0)
    xr = runs_from_profile(xp, 50)
    xr.sort(key=lambda r: -xp[r[0]:r[1] + 1].sum())
    xr = sorted(xr[:2])
    glyphs = []
    for ci, (a, b) in enumerate(xr):
        a2, b2 = max(a - 20, 0), b + 20
        col = mm[:, a2:b2]
        yp = (col > 0).sum(axis=1)
        yr = runs_from_profile(yp, 12)
        yr = [r for r in yr if yp[r[0]:r[1] + 1].sum() > 45]
        yr = fit_runs(yr, yp, 15)
        rows = [[r] for r in yr]
        for ri, rs in enumerate(rows):
            if not rs:
                continue
            ya = min(r[0] for r in rs)
            yb = max(r[1] for r in rs)
            sub = mm[ya:yb + 1, a2:b2]
            ys, xs = np.where(sub > 0)
            glyphs.append(dict(col=ci, row=ri, x0=int(a2 + xs.min()), x1=int(a2 + xs.max()), y0=int(ya + ys.min()),
                               y1=int(ya + ys.max()), band=(int(ya), int(yb))))
    return im, ratio, mm, glyphs


if __name__ == '__main__':
    allg = {}
    for k in ['p1', 'p2', 'p3', 'p4']:
        im, ratio, mm, gl = extract_page(k)
        labs = pages[page_key[k]]
        print(k, len(gl))
        # order: row-major, left col then right col
        gl.sort(key=lambda g: (g['row'], g['col']))
        sheet = []
        for g, ch in zip(gl, labs):
            g['ch'] = ch
            crop = mm[g['band'][0]:g['band'][1] + 1, g['x0'] - 5:g['x1'] + 6]
            # alpha from darkness
            alpha = (255 - np.clip(ratio[g['band'][0]:g['band'][1] + 1, g['x0'] - 5:g['x1'] + 6] * 255, 0, 255)).astype(np.uint8)
            sheet.append((ch, crop))
        allg[k] = gl
        # contact sheet
        cell = 140
        rows = []
        cols = 6
        canvas = np.full((cell * 5 + 10, cell * cols), 255, np.uint8)
        for i, (ch, crop) in enumerate(sheet):
            r, c = divmod(i, cols)
            h, w = crop.shape
            s = min((cell - 30) / max(h, 1), (cell - 10) / max(w, 1), 1.0)
            t = cv2.resize(255 - crop, (max(int(w * s), 1), max(int(h * s), 1)), interpolation=cv2.INTER_AREA)
            y = r * cell + 20
            x = c * cell + 5
            canvas[y:y + t.shape[0], x:x + t.shape[1]] = np.minimum(canvas[y:y + t.shape[0], x:x + t.shape[1]], t)
            cv2.putText(canvas, str(i) + ':' + ch.encode('ascii', 'replace').decode(), (x, r * cell + 14), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, 120, 1)
        cv2.imwrite(D + f'sheet_{k}.png', canvas)
    json.dump(allg, open(D + 'glyphs.json', 'w'))

import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src" if "legacy" not in __file__ else ".."))
import cv2, numpy as np, pickle, json
from extract import *
from extract2 import extract_page

lib = {}   # ch -> dict(alpha=uint8 array, (h,w), page)
pagescale = {}
raw = {}

for k in ['p1', 'p2', 'p3', 'p4']:
    im, ratio, mm, gl = extract_page(k)
    labs = pages[page_key[k]]
    gl.sort(key=lambda g: (g['row'], g['col']))
    for g, ch in zip(gl, labs):
        ya, yb = g['band']
        xa, xb = g['x0'] - 6, g['x1'] + 7
        sub_m = (mm[ya:yb + 1, xa:xb] > 0).astype(np.uint8)
        soft = np.clip((0.86 - ratio[ya:yb + 1, xa:xb]) / 0.42, 0, 1)
        # connected components on the mask, with a bridging dilation for grouping
        grp = cv2.dilate(sub_m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35)))
        n, lab, st, _ = cv2.connectedComponentsWithStats(grp)
        keep = np.zeros_like(sub_m)
        # per group: density test to remove scribble blobs
        infos = []
        for i in range(1, n):
            comp = (lab == i) & (sub_m > 0)
            area = int(comp.sum())
            if area == 0:
                continue
            ys, xs = np.where(comp)
            bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
            dens = area / float(bw * bh)
            infos.append((i, area, bw, bh, dens, xs.min(), ys.min()))
        # scribble: very dense compact blob
        good = []
        for inf in infos:
            i, area, bw, bh, dens, x0_, y0_ = inf
            if area > 2500 and dens > 0.42 and ch not in '8':
                continue
            if ch in 'wxyXφ' and area > 900 and dens > 0.30:
                continue
            good.append(inf)
        if not good:
            good = infos
        # remove tiny far-away leftovers unless near the biggest
        big = max(good, key=lambda t: t[1])
        sel = []
        for inf in good:
            i = inf[0]
            if inf is big or inf[1] > 0.12 * big[1]:
                sel.append(i)
            else:
                # small mark (dot/accent): keep if close to big
                sel.append(i)
        mask = np.isin(lab, sel) & (sub_m > 0)
        if ch not in "ij!:;?\"'.,·…%=&":
            n3, l3, st3, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
            if n3 > 2:
                amax = st3[1:, 4].max()
                for q in range(1, n3):
                    if st3[q][4] < 0.08 * amax:
                        mask[l3 == q] = False
        # but special handling for scribbled pages: if scribble removed, glyph may be left
        ys, xs = np.where(mask)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        # include soft halo
        pad = 4
        y0p, y1p = max(y0 - pad, 0), min(y1 + pad, mask.shape[0] - 1)
        x0p, x1p = max(x0 - pad, 0), min(x1 + pad, mask.shape[1] - 1)
        halo = cv2.dilate(mask.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        alpha = (soft * halo)[y0p:y1p + 1, x0p:x1p + 1]
        alpha = (alpha * 255).astype(np.uint8)
        lib[ch] = dict(alpha=alpha, page=k, h=int(y1 - y0 + 1), w=int(x1 - x0 + 1), pad=pad)
        raw[ch] = (k, int(y1 - y0 + 1))

# normalise scale between pages using cap heights / digit heights
def med(chs, k):
    return float(np.median([lib[c]['h'] for c in chs if lib[c]['page'] == k]))


caps_p2 = upper[4:]
cap_p2 = med(caps_p2, 'p2')
cap_p1 = float(np.median([lib[c]['h'] for c in 'ABCD']))
dig_p2 = float(np.median([lib[c]['h'] for c in '01234567']))
dig_p3 = float(np.median([lib[c]['h'] for c in '89']))
sym_p4 = float(np.median([lib[c]['h'] for c in 'ΔΣ∀∃∅']))
scale = {'p2': 1.0, 'p1': cap_p2 / cap_p1, 'p3': dig_p2 / dig_p3, 'p4': cap_p2 / sym_p4}
print('cap_p2', cap_p2, 'cap_p1', cap_p1, 'dig_p2', dig_p2, 'dig_p3', dig_p3, 'sym_p4', sym_p4, scale)
for ch, g in lib.items():
    s = scale[g['page']]
    a = g['alpha']
    if abs(s - 1) > 1e-3:
        a = cv2.resize(a, (max(int(a.shape[1] * s), 1), max(int(a.shape[0] * s), 1)), interpolation=cv2.INTER_AREA)
    g['alpha'] = a
    g['h'] = g['h'] * s
    g['w'] = g['w'] * s
    g['pad'] = g['pad'] * s
pickle.dump(dict(lib=lib, cap=cap_p2), open(D + 'lib.pkl', 'wb'))

# contact sheet of the final library
cell = 120
cols = 10
chars_all = list(lib.keys())
rows = (len(chars_all) + cols - 1) // cols
canvas = np.full((rows * cell, cols * cell), 255, np.uint8)
for i, ch in enumerate(chars_all):
    r, c = divmod(i, cols)
    a = lib[ch]['alpha']
    s = min((cell - 16) / a.shape[0], (cell - 10) / a.shape[1], 0.5)
    t = cv2.resize(255 - a, (max(int(a.shape[1] * s), 1), max(int(a.shape[0] * s), 1)), interpolation=cv2.INTER_AREA)
    canvas[r * cell + 14:r * cell + 14 + t.shape[0], c * cell + 4:c * cell + 4 + t.shape[1]] = t
    cv2.putText(canvas, ch.encode('ascii', 'replace').decode() + str(i), (c * cell + 2, r * cell + 11), cv2.FONT_HERSHEY_SIMPLEX, 0.4, 100, 1)
cv2.imwrite(D + 'lib_sheet.png', canvas)
print(len(lib))

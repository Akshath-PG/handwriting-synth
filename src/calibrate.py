"""Photos of the filled-in template  ->  glyph library (work/lib.pkl).

Steps per photo:
  1. find the 4 black squares, straighten the page to 2480x3508 (300 dpi)
  2. estimate local paper brightness; ink = pixels clearly darker than their surroundings
  3. cut each character out of its box (box positions come from layout.py)
  4. store a soft alpha mask + how far the ink sits below the baseline
"""
import math, os, pickle, sys
import cv2, numpy as np
import charset, layout as L
from imgio import imread, imwrite

INK_RATIO = 0.72          # pixel darker than 72% of local paper brightness = ink
SOFT_LO, SOFT_SPAN = 0.86, 0.42


class CalibrationError(Exception):
    pass


# ------------------------------------------------------------------ straightening
def find_markers(img):
    """Return 4 marker centres in photo pixels ordered TL, TR, BR, BL."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sc = 1600.0 / max(g.shape)
    small = cv2.resize(g, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (5, 5), 0)
    k = int(max(small.shape) * 0.08) | 1                       # larger than a marker
    bg = cv2.GaussianBlur(cv2.dilate(small, np.ones((k, k), np.uint8)), (0, 0), k / 4)
    ratio = small.astype(np.float32) / np.maximum(bg, 1)
    dark = (ratio < 0.55).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(dark)
    side = max(small.shape)
    cands = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (0.012 * side < w < 0.12 * side and 0.012 * side < h < 0.12 * side):
            continue
        if not (0.65 < w / float(h) < 1.55):
            continue
        if a / float(w * h) < 0.78:
            continue
        cands.append((a, cen[i][0] / sc, cen[i][1] / sc))
    cands.sort(reverse=True)
    if len(cands) < 4:
        raise CalibrationError('found %d of the 4 black corner squares - make sure all four are visible, the page is '
                               'in focus and lit evenly' % len(cands))
    big = cands[0]
    rest = [c for c in cands[1:] if 0.45 < c[0] / np.median([x[0] for x in cands[1:4]]) < 2.2][:3]
    if len(rest) < 3 or big[0] < 1.6 * np.median([x[0] for x in rest]):
        raise CalibrationError('could not tell the large top-left square from the other three; is the page cut off?')
    pts = np.array([[c[1], c[2]] for c in [big] + rest], np.float32)
    ctr = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - ctr[1], pts[:, 0] - ctr[0])
    order = np.argsort((ang - ang[0]) % (2 * math.pi))
    return pts[order]


def rectify(img):
    src = find_markers(img)
    dst = np.array(L.marker_centres_px(), np.float32)
    H = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, H, (L.PAGE_W, L.PAGE_H), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def ink_ratio(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bg = cv2.dilate(g, np.ones((31, 31), np.uint8))
    bg = cv2.GaussianBlur(bg, (0, 0), 15)
    return g.astype(np.float32) / np.maximum(bg, 1)


# ------------------------------------------------------------------ glyph cutting
def cut_glyph(ratio, idx, ch, thr=INK_RATIO):
    x0, y0, x1, y1 = L.write_rect_px(idx)
    r = ratio[y0:y1, x0:x1]
    mask = (r < thr).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for i in range(1, n):
        if st[i][4] < 25:
            mask[lab == i] = 0
    if mask.sum() == 0:
        return None, []
    warns = []
    edge = int(mask[0, :].sum() + mask[-1, :].sum() + mask[:, 0].sum() + mask[:, -1].sum())
    if edge > 30:
        warns.append('touches the edge of its box')
    ys, xs = np.where(mask > 0)
    ya, yb, xa, xb = ys.min(), ys.max(), xs.min(), xs.max()
    pad = 4
    ya2, yb2 = max(ya - pad, 0), min(yb + pad, mask.shape[0] - 1)
    xa2, xb2 = max(xa - pad, 0), min(xb + pad, mask.shape[1] - 1)
    halo = cv2.dilate(mask, np.ones((7, 7), np.uint8)) > 0
    soft = np.clip((SOFT_LO - r) / SOFT_SPAN, 0, 1) * halo
    alpha = (soft[ya2:yb2 + 1, xa2:xb2 + 1] * 255).astype(np.uint8)
    base_in_crop = (L.baseline_px(idx) - y0) - ya2
    inkb = np.where(alpha > 70)[0]
    below = float(inkb.max() - base_in_crop)            # >0: ink hangs below the baseline
    return dict(alpha=alpha, h=int(yb - ya + 1), w=int(xb - xa + 1), pad=pad, below=below), warns


def calibrate(photos, out_path, debug_dir=None, thr=INK_RATIO, log=print):
    pages = charset.pages(L.PER_PAGE)
    if len(photos) != len(pages):
        raise CalibrationError('the template has %d pages, so %d photos are needed (you gave %d)'
                               % (len(pages), len(pages), len(photos)))
    lib, missing, warnings = {}, [], []
    for pi, (path, chars) in enumerate(zip(photos, pages)):
        img = imread(path)
        if img is None:
            raise CalibrationError('cannot read image %s' % path)
        log('page %d/%d: %s' % (pi + 1, len(pages), os.path.basename(path)))
        try:
            warped = rectify(img)
        except CalibrationError as e:
            raise CalibrationError('%s: %s' % (os.path.basename(path), e))
        ratio = ink_ratio(warped)
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            vis = warped.copy()
            for i, ch in enumerate(chars):
                a, b, c, d = L.write_rect_px(i)
                cv2.rectangle(vis, (a, b), (c, d), (0, 160, 0), 3)
                cv2.line(vis, (a, L.baseline_px(i)), (c, L.baseline_px(i)), (0, 0, 255), 2)
            imwrite(os.path.join(debug_dir, 'rectified_%d.jpg' % (pi + 1)), cv2.resize(vis, None, fx=0.5, fy=0.5))
        for i, ch in enumerate(chars):
            g, w = cut_glyph(ratio, i, ch, thr)
            if g is None:
                missing.append(ch)
                continue
            lib[ch] = g
            warnings += ['%r %s' % (ch, m) for m in w]
    need = [c for c in charset.REQUIRED if c not in lib]
    if need:
        raise CalibrationError('these essential characters are empty or unreadable: %s' % ' '.join(need))
    caps = [lib[c]['h'] for c in charset.UPPER if c not in 'JQ']
    cap = float(np.median(caps))
    pickle.dump(dict(lib=lib, cap=cap, version=2), open(out_path, 'wb'))
    log('glyphs: %d of %d, capital height %.0f px' % (len(lib), len(charset.ALL), cap))
    if missing:
        log('empty boxes (these characters will be skipped when writing): ' + ' '.join(missing))
    for w in warnings:
        log('warning: ' + w)
    if debug_dir:
        contact_sheet(lib, os.path.join(debug_dir, 'glyph_sheet.png'))
    return lib, missing, warnings


def contact_sheet(lib, path, cols=14, cell=110):
    chars = list(lib.keys())
    rows = (len(chars) + cols - 1) // cols
    sheet = np.full((rows * cell, cols * cell), 255, np.uint8)
    for i, ch in enumerate(chars):
        r, c = divmod(i, cols)
        a = lib[ch]['alpha']
        s = min((cell - 12) / a.shape[0], (cell - 8) / a.shape[1], 1.0)
        t = cv2.resize(255 - a, (max(int(a.shape[1] * s), 1), max(int(a.shape[0] * s), 1)), interpolation=cv2.INTER_AREA)
        sheet[r * cell + 10:r * cell + 10 + t.shape[0], c * cell + 4:c * cell + 4 + t.shape[1]] = t
    imwrite(path, sheet)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('photos', nargs='+')
    ap.add_argument('--out', default='lib.pkl')
    ap.add_argument('--debug')
    a = ap.parse_args()
    calibrate(a.photos, a.out, a.debug)

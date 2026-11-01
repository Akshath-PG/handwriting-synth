"""Photos of the filled-in template  ->  glyph library (work/lib.pkl).

Steps per photo:
  1. find the 4 black squares, straighten the page to 2480x3508 (300 dpi)
  2. read the page code (small squares at the bottom) so photos may come in any order
  3. estimate local paper brightness; ink = pixels clearly darker than their surroundings
  4. cut each character / word / drawing out of its box (box positions come from the template plan, plan.py)
  5. store a soft alpha mask + how far the ink sits below the baseline
"""
import math, os, pickle, sys
import cv2, numpy as np
import charset, layout as L, plan as PL, styles, style_model
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


# ------------------------------------------------------------------ page code
def read_code(ratio):
    """The page code squares of a straightened page -> (page index, template id) or None (old template / unreadable)."""
    bits = []
    for x, y, s in PL.code_squares_mm():
        h = max(int(s * L.MM * 0.3), 2)
        cx, cy = L.px(x), L.px(y)
        bits.append(1 if float(np.median(ratio[cy - h:cy + h, cx - h:cx + h])) < 0.55 else 0)
    return PL.decode_bits(bits)


# ------------------------------------------------------------------ glyph cutting
def cut_cell(ratio, cell, thr=INK_RATIO):
    """Cut the ink of one char / word box -> (glyph dict or None, warnings)."""
    x0, y0, x1, y1 = PL.write_rect_px(cell)
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
    base_in_crop = (PL.baseline_px(cell) - y0) - ya2
    inkb = np.where(alpha > 70)[0]
    if len(inkb) == 0:
        return None, []
    below = float(inkb.max() - base_in_crop)            # >0: ink hangs below the baseline
    return dict(alpha=alpha, h=int(yb - ya + 1), w=int(xb - xa + 1), pad=pad, below=below, base=float(base_in_crop)), warns


def cut_glyph(ratio, idx, ch, thr=INK_RATIO):
    """Universal-template box number idx (kept for older callers)."""
    x, y, w, h = L.cell_mm(idx)
    return cut_cell(ratio, dict(r=[x, y, w, h], lh=L.LABEL_H, b=L.BASE), thr)


def cut_figure(ratio, cell, thr=INK_RATIO, min_ink=400):
    """Your drawing inside a figure box (the grey trace guide is lighter than ink and is ignored)."""
    x0, y0, x1, y1 = PL.write_rect_px(cell, inset=2.0)
    r = ratio[y0:y1, x0:x1]
    mask = (r < thr).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for i in range(1, n):
        if st[i][4] < 30:
            mask[lab == i] = 0
    if int(mask.sum()) < min_ink:
        return None
    halo = cv2.dilate(mask, np.ones((5, 5), np.uint8)) > 0
    alpha = (np.clip((SOFT_LO - r) / SOFT_SPAN, 0, 1) * halo * 255).astype(np.uint8)
    return dict(alpha=alpha, w_mm=cell['r'][2], h_mm=cell['r'][3] - cell['lh'])


def _order_photos(photos, ratios, plan, log):
    """Use the page codes to put the photos in page order. Falls back to the given order for old templates."""
    npg = len(plan['pages'])
    codes = [read_code(r) for r in ratios]
    if not any(codes):
        if len(photos) != npg:
            raise CalibrationError('the template has %d pages, so %d photos are needed (you gave %d)' % (npg, npg, len(photos)))
        return list(range(len(photos)))
    order = [None] * npg
    for i, code in enumerate(codes):
        name = os.path.basename(photos[i])
        if code is None:
            raise CalibrationError('%s: cannot read the small squares at the bottom of the page; retake the photo with the '
                                   'whole page in focus' % name)
        page, tid = code
        if tid != plan['id']:
            raise CalibrationError('%s is a photo of a different template (code %d, expected %d). Use the template you '
                                   'downloaded for this document.' % (name, tid, plan['id']))
        if page >= npg:
            raise CalibrationError('%s: page %d does not exist in this %d-page template' % (name, page + 1, npg))
        if order[page] is not None:
            raise CalibrationError('page %d was given twice (%s and %s)' % (page + 1, os.path.basename(photos[order[page]]), name))
        order[page] = i
    miss = [str(p + 1) for p, o in enumerate(order) if o is None]
    if miss:
        raise CalibrationError('photo of page %s is missing (the template has %d pages)' % (', '.join(miss), npg))
    if order != list(range(npg)):
        log('photos were put in page order using the page codes')
    return order


def choose_plan(photos, plan):
    """If the photos carry the universal template's page code but another template was given (or the other way
    round), use the template the photos actually show. Returns (plan, None)."""
    img = imread(photos[0]) if photos else None
    if img is None:
        return plan, None
    try:
        code = read_code(ink_ratio(rectify(img)))
    except CalibrationError:
        return plan, None
    if code and code[1] == 0 and plan['id'] != 0:
        return PL.universal_plan(), None
    return plan, None


def calibrate(photos, out_path, debug_dir=None, thr=INK_RATIO, log=print, plan=None, merge=None):
    """photos -> glyph library. plan: template plan (default: the universal template). merge: older library of the
    same style whose glyphs are kept where the new photos have none."""
    plan = plan or PL.universal_plan()
    style = plan.get('style', 'print')
    npg = len(plan['pages'])
    if not photos:
        raise CalibrationError('no photos given')
    if len(photos) > npg + 2:
        raise CalibrationError('the template has %d pages but %d photos were given' % (npg, len(photos)))
    warped_all, ratios = [], []
    for path in photos:
        img = imread(path)
        if img is None:
            raise CalibrationError('cannot read image %s' % path)
        try:
            warped = rectify(img)
        except CalibrationError as e:
            raise CalibrationError('%s: %s' % (os.path.basename(path), e))
        warped_all.append(warped)
        ratios.append(ink_ratio(warped))
    order = _order_photos(photos, ratios, plan, log)
    lib, alts, figs, missing, warnings = {}, {}, {}, [], []
    lines, formulas = [], {}
    nchars = 0
    for pi, cells in enumerate(plan['pages']):
        k = order[pi]
        warped, ratio = warped_all[k], ratios[k]
        log('page %d/%d: %s' % (pi + 1, npg, os.path.basename(photos[k])))
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            vis = warped.copy()
            for cell in cells:
                if cell['k'] in ('char', 'word', 'figure', 'sentence', 'formula'):
                    a, b, c, d = PL.write_rect_px(cell)
                    cv2.rectangle(vis, (a, b), (c, d), (0, 160, 0), 3)
                    if cell['k'] not in ('figure',):
                        cv2.line(vis, (a, PL.baseline_px(cell)), (c, PL.baseline_px(cell)), (0, 0, 255), 2)
            imwrite(os.path.join(debug_dir, 'rectified_%d.jpg' % (pi + 1)), cv2.resize(vis, None, fx=0.5, fy=0.5))
        for cell in cells:
            t = cell['k']
            if t == 'figure':
                f = cut_figure(ratio, cell, thr)
                if f is not None:
                    figs[cell['key']] = f
                continue
            if t in ('sentence', 'formula'):
                g, _ = cut_cell(ratio, cell, thr)
                if g is not None and t == 'sentence':
                    lines.append((cell['t'], g['alpha'], g['base']))
                elif g is not None:
                    formulas[cell['key']] = g
                continue
            if t not in ('char', 'word'):
                continue
            nchars += t == 'char' and not cell.get('alt')
            g, w = cut_cell(ratio, cell, thr)
            if g is None:
                if not cell.get('alt'):
                    missing.append(cell['t'])
                continue
            if t == 'word':
                g['word'] = True
            if cell.get('alt'):
                alts.setdefault(cell['t'], []).append(g)
            else:
                lib[cell['t']] = g
            warnings += ['%r %s' % (cell['t'], m) for m in w]
    for key, gs in alts.items():
        if key in lib:
            lib[key]['alts'] = gs
        else:
            lib[key] = gs[0]
            if gs[1:]:
                lib[key]['alts'] = gs[1:]
            if key in missing:
                missing.remove(key)
    planned = {c['t'] for _, c in PL.cells(plan, ('char',))}
    required = (charset.UPPER + charset.DIGITS) if styles.get(style)['caps'] else charset.REQUIRED
    need = [c for c in required if c in planned and c not in lib]
    if need:
        raise CalibrationError('these essential characters are empty or unreadable: %s' % ' '.join(need))
    caps = [lib[c]['h'] for c in charset.UPPER if c not in 'JQ' and c in lib]
    if not caps:
        raise CalibrationError('no capital letters were found; they are needed to measure your writing size')
    cap = float(np.median(caps))
    # how you write running text: measured from the sample sentences (style_model.py)
    model, nat_words, report = style_model.learn(lines, lib, style)
    nnat = 0
    for key, gs in nat_words.items():
        if key in lib:
            lib[key]['alts'] = list(lib[key].get('alts', [])) + gs
        else:
            lib[key] = gs[0]
            if gs[1:]:
                lib[key]['alts'] = gs[1:]
        nnat += len(gs)
    old_figs, old_forms, old_model = {}, {}, None
    if merge and os.path.exists(merge):
        try:
            old = pickle.load(open(merge, 'rb'))
        except Exception:
            old = None
        if old and old.get('style', 'print') == style:
            k = cap / float(old['cap'])
            kept = 0
            for key, g in old['lib'].items():
                if key not in lib and 0.75 < k < 1.33:      # same person, similar size: keep what this template lacked
                    lib[key] = g
                    kept += 1
            old_figs = old.get('figures', {})
            old_forms = old.get('formulas', {})
            old_model = old.get('model')
            if kept:
                log('kept %d glyphs/words from your earlier %s library' % (kept, style))
    old_figs.update(figs)
    old_forms.update(formulas)
    if not lines and old_model:                           # no sentences this time: keep what was learned before
        model = old_model
    nword = sum(1 for g in lib.values() if g.get('word'))
    pickle.dump(dict(lib=lib, cap=cap, version=3, style=style, figures=old_figs, formulas=old_forms, model=model,
                     template=plan['id']), open(out_path, 'wb'))
    log('glyphs: %d of %d, capital height %.0f px' % (sum(1 for key in lib if len(key) == 1 and key in planned), nchars, cap))
    if nword or figs or alts or formulas:
        log('also learned: %d words / letter groups, %d second samples, %d drawings, %d equations, %d words from your '
            'sentences' % (nword, sum(len(v) for v in alts.values()), len(figs), len(formulas), nnat))
    if report:
        log('your writing: ' + '; '.join(report))
    elif lines:
        log('your writing: the sentences could not be measured (write them on the line, with clear spaces between words)')
    if missing:
        log('empty boxes (these characters will be skipped when writing): ' + ' '.join(missing))
    for w in warnings:
        log('warning: ' + w)
    if debug_dir:
        contact_sheet(lib, os.path.join(debug_dir, 'glyph_sheet.png'))
    return lib, missing, warnings


def contact_sheet(lib, path, width=1540, cell=110):
    """One picture with every glyph and word that was learned (second samples shown next to the first)."""
    items = []
    for key, g in lib.items():
        items += [g] + list(g.get('alts', []))
    x = y = 0
    places = []
    for g in items:
        a = g['alpha']
        s = min((cell - 12) / a.shape[0], 1.0)
        w = max(int(a.shape[1] * s), 1)
        w = min(w, width - 8)
        if x + w + 8 > width:
            x, y = 0, y + cell
        places.append((x, y, s, w))
        x += max(w + 8, cell // 2)
    sheet = np.full((y + cell, width), 255, np.uint8)
    for g, (x, y, s, w) in zip(items, places):
        a = g['alpha']
        t = cv2.resize(255 - a, (w, max(int(a.shape[0] * s), 1)), interpolation=cv2.INTER_AREA)
        sheet[y + 10:y + 10 + t.shape[0], x + 4:x + 4 + t.shape[1]] = t
    imwrite(path, sheet)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('photos', nargs='+')
    ap.add_argument('--out', default='lib.pkl')
    ap.add_argument('--debug')
    ap.add_argument('--template', help='template description (.json) written next to a document template')
    a = ap.parse_args()
    calibrate(a.photos, a.out, a.debug, plan=PL.load(a.template))

"""Create fake phone photos of a filled-in template, so the calibration can be tested without a human.

Uses an existing glyph library as the 'handwriting': one character per character box, whole words (joined up) in
word boxes, and the grey guide in figure boxes is 'traced' with a pen. Then each page is made to look like a phone
photo (rotation, perspective, uneven lighting, blur, noise, JPEG).

usage: python3 tests/simulate_photos.py TEMPLATE.pdf SOURCE_LIB.pkl OUTDIR [seed] [--shuffle]
       the template's .json (written next to a document template) is used when present
"""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import numpy as np, cv2
import layout as L, plan as PL


def main(tpl, lib, outdir, seed=1, shuffle=False):
    os.environ['HW_LIB'] = lib
    man = PL.manifest_path(tpl)
    plan = PL.load(man) if os.path.exists(man) else PL.universal_plan()
    os.environ['HW_STYLE'] = 'cursive' if plan.get('style') in ('cursive', 'semi') else plan.get('style', 'print')
    import hw_render as H
    os.makedirs(outdir, exist_ok=True)
    import pypdfium2 as pdfium
    rasters = [np.array(p.render(scale=300 / 72.0).to_pil().convert('RGB')) for p in pdfium.PdfDocument(tpl)]
    rng = random.Random(seed)
    s = 94.0 / H.CAP                                          # capital ~ 8 mm
    written = 0
    names = list(range(1, len(plan['pages']) + 1))
    if shuffle:
        rng.shuffle(names)
    for pi, cells in enumerate(plan['pages']):
        img = rasters[pi].astype(np.float32)
        img = cv2.resize(img, (L.PAGE_W, L.PAGE_H))
        page = H.Page(seed=pi)
        page.img = img
        pen = H.Pen(page, cap=94, jitter=1.0, seed=pi + 5)
        for cell in cells:
            x0, y0, x1, y1 = PL.write_rect_px(cell)
            if cell['k'] == 'char':
                ch = cell['t']
                if ch not in H.LIB:
                    continue
                w = H.META[ch]['w'] * s
                pen.draw_glyph(ch, x0 + (x1 - x0 - w) / 2 + rng.uniform(-25, 25), PL.baseline_px(cell) + rng.uniform(-6, 6), s)
                written += 1
            elif cell['k'] == 'word':
                w = pen.width(cell['t'], s * 0.9, raw=True)
                if w > x1 - x0 - 10:
                    continue
                pen.run(cell['t'], x0 + (x1 - x0 - w) / 2, PL.baseline_px(cell) + rng.uniform(-5, 5), s * 0.9, raw=True)
                written += 1
            elif cell['k'] == 'figure':                    # trace the grey guide: grey pixels become pen ink
                region = page.img[y0:y1, x0:x1]
                g = region.mean(axis=2)
                guide = ((g < 235) & (g > 150)).astype(np.uint8) * 255
                guide = cv2.dilate(guide, np.ones((2, 2), np.uint8))
                M = np.float32([[1, 0, rng.uniform(-3, 3)], [0, 1, rng.uniform(-3, 3)]])
                guide = cv2.warpAffine(guide, M, (guide.shape[1], guide.shape[0]))
                page.blit(guide, x0, y0, strength=0.9)
        out = np.clip(page.img, 0, 255).astype(np.uint8)
        # --- desk photo
        Wd, Hd = 3000, 4000
        desk = np.zeros((Hd, Wd, 3), np.uint8)
        desk[:] = (70, 85, 105)
        ang = rng.uniform(-4, 4)
        sc = 0.80
        M = cv2.getRotationMatrix2D((L.PAGE_W / 2, L.PAGE_H / 2), ang, sc)
        M[0, 2] += (Wd - L.PAGE_W) / 2 + rng.uniform(-60, 60)
        M[1, 2] += (Hd - L.PAGE_H) / 2 + rng.uniform(-60, 60)
        M3 = np.vstack([M, [0, 0, 1]])
        src = np.float32([[0, 0], [L.PAGE_W, 0], [L.PAGE_W, L.PAGE_H], [0, L.PAGE_H]])
        dst = cv2.perspectiveTransform(src.reshape(-1, 1, 2), M3).reshape(-1, 2)
        dst += np.float32([[rng.uniform(-50, 50), rng.uniform(-50, 50)] for _ in range(4)])
        P = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
        photo = cv2.warpPerspective(cv2.cvtColor(out, cv2.COLOR_RGB2BGR), P, (Wd, Hd), dst=desk, borderMode=cv2.BORDER_TRANSPARENT)
        yy, xx = np.mgrid[0:Hd, 0:Wd]
        light = 0.78 + 0.22 * (xx / Wd * rng.uniform(0.3, 1) + (1 - yy / Hd) * rng.uniform(0.3, 1)) / 1.5
        photo = (photo.astype(np.float32) * light[..., None])
        photo = cv2.GaussianBlur(photo, (0, 0), 1.1)
        photo += np.random.default_rng(pi).normal(0, 3.0, photo.shape)
        from imgio import imwrite
        imwrite(os.path.join(outdir, 'photo_%d.jpg' % names[pi]), np.clip(photo, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 82])
    print('simulated', len(plan['pages']), 'photos with', written, 'characters/words in', outdir)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--shuffle']
    main(args[0], args[1], args[2], int(args[3]) if len(args) > 3 else 1, shuffle='--shuffle' in sys.argv)

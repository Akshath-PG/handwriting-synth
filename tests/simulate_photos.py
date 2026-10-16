"""Create fake phone photos of a filled-in template, so the calibration can be tested without a human.

Uses an existing glyph library as the 'handwriting', writes one character per box on the rasterised template,
then makes it look like a phone photo (rotation, perspective, uneven lighting, blur, noise, JPEG).

usage: python3 tests/simulate_photos.py TEMPLATE.pdf SOURCE_LIB.pkl OUTDIR [seed]
"""
import os, sys, subprocess, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import numpy as np, cv2
import layout as L, charset


def main(tpl, lib, outdir, seed=1):
    os.environ['HW_LIB'] = lib
    import hw_render as H
    os.makedirs(outdir, exist_ok=True)
    import pypdfium2 as pdfium
    rasters = [np.array(p.render(scale=300 / 72.0).to_pil().convert('RGB')) for p in pdfium.PdfDocument(tpl)]
    rng = random.Random(seed)
    pages = charset.pages(L.PER_PAGE)
    s = 94.0 / H.CAP                                          # capital ~ 8 mm
    written = 0
    for pi, chars in enumerate(pages):
        img = rasters[pi].astype(np.float32)
        img = cv2.resize(img, (L.PAGE_W, L.PAGE_H))
        page = H.Page(seed=pi)
        page.img = img
        pen = H.Pen(page, cap=94, jitter=1.0, seed=pi + 5)
        for i, ch in enumerate(chars):
            if ch not in H.LIB:
                continue
            x0, y0, x1, y1 = L.write_rect_px(i)
            w = H.META[ch]['w'] * s
            pen.draw_glyph(ch, x0 + (x1 - x0 - w) / 2 + rng.uniform(-25, 25), L.baseline_px(i) + rng.uniform(-6, 6), s)
            written += 1
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
        imwrite(os.path.join(outdir, 'photo_%d.jpg' % (pi + 1)), np.clip(photo, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 82])
    print('simulated', len(pages), 'photos with', written, 'characters in', outdir)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1)

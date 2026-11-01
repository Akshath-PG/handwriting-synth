"""Pen-stroke geometry of a glyph image: its skeleton (centre line), where strokes start and end, which way the pen
was moving there and how wide the line is. Used to join letters the way a pen would, and to draw joins that look like
the same ink.

Everything is plain NumPy / OpenCV (Zhang-Suen thinning), so no extra packages are needed.
"""
import math
import cv2, numpy as np


def thin(mask):
    """Zhang-Suen thinning of a 0/1 uint8 mask -> 1-pixel-wide skeleton."""
    img = np.pad((mask > 0).astype(np.uint8), 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = img
            p2, p3, p4 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:]
            p5, p6, p7 = P[2:, 2:], P[2:, 1:-1], P[2:, :-2]
            p8, p9 = P[1:-1, :-2], P[:-2, :-2]
            c = P[1:-1, 1:-1]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(n.astype(np.int32) for n in nb)
            seq = nb + [p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            if step == 0:
                m = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                m = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            rm = (c == 1) & (B >= 2) & (B <= 6) & (A == 1) & m
            if rm.any():
                img[1:-1, 1:-1][rm] = 0
                changed = True
    return img[1:-1, 1:-1]


def neighbours(sk):
    k = np.ones((3, 3), np.float32)
    k[1, 1] = 0
    return cv2.filter2D(sk.astype(np.float32), -1, k, borderType=cv2.BORDER_CONSTANT).astype(np.int32) * sk


def _direction(sk, y, x, reach=9):
    """Unit vector pointing OUT of the stroke at end point (x, y): from the stroke behind it towards the end."""
    ys, xs = np.nonzero(sk[max(y - reach, 0):y + reach + 1, max(x - reach, 0):x + reach + 1])
    ys = ys + max(y - reach, 0)
    xs = xs + max(x - reach, 0)
    d = np.hypot(xs - x, ys - y)
    sel = (d > 1.5) & (d <= reach)
    if not sel.any():
        return None
    v = np.array([x - xs[sel].mean(), y - ys[sel].mean()])
    n = np.hypot(*v)
    return (v / n) if n > 1e-6 else None


def analyse(alpha, base_y, xh):
    """Stroke features of one glyph sample (alpha uint8, base_y = baseline row in the image, xh = x-height px).

    Returns dict(entry, entry_dir, exit, exit_dir, width, ink) in image pixels:
      entry     where the pen most plausibly arrives from the left (a stroke start, else the left of the body)
      exit      where it leaves to the right (a stroke end, else the right of the body)
      *_dir     unit vectors: exit_dir points the way the pen was moving when it left; entry_dir the way it moves
                when it arrives
      width     typical stroke width; ink: typical ink strength (0..1) of the strokes
    """
    mask = (alpha > 110).astype(np.uint8)
    if mask.sum() < 8:
        mask = (alpha > 40).astype(np.uint8)
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    sk = thin(mask)
    ys, xs = np.nonzero(sk)
    if len(xs) == 0:
        ys, xs = np.nonzero(mask)
        sk = mask
    width = float(np.median(dist[sk > 0]) * 2.0) if (sk > 0).any() else 3.0
    ink = float(np.percentile(alpha[mask > 0], 75) / 255.0) if mask.any() else 0.9
    nb = neighbours(sk)
    ey, ex = np.nonzero((nb == 1) & (sk > 0))                  # stroke end points
    l, r = xs.min(), xs.max()
    w = max(r - l, 1)
    zone_top, zone_bot = base_y - 1.15 * xh, base_y + 0.25 * xh

    def in_zone(y):
        return (y >= zone_top) & (y <= zone_bot)

    # exit: a stroke end in the right part of the letter, in the x-height zone; lower ends preferred (cursive
    # exits run along or up from the baseline); else the right-most body point near the baseline
    cand = [(x_ + 0.25 * (y_ - zone_top), x_, y_) for y_, x_ in zip(ey, ex) if in_zone(y_) and x_ >= l + 0.55 * w]
    if cand:
        _, x0, y0 = max(cand)
        d = _direction(sk, y0, x0)
    else:
        low = in_zone(ys) & (ys >= base_y - 0.55 * xh)
        sel = low if low.any() else in_zone(ys) if in_zone(ys).any() else np.ones_like(ys, bool)
        i = np.argmax(xs[sel])
        x0, y0 = xs[sel][i], ys[sel][i]
        d = None
    if d is None or d[0] < 0.15:                              # a pen leaving to the right moves right (and up)
        d = np.array([0.85, -0.5]) if d is None else np.array([max(d[0], 0.4), d[1]])
    exit_dir = d / np.hypot(*d)
    # entry: a stroke start on the left; else the top-left of the body (a, c, d, g, o, q are entered from above)
    cand = [(x_ - 0.15 * (y_ - zone_top), x_, y_) for y_, x_ in zip(ey, ex) if in_zone(y_) and x_ <= l + 0.45 * w]
    if cand:
        _, x1, y1 = min(cand)
        d = _direction(sk, y1, x1)
        d = -d if d is not None else None                     # the pen moves INTO the letter
    else:
        body = in_zone(ys) & (ys <= base_y - 0.45 * xh)
        sel = body if body.any() else in_zone(ys) if in_zone(ys).any() else np.ones_like(ys, bool)
        i = np.argmin(xs[sel] + 0.3 * (ys[sel] - zone_top))
        x1, y1 = xs[sel][i], ys[sel][i]
        d = None
    if d is None or d[0] < 0.1:
        d = np.array([0.8, -0.6]) if d is None else np.array([max(d[0], 0.3), d[1]])
    entry_dir = d / np.hypot(*d)
    return dict(entry=(float(x1), float(y1)), entry_dir=(float(entry_dir[0]), float(entry_dir[1])),
                exit=(float(x0), float(y0)), exit_dir=(float(exit_dir[0]), float(exit_dir[1])),
                width=max(width, 1.5), ink=min(max(ink, 0.5), 1.0))


def join_alpha(p0, d0, w0, p3, d3, w3, ink=0.9, seed=0, ss=4):
    """Alpha image of a pen stroke running from p0 (leaving in direction d0) to p3 (arriving in direction d3),
    width tapering from w0 to w3 and thinner in the middle, like a quick upstroke.
    Returns (alpha uint8, x offset, y offset) in page pixels."""
    rng = np.random.default_rng(seed)
    w0, w3 = 0.78 * w0, 0.78 * w3                 # stroke ends taper; a full-width cap would show as a blob
    p0 = np.array(p0, float) - np.array(d0) * 0.6 * w0      # start / finish hidden inside the letter's own ink
    p3 = np.array(p3, float) + np.array(d3) * 0.6 * w3
    L = float(np.hypot(*(p3 - p0)))
    if L < 1.0:
        return None
    k = 0.42 * L
    c1 = p0 + np.array(d0) * k
    c2 = p3 - np.array(d3) * k
    n = max(int(L * 1.5), 8)
    t = np.linspace(0, 1, n)[:, None]
    pts = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p3
    # a hand is never perfectly smooth: tiny low-frequency tremor across the stroke
    normal = np.array([-(p3 - p0)[1], (p3 - p0)[0]]) / L
    trem = np.interp(t[:, 0], np.linspace(0, 1, 4), rng.normal(0, 0.35, 4)) * np.sin(np.pi * t[:, 0])
    pts = pts + normal * trem[:, None]
    wid = (w0 * (1 - t[:, 0]) + w3 * t[:, 0]) * (1 - 0.32 * np.sin(np.pi * t[:, 0]))
    pad = int(max(w0, w3)) + 3
    x0, y0 = int(math.floor(pts[:, 0].min())) - pad, int(math.floor(pts[:, 1].min())) - pad
    x1, y1 = int(math.ceil(pts[:, 0].max())) + pad, int(math.ceil(pts[:, 1].max())) + pad
    W, H = x1 - x0 + 1, y1 - y0 + 1
    if W > 800 or H > 800:
        return None
    big = np.zeros((H * ss, W * ss), np.float32)
    for (x, y), r in zip(pts, wid):
        cv2.circle(big, (int(round((x - x0) * ss)), int(round((y - y0) * ss))), max(int(round(r * ss / 2)), 1), 1.0, -1,
                   cv2.LINE_AA)
    a = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA)
    a = cv2.GaussianBlur(a, (0, 0), 0.75)                     # photographed ink is never razor sharp
    tex = cv2.GaussianBlur(rng.normal(1.0, 0.12, (H, W)).astype(np.float32), (0, 0), 1.2)
    a = np.clip(a * ink * np.clip(tex, 0.8, 1.1), 0, 1)
    return (a * 255).astype(np.uint8), x0, y0

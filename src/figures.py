"""Pictures, diagrams and graphs: find them in documents and draw them by hand.

A figure is a dict:
  key     stable id (the same document always gives the same key), used to find YOUR traced drawing
  img     RGB uint8 array of the figure, with its text labels painted out when they could be read
  full    (optional) the same picture with its labels, printed in the template to trace over
  labels  [(text, x0, top, x1, bottom)] in img pixels: text that sits on the figure (axis labels, box titles ...)
  wfrac   width of the figure as a fraction of the page's text width (so it is drawn at a similar size)
  page    1-based page / position, for messages

Two ways it ends up handwritten:
  1. the personalised template prints a faint copy to trace over; your traced drawing is cut out of the photo
  2. otherwise sketch() turns the picture into wobbly pen lines + hatching, and the labels are written in your hand
"""
import hashlib, math, os, re
import cv2, numpy as np

RENDER_DPI = 200


def _key(*parts):
    return hashlib.sha1('|'.join(str(p) for p in parts).encode('utf-8')).hexdigest()[:16]


def _decode(blob):
    data = np.frombuffer(blob, np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:                                   # transparent PNG: put it on white paper
        a = img[..., 3:4].astype(np.float32) / 255
        img = (img[..., :3].astype(np.float32) * a + 255 * (1 - a)).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _usable(img):
    return img is not None and min(img.shape[:2]) >= 24


# ------------------------------------------------------------------ PDF
def _overlap(a, b, grow=0.0):
    return not (a[2] + grow < b[0] or b[2] + grow < a[0] or a[3] + grow < b[1] or b[3] + grow < a[1])


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _merge(boxes, grow=0.0):
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out = []
        for b in boxes:
            for o in out:
                if _overlap(o, b, grow):
                    o[:] = _union(o, b)
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def _classify(o, kind, W, H):
    """'skip' | 'shape' (curve / slanted line) | 'solid' (filled block, e.g. a bar) | 'axis' (thin straight rule)"""
    w, h = o['x1'] - o['x0'], o['bottom'] - o['top']
    if w * h > 0.4 * W * H:
        return 'skip'                                       # page background / frame
    fill, stroke = o.get('fill'), o.get('stroke')
    col = o.get('non_stroking_color')
    light = False
    if isinstance(col, (tuple, list)) and col and all(isinstance(c, (int, float)) for c in col):
        light = (min(col) > 0.9) if len(col) in (1, 3) else (max(col) < 0.1 if len(col) == 4 else False)
    if fill and not stroke and light and max(w, h) > 40:
        return 'skip'                                       # pale panel behind code / call-outs
    if max(w, h) < 6:
        return 'skip'                                       # bullets, dots
    if kind == 'curves':
        return 'shape'
    if kind == 'lines':
        return 'axis' if min(w, h) < 1.5 else 'shape'
    return 'axis' if min(w, h) < 2 else 'solid'


def pdf_figure_boxes(pg, exclude=()):
    """Bounding boxes (x0, top, x1, bottom in PDF points) of pictures and vector drawings on a pdfplumber page."""
    W, H = float(pg.width), float(pg.height)
    boxes = []
    for im in pg.images:
        b = [max(im['x0'], 0), max(im['top'], 0), min(im['x1'], W), min(im['bottom'], H)]
        if b[2] - b[0] > 30 and b[3] - b[1] > 30 and (b[2] - b[0]) * (b[3] - b[1]) >= 0.012 * W * H:
            boxes.append(b)
    objs = []
    for kind in ('curves', 'lines', 'rects'):
        for o in getattr(pg, kind):
            c = _classify(o, kind, W, H)
            b = [o['x0'], o['top'], o['x1'], o['bottom']]
            if c == 'skip' or any(_overlap(b, e) and b[0] >= e[0] - 2 and b[2] <= e[2] + 2 and b[1] >= e[1] - 2 and b[3] <= e[3] + 2 for e in exclude):
                continue
            objs.append((c, b))
    if 0 < len(objs) <= 4000:
        groups = []                                         # [bbox, counts]
        for c, b in objs:
            groups.append([list(b), {'shape': 0, 'solid': 0, 'axis': 0, c: 1}])
            groups[-1][1][c] = 1
        changed = True
        while changed:
            changed = False
            out = []
            for g in groups:
                for o in out:
                    if _overlap(o[0], g[0], 10):
                        o[0] = _union(o[0], g[0])
                        for k in o[1]:
                            o[1][k] += g[1].get(k, 0)
                        changed = True
                        break
                else:
                    out.append(g)
            groups = out
        for b, n in groups:
            area = (b[2] - b[0]) * (b[3] - b[1])
            tot = n['shape'] + n['solid'] + n['axis']
            drawing = n['shape'] >= 3 or (n['solid'] >= 3 and n['axis'] >= 1) or (n['shape'] >= 1 and n['solid'] >= 2)
            if tot >= 5 and drawing and area >= 0.03 * W * H:
                boxes.append(b)
    boxes = _merge(boxes, 4)
    if boxes:                                               # take in labels just outside the drawing (ticks, axis titles)
        try:
            lines = [l for l in pg.extract_text_lines(strip=True, return_chars=False) if l.get('text', '').strip()]
        except Exception:
            lines = []
        for b in boxes:
            for _ in range(4):
                grown = False
                for l in lines:
                    lb = [l['x0'], l['top'], l['x1'], l['bottom']]
                    if lb[0] >= b[0] - 1 and lb[2] <= b[2] + 1 and lb[1] >= b[1] - 1 and lb[3] <= b[3] + 1:
                        continue
                    short = (len(l['text']) <= 60 and (lb[2] - lb[0]) <= 1.02 * max(b[2] - b[0], 1)
                             and not l['text'].lower().startswith(('fig', 'table', 'source')))
                    if short and _overlap(b, lb, 20):
                        b[:] = _union(b, lb)
                        grown = True
                if not grown:
                    break
    return [[max(b[0] - 3, 0), max(b[1] - 3, 0), min(b[2] + 3, W), min(b[3] + 3, H)] for b in boxes]


def pdf_figures(pdf_path, pg, page_index, boxes):
    """Render each box of a pdfplumber page to an RGB image; read the text on it as labels."""
    import pypdfium2 as pdfium
    if not boxes:
        return []
    doc = pdfium.PdfDocument(pdf_path)
    try:
        page = doc[page_index]
        sc = RENDER_DPI / 72.0
        full = np.array(page.render(scale=sc).to_pil().convert('RGB'))
    finally:
        doc.close()
    W = float(pg.width)
    figs = []
    for b in boxes:
        x0, y0, x1, y1 = [int(round(v * sc)) for v in b]
        img = full[y0:y1, x0:x1].copy()
        if not _usable(img):
            continue
        orig = img.copy()
        labels = []
        try:                                   # word by word, so tick labels stay exactly under their ticks
            lines = pg.within_bbox(b).extract_words(keep_blank_chars=False, use_text_flow=False)
        except Exception:
            lines = []
        for ln in lines:
            t = ln.get('text', '').strip()
            if not t:
                continue
            lx0, lt, lx1, lb = [v * sc for v in (ln['x0'], ln['top'], ln['x1'], ln['bottom'])]
            lx0, lx1, lt, lb = lx0 - x0, lx1 - x0, lt - y0, lb - y0
            labels.append((t, lx0, lt, lx1, lb))
            cv2.rectangle(img, (int(lx0) - 1, int(lt) - 1), (int(lx1) + 1, int(lb) + 1), (255, 255, 255), -1)
        figs.append(dict(key=_key('pdf', page_index, *[round(v) for v in b]), img=img, full=orig, labels=labels,
                         wfrac=min(1.0, (b[2] - b[0]) / max(W * 0.8, 1)), page=page_index + 1))
    return figs


# ------------------------------------------------------------------ DOCX / Markdown
def docx_figures(paragraph_element, part):
    """Pictures inside one Word paragraph (python-docx oxml element)."""
    from docx.oxml.ns import qn
    figs = []
    for drawing in paragraph_element.iter(qn('w:drawing')):
        ext = next(drawing.iter(qn('wp:extent')), None)
        for blip in drawing.iter(qn('a:blip')):
            rid = blip.get(qn('r:embed'))
            if not rid or rid not in part.related_parts:
                continue
            blob = part.related_parts[rid].blob
            img = _decode(blob)
            if not _usable(img):
                continue
            wfrac = 0.8
            if ext is not None and ext.get('cx'):
                wfrac = min(1.0, int(ext.get('cx')) / (6.0 * 914400))        # 6 inch text width
            figs.append(dict(key=_key('img', hashlib.sha1(blob).hexdigest()), img=img, labels=[], wfrac=wfrac, page=0))
    return figs


MD_IMAGE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)\s*$')


def file_figure(path):
    try:
        blob = open(path, 'rb').read()
    except OSError:
        return None
    img = _decode(blob)
    if not _usable(img):
        return None
    return dict(key=_key('img', hashlib.sha1(blob).hexdigest()), img=img, labels=[], wfrac=0.8, page=0)


# ------------------------------------------------------------------ hand drawing
def wobble(alpha, seed, amp=2.0, cell=160):
    """Bend straight lines slightly, like a hand that is not using a ruler."""
    h, w = alpha.shape
    rng = np.random.default_rng(seed)
    gh, gw = max(h // cell, 1) + 2, max(w // cell, 1) + 2
    dx = cv2.resize(rng.normal(0, 1, (gh, gw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC) * amp
    dy = cv2.resize(rng.normal(0, 1, (gh, gw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC) * amp
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(alpha, xx + dx, yy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _hatch(h, w, spacing, seed):
    rng = np.random.default_rng(seed)
    m = np.zeros((h, w), np.uint8)
    off = rng.uniform(0, spacing)
    k = -int(h) - spacing
    while k < w + spacing:
        x0 = k + off + rng.normal(0, spacing * 0.08)
        cv2.line(m, (int(x0), h), (int(x0 + h * 1.0), 0), 255, 2, cv2.LINE_AA)
        k += spacing
    return m.astype(np.float32) / 255


def line_art(img, W, H, seed=0):
    """Picture -> float alpha (0..1) of pen lines at W x H pixels: lines stay lines (even pale ones), borders of
    coloured shapes become pen outlines, big dark areas become hatching."""
    W, H = max(int(W), 8), max(int(H), 8)
    rgb = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    pen = max(2, int(round(min(W, H) / 450.0)) + 1)
    k = pen * 6 + 1
    bg = cv2.dilate(g, np.ones((k, k), np.uint8))
    stroke = np.clip((0.95 - g / np.maximum(bg, 0.05)) / 0.18, 0, 1)        # darker than its surroundings
    dark = np.clip((0.80 - g) / 0.45, 0, 1)
    ks = max(pen * 4, 7) | 1
    solid = cv2.morphologyEx((dark > 0.25).astype(np.uint8), cv2.MORPH_OPEN, np.ones((ks, ks), np.uint8))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    e = cv2.Canny(cv2.GaussianBlur(lab[..., 0], (0, 0), 1.2), 14, 40)
    for c in (1, 2):
        e |= cv2.Canny(cv2.GaussianBlur(lab[..., c], (0, 0), 1.2), 8, 22)
    near = cv2.dilate(((stroke > 0.2) | (solid > 0)).astype(np.uint8), np.ones((pen * 3 + 1, pen * 3 + 1), np.uint8))
    e[near > 0] = 0                                     # only borders that have no drawn line of their own
    e = cv2.dilate(e, np.ones((pen, pen), np.uint8))
    edges = cv2.GaussianBlur(e.astype(np.float32) / 255, (0, 0), 0.6)
    rim = cv2.morphologyEx(solid, cv2.MORPH_GRADIENT, np.ones((pen + 1, pen + 1), np.uint8)).astype(np.float32)
    solid = solid.astype(np.float32)
    hatch = _hatch(H, W, spacing=pen * 5, seed=seed)
    a = np.maximum(np.maximum(stroke, dark) * (1 - solid), edges * 0.85)
    a = np.maximum(a, solid * hatch * (0.45 + 0.45 * dark))
    return np.maximum(a, rim)


def sketch(img, W, H, seed=0):
    """uint8 alpha (H, W) of a hand-drawn version of img."""
    a = line_art(img, W, H, seed)
    a = wobble(a, seed, amp=max(1.2, min(W, H) / 700.0))
    return (np.clip(a, 0, 1) * 255).astype(np.uint8)


def trace_guide(img, W, H, seed=0):
    """Light-grey RGB image printed in the template for the user to trace over (stays lighter than real ink)."""
    a = line_art(img, W, H, seed)
    v = 255 - np.clip(a, 0, 1) * (255 - 212)               # darkest 212/255 (83 %): calibration ignores it
    return np.dstack([v, v, v]).astype(np.uint8)

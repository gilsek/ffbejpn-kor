"""Re-draw the Japanese text of transparent UI label sprites in Korean (Pillow), keeping icons untouched.

For each sprite in build/out/sprite_work/label_list.txt (alpha mostly transparent: the glyphs are the sprite):
  1. text lines   : RapidOCR detection boxes (det only) on the sprite over grey, x3.
  2. text pixels  : connected components of the alpha mask that lie mostly inside the boxes. Everything else
                    (icons, frames) is kept byte for byte.
  3. style        : measured from those pixels - fill colour (top/bottom gradient), outline colour + width,
                    soft glow colour/radius/strength, per-line glyph height and centre.
  4. draw         : Noto Sans KR (variable weight) at 4x, glow -> outline -> fill, downscale; same centre and
                    glyph height as the Japanese line; width limited to the free space (shrink, then <=12% squeeze).
  5. pairs        : _s1/_s2, _l1/_l2, _1/_2, -on/-off, _on/_off, btn1/btn2 share the layout of the first one.

out : build/out/sprite_work/ko_render/<name>.png, ko_render/_report.json, ko_render/_sheet_<n>.png
usage: python -E -P tools/render_ko_labels.py [--names a.png,b.png] [--list FILE] [--limit N]
"""
import argparse, json, re, sys
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'build/out/sprite_work'
OUT = W / 'ko_render'
FONT = 'C:/Windows/Fonts/NotoSansKR-VF.ttf'
SS = 4  # supersampling

_ocr = None


def detector():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def det_boxes(rgba):
    s = 3
    bg = Image.new('RGB', rgba.size, (58, 58, 64)); bg.paste(rgba, (0, 0), rgba)
    arr = np.array(bg.resize((rgba.width * s, rgba.height * s), Image.LANCZOS))
    res, _ = detector()(arr, use_det=True, use_cls=False, use_rec=False)
    out = []
    for b in res or []:
        xs = [p[0] / s for p in b]; ys = [p[1] / s for p in b]
        out.append([max(0, min(xs)), max(0, min(ys)), min(rgba.width, max(xs)), min(rgba.height, max(ys))])
    return out


def text_components(a, boxes, rgb=None):
    """alpha array -> bool mask of components that are text (>=55% inside a det box)."""
    m = (a > 8).astype(np.uint8)
    n, lab = cv2.connectedComponents(m, connectivity=8)
    inbox = np.zeros_like(m, bool)
    for x0, y0, x1, y1 in boxes:
        inbox[int(y0):int(np.ceil(y1)), int(x0):int(np.ceil(x1))] = True
    comps = []
    for i in range(1, n):
        c = lab == i
        if (c & inbox).sum() >= 0.55 * c.sum():
            ys, xs = np.where(c & (a > 100))
            if len(ys):
                comps.append((c, ys.max() - ys.min() + 1, xs.min(), xs.max(), len(xs)))
    text = np.zeros_like(m, bool)
    for c, *_ in comps:
        text |= c
    if rgb is None:
        return text
    # an icon inside the detection box (often joined to the word by its glow): among the opaque pieces,
    # a chunky, colourful piece at the left/right end that is taller than the typical glyph
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    colour = (hsv[..., 1] > 90) & (hsv[..., 2] > 80)
    sub = (text & (a > 100)).astype(np.uint8)
    k, sl, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    pieces = [dict(i=i, x=stats[i, 0], y=stats[i, 1], w=stats[i, 2], h=stats[i, 3], n=stats[i, 4]) for i in range(1, k)]
    total = sum(p['n'] for p in pieces)
    big = [p for p in pieces if p['n'] > 0.02 * total]
    if len(big) >= 2:
        med_h = float(np.median([p['h'] for p in big]))
        ends = [min(big, key=lambda p: p['x']), max(big, key=lambda p: p['x'] + p['w'])]
        for p in ends:
            piece = sl == p['i']
            col = (colour & piece).sum() / max(1, p['n'])
            if p['h'] >= 1.2 * med_h and col > 0.3 and p['w'] >= 0.6 * p['h']:
                halo = cv2.dilate(piece.astype(np.uint8), np.ones((11, 11), np.uint8)).astype(bool)
                text &= ~(halo & ((a <= 100) | piece))
    return text


def lines_from(text, boxes, a):
    """lines = clusters of det boxes by vertical position; extent of each line = opaque text pixels in its band."""
    opq = text & (a > 200)
    if opq.sum() < 10:
        opq = text & (a > 100)
    bs = sorted(boxes, key=lambda b: (b[1] + b[3]) / 2)
    clusters = []
    for b in bs:
        if clusters:
            c = clusters[-1]
            ov = min(c[3], b[3]) - max(c[1], b[1])
            if ov > 0.4 * min(c[3] - c[1], b[3] - b[1]):
                clusters[-1] = [min(c[0], b[0]), min(c[1], b[1]), max(c[2], b[2]), max(c[3], b[3])]; continue
        clusters.append(list(b))
    H = text.shape[0]
    centres = [(c[1] + c[3]) / 2 for c in clusters]
    cuts = [0] + [int(round((centres[i] + centres[i + 1]) / 2)) for i in range(len(centres) - 1)] + [H]
    lines = []
    for i in range(len(clusters)):
        band = np.zeros_like(opq); band[cuts[i]:cuts[i + 1]] = True
        m = opq & band
        if m.sum() < 5:
            continue
        ys = np.where(m.any(1))[0]; xs = np.where(m.any(0))[0]
        lines.append({'y0': int(ys.min()), 'y1': int(ys.max()) + 1, 'x0': int(xs.min()), 'x1': int(xs.max()) + 1})
    return lines


def style_of(rgba, text):
    arr = np.array(rgba).astype(np.float32)
    a = arr[..., 3]
    op = text & (a > 200)
    if op.sum() < 10:
        op = text & (a > 100)
    rgb = arr[..., :3]
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    L = lum[op]
    hi = op & (lum >= np.percentile(L, 55))
    lo = op & (lum <= np.percentile(L, 20))
    ys = np.where(hi.any(1))[0]
    y0, y1 = ys.min(), ys.max()
    top = hi.copy(); top[int(y0 + (y1 - y0) * 0.4):] = False
    bot = hi.copy(); bot[:int(y0 + (y1 - y0) * 0.6)] = False
    med = lambda m: np.median(rgb[m], 0) if m.sum() else np.median(rgb[hi], 0)
    fill_top, fill_bot = med(top), med(bot)
    outline = med(lo) if lo.sum() else np.array([20, 20, 30], np.float32)
    # outline width: distance of opaque non-fill pixels to the fill core
    core = (hi).astype(np.uint8)
    dist = cv2.distanceTransform((1 - core).astype(np.uint8), cv2.DIST_L2, 3)
    ring = op & ~hi
    ow = float(np.percentile(dist[ring], 70)) if ring.sum() > 5 else 1.0
    # glow: semi transparent text pixels outside the opaque body
    body = (op).astype(np.uint8)
    gd = cv2.distanceTransform((1 - body).astype(np.uint8), cv2.DIST_L2, 3)
    soft = text & (a > 12) & (a < 160) & (gd >= 1.5)
    glow = None
    if soft.sum() > 0.15 * op.sum():
        glow = {'color': np.median(rgb[soft], 0).tolist(), 'radius': float(np.percentile(gd[soft], 85)),
                'alpha': float(np.percentile(a[soft], 80)) / 255}
    # stroke weight of the fill: core area / skeleton-ish length -> ratio to glyph height
    dcore = cv2.distanceTransform(core, cv2.DIST_L2, 3)
    stroke = 2 * float(np.percentile(dcore[core > 0], 90)) if core.sum() else 2.0
    return {'fill_top': fill_top.tolist(), 'fill_bot': fill_bot.tolist(), 'outline': outline.tolist(),
            'ow': max(0.6, min(ow, 4.0)), 'glow': glow, 'stroke': stroke, 'hi': hi}


_wcal = {}


def weight_for(stroke, gh):
    """Noto weight whose fill stroke (same measure) matches the original at glyph height gh."""
    key = int(round(gh))
    if key not in _wcal:
        cal = {}
        for w in (400, 500, 600, 700, 800, 900):
            size, _ = fit_size('공격력', gh, 1e9, w)
            f = font(size * SS, w)
            im = Image.new('L', (int(size * SS * 5), int(size * SS * 2)), 0)
            ImageDraw.Draw(im).text((10, 10), '공격력', font=f, fill=255)
            m = (np.array(im.resize((im.width // SS, im.height // SS), Image.LANCZOS)) > 128).astype(np.uint8)
            d = cv2.distanceTransform(m, cv2.DIST_L2, 3)
            cal[w] = 2 * float(np.percentile(d[m > 0], 90)) if m.sum() else 1
        _wcal[key] = cal
    cal = _wcal[key]
    return min(cal, key=lambda w: abs(cal[w] - stroke))


def font(size, weight):
    f = ImageFont.truetype(FONT, max(4, int(round(size))))
    f.set_variation_by_axes([weight])
    return f


def ink_box(text, size, weight):
    f = font(size, weight)
    im = Image.new('L', (int(size * (len(text) + 2) * 1.2) + 20, int(size * 2) + 20), 0)
    ImageDraw.Draw(im).text((10, 10), text, font=f, fill=255)
    bb = im.getbbox()
    return (bb[0] - 10, bb[1] - 10, bb[2] - 10, bb[3] - 10) if bb else (0, 0, 1, 1)


def fit_size(text, target_h, max_w, weight):
    """font size whose ink height == target_h; shrink (and allow <=12% squeeze) to fit max_w."""
    size = target_h * 1.3
    for _ in range(3):
        b = ink_box(text, size * SS, weight); h = (b[3] - b[1]) / SS
        size *= target_h / max(1e-3, h)
    b = ink_box(text, size * SS, weight); w = (b[2] - b[0]) / SS
    squeeze = 1.0
    if w > max_w:
        squeeze = max(0.88, max_w / w)
        if w * squeeze > max_w:
            size *= max_w / (w * squeeze)
    return size, squeeze


def split_two(ko):
    if '/' in ko:
        p = [s.strip() for s in ko.split('/', 1)]; return p
    if '(' in ko and ko.index('(') > 0:
        i = ko.index('('); return [ko[:i].strip(), ko[i:].strip()]
    words = ko.split(' ')
    if len(words) > 1:
        best = min(range(1, len(words)), key=lambda i: abs(len(' '.join(words[:i])) - len(' '.join(words[i:]))))
        return [' '.join(words[:best]), ' '.join(words[best:])]
    h = (len(ko) + 1) // 2
    return [ko[:h], ko[h:]]


def render_line(canvas_size, text, size, weight, squeeze, cx, cy, st):
    """returns RGBA layer (canvas size) with the line drawn centred at (cx, cy) (ink centre)."""
    Wd, Ht = canvas_size
    f = font(size * SS, weight)
    b = ink_box(text, size * SS, weight)
    iw, ih = b[2] - b[0], b[3] - b[1]
    pad = int(12 * SS + st['ow'] * SS * 2 + (st['glow']['radius'] if st['glow'] else 0) * SS * 2)
    tile = Image.new('L', (iw + 2 * pad, ih + 2 * pad), 0)
    ImageDraw.Draw(tile).text((pad - b[0], pad - b[1]), text, font=f, fill=255)
    if squeeze < 0.999:
        tile = tile.resize((max(1, int(tile.width * squeeze)), tile.height), Image.LANCZOS)
    fillm = np.array(tile).astype(np.float32) / 255
    k = max(1, int(round(st['ow'] * SS)))
    outm = cv2.dilate(fillm, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    th, tw = fillm.shape
    rgba = np.zeros((th, tw, 4), np.float32)
    if st['glow']:
        r = max(1, st['glow']['radius'] * SS)
        g = cv2.GaussianBlur(outm, (0, 0), r / 2)
        g = np.clip(g / max(1e-3, g.max()), 0, 1) * st['glow']['alpha']
        rgba[..., :3] = np.array(st['glow']['color'], np.float32); rgba[..., 3] = g
    def over(color, alpha):
        a0 = rgba[..., 3:4]; a1 = alpha[..., None]
        out_a = a1 + a0 * (1 - a1)
        rgba[..., :3] = (color * a1 + rgba[..., :3] * a0 * (1 - a1)) / np.maximum(out_a, 1e-6)
        rgba[..., 3:4] = out_a
    over(np.array(st['outline'], np.float32)[None, None, :].repeat(th, 0).repeat(tw, 1), outm)
    ys = np.linspace(0, 1, th, dtype=np.float32)[:, None, None]
    top, bot = np.array(st['fill_top'], np.float32), np.array(st['fill_bot'], np.float32)
    # gradient over the ink rows only
    rows = np.where(fillm.max(1) > 0.5)[0]
    if len(rows):
        t = np.clip((np.arange(th) - rows.min()) / max(1, rows.max() - rows.min()), 0, 1)[:, None, None]
    else:
        t = ys
    grad = top * (1 - t) + bot * t
    over(np.broadcast_to(grad, (th, tw, 3)).copy(), fillm)
    tile_rgba = Image.fromarray(np.dstack([np.clip(rgba[..., :3], 0, 255), np.clip(rgba[..., 3:] * 255, 0, 255)]).astype(np.uint8), 'RGBA')
    small = tile_rgba.resize((max(1, round(tile_rgba.width / SS)), max(1, round(tile_rgba.height / SS))), Image.LANCZOS)
    layer = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
    # ink centre in the small tile
    ink_cx = (pad + iw / 2) * (squeeze if squeeze < 0.999 else 1) / SS
    ink_cy = (pad + ih / 2) / SS
    layer.paste(small, (int(round(cx - ink_cx)), int(round(cy - ink_cy))))  # empty layer: copy RGBA as is
    return layer


PAIR = re.compile(r'(_s[12]|_l[12]|_[12]|-on|-off|_on|_off|btn[12]|_normal)(?=\.png$)')


def pair_key(name):
    return PAIR.sub('', name)


def process(name, ko, layouts, ocr_ja=''):
    # bands / speech balloons / plates carry a filled shape: erasing the text mask erases the shape too
    if re.search(r'ballon|balloon|plate|header|title|band|ribbon|banner', name, re.I):
        return None, {'name': name, 'status': 'shape_background'}
    src = Image.open(W / 'in' / name).convert('RGBA')
    a = np.array(src)[..., 3]
    boxes = det_boxes(src)
    if not boxes:
        return None, {'name': name, 'status': 'no_text_box'}
    text = text_components(a, boxes, np.array(src)[..., :3])
    if text.sum() < 10:
        return None, {'name': name, 'status': 'no_text_pixels'}
    # text drawn on a filled shape (ribbon, plate): the merged component reaches far outside the text boxes,
    # and erasing it would erase the shape too -> leave for manual work
    grown = np.zeros_like(text)
    for x0, y0, x1, y1 in boxes:
        m = 0.25 * (y1 - y0)
        grown[max(0, int(y0 - m)):int(y1 + m) + 1, max(0, int(x0 - m)):int(x1 + m) + 1] = True
    solid = (text & (a > 200)).astype(np.uint8)
    dd = cv2.distanceTransform(solid, cv2.DIST_L2, 3)
    hsv = cv2.cvtColor(np.array(src)[..., :3], cv2.COLOR_RGB2HSV)
    thick = dd > 4; col = thick & (hsv[..., 1] > 130) & (hsv[..., 2] > 90)
    ys_, xs_ = np.where(text)
    bb = (np.ptp(ys_) + 1) * (np.ptp(xs_) + 1)
    if (text & ~grown & (a > 200)).sum() > 0.2 * max(1, solid.sum()) or             (col.sum() > 0.55 * max(1, thick.sum()) and col.sum() > 0.12 * bb):
        return None, {'name': name, 'status': 'shape_background'}
    lines = lines_from(text, boxes, a)
    keep0 = (a > 8) & ~text
    if len(lines) >= 3 or keep0.sum() > 0.4 * a.size:
        return None, {'name': name, 'status': 'complex'}
    if '/' in ko and len(lines) == 1:
        ln = lines[0]; opq = text & (a > 200)
        prof = opq[ln['y0']:ln['y1']].sum(1).astype(float)
        h = len(prof)
        if h >= 16:
            lo_, hi_ = int(h * 0.3), int(h * 0.7)
            cut = ln['y0'] + lo_ + int(np.argmin(prof[lo_:hi_]))
            parts = []
            for y0, y1 in ((ln['y0'], cut), (cut, ln['y1'])):
                m = opq[y0:y1]
                ys = np.where(m.any(1))[0]; xs = np.where(m.any(0))[0]
                if len(ys) and len(xs):
                    parts.append({'y0': y0 + int(ys.min()), 'y1': y0 + int(ys.max()) + 1, 'x0': int(xs.min()), 'x1': int(xs.max()) + 1})
            if len(parts) == 2:
                lines = parts
    st = style_of(src, text)
    if lines:
        gmin = min(l['y1'] - l['y0'] for l in lines)
        st['ow'] = min(st['ow'], max(0.8, 0.08 * gmin))
    # free horizontal space: sprite width minus kept (non-text) opaque pixels on the text rows
    keep = (a > 8) & ~text
    base = np.array(src).copy(); base[text] = 0
    out = Image.fromarray(base, 'RGBA')
    ko_lines = [re.sub(r'\s*/\s*', ' ', ko).strip()] if len(lines) < 2 else split_two(ko)
    if len(lines) >= 2 and len(ko_lines) < len(lines):
        ko_lines = ko_lines + [''] * (len(lines) - len(ko_lines))
    use = lines[:len(ko_lines)] if len(lines) >= len(ko_lines) else lines
    if len(lines) == 1 and len(ko_lines) == 1:
        use = lines
    key = (pair_key(name), ko, src.size)
    lay = layouts.get(key)
    plan = []
    for i, (ln, txt) in enumerate(zip(use, ko_lines)):
        if not txt:
            continue
        hrows = np.where(st['hi'][ln['y0']:ln['y1']].any(1))[0]
        gh = (hrows.max() - hrows.min() + 1) if len(hrows) >= 3 else ln['y1'] - ln['y0'] - 2 * st['ow']
        cx = (ln['x0'] + ln['x1']) / 2; cy = (ln['y0'] + ln['y1']) / 2
        # free span on these rows
        band = keep[ln['y0']:ln['y1']].any(0)
        left = ln['x0']; right = ln['x1']
        while left > 0 and not band[left - 1]:
            left -= 1
        while right < src.width and not band[right]:
            right += 1
        margin = 2 + st['ow'] + (st['glow']['radius'] if st['glow'] else 0) * 0.5
        max_w = max(4, min(right - cx, cx - left) * 2 - 2 * margin)
        weight = max(400, weight_for(st['stroke'], gh) - 100)
        if gh < 24:
            weight = min(weight, 600)
        plan.append((txt, max(4, gh), max_w, weight, cx, cy))
    if lay is None:
        sizes = [fit_size(t, gh, mw, wt) for t, gh, mw, wt, _, _ in plan]
        # all lines of one label share one size (smallest)
        s = min(x[0] for x in sizes) if sizes else 0; q = min(x[1] for x in sizes) if sizes else 1
        lay = {'size': s, 'squeeze': q, 'centres': [(cx, cy) for *_, cx, cy in plan], 'weights': [p[3] for p in plan]}
        layouts[key] = lay
    for (txt, gh, mw, wt, _, _), (cx, cy), w8 in zip(plan, lay['centres'], lay['weights']):
        out.alpha_composite(render_line(src.size, txt, lay['size'], w8, lay['squeeze'], cx, cy, st))
    kept_diff = int(np.abs(np.array(out).astype(int)[keep & ~cv2.dilate(text.astype(np.uint8), np.ones((3, 3))).astype(bool)]
                           - np.array(src).astype(int)[keep & ~cv2.dilate(text.astype(np.uint8), np.ones((3, 3))).astype(bool)]).sum())
    orig_h = max(l['y1'] - l['y0'] for l in use) if use else 0
    ja = (ocr_ja or '')
    warn = 'ko_short' if len(ko.replace(' ', '')) < 0.45 * len(ja.replace(' ', '')) else ''
    return out, {'name': name, 'status': 'ok', 'warn': warn, 'lines': len(use), 'ko': ko, 'size': round(lay['size'], 1),
                 'squeeze': round(lay['squeeze'], 3), 'weight': lay['weights'][0] if lay['weights'] else None, 'orig_line_h': orig_h, 'kept_pixels_changed': kept_diff,
                 'glow': bool(st['glow']), 'ow': round(st['ow'], 2)}


def sheet(rows, path):
    from PIL import ImageFont as F
    fnt = F.truetype('malgun.ttf', 12)
    H = sum(int(o.height * max(0.5, min(2.0, 290 / o.width, 160 / o.height))) + 12 for _, o, n, _ in rows) + 10
    sh = Image.new('RGB', (900, H), (36, 36, 42)); d = ImageDraw.Draw(sh); y = 5
    for name, o, n, info in rows:
        sc = max(0.5, min(2.0, 290 / o.width, 160 / o.height))
        for j, im in enumerate((o, n)):
            t = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
            bg = Image.new('RGB', t.size, (78, 78, 88))
            for yy in range(0, t.height, 16):
                for xx in range(0, t.width, 16):
                    if (xx // 16 + yy // 16) % 2:
                        bg.paste((92, 92, 104), (xx, yy, xx + 16, yy + 16))
            bg.paste(t, (0, 0), t); sh.paste(bg, (5 + j * 300, y))
        d.text((610, y + 2), name[:40], fill=(230, 230, 130), font=fnt)
        d.text((610, y + 18), f"{info.get('ko','')}  L{info.get('lines')} s{info.get('size')} q{info.get('squeeze')} w{info.get('weight')} {info.get('warn','')}", fill=(255, 255, 255), font=fnt)
        y += int(o.height * sc) + 12
    sh.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names'); ap.add_argument('--list'); ap.add_argument('--limit', type=int)
    ap.add_argument('--sheet', default='_sheet')
    args = ap.parse_args()
    ocr = {x['name']: x for x in json.loads((W / 'ocr.json').read_text(encoding='utf-8'))}
    if args.names:
        names = args.names.split(',')
    else:
        names = [l.strip() for l in Path(args.list or W / 'label_list.txt').read_text(encoding='utf-8').splitlines() if l.strip()]
    names = sorted(names, key=pair_key)
    if args.limit:
        names = names[:args.limit]
    OUT.mkdir(parents=True, exist_ok=True)
    layouts, report, rows = {}, [], []
    for n in names:
        ko = re.sub(r'\s*[\n/]\s*', ' / ', (ocr.get(n) or {}).get('ko', '').strip())
        if not ko:
            report.append({'name': n, 'status': 'no_translation'}); continue
        try:
            img, info = process(n, ko, layouts, (ocr.get(n) or {}).get('ja', ''))
        except Exception as e:
            img, info = None, {'name': n, 'status': f'error {e!r}'[:200]}
        report.append(info)
        if img is not None:
            img.save(OUT / n)
            rows.append((n, Image.open(W / 'in' / n).convert('RGBA'), img, info))
    per = 14
    for i in range(0, len(rows), per):
        sheet(rows[i:i + per], OUT / f'{args.sheet}_{i // per + 1}.png')
    (OUT / '_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    from collections import Counter
    print(Counter(r['status'] if not r['status'].startswith('error') else 'error' for r in report))
    for r in report:
        if r['status'] != 'ok':
            print(' ', r['name'], r['status'])


if __name__ == '__main__':
    main()

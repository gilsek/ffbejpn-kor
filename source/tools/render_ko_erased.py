"""Draw the Korean text on sprites whose Japanese text was erased locally (LaMa, OCR-box masks) (2026-11-10).

Inputs (build/out/sprite_work):
  in/<name>                      original sprite (Japanese)
  ocrmask_all/final_local/<name> erased sprite (tools/lama_erase.py with tools/ocr_text_mask.py masks)
  ocrmask_all/report.json        OCR text boxes per sprite
  ocr.json                       Korean text ("ko")
Style (fill gradient, outline, glow, weight) is measured from the pixels the erase changed (= the Japanese glyphs),
with the functions of tools/render_ko_labels.py; the line centre and glyph height follow the Japanese line, the width
is limited to the erased span (shrink, then <= 12 % squeeze). _1/_2, btn1/btn2 ... pairs share one layout.

out: ocrmask_all/ko/<name>.png, ko/_report.json, ko/_sheet_<n>.png (original | Korean)
--clear: transparent text-only labels. No LaMa: the text pixels (OCR stroke mask ocrmask_all/masks, grown 2 px, inside
the text boxes) are made transparent and the Korean is drawn with its own alpha.
--scale F: Korean glyph height = F x Japanese glyph height (default 0.85; 1.0 looked oversized on buttons, 2026-11-10).
Tilted text: the angle of the OCR box (top edge) is applied to the drawn line (rotation about the line centre).
usage: python -I -X utf8 tools/render_ko_erased.py [--list FILE] [--names a.png,b.png] [--clear] [--scale 0.85] [--out DIR]
"""
import argparse, json, re, sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_ko_labels as L                                    # noqa: E402

W = Path(__file__).resolve().parents[1] / 'build/out/sprite_work'
M = W / 'ocrmask_all'
OUT = M / 'ko'


def cleared(name, src, boxes):
    a = np.array(src)
    region = np.zeros(a.shape[:2], np.uint8)
    for q in boxes:
        cv2.fillPoly(region, [np.array(q, np.int32)], 255)
    region = cv2.dilate(region, np.ones((7, 7), np.uint8)) > 0
    m = np.array(Image.open(M / 'masks' / name).convert('L')) > 127
    m = (cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & region
    b = a.copy(); b[m] = 0
    return Image.fromarray(b, 'RGBA'), m


def angle_of(boxes, cy):
    """tilt (degrees, PIL counter-clockwise) of the OCR box nearest to the line centre y; 0 when under 5 degrees."""
    import math
    if not boxes:
        return 0.0
    q = min(boxes, key=lambda q: abs(sum(p[1] for p in q) / 4 - cy))
    (x0, y0), (x1, y1), (x2, y2) = q[0], q[1], q[2]
    w, h = math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x1, y2 - y1)
    ang = -math.degrees(math.atan2(y1 - y0, x1 - x0))
    # the detector's box angle is noisy on short words: only clear tilts on boxes at least twice as wide as tall
    return ang if 5 <= abs(ang) <= 45 and w >= 2 * h else 0.0


def process(name, ko, layouts, boxes, clear=False, scale=0.85):
    src = Image.open(W / 'in' / name).convert('RGBA')
    if clear:
        base, cm = cleared(name, src, boxes)
    else:
        base = Image.open(M / 'final_local' / name).convert('RGBA')
    o, e = np.array(src).astype(np.int16), np.array(base).astype(np.int16)
    a = o[..., 3].astype(np.uint8)
    text = (cm if clear else (np.abs(o[..., :3] - e[..., :3]).max(2) > 30)) & (a > 100)
    if text.sum() < 10:
        return None, {'name': name, 'status': 'no_text_pixels'}
    xyxy = [[min(p[0] for p in q), min(p[1] for p in q), max(p[0] for p in q) + 1, max(p[1] for p in q) + 1] for q in boxes]
    lines = L.lines_from(text, xyxy, np.where(text, 255, a).astype(np.uint8))
    if not lines:
        return None, {'name': name, 'status': 'no_lines'}
    if len(lines) >= 3:
        return None, {'name': name, 'status': 'complex'}
    st = L.style_of(src, text)
    gmin = min(l['y1'] - l['y0'] for l in lines)
    st['ow'] = min(st['ow'], max(0.8, 0.08 * gmin))
    changed = np.abs(o - e).max(2) > 0
    ko_lines = [re.sub(r'\s*/\s*', ' ', ko).strip()] if len(lines) < 2 else L.split_two(ko)
    use = lines[:len(ko_lines)]
    key = (L.pair_key(name), ko, src.size)
    lay = layouts.get(key)
    plan = []
    for ln, txt in zip(use, ko_lines):
        if not txt:
            continue
        hrows = np.where(st['hi'][ln['y0']:ln['y1']].any(1))[0]
        gh = (hrows.max() - hrows.min() + 1) if len(hrows) >= 3 else ln['y1'] - ln['y0'] - 2 * st['ow']
        cx, cy = (ln['x0'] + ln['x1']) / 2, (ln['y0'] + ln['y1']) / 2
        cols = np.where(changed[ln['y0']:ln['y1']].any(0))[0]
        span = (cols.max() - cols.min() + 1) if len(cols) else ln['x1'] - ln['x0']
        margin = st['ow'] + (st['glow']['radius'] if st['glow'] else 0) * 0.5
        max_w = max(4, min(max(span, (ln['x1'] - ln['x0']) * 1.1), src.width - 12) - 2 * margin)
        weight = max(400, L.weight_for(st['stroke'], gh) - 100)
        if gh < 24:
            weight = min(weight, 600)
        plan.append((txt, max(4, gh * scale), max_w, weight, cx, cy))
    if lay is None:
        sizes = [L.fit_size(t, gh, mw, wt) for t, gh, mw, wt, _, _ in plan]
        lay = {'size': min(s for s, _ in sizes), 'squeeze': min(q for _, q in sizes),
               'centres': [(cx, cy) for *_, cx, cy in plan], 'weights': [p[3] for p in plan]}
        layouts[key] = lay
    out = base.copy()
    for (txt, *_), (cx, cy), w8 in zip(plan, lay['centres'], lay['weights']):
        layer = L.render_line(src.size, txt, lay['size'], w8, lay['squeeze'], cx, cy, st)
        ang = angle_of(boxes, cy)
        if ang:
            layer = layer.rotate(ang, resample=Image.BICUBIC, center=(cx, cy))
        out.alpha_composite(layer)
    if not clear:
        res = np.array(out); res[..., 3] = a                      # keep the original alpha exactly
        out = Image.fromarray(res, 'RGBA')
    return out, {'name': name, 'status': 'ok', 'lines': len(use), 'ko': ko, 'size': round(lay['size'], 1),
                 'squeeze': round(lay['squeeze'], 3), 'weight': lay['weights'][0] if lay['weights'] else None,
                 'glow': bool(st['glow'])}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--list', type=Path, default=M / 'todo_local.txt'); ap.add_argument('--names'); ap.add_argument('--clear', action='store_true')
    ap.add_argument('--scale', type=float, default=0.85); ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    names = a.names.split(',') if a.names else [l.strip() for l in a.list.read_text(encoding='utf-8').splitlines() if l.strip()]
    names = sorted(names, key=L.pair_key)
    ocr = {x['name']: x for x in json.loads((W / 'ocr.json').read_text(encoding='utf-8'))}
    boxes = json.loads((M / 'report.json').read_text(encoding='utf-8'))
    global OUT
    OUT = a.out or OUT
    OUT.mkdir(parents=True, exist_ok=True)
    layouts, report, rows = {}, [], []
    for n in names:
        ko = re.sub(r'\s*[\n/]\s*', ' / ', (ocr.get(n) or {}).get('ko', '').strip())
        try:
            img, info = process(n, ko, layouts, boxes[n]['boxes'], a.clear, a.scale) if ko else (None, {'name': n, 'status': 'no_translation'})
        except Exception as ex:                                  # report and go on
            img, info = None, {'name': n, 'status': f'error {ex!r}'[:200]}
        report.append(info)
        if img is not None:
            img.save(OUT / n)
            rows.append((n, Image.open(W / 'in' / n).convert('RGBA'), img, info))
    for i in range(0, len(rows), 14):
        L.sheet(rows[i:i + 14], OUT / f'_sheet{"_clear" if a.clear else ""}_{i // 14 + 1:02d}.png')
    (OUT / ('_report_clear.json' if a.clear else '_report.json')).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    from collections import Counter
    print(Counter(r['status'] if not r['status'].startswith('error') else 'error' for r in report))
    for r in report:
        if r['status'] != 'ok':
            print(' ', r['name'], r['status'])


if __name__ == '__main__':
    main()

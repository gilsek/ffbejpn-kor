"""Text-only erase masks from OCR text boxes (2026-11-10).

The auto mask of tools/lama_erase.py takes every bright / high-contrast pixel, so on icons with art behind the text it
covers the art too. Here the OCR text detector (PP-OCRv4 det, bundled with rapidocr_onnxruntime) finds the text boxes,
and the mask is the stroke mask *inside those boxes only*.

  python -I -X utf8 tools/ocr_text_mask.py --in build/out/sprite_work/in --list names.txt --out <mask dir> --report <json>

Each sprite is also classified for the erase route:
  local   flat button / tab (opaque pixels fill >= --fill of the bounding box) -> LaMa (lama_erase.py --mask <dir>)
  gemini  icon with art behind the text (rounded / ornament outline, fill < --fill) -> wait for the Gemini quota
  label   transparent text-only label -> nothing to erase: clear it and draw the Korean text
Calibrated on 14 sprites judged by eye (2026-11-10): tabs/buttons fill 0.94-0.95, art icons 0.75-0.85; LaMa smears the
ornament frame of art icons, and the 'busy' gradient score did not separate the two (kept in the report only).
  none    no text box found (mask left empty, sprite not touched)
Only the detector is used (no recognition), so rapidocr's yaml config is never read.
"""
import argparse, json, sys, types
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.modules.setdefault('yaml', types.ModuleType('yaml'))      # rapidocr imports yaml at module level; det does not use it
from rapidocr_onnxruntime.ch_ppocr_det import TextDetector     # noqa: E402
import rapidocr_onnxruntime as R                                # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lama_erase import auto_mask, is_text_only_label            # noqa: E402

BG = (58, 58, 64)


def detector():
    return TextDetector({'intra_op_num_threads': -1, 'inter_op_num_threads': -1, 'use_cuda': False, 'use_dml': False,
                         'model_path': str(Path(R.__file__).parent / 'models/ch_PP-OCRv4_det_infer.onnx'),
                         'limit_side_len': 736, 'limit_type': 'min', 'std': [0.5] * 3, 'mean': [0.5] * 3,
                         'thresh': 0.3, 'box_thresh': 0.5, 'max_candidates': 1000, 'unclip_ratio': 1.6,
                         'use_dilation': True, 'score_mode': 'fast'})


def boxes_of(det, rgba):
    a = rgba[:, :, 3:4].astype(np.float32) / 255
    comp = (rgba[:, :, :3] * a + np.array(BG) * (1 - a)).astype(np.uint8)
    h, w = comp.shape[:2]
    s = max(1, int(np.ceil(64 / min(h, w))))                    # tiny sprites: upscale so the detector sees the text
    img = cv2.resize(comp, (w * s, h * s), interpolation=cv2.INTER_CUBIC) if s > 1 else comp
    pad = 16                                                    # text touching the edge is missed without a margin
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=BG)
    b, _ = det(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    if b is None:
        return []
    return [((np.array(q, np.float32) - pad) / s).round().astype(np.int32) for q in b]


def busy(rgba, region, text):
    """Background complexity right around the text: mean local gradient of the non-text opaque pixels in a ring."""
    ring = (cv2.dilate(region, np.ones((9, 9), np.uint8)) > 0) & ~(cv2.dilate(text, np.ones((5, 5), np.uint8)) > 0)
    ring &= rgba[:, :, 3] > 200
    if ring.sum() < 30:
        return 0.0, int(ring.sum())
    g = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    mag = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))
    return float(mag[ring].mean()), int(ring.sum())


def make(det, rgba, grow=3, fill_thr=0.9, name=''):
    h, w = rgba.shape[:2]
    region = np.zeros((h, w), np.uint8)
    qs = boxes_of(det, rgba)
    for q in qs:
        cv2.fillPoly(region, [q], 255)
    info = {'boxes': [q.tolist() for q in qs]}
    if not qs:
        info['route'] = 'none'
        return region, info
    region = cv2.dilate(region, np.ones((5, 5), np.uint8))       # box edges are tight: 2 px margin for the glow
    strokes = auto_mask(rgba, grow=0, border=0)
    text = cv2.bitwise_and(strokes, region)
    mask = cv2.bitwise_and(cv2.dilate(text, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1,) * 2)), region)
    opaque = max(1, int((rgba[:, :, 3] > 16).sum()))
    score, ring = busy(rgba, region, text)
    ys, xs = np.where(rgba[:, :, 3] > 128)
    fill = float(len(xs)) / ((np.ptp(xs) + 1) * (np.ptp(ys) + 1)) if len(xs) else 0.0
    route = 'label' if ('_label' in name or is_text_only_label(rgba)[0]) else 'local' if fill >= fill_thr else 'gemini'
    info.update({'mask_frac': round(float((mask > 0).sum()) / opaque, 3), 'busy': round(score, 1), 'ring_px': ring,
                 'fill': round(fill, 3), 'route': route})
    return mask, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', type=Path, required=True)
    ap.add_argument('--list', type=Path, help='file names, one per line (default: every PNG)')
    ap.add_argument('--out', type=Path, required=True, help='mask folder (white = erase)')
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--fill', type=float, default=0.9, help='opaque share of the bounding box; below -> gemini route')
    a = ap.parse_args()
    names = ([l.strip() for l in a.list.read_text(encoding='utf-8').splitlines() if l.strip()] if a.list
             else sorted(p.name for p in a.inp.glob('*.png')))
    a.out.mkdir(parents=True, exist_ok=True)
    det, rep = detector(), {}
    for i, n in enumerate(names, 1):
        rgba = np.array(Image.open(a.inp / n).convert('RGBA'))
        mask, info = make(det, rgba, fill_thr=a.fill, name=n)
        Image.fromarray(mask).save(a.out / n)
        rep[n] = info
        if i % 100 == 0:
            print(i, '/', len(names), flush=True)
    a.report.write_text(json.dumps(rep, ensure_ascii=False, indent=0), encoding='utf-8')
    from collections import Counter
    print(json.dumps(Counter(v['route'] for v in rep.values())))


if __name__ == '__main__':
    main()

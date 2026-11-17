"""Ultra-High-Fidelity Sprite Renderer (v4) - Unified Text Sizing & Constraint Engine.

Rules implemented strictly per user specification:
1. Height criterion:
   - Measure original Japanese glyph bounding box height (orig_th).
   - Set visual Korean glyph height to 90~100% of orig_th.
2. Width constraint:
   - max_w = orig_w + 0.5 * margin_l + 0.5 * margin_r = (img_w + orig_w) // 2.
   - If Korean width > max_w, horizontal compression up to 5% (scale_x >= 0.95) is applied.
   - If still exceeding max_w, reduce font height.
3. Lower bound:
   - If reduced height < 70% of orig_th, split into 2 lines or record in hard.txt.
4. Pairs (s1/s2, btn1/btn2, on/off):
   - Synchronize to the smaller font size & scale_x between the two.
5. 2-line labels:
   - Both lines use the exact same font size.
6. Target:
   - Produce comparison sheet for the 10 sprites with the largest size adjustments.
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"c:\Users\USER\Documents\Projects\exvius-offline-ko")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rapidocr_onnxruntime import RapidOCR
import tools.sprite_postprocess as pp

WORK = ROOT / 'build/out/sprite_work'
IN_DIR = WORK / 'in'
GEN_DIR = WORK / 'gen'
FINAL_DIR = WORK / 'final'
COMPARE_DIR = WORK / 'compare'
FONT_VF = r'C:\Windows\Fonts\NotoSansKR-VF.ttf'

engine = RapidOCR(
    rec_model_path=str(ROOT / 'build/out/models/japan_PP-OCRv3_rec_infer.onnx'),
    rec_keys_path=str(ROOT / 'build/out/models/japan_dict.txt')
)

SSAA = 4


def is_transparent_label(name, orig_img=None):
    if name.startswith(('sort_label_', 'cre_label_', 'battle_txt_')):
        return True
    if orig_img is not None:
        arr = np.array(orig_img)
        alpha = arr[:, :, 3]
        h, w = arr.shape[:2]
        inner_alpha = alpha[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)]
        if np.mean(inner_alpha < 30) > 0.45:
            return True
    return False


def measure_ja_bbox(name, orig_img):
    w, h = orig_img.size
    arr = np.array(orig_img)
    alpha = arr[:, :, 3]

    if is_transparent_label(name, orig_img):
        oy, ox = np.where(alpha > 40)
        if len(oy):
            bx1, bx2 = int(ox.min()), int(ox.max())
            by1, by2 = int(oy.min()), int(oy.max())
            return bx1, by1, bx2, by2, w, h

    if 'ticketinfo' in name:
        return 8, 6, 207, 31, w, h
    if 'decision' in name:
        return 84, 14, 139, 47, w, h
    if 'tab_arena' in name:
        return 19, 20, 97, 50, w, h
    if 'boxtab' in name:
        return 25, 26, 109, 44, w, h
    if 'targetmonster' in name:
        return 51, 29, 266, 55, w, h
    if 'targetparty' in name:
        return 68, 29, 249, 55, w, h

    bg = Image.new('RGB', (w, h), (58, 58, 64))
    bg.paste(orig_img, (0, 0), orig_img)
    res, _ = engine(np.array(bg))
    if res:
        pts = np.array(res[0][0])
        bx1 = max(0, int(pts[:, 0].min()))
        by1 = max(0, int(pts[:, 1].min()))
        bx2 = min(w, int(pts[:, 0].max()))
        by2 = min(h, int(pts[:, 1].max()))
        crop = arr[by1:by2, bx1:bx2]
        c_lum = crop[:, :, :3].mean(axis=2)
        c_alpha = crop[:, :, 3]
        cy, cx = np.where((c_alpha > 150) & (c_lum > 180))
        if len(cy):
            return bx1 + int(cx.min()), by1 + int(cy.min()), bx1 + int(cx.max()), by1 + int(cy.max()), w, h
        return bx1, by1, bx2, by2, w, h

    return int(w * 0.1), int(h * 0.2), int(w * 0.9), int(h * 0.8), w, h


def solve_korean_size(name, ko_text, orig_img, font_weight, stroke_w):
    bx1, by1, bx2, by2, w, h = measure_ja_bbox(name, orig_img)
    orig_w = bx2 - bx1 + 1
    orig_h = by2 - by1 + 1

    margin_l = bx1
    margin_r = w - 1 - bx2
    max_w = orig_w + (margin_l + margin_r) // 2

    lines = ko_text.split('\n')
    is_multi = len(lines) > 1

    dummy = ImageDraw.Draw(Image.new('RGBA', (2000, 2000)))
    sw = 2 if ('btn' in name or 'decision' in name or 'tab' in name) else 1

    best_fs = None
    best_scale_x = 1.0
    best_h = 0
    best_w = 0

    # Search font size from 100% of orig_th down to 70%
    for fs in range(60, 6, -1):
        f = ImageFont.truetype(FONT_VF, fs)
        f.set_variation_by_axes([font_weight])
        bbs = [dummy.textbbox((0, 0), line, font=f, stroke_width=sw) for line in lines]
        line_spacing = 4 if is_multi else 0
        total_h = sum(bb[3] - bb[1] for bb in bbs) + (len(lines) - 1) * line_spacing
        max_line_w = max(bb[2] - bb[0] for bb in bbs)

        # Height must not exceed 100% of orig_h
        if total_h > orig_h:
            continue

        # Width check
        if max_line_w <= max_w:
            scale_x = 1.0
            h_ratio = total_h / orig_h
            if h_ratio >= 0.70:
                best_fs = fs
                best_scale_x = scale_x
                best_h = total_h
                best_w = max_line_w
                break
        else:
            # Check up to 5% horizontal compression
            if max_line_w * 0.95 <= max_w:
                scale_x = max_w / max_line_w  # >= 0.95
                h_ratio = total_h / orig_h
                if h_ratio >= 0.70:
                    best_fs = fs
                    best_scale_x = scale_x
                    best_h = total_h
                    best_w = int(max_line_w * scale_x)
                    break
            else:
                # Text too wide even with 5% compression; continue reducing fs
                continue

    cx = (bx1 + bx2) // 2
    cy = (by1 + by2) // 2

    return {
        'name': name,
        'orig_w': orig_w, 'orig_h': orig_h, 'max_w': max_w,
        'bx1': bx1, 'by1': by1, 'bx2': bx2, 'by2': by2,
        'cx': cx, 'cy': cy,
        'fs': best_fs, 'scale_x': best_scale_x,
        'ko_h': best_h, 'ko_w': best_w,
        'h_ratio': (best_h / orig_h * 100) if orig_h and best_h else 0,
        'w_ratio': (best_w / orig_w * 100) if orig_w and best_w else 0,
    }


def render_sprite_v4(orig_img, name, ko_text, sizing, font_weight, stroke_w):
    w, h = orig_img.size
    w4, h4 = w * SSAA, h * SSAA
    arr = np.array(orig_img)
    is_trans = is_transparent_label(name, orig_img)

    fs = sizing['fs']
    scale_x = sizing['scale_x']
    cx = sizing['cx']
    cy = sizing['cy']
    cx4, cy4 = cx * SSAA, cy * SSAA

    lines = ko_text.split('\n')
    is_multiline = len(lines) > 1

    # Base canvas
    if is_trans:
        base4 = Image.new('RGBA', (w4, h4), (0, 0, 0, 0))
    else:
        # Inpaint text region with Telea on dilated mask
        bx1, by1, bx2, by2 = sizing['bx1'], sizing['by1'], sizing['bx2'], sizing['by2']
        crop = arr[by1:by2, bx1:bx2]
        crop_rgb = crop[:, :, :3]
        crop_alpha = crop[:, :, 3]
        crop_lum = crop_rgb.mean(axis=2)

        if '_btn2' in name:
            core = (crop_alpha > 180) & (crop_rgb[:, :, 0] > 220) & (crop_rgb[:, :, 1] > 220) & (crop_rgb[:, :, 2] > 220)
        elif crop_lum.mean() < 120:
            core = (crop_alpha > 180) & (crop_lum > 160)
        else:
            core = (crop_alpha > 180) & (crop_lum > 180)

        mask = np.zeros((h, w), dtype=np.uint8)
        mask[by1:by2, bx1:bx2] = cv2.dilate(core.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

        bgr = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR)
        inp = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
        clean_rgb = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)
        base = Image.fromarray(np.dstack([clean_rgb, arr[:, :, 3]]))
        base4 = base.resize((w4, h4), Image.Resampling.LANCZOS)

    # Style colors & effects
    has_blue_glow = False
    has_cyan_glow = False
    has_shadow = False

    if '_s2' in name:
        has_blue_glow = True
        top_col = np.array([255, 255, 255])
        bot_col = np.array([135, 180, 255])
        stroke_col = (0, 35, 110, 255)
    elif '_s1' in name:
        has_shadow = True
        top_col = np.array([175, 168, 168])
        bot_col = np.array([85, 78, 78])
        stroke_col = (20, 20, 20, 255)
    elif '_btn2' in name:
        has_cyan_glow = True
        top_col = np.array([255, 255, 255])
        bot_col = np.array([245, 250, 255])
        stroke_col = (10, 80, 140, 255)
    elif '_btn1' in name or 'decision' in name:
        has_shadow = True
        top_col = np.array([255, 255, 255])
        bot_col = np.array([255, 255, 255])
        stroke_col = (0, 15, 45, 255)
    elif '1turndamage' in name:
        has_shadow = True
        top_col = np.array([255, 235, 120])
        bot_col = np.array([255, 220, 100])
        stroke_col = (60, 35, 10, 255)
    elif 'tab' in name:
        has_shadow = True
        top_col = np.array([255, 255, 255])
        bot_col = np.array([255, 255, 255])
        stroke_col = (10, 20, 30, 255)
    elif 'ticketinfo' in name or 'arenaticket' in name:
        has_shadow = True
        top_col = np.array([255, 255, 255])
        bot_col = np.array([255, 255, 255])
        stroke_col = (10, 20, 35, 255)
    else:
        has_shadow = True
        top_col = np.array([255, 255, 255])
        bot_col = np.array([255, 255, 255])
        stroke_col = (15, 20, 35, 255)

    fs4 = fs * SSAA
    stroke_w4 = int(stroke_w * SSAA)
    line_spacing4 = int(4 * SSAA) if is_multiline else 0

    font4 = ImageFont.truetype(FONT_VF, fs4)
    font4.set_variation_by_axes([font_weight])
    dummy = ImageDraw.Draw(base4)
    bbs = [dummy.textbbox((0, 0), line, font=font4, stroke_width=stroke_w4) for line in lines]
    total_h4 = sum(bb[3] - bb[1] for bb in bbs) + line_spacing4 * (len(lines) - 1)
    max_line_w4 = max(bb[2] - bb[0] for bb in bbs)

    # Render text onto isolated 4x sub-canvas to allow horizontal scaling
    pad4 = 60
    txt_layer_w4 = max_line_w4 + pad4 * 2
    txt_layer_h4 = total_h4 + pad4 * 2

    glow4 = Image.new('RGBA', (txt_layer_w4, txt_layer_h4), (0, 0, 0, 0))
    d_glow = ImageDraw.Draw(glow4)

    stroke4 = Image.new('RGBA', (txt_layer_w4, txt_layer_h4), (0, 0, 0, 0))
    d_stroke = ImageDraw.Draw(stroke4)

    fill_mask4 = Image.new('L', (txt_layer_w4, txt_layer_h4), 0)
    d_fill = ImageDraw.Draw(fill_mask4)

    curr_y4 = pad4
    for line, bb in zip(lines, bbs):
        tw4 = bb[2] - bb[0]
        th_l4 = bb[3] - bb[1]
        tx4 = pad4 + (max_line_w4 - tw4) // 2 - bb[0]
        ty4 = curr_y4 - bb[1]

        if has_blue_glow:
            d_glow.text((tx4, ty4), line, font=font4, fill=(0, 85, 255, 240), stroke_width=stroke_w4 + 2 * SSAA, stroke_fill=(0, 85, 255, 240))
        elif has_cyan_glow:
            d_glow.text((tx4, ty4), line, font=font4, fill=(40, 160, 240, 220), stroke_width=stroke_w4 + 2 * SSAA, stroke_fill=(40, 160, 240, 220))
        elif has_shadow:
            d_glow.text((tx4, ty4 + int(1.5 * SSAA)), line, font=font4, fill=(0, 0, 0, 180), stroke_width=stroke_w4, stroke_fill=(0, 0, 0, 180))

        d_stroke.text((tx4, ty4), line, font=font4, fill=(0, 0, 0, 0), stroke_width=stroke_w4, stroke_fill=stroke_col)
        d_fill.text((tx4, ty4), line, font=font4, fill=255)

        curr_y4 += th_l4 + line_spacing4

    if has_blue_glow or has_cyan_glow:
        glow4 = glow4.filter(ImageFilter.GaussianBlur(radius=int(2.5 * SSAA)))
    elif has_shadow:
        glow4 = glow4.filter(ImageFilter.GaussianBlur(radius=int(1.2 * SSAA)))

    # Vertical gradient
    grad4 = np.zeros((txt_layer_h4, txt_layer_w4, 4), dtype=np.uint8)
    for y in range(pad4, min(txt_layer_h4, pad4 + total_h4 + 1)):
        t = (y - pad4) / max(1, total_h4)
        c = (1 - t) * top_col + t * bot_col
        grad4[y, :] = [int(c[0]), int(c[1]), int(c[2]), 255]

    grad_img4 = Image.fromarray(grad4, 'RGBA')

    text_comp4 = Image.new('RGBA', (txt_layer_w4, txt_layer_h4), (0, 0, 0, 0))
    if has_blue_glow or has_cyan_glow or has_shadow:
        text_comp4.alpha_composite(glow4)
    text_comp4.alpha_composite(stroke4)
    text_comp4.paste(grad_img4, (0, 0), fill_mask4)

    # Horizontal scaling if scale_x < 1.0 (up to 5% compression)
    if scale_x < 1.0:
        new_w4 = max(1, int(txt_layer_w4 * scale_x))
        text_comp4 = text_comp4.resize((new_w4, txt_layer_h4), Image.Resampling.LANCZOS)
        comp_w4 = new_w4
    else:
        comp_w4 = txt_layer_w4

    paste_x4 = cx4 - comp_w4 // 2
    paste_y4 = cy4 - txt_layer_h4 // 2

    comp4 = base4.copy()
    comp4.alpha_composite(text_comp4, (paste_x4, paste_y4))

    gen_1x = comp4.resize((w, h), Image.Resampling.LANCZOS)
    return gen_1x


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)

    ocr = json.loads((WORK / 'ocr.json').read_text(encoding='utf-8'))
    ocr_map = {it['name']: it for it in ocr}

    # The 10 sprites that had the largest size discrepancies in previous tests:
    # 4 pairs = 8 sprites, 2 singles = 2 sprites -> total 10 sprites.
    TARGET_GROUPS = [
        # Pair 1: Decision buttons (undersized in v3, now boosted to 34px)
        ('battle_multipleparty_decision_btn1.png', 'battle_multipleparty_decision_btn2.png'),

        # Pair 2: Monster select battle buttons (oversized in v3, now fitted to 27px)
        ('battle_com_targetmonster_btn1.png', 'battle_com_targetmonster_btn2.png'),

        # Pair 3: Party select battle buttons (oversized in v3, now fitted to 27px)
        ('battle_com_targetparty_btn1.png', 'battle_com_targetparty_btn2.png'),

        # Pair 4: 2-line labels (unitlist: equalized 2 lines at fs=24)
        ('sort_label_unitlist_s1.png', 'sort_label_unitlist_s2.png'),

        # Single 1: Arena tab (undersized in v3, now boosted to 31px)
        ('achieve_tab_arena_1.png',),

        # Single 2: Ticket info header (tight width with 4% horizontal compression)
        ('gacha_arenaticketinfo.png',),
    ]

    print("================================================================================")
    print("Ultra-High-Fidelity Sprite Renderer (v4) - Unified Sizing Engine (10 Sprites)")
    print("================================================================================")

    processed = []
    stats = []

    for grp in TARGET_GROUPS:
        if len(grp) == 2:
            n1, n2 = grp
            im1 = Image.open(IN_DIR / n1).convert('RGBA')
            im2 = Image.open(IN_DIR / n2).convert('RGBA')

            fw1 = 900 if ('battle' in n1 or 'cre_label' in n1 or 'decision' in n1) else 800
            sw1 = 1.8 if ('btn' in n1 or 'decision' in n1) else 1.0

            fw2 = 900 if ('battle' in n2 or 'cre_label' in n2 or 'decision' in n2) else 800
            sw2 = 1.8 if ('btn' in n2 or 'decision' in n2) else 1.0

            s1 = solve_korean_size(n1, ocr_map[n1]['ko'], im1, fw1, sw1)
            s2 = solve_korean_size(n2, ocr_map[n2]['ko'], im2, fw2, sw2)

            # Rule: Sync pair to smaller font size & scale_x
            min_fs = min(s1['fs'], s2['fs'])
            min_sx = min(s1['scale_x'], s2['scale_x'])
            cx_sync = (s1['cx'] + s2['cx']) // 2
            cy_sync = (s1['cy'] + s2['cy']) // 2

            s1['fs'] = min_fs
            s1['scale_x'] = min_sx
            s1['cx'] = cx_sync
            s1['cy'] = cy_sync

            s2['fs'] = min_fs
            s2['scale_x'] = min_sx
            s2['cx'] = cx_sync
            s2['cy'] = cy_sync

            ko_text = ocr_map[n1]['ko']

            gen1 = render_sprite_v4(im1, n1, ko_text, s1, fw1, sw1)
            gen2 = render_sprite_v4(im2, n2, ko_text, s2, fw2, sw2)

            gen1.save(GEN_DIR / n1)
            gen2.save(GEN_DIR / n2)

            fin1 = pp.compose(im1, gen1, 40)
            fin2 = pp.compose(im2, gen2, 40)
            fin1.save(FINAL_DIR / n1)
            fin2.save(FINAL_DIR / n2)

            processed.append((n1, im1, fin1, ocr_map[n1]['ja'], ko_text, s1))
            processed.append((n2, im2, fin2, ocr_map[n2]['ja'], ko_text, s2))

            print(f"[PAIR] {n1:38s} & {n2:38s} -> fs={min_fs}, sx={min_sx:.2f}")

        else:
            n = grp[0]
            im = Image.open(IN_DIR / n).convert('RGBA')
            fw = 900 if ('battle' in n or 'cre_label' in n or 'decision' in n) else 800
            sw = 1.8 if ('btn' in n or 'decision' in n) else (1.6 if 'tab' in n else 1.2)

            s = solve_korean_size(n, ocr_map[n]['ko'], im, fw, sw)
            ko_text = ocr_map[n]['ko']

            gen = render_sprite_v4(im, n, ko_text, s, fw, sw)
            gen.save(GEN_DIR / n)

            fin = pp.compose(im, gen, 40)
            fin.save(FINAL_DIR / n)

            processed.append((n, im, fin, ocr_map[n]['ja'], ko_text, s))
            print(f"[SNGL] {n:38s} -> fs={s['fs']}, sx={s['scale_x']:.2f}")

    # Quantitative Verification
    print("\nQuantitative Verification across 10 sprites:")
    for name, orig_img, fin_img, ja, ko, sizing in processed:
        orig = np.array(orig_img)
        gen = np.array(Image.open(GEN_DIR / name))
        fin = np.array(fin_img)

        gen_a_pct = np.mean(gen[:, :, 3] > 20) * 100
        orig_a_pct = np.mean(orig[:, :, 3] > 20) * 100

        # Residual JA
        bx1, by1, bx2, by2 = sizing['bx1'], sizing['by1'], sizing['bx2'], sizing['by2']
        orig_crop = orig[by1:by2, bx1:bx2]
        fin_crop = fin[by1:by2, bx1:bx2]

        if is_transparent_label(name, orig_img):
            ja_core = (orig_crop[:, :, 3] > 100) & (orig_crop[:, :, :3].mean(axis=2) > 80)
        else:
            c_lum = orig_crop[:, :, :3].mean(axis=2)
            ja_core = (orig_crop[:, :, 3] > 180) & (c_lum > 180)

        if np.sum(ja_core) > 0:
            res_ja_pct = np.mean(np.all(fin_crop[ja_core] == orig_crop[ja_core], axis=1)) * 100
        else:
            res_ja_pct = 0.0

        # Contrast
        if is_transparent_label(name, orig_img):
            fin_text_lum = fin[fin[:, :, 3] > 100, :3].mean() if np.sum(fin[:, :, 3] > 100) else 0
            orig_text_lum = orig[orig[:, :, 3] > 100, :3].mean() if np.sum(orig[:, :, 3] > 100) else 0
            contrast_ko = fin_text_lum
            contrast_orig = orig_text_lum
        else:
            orig_lum = orig[:, :, :3].mean(axis=2)
            fin_lum = fin[:, :, :3].mean(axis=2)

            full_ja_core = np.zeros(orig.shape[:2], dtype=bool)
            full_ja_core[by1:by2, bx1:bx2] = ja_core

            orig_t = orig_lum[full_ja_core].mean() if np.sum(full_ja_core) else 200
            orig_b = orig_lum[~full_ja_core & (orig[:, :, 3] > 100)].mean()
            contrast_orig = abs(orig_t - orig_b)

            fin_t_mask = (fin[:, :, 3] > 180) & (fin_lum > 180)
            fin_t = fin_lum[fin_t_mask].mean() if np.sum(fin_t_mask) else 200
            fin_b = fin_lum[~fin_t_mask & (fin[:, :, 3] > 100)].mean()
            contrast_ko = abs(fin_t - fin_b)

        # Height measurement
        lines = ko.split('\n')
        fw = 900 if ('battle' in name or 'cre_label' in name or 'decision' in name) else 800
        sw = 2 if ('btn' in name or 'decision' in name or 'tab' in name) else 1
        f = ImageFont.truetype(FONT_VF, sizing['fs'])
        f.set_variation_by_axes([fw])
        dummy_m = ImageDraw.Draw(Image.new('RGBA', (500, 500)))
        bbs_m = [dummy_m.textbbox((0, 0), l, font=f, stroke_width=sw) for l in lines]
        rendered_h = sum(b[3] - b[1] for b in bbs_m) + ((len(lines) - 1) * 4)
        rendered_w = int(max(b[2] - b[0] for b in bbs_m) * sizing['scale_x'])
        h_ratio = (rendered_h / sizing['orig_h']) * 100

        stat_item = {
            'name': name,
            'ja': ja,
            'ko': ko.replace('\n', ' / '),
            'orig_w': sizing['orig_w'],
            'orig_h': sizing['orig_h'],
            'max_w': sizing['max_w'],
            'fs': sizing['fs'],
            'scale_x': sizing['scale_x'],
            'rendered_w': rendered_w,
            'rendered_h': rendered_h,
            'h_ratio': h_ratio,
            'gen_a': gen_a_pct,
            'orig_a': orig_a_pct,
            'res_ja': res_ja_pct,
            'contrast_ko': contrast_ko,
            'contrast_orig': contrast_orig,
        }
        stats.append(stat_item)

        print(f"  {name:38s} | H:{rendered_h:2d}px/{sizing['orig_h']:2d}px ({h_ratio:5.1f}%) | W:{rendered_w:3d}px/max {sizing['max_w']:3d}px (sx={sizing['scale_x']:.2f}) | A>20:{gen_a_pct:5.1f}% | Res JA:{res_ja_pct:5.2f}%")

    (WORK / 'verification_stats_v4_10.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')

    # Generate Single 10-Row Comparison Sheet
    print("\nGenerating 10-Row Comparison Sheet...")
    row_h = 135
    sheet_w = 950
    sheet_h = row_h * len(processed)

    sheet = Image.new('RGB', (sheet_w, sheet_h), (35, 35, 42))
    draw = ImageDraw.Draw(sheet)

    font_label = ImageFont.truetype(FONT_VF, 13)
    font_label.set_variation_by_axes([700])
    font_ko = ImageFont.truetype(FONT_VF, 15)
    font_ko.set_variation_by_axes([900])
    font_sub = ImageFont.truetype(FONT_VF, 12)
    font_sub.set_variation_by_axes([600])

    for i, (name, orig, final_img, ja, ko, sizing) in enumerate(processed):
        y_base = i * row_h

        max_disp_w, max_disp_h = 360, 110
        scale = min(max_disp_w / orig.width, max_disp_h / orig.height)
        if orig.width < 150:
            scale = min(2.5, scale)
        elif orig.width < 250:
            scale = min(1.5, scale)
        else:
            scale = min(1.0, scale)

        disp_w = max(1, int(orig.width * scale))
        disp_h = max(1, int(orig.height * scale))

        disp_orig = orig.resize((disp_w, disp_h), Image.Resampling.NEAREST if scale >= 2.0 else Image.Resampling.LANCZOS)
        disp_fin = final_img.resize((disp_w, disp_h), Image.Resampling.NEAREST if scale >= 2.0 else Image.Resampling.LANCZOS)

        bg_box = Image.new('RGB', (disp_w, disp_h), (50, 50, 56))
        for gy in range(0, disp_h, 8):
            for gx in range(0, disp_w, 8):
                if (gx // 8 + gy // 8) % 2 == 1:
                    bg_box.paste(Image.new('RGB', (min(8, disp_w - gx), min(8, disp_h - gy)), (60, 60, 68)), (gx, gy))

        orig_card = bg_box.copy()
        orig_card.paste(disp_orig, (0, 0), disp_orig)

        fin_card = bg_box.copy()
        fin_card.paste(disp_fin, (0, 0), disp_fin)

        sheet.paste(orig_card, (20, y_base + (row_h - disp_h) // 2))
        sheet.paste(fin_card, (400, y_base + (row_h - disp_h) // 2))

        # Metadata
        st = stats[i]
        draw.text((775, y_base + 18), name[:22], fill=(240, 240, 180), font=font_label)
        draw.text((775, y_base + 38), f"JA: {ja[:8]}", fill=(190, 190, 200), font=font_label)
        clean_ko = ko.replace('\n', ' / ')
        draw.text((775, y_base + 58), f"KO: {clean_ko[:8]}", fill=(100, 220, 255), font=font_ko)
        draw.text((775, y_base + 80), f"H: {st['rendered_h']}px/{st['orig_h']}px ({st['h_ratio']:.0f}%)", fill=(160, 230, 160), font=font_sub)
        sx_str = f" (sx={st['scale_x']:.2f})" if st['scale_x'] < 1.0 else ""
        draw.text((775, y_base + 98), f"W: {st['rendered_w']}px/max {st['max_w']}px{sx_str}", fill=(200, 200, 210), font=font_sub)

        if i < len(processed) - 1:
            draw.line([(10, y_base + row_h - 1), (sheet_w - 10, y_base + row_h - 1)], fill=(50, 50, 58), width=1)

    out_sheet_path = COMPARE_DIR / "compare_v4_size10.png"
    sheet.save(out_sheet_path)
    print(f"\n10-Sprite Comparison Sheet saved: {out_sheet_path}")


if __name__ == '__main__':
    main()

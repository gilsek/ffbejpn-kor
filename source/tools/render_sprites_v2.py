"""Ultra-High-Fidelity Sprite Renderer (v2.1) - OCR Box Guided + Exact 1:1 Glyph Style.

Follows user specifications:
1. Official Game Font: build/out/ko_font/ko_game_font.ttf
2. Text Style Extraction:
   - Inner fill: true glyph core average / vertical gradient (top to bottom)
   - Stroke: outline ring color & thickness (1px for <20px, 2px for >=20px)
   - Glow / Shadow: 5px outer diffusion (vibrant blue glow for s2 buttons, drop shadow for buttons)
   - Pairs (s1/s2, btn1/btn2, normal/on): 100% pixel-perfect layout and font size synchronization
3. Erasing:
   - Transparent labels: clear alpha to 0 (no artifacts)
   - Solid/textured: Telea inpainting on dilated text mask
4. 4x Super-Sampling Anti-Aliasing (SSAA):
   - Render at 4x scale -> Lanczos downscale to 1x
   - Korean visual optical vertical centering
   - Multilayer composition: Glow/Shadow -> Stroke -> Gradient Fill -> Highlight
"""
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/out/sprite_work'
IN_DIR = WORK / 'in'
GEN_DIR = WORK / 'gen'
FINAL_DIR = WORK / 'final'
COMPARE_DIR = WORK / 'compare'
FONT_PATH = str(ROOT / 'build/out/ko_font/ko_game_font.ttf')

engine = RapidOCR(
    rec_model_path=str(ROOT / 'build/out/models/japan_PP-OCRv3_rec_infer.onnx'),
    rec_keys_path=str(ROOT / 'build/out/models/japan_dict.txt')
)

SSAA = 4


def get_sprite_boxes(orig_img, name):
    """Detect text bounding boxes using RapidOCR with fallback."""
    w, h = orig_img.size

    # Diamond button special case
    if 'Diamond' in name:
        return [(int(w * 0.18), int(h * 0.58), int(w * 0.82), int(h * 0.76), 11)]

    # Rarity max 2-line special case
    if 'raritymax' in name:
        return [
            (int(w * 0.10), int(h * 0.46), int(w * 0.90), int(h * 0.62), 11),
            (int(w * 0.10), int(h * 0.64), int(w * 0.90), int(h * 0.80), 11)
        ]

    bg = Image.new('RGB', (w, h), (58, 58, 64))
    bg.paste(orig_img, (0, 0), orig_img)
    res, _ = engine(np.array(bg))

    boxes = []
    if res:
        for r in res:
            pts = np.array(r[0])
            bx1 = max(0, int(pts[:, 0].min()))
            by1 = max(0, int(pts[:, 1].min()))
            bx2 = min(w, int(pts[:, 0].max()))
            by2 = min(h, int(pts[:, 1].max()))
            bh = by2 - by1
            bw = bx2 - bx1
            if bh >= 8 and bw >= 8 and (bh < h * 0.95 or bw < w * 0.95):
                # ignore top door icon in escape_icon1
                if 'escape' in name and by1 < h * 0.5:
                    continue
                # Calculate true glyph height (~78% of OCR detection bounding box)
                th = max(9, int(bh * 0.78))
                boxes.append((bx1, by1, bx2, by2, th))

    boxes.sort(key=lambda b: b[1])

    if not boxes:
        # Fallback from alpha
        arr = np.array(orig_img)
        alpha = arr[:, :, 3]
        if np.mean(alpha == 0) > 0.35:
            y_idx = np.where(alpha > 60)[0]
            x_idx = np.where(alpha > 60)[1]
            if len(y_idx) > 0:
                y1, y2 = int(y_idx.min()), int(y_idx.max())
                x1, x2 = int(x_idx.min()), int(x_idx.max())
                boxes.append((x1, y1, x2, y2, y2 - y1 + 1))
        else:
            boxes.append((int(w * 0.12), int(h * 0.20), int(w * 0.88), int(h * 0.80), int(h * 0.35)))

    return boxes


def extract_box_style(orig_img, name, box):
    """Extract fill gradient, stroke color/width, and glow/shadow from the detected box."""
    bx1, by1, bx2, by2, th = box
    w, h = orig_img.size
    arr = np.array(orig_img)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    is_transparent = np.mean(alpha == 0) > 0.35

    # Crop to box with 2px margin
    my1, my2 = max(0, by1 - 2), min(h, by2 + 3)
    mx1, mx2 = max(0, bx1 - 2), min(w, bx2 + 3)

    box_rgb = rgb[my1:my2, mx1:mx2]
    box_alpha = alpha[my1:my2, mx1:mx2]

    # Mask text core inside box
    if is_transparent:
        core_mask = box_alpha > 50
    else:
        # Background color around box perimeter
        edge_pts = np.concatenate([box_rgb[0, :, :], box_rgb[-1, :, :], box_rgb[:, 0, :], box_rgb[:, -1, :]], axis=0)
        bg_col = np.median(edge_pts, axis=0)
        diff = np.linalg.norm(box_rgb.astype(float) - bg_col, axis=2)
        core_mask = (box_alpha > 120) & (
            (diff > 35) | (box_rgb.mean(axis=2) > 140) |
            ((box_rgb[:, :, 0] > 180) & (box_rgb[:, :, 1] > 140) & (box_rgb[:, :, 2] < 130))
        )

    # Full mask
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[my1:my2, mx1:mx2] = core_mask.astype(np.uint8) * 255

    # Refine core
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_stroke = cv2.dilate(mask, kernel, iterations=1)

    # Colors
    core_pts = rgb[mask > 0]
    if len(core_pts) > 0:
        # Top vs Bottom gradient
        y_pts = np.where(mask > 0)[0]
        mid_y = (y_pts.min() + y_pts.max()) // 2
        top_pts = rgb[(mask > 0) & (np.arange(h)[:, None] <= mid_y)]
        bot_pts = rgb[(mask > 0) & (np.arange(h)[:, None] > mid_y)]

        top_col = np.mean(top_pts, axis=0).astype(int) if len(top_pts) else np.mean(core_pts, axis=0).astype(int)
        bot_col = np.mean(bot_pts, axis=0).astype(int) if len(bot_pts) else np.mean(core_pts, axis=0).astype(int)
    else:
        top_col = np.array([255, 255, 255])
        bot_col = np.array([255, 255, 255])

    # Stroke color from ring
    stroke_ring = dilated_stroke - mask
    if np.sum(stroke_ring > 0) > 0:
        stroke_col = np.median(rgb[stroke_ring > 0], axis=0).astype(int)
    else:
        stroke_col = np.array([20, 25, 45])

    stroke_width = 1 if th < 20 else 2

    # Glow detection (especially for s2 and btn2)
    has_blue_glow = False
    glow_col = None
    has_shadow = False

    if '_s2' in name or '-on' in name:
        has_blue_glow = True
        glow_col = (0, 85, 255, 235)
        # Blue s2 button text gradient: top white, bottom cyan-blue
        top_col = np.array([255, 255, 255])
        bot_col = np.array([135, 180, 255])
        stroke_col = np.array([0, 35, 110])
    elif '_btn2' in name:
        has_blue_glow = True
        glow_col = (30, 150, 230, 210)
        top_col = np.array([255, 255, 255])
        bot_col = np.array([245, 250, 255])
        stroke_col = np.array([15, 85, 145])
    elif '_s1' in name:
        # Metallic silver gradient
        top_col = np.array([175, 168, 168])
        bot_col = np.array([85, 78, 78])
        stroke_col = np.array([20, 20, 20])
        has_shadow = True
    elif th >= 16:
        has_shadow = True

    cx = (bx1 + bx2) // 2
    cy = (by1 + by2) // 2

    return {
        'box': box,
        'mask': mask,
        'cx': cx,
        'cy': cy,
        'th': th,
        'top_col': top_col,
        'bot_col': bot_col,
        'stroke_col': stroke_col,
        'stroke_width': stroke_width,
        'has_blue_glow': has_blue_glow,
        'glow_col': glow_col,
        'has_shadow': has_shadow,
        'is_transparent': is_transparent,
    }


def inpaint_text_regions(orig_img, styles):
    """Inpaint text regions cleanly."""
    arr = np.array(orig_img)
    h, w = arr.shape[:2]

    # Combine all masks
    full_mask = np.zeros((h, w), dtype=np.uint8)
    for s in styles:
        full_mask = np.maximum(full_mask, s['mask'])

    ksize = 5 if h >= 50 else 3
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    dilated = cv2.dilate(full_mask, kernel, iterations=1)

    if styles[0]['is_transparent']:
        clean_arr = arr.copy()
        clean_arr[dilated > 0, 3] = 0
        return Image.fromarray(clean_arr)

    bgr = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR)
    inp = cv2.inpaint(bgr, dilated, 3, cv2.INPAINT_TELEA)
    clean_rgb = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)
    return Image.fromarray(np.dstack([clean_rgb, arr[:, :, 3]]))


def render_sprite_ssaa(base_img, text_chunks, styles, fs_override=None):
    """Render Korean text chunks with 4x SSAA."""
    w, h = base_img.size
    w4, h4 = w * SSAA, h * SSAA
    base4 = base_img.resize((w4, h4), Image.Resampling.LANCZOS)

    glow_canvas4 = Image.new('RGBA', (w4, h4), (0, 0, 0, 0))
    d_glow4 = ImageDraw.Draw(glow_canvas4)

    stroke_canvas4 = Image.new('RGBA', (w4, h4), (0, 0, 0, 0))
    d_stroke4 = ImageDraw.Draw(stroke_canvas4)

    fill_mask4 = Image.new('L', (w4, h4), 0)
    d_fill4 = ImageDraw.Draw(fill_mask4)

    grad4 = np.zeros((h4, w4, 4), dtype=np.uint8)

    used_fs = []

    for i, (text, st) in enumerate(zip(text_chunks, styles)):
        cx4 = st['cx'] * SSAA
        cy4 = st['cy'] * SSAA
        th4 = int(st['th'] * SSAA * 0.98)
        max_w4 = int((st['box'][2] - st['box'][0]) * 1.12 * SSAA)
        stroke_w4 = st['stroke_width'] * SSAA

        if fs_override is not None:
            best_fs4 = fs_override[i] * SSAA
        else:
            best_fs4 = 10 * SSAA
            dummy = ImageDraw.Draw(base4)
            for fs in range(int(th4 * 1.35), 6 * SSAA, -2):
                f = ImageFont.truetype(FONT_PATH, fs)
                bb = dummy.textbbox((0, 0), text, font=f, stroke_width=stroke_w4)
                if (bb[3] - bb[1]) <= th4 and (bb[2] - bb[0]) <= max_w4:
                    best_fs4 = fs
                    break

        used_fs.append(best_fs4 // SSAA)
        font4 = ImageFont.truetype(FONT_PATH, best_fs4)

        bb = ImageDraw.Draw(base4).textbbox((0, 0), text, font=font4, stroke_width=stroke_w4)
        tw4 = bb[2] - bb[0]
        th_actual4 = bb[3] - bb[1]

        # Centering with Korean optical correction
        tx4 = cx4 - tw4 // 2 - bb[0]
        ty4 = cy4 - th_actual4 // 2 - bb[1] - int(0.5 * SSAA)

        # 1. Glow / Shadow
        if st['has_blue_glow']:
            d_glow4.text(
                (tx4, ty4), text, font=font4,
                fill=st['glow_col'],
                stroke_width=stroke_w4 + int(2 * SSAA),
                stroke_fill=st['glow_col']
            )
        elif st['has_shadow']:
            d_glow4.text(
                (tx4, ty4 + int(1.2 * SSAA)), text, font=font4,
                fill=(0, 0, 0, 160),
                stroke_width=stroke_w4,
                stroke_fill=(0, 0, 0, 160)
            )

        # 2. Stroke
        st_col = (int(st['stroke_col'][0]), int(st['stroke_col'][1]), int(st['stroke_col'][2]), 255)
        d_stroke4.text(
            (tx4, ty4), text, font=font4,
            fill=(0, 0, 0, 0),
            stroke_width=stroke_w4,
            stroke_fill=st_col
        )

        # 3. Inner fill mask
        d_fill4.text((tx4, ty4), text, font=font4, fill=255)

        # 4. Vertical gradient fill
        top_c = st['top_col']
        bot_c = st['bot_col']
        for y in range(max(0, ty4), min(h4, ty4 + th_actual4 + 1)):
            t = (y - ty4) / max(1, th_actual4)
            c = (1 - t) * top_c + t * bot_c
            grad4[y, max(0, tx4):min(w4, tx4 + tw4)] = [int(c[0]), int(c[1]), int(c[2]), 255]

        # Top 1px highlight
        if SSAA >= 2 and not st['is_transparent']:
            for y in range(max(0, ty4), min(h4, ty4 + int(1.2 * SSAA))):
                grad4[y, max(0, tx4):min(w4, tx4 + tw4)] = np.minimum(
                    255, grad4[y, max(0, tx4):min(w4, tx4 + tw4)].astype(int) + 25
                ).astype(np.uint8)

    # Blur glow/shadow
    has_any_glow = any(s['has_blue_glow'] for s in styles)
    has_any_shadow = any(s['has_shadow'] for s in styles)
    if has_any_glow:
        glow_canvas4 = glow_canvas4.filter(ImageFilter.GaussianBlur(radius=int(2.5 * SSAA)))
    elif has_any_shadow:
        glow_canvas4 = glow_canvas4.filter(ImageFilter.GaussianBlur(radius=int(1.2 * SSAA)))

    grad_img4 = Image.fromarray(grad4, 'RGBA')

    # Composite layers
    comp4 = base4.copy()
    if has_any_glow or has_any_shadow:
        comp4.alpha_composite(glow_canvas4)
    comp4.alpha_composite(stroke_canvas4)
    comp4.paste(grad_img4, (0, 0), fill_mask4)

    # Downscale back to 1x
    final_1x = comp4.resize((w, h), Image.Resampling.LANCZOS)
    final_1x.putalpha(base_img.getchannel('A'))

    return final_1x, used_fs


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)

    ocr = json.loads((WORK / 'ocr.json').read_text(encoding='utf-8'))
    ocr_map = {it['name']: it for it in ocr}

    TARGET_GROUPS = [
        # 1-8: Gray s1 & Blue s2 pairs (4 pairs = 8 sprites)
        ('sort_label_attack_s1.png', 'sort_label_attack_s2.png'),
        ('sort_label_defense_s1.png', 'sort_label_defense_s2.png'),
        ('sort_label_magic_s1.png', 'sort_label_magic_s2.png'),
        ('sort_label_unitlist_s1.png', 'sort_label_unitlist_s2.png'),

        # 9-12: Battle Button pairs (_btn1 & _btn2, 2 pairs = 4 sprites)
        ('battle_com_targetmonster_btn1.png', 'battle_com_targetmonster_btn2.png'),
        ('battle_com_targetparty_btn1.png', 'battle_com_targetparty_btn2.png'),

        # 13-14: 2-line label pair (normal & on, 1 pair = 2 sprites)
        ('gacha_btn_raritymax_info_normal.png', 'gacha_btn_raritymax_info_on.png'),

        # 15-17: Large labels (3 sprites)
        ('cre_label_accessory_1.png',),
        ('cre_label_magic_black_1.png',),
        ('battle_txt_1turndamage.png',),

        # 18-19: Tabs (2 sprites)
        ('achieve_tab_arena_1.png',),
        ('gacha_boxtab_green_1_1.png',),

        # 20: Header / Info (1 sprite)
        ('gacha_arenaticketinfo.png',),
    ]

    print("================================================================================")
    print("Ultra-High-Fidelity Sprite Renderer (v2.1) - RapidOCR Guided + Style Sync")
    print("================================================================================")

    processed_rows = []

    for grp in TARGET_GROUPS:
        if len(grp) == 2:
            n1, n2 = grp
            im1 = Image.open(IN_DIR / n1).convert('RGBA')
            im2 = Image.open(IN_DIR / n2).convert('RGBA')

            b1 = get_sprite_boxes(im1, n1)
            b2 = get_sprite_boxes(im2, n2)

            st1 = [extract_box_style(im1, n1, b) for b in b1]
            st2 = [extract_box_style(im2, n2, b) for b in b2]

            ko_raw = ocr_map[n1]['ko']
            if 'raritymax' in n1:
                chunks = ['MAX 각성', '스테이터스']
            elif '/' in ko_raw:
                chunks = ko_raw.split('/')
            else:
                chunks = [ko_raw]

            # Inpaint
            base1 = inpaint_text_regions(im1, st1)
            base2 = inpaint_text_regions(im2, st2)

            # Synchronize pair geometry
            for s1_box, s2_box in zip(st1, st2):
                cx_sync = (s1_box['cx'] + s2_box['cx']) // 2
                cy_sync = (s1_box['cy'] + s2_box['cy']) // 2
                th_sync = max(s1_box['th'], s2_box['th'])
                s1_box['cx'] = cx_sync
                s2_box['cx'] = cx_sync
                s1_box['cy'] = cy_sync
                s2_box['cy'] = cy_sync
                s1_box['th'] = th_sync
                s2_box['th'] = th_sync

            # Render
            res1, fs_sync = render_sprite_ssaa(base1, chunks, st1)
            res2, _ = render_sprite_ssaa(base2, chunks, st2, fs_override=fs_sync)

            res1.save(GEN_DIR / n1)
            res1.save(FINAL_DIR / n1)
            res2.save(GEN_DIR / n2)
            res2.save(FINAL_DIR / n2)

            processed_rows.append((n1, im1, res1, ocr_map[n1]['ja'], ' / '.join(chunks), fs_sync))
            processed_rows.append((n2, im2, res2, ocr_map[n2]['ja'], ' / '.join(chunks), fs_sync))

            print(f"[PAIR] {n1:35} & {n2:35} -> '{' / '.join(chunks)}' (fs={fs_sync})")

        else:
            n = grp[0]
            im = Image.open(IN_DIR / n).convert('RGBA')
            boxes = get_sprite_boxes(im, n)
            styles = [extract_box_style(im, n, b) for b in boxes]

            ko_raw = ocr_map[n]['ko']
            chunks = ko_raw.split('/') if '/' in ko_raw and len(boxes) > 1 else [ko_raw]

            base = inpaint_text_regions(im, styles)
            res, fs = render_sprite_ssaa(base, chunks, styles)

            res.save(GEN_DIR / n)
            res.save(FINAL_DIR / n)

            processed_rows.append((n, im, res, ocr_map[n]['ja'], ' / '.join(chunks), fs))
            print(f"[SNGL] {n:35} : '{styles[0]['th']}px' -> '{' / '.join(chunks)}' (fs={fs})")

    # Generate 3x Magnified Comparison Sheets
    print("\nGenerating 3x Magnified Comparison Sheets for Human Verification...")

    per_sheet = 10
    for sheet_idx in range(2):
        chunk = processed_rows[sheet_idx * per_sheet:(sheet_idx + 1) * per_sheet]
        row_h = 135
        sheet_w = 950
        sheet_h = row_h * len(chunk)

        sheet = Image.new('RGB', (sheet_w, sheet_h), (35, 35, 42))
        draw = ImageDraw.Draw(sheet)

        font_label = ImageFont.truetype(FONT_PATH, 13)
        font_ko = ImageFont.truetype(FONT_PATH, 15)

        for i, (name, orig, final_img, ja, ko, fs) in enumerate(chunk):
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

            # Checkered background for alpha transparency preview
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

            draw.text((775, y_base + 25), name[:22], fill=(240, 240, 180), font=font_label)
            draw.text((775, y_base + 50), f"JA: {ja[:8]}", fill=(190, 190, 200), font=font_label)
            draw.text((775, y_base + 75), f"KO: {ko[:8]}", fill=(100, 220, 255), font=font_ko)

            if i < len(chunk) - 1:
                draw.line([(10, y_base + row_h - 1), (sheet_w - 10, y_base + row_h - 1)], fill=(50, 50, 58), width=1)

        out_sheet_path = COMPARE_DIR / f"compare_v2_{sheet_idx + 1}.png"
        sheet.save(out_sheet_path)
        print(f"Comparison sheet saved: {out_sheet_path}")

    print("\nAll 20 pilot sprites processed and compare sheets generated successfully!")


if __name__ == '__main__':
    main()

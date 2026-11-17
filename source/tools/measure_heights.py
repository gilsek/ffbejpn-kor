import json
from pathlib import Path
from PIL import Image, ImageFont, ImageDraw
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
pilot = json.load(open(ROOT / 'build/out/sprite_work/pilot30.json', encoding='utf-8'))
font_path = str(ROOT / 'build/out/ko_font/ko_game_font.ttf')

print(f"{'Filename':38} | {'Img H':5} | {'Orig Text H':11} | {'Cur Text H':10} | {'Cur Font Size':13} | {'Oversize'}")
print("-" * 88)

results = []
for p in pilot:
    fn = p['name']
    orig = Image.open(ROOT / f'build/out/sprite_work/in/{fn}').convert('RGBA')
    w, h = orig.size
    arr = np.array(orig)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    # Mask text in original
    bright = (alpha > 150) & ((rgb[:, :, 0] > 160) & (rgb[:, :, 1] > 160) & (rgb[:, :, 2] > 160))
    # Exclude extreme borders
    center = np.zeros((h, w), dtype=bool)
    center[int(h*0.08):int(h*0.92), int(w*0.08):int(w*0.92)] = True
    cand = bright & center
    ys, xs = np.where(cand)
    orig_th = (ys.max() - ys.min() + 1) if len(ys) > 10 else int(h * 0.4)

    # What render_sprites.py currently calculated:
    avail_w = max(int(w * 0.7), int(w * 0.6))
    avail_h = max(orig_th, int(h * 0.6))
    max_fs = max(10, min(int(avail_h * 0.95), int(h * 0.65)))

    draw = ImageDraw.Draw(orig)
    best_fs = 10
    for fs in range(max_fs, 8, -1):
        f = ImageFont.truetype(font_path, fs)
        bbox = draw.textbbox((0, 0), p['ko'], font=f)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        if bw <= int(w * 0.85) and bh <= avail_h:
            best_fs = fs
            break

    f = ImageFont.truetype(font_path, best_fs)
    bbox = draw.textbbox((0, 0), p['ko'], font=f)
    cur_th = bbox[3] - bbox[1]
    pct = (cur_th / orig_th * 100.0) if orig_th > 0 else 100.0

    print(f"{fn:38} | {h:5d} | {orig_th:11d}px | {cur_th:10d}px | fs={best_fs:2d} ({best_fs}pt)    | {pct:.0f}%")
    results.append((orig_th, cur_th, best_fs))

avg_orig = sum(r[0] for r in results) / len(results)
avg_cur = sum(r[1] for r in results) / len(results)
print("-" * 88)
print(f"Average: Original Text Height = {avg_orig:.1f}px | Current Rendered Height = {avg_cur:.1f}px (about {avg_cur/avg_orig*100:.0f}% of original)")

"""소환 화면 3개 탭(유료/무료/교환소 자리)을 'FFBE' / 'FF SERIES' / 'COLLAB'으로 다시 그린다.

입력: build/out/jp_offline/gacha_jp/stepup_tab/en_gacha_tab_{pay,free,exchange}_{1,2}.png
출력: translations/ui-ko/sprites/labels/gacha_tab_{pay,free,exchange}_{1,2}.png + labels_manifest.json 갱신.
배경은 글자 영역 밖 좌우 픽셀로 행마다 2차 곡선을 맞춰 복원하고, 글자는 Bahnschrift Bold로 그린다.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / 'translations/ui-ko/sprites/labels'
MANIFEST = ROOT / 'translations/ui-ko/sprites/labels_manifest.json'
SOURCE = ROOT / 'build/out/jp_offline/gacha_jp/stepup_tab'
FONT = 'C:/Windows/Fonts/bahnschrift.ttf'
VARIATION = 'Bold SemiCondensed'
FONT_PX = 22
BOLD = 1          # 슈퍼샘플 픽셀 단위 가짜 굵기(MaxFilter 크기, 홀수; 1 = 없음)
SS = 4
# frame -> (text, x0, x1, y0, y1, baseline y of capitals' bottom)
FRAMES = {
    'gacha_tab_pay_1.png': ('FFBE', 24, 196, 23, 50, 44),
    'gacha_tab_pay_2.png': ('FFBE', 24, 196, 26, 52, 47),
    'gacha_tab_free_1.png': ('FF SERIES', 24, 196, 23, 50, 44),
    'gacha_tab_free_2.png': ('FF SERIES', 24, 196, 26, 52, 47),
    'gacha_tab_exchange_1.png': ('COLLAB', 24, 196, 23, 50, 44),
    'gacha_tab_exchange_2.png': ('COLLAB', 24, 196, 26, 52, 47),
}
FILL_TOP = (255, 255, 255)
FILL_BOTTOM = (205, 214, 211)
OUTLINE = (0, 38, 40)


def erase(a, x0, x1, y0, y1):
    out = a.copy()
    xs_l = np.arange(8, x0)
    xs_r = np.arange(x1, 212)
    xs = np.concatenate([xs_l, xs_r])
    for y in range(y0, y1):
        for c in range(3):
            coef = np.polyfit(xs, a[y, xs, c], 2)
            out[y, x0:x1, c] = np.clip(np.polyval(coef, np.arange(x0, x1)), 0, 255)
    return out


def text_layer(size, baseline, text):
    w, h = size
    font = ImageFont.truetype(FONT, FONT_PX * SS)
    if VARIATION:
        font.set_variation_by_name(VARIATION)
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font, anchor='ls')
    x = (w * SS - (r - l)) // 2 - l
    y = baseline * SS
    mask = Image.new('L', (w * SS, h * SS), 0)
    ImageDraw.Draw(mask).text((x, y), text, font=font, fill=255, anchor='ls')
    if BOLD > 1:
        mask = mask.filter(ImageFilter.MaxFilter(BOLD))
    outline = mask.filter(ImageFilter.MaxFilter(2 * SS + 1))
    grad = Image.new('RGB', (w * SS, h * SS))
    cap_top = (baseline - 15) * SS
    gd = ImageDraw.Draw(grad)
    for yy in range(h * SS):
        t_ = min(1.0, max(0.0, (yy - cap_top - 9 * SS) / (6 * SS)))
        col = tuple(int(FILL_TOP[i] + (FILL_BOTTOM[i] - FILL_TOP[i]) * t_) for i in range(3))
        gd.line([(0, yy), (w * SS, yy)], fill=col)
    layer = Image.new('RGBA', (w * SS, h * SS), OUTLINE + (0,))
    layer.putalpha(outline)
    fill = grad.convert('RGBA')
    fill.putalpha(mask)
    layer = Image.alpha_composite(layer, fill)
    return layer.resize((w, h), Image.LANCZOS), (r - l) // SS


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    for name, (text, x0, x1, y0, y1, base) in FRAMES.items():
        path = LABELS / name
        im = Image.open(SOURCE / f'en_{name}').convert('RGBA')
        a = np.array(im).astype(float)
        bg = Image.fromarray(erase(a, x0, x1, y0, y1).astype('uint8'), 'RGBA')
        layer, width = text_layer(im.size, base, text)
        out = Image.alpha_composite(bg, layer)
        out.save(path)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[name] = {'translation': text, 'sha256': sha,
                          'source': f"영문판 탭 배경에 글자를 지우고 Bahnschrift Bold '{text}'로 다시 그림 "
                                    "(build/make_stepup_tab_label.py, 2026-11-16 3탭 분류 전환)"}
        print(name, '->', text, 'width', width)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

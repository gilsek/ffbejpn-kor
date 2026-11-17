"""1단계: 일본어 지우기(제미나이) -> 한글 폰트 렌더. 글자 크기는 그룹별로 통일."""
import sys, io, base64, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path.home() / '.claude/skills/game-image-text-translate/scripts'))
from _common import *
from PIL import ImageDraw, ImageFont
FONT = str(Path('../../ko_font/ko_game_font.ttf').resolve())
DARK = ((255, 255, 255), (30, 30, 40)); BAN = ((255, 255, 255), (20, 70, 140))
# name: (group, [(ja, ko, y0frac, y1frac)], style)
B = {
 'home_icon_news.png': ('icon', [('お知らせ', '공지', .55, 1)], DARK),
 'home_submenu_mail_off.png': ('icon', [('メール', '메일', .6, 1)], DARK),
 'home_submenu_mission_off.png': ('icon', [('ミッション', '미션', .6, 1)], DARK),
 'mypage_icon_mission3.png': ('icon', [('ミッション', '미션', .6, 1)], DARK),
 'mypage_icon_news3.png': ('icon', [('お知らせ', '공지', .6, 1)], DARK),
 'homeBanner_01_blank.png': ('banner', [('アリーナ', '아레나', .72, 1)], BAN),
 'homeBanner_03_blank.png': ('banner', [('次元の狭間', '차원의 틈', .72, 1)], BAN),
 'homeBanner_04_blank.png': ('banner', [('武具強化', '무기 강화', .72, 1)], BAN),
 'mypage_world1.png': ('plate', [('ワールド', '월드', .75, 1)], DARK),
 'mypage_world3.png': ('card', [('ストーリー', '스토리', 0, .25), ('ワールド', '월드', .7, 1)], DARK),
}
def erase(name, texts):
    dst = Path('er') / name
    if dst.exists(): return
    s = Image.open(Path('src') / name).convert('RGBA')
    jp = ' and '.join(f"'{t[0]}'" for t in texts)
    p = (f"Edit this game UI image. Remove the Japanese text {jp} completely and restore what is behind it (background, glow, icon parts). "
         "Do not add any new text. Keep everything else exactly the same: shape, colors, size, position. Output only the edited image.")
    for _ in range(3):
        try:
            m = chat(IMG_MODEL, p, on_dark(s)); u = m['images'][0]['image_url']['url']; break
        except Exception as e: err = e
    else: raise err
    g = Image.open(io.BytesIO(base64.b64decode(u.split(',', 1)[1]))).convert('RGB').resize(s.size, Image.LANCZOS)
    oa = np.array(s); a = oa[..., 3:4]
    Image.fromarray(np.concatenate([np.where(a >= 200, np.array(g), oa[..., :3]), a], 2).astype('uint8'), 'RGBA').save(dst)
def boxes(name, texts):
    o = np.array(Image.open(Path('src') / name).convert('RGBA')); e = np.array(Image.open(Path('er') / name).convert('RGBA'))
    D = np.abs(o[..., :3].astype(int) - e[..., :3].astype(int)).sum(2) * (o[..., 3] > 200); res = []
    for ja, ko, f0, f1 in texts:
        d = D.copy(); d[: int(o.shape[0] * f0)] = 0; d[int(o.shape[0] * f1):] = 0
        ys, xs = np.where(d > 150); res.append((xs.min(), ys.min(), xs.max(), ys.max()))
    return res
def fit(ko, bw, bh):
    for size in range(48, 6, -1):
        f = ImageFont.truetype(FONT, size); l, t, r, b = f.getbbox(ko, stroke_width=2)
        if r - l <= bw + 4 and b - t <= bh + 8: return size
    return 7
for n, (g, t, s) in B.items(): erase(n, t)
allbox = {n: boxes(n, B[n][1]) for n in B}
sizes = {}
for n, (g, texts, s) in B.items():
    for i, (ja, ko, f0, f1) in enumerate(texts):
        x0, y0, x1, y1 = allbox[n][i]; key = (g, i)
        sizes[key] = min(sizes.get(key, 99), fit(ko, x1 - x0 + 1, y1 - y0 + 1))
print('unified sizes', sizes)
json.dump({f'{k[0]}:{k[1]}': v for k, v in sizes.items()}, open('sizes.json', 'w'))
for n, (g, texts, st) in B.items():
    out = Image.open(Path('er') / n).convert('RGBA'); o = Image.open(Path('src') / n).convert('RGBA')
    for i, (ja, ko, f0, f1) in enumerate(texts):
        x0, y0, x1, y1 = allbox[n][i]; f = ImageFont.truetype(FONT, sizes[(g, i)]); l, t, r, b = f.getbbox(ko, stroke_width=2)
        layer = Image.new('RGBA', o.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(((x0 + x1) / 2 - (l + r) / 2, (y0 + y1) / 2 - (t + b) / 2), ko, font=f, fill=st[0] + (255,), stroke_width=2, stroke_fill=st[1] + (255,))
        out.alpha_composite(layer)
    out.save(Path('base') / n)
names = list(B); sheet = Image.new('RGB', (1300, 400), (40, 40, 50))
for row, dd in enumerate(('src', 'base')):
    x = 5
    for n in names:
        im = Image.open(Path(dd) / n).convert('RGBA'); sheet.paste(im, (x, 5 + row * 190), im); x += im.width + 8
sheet.save('base_compare.png')

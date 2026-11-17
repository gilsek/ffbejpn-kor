"""홈 하단 배너 4장: 제미나이로 일본어만 지우고 한글을 G마켓 산스 Bold(사용자 선택 2026-11-10)로 그린다.
homeBanner_02(「ワールド」, 다운로드 campaign_ui.cpk) + homeBanner_01/03/04_blank(resources.cpk home 아틀라스).
글자: 하늘색 채움 + 파란 외곽선 + 파란 광채, 원본 일본어 자리(띠 안 파란 글자, y>=85) 가운데, 4장 같은 크기."""
import sys, io, base64
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path.home() / '.claude/skills/game-image-text-translate/scripts'))
from _common import *
from PIL import ImageDraw, ImageFont, ImageFilter
H = Path(__file__).resolve().parent
FONT = str(Path.home() / 'AppData/Local/Microsoft/Windows/Fonts/GmarketSansBold.otf')
B = {'homeBanner_01_blank.png': ('アリーナ', '아레나'), 'homeBanner_02.png': ('ワールド', '월드'),
     'homeBanner_03_blank.png': ('次元の狭間', '차원의 틈'), 'homeBanner_04_blank.png': ('武具強化', '무기 강화')}
MAX, SW = 25, 2
def erase(n, ja):
    dst = H / 'er' / n
    if dst.exists(): return
    s = Image.open(H / 'src' / n).convert('RGBA')
    p = (f"Edit this game UI image. Remove the Japanese text '{ja}' completely and restore what is behind it (background, dark band, artwork). "
         "Do not add any new text. Keep everything else exactly the same: shape, colors, size, position. Output only the edited image.")
    for _ in range(3):
        try:
            m = chat(IMG_MODEL, p, on_dark(s)); u = m['images'][0]['image_url']['url']; break
        except Exception as e: err = e
    else: raise err
    g = Image.open(io.BytesIO(base64.b64decode(u.split(',', 1)[1]))).convert('RGB').resize(s.size, Image.LANCZOS)
    oa = np.array(s); a = oa[..., 3:4]
    Image.fromarray(np.concatenate([np.where(a >= 200, np.array(g), oa[..., :3]), a], 2).astype('uint8'), 'RGBA').save(dst)
def box(n):
    o = np.array(Image.open(H / 'src' / n).convert('RGB')).astype(int)
    mk = (o[..., 2] > 150) & (o[..., 2] - o[..., 0] > 60); mk[:85] = 0
    ys, xs = np.where(mk); return xs.min(), ys.min(), xs.max(), ys.max()
for n, (ja, ko) in B.items(): erase(n, ja)
boxes = {n: box(n) for n in B}
size = MAX
for n, (ja, ko) in B.items():                     # 가장 긴 글자가 자기 배너 폭(여백 6px) 안에 들어가는 크기로 통일
    w = Image.open(H / 'src' / n).width
    while size > 12:
        l, t, r, b = ImageFont.truetype(FONT, size).getbbox(ko, stroke_width=SW)
        if r - l <= w - 12: break
        size -= 1
print('size', size, boxes)
f = ImageFont.truetype(FONT, size)
for n, (ja, ko) in B.items():
    s = Image.open(H / 'src' / n).convert('RGBA'); e = Image.open(H / 'er' / n).convert('RGBA')
    x0, y0, x1, y1 = boxes[n]; l, t, r, b = f.getbbox(ko, stroke_width=SW)
    cx = min(max((x0 + x1) / 2, (r - l) / 2 + 6), s.width - (r - l) / 2 - 6)
    pos = (cx - (l + r) / 2, 100 - (t + b) / 2)        # 세로는 4장 같은 중심선(y=100)
    glow = Image.new('RGBA', s.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).text(pos, ko, font=f, fill=(70, 150, 255, 255), stroke_width=SW + 2, stroke_fill=(70, 150, 255, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(2))
    layer = Image.new('RGBA', s.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(pos, ko, font=f, fill=(205, 238, 255, 255), stroke_width=SW, stroke_fill=(20, 70, 140, 255))
    out = e.copy(); out.alpha_composite(glow); out.alpha_composite(layer); out.putalpha(s.getchannel('A'))
    out.save(H / 'final' / n)
S = 3; sheet = Image.new('RGB', (4 * (166 * S + 10) + 10, 2 * (112 * S + 10) + 10), (40, 40, 50))
for i, n in enumerate(B):
    for j, d in enumerate(('src', 'final')):
        im = Image.open(H / d / n).convert('RGBA'); im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
        sheet.paste(im, (10 + i * (166 * S + 10), 10 + j * (112 * S + 10)), im)
sheet.save(H / 'compare.png')

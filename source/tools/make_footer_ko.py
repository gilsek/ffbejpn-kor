"""홈 하단 6버튼(footer_btn_*_on/off, 영문판 영어 스프라이트): 제미나이로 영어 글자만 지우고 한글을 폰트로 그린다.
원본 영어 글자 모양에 맞춤: 둥근 고딕 볼드(G마켓 산스 Bold, 배너와 같은 폰트), 흰 채움, 얇은 어두운 외곽선,
오른쪽 아래 그림자; on 은 파란 광채를 더한다. 가운데 정렬, 영어 글자의 세로 중심, 6개 같은 크기."""
import sys, io, base64
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path.home() / '.claude/skills/game-image-text-translate/scripts'))
from _common import *
from PIL import ImageDraw, ImageFont, ImageFilter
H = Path(__file__).resolve().parent
FONT = str(Path.home() / 'AppData/Local/Microsoft/Windows/Fonts/GmarketSansBold.otf')
T = {'home': ('Home', '홈'), 'unit': ('Units', '유닛'), 'item': ('Items', '아이템'), 'shop': ('Shop', '상점'),
     'gacha': ('Summon', '소환'), 'friend': ('Friends', '친구')}
NAMES = [(f'footer_btn_{k}_{s}.png', en, ko, s) for k, (en, ko) in T.items() for s in ('off', 'on')]
def erase(n, en):
    dst = H / 'er' / n
    if dst.exists(): return
    s = Image.open(H / 'src' / n).convert('RGBA')
    p = (f"Edit this game UI icon. Remove the English word '{en}' at the bottom completely and restore the icon parts and background behind it. "
         "Do not add any new text. Keep everything else exactly the same: shape, colors, glow, size, position. Output only the edited image.")
    for _ in range(3):
        try:
            m = chat(IMG_MODEL, p, on_dark(s)); u = m['images'][0]['image_url']['url']; break
        except Exception as e: err = e
    else: raise err
    g = Image.open(io.BytesIO(base64.b64decode(u.split(',', 1)[1]))).convert('RGB').resize(s.size, Image.LANCZOS)
    oa = np.array(s); a = oa[..., 3:4]
    Image.fromarray(np.concatenate([np.where(a >= 200, np.array(g), oa[..., :3]), a], 2).astype('uint8'), 'RGBA').save(dst)
def text_rows(n):                       # 영어 흰 글자(밝고 채도 낮은 픽셀)의 세로 범위
    o = np.array(Image.open(H / 'src' / n).convert('RGBA')).astype(int)
    w = (o[..., :3].min(2) > 215) & (o[..., 3] > 200); w[:55] = 0
    ys, xs = np.where(w); return xs.min(), ys.min(), xs.max(), ys.max()
for n, en, ko, s in NAMES: erase(n, en)
boxes = {n: text_rows(n) for n, *_ in NAMES}
cy = 75.0                               # 세로 중심(사용자 요청 2026-11-10: 68.5 에서 내림)
size = 19                              # 사용자 요청 2026-11-10: 25 가 너무 커서 줄임(「아이템」 폭 약 58px, 영어 글자 폭 53~80px 수준)
print('size', size, 'cy', cy, boxes)
f = ImageFont.truetype(FONT, size)
for n, en, ko, st in NAMES:
    s = Image.open(H / 'src' / n).convert('RGBA'); e = Image.open(H / 'er' / n).convert('RGBA')
    l, t, r, b = f.getbbox(ko, stroke_width=2); pos = (50 - (l + r) / 2, cy - (t + b) / 2)
    out = e.copy()
    if st == 'on':
        glow = Image.new('RGBA', s.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).text(pos, ko, font=f, fill=(60, 140, 255, 255), stroke_width=5, stroke_fill=(60, 140, 255, 255))
        out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3)))
    sh = Image.new('RGBA', s.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pos[0] + 2, pos[1] + 2), ko, font=f, fill=(0, 0, 0, 200), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(1.5)))
    layer = Image.new('RGBA', s.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(pos, ko, font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(25, 25, 30, 255))
    out.alpha_composite(layer)
    a = np.maximum(np.array(s.getchannel('A')), np.array(out.getchannel('A')))   # 글자가 원래 투명한 곳에 걸치면 살린다
    out.putalpha(Image.fromarray(a.astype('uint8'))); out.save(H / 'final' / n)
S = 3; sheet = Image.new('RGB', (6 * (100 * S + 10) + 10, 4 * (100 * S + 10) + 10), (40, 40, 50))
for i, (n, *_r) in enumerate(NAMES):
    for j, d in enumerate(('src', 'final')):
        im = Image.open(H / d / n).convert('RGBA').resize((100 * S, 100 * S), Image.LANCZOS)
        sheet.paste(im, (10 + (i // 2) * (100 * S + 10), 10 + (j * 2 + i % 2) * (100 * S + 10)), im)
sheet.save(H / sys.argv[1] if len(sys.argv) > 1 else H / 'compare.png')

"""gemini로 일본어만 지운 뒤(원본 크기·알파 유지) 한글을 폰트로 직접 그린다."""
import sys, io, base64, json
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path.home() / '.claude/skills/game-image-text-translate/scripts'))
from _common import *
from PIL import ImageDraw, ImageFont, ImageFilter
FONT = Path('../../ko_font/ko_game_font.ttf').resolve()
plan = json.load(open('plan.json', encoding='utf8'))
def erase(name):
    dst = Path('erased') / name
    if dst.exists(): return
    s = Image.open('src' / Path(name)).convert('RGBA')
    p = (f"Edit this game UI image. Remove the Japanese text '{plan[name]['ja']}' completely and restore what is behind it "
         "(background, glow, icon parts). Do not add any new text. Keep everything else exactly the same: shape, colors, size, position. Output only the edited image.")
    m = chat(IMG_MODEL, p, on_dark(s)); u = m['images'][0]['image_url']['url']
    g = Image.open(io.BytesIO(base64.b64decode(u.split(',', 1)[1]))).convert('RGB').resize(s.size, Image.LANCZOS)
    oa = np.array(s); a = oa[..., 3:4]
    rgb = np.where(a >= 200, np.array(g), oa[..., :3])
    Image.fromarray(np.concatenate([rgb, a], 2).astype('uint8'), 'RGBA').save(dst)
def render(name):
    o = Image.open('src' / Path(name)).convert('RGBA'); e = Image.open('erased' / Path(name)).convert('RGBA')
    d = np.abs(np.array(o)[..., :3].astype(int) - np.array(e)[..., :3].astype(int)).sum(2) * (np.array(o)[..., 3] > 200)
    d[: int(o.height * 0.6)] = 0
    ys, xs = np.where(d > 150)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    txt = plan[name]['ko']; bw, bh = x1 - x0 + 1, y1 - y0 + 1
    for size in range(40, 6, -1):
        f = ImageFont.truetype(str(FONT), size); l, t, r, b = f.getbbox(txt, stroke_width=2)
        if r - l <= bw + 4 and b - t <= bh + 8: break
    layer = Image.new('RGBA', o.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(layer)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dr.text((cx - (l + r) / 2, cy - (t + b) / 2), txt, font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(30, 30, 40, 255))
    out = e.copy(); out.alpha_composite(layer); out.putalpha(o.getchannel('A')) if False else None
    out.save(Path('font') / name); print(name, 'bbox', (x0, y0, x1, y1), 'size', size)
for n in sys.argv[1:]:
    erase(n); render(n)
rows = sys.argv[1:]; sheet = Image.new('RGB', (900, 200 * len(rows)), (40, 40, 50))
for i, n in enumerate(rows):
    for j, dd in enumerate(('src', 'erased', 'font')):
        im = Image.open(Path(dd) / n).convert('RGBA'); im = im.resize((im.width * 2, im.height * 2)); sheet.paste(im, (5 + j * 300, 3 + i * 200), im)
sheet.save('font_compare.png')

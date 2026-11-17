"""Contact sheets of the JP APK atlas sprites that are not yet Korean, for eyeballing which ones carry Japanese text.

Reads build/out/jp_offline/dec/assets/cpk/{common,resources}.cpk, skips sprites already replaced
(translations/ui-ko/sprites/{official,custom}) and tiny ones, and writes one sheet per ~80 sprites:
build/out/sprite_sheets/<atlas>_<n>.png plus index.json (sheet -> sprite names, in cell order).

usage: python -I tools/sprite_contact_sheets.py
"""
import io, json, plistlib, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402

SRC = ROOT / 'build/out/jp_offline/dec/assets/cpk'
OUT = ROOT / 'build/out/sprite_sheets'
COLS, ROWS, CW, CH = 8, 10, 200, 92
MIN_SIDE = 20
done = {Path(r['file']).name for r in json.loads((ROOT / 'translations/ui-ko/sprites/official_index.json').read_text(encoding='utf-8'))}
done |= {p.name for p in (ROOT / 'translations/ui-ko/sprites/custom').glob('*.png')}
try:
    font = ImageFont.truetype('malgun.ttf', 10)
except Exception:
    font = ImageFont.load_default()


def nums(t):
    return [int(float(n)) for n in re.findall(r'-?\d+(?:\.\d+)?', t)]


def frame(meta):
    if 'frame' in meta:
        x, y, w, h = nums(meta['frame']); return x, y, w, h, bool(meta.get('rotated'))
    if 'textureRect' in meta:
        x, y, w, h = nums(meta['textureRect']); return x, y, w, h, bool(meta.get('textureRotated'))
    return int(meta.get('x', 0)), int(meta.get('y', 0)), int(meta.get('width', 0)), int(meta.get('height', 0)), False


def checker(w, h):
    im = Image.new('RGB', (w, h), (58, 58, 64))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            if (x // 8 + y // 8) % 2:
                d.rectangle([x, y, x + 7, y + 7], fill=(78, 78, 86))
    return im


def sheet(items, path):
    im = Image.new('RGB', (COLS * CW, ROWS * CH), (30, 30, 34)); d = ImageDraw.Draw(im)
    for i, (name, spr) in enumerate(items):
        cx, cy = (i % COLS) * CW, (i // COLS) * CH
        box = (CW - 8, CH - 24)
        s = min(box[0] / spr.width, box[1] / spr.height, 3.0)
        t = spr.resize((max(1, int(spr.width * s)), max(1, int(spr.height * s))), Image.LANCZOS)
        bg = checker(*t.size); bg.paste(t, (0, 0), t)
        im.paste(bg, (cx + 4, cy + 3))
        d.text((cx + 4, cy + CH - 17), f'{i + 1}.{name[:30]}', fill=(220, 220, 120), font=font)
        d.text((cx + 4, cy + CH - 8), f'{spr.width}x{spr.height}', fill=(150, 150, 160), font=font)
    im.save(path)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index, stats = {}, {'total': 0, 'done': 0, 'tiny': 0, 'sheeted': 0}
    for cname in ('common.cpk', 'resources.cpk'):
        pkg = cpk.Cpk.load_bytes((SRC / cname).read_bytes(), encoding='cp932')
        files = {i.full_path.replace('\\', '/'): i for i in pkg.file_infos()}
        for path in sorted(files):
            if not path.endswith('.plist'):
                continue
            tex = path[:-6] + '.png'
            if tex not in files:
                continue
            pl = plistlib.loads(pkg.file_bytes(files[path].toc_index))
            atlas = Image.open(io.BytesIO(pkg.file_bytes(files[tex].toc_index))).convert('RGBA')
            items = []
            for sname, meta in sorted(pl.get('frames', {}).items()):
                stats['total'] += 1
                x, y, w, h, rot = frame(meta)
                if sname in done:
                    stats['done'] += 1; continue
                if min(w, h) < MIN_SIDE and max(w, h) < 60:
                    stats['tiny'] += 1; continue
                img = atlas.crop((x, y, x + (h if rot else w), y + (w if rot else h)))
                if rot:
                    img = img.rotate(90, expand=True)
                items.append((sname, img))
            tag = re.sub(r'[^\w]+', '_', path[len('image/'):-6] if path.startswith('image/') else path[:-6])
            per = COLS * ROWS
            for n in range(0, len(items), per):
                key = f'{cname[:-4]}_{tag}_{n // per + 1}'
                sheet(items[n:n + per], OUT / f'{key}.png')
                index[key] = [nm for nm, _ in items[n:n + per]]
                stats['sheeted'] += len(items[n:n + per])
    (OUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf-8')
    print(stats, 'sheets', len(index))


if __name__ == '__main__':
    main()

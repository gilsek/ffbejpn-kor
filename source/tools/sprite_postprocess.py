"""Composite generated sprites onto the originals and build a before/after sheet.

For each build/out/sprite_work/gen/<name>.png (made from in/<name>.png):
  resize to original size -> use generated RGBA only where it differs from the original (colour or alpha)
  by more than THRESH (dilated a bit), else keep the original pixels -> final/<name>.png.
Writes compare/<n>.png sheets (original | final per row) for human approval.

usage: python -E -P tools/sprite_postprocess.py [--thresh 40]
"""
import argparse
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'build/out/sprite_work'


def compose(orig, gen, thresh):
    gen = gen.convert('RGBA').resize(orig.size, Image.LANCZOS)
    diff = ImageChops.difference(orig.convert('RGB'), gen.convert('RGB')).convert('L').point(lambda v: 255 if v > thresh else 0)
    mask = diff.filter(ImageFilter.MaxFilter(5))
    # also count alpha changes: on transparent labels the glyph itself is the only opaque part, so the Korean
    # glyph needs its own alpha (taking the original alpha would clip it to the Japanese glyph shape)
    da = ImageChops.difference(orig.getchannel('A'), gen.getchannel('A')).point(lambda v: 255 if v > thresh else 0)
    mask = ImageChops.lighter(mask, da.filter(ImageFilter.MaxFilter(5)))
    return Image.composite(gen, orig, mask)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--thresh', type=int, default=40); a = ap.parse_args()
    (W / 'final').mkdir(exist_ok=True); (W / 'compare').mkdir(exist_ok=True)
    rows = []
    for g in sorted((W / 'gen').glob('*.png')):
        o = W / 'in' / g.name
        if not o.exists():
            print('no original for', g.name); continue
        orig = Image.open(o).convert('RGBA')
        fin = compose(orig, Image.open(g), a.thresh)
        fin.save(W / 'final' / g.name)
        rows.append((g.name, orig, fin))
    per = 12
    for n in range(0, len(rows), per):
        chunk = rows[n:n + per]
        sheet = Image.new('RGB', (900, 110 * len(chunk)), (40, 40, 46)); d = ImageDraw.Draw(sheet)
        for i, (name, o, f) in enumerate(chunk):
            s = min(1.0, 330 / o.width, 90 / o.height) if o.width > 330 or o.height > 90 else 1.0
            for j, im in enumerate((o, f)):
                t = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
                bg = Image.new('RGB', t.size, (70, 70, 78)); bg.paste(t, (0, 0), t)
                sheet.paste(bg, (5 + j * 340, 110 * i + 4))
            d.text((690, 110 * i + 40), name[:30], fill=(230, 230, 130))
        sheet.save(W / 'compare' / f'{n // per + 1}.png')
    print('final', len(rows))


if __name__ == '__main__':
    main()

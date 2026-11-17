"""Title NEW GAME button art: the titlebutton_label_info.png frame (88x32) redrawn as 새 게임.

The JP title draws the info button label from the title atlas frame titlebutton_label_info.png
(image/ui/title/title.plist, textureRect {{1616,2},{88,32}} in 11.0.0). build/apply_ko_ui.py places every
translations/ui-ko/sprites/custom/*.png into whichever atlas frame has that name, so this writes the frame there.
Style sampled from the original »info glyphs: white fill, blue (30,85,161) outline.

usage: python -I build/make_jp_title_art.py [--text "새 게임"] [--preview out.png]
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'translations/ui-ko/sprites/custom/titlebutton_label_info.png'
SIZE = (88, 32)
FILL, STROKE = (255, 255, 255, 255), (30, 85, 161, 255)
FONT = 'C:/Windows/Fonts/malgunbd.ttf'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--text', default='새 게임')
    ap.add_argument('--preview')
    args = ap.parse_args()
    w, h = SIZE
    cell = Image.new('RGBA', SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(cell)
    stroke = 2
    for size in range(20, 8, -1):     # largest font (max 20, like the official labels) that fits the frame
        font = ImageFont.truetype(FONT, size)
        l, t, r, b = draw.textbbox((0, 0), args.text, font=font, stroke_width=stroke)
        if r - l <= w - 2 and b - t <= h - 2:
            break
    draw.text(((w - (r - l)) / 2 - l, (h - (b - t)) / 2 - t), args.text, font=font, fill=FILL,
              stroke_width=stroke, stroke_fill=STROKE)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cell.save(OUT)
    print('font size', size, '->', OUT)
    if args.preview:
        big = cell.resize((w * 6, h * 6), Image.NEAREST)
        bg = Image.new('RGBA', big.size, (40, 70, 140, 255)); bg.alpha_composite(big); bg.save(args.preview)


if __name__ == '__main__':
    main()

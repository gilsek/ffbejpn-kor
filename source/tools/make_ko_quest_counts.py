"""월드맵 지역 정보 라벨 「ステージ数」「エリア数」(quest.plist)을 한국어로 다시 그린다.

usage: python -I -X utf8 tools/make_ko_quest_counts.py [--out DIR]
원본: build/out/sprite_work/in/thenumberof_{stage,area}.png (228x24).
1. 글자 영역(x 39-119)의 어두운 판을 글자 없는 열(31-38, 120-194)로 행마다 2차식 맞춤해 복원.
2. 한글을 Noto Sans KR 굵게, 원본 글자의 행별 금색 세로 그라데이션으로 그린다.
   가로 중심은 원본 두 라벨의 글자 중심(약 x=79), 세로는 원본 글자 범위(y 5-18).
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'build/out/sprite_work/in'
FONT = 'C:/Windows/Fonts/NotoSansKR-VF.ttf'
LABELS = {'thenumberof_stage.png': '스테이지 수', 'thenumberof_area.png': '에어리어 수'}
TX0, TX1 = 39, 120          # 원본 글자 열 범위
FIT_COLS = list(range(31, 39)) + list(range(120, 195))
TOP, BOTTOM = 5, 18         # 원본 글자 행 범위
CX = 79


def clean_plate(a):
    """글자 영역을 판 그라데이션으로 채운다(premultiplied 공간에서 행별 2차식)."""
    out = a.copy()
    xs = np.array(FIT_COLS)
    for y in range(a.shape[0]):
        alpha = a[y, xs, 3]
        prem = a[y, xs, :3] * alpha[:, None] / 255.0
        fill_x = np.arange(TX0 - 1, TX1 + 1)
        al = np.polyval(np.polyfit(xs, alpha, 2), fill_x).clip(0, 255)
        for c in range(3):
            p = np.polyval(np.polyfit(xs, prem[:, c], 2), fill_x).clip(0, None)
            out[y, fill_x, c] = np.where(al > 0, (p * 255 / np.maximum(al, 1)).clip(0, 255), 0)
        out[y, fill_x, 3] = al
    return out


def row_colors(a):
    """원본 글자 행별 색(밝은 글자 픽셀 중앙값)."""
    cols = []
    for y in range(TOP, BOTTOM + 1):
        row = a[y, TX0:TX1]
        m = row[:, 0] > 150
        cols.append(np.median(row[m][:, :3], axis=0) if m.any() else np.array([214, 160, 0]))
    return np.array(cols)


def draw(plate, text, colors, weight=900):
    h, w = plate.shape[:2]
    target = BOTTOM - TOP + 1
    size = 15
    while True:
        f = ImageFont.truetype(FONT, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001
            pass
        x0, y0, x1, y1 = f.getbbox(text)
        if y1 - y0 <= target or size <= 9:
            break
        size -= 1
    mask = Image.new('L', (w, h), 0)
    left = round(CX - (x1 - x0) / 2) - x0
    top = TOP + (target - (y1 - y0)) // 2 - y0
    ImageDraw.Draw(mask).text((left, top), text, font=f, fill=255)
    m = np.asarray(mask).astype(float) / 255
    # 글자 세로 범위에 원본 행 색을 늘려 입힌다.
    ys = np.where(m.max(1) > 0)[0]
    col = np.zeros((h, 3))
    for y in range(h):
        t = 0 if len(ys) < 2 else (y - ys[0]) / max(1, ys[-1] - ys[0])
        i = min(len(colors) - 1, max(0, round(t * (len(colors) - 1))))
        col[y] = colors[i]
    out = plate.copy()
    pa = plate[..., 3:4] / 255.0
    ta = m[..., None]
    na = ta + pa * (1 - ta)
    rgb = (col[:, None, :] * ta + plate[..., :3] * pa * (1 - ta)) / np.maximum(na, 1e-6)
    out[..., :3] = rgb
    out[..., 3:4] = na * 255
    return out, size, (left + x0, left + x1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'build/out/sprite_work/quest_counts')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    colors = row_colors(np.asarray(Image.open(SRC / 'thenumberof_stage.png').convert('RGBA')).astype(float))
    for name, ko in LABELS.items():
        a = np.asarray(Image.open(SRC / name).convert('RGBA')).astype(float)
        out, size, span = draw(clean_plate(a), ko, colors)
        Image.fromarray(out.round().clip(0, 255).astype(np.uint8), 'RGBA').save(args.out / name)
        print(name, ko, 'size', size, 'x', span)


if __name__ == '__main__':
    main()

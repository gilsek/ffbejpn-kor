"""2026-11-10. Draw Korean dictionary-button labels on an empty transparent canvas, with the exact style of the installed
아이템 label (largebutton_label_dic_item): same font, size, weight, colours, outline, line centre."""
import sys, json
from pathlib import Path
ROOT = Path(r'C:\Users\USER\Documents\Projects\exvius-offline-ko')
sys.path.insert(0, str(ROOT / 'tools'))
import numpy as np
from PIL import Image
import ocr_text_mask as M
import render_ko_labels as L
_det = M.detector()
def det_boxes(rgba):
    a = np.array(rgba.convert('RGBA')); out = []
    for q in M.boxes_of(_det, a):
        out.append([max(0, q[:, 0].min()), max(0, q[:, 1].min()), min(rgba.width, q[:, 0].max() + 1), min(rgba.height, q[:, 1].max() + 1)])
    return out
W = ROOT / 'build/out/sprite_work'; OUT = ROOT / 'build/out/dic_buttons/tpl'; OUT.mkdir(parents=True, exist_ok=True)
ref = Image.open(W / 'in/largebutton_label_dic_item.png').convert('RGBA')
a = np.array(ref)[..., 3]; boxes = det_boxes(ref)
text = L.text_components(a, boxes, np.array(ref)[..., :3]); lines = L.lines_from(text, boxes, a); st = L.style_of(ref, text)
size, weight = 29.5, 800          # the installed 아이템 label (ko_render report: size 29.5, weight 800)
gmin = min(l['y1'] - l['y0'] for l in lines); st['ow'] = min(st['ow'], max(0.8, 0.08 * gmin))
ln = lines[0]; cy = (ln['y0'] + ln['y1']) / 2; CX = (ln['x0'] + ln['x1']) / 2
targets = {'largebutton_label_dic_item.png': '아이템', 'largebutton_label_dic_ability.png': '어빌리티', 'largebutton_label_dic_recipe.png': '레시피',
           'largebutton_label_dic_monster.png': '몬스터', 'largebutton_label_dic_visioncard.png': '비전 카드',
           'largebutton_label_dic_equip.png': '장비품', 'largebutton_label_dic_summon.png': '환수', 'largebutton_label_dic_unit.png': '유닛',
           'largebutton_label_dic_material.png': '소재', 'largebutton_label_dic_gallery.png': '갤러리'}
for n, ko in targets.items():
    src = Image.open(W / 'in' / n).convert('RGBA')
    cx = CX
    b = L.ink_box(ko, size * L.SS, weight); w = (b[2] - b[0]) / L.SS
    q = min(1.0, (src.width - 8) / w) if w > src.width - 8 else 1.0
    canvas = Image.new('RGBA', src.size, (0, 0, 0, 0))
    canvas.alpha_composite(L.render_line(src.size, ko, size, weight, q, cx, cy, st))
    canvas.save(OUT / n); print(n, src.size, 'width', round(w, 1), 'squeeze', round(q, 3))

# usage: python -I -X utf8 tools/render_ko_dic_buttons.py -> build/out/dic_buttons/tpl/

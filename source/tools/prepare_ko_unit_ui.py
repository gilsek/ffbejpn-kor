"""유닛 UI 전수 대조 및 검수한 글꼴 라벨 생성. 입력/공유 OCR 결과는 보존한다.

python -I -X utf8 tools/prepare_ko_unit_ui.py [--pin]
--pin: 검수한 결과만 labels/와 고정 manifest에 연결한다. APK/기기는 변경하지 않는다.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import render_ko_labels as R

WORK = ROOT / 'build/out/sprite_work'
OUT = ROOT / 'build/out/ko_ui_labels/unit-detail'
KO = ROOT / 'translations/ui-ko/sprites'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_path(name):
    pinned=KO/'unit_sources'/name
    return pinned if pinned.exists() else WORK/'in'/name


def glyph(src, text, height=None, weight=450, fill=None):
    """문자만 있는 투명 라벨을 글꼴에서 새로 생성한다. 아이콘 합성 라벨에는 쓰지 않는다."""
    a = np.asarray(src)
    ys, xs = np.where(a[..., 3] > 180)
    assert len(xs), text
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    colors = a[ys, xs, :3]
    color = fill or np.percentile(colors, 85, axis=0).tolist()
    st = dict(fill_top=color, fill_bot=color, outline=[8, 15, 25], ow=0.3, glow=None)
    h = min(src.height - 3, height or y1-y0)
    size, squeeze = R.fit_size(text, h, src.width-4, weight)
    return R.render_line(src.size, text, size, weight, squeeze,
                         float(x0+x1)/2, float(y0+y1)/2, st)


def favorite(src, lines=('즐겨찾기','장비')):
    st = dict(fill_top=[255]*3, fill_bot=[245]*3, outline=[8, 15, 25], ow=0.3, glow=None)
    out = Image.new('RGBA', src.size)
    for i,text in enumerate(lines):
        cy=src.height*(i+0.5)/len(lines)
        size, q = R.fit_size(text, min(20,src.height/len(lines)-5), src.width-10, 450)
        out.alpha_composite(R.render_line(src.size, text, size, 450, q, src.width/2, cy, st))
    return out


def panel(src, spec):
    """검수한 문자 사각형만 교체한다. 테두리/아이콘/나머지 픽셀 보존을 검사한다."""
    out = src.copy()
    if spec['background'] == 'solid_black':
        blank = Image.new('RGBA',src.size,(0,0,0,255))
    elif spec['background'] == 'dominant':
        pixels=np.asarray(src);colors=pixels[pixels[...,3]>240]
        color=Counter(map(tuple,colors)).most_common(1)[0][0]
        blank=Image.new('RGBA',src.size,tuple(int(v) for v in color))
    elif spec['background'] == 'blank_skill':
        blank = Image.open(WORK/'in/unit_skillbg.png').convert('RGBA')
    else:
        path=KO/'unit_backgrounds'/spec['name']
        assert digest(path)==spec['background_sha256'],path
        blank = Image.open(path).convert('RGBA')
    boxes = []
    for line in spec['lines']:
        box = tuple(line['box']); boxes.append(box)
        out.paste(blank.crop(box), box)
        tile = Image.new('RGBA', (box[2]-box[0], box[3]-box[1]))
        st = dict(fill_top=[255]*3, fill_bot=[240]*3, outline=[8, 15, 25], ow=0.3, glow=None)
        size, q = R.fit_size(line['ko'], line['height'], tile.width-4, 450)
        ink=R.ink_box(line['ko'],size*R.SS,450)
        cx=(ink[2]-ink[0])/R.SS*q/2+2 if line.get('align','left')=='left' else tile.width/2
        tile.alpha_composite(R.render_line(tile.size, line['ko'], size, 450, q, cx, tile.height/2, st))
        out.alpha_composite(tile, (box[0], box[1]))
    restored = out.copy()
    for box in boxes:
        restored.paste(src.crop(box), box)
    assert restored.tobytes() == src.tobytes(), spec['name']
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pin', action='store_true'); args=ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); dest=OUT/'generated'; dest.mkdir(exist_ok=True)
    config=read(KO/'unit_ui_review.json')
    manifest=read(KO/'labels_manifest.json')
    ocr={r['name']:r for r in read(WORK/'ocr.json')}
    specs={r['name']:r for r in config['render']}
    inventory=[]
    actual=read(OUT/'actual-unit-inventory.json')
    for row in actual['rows']:
        name=row['name']; override=config['translations'].get(name)
        inventory.append({**row, 'existing_translation':ocr.get(name), 'review':override,
            'pinned_before':name in manifest, 'selected':name in specs,
            'classification':'reviewed_text' if override else 'existing_text' if name in ocr else 'nontext_or_latin',
            'note':config.get('notes',{}).get(name)})
    generated=[]; sheet_rows=[]
    for name,spec in specs.items():
        src=Image.open(source_path(name)).convert('RGBA'); mode=spec.get('mode','glyph')
        if 'source_sha256' in spec:assert digest(source_path(name))==spec['source_sha256'],name
        text=config['translations'][name]['ko']
        if mode=='favorite': result=favorite(src,spec.get('text_lines',('즐겨찾기','장비')))
        elif mode=='original': result=src
        elif mode=='panel': result=panel(src,spec)
        else: result=glyph(src,text,spec.get('height'),spec.get('weight',450),spec.get('fill'))
        assert result.size==src.size and result.getbbox(),name
        result.save(dest/name)
        record={'translation':text,'sha256':digest(dest/name),'source_sha256':digest(source_path(name)),
                'review_source':'unit_ui_review.json','mode':mode}
        generated.append({'name':name,**record})
        oldpath=KO/'labels'/name
        old=Image.open(oldpath).convert('RGBA') if oldpath.exists() else src
        sheet_rows.append((name,old,result,{'ko':text,'lines':2 if mode=='favorite' else 1}))
        if args.pin:
            (KO/'labels'/name).write_bytes((dest/name).read_bytes());manifest[name]=record
    for start in range(0,len(sheet_rows),12):
        R.sheet(sheet_rows[start:start+12],OUT/f'review-{start//12+1}.png')
    result={'unit_frames':len(inventory),'atlas_placements':actual['placements'],'missing_work_manifest':actual['missing_work_manifest'],'counts':dict(Counter(r['classification'] for r in inventory)),
        'existing_ocr_entries':sum(bool(r['existing_translation']) for r in inventory),
        'existing_translated_unpinned':sum(bool(r['existing_translation']) and not r['pinned_before'] for r in inventory),
        'generated':generated,'inventory':inventory,'pinned':args.pin}
    (OUT/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    if args.pin:(KO/'labels_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('유닛 프레임',len(inventory),'기존 OCR',result['existing_ocr_entries'],'검수 생성',len(generated),'고정',args.pin)


if __name__=='__main__':main()

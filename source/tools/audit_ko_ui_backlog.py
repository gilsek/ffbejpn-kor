"""OCR 미연결 후보를 현재 APK 원본 픽셀과 대조한다. 미번역 확정 집계가 아니다."""
import argparse
from collections import Counter
import io
import hashlib
import html
import json
from pathlib import Path
import plistlib
import re
import sys
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build'))
import apply_ko_ui as U


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apk',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--collect',type=Path,help='후보 원본과 전체 프레임 색인·검수 갤러리 저장');args=ap.parse_args()
    work=ROOT/'build/out/sprite_work'
    pin=json.loads((U.KO/'sprites/labels_manifest.json').read_text(encoding='utf-8'))
    candidates={r['name']:dict(r,locations=[]) for r in json.loads((work/'ocr.json').read_text(encoding='utf-8'))
                if r['name'] not in pin and re.search(r'[ぁ-ヿ一-鿿]',r.get('ja',''))}
    actual=[]
    if args.collect:(args.collect/'originals').mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.apk) as apk:
        for cname in ('common','resources'):
            c=U.cpk.Cpk.load_bytes(apk.read(f'assets/cpk/{cname}.cpk'),encoding='cp932')
            by={i.full_path:i for i in c.file_infos()};images={}
            for info in by.values():
                if not info.full_path.endswith('.plist'):continue
                pl=plistlib.loads(c.file_bytes(info.toc_index))
                for name,meta in pl.get('frames',{}).items():
                    rect,rot=U.frame_info(meta)
                    actual.append({'name':name,'atlas':cname+':'+info.full_path,
                                   'size':list(rect[2:]),'pinned':name in pin,
                                   'ocr_candidate':name in candidates})
                for name in candidates.keys() & pl.get('frames',{}).keys():
                    meta=pl['frames'][name];(x,y,w,h),rot=U.frame_info(meta)
                    texture=pl.get('metadata',{}).get('textureFileName') or Path(info.full_path).with_suffix('.png').name
                    png=(Path(info.full_path).parent/texture).as_posix()
                    if png not in images:images[png]=Image.open(io.BytesIO(c.file_bytes(by[png].toc_index))).convert('RGBA')
                    crop=images[png].crop((x,y,x+(h if rot else w),y+(w if rot else h)))
                    if rot:crop=crop.rotate(90,expand=True)
                    original=Image.open(work/'in'/name).convert('RGBA')
                    same=crop.size==original.size and crop.tobytes()==original.tobytes()
                    candidates[name]['locations'].append({'atlas':cname+':'+info.full_path,'same_original':same})
                    if args.collect and not (args.collect/'originals'/name).exists():
                        assert Path(name).name==name,name
                        crop.save(args.collect/'originals'/name)
    for r in candidates.values():
        loc=r['locations']
        r['status']='missing' if not loc else 'same_original' if all(l['same_original'] for l in loc) else 'mixed' if any(l['same_original'] for l in loc) else 'changed_review_needed'
    counts=dict(Counter(r['status'] for r in candidates.values()))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'counts':counts,'candidates':list(candidates.values()),
        'caution':'OCR 기반 후보. 원본과 다른 픽셀은 번역 완료의 증거가 아니며 원본 일치도 OCR 오인식 가능성을 별도 검수해야 한다.'},ensure_ascii=False,indent=1),encoding='utf-8')
    print('OCR 미연결 후보',len(candidates),counts)
    if args.collect:
        official=json.loads((U.KO/'sprites/official_index.json').read_text(encoding='utf-8'))
        byname={r['sprite']:r for r in official};groups=Counter();cards=[]
        for r in candidates.values():
            name=r['name'];source=args.collect/'originals'/name
            r['size']=list(Image.open(source).size) if source.exists() else None
            r['sha256']=hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None
            r['state_group']=re.sub(r'(?:_s[12]|_l[12]|[-_]on|[-_]off|[12])(?=\.png$)','',name)
            r['screen']=Path(r['locations'][0]['atlas'].partition(':')[2]).parent.name if r['locations'] else 'missing'
            r['official_candidate']=byname.get(name)
            r['production_status']='검수 대기'
            groups[r['screen']]+=1
            label=html.escape(r['ja']+' → '+r.get('ko',''))
            cards.append(f'<article data-search="{html.escape(name+" "+r["screen"]+" "+r["ja"]+" "+r.get("ko",""),quote=True)}"><img loading="lazy" src="originals/{name}"><b>{label}</b><small>{html.escape(name)} · {r["screen"]} · {r["size"]}</small></article>')
        report={'apk_sha256':hashlib.sha256(args.apk.read_bytes()).hexdigest(),
                'actual_placements':len(actual),'actual_unique_names':len({r['name'] for r in actual}),
                'ocr_candidates':len(candidates),'screen_counts':dict(groups),
                'state_groups':len({r['state_group'] for r in candidates.values()}),
                'official_candidates':sum(bool(r['official_candidate']) for r in candidates.values()),
                'candidates':list(candidates.values())}
        (args.collect/'inventory.json').write_text(json.dumps(actual,ensure_ascii=False,indent=1),encoding='utf-8')
        (args.collect/'queue.json').write_text(json.dumps(report,ensure_ascii=False,indent=1),encoding='utf-8')
        page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>한국어 UI 제작 후보</title><style>body{background:#111827;color:#eee;font:15px sans-serif;padding:24px}input{padding:12px;width:90%;font-size:18px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}article{padding:14px;background:#1e293b;display:flex;flex-direction:column;gap:10px;border-radius:8px}img{max-width:100%;max-height:160px;object-fit:contain;align-self:center}small{overflow-wrap:anywhere;color:#b4c1d5}p{line-height:1.7}</style><h1>일본어 UI 이미지 제작 후보</h1><p>현재 APK에서 수집한 OCR 기반 후보. 일본어 원문·번역 후보는 OCR 기록이며 오인식/용어 검수가 필요합니다.<br>전체 게임의 모든 글자 이미지를 검출했다는 뜻은 아닙니다. 전체 프레임 색인은 inventory.json 참조.</p><input placeholder="화면·파일명·일본어·한국어 검색" oninput="document.querySelectorAll('article').forEach(x=>x.hidden=!x.dataset.search.toLowerCase().includes(this.value.toLowerCase()))"><main>'''+''.join(cards)+'</main></html>'
        (args.collect/'gallery.html').write_text(page,encoding='utf-8')
        print('전체 프레임 배치',len(actual),'후보 상태그룹',report['state_groups'],'공식 자산 동명이름',report['official_candidates'])


if __name__=='__main__':main()

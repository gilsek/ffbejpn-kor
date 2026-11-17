"""현재 APK의 실제 프레임과 공식 한국어 이미지 위치/크기를 읽기 전용 대조한다."""
import argparse,json,plistlib,sys,zipfile
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build'))
import apply_ko_ui as U
from PIL import Image

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apk',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    actual=defaultdict(list)
    with zipfile.ZipFile(a.apk) as z:
        for cn in ('common','resources'):
            c=U.cpk.Cpk.load_bytes(z.read(f'assets/cpk/{cn}.cpk'),encoding='cp932')
            for info in c.file_infos():
                if not info.full_path.endswith('.plist'):continue
                pl=plistlib.loads(c.file_bytes(info.toc_index))
                for name,meta in pl.get('frames',{}).items():
                    rect,rot=U.frame_info(meta)
                    actual[name].append({'cpk':cn,'plist':info.full_path,'size':list(rect[2:]),'rotated':rot})
    official=json.loads((U.KO/'sprites/official_index.json').read_text(encoding='utf-8'));rows=[]
    for row in official:
        hits=actual.get(row['sprite'],[]);exact=[h for h in hits if h['plist']==row['plist']]
        kind='exact' if exact else 'relocated' if hits else 'absent'
        size=list(Image.open(U.KO/row['file']).size)
        rows.append({'name':row['sprite'],'kind':kind,'expected_plist':row['plist'],'image':row['file'],
                     'image_size':size,'hits':hits,'all_sizes_match':all(h['size']==size for h in hits) if hits else None})
    result={'counts':dict(Counter(r['kind'] for r in rows)),'rows':rows}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('공식 자산 위치 대조',result['counts'])
    relocated=[r for r in rows if r['kind']=='relocated']
    print('이동 후보 중 크기 일치',sum(r['all_sizes_match'] for r in relocated),'불일치',sum(not r['all_sizes_match'] for r in relocated))
    for r in relocated[:25]:print(r['name'],r['expected_plist'],'->',','.join(h['plist'] for h in r['hits']),'size',r['all_sizes_match'])
if __name__=='__main__':main()

"""감사한 동일 크기 공식 한국어 라벨을 실제 프레임에 연결한다."""
import argparse,hashlib,json,shutil
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--audit',type=Path,required=True);a=ap.parse_args()
    data=json.loads(a.audit.read_text(encoding='utf-8'))
    root=ROOT/'translations/ui-ko';path=root/'sprites/labels_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    selected=[r for r in data['rows'] if r['kind']=='relocated' and r['all_sizes_match'] and 'label' in r['name']]
    assert len(selected)==53,'감사 범위가 변경되면 다시 확인한다'
    skipped=[]
    for row in selected:
        source=root/row['image'];name=row['name']
        if Image.open(source).convert('RGBA').getchannel('A').getbbox() is None:
            skipped.append(name);manifest.pop(name,None);continue
        shutil.copyfile(source,root/'sprites/labels'/name)
        old=manifest.get(name,{})
        manifest[name]={'translation':old.get('translation','공식 한국어 이미지'),
                        'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                        'origin':row['image'],'resolved_locations':row['hits']}
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('공식 위치 이동 후보',len(selected),'빈 이미지 제외',skipped,'확정 사전',len(manifest))
if __name__=='__main__':main()

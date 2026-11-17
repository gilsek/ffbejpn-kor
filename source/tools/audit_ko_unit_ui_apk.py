"""APK의 실제 유닛 UI 아틀라스 전체를 작업 목록과 대조한다(앱/기기 변경 없음)."""
import argparse
import io
import json
import plistlib
import sys
import zipfile
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build'))
import apply_ko_ui as U


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apk',type=Path,required=True)
    ap.add_argument('--out',type=Path,default=ROOT/'build/out/ko_ui_labels/unit-detail')
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    dest=a.out/'extracted';dest.mkdir(exist_ok=True)
    work={r['name']:r for r in json.loads((ROOT/'build/out/sprite_work/manifest.json').read_text())}
    actual={};placements=0
    with zipfile.ZipFile(a.apk) as z:
        c=U.cpk.Cpk.load_bytes(z.read('assets/cpk/resources.cpk'),encoding='cp932')
        files={i.full_path:i for i in c.file_infos()}
        for info in files.values():
            if not info.full_path.startswith('image/ui/unit/') or not info.full_path.endswith('.plist'):continue
            pl=plistlib.loads(c.file_bytes(info.toc_index))
            png=(Path(info.full_path).parent/(pl['metadata'].get('textureFileName') or Path(info.full_path).with_suffix('.png').name)).as_posix()
            image=Image.open(io.BytesIO(c.file_bytes(files[png].toc_index))).convert('RGBA')
            for name,meta in pl['frames'].items():
                placements+=1;(x,y,w,h),rot=U.frame_info(meta)
                row=actual.setdefault(name,{'name':name,'w':w,'h':h,'locations':[],'in_work_manifest':name in work})
                assert [w,h]==[row['w'],row['h']],name
                row['locations'].append(info.full_path)
                if name not in work:
                    crop=image.crop((x,y,x+(h if rot else w),y+(w if rot else h)))
                    if rot:crop=crop.rotate(90,expand=True)
                    path=dest/name
                    if path.exists():assert Image.open(path).convert('RGBA').tobytes()==crop.tobytes(),name
                    else:crop.save(path)
    report={'placements':placements,'unique_frames':len(actual),'missing_work_manifest':sum(not r['in_work_manifest'] for r in actual.values()),'rows':list(actual.values())}
    (a.out/'actual-unit-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('실제 배치',placements,'고유 프레임',len(actual),'작업목록 누락',report['missing_work_manifest'])


if __name__=='__main__':main()

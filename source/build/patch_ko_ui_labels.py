"""현재 APK의 준비된 한국어 UI 라벨만 연결한다. 기존 그림·엔진을 보존한다."""
import argparse, hashlib, io, json, plistlib, re, shutil, sys, zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import apply_ko_ui as U
import jp_offline_build as B
from PIL import Image

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--only',help='쉼표로 구분한 고정 프레임 이름만 적용(다른 세션의 자산 보존)');a=ap.parse_args()
    assert a.source.resolve()!=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    work=U.ROOT/'build/out/sprite_work';dest=a.out/'labels';dest.mkdir(exist_ok=True)
    manifest=U.KO/'sprites/labels_manifest.json'
    if manifest.exists():
        pinned=json.loads(manifest.read_text(encoding='utf-8'))
        if a.only:
            names=set(a.only.split(','));assert names <= pinned.keys(), sorted(names-pinned.keys())
            pinned={name:r for name,r in pinned.items() if name in names}
        selected={name:{'ko':r['translation']} for name,r in pinned.items()}
        for name,r in pinned.items():
            source=U.KO/'sprites/labels'/name
            assert sha(source.read_bytes())==r['sha256'],name
            shutil.copyfile(source,dest/name)
    else:
        rows=json.loads((work/'ko_render/_report.json').read_text(encoding='utf-8'))
        selected={r['name']:r for r in rows if r.get('status')=='ok' and not r.get('warn') and r.get('kept_pixels_changed')==0}
        for name in selected:shutil.copyfile(work/'ko_render'/name,dest/name)
    report={'selected':len(selected),'applied':[],'unmatched':[],'unchanged_cpk_files':0,'unchanged_base_entries':0,'output':{}}
    changes={};hit=set()
    with zipfile.ZipFile(a.source/'base.apk') as z:
        for cname in ('common','resources'):
            entry=f'assets/cpk/{cname}.cpk';orig=z.read(entry);c=U.cpk.Cpk.load_bytes(orig,encoding='cp932');infos=list(c.file_infos());by={i.full_path:i for i in infos};atlases={};rects={}
            for info in infos:
                if not info.full_path.endswith('.plist'):continue
                pl=plistlib.loads(c.file_bytes(info.toc_index));frames=pl.get('frames',{})
                for name in selected.keys() & frames.keys():
                    meta=frames[name];(x,y,w,h),rotated=U.frame_info(meta)
                    tex=pl.get('metadata',{}).get('textureFileName') or Path(info.full_path).with_suffix('.png').name
                    png=(Path(info.full_path).parent/tex).as_posix();assert png in by,png
                    if png not in atlases:atlases[png]=Image.open(io.BytesIO(c.file_bytes(by[png].toc_index))).convert('RGBA')
                    im=Image.open(dest/name).convert('RGBA');assert im.size==(w,h),(name,im.size,(w,h))
                    if rotated:im=im.rotate(-90,expand=True)
                    assert x+im.width<=atlases[png].width and y+im.height<=atlases[png].height
                    atlases[png].paste(im,(x,y));rects.setdefault(png,[]).append((x,y,im.width,im.height))
                    hit.add(name);report['applied'].append({'name':name,'cpk':cname,'atlas':png,'ko':selected[name]['ko'],'sha256':sha((dest/name).read_bytes())})
            replace={}
            for png,im in atlases.items():
                before=Image.open(io.BytesIO(c.file_bytes(by[png].toc_index))).convert('RGBA')
                # 교체 범위를 복원하면 모든 픽셀이 원본과 일치해야 한다.
                restored=im.copy()
                for x,y,w,h in rects[png]:restored.paste(before.crop((x,y,x+w,y+h)),(x,y))
                assert restored.tobytes()==before.tobytes(),png
                b=io.BytesIO();im.save(b,format='PNG');replace[png]=b.getvalue()
            patched=U.cpk_inplace.patch(orig,replace);after=U.cpk.Cpk.load_bytes(patched,encoding='cp932');later=list(after.file_infos())
            assert [(i.full_path,i.toc_index) for i in infos]==[(i.full_path,i.toc_index) for i in later]
            for old,new in zip(infos,later):
                assert after.file_bytes(new.toc_index)==replace.get(old.full_path,c.file_bytes(old.toc_index))
                report['unchanged_cpk_files']+=old.full_path not in replace
            if replace:changes[entry]=patched
        report['unmatched']=sorted(selected.keys()-hit)
        unsigned=a.out/'base-labels-unsigned.apk'
        with zipfile.ZipFile(unsigned,'w') as target:
            for info in z.infolist():
                if re.fullmatch(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))',info.filename,re.I):continue
                target.writestr(info,changes.get(info.filename,z.read(info.filename)))
    B.align_sign(unsigned,a.out/'base.apk')
    with zipfile.ZipFile(a.source/'base.apk') as old,zipfile.ZipFile(a.out/'base.apk') as new:
        for name in old.namelist():
            if name in changes or name.startswith('META-INF/'):continue
            assert old.read(name)==new.read(name),name
            report['unchanged_base_entries']+=1
    for path in a.source.glob('split_*.apk'):shutil.copyfile(path,a.out/path.name)
    for path in [a.source/'base.apk',*a.source.glob('split_*.apk')]:
        report['output'][path.name]=sha((a.out/path.name).read_bytes())
        if path.name!='base.apk':assert report['output'][path.name]==sha(path.read_bytes())
    (a.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('PASS: 선택',len(selected),'적용',len(hit),'미매칭',len(report['unmatched']),'CPK 비대상',report['unchanged_cpk_files'],'base 비대상',report['unchanged_base_entries'],'split 3개 보존')
if __name__=='__main__':main()

"""현재 앱 APK 사본의 지정 엔진 overlay만 갱신해 재서명한다.

다른 UI 산출물/네이티브/세이브를 포함하지 않고, 원본 APK 디렉터리는 읽기만 한다.
python -I -X utf8 build/repack_jp_engine.py --source <APK 4개 사본 폴더> --out <별도 폴더> --only a.py,b.json
"""
import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import jp_offline_build as B

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--only',required=True);a=ap.parse_args()
    src=a.source.resolve();out=a.out.resolve()
    assert src!=out and src not in out.parents,'입력/출력 폴더를 분리한다'
    names=a.only.split(',');assert all(Path(n).name==n for n in names)
    overlay={n:(B.ROOT/'build/engine_overlay'/n).read_bytes() for n in names}
    parts=['base','split_config.arm64_v8a','split_config.ja','split_config.xhdpi']
    assert all((src/(p+'.apk')).is_file() for p in parts)
    out.mkdir(parents=True,exist_ok=True)
    base=src/'base.apk'
    cpk_updates={}
    for cpk_name in ('common.cpk','resources.cpk'):
        cpk_path=B.KO_UI/cpk_name
        if cpk_path.is_file():cpk_updates[f'assets/cpk/{cpk_name}']=cpk_path.read_bytes()
    synced_cpks={}
    with zipfile.ZipFile(base) as z:
        imyname='assets/chaquopy/app.imy'
        with zipfile.ZipFile(io.BytesIO(z.read(imyname))) as app:
            assert b'_jp_korean.install(game.server)' in app.read('android_game.py')
            mem=io.BytesIO()
            with zipfile.ZipFile(mem,'w',zipfile.ZIP_DEFLATED) as target:
                for info in app.infolist():
                    if info.filename in overlay or info.filename in {n[:-3]+'.pyc' for n in names if n.endswith('.py')}:continue
                    target.writestr(info,app.read(info.filename))
                for n,data in overlay.items():target.writestr(n,data)
        unsigned=out/'base-engine-unsigned.apk'
        with zipfile.ZipFile(unsigned,'w') as target:
            for info in z.infolist():
                if re.fullmatch(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))',info.filename,re.I):continue
                if info.filename in cpk_updates:
                    old_bytes=z.read(info.filename)
                    new_bytes=cpk_updates[info.filename]
                    if hashlib.sha256(old_bytes).digest()!=hashlib.sha256(new_bytes).digest():
                        new_sha=hashlib.sha256(new_bytes).hexdigest()
                        zi=zipfile.ZipInfo(info.filename,date_time=info.date_time)
                        target.writestr(zi,new_bytes,compress_type=zipfile.ZIP_STORED)
                        synced_cpks[info.filename]=new_sha
                        print(f'SYNCED CPK: {info.filename} ({new_sha[:16]})')
                        continue
                target.writestr(info,mem.getvalue() if info.filename==imyname else z.read(info.filename))
    B.align_sign(unsigned,out/'base.apk')
    for p in parts[1:]:shutil.copyfile(src/(p+'.apk'),out/(p+'.apk'))
    # APK 재서명으로 바뀌는 메타데이터/엔진/동기화 CPK 외 모든 원래 항목을 대조한다.
    with zipfile.ZipFile(base) as old,zipfile.ZipFile(out/'base.apk') as new:
        checked=0
        for name in old.namelist():
            if name==imyname or name.startswith('META-INF/'):continue
            if name in synced_cpks:
                assert new.read(name)==cpk_updates[name],name
            else:
                assert old.read(name)==new.read(name),name
            checked+=1
        with zipfile.ZipFile(io.BytesIO(new.read(imyname))) as app:
            for name,data in overlay.items():assert app.read(name)==data
    report={'overlay':{n:hashlib.sha256(d).hexdigest() for n,d in overlay.items()},
            'synced_cpks':synced_cpks,
            'unchanged_base_entries':checked,'source':{p:sha(src/(p+'.apk')) for p in parts},
            'output':{p:sha(out/(p+'.apk')) for p in parts},'unchanged_splits':True}
    assert all(report['source'][p]==report['output'][p] for p in parts[1:])
    (out/'engine-check.json').write_text(json.dumps(report,indent=1)+'\n',encoding='utf-8')
    print('PASS: 엔진',len(overlay),'파일 갱신, base 항목',checked,'개·split 3개 원본과 동일')

if __name__=='__main__':main()

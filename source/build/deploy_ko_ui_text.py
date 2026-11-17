"""현재 설치본과 입력 사본이 같은 경우에만 UI 텍스트 APK를 설치·해시 검증한다."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PKG='com.exvius.jpkorean.app'

def main():
    p=argparse.ArgumentParser();p.add_argument('--serial',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--apk-dir',type=Path,required=True);a=p.parse_args()
    adb=lambda *args:subprocess.check_output(['adb','-s',a.serial,*args])
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    def remote():
        paths=adb('shell','pm','path',PKG).decode().splitlines()
        result={}
        for line in paths:
            name=line.removeprefix('package:');value=adb('shell','sha256sum',name).decode().split()[0]
            result[name.rsplit('/',1)[-1]]=value
        return result
    old=remote();sources={x.name:digest(x) for x in a.source.glob('*.apk')}
    assert len(old)==4 and old==sources,'설치본 변경 감지: 현재 APK를 새로 읽고 패치할 것'
    expected={name:digest(a.apk_dir/name) for name in old}
    for name in old:
        if name!='base.apk':assert old[name]==expected[name],'split 변경 금지'
    # patch_ko_ui_text.py가 만든 비대상 보존 검사 보고서를 필수로 요구한다.
    report=json.loads((a.apk_dir/'report.json').read_text(encoding='utf-8'))
    assert expected==report['output']
    installed=adb('install-multiple','-r',*[str(a.apk_dir/n) for n in sorted(old)])
    (a.apk_dir/'install.log').write_bytes(installed)
    assert b'Success' in installed,installed.decode(errors='replace')
    actual=remote();assert actual==expected,'설치 후 APK 해시 불일치'
    (a.apk_dir/'device-check.json').write_text(json.dumps({'source':old,'expected':expected,'installed':actual,'apk_hashes_match':True},indent=1)+'\n',encoding='utf-8')
    print('Success: 설치 APK 4/4 SHA-256 일치')

if __name__=='__main__':main()

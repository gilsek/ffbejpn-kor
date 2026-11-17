"""기기를 변경하지 않고 설치 APK·번역 사전·시작 로그를 검증한다."""
import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--serial',required=True)
    ap.add_argument('--apk-dir',type=Path,required=True)
    ap.add_argument('--require-startup',action='store_true',help='시작 로그가 버퍼에 남아 있어야 통과')
    a=ap.parse_args()
    def adb(*args):
        return subprocess.check_output(['adb','-s',a.serial,*args],encoding='utf-8',errors='replace')
    expected=json.loads((a.apk_dir/'engine-check.json').read_text(encoding='utf-8'))
    paths=[s.removeprefix('package:') for s in adb('shell','pm','path','com.exvius.jpkorean.app').splitlines()]
    assert len(paths)==4,'설치 APK 분할 수 불일치'
    hashes={}
    for remote in paths:
        name=Path(remote).stem
        digest=adb('shell','sha256sum',remote).split()[0]
        assert digest==expected['output'][name],(name,'기기 APK 해시 불일치')
        hashes[name]=digest
    with zipfile.ZipFile(a.apk_dir/'base.apk') as z:
        with zipfile.ZipFile(io.BytesIO(z.read('assets/chaquopy/app.imy'))) as app:
            for name,digest in expected['overlay'].items():
                assert hashlib.sha256(app.read(name)).hexdigest()==digest,name
            mapping=json.loads(app.read('jp_monster_skills_ko.json'))
    with zipfile.ZipFile(a.apk_dir/'split_config.arm64_v8a.apk') as z:
        native=hashlib.sha256(z.read('lib/arm64-v8a/libgame.so')).hexdigest()
    assert native=='54ef0fe9a5c160254654a741bd8a3791e83bac80f7ece8c806af589e8fa1184e','원본 네이티브 해시 불일치'
    pid=adb('shell','pidof','com.exvius.jpkorean.app').strip()
    assert pid.isdigit(),'앱 PID 확인 실패'
    raw=adb('logcat','-d','--pid='+pid)
    lines=[line for line in raw.splitlines() if 'JP_KOREAN monster-' in line]
    startup=any('JP_KOREAN monster-skill ids='+str(len(mapping)) in line for line in lines)
    if a.require_startup:assert startup,'현재 PID 번역 사전 로드 로그 없음(버퍼 순환 여부 확인)'
    fatal=[line for line in raw.splitlines() if 'FATAL EXCEPTION' in line or 'Fatal signal' in line]
    assert not fatal,'현재 PID 크래시 로그 존재'
    report={'pid':pid,'apk_hashes':hashes,'overlay':expected['overlay'],'native_sha256':native,
            'translated_ids':len(mapping),'fatal_lines_in_available_buffer':len(fatal),
            'startup_log_available':startup,'startup_lines':lines}
    (a.apk_dir/'device-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    if lines:(a.apk_dir/'startup-filtered.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('PASS: 설치 APK 4/4 해시, 엔진 2파일, 원본 libgame, 사전',len(mapping),'ID; 현재 버퍼 크래시 로그 0')
    if not startup:print('제한: 현재 PID 시작 로그는 버퍼에 없음. 이 검사를 위해 앱을 재시작하지 않는다.')

if __name__=='__main__':main()

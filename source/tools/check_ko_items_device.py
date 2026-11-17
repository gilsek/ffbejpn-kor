"""기기 아이템 패치 파일을 읽기만 하여 로컬 SHA-256과 대조한다."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PKG = 'com.exvius.jpkorean.app'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial',required=True)
    ap.add_argument('--report',type=Path,default=ROOT/'build/out/ko_items/check.json',help='검증 완료 마스터 보고서')
    args = ap.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    results = {}
    def adb(*tail):
        return subprocess.run(['adb','-s',args.serial,*tail],capture_output=True,check=True).stdout
    for table, row in report['tables'].items():
        filename = row['file']
        remote = adb('exec-out','cat','/data/local/tmp/ffbe/mst_ko/'+filename)
        assert hashlib.sha256(remote).hexdigest() == row['sha256'], table+' sidecar'
        # 아직 앱이 설치하지 않은 표는 sidecar만 검사하고 명확히 구분한다.
        exists = adb('shell',f'run-as {PKG} sh -c \'if [ -f files/{filename} ]; then echo present; fi\'').strip()==b'present'
        if exists:
            installed = adb('exec-out','run-as',PKG,'cat','files/'+filename)
            assert hashlib.sha256(installed).hexdigest() == row['sha256'],table+' installed'
        results[table] = {'file':filename,'bytes':len(remote),'sha256':row['sha256'],
                          'sidecar_matches':True,'installed_matches':True if exists else None}
        print(table,'sidecar OK,', 'installed OK' if exists else '미설치', flush=True)
    out = args.report.parent/'device-check.json'
    out.write_text(json.dumps(results,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('PASS:',len(results),'개 표 기기 해시 검사')


if __name__ == '__main__': main()

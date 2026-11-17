"""검수된 image_gen 원본을 앱 프레임 크기로 정규화하고 고정 UI 목록에 연결한다.

이미지 디자인 수정은 하지 않는다. PowerShell/System.Drawing은 배포용 크기 변환만 한다.
실행: python -I -X utf8 build/apply_ko_generated_ui.py
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KO = ROOT / 'translations/ui-ko/sprites'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    rows = json.loads((KO / 'generated_manifest.json').read_text(encoding='utf-8'))
    out = ROOT / 'build/out/ko_ui_generated/prepared'
    out.mkdir(parents=True, exist_ok=True)
    fit = []
    for r in rows:
        for key in ('source', 'generated'):
            assert sha(KO / r[key]) == r[key + '_sha256'], (r['name'], key)
        fit.append(dict(r, source=str(KO/r['source']), generated=str(KO/r['generated']),
                        output=str(out/r['name'])))
    manifest = out / 'fit.json'
    manifest.write_text(json.dumps(fit, ensure_ascii=False, indent=1), encoding='utf-8')
    subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT/'tools/prepare_ko_generated_ui.ps1'),
                    '-Manifest', str(manifest)], check=True, cwd=ROOT)
    # PIL은 출력 크기/알파 검사에만 사용하며 픽셀을 편집하지 않는다.
    from PIL import Image
    pin_path = KO / 'labels_manifest.json'
    pinned = json.loads(pin_path.read_text(encoding='utf-8'))
    backup = KO / 'generated/previous_labels'
    backup.mkdir(exist_ok=True)
    for r in rows:
        target = KO / 'labels' / r['name']
        if target.exists() and sha(target) != sha(out/r['name']):
            shutil.copyfile(target, backup/(target.stem+'-'+sha(target)[:12]+'.png'))
        with Image.open(out/r['name']) as im:
            assert list(im.size) == r['size'], r['name']
            assert im.mode == 'RGBA' and im.getchannel('A').getextrema()[0] == 0, r['name']
        shutil.copyfile(out/r['name'], target)
        pinned[r['name']] = {'translation':r['translation'], 'sha256':sha(target),
                             'method':'image_gen', 'generated_source':r['generated']}
    pin_path.write_text(json.dumps(pinned, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
    print('PASS: 생성 이미지', len(rows), '연결, 전체 고정', len(pinned))


if __name__ == '__main__':
    main()

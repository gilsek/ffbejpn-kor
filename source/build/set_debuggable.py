"""base.apk 매니페스트의 android:debuggable 값만 바꾼 APK 세트를 만든다.

usage: python -I -X utf8 build/set_debuggable.py --source build/out/jp_shop/k1-apk --out build/out/jp_shop/k1nd-apk --value false
- 플레이용: false. 영문판 Offline과 같다. debuggable이면 ART가 CheckJNI·디버그 모드로 돌아
  로그인→홈 마스터 로딩(LoginScene::procStateMstLoad)이 18.1초, false면 8.5~8.9초(2026-11-10 실기기).
- 개발용: true. run-as(표·세이브 복사)가 필요할 때. 같은 키로 서명하므로 install-multiple -r로 오가도 데이터가 남는다.
바이너리 AndroidManifest.xml의 속성 값(4바이트)만 바꾸고, 다른 base 항목·split은 그대로인지 확인한다.
"""
import argparse, shutil, struct, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jp_offline_build as B  # noqa: E402

DEBUGGABLE = 0x0101000f


def flip(m, value):
    m = bytearray(m)
    pos, resmap, hits = 8, [], 0
    while pos < len(m):
        typ, _, size = struct.unpack_from('<HHI', m, pos)
        if typ == 0x0180:                       # resource map
            resmap = list(struct.unpack_from('<%dI' % ((size - 8) // 4), m, pos + 8))
        elif typ == 0x0102:                     # start element
            astart, asize, acount = struct.unpack_from('<HHH', m, pos + 24)
            for k in range(acount):
                a = pos + 16 + astart + k * asize
                name = struct.unpack_from('<I', m, a + 4)[0]
                if name < len(resmap) and resmap[name] == DEBUGGABLE:
                    assert m[a + 15] == 0x12, 'boolean 아님'
                    struct.pack_into('<I', m, a + 16, 0xFFFFFFFF if value else 0)
                    hits += 1
        pos += size
    assert hits == 1, hits
    return bytes(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--value', choices=['true', 'false'], required=True)
    a = ap.parse_args()
    assert a.source.resolve() != a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    unsigned = a.out / 'base-unsigned.apk'
    with zipfile.ZipFile(a.source / 'base.apk') as z, zipfile.ZipFile(unsigned, 'w') as w:
        for i in z.infolist():
            if i.filename.startswith('META-INF/') and i.filename.rsplit('.', 1)[-1].upper() in ('MF', 'SF', 'RSA', 'DSA', 'EC'):
                continue
            data = z.read(i.filename)
            w.writestr(i, flip(data, a.value == 'true') if i.filename == 'AndroidManifest.xml' else data)
    B.align_sign(unsigned, a.out / 'base.apk')
    same = 0
    with zipfile.ZipFile(a.source / 'base.apk') as old, zipfile.ZipFile(a.out / 'base.apk') as new:
        for n in old.namelist():
            if n == 'AndroidManifest.xml' or n.startswith('META-INF/'):
                continue
            assert old.read(n) == new.read(n), n
            same += 1
    for p in a.source.glob('split_*.apk'):
        shutil.copyfile(p, a.out / p.name)
    print('PASS: debuggable =', a.value, '| base 같은 항목', same, '| split', len(list(a.out.glob('split_*.apk'))))


if __name__ == '__main__':
    main()

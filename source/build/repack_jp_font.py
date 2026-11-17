"""Replace only the two game fonts in a copy of the installed APK set (same files jp_offline_build.apply_ko_font writes).

python -I -X utf8 build/repack_jp_font.py --source <dir with the 4 installed APKs> --out <new dir>
Everything else in base.apk is copied byte for byte; the three splits are copied unchanged.
"""
import argparse, json, re, shutil, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jp_offline_build as B

FONTS = ('assets/font/TT_RodinCattleya-B.ttf', 'assets/font/FOT-SkipStd-E.otf')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--source', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    src, out = a.source.resolve(), a.out.resolve()
    assert src != out
    out.mkdir(parents=True, exist_ok=True)
    font = B.KO_FONT.read_bytes()
    unsigned = out / 'base-font-unsigned.apk'
    with zipfile.ZipFile(src / 'base.apk') as z, zipfile.ZipFile(unsigned, 'w') as t:
        names = z.namelist()
        assert all(f in names for f in FONTS)
        for info in z.infolist():
            if re.fullmatch(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))', info.filename, re.I):
                continue
            t.writestr(info, font if info.filename in FONTS else z.read(info.filename))
    B.align_sign(unsigned, out / 'base.apk'); unsigned.unlink()
    for p in ('split_config.arm64_v8a', 'split_config.ja', 'split_config.xhdpi'):
        shutil.copyfile(src / f'{p}.apk', out / f'{p}.apk')
    same = 0
    with zipfile.ZipFile(src / 'base.apk') as old, zipfile.ZipFile(out / 'base.apk') as new:
        for n in old.namelist():
            if n in FONTS or n.startswith('META-INF/'):
                continue
            assert old.read(n) == new.read(n), n; same += 1
        assert all(new.read(f) == font for f in FONTS)
    print(json.dumps({'base_entries_unchanged': same, 'fonts_replaced': list(FONTS), 'font_bytes': len(font)}))


if __name__ == '__main__':
    main()

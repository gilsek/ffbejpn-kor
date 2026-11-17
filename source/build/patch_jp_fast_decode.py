"""로그인 마스터 로딩 복호화를 빠르게: LapisJNI 복호화 2개를 com.exvius.jp.FastDecode 로 연결한다.

usage: python -I -X utf8 build/patch_jp_fast_decode.py --source build/out/jp_shop/k1-apk --out build/out/jp_shop/f2-apk
근거(2026-11-10 실기기, debuggable=false): LoginScene::procStateMstLoad 9.1초 중
  decodeFileForBase64WithNewCrypto 3.8초(파일 123개) + decodeCStringForBase64WithNewCrypto 1.5초(46,129줄), JSON 해석 2.7초.
원본 Java 는 줄마다 Cipher.getInstance + init 을 하고 base64 를 String.charAt 으로 푼다. FastDecode 는 같은 키·IV면
Cipher 를 재사용한다. 결과 동일성: build/java/test/FastDecodeCheck.java (JP 마스터 170개 파일 539,540줄 일치).
1. build/java/com/exvius/jp/FastDecode.java -> javac(--release 8) -> d8 -> base.apk classes6.dex(새로 추가)
2. apktool d -r 로 classes.dex 만 다시 만들고 LapisJNI 의 두 메서드 본문을 FastDecode 호출로 바꾼다.
   Lapis.onCreate 에 FastDecode.prefetch(this) 를 넣는다(느렸던 파일을 백그라운드에서 미리 복호화).
3. base.apk 에서 classes.dex 교체, classes6.dex 추가. 다른 항목·split 은 그대로인지 확인.
"""
import argparse, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jp_offline_build as B  # noqa: E402

ROOT = B.ROOT
SRC = ROOT / 'build/java/com/exvius/jp/FastDecode.java'
ANDROID_JAR = Path.home() / 'AppData/Local/Android/Sdk/platforms/android-36/android.jar'
SIG = 'Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;'
METHODS = {
    f'public static decodeCStringForBase64WithNewCrypto({SIG})Ljava/lang/String;': 'line',
    f'public static decodeFileForBase64WithNewCrypto({SIG})Ljava/lang/String;': 'file',
}
NL = '\n'
ONCREATE = ('.method protected onCreate(Landroid/os/Bundle;)V' + NL + '    .locals 2' + NL + NL +
            '    invoke-super {p0, p1}, Lorg/cocos2dx/lib/Cocos2dxActivity;->onCreate(Landroid/os/Bundle;)V' + NL)
PREFETCH = NL + '    invoke-static {p0}, Lcom/exvius/jp/FastDecode;->prefetch(Landroid/content/Context;)V' + NL


def run(cmd):
    print('$', ' '.join(map(str, cmd))[:200], flush=True)
    subprocess.run([str(c) for c in cmd], check=True, shell=str(cmd[0]).endswith('.bat'))


def body(target):
    return ('    .locals 1\n'
            f'    invoke-static {{p0, p1, p2}}, Lcom/exvius/jp/FastDecode;->{target}({SIG})Ljava/lang/String;\n'
            '    move-result-object v0\n'
            '    return-object v0')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    assert a.source.resolve() != a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1. FastDecode -> dex
        (tmp / 'cls').mkdir()
        run(['javac', '-encoding', 'UTF-8', '--release', '8', '-classpath', ANDROID_JAR, '-d', tmp / 'cls', SRC])
        (tmp / 'dex').mkdir()
        run([B.SDK / 'd8.bat', '--release', '--min-api', '26', '--lib', ANDROID_JAR, '--output', tmp / 'dex',
             *sorted((tmp / 'cls').rglob('*.class'))])
        new_dex = (tmp / 'dex/classes.dex').read_bytes()
        # 2. LapisJNI 메서드 교체 + Lapis.onCreate 미리 복호화 시작, classes.dex 재조립
        run(['java', '-jar', B.APKTOOL, 'd', '-r', '-f', '-o', tmp / 'dec', a.source / 'base.apk'])
        lapis = tmp / 'dec/smali' / B.JPP / 'LapisJNI.smali'
        t = lapis.read_text(encoding='utf-8')
        assert 'Lcom/exvius/jp/FastDecode;' not in t, '이미 적용됨'
        for sig, target in METHODS.items():
            t = B.replace_method(t, sig, body(target))
        lapis.write_text(t, encoding='utf-8')
        act = tmp / 'dec/smali' / B.JPP / 'Lapis.smali'
        t = act.read_text(encoding='utf-8')
        assert t.count(ONCREATE) == 1, 'Lapis.onCreate 첫 부분이 예상과 다름'
        act.write_text(t.replace(ONCREATE, ONCREATE + PREFETCH), encoding='utf-8')
        run(['java', '-jar', B.APKTOOL, 'b', tmp / 'dec', '-o', tmp / 'rebuilt.apk'])
        with zipfile.ZipFile(tmp / 'rebuilt.apk') as z:
            main_dex = z.read('classes.dex')
        # 3. base.apk 조립
        unsigned = a.out / 'base-unsigned.apk'
        with zipfile.ZipFile(a.source / 'base.apk') as z, zipfile.ZipFile(unsigned, 'w') as w:
            names = z.namelist()
            assert 'classes6.dex' not in names and 'classes5.dex' in names, names
            for i in z.infolist():
                if i.filename.startswith('META-INF/') and i.filename.rsplit('.', 1)[-1].upper() in ('MF', 'SF', 'RSA', 'DSA', 'EC'):
                    continue
                w.writestr(i, main_dex if i.filename == 'classes.dex' else z.read(i.filename))
            info = zipfile.ZipInfo('classes6.dex', date_time=z.getinfo('classes5.dex').date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            w.writestr(info, new_dex)
    B.align_sign(unsigned, a.out / 'base.apk')
    same = 0
    with zipfile.ZipFile(a.source / 'base.apk') as old, zipfile.ZipFile(a.out / 'base.apk') as new:
        for n in old.namelist():
            if n == 'classes.dex' or n.startswith('META-INF/'):
                continue
            assert old.read(n) == new.read(n), n
            same += 1
        assert old.read('classes.dex') != new.read('classes.dex')
    for p in a.source.glob('split_*.apk'):
        shutil.copyfile(p, a.out / p.name)
    print('PASS: classes.dex LapisJNI 2개 메서드 교체 + Lapis.onCreate prefetch, classes6.dex(FastDecode) 추가 | base 같은 항목', same)


if __name__ == '__main__':
    main()

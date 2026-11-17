"""Build the distribution APK (one universal file, no splits) in one run.

    jp_offline_build.py --release (downloader/launcher/debuggable off/Frida embedded,
                                   xhdpi split resources folded in, native libs in the base)
    -> patch_jp_fast_decode.py (JP master decode speedup)
    -> strip old signature, zipalign -P 16 (16 KB pages)
    -> apksigner with D:\\Util\\exvius-kr-release\\exvius-kr-release.jks (password only from
       EXVIUS_KR_KS_PASS, never written to disk or the command line)
    -> checks: no /data/local/tmp strings, no debuggable, .so stored uncompressed,
       original libgame.so hash, embedded Frida bundle byte-identical,
       launcher is DataDownloadActivity, no split attributes/meta-data,
       badging = com.exvius.offline.jpkr / RELEASE_VERSION_CODE / RELEASE_VERSION_NAME / Exvius KR / arm64-v8a.

The result is ExviusKR-<version>.apk (ExviusKR-v0.1.0.apk) in build/out/release_apk/<version>[/ -debugkey].

If EXVIUS_KR_KS_PASS is not set, the same pipeline signs with the debug keystore and writes a
separate trial APK (v0.1.0-debugkey) so every other check still runs.

usage: python -I -X utf8 build/build_release_apk.py [--manifest-url URL] [--assets-prefix PREFIX]
                                                   [--out DIR] [--skip-build]
"""
import argparse
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jp_offline_build as B  # noqa: E402
import deploy_jp_frida as FRIDA  # noqa: E402

ROOT = B.ROOT
BUILD = ROOT / 'build'
SDK = B.SDK
DIST = B.DIST
RELEASE_DIR = ROOT / 'build/out/release_apk'
VERSION = 'v' + B.RELEASE_VERSION_NAME
KEYSTORE = Path('D:/Util/exvius-kr-release/exvius-kr-release.jks')
KEY_ALIAS = 'exvius-kr'
DEBUG_KS = Path.home() / '.android/debug.keystore'
ANDROID_NS = '{http://schemas.android.com/apk/res/android}'
DEBUGGABLE_ID = 0x0101000f


def run(cmd, **kw):
    print('$', ' '.join(map(str, cmd))[:240], flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_entry(apk, name):
    with zipfile.ZipFile(apk) as archive:
        return hashlib.sha256(archive.read(name)).hexdigest()


def manifest_debuggable(data):
    """Return True/False for android:debuggable in a binary manifest, or None when absent."""
    pos, resmap, value = 8, [], None
    while pos + 8 <= len(data):
        typ, header, size = struct.unpack_from('<HHI', data, pos)
        if size == 0:
            break
        if typ == 0x0180:
            resmap = list(struct.unpack_from('<%dI' % ((size - 8) // 4), data, pos + 8))
        elif typ == 0x0102:
            astart, asize, acount = struct.unpack_from('<HHH', data, pos + 24)
            for k in range(acount):
                attribute = pos + 16 + astart + k * asize
                name = struct.unpack_from('<I', data, attribute + 4)[0]
                if name < len(resmap) and resmap[name] == DEBUGGABLE_ID:
                    assert data[attribute + 15] == 0x12, 'debuggable is not a boolean'
                    value = struct.unpack_from('<I', data, attribute + 16)[0] != 0
        pos += size
    return value


def strip_signature(source, target):
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(target, 'w') as out:
        for info in archive.infolist():
            if info.filename.startswith('META-INF/') and \
                    info.filename.rsplit('.', 1)[-1].upper() in ('MF', 'SF', 'RSA', 'DSA', 'EC'):
                continue
            entry = zipfile.ZipInfo(info.filename, info.date_time)
            entry.compress_type = info.compress_type
            entry.external_attr = info.external_attr
            out.writestr(entry, archive.read(info.filename))


def sign_set(stage, out_dir, release_password):
    """Sign the single universal APK (no split set) and drop it in out_dir as ExviusKR-<version>.apk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in sorted(out_dir.glob('*.apk')) + sorted(out_dir.glob('*.idsig')):
        old.unlink()   # a previous split set must not sit next to the universal APK
        print('removed stale:', old.name, flush=True)
    apk = stage / 'base.apk'
    if not apk.is_file():
        raise SystemExit(f'{apk} missing from the stage')
    produced = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        unsigned = tmp / 'universal-unsigned.apk'
        aligned = tmp / 'universal-aligned.apk'
        final = out_dir / f'ExviusKR-{VERSION}.apk'
        strip_signature(apk, unsigned)
        run([SDK / 'zipalign.exe', '-f', '-P', '16', '4', unsigned, aligned])
        common = ['sign', '--v4-signing-enabled', 'false', '--out', final]
        if release_password:
            run([SDK / 'apksigner.bat'] + common + ['--ks', KEYSTORE, '--ks-key-alias', KEY_ALIAS,
                                                     '--ks-pass', 'env:EXVIUS_KR_KS_PASS', aligned],
                env=os.environ.copy())
        else:
            run([SDK / 'apksigner.bat'] + common + ['--ks', DEBUG_KS, '--ks-pass', 'pass:android',
                                                     '--key-pass', 'pass:android', aligned])
        produced.append(final)
        print('signed:', final.name)
    return produced


def read_manifest(base_apk):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # -s (skip dex) but decode resources so AndroidManifest.xml comes out as text.
        run(['java', '-jar', B.APKTOOL, 'd', '-s', '-f', '-o', tmp / 'dec', base_apk])
        manifest = ET.parse(tmp / 'dec/AndroidManifest.xml').getroot()
        yml = (tmp / 'dec/apktool.yml').read_text(encoding='utf-8')
    return manifest, yml


def launcher_activities(manifest):
    found = set()
    for activity in manifest.iter('activity'):
        for intent in activity.findall('intent-filter'):
            actions = {a.get(ANDROID_NS + 'name') for a in intent.findall('action')}
            categories = {c.get(ANDROID_NS + 'name') for c in intent.findall('category')}
            if 'android.intent.action.MAIN' in actions and 'android.intent.category.LAUNCHER' in categories:
                found.add(activity.get(ANDROID_NS + 'name'))
    return found


import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('rename_package', Path(__file__).resolve().parent / 'rename_package.py')
RENAME = _ilu.module_from_spec(_spec); _spec.loader.exec_module(RENAME)

def check(apk):
    """Same acceptance set as the old split-set check, now against the one universal APK."""
    errors = []
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            name = info.filename
            if not name.lower().endswith(('.dex', '.so', '.xml')):
                continue
            if b'/data/local/tmp' in archive.read(name):
                errors.append(f'{name} contains /data/local/tmp')
        libs = [i for i in archive.infolist() if i.filename.startswith('lib/arm64-v8a/')]
        if not libs:
            errors.append('lib/arm64-v8a/ is missing from the universal APK')
        for info in libs:
            # extractNativeLibs="false" + 16 KB pages: the .so entries must be uncompressed.
            if info.compress_type != zipfile.ZIP_STORED:
                errors.append(f'{info.filename} is compressed, expected ZIP_STORED')
        value = manifest_debuggable(archive.read('AndroidManifest.xml'))
        if value is not None:
            errors.append(f'android:debuggable={value} is still present')
        # libgame.so must stay byte-identical to the JP original split.
        orig = B.OUT / 'orig/split_config.arm64_v8a.apk'
        try:
            if sha256_zip_entry(apk, 'lib/arm64-v8a/libgame.so') != sha256_zip_entry(orig, 'lib/arm64-v8a/libgame.so'):
                errors.append('libgame.so differs from the original split')
        except KeyError as exc:
            errors.append(f'libgame.so missing: {exc}')
        bundle = FRIDA.build_bundle(release=True).encode('utf-8')
        try:
            if archive.read('lib/arm64-v8a/libexviustest.js.so') != bundle:
                errors.append('embedded Frida bundle differs from deploy_jp_frida.build_bundle(release=True)')
        except KeyError:
            errors.append('lib/arm64-v8a/libexviustest.js.so missing')
        raw = archive.read('AndroidManifest.xml')
    version = RENAME.get_version_code(raw)
    if version != B.RELEASE_VERSION_CODE:
        errors.append(f'versionCode {version}, expected {B.RELEASE_VERSION_CODE}')
    if FRIDA.DEV_PKG.encode('utf-16-le') in raw or FRIDA.DEV_PKG.encode('utf-8') in raw:
        errors.append('manifest still names the dev package ' + FRIDA.DEV_PKG)
    manifest, yml = read_manifest(apk)
    if manifest.get('package') != FRIDA.RELEASE_PKG:
        errors.append(f'package is {manifest.get("package")}, expected {FRIDA.RELEASE_PKG}')
    for attr in ('requiredSplitTypes', 'splitTypes'):
        if manifest.get(ANDROID_NS + attr) is not None:
            errors.append(f'manifest still declares android:{attr}')
    for meta in manifest.iter('meta-data'):
        if meta.get(ANDROID_NS + 'name') in ('com.android.vending.splits', 'com.android.vending.splits.required'):
            errors.append(f'manifest still declares {meta.get(ANDROID_NS + "name")}')
    found = launcher_activities(manifest)
    if found != {'com.exvius.local.DataDownloadActivity'}:
        errors.append(f'launcher activities are {sorted(found)}')
    if not any(a.get(ANDROID_NS + 'name') == 'com.square_enix.ffbejpn.Lapis' for a in manifest.iter('activity')):
        errors.append('Lapis activity was removed')
    if not any(s.get(ANDROID_NS + 'name') == 'com.exvius.local.DataDownloadService' for s in manifest.iter('service')):
        errors.append('DataDownloadService is not declared')
    code = re.search(r'versionCode:\s*(\d+)', yml)
    name = re.search(r'versionName:\s*(\S+)', yml)
    if not code or int(code.group(1)) != B.RELEASE_VERSION_CODE:
        errors.append(f'versionCode is {code.group(1) if code else "?"}, expected {B.RELEASE_VERSION_CODE}')
    if not name or name.group(1) != B.RELEASE_VERSION_NAME:
        errors.append(f'versionName is {name.group(1) if name else "?"}, expected {B.RELEASE_VERSION_NAME}')
    # Badging: package / version / label / no split types / arm64 native code.
    badging = subprocess.run([str(SDK / 'aapt2.exe'), 'dump', 'badging', str(apk)],
                             capture_output=True, check=True)
    text = badging.stdout.decode('utf-8', 'replace')
    for pattern, what in (
            (r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", 'package line'),
            (r"application-label:'([^']+)'", 'application-label'),
            (r"native-code: '([^']+)'", 'native-code')):
        m = re.search(pattern, text)
        if not m:
            errors.append(f'badging has no {what}')
        elif what == 'package line':
            if m.group(1) != FRIDA.RELEASE_PKG or int(m.group(2)) != B.RELEASE_VERSION_CODE or m.group(3) != B.RELEASE_VERSION_NAME:
                errors.append(f'badging package/version: {m.group(1)} {m.group(2)} {m.group(3)}')
        elif what == 'application-label':
            if m.group(1) != 'Exvius KR':
                errors.append(f'badging label is {m.group(1)!r}, expected Exvius KR')
        else:
            if 'arm64-v8a' not in m.group(1).split():
                errors.append(f'badging native-code is {m.group(1)!r}, expected arm64-v8a')
    for line in text.splitlines():
        if line.startswith(('split-types', 'required-split-types', 'provides-split')):
            errors.append('badging still reports ' + line)
    if errors:
        for error in errors:
            print('FAIL:', error, flush=True)
        raise SystemExit(1)
    print(f'PASS: 단일 APK {apk.name} | 패키지 {FRIDA.RELEASE_PKG} / versionCode {B.RELEASE_VERSION_CODE} / label Exvius KR / '
          'native-code arm64-v8a, split 속성·meta-data 없음, /data/local/tmp 0건, debuggable 없음, .so 전부 STORED, '
          'libgame 원본 일치, Frida 묶음 일치, 런처 DataDownloadActivity', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-url')
    parser.add_argument('--assets-prefix')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--skip-build', action='store_true', help='reuse build/out/jp_offline/dist')
    args = parser.parse_args()
    password = os.environ.get('EXVIUS_KR_KS_PASS')
    release = bool(password)
    out_dir = args.out or (RELEASE_DIR / (VERSION if release else VERSION + '-debugkey'))
    cleartext = any(v and v.startswith('http://') for v in (args.manifest_url, args.assets_prefix))

    if not args.skip_build:
        cmd = [sys.executable, '-I', str(BUILD / 'jp_offline_build.py'), '--release']
        if args.manifest_url:
            cmd += ['--manifest-url', args.manifest_url]
        if args.assets_prefix:
            cmd += ['--assets-prefix', args.assets_prefix]
        if cleartext:
            cmd += ['--allow-cleartext']
        run(cmd)

    stage = RELEASE_DIR / '_stage'
    if stage.exists():
        shutil.rmtree(stage)
    run([sys.executable, '-I', '-X', 'utf8', str(BUILD / 'patch_jp_fast_decode.py'),
         '--source', DIST, '--out', stage])
    # patch_jp_fast_decode copies split_*.apk verbatim; a distribution stage is base-only.
    for stale in sorted(stage.glob('split_*.apk')):
        stale.unlink()
        print('removed stale stage split:', stale.name, flush=True)

    if release:
        if not KEYSTORE.is_file():
            raise SystemExit(f'release keystore not found: {KEYSTORE}')
        print('release signing key:', KEYSTORE, '| key password from EXVIUS_KR_KS_PASS', flush=True)
    else:
        print('EXVIUS_KR_KS_PASS is not set: building the debug-key trial APK in', out_dir, flush=True)
    apks = sign_set(stage, out_dir, password)
    if len(apks) != 1:
        raise SystemExit(f'expected exactly one universal APK, got {len(apks)}')
    check(apks[0])
    print('output:', out_dir, flush=True)
    for apk in apks:
        print(f'  {apk.name}: {apk.stat().st_size} bytes', flush=True)


if __name__ == '__main__':
    main()

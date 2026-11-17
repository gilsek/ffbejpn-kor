"""JP 한국어 오프라인 데이터 팩 생성기 (GitHub 릴리스용 zip + latest.json).

영문 Exvius Offline 의 build_release_data.py 구조를 따른다. 입력은 JP 원본 리소스
(D:/Downloads/ffbejpdata/ffbejpdata) 위에 한국어 대체본(맵/스토리/마스터)을 같은 이름으로
덮은 최종 세트, 엔진 static, UI 그림, gamedata.xml 에서 만든 registry 다.

zip 엔트리 규칙(앱과의 약속, 바꾸지 말 것):
  res/mst/<이름>      마스터 .dat (게임이 lapis/resource/mst/... 로 요청)
  res/flat/<이름>     그 밖의 원본 리소스(cpk/acb/usm 등)
  static/<경로>       엔진 static 사본
  ui_ko/<경로>        한국어 UI 그림 대체
  metadata/registry.json

사용 예:
  python -I -X utf8 build/build_release_data_jp.py --min-app-version-code 194
"""

import argparse
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('D:/Downloads/ffbejpdata/ffbejpdata')
KO_MAP = ROOT / 'build/out/ko_map/flat_ko'
KO_STORY = ROOT / 'build/out/ko_story/flat_ko'
KO_NAMES = ROOT / 'build/out/ko_names/mst_ko'
STATIC = ROOT / 'build/out/jp_offline/engine/static'
DEV_OVERLAY = ROOT / 'build/out/release/dev_overlay'
UI = ROOT / 'translations/ui-ko/sprites/campaign_ui'
GAMEDATA = STATIC / 'client/shared_prefs/gamedata.xml'

DEFAULT_ASSETS = 'https://github.com/gilsek/ffbejpn-kor/releases/download'
NONGAME = {'ffbejpdata_meta.sqlite', 'ffbejpdata_meta.xml', 'ffbejpdata_files.xml'}
TEXT_EXT = ('.json', '.ndjson', '.xml', '.csv', '.txt', '.py')
MB = 1024 * 1024
PACK_RESERVE = 4 * MB


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * MB), b''):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(body):
    return hashlib.sha256(body).hexdigest()


def is_text(name):
    return name.lower().endswith(TEXT_EXT)


def check_name(name, violations):
    """zip 엔트리 경로 규칙: '/', 상대 경로, '..'·절대경로·드라이브 문자 금지."""
    if name.startswith('/') or name.startswith('\\') or ':' in name:
        violations.append(name)
    if '\\' in name:
        violations.append(name)
    if any(part in ('', '.', '..') for part in name.split('/')):
        violations.append(name)


def iter_files(base):
    for path in sorted(base.rglob('*')):
        if path.is_file() and not path.is_symlink():
            yield path


def add_entry(entries, seen, duplicates, name, source, size, sig):
    check_name(name, [])
    if name in seen:
        duplicates.append(name)
        return
    seen.add(name)
    entries.append({'name': name, 'source': source, 'size': size, 'sig': sig})


def file_entry(path):
    info = path.stat()
    return info.st_size, f'f:{info.st_size}:{info.st_mtime_ns}'


def build_plan(source):
    """최종 엔트리 목록과 점검용 통계를 만든다."""
    errors = []
    duplicates = []
    violations = []
    overlaps = []
    replaced_missing = []
    replaced = {'map': 0, 'story': 0, 'master': 0}

    if not source.is_dir():
        raise SystemExit(f'원본 폴더가 없습니다: {source}')
    for folder in (KO_MAP, KO_STORY, KO_NAMES, STATIC, UI, GAMEDATA):
        if not folder.exists():
            raise SystemExit(f'입력이 없습니다: {folder}')

    originals = {}
    excluded_i = 0
    excluded_nongame = 0
    for path in source.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name.lower().endswith('.i'):
            excluded_i += 1
            continue
        if name in NONGAME or name.lower().endswith('.torrent'):
            excluded_nongame += 1
            continue
        originals[name] = path

    # 한국어 대체본. zip 안에서는 원본과 같은 이름/자리를 차지한다.
    overrides = {}
    sources = (
        ('map', KO_MAP, '.cpk', 'res/flat/'),
        ('story', KO_STORY, '.cpk', 'res/flat/'),
        ('master', KO_NAMES, '.dat', 'res/mst/'),
    )
    for category, folder, suffix, prefix in sources:
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.suffix.lower() != suffix:
                continue
            name = path.name
            if name not in originals:
                replaced_missing.append(str(path))
                continue
            if name in overrides and overrides[name][0] != category:
                # 지금은 겹침이 없지만, 생기면 수정 시각이 새 것을 쓰고 크게 알린다.
                old = overrides[name][1]
                newer = path if path.stat().st_mtime_ns > old.stat().st_mtime_ns else old
                keep = 'story' if newer == path else 'map'
                overlaps.append({'name': name, 'kept': keep,
                                 'mapMtime': old.stat().st_mtime, 'storyMtime': path.stat().st_mtime})
                if newer != path:
                    continue
            overrides[name] = (category, path)
            replaced[category] += 1

    # 개발판 기기(/data/local/tmp/ffbe/mst_ko, flat_ko)에만 있던 덮어쓰기·추가 파일(버전 올린 마스터, 대체 장면 등).
    # 기기에서 받아 둔 사본이 가장 우선이고, 원본에 없는 새 이름도 넣는다(없으면 게임이 그 파일을 찾다 멈춘다).
    for sub, suffix in (('mst_ko', '.dat'), ('flat_ko', '.cpk')):
        folder = DEV_OVERLAY / sub
        if not folder.is_dir():
            raise SystemExit(f'입력이 없습니다: {folder}')
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() == suffix:
                if path.name not in originals:
                    originals[path.name] = path
                overrides[path.name] = ('dev', path)
                replaced['dev'] = replaced.get('dev', 0) + 1

    entries = []
    seen = set()
    # 앱은 res/mst/... 와 res/flat/... 를 기기 files/ 한 폴더에 평면으로 푼다.
    # 그러므로 res/ 전체에서 basename 이 겹치면 서로 덮어써 오류다.
    res_names = {}
    collisions = []
    for name in sorted(originals):
        if name.lower().endswith('.dat'):
            entry_name, prefix = 'res/mst/' + name, 'res/mst/'
        else:
            entry_name, prefix = 'res/flat/' + name, 'res/flat/'
        if name in res_names:
            collisions.append(f'{name} ({res_names[name]} vs {entry_name})')
        else:
            res_names[name] = entry_name
        chosen = overrides.get(name)
        path = chosen[1] if chosen else originals[name]
        check_name(entry_name, violations)
        size, sig = file_entry(path)
        add_entry(entries, seen, duplicates, entry_name, path, size, sig)

    # 게임은 버전을 올린 마스터·대체 장면을 '새로 받을 파일'로 요청하고, jp_offline.js localize()는
    # 그것을 files/ffbe/{mst_ko,flat_ko}/ 에서 복사해 온다(개발판 /data/local/tmp/ffbe/ 와 같은 구조).
    # 그래서 같은 파일을 그 경로에도 둔다. 기존 팩 경계를 흔들지 않게 pack_plan 이 맨 뒤 별도 팩으로 뺀다.
    for sub, suffix in (('mst_ko', '.dat'), ('flat_ko', '.cpk')):
        for path in sorted((DEV_OVERLAY / sub).iterdir()):
            if path.is_file() and path.suffix.lower() == suffix:
                name = f'ffbe/{sub}/{path.name}'
                check_name(name, violations)
                size, sig = file_entry(path)
                add_entry(entries, seen, duplicates, name, path, size, sig)

    # 개발판은 /data/local/tmp/ffbe/art/<basename> 이 배너 그림을 이긴다(jp_offline.js ART_DEV_OVERRIDE). 같은 규칙.
    dev_art = {p.name: p for p in (DEV_OVERLAY / 'art').iterdir() if p.is_file()} if (DEV_OVERLAY / 'art').is_dir() else {}
    for path in iter_files(STATIC):
        if path.name.endswith('.global'):  # apply_jp_masters.py 가 남긴 영문 원본 백업, 엔진은 읽지 않음
            continue
        name = 'static/' + path.relative_to(STATIC).as_posix()
        if path.name in dev_art and path.suffix.lower() == '.png':
            path = dev_art[path.name]
        check_name(name, violations)
        size, sig = file_entry(path)
        add_entry(entries, seen, duplicates, name, path, size, sig)

    # jp_ui_override.js reads ui_ko/index.txt + the images it lists (same set as deploy_ko_ui_override.py);
    # generator scripts and manifest.json in that folder are not shipped.
    ui_manifest = json.loads((UI / 'manifest.json').read_text(encoding='utf-8'))
    ui_index = ROOT / 'build/out/release/ui_ko_index.txt'
    ui_index.write_text(''.join(n + '\n' for n in ui_manifest), encoding='utf-8')
    for name_ui, path in [('index.txt', ui_index)] + [(n, UI / n) for n in ui_manifest]:
        name = 'ui_ko/' + name_ui
        check_name(name, violations)
        size, sig = file_entry(path)
        add_entry(entries, seen, duplicates, name, path, size, sig)

    # registry: gamedata.xml 의 keyF_* 만 (영문 생성기와 같은 형식).
    root = ET.parse(GAMEDATA).getroot()
    registry = {}
    for row in root:
        name = row.get('name', '')
        if not name.startswith('keyF_'):
            continue
        if row.tag != 'string':
            raise SystemExit(f'gamedata.xml 에 예상 밖 항목: {row.tag} {name}')
        registry[name] = row.text or ''
    body = json.dumps(registry, sort_keys=True).encode()
    check_name('metadata/registry.json', violations)
    add_entry(entries, seen, duplicates, 'metadata/registry.json', body, len(body),
              'b:' + sha256_bytes(body))

    stats = {
        'sourceFiles': len(originals),
        'excludedIndex': excluded_i,
        'excludedNonGame': excluded_nongame,
        'replaced': replaced,
        'replacedMissing': replaced_missing,
        'overlaps': overlaps,
        'registryKeys': len(registry),
        'resourceNameCollisions': collisions,
    }
    return entries, stats, duplicates, violations, errors


def pack_plan(entries, limit):
    """static/metadata 먼저, 그 뒤 res. 영문처럼 팩 상한에서 4MiB 를 남긴다."""
    extra = sorted((row for row in entries if row['name'].startswith('ffbe/')), key=lambda row: row['name'])
    ordered = sorted((row for row in entries if not row['name'].startswith('ffbe/')),
                     key=lambda row: (not row['name'].startswith(('static/', 'metadata/')), row['name']))
    packs = []
    current = []
    raw = 0
    for row in ordered:
        if row['size'] > limit - PACK_RESERVE:
            raise SystemExit(f'단일 파일이 팩 크기를 넘습니다: {row["name"]} ({row["size"]} bytes)')
        if current and raw + row['size'] > limit - PACK_RESERVE:
            packs.append(current)
            current = []
            raw = 0
        current.append(row)
        raw += row['size']
    if current:
        packs.append(current)
    if extra:  # 별도 팩(기존 팩 sha 유지). 69MB 수준이라 분할하지 않는다.
        if sum(row['size'] for row in extra) > limit - PACK_RESERVE:
            raise SystemExit('ffbe/ 별도 팩이 팩 크기를 넘습니다')
        packs.append(extra)
    return packs


def write_entry(archive, row):
    source = row['source']
    info = zipfile.ZipInfo(row['name'], date_time=(2000, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED if is_text(row['name']) else zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    with archive.open(info, 'w', force_zip64=True) as destination:
        if isinstance(source, Path):
            with source.open('rb') as stream:
                for block in iter(lambda: stream.read(MB), b''):
                    destination.write(block)
        else:
            destination.write(source)


def build(args):
    output = args.output
    required = 15 * 1024 ** 3
    anchor = output
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    free = shutil.disk_usage(str(anchor)).free
    if free < required:
        raise SystemExit(f'디스크 여유 부족: {free / 1e9:.1f} GB < 15 GB. 출력을 만들지 않았습니다: {output}')
    output.mkdir(parents=True, exist_ok=True)

    entries, stats, duplicates, violations, errors = build_plan(args.source)
    # 계획 단계에서 확정된 오류는 15GB 를 쓰기 전에 멈춘다. check.json 은 남긴다.
    plan_problems = (stats['resourceNameCollisions'] + stats['replacedMissing']
                     + sorted(set(duplicates)) + sorted(set(violations)))
    if plan_problems:
        check = {'ok': False, 'stage': 'plan', 'replaced': stats['replaced'],
                 'resourceNameCollisions': stats['resourceNameCollisions'],
                 'replacedMissing': stats['replacedMissing'],
                 'duplicateEntries': sorted(set(duplicates)),
                 'pathViolations': sorted(set(violations))}
        (output / 'check.json').write_text(json.dumps(check, indent=2) + '\n', encoding='utf-8')
        print('CHECK FAILED (plan): 팩을 만들지 않았습니다.', flush=True)
        for problem in plan_problems:
            print('  ' + str(problem), flush=True)
        return 1
    limit = args.pack_mib * MB
    packs = pack_plan(entries, limit)

    reuse = {}
    state_path = output / 'reuse_state.json'
    if args.reuse and state_path.is_file():
        for row in json.loads(state_path.read_text(encoding='utf-8')).get('packs', []):
            reuse[row['name']] = row

    base = args.base_url or (DEFAULT_ASSETS + '/' + args.tag)
    if not base.endswith('/'):
        base += '/'

    manifest = {'schema': 1, 'revision': args.revision, 'version': f'2026.11.17.{args.revision}',
                'minAppVersionCode': args.min_app_version_code, 'packs': []}
    check_packs = []
    new_state = []
    total_entries = 0

    for number, rows in enumerate(packs, 1):
        name = f'jpkr-data-{number:03d}.zip'
        target = output / name
        raw = sum(row['size'] for row in rows)
        sigs = [row['sig'] for row in rows]
        saved = reuse.get(name)
        if (saved and target.is_file() and saved.get('raw') == raw and saved.get('sigs') == sigs
                and (sha := sha256(target)) == saved.get('sha256')):
            print(f'Reused {name}: {target.stat().st_size / 1e6:.1f} MB', flush=True)
        else:
            with zipfile.ZipFile(target, 'w', allowZip64=True) as archive:
                for row in rows:
                    write_entry(archive, row)
            sha = sha256(target)
            print(f'Finished {name}: {target.stat().st_size / 1e6:.1f} MB, '
                  f'expanded {raw / 1e6:.1f} MB, {len(rows)} entries', flush=True)
        size = target.stat().st_size
        if size >= 2 * 1024 ** 3:
            errors.append(f'Pack exceeds 2 GiB: {name} ({size} bytes)')
        manifest['packs'].append({'id': 'data-' + str(number).zfill(3), 'url': base + name,
                                  'size': size, 'unpackedSize': raw, 'sha256': sha})
        check_packs.append({'name': name, 'entries': len(rows), 'size': size,
                            'unpackedSize': raw, 'sha256': sha})
        new_state.append({'name': name, 'raw': raw, 'sigs': sigs, 'sha256': sha})
        total_entries += len(rows)

    manifest['downloadBytes'] = sum(p['size'] for p in manifest['packs'])
    manifest['installedBytes'] = sum(p['unpackedSize'] for p in manifest['packs'])
    manifest['files'] = total_entries

    if args.app_apk:
        apk = Path(args.app_apk)
        if not apk.is_file():
            raise SystemExit(f'APK 가 없습니다: {apk}')
        if not args.app_version_code:
            raise SystemExit('--app-apk 에는 --app-version-code 가 필요합니다.')
        app = {'version': args.app_version, 'versionCode': args.app_version_code,
               'url': args.app_url or base + apk.name, 'size': apk.stat().st_size,
               'sha256': sha256(apk)}
        if args.app_version_name:
            app['versionName'] = args.app_version_name
        manifest['app'] = app

    # 자동 점검: 다시 열어 엔트리 수·unpackedSize·sha256 을 매니페스트와 대조.
    mismatches = []
    for pack, meta in zip(manifest['packs'], check_packs):
        target = output / pack['url'].rsplit('/', 1)[-1]
        try:
            with zipfile.ZipFile(target) as archive:
                infos = archive.infolist()
        except (OSError, zipfile.BadZipFile) as exc:
            mismatches.append(f'{meta["name"]}: 열기 실패 {exc}')
            continue
        if len(infos) != meta['entries']:
            mismatches.append(f'{meta["name"]}: 엔트리 {len(infos)} != {meta["entries"]}')
        expanded = sum(i.file_size for i in infos)
        if expanded != meta['unpackedSize']:
            mismatches.append(f'{meta["name"]}: unpackedSize {expanded} != {meta["unpackedSize"]}')
        if sha256(target) != meta['sha256']:
            mismatches.append(f'{meta["name"]}: sha256 불일치')
    errors.extend(mismatches)

    total_bytes = manifest['installedBytes']
    collisions = stats['resourceNameCollisions']
    check = {
        'ok': not (errors or duplicates or violations or stats['replacedMissing'] or collisions),
        'totalEntries': total_entries,
        'totalBytes': total_bytes,
        'packs': check_packs,
        'replaced': stats['replaced'],
        'replacedTotal': sum(stats['replaced'].values()),
        'replacedMissing': stats['replacedMissing'],
        'overlaps': stats['overlaps'],
        'sourceFiles': stats['sourceFiles'],
        'excluded': {'index': stats['excludedIndex'], 'nonGame': stats['excludedNonGame']},
        'duplicateEntries': sorted(set(duplicates)),
        'pathViolations': sorted(set(violations)),
        'resourceNameCollisions': collisions,
        'registryKeys': stats['registryKeys'],
        'manifestMismatches': mismatches,
        'errors': errors,
    }

    (output / 'latest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'check.json').write_text(json.dumps(check, indent=2) + '\n', encoding='utf-8')
    if args.reuse:
        state_path.write_text(json.dumps({'packs': new_state}, indent=1) + '\n', encoding='utf-8')

    print(f'Complete: {total_entries} entries, {len(manifest["packs"])} packs, '
          f'{total_bytes / 1e9:.2f} GB installed, {manifest["downloadBytes"] / 1e9:.2f} GB download',
          flush=True)
    print(f'Korean replacements: map {stats["replaced"]["map"]}, '
          f'story {stats["replaced"]["story"]}, master {stats["replaced"]["master"]} '
          f'(total {sum(stats["replaced"].values())})', flush=True)
    print(f'Excluded: .i {stats["excludedIndex"]}, non-game {stats["excludedNonGame"]}; '
          f'duplicates {len(check["duplicateEntries"])}; path violations {len(check["pathViolations"])}; '
          f'res name collisions {len(collisions)}',
          flush=True)
    if stats['overlaps']:
        print(f'Overlap between ko_map and ko_story resolved by mtime: {stats["overlaps"]}', flush=True)
    if check['ok']:
        print('CHECK OK', flush=True)
    else:
        print('CHECK FAILED', flush=True)
        for problem in errors + check['duplicateEntries'] + check['pathViolations'] + stats['replacedMissing'] + collisions:
            print('  ' + str(problem), flush=True)
    return 0 if check['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description='JP 한국어 오프라인 데이터 팩 생성')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/out/release/v0.1.0')
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--tag', default='v0.1.0')
    parser.add_argument('--base-url', default=None,
                        help='URL 접두 (기본 https://github.com/gilsek/ffbejpn-kor/releases/download/<tag>/)')
    parser.add_argument('--revision', type=int, default=1)
    parser.add_argument('--min-app-version-code', type=int, required=True)
    parser.add_argument('--pack-mib', type=int, default=1400)
    parser.add_argument('--reuse', action='store_true',
                        help='reuse_state.json 과 내용 서명이 같은 팩은 다시 압축하지 않는다')
    parser.add_argument('--app-apk', default=None)
    parser.add_argument('--app-version', default='0.1.0')
    parser.add_argument('--app-version-name', default=None)
    parser.add_argument('--app-version-code', type=int, default=None)
    parser.add_argument('--app-url', default=None)
    args = parser.parse_args()
    try:
        return build(args)
    except (SystemExit, KeyboardInterrupt):
        raise


if __name__ == '__main__':
    sys.exit(main())

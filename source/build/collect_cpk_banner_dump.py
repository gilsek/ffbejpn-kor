#!/usr/bin/env python3
"""기기 앱(com.exvius.jpkorean.app)이 덤프한 배너 PNG를 PC로 모아 검사·복사·집계한다.

기기 덤프 폴더에는 <파일명>.png 들과 진행 기록 _log.tsv(열: name, cpk, size, status)가 생긴다.
이 도구는

  1. (--pull) adb로 기기 덤프 폴더를 --raw 폴더로 가져온다. 일반 경로가 실패하면
     `adb exec-out run-as <pkg> tar cf - files/cpk_dump`로 받아서 푼다.
  2. --raw 아래에서 *.png를 재귀적으로 찾아 PNG 시그니처·IHDR 폭/높이를 읽고,
     build/out/seal_room/banner_files.tsv 의 이름/크기와 대조해 출처 CPK를 고른다
     (같은 이름이 두 CPK에 있으면 크기로 구분, 둘 다 안 맞으면 cpk=?).
  3. 시그니처가 정상인 파일만 inputs/jp_cpk_banners/<원래 파일명> 으로 복사한다
     (이미 같은 sha1이면 건너뜀).
  4. 목록의 모든 행에 대해 manifest.tsv 를 쓰고 summary.json 으로 집계한다.

usage:
  python -I -X utf8 build/collect_cpk_banner_dump.py --pull
  python -I -X utf8 build/collect_cpk_banner_dump.py --raw <가져온 폴더>
  python -I -X utf8 build/collect_cpk_banner_dump.py --raw <폴더> --out-images <D> --out-dir <D>

manifest.tsv 열: file  cpk  size  list_size  size_match  sha1  width  height  status
status: ok / size_mismatch / bad_png / missing / missing:<기기 _log.tsv 상태>
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from collections import OrderedDict, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PKG = 'com.exvius.jpkorean.app'
PNG_SIG = b'\x89PNG\r\n\x1a\n'
DEVICE_DIR = '/sdcard/Android/data/%s/files/cpk_dump' % PKG
DEFAULT_LIST = ROOT / 'build/out/seal_room/banner_files.tsv'
DEFAULT_RAW = ROOT / 'build/out/vortex_season/cpk_dump/raw'
DEFAULT_OUT_IMAGES = ROOT / 'inputs/jp_cpk_banners'
DEFAULT_OUT_DIR = ROOT / 'build/out/vortex_season/cpk_dump'
OBTAINED = ('ok', 'size_mismatch')
MANIFEST_COLS = ['file', 'cpk', 'size', 'list_size', 'size_match', 'sha1', 'width', 'height', 'status']


# ---------------------------------------------------------------- adb

def run_adb(args, extra, **kw):
    """adb 호출(인자 리스트). Git Bash의 /sdcard 경로 변환을 막는다."""
    env = dict(os.environ)
    env['MSYS_NO_PATHCONV'] = '1'
    cmd = ['adb']
    if args.serial:
        cmd += ['-s', args.serial]
    cmd += extra
    try:
        return subprocess.run(cmd, env=env, **kw)
    except FileNotFoundError:
        raise SystemExit('[오류] adb를 찾을 수 없습니다. PATH를 확인하세요.')


def extract_tar_bytes(data, dest, strip_prefix):
    """tar 바이트에서 파일만 풀어 dest에 쓴다. strip_prefix는 앞 경로 접두사."""
    prefix = PurePosixPath(strip_prefix)
    dest = Path(dest)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as tar:
        for member in tar:
            if not member.isfile():
                continue
            rel = PurePosixPath(member.name)
            try:
                rel = rel.relative_to(prefix)
            except ValueError:
                pass
            if not rel.parts or rel.is_absolute() or any(p == '..' for p in rel.parts):
                continue
            target = dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            fh = tar.extractfile(member)
            if fh is None:
                continue
            target.write_bytes(fh.read())
            n += 1
    return n


def pull(args):
    raw = Path(args.raw)
    raw.parent.mkdir(parents=True, exist_ok=True)
    print('[pull] adb pull %s -> %s' % (args.device_dir, raw))
    proc = run_adb(args, ['pull', args.device_dir, str(raw)],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
    if proc.returncode == 0:
        print('[pull] 완료')
        return
    tail = (proc.stderr or proc.stdout or '').strip().splitlines()
    print('[pull] 일반 경로 실패%s, run-as tar로 재시도' % (': ' + tail[-1] if tail else ''))
    proc = run_adb(args, ['exec-out', 'run-as', PKG, 'tar', 'cf', '-', 'files/cpk_dump'],
                   capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or b'').decode('utf-8', 'replace').strip()
        raise SystemExit('[pull] 실패: %s' % (err[-400:] or '알 수 없는 오류'))
    raw.mkdir(parents=True, exist_ok=True)
    n = extract_tar_bytes(proc.stdout, raw, 'files/cpk_dump')
    print('[pull] run-as tar 완료 (%d개 파일)' % n)


# ------------------------------------------------------------ 입력 읽기

def resolve(p):
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def read_list(path):
    rows = []
    with path.open(encoding='utf-8', newline='') as fh:
        header = fh.readline().rstrip('\r\n').split('\t')
        if header[:3] != ['cpk', 'file', 'size']:
            raise SystemExit('[오류] 목록 헤더가 예상과 다릅니다: %r (%s)' % (header[:3], path))
        for lineno, line in enumerate(fh, 2):
            line = line.rstrip('\r\n')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                raise SystemExit('[오류] %s:%d 열이 3개 미만: %r' % (path, lineno, line))
            try:
                size = int(parts[2])
            except ValueError:
                raise SystemExit('[오류] %s:%d 크기가 정수가 아님: %r' % (path, lineno, parts[2]))
            rows.append({'cpk': parts[0], 'file': parts[1], 'size': size, 'line': lineno})
    return rows


def read_device_log(raw):
    """_log.tsv(이름, cpk, 크기, 상태)를 (name,cpk)와 name 키로 모은다."""
    log = {}
    for path in sorted(Path(raw).rglob('_log.tsv')):
        with path.open(encoding='utf-8', errors='replace', newline='') as fh:
            for line in fh:
                line = line.rstrip('\r\n')
                if not line:
                    continue
                parts = line.split('\t')
                if parts[0] == 'name':
                    continue
                name = parts[0]
                cpk = parts[1] if len(parts) > 1 else ''
                status = parts[3] if len(parts) > 3 else ''
                log.setdefault((name, cpk), status)
                log.setdefault(name, status)
    return log


# ------------------------------------------------------------- PNG 검사

def png_info(path):
    """(시그니처OK, width, height). IHDR이 없으면 폭/높이는 None."""
    with path.open('rb') as fh:
        head = fh.read(33)
    if len(head) < 8 or head[:8] != PNG_SIG:
        return False, None, None
    if len(head) < 24 or head[12:16] != b'IHDR':
        return True, None, None
    return True, int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')


def sha1_file(path):
    h = hashlib.sha1()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def match_rows(rows, by_name):
    """행 인덱스 -> (원본 PNG 경로, 강제 cpk 또는 None)."""
    rows_by_name = defaultdict(list)
    for i, row in enumerate(rows):
        rows_by_name[row['file']].append(i)

    assign = {}
    for name, idxs in rows_by_name.items():
        cands = by_name.get(name)
        if not cands:
            continue
        if len(idxs) == 1:
            i = idxs[0]
            want = rows[i]['size']
            exact = [c for c in cands if c.stat().st_size == want]
            assign[i] = (exact[0] if exact else cands[0], None)
            continue
        # 같은 이름이 여러 CPK에 있음: 크기로 출처를 고른다.
        used = set()
        for i in idxs:
            want = rows[i]['size']
            for cand in cands:
                if cand in used:
                    continue
                if cand.stat().st_size == want:
                    assign[i] = (cand, None)
                    used.add(cand)
                    break
        if not used:            # 둘 다 안 맞음
            assign[idxs[0]] = (cands[0], '?')
    return assign


# ------------------------------------------------------------ 출력

def write_manifest(path, records):
    with path.open('w', encoding='utf-8', newline='\n') as fh:
        fh.write('\t'.join(MANIFEST_COLS) + '\n')
        for rec in records:
            fh.write('\t'.join(str(rec[c]) for c in MANIFEST_COLS) + '\n')


def make_summary(records):
    total = len(records)
    obtained = sum(1 for r in records if r['status'] in OBTAINED)
    failed = total - obtained
    bn = [r for r in records if 'bn_list' in r['file']]
    bn_obtained = sum(1 for r in bn if r['status'] in OBTAINED)
    by_cpk = OrderedDict()
    for rec in records:
        cpk = rec['cpk']
        by_cpk.setdefault(cpk, 0)
        if rec['status'] in OBTAINED:
            by_cpk[cpk] += 1
    counts = OrderedDict()
    for rec in records:
        counts[rec['status']] = counts.get(rec['status'], 0) + 1
    return {
        'total': total,
        'obtained': obtained,
        'failed': failed,
        'bn_list': {
            'total': len(bn),
            'obtained': bn_obtained,
            'rate': round(bn_obtained / len(bn), 4) if bn else 0.0,
        },
        'by_cpk': by_cpk,
        'failed_files': [r['file'] for r in records if r['status'] not in OBTAINED],
        'status_counts': counts,
    }


def print_summary(summary, manifest_path, summary_path, copied, skipped):
    bn = summary['bn_list']
    print('')
    print('목록 행: %d, 확보: %d, 실패: %d' % (summary['total'], summary['obtained'], summary['failed']))
    print('bn_list 확보: %d/%d (%.1f%%)' % (bn['obtained'], bn['total'], bn['rate'] * 100))
    print('CPK별 확보: ' + ', '.join('%s %d' % (k, v) for k, v in summary['by_cpk'].items()))
    print('상태: ' + ', '.join('%s %d' % (k, v) for k, v in summary['status_counts'].items()))
    print('복사: %d개 (같은 sha1로 건너뜀: %d개)' % (copied, skipped))
    print('manifest: %s' % manifest_path)
    print('summary : %s' % summary_path)


# ------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description='기기 덤프 배너 PNG를 모아 검사·복사·집계한다.')
    ap.add_argument('--pull', action='store_true',
                    help='adb로 기기 덤프 폴더를 --raw로 가져온다(기본 끔)')
    ap.add_argument('--device-dir', default=DEVICE_DIR,
                    help='기기 덤프 폴더(기본 %s)' % DEVICE_DIR)
    ap.add_argument('--raw', default=str(DEFAULT_RAW),
                    help='가져온 파일 폴더(기본 build/out/vortex_season/cpk_dump/raw)')
    ap.add_argument('--list', default=str(DEFAULT_LIST),
                    help='배너 목록 TSV(기본 build/out/seal_room/banner_files.tsv)')
    ap.add_argument('--out-images', default=str(DEFAULT_OUT_IMAGES),
                    help='PNG 복사 대상(기본 inputs/jp_cpk_banners)')
    ap.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR),
                    help='manifest/summary 출력 폴더(기본 build/out/vortex_season/cpk_dump)')
    ap.add_argument('--serial', default=None, help='adb -s 값(선택)')
    args = ap.parse_args()

    args.raw = str(resolve(args.raw))
    args.list = str(resolve(args.list))
    args.out_images = str(resolve(args.out_images))
    args.out_dir = str(resolve(args.out_dir))

    if args.pull:
        pull(args)

    raw = Path(args.raw)
    if not raw.is_dir():
        raise SystemExit('[오류] raw 폴더가 없습니다: %s\n'
                         '  --pull로 가져오거나 --raw로 폴더를 지정하세요.' % raw)

    list_path = Path(args.list)
    if not list_path.is_file():
        raise SystemExit('[오류] 목록 파일이 없습니다: %s' % list_path)

    out_images = Path(args.out_images)
    out_dir = Path(args.out_dir)
    out_images.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_list(list_path)
    by_name = defaultdict(list)
    for path in sorted(raw.rglob('*.png')):
        if path.is_file():
            by_name[path.name].append(path)
    log = read_device_log(raw)

    assign = match_rows(rows, by_name)

    copied = skipped = 0
    records = []
    for i, row in enumerate(rows):
        rec = {
            'file': row['file'], 'cpk': row['cpk'], 'size': '', 'list_size': row['size'],
            'size_match': '', 'sha1': '', 'width': '', 'height': '', 'status': 'missing',
        }
        src_info = assign.get(i)
        if src_info is None:
            dev = log.get((row['file'], row['cpk']))
            if dev is None:
                dev = log.get(row['file'])
            if dev:
                rec['status'] = 'missing:%s' % dev
            records.append(rec)
            continue

        src, forced_cpk = src_info
        if forced_cpk:
            rec['cpk'] = forced_cpk
        actual = src.stat().st_size
        sig_ok, width, height = png_info(src)
        rec['size'] = actual
        rec['size_match'] = '1' if actual == row['size'] else '0'
        rec['sha1'] = sha1_file(src)
        if width is not None:
            rec['width'] = width
        if height is not None:
            rec['height'] = height

        if not sig_ok:
            rec['status'] = 'bad_png'
            records.append(rec)
            continue

        rec['status'] = 'ok' if actual == row['size'] else 'size_mismatch'
        dest = out_images / row['file']
        if dest.is_file() and sha1_file(dest) == rec['sha1']:
            skipped += 1
        else:
            shutil.copy2(src, dest)
            copied += 1
        records.append(rec)

    manifest_path = out_dir / 'manifest.tsv'
    summary_path = out_dir / 'summary.json'
    write_manifest(manifest_path, records)
    summary = make_summary(records)
    with summary_path.open('w', encoding='utf-8', newline='\n') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
        fh.write('\n')

    print_summary(summary, manifest_path, summary_path, copied, skipped)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()

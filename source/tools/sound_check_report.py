"""빠진 소리 기록(build/frida/jp_sound_check.js)의 결과를 요약한다. 읽기 전용.

기기의 files/exvius/sound_check.log를 run-as로 가져오거나(--serial), 로컬 사본을 읽는다(--log).
acb 크기 -> 파일 이름은 아카이브 폴더와 APK assets의 acb 크기로 찾는다.

usage: python -I tools/sound_check_report.py --serial <tablet-ip>:34793 [--save build/out/jp_offline/sound/sound_check.log]
       python -I tools/sound_check_report.py --log <파일>
"""
import argparse, collections, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = 'com.exvius.jpkorean.app'


def size_names(dirs):
    names = collections.defaultdict(list)
    for d in dirs:
        d = Path(d)
        if d.is_dir():
            for p in d.rglob('*.acb'):
                names[p.stat().st_size].append(p.name + (' (APK)' if 'assets' in p.parts else ''))
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--serial')
    ap.add_argument('--log')
    ap.add_argument('--save', help='기기에서 가져온 로그를 이 경로에 저장')
    ap.add_argument('--archive', default='D:/Downloads/ffbejpdata/ffbejpdata')
    ap.add_argument('--assets', default=str(ROOT / 'build/out/jp_offline/dec/assets/android'))
    args = ap.parse_args()
    if args.log:
        text = Path(args.log).read_text(encoding='utf-8', errors='replace')
    elif args.serial:
        raw = subprocess.check_output(['adb', '-s', args.serial, 'exec-out', 'run-as', PKG, 'cat', 'files/exvius/sound_check.log'])
        text = raw.decode('utf-8', 'replace')
        if args.save:
            Path(args.save).parent.mkdir(parents=True, exist_ok=True)
            Path(args.save).write_bytes(raw)
    else:
        ap.error('--serial 또는 --log 필요')
    names = size_names([args.archive, args.assets])

    def acb(size):
        if not size.isdigit():
            return size
        n = names.get(int(size))
        return '/'.join(n) if n else 'size ' + size

    ok, fails, errs, starts = set(), collections.Counter(), collections.Counter(), 0
    for line in text.splitlines():
        f = line.split('\t')
        if len(f) < 2:
            continue
        if f[1] == 'START':
            starts += 1
        elif f[1] == 'CRI_ERR':
            errs['\t'.join(f[2:])] += 1
        elif f[1] in ('OK', 'FAIL_ERROR', 'FAIL_EARLY') and len(f) >= 8:
            key = (acb(f[2]), f[3], f[4], f[5])
            if f[1] == 'OK':
                ok.add(key)
            else:
                fails[(f[1],) + key] += 1
    print(f'실행 {starts}회, 정상 재생 cue {len(ok)}개, 실패 cue {len(fails)}종, CRI 오류 {sum(errs.values())}건')
    if fails:
        print('\n[실패] 판정 | acb | cue id | cue 이름 | 길이 ms | 횟수')
        for (v, a, cid, name, length), n in sorted(fails.items(), key=lambda x: (-x[1], x[0])):
            print(f'  {v} | {a} | {cid} | {name} | {length} | {n}')
    if errs:
        print('\n[CRI 오류]')
        for e, n in errs.most_common(20):
            print(f'  {n}회  {e}')
    by_acb = collections.Counter(k[0] for k in ok)
    print('\n[정상 재생] acb별 cue 수')
    for a, n in by_acb.most_common():
        print(f'  {a}: {n}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

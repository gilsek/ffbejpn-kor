"""Put the Korean masters (build/apply_ko_names.py) on the device.

/data/local/tmp/ffbe/mst_ko/Ver*_<token>.dat (originals in mst/ stay; jp_offline.js localize() prefers mst_ko/),
and the copies the client already installed (files/Ver*_<token>.dat) are overwritten.

usage: python -I build/deploy_ko_names.py --serial <tablet-ip>:<port>
"""
import argparse, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'build/out/ko_names/mst_ko'
PKG = 'com.exvius.jpkorean.app'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial', required=True)
    ap.add_argument('--only', help='배포할 마스터 token을 쉼표로 구분 (생략하면 전체)')
    args = ap.parse_args()
    adb = lambda *a: subprocess.run(['adb', '-s', args.serial, *a], check=True)
    adb('shell', 'mkdir -p /data/local/tmp/ffbe/mst_ko')
    files = sorted(SRC.glob('Ver*_*.dat'))
    if args.only:
        tokens = set(args.only.split(','))
        files = [f for f in files if f.stem.split('_')[-1] in tokens]
        if {f.stem.split('_')[-1] for f in files} != tokens:
            ap.error('요청한 마스터 산출물이 없음')
    if not files:
        ap.error('배포할 마스터 없음')
    adb('push', *map(str, files), '/data/local/tmp/ffbe/mst_ko/')
    targets = ' '.join('/data/local/tmp/ffbe/mst_ko/' + f.name for f in files)
    adb('shell', 'chmod 644 ' + targets)
    # The client keeps a row-offset index files/<token>.i for large tables (DungeonMstList::readIndexFile etc.).
    # A replaced .dat with different row lengths makes the old index point into the wrong rows
    # (2026-11-09: Korean F_DUNGEON_MST -> MapEventStartScene crash). Remove it; the client rebuilds it.
    script = ('n=0; for f in ' + targets + '; do b=${f##*/}; t=${b#*_}; t=${t%.dat}; '
              'if [ -f files/$b ]; then cp $f files/$b && n=$((n+1)); fi; rm -f files/$t.i; done; '
              'echo installed-copies-replaced $n')
    adb('shell', f"run-as {PKG} sh -c '{script}'")
    print(len(files), 'masters deployed')


if __name__ == '__main__':
    main()

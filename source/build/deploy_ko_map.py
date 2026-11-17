"""Put the Korean map CPKs (build/apply_ko_map.py) on the device.

1. adb push build/out/ko_map/flat_ko/*.cpk -> /data/local/tmp/ffbe/flat_ko/ (about 4 GB: the map CPKs carry their
   tile images, so no tar copy is made). Originals in flat/ stay untouched; jp_offline.js localize() prefers
   flat_ko/<name> when it exists.
2. Maps the client already installed live in the app's files/<name>.cpk: overwrite those copies (run-as).

usage: python -I build/deploy_ko_map.py --serial <tablet-ip>:<port>
"""
import argparse, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'build/out/ko_map/flat_ko'
PKG = 'com.exvius.jpkorean.app'


def adb(serial, *args, **kw):
    return subprocess.run(['adb', '-s', serial, *args], check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial', required=True)
    args = ap.parse_args()
    names = sorted(p.name for p in SRC.glob('*.cpk'))
    print('push', len(names), 'files')
    adb(args.serial, 'shell', 'mkdir -p /data/local/tmp/ffbe/flat_ko')
    adb(args.serial, 'push', str(SRC) + '/.', '/data/local/tmp/ffbe/flat_ko/')
    adb(args.serial, 'shell', 'chmod 644 /data/local/tmp/ffbe/flat_ko/*.cpk')
    listing = '/data/local/tmp/ffbe/ko_map_names.txt'
    tmp = ROOT / 'build/out/ko_map/names.txt'
    # LF only: write_text on Windows wrote CRLF, every name then ended in \r and no installed copy was replaced
    tmp.write_bytes(('\n'.join(names) + '\n').encode('ascii'))
    adb(args.serial, 'push', str(tmp), listing)
    script = (f'n=0; while read b; do if [ -f files/$b ]; then cp /data/local/tmp/ffbe/flat_ko/$b files/$b && n=$((n+1)); fi; '
              f'done < {listing}; echo installed-copies-replaced $n')
    adb(args.serial, 'shell', f"run-as {PKG} sh -c '{script}'")


if __name__ == '__main__':
    main()

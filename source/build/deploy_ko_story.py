"""Put the Korean scene CPKs (build/apply_ko_story.py) on the device.

1. tar build/out/ko_story/flat_ko -> /data/local/tmp/ffbe/flat_ko/ (originals in flat/ stay untouched;
   jp_offline.js localize() prefers flat_ko/<name> when it exists, so scenes installed later come in Korean).
2. Scenes the client already installed live in the app's files/<name>.cpk: overwrite those copies (run-as).
   The original copies are recoverable from /data/local/tmp/ffbe/flat/.

usage: python -I build/deploy_ko_story.py --serial <tablet-ip>:<port>
"""
import argparse, subprocess, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'build/out/ko_story/flat_ko'
PKG = 'com.exvius.jpkorean.app'


def adb(serial, *args, **kw):
    return subprocess.run(['adb', '-s', serial, *args], check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial', required=True)
    args = ap.parse_args()
    files = sorted(SRC.glob('*.cpk'))
    tar = ROOT / 'build/out/ko_story/flat_ko.tar'
    with tarfile.open(tar, 'w') as t:
        for f in files:
            t.add(f, arcname=f.name)
    print('tar', len(files), 'files', tar.stat().st_size // 1_000_000, 'MB')
    adb(args.serial, 'push', str(tar), '/data/local/tmp/ffbe_flat_ko.tar')
    adb(args.serial, 'shell', 'mkdir -p /data/local/tmp/ffbe/flat_ko && cd /data/local/tmp/ffbe/flat_ko && '
        'tar xf /data/local/tmp/ffbe_flat_ko.tar && chmod 644 *.cpk && rm /data/local/tmp/ffbe_flat_ko.tar && ls | wc -l')
    script = ('n=0; for f in /data/local/tmp/ffbe/flat_ko/*.cpk; do b=${f##*/}; '
              'if [ -f files/$b ]; then cp $f files/$b && n=$((n+1)); fi; done; echo installed-copies-replaced $n')
    adb(args.serial, 'shell', f"run-as {PKG} sh -c '{script}'")


if __name__ == '__main__':
    main()

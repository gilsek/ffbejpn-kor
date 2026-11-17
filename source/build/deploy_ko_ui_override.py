"""Push the Korean replacements for single images inside downloaded CPKs (build/frida/jp_ui_override.js).

translations/ui-ko/sprites/campaign_ui/manifest.json -> /data/local/tmp/ffbe/ui_ko/<name> + index.txt (sha256 checked).
usage: python -I build/deploy_ko_ui_override.py --serial <tablet-ip>:5555
"""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'translations/ui-ko/sprites/campaign_ui'
DEV = '/data/local/tmp/ffbe/ui_ko/'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serial', required=True)
    a = ap.parse_args()
    man = json.loads((SRC / 'manifest.json').read_text(encoding='utf-8'))
    for name, r in man.items():
        assert hashlib.sha256((SRC / name).read_bytes()).hexdigest() == r['sha256'], name
    adb = ['adb', '-s', a.serial]
    subprocess.run(adb + ['shell', 'mkdir -p ' + DEV], check=True)
    with tempfile.TemporaryDirectory() as t:
        idx = Path(t) / 'index.txt'
        idx.write_text(''.join(n + '\n' for n in man), encoding='utf-8')
        for p in [idx] + [SRC / n for n in man]:
            subprocess.run(adb + ['push', str(p), DEV + p.name], check=True)
    subprocess.run(adb + ['shell', 'chmod 644 ' + DEV + '*'], check=True)
    print('PASS: pushed', len(man), 'images + index.txt to', DEV)


if __name__ == '__main__':
    main()

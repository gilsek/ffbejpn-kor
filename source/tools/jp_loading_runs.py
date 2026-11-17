"""실기기 3회 실행 관찰. 앱의 정상 실행/TOUCH START/force-stop만 수행한다."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serial', required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--keep-running', action='store_true', help='마지막 홈에서 회귀 검증을 이어간다')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    adb = ['adb', '-s', args.serial]
    package = 'com.exvius.jpkorean.app'
    results = []
    for run in range(1, args.runs + 1):
        path = args.out / f'run{run}.log'
        subprocess.run(adb + ['shell', 'am', 'force-stop', package], check=True)
        with path.open('wb') as output:
            log = subprocess.Popen(adb + ['logcat', '-v', 'threadtime', '-T', '1'], stdout=output)
            try:
                subprocess.run(adb + ['shell', 'am', 'start', '-n', package + '/com.square_enix.ffbejpn.Lapis'], check=True)
                start = time.monotonic()
                next_tap = 16
                while time.monotonic() - start < 120:
                    time.sleep(1)
                    text = path.read_text(encoding='utf-8', errors='replace')
                    if 'SCENE_NEW HomeScene' in text:
                        break
                    if time.monotonic() - start >= next_tap and 'SCENE_NEW InitializeScene' not in text:
                        subprocess.run(adb + ['shell', 'input', 'tap', '900', '2400'], check=True)
                        next_tap += 4
                else:
                    raise RuntimeError('120초 내 홈 미도달: ' + str(path))
                time.sleep(1)
                (args.out / f'run{run}_home.png').write_bytes(subprocess.check_output(adb + ['exec-out', 'screencap', '-p']))
            finally:
                log.terminate()
                log.wait()
        events = []
        for number, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if 'SCENE_NEW ' in line and 'cocos2d' not in line or 'JP_VERSION_DELTA' in line:
                events.append({'line': number, 'text': line})
        result = {'run': run, 'events': events, 'initial_download': any('InitialDownloadScene' in e['text'] for e in events)}
        results.append(result)
        (args.out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not (args.keep_running and run == args.runs):
            subprocess.run(adb + ['shell', 'am', 'force-stop', package], check=True)


if __name__ == '__main__':
    main()

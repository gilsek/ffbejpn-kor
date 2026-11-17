"""Same reading as identify_twitter_gacha_art.py, but through the Antigravity CLI (agy) with several workers.

One image per agy call (agy opens the file itself; cwd = the image folder), N calls in parallel.
Writes twitter_identify_agy.jsonl (same record format); files already in either jsonl are skipped.

usage: python -I -X utf8 build/identify_twitter_gacha_art_agy.py --list <txt> [--workers 5] [--limit N]
"""
import argparse, io, json, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'build/out/jp_offline/gacha_jp/twitter_identify.jsonl'      # CLIProxy 쪽 결과(읽기만)
OUT = ROOT / 'build/out/jp_offline/gacha_jp/twitter_identify_agy.jsonl'   # 이 스크립트의 결과
MODEL = 'gemini-3.8-flash-high'
PROMPT = re.search(r'PROMPT = """(.*?)"""', (ROOT / 'build/identify_twitter_gacha_art.py').read_text(encoding='utf-8'), re.S).group(1)
HEAD = ('このフォルダの画像ファイル {name} を開いて読み取ってください。ファイルの変更やコマンド実行はしないでください。'
        '他のファイルは開かないでください。\n')

lock = threading.Lock()
stop = threading.Event()
fails = [0]


def one(path):
    if stop.is_set():
        return
    try:
        p = subprocess.run(['agy', '-p', HEAD.format(name=path.name) + PROMPT, '--model', MODEL,
                            '--print-timeout', '150s', '--output-format', 'json'],
                           cwd=str(path.parent), capture_output=True, timeout=200)
        raw = p.stdout.decode('utf-8', 'replace')
        env = json.loads(raw[raw.find('{'):raw.rfind('}') + 1])
        if env.get('status') != 'SUCCESS':
            raise RuntimeError(f'status {env.get("status")} {str(env)[:300]}')
        txt = env['response']
        rec = json.loads(txt[txt.find('{'):txt.rfind('}') + 1])
    except Exception as e:
        with lock:
            fails[0] += 1
            print(f'FAIL {path.name}: {type(e).__name__} {str(e)[:300]}')
            if fails[0] >= 8:               # 연속 실패(한도·쿨다운 등)면 더 보내지 않는다
                stop.set()
        return
    with lock:
        fails[0] = 0
        with OUT.open('a', encoding='utf-8') as out:
            out.write(json.dumps({'file': path.name, 'folder': path.parent.name, 'model': 'agy:' + MODEL, **rec},
                                 ensure_ascii=False) + '\n')
        print(f'{path.name} | {rec.get("kind")} | {rec.get("title")}')


def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', required=True)
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--model', default=MODEL)
    a = ap.parse_args()
    MODEL = a.model
    files = [Path(l.strip()) for l in Path(a.list).read_text(encoding='utf-8').splitlines() if l.strip()]
    done = set()
    for src in (MAIN, OUT):
        if src.exists():
            done |= {json.loads(l)['file'] for l in src.read_text(encoding='utf-8').splitlines() if l.strip()}
    todo = [f for f in files if f.name not in done]
    if a.limit:
        todo = todo[-a.limit:]
    print(f'files {len(files)}, done {len(done)}, to do {len(todo)}, workers {a.workers}')
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, todo))
    print('STOPPED after repeated failures' if stop.is_set() else 'finished')
    return 2 if stop.is_set() else 0


if __name__ == '__main__':
    sys.exit(main())

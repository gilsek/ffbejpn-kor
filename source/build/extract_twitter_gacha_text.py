"""Read FFRS_JP tweets that mention 召喚 and extract which gacha(s) each tweet announces, from the TEXT only.

Independent of the image reading (identify_twitter_gacha_art.py). Model/endpoint are arguments so the same tweets can
be read by two different models and compared (Gemini via CLIProxy now, DeepSeek via the LiteLLM gateway later).

usage:
  python -I -X utf8 build/extract_twitter_gacha_text.py --tag gemini [--limit N]
  python -I -X utf8 build/extract_twitter_gacha_text.py --tag deepseek --base-url http://127.0.0.1:4000/v1 \
         --model ds-flash --key-env GATEWAY_KEY
writes build/out/jp_offline/gacha_jp/twitter_text_<tag>.jsonl (append, resumable: done tweet ids are skipped).
"""
import argparse, io, json, os, subprocess, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
ROOT = Path(__file__).resolve().parents[1]
SRC = Path('D:/Archive/gallery-dl/twitter/FFRS_JP')
OUTDIR = ROOT / 'build/out/jp_offline/gacha_jp'
BATCH = 10

PROMPT = """以下はスマホゲーム「FFBE」公式Twitterのツイートです（id, 投稿日, 本文）。各ツイートについて、本文に書かれている内容だけから、
告知されている「召喚」(ガチャ)を抜き出してください。本文に無い情報は書かない・推測しない。不明な項目は null。
JSON オブジェクト {"tweets":[...]} だけを出力。tweets の各要素:
{
 "id": "ツイートid（入力と同じ文字列）",
 "is_gacha": true/false,          // 召喚そのものの開催・予告・終了間近の告知なら true。召喚チケット配布やイベント告知だけなら false
 "phase": "予告 | 開催中 | 終了間近 | その他",
 "gachas": [{                     // 1ツイートに複数の召喚があれば全部。is_gacha=false なら空配列
   "name": "召喚の名称を本文の表記どおりに（括弧や★の飾りは除く）",
   "type": "pickup | step_up | free | box | ticket | select | trust_master | raid | other",
   "rerun": true/false,           // 復刻と書かれているか
   "start": "開始日時を本文の表記どおり（例 9/14(金)17:00）。無ければ null",
   "end": "終了日時を本文の表記どおり。無ければ null",
   "start_iso": "投稿日から年を補って YYYY-MM-DD。開始が書かれていなければ null",
   "end_iso": "同様に YYYY-MM-DD。無ければ null",
   "units": [{"name": "本文に書かれたユニット名そのまま", "rarity": "★5 / NV など本文にあれば。無ければ null"}],
   "series": "作品名(FFVII, FFBE など)が書かれていれば。無ければ null",
   "prices": ["本文に書かれた価格・回数・確定内容の表記そのまま"]
 }]
}"""


def call(base, model, key, tweets):
    body = {'model': model, 'temperature': 0, 'response_format': {'type': 'json_object'},
            'messages': [{'role': 'user', 'content': PROMPT + '\n\n' + json.dumps(tweets, ensure_ascii=False, indent=1)}]}
    req = urllib.request.Request(base.rstrip('/') + '/chat/completions', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'})
    with urllib.request.urlopen(req, timeout=300) as r:
        txt = json.load(r)['choices'][0]['message']['content']
    return json.loads(txt[txt.find('{'):txt.rfind('}') + 1])['tweets']


def call_agy(model, tweets):
    """Same request through the Antigravity CLI (agy). No tools are needed: the tweets are in the prompt."""
    prompt = (PROMPT + '\n\nファイルを開いたりコマンドを実行したりせず、次の入力だけを読んで答えてください。\n'
              + json.dumps(tweets, ensure_ascii=False))
    p = subprocess.run(['agy', '-p', prompt, '--model', model, '--print-timeout', '240s', '--output-format', 'json'],
                       cwd=str(OUTDIR), capture_output=True, timeout=300)
    raw = p.stdout.decode('utf-8', 'replace')
    env = json.loads(raw[raw.find('{'):raw.rfind('}') + 1])
    if env.get('status') != 'SUCCESS':
        raise RuntimeError(f'status {env.get("status")} {str(env)[:300]}')
    txt = env['response']
    return json.loads(txt[txt.find('{'):txt.rfind('}') + 1])['tweets']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True)
    ap.add_argument('--base-url', default='http://127.0.0.1:8317/v1')
    ap.add_argument('--model', default='gemini-3.8-flash-high')
    ap.add_argument('--key-env', default='', help='env var holding the API key (default: CLIProxy token)')
    ap.add_argument('--limit', type=int, default=0, help='max tweets this run')
    ap.add_argument('--agy', action='store_true', help='use the Antigravity CLI instead of an HTTP endpoint')
    ap.add_argument('--workers', type=int, default=1, help='parallel requests (agy only)')
    a = ap.parse_args()
    key = os.environ.get(a.key_env, '') if a.key_env else 'not-a-secret'
    out_path = OUTDIR / f'twitter_text_{a.tag}.jsonl'
    done = set()
    if out_path.exists():
        done = {json.loads(l)['id'] for l in out_path.read_text(encoding='utf-8').splitlines() if l.strip()}
    todo = []
    for name in sorted(os.listdir(SRC)):
        if not name.endswith('.json'):
            continue
        tid = name[:-5].split('_')[1]
        if tid in done:
            continue
        try:
            c = json.loads((SRC / name).read_text(encoding='utf-8')).get('content') or ''
        except Exception:
            continue
        if '召喚' in c:
            todo.append({'id': tid, 'date': name[:10], 'text': c})
    if a.limit:
        todo = todo[:a.limit]
    print(f'done {len(done)}, to do {len(todo)}, model {a.model}')
    lock, stop, fails, count = threading.Lock(), threading.Event(), [0], [0]

    def work(chunk):
        if stop.is_set():
            return
        try:
            res = call_agy(a.model, chunk) if a.agy else call(a.base_url, a.model, key, chunk)
        except urllib.error.HTTPError as e:      # 429 등: 재시도하지 않고 본문을 보여 주고 멈춘다
            print(f'STOP at {chunk[0]["id"]}: HTTP {e.code} {e.read().decode("utf-8", "replace")[:500]}')
            stop.set()
            return
        except Exception as e:
            with lock:
                fails[0] += 1
                print(f'FAIL batch {chunk[0]["id"]}: {type(e).__name__} {str(e)[:300]}')
                if fails[0] >= 6:
                    stop.set()
            return
        by_id = {str(r.get('id')): r for r in res if isinstance(r, dict)}
        with lock:                                # 모델이 빠뜨린 트윗은 기록하지 않아 다음 실행에서 다시 시도된다
            fails[0] = 0
            with out_path.open('a', encoding='utf-8') as out:
                for t in chunk:
                    r = by_id.get(t['id'])
                    if r:
                        out.write(json.dumps({**r, 'id': t['id'], 'date': t['date'], 'model': ('agy:' if a.agy else '') + a.model},
                                             ensure_ascii=False) + '\n')
            count[0] += len(chunk)
            print(f'{count[0]}/{len(todo)} ok {sum(1 for t in chunk if t["id"] in by_id)}/{len(chunk)}')

    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    with ThreadPoolExecutor(a.workers if a.agy else 1) as ex:
        list(ex.map(work, chunks))
    if stop.is_set():
        print('STOPPED')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

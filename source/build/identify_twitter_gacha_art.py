"""Read what each Twitter(FFRS_JP) banner image actually is: transcribe the text drawn in the image.

The model sees ONLY the image (no tweet text, no file name), so its reading is independent evidence that can be
checked against the tweet body afterwards. One image per request, sequential, resumable (done files are skipped).

usage: python -I -X utf8 build/identify_twitter_gacha_art.py --list <txt: one image path per line> [--limit N]
writes build/out/jp_offline/gacha_jp/twitter_identify.jsonl (append).
Needs the local CLIProxy (http://127.0.0.1:8317/v1, token not-a-secret).
"""
import argparse, base64, io, json, sys, time, urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/out/jp_offline/gacha_jp/twitter_identify.jsonl'
URL = 'http://127.0.0.1:8317/v1/chat/completions'
MODEL = 'gemini-3.8-flash-high'

PROMPT = """この画像はスマホゲーム「FFBE」公式の告知画像です。画像の中に実際に描かれている文字だけを、一字一句そのまま書き写してください。
推測や補完は禁止です。読めない文字は「?」にし、項目ごと読めない場合は null にしてください。画像にない情報は書かないでください。
次のキーを持つ JSON オブジェクトだけを出力してください（説明文なし）:
{
 "kind": "gacha | event | campaign | login_bonus | shop | other",   // 画像の種類。召喚(ガチャ)の告知なら gacha
 "title": "画像内の一番大きな見出し文字（召喚名）。そのまま",
 "subtitles": ["見出し以外の説明文字を、そのまま、上から順に"],
 "period": "開催期間や日付の文字があればそのまま、無ければ null",
 "prices": ["価格や回数の表記（例: 1回 500, 11連 5000, STEP1 無料）をそのまま"],
 "step_count": 0,                 // STEP 表記の段数。無ければ 0
 "unit_names": ["画像内に文字で書かれたユニット(キャラクター)名。文字が無ければ空配列。絵から人物を推測しない"],
 "series": "作品ロゴや作品名の文字（例: FINAL FANTASY VII）。無ければ null",
 "character_count": 0,            // 描かれている人物のおおよその数
 "unreadable": ["読めなかった箇所の説明"]
}"""


def ask(path):
    data = base64.b64encode(path.read_bytes()).decode()
    mime = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
    body = {'model': MODEL, 'temperature': 0, 'response_format': {'type': 'json_object'},
            'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': PROMPT},
                {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{data}'}}]}]}
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', 'Authorization': 'Bearer not-a-secret'})
    with urllib.request.urlopen(req, timeout=180) as r:
        txt = json.load(r)['choices'][0]['message']['content']
    txt = txt.strip()
    if txt.startswith('```'):
        txt = txt.strip('`').split('\n', 1)[1].rsplit('```', 1)[0] if '\n' in txt else txt
    return json.loads(txt[txt.find('{'):txt.rfind('}') + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', required=True)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    files = [Path(l.strip()) for l in Path(a.list).read_text(encoding='utf-8').splitlines() if l.strip()]
    done = set()
    if OUT.exists():
        done = {json.loads(l)['file'] for l in OUT.read_text(encoding='utf-8').splitlines() if l.strip()}
    todo = [f for f in files if f.name not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f'files {len(files)}, done {len(done)}, to do {len(todo)}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('a', encoding='utf-8') as out:
        for i, f in enumerate(todo, 1):
            try:
                rec = ask(f)
            except urllib.error.HTTPError as e:      # 429 등: 재시도하지 않고 본문을 보여 주고 멈춘다
                print(f'STOP {f.name}: HTTP {e.code} {e.read().decode("utf-8", "replace")[:500]}')
                return 2
            except Exception as e:
                print(f'FAIL {f.name}: {type(e).__name__} {e}')
                continue
            rec = {'file': f.name, 'folder': f.parent.name, 'model': MODEL, **rec}
            out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            out.flush()
            print(f'{i}/{len(todo)} {f.name} | {rec.get("kind")} | {rec.get("title")}')
            time.sleep(1)
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""전투 대사 창(2줄 × 24자)에 줄바꿈만으로 들어가지 않는 번역을 줄인다.

usage: python -I -X utf8 translations/battle-ko/shorten_lines.py [--model ds-flash]
입력: gt_output + manifest(원문·화자). 출력: translations/battle-ko/line_fits.json {ffbe_id: {"ko": 원번역, "fit": 줄인 문장}}
이미 있는 항목은 원번역이 같으면 다시 요청하지 않는다. 결과는 build/ko_line_fit.fits 통과분만 저장.
LiteLLM 게이트웨이(http://127.0.0.1:4000, ds-flash) 필요.
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'translations/battle-ko'
OUT = HERE / 'line_fits.json'
sys.path.insert(0, str(ROOT / 'build'))
import ko_line_fit as F  # noqa: E402

GATEWAY_ENV = Path.home() / 'litellm-gateway' / '.env'


def gateway_key():
    key = os.environ.get('LITELLM_MASTER_KEY', '').strip()
    if not key and GATEWAY_ENV.exists():
        for line in GATEWAY_ENV.read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('LITELLM_MASTER_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')

    if not key:
        raise SystemExit('LITELLM_MASTER_KEY not found (env or ' + str(GATEWAY_ENV) + ')')
    return key


PROMPT = """너는 게임 「파이널 판타지 브레이브 엑스비어스」 한국어 번역 교정자다.
아래 전투 대사의 한국어 번역이 대사 창에 들어가지 않는다. 대사 창은 최대 2줄, 한 줄 최대 {w}자(공백·문장부호 포함)다.
일본어 원문의 뜻과 말투(화자 성격, 반말/존댓말)를 유지하면서 한국어 번역을 줄여라.
- 고유명사·용어는 현재 번역 그대로 둔다.
- 두 줄로 나눌 때는 줄바꿈 문자(\\n)를 쓴다. 각 줄은 {w}자 이하.
- 설명 없이 고친 대사만 출력한다.

화자: {speaker}
일본어 원문: {jp}
현재 번역: {ko}"""


def ask(model, text):
    req = urllib.request.Request(
        'http://127.0.0.1:4000/v1/chat/completions',
        data=json.dumps({'model': model, 'messages': [{'role': 'user', 'content': text}],
                         'temperature': 0.3}).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + gateway_key(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())['choices'][0]['message']['content'].strip().strip('"').replace('\\n', '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='ds-flash')
    ap.add_argument('--tries', type=int, default=4)
    args = ap.parse_args()
    man = {r['ffbe_id']: r for r in json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))['records']}
    ko = {}
    for f in sorted((HERE / 'gt_output').glob('*.json')):
        for r in json.loads(f.read_text(encoding='utf-8-sig')):
            ko[r['ffbe_id']] = (r.get('name', ''), r['message'])
    done = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    # 원문이 3줄 이상인 특수 메시지(다른 창)는 대상이 아니다.
    todo = [k for k, (_, t) in ko.items() if F.fit(t) is None and man[k]['source'].count('\n') < 2
            and done.get(k, {}).get('ko') != t]
    print('unfit', sum(1 for _, t in ko.values() if F.fit(t) is None), 'to ask', len(todo))
    failed = []
    for k in todo:
        speaker, text = ko[k]
        for _ in range(args.tries):
            out = ask(args.model, PROMPT.format(w=F.WIDTH, speaker=speaker, jp=man[k]['source'], ko=text))
            got = F.fit(out)
            if got is not None and F.HANGUL.search(got):
                done[k] = {'ko': text, 'fit': got}
                print('OK', repr(got))
                break
        else:
            failed.append(k)
            print('FAIL', k, repr(text))
        OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print('saved', len(done), 'failed', len(failed))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()

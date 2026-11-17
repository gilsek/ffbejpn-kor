"""Translate the map_text / map_teller strings no existing translation covers (build/out/ko_map/missing.json).
Model: ds-flash via the LiteLLM gateway (http://127.0.0.1:4000). Tags must survive unchanged. Resumable (cache file)."""
import sys, re, json, os, time, urllib.request, urllib.error, concurrent.futures as cf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import name_coverage as NC
OUT = ROOT / 'build/out/ko_map/new_translations.json'
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


URL = 'http://127.0.0.1:4000/v1/chat/completions'; MODEL = 'ds-flash'
TAG = re.compile(r'<[^>]*>')
known = NC.name_sources()[0]
names_long = sorted((k for k in known if len(k) >= 2), key=len, reverse=True)
miss = json.load(open(ROOT / 'build/out/ko_map/missing.json', encoding='utf-8'))
items = [('teller', k) for k in miss['teller'] if k not in known] + [('text', k) for k in miss['text'] if k not in known]
done = json.load(open(OUT, encoding='utf-8')) if OUT.exists() else {}
todo = [x for x in items if x[1] not in done]
print('items', len(items), 'todo', len(todo), flush=True)
PROMPT = ("You translate Japanese text from the RPG FINAL FANTASY BRAVE EXVIUS (town/field maps) into natural Korean "
          "game text. Rules: keep every tag like <name=200022>, <br>, <keywait>, <page>, <wait=60>, <name_npc=...> "
          "exactly as is and in the same order; translate only the text between tags; keep line breaks as <br>; "
          "use the glossary for proper nouns; do not use ASCII commas (use ‚ or rephrase); NPC role names "
          "(街の人 etc.) should be short Korean nouns. Reply with JSON only: {\"<id>\": \"<korean>\", ...}.")
def glossary(texts):
    g = {}
    for t in texts:
        plain = TAG.sub('', t)
        for n in names_long:
            if n in plain and len(g) < 40:
                g[n] = known[n]; plain = plain.replace(n, '')
    return g
def call(batch):
    src = {str(i): t for i, (_, t) in enumerate(batch)}
    kinds = {str(i): k for i, (k, _) in enumerate(batch)}
    msg = PROMPT + '\nGlossary: ' + json.dumps(glossary(src.values()), ensure_ascii=False) + \
          '\nKinds (teller = speaker/NPC name, text = map text): ' + json.dumps(kinds) + \
          '\nInput: ' + json.dumps(src, ensure_ascii=False)
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': msg}]}
    for attempt in range(5):
        try:
            r = urllib.request.Request(URL, json.dumps(body).encode(), {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + gateway_key()})
            c = json.loads(urllib.request.urlopen(r, timeout=300).read())['choices'][0]['message']['content']
            res = json.loads(re.search(r'\{.*\}', c, re.S).group(0))
            out = {}
            for i, (_, t) in enumerate(batch):
                ko = str(res.get(str(i), '')).strip()
                if ko and TAG.findall(ko) == TAG.findall(t) and re.search(r'[가-힣]', ko) or (ko and not re.search(r'[぀-ヿ一-鿿]', t.replace('…', ''))):
                    out[t] = ko.replace(',', '‚')
            return out
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, AttributeError, KeyError) as e:
            time.sleep(10 * (attempt + 1))
    return {}
batches = [todo[i:i + 30] for i in range(0, len(todo), 30)]
with cf.ThreadPoolExecutor(4) as ex:
    for n, res in enumerate(ex.map(call, batches)):
        done.update(res)
        if n % 5 == 0:
            OUT.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding='utf-8')
            print('batch', n + 1, '/', len(batches), 'done', len(done), flush=True)
OUT.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding='utf-8')
print('finished', len(done), 'of', len(items), 'missing', len([1 for _, t in items if t not in done]), flush=True)

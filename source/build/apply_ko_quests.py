"""Korean for the town sub-quest and town-screen texts still in Japanese (2026-11-10).

F_QUEST_SUB_MST: 7EuJK9ZL description, 42ZNoa7B objective, K50szcYX step names (comma-separated list), 96ej0dxb client
("？？？(ナシャトの町)"), G4L0YIB2 names left half-translated. F_QUEST_MST: 96ej0dxb client.
Base = the already patched files in build/out/ko_names/mst_ko (names), so earlier work is kept.

  --translate  translate the strings no translation covers yet (gemini-3.8-flash-high via the local proxy) into
               translations/quests-ko/translated.json (resumable)
  (always)     patch -> build/out/ko_names/mst_ko/<same file>, report build/out/ko_quests/report.json
deploy: python -I -X utf8 build/deploy_ko_names.py --serial <adb> --only myGc0U5v,2Px75LpY,QJF37LcR,v34C8PdG,ASh8IH0b,6P9XZ7ts,94diC1bt
"""
import argparse, hashlib, json, re, sys, time, urllib.error, urllib.request, concurrent.futures as cf
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'translations/items-ko'))
import name_coverage as N                      # noqa: E402
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16   # noqa: E402

MST_KO = ROOT / 'build/out/ko_names/mst_ko'
TR = ROOT / 'translations/quests-ko/translated.json'
JP = re.compile(r'[぀-ヿ一-鿿]')
TAG = re.compile(r'<[^>]*>')
COMMA = '‚'
FIELDS = {'F_QUEST_SUB_MST': ('7EuJK9ZL', '42ZNoa7B', 'K50szcYX', '96ej0dxb', 'G4L0YIB2'),
          'F_QUEST_MST': ('96ej0dxb',),
          # town screens (2026-11-10): explanation, shop names / owners / lines, leftover names
          'F_TOWN_EXPLAIN_MST': ('VC9F3eJn',),
          'F_TOWN_STORE_MST': ('G4L0YIB2', 'mBVN12cS'),
          'F_TOWN_STORE_COMMENT_MST': ('85DIQ1nK',),
          'F_TOWN_MST': ('G4L0YIB2',),
          'F_NPC_MST': ('G4L0YIB2',)}
LISTS = {'K50szcYX'}                          # comma-separated lists: translate item by item
URL, MODEL = 'http://127.0.0.1:8317/v1/chat/completions', 'gemini-3.8-flash-high'


def table_rows(table):
    token, key = N.masters()[table]
    src = next(MST_KO.glob(f'Ver*_{token}.dat'), None)
    if src is None:                            # not patched before: start from the JP original
        orig = next((N.OLD / 'downloads/ffbejpdata-archive-org').glob(f'Ver*_{token}.dat'))
        src = MST_KO / orig.name
        src.write_bytes(orig.read_bytes())
    k16 = key16(key)
    lines = src.read_text(encoding='ascii').splitlines()
    first = cbc_decrypt(k16, lines[0]); pad = first[-1]
    double = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
    rows = N.D.decode(src.read_bytes(), key)[1]
    assert len(rows) == len(lines)
    return src, k16, lines, rows, double


def units(table, field, value):
    if not isinstance(value, str) or not JP.search(value):
        return []
    return [p for p in value.split(',') if JP.search(p)] if field in LISTS else [value]


def glossary(texts, known):
    g = {}
    for t in texts:
        plain = TAG.sub('', t)
        for n in sorted((k for k in known if len(k) >= 2 and k in plain), key=len, reverse=True)[:25]:
            if n in plain:
                g[n] = known[n]; plain = plain.replace(n, '')
    return g


def translate(todo, known, done):
    prompt = ("Translate these Japanese texts from the RPG FINAL FANTASY BRAVE EXVIUS (town sub-quests: descriptions, "
              "objectives, step names, quest-giver labels like '？？？(ナシャトの町)') into natural, concise Korean game text. "
              "Keep every tag such as <br> exactly and in order; use the glossary for names and places; never use ASCII "
              "commas (use ‚ or rephrase). Reply with JSON only: {\"<id>\": \"<korean>\"}.")

    def call(batch):
        src = {str(i): t for i, t in enumerate(batch)}
        msg = prompt + '\nGlossary: ' + json.dumps(glossary(batch, known), ensure_ascii=False) + '\nInput: ' + json.dumps(src, ensure_ascii=False)
        body = json.dumps({'model': MODEL, 'messages': [{'role': 'user', 'content': msg}]}).encode()
        for attempt in range(5):
            try:
                r = urllib.request.Request(URL, body, {'Content-Type': 'application/json', 'Authorization': 'Bearer not-a-secret'})
                c = json.loads(urllib.request.urlopen(r, timeout=300).read())['choices'][0]['message']['content']
                res = json.loads(re.search(r'\{.*\}', c, re.S).group(0))
                out = {}
                for i, t in enumerate(batch):
                    ko = str(res.get(str(i), '')).strip().replace(',', COMMA)
                    if ko and TAG.findall(ko) == TAG.findall(t) and re.search(r'[가-힣]', ko) and not JP.search(ko):
                        out[t] = ko
                return out
            except (urllib.error.URLError, ValueError, AttributeError, KeyError):
                time.sleep(10 * (attempt + 1))
        return {}
    batches = [todo[i:i + 25] for i in range(0, len(todo), 25)]
    with cf.ThreadPoolExecutor(4) as ex:
        for res in ex.map(call, batches):
            done.update(res)
    return done


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--translate', action='store_true'); a = ap.parse_args()
    known = N.name_sources()[0]
    tr = json.loads(TR.read_text(encoding='utf-8')) if TR.exists() else {}
    loaded = {t: table_rows(t) for t in FIELDS}
    need = sorted({u for t, fs in FIELDS.items() for r in loaded[t][3] for f in fs for u in units(t, f, r.get(f))})
    todo = [u for u in need if u not in tr and u not in known]
    print('strings', len(need), 'already', len(need) - len(todo), 'to translate', len(todo))
    if a.translate and todo:
        for _ in range(3):
            tr = translate([u for u in need if u not in tr and u not in known], known, tr)
            TR.parent.mkdir(parents=True, exist_ok=True)
            TR.write_text(json.dumps(tr, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
    lookup = {**known, **tr}
    report = {}
    for table, fields in FIELDS.items():
        src, k16, lines, rows, double = loaded[table]
        changed, left = 0, []
        for i, row in enumerate(rows):
            new = dict(row)
            for f in fields:
                v = row.get(f)
                if not isinstance(v, str) or not JP.search(v):
                    continue
                if f in LISTS:
                    parts = [lookup.get(p, p) if JP.search(p) else p for p in v.split(',')]
                    new[f] = ','.join(p.replace(',', COMMA) for p in parts)
                else:
                    new[f] = lookup.get(v, v)
                if JP.search(new[f]):
                    left.append((i, f, v[:40]))
            if new != row:
                assert list(new) == list(row)
                lines[i] = cbc_encrypt(k16, json.dumps(new, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), double_pad=double)
                changed += 1
        src.write_text('\n'.join(lines) + '\n', encoding='ascii')
        check = N.D.decode(src.read_bytes(), N.masters()[table][1])[1]
        assert len(check) == len(rows) and all(list(a) == list(b) for a, b in zip(check, rows))
        report[table] = {'file': src.name, 'rows_changed': changed, 'japanese_left': left[:20], 'japanese_left_count': len(left),
                         'sha256': hashlib.sha256(src.read_bytes()).hexdigest()}
        print(table, src.name, 'rows changed', changed, 'Japanese left', len(left))
    out = ROOT / 'build/out/ko_quests'; out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()

"""All remaining Japanese master text -> Korean, in three steps (2026-11-10).

  extract    every display string still in Japanese, from the effective masters (build/out/ko_names/mst_ko when the
             table was patched before, else the JP original) -> translations/masters-ko/source.json
  translate  gemini-3.8-flash-high via CLIProxy (start it first, see CLAUDE.md); --backend deepseek uses the
             DeepSeek API (deepseek-flash) with the endpoint/key saved in build/out/battle_gt/config.yaml
             (GalTransl dashboard line, 2026-11-10: Gemini quota ran out at 11,862 strings); resumable cache
             translations/masters-ko/translated.json; a translation is kept only when its tags (<...>) and ASCII
             commas match the source, it contains Hangul and no kana/kanji
  apply      write the translations into build/out/ko_names/mst_ko (row count, field order and every non-target
             field kept), report build/out/ko_masters/report.json (+ deploy token list)
deploy: python -I -X utf8 build/deploy_ko_names.py --serial <adb> --only <report.json "tokens">

Tables the game uses as internal keys are not touched (EXCLUDE); F_DEFINE_MST only its user message field.
"""
import argparse, concurrent.futures as cf, hashlib, json, re, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'translations/items-ko'))
import name_coverage as N                                   # noqa: E402
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16     # noqa: E402
import fix_jp_leftovers as FIX                               # noqa: E402

MST_KO = ROOT / 'build/out/ko_names/mst_ko'
ARCHIVE = N.OLD / 'downloads/ffbejpdata-archive-org'
TR_DIR = ROOT / 'translations/masters-ko'
SOURCE, CACHE = TR_DIR / 'source.json', TR_DIR / 'translated.json'
OUT = ROOT / 'build/out/ko_masters'
URL, MODEL, TOKEN = 'http://127.0.0.1:8317/v1/chat/completions', 'gemini-3.8-flash-high', 'not-a-secret'


def use_deepseek():
    import base64
    global URL, MODEL, TOKEN
    line = (ROOT / 'build/out/battle_gt/config.yaml').read_text(encoding='utf-8').splitlines()[0]
    cfg = json.loads(base64.b64decode(line.split(':', 1)[1].strip()))
    URL, MODEL, TOKEN = cfg['endpoint'].rstrip('/') + '/chat/completions', cfg['model'], cfg['token']
STRICT_JP = re.compile(r'[぀-ゟ゠-ヺヽ-ヿ一-鿿々〆]')          # kana (not ・ ー) and kanji
TAG = re.compile(r'<[^>]*>')
EXCLUDE = {'F_AI_MST', 'F_URL_MST', 'F_SWITCH_TYPE_MST', 'F_ANIMATION_MST', 'F_EFFECT_MST', 'F_ICON_MST',
           'F_BANNER_MST', 'F_ENCOUNT_FIELD_MST', 'F_CLSM_ROUND_MST', 'F_MAP_OBJECT_MST', 'F_FOOTPRINT_MST',
           'F_STATIC_PARTY_DECK_MST', 'F_RB_AI_PATTERN_MST'}
FIELD_ONLY = {'F_DEFINE_MST': {'YjIUDJ97'}}
# translation order: what the player meets first
PRIORITY = ['F_UNIT_EXPLAIN_MST', 'F_JOB_MST', 'F_UNIT_CHARACTER_MST', 'F_NV_EX_CLASS_UP_MST', 'F_RULE_MST',
            'F_MISSION_MST', 'F_CHALLENGE_MST', 'F_SP_CHALLENGE_MST', 'F_BEAST_MST', 'F_BEAST_SKILL_MST',
            'F_MONSTER_DICTIONARY_EXPLAIN_MST', 'F_SUBLIMATION_RECIPE_MST', 'F_CAPTURE_MST']


def rows_of(table):
    token, key = N.masters()[table]
    src = next(MST_KO.glob(f'Ver*_{token}.dat'), None) or next(ARCHIVE.glob(f'Ver*_{token}.dat'))
    return src, key, N.D.decode(src.read_bytes(), key)[1]


def walk_fields(row, table):
    for f, v in row.items():
        if table in FIELD_ONLY and f not in FIELD_ONLY[table]:
            continue
        if isinstance(v, str) and STRICT_JP.search(TAG.sub('', v)):
            yield f, v


def extract():
    tables = json.loads((ROOT / 'build/out/inventory_now/remaining.json').read_text(encoding='utf-8'))['tables']
    src = {}
    for table in sorted(tables):
        if table in EXCLUDE or table not in N.masters():
            continue
        _, _, rows = rows_of(table)
        fields = {}
        for r in rows:
            for f, v in walk_fields(r, table):
                fields.setdefault(f, set()).add(v)
        if fields:
            src[table] = {f: sorted(v) for f, v in fields.items()}
    TR_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE.write_text(json.dumps(src, ensure_ascii=False, indent=0), encoding='utf-8')
    uniq = {s for t in src.values() for vs in t.values() for s in vs}
    print('tables', len(src), 'unique strings', len(uniq), 'chars', sum(map(len, uniq)))


def valid(src, ko):
    if not ko or not re.search(r'[가-힣]', ko) or STRICT_JP.search(TAG.sub('', ko)):
        return False
    if TAG.findall(ko) != TAG.findall(src):
        return False
    return TAG.sub('', ko).count(',') == TAG.sub('', src).count(',')


def translate(workers):
    src = json.loads(SOURCE.read_text(encoding='utf-8'))
    known = N.name_sources()[0]
    done = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    order = [t for t in PRIORITY if t in src] + sorted(t for t in src if t not in PRIORITY)
    todo, seen = [], set(done)
    for t in order:
        for vs in src[t].values():
            for s in vs:
                if s in seen:
                    continue
                seen.add(s)
                if s in known and re.search(r'[가-힣]', known[s]):
                    done[s] = known[s]
                else:
                    todo.append(s)
    batches, cur, size = [], [], 0
    for s in todo:
        if cur and (size + len(s) > 2500 or len(cur) >= 30):
            batches.append(cur); cur, size = [], 0
        cur.append(s); size += len(s)
    if cur:
        batches.append(cur)
    names = sorted((k for k in known if len(k) >= 2), key=len, reverse=True)
    prompt = ("Translate these Japanese texts from the RPG FINAL FANTASY BRAVE EXVIUS (unit profiles and quotes, "
              "ability descriptions, monster encyclopedia, quest and rule texts, item and UI labels) into natural "
              "Korean game text. Rules: keep every tag (<br>, <color=...>, </color>, <param=...> ...) exactly and in "
              "order; keep ASCII commas exactly where they are (they are separators) and never add new ones (use ‚ "
              "or rephrase); keep numbers, % and symbols; use the glossary for names; keep unit speech style; "
              "no Japanese characters in the output. Reply with JSON only: {\"<id>\": \"<korean>\"}.")
    lock = threading.Lock()

    def gloss(batch):
        g = {}
        for t in batch:
            plain = TAG.sub('', t)
            for n in names:
                if len(g) >= 40:
                    break
                if n in plain:
                    g[n] = known[n]; plain = plain.replace(n, '')
        return g

    def call(batch):
        msg = prompt + '\nGlossary: ' + json.dumps(gloss(batch), ensure_ascii=False) + \
              '\nInput: ' + json.dumps({str(i): s for i, s in enumerate(batch)}, ensure_ascii=False)
        body = json.dumps({'model': MODEL, 'messages': [{'role': 'user', 'content': msg}]}).encode()
        for attempt in range(6):
            try:
                r = urllib.request.Request(URL, body, {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN})
                c = json.loads(urllib.request.urlopen(r, timeout=300).read())['choices'][0]['message']['content']
                res = json.loads(re.search(r'\{.*\}', c, re.S).group(0))
                out = {}
                for i, s in enumerate(batch):
                    ko = FIX.fix(str(res.get(str(i), '')).strip())
                    if ',' not in TAG.sub('', s):    # no separators in the source: a comma the model added is prose
                        ko = ''.join(part if part.startswith('<') else part.replace(',', '‚') for part in re.split(r'(<[^>]*>)', ko))
                    if valid(s, ko):
                        out[s] = ko
                return out
            except (urllib.error.URLError, ValueError, AttributeError, KeyError, TimeoutError, OSError):
                time.sleep(15 * (attempt + 1))
        return {}

    print('known names reused', sum(1 for s in done if s in known), 'to translate', len(todo), 'batches', len(batches), flush=True)
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(call, b) for b in batches]
        for n, fut in enumerate(cf.as_completed(futs), 1):
            res = fut.result()
            with lock:
                done.update(res)
                if n % 10 == 0 or n == len(futs):
                    CACHE.write_text(json.dumps(done, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
                    print('batch %d/%d translated %d (%.0f min)' % (n, len(futs), len(done), (time.time() - t0) / 60), flush=True)
    left = [s for s in todo if s not in done]
    print('finished: translated', len(done), 'left', len(left), flush=True)


def apply():
    src = json.loads(SOURCE.read_text(encoding='utf-8'))
    tr = json.loads(CACHE.read_text(encoding='utf-8'))
    report, tokens = {}, []
    for table in src:
        token, key = N.masters()[table]
        srcfile, _, rows = rows_of(table)
        k16 = key16(key)
        lines = srcfile.read_text(encoding='ascii').splitlines()
        first = cbc_decrypt(k16, lines[0]); pad = first[-1]
        double = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
        changed, fields, left = 0, {}, 0
        for i, row in enumerate(rows):
            new = dict(row)
            for f, v in walk_fields(row, table):
                if v in tr:
                    new[f] = tr[v]; fields[f] = fields.get(f, 0) + 1
                else:
                    left += 1
            if new != row:
                lines[i] = cbc_encrypt(k16, json.dumps(new, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), double_pad=double)
                changed += 1
        if not changed:
            report[table] = {'rows_changed': 0, 'japanese_left': left}
            continue
        dst = MST_KO / srcfile.name
        dst.write_text('\n'.join(lines) + '\n', encoding='ascii')
        check = N.D.decode(dst.read_bytes(), key)[1]
        assert len(check) == len(rows) and all(list(a) == list(b) for a, b in zip(check, rows)), table
        report[table] = {'file': dst.name, 'rows_changed': changed, 'fields': fields, 'japanese_left': left,
                         'sha256': hashlib.sha256(dst.read_bytes()).hexdigest()}
        tokens.append(token)
        print(table, dst.name, 'rows', changed, 'left', left)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.json').write_text(json.dumps({'tokens': ','.join(tokens), 'tables': report}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('tables changed', len(tokens), '-> deploy --only', ','.join(tokens))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['extract', 'translate', 'apply'])
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--backend', choices=['proxy', 'deepseek'], default='proxy')
    a = ap.parse_args()
    if a.backend == 'deepseek':
        use_deepseek()
    {'extract': extract, 'translate': lambda: translate(a.workers), 'apply': apply}[a.step]()

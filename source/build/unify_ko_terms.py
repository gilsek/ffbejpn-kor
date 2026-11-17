"""Unify Korean spellings that drifted between translation passes (2026-11-10).

土の神殿 = 「땅의 신전」 (translations/pilot-ko/shared_gpt_dict.txt: official name, never 「흙의 신전」).
Rewrites, in place:
  1. translation sources: masters-ko/translated.json, events-ko/{patches,translated,manifest}.json,
     map-ko/{map_text_ko,map_teller_ko}.json, quests-ko/translated.json (values only)
  2. the already patched masters in build/out/ko_names/mst_ko (every string field; row count/field order kept)
     -> prints the tokens to deploy: python -I -X utf8 build/deploy_ko_names.py --serial <adb> --only <tokens>
Then rebuild the maps: python -I -X utf8 build/apply_ko_map.py and deploy the changed ones.

usage: python -I -X utf8 build/unify_ko_terms.py
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'translations/items-ko'))
import name_coverage as N                                   # noqa: E402
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16     # noqa: E402

TERMS = {'흙의 신전': '땅의 신전', '대지의 신전': '땅의 신전', '토의 신전': '땅의 신전'}
SOURCES = ['translations/masters-ko/translated.json', 'translations/events-ko/patches.json',
           'translations/events-ko/translated.json', 'translations/events-ko/manifest.json',
           'translations/map-ko/map_text_ko.json', 'translations/map-ko/map_teller_ko.json',
           'translations/quests-ko/translated.json']
MST_KO = ROOT / 'build/out/ko_names/mst_ko'


def fix(s):
    for a, b in TERMS.items():
        s = s.replace(a, b)
    return s


def walk(v):
    if isinstance(v, str):
        return fix(v)
    if isinstance(v, list):
        return [walk(x) for x in v]
    if isinstance(v, dict):
        return {k: walk(x) for k, x in v.items()}
    return v


def main():
    for rel in SOURCES:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding='utf-8')
        if not any(a in text for a in TERMS):
            continue
        data = json.loads(text)
        new = walk(data)
        indent = 1 if '\n ' in text[:200] else 0
        p.write_text(json.dumps(new, ensure_ascii=False, indent=indent, sort_keys=rel.endswith('masters-ko/translated.json')), encoding='utf-8')
        print('source', rel, sum(text.count(a) for a in TERMS))
    by_token = {tok: (t, key) for t, (tok, key) in N.masters().items()}
    tokens = []
    for f in sorted(MST_KO.glob('Ver*_*.dat')):
        tok = f.stem.split('_', 1)[1]
        if tok not in by_token:
            continue
        table, key = by_token[tok]
        raw = f.read_bytes()
        rows = N.D.decode(raw, key)[1]
        if not any(a in json.dumps(r, ensure_ascii=False) for r in rows for a in TERMS):
            continue
        k16 = key16(key)
        lines = f.read_text(encoding='ascii').splitlines()
        first = cbc_decrypt(k16, lines[0]); pad = first[-1]
        double = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
        n = 0
        for i, r in enumerate(rows):
            new = {k: fix(v) if isinstance(v, str) else v for k, v in r.items()}
            if new != r:
                lines[i] = cbc_encrypt(k16, json.dumps(new, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), double_pad=double)
                n += 1
        f.write_text('\n'.join(lines) + '\n', encoding='ascii')
        check = N.D.decode(f.read_bytes(), key)[1]
        assert len(check) == len(rows), table
        tokens.append(tok)
        print('master', table, f.name, 'rows', n)
    print('deploy --only', ','.join(tokens))


if __name__ == '__main__':
    main()

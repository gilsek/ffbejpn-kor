"""Apply the difficulty-grade decisions to every built Korean master and the engine monster-name dictionary,
in place (re-running build/apply_ko_names.py would drop Korean that later scripts wrote into the same files).
Grade decisions (user, 2026-11-11; Namu Wiki has no Korean names for them):
  超級 -> 특급  (Gemini/Memorial mixed 특급/초특급/최상급/슈퍼급/초월급/초급/상급; 초급 collides with 初級)
  獄級 -> 지옥급 (only ジエ・リヴォース討伐・獄級; never in the same quest series as 地獄級)
Each Korean string field is paired with the same row/field of the Japanese original (build/out/ko_names/mst_ko
rows are in source order); only fields whose Japanese has the grade are touched, and a variant is kept when the
Japanese also has the word it legitimately translates (初級 초급, 上級 상급, 最上級 최상급).
Unchanged rows stay byte-identical.
usage: python -I translations/names-ko/apply_grade_fix.py  -> prints the master tokens to deploy"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import name_coverage as NC
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16
from decode_client_data import json_record

RULES = [('超級', ['초특급', '최상급', '슈퍼급', '초월급', '초급', '상급'], '특급', {'초급': '初級', '상급': '上級', '최상급': '最上級'}),
         ('獄級', ['옥급'], '지옥급', {})]


def fix(jp, ko):
    for grade, variants, want, legit in RULES:
        if grade not in jp.replace('地獄級', ''):
            continue
        for v in variants:
            if v in legit and legit[v] in jp:
                continue
            ko = re.sub(r'(?<![가-힣])옥급' if v == '옥급' else v, want, ko)
    return ko


def main():
    keys = {tok: key for tok, key in NC.masters().values()}
    src = NC.OLD / 'downloads/ffbejpdata-archive-org'
    tokens, total = [], 0
    for f in sorted((ROOT / 'build/out/ko_names/mst_ko').glob('Ver*_*.dat')):
        tok = f.stem.split('_', 1)[1]
        orig = src / f.name
        if tok not in keys or not orig.exists():
            continue
        k16 = key16(keys[tok])
        jp_lines = [l for l in orig.read_text(encoding='ascii').splitlines() if l.strip()]
        lines = f.read_text(encoding='ascii').splitlines()
        body = [i for i, l in enumerate(lines) if l.strip()]
        assert len(body) == len(jp_lines), f.name
        first = cbc_decrypt(k16, lines[body[0]]); pad = first[-1]
        double_pad = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
        n = 0
        for i, jl in zip(body, jp_lines):
            if lines[i] == jl:
                continue  # untranslated row
            jr = json_record(cbc_decrypt(k16, jl))
            if not any(isinstance(v, str) and ('超級' in v or '獄級' in v) for v in jr.values()):
                continue
            row = json_record(cbc_decrypt(k16, lines[i])); hit = False
            for fld, v in row.items():
                if isinstance(v, str) and isinstance(jr.get(fld), str):
                    new = fix(jr[fld], v)
                    if new != v:
                        row[fld] = new; hit = True
            if hit:
                enc = cbc_encrypt(k16, json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                                  double_pad=double_pad)
                assert json_record(cbc_decrypt(k16, enc)) == row
                lines[i] = enc; n += 1
        if n:
            f.write_text('\n'.join(lines) + '\n', encoding='ascii'); tokens.append(tok); total += n
            print(f.name, 'rows', n)
    ov = ROOT / 'build/engine_overlay/jp_monster_names_ko.json'
    names = json.loads(ov.read_text(encoding='utf-8')); m = 0
    for jp, ko in names.items():
        new = fix(jp, ko)
        if new != ko:
            names[jp] = new; m += 1
    if m:
        ov.write_text(json.dumps(names, ensure_ascii=False, sort_keys=True, indent=1) + '\n', encoding='utf-8')
    print('master rows', total, '| engine monster names', m, '| tokens', ','.join(tokens))


if __name__ == '__main__':
    main()

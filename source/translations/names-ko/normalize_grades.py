"""Make difficulty-grade words consistent in names_pass*.json.
Decisions: 超級 -> 특급 everywhere (2026-11-09, user re-confirmed 2026-11-11: Gemini mixed 특급/초특급/최상급/슈퍼급/
초월급/초급/상급; 초급 collides with 初級). 獄級 -> 지옥급 (user 2026-11-11; only ジエ・リヴォース討伐・獄級, never in the
same quest series as 地獄級). Namu Wiki has no Korean names for these grades (checked 2026-11-11).
A variant is replaced only when the Japanese has the grade and not a word that legitimately gives that variant
(初級 -> 초급, 上級 -> 상급, 最上級 -> 최상급, 地獄級 -> 지옥급).
usage: python -I translations/names-ko/normalize_grades.py"""
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
RULES = [  # (grade in Japanese, Korean variants, wanted, Japanese words that make a variant legitimate)
    ('超級', ['초특급', '최상급', '슈퍼급', '초월급', '초급', '상급'], '특급', {'초급': '初級', '상급': '上級', '최상급': '最上級'}),
    ('獄級', ['옥급'], '지옥급', {}),
]
for f in sorted(HERE.glob('names_pass[0-9].json')):
    d = json.loads(f.read_text(encoding='utf-8')); n = 0
    for jp, ko in d.items():
        new = ko
        for grade, variants, want, legit in RULES:
            if grade not in jp.replace('地獄級', ''):
                continue
            for v in variants:  # longest first; 옥급 only as a whole word (not inside 지옥급)
                if v in legit and legit[v] in jp:
                    continue
                new = re.sub(rf'(?<![가-힣]){v}' if v == '옥급' else v, want, new)
        if new != ko:
            d[jp] = new; n += 1
    f.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding='utf-8')
    print(f.name, 'normalized', n)

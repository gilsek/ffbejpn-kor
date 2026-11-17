"""Hand fixes after the GalTransl name passes (2026-11-09): kanji Gemini left in a few values, 4 NPC names.
usage: python -I translations/names-ko/manual_fixes.py"""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPLACE = [('초급(超級)', '특급'), ('超級', '특급'), ('魔人급', '마인급'), ('시련 改', '시련 개')]
EXTRA = {'古い日記': '낡은 일기', '吟遊詩人': '음유시인', '店員': '점원', '謎の男': '수수께끼의 남자'}
for f in sorted(HERE.glob('names_pass[0-9].json')):
    d = json.loads(f.read_text(encoding='utf-8')); n = 0
    for jp, ko in d.items():
        new = ko
        for a, b in REPLACE:
            new = new.replace(a, b)
        if new != ko:
            d[jp] = new; n += 1
    if f.name == 'names_pass3.json':
        for jp, ko in EXTRA.items():
            d.setdefault(jp, ko)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding='utf-8')
    print(f.name, 'fixed', n)

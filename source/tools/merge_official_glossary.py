import csv
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

dict_path = "artifacts/chapter1-ko/Dict/gpt_dict.txt"

# 1. Read existing gpt_dict.txt
existing_entries = {}
existing_lines = []

with open(dict_path, "r", encoding="utf-8") as f:
    for line in f:
        existing_lines.append(line.rstrip("\r\n"))
        parts = line.strip().split("\t")
        if len(parts) >= 2:
            existing_entries[parts[0]] = (parts[1], parts[2] if len(parts) > 2 else "")

print(f"Existing entries in gpt_dict.txt: {len(existing_entries)}")

new_entries = {}

# 2. Add Monsters from CH1_MONSTER_TRANSLATIONS
sys.path.append("artifacts/chapter1-ko")
try:
    from ch1_monster_dict import CH1_MONSTER_TRANSLATIONS
    for jp, ko in CH1_MONSTER_TRANSLATIONS.items():
        if jp not in existing_entries and jp not in new_entries:
            new_entries[jp] = (ko, "마물 명칭 (공식 한글판 명칭)")
except Exception as e:
    print("Monster dict import error:", e)

# 3. Add Magic / Spells / Abilities from export_chapter1_csvs.py SPELL_DICT
SPELL_DICT = {
    'ファイア': '파이어', 'ファイラ': '파이라', 'ファイガ': '파이가',
    'ブリザド': '블리자드', 'ブリザラ': '블리자라', 'ブリザガ': '블리자가',
    'サンダー': '선더', 'サンダラ': '선더라', 'サンダガ': '선더가',
    'ウォータ': '워터', 'ウォタラ': '워터라', 'ウォタガ': '워터가',
    'ウォータ剣': '워터검', 'ファイア剣': '파이어검', 'ブリザド剣': '블리자드검', 'サンダー剣': '선더검',
    'エアロ': '에어로', 'エアロラ': '에어로라', 'エアロガ': '에어로가',
    'ストーン': '스톤', 'ストンラ': '스톤라', 'ストンガ': '스톤가',
    'ケアル': '케알', 'ケアルラ': '케알라', 'ケアルガ': '케알가',
    'プロテス': '프로테스', 'シェル': '셸', 'フェイス': '페이스', 'ブレイブ': '브레이브',
    'ポイゾナ': '포이조나', 'ブラナ': '블라인나', 'サイ레ナ': '사일레나', 'ストナ': '스토나',
    'エスナ': '에스나', 'ディスペル': '디스펠', 'レイズ': '레이즈', 'アレイズ': '아레이즈',
    'バファイ': '바파이', 'バファイラ': '바파이라', 'バブリザ': '바블리자', 'バブリザラ': '바블리자라',
    'バサンダ': '바선더', 'バサンダラ': '바선더라', 'バウォタ': '바워터', 'バウォタラ': '바워터라',
    'バエアロ': '바에어로', 'バエアロラ': '바에어로라', 'バストン': '바스톤', 'バストンラ': '바스톤라',
    'バイオ': '바이오', 'バイオラ': '바이오라', 'バイオブラスター': '바이오 블래스터',
    'ポーション': '포션', 'ハイポーション': '하이포션', 'エーテル': '에테르',
    'バニシュ': '바니슈', 'バニシュラ': '바니슈라', 'バニシュガ': '바니슈가',
    '明鏡': '명경', '醒夢': '성몽', 'いのり': '기도', 'たくす': '양도', 'ぬすむ': '훔치기',
    'はげます': '격려', 'まもり': '방어',
    'ディアボロス': '디아볼로스', 'カーバンクル': '카벙클', 'オーディン': '오딘',
    'タイタン': '타이탄', 'ラクシュミ': '라크슈미', 'テトラシルフィード': '테트라 실피드',
    'バハムート': '바하무트', 'フェンリル': '펜리르', '阿修羅': '아수라', 'アレキサンダー': '알렉산더',
    'フェニックス': '피닉스'
}
for jp, ko in SPELL_DICT.items():
    if jp not in existing_entries and jp not in new_entries:
        new_entries[jp] = (ko, "마법/어빌리티/환수 (공식 한글판 명칭)")

# 4. Add Town and Facility Names from chapter1_town_npcs_and_shops.csv
town_csv = "artifacts/chapter1-ko/csv_exports/chapter1_town_npcs_and_shops.csv"
if os.path.exists(town_csv):
    with open(town_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            cat = row.get("category", "")
            if "Name" in cat:
                jp = row.get("japanese", "").strip()
                ko = row.get("korean", "").strip()
                if jp and ko and jp not in existing_entries and jp not in new_entries:
                    new_entries[jp] = (ko, f"{cat} (공식 한글판 명칭)")

# 5. Add Battle Notice / Skill Names from chapter1_battle_skills.csv
battle_csv = "artifacts/chapter1-ko/csv_exports/chapter1_battle_skills.csv"
if os.path.exists(battle_csv):
    with open(battle_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            jp = row.get("japanese", "").strip()
            ko = row.get("korean", "").strip()
            # Only add if korean is valid and not english copy
            if jp and ko and jp != ko:
                has_hangul = any('\uac00' <= ch <= '\ud7a3' for ch in ko)
                if has_hangul and len(jp) <= 20 and jp not in existing_entries and jp not in new_entries:
                    new_entries[jp] = (ko, "전투 기술/알림 (공식 한글판 명칭)")

print(f"Total new unique entries to add: {len(new_entries)}")

# 6. Safe Backup & Write Merged Dictionary
backup_path = dict_path + ".bak_core80"
if not os.path.exists(backup_path):
    import shutil
    shutil.copy2(dict_path, backup_path)
    print(f"Backed up original 80 entries to {backup_path}")

with open(dict_path, "w", encoding="utf-8") as f:
    for line in existing_lines:
        f.write(line + "\n")
    f.write("\n# =========================================================================\n")
    f.write("# FFBE Official Database Bulk Glossary (Chapter 1 Expansion: Monsters, Spells, Towns, Battle)\n")
    f.write("# =========================================================================\n")
    for jp, (ko, note) in new_entries.items():
        f.write(f"{jp}\t{ko}\t{note}\n")

total_lines = len(existing_lines) + len(new_entries)
print(f"Successfully updated {dict_path}!")
print(f"Total entries: {len(existing_entries) + len(new_entries)} (Original: {len(existing_entries)} + New: {len(new_entries)})")


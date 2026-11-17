import glob
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

terms_to_check = [
    ('土の神殿', '땅의 신전', '토의 신전'),
    ('土のクリスタル', '땅의 크리스탈', '토의 크리스탈'),
    ('グランシェルト', '그랑셸트', '그란셸트'),
    ('飛空艇', '비공정', '비행선'),
    ('幻獣', '환수', '소환수'),
    ('結界', '결계', None),
    ('ビジョン', '비전', None),
    ('ラピス', '라피스', None),
    ('ヴェリアス', '베리어스', '베리아스')
]

correct_counts = {t[1]: 0 for t in terms_to_check}
wrong_counts = {t[2]: 0 for t in terms_to_check if t[2]}

files = glob.glob('artifacts/chapter1-ko/transl_cache/*.json')
print(f"Checking {len(files)} completed cache files...")

for f in files:
    try:
        data = json.load(open(f, encoding='utf-8', errors='ignore'))
        for item in data:
            dst = item.get('post_dst_preview') or item.get('dst') or item.get('message') or ''
            for jp, correct, wrong in terms_to_check:
                if correct in dst:
                    correct_counts[correct] += 1
                if wrong and wrong in dst:
                    wrong_counts[wrong] += 1
    except Exception:
        pass

print("=== Glossary Consistency Check Results ===")
for jp, correct, wrong in terms_to_check:
    c = correct_counts[correct]
    w = wrong_counts.get(wrong, 0) if wrong else 0
    print(f"  [{jp}] -> 정식 표기 '{correct}': {c}회 | 오표기 '{wrong}': {w}회")

import glob
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

kana_pattern = re.compile(r'[\u3040-\u30ff]') # Hiragana and Katakana
tag_pattern = re.compile(r'<[^>]+>')

defect_by_model = {}

files = glob.glob('artifacts/chapter1-ko/transl_cache/*.json')

for f in files:
    try:
        data = json.load(open(f, encoding='utf-8', errors='ignore'))
        for item in data:
            model = item.get('trans_by', 'UNKNOWN')
            if model not in defect_by_model:
                defect_by_model[model] = {
                    'total': 0,
                    'kana_leak': 0,
                    'empty_dst': 0,
                    'tag_mismatch': 0,
                    'files_with_issues': set()
                }
            stats = defect_by_model[model]
            stats['total'] += 1
            
            src = item.get('pre_src') or ''
            dst = item.get('post_dst_preview') or item.get('pre_dst') or ''
            
            if not dst or not dst.strip():
                stats['empty_dst'] += 1
                stats['files_with_issues'].add(f)
                continue
                
            # Check kana leak
            # Ignore special punctuation like 「」・…
            # Only match actual kana
            kanas = kana_pattern.findall(dst)
            if kanas:
                stats['kana_leak'] += 1
                stats['files_with_issues'].add(f)
                
            # Check tag mismatch
            src_tags = tag_pattern.findall(src)
            dst_tags = tag_pattern.findall(dst)
            if len(src_tags) != len(dst_tags):
                stats['tag_mismatch'] += 1
                stats['files_with_issues'].add(f)
    except Exception:
        pass

print("=== Quality Defect Analysis by Model ===")
for model, s in sorted(defect_by_model.items(), key=lambda x: x[1]['total'], reverse=True):
    total = s['total']
    kana = s['kana_leak']
    empty = s['empty_dst']
    tag = s['tag_mismatch']
    issue_files = len(s['files_with_issues'])
    print(f"Model: {model}")
    print(f"  Total Rows: {total}")
    print(f"  Kana Leaks (일본어 잔류): {kana} ({kana/total*100:.2f}%)")
    print(f"  Empty Rows (누락): {empty}")
    print(f"  Tag Mismatches (태그 불일치): {tag} ({tag/total*100:.2f}%)")
    print(f"  Affected Files: {issue_files}")
    print()

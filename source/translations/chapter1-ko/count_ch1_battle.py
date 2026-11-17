import json
import re

with open('upstream/source/server/content/dialogue_en.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

trans = d.get('translations', {})
ch1_count = 0
ch1_sources = []

for k, v in trans.items():
    sc = v.get('scene') or ''
    ref = v.get('reference') or ''
    if re.search(r'11[1-3]\d+', sc) or re.search(r'11[1-3]\d+', ref):
        ch1_count += 1
        if len(ch1_sources) < 5:
            ch1_sources.append((sc, ref, v.get('source', ''), v.get('english', '')))

print(f"Total Chapter 1 (111-113) dialogue records in dialogue_en.json: {ch1_count}")
for s in ch1_sources:
    print(s)

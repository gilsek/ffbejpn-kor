import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/out/sprite_work'

manifest = json.load(open(WORK / 'manifest.json', encoding='utf-8'))
sizes = {m['name']: (m['w'], m['h']) for m in manifest}
ocr = json.load(open(WORK / 'ocr.json', encoding='utf-8'))

# Filter valid candidates (h >= 24 and len(ja) >= 3 and valid ko)
valid = []
for d in ocr:
    w, h = sizes.get(d['name'], (0, 0))
    if h >= 24 and len(d['ja']) >= 3 and d['ko']:
        valid.append((d, w, h))

headers, tabs, buttons, labels = [], [], [], []
for d, w, h in valid:
    n = d['name'].lower()
    if any(k in n for k in ['header', 'top', 'cap', 'title', 'info', 'bg2', 'regist']):
        headers.append((d, w, h))
    elif any(k in n for k in ['tab', 'navi', 'switch']):
        tabs.append((d, w, h))
    elif any(k in n for k in ['btn', 'button', 'diamond']):
        buttons.append((d, w, h))
    elif any(k in n for k in ['label', 'txt', 'tag']):
        labels.append((d, w, h))

# Select diverse 30 items
# 8 Buttons, 8 Labels, 7 Tabs, 7 Headers
selected = []

def pick(lst, count, kind):
    # Sort or pick distinct ja terms
    seen_ja = set()
    res = []
    # prioritize well-known UI elements
    for d, w, h in lst:
        if d['ja'] not in seen_ja and w <= 400 and h <= 120:  # standard UI sizes
            seen_ja.add(d['ja'])
            res.append({
                'name': d['name'],
                'ja': d['ja'],
                'ko': d['ko'],
                'w': w,
                'h': h,
                'kind': kind
            })
            if len(res) == count:
                break
    return res

selected.extend(pick(buttons, 8, 'Button'))
selected.extend(pick(labels, 8, 'Large Label'))
selected.extend(pick(tabs, 7, 'Tab'))
selected.extend(pick(headers, 7, 'Header'))

out = WORK / 'pilot30.json'
out.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')

print(f'Selected {len(selected)} diverse sprites:')
for i, s in enumerate(selected):
    print(f"{i+1:2d}. [{s['kind']}] {s['name']} ({s['w']}x{s['h']}): {s['ja']} -> {s['ko']}")

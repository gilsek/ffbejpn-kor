import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/out/sprite_work'

manifest = json.load(open(WORK / 'manifest.json', encoding='utf-8'))
sizes = {m['name']: (m['w'], m['h']) for m in manifest}
ocr = json.load(open(WORK / 'ocr.json', encoding='utf-8'))

small_list = []
for d in ocr:
    w, h = sizes.get(d['name'], (0, 0))
    if h < 24 or len(d['ja']) <= 2:
        small_list.append(f"{d['name']}\t{w}x{h}\t{d['ja']}\t{d['ko']}")

out = WORK / 'small.txt'
out.write_text('\n'.join(small_list), encoding='utf-8')
print(f'Written {len(small_list)} small sprites to {out}')

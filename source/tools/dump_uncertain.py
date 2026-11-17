import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/out/sprite_work'

data = json.load(open(WORK / 'ocr.json', encoding='utf-8'))
manifest = json.load(open(WORK / 'manifest.json', encoding='utf-8'))
sizes = {m['name']: (m['w'], m['h']) for m in manifest}

uncertains = [d for d in data if d['uncertain']]
lines = []
for i, u in enumerate(uncertains):
    w, h = sizes.get(u['name'], (0, 0))
    lines.append(f"{i+1:3d}. {u['name']}|{w}x{h}|{u['ja']}|{u['ko']}")

out = WORK / 'uncertain_list.txt'
out.write_text('\n'.join(lines), encoding='utf-8')
print('Written', len(lines), 'to', out)

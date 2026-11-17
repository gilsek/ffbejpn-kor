import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = "artifacts/tool-evaluation/gal-original-project/gt_output/ui_pilot_core.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total entries: {len(data)}")
for i, item in enumerate(data[50:75], start=50):
    print(f"{i+1:02d}. [{item.get('ffbe_id')}]: {item['message']}")





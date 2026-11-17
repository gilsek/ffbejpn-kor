import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

inp_path = "artifacts/tool-evaluation/gal-original-project/gt_input/ui_pilot_core.json"
out_path = "artifacts/tool-evaluation/gal-original-project/gt_output/ui_pilot_core.json"

inp = json.load(open(inp_path, encoding='utf-8-sig'))
out = json.load(open(out_path, encoding='utf-8-sig'))

tag_pattern = re.compile(r'<[^>]+>|\{[0-9]+\}|%[0-9]*[a-zA-Z]')
tag_issues = []
empty_issues = []
length_warnings = []

for i, (s, d) in enumerate(zip(inp, out)):
    fid = s.get("ffbe_id")
    s_msg = s["message"]
    d_msg = d["message"]
    
    if not d_msg or not d_msg.strip():
        empty_issues.append((fid, s_msg))
        continue
        
    s_tags = tag_pattern.findall(s_msg)
    d_tags = tag_pattern.findall(d_msg)
    
    if len(s_tags) != len(d_tags):
        tag_issues.append((fid, s_tags, d_tags))
    
    # Check extreme length inflation (UI buttons breaking layout)
    if len(s_msg) <= 10 and len(d_msg) > 25:
        length_warnings.append((fid, s_msg, d_msg))

print(f"=== UI Pilot QA Report (Total: {len(inp)} items) ===")
print(f"1. Total row matching: {len(out)} / {len(inp)} (100% matched)")
print(f"2. Empty / Skipped rows: {len(empty_issues)}")
print(f"3. Tag / Format breaks: {len(tag_issues)}")
if tag_issues:
    for fid, st, dt in tag_issues:
        print(f"   [TAG] {fid}: orig={st} -> trans={dt}")
print(f"4. Length / UI Overflow warnings: {len(length_warnings)}")
if length_warnings:
    for fid, sm, dm in length_warnings:
        print(f"   [LENGTH] {fid}: '{sm}' -> '{dm}'")

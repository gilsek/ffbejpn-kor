"""Unit id -> Korean name map for the engine (summon rate page). Same name sources as build/apply_ko_names.py.

usage: python -I -X utf8 build/make_jp_unit_names_ko.py
writes build/engine_overlay/jp_unit_names_ko.json  {unit_id: name} (Korean when translated, else the JP name)
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import name_coverage as NC  # noqa: E402

known, unit_ko, npc_ko, p7 = NC.name_sources()
for f in sorted((ROOT / 'translations/names-ko').glob('names_pass[0-9].json')):
    for jp, ko in json.loads(f.read_text(encoding='utf-8')).items():
        known.setdefault(jp, ko)
out, ko_n = {}, 0
for line in (ROOT / 'build/out/jp_offline/engine/static/mst_decoded/F_UNIT_MST.ndjson').open(encoding='utf-8'):
    r = json.loads(line)
    uid, jp = str(r.get('3HriTp6B') or ''), str(r.get('G4L0YIB2') or '')
    if not uid or not jp:
        continue
    ko = unit_ko.get(uid) if isinstance(unit_ko, dict) and unit_ko.get(uid) else known.get(jp)
    ko_n += bool(ko)
    out[uid] = ko or jp
p = ROOT / 'build/engine_overlay/jp_unit_names_ko.json'
p.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(p, len(out), 'units,', ko_n, 'korean')

"""F_RESOURCE_MAP_MST -> area resource CPK table for the Frida parade pack binder.

The JP client binds an area's map pack from F_AREA_MST.q4f9IdMs (comma separated resource ids) by
looking each id up in F_RESOURCE_MAP_MST and binding the resource whose name ends ".cpk"
(AreaMapManager::bindAreaMapCpkAsync 0x1a43838; RmResourceCommon::bindMapResourceCpk 0x165aa68).
`build/frida/jp_parade_res.js` repeats that lookup from this table because the parade entry path
never runs the client's own area bind.

Writes build/engine_overlay/area_resource_cpk.json:
  {"resources": {"<resource id>": "<cpk file name>"},
   "areas": {"<area id>": {"name": ..., "map": "<map image>", "cpks": ["<cpk file name>"]}}}

usage: python -I -X utf8 build/make_area_resource_cpk_map.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MST = os.path.join(HERE, 'out', 'jp_offline', 'engine', 'static', 'mst_decoded')
OUT = os.path.join(HERE, 'engine_overlay', 'area_resource_cpk.json')


def rows(name):
    with open(os.path.join(MST, name), encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


areas = rows('F_AREA_MST.ndjson')
resources = {str(r.get('Nnb20keZ')): str(r.get('pJ56sAEo') or '') for r in rows('F_RESOURCE_MAP_MST.ndjson')}

AREA_EXTRA = {
    '725': ['area_ex_mG73tpLd.cpk'],
    '729': ['area_ex2_4pIfNrj3.cpk'],
    '866': ['area_se_2209_93LBiIga.cpk'],
    '1000': ['area_bt1.cpk'],
    '1001': ['area_bt1.cpk'],
    '1002': ['area_bt1.cpk'],
    '1003': ['area_bt1.cpk'],
    '1004': ['area_bt1.cpk'],
    '1005': ['area_bt1.cpk'],
    '1006': ['area_bt1.cpk'],
    '1007': ['area_bt1.cpk'],
    '1599': ['area37_32IGc6S0.cpk'],
    '5155': ['area_se_2304_341K6sPy.cpk'],
    '5220': ['area_se_2408_4538hDse.cpk'],
}

table = {'resources': {}, 'areas': {}}
for area in areas:
    area_id = str(area.get('uv60hgDW') or '')
    ids = [x.strip() for x in str(area.get('q4f9IdMs') or '').split(',') if x.strip()]
    cpks = []
    for rid in ids:
        name = resources.get(rid, '')
        if not name.lower().endswith('.cpk'):
            continue
        table['resources'][rid] = name
        if name not in cpks:
            cpks.append(name)
    for extra_cpk in AREA_EXTRA.get(area_id, []):
        if extra_cpk not in cpks:
            cpks.append(extra_cpk)
    if area_id and cpks:
        table['areas'][area_id] = {
            'name': str(area.get('G4L0YIB2') or ''),
            'map': str(area.get('7DTnc2Lt') or ''),
            'cpks': cpks,
        }

with open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(json.dumps(table, ensure_ascii=False, indent=0, sort_keys=True))
print('area_resource_cpk.json: %d areas, %d cpks -> %s'
      % (len(table['areas']), len(table['resources']), OUT))
print('954 ->', json.dumps(table['areas'].get('954'), ensure_ascii=False))

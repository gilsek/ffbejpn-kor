#!/usr/bin/env python3
"""장면 파일이 없는 Rm(지도형 이벤트) 스토리 노드 목록 -> build/engine_overlay/jp_rm_noscene.json

스토리 전용 노드(F_MISSION_MST.8xi6Xvyk == '0')는 장면 cpk(리소스 id 3xxxxxxxx)가 대사를 재생하고 미션을 끝낸다.
그 장면이 일판 자료에도, 채워 넣은 자료(build/out/en_story_fill)에도 없으면 맵만 뜨고 끝나지 않는다
(2026-11-13 기기: 8660101, 장면 397960101 행 없음). 엔진(jp_compat.install_rm_modes)이 이 목록의 노드를
입장 없이 클리어한 것으로 넘긴다.

실행: python -I -X utf8 build/make_jp_rm_noscene.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MST = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
JP_FILES = Path(r'D:\Downloads\ffbejpdata\ffbejpdata')
FILL = ROOT / 'build/out/en_story_fill'
AREAS = ROOT / 'build/engine_overlay/jp_rm_areas.json'
OUT = ROOT / 'build/engine_overlay/jp_rm_noscene.json'


def ndjson(path):
    with path.open(encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def area_ids():
    data = json.loads(AREAS.read_text(encoding='utf-8'))
    items = data.get('areas', data) if isinstance(data, dict) else data
    out = set()
    for it in items:
        out.add(str(it.get('area', it.get('id', ''))) if isinstance(it, dict) else str(it))
    return out


def main():
    res = {str(r['Nnb20keZ']): r for r in ndjson(MST / 'F_RESOURCE_MAP_MST.ndjson')}
    add = FILL / 'resource_map_add.ndjson'
    if add.is_file():
        res.update({str(r['Nnb20keZ']): r for r in ndjson(add)})
    fill_files = {p.name for p in (FILL / 'flat_ko').glob('*.cpk')}

    def has_scene(rid):
        row = res.get(rid)
        name = row.get('pJ56sAEo') if row else None
        return bool(name) and (name in fill_files or (JP_FILES / name).is_file())

    areas = area_ids()
    missions, by_area, story_total = {}, {}, 0
    for r in ndjson(MST / 'F_MISSION_MST.ndjson'):
        area = str(r.get('uv60hgDW'))
        if area not in areas or str(r.get('8xi6Xvyk') or '0') != '0':
            continue
        story_total += 1
        scenes = [x for x in str(r.get('q4f9IdMs') or '').split(',') if len(x) == 9 and x[0] == '3']
        if scenes and not any(has_scene(x) for x in scenes):
            mid = str(r['qo3PECw6'])
            missions[mid] = {'area': area, 'name': r.get('G4L0YIB2', ''), 'scenes': scenes}
            by_area[area] = by_area.get(area, 0) + 1
    OUT.write_text(json.dumps({'missions': missions}, ensure_ascii=False, indent=1, sort_keys=True) + '\n',
                   encoding='utf-8')
    print('Rm areas %d, story-only nodes %d, no scene %d -> %s' % (len(areas), story_total, len(missions), OUT))
    for a in sorted(by_area, key=int):
        print('  area %s: %d' % (a, by_area[a]))


if __name__ == '__main__':
    main()

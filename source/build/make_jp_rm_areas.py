#!/usr/bin/env python3
"""Rm(지도형 이벤트) 지역 목록 -> build/engine_overlay/jp_rm_areas.json

rm_areas.tsv(build/out/vortex_season/rm_mode/)에서 first_subtype == 3 이고 map_files 가 있는
지역을 뽑는다. 725(area_ex_mG73tpLd.cpk)·729(area_ex2_4pIfNrj3.cpk)는 F_AREA_MST.q4f9IdMs 가
비어 있으나 jp_parade_res.js 및 area_resource_cpk.json 의 AREA_EXTRA 로 CPK 를 바인딩하므로
58개 전체를 저장한다.

이 목록은 세 곳이 같은 파일을 본다:
  * build/engine_overlay/jp_compat.py  JP_RM_TEST_AREAS (미션 선택·게이트 Q4kJKh8b·지역 전환)
  * build/frida/jp_offline.js          게이트 터치 시 RmEventInfo 전환(files/exvius/jp_rm_areas.json)
  * build/jp_offline_build.py          JSON 을 app.imy 에 넣고 시작 시 files/exvius/ 로 복사

실행: python -I -X utf8 build/make_jp_rm_areas.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / 'build/out/vortex_season/rm_mode/rm_areas.tsv'
OUT = ROOT / 'build/engine_overlay/jp_rm_areas.json'
FIRST_SUBTYPE = '3'          # 5040 과 같은 게이트 분기(첫 미션 subtype 3); 12 는 패러디 계열
EXTRA_CPK_AREAS = {'725', '729'}


def main():
    rows = list(csv.DictReader(TSV.open(encoding='utf-8'), delimiter='\t'))
    areas, excluded = [], []
    for row in rows:
        if row.get('first_subtype') != FIRST_SUBTYPE:
            continue
        has_cpk = bool(row.get('cpk', '').strip()) or row.get('area') in EXTRA_CPK_AREAS
        if not row.get('map_files', '').strip() or not has_cpk:
            excluded.append(row)
            continue
        areas.append(row['area'])
    areas.sort(key=int)
    OUT.write_text(json.dumps(areas, indent=2) + '\n', encoding='utf-8')
    maps = {}
    for row in rows:
        if row['area'] in areas:
            maps.setdefault(row['map_files'], []).append(row['area'])
    shared = {k: v for k, v in maps.items() if len(v) > 1}
    print('rm areas: %d -> %s' % (len(areas), OUT))
    for row in excluded:
        print('  excluded %s (%s): missing %s' % (row['area'], row['name'],
              'cpk' if not row['cpk'].strip() else 'map_files'))
    for files, ids in shared.items():
        print('  shared map %s: %s' % (files, ','.join(ids)))


if __name__ == '__main__':
    main()

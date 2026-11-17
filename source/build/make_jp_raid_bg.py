#!/usr/bin/env python3
"""레이드 화면 배경(RaidMenuInfo 7DTnc2Lt)을 일본판 raid1.cpk 파일 이름으로 바꾸는 표를 만든다.

영문판 엔진의 raid_archive.json은 레이드마다 `event_<구역>.png`(영문판 이름)를 배경으로 넘긴다. 일본판 팩에는
그 이름이 없어서 클라이언트가 배경을 못 찾고 빈칸으로 둔다(2026-11-14, 6260 봉인된 화산). 이 스크립트는
구역 -> 일본판 raid1.cpk 파일 대응표(TSV: area, file[, confidence, ...])를 읽어,
파일이 실제로 raid1.cpk 추출본에 있는지 확인한 뒤 build/engine_overlay/jp_raid_bg.json 을 쓴다.
jp_compat._jp_raid_event 가 이 표로 menu_background 를 바꾼다.

usage:
  python -I -X utf8 build/make_jp_raid_bg.py --map <TSV> [--min-confidence medium]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAID_DIR = ROOT / 'build/out/jp_offline/engine/static/cpk_extract/common_lang/area/Ver49_raid1_common'
OUT = ROOT / 'build/engine_overlay/jp_raid_bg.json'
RANK = {'high': 3, 'medium': 2, 'low': 1, 'none': 0, '': 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', type=Path, required=True)
    ap.add_argument('--min-confidence', default='medium', choices=['high', 'medium', 'low'])
    a = ap.parse_args()
    shipped = {p.name for p in RAID_DIR.glob('*.png')}
    if not shipped:
        sys.exit('raid1.cpk 추출본이 없다: %s' % RAID_DIR)
    floor = RANK[a.min_confidence]
    by_area, skipped, bad = {}, [], []
    with open(a.map, encoding='utf-8') as fh:
        for row in csv.DictReader(fh, delimiter='\t'):
            area, name = (row.get('area') or '').strip(), (row.get('file') or '').strip()
            conf = (row.get('confidence') or 'high').strip().lower()
            if not area or not name:
                skipped.append(area)
                continue
            if RANK.get(conf, 0) < floor:
                skipped.append(area)
                continue
            if name not in shipped:
                bad.append('%s:%s' % (area, name))
                continue
            by_area[area] = name
    if bad:
        sys.exit('raid1.cpk 에 없는 파일: %s' % ', '.join(bad))
    OUT.write_text(json.dumps({
        'version': 1,
        'note': 'GL raid event id -> JP raid1.cpk background (RaidMenuInfo 7DTnc2Lt); build/make_jp_raid_bg.py',
        'source': str(a.map.name),
        'min_confidence': a.min_confidence,
        'by_area': dict(sorted(by_area.items(), key=lambda kv: int(kv[0]))),
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('written %s: %d areas, skipped %d (%s)' % (OUT.name, len(by_area), len(skipped), ','.join(skipped)))


if __name__ == '__main__':
    main()

"""Korean master NAMES: re-encrypt the JP masters with Korean names (speakers, units, places, missions, monsters ...).

Tables/fields = tools/name_coverage.py TABLES. Korean = Memorial-era sources (name_coverage.name_sources) +
translations/names-ko/names_pass*.json (GalTransl/Gemini, 2026-11-09). A name with a "＠..." suffix keeps it.
Rows are re-encrypted one line at a time like the Memorial build_master_name_patches.repack_cbc_dat; unchanged
lines stay byte-identical.
Output: build/out/ko_names/mst_ko/Ver*_<token>.dat (+ report.json); build/deploy_ko_names.py installs them.

usage: python -I build/apply_ko_names.py
"""
import argparse, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import name_coverage as NC  # noqa: E402  (also puts the decoder on sys.path)
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16  # noqa: E402
from decode_client_data import json_record  # noqa: E402

OUT = ROOT / 'build/out/ko_names'


def safe(text):
    """No JSON escapes in master values: the client's master reader lost the F_DUNGEON_MST row whose new
    Korean name had ASCII quotes (MapEventStartScene crash, 2026-11-09). Originals carry none."""
    out, opening = [], True
    for ch in text:
        if ch == '"':
            out.append('“' if opening else '”'); opening = not opening
        elif ch == '\\':
            out.append('＼')
        else:
            out.append(ch)
    return ''.join(out)


def korean(known, value):
    base, at, rest = value.partition('＠')
    ko = known.get(value) or known.get(base.strip())
    if ko:
        ko = safe(ko)
    return (ko + at + rest) if ko and at else ko


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='처리할 표 이름을 쉼표로 구분 (생략하면 전체)')
    args = ap.parse_args()
    selected = set(args.only.split(',')) if args.only else set(NC.TABLES)
    if selected - set(NC.TABLES):
        ap.error('알 수 없는 표: ' + ','.join(sorted(selected - set(NC.TABLES))))
    known, unit_ko, npc_ko, p7 = NC.name_sources()
    equipment_ko = NC.equipment_names()
    for f in sorted((ROOT / 'translations/names-ko').glob('names_pass[0-9].json')):
        for jp, ko in json.loads(f.read_text(encoding='utf-8')).items():
            known.setdefault(jp, ko)
    man = NC.masters()
    item_path = ROOT / 'translations/items-ko/patches.json'
    item_patches = json.loads(item_path.read_text(encoding='utf-8')) if item_path.exists() else {}
    item_manifest_path = ROOT / 'translations/items-ko/manifest.json'
    item_tables = json.loads(item_manifest_path.read_text(encoding='utf-8'))['tables'] if item_patches else {}
    src = NC.OLD / 'downloads/ffbejpdata-archive-org'
    dest = OUT / 'mst_ko'; dest.mkdir(parents=True, exist_ok=True)
    report_path = OUT / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if args.only and report_path.exists() else {}
    for table, (idf, fields) in NC.TABLES.items():
        if table not in selected:
            continue
        if table not in man:
            continue
        tok, key = man[table]
        f = next(src.glob(f'Ver*_{tok}.dat'), None)
        if not f:
            continue
        if table in item_patches:
            assert hashlib.sha256(f.read_bytes()).hexdigest() == item_tables[table]['sha256']
        k16 = key16(key)
        lines = [l for l in f.read_text(encoding='ascii').splitlines() if l.strip()]
        first = cbc_decrypt(k16, lines[0]); pad = first[-1]
        double_pad = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
        out, changed, left = [], 0, 0
        for index, line in enumerate(lines):
            row = json_record(cbc_decrypt(k16, line))
            rid = str(row.get(idf, '')) if idf else ''
            hit = False
            for fld in fields:
                v = row.get(fld)
                if not isinstance(v, str) or not NC.JP.search(v):
                    continue
                ko = (safe(equipment_ko[rid]) if table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST')
                      and rid in equipment_ko else korean(known, v.strip()))
                if not ko and table == 'F_UNIT_MST':
                    ko = unit_ko.get(rid) or (p7.get(rid[:7]) if len(rid) == 9 else None)
                if not ko and table == 'F_NPC_MST':
                    ko = npc_ko.get(rid) or (p7.get(rid[:7]) if len(rid) == 9 and rid.startswith('1000') else None)
                if ko and ko != v:
                    row[fld] = ko; hit = True
                elif not ko:
                    left += 1
            # 아이템 전체 패치가 게시된 뒤 이름만 재실행해도 완성 이름·검색 필드를 되돌리지 않는다.
            for fld, ko in item_patches.get(table, {}).get(str(index), {}).items():
                assert fld in row and isinstance(row[fld], str)
                if row[fld] != ko:
                    row[fld] = ko; hit = True
            if hit:
                changed += 1
                out.append(cbc_encrypt(k16, json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                                       double_pad=double_pad))
            else:
                out.append(line)
        (dest / f.name).write_text('\n'.join(out) + '\n', encoding='ascii')
        if table in item_patches:
            left = sum(bool(NC.LEFT_JP.search(json_record(cbc_decrypt(k16, line)).get(fld, '')))
                       for line in out for fld in fields)
        report[table] = {'file': f.name, 'rows': len(lines), 'rows_changed': changed, 'names_left_japanese': left}
        print(f'{table} ({f.name}): {changed}/{len(lines)} rows, Japanese names left {left}')
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()

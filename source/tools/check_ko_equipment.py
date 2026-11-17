"""장비·마테리아 이름의 ID 대응, 이름 외 필드 불변, 암호화 행을 검증한다."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'build'))
import name_coverage as N
from apply_ko_names import safe


def main():
    if (ROOT / 'translations/items-ko/patches.json').exists():
        # 설명·검색 필드와 JP 명칭 보정이 추가된 이후에는 확장된 계약으로 검증한다.
        from check_ko_items import main as check_items
        check_items()
        return
    names, manifest = N.equipment_names(), N.masters()
    report = {}
    for table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST'):
        token, key = manifest[table]
        src = next((N.OLD / 'downloads/ffbejpdata-archive-org').glob(f'Ver*_{token}.dat'))
        dst = ROOT / 'build/out/ko_names/mst_ko' / src.name
        original = N.D.decode(src.read_bytes(), key)[1]
        patched = N.D.decode(dst.read_bytes(), key)[1]
        old_lines, new_lines = src.read_text(encoding='ascii').splitlines(), dst.read_text(encoding='ascii').splitlines()
        assert len(original) == len(patched) == len(old_lines) == len(new_lines)
        id_field = N.TABLES[table][0]
        changed, id_hits = 0, 0
        examples = []
        for i, (a, b) in enumerate(zip(original, patched)):
            assert {k: v for k, v in a.items() if k != 'G4L0YIB2'} == {k: v for k, v in b.items() if k != 'G4L0YIB2'}
            rid = str(a[id_field])
            if rid in names and N.JP.search(a['G4L0YIB2']):
                assert b['G4L0YIB2'] == safe(names[rid])
                id_hits += 1
            if a == b:
                assert old_lines[i] == new_lines[i]
            else:
                changed += 1
                name = b['G4L0YIB2']
                assert N.HANGUL.search(name) and not N.LEFT_JP.search(name)
                assert '"' not in name and '\\' not in name
                if len(examples) < 3:
                    examples.append({'id': rid, 'jp': a['G4L0YIB2'], 'ko': name})
        report[table] = {'file': dst.name, 'rows': len(patched), 'changed_names': changed,
                         'by_id': id_hits, 'examples': examples}
    out = ROOT / 'build/out/ko_names/equipment-check.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('PASS: 실제 ID 대응, 이름 외 모든 필드 불변, 미변경 암호화 행 불변, 전 행 복호화')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

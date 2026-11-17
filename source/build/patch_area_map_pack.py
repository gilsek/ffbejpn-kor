"""Point an area's map pack at the CPK that really holds its map images.

Why: F_AREA_MST 866 「非情は七色」 is a rerun of 796. Its map list (7DTnc2Lt) is map796_1.jpg,map796_2.jpg
and its dungeons use 796xx_1.jpg, but its resource list (q4f9IdMs) names 108529 = area_ex29 (the 872 pack:
map872_*.jpg, 872xx_1.jpg). RmAreaScene then misses map796_1.jpg and draws a null texture (SIGSEGV at
fault addr 0x3c, 2026-11-13 19:10). The images are in area_ex15 = 108515, so swap the id.
Checked 2026-11-13 over all 56 Rm areas (jp_rm_areas.json): 866 is the only one whose map images are not
in the pack its row lists.

The swap keeps the row length (6 digits -> 6 digits), so line offsets do not move.
Target: build/out/ko_names/mst_ko/Ver1543_Fvix6V0n.dat (apply_ko_names.py regenerates it -> run this after).
Idempotent. The pre-patch bytes are kept once as <name>.bak.

usage: python -I -X utf8 build/patch_area_map_pack.py
deploy: python -I build/deploy_ko_names.py --serial <adb> --only Fvix6V0n   (debuggable build, run-as)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
sys.path.insert(0, str(OLD / 'upstream/source/server'))
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))

from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16   # noqa: E402
from decode_client_data import json_record                # noqa: E402

TOKEN, KEY = 'Fvix6V0n', 'pR2DHS6i'   # tools/name_coverage.masters()['F_AREA_MST']
TARGET = ROOT / ('build/out/ko_names/mst_ko/Ver1543_%s.dat' % TOKEN)
SWAPS = {'866': ('108529', '108515')}  # area -> (listed pack id, pack id that holds its map images)


def main():
    path = TARGET
    k16 = key16(KEY)
    original = [line for line in path.read_text(encoding='ascii').splitlines() if line.strip()]
    first = cbc_decrypt(k16, original[0])
    pad = first[-1]
    double_pad = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
    fixed, changed, seen = [], [], set()
    for line in original:
        row = json_record(cbc_decrypt(k16, line))
        swap = SWAPS.get(str(row.get('uv60hgDW')))
        if not swap:
            fixed.append(line)
            continue
        seen.add(str(row['uv60hgDW']))
        ids = str(row.get('q4f9IdMs') or '').split(',')
        if swap[0] in ids:
            row['q4f9IdMs'] = ','.join(swap[1] if i == swap[0] else i for i in ids)
            new = cbc_encrypt(k16, json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                              double_pad=double_pad)
            if len(new) != len(line):
                raise SystemExit('row length changed for area %s' % row['uv60hgDW'])
            fixed.append(new)
            changed.append(str(row['uv60hgDW']))
        elif swap[1] in ids:
            fixed.append(line)
        else:
            raise SystemExit('area %s lists neither %s nor %s' % (row['uv60hgDW'], swap[0], swap[1]))
    if set(SWAPS) - seen:
        raise SystemExit('areas not found: %s' % sorted(set(SWAPS) - seen))
    if changed:
        bak = path.with_name(path.name + '.bak')
        if not bak.exists():
            bak.write_bytes(path.read_bytes())
        path.write_text('\n'.join(fixed) + '\n', encoding='ascii')
    for line in path.read_text(encoding='ascii').splitlines():
        row = json_record(cbc_decrypt(k16, line))
        if str(row.get('uv60hgDW')) in SWAPS:
            print('area', row['uv60hgDW'], 'packs', str(row.get('q4f9IdMs')).split(',')[0], 'maps', row.get('7DTnc2Lt'))
    print('patched' if changed else 'already patched', changed, 'rows', len(original))


if __name__ == '__main__':
    main()

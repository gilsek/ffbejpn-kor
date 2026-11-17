"""Point F_DUNGEON_MST rows whose icon id is 0 at the shared dummy map icon.

Why: GateDungeonScene::setListLayout (+0x38c/+0x3b0 = 0x1bc03ec/0x1bc040c) calls the 5-parameter
overload LayoutUtils::getOrCreateSpriteBatchNode(string const&, CriFileLoader*, int, int, unsigned)
(0x154709c) with IconMstList::getFileName(DungeonMst+0x58). JP F_DUNGEON_MST has 16 rows with
`0HUPxDf1` == "0" and F_ICON_MST has no row with id 0, so getFileName returns "" (0x1cafec0), the
texture load fails, and the body hands a null SpriteBatchNode to GameLayer::addChild(2,3,null)
(Ref::retain(null) = SIGSEGV). See build/out/vortex_season/dungeon_crash.md.
Rewriting those ids to 9001 (F_ICON_MST -> dummy_mapicon_000.png, already used by 27 dungeons and 26
of them in served areas) removes the empty name.

Target: the Korean F_DUNGEON_MST that build/deploy_ko_names.py pushes
(build/out/ko_names/mst_ko/Ver1339_1Bj4oy5Q.dat -> /data/local/tmp/ffbe/mst_ko/).
apply_ko_names.py regenerates that file from the JP release master, so run this AFTER it.
Idempotent: a second run finds no icon-0 rows and rewrites nothing. The pre-patch bytes are kept once
as <name>.bak; unchanged rows stay byte-identical.

Rebuild+deploy: python -I -X utf8 build/apply_ko_names.py   (regenerates from JP -> icon 0 comes back)
                python -I -X utf8 build/patch_dungeon_icon_zero.py
                python -I build/deploy_ko_names.py --serial <adb> --only 1Bj4oy5Q
deploy_ko_names.py also removes the app-side files/1Bj4oy5Q.i row-index (row lengths change here).

usage: python -I -X utf8 build/patch_dungeon_icon_zero.py [--file PATH]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
sys.path.insert(0, str(OLD / 'upstream/source/server'))
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))

from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16   # noqa: E402
from decode_client_data import json_record                # noqa: E402

TOKEN, KEY = '1Bj4oy5Q', '9bEA2SYP'   # tools/name_coverage.masters()['F_DUNGEON_MST']
ICON_KEY = '0HUPxDf1'                 # DungeonMst.iconId (+0x58, getIconId 0x1cc95f8)
DUNGEON_ID = 'U9iHsau3'               # DungeonMst.dungeonId (+0x24)
AREA_ID = 'uv60hgDW'                  # DungeonMst.areaId (+0x4c)
DUMMY_ICON = '9001'                   # F_ICON_MST -> dummy_mapicon_000.png
TARGET = ROOT / ('build/out/ko_names/mst_ko/Ver1339_%s.dat' % TOKEN)   # Ver<VERSION>_<TOKEN>.dat
ICON_MST = ROOT / 'build/out/jp_offline/engine/static/mst_decoded/F_ICON_MST.ndjson'


def icon_ids():
    if not ICON_MST.exists():
        return None
    return {str(json.loads(line)[ICON_KEY])
            for line in ICON_MST.read_text(encoding='utf-8').splitlines() if line.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default=str(TARGET), help='patch target (default: Korean deployment master)')
    args = ap.parse_args()
    path = Path(args.file)
    if not path.exists():
        raise SystemExit('target master not found: %s (run build/apply_ko_names.py first)' % path)

    k16 = key16(KEY)
    original = [line for line in path.read_text(encoding='ascii').splitlines() if line.strip()]
    first = cbc_decrypt(k16, original[0])
    pad = first[-1]
    double_pad = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad

    fixed, changed, changed_at = [], [], []
    for index, line in enumerate(original):
        row = json_record(cbc_decrypt(k16, line))
        if str(row.get(ICON_KEY)) == '0':
            row[ICON_KEY] = DUMMY_ICON
            changed.append((str(row.get(DUNGEON_ID)), str(row.get(AREA_ID))))
            changed_at.append(index)
            fixed.append(cbc_encrypt(
                k16, json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                double_pad=double_pad))
        else:
            fixed.append(line)                 # byte-identical: not re-encrypted

    bak = path.with_name(path.name + '.bak')
    if changed:
        if not bak.exists():
            bak.write_bytes(path.read_bytes())
        path.write_text('\n'.join(fixed) + '\n', encoding='ascii')

    # ---- verify the artifact by re-reading it ----
    produced = [line for line in path.read_text(encoding='ascii').splitlines() if line.strip()]
    if len(produced) != len(original):
        raise SystemExit('artifact check failed: %d rows -> %d rows' % (len(original), len(produced)))
    stale = [i for i in set(range(len(original))) - set(changed_at) if produced[i] != original[i]]
    if stale:
        raise SystemExit('artifact check failed: %d unchanged lines were rewritten' % len(stale))
    rows = [json_record(cbc_decrypt(k16, line)) for line in produced]
    left = [str(row.get(DUNGEON_ID)) for row in rows if str(row.get(ICON_KEY)) == '0']
    if left:
        raise SystemExit('artifact check failed: icon id 0 still on %s' % left)
    known = icon_ids()
    if known is not None:
        unresolved = sorted({str(row.get(ICON_KEY)) for row in rows
                             if str(row.get(ICON_KEY)) not in known}, key=int)
        if unresolved:
            raise SystemExit('artifact check failed: icon ids absent from F_ICON_MST: %s' % unresolved)

    changed = sorted(changed, key=lambda pair: int(pair[0]))
    if changed:
        print('%s: %d rows patched (%s -> %s)' % (path, len(changed), ICON_KEY, DUMMY_ICON))
        for dungeon, area in changed:
            print('  dungeon=%s area=%s' % (dungeon, area))
        print('backup: %s' % bak)
    else:
        print('%s: already patched (0 icon-0 rows, nothing written)' % path)
    print('rows=%d icon_ids_resolved=%s' % (len(produced), 'yes' if known is not None else 'not checked'))


if __name__ == '__main__':
    main()

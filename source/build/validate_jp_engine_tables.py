"""엔진 정적 표 JP 전환 검사 (docs/plans/2026-11-10-jp-engine-tables.md).

usage: python -I -X utf8 build/validate_jp_engine_tables.py [save.json]
1. apply_jp_tables_all 대상 표가 모두 JP 11.0.0 마스터와 행 단위로 같다(.global 보관본 있음).
2. 검수 대상(KEEP) 표는 영문판 그대로다.
3. 엔진이 쓰는 영문판 전용 열이 교체된 표에 없다.
4. 엔진이 하드코딩한 스위치가 JP F_SWITCH_MST에 있다.
5. 엔진 모듈 import, 세이브 로드·정합성, 팀 행·스태미나 상한·경험치, 오브 회복·슬롯 확장 호출이 예외 없이 된다.
6. 세이브의 유닛·아이템이 JP 마스터에 있다.
실패가 하나라도 있으면 종료 코드 1.
"""
import importlib, io, json, os, re, sys, traceback, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
SERVER = OLD / 'upstream/source/server'
STATIC = ROOT / 'build/out/jp_offline/engine/static'
MST = STATIC / 'mst_decoded'
SAVE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'build/out/jp_shop/save/campaign-after-slot5.json'

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.modules.setdefault('yaml', types.ModuleType('yaml'))
os.environ['FFBE_DATA'] = str(STATIC)
sys.path.insert(0, str(ROOT / 'build'))
sys.path.insert(1, str(ROOT / 'build/engine_overlay'))
sys.path.insert(2, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(3, str(SERVER))
import apply_jp_tables_all as A  # noqa: E402
import decode_client_data as D  # noqa: E402

fails = []


def check(ok, what):
    print('PASS' if ok else 'FAIL', what)
    if not ok:
        fails.append(what)


def rows(path):
    return [json.loads(l) for l in path.open(encoding='utf-8') if l.strip()]


def main():
    import zipfile
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read(
        'lib/arm64-v8a/libgame.so')
    man = {m.group(1).decode(): (m.group(2).decode(), m.group(3).decode()) for m in D.TRIPLET.finditer(native)}
    files = {p.stem.split('_', 1)[1]: p for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}

    def jp(t):
        tok, key = man[t]
        return D.decode(files[tok].read_bytes(), key, localized=False)[1]

    # 1. replaced tables == JP
    names = A.targets()
    bad = [t for t in names if not (MST / (t + '.ndjson.global')).exists() or rows(MST / (t + '.ndjson')) != jp(t)]
    check(not bad, '교체 표 %d개 = JP, 영문판 보관본 있음 %s' % (len(names), bad[:5]))

    # 2. KEEP tables untouched
    kept = [t for t in A.KEEP if (MST / (t + '.ndjson')).exists()]
    touched = [t for t in kept if (MST / (t + '.ndjson.global')).exists()]
    check(not touched, '검수 대상 %d개는 영문판 그대로 %s' % (len(kept), touched))

    # 3. English-only columns used by engine code
    srcs = {p.name: p.read_text(encoding='utf-8', errors='replace')
            for d in (SERVER, ROOT / 'build/engine_overlay') for p in d.glob('*.py')}
    used_missing = []
    for t in names:
        g = rows(MST / (t + '.ndjson.global'))
        j = rows(MST / (t + '.ndjson'))
        gone = (set().union(*map(set, g)) if g else set()) - (set().union(*map(set, j)) if j else set())
        used_missing += [(t, c) for c in gone if any(c in s for s in srcs.values())]
    check(not used_missing, '교체 표에서 사라진 열 중 엔진이 쓰는 열 없음 %s' % used_missing)

    # 4. hard-coded switches
    sw = {r['8vAYn3IX'] for r in rows(MST / 'F_SWITCH_MST.ndjson')}
    hard = sorted({m for s in srcs.values() for m in re.findall(r'["\'](100\d{5})["\']', s)})
    missing = [s for s in hard if s not in sw]
    check(not missing, '엔진 소스의 스위치 ID %d개가 JP F_SWITCH_MST에 있음 %s' % (len(hard), missing[:10]))

    # 5. smoke
    errs = []
    for p in sorted(SERVER.glob('*.py')):
        if p.stem in ('capture_server', 'android_game') or p.stem.startswith('test'):
            continue
        try:
            importlib.import_module(p.stem)
        except Exception as e:  # noqa: BLE001
            errs.append('%s: %s' % (p.stem, e))
    check(not errs, '엔진 모듈 import %s' % errs[:5])

    import player_state as ps
    import jp_compat
    jp_compat.install_shop(None)
    jp_compat.install_stores(None)
    jp_compat.install_slot_expansion(None)
    data = json.loads(SAVE.read_text(encoding='utf-8'))
    try:
        p = ps.PlayerState(data)
        issues = ps.state_coherence_issues(p.data)
        check(not issues, '세이브 로드·정합성 (%s) %s' % (SAVE.name, issues[:5]))
        lv = int(p.data['rank']['level'])
        row = p._team_row()
        check(row.get('4BI0WKjQ') == str(p.data['counts'].get('item', 0)), '팀 행 아이템 확장 칸 %s' % row.get('4BI0WKjQ'))
        check(ps.nrg_cap(lv) > 0 and ps.need_exp(lv) >= 0, '랭크 %d 스태미나 상한 %d' % (lv, ps.nrg_cap(lv)))
        body = json.dumps({'L5Nj3cKE': [{'gdR2tJI9': '11', 'Qy5EvcK1': '5'}]})
        before = p.data['counts'].get('item', 0)
        p.apply_shop_use({}, ps.SHOP_USE_REQUEST, body)
        check(p.data['counts'].get('item', 0) in (before, before + 5), '슬롯 확장 호출')
        body = json.dumps({'L5Nj3cKE': [{'gdR2tJI9': '21', 'Qy5EvcK1': '0'}]})
        p.apply_shop_use({}, ps.SHOP_USE_REQUEST, body)
        check(True, '오브 회복 호출')
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        check(False, '세이브 스모크 호출')
        return

    # 6. save contents exist in JP masters
    roster = p.data.get('roster') or []
    lost_units = sorted({str(u['master_id']) for u in roster if ps.unit_mst(u['master_id']) is None})
    check(not lost_units, '세이브 유닛 %d명이 JP F_UNIT_MST에 있음 %s' % (len(roster), lost_units[:5]))
    valid = json.loads((ROOT / 'build/engine_overlay/jp_valid_ids.json').read_text(encoding='utf-8'))
    kinds = {int(k): set(v) for k, v in valid['kinds'].items()}
    inv = p.data.get('inventory') or {}
    held = [(int(r.get('item_type', 20)), str(r['item_id'])) for r in inv.get('items', []) + inv.get('carry_items', [])]
    held += [(21, str(r['item_id'])) for r in inv.get('equipment', [])]
    lost_items = [(k, i) for k, i in held if k in kinds and i not in kinds[k]]
    check(not lost_items, '세이브 아이템·장비 %d종이 JP 마스터에 있음 %s' % (len(held), lost_items[:5]))


if __name__ == '__main__':
    main()
    print('ALL PASS' if not fails else 'FAIL %d' % len(fails))
    sys.exit(1 if fails else 0)

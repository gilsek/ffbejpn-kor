"""상점·교환소 JP 전환 검사 (docs/plans/2026-11-10-jp-shop.md 3장).

usage: python -I -X utf8 build/validate_jp_shop.py
1. 엔진 표 6개가 JP 11.0.0 마스터와 행 단위로 같다.
2. 교환소 화면 목록(overlay 적용 후 catalogue)의 모든 보상·통화가 JP 마스터에 있고 충돌 유닛이 없다.
3. 이벤트 상인(variable_store_check)의 모든 상인이 JP 메달 상인이고, 상품 보상·통화가 JP 마스터에 있다.
4. 한국어 마스터에 상점·상인 표가 있고 가나가 남지 않았다.
실패가 하나라도 있으면 종료 코드 1.
"""
import io, json, os, re, sys, types, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
STATIC = ROOT / 'build/out/jp_offline/engine/static'
TABLES = ('F_TOWN_STORE_MST', 'F_STORE_ITEM_MST', 'F_MEDAL_EXCHANGE_MST', 'F_SHOP_MST',
          'F_EXCHANGE_SHOP_ITEM_MST', 'F_GACHA_SELECT_UNIT_MST', 'F_TEAM_LV_MST')
KO_TABLES = ('F_TOWN_STORE_MST', 'F_MEDAL_EXCHANGE_MST', 'F_TOWN_STORE_COMMENT_MST')
KANA = re.compile('[\u3040-\u30ff]')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.modules.setdefault('yaml', types.ModuleType('yaml'))
os.environ['FFBE_DATA'] = str(STATIC)
sys.path.insert(0, str(ROOT / 'build/engine_overlay'))
sys.path.insert(1, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(2, str(OLD / 'upstream/source/server'))
import decode_client_data as D  # noqa: E402

fails = []


def check(ok, what):
    print('PASS' if ok else 'FAIL', what)
    if not ok:
        fails.append(what)


def main():
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read(
        'lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups())
        man[n] = (t, k)
    files = {p.stem.split('_', 1)[1]: p for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}

    def jp(table, folder=None):
        tok, key = man[table]
        src = files[tok] if folder is None else next(folder.glob('Ver*_%s.dat' % tok), None)
        return None if src is None else D.decode(src.read_bytes(), key, localized=False)[1]

    # 1. engine tables == JP
    for t in TABLES:
        eng = [json.loads(l) for l in (STATIC / 'mst_decoded' / (t + '.ndjson')).open(encoding='utf-8')]
        check(eng == jp(t), '엔진 %s = JP (%d행)' % (t, len(eng)))

    valid = json.loads((ROOT / 'build/engine_overlay/jp_valid_ids.json').read_text(encoding='utf-8'))
    ids = {int(k): set(v) for k, v in valid['kinds'].items()}
    conflict = set(valid['conflict_units'])

    def bad(kind, iid):
        kind, iid = int(kind), str(iid)
        return (kind == 10 and iid in conflict) or (kind in ids and iid not in ids[kind])

    # 2. exchange screen after the overlay
    import exvius_shop_catalogue as sc
    import jp_compat
    jp_compat.install_shop(None)
    jp_compat.install_stores(None)
    details, products, offers = sc.catalogue()
    wrong = [(pid, r['kind'], r['id']) for pid, o in offers.items() for r in o['rewards'] if bad(r['kind'], r['id'])]
    wrong += [(pid, 'cost', o['cost']) for pid, o in offers.items() if bad(*o['cost'])]
    check(not wrong, '교환소 상품 %d개의 보상·통화가 JP 마스터에 있음 %s' % (len(offers), wrong[:5]))
    check({str(p['jPV7Xc4N']) for p in products} == set(offers), '교환소 상품 목록과 구매 검증 목록이 같음')
    labels = sc.labels()
    check(set(labels) == set(offers) and not any(KANA.search(v['name']) for v in labels.values()),
          '교환소 상품 이름 %d개 모두 한국어' % len(labels))

    # 3. event merchants
    import exvius_actions_shops as sh
    stores = sh._table('F_TOWN_STORE_MST', 'Z20mNDvL')
    medals = sh._table('F_MEDAL_EXCHANGE_MST', 'S21FT3L8')
    rows = sh.archived_store_schedules()
    sids = [r['za2xsDj5'] for r in rows] + [sid for _, sid in jp_compat.FIXED_STORES]
    check(len(sids) == len(set(sids)) == 136, '이벤트 상인 136곳, 중복 없음 (%d)' % len(sids))
    check(all(stores.get(s, {}).get('kaG4xf3I') == '5' for s in sids), '이벤트 상인이 모두 JP 메달 상인')
    from exvius_rewards import parse
    linked = [medals[str(r['6uIYE15X'])] for r in sh._rows('F_STORE_ITEM_MST')
              if str(r['Z20mNDvL']) in set(sids) and str(r['YWF08vZS']) == '50' and str(r['6uIYE15X']) in medals]
    wrong = [(m['S21FT3L8'], x['kind'], x['id']) for m in linked for x in parse(m['7iJpH5zZ']) if bad(x['kind'], x['id'])]
    wrong += [(m['S21FT3L8'], 'cost', m['ak2dhKm3']) for m in linked if bad(20, m['ak2dhKm3'])]
    check(not wrong, '이벤트 상인 상품 %d개의 보상·통화가 JP 마스터에 있음 %s' % (len(linked), wrong[:5]))
    check(not any(KANA.search(v) for s in jp_compat.STORE_LINES.values() for v in s), '고정 상인 대사 한국어')

    # 4. Korean client masters
    for t in KO_TABLES:
        rows = jp(t, ROOT / 'build/out/ko_names/mst_ko')
        kana = rows and sum(1 for r in rows for v in r.values() if isinstance(v, str) and KANA.search(v))
        check(rows is not None and kana == 0, '한국어 마스터 %s (%s행, 가나 %s칸)' % (t, rows and len(rows), kana))

    print('FAIL %d' % len(fails) if fails else 'ALL PASS')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()

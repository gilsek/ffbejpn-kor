"""JP 상설 교환소 데이터와 교환소 상품 한국어 이름을 만든다 (docs/plans/2026-11-10-jp-shop.md C단계).

usage: python -I build/make_jp_shops.py
입력: build/jp_shops_source.json (공략 페이지에서 옮긴 상점·상품, 출처 URL 포함)
      JP 11.0.0 마스터(ffbejpdata-archive-org)와 한국어 마스터(build/out/ko_names/mst_ko)
출력: build/engine_overlay/jp_shops.json  {"shops": [...], "names": {"<kind>:<id>": "한국어 이름"}}
상품 보상·통화가 JP 마스터에 없거나, 충돌 유닛이거나, 수집 불가 유닛이면 실패한다.
"""
import io, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
SRC = ROOT / 'build/jp_shops_source.json'
OUT = ROOT / 'build/engine_overlay/jp_shops.json'
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(OLD / 'upstream/source/server'))
import decode_client_data as D  # noqa: E402

TABLES = {
    10: ('F_UNIT_MST', '3HriTp6B'),
    20: ('F_ITEM_MST', 'tL6G9egd'),
    21: ('F_EQUIP_ITEM_MST', 'J1YX9kmM'),
    22: ('F_MATERIA_MST', 'H5jBL0Vf'),
    23: ('F_IMPORTANT_ITEM_MST', '2dfixko3'),
    27: ('F_VISION_CARD_MST', '5giCMUd2'),
    60: ('F_RECIPE_BOOK_MST', 'staFu8U1'),
}


def load(folder, man):
    files = {p.stem.split('_', 1)[1]: p for p in folder.glob('Ver*_*.dat')}
    out = {}
    for kind, (table, col) in TABLES.items():
        tok, key = man[table]
        out[kind] = {str(r[col]): r for r in D.decode(files[tok].read_bytes(), key, localized=False)[1]}
    return out


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read(
        'lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups())
        man[n] = (t, k)
    jp = load(OLD / 'downloads/ffbejpdata-archive-org', man)
    ko = load(ROOT / 'build/out/ko_names/mst_ko', man)
    conflict = set(json.loads((ROOT / 'build/engine_overlay/jp_valid_ids.json').read_text(encoding='utf-8'))
                   ['conflict_units'])
    src = json.loads(SRC.read_text(encoding='utf-8'))
    errors, shops = [], []
    for shop in src['shops']:
        ckind, cid = shop['currency'].split(':')
        if int(ckind) != 30 and cid not in jp[int(ckind)]:
            errors.append((shop['key'], 'currency', shop['currency']))
        products = []
        for p in shop['products']:
            f = p['reward'].split(':')
            kind, iid = int(f[0]), f[1]
            row = jp.get(kind, {}).get(iid)
            if row is None:
                errors.append((shop['key'], p['name'], p['reward'], 'not in JP master'))
            elif kind == 10 and (iid in conflict or row.get('A86KwrGh') == '0'):
                errors.append((shop['key'], p['name'], p['reward'], 'conflict/uncollectable unit'))
            limit = p['limit'] if p['limit'] is not None else 2147483647
            products.append({'reward': p['reward'], 'price': int(p['price']), 'limit': int(limit)})
        shops.append({'key': shop['key'], 'name': shop['name_ko'], 'category': shop['category'],
                      'currency': [int(ckind), cid], 'reset_months': shop['reset_months'],
                      'sources': shop['sources'], 'products': products})
        print(shop['key'], shop['category'], shop['currency'], len(products), 'products')
    if errors:
        for e in errors:
            print('FAIL', e)
        sys.exit(1)
    names = {}
    for kind, rows in jp.items():
        for iid, row in rows.items():
            name = (ko[kind].get(iid) or {}).get('G4L0YIB2') or row.get('G4L0YIB2')
            if name:
                names['%d:%s' % (kind, iid)] = name.strip()
    data = {'source': 'build/jp_shops_source.json', 'shops': shops, 'names': names}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('names', len(names), '->', OUT, OUT.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()

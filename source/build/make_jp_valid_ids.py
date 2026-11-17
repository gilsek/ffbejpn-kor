"""JP 11.0.0 마스터에 있는 보상 ID 목록을 만든다 (상점 필터용, docs/plans/2026-11-10-jp-shop.md A단계).

usage: python -I build/make_jp_valid_ids.py
출력: build/engine_overlay/jp_valid_ids.json  {"kinds": {"10": [...], ...}, "conflict_units": [...], "source": {...}}
엔진(영문판 표)이 보내는 상품 중 JP 클라이언트가 모르는 ID를 거르는 데 쓴다(jp_compat.install_shop).
"""
import io, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
OUT = ROOT / 'build/engine_overlay/jp_valid_ids.json'
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(OLD / 'upstream/source/server'))
import decode_client_data as D  # noqa: E402

# 보상 종류 -> (JP 표, ID 열)
KINDS = {
    10: ('F_UNIT_MST', '3HriTp6B'),
    20: ('F_ITEM_MST', 'tL6G9egd'),
    21: ('F_EQUIP_ITEM_MST', 'J1YX9kmM'),
    22: ('F_MATERIA_MST', 'H5jBL0Vf'),
    23: ('F_IMPORTANT_ITEM_MST', '2dfixko3'),
    27: ('F_VISION_CARD_MST', '5giCMUd2'),
    60: ('F_RECIPE_BOOK_MST', 'staFu8U1'),
}
# 같은 ID에 JP와 영문판이 다른 캐릭터인 유닛 (docs/plans/2026-11-09-unit-id-mismatch.md)
CONFLICT_UNITS = ['401008507', '401008607', '401008707',
                  '401014207', '401014217', '401014307', '401014317',
                  '401014507', '401014517', '401014607', '401014617']


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read(
        'lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups())
        man[n] = (t, k)
    src = OLD / 'downloads/ffbejpdata-archive-org'
    files = {p.stem.split('_', 1)[1]: p for p in src.glob('Ver*_*.dat')}
    kinds, source = {}, {}
    for kind, (table, col) in KINDS.items():
        tok, key = man[table]
        recs = D.decode(files[tok].read_bytes(), key, localized=False)[1]
        ids = sorted({str(r[col]) for r in recs if r.get(col)}, key=int)
        kinds[str(kind)] = ids
        source[table] = files[tok].name
        print(kind, table, files[tok].name, len(ids), 'ids')
    units = set(kinds['10'])
    missing = [u for u in CONFLICT_UNITS if u not in units]
    assert not missing, ('conflict ids not in JP unit table', missing)
    data = {'kinds': kinds, 'conflict_units': CONFLICT_UNITS, 'source': source}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('->', OUT, OUT.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()

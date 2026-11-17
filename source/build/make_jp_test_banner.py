"""Build ONE test JP gacha banner (FF11 collab, JP art, fair rates) on top of the engine's gacha_authored.json.
usage: python -I build/make_jp_test_banner.py <out_dir>   -> <out_dir>/gacha_authored.json, gacha_only.txt
"""
import io, json, sys, zipfile
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix'); PRJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRJ / 'tools/upstream_ref')); sys.path.insert(0, str(OLD / 'upstream/source/server'))
import decode_client_data as D
native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
man = {}
for m in D.TRIPLET.finditer(native):
    n, t, k = (v.decode() for v in m.groups()); man[n] = (t, k)
files = {p.stem.split('_', 1)[1]: p for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}
def jp(n):
    t, k = man[n]; return D.decode(files[t].read_bytes(), k, localized=False)[1]
engine_units = {json.loads(l)['3HriTp6B'] for l in open(PRJ / 'build/out/jp_offline/engine/static/mst_decoded/F_UNIT_MST.ndjson', encoding='utf-8')}
title = [r['taQ69cIx'] for r in jp('F_GAME_TITLE_MST') if r['G4L0YIB2'] == 'FF11'][0]
units = [r for r in jp('F_UNIT_MST') if r['taQ69cIx'] == title and r['3HriTp6B'] in engine_units and int(r['9fW0TePj']) >= 5]
print('FF11 units (rarity>=5) in JP and engine:', len(units))
BID = '990101'
banner = {
    'id': BID, 'region': 'jp', 'type': 'normal', 'name': 'FF11コラボ 再録ピックアップ召喚(試験)', 'detail_id': BID,
    'exe_type': 'primary', 'cost': {'kind': 'lapis', 'amount': 1}, 'draws': 1,
    'secondary_offer': {'cost': {'kind': 'lapis', 'amount': 1}, 'draws': 11, 'exe_count': 1, 'img_btn': 'gacha_btns_gold_11'},
    'schedule': {'disp_order': 1, 'banner_type': 0, 'window': {'from': '2025-09-30 00:00:00', 'to': '2099-12-31 23:59:59'}},
    'art': {'banner': 'gacha_20250930_FF11_reprintpickup_top.png', 'detail_banner': 'gacha_20250930_FF11_reprintpickup.png',
            'anime_file': 'gacha_animation', 'anime_name': 'gacha_moogle_rare/anime', 'img_btn': 'gacha_btn_n'},
    'provenance': 'jp-test', 'source': 'jp-test',
    'pool': [{'unit_id': r['3HriTp6B'], 'rarity': int(r['9fW0TePj']), 'rate': 1.0 / len(units)} for r in units],
    'notes': 'JP test banner: FF11 collab units (JP F_UNIT_MST title FF11, also present in engine table), fair rates, art from JP gachaeffect/gacha CPK.',
}
src = OLD / 'upstream/source/server/gacha_authored.json'
doc = json.loads(src.read_text(encoding='utf-8'))
doc['banners'] = [b for b in doc['banners'] if b['id'] != BID] + [banner]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
(out / 'gacha_authored.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
(out / 'gacha_only.txt').write_text(BID + '\n', encoding='utf-8')
print('wrote', out, 'banner', BID, 'pool', len(units))

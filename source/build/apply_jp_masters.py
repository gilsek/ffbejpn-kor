"""Overwrite engine mst_decoded tables with the JP live masters (decoded with the Global libgame keys).

usage: python -I build/apply_jp_masters.py F_CHALLENGE_MST [F_SHOP_MST ...]
Global originals are kept once as <name>.ndjson.global.
"""
import io, json, shutil, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
STATIC = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(OLD / 'upstream/source/server'))
import decode_client_data as D  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
man = {}
for m in D.TRIPLET.finditer(native):
    n, t, k = (v.decode() for v in m.groups())
    man[n] = (t, k)
src = OLD / 'downloads/ffbejpdata-archive-org'
files = {p.stem.split('_', 1)[1]: p for p in src.glob('Ver*_*.dat')}
for table in sys.argv[1:]:
    tok, key = man[table]
    recs = D.decode(files[tok].read_bytes(), key, localized=False)[1]
    dst = STATIC / (table + '.ndjson')
    bak = dst.with_name(dst.name + '.global')
    if dst.exists() and not bak.exists():
        shutil.copy2(dst, bak)
    with open(dst, 'w', encoding='utf-8', newline='\n') as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(table, tok, files[tok].name, len(recs), 'rows ->', dst)

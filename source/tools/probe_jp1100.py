import sys, re, json, zipfile, hashlib, collections
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
sys.path.insert(0, str(OLD/'upstream/source/server')); sys.path.insert(0, str(Path(__file__).parent/'upstream_ref'))
import decode_client_data as D
J = Path(__file__).resolve().parents[1]/'inputs/jp1100'
n11 = (J/'arm64/lib/arm64-v8a/libgame.so').read_bytes()
with zipfile.ZipFile(OLD/'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk') as z: n9 = z.read('lib/arm64-v8a/libgame.so')
print('sha256 11.0.0', hashlib.sha256(n11).hexdigest()[:16], 'size', len(n11), '| 9.0.0', hashlib.sha256(n9).hexdigest()[:16], len(n9))
def man(n):
    m = {}
    for x in D.TRIPLET.finditer(n):
        a,t,k = (v.decode() for v in x.groups()); m[t] = (a,k)
    try:
        for t,v in D.getter_manifest(n).items(): m[t] = (v['table'], v['key'])
    except Exception as e: print('getter_manifest failed:', repr(e)[:120])
    return m
m9, m11 = man(n9), man(n11)
print('triplets 9.0.0', len(m9), '11.0.0', len(m11))
same = sum(1 for t in m11 if t in m9 and m9[t] == m11[t]); print('identical token+table+key', same,
      'same token diff key', sum(1 for t in m11 if t in m9 and m9[t][1] != m11[t][1]), 'new in 11', sum(1 for t in m11 if t not in m9))
# try decode JP live .dat with 11.0.0 keys
src = OLD/'downloads/ffbejpdata-archive-org'; ok = fail = nokey = 0; failed = []
for f in sorted(src.glob('Ver*_*.dat')):
    t = f.stem.split('_',1)[1]
    if t not in m11: nokey += 1; continue
    try: D.decode(f.read_bytes(), m11[t][1], localized=m11[t][0].startswith('F_TEXT')); ok += 1
    except Exception as e: fail += 1; failed.append((f.name, m11[t][0]))
print('JP .dat with 11.0.0 keys: ok', ok, 'fail', fail, 'nokey', nokey, failed[:5])
# strings of interest
for pat in [rb'https?://[\x21-\x7e]{6,80}', rb'(?:Localiz|setCurrentLanguage)[\x21-\x7e]{0,60}', rb'[a-z]{2}(?:-[A-Z]{2})?_sg\.txt|_sg\b']:
    for name, n in (('11', n11), ('9', n9)):
        hits = collections.Counter(x.group().decode('latin-1') for x in re.finditer(pat, n))
        print(name, pat[:20], len(hits), list(hits)[:12])

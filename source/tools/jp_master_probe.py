"""JP live master .dat -> Offline(global 9.0.0) key decrypt probe. Read-only; writes summary json only."""
import sys, json, zipfile, collections
from pathlib import Path
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
sys.path.insert(0, str(OLD/'upstream/source/server'))
sys.path.insert(0, str(Path(__file__).parent/'upstream_ref'))
import decode_client_data as D
apk = OLD/'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk'
with zipfile.ZipFile(apk) as z: native = z.read('lib/arm64-v8a/libgame.so')
man = {}
for m in D.TRIPLET.finditer(native):
    n,t,k = (v.decode() for v in m.groups()); man[t]={'table':n,'token':t,'key':k}
man.update(D.getter_manifest(native))
man['8e6PGb3p']={'table':'F_TEXT_ANALYTICS_ITEMS','token':'8e6PGb3p','key':'7nyO4pC9'}
man['0ThfQQWd']={'table':'F_TEXT_TEXT_EN','token':'0ThfQQWd','key':'s9E34w78'}
src = OLD/'downloads/ffbejpdata-archive-org'
out = {'manifest_entries':len(man),'files':[]}
for f in sorted(src.glob('Ver*_*.dat')):
    tok = f.stem.split('_',1)[1]; e = man.get(tok)
    r = {'file':f.name,'token':tok,'table':e and e['table']}
    if not e: r['status']='no_key'; out['files'].append(r); continue
    try:
        mode, recs = D.decode(f.read_bytes(), e['key'], localized=e['table'].startswith('F_TEXT'))
        r.update(status='ok',mode=mode,records=len(recs))
        if recs:
            s = recs[0]; r['sample_keys']=list(s.keys())[:12] if isinstance(s,dict) else None
            r['_first']=json.dumps(s,ensure_ascii=False)[:300]
    except Exception as ex:
        r.update(status='fail',err=str(ex)[:120])
    out['files'].append(r)
c = collections.Counter(x['status'] for x in out['files']); out['summary']=dict(c)
Path('translations/reports/jp_master_probe.json').write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding='utf-8')
print(out['summary'], 'manifest',len(man))
for x in out['files']:
    if x['status']=='ok' and any(k in (x['table'] or '') for k in ('QUEST','DUNGEON','MONSTER','ENEMY','WORLD','FIELD','MAP','STORY','TEXT_TEXT')): print(x['table'],x['records'],x['mode'])

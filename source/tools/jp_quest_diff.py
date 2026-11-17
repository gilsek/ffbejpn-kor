import sys,json,zipfile,glob,re,collections
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
OLD=Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
sys.path.insert(0,str(OLD/'upstream/source/server')); sys.path.insert(0,str(Path(__file__).parent/'upstream_ref'))
import decode_client_data as D
with zipfile.ZipFile(OLD/'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk') as z: native=z.read('lib/arm64-v8a/libgame.so')
man={}
for m in D.TRIPLET.finditer(native):
    n,t,k=(v.decode() for v in m.groups()); man[t]=(n,k)
for t,v in D.getter_manifest(native).items(): man[t]=(v['table'],v['key'])
src=OLD/'downloads/ffbejpdata-archive-org'
tabs=['F_QUEST_MST','F_DUNGEON_MST','F_MAP_EVENT_MST','F_STORY_SUB_MST','F_ENCOUNT_FIELD_MST','F_STORY_MST','F_MONSTER_MST','F_WORLD_MST']
jp={}
for f in src.glob('Ver*_*.dat'):
    t=f.stem.split('_',1)[1]
    if t in man and man[t][0] in tabs: jp[man[t][0]]=D.decode(f.read_bytes(),man[t][1])[1]
off={}
for z in glob.glob(str(OLD/'downloads/release-2026.11.04.9/exvius-data-*.zip')):
    with zipfile.ZipFile(z) as zf:
        for i in zf.infolist():
            m=re.search(r'mst_decoded/(F_[A-Z0-9_]+)\.ndjson$',i.filename)
            if m and m[1] in tabs: off[m[1]]=[json.loads(l) for l in zf.open(i)]
print('jp tables',{k:len(v) for k,v in jp.items()},'off',{k:len(v) for k,v in off.items()})
for tab in jp:
    if tab not in off: continue
    print('==',tab,'fields',list(jp[tab][0].keys())[:8])
    print(' sample',json.dumps(jp[tab][0],ensure_ascii=False)[:260])
    # find id col: first col with all-unique values
    cols=list(jp[tab][0].keys()); idc=next((c for c in cols if len({str(r.get(c)) for r in jp[tab]})==len(jp[tab])),cols[0])
    a={str(r.get(idc)) for r in jp[tab]}; b={str(r.get(idc)) for r in off[tab]}
    new=sorted(a-b); print(' idcol',idc,'jp',len(a),'off',len(b),'jp-only',len(new),'off-only',len(b-a))
    print(' jp-only prefix5',collections.Counter(s[:5] for s in new).most_common(12))
    print(' same cols',set(jp[tab][0])==set(off[tab][0]))

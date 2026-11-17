"""Read-only: engine (Global) masters vs JP 11.0.0 masters for the tables the engine code reads.
- PK overlap (first field) per table
- reward-like references "<type>:<id>:<count>" and bare 9-10 digit ids in GL rows -> missing from the JP id universe
"""
import sys, json, re, zipfile, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import jp_text_inventory as I
D = I.D
GL = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
SRV = ROOT.parent / 'ffbe_offline_modfix/upstream/source/server'
names = sorted(set(re.findall(r'"(F_[A-Z0-9_]+_MST)', ''.join(p.read_text(encoding='utf-8', errors='ignore') for p in SRV.glob('*.py')))))
with zipfile.ZipFile(I.APK_GL) as z: native = z.read('lib/arm64-v8a/libgame.so')
man = {}
for m in D.TRIPLET.finditer(native):
    n, t, k = (v.decode() for v in m.groups()); man[t] = (n, k)
man.update({t: (e['table'], e['key']) for t, e in D.getter_manifest(native).items()})
byname = {}
for f in I.MASTERS.glob('Ver*_*.dat'):
    tok = f.stem.split('_', 1)[1]
    if tok in man:
        v = int(f.stem.split('_')[0][3:])
        if man[tok][0] not in byname or byname[man[tok][0]][0] < v: byname[man[tok][0]] = (v, f, man[tok][1])
def jp_rows(name):
    if name not in byname: return None
    _, f, k = byname[name]
    try: return D.decode(f.read_bytes(), k, localized=False)[1]
    except Exception as ex: return None
def gl_rows(name):
    p = GL / (name + '.ndjson')
    if not p.is_file(): return None
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
def pk(r): return str(next(iter(r.values()))) if r else ''
UNIVERSE_T = ['F_ITEM_MST', 'F_EQUIP_ITEM_MST', 'F_MATERIA_MST', 'F_IMPORTANT_ITEM_MST', 'F_UNIT_MST', 'F_BEAST_MST',
              'F_VISION_CARD_MST', 'F_RECIPE_MST', 'F_EMBLEM_MST', 'F_TICKET_MST', 'F_ITEM_EXT_BEAST_MST']
jpu, glu = {}, {}
for t in UNIVERSE_T:
    for r in (jp_rows(t) or []): jpu[pk(r)] = t
    for r in (gl_rows(t) or []): glu[pk(r)] = t
REF = re.compile(r'(?<![\d])(\d{1,3}):(\d{6,10}):(\d+)')
out = {'universe': {'jp': len(jpu), 'gl': len(glu)}, 'tables': {}}
for name in names:
    g, j = gl_rows(name), jp_rows(name)
    if g is None:
        continue
    row = {'gl_rows': len(g), 'jp_rows': None if j is None else len(j)}
    if j is not None:
        gk, jk = {pk(r) for r in g}, {pk(r) for r in j}
        row.update(pk_common=len(gk & jk), gl_only=len(gk - jk), jp_only=len(jk - gk),
                   gl_only_sample=sorted(gk - jk)[:8], jp_only_sample=sorted(jk - gk)[:8])
    miss = collections.Counter()
    for r in g:
        for v in r.values():
            for a, b, c in REF.findall(str(v)):
                if b in glu and b not in jpu: miss[b] += 1
    if miss:
        row['gl_only_refs'] = len(miss); row['gl_only_ref_sample'] = [(i, glu[i], n) for i, n in miss.most_common(10)]
    out['tables'][name] = row
srv = collections.Counter(); where = collections.defaultdict(set)
for p in SRV.glob('*.json'):
    s = p.read_text(encoding='utf-8', errors='ignore')
    for b in set(re.findall(r'(?<!\d)(\d{9,10})(?!\d)', s)):
        if b in glu and b not in jpu: srv[b] += 1; where[b].add(p.name)
ov = ROOT / 'build/engine_overlay'
for p in ov.glob('*.json'):
    s = p.read_text(encoding='utf-8', errors='ignore')
    for b in set(re.findall(r'(?<!\d)(\d{9,10})(?!\d)', s)):
        if b in glu and b not in jpu: srv[b] += 1; where[b].add('overlay/' + p.name)
out['server_json_gl_only'] = {b: [glu[b], sorted(where[b])] for b in srv}
json.dump(out, open(ROOT / 'build/out/audit/mst_compare.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('universe', out['universe'])
for n, r in out['tables'].items():
    print(n, {k: v for k, v in r.items() if not k.endswith('sample')})
print('server json gl-only ids', len(srv))
bys = collections.Counter(f for b in srv for f in where[b]); print(bys.most_common(20))

"""Read-only: JP map_text/map_teller lines of every map CPK vs the translations in ../ffbe-jp-korean."""
import sys, re, json, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'build'))
import apply_ko_ui as U
SIB = ROOT.parent / 'ffbe-jp-korean/translations'
JP = re.compile(r'[぀-ヿ一-鿿]')
def load(d):
    ids = json.load(open(SIB / d / 'ids.json', encoding='utf8')); tr = {}
    for f in glob.glob(str(SIB / d / 'gt_output/*.json')):
        for r in json.load(open(f, encoding='utf8')):
            m = (r.get('message') or '').replace('\r', '').replace('\n', '<br>')
            if r['ffbe_id'] in ids and m:
                tr[ids[r['ffbe_id']]] = m
    return tr
text = {}; text.update(load('map_text')); text.update(load('map_text2'))
names = load('names_npc')
inv = json.load(open(ROOT / 'build/out/town/map_text_inventory.json'))
arc = Path('D:/Downloads/ffbejpdata/ffbejpdata')
miss_t, miss_n, hit_t, hit_n, uniq_t, uniq_n = {}, {}, 0, 0, set(), set()
samples = []
for name in sorted(inv):
    c = U.cpk.Cpk.load_bytes((arc / name).read_bytes(), encoding='cp932')
    for i in c.file_infos():
        if i.filename not in ('map_text.txt', 'map_teller.txt'):
            continue
        for l in c.file_bytes(i.toc_index).decode('utf-8-sig', 'replace').splitlines():
            k, sep, b = l.partition(',')
            if not sep or not JP.search(b):
                continue
            if i.filename == 'map_text.txt':
                uniq_t.add(b)
                if b in text: hit_t += 1
                else: miss_t[b] = miss_t.get(b, 0) + 1
            else:
                uniq_n.add(b)
                if b in names or b in text: hit_n += 1
                else: miss_n[b] = miss_n.get(b, 0) + 1
print('map_text unique', len(uniq_t), 'translated', len(uniq_t) - len(miss_t), 'missing', len(miss_t), 'row hits', hit_t)
print('map_teller unique', len(uniq_n), 'translated', len(uniq_n) - len(miss_n), 'missing', len(miss_n), 'row hits', hit_n)
json.dump({'text': miss_t, 'teller': miss_n}, open(ROOT / 'build/out/ko_map/missing.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
for b in list(miss_t)[:8]: print('MISS T', b[:80])
for b in list(miss_n)[:15]: print('MISS N', b)
k = next(iter(text)); print('sample', k[:80], '->', text[k][:80])

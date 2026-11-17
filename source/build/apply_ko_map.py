"""Korean map texts: resident names (map_teller.txt) and field / NPC lines, shop and place labels (map_text.txt)
inside every JP map CPK (934 files that carry them), patched IN PLACE (tools/cpk_inplace.py).

Translations, JP text -> Korean (translations/map-ko/):
  * map_text_ko.json   field / NPC lines: ../ffbe-jp-korean map_text + map_text2 (GalTransl), plus the strings
                       none of them covered, translated 2026-11-09 (gemini-3.8-flash-high, tags kept)
  * map_teller_ko.json resident names: ../ffbe-jp-korean names_npc, this project's name dictionary
                       (tools/name_coverage.py), plus new translations
  `--merge` rebuilds both files from those sources (needs ../ffbe-jp-korean and build/out/ko_map/new_translations.json);
  a plain run only reads translations/map-ko/.

Rows are "id,text" and the client splits on every ASCII comma, so Korean commas become U+201A (as in the story).
In place, not cpk.create: a rebuilt CPK loses its ID table (ITOC) and the client stops finding files by id
(map_common.cpk drew a black town map, 2026-11-09).

usage: python -I -X utf8 build/apply_ko_map.py [--merge] [--archive D:/Downloads/ffbejpdata/ffbejpdata]
output: build/out/ko_map/flat_ko/<name>.cpk, build/out/ko_map/report.json
"""
import argparse, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build')); sys.path.insert(0, str(ROOT / 'tools'))
import apply_ko_ui as U          # noqa: E402  (cricodecs cpk reader)
import cpk_inplace               # noqa: E402
TR = ROOT / 'translations/map-ko'
OUT = ROOT / 'build/out/ko_map'
JP = re.compile(r'[぀-ヿ一-鿿]')
COMMA = '‚'


def split_rows(data):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('cp932')
    nl = '\r\n' if '\r\n' in text else '\n'
    return text.split(nl), nl, data.startswith(b'\xef\xbb\xbf')


def join_rows(lines, nl, bom):
    b = nl.join(lines).encode('utf-8')
    return b'\xef\xbb\xbf' + b if bom else b


def merge():
    sib = ROOT.parent / 'ffbe-jp-korean/translations'

    def load(d):
        ids = json.load(open(sib / d / 'ids.json', encoding='utf8')); tr = {}
        for f in glob.glob(str(sib / d / 'gt_output/*.json')):
            for r in json.load(open(f, encoding='utf8')):
                m = (r.get('message') or '').replace('\r', '').replace('\n', '<br>')
                if r['ffbe_id'] in ids and m:
                    tr[ids[r['ffbe_id']]] = m
        return tr
    import name_coverage as NC
    known = NC.name_sources()[0]
    new = json.load(open(OUT / 'new_translations.json', encoding='utf-8'))
    text = {**load('map_text'), **load('map_text2')}
    for k, v in new.items():
        text.setdefault(k, v)
    teller = {**text, **load('names_npc'), **known}
    for k, v in new.items():
        teller.setdefault(k, v)
    TR.mkdir(parents=True, exist_ok=True)
    (TR / 'map_text_ko.json').write_text(json.dumps(text, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
    (TR / 'map_teller_ko.json').write_text(json.dumps(teller, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
    print('merged: map_text', len(text), 'map_teller', len(teller))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--merge', action='store_true')
    ap.add_argument('--archive', default='D:/Downloads/ffbejpdata/ffbejpdata')
    a = ap.parse_args()
    if a.merge:
        merge()
    text = json.loads((TR / 'map_text_ko.json').read_text(encoding='utf-8'))
    teller = json.loads((TR / 'map_teller_ko.json').read_text(encoding='utf-8'))
    dest = OUT / 'flat_ko'; dest.mkdir(parents=True, exist_ok=True)
    rep = {'files': 0, 'rows_changed': 0, 'rows_jp_left': 0, 'unique_left': {}, 'errors': []}
    for p in sorted(Path(a.archive).glob('*.cpk')):
        if p.stat().st_size < 20000:
            continue
        data = p.read_bytes()
        try:
            c = U.cpk.Cpk.load_bytes(data, encoding='cp932')
        except Exception:
            continue
        infos = {i.filename: i for i in c.file_infos()}
        if 'map_text.txt' not in infos and 'map_teller.txt' not in infos:
            continue
        replace = {}
        for fn, table in (('map_text.txt', text), ('map_teller.txt', teller)):
            if fn not in infos:
                continue
            lines, nl, bom = split_rows(c.file_bytes(infos[fn].toc_index))
            out = []
            for line in lines:
                k, sep, body = line.partition(',')
                if sep and JP.search(body):
                    ko = table.get(body)
                    if ko:
                        line = k + ',' + ko.replace(',', COMMA); rep['rows_changed'] += 1
                    else:
                        rep['rows_jp_left'] += 1; rep['unique_left'][body] = rep['unique_left'].get(body, 0) + 1
                out.append(line)
            new = join_rows(out, nl, bom)
            if new != c.file_bytes(infos[fn].toc_index):
                replace[infos[fn].full_path] = new
        if replace:
            try:
                (dest / p.name).write_bytes(cpk_inplace.patch(data, replace))
                rep['files'] += 1
            except Exception as ex:
                rep['errors'].append(f'{p.name}: {str(ex)[:100]}')
    left = rep['unique_left']
    rep['unique_left_count'] = len(left)
    rep['unique_left'] = dict(sorted(left.items(), key=lambda x: -x[1]))
    (OUT / 'report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"files {rep['files']}, rows changed {rep['rows_changed']}, JP rows left {rep['rows_jp_left']} "
          f"({len(left)} unique), errors {len(rep['errors'])} -> {dest}")


if __name__ == '__main__':
    main()

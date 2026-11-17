"""Build the Korean overlay: Offline story CPKs with Korean text in every language column.

usage: python -I build/apply_ko_overlay.py --release <release dir> --tables <dir of <stem>_event_text_sg.txt>
                                            --out <overlay dir>
Output tree mirrors the zip entry paths (native/common_lang/sd/event/..../VerNN_<stem>.cpk), i.e. the app's files dir.
Rows are merged by id: ids present in the Korean table replace all 8 language columns, other rows stay untouched.
"""
import argparse, collections, glob, json, re, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'vendor'))
from cricodecs import cpk

ap = argparse.ArgumentParser()
ap.add_argument('--release', required=True); ap.add_argument('--tables', required=True); ap.add_argument('--out', required=True)
a = ap.parse_args()
tables = {f.name.split('_')[0]: f for f in Path(a.tables).glob('*_event_text_sg.txt')}
entries = {}
for z in sorted(glob.glob(str(Path(a.release) / 'exvius-data-*.zip'))):
    for n in zipfile.ZipFile(z).namelist():
        m = re.search(r'native/common_lang/sd/event/.*/Ver\d+_(\d+)\.cpk$', n)
        if m and m[1] in tables: entries[m[1]] = (z, n)
out = Path(a.out); report = collections.Counter(); log = []
for stem, (z, n) in sorted(entries.items()):
    blob = zipfile.ZipFile(z).read(n)
    for enc in ('utf-8', 'latin-1'):
        try:
            c = cpk.Cpk.load_bytes(blob, encoding=enc); c.save_bytes(); break
        except (ValueError, RuntimeError):
            continue
    report['enc_' + enc] += 1
    names = [e.filename for e in c.files]
    ko = {}
    for line in tables[stem].read_text('utf-8').split('\n'):
        if line:
            p = line.split('^'); ko[p[0]] = p[1:]
    sg_i = names.index(f'{stem}_event_text_sg.txt'); txt_i = names.index(f'{stem}_event_text.txt')
    raw = c.file_bytes(sg_i).decode('utf-8'); eol = '\r\n' if '\r\n' in raw else '\n'
    rows, hit = [], 0
    for line in raw.split(eol):
        if not line: continue
        p = line.split('^')
        if p[0] in ko:
            p = [p[0]] + ko[p[0]][:len(p) - 1] + p[len(ko[p[0]]) + 1:]; hit += 1
        rows.append(p)
    c.replace_bytes(sg_i, (eol.join('^'.join(r) for r in rows) + eol).encode('utf-8'))
    # legacy "id,text" sibling: Korean in column 1
    traw = c.file_bytes(txt_i).decode('utf-8'); teol = '\r\n' if '\r\n' in traw else '\n'
    trows = []
    for line in traw.split(teol):
        if not line: continue
        k = line.split(',', 1)[0]; trows.append(k + ',' + ko[k][0] if k in ko else line)
    c.replace_bytes(txt_i, (teol.join(trows) + teol).encode('utf-8'))
    dst = out / n; dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(c.save_bytes())
    report['cpk'] += 1; report['rows_replaced'] += hit; report['rows_total'] += len(rows)
    if hit != len(rows): log.append((stem, hit, len(rows)))
print(dict(report)); print('partial:', log)
(out / '_overlay_report.json').write_text(json.dumps({'counts': report, 'partial': log}, ensure_ascii=False, indent=1), 'utf-8')

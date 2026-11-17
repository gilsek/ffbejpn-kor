"""Read-only: Japanese text still present in the EFFECTIVE masters (mst_ko file if patched, else JP original).
Compares with build/out/inventory/masters_japanese.json (pre-translation) -> per-table done/remaining.
usage: python -I -X utf8 tools/audit_remaining_ja.py [--out build/out/inventory_now]
"""
import argparse, collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jp_text_inventory as I
D, JP, walk = I.D, I.JP, I.walk
ROOT = I.ROOT
KO = ROOT / 'build/out/ko_names/mst_ko'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default=str(ROOT / 'build/out/inventory_now'))
    out = Path(ap.parse_args().out); out.mkdir(parents=True, exist_ok=True)
    import zipfile
    with zipfile.ZipFile(I.APK_GL) as z:
        native = z.read('lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups()); man[t] = {'table': n, 'key': k}
    man.update({t: {'table': e['table'], 'key': e['key']} for t, e in D.getter_manifest(native).items()})
    before = json.loads((ROOT / 'build/out/inventory/masters_japanese.json').read_text(encoding='utf-8'))['tables']
    res, failed = {}, []
    for f in sorted(I.MASTERS.glob('Ver*_*.dat')):
        tok = f.stem.split('_', 1)[1]; e = man.get(tok)
        if not e:
            failed.append(f.name); continue
        patched = KO / f.name
        src = patched if patched.exists() else f
        try:
            _, recs = D.decode(src.read_bytes(), e['key'], localized=e['table'].startswith('F_TEXT'))
        except Exception as ex:
            failed.append(f'{f.name} {ex}'[:100]); continue
        fields = collections.defaultdict(lambda: [set(), 0, ''])
        for rec in recs:
            for p, s in walk(rec):
                if JP.search(s) and s not in fields[p][0]:
                    fields[p][0].add(s); fields[p][1] += len(s); fields[p][2] = fields[p][2] or s[:50]
        res[e['table']] = {'file': f.name, 'patched': patched.exists(), 'fields': {
            p: {'unique': len(v[0]), 'chars': v[1], 'sample': v[2]} for p, v in sorted(fields.items(), key=lambda x: -x[1][1])}}
    (out / 'remaining.json').write_text(json.dumps({'tables': res, 'undecoded': failed}, ensure_ascii=False, indent=1), encoding='utf-8')
    rows = []
    for n, t in res.items():
        rem = sum(x['chars'] for x in t['fields'].values())
        b = before.get(n); orig = sum(x['chars'] for x in b['fields'].values()) if b else rem
        if orig or rem:
            rows.append((rem, orig, n, t['patched'], sum(x['unique'] for x in t['fields'].values())))
    rows.sort(reverse=True)
    to, tr = sum(r[1] for r in rows), sum(r[0] for r in rows)
    print('tables with JP before/now:', len(rows), '| chars before', to, 'remaining', tr, 'translated %.1f%%' % ((to - tr) * 100 / to))
    for r in rows[:40]:
        print('rem=%d orig=%d %s patched=%s uniq=%d' % r)
    print('undecoded:', failed)


main()

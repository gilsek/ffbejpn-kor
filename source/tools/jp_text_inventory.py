"""JP 11.0.0 translation inventory: every master-data field that carries Japanese text, plus APK CPK text files.

Read-only. Decrypts the JP masters (ffbejpdata Ver*.dat) with the Global 9.0.0 keys like tools/jp_master_probe.py,
then counts, per table and field: records with Japanese, unique strings, characters.
Also scans the APK's assets/cpk/*.cpk for text files (csv/txt/plist strings) with Japanese.

usage: python -I tools/jp_text_inventory.py [--out build/out/inventory]
"""
import argparse, collections, json, re, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'ffbe_offline_modfix'
sys.path.insert(0, str(OLD / 'upstream/source/server'))
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(ROOT / 'tools/vendor'))
import decode_client_data as D  # noqa: E402

JP = re.compile(r'[぀-ヿ一-鿿ｦ-ﾟ]')
APK_GL = OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk'
MASTERS = OLD / 'downloads/ffbejpdata-archive-org'
APK_CPK = ROOT / 'build/out/jp_offline/dec/assets/cpk'


def walk(value, path=''):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, f'{path}.{k}' if path else k)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v, path + '[]')
    elif isinstance(value, str):
        yield path, value


def masters():
    with zipfile.ZipFile(APK_GL) as z:
        native = z.read('lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups()); man[t] = {'table': n, 'key': k}
    man.update({t: {'table': e['table'], 'key': e['key']} for t, e in D.getter_manifest(native).items()})
    tables, failed = {}, []
    for f in sorted(MASTERS.glob('Ver*_*.dat')):
        tok = f.stem.split('_', 1)[1]; e = man.get(tok)
        if not e:
            failed.append(f.name + ' (no key)'); continue
        try:
            _, recs = D.decode(f.read_bytes(), e['key'], localized=e['table'].startswith('F_TEXT'))
        except Exception as ex:
            failed.append(f'{f.name} ({ex})'[:120]); continue
        fields = collections.defaultdict(lambda: {'records': 0, 'unique': set(), 'chars': 0, 'sample': ''})
        for rec in recs:
            seen = set()
            for path, s in walk(rec):
                if not JP.search(s):
                    continue
                d = fields[path]
                if path not in seen:
                    d['records'] += 1; seen.add(path)
                if s not in d['unique']:
                    d['unique'].add(s); d['chars'] += len(s)
                if not d['sample']:
                    d['sample'] = s[:60]
        if fields:
            tables[e['table']] = {'records': len(recs), 'file': f.name, 'fields': {
                p: {'records': d['records'], 'unique': len(d['unique']), 'chars': d['chars'], 'sample': d['sample']}
                for p, d in sorted(fields.items(), key=lambda x: -x[1]['chars'])}}
    return tables, failed


def apk_cpks():
    from cricodecs import cpk
    out = {}
    for f in sorted(APK_CPK.glob('*.cpk')):
        c = cpk.Cpk.load_bytes(f.read_bytes(), encoding='cp932')
        files = {}
        for info in c.file_infos():
            if not info.full_path.lower().endswith(('.csv', '.txt', '.json', '.xml', '.plist', '.ssbp', '.lua')):
                continue
            try:
                text = c.file_bytes(info.toc_index).decode('utf-8-sig', 'replace')
            except Exception:
                continue
            hits = [ln for ln in text.splitlines() if JP.search(ln)]
            if hits:
                files[info.full_path] = {'lines_with_japanese': len(hits), 'chars': sum(len(h) for h in hits), 'sample': hits[0][:80]}
        out[f.name] = files
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'build/out/inventory'))
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    tables, failed = masters()
    (out / 'masters_japanese.json').write_text(json.dumps({'tables': tables, 'undecoded': failed}, ensure_ascii=False, indent=1), encoding='utf-8')
    cpks = apk_cpks()
    (out / 'apk_cpk_text.json').write_text(json.dumps(cpks, ensure_ascii=False, indent=1), encoding='utf-8')
    tot = sum(fd['chars'] for t in tables.values() for fd in t['fields'].values())
    uniq = sum(fd['unique'] for t in tables.values() for fd in t['fields'].values())
    print('masters with Japanese:', len(tables), 'tables; unique strings', uniq, 'chars', tot, '; undecoded', len(failed))
    for name, t in sorted(tables.items(), key=lambda x: -sum(f['chars'] for f in x[1]['fields'].values()))[:60]:
        top = ', '.join(f"{p}({fd['unique']}/{fd['chars']})" for p, fd in list(t['fields'].items())[:3])
        print(f"  {name}: rows {t['records']} | {top}")
    print('APK CPK text files with Japanese:')
    for c, files in cpks.items():
        print(' ', c, len(files), 'files', sum(f['lines_with_japanese'] for f in files.values()), 'lines')


if __name__ == '__main__':
    main()

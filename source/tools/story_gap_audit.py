"""Story coverage for THIS app's archive: JP event text rows vs the Memorial Korean machine translation.

For every CPK in the JP 11.0.0 archive (ffbejpdata), reads *_event_text.txt rows that contain Japanese and checks
whether translations/chapter1-ko/gt_output/<scene>.json has the same row id with Korean.
(translations/translation-gap/ did this against the Memorial 11.1.2 asset packs; this repeats it for 11.0.0.)

usage: python -I tools/story_gap_audit.py [--archive D:/Downloads/ffbejpdata/ffbejpdata] [--out build/out/inventory]
"""
import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402

JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
HANGUL = re.compile(r'[\uac00-\ud7a3]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', default='D:/Downloads/ffbejpdata/ffbejpdata')
    ap.add_argument('--out', default=str(ROOT / 'build/out/inventory'))
    args = ap.parse_args()
    gt = {}
    for f in (ROOT / 'translations/chapter1-ko/gt_output').glob('*.json'):
        try:
            rows = json.loads(f.read_text(encoding='utf-8-sig'))
        except Exception:
            continue
        stem = f.stem.split('__', 1)[0].lower()
        d = gt.setdefault(stem, {})
        for r in rows:
            if isinstance(r, dict) and r.get('ffbe_id') is not None:
                d[str(r['ffbe_id'])] = r.get('message', '')
    scenes, errors = [], []
    for path in sorted(Path(args.archive).glob('*.cpk')):
        try:
            pkg = cpk.Cpk.load_bytes(path.read_bytes(), encoding='cp932')
            infos = [i for i in pkg.file_infos() if i.filename.endswith('_event_text.txt')]
            if not infos:
                continue
            rows = {}
            for info in infos:
                for line in pkg.file_bytes(info.toc_index).decode('utf-8-sig', 'replace').splitlines():
                    rid, sep, body = line.partition(',')
                    if sep and rid.strip() and JP.search(body):
                        rows[rid.strip()] = body
        except Exception as ex:
            errors.append(f'{path.name}: {str(ex)[:80]}'); continue
        if not rows:
            continue
        stem = path.stem.lower(); have = gt.get(stem, {})
        done = sum(1 for rid in rows if rid in have and HANGUL.search(have[rid]))
        scenes.append({'scene': path.stem, 'rows': len(rows), 'translated': done,
                       'chars': sum(len(b) for b in rows.values()),
                       'missing_chars': sum(len(b) for rid, b in rows.items() if not (rid in have and HANGUL.search(have[rid])))})
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'story_gap.json').write_text(json.dumps({'scenes': scenes, 'errors': errors}, ensure_ascii=False, indent=1), encoding='utf-8')
    tot = sum(s['rows'] for s in scenes); done = sum(s['translated'] for s in scenes)
    full = sum(1 for s in scenes if s['translated'] == s['rows']); none = sum(1 for s in scenes if s['translated'] == 0)
    print(f'scenes with JP event text {len(scenes)}; rows {tot}; translated {done} ({done * 100 // max(tot, 1)}%);'
          f' fully {full}, partly {len(scenes) - full - none}, none {none}; missing chars {sum(s["missing_chars"] for s in scenes)};'
          f' read errors {len(errors)}')
    groups = collections.Counter(); gchars = collections.Counter()
    for s in scenes:
        miss = s['rows'] - s['translated']
        if miss:
            key = s['scene'][:5]; groups[key] += miss; gchars[key] += s['missing_chars']
    print('untranslated rows by scene-id prefix (top 25):')
    for k, n in groups.most_common(25):
        print(f'  {k}: {n} rows, {gchars[k]} chars')


if __name__ == '__main__':
    main()

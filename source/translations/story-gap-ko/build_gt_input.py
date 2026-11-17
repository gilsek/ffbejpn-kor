"""GalTransl input for the story rows the Memorial translation lacks (JP 11.0.0 archive).

Rows = JP *_event_text.txt rows with Japanese whose id has no Korean in translations/chapter1-ko/gt_output
(the same test as tools/story_gap_audit.py). Record format and cleaning follow
translations/translation-gap/build_gt_input.py (ffbe_id, optional speaker name, message).
Output: <project>/gt_input/<scene>.json + manifest.json.

usage: python -I translations/story-gap-ko/build_gt_input.py [--project build/out/story_gap_gt] [--archive ...]
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402

JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
HANGUL = re.compile(r'[\uac00-\ud7a3]')
NAME_TAG = re.compile(r'<name(?:_npc)?=([^>]+)>(?:<br>)?', re.IGNORECASE)


def clean(raw):
    text = re.sub(r'(?i)<invalid_touchwait>', '', raw or '').lstrip('\r\n \t\u3000')
    text = NAME_TAG.sub('', text, count=1)
    text = re.sub(r'(?i)<page>(?:<br>)?', '[PAGE]\n', text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)<wait=\d+>', '', text)
    text = re.sub(r'(?i)<speed=\d+>', '', text)
    text = re.sub(r'(?i)<keywait>', '', text)
    return text.replace('\\n', '\n').strip()


def rows_of(data):
    out = []
    for line in data.decode('utf-8-sig', 'replace').splitlines():
        rid, sep, body = line.partition(',')
        if sep and rid.strip():
            out.append((rid.strip(), body))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default=str(ROOT / 'build/out/story_gap_gt'))
    ap.add_argument('--archive', default='D:/Downloads/ffbejpdata/ffbejpdata')
    args = ap.parse_args()
    have = {}
    for f in (ROOT / 'translations/chapter1-ko/gt_output').glob('*.json'):
        try:
            rows = json.loads(f.read_text(encoding='utf-8-sig'))
        except Exception:
            continue
        d = have.setdefault(f.stem.split('__', 1)[0].lower(), set())
        d.update(str(r['ffbe_id']) for r in rows if isinstance(r, dict) and HANGUL.search(r.get('message', '')))
    gap = json.loads((ROOT / 'build/out/inventory/story_gap.json').read_text(encoding='utf-8'))
    scenes = [s['scene'] for s in gap['scenes'] if s['translated'] < s['rows']]
    out_dir = Path(args.project) / 'gt_input'
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest, total, blank = [], 0, 0
    for scene in scenes:
        pkg = cpk.Cpk.load_bytes((Path(args.archive) / f'{scene}.cpk').read_bytes(), encoding='cp932')
        entries = {i.filename: i for i in pkg.file_infos()}
        text_name = next(n for n in entries if n.endswith('_event_text.txt'))
        teller_name = next((n for n in entries if n.endswith('_event_teller.txt')), None)
        tellers = {}
        if teller_name:
            for sid, name in rows_of(pkg.file_bytes(entries[teller_name].toc_index)):
                tellers[sid] = name.strip()
        done = have.get(scene.lower(), set())
        records = []
        for rid, raw in rows_of(pkg.file_bytes(entries[text_name].toc_index)):
            if not JP.search(raw) or rid in done:
                continue
            msg = clean(raw)
            if not msg:
                blank += 1; continue
            rec = {'ffbe_id': rid}
            m = NAME_TAG.search(re.sub(r'(?i)<invalid_touchwait>', '', raw).lstrip('\r\n \t\u3000'))
            if m and tellers.get(m.group(1)):
                rec['name'] = tellers[m.group(1)]
            rec['message'] = msg
            records.append(rec)
        if records:
            (out_dir / f'{scene}.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            manifest.append({'scene': scene, 'rows': len(records)})
            total += len(records)
    (Path(args.project) / 'manifest.json').write_text(json.dumps({'files': manifest, 'rows': total, 'blank_skipped': blank},
                                                               ensure_ascii=False, indent=1), encoding='utf-8')
    print('scenes', len(manifest), 'rows', total, 'blank skipped', blank, '->', out_dir)


if __name__ == '__main__':
    main()

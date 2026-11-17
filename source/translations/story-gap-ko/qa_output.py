"""QA for a GalTransl story project: every input row has a Korean output row with matching structure.

Checks per row: ffbe_id present in output, Korean present, no kana left, same [PAGE] count, same line count (±1).
Writes <project>/qa.json and prints a summary.

usage: python -I translations/story-gap-ko/qa_output.py [--project build/out/story_gap_gt]
"""
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KANA = re.compile(r'[぀-ヿ]')
HANGUL = re.compile(r'[가-힣]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default=str(ROOT / 'build/out/story_gap_gt'))
    args = ap.parse_args()
    project = Path(args.project)
    issues, rows, files_missing = [], 0, []
    for src in sorted((project / 'gt_input').glob('*.json')):
        out = project / 'gt_output' / src.name
        if not out.exists():
            files_missing.append(src.name); continue
        got = {str(r.get('ffbe_id')): r for r in json.loads(out.read_text(encoding='utf-8'))}
        for r in json.loads(src.read_text(encoding='utf-8')):
            rows += 1
            rid, jp = str(r['ffbe_id']), r['message']
            o = got.get(rid)
            if o is None:
                issues.append({'file': src.name, 'id': rid, 'issue': 'missing row'}); continue
            ko = o.get('message', '')
            probs = []
            if not HANGUL.search(ko):
                probs.append('no Korean')
            if KANA.search(ko):
                probs.append('kana left')
            if jp.count('[PAGE]') != ko.count('[PAGE]'):
                probs.append(f"[PAGE] {jp.count('[PAGE]')}->{ko.count('[PAGE]')}")
            if abs(jp.count('\n') - ko.count('\n')) > 1:
                probs.append(f"lines {jp.count(chr(10)) + 1}->{ko.count(chr(10)) + 1}")
            if probs:
                issues.append({'file': src.name, 'id': rid, 'issue': ', '.join(probs), 'jp': jp[:80], 'ko': ko[:80]})
    (project / 'qa.json').write_text(json.dumps({'rows': rows, 'files_missing': files_missing, 'issues': issues},
                                                ensure_ascii=False, indent=1), encoding='utf-8')
    kinds = {}
    for i in issues:
        for k in i['issue'].split(', '):
            kinds[k.split(' ')[0]] = kinds.get(k.split(' ')[0], 0) + 1
    print(f'rows {rows}, output files missing {len(files_missing)}, rows with issues {len(issues)}', kinds)


if __name__ == '__main__':
    main()

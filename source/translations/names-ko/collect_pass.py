"""Collect a GalTransl name pass into translations/names-ko/names_pass<N>.json (JP name -> Korean).

Rows whose Korean still has kana (except the long-vowel 'ー', changed to '~' only between Hangul) or no
Hangul at all are left out and listed in names_pass<N>_rejected.json for a retry / manual fix.

usage: python -I translations/names-ko/collect_pass.py --pass 1|2
"""
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KANA = re.compile(r'[぀-ヺヽ-ヿ]')   # kana; '・' (U+30FB) and 'ー' (U+30FC) are not counted
HANGUL = re.compile(r'[가-힣]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pass', dest='p', type=int, required=True)
    args = ap.parse_args()
    proj = ROOT / f'build/out/names_gt{args.p}'
    good, bad = {}, []
    for src in sorted((proj / 'gt_input').glob('*.json')):
        out = proj / 'gt_output' / src.name
        got = {str(r['ffbe_id']): r.get('message', '') for r in json.loads(out.read_text(encoding='utf-8'))} if out.exists() else {}
        for r in json.loads(src.read_text(encoding='utf-8')):
            jp, ko = r['message'], got.get(str(r['ffbe_id']), '').strip()
            ko = re.sub(r'(?<=[가-힣])ー+', lambda m: '~' * len(m.group()), ko)
            if ko and HANGUL.search(ko) and not KANA.search(ko) and '\n' not in ko:
                good[jp] = ko
            else:
                bad.append({'file': src.name, 'jp': jp, 'ko': ko})
    here = ROOT / 'translations/names-ko'
    (here / f'names_pass{args.p}.json').write_text(json.dumps(good, ensure_ascii=False, indent=0), encoding='utf-8')
    (here / f'names_pass{args.p}_rejected.json').write_text(json.dumps(bad, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'pass {args.p}: {len(good)} names kept, {len(bad)} rejected')


if __name__ == '__main__':
    main()

"""GalTransl projects for the master NAMES with no Korean (tools/name_coverage.py -> missing_names.json).

Pass 1 (build/out/names_gt1): every missing name except missions — units, speakers, places, dungeons, monsters ...
Pass 2 (build/out/names_gt2): mission names, after pass 1 is merged into the glossary (they are "place・detail").
Pass 3 (build/out/names_gt3): anything still missing in any table (e.g. names whose Memorial value was half Japanese).
Each project: gt_input/<table>_<n>.json (rows {ffbe_id, message}), Dict/gpt_dict.txt = Memorial glossary + every
known JP->KO name (Memorial sources, and for pass 2 the pass-1 results), config.yaml/name table copied from
the story-gap project (Gemini 3.8 via the local proxy).

usage: python -I translations/names-ko/build_name_projects.py --pass 1|2
"""
import argparse, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import name_coverage as NC  # noqa: E402

CHUNK = 400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pass', dest='p', type=int, choices=(1, 2, 3), required=True)
    args = ap.parse_args()
    missing = json.loads((ROOT / 'build/out/inventory/missing_names.json').read_text(encoding='utf-8'))
    known, _, _, _ = NC.name_sources()
    done = {}
    for f in (ROOT / 'translations/names-ko').glob('names_pass[0-9].json'):
        done.update(json.loads(f.read_text(encoding='utf-8')))
    known.update(done)
    proj = ROOT / f'build/out/names_gt{args.p}'
    if proj.exists():
        shutil.rmtree(proj)
    (proj / 'gt_input').mkdir(parents=True)
    (proj / 'Dict').mkdir()
    seen, n_rows = set(), 0
    for table, names in missing.items():
        if args.p in (1, 2) and (table == 'F_MISSION_MST') != (args.p == 2):
            continue   # pass 3: whatever is still missing, any table
        rows = []
        for name in names:
            base = name.split('＠')[0].strip()
            if not base or base in seen or base in known:
                continue
            seen.add(base); rows.append({'ffbe_id': str(len(rows)), 'message': base})
        for i in range(0, len(rows), CHUNK):
            chunk = [dict(r, ffbe_id=str(j)) for j, r in enumerate(rows[i:i + CHUNK])]
            (proj / 'gt_input' / f'{table}_{i // CHUNK:03d}.json').write_text(
                json.dumps(chunk, ensure_ascii=False, indent=1), encoding='utf-8')
        n_rows += len(rows)
    base_dict = (NC.A / 'chapter1-ko/Dict/gpt_dict.txt').read_text(encoding='utf-8').rstrip('\n').splitlines()
    have = {l.split('\t')[0] for l in base_dict if '\t' in l}
    extra = [f'{jp}\t{ko}\t고유명사' for jp, ko in known.items() if jp not in have and len(jp) >= 2]
    (proj / 'Dict/gpt_dict.txt').write_text('\n'.join(base_dict + extra) + '\n', encoding='utf-8')
    story = ROOT / 'build/out/story_gap_gt'
    shutil.copy(story / 'config.yaml', proj / 'config.yaml')
    shutil.copy(story / 'name替换表.csv', proj / 'name替换表.csv')
    print(f'pass {args.p}: {n_rows} names in {len(list((proj / "gt_input").glob("*.json")))} files; glossary {len(base_dict) + len(extra)} lines -> {proj}')


if __name__ == '__main__':
    main()

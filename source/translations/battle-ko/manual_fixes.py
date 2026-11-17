"""GalTransl 전체 검수에서 확인한 3건을 재현 가능하게 보정한다."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXES = {
    'battle_013.json': ('battle_ca382b7d0d277e1275ca', '아버지인가…….<br>', '아버지인가…….'),
    'battle_015.json': ('battle_07adb5672ba92d4ed7d9', '무(無)다.\n죽음으로 모든 것을 무로 돌린다.',
                       '무다.\n죽음으로 모든 것을 무로 돌린다.'),
    'battle_020.json': ('battle_6fea4ad8e004c65745e8', '자, 잠깐, 조용히 있지 마…….<br>',
                       '자, 잠깐, 조용히 있지 마…….'),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=ROOT / 'build/out/battle_gt')
    args = ap.parse_args()
    changed = 0
    for filename, (rid, old, new) in FIXES.items():
        path = args.project / 'gt_output' / filename
        rows = json.loads(path.read_text(encoding='utf-8-sig'))
        matches = [r for r in rows if r.get('ffbe_id') == rid]
        if len(matches) != 1 or matches[0].get('message') not in (old, new):
            raise ValueError('보정 대상이 예상과 다름: ' + filename + ' ' + rid)
        if matches[0]['message'] == old:
            matches[0]['message'] = new
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            changed += 1
    print('검수 보정', changed, '건')


if __name__ == '__main__':
    main()

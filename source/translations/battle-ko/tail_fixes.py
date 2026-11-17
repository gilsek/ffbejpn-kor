"""4필드 전투 대사(battle_gt_tail) 검수 보정 + 저장소 반영.

python -I -X utf8 translations/battle-ko/tail_fixes.py            # 보정만
python -I -X utf8 translations/battle-ko/tail_fixes.py --publish  # gt_output/tail_*.json + manifest.json 병합

2026-11-13 하이쿠 검수(build/out/battle_gt_tail/review/haiku_review_*.tsv)에서 채택한 것:
- 원문에 해당 일본어가 있을 때만 바꾸는 표기 통일(기존 전투 번역·이름표 기준)
- 개별 오역·줄바꿈·일본어 잔존 보정
- 한글 뒤에 남은 장음 기호 ー → ~
화자 이름(name)은 이름 치환표 몫이라 여기서 다루지 않는다.
"""
import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
# (원문에 있어야 하는 일본어, 잘못된 표기, 통일 표기)
TERMS = [
    ('アルドール', '아르도르', '알도르'), ('ミド', '미도', '미드'), ('コラール', '콜라르', '코랄'),
    ('まるボン', '마루봉', '동글봄'), ('モルボル', '몰보르', '몰볼'), ('虚無', '공허', '허무'),
    ('原初', '태초', '원초'), ('グンガン', '궁간', '군간'), ('メロイ', '메로이', '멜로이'),
    ('ダット', '닷트', '다트'), ('オーダーズ', '오더스', '오더즈'), ('キーパーズ', '키퍼스', '키퍼즈'),
    ('ミヌール', '미노르', '미누르'), ('シンフォニア', '신포니아', '심포니아'), ('ロレーヌ', '로렌느', '로렌'),
    ('ロカちゃん', '로카 양', '로카짱'), ('ブルース', '블루스', '브루스'), ('魔物', '몬스터', '마물'),
    ('十六闘星', '십육투성', '16투성'),
]
# ffbe_id 끝 6자리 → (예상 번역, 보정 번역)
FIXES = {
    '601d11': ('오케이, 맡겨!\n데이지! 업어 줘!', '오케이, 맡겨!\n데이지! 업어 드려!'),
    '22212b': ('엘마티르.\n가능한 한 검체는 무상으로 확보해 줘.', '엘마티르.\n가능한 한 검체는 상처 없이 확보해 줘.'),
    'fe91fa': ('개굴.(팀은 어떤 아이야?)', '개굴.\n(팀은 어떤 아이야?)'),
    '6c1bab': ('이 돌은 엄청난 힘을 지닌 비석.\n히사메 일족에게야말로 필요한 것이다.',
               '이 돌은 엄청난 힘을 지닌 신비한 돌.\n히사메 일족에게야말로 필요한 것이다.'),
    '34e8f3': ('하지만, 질 수는 없다.\n오늘こそ 멜로이를 멈춘다. 여왕님을 위해!',
               '하지만, 질 수는 없다.\n오늘이야말로 멜로이를 멈춘다. 여왕님을 위해!'),
}
LONG = re.compile(r'(?<=[가-힣])ー+')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=ROOT / 'build/out/battle_gt_tail')
    ap.add_argument('--publish', action='store_true')
    args = ap.parse_args()
    source = {}
    for f in sorted((args.project / 'gt_input').glob('*.json')):
        for r in json.loads(f.read_text(encoding='utf-8')):
            source[r['ffbe_id']] = r['message']
    counts = {'terms': 0, 'fixes': 0, 'long': 0}
    seen = set()
    for f in sorted((args.project / 'gt_output').glob('*.json')):
        rows = json.loads(f.read_text(encoding='utf-8-sig'))
        before = json.dumps(rows, ensure_ascii=False)
        for r in rows:
            jp, ko = source[r['ffbe_id']], r.get('message', '')
            fix = FIXES.get(r['ffbe_id'][-6:])
            if fix:
                seen.add(r['ffbe_id'][-6:])
                if ko == fix[0]:
                    ko = fix[1]; counts['fixes'] += 1
                elif ko != fix[1]:
                    raise ValueError('보정 대상이 예상과 다름: ' + r['ffbe_id'] + ' ' + ko)
            for needle, bad, good in TERMS:
                if needle in jp and bad in ko:
                    ko = ko.replace(bad, good); counts['terms'] += 1
            new = LONG.sub('~', ko)
            if new != ko:
                ko = new; counts['long'] += 1
            r['message'] = ko
        if json.dumps(rows, ensure_ascii=False) != before:
            f.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if set(FIXES) - seen:
        raise ValueError('보정 대상을 찾지 못함: ' + ', '.join(sorted(set(FIXES) - seen)))
    print('표기 통일', counts['terms'], '건, 개별 보정', counts['fixes'], '건, 장음 기호', counts['long'], '건')
    if not args.publish:
        return
    folder = ROOT / 'translations/battle-ko/gt_output'
    for f in sorted((args.project / 'gt_output').glob('battle_*.json')):
        shutil.copyfile(f, folder / f.name.replace('battle_', 'tail_'))
    main_path = ROOT / 'translations/battle-ko/manifest.json'
    manifest = json.loads(main_path.read_text(encoding='utf-8'))
    tail = json.loads((ROOT / 'translations/battle-ko/manifest_tail.json').read_text(encoding='utf-8'))
    have = {r['ffbe_id'] for r in manifest['records']}
    add = [r for r in tail['records'] if r['ffbe_id'] not in have]
    manifest['records'].extend(add)
    manifest['unique_messages'] = len(manifest['records'])
    manifest['occurrences'] = sum(len(r.get('locations') or []) for r in manifest['records'])
    manifest['characters'] = sum(len(r['source']) for r in manifest['records'])
    main_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('저장소 반영: tail 파일', len(list(folder.glob('tail_*.json'))), '개, manifest 추가', len(add),
          '건 (합계', len(manifest['records']), ')')


if __name__ == '__main__':
    main()

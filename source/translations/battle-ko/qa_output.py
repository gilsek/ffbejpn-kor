"""전투 번역 결과의 행 ID·누락·일본어·치환 변수·줄바꿈을 검수한다.

--publish는 검수를 통과한 완성 파일만 저장소 gt_output에 복사한다.
번역 중인 미완성 파일은 오류로 오인하지 않고 대기 상태로 집계한다.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
JP = re.compile(r'[぀-ヺヽ-ヿ一-鿿]')
KO = re.compile(r'[가-힣]')
VARIABLE = re.compile(r'%\d*\$?[-+0-9.]*[sdfiu]|\{[^{}]+\}|\[[A-Z_]+\]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=ROOT / 'build/out/battle_gt')
    ap.add_argument('--publish', action='store_true')
    args = ap.parse_args()
    issues, pending, passed, total = [], [], [], 0
    for src in sorted((args.project / 'gt_input').glob('*.json')):
        dest = args.project / 'gt_output' / src.name
        if not dest.exists():
            pending.append(src.name); continue
        try:
            got_rows = json.loads(dest.read_text(encoding='utf-8-sig'))
        except json.JSONDecodeError:
            pending.append(src.name); continue
        source = json.loads(src.read_text(encoding='utf-8'))
        got = {r.get('ffbe_id'): r for r in got_rows}
        bad = len(issues)
        if len(got) != len(got_rows) or set(got) != {r['ffbe_id'] for r in source}:
            issues.append({'file': src.name, 'issue': '행 ID 누락·중복·추가'})
        for row in source:
            rid, jp = row['ffbe_id'], row['message']
            ko = got.get(rid, {}).get('message', '')
            total += 1
            probs = []
            if not KO.search(ko): probs.append('한국어 없음')
            if JP.search(ko): probs.append('일본어 잔존')
            if Counter(VARIABLE.findall(jp)) != Counter(VARIABLE.findall(ko)): probs.append('치환 변수 변경')
            if re.findall(r'<[^>]*>', jp) != re.findall(r'<[^>]*>', ko): probs.append('제어 태그 변경')
            if abs(jp.count('\n') - ko.count('\n')) > 1: probs.append('줄바꿈 차이 2개 이상')
            if probs:
                issues.append({'file': src.name, 'id': rid, 'issue': ', '.join(probs), 'source': jp, 'translation': ko})
        if len(issues) == bad:
            passed.append(src.name)
            if args.publish:
                folder = ROOT / 'translations/battle-ko/gt_output'
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dest, folder / dest.name)
    report = {'checked_rows': total, 'passed_files': passed, 'pending_files': pending, 'issues': issues}
    (args.project / 'qa.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'검사 {total}행, 통과 {len(passed)}파일, 대기 {len(pending)}파일, 문제 {len(issues)}건')
    if issues:
        print('문제 유형', dict(Counter(i['issue'] for i in issues)))


if __name__ == '__main__':
    main()

"""아이템 번역의 ID·보호 표식·태그·수치·일본어 잔존을 검사한다."""
import argparse
from collections import Counter
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import item_common as C


def problems(source, text):
    issues = []
    if not isinstance(text, str) or not text.strip():
        return ['빈 번역']
    if C.JP.search(text): issues.append('일본어 잔존')
    if not C.N.HANGUL.search(text): issues.append('한국어 없음')
    if C.TAG.findall(source) != C.TAG.findall(text): issues.append('태그 변경')
    if Counter(C.VARIABLE.findall(source)) != Counter(C.VARIABLE.findall(text)): issues.append('치환 변수 변경')
    required = Counter(C.raw_numbers(source))
    actual = Counter(C.raw_numbers(text))
    # 원래 아라비아 숫자는 필수다. 한자 수사를 숫자로 바꾼 경우는 원문에 같은 값이 있어야 한다.
    if required != actual:
        natural = Counter(C.numbers(source)) - required
        actual = Counter(C.numbers(text))
        mismatch = bool((required-actual) or ((actual-required)-natural))
    else:
        mismatch = False
    if mismatch:
        # 한자/자연어 수사의 아라비아 숫자 번역은 원문·번역 쌍을 직접 검토한 경우만 허용.
        reviewed = C.HERE/'number_equivalents.json'
        equivalent = C.read(reviewed).get(C.rid(source)) if reviewed.exists() else None
        if not equivalent or equivalent['source'] != source or equivalent['translation'] != text:
            issues.append('수치 변경')
    if C.MARKER.search(text): issues.append('미복원 표식')
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--publish', action='store_true')
    args = ap.parse_args()
    manifest = C.manifest()
    records = {r['ffbe_id']: r for r in manifest['records']}
    translations = dict(manifest['reused'])
    fixes = C.HERE/'manual_fixes.json'
    manual = C.read(fixes) if fixes.exists() else {}
    issues, pending, passed = [], [], []
    for src in sorted((C.PROJECT/'gt_input').glob('*.json')):
        dest = C.PROJECT/'gt_output'/src.name
        if not dest.exists():
            pending.append(src.name); continue
        try:
            rows = C.read(dest)
        except json.JSONDecodeError:
            pending.append(src.name); continue
        source = C.read(src)
        got = {r.get('ffbe_id'): r for r in rows}
        expected = {r['ffbe_id'] for r in source}
        before = len(issues)
        if len(got) != len(rows) or set(got) != expected:
            issues.append({'file': src.name, 'issue': '행 ID 누락·중복·추가'})
        for rid in expected:
            if rid in manifest['reused']:
                continue
            text = got.get(rid, {}).get('message', '')
            rec = records[rid]
            if Counter(C.MARKER.findall(text)) != Counter(C.MARKER.findall(rec['message'])):
                if rid in manual:
                    continue
                issues.append({'file': src.name, 'id': rid, 'issue': '보호 표식 변경', 'translation': text})
                continue
            translations[rid] = C.restore(text, rec['tokens'])
        if len(issues) == before:
            passed.append(src.name)
    # 수정은 명시적 ID→최종 번역 파일에 보존하며 원본/번역 캐시는 직접 고치지 않는다.
    if manual:
        for rid, text in manual.items():
            if rid not in records: raise ValueError('알 수 없는 수정 ID: '+rid)
            translations[rid] = text
    for rid, text in translations.items():
        rec = records[rid]
        for issue in problems(rec['source'], text):
            issues.append({'id': rid, 'issue': issue, 'source': rec['source'], 'translation': text})
    missing = sorted(set(records)-set(translations))
    report = {'checked': len(translations), 'total': len(records), 'passed_files': len(passed),
              'pending_files': pending, 'missing_ids': missing, 'issues': issues}
    (C.PROJECT/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(f"검사 {len(translations)}/{len(records)}, 통과 {len(passed)}파일, 대기 {len(pending)}파일, 문제 {len(issues)}건")
    print('문제 유형',dict(Counter(r['issue'] for r in issues)))
    if args.publish:
        if pending or missing or issues:
            raise SystemExit('누락/검수 문제가 있어 게시하지 않음')
        patch = {}
        for loc in manifest['locations']:
            patch.setdefault(loc['table'],{}).setdefault(str(loc['row']),{})[loc['field']] = C.clean(translations[loc['translation_id']])
        (C.HERE/'translated.json').write_text(json.dumps(translations,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
        (C.HERE/'patches.json').write_text(json.dumps(patch,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
        print('전체 번역 및 행/필드 패치 게시 완료')


if __name__ == '__main__': main()

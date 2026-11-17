"""유닛 기술 번역을 검수하고 통과한 전체 결과만 게시한다."""
import argparse
from functools import lru_cache
from collections import Counter,defaultdict
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import skills_common as C
import qa_output as Q
Q.C=C

@lru_cache(maxsize=1)
def retained_names():
    path=C.HERE/'retained_names.json'
    return C.read(path) if path.exists() else {}

def problems(source,text):
    issues=Q.problems(source,text)
    entry=retained_names().get(C.rid(source))
    if entry and entry['source']==source and entry['translation']==text:
        issues=[i for i in issues if i!='한국어 없음']
    return issues

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--publish',action='store_true');args=ap.parse_args()
    m=C.manifest();records={r['ffbe_id']:r for r in m['records']}; translations=dict(m['reused'])
    fixes=C.read(C.HERE/'manual_fixes.json') if (C.HERE/'manual_fixes.json').exists() else {}
    issues,pending,passed=[],[],[]
    for source in sorted((C.PROJECT/'gt_input').glob('*.json')):
        dest=C.PROJECT/'gt_output'/source.name
        if not dest.exists():pending.append(source.name);continue
        try:rows=C.read(dest)
        except json.JSONDecodeError:pending.append(source.name);continue
        expected={r['ffbe_id'] for r in C.read(source)};got={r.get('ffbe_id'):r for r in rows}
        if len(got)!=len(rows) or set(got)!=expected:issues.append({'file':source.name,'issue':'ID 불일치'})
        for rid in expected:
            r=records[rid];text=got.get(rid,{}).get('message','')
            if Counter(C.MARKER.findall(text))!=Counter(C.MARKER.findall(r['message'])):
                if rid not in fixes:issues.append({'id':rid,'issue':'보호 표식 변경','source':r['source'],'translation':text})
                continue
            translations[rid]=C.restore(text,r['tokens'])
        passed.append(source.name)
    assert set(fixes)<=set(records)
    translations.update(fixes)
    for rid,text in translations.items():
        for issue in problems(records[rid]['source'],text):
            issues.append({'id':rid,'issue':issue,'source':records[rid]['source'],'translation':text})
    missing=sorted(set(records)-set(translations))
    report={'checked':len(translations),'total':len(records),'passed_files':len(passed),
            'pending_files':pending,'missing_ids':missing,'issues':issues}
    (C.PROJECT/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(f'검사 {len(translations)}/{len(records)}, 출력 {len(passed)}/{m["files"]}파일, 대기 {len(pending)}파일, 문제 {len(issues)}건')
    print('유형',dict(Counter(r['issue'] for r in issues)))
    if args.publish:
        if pending or missing or issues:raise SystemExit('누락/문제로 게시하지 않음')
        tables=C.load_tables();locations=defaultdict(list);patches={}
        for loc in m['locations']:locations[(loc['table'],loc['row'],loc['field'])].append(loc)
        for (table,row,field),locs in locations.items():
            original=tables[table][2][row][field]
            patches.setdefault(table,{}).setdefault(str(row),{})[field]=C.patched_value(field,original,locs,translations)
        (C.HERE/'translated.json').write_text(json.dumps(translations,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
        (C.HERE/'patches.json').write_text(json.dumps(patches,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
        print('기술 전체 번역·필드 패치 게시 완료')

if __name__=='__main__':main()

"""적 기술 전 행을 감사하고 기존 번역 재사용 후 누락 전체를 추출한다."""
from collections import defaultdict
import hashlib
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import monster_common as C

def main():
    rows=C.load_rows();path=C.source_path()
    seed=C.read(C.ROOT/'build/engine_overlay/jp_monster_skills_ko.json')
    candidates=defaultdict(set)
    for entry in seed.values():candidates[entry['source']].add(entry['translation'])
    conflicts={s:sorted(v) for s,v in candidates.items() if len(v)>1}
    assert not conflicts,conflicts
    known=C.N.name_sources()[0]
    # 검수 완료한 아이템/아군 기술 번역을 정확한 원문 일치일 때만 재사용한다.
    for folder in ('items-ko','skills-ko'):
        root=C.ROOT/'translations'/folder
        manifest=C.read(root/'manifest.json');translated=C.read(root/'translated.json')
        for rec in manifest['records']:known[rec['source']]=translated[rec['ffbe_id']]
    known.update({s:next(iter(v)) for s,v in candidates.items()})
    records,locations,reused,excluded={},{},{},[]
    before_missing=[]
    for index,row in enumerate(rows):
        source=row['G4L0YIB2'];sid=row['6E5u1xrs']
        assert isinstance(source,str)
        if not C.human(source):
            assert source.strip().isdigit() or source=='「……」',(sid,source,'제외 규칙 검토 필요')
            excluded.append({'id':sid,'source':source,'reason':'숫자 카운트다운/무언 표시 보존'});continue
        rid=C.rid(source)
        locations.setdefault(rid,[]).append({'table':'F_MONSTER_SKILL_MST','row':index,'id':sid,
                                             'field':'G4L0YIB2','source':source,'translation_id':rid})
        if rid not in records:
            message,tokens=C.protect(source)
            records[rid]={'ffbe_id':rid,'source':source,'message':message,'tokens':tokens}
        if sid not in seed:before_missing.append(sid)
        ko=known.get(source)
        if ko and C.N.HANGUL.search(ko) and not C.JP.search(ko):reused[rid]=ko
    needed=[v for rid,v in records.items() if rid not in reused]
    batches=[]
    for offset in range(0,len(needed),80):
        batches.append([{'ffbe_id':r['ffbe_id'],'name':'','message':r['message']} for r in needed[offset:offset+80]])
    for i,batch in enumerate(batches):C.write_checked(C.PROJECT/'gt_input'/f'monster_{i:03}.json',batch)
    manifest={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_rows':len(rows),
              'source_unique_names':len({r['G4L0YIB2'] for r in rows}),
              'seed':seed,'before_missing_ids':before_missing,'excluded':excluded,
              'records':list(records.values()),'locations':[v for values in locations.values() for v in values],
              'reused':reused,'unique_total':len(records),'unique_reused':len(reused),
              'unique_new':len(needed),'new_characters':sum(len(v['source']) for v in needed),'files':len(batches)}
    C.write_checked(C.HERE/'manifest.json',manifest)
    if not (C.HERE/'number_equivalents.json').exists():C.write_checked(C.HERE/'number_equivalents.json',{})
    src=C.ROOT/'build/out/skills_gt'
    for name in ('config.yaml','name替换表.csv'):
        dest=C.PROJECT/name
        if not dest.exists():shutil.copyfile(src/name,dest)
    if not (C.PROJECT/'Dict').exists():
        shutil.copytree(src/'Dict',C.PROJECT/'Dict')
        with (C.PROJECT/'Dict/gpt_dict.txt').open('a',encoding='utf-8') as f:
            for rid,ko in reused.items():
                source=records[rid]['source']
                if len(source)<60 and not any(v in source+ko for v in ('\t','\n','<')):f.write(f'\n{source}\t{ko}')
    print({k:manifest[k] for k in ('source_rows','source_unique_names','unique_total','unique_reused','unique_new','new_characters','files')})
    print('번역 대상',sum(map(len,locations.values())),'ID, 숫자 보존',len(excluded),'ID')

if __name__=='__main__':main()

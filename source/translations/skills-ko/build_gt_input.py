"""유닛 기술 전체의 표시 문자열과 기존 한국어를 고정한다."""
import hashlib
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import skills_common as C


def main():
    known=C.N.name_sources()[0]
    im=C.I.manifest(); it=C.read(C.I.HERE/'translated.json')
    for r in im['records']:
        known[r['source']]=it[r['ffbe_id']]
    records,locations,reused,counts={},[],{},{}
    tables=C.load_tables()
    for table,(idf,fields) in C.SPECS.items():
        src,key,rows=tables[table]
        counts[table]={'file':src.name,'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
                       'rows':len(rows),'target_fields':0,'target_pieces':0}
        for index,row in enumerate(rows):
            for field in fields:
                value=row.get(field,'')
                if not isinstance(value,str): continue
                parts=C.pieces(field,value)
                if parts: counts[table]['target_fields']+=1
                for part,source in parts:
                    rid=C.rid(source)
                    locations.append({'table':table,'row':index,'id':str(row[idf]),'field':field,
                                      'part':part,'source':source,'translation_id':rid})
                    counts[table]['target_pieces']+=1
                    if rid not in records:
                        message,tokens=C.protect(source)
                        records[rid]={'ffbe_id':rid,'source':source,'message':message,'tokens':tokens,'category':table}
                    ko=known.get(source)
                    if ko and C.N.HANGUL.search(ko) and not C.JP.search(ko): reused[rid]=ko
    needed=[r for k,r in records.items() if k not in reused]
    batches,batch,chars=[],[],0
    for r in needed:
        if batch and (len(batch)>=80 or chars+len(r['message'])>8000):
            batches.append(batch);batch=[];chars=0
        batch.append({'ffbe_id':r['ffbe_id'],'name':'','message':r['message']});chars+=len(r['message'])
    if batch:batches.append(batch)
    for i,b in enumerate(batches): C.write_checked(C.PROJECT/'gt_input'/f'skills_{i:03}.json',b)
    manifest={'tables':counts,'records':list(records.values()),'locations':locations,'reused':reused,
              'unique_total':len(records),'unique_reused':len(reused),'unique_new':len(needed),
              'new_characters':sum(len(r['source']) for r in needed),'files':len(batches)}
    C.write_checked(C.HERE/'manifest.json',manifest)
    # 기존 아이템 검수에서 확인한 수치 동치만 동일 원문/번역 쌍으로 재사용한다.
    exceptions={k.replace('item_','skill_',1):v for k,v in C.read(C.I.HERE/'number_equivalents.json').items()
                if k.replace('item_','skill_',1) in records}
    C.write_checked(C.HERE/'number_equivalents.json',exceptions)
    src=C.ROOT/'build/out/items_gt'
    for name in ('config.yaml','name替换表.csv'):
        dest=C.PROJECT/name
        if not dest.exists():shutil.copyfile(src/name,dest)
    if not (C.PROJECT/'Dict').exists():
        shutil.copytree(src/'Dict',C.PROJECT/'Dict')
        with (C.PROJECT/'Dict/gpt_dict.txt').open('a',encoding='utf-8') as out:
            for rid,ko in reused.items():
                jp=records[rid]['source']
                if len(jp)<40 and not any(x in jp+ko for x in ('\n','\t','<')):out.write(f'\n{jp}\t{ko}')
    print({k:v for k,v in manifest.items() if k not in ('tables','records','locations','reused')})
    for t,v in counts.items():print(t,v['rows'],'행',v['target_fields'],'표시필드')


if __name__=='__main__':main()

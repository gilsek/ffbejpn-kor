"""기술 표 전 행에서 ID/전투 명령/수치와 아이템 번역 보존을 검사한다."""
from collections import defaultdict
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'translations/skills-ko'))
import skills_common as C
from qa import problems

def main():
    m=C.manifest();patches=C.read(C.HERE/'patches.json');translations=C.read(C.HERE/'translated.json')
    records={r['ffbe_id']:r for r in m['records']};assert set(records)==set(translations)
    for rid,text in translations.items():assert not problems(records[rid]['source'],text),(rid,problems(records[rid]['source'],text))
    locs=defaultdict(list)
    for loc in m['locations']:locs[(loc['table'],loc['row'],loc['field'])].append(loc)
    items=C.read(C.I.HERE/'patches.json');tables=C.load_tables();result={}
    checked=changed=field_count=effect_count=0
    for table,(idf,fields) in C.SPECS.items():
        src,key,rows=tables[table]
        assert hashlib.sha256(src.read_bytes()).hexdigest()==m['tables'][table]['sha256']
        path=ROOT/'build/out/ko_names/mst_ko'/src.name
        modified=C.N.D.decode(path.read_bytes(),key)[1]
        atext,btext=src.read_text(encoding='ascii').splitlines(),path.read_text(encoding='ascii').splitlines()
        assert len(rows)==len(modified)==len(atext)==len(btext)
        changes=0;fields_n=0
        for index,(a,b) in enumerate(zip(rows,modified)):
            values=patches.get(table,{}).get(str(index),{})
            assert set(values)<=set(fields)
            expected=dict(a);expected.update(values);assert b==expected,(table,index,'허용 필드 외 변경')
            assert a[idf]==b[idf]
            for fld in fields:
                if not isinstance(a.get(fld),str):continue
                pieces=C.pieces(fld,a[fld])
                if pieces:
                    assert fld in values,(table,index,fld,'대상 누락')
                    assert not C.JP.search(b[fld]),(table,index,fld,'일문 잔존')
                    expected_value=C.patched_value(fld,a[fld],locs[(table,index,fld)],translations)
                    assert b[fld]==expected_value
                if fld==C.EFFECT and fld in values:
                    x,y=C.SEPARATOR.split(a[fld]),C.SEPARATOR.split(b[fld])
                    assert len(x)==len(y)
                    indices={i for i,v in pieces}
                    for i,(p,q) in enumerate(zip(x,y)):
                        if i not in indices:assert p==q,(table,index,'효과 명령/구분자 변경')
                    effect_count+=1
            for fld,v in items.get(table,{}).get(str(index),{}).items():assert b[fld]==v,(table,index,fld,'아이템 되돌림')
            if a==b:assert atext[index]==btext[index]
            else:
                changes+=1;fields_n+=sum(a[k]!=b[k] for k in values)
                assert all('"' not in v and '\\' not in v and '\n' not in v and '\r' not in v for v in values.values())
        checked+=len(rows);changed+=changes;field_count+=fields_n
        result[table]={'file':path.name,'rows':len(rows),'changed_rows':changes,'changed_fields':fields_n,
                       'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    report={'checked_rows':checked,'changed_rows':changed,'changed_fields':field_count,'effect_dialogue_fields':effect_count,
            'translated_strings':len(records),'remaining_japanese_fields_in_scope':0,'tables':result}
    folder=ROOT/'build/out/ko_skills';folder.mkdir(exist_ok=True)
    (folder/'check.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('PASS:',len(result),'표',checked,'행, 변경',changed,'행',field_count,'필드, 효과 대사',effect_count,'필드 구분자 보존')

if __name__=='__main__':main()

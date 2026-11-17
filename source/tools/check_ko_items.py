"""전체 아이템 행의 암호문·필드·번역 원문 계약을 검사한다."""
from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'translations/items-ko'))
import item_common as C
from qa_output import problems


def main():
    manifest = C.manifest()
    patches = C.read(C.HERE/'patches.json')
    translations = C.read(C.HERE/'translated.json')
    records = {r['ffbe_id']:r for r in manifest['records']}
    assert set(records) == set(translations)
    for rid,text in translations.items():
        assert not problems(records[rid]['source'],text), rid
    tables = C.load_tables()
    references = C.references(tables)
    checked,changed,fields_changed = 0,0,0
    result = {}
    for table,(idfield,fields) in C.SPECS.items():
        src,key,original = tables[table]
        assert hashlib.sha256(src.read_bytes()).hexdigest() == manifest['tables'][table]['sha256']
        skill_overlay = C.skill_overlay(table,src)
        path = ROOT/'build/out/ko_names/mst_ko'/src.name
        patched = C.N.D.decode(path.read_bytes(),key)[1]
        oldlines,newlines = src.read_text(encoding='ascii').splitlines(),path.read_text(encoding='ascii').splitlines()
        assert len(original) == len(patched) == len(oldlines) == len(newlines)
        count,field_count = 0,0
        for index,(a,b) in enumerate(zip(original,patched)):
            values = patches.get(table,{}).get(str(index),{})
            skill_values=skill_overlay.get(str(index),{})
            assert all(v==skill_values[k] for k,v in values.items() if k in skill_values)
            expected = dict(a); expected.update(values); expected.update(skill_values)
            assert b == expected,(table,index)
            assert set(values) <= set(fields)
            assert a[idfield] == b[idfield]
            scoped = table not in references or str(a[idfield]) in references[table]
            if scoped:
                for field in fields:
                    source = a.get(field,'')
                    if not isinstance(source,str): continue
                    if C.JP.search(source):
                        assert field in values,(table,index,field,'번역 대상 누락')
                        assert not C.JP.search(b[field]),(table,index,field,'일본어 잔존')
                    elif (field != '1ux5sP4L' and re.search('[A-Za-z]',source)
                            and not re.fullmatch(r'[A-Z0-9+%, ./\-]+',source)):
                        assert field in values,(table,index,field,'영문 아이템 문구 누락')
            if a == b:
                assert oldlines[index] == newlines[index]
            else:
                count += 1
                field_count += sum(a[k] != b[k] for k in values)
                for k,v in values.items():
                    assert not C.JP.search(v),(table,index,k)
                    assert '"' not in v and '\\' not in v and '\n' not in v and '\r' not in v
        checked += len(original); changed += count; fields_changed += field_count
        result[table] = {'file':path.name,'rows':len(original),'changed_rows':count,'changed_fields':field_count,
                          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    report = {'checked_rows':checked,'changed_rows':changed,'changed_fields':fields_changed,
              'translated_strings':len(records),'remaining_japanese_fields_in_scope':0,'tables':result}
    out = ROOT/'build/out/ko_items'; out.mkdir(exist_ok=True)
    (out/'check.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(f'PASS: {len(result)}표 {checked}행, 변경 {changed}행·{fields_changed}필드, 원문·태그·수치·구조 보존')


if __name__ == '__main__': main()

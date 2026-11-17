"""검수 완료 아이템 번역만 원본 JP 표의 표시 필드에 반영한다."""
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'translations/items-ko'))
import item_common as C
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16


def main():
    manifest = C.manifest()
    patches = C.read(C.HERE/'patches.json')
    tables = C.load_tables()
    out = ROOT/'build/out/ko_names/mst_ko'
    out.mkdir(parents=True,exist_ok=True)
    report = {}
    for table,(idfield,fields) in C.SPECS.items():
        src,key,rows = tables[table]
        assert hashlib.sha256(src.read_bytes()).hexdigest() == manifest['tables'][table]['sha256']
        skill_overlay = C.skill_overlay(table,src)
        k16 = key16(key)
        lines = src.read_text(encoding='ascii').splitlines()
        first = cbc_decrypt(k16,lines[0]); pad = first[-1]
        double = 1 <= pad <= 16 and first[-pad:] == bytes([pad])*pad
        changed,counts = 0,Counter()
        for index,row in enumerate(rows):
            item_values = patches.get(table,{}).get(str(index),{})
            skill_values = skill_overlay.get(str(index),{})
            assert all(v==skill_values[k] for k,v in item_values.items() if k in skill_values)
            values = dict(item_values); values.update(skill_values)
            if not values: continue
            assert set(item_values) <= set(fields)
            assert all(isinstance(row.get(k),str) for k in values)
            for field,text in values.items():
                assert not C.JP.search(text), (table,index,field)
                assert '"' not in text and '\\' not in text
                if row[field] != text:
                    row[field] = text; counts[field] += 1
            lines[index] = cbc_encrypt(k16,json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf-8'),double_pad=double)
            changed += 1
        path = out/src.name
        path.write_text('\n'.join(lines)+'\n',encoding='ascii')
        report[table] = {'file':src.name,'rows':len(rows),'rows_changed':changed,
                         'fields_changed':dict(counts),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(table,changed,'/',len(rows),dict(counts))
    folder = ROOT/'build/out/ko_items'; folder.mkdir(exist_ok=True)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')


if __name__ == '__main__': main()

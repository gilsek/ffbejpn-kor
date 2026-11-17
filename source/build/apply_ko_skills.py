"""검수 완료 기술 번역을 원본 JP 표시 필드/효과 대사 조각에만 적용한다."""
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'translations/skills-ko'))
import skills_common as C
from ffbe_crypto import cbc_decrypt,cbc_encrypt,key16

def main():
    m=C.manifest();patches=C.read(C.HERE/'patches.json');tables=C.load_tables()
    items=C.read(C.I.HERE/'patches.json');out=ROOT/'build/out/ko_names/mst_ko';out.mkdir(exist_ok=True)
    report={}
    for table,(idf,fields) in C.SPECS.items():
        src,key,rows=tables[table];assert hashlib.sha256(src.read_bytes()).hexdigest()==m['tables'][table]['sha256']
        lines=src.read_text(encoding='ascii').splitlines();k=key16(key)
        first=cbc_decrypt(k,lines[0]);pad=first[-1];double=1<=pad<=16 and first[-pad:]==bytes([pad])*pad
        counts=Counter();changed=0
        for index,row in enumerate(rows):
            values=patches.get(table,{}).get(str(index),{})
            for fld,v in items.get(table,{}).get(str(index),{}).items():assert values.get(fld)==v,(table,index,fld,'아이템 번역 충돌')
            assert set(values)<=set(fields)
            modified=False
            for fld,text in values.items():
                assert not C.JP.search(text) and '"' not in text and '\\' not in text
                if row[fld]!=text:row[fld]=text;counts[fld]+=1;modified=True
            if modified:
                lines[index]=cbc_encrypt(k,json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf-8'),double_pad=double)
                changed+=1
        path=out/src.name;path.write_text('\n'.join(lines)+'\n',encoding='ascii')
        report[table]={'file':path.name,'rows':len(rows),'changed_rows':changed,'fields_changed':dict(counts),
                       'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(table,changed,'/',len(rows),dict(counts),flush=True)
    folder=ROOT/'build/out/ko_skills';folder.mkdir(exist_ok=True)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')

if __name__=='__main__':main()

"""현재 설치 APK 사본의 UI 텍스트만 갱신하고 그림·엔진·split을 보존한다."""
import argparse, hashlib, json, re, shutil, zipfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import apply_ko_ui as U
import jp_offline_build as B

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    assert a.source.resolve()!=a.out.resolve()
    a.out.mkdir(parents=True,exist_ok=True)
    ko=U.keyed(U.KO/'text_ko_memorial.csv');ko.update(U.keyed(U.KO/'text_ko_extra.csv'))
    extra=json.loads((U.KO/'buff_desc_extra_ko.json').read_text(encoding='utf-8'))
    report={'changed_files':{},'unchanged_cpk_files':0,'unchanged_base_entries':0,'output':{}}
    with zipfile.ZipFile(a.source/'base.apk') as z:
        old=z.read('assets/cpk/common.cpk');c=U.cpk.Cpk.load_bytes(old,encoding='cp932');replace={}
        for i in c.file_infos():
            original=c.file_bytes(i.toc_index);data=original
            if i.filename in ('text_ja.csv','text_en.csv'):
                data=U.korean_text(original,ko,{})
                assert [l.partition(',')[0] for l in original.decode('utf-8-sig').splitlines()]==[l.partition(',')[0] for l in data.decode('utf-8-sig').splitlines()]
            elif i.filename=='buff_desc.txt':
                lines=original.decode('utf-8-sig').splitlines();changed=0
                report['buff_rows_total']=len(lines)
                report['buff_japanese_rows_before']=sum(bool(re.search(r'[぀-ヺヽ-ヿ一-鿿ｦ-ﾟ]',s)) for s in lines)
                report['buff_changed_indices']=[]
                for key,entry in extra.items():
                    n=int(key.removeprefix('BUFF_DESC_'))
                    assert lines[n] in (entry['source'],entry['translation']),(key,'원문 불일치')
                    if lines[n]!=entry['translation']:changed+=1;report['buff_changed_indices'].append(n)
                    lines[n]=entry['translation']
                assert len(lines)==351
                data=('\r\n'.join(lines)+'\r\n').encode('utf-8-sig')
                report['buff_rows_changed']=changed
                assert not re.search(r'[぀-ヺヽ-ヿ一-鿿ｦ-ﾟ]',data.decode('utf-8-sig')),'버프 일본어 잔존'
                report['buff_japanese_rows_after']=0
            if data!=original:replace[i.full_path]=data;report['changed_files'][i.full_path]=sha(data)
        patched=U.cpk_inplace.patch(old,replace)
        after=U.cpk.Cpk.load_bytes(patched,encoding='cp932')
        before=list(c.file_infos());later=list(after.file_infos())
        assert [(i.full_path,i.toc_index) for i in before]==[(i.full_path,i.toc_index) for i in later]
        for x,y in zip(before,later):
            assert after.file_bytes(y.toc_index)==replace.get(x.full_path,c.file_bytes(x.toc_index))
            if x.full_path not in replace:report['unchanged_cpk_files']+=1
        unsigned=a.out/'base-ui-unsigned.apk'
        with zipfile.ZipFile(unsigned,'w') as target:
            for i in z.infolist():
                if re.fullmatch(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))',i.filename,re.I):continue
                target.writestr(i,patched if i.filename=='assets/cpk/common.cpk' else z.read(i.filename))
    B.align_sign(unsigned,a.out/'base.apk')
    with zipfile.ZipFile(a.source/'base.apk') as old,zipfile.ZipFile(a.out/'base.apk') as new:
        for name in old.namelist():
            if name=='assets/cpk/common.cpk' or name.startswith('META-INF/'):continue
            assert old.read(name)==new.read(name),name
            report['unchanged_base_entries']+=1
    for path in a.source.glob('split_*.apk'):shutil.copyfile(path,a.out/path.name)
    for path in [a.source/'base.apk',*a.source.glob('split_*.apk')]:   # skip intermediate *-unsigned.apk
        report['output'][path.name]=sha((a.out/path.name).read_bytes())
        if path.name!='base.apk':assert report['output'][path.name]==sha(path.read_bytes())
    (a.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

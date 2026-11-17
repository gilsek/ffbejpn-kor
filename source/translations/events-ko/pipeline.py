"""효과 템플릿/이벤트 안내의 추출 → 검수 → 적용. 비표시 조건·보상은 보존한다."""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'translations/items-ko'))
import item_common as C
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16

HERE = Path(__file__).resolve().parent
PROJECT = ROOT/'build/out/events_gt'
SPECS = {
    'F_PROCESS_TYPE_MST': ['VC9F3eJn'],
    'F_PROCESS_PASSIVE_TYPE_MST': ['VC9F3eJn'],
    'F_AREA_PROCESS_PASSIVE_TYPE_MST': ['VC9F3eJn'],
    'F_FIELD_EFFECT_MST': ['VC9F3eJn', 'T7aEx3Mj'],
    'F_CHALLENGE_MST': ['G4L0YIB2', '6uvHX2JG', 'kd4y3hz2', '4MVta1AG', '5L6F1c7Q'],
    'F_SP_CHALLENGE_MST': ['G4L0YIB2', '6uvHX2JG', 'LVPGo73b'],
    'F_MEDAL_EXCHANGE_MST': ['6uvHX2JG'],
    'F_LOGIN_BONUS_MST': ['VC9F3eJn'],
    'F_LOGIN_BONUS_SP_REWARD_MST': ['FcdAf60M', 'M2Yz8WD5'],
    'F_LOGIN_BONUS_TOTAL_REWARD_MST': ['FcdAf60M', 'M2Yz8WD5'],
    'F_MISSION_NOTICE_MST': ['6uvHX2JG', 'Ikd0go5h'],
}
TEMPLATES = {'F_PROCESS_TYPE_MST','F_PROCESS_PASSIVE_TYPE_MST','F_AREA_PROCESS_PASSIVE_TYPE_MST'}

def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')

def rid(source):
    return 'event_'+hashlib.sha256(source.encode()).hexdigest()[:20]

def tables():
    master=C.N.masters(); result={}
    for name in SPECS:
        token,key=master[name]
        src=next((C.N.OLD/'downloads/ffbejpdata-archive-org').glob(f'Ver*_{token}.dat'))
        result[name]=(src,key,C.N.D.decode(src.read_bytes(),key)[1])
    return result

def parts(table,text):
    return re.split(r'(<[^>]+>)',text) if table in TEMPLATES else [text]

def clean_markup(text):
    # 원문에도 있는 font size="4" 등의 태그 속성은 보존한다.
    # 본문에 새로 추가된 JSON 특수문자만 기존의 안전한 표기로 바꾼다.
    return ''.join(s if s.startswith('<') else C.clean(s) for s in re.split(r'(<[^>]+>)',text))

@lru_cache(maxsize=1)
def markup_fixes():
    return C.read(HERE/'source_markup_fixes.json')

def markup_source(source):
    fix=markup_fixes().get(rid(source))
    if not fix:return source
    assert fix['source']==source and source.count('<br滝')==1
    assert fix['normalized_source']==source.replace('<br滝','<br>滝',1)
    return fix['normalized_source']

def extract():
    known=C.N.name_sources()[0]
    for folder in ('names-ko','items-ko','skills-ko','battle-ko','monster-skills-ko'):
        base=ROOT/'translations'/folder
        for p in sorted(base.glob('names_pass[0-9].json')):
            known.update(C.read(p))
        if (base/'manifest.json').exists() and (base/'translated.json').exists():
            m=C.read(base/'manifest.json'); tr=C.read(base/'translated.json')
            for r in m.get('records',[]):
                if r.get('ffbe_id') in tr:known.setdefault(r['source'],tr[r['ffbe_id']])
    records={}; locations=[]; reused={}; info={}
    for table,(src,key,rows) in tables().items():
        info[table]={'file':src.name,'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'rows':len(rows)}
        for index,row in enumerate(rows):
            for field in SPECS[table]:
                text=row.get(field,'')
                if not isinstance(text,str):continue
                for part,value in enumerate(parts(table,text)):
                    if value.startswith('<') and table in TEMPLATES:continue
                    if not C.JP.search(value):continue
                    ident=rid(value)
                    locations.append({'table':table,'row':index,'field':field,'part':part,'translation_id':ident,'source':value})
                    if ident not in records:
                        message,tokens=C.protect(value)
                        records[ident]={'ffbe_id':ident,'source':value,'message':message,'tokens':tokens,'category':table}
                    ko=known.get(value)
                    if ko and C.N.HANGUL.search(ko) and not C.JP.search(ko) and C.TAG.findall(value)==C.TAG.findall(ko) and Counter(C.raw_numbers(value))==Counter(C.raw_numbers(ko)):
                        reused[ident]=ko
    needed=[r for k,r in records.items() if k not in reused]
    batches=[]; batch=[]; chars=0
    for r in needed:
        if batch and (len(batch)>=80 or chars+len(r['message'])>8000):
            batches.append(batch);batch=[];chars=0
        batch.append({'ffbe_id':r['ffbe_id'],'name':'','message':r['message']});chars+=len(r['message'])
    if batch:batches.append(batch)
    for i,batch in enumerate(batches):C.write_checked(PROJECT/'gt_input'/f'events_{i:03}.json',batch)
    m={'tables':info,'locations':locations,'records':list(records.values()),'reused':reused,'unique_total':len(records),'unique_new':len(needed),'files':len(batches),'new_characters':sum(len(r['source']) for r in needed)}
    C.write_checked(HERE/'manifest.json',m)
    for name in ('config.yaml','name替换表.csv'):
        dest=PROJECT/name
        if not dest.exists():shutil.copyfile(ROOT/'build/out/items_gt'/name,dest)
    if not (PROJECT/'Dict').exists():shutil.copytree(ROOT/'build/out/skills_gt/Dict',PROJECT/'Dict')
    print(json.dumps({k:v for k,v in m.items() if k not in ('tables','locations','records','reused')},ensure_ascii=False))

def qa(publish=False, only=None):
    m=C.read(HERE/'manifest.json');records={r['ffbe_id']:r for r in m['records']};tr=dict(m['reused']);issues=[];pending=[]
    selected=set(only or SPECS)
    assert selected<=set(SPECS)
    wanted={l['translation_id'] for l in m['locations'] if l['table'] in selected}
    english=C.read(HERE/'english_names.json')
    for table,fields in english.items():
        assert table in SPECS and set(fields)<=set(SPECS[table])
        for values in fields.values():
            for source,text in values.items():
                assert not C.JP.search(source) and not C.JP.search(text) and C.N.HANGUL.search(text)
                assert Counter(C.raw_numbers(source))==Counter(C.raw_numbers(text))
    fixes=C.read(HERE/'manual_fixes.json') if (HERE/'manual_fixes.json').exists() else {}
    for src in sorted((PROJECT/'gt_input').glob('*.json')):
        expected_all={r['ffbe_id'] for r in C.read(src)}
        expected=expected_all & wanted
        if not expected:continue
        dest=PROJECT/'gt_output'/src.name
        if not dest.exists():pending.append(src.name);continue
        rows=C.read(dest);got={r.get('ffbe_id'):r for r in rows}
        if len(got)!=len(rows) or set(got)!=expected_all:issues.append({'file':src.name,'issue':'ID 불일치'})
        for ident in expected:
            if ident in fixes:continue
            r=records[ident];text=got.get(ident,{}).get('message','')
            if Counter(C.MARKER.findall(text))!=Counter(C.MARKER.findall(r['message'])):
                issues.append({'id':ident,'issue':'표식 변경','source':r['source'],'translation':text});continue
            tr[ident]=C.restore(text,r['tokens'])
    assert set(fixes)<=set(records)
    tr.update(fixes)
    tr={ident:text for ident,text in tr.items() if ident in wanted}
    for ident,text in tr.items():
        source=records[ident]['source'];why=[]
        if not text.strip() or not C.N.HANGUL.search(text):why.append('한국어 없음')
        if C.JP.search(text):why.append('일본어 잔존')
        if C.TAG.findall(markup_source(source))!=C.TAG.findall(text):why.append('태그 변경')
        if Counter(C.VARIABLE.findall(source))!=Counter(C.VARIABLE.findall(text)):why.append('변수 변경')
        bracket_source=unicodedata.normalize('NFKC',source)
        bracket_text=unicodedata.normalize('NFKC',text)
        for left,right in [('「','」'),('『','』'),('【','】'),('(',')')]:
            if bracket_source.count(left)==bracket_source.count(right) and bracket_text.count(left)!=bracket_text.count(right):
                why.append('괄호 불균형');break
        if '超級' in source and '初級' not in source and re.search(r'(?<![가-힣])초급(?![가-힣])',text):
            why.append('초급/초월급 혼동')
        # 보호한 숫자가 같아야 하며 한자 수사의 숫자 표기만 별도 검토한다.
        if Counter(C.raw_numbers(source))!=Counter(C.raw_numbers(text)):
            equiv=C.read(HERE/'number_equivalents.json') if (HERE/'number_equivalents.json').exists() else {}
            if equiv.get(ident)!={'source':source,'translation':text}:why.append('수치 변경')
        for w in why:issues.append({'id':ident,'issue':w,'source':source,'translation':text})
    missing=sorted(wanted-set(tr));report={'tables':sorted(selected),'total':len(wanted),'checked':len(tr),'pending_files':pending,'missing_ids':missing,'issues':issues}
    save(PROJECT/('qa.partial.json' if only else 'qa.json'),report)
    print('검수',len(tr),'/',len(wanted),'대기',len(pending),'누락',len(missing),'문제',len(issues),dict(Counter(x['issue'] for x in issues)))
    if publish:
        if pending or missing or issues:raise SystemExit('검수 미통과: 게시하지 않음')
        existing=C.read(HERE/'translated.json') if (HERE/'translated.json').exists() else {}
        existing.update(tr);save(HERE/'translated.json',existing)

def apply(only=None):
    qa(True,only)
    m=C.read(HERE/'manifest.json');tr=C.read(HERE/'translated.json');locs=defaultdict(list)
    for l in m['locations']:locs[(l['table'],l['row'],l['field'])].append(l)
    report={'tables':{},'issues':[]};patches={}
    english=C.read(HERE/'english_names.json')
    out=ROOT/'build/out/ko_names/mst_ko'
    for table,(src,key,original) in tables().items():
        if only and table not in only:continue
        assert hashlib.sha256(src.read_bytes()).hexdigest()==m['tables'][table]['sha256']
        rows=json.loads(json.dumps(original));lines=src.read_text(encoding='ascii').splitlines();k=key16(key)
        first=cbc_decrypt(k,lines[0]);pad=first[-1];double=1<=pad<=16 and first[-pad:]==bytes([pad])*pad
        count=Counter();changed=0
        english_seen=set();english_fields=0
        for n,row in enumerate(rows):
            modified=False
            for field in SPECS[table]:
                extra=english.get(table,{}).get(field,{}).get(row.get(field,''))
                if (table,n,field) not in locs and extra is None:continue
                old=row[field];p=parts(table,old)
                for l in locs[(table,n,field)]:
                    assert p[l['part']]==l['source'];p[l['part']]=clean_markup(tr[l['translation_id']])
                value=''.join(p)
                if extra is not None:
                    value=clean_markup(extra);english_seen.add((field,old));english_fields+=1
                assert C.TAG.findall(markup_source(old))==C.TAG.findall(value),(table,n,field,'태그/조건식 변경')
                assert not C.JP.search(value),(table,n,field,'일본어 잔존')
                row[field]=value;count[field]+=1;modified=True
                patches.setdefault(table,{}).setdefault(str(n),{})[field]=value
            if modified:lines[n]=cbc_encrypt(k,json.dumps(row,ensure_ascii=False,separators=(',',':')).encode(),double_pad=double);changed+=1
        target=out/src.name;target.write_text('\n'.join(lines)+'\n',encoding='ascii')
        decoded=C.N.D.decode(target.read_bytes(),key)[1];assert decoded==rows
        for n,(old,new) in enumerate(zip(original,decoded)):
            assert old.keys()==new.keys()
            for fld,val in old.items():assert new[fld]==patches.get(table,{}).get(str(n),{}).get(fld,val),(table,n,fld,'비대상 변경')
        assert len(decoded)==len(original)
        expected_english={(field,source) for field,values in english.get(table,{}).items() for source in values}
        assert english_seen==expected_english,(table,'영문 보완 원문 미발견')
        report['tables'][table]={'file':target.name,'rows':len(rows),'changed_rows':changed,'fields_changed':dict(count),'english_names':len(english_seen),'english_fields':english_fields,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        print(table,changed,'/',len(rows),dict(count),flush=True)
    existing=C.read(HERE/'patches.json') if (HERE/'patches.json').exists() else {}
    existing.update(patches);save(HERE/'patches.json',existing)
    save(ROOT/'build/out/ko_events'/('check.partial.json' if only else 'check.json'),report)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['extract','qa','publish','apply']);ap.add_argument('--only',help='일부 표만 검수/적용(쉼표 구분)');a=ap.parse_args()
    only=a.only.split(',') if a.only else None
    if a.action=='extract':extract()
    elif a.action in ('qa','publish'):qa(a.action=='publish',only)
    else:apply(only)

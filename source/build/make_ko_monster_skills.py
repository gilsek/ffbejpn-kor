"""검증된 실제 적 기술 ID/원문에 한국어를 연결한다. 전체 게시본 우선."""
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'translations/items-ko'))
import name_coverage as N
import item_common as I
import battle_content as B

# 실기기에서 확인된 기존 번역 누락. 실제 엔진 기본키와 원문을 함께 검증한다.
REVIEWED_SKILLS={rid:{'source':'Megavolt','translation':'메가볼트'}
                 for rid in ('150040','160140','160670','216755','221912')}
EFFECT_SEPARATOR=re.compile(r'([,@&])')

def effect_translation(source,texts):
    parts=EFFECT_SEPARATOR.split(source)
    for index,value in enumerate(parts):
        if I.JP.search(value):
            assert value in texts,('효과 표시 문구 누락',value)
            parts[index]=I.clean(texts[value]).replace(',','‚').replace(':','：').replace('@','＠').replace('&','＆')
    return ''.join(parts)

def authored_skill_rows(data):
    rows=[]
    def walk(value):
        if isinstance(value,dict):
            if isinstance(value.get('Wp39QX52'),list):
                rows.extend(r for r in value['Wp39QX52'] if isinstance(r,dict))
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(data)
    return rows

def load_catalog():
    src=N.OLD/'upstream/source/server/content/battle/F_MONSTER_SKILL_MST.tsv'
    indexed=B.read_index_table(str(src),'F_MONSTER_SKILL_MST')
    authored=authored_skill_rows(I.read(N.OLD/'upstream/source/server/responses.json'))
    byid={r['6E5u1xrs']:r for r in indexed}
    assert len(byid)==len(indexed)
    for row in authored:
        rid=str(row['6E5u1xrs'])
        if rid in byid:assert byid[rid]['G4L0YIB2']==row['G4L0YIB2'],(rid,'응답 원문 불일치')
        else:byid[rid]=row
    return indexed,authored,list(byid.values())

def main():
    src=N.OLD/'upstream/source/server/content/battle/F_MONSTER_SKILL_MST.tsv'
    indexed,authored,rows=load_catalog()
    byid={r['6E5u1xrs']:r for r in rows}
    assert len(byid)==len(rows)
    csvpath=ROOT/'translations/chapter1-ko/csv_exports/chapter1_battle_skills.csv'
    csvrows=list(csv.DictReader(csvpath.open(encoding='utf-8-sig')))
    known=[r for r in csvrows if N.HANGUL.search(r['korean']) and not I.JP.search(r['korean'])]
    candidates=defaultdict(set); matched=[]; missing=[]
    for r in known:
        # 기존 생성기의 'ignores cover' 분기 순서 때문에 도발 불가까지 붙은 오역을 바로잡는다.
        ko='감싸기 불가 공격!' if r['japanese']=='かばう不可の攻撃！' else r['korean']
        if r['id'].startswith('SKILL_'):
            rid=r['id'].removeprefix('SKILL_'); actual=byid.get(rid)
            if not actual or actual['G4L0YIB2'] not in (r['japanese'],r['english']):
                missing.append(r['id']); continue
            targets=[actual]
        else:
            targets=[x for x in rows if x['G4L0YIB2'] in (r['japanese'],r['english'])]
        if not targets:missing.append(r['id']);continue
        matched.append(r['id'])
        for row in targets:candidates[row['6E5u1xrs']].add(I.clean(ko))
    for rid,entry in REVIEWED_SKILLS.items():
        assert rid in byid and byid[rid]['G4L0YIB2']==entry['source'],(rid,'검수 원문 불일치')
        candidates[rid].add(I.clean(entry['translation']))
    conflicts={k:sorted(v) for k,v in candidates.items() if len(v)!=1}
    assert not missing,(missing[:10])
    # 충돌하는 기존 번역을 임의 선택하지 않고 수동 검토하도록 중단한다.
    assert not conflicts,conflicts
    mapping={rid:{'source':byid[rid]['G4L0YIB2'],'translation':next(iter(v))} for rid,v in candidates.items()}
    full=ROOT/'translations/monster-skills-ko'
    full_ids=[]
    if (full/'translated.json').exists():
        manifest=I.read(full/'manifest.json');translated=I.read(full/'translated.json')
        assert manifest['source_sha256']==hashlib.sha256(src.read_bytes()).hexdigest()
        assert set(translated)=={r['ffbe_id'] for r in manifest['records']}
        for loc in manifest['locations']:
            rid=loc['id'];entry={'source':loc['source'],'translation':I.clean(translated[loc['translation_id']])}
            assert byid[rid]['G4L0YIB2']==entry['source']
            assert N.HANGUL.search(entry['translation']) and not I.JP.search(entry['translation'])
            if rid in mapping:assert mapping[rid]==entry,(rid,'기존 검수 번역 변경')
            mapping[rid]=entry;full_ids.append(rid)
        extra=I.read(full/'authored_skills.json')
        assert set(extra)==set(byid)-{r['6E5u1xrs'] for r in indexed}
        for rid,entry in extra.items():
            assert byid[rid]['G4L0YIB2']==entry['source']
            assert N.HANGUL.search(entry['translation']) and not I.JP.search(entry['translation'])
            mapping[rid]=entry;full_ids.append(rid)
        assert set(mapping)|{r['id'] for r in manifest['excluded']}==set(byid),'기술 ID 범위 누락'
        texts=I.read(full/'effect_texts.json')
        for rid,row in byid.items():
            original=row.get('Ha9G5sCS','')
            if I.JP.search(original):
                assert rid in mapping,(rid,'효과 문구의 기술명 누락')
                mapping[rid].update(effect_source=original,effect_translation=effect_translation(original,texts))
    out=ROOT/'build/engine_overlay/jp_monster_skills_ko.json'
    out.write_text(json.dumps(mapping,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    report={'source':str(src.relative_to(N.OLD)),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
            'csv_sha256':hashlib.sha256(csvpath.read_bytes()).hexdigest(),'source_rows':len(indexed),
            'catalog_rows':len(rows),'authored_skill_occurrences':len(authored),
            'authored_source_sha256':hashlib.sha256((N.OLD/'upstream/source/server/responses.json').read_bytes()).hexdigest(),
            'matched_skills':sum(x.startswith('SKILL_') for x in matched),
            'matched_notices':sum(x.startswith('NOTICE_') for x in matched),
            'reviewed_skill_ids':list(REVIEWED_SKILLS),
            'full_translated_ids':len(full_ids),
            'effect_text_fields':sum('effect_source' in entry for entry in mapping.values()),
            'mapped_ids':len(mapping),'missing':missing,'conflicts':conflicts,
            'source_name_japanese':sum(bool(I.JP.search(x['G4L0YIB2'])) for x in rows),
            'example_150020':mapping['150020']}
    folder=ROOT/'build/out/ko_skills';folder.mkdir(exist_ok=True)
    (folder/'monster-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('적 기술 기존 번역 대응',report['matched_skills'],'공지',report['matched_notices'],'적용 ID',len(mapping))

if __name__=='__main__':main()

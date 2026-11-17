"""실제 엔진 표 전 행의 번역과 효과 명령 보존을 검사한다."""
import copy
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build'))
sys.path.insert(0,str(ROOT/'build/engine_overlay'))
import make_ko_monster_skills as M
import jp_korean as K
import qa_output as Q

def check_effect(original,localized,texts):
    before=M.EFFECT_SEPARATOR.split(original);after=M.EFFECT_SEPARATOR.split(localized)
    assert len(before)==len(after),'효과 명령 조각 수 변경'
    for a,b in zip(before,after):
        if M.I.JP.search(a):
            assert b==M.effect_translation(a,texts) and not M.I.JP.search(b),(a,b)
        else:assert a==b,('효과 수치·명령·구분자 변경',a,b)

def main():
    src=M.N.OLD/'upstream/source/server/content/battle/F_MONSTER_SKILL_MST.tsv'
    indexed,authored,rows=M.load_catalog()
    skills=M.I.read(ROOT/'build/engine_overlay/jp_monster_skills_ko.json')
    sample={'Wp39QX52':rows,'other':[{'G4L0YIB2':'維持','hp':'10'}]}
    snapshot=copy.deepcopy(sample);out=K.localize_skills(sample,skills)
    assert sample==snapshot
    texts=M.I.read(ROOT/'translations/monster-skills-ko/effect_texts.json')
    for source,translation in texts.items():assert not Q.problems(source,translation),(source,'효과 표시 문구 검수 실패')
    changed=0;effects=0;fragments=set()
    for a,b in zip(rows,out['Wp39QX52']):
        assert {k:v for k,v in a.items() if k not in ('G4L0YIB2','Ha9G5sCS')}=={k:v for k,v in b.items() if k not in ('G4L0YIB2','Ha9G5sCS')}
        check_effect(a.get('Ha9G5sCS',''),b.get('Ha9G5sCS',''),texts)
        effects+=a.get('Ha9G5sCS')!=b.get('Ha9G5sCS')
        fragments.update(v for v in M.EFFECT_SEPARATOR.split(a.get('Ha9G5sCS','')) if M.I.JP.search(v))
        if a['6E5u1xrs'] in skills:
            assert b['G4L0YIB2']==skills[a['6E5u1xrs']]['translation'];changed+=1
        else:assert a==b
    assert changed==len(skills)
    full=ROOT/'translations/monster-skills-ko';canonical={}
    if (full/'translated.json').exists():
        assert fragments==set(texts),'효과 문구 사전의 누락·초과'
        manifest=M.I.read(full/'manifest.json')
        translated=M.I.read(full/'translated.json')
        canonical=M.I.read(full/'canonical_terms.json')
        records={v['source']:v['ffbe_id'] for v in manifest['records']}
        for source,entry in canonical.items():
            if source in records:assert translated[records[source]]==entry['translation'],(source,'고유 명칭 불일치')
        excluded={v['id']:v for v in manifest['excluded']}
        assert set(skills)|set(excluded)=={r['6E5u1xrs'] for r in rows}
        assert not set(skills)&set(excluded)
        for row in out['Wp39QX52']:
            if row['6E5u1xrs'] in excluded:
                assert row['G4L0YIB2']==excluded[row['6E5u1xrs']]['source']
            else:
                assert M.N.HANGUL.search(row['G4L0YIB2']) and not M.I.JP.search(row['G4L0YIB2'])
    assert out['other']==sample['other']
    blood=next(r for r in out['Wp39QX52'] if r['6E5u1xrs']=='150020')
    assert blood['G4L0YIB2']=='흡혈'
    for rid,entry in M.REVIEWED_SKILLS.items():
        row=next(r for r in out['Wp39QX52'] if r['6E5u1xrs']==rid)
        assert row['G4L0YIB2']==entry['translation'],rid
    assert K.localize_skills(None,skills) is None
    assert K.localize_skills({'Wp39QX52':None},skills)=={'Wp39QX52':None}
    mismatch={'Wp39QX52':[{'6E5u1xrs':'150020','G4L0YIB2':'別技'},None,{'6E5u1xrs':'0','G4L0YIB2':'Bloodfeast'}]}
    assert K.localize_skills(mismatch,skills)==mismatch
    for rid,entry in skills.items():
        if 'effect_source' not in entry:continue
        row={'6E5u1xrs':rid,'G4L0YIB2':entry['source'],'Ha9G5sCS':'unknown,1,2'}
        actual=K.localize_skills({'Wp39QX52':[row]},skills)['Wp39QX52'][0]
        assert actual==dict(row,G4L0YIB2=entry['translation']),'효과 원문 불일치 시 보존 실패'
    from types import SimpleNamespace
    server=SimpleNamespace(reply_pipeline=lambda:sample)
    K.install(server)
    assert server.reply_pipeline()['Wp39QX52']==out['Wp39QX52']
    report={'catalog_rows':len(rows),'translated_names':changed,'effect_text_fields':effects,
            'effect_fragments':len(fragments),'canonical_aliases':len(canonical),
            'preserved_names':len(rows)-changed,'structure_checks':'PASS'}
    (ROOT/'build/out/ko_skills/monster-check.json').write_text(json.dumps(report,indent=1)+'\n',encoding='utf-8')
    print('PASS:',len(rows),'행 중',changed,'이름,',effects,'효과 표시 문구 필드 변경; ID·수치·명령·구분자·미매칭 보존, 실제 호출 바인딩')

if __name__=='__main__':main()

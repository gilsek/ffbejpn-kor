"""설치 APK의 실제 미리 작성된 전투 응답을 읽어 전체 기술 연결을 검사한다."""
import argparse
import copy
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'build'))
sys.path.insert(0,str(ROOT/'build/engine_overlay'))
import make_ko_monster_skills as M
import jp_korean as K
from check_ko_monster_skills import check_effect

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apk',type=Path,required=True);a=ap.parse_args()
    with zipfile.ZipFile(a.apk) as z:
        with zipfile.ZipFile(io.BytesIO(z.read('assets/chaquopy/app.imy'))) as app:
            data=app.read('responses.json')
    rows=M.authored_skill_rows(json.loads(data));skills=M.I.read(ROOT/'build/engine_overlay/jp_monster_skills_ko.json')
    manifest=M.I.read(ROOT/'translations/monster-skills-ko/manifest.json')
    excluded={v['id']:v for v in manifest['excluded']}
    sample={'Wp39QX52':rows};before=copy.deepcopy(sample);out=K.localize_skills(sample,skills)
    assert sample==before
    texts=M.I.read(ROOT/'translations/monster-skills-ko/effect_texts.json')
    changed=0;effects=0
    for original,localized in zip(rows,out['Wp39QX52']):
        rid=str(original['6E5u1xrs'])
        expected=dict(original)
        if rid in excluded:assert original['G4L0YIB2']==excluded[rid]['source']
        else:
            assert rid in skills,(rid,original['G4L0YIB2'],'APK 응답 기술 누락')
            assert original['G4L0YIB2']==skills[rid]['source'],(rid,'원문 불일치')
            expected['G4L0YIB2']=skills[rid]['translation']
            entry=skills[rid]
            if 'effect_source' in entry:
                assert original.get('Ha9G5sCS')==entry['effect_source'],(rid,'APK 효과 원문 불일치')
                expected['Ha9G5sCS']=entry['effect_translation']
            assert M.N.HANGUL.search(localized['G4L0YIB2']) and not M.I.JP.search(localized['G4L0YIB2'])
        assert localized==expected,(rid,'허용하지 않은 필드 변경')
        check_effect(original.get('Ha9G5sCS',''),localized.get('Ha9G5sCS',''),texts)
        changed+=localized['G4L0YIB2']!=original['G4L0YIB2']
        effects+=localized.get('Ha9G5sCS')!=original.get('Ha9G5sCS')
    report={'authored_occurrences':len(rows),'unique_ids':len({str(v['6E5u1xrs']) for v in rows}),
            'changed_names':changed,'untranslated_names_in_scope':0,
            'changed_effect_text_fields':effects,
            'responses_sha256':hashlib.sha256(data).hexdigest(),
            'mapping_sha256':hashlib.sha256((ROOT/'build/engine_overlay/jp_monster_skills_ko.json').read_bytes()).hexdigest()}
    (ROOT/'build/out/ko_skills/authored-apk-check.json').write_text(json.dumps(report,indent=1)+'\n',encoding='utf-8')
    print('PASS: 실제 APK 전투 응답',len(rows),'기술 출현, 번역',changed,'이름 /',effects,'효과 표시 필드, 누락·효과 명령 변경 0')

if __name__=='__main__':main()

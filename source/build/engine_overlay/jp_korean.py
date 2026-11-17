"""JP 전투 응답에 포함된 몬스터 이름에 기존 한국어 번역을 적용한다."""
import json
from pathlib import Path

GROUPS = ('bV34YIJQ', 'wbet57nF')


def localize_monsters(spec, names):
    if not isinstance(spec, dict):
        return spec
    result = dict(spec)
    for group in GROUPS:
        rows = spec.get(group)
        if not isinstance(rows, list):
            continue
        result[group] = [dict(row, G4L0YIB2=names[row['G4L0YIB2']])
                         if isinstance(row, dict) and row.get('G4L0YIB2') in names else row
                         for row in rows]
    return result


def localize_skills(spec, skills):
    """ID·원문이 일치하는 표시 이름과 정확히 일치한 효과 표시 문구를 바꾼다."""
    if not isinstance(spec,dict) or not isinstance(spec.get('Wp39QX52'),list):
        return spec
    result=dict(spec)
    def localized(row):
        if not isinstance(row,dict):return row
        entry=skills.get(str(row.get('6E5u1xrs')))
        if entry and row.get('G4L0YIB2')==entry['source']:
            result=dict(row,G4L0YIB2=entry['translation'])
            if 'effect_source' in entry and row.get('Ha9G5sCS')==entry['effect_source']:
                result['Ha9G5sCS']=entry['effect_translation']
            return result
        return row
    result['Wp39QX52']=[localized(row) for row in spec['Wp39QX52']]
    return result


def install(server):
    names = json.loads(Path(__file__).with_name('jp_monster_names_ko.json').read_text(encoding='utf-8'))
    skills = json.loads(Path(__file__).with_name('jp_monster_skills_ko.json').read_text(encoding='utf-8'))
    # capture_server는 함수를 직접 import하므로 실제 호출자의 바인딩을 감싼다.
    original = server.reply_pipeline
    def reply(*args, **kwargs):
        return localize_skills(localize_monsters(original(*args, **kwargs), names),skills)
    server.reply_pipeline = reply
    print('JP_KOREAN monster-name pairs=' + str(len(names)), flush=True)
    print('JP_KOREAN monster-skill ids=' + str(len(skills)), flush=True)

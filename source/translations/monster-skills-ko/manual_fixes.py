"""적 기술 전체 번역의 명시적 보정. GalTransl 원출력은 보존한다."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import monster_common as C
from terminology import canonical_terms,normalize_families

FIXES={'N/A':'해당 없음','Doublejump':'더블 점프',
       'Waterstrike':'수격','Confusion Wave':'혼란의 파동',"You're next!":'다음은 네 차례다!',
       'Firestrike':'화염 타격','Fierce Fist':'맹렬한 주먹','Aerostrike':'바람 타격','Darkstrike':'암흑 타격'}
NUMBER_EQUIVALENTS={
    'Torture: Primary':('고문: 1단계','Primary의 첫째/1차 의미'),
    'Torture: Secondary':('고문: 2단계','Secondary의 둘째/2차 의미'),
    'Torture: Tertiary':('고문: 3단계','Tertiary의 셋째/3차 의미'),
    'Third Eye':('제3의 눈','Third의 세 번째 의미'),
    'Trilateral Shot':('3방 사격','Trilateral의 세 방향 의미'),
    'Two turns until megaflare.':('메가플레어까지 앞으로 2턴.','Two turns는 2턴'),
    'One turn until megaflare.':('메가플레어까지 앞으로 1턴.','One turn은 1턴'),
    '次ターンに5周年記念 針五万本を使用！':('다음 턴에 5주년 기념 침 5만 개를 사용!','五万本과 5만 개의 수량 일치'),
    '5周年記念 針五万本':('5주년 기념 침 5만 개','五万本과 5만 개의 수량 일치'),
    'カウントがゼロに近づいた':('카운트가 0에 가까워졌다','ゼロ는 0'),
    'Quadruple Blade Slash':('4연 베기','Quadruple은 네 번'),
    'Quadruple Sword Strike':('4연속 검격','Quadruple은 네 번'),
    'Can escape death once during battle!':('전투 중 1회 전투 불능을 버텨냄!','once는 한 번'),
}

def main():
    records={v['source']:v['ffbe_id'] for v in C.manifest()['records']}
    assert set(FIXES)<=set(records)
    terms=canonical_terms()
    fixes={records[source]:ko for source,ko in FIXES.items()}
    equivalents={records[source]:{'source':source,'translation':ko,'reason':reason}
                 for source,(ko,reason) in NUMBER_EQUIVALENTS.items()}
    fixes.update({rid:entry['translation'] for rid,entry in equivalents.items()})
    (C.HERE/'number_equivalents.json').write_text(json.dumps(equivalents,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    fixes.update({records[source]:entry['translation'] for source,entry in terms.items() if source in records})
    byid={v['ffbe_id']:v for v in C.manifest()['records']}
    for path in sorted((C.PROJECT/'gt_output').glob('*.json')):
        try:rows=C.read(path)
        except json.JSONDecodeError:continue
        for row in rows:
            rec=byid[row['ffbe_id']]
            before=C.restore(row.get('message',''),rec['tokens'])
            after=normalize_families(rec['source'],before)
            if before!=after:fixes.setdefault(row['ffbe_id'],after)
    (C.HERE/'canonical_terms.json').write_text(json.dumps(terms,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    (C.HERE/'manual_fixes.json').write_text(json.dumps(fixes,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('적 기술 명시적 보정',len(fixes),'문구')

if __name__=='__main__':main()

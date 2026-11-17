"""기술 번역의 명시적 검수 보정. 원본/번역 캐시는 수정하지 않는다."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import skills_common as C

FIXES={
    '片手持ちアタッカー(魔精)II':'한손잡기 공격자(마력·정신력) II',
    'くすりのちしき改':'약의 지식 개량',
    'Code：E':'코드: E',
    '光の報復改':'빛의 보복 개량',
    'ぜんそくぜんぎり改':'전속력 전방위 베기 개량',
    'or not to [B]e':'존재하지 않을 것인가 [B]',
    'Shall We Dance?':'함께 춤추실까요?',
    'クイックトリック改':'퀵 트릭 개량',
    'スパイラルカット改':'스파이럴 컷 개량',
    'エナジーレイン改':'에너지 레인 개량',
    '絆を情の力に変えて':'유대를 정이라는 힘으로 바꾸어',
    'レーザーキャノン改':'레이저 캐논 개량',
    'さくれつだん改':'작렬탄 개량',
    '高出力発生装置改':'고출력 발생 장치 개량',
    '紅き騎士の剣 改':'붉은 기사의 검 개량',
    'ブレイズセイバーIf 改':'블레이즈 세이버 If 개량',
    'かばって受ける 改':'감싸서 받기 개량',
    '炎獣の剣 改':'염수의 검 개량',
    'ソイルセイバーIf 改':'소일 세이버 If 개량',
    'サニタイズハート・重度':'새니타이즈 하트·중증',
    'オニオンブレイダー改':'어니언 블레이더 개량',
    '武神に立ち向かう者-宴-':'무신에 맞서는 자 -잔치-',
    '武神に立ち向かう者-縁-':'무신에 맞서는 자 -인연-',
    '鎧化(アムド)':'갑옷화(아무드)',
    'サスーンの護り':'사슨의 수호',
    'シーンドライブ改':'시너 드라이브 개량',
    'Distress Signal':'구조 신호',
    'Command - Showtime':'커맨드 - 쇼타임',
    'Yeah!':'좋았어!',
    'MP BOOST':'MP 부스트',
    'Ho229 Type-B':'Ho229 B형',
    'さんれんメイキョウゥゥ！':'삼연속 메이쿄오오!',
    '味方全体:攻魔アップ<br>敵全体:防精ダウン<br>味方全体:毎ターンMP回復<br>1T後特定効果発動<br>2T後特定効果発動':
        '아군 전체: 공격력·마력 증가<br>적 전체: 방어력·정신력 감소<br>아군 전체: 매 턴 MP 회복<br>1턴 후 특정 효과 발동<br>2턴 후 특정 효과 발동',
    '味方全体:攻防魔精アップ<br>1T後特定効果発動<br>2T後特定効果発動<br>味方全体:光属性付与':
        '아군 전체: 공격력·방어력·마력·정신력 증가<br>1턴 후 특정 효과 발동<br>2턴 후 특정 효과 발동<br>아군 전체: 빛 속성 부여',
    '味方全体:防精アップ<br>敵全体:攻魔ダウン<br>味方全体:毎ターンHP回復<br>1T後特定効果発動<br>2T後特定効果発動':
        '아군 전체: 방어력·정신력 증가<br>적 전체: 공격력·마력 감소<br>아군 전체: 매 턴 HP 회복<br>1턴 후 특정 효과 발동<br>2턴 후 특정 효과 발동',
    '敵1体:火物理ダメージ<br>敵1体:火耐性ダウン<br>自分:火属性付与<br>自分:火属性ダメージアップ(LB/アビリティ)<br>自分:火属性ダメージアップ(LB/魔法)':
        '적 1체: 불속성 물리 피해<br>적 1체: 불속성 내성 감소<br>자신: 불속성 부여<br>자신: 불속성 피해 증가(LB/어빌리티)<br>자신: 불속성 피해 증가(LB/마법)',
    '攻固定値アップ:500<br>特定アビリティ強化<br>特定アビリティ強化':
        '공격력 고정치 증가:500<br>특정 어빌리티 강화<br>특정 어빌리티 강화',
    '【戦闘終了時】8種状態異常解除<br>8種状態異常耐性アップ:50%':
        '【전투 종료 시】8종 상태이상 해제<br>8종 상태이상 내성 증가:50%',
    '攻アップ:30%<br>特定アビリティ強化<br>特定アビリティ強化<br>LBダメージアップ:150%<br>攻固定値アップ:1000':
        '공격력 증가:30%<br>특정 어빌리티 강화<br>특정 어빌리티 강화<br>LB 피해 증가:150%<br>공격력 고정치 증가:1000',
    '自分:火属性ダメージアップ(LB/アビリティ)<br>自分:火属性ダメージアップ(LB/魔法)<br>自分:召喚ダメージアップ<br>自分:特定LB強化<br>自分:魔力ためる':
        '자신: 불속성 피해 증가(LB/어빌리티)<br>자신: 불속성 피해 증가(LB/마법)<br>자신: 소환 피해 증가<br>자신: 특정 LB 강화<br>자신: 마력 모으기',
    '召喚ゲージ消費:1<br>敵全体:召喚ダメージ<br>自分:特定アビリティ強化':
        '소환 게이지 소비:1<br>적 전체: 소환 피해<br>자신: 특정 어빌리티 강화',
    '召喚ゲージ消費:1<br>敵全体:召喚ダメージ<br>敵全体:確率で即死<br>自分:特定アビリティ強化':
        '소환 게이지 소비:1<br>적 전체: 소환 피해<br>적 전체: 확률로 즉사<br>자신: 특정 어빌리티 강화',
    '召喚ゲージ消費:1<br>敵全体:召喚ダメージ<br>敵全体:確率で即死':
        '소환 게이지 소비:1<br>적 전체: 소환 피해<br>적 전체: 확률로 즉사',
    '召喚ゲージ消費:1<br>味方全体:攻魔アップ<br>自分:特定アビリティ強化':
        '소환 게이지 소비:1<br>아군 전체: 공격력·마력 증가<br>자신: 특정 어빌리티 강화',
    '召喚ゲージ消費:1<br>味方全体:HPバリア付与<br>自分:特定アビリティ強化':
        '소환 게이지 소비:1<br>아군 전체: HP 보호막 부여<br>자신: 특정 어빌리티 강화',
}
RETAIN={
    'SeeD':'SeeD', 'G.F.':'G.F.', 'BWH30cm':'BWH30cm',
    'W・D.M.W':'W·D.M.W', 'T・D.M.W':'T·D.M.W',
    'WELT177':'WELT177','OMEGA100':'OMEGA100','Xeno304':'Xeno304',
    'HEIM270':'HEIM270','VIER170':'VIER170','USP-TU':'USP-TU','BRIG260':'BRIG260',
    'EVO MAG+20%':'EVO MAG+20%',
    **{f'FFBE+{v}%':f'FFBE+{v}%' for v in (10,20,30,60,100,200,300)},
}

def main():
    allrecords=C.manifest()['records']
    byid={r['ffbe_id']:r for r in allrecords}
    records={r['source']:r['ffbe_id'] for r in allrecords}
    fixes={records[jp]:ko for jp,ko in FIXES.items() if jp in records}
    retained={records[jp]:{'source':jp,'translation':ko,'reason':'원래 영문인 약칭·병기 고유 코드 보존'}
              for jp,ko in RETAIN.items() if jp in records}
    fixes.update({rid:v['translation'] for rid,v in retained.items()})
    # 반각 장음 기호만 남은 번역은 표시용 전각 대시로 통일한다.
    for path in sorted((C.PROJECT/'gt_output').glob('*.json')):
        try:rows=C.read(path)
        except json.JSONDecodeError:continue
        for row in rows:
            text=row.get('message','')
            if 'ｰ' in text:
                rec=byid[row['ffbe_id']]
                fixes.setdefault(row['ffbe_id'],C.restore(text.replace('ｰ','－'),rec['tokens']))
    (C.HERE/'retained_names.json').write_text(json.dumps(retained,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    (C.HERE/'manual_fixes.json').write_text(json.dumps(fixes,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('명시적 기술 번역 보정',len(fixes),'문구')

if __name__=='__main__':main()

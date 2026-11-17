"""JP 표에 원래 영어로 있던 아이템 이름/설명을 소량 수동 번역한다.

진행 중인 GalTransl 입력은 바꾸지 않는다. BGM의 영문 정식 곡명·HP+10% 같은
능력치 표기는 유지하고, 영어 고유 아이템 이름과 일반 설명만 함께 마무리한다.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import item_common as C

ENGLISH = {
    "Popstar's Microphone": '팝스타의 마이크',
    'Crimson Dragon Cowl': '크림슨 드래곤 두건',
    'Crimson Dragon Robe': '크림슨 드래곤 로브',
    "Popstar's Pendulum": '팝스타의 펜듈럼',
    'Crimson Wedge Heels': '크림슨 웨지힐',
    'Executioner': '처형인',
    'Instrumental Rhythm': '기악의 리듬',
    'Water': '워터',
    'Black Water': '블랙 워터',
    'Engage Kill': '인게이지 킬',
    'Null Silence': '침묵 무효',
    'Null Sleep': '수면 무효',
    'Null Confusion': '혼란 무효',
    '【VC】Project Engage': '【VC】프로젝트 인게이지',
    '【VC】Engage Kill': '【VC】인게이지 킬',
    '【VC】Engage Kiss': '【VC】인게이지 키스',
    'A red microphone made from the scales of the Crimson Dragon.': '크림슨 드래곤의 비늘로 만든 붉은 마이크.',
    'A red microphone made from the scales of the Crimson Dragon. Not only is it incredibly fashionable for a normal microphone, rumor also has it that whoever speaks through it can never be silenced.': '크림슨 드래곤의 비늘로 만든 붉은 마이크. 일반적인 마이크로 보기에는 무척 세련되었을 뿐 아니라, 이것을 통해 말하는 사람은 절대로 침묵에 걸리지 않는다는 소문도 있다.',
    'A red cowl decorated with the scales of the Crimson Dragon.': '크림슨 드래곤의 비늘로 장식한 붉은 두건.',
    'A red cowl decorated with the scales of the Crimson Dragon. It was especially designed to help the wearer keep warm, while also providing a means to conceal their identity whenever necessary.': '크림슨 드래곤의 비늘로 장식한 붉은 두건. 착용자의 체온을 유지하는 동시에, 필요할 때 정체를 숨길 수 있도록 특별히 제작되었다.',
    'A long robe decorated with the scales of the Crimson Dragon.': '크림슨 드래곤의 비늘로 장식한 긴 로브.',
    'A long robe decorated with the scales of the Crimson Dragon. Only the finest quality scales were selected to assemble this masterpiece. Many claim that the scales on the robe are so refined that they shimmer under the light of the moon.': '크림슨 드래곤의 비늘로 장식한 긴 로브. 최상급 비늘만을 엄선해 만든 걸작이다. 로브의 비늘은 매우 정교하게 다듬어져 달빛 아래에서 반짝인다고 한다.',
    'An antique pendulum very dear to a popstar from another world.': '이세계의 팝스타가 매우 소중히 여기는 오래된 펜듈럼.',
    'An antique pendulum very dear to a popstar from another world. It is rumored to be an heirloom of her family, and attached at the end of its chain is a crystal said to be enchanted with transcendental summoning magic.': '이세계의 팝스타가 매우 소중히 여기는 오래된 펜듈럼. 가문 대대로 내려온 물건이라는 소문이 있다. 사슬 끝에는 초월적인 소환 마법이 깃들었다고 전해지는 크리스탈이 달려 있다.',
    'A pair of pumps designed to give the wearer superb mobility.': '착용자에게 뛰어난 기동성을 주도록 설계한 구두.',
    'A pair of pumps designed to give the wearer superb mobility. These stylish shoes are said to be so comfortable that they help prolong the stamina of the wearer.': '착용자에게 뛰어난 기동성을 주도록 설계한 구두. 세련된 이 구두는 무척 편안하여 착용자가 더 오랫동안 활동할 수 있도록 돕는다고 한다.',
}


def main():
    tables = C.load_tables(); refs = C.references(tables)
    records,locations,translations = {},[],{}
    base = C.read(C.HERE/'manifest.json')
    occupied = {(r['table'],r['row'],r['field']) for r in base['locations']}
    for table,(idf,fields) in C.SPECS.items():
        for index,row in enumerate(tables[table][2]):
            if table in refs and str(row[idf]) not in refs[table]: continue
            for fld in fields:
                if (table,index,fld) in occupied: continue
                original = row.get(fld,'')
                source = row.get('G4L0YIB2',original) if fld=='cnLF6Cz1' else original
                if source not in ENGLISH: continue
                rid = C.rid(source)
                message,tokens = C.protect(source)
                records[rid] = {'ffbe_id':rid,'source':source,'message':message,'tokens':tokens,'category':table}
                translations[rid] = ENGLISH[source]
                locations.append({'table':table,'row':index,'id':str(row[idf]),'field':fld,
                                  'source':original,'translation_id':rid})
    assert set(ENGLISH) == {r['source'] for r in records.values()}
    C.write_checked(C.HERE/'supplement.json',{'records':list(records.values()),'locations':locations,'translations':translations})
    print('영문 보완 번역',len(records),'문구·',len(locations),'필드')


if __name__ == '__main__': main()

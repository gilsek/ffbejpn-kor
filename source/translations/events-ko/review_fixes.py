"""검수에서 확인한 두 패턴만 보정하고 ID별 결과를 남긴다. 숫자 예외는 자동 승인하지 않는다."""
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    report=json.loads((ROOT/'build/out/events_gt/qa.json').read_text(encoding='utf-8'))
    path=HERE/'manual_fixes.json'
    fixes=json.loads(path.read_text(encoding='utf-8'))
    changed={}
    for issue in report['issues']:
        source=issue.get('source','');old=issue.get('translation','');text=fixes.get(issue.get('id'),old)
        if issue['issue']=='괄호 불균형' and source.count('「')==source.count('」'):
            # 이전 이름 사전에서 유입된 「'이름'을 / 「'이름'전 패턴.
            text=re.sub(r"「'([^']+)'(?!」)",r'「\1」',text)
            text=re.sub(r"(?<!「)'([^']+)'」",r'「\1」',text)
            if text.count('「')!=text.count('」'):continue
        elif issue['issue']=='초급/초월급 혼동' and '超級' in source and '初級' not in source:
            text=re.sub(r'(?<![가-힣])초급(?![가-힣])','초월급',text)
        elif issue['issue']=='수치 변경' and '闘星' in source:
            # 고유 칭호의 한자 수를 숫자로 쓰지 않는다. 실제 턴 수 등은 보존한다.
            titles={'三':('3','삼'),'四':('4','사'),'五':('5','오'),'六':('6','육'),
                    '八':('8','팔'),'十':('10','십'),'十一':('11','십일'),
                    '十四':('14','십사'),'十五':('15','십오')}
            m=re.search(r'([一二三四五六七八九十]+)闘星',source)
            if m and m[1] in titles:
                number,word=titles[m[1]]
                text=re.sub(r'(?<!\d)'+number+r'투성',word+'투성',text)
        elif issue['issue']=='수치 변경' and '八賢者' in source:
            text=text.replace('8현자','팔현자')
        elif issue['issue']=='일본어 잔존':
            # 같은 이벤트의 완료된 번역 제목과 대조한 잔존 조각.
            reviewed={'煉獄降臨':'연옥강림','劫火の加護':'겁화의 가호',
                      '迅雷の加護':'신뢰의 가호','加護':'가호','巨人の心臓部':'거인의 심장부'}
            for jp,ko in reviewed.items():
                if jp in source:text=text.replace(jp,ko)
        if text!=old:
            fixes[issue['id']]=text
            changed[issue['id']]={'source':source,'before':old,'after':text,'reason':issue['issue']}
    path.write_text(json.dumps(fixes,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    log=ROOT/'build/out/events_gt/pattern-fixes.json'
    existing=json.loads(log.read_text(encoding='utf-8')) if log.exists() else {}
    existing.update(changed)
    log.write_text(json.dumps(existing,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('검토한 문구 패턴 보정',len(changed),'건')

if __name__=='__main__':main()

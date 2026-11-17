"""전투 대사 창 줄 맞춤.

JP 클라이언트 전투 대사 창은 한 줄 24자(공백 포함)에서 자동 줄바꿈하고 2줄까지 창 안에 보인다.
근거(2026-11-10): 기기 화면 「흥분해서 앞뒤 안 가리고 내달리는 건 내 역 / 할이잖아.」(24자 뒤 꺾임, 3번째 줄 창 밖),
JP 원문 전투 대사 18,217줄 중 24자 초과 10줄(튜토리얼 안내)뿐, 3줄 이상 대사 1개.

2026-11-14 변경: 엔진(TagString::parse)은 실제 글자 폭이 아니라 글자 크기 설정값으로 폭을 센다
(전각 1, 반각 0.5). 한국어 폰트를 0.90배로 줄였으므로 한 줄을 26자로 늘리고, 사용자 요청으로
문장 부호(PUNCT)는 글자 수에 넣지 않는다. 엔진 쪽 자동 줄바꿈은 jp_talk_wrap.js가 대사 창에서만
여유 있게 넓혀 이 표의 줄 나눔이 그대로 보이게 한다.
"""
import re

HANGUL = re.compile('[가-힣]')
WIDTH = 26
MAX_LINES = 2
BREAK_AFTER = '.!?…‚,~」』)'
# 글자 수에서 빼는 문장 부호(반각·전각). 공백과 글자는 1자로 센다.
PUNCT = set('.,!?…‥~～・、。，．！？：；:;\'"“”‘’「」『』()（）[]［］-－—–')
TAG = re.compile(r'<[^>]*>')


def units(line):
    """줄의 글자 수(태그와 문장 부호 제외)."""
    return sum(1 for ch in TAG.sub('', line) if ch not in PUNCT)


def rendered_lines(lines, width=WIDTH):
    return sum(max(1, -(-units(l) // width)) for l in lines)


def fits(lines, width=WIDTH, max_lines=MAX_LINES):
    return all(units(l) <= width for l in lines) and len(lines) <= max_lines


def fit(text, sep='\n', width=WIDTH, max_lines=MAX_LINES):
    """줄이 창을 넘으면 공백 위치에서 다시 나눈다. 맞출 수 없으면 None, 이미 맞으면 원문 그대로."""
    lines = text.split(sep)
    if fits(lines, width, max_lines):
        return text
    words = ' '.join(l.strip() for l in lines).split(' ')
    joined = ' '.join(words)
    if units(joined) <= width:
        return joined
    if max_lines != 2:
        raise ValueError('max_lines 2 only')
    # 원래 줄바꿈 위치(단어 경계 번호)
    orig, n = set(), 0
    for l in lines[:-1]:
        n += len(l.strip().split(' '))
        orig.add(n)
    best = None
    for i in range(1, len(words)):
        a, b = ' '.join(words[:i]), ' '.join(words[i:])
        if units(a) > width or units(b) > width:
            continue
        score = (0 if i in orig else 1, 0 if a[-1] in BREAK_AFTER else 1, abs(units(a) - units(b)))
        if best is None or score < best[0]:
            best = (score, a + sep + b)
    return best[1] if best else None

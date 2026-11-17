"""스텝업 탭 시험용 배너를 build/engine_overlay/gacha_authored.json에 붙인다(2026-11-16).

기존 시즌/콜라보 배너의 풀과 그림을 복제해 type 'step' 배너로 만든다. 엔진 wire_type이 steps 배너를 타입 5로
보내고, build/frida/jp_stepup_tab.js가 타입 5를 세 번째 탭(Step-Up Summon)으로 옮긴다.
단계 구성은 STEP_OVERRIDES가 없으면 임시 틀(사용자 확정 전): 5단계 모두 11연, 3단계 ★5 이상 1체 확정, 5단계 NV 1체 확정.
비용은 시험 정책대로 단계마다 라피스 1. 다시 실행해도 같은 결과(stepup_source 표시가 있는 배너를 먼저 지운다).
make_jp_season_banners.py가 gacha_authored.json을 다시 쓰면 이 스크립트도 다시 실행해야 한다.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'build/engine_overlay/gacha_authored.json'
SOURCES = ['99920024', '99920037', '99111001']   # 제노기어스, 다이의 대모험, 시즌1 FFBE
# 2026-11-16 스텝업 보류(사용자 결정): 구형 화면은 위쪽 큰 그림 자리가 비어 애매하다. False면 시험 배너를 지우기만 한다.
ENABLED = False
ID_PREFIX = '9993'
TEST_COST = {'kind': 'lapis', 'amount': 500}   # 11연 가격(2026-11-17, make_jp_banners.lapis_price)
STEPUP_LAYOUT = 0
MOG_MESSAGE = '스텝마다 보너스를 받을 수 있어쿠포!'
STEPS = [
    {'draws': 11},
    {'draws': 11},
    {'draws': 11, 'guarantee': {'rarity': 5, 'count': 1}},
    {'draws': 11},
    {'draws': 11, 'guarantee': {'rarity': 7, 'count': 1}},
]

# 그림이 원작 스텝업 그림인 배너는 그 공지대로 단계를 맞춘다(비용만 시험용 1 라피스, 무료 단계는 무료).
# 다이: 2022-01-31 「ダイの大冒険」コラボ ステップアップ11連召喚フェス [バラン・ハドラー・ヒュンケル]
#   (twitter_identify_agy.jsonl id 1488064508094386177; 3周限定).
#   STEP1 2500 ★5/NV 1체 확정 / STEP2 3000 ★5/NV 3체 확정 + 티켓×1 / STEP3 NV 1체 확정(픽업 3체 합계 5%)
#   STEP4 무료 11연 / STEP5 티켓×2 / STEP6 NV 1체 확정(픽업 3체 합계 10%).
#   원작 가격은 orig_cost에 남긴다(3·5·6단계 가격은 그림에 없음). 티켓 보너스(아이템 판독 불가)와
#   확정 칸 안의 픽업 확률(5%/10%)은 아직 넣지 않았다.
FREE = {'kind': 'free', 'amount': 0}
STEP_OVERRIDES = {
    '99920037': {
        'lap_limit': 3,
        'steps': [
            {'draws': 11, 'guarantee': {'rarity': 5, 'count': 1}, 'orig_cost': 2500},
            {'draws': 11, 'guarantee': {'rarity': 5, 'count': 3}, 'orig_cost': 3000},
            {'draws': 11, 'guarantee': {'rarity': 7, 'count': 1}},
            {'draws': 11, 'cost': FREE, 'orig_cost': 0},
            {'draws': 11},
            {'draws': 11, 'guarantee': {'rarity': 7, 'count': 1}},
        ],
    },
}


def make(src):
    b = copy.deepcopy(src)
    for k in ('secondary_offer', 'detail_id', 'draws', 'cost', 'gacha_layout', 'preview_units'):
        b.pop(k, None)
    b['id'] = ID_PREFIX + str(src['id'])[4:]
    b['type'] = 'step'
    b['name'] = str(src['name']) + ' 스텝업'
    over = STEP_OVERRIDES.get(str(src['id']), {})
    b['steps'] = [dict(s, cost=dict(s.get('cost') or TEST_COST)) for s in over.get('steps', STEPS)]
    b['lap_limit'] = over.get('lap_limit', 0)
    b['stepup_source'] = str(src['id'])
    # 0 = 구형 스텝업 레이아웃(그림이 위쪽 640x420 자리). 2(신형)는 전면 배경 그림(bgInfo)이 없으면 위쪽이 빈다.
    b['stepup_layout'] = STEPUP_LAYOUT
    # 구형 화면의 모그리·말풍선은 GachaMst 긴 설명문(+0x70)이 있어야 나온다(jp_gacha.py jp_groups).
    b['mog_message'] = MOG_MESSAGE
    if src.get('preview_units'):
        b['preview_units'] = list(src['preview_units'])
    return b


def main():
    doc = json.loads(PATH.read_text(encoding='utf-8'))
    banners = [b for b in doc['banners'] if 'stepup_source' not in b]
    by_id = {str(b['id']): b for b in banners}
    added = []
    for sid in (SOURCES if ENABLED else []):
        src = by_id.get(sid)
        if not src:
            print('missing source', sid)
            continue
        if not any(int(p.get('rarity') or 0) >= 7 for p in src.get('pool', [])):
            print('skip (no NV in pool)', sid)
            continue
        added.append(make(src))
    doc['banners'] = banners + added
    PATH.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for b in added:
        print(b['id'], b['name'], b['season'], len(b['steps']), 'steps')


if __name__ == '__main__':
    main()

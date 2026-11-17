"""모든 소환 배너의 풀에 저레어 공용 풀을 섞어 확률을 다시 짠다(2026-11-16 사용자 결정, 전체 배너 적용).

기조: 공용 풀 70% + 배너 유닛 30%, NV 확률은 배너당 합산 15%.
  배너 몫: ★1-4 10% / ★5-6 5% / NV(★7) 15%. 배너에 없는 등급의 몫은 공용 풀로 넘긴다
  (NV만 있는 콜라보 배너가 NV 30%가 되지 않게).
  공용 풀: 시즌 배너(콜라보 제외)에 들어 있는 기본 ★3·★4 유닛 전체, 유닛마다 같은 확률.
배너 원래 유닛은 'banner_pool'에 보관하고 다시 실행하면 그것에서 새로 계산한다(재실행 가능).
비용은 건드리지 않는다(시험 중 라피스 1 유지).

순서: make_jp_season_banners.py -> (make_jp_stepup_banners.py) -> 이 스크립트.
스텝업 배너는 원본 배너를 복제하므로 둘 다 이 스크립트가 처리한다.
"""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'build/engine_overlay/gacha_authored.json'
COMMON_SHARE = 0.70
BANNER_TIERS = {'low': 0.10, 'mid': 0.05, 'high': 0.15}
COMMON_RARITIES = (3, 4)
EXCLUSIVE_BANNER_TIERS = {
    '99920048': {'low': 0.55, 'mid': 0.30, 'high': 0.15},
}


def tier(r):
    return 'low' if r <= 4 else 'mid' if r <= 6 else 'high'


def main():
    doc = json.loads(PATH.read_text(encoding='utf-8'))
    banners = doc['banners']
    for b in banners:
        if 'banner_pool' not in b:
            b['banner_pool'] = b['pool']
    common = {}
    for b in banners:
        if b.get('season') == 'collaborations' or 'stepup_source' in b:
            continue
        for p in b['banner_pool']:
            if int(p['rarity']) in COMMON_RARITIES:
                common[str(p['unit_id'])] = int(p['rarity'])
    assert common, 'empty common pool'
    report = collections.Counter()
    for b in banners:
        by_tier = collections.defaultdict(list)
        for p in b['banner_pool']:
            by_tier[tier(int(p['rarity']))].append(p)
        excl_tiers = EXCLUSIVE_BANNER_TIERS.get(str(b['id']))
        rates = collections.defaultdict(float)
        rarity = {}
        if excl_tiers:
            total_w = sum(excl_tiers[t] for t in by_tier)
            assert total_w > 0, (b['id'], 'empty exclusive tiers')
            for t, items in by_tier.items():
                tier_share = excl_tiers[t] / total_w
                for p in items:
                    uid = str(p['unit_id'])
                    rates[uid] += tier_share / len(items)
                    rarity[uid] = int(p['rarity'])
        else:
            common_share = COMMON_SHARE + sum(v for t, v in BANNER_TIERS.items() if t not in by_tier)
            for uid, r in common.items():
                rates[uid] += common_share / len(common)
                rarity[uid] = r
            for t, items in by_tier.items():
                for p in items:
                    uid = str(p['unit_id'])
                    rates[uid] += BANNER_TIERS[t] / len(items)
                    rarity[uid] = int(p['rarity'])
        b['pool'] = sorted(({'unit_id': u, 'rarity': rarity[u], 'rate': rates[u]} for u in rates),
                           key=lambda e: (-e['rarity'], e['unit_id']))
        s = sum(e['rate'] for e in b['pool'])
        assert abs(s - 1) < 1e-9, (b['id'], s)
        report[tuple(sorted(by_tier))] += 1
    PATH.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('banners', len(banners), 'common units', len(common),
          dict(collections.Counter(common.values())), 'tier sets', dict(report))


if __name__ == '__main__':
    main()

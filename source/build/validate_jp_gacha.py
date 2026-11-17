"""Check generated JP banner prices, currency preservation, preview membership and runtime policy."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def costs(value):
    if isinstance(value, dict):
        if 'kind' in value and 'amount' in value:
            yield value
        for item in value.values():
            yield from costs(item)
    elif isinstance(value, list):
        for item in value:
            yield from costs(item)


def jp_units():
    import sys
    sys.path.insert(0, str(ROOT / 'build'))
    import make_jp_banners as M
    return M.jp_masters()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--overlay', type=Path, default=ROOT / 'build/engine_overlay')
    args = parser.parse_args()
    overlay = args.overlay
    banners = json.loads((overlay / 'gacha_authored.json').read_text(encoding='utf-8'))['banners']
    by_id = {str(b['id']): b for b in banners}
    lapis = [c for c in costs(banners) if c['kind'] == 'lapis']
    assert lapis and any(c['amount'] == 500 for c in lapis) and all(c['amount'] > 1 for c in lapis), 'expected real lapis costs'
    assert '60001' in by_id and int(by_id['60001'].get('ticket_group_id') or 0) == 10010, 'missing 60001 EXVIUS ticket banner'
    checked = 0
    if args.before:
        before = json.loads(args.before.read_text(encoding='utf-8'))['banners']
        for b in before:
            if str(b['id']) not in by_id:
                continue
            other = lambda value: [c for c in costs(value) if c['kind'] != 'lapis']
            assert other(b) == other(by_id[str(b['id'])]), ('other currency changed', b['id'])
            checked += 1
    for b in banners:
        if isinstance(b.get('pool'), list) and 'preview_units' in b:
            pool = {str(u['unit_id']) for u in b['pool']}
            assert set(b['preview_units']) <= pool, ('preview outside pool', b['id'])
    units = {r['3HriTp6B']: r for r in jp_units()}
    import make_jp_banners as M
    for b in banners:
        for u in (b.get('pool') if isinstance(b.get('pool'), list) else []):
            uid = str(u['unit_id'])
            assert uid not in M.ID_CONFLICT, ('JP/GL id conflict in pool', b['id'], uid)
            assert str(units.get(uid, {}).get('A86KwrGh', '1')) != '0', ('non-collectible unit in pool', b['id'], uid)
    # No Global-only id anywhere a banner can name one (field units, bonus / box / reward-pool rewards).
    universe = M.jp_universe()
    def reward_ids(value):
        if isinstance(value, dict):
            r = value.get('reward') if isinstance(value.get('reward'), dict) else value
            if 'kind' in r and 'id' in r and 'amount' not in r:
                yield str(r['id'])
            for v in value.values():
                yield from reward_ids(v)
        elif isinstance(value, list):
            for v in value:
                yield from reward_ids(v)
    rewards = 0
    for b in banners:
        for u in (b.get('community') or {}).get('unit_ids') or []:
            assert str(u) in universe and str(u) not in M.ID_CONFLICT, ('Global-only field unit', b['id'], u)
        for rid in reward_ids(b):
            assert rid in universe, ('Global-only reward', b['id'], rid); rewards += 1
    assert rewards, 'reward scan found nothing'
    assert by_id['9100279']['preview_units'] == [], 'GL-only Maeve substituted'
    assert by_id['9100280']['preview_units'] == ['210002107'], 'Yuna banner selected numeric-first Wakka'
    assert by_id['12']['preview_units'] == ['206001705'], 'featured name order lost'
    spec = importlib.util.spec_from_file_location('jp_gacha_policy', overlay / 'jp_gacha.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    assert policy.wire_type({'boxes': [{}]}, 7, lambda b, c: c) == 7, 'JP box moved off free tab'
    assert policy.wire_type({'cost': {'kind': 'lapis'}}, 50, lambda b, c: c) == 1, 'GL event type not filed on JP pay tab'
    assert policy.wire_type({}, 5, lambda b, c: c) == 5, 'step-up type changed'
    assert policy.wire_type({'cost': {'kind': 'item'}, 'tab': 'limited'}, 50, lambda b, c: c) == 0, 'ticket retained GL limited/pay tab'
    assert policy.normalize_ticket_rarity('4:95000000,5:5000000@2020-01-01 00:00:00#4:90000000,5:7000000,7:3000000') == '4'
    assert policy.normalize_ticket_rarity('5') == '5'
    assert policy.normalize_ticket_rarity('') == ''
    original = [
        {'cost': {'kind': 'lapis', 'amount': 500}, 'draws': 1, 'preview_units': ['100000105'],
         'secondary_offer': {'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11}},
        {'cost': {'kind': 'lapis', 'amount': 500}, 'draws': 1, 'preview_units': [],
         'secondary_offer': {'cost': {'kind': 'lapis', 'amount': 5000}, 'draws': 11}},
        {'id': '60001', 'cost': None, 'ticket_group_id': 10010, 'preview_units': ['100000105']},
        {'cost': {'kind': 'lapis', 'amount': 500}, 'steps': [{'cost': {'kind': 'lapis', 'amount': 2500}}]},
    ]
    fake = SimpleNamespace(
        all_banners=lambda: original,
        gacha_field_units=lambda b: ['wrong fallback'],
        _gacha_cost_string=lambda c, d=1, i=0: '' if not c or c.get('kind') == 'free' else 'original',
    )
    policy.install(fake)
    norm = fake.all_banners()
    assert [c['amount'] for c in costs(norm)] == [500, 5000, 500, 5000, 500, 2500], 'lapis costs altered'
    assert norm[0]['gacha_layout'] == 1 and norm[0]['img_btn_primary'] == 'gacha_btns_gold_1'
    assert norm[0]['secondary_offer']['img_btn'] == 'gacha_btns_gold_11'
    assert norm[1]['gacha_layout'] == 0 and norm[1]['img_btn_primary'] == 'gacha_btn_r'
    assert norm[1]['secondary_offer']['img_btn'] == 'gacha_btn_r_multi'
    assert norm[2]['gacha_layout'] == 0 and norm[2]['img_btn_primary'] == 'gacha_btn_r'
    assert norm[3]['gacha_layout'] == 2
    assert 'gacha_layout' not in original[0], 'runtime policy mutated cached original'
    assert fake.gacha_field_units({'preview_units': []}) == [], 'empty preview fell back'
    assert fake.gacha_field_units({}) == ['wrong fallback'], 'legacy behavior changed'
    assert fake._gacha_cost_string({'kind': 'free'}) == '50:1:0:1', 'free JP cost map empty'
    assert fake._gacha_cost_string(None) == '', 'ticket-only empty cost rewritten'
    assert fake._gacha_cost_string({'kind': 'item', 'amount': 1}) == 'original', 'item protocol changed'
    print(f'PASS: {len(banners)} banners, {len(lapis)} real lapis costs, 60001 EXVIUS ticket present, '
          f'{checked} currency-preservation comparisons; layout/button/rarity checks OK')


if __name__ == '__main__':
    main()

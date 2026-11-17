"""Audit JP cost IDs/wire and isolated engine deductions; never writes a player save."""
import copy
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_jp_banners as M
os.environ['FFBE_DATA'] = str(M.STATIC)
import ffbe_gacha as G
import player_state as P
import gacha_archive as A


def main():
    spec = importlib.util.spec_from_file_location('jp_policy', M.OVERLAY / 'jp_gacha.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    policy.install(G)
    native = zipfile.ZipFile(M.OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
    manifest = {m.group(1).decode(): (m.group(2).decode(), m.group(3).decode()) for m in M.D.TRIPLET.finditer(native)}
    files = {p.stem.split('_', 1)[1]: p for p in (M.OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}
    masters = {}
    sources = {}
    for kind, table, key in [('item', 'F_ITEM_MST', 'tL6G9egd'), ('important', 'F_IMPORTANT_ITEM_MST', '2dfixko3')]:
        token, secret = manifest[table]
        masters[kind] = {r[key]: r for r in M.D.decode(files[token].read_bytes(), secret, localized=False)[1]}
        sources[kind] = files[token].name
    banners = json.loads((M.OVERLAY / 'gacha_authored.json').read_text(encoding='utf-8'))['banners']
    result = []
    for b in banners:
        c = b.get('cost') or {}
        if not isinstance(c, dict) or c.get('kind') not in masters:
            continue
        kind, item, amount = c['kind'], str(c['item_id']), int(c['amount'])
        assert item in masters[kind], (b['id'], 'JP master missing', kind, item)
        wire = G._gacha_cost_string(c, 1, int(item))
        assert wire == f'{P.cost_numeric_kind(kind)}:{item}:{amount}:1', (b['id'], wire)
        entry = {'id': str(b['id']), 'banner': b['name'], 'kind': kind, 'item_id': item,
                 'jp_item': masters[kind][item].get('G4L0YIB2'), 'wire': wire,
                 'jp_tab_code': policy.wire_type(b, G.gacha_type_code(b), A.wire_type)}
        assert entry['jp_tab_code'] == (6 if b.get('selection') else 7 if b.get('boxes') else 0), (b['id'], 'wrong JP tab')
        outcomes = []
        for balance in (0, amount - 1, amount, amount + 1):
            state = P.PlayerState(P.default_state(), mode='ephemeral')
            state.grant_item(P.cost_numeric_kind(kind), int(item), balance)
            before = copy.deepcopy(state.data)
            if b.get('selection'):
                # Selection uses a separate endpoint, not roll_gacha; test its storage deduction only.
                response = {} if state.spend_item(P.cost_numeric_kind(kind), int(item), amount) else None
                entry['test_operation'] = 'spend_item_only; selection endpoint not exercised'
            elif b.get('boxes'):
                from gacha_box import detail_id, roll
                response = roll(state, copy.deepcopy(b), detail_id(state, b), 1)
                entry['test_operation'] = 'gacha_box.roll'
            else:
                response = state.roll_gacha(copy.deepcopy(b))
                entry['test_operation'] = 'PlayerState.roll_gacha'
            after = state.item_count(P.cost_numeric_kind(kind), int(item))
            assert (response is not None) == (balance >= amount), (b['id'], balance, response)
            assert after == (balance - amount if response is not None else balance), (b['id'], balance, after)
            assert state.currencies == before['currencies'], (b['id'], 'unrelated currency changed')
            if response is None:
                assert state.data.get('roster') == before.get('roster'), (b['id'], 'failed pull awarded units')
            outcomes.append({'before': balance, 'after': after, 'awarded': response is not None})
        entry['isolated_checks'] = outcomes
        result.append(entry)
    output = {'sources': sources, 'limits': 'Tests use original GL engine in-memory ephemeral state, not the JP UI. Numeric JP master existence does not prove GL/JP event semantics match.',
              'banners': result, 'checks': sum(len(r['isolated_checks']) for r in result)}
    (M.REPORT / 'cost-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'PASS: {len(result)} item/important banners; {output["checks"]} isolated cost checks; no save written')


if __name__ == '__main__':
    main()

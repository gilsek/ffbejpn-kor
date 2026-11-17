"""Tests for build/engine_overlay/jp_unit_fixes.py.

Runs the engine modules in-process against the JP decoded masters and a fake live player.
Run:  python -I -X utf8 build/test_jp_unit_fixes.py   (PYTHONIOENCODING=utf-8)
"""
import json
import os
import site
import sys

# `python -I` hides the user site, where the engine's PyYAML lives; the test needs it.
sys.path.append(site.getusersitepackages())

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix\upstream\source\server'
MST = os.path.join(ROOT, 'build', 'out', 'jp_offline', 'engine', 'static', 'mst_decoded')
OVERLAY = os.path.join(ROOT, 'build', 'engine_overlay')

os.environ['MST_DIR'] = MST
sys.path.insert(0, ENGINE)
sys.path.insert(0, OVERLAY)

import ffbe_state                      # noqa: E402
import player_state                    # noqa: E402
import exvius_actions as ea            # noqa: E402
import exvius_actions_shops as sh      # noqa: E402
import jp_unit_fixes                   # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + ((' -- ' + detail) if detail and not ok else ''))


def player():
    return ffbe_state.State.player


def fresh_player():
    ffbe_state.State.player = player_state.PlayerState(player_state.default_state(), mode='live')
    jp_unit_fixes.install(None)
    return ffbe_state.State.player


def add_unit(master_id, iid):
    unit = player().grant_unit(master_id, instance_id=iid)
    assert unit is not None, master_id
    return unit


FIVE_KEYS = {'og2GHy49', 'ijEey5f7', 'tL6G9egd', '1swM3H4T', 'T85HmdKB'}

if not os.path.isdir(MST):
    print('SKIP: JP masters not found at ' + MST)
    raise SystemExit(2)

# --- 1. conversion -------------------------------------------------------------------------------------
fresh_player()

# (a) exeType 0 (輝源) of a ★6: the series row's shine item only, sent in SacrificeRequest.
add_unit('100000106', 900000001)
out = ea.HANDLERS['7tWdn9zH']({'Z': 1}, {'6kvFj2Kw': [{'og2GHy49': '900000001', 'ijEey5f7': '0'}]})
node = (out.get('6kvFj2Kw') or [{}])[0]
check('sacrifice exe0: five response keys', set(node) == FIVE_KEYS, repr(sorted(node)))
check('sacrifice exe0: shine item id', node.get('tL6G9egd') == '300005800', repr(node.get('tL6G9egd')))
check('sacrifice exe0: only the item, no 欠片', node.get('1swM3H4T') == '20:300005800:1',
      repr(node.get('1swM3H4T')))
check('sacrifice exe0: no moogle', node.get('T85HmdKB') == '', repr(node.get('T85HmdKB')))
check('sacrifice exe0: unit removed', player().roster_row('900000001') is None)
check('sacrifice exe0: item credited', player().item_count(20, 300005800) >= 1,
      repr(player().item_count(20, 300005800)))

# (b) exeType 1 of a pure NV: the series row's 欠片, sent in SacrificeRequest.
add_unit('100031527', 900000002)
out = ea.HANDLERS['7tWdn9zH']({'Z': 1}, {'6kvFj2Kw': [{'og2GHy49': '900000002', 'ijEey5f7': '1'}]})
node = (out.get('6kvFj2Kw') or [{}])[0]
check('sacrifice exe1 pure NV: no shine id', node.get('tL6G9egd') == '0', repr(node.get('tL6G9egd')))
check('sacrifice exe1 pure NV: series 欠片', node.get('1swM3H4T') == '20:250000080:50,20:293000100:1',
      repr(node.get('1swM3H4T')))
check('sacrifice exe1 pure NV: five keys', set(node) == FIVE_KEYS, repr(sorted(node)))

# (c) exeType 1 of a sublimated NV: the unit-id row's 欠片, sent in NvSacrificeRequest.
add_unit('100000327', 900000003)
out = ea.HANDLERS['x94MnujU']({'Z': 1}, {'4Ncra9DF': [{'og2GHy49': '900000003', 'ijEey5f7': '1'}]})
node = (out.get('4Ncra9DF') or [{}])[0]
check('sacrifice exe1 NV: no shine id', node.get('tL6G9egd') == '0', repr(node.get('tL6G9egd')))
check('sacrifice exe1 NV: unit-id 欠片', node.get('1swM3H4T') == '20:250000120:50,20:293000200:4',
      repr(node.get('1swM3H4T')))

# (d) wrong group: the same conversion in SacrificeRequest is refused, nothing changes.
add_unit('100000327', 900000004)
out = ea.HANDLERS['7tWdn9zH']({'Z': 1}, {'6kvFj2Kw': [{'og2GHy49': '900000004', 'ijEey5f7': '1'}]})
check('sacrifice wrong group: no result list', not out.get('6kvFj2Kw'), repr(out.get('6kvFj2Kw')))
check('sacrifice wrong group: unit kept', player().roster_row('900000004') is not None)

# (e) a favourite unit is still refused (engine protection kept).
unit = player().roster_row('900000004')
unit['favourite'] = 1
out = ea.HANDLERS['x94MnujU']({'Z': 1}, {'4Ncra9DF': [{'og2GHy49': '900000004', 'ijEey5f7': '1'}]})
check('sacrifice favourite: refused', not out.get('4Ncra9DF') and player().roster_row('900000004') is not None)

# --- 2. EX awakening: a refusal names the unit ---------------------------------------------------------
add_unit('100000106', 900000005)
out = ea.HANDLERS['k6NI9Tm1']({'Z': 1}, {'14vWb7kX': [{'og2GHy49': '900000005', 'KCk8u0am': '20:1:1'}]})
node = (out.get('14vWb7kX') or [{}])[0]
check('EX refusal: result node present', set(node) == {'og2GHy49', 'KCk8u0am', 'Knra4I19', 'Qic38SuC'},
      repr(sorted(node)))
check('EX refusal: unit id echoed', node.get('og2GHy49') == '900000005', repr(node.get('og2GHy49')))
check('EX refusal: discount 0', node.get('Knra4I19') == '0', repr(node.get('Knra4I19')))
check('EX refusal: unchanged lv info', str(node.get('Qic38SuC', '')).startswith('900000005@')
      and str(node.get('Qic38SuC', '')).split('@', 1)[1].split('_')[0] == str(node.get('Qic38SuC', '')).split('_')[-1],
      repr(node.get('Qic38SuC')))

# --- 3a. warehouse move: the answer carries the moved unit record --------------------------------------
add_unit('100000106', 900000006)
import ffbe_player as fp  # noqa: E402
request = json.dumps({'JMxPV87y': [{'km9gKXJ5': '1', 'ng9xPNt8': '900000006'}]})
out = fp.serve_unit_storage({'Z': 1}, request)
records = out.get('8gSkPD6b') or []
rec = next((r for r in records if r.get('og2GHy49') == '900000006'), None)
check('storage move: unit record present', rec is not None, repr(records)[:300])
check('storage move: QHFU1k43 set', bool(rec) and rec.get('QHFU1k43') == '1', repr(rec and rec.get('QHFU1k43')))
check('storage move: state updated', (player().roster_row('900000006') or {}).get('storage_state') == 1)

# --- 3b. warehouse rename ------------------------------------------------------------------------------
out = ea.HANDLERS['1ghJ8WpG']({'Z': 1}, {'n0uA2hzR': [{'QHFU1k43': '2', 'G4L0YIB2': '보관함'}]})
node = (out.get('n0uA2hzR') or [{}])[0]
check('rename: same node answer', node.get('G4L0YIB2') == '보관함' and node.get('QHFU1k43') == '2',
      repr(node))
check('rename: name saved', (player().data.get('unit_storage_names') or {}).get('2') == '보관함',
      repr(player().data.get('unit_storage_names')))
check('rename: dirty', player().dirty is True)

# --- summary -------------------------------------------------------------------------------------------
failed = [name for name, ok, _ in RESULTS if not ok]
print('\n%d/%d passed' % (len(RESULTS) - len(failed), len(RESULTS)))
if failed:
    print('FAILED: ' + ', '.join(failed))
raise SystemExit(1 if failed else 0)

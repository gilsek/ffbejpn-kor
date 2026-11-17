"""Tests for build/engine_overlay/jp_unit_refusals.py.

Runs the engine modules in-process against the JP decoded masters and a fake live player.
Run:  python -I -X utf8 build/test_jp_unit_refusals.py   (PYTHONIOENCODING=utf-8)

Every refusal case asserts (a) the reply carries the result tag L's safe-refusal body carries and
(b) player.data is byte-identical before and after. Every success case asserts the wrapped reply
and state equal the ORIGINAL handler's (time frozen: renewed instance ids are epoch-ms based).
"""
import copy
import json
import os
import site
import sys
import time as _time_mod

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
import ffbe_player as fp               # noqa: E402

# The ORIGINAL handlers, saved before the install wraps them.
ORIG_STAR = ea.HANDLERS['zf49XKg8']
ORIG_NV = sh.HANDLERS['Pf5C8xjJ']
ORIG_NVP = sh.HANDLERS['V8GtMQ2q']
ORIG_MIX = fp.serve_unit_mix

import jp_unit_refusals                # noqa: E402
jp_unit_refusals.install(None)

import ffbe_pipeline as pl             # noqa: E402

RESULTS = []
STAR_KEYS = {'og2GHy49', '5u7VYNEX', 'KCk8u0am', 'WbGYcN17', '02CI3bpE', 'p9Xj4Anc'}
MIX_KEYS = {'og2GHy49', 'WbGYcN17', '7UR4J2SE', 'B6H34Mea', 'UDMIFB72', '1dT7ha9H', 'E90oBqct'}

# Renewed instance ids are int(time.time() * 1000) + 1 (player_state.renew_unit_instance), and
# progress audit rows carry _mail_time(): freeze both so two runs are byte-comparable.
_REAL_TIME = _time_mod.time
_REAL_MAIL = player_state._mail_time


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + ((' -- ' + detail) if detail and not ok else ''))


def freeze_time():
    _time_mod.time = lambda: 1900000000.0
    player_state._mail_time = lambda: '2030-01-15T00:00:00Z'


def thaw_time():
    _time_mod.time = _REAL_TIME
    player_state._mail_time = _REAL_MAIL


def player():
    return ffbe_state.State.player


def fresh_player():
    ffbe_state.State.player = player_state.PlayerState(player_state.default_state(), mode='live')
    return player()


def add_unit(master_id, iid):
    unit = player().grant_unit(master_id, instance_id=iid)
    assert unit is not None, master_id
    return unit


def snapshot():
    return (copy.deepcopy(player().data), player().dirty)


def steps():
    return ea._mst('F_UNIT_CLASS_UP_MST.ndjson', '3HriTp6B')


def check_state(name, before):
    data, dirty = before
    check(name + ': player.data unchanged', player().data == data and player().dirty == dirty)


def check_no_roster_replace(name, out, reply_id):
    """The refusal must not hand the client a full B71MekS8 roster replacement."""
    answered = player().apply_to_reply(copy.deepcopy(out), reply_id=reply_id)
    check(name + ': no full roster in reply', 'B71MekS8' not in answered, repr(sorted(answered)))


if not os.path.isdir(MST):
    print('SKIP: JP masters not found at ' + MST)
    raise SystemExit(2)

# --- install wiring -----------------------------------------------------------------------------
check('install: pipeline rebound to the wrapper', pl.serve_unit_mix is fp.serve_unit_mix)
before_reinstall = ea.HANDLERS['zf49XKg8']
jp_unit_refusals.install(None)          # second call must be a no-op
check('install: idempotent', ea.HANDLERS['zf49XKg8'] is before_reinstall)
star_handler = ea.HANDLERS['zf49XKg8']
nv_handler = ea.HANDLERS['Pf5C8xjJ']
nvp_handler = ea.HANDLERS['V8GtMQ2q']
check('install: NV handlers registered in exvius_actions',
      sh.HANDLERS['Pf5C8xjJ'] is nv_handler and sh.HANDLERS['V8GtMQ2q'] is nvp_handler)

# --- 1a. ★ refusal: unit not owned ---------------------------------------------------------------
fresh_player()
before = snapshot()
out = star_handler(None, {'sWc7EH69': [{'og2GHy49': '999999999'}]})
node = (out.get('sWc7EH69') or [{}])[0]
check('★ unowned: result node present', set(node) == STAR_KEYS, repr(sorted(node)))
check('★ unowned: nothing to remove', node.get('og2GHy49') == '', repr(node.get('og2GHy49')))
check('★ unowned: requested unit as new', node.get('5u7VYNEX') == '999999999',
      repr(node.get('5u7VYNEX')))
check('★ unowned: no unit record group', '8gSkPD6b' not in out, repr(sorted(out)))
check_state('★ unowned', before)
check_no_roster_replace('★ unowned', out, 'zf49XKg8')

# --- 1b. ★ refusal: gil/materials missing -------------------------------------------------------
fresh_player()
add_unit('100000106', 900000101)
player().data.setdefault('inventory', {})['items'] = []
player().currencies['gil'] = 0
before = snapshot()
out = star_handler(None, {'sWc7EH69': [{'og2GHy49': '900000101'}]})
node = (out.get('sWc7EH69') or [{}])[0]
check('★ poor: result node present', set(node) == STAR_KEYS, repr(sorted(node)))
check('★ poor: unit echoed as new', node.get('5u7VYNEX') == '900000101', repr(node.get('5u7VYNEX')))
check('★ poor: unchanged unit record returned',
      any(r.get('og2GHy49') == '900000101' for r in out.get('8gSkPD6b') or []),
      repr(out.get('8gSkPD6b'))[:200])
check('★ poor: unit not awakened',
      (player().roster_row('900000101') or {}).get('master_id') == '100000106')
check_state('★ poor', before)
check_no_roster_replace('★ poor', out, 'zf49XKg8')

# --- 1c. ★ success: the wrapper changes nothing --------------------------------------------------
def star_setup():
    add_unit('100000106', 900000101)
    player().data.setdefault('inventory', {})['items'] = []
    player().add_currency('gil', 10000000)
    player()._grant_items([{'kind': 20, 'id': 300005800, 'count': 1}])


STAR_REQ = {'sWc7EH69': [{'og2GHy49': '900000101'}]}
freeze_time()
try:
    fresh_player(); star_setup()
    out_orig = ORIG_STAR(None, STAR_REQ)
    state_orig = snapshot()
    fresh_player(); star_setup()
    out_wrap = star_handler(None, STAR_REQ)
    state_wrap = snapshot()
finally:
    thaw_time()
new_id = ((out_wrap.get('sWc7EH69') or [{}])[0].get('5u7VYNEX'))
check('★ success: really awakened', new_id not in (None, '', '900000101'), repr(new_id))
check('★ success: reply identical to the original', out_wrap == out_orig,
      '%r vs %r' % (out_wrap, out_orig))
check('★ success: state identical to the original', state_wrap == state_orig)

# --- 2a. NV refusal: unit not owned --------------------------------------------------------------
fresh_player()
before = snapshot()
out = nv_handler(None, {'6U5w20zk': [{'og2GHy49': '999999999'}]})
node = (out.get('6U5w20zk') or [{}])[0]
check('NV unowned: result node present', set(node) == STAR_KEYS, repr(sorted(node)))
check('NV unowned: requested unit as new', node.get('5u7VYNEX') == '999999999',
      repr(node.get('5u7VYNEX')))
# _reply may attach a sublimation-flag delta under 8gSkPD6b (engine behaviour); the REFUSAL fill
# must not invent a record for the unowned unit.
check('NV unowned: no record invented for the unowned unit',
      not any(r.get('og2GHy49') == '999999999' for r in out.get('8gSkPD6b') or []),
      repr(out.get('8gSkPD6b'))[:200])
check_state('NV unowned', before)

# --- 2b. NV refusal: preconditions not met (a 7-star below the caps) -------------------------------
fresh_player()
add_unit('100000107', 900000102)
before = snapshot()
out = nv_handler(None, {'6U5w20zk': [{'og2GHy49': '900000102'}]})
node = (out.get('6U5w20zk') or [{}])[0]
check('NV preconditions: result node present', set(node) == STAR_KEYS, repr(sorted(node)))
check('NV preconditions: unchanged unit as new', node.get('5u7VYNEX') == '900000102',
      repr(node.get('5u7VYNEX')))
check('NV preconditions: unit not awakened',
      (player().roster_row('900000102') or {}).get('master_id') == '100000107')
check_state('NV preconditions', before)
# The @action refusal reply already carries the player groups (existing M behaviour, untouched here).
answered = player().apply_to_reply(copy.deepcopy(out), reply_id='Pf5C8xjJ')
check('NV refusal: full roster already present (existing behaviour, unchanged)',
      'B71MekS8' in answered, repr(sorted(answered)))

# --- 2c. NV+ refusal: wrong destination (a ★5's class-up row is not Neo Vision) --------------------
fresh_player()
add_unit('100000102', 900000103)
before = snapshot()
out = nvp_handler(None, {'6U5w20zk': [{'og2GHy49': '900000103'}]})
node = (out.get('6U5w20zk') or [{}])[0]
check('NV+ destination: result node present', set(node) == STAR_KEYS, repr(sorted(node)))
check('NV+ destination: unchanged unit as new', node.get('5u7VYNEX') == '900000103',
      repr(node.get('5u7VYNEX')))
check('NV+ destination: unit not awakened',
      (player().roster_row('900000103') or {}).get('master_id') == '100000102')
check_state('NV+ destination', before)

# --- 2d. NV+ success: the wrapper changes nothing -------------------------------------------------
STEP_NVP = steps()['100031507']
NVP_MAT = str(STEP_NVP.get('KCk8u0am') or '')
NVP_GIL = int(str(STEP_NVP.get('7UR4J2SE') or '0'))


def nvp_setup():
    add_unit('100031507', 900000104)
    player().data.setdefault('inventory', {})['items'] = []
    player().add_currency('gil', NVP_GIL + 1000)
    rows = [{'kind': int(k), 'id': int(i), 'count': int(c)}
            for k, i, c in (part.split(':') for part in NVP_MAT.split(',') if part)]
    player()._grant_items(rows)


NVP_REQ = {'6U5w20zk': [{'og2GHy49': '900000104', 'KCk8u0am': NVP_MAT, 'Knra4I19': '0'}]}
freeze_time()
try:
    fresh_player(); nvp_setup()
    out_orig = ORIG_NVP(None, NVP_REQ)
    state_orig = snapshot()
    fresh_player(); nvp_setup()
    out_wrap = nvp_handler(None, NVP_REQ)
    state_wrap = snapshot()
finally:
    thaw_time()
new_id = ((out_wrap.get('6U5w20zk') or [{}])[0].get('5u7VYNEX'))
check('NV+ success: really awakened', new_id not in (None, '', '900000104'), repr(new_id))
check('NV+ success: reply identical to the original', out_wrap == out_orig,
      '%r vs %r' % (out_wrap, out_orig))
check('NV+ success: state identical to the original', state_wrap == state_orig)

# --- 3a. fusion refusal: the client dropped the material, the answer gives it back -----------------
fresh_player()
add_unit('100000106', 900000105)
before = snapshot()
mix_req = {'f08du6EW': [{'og2GHy49': '999999999', 'WbGYcN17': '900000105'}]}
out = fp.serve_unit_mix(None, json.dumps(mix_req))
node = (out.get('f08du6EW') or [{}])[0]
check('mix unowned base: result node present', set(node) == MIX_KEYS, repr(sorted(node)))
check('mix unowned base: request echoed', node.get('og2GHy49') == '999999999'
      and node.get('WbGYcN17') == '900000105', repr(node))
check('mix unowned base: all zero fields',
      all(node.get(k) == '0' for k in ('7UR4J2SE', 'B6H34Mea', 'UDMIFB72', '1dT7ha9H', 'E90oBqct')),
      repr(node))
check('mix unowned base: material record returned',
      any(r.get('og2GHy49') == '900000105' for r in out.get('8gSkPD6b') or []),
      repr(out.get('8gSkPD6b'))[:200])
check_state('mix unowned base', before)
check_no_roster_replace('mix unowned base', out, 'UiSC9y8R')

# --- 3b. fusion refusal: no owned material at all --------------------------------------------------
fresh_player()
add_unit('100000106', 900000106)
before = snapshot()
mix_req = {'f08du6EW': [{'og2GHy49': '900000106', 'WbGYcN17': '999999999'}]}
out = fp.serve_unit_mix(None, json.dumps(mix_req))
node = (out.get('f08du6EW') or [{}])[0]
check('mix no material: result node present', set(node) == MIX_KEYS, repr(sorted(node)))
check('mix no material: body is not empty', bool(out), repr(out)[:200])
check('mix no material: empty record list, key present', out.get('8gSkPD6b') == [],
      repr(out.get('8gSkPD6b')))
check_state('mix no material', before)
check_no_roster_replace('mix no material', out, 'UiSC9y8R')

# --- 3c. fusion success: the wrapper changes nothing -----------------------------------------------
def mix_setup():
    add_unit('100000106', 900000107)
    add_unit('100000106', 900000108)


MIX_REQ = {'f08du6EW': [{'og2GHy49': '900000107', 'WbGYcN17': '900000108'}]}
freeze_time()
try:
    fresh_player(); mix_setup()
    out_orig = ORIG_MIX(None, json.dumps(MIX_REQ))
    state_orig = snapshot()
    fresh_player(); mix_setup()
    out_wrap = fp.serve_unit_mix(None, json.dumps(MIX_REQ))
    state_wrap = snapshot()
finally:
    thaw_time()
check('mix success: material consumed',
      player().roster_row('900000108') is None and player().roster_row('900000107') is not None,
      repr(player().data['roster']))
check('mix success: result node built by the engine',
      bool(out_wrap.get('f08du6EW')), repr(out_wrap.get('f08du6EW'))[:200])
check('mix success: reply identical to the original', out_wrap == out_orig,
      '%r vs %r' % (out_wrap, out_orig))
check('mix success: state identical to the original', state_wrap == state_orig)

# --- summary ---------------------------------------------------------------------------------------
failed = [name for name, ok, _ in RESULTS if not ok]
print('\n%d/%d passed' % (len(RESULTS) - len(failed), len(RESULTS)))
if failed:
    print('FAILED: ' + ', '.join(failed))
raise SystemExit(1 if failed else 0)

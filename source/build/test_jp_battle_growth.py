"""Tests for build/engine_overlay/jp_battle_growth.py.

Runs the engine modules in-process against the JP decoded masters and a fake live player.
Run:  python -I -X utf8 build/test_jp_battle_growth.py   (PYTHONIOENCODING=utf-8)
"""
import copy
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
import ffbe_battle as fb               # noqa: E402
import exvius_repeat                   # noqa: E402

if not os.path.isdir(MST):
    print('SKIP: JP masters not found at ' + MST)
    raise SystemExit(2)

ORIG_LV_HALF_5 = fb._lv_half(3, 120, [100, 20, 30, 25, 15, 18], 2, 45)
ORIG_CREDIT = fb._credit_mission_rewards

import jp_battle_growth as bg          # noqa: E402

RESULTS = []


class FakeRng:
    def __init__(self, values, pick=0):
        self._values = list(values)
        self._pick = pick

    def random(self):
        return self._values.pop(0) if self._values else 0.99

    def randrange(self, stop):
        return self._pick % stop


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + ((' -- ' + detail) if detail and not ok else ''))


def player():
    return ffbe_state.State.player


def fresh_player():
    ffbe_state.State.player = player_state.PlayerState(player_state.default_state(), mode='live')
    # Start with an empty party so tests control exact party members.
    ffbe_state.State.player.data['roster'] = []
    ffbe_state.State.player.data['party']['decks'][0]['members'] = []
    return ffbe_state.State.player


def set_party(*units):
    members = []
    for idx, u in enumerate(units):
        members.append({'slot': idx, 'instance_id': str(u['instance_id']), 'role': 'leader' if idx == 0 else 'member'})
    player().data['party']['decks'][0]['members'] = members


def add_unit(master_id, iid, level=1, tmr=None, stmr=None, lb_level=1, lb_exp=0):
    u = player().grant_unit(master_id, instance_id=iid)
    assert u is not None, master_id
    if level > 1:
        player().set_unit_level(iid, level)
    u['lb_level'] = lb_level
    u['lb_exp'] = lb_exp
    if tmr is not None or stmr is not None:
        u['affinity_points'] = [
            str(tmr) if tmr is not None else '',
            str(stmr) if stmr is not None else '',
        ]
    return u


# --- 1. install idempotency & _lv_half compatibility ------------------------------------------------
bg.install(None)
wrapped_credit = fb._credit_mission_rewards
wrapped_lv_half = fb._lv_half
bg.install(None)
check('install: idempotent', fb._credit_mission_rewards is wrapped_credit and fb._lv_half is wrapped_lv_half)
check(
    '_lv_half: 5-arg compatibility',
    fb._lv_half(3, 120, [100, 20, 30, 25, 15, 18], 2, 45) == ORIG_LV_HALF_5,
    repr(fb._lv_half(3, 120, [100, 20, 30, 25, 15, 18], 2, 45)),
)

# --- 2. lb_exp_for_mission & give_unit_lb -----------------------------------------------------------
normal_mission = player_state.mission_row('1110405')   # cost 15, waves 1
raid_mission = player_state.mission_row('7220101')     # subtype 2, cost kind 1, cost 1
eg_mission = player_state.mission_row('7860101')       # subtype 6

check('lb_exp normal: NRG * 100', bg.lb_exp_for_mission(normal_mission) == 1500, repr(bg.lb_exp_for_mission(normal_mission)))
check('lb_exp raid: orb * 250', bg.lb_exp_for_mission(raid_mission) == 250, repr(bg.lb_exp_for_mission(raid_mission)))
check('lb_exp equip grow: 125', bg.lb_exp_for_mission(eg_mission) == 125, repr(bg.lb_exp_for_mission(eg_mission)))
check('lb_exp None: 0', bg.lb_exp_for_mission(None) == 0)

fresh_player()
u_lb = add_unit('100000115', 910000001, lb_level=1, lb_exp=0)  # max_lb=20, step 2=1450
used = bg.give_unit_lb(u_lb, 1500)
check('give_unit_lb: used=1500', used == 1500, repr(used))
check('give_unit_lb: leveled 1->2 exp=50', u_lb['lb_level'] == 2 and u_lb['lb_exp'] == 50,
      repr((u_lb['lb_level'], u_lb['lb_exp'])))

# Cap at max_lb -> lb_exp must become 0 and overflow not used.
u_lb_cap = add_unit('100000115', 910000002, lb_level=19, lb_exp=0)
steps = bg._lb_steps(str(player_state.limit_burst('100000115')['PR2HIc71']))
need_20 = steps[20]
used_cap = bg.give_unit_lb(u_lb_cap, need_20 + 500)
check('give_unit_lb cap: used exact need', used_cap == need_20, repr((used_cap, need_20)))
check('give_unit_lb cap: max_lb=20, lb_exp=0', u_lb_cap['lb_level'] == 20 and u_lb_cap['lb_exp'] == 0,
      repr((u_lb_cap['lb_level'], u_lb_cap['lb_exp'])))
check('give_unit_lb already max: used=0', bg.give_unit_lb(u_lb_cap, 500) == 0 and u_lb_cap['lb_exp'] == 0)

# --- 3. gain_unit_trust -----------------------------------------------------------------------------
fresh_player()
u_tmr = add_unit('100000115', 910000010, tmr=0)  # ordinary unit, no STMR
add, rw = bg.gain_unit_trust(player(), u_tmr, rng=FakeRng([0.29]))
check('gain_unit_trust <0.30: +10 points', add == 10 and u_tmr['affinity_points'] == ['10', ''] and rw == [],
      repr((add, u_tmr['affinity_points'], rw)))

add, rw = bg.gain_unit_trust(player(), u_tmr, rng=FakeRng([0.30]))
check('gain_unit_trust >=0.30: no gain', add == 0 and u_tmr['affinity_points'] == ['10', ''] and rw == [],
      repr((add, u_tmr['affinity_points'], rw)))

u_full = add_unit('100000115', 910000011, tmr=1000)
add, rw = bg.gain_unit_trust(player(), u_full, rng=FakeRng([0.0]))
check('gain_unit_trust already 1000: no gain', add == 0 and u_full['affinity_points'] == ['1000', ''])

u_mog = add_unit('904000101', 910000012, tmr=0)
add, rw = bg.gain_unit_trust(player(), u_mog, rng=FakeRng([0.0]))
check('gain_unit_trust moogle: ignored', add == 0 and u_mog['affinity_points'] == ['0', ''])

# --- 4. TMR 100% reward grant once ------------------------------------------------------------------
fresh_player()
player().data.setdefault('inventory', {})['equipment'] = []
player().data.setdefault('inventory', {})['items'] = []
u_990 = add_unit('100000115', 910000020, tmr=990)  # TMR = 21:303002800:1
eq_before = sum(int(r.get('count', 0)) for r in player().data['inventory']['equipment'] if str(r.get('item_id')) == '303002800')
add, rw = bg.gain_unit_trust(player(), u_990, rng=FakeRng([0.10]))
eq_after = sum(int(r.get('count', 0)) for r in player().data['inventory']['equipment'] if str(r.get('item_id')) == '303002800')
check('TMR 990->1000: points & reward',
      add == 10 and u_990['affinity_points'] == ['1000', ''] and rw == [{'kind': 21, 'id': 303002800, 'count': 1}],
      repr((add, u_990['affinity_points'], rw)))
check('TMR 990->1000: equip credited', eq_after == eq_before + 1, repr((eq_before, eq_after)))
check('TMR 990->1000: claimed key saved', '0:21:303002800:1' in (u_990.get('affinity_reward_claimed') or []),
      repr(u_990.get('affinity_reward_claimed')))

# Even if points are manually dropped and re-reached, claimed prevents duplicate grant.
u_990['affinity_points'] = ['990', '']
add2, rw2 = bg.gain_unit_trust(player(), u_990, rng=FakeRng([0.10]))
eq_after2 = sum(int(r.get('count', 0)) for r in player().data['inventory']['equipment'] if str(r.get('item_id')) == '303002800')
check('TMR reclaim: no duplicate reward', add2 == 10 and rw2 == [] and eq_after2 == eq_after)

# Materia TMR (unit 100000317 -> 22:504204590:1)
u_mat = add_unit('100000317', 910000021, tmr=990, stmr=500)
mat_before = player().item_count(22, 504204590)
add_m, rw_m = bg.gain_unit_trust(player(), u_mat, rng=FakeRng([0.05]))
mat_after = player().item_count(22, 504204590)
check('Materia TMR 990->1000: credited & STMR kept',
      add_m == 10 and u_mat['affinity_points'] == ['1000', '500'] and mat_after == mat_before + 1 and len(rw_m) == 1,
      repr((add_m, u_mat['affinity_points'], mat_before, mat_after, rw_m)))

# --- 5. Trust bonus drop ----------------------------------------------------------------------------
fresh_player()
u_b0 = add_unit('100000115', 910000030, tmr=0)
u_b1 = add_unit('100000115', 910000031, tmr=1000)
u_b2 = add_unit('100000317', 910000032, tmr=1000)
check('party_bonus_chance 0%', bg.party_bonus_chance(player(), [u_b0]) == 0.0)
check('party_bonus_chance 1x100%', abs(bg.party_bonus_chance(player(), [u_b1]) - 0.10) < 1e-9)
check('party_bonus_chance 2x100%', abs(bg.party_bonus_chance(player(), [u_b0, u_b1, u_b2]) - 0.19) < 1e-9)

spec_drop = {'09HRWXDf': [{'xF9Sr1a6': '20:101000100:2'}]}
before_item = player().item_count(20, 101000100)
bonus_rw = bg.add_bonus_drop(player(), [u_b1], spec_drop, '20:101000100:2', rng=FakeRng([0.05], pick=0))
after_item = player().item_count(20, 101000100)
check('add_bonus_drop: item granted +2', bonus_rw == {'kind': 20, 'id': 101000100, 'count': 2} and after_item == before_item + 2,
      repr((bonus_rw, before_item, after_item)))
check('add_bonus_drop: 09HRWXDf doubled', spec_drop['09HRWXDf'][0]['xF9Sr1a6'] == '20:101000100:4',
      repr(spec_drop['09HRWXDf'][0]))

# --- 6. credit_mission_rewards integration (Qic38SuC, A90DrNfp, bonus drop, max-level) ------------
fresh_player()
u1 = add_unit('100000115', 910000040, level=1, tmr=20, lb_level=1, lb_exp=0)
u2 = add_unit('100000317', 910000041, level=120, tmr=1000, stmr=450, lb_level=1, lb_exp=0)  # max_lv=120
set_party(u1, u2)

# Mission 1110405: cost=15 -> LB EXP 1500.
# RNG sequence per MissionEnd:
#   u1 gain_unit_trust: 0.10 (< 0.30 -> +10 TMR: 20 -> 30)
#   u2 gain_unit_trust: skipped (already tmr=1000, no rng consumed)
#   add_bonus_drop:     0.05 (< 0.103 -> extra 20:101000100:1)
bg._RNG = FakeRng([0.10, 0.05], pick=0)
exvius_repeat.begin_attempt(player(), '1110405')
req_body = {
    'jQsE54Iz': [{'qo3PECw6': '1110405'}],
    '09HRWXDf': [{'S4U09svH': '200', 'Wdi3MAs2': '50', 'xF9Sr1a6': '20:101000100:1'}],
}
req_json = json.dumps(req_body)
base_reply = {'09HRWXDf': [{'Qic38SuC': '1000000001@fake', 'A90DrNfp': '1000000001:0', 'wuUakq71': '10'}]}
echoed = fb.mission_end_echo(copy.deepcopy(base_reply), req_json)
bag_before = player().item_count(20, 101000100)
reply = fb.credit_mission_rewards(req_json, echoed)
bag_after = player().item_count(20, 101000100)

res_row = reply['09HRWXDf'][0]
qic_parts = res_row.get('Qic38SuC', '').split(',')
check('integration: 2 Qic38SuC rows', len(qic_parts) == 2, repr(res_row.get('Qic38SuC')))

u1_key, u1_ba = qic_parts[0].split('@', 1)
u1_before, u1_after = [s.split(':') for s in u1_ba.split('_', 1)]
check('integration u1 key & field counts', u1_key == '910000040' and len(u1_before) == 15 and len(u1_after) == 15)
check('integration u1 TMR 20->30 (f9)', u1_before[9] == '20' and u1_after[9] == '30', repr((u1_before[9], u1_after[9])))
check('integration u1 LB 1:0->2:50 (f10,f11)',
      u1_before[10] == '1' and u1_before[11] == '0' and u1_after[10] == '2' and u1_after[11] == '50',
      repr((u1_before[10:12], u1_after[10:12])))
check('integration u1 gained exp 0->100 (f12)', u1_before[12] == '0' and u1_after[12] == '100',
      repr((u1_before[12], u1_after[12])))
check('integration u1 STMR 0 (f14)', u1_before[14] == '0' and u1_after[14] == '0')
check('integration u1 stmr empty string kept', u1['affinity_points'] == ['30', ''], repr(u1['affinity_points']))

u2_key, u2_ba = qic_parts[1].split('@', 1)
u2_before, u2_after = [s.split(':') for s in u2_ba.split('_', 1)]
check('integration u2 max-lv gained exp=0 (f12)', u2_key == '910000041' and u2_before[12] == '0' and u2_after[12] == '0',
      repr((u2_before[12], u2_after[12])))
check('integration u2 TMR 1000->1000, STMR 450 (f9,f14)',
      u2_before[9] == '1000' and u2_after[9] == '1000' and u2_before[14] == '450' and u2_after[14] == '450',
      repr((u2_before[9], u2_after[9], u2_before[14], u2_after[14])))

check('integration A90DrNfp', res_row.get('A90DrNfp') == '910000040:1500,910000041:1500',
      repr(res_row.get('A90DrNfp')))
check('integration bonus drop: bag +2 (1 normal + 1 bonus) & csv doubled',
      bag_after == bag_before + 2 and res_row.get('xF9Sr1a6') == '20:101000100:2',
      repr((bag_before, bag_after, res_row.get('xF9Sr1a6'))))
check('integration B71MekS8 present for projection', 'B71MekS8' in reply, repr(sorted(reply.keys())))

# Case B: zero unit EXP (S4U09svH=0), LB/TMR still write Qic38SuC & A90DrNfp with f12=0.
fresh_player()
u3 = add_unit('100000115', 910000050, level=1, tmr=0, lb_level=1, lb_exp=0)
set_party(u3)
bg._RNG = FakeRng([0.10])
exvius_repeat.begin_attempt(player(), '1110405')
req_zero_exp = json.dumps({
    'jQsE54Iz': [{'qo3PECw6': '1110405'}],
    '09HRWXDf': [{'S4U09svH': '0', 'Wdi3MAs2': '0'}],
})
reply0 = fb.credit_mission_rewards(req_zero_exp, {'09HRWXDf': [{}]})
row0 = reply0['09HRWXDf'][0]
u3_ba = row0.get('Qic38SuC', '@').split('@', 1)[1]
u3_b, u3_a = [s.split(':') for s in u3_ba.split('_', 1)]
check('zero-exp: Qic38SuC written with f12=0, f9 0->10, LB updated',
      u3_b[12] == '0' and u3_a[12] == '0' and u3_b[9] == '0' and u3_a[9] == '10' and u3_a[10] == '2',
      repr((u3_b[9:13], u3_a[9:13])))
check('zero-exp: A90DrNfp written', row0.get('A90DrNfp') == '910000050:1500', repr(row0.get('A90DrNfp')))

# --- 7. Duplicate MissionEnd guard (no new begin_attempt) -------------------------------------------
snap_before_dup = copy.deepcopy(player().data)
bg._RNG = FakeRng([0.0, 0.0])
reply_dup = fb.credit_mission_rewards(req_zero_exp, {'09HRWXDf': [{}]})
check('duplicate MissionEnd: state unchanged', player().data == snap_before_dup)
check('duplicate MissionEnd: no Qic38SuC added', 'Qic38SuC' not in reply_dup['09HRWXDf'][0], repr(reply_dup))

# --- summary ----------------------------------------------------------------------------------------
failed = [name for name, ok, _ in RESULTS if not ok]
print('\n%d/%d passed' % (len(RESULTS) - len(failed), len(RESULTS)))
if failed:
    print('FAILED: ' + ', '.join(failed))
raise SystemExit(1 if failed else 0)

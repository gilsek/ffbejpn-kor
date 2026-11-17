"""Post-battle LB EXP, Trust Mastery (TMR), and Trust Bonus drop for JP 11.0.0.

Installed by jp_compat.install(server). Rules mirror lapis-server's battle_growth.py / nv_ex.py
and libgame.so's ResultUnitExpScene / UserUnitLvInfo::setupParams:
  * LB EXP per battle: NRG * 100 (raid orbs * 250, Item World floors * 125).
  * Trust (TMR): 30% chance per cleared battle for each ordinary party unit to gain 1%
    (need // 100, i.e. 10 of 1000). Reaching 100% grants the TMR reward once.
  * Trust bonus drop: independent per-unit probability of (tmr / need) * 10% for an extra
    copy of one battle drop (kinds 20/21/22), credited to inventory and added to 09HRWXDf.
  * Result screen fields:
      - Qic38SuC: 15-field before/after unit stats with field 9 = TMR, 10 = LbLv,
        11 = LbExp, 12 = gained EXP (0 if unchanged), 14 = STMR.
      - A90DrNfp: "<userUnitId>:<lbExpUsed>,..." read by ResultUnitExpScene::setLbExp.

The upstream engine (ffbe_offline_modfix) is not edited; install() wraps
ffbe_battle._lv_half and ffbe_battle._credit_mission_rewards in place.
"""
from __future__ import annotations

import json
import random

LB_PER_NRG = 100
LB_PER_RAID_ORB = 250
LB_PER_EG_ORB = 125
EG_FLOOR_COST = 1

TRUST_CHANCE = 0.30
TRUST_PERCENT = 1
BONUS_AT_FULL = 0.10

_RNG = random
_LB_TABLE: dict[str, dict[int, int]] | None = None
_installed = False


def _lb_steps(lb_id: str) -> dict[int, int]:
    """Load and cache F_LIMITBURST_LV_MST as {lb_id: {level: exp_needed}}."""
    global _LB_TABLE
    if _LB_TABLE is None:
        import player_state as ps
        table: dict[str, dict[int, int]] = {}
        rows = ps._load_ndjson('F_LIMITBURST_LV_MST.ndjson').get('__rows__', [])
        for r in rows:
            if not isinstance(r, dict):
                continue
            lid = str(r.get('PR2HIc71') or '')
            lv_raw = str(r.get('7wV3QZ80') or '')
            need_raw = str(r.get('T3Zcf40Q') or '')
            if lid and lv_raw.isdigit() and need_raw.isdigit():
                table.setdefault(lid, {})[int(lv_raw)] = int(need_raw)
        _LB_TABLE = table
    return _LB_TABLE.get(str(lb_id), {})


def lb_exp_for_mission(mission: dict | None) -> int:
    """Return the LB EXP each party unit earns for clearing `mission`."""
    if not isinstance(mission, dict) or not mission:
        return 0
    raw_cost = str(mission.get('B6kyCQ9M') or '0')
    cost = int(raw_cost) if raw_cost.isdigit() else 0
    subtype = str(mission.get('gQR24kST') or '0')
    cost_kind = str(mission.get('CQN15Hgr') or '0')
    if subtype == '2' and cost_kind == '1':
        return cost * LB_PER_RAID_ORB
    if subtype == '6':
        return EG_FLOOR_COST * LB_PER_EG_ORB
    return cost * LB_PER_NRG


def give_unit_lb(unit: dict, amount: int) -> int:
    """Credit up to `amount` LB EXP to `unit`, respecting max LB level. Returns EXP used."""
    if not isinstance(unit, dict) or int(amount or 0) <= 0:
        return 0
    import player_state as ps
    lb = ps.limit_burst(unit['master_id'])
    master = ps.unit_mst(unit['master_id']) or {}
    if not lb:
        return 0
    steps = _lb_steps(str(lb.get('PR2HIc71') or ''))
    if not steps:
        return 0
    max_lb = min(max(steps), int(master.get('ENwn42DV') or 1))
    lv = max(1, int(unit.get('lb_level') or 1))
    exp = int(unit.get('lb_exp') or 0)
    left = int(amount)
    used = 0
    while left > 0 and lv < max_lb and steps.get(lv + 1, 0) > 0:
        need = steps[lv + 1]
        step = max(0, min(left, need - exp))
        exp += step
        left -= step
        used += step
        if exp >= need:
            lv += 1
            exp = 0
    if used > 0:
        unit['lb_level'] = lv
        unit['lb_exp'] = exp
    return used


def gain_unit_trust(player, unit: dict, rng=None) -> tuple[int, list[dict]]:
    """With TRUST_CHANCE, add TRUST_PERCENT% TMR to an ordinary unit and grant its TMR item once."""
    if player is None or not isinstance(unit, dict):
        return 0, []
    rng = rng or _RNG
    import player_state as ps
    master = ps.unit_mst(unit['master_id']) or {}
    if int(master.get('rUnq35N9') or 0) != 0:
        return 0, []
    target, _ = player._unit_trust_info(unit, 0)
    if not target or target[0] in (70, 71) or target[3] <= 0:
        return 0, []
    raw_points = list(unit.get('affinity_points') or []) + ['', '']
    have = int(raw_points[0]) if str(raw_points[0]).isdigit() else 0
    need = int(target[3])
    if have >= need or rng.random() >= TRUST_CHANCE:
        return 0, []
    step = max(1, need * TRUST_PERCENT // 100)
    new_tmr = min(need, have + step)
    stmr_raw = str(raw_points[1]) if len(raw_points) > 1 and str(raw_points[1]).isdigit() else ''
    unit['affinity_points'] = [str(new_tmr), stmr_raw]

    claimed = list(unit.get('affinity_reward_claimed') or [])
    key = f'0:{target[0]}:{target[1]}:{target[2]}'
    granted: list[dict] = []
    if have < need <= new_tmr and key not in claimed and target[0] in (20, 21, 22):
        reward = {'kind': int(target[0]), 'id': int(target[1]), 'count': int(target[2])}
        if player._can_credit(reward) and player._grant_items([reward]) == [reward]:
            claimed.append(key)
            unit['affinity_reward_claimed'] = claimed
            granted.append(reward)
    return new_tmr - have, granted


def party_bonus_chance(player, party_units: list[dict]) -> float:
    """Combined probability that at least one party unit triggers a trust bonus drop."""
    if player is None:
        return 0.0
    none_prob = 1.0
    for unit in party_units:
        if not isinstance(unit, dict):
            continue
        target, _ = player._unit_trust_info(unit, 0)
        if not target or target[0] in (70, 71) or target[3] <= 0:
            continue
        raw = (list(unit.get('affinity_points') or []) + [''])[0]
        tmr = int(raw) if str(raw).isdigit() else 0
        none_prob *= 1.0 - min(1.0, tmr / target[3]) * BONUS_AT_FULL
    return 1.0 - none_prob


def _parse_bonus_choices(drops_csv: str) -> list[tuple[int, int, int]]:
    totals: dict[tuple[int, int], int] = {}
    order: list[tuple[int, int]] = []
    for entry in str(drops_csv or '').split(','):
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(':')]
        if len(parts) < 3 or not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()):
            continue
        kind, item_id, count = int(parts[0]), int(parts[1]), int(parts[2])
        if kind not in (20, 21, 22) or count <= 0:
            continue
        key = (kind, item_id)
        if key not in totals:
            order.append(key)
        totals[key] = totals.get(key, 0) + count
    return [(kind, item_id, totals[(kind, item_id)]) for kind, item_id in order]


def add_bonus_drop(player, party_units: list[dict], spec: dict, drops_csv: str, rng=None) -> dict | None:
    """Roll for an extra copy of one battle drop and reflect it in both inventory and 09HRWXDf."""
    if player is None or not isinstance(spec, dict):
        return None
    rng = rng or _RNG
    choices = _parse_bonus_choices(drops_csv)
    chance = party_bonus_chance(player, party_units)
    if not choices or chance <= 0 or rng.random() >= chance:
        return None
    kind, item_id, count = choices[rng.randrange(len(choices))]
    reward = {'kind': kind, 'id': item_id, 'count': count}
    if not player._can_credit(reward) or player._grant_items([reward]) != [reward]:
        return None
    import ffbe_battle as fb
    token = fb.TYPED_RESULT_DROPS.get(str(kind), fb.RESULT_DROP_TOKEN)
    for row in spec.get(fb.RESULT_TAG, []):
        if not isinstance(row, dict):
            continue
        existing = [e for e in str(row.get(token) or '').split(',') if e]
        updated = []
        bumped = False
        for entry in existing:
            parts = entry.split(':')
            if (
                not bumped
                and len(parts) >= 3
                and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()
                and int(parts[0]) == kind and int(parts[1]) == item_id
            ):
                parts[2] = str(int(parts[2]) + count)
                updated.append(':'.join(parts))
                bumped = True
            else:
                updated.append(entry)
        if not bumped:
            updated.append(f'{kind}:{item_id}:{count}')
        row[token] = ','.join(updated)
    return reward


def _unit_trust_points(unit: dict) -> tuple[int, int]:
    pts = list(unit.get('affinity_points') or []) + ['', '']
    tmr = int(pts[0]) if str(pts[0]).isdigit() else 0
    stmr = int(pts[1]) if len(pts) > 1 and str(pts[1]).isdigit() else 0
    return tmr, stmr


def _lv_half(level, exp, stats, lb_level, lb_exp, tmr=0, stmr=0, gained=None) -> str:
    """15-field Qic38SuC half compatible with 5-arg callers; exposes TMR (9) and STMR (14)."""
    gained_val = exp if gained is None else gained
    fields = [str(level), '0', str(exp)]
    fields += [f'{int(s)}-0-0-0' for s in stats]
    fields += [str(tmr), str(lb_level), str(lb_exp), str(gained_val), '0', str(stmr)]
    assert len(fields) == 15, len(fields)
    return ':'.join(fields)


def _drops_csv_for_bonus(fb, ps, resolved_mid: str, plaintext: str, src: dict) -> str:
    if resolved_mid in fb.ENLIGHTENMENT_DROPS:
        cleared = fb.mission_result_from(plaintext).get('cleared') is True
        return fb.ENLIGHTENMENT_DROPS[resolved_mid] if cleared else ''
    if resolved_mid in fb.CAPTURE_MISSIONS:
        return ''
    if int(fb.mission_wave_count(resolved_mid) or 0) <= 0:
        return ''
    return fb._reported_drops(src)


def _snapshot_party(player, party_ids: list[str]) -> dict[str, dict]:
    snap: dict[str, dict] = {}
    for iid in party_ids:
        u = player.roster_row(iid)
        if u is None:
            continue
        tmr0, stmr0 = _unit_trust_points(u)
        snap[iid] = {
            'master_id': u['master_id'],
            'level': int(u.get('level', 1)),
            'exp': int(u.get('exp', 0)),
            'tmr': tmr0,
            'stmr': stmr0,
            'lb_level': int(u.get('lb_level', 0) or 0),
            'lb_exp': int(u.get('lb_exp', 0) or 0),
        }
    return snap


def install(server=None):
    """Wrap ffbe_battle._lv_half and ffbe_battle._credit_mission_rewards."""
    global _installed
    if _installed:
        return
    import ffbe_battle as fb
    import player_state as ps

    fb._lv_half = _lv_half
    original_credit = fb._credit_mission_rewards

    def _credit_mission_rewards(plaintext: str | None, spec=None, mid=None):
        player = fb.State.player
        if player is None or player.mode == 'frozen' or not plaintext:
            return original_credit(plaintext, spec, mid)

        resolved_mid = str(mid or fb.mission_id_from(plaintext) or '')
        party_ids = player.party_instance_ids(resolved_mid or None)
        before_snap = _snapshot_party(player, party_ids)

        out = original_credit(plaintext, spec, mid)
        if not isinstance(out, dict) or fb.RESULT_TAG not in out:
            return out

        try:
            req = json.JSONDecoder().raw_decode(plaintext)[0]
        except Exception:  # noqa: BLE001
            return out
        rows = req.get(fb.RESULT_TAG) if isinstance(req, dict) else None
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return out
        src = rows[0]

        mission = ps.mission_row(resolved_mid) or {}
        lb_amount = lb_exp_for_mission(mission)
        uexp = src.get('S4U09svH')
        exp_gain = fb.per_unit_exp(uexp)[0] if uexp is not None and str(uexp).isdigit() and int(uexp) > 0 else 0

        party_units: list[dict] = []
        lb_used_by_iid: dict[str, int] = {}
        active_iids: list[str] = []
        lv_rows: list[str] = []
        tmr_gained_any = False
        changed = False

        for iid in party_ids:
            u = player.roster_row(iid)
            b = before_snap.get(iid)
            if u is None or b is None:
                continue
            party_units.append(u)
            active_iids.append(iid)

            lb_used = give_unit_lb(u, lb_amount)
            if lb_used > 0:
                lb_used_by_iid[iid] = lb_used
                changed = True

            tmr_add, tmr_rewards = gain_unit_trust(player, u, rng=_RNG)
            if tmr_add > 0:
                tmr_gained_any = True
                changed = True
            if tmr_rewards:
                changed = True

            a_lv, a_exp = int(u.get('level', 1)), int(u.get('exp', 0))
            a_lbl, a_lbe = int(u.get('lb_level', 0) or 0), int(u.get('lb_exp', 0) or 0)
            a_tmr, a_stmr = _unit_trust_points(u)
            unit_exp_gained = exp_gain if (b['level'], b['exp']) != (a_lv, a_exp) else 0
            before_str = _lv_half(
                b['level'], b['exp'], ps.unit_stats(b['master_id'], b['level']),
                b['lb_level'], b['lb_exp'], tmr=b['tmr'], stmr=b['stmr'], gained=0,
            )
            after_str = _lv_half(
                a_lv, a_exp, ps.unit_stats(u['master_id'], a_lv),
                a_lbl, a_lbe, tmr=a_tmr, stmr=a_stmr, gained=unit_exp_gained,
            )
            lv_rows.append(f'{iid}@{before_str}_{after_str}')

        drops_csv = _drops_csv_for_bonus(fb, ps, resolved_mid, plaintext, src)
        bonus_drop = add_bonus_drop(player, party_units, out, drops_csv, rng=_RNG) if drops_csv else None
        if bonus_drop is not None:
            changed = True

        if lv_rows:
            qic = ','.join(lv_rows)
            a90 = ','.join(f'{iid}:{lb_used_by_iid.get(iid, 0)}' for iid in active_iids)
            has_growth = bool(exp_gain > 0 or lb_used_by_iid or tmr_gained_any)
            for row in out.get(fb.RESULT_TAG, []):
                if not isinstance(row, dict):
                    continue
                if has_growth or 'Qic38SuC' in row:
                    row['Qic38SuC'] = qic
                if has_growth or 'A90DrNfp' in row:
                    row['A90DrNfp'] = a90

        if changed:
            player.dirty = True
            out.setdefault('B71MekS8', [])

        return out

    fb._credit_mission_rewards = _credit_mission_rewards
    _installed = True
    print('JP battle growth: post-battle LB EXP, TMR (+1% @ 30%), trust bonus drop installed', flush=True)

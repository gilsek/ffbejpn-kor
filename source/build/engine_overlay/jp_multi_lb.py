"""JP units with several Limit Bursts (2026-11-17).

JP F_UNIT_MST `PR2HIc71` (the unit's LB id) is a CSV for 94 units (NV forms: e.g. 100044707 ->
"100044700,100044701,100044702"). The engine's player_state.limit_burst() looks the whole string up in
F_LIMITBURST_MST, finds nothing, and every such unit is served `lb_level = 0`. Level 0 has no
F_LIMITBURST_LV_MST row, and BattleCharacter::reserveLimitBurstAction dereferences that null lookup
unguarded: the client crashed the moment such a unit's LB was activated (tablet 2026-11-17 16:22:13,
TFA mission 1110301, SIGSEGV at NULL+0x28 -- the same signature the engine documents for lb_level 0).

Every id in those CSVs has its own F_LIMITBURST_MST row and level rows from 1, so the first id stands
for the unit: the engine's level/exp bookkeeping uses that row, and the client reads the level for
whichever id it activates. The engine (ffbe_offline_modfix upstream) is NOT edited; install() replaces
player_state.limit_burst and the copies other modules imported by name, and repairs a roster that was
already written with level 0.
"""

_installed = False


def _repair(data):
    import player_state as ps
    fixed = []
    for unit in (data or {}).get('roster') or []:
        if int(unit.get('lb_level') or 0) < 1 and ps.limit_burst(unit.get('master_id')):
            unit['lb_level'] = 1
            fixed.append(str(unit.get('instance_id')))
    return fixed


def install(server):
    import sys
    import player_state as ps
    from ffbe_state import State

    global _installed
    if _installed:
        return
    _installed = True

    original = ps.limit_burst

    def limit_burst(master_id):
        row = original(master_id)
        if row is not None:
            return row
        lb_id = str((ps.unit_mst(str(master_id)) or {}).get(ps.LB_KEY) or '')
        if ',' not in lb_id:
            return None
        table = ps._load_ndjson('F_LIMITBURST_MST.ndjson', ps.LB_KEY)
        for part in lb_id.split(','):
            row = table.get(part.strip())
            if row is not None:
                return row
        return None

    ps.limit_burst = limit_burst
    for name in ('exvius_arena', 'ffbe_friends'):      # modules that imported the function by name
        module = sys.modules.get(name)
        if module is None:
            try:
                module = __import__(name)
            except Exception:  # noqa: BLE001 - an optional module must not block the fix
                module = None
        if module is not None and getattr(module, 'limit_burst', None) is original:
            module.limit_burst = limit_burst

    # A state loaded later goes through the engine's own _normalise repair (now with the fixed lookup);
    # one that is already loaded is repaired here.
    fixed = []
    player = State.player
    if player is not None and isinstance(getattr(player, 'data', None), dict):
        fixed = _repair(player.data)
        if fixed:
            player.dirty = True
    print('JP multi-LB: CSV limit-burst ids resolved by their first id; repaired lb_level on %d unit(s)%s'
          % (len(fixed), ': ' + ','.join(fixed) if fixed else ''), flush=True)

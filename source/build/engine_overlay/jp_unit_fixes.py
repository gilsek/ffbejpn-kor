"""JP-only unit fixes, installed from jp_compat.install(): unit conversion (convert / 変身), EX
awakening's no-change success, and the unit warehouse (storage move + rename).

Rules taken from the JP offline server (build/out/lapis_audit/cmp/lapis_full/lapis/server):
  * handlers/nv.py + sacrifice.py + nv_keys.py -- conversion rewards by exeType, the five-field
    SacrificeResponse node, and EX awakening's Unitchanged answer.
  * handlers/storage.py + storage_keys.py -- the warehouse answer carries the moved unit records;
    the rename request is answered with the same node it sent and the name is kept on the account.

The engine (ffbe_offline_modfix upstream) is NOT edited. install(server) swaps handlers:
  * exvius_actions.HANDLERS['7tWdn9zH' / 'x94MnujU']  unit conversion
  * exvius_actions_shops.HANDLERS['k6NI9Tm1']         EX awakening (wraps the engine handler)
  * ffbe_player / ffbe_pipeline .serve_unit_storage   warehouse move (wraps the engine step)
  * exvius_actions.HANDLERS['1ghJ8WpG']               warehouse rename (engine has no handler)
"""

SACRIFICE_REQUEST = '7tWdn9zH'
NV_SACRIFICE_REQUEST = 'x94MnujU'
SAC_TAG = '6kvFj2Kw'
NV_SAC_TAG = '4Ncra9DF'

SAC_UNIT = 'og2GHy49'        # setUserUnitID
SAC_EXE = 'ijEey5f7'         # exeType
SAC_SHINE_ITEM = 'tL6G9egd'  # setItemId: the 輝源 item (exeType 0 only)
SAC_ITEMS = '1swM3H4T'       # setItemInfo: what was granted, "20:<item>:<count>,..."
SAC_MOOGLE = 'T85HmdKB'      # setMoguUserUnitId: a granted moogle ("" = none)

SM_KEY = 'woghJa61'
SM_MIN_RARITY = 'jBVop84T'
SM_SHINE = 'tL6G9egd'
SM_PIECES = '1swM3H4T'
SM_PIECES_OTHER = 'q1PJQ3eE'

UM_ID = '3HriTp6B'
UM_SERIES = 'woghJa61'
UM_RARITY = '9fW0TePj'
UM_NV_TYPE = '5Mgpv8hJ'
UM_NV_SUBLIMATION = 'k9GFaWm1'
NV_TYPES = ('1', '2')

EXE_SHINE = 0
EXE_PIECE = 1
SHINE_RARITIES = ('5', '6')

EX_TAG = '14vWb7kX'
EX_UNIT = 'og2GHy49'
EX_ELEMS = 'KCk8u0am'
EX_DISCOUNT = 'Knra4I19'
EX_LV_INFO = 'Qic38SuC'

STORAGE_REQUEST = '5ik69cuw'
STORAGE_TAG = 'JMxPV87y'
STORAGE_NUMBER = 'km9gKXJ5'
STORAGE_IDS = 'ng9xPNt8'

NAME_REQUEST = '1ghJ8WpG'
NAME_TAG = 'n0uA2hzR'
NAME_USER = '9Tbns0eI'
NAME_FIELD = 'G4L0YIB2'
NAME_NUMBER = 'QHFU1k43'      # the warehouse number in the unit record / rename node
NAME_MAX = 40
STORAGE_NAMES_KEY = 'unit_storage_names'
UNIT_ADD_TAG = '8gSkPD6b'    # UserUnitInfoList updateObject (incremental unit records)


def _num(value, default=None):
    text = str(value if value is not None else '')
    return int(text) if text.isascii() and text.isdigit() else default


def _csv_ids(raw):
    if not isinstance(raw, str):
        return []
    return [part.strip() for part in raw.split(',') if part.strip().isdigit()]


def _reward_rows(items_text):
    """'20:<item>:<count>,...' -> [{'kind':20,'id':...,'count':...}] (engine reward rows)."""
    rows = []
    for entry in str(items_text or '').split(','):
        parts = [p.strip() for p in entry.split(':')]
        if len(parts) == 3 and all(p.isdigit() for p in parts) and int(parts[2]) > 0:
            rows.append({'kind': int(parts[0]), 'id': int(parts[1]), 'count': int(parts[2])})
    return rows


def _items_text(rows):
    return ','.join('%d:%d:%d' % (row['kind'], row['id'], row['count']) for row in rows)


def _is_nv(master):
    return str((master or {}).get(UM_NV_TYPE, '0')) in NV_TYPES


def _pure_nv(master):
    """UnitInfoBase::isPureNeoVision: an NV that was not sublimated from a ★7."""
    return _is_nv(master) and str((master or {}).get(UM_NV_SUBLIMATION, '0')) != '1'


def _request_tag(master, exe):
    """The group the client sends the conversion in (SACRIFICE for 輝源 and pure-NV 欠片)."""
    return SAC_TAG if exe == EXE_SHINE or _pure_nv(master) else NV_SAC_TAG


def _plan(master, exe, rows):
    """What converting `master` with `exe` grants, or None when it cannot be converted that way."""
    if not master:
        return None
    rarity = _num(master.get(UM_RARITY), 0)
    if exe == EXE_SHINE:
        row = rows.get(str(master.get(UM_SERIES)))
        if (row is None or _is_nv(master) or str(rarity) not in SHINE_RARITIES
                or rarity < _num(row.get(SM_MIN_RARITY), 0) or not _num(row.get(SM_SHINE), 0)):
            return None
        return [{'kind': 20, 'id': int(row[SM_SHINE]), 'count': 1}]
    if exe != EXE_PIECE:
        return None
    pure = _pure_nv(master)
    row = rows.get(str(master.get(UM_SERIES) if pure else master.get(UM_ID)))
    if row is None or rarity < _num(row.get(SM_MIN_RARITY), 0):
        return None
    return _reward_rows(row.get(SM_PIECES if pure else SM_PIECES_OTHER))


def _note(message):
    from ffbe_state import _note
    _note(message)


def _unit_lv_half(unit):
    """One 15-field Qic38SuC half from a roster row (the same builder the EX success path uses)."""
    from ffbe_battle import _lv_half
    from player_state import owned_unit_stats
    if unit is None:
        return _lv_half(1, 0, [0] * 6, 1, 0)
    return _lv_half(int(unit.get('level') or 1), int(unit.get('exp') or 0),
                    owned_unit_stats(unit), int(unit.get('lb_level') or 1),
                    int(unit.get('lb_exp') or 0))


def install(server):
    import exvius_actions as ea
    import exvius_actions_shops as sh
    import ffbe_player as fp
    import ffbe_pipeline as pl
    from ffbe_state import State
    from player_state import unit_mst

    # --- 1. unit conversion (SacrificeRequest / NvSacrificeRequest) ---------------------------------
    def sacrifice(spec, req, tag=SAC_TAG):
        player = State.player
        nodes = req.get(tag) if isinstance(req, dict) else None
        if player is None or player.mode == 'frozen' or not isinstance(nodes, list) or not nodes:
            return spec
        rows = ea._mst('F_SACRIFICE_MST.ndjson', SM_KEY)
        deployed = sh.deployed_unit_ids(player)
        ids, rewards, result = set(), [], []
        for node in nodes:
            iid = str(node.get(SAC_UNIT, '')) if isinstance(node, dict) else ''
            unit = player.roster_row(iid)
            exe = _num(node.get(SAC_EXE)) if isinstance(node, dict) else None
            master = unit_mst(unit['master_id']) if unit else None
            if (unit is None or iid in ids or iid in deployed or unit.get('favourite')
                    or exe not in (EXE_SHINE, EXE_PIECE)):
                return ea._refresh(spec)
            plan = _plan(master, exe, rows)
            # The client chooses the request by the same rule; a unit sent in the wrong group is refused.
            # An empty plan would consume the unit for nothing, so it is refused too.
            if not plan or _request_tag(master, exe) != tag:
                return ea._refresh(spec)
            if any(not player._can_credit(reward) for reward in plan):
                return ea._refresh(spec)
            ids.add(iid)
            rewards.extend(plan)
            result.append({SAC_UNIT: iid, SAC_EXE: str(exe),
                           SAC_SHINE_ITEM: str(plan[0]['id']) if exe == EXE_SHINE else '0',
                           SAC_ITEMS: _items_text(plan),
                           SAC_MOOGLE: ''})
        if len(ids) >= len(player.data['roster']):
            return ea._refresh(spec)
        player.drop_units(ids)
        player._grant_items(rewards)
        out = ea._refresh(spec)
        out[tag] = result
        _note('unit-convert: granted rewards for %d unit(s) (exeType per unit)' % len(ids))
        return out

    def nv_sacrifice(spec, req):
        return sacrifice(spec, req, NV_SAC_TAG)

    ea.HANDLERS[SACRIFICE_REQUEST] = sacrifice
    ea.HANDLERS[NV_SACRIFICE_REQUEST] = nv_sacrifice

    # The conversion scene keeps the selected units and removes them itself (GameUtils::removeUserUnit, lapis
    # handlers/nv.py). The engine's full-roster projection (B71MekS8 replaces UserUnitInfoList) freed those
    # objects under the scene -> SIGSEGV jumping into libgame data (device 2026-11-16 10:43 and 15:08, both
    # right after "unit-convert: granted"). Same cause as the engine's own 68RQ9GwN / Q7jV6pno exceptions:
    # answer the conversion with the result list and item counts only, no unit or deck groups.
    import player_state as ps
    original_apply = ps.PlayerState.apply_to_reply

    def apply_to_reply(self, spec, reply_id=None):
        if str(reply_id) in (SACRIFICE_REQUEST, NV_SACRIFICE_REQUEST) and isinstance(spec, dict):
            groups = self.groups()
            out = {tag: rows for tag, rows in spec.items() if tag not in groups}
            out.pop(ea.UNIT_GROUP, None)
            out['0dNXQa3R'] = groups['0dNXQa3R']
            # lapis also sends the granted items through UserItemInfo's add/update group (4pYnBMw7) with their new
            # counts; the result screen showed no items with the full list alone (user, 2026-11-16 15:16).
            granted = set()
            for node in (spec.get(SAC_TAG) or []) + (spec.get(NV_SAC_TAG) or []):
                granted.update(str(r['id']) for r in _reward_rows(node.get(SAC_ITEMS)))
            counts = {str(r.get('tL6G9egd')): r.get('Qy5EvcK1') for r in groups['0dNXQa3R'] if isinstance(r, dict)}
            if granted:
                out['4pYnBMw7'] = [{'tL6G9egd': iid, 'Qy5EvcK1': str(counts.get(iid, '0'))} for iid in sorted(granted)]
            return out
        return original_apply(self, spec, reply_id)
    ps.PlayerState.apply_to_reply = apply_to_reply

    # --- 2. EX awakening: a refusal must still name the unit (the effect scene dereferences it) ------
    original_ex = sh.HANDLERS.get('k6NI9Tm1')

    def unit_ex_class_up(spec, req):
        out = original_ex(spec, req) if original_ex else spec
        node = ea._node(req, EX_TAG) or {}
        sent_id = str(node.get(EX_UNIT, ''))
        if not isinstance(out, dict):
            return out
        if out.get(EX_TAG):
            return out                    # the engine changed something and built its own answer
        out = dict(out)
        half = _unit_lv_half(State.player.roster_row(sent_id) if State.player else None)
        out[EX_TAG] = [{EX_UNIT: sent_id, EX_ELEMS: str(node.get(EX_ELEMS, '')),
                        EX_DISCOUNT: '0',
                        EX_LV_INFO: str(sent_id) + '@' + half + '_' + half}]
        _note('unit-ex-class-up: refusal/no-change answered with the unchanged unit node')
        return out

    sh.HANDLERS['k6NI9Tm1'] = unit_ex_class_up
    ea.HANDLERS['k6NI9Tm1'] = unit_ex_class_up
    sh.unit_ex_class_up = unit_ex_class_up

    # --- 3a. warehouse move: the JP client does not apply the move itself ---------------------------
    original_storage = fp.serve_unit_storage

    def unit_storage_update(spec, plaintext):
        out = original_storage(spec, plaintext)
        req = ea._request(plaintext)
        node = (req.get(STORAGE_TAG) or [None])[0] if isinstance(req, dict) else None
        ids = _csv_ids(node.get(STORAGE_IDS)) if isinstance(node, dict) else []
        if not ids or State.player is None or not isinstance(out, dict):
            return out
        records = [row for row in State.player._unit_rows() if str(row.get('og2GHy49')) in ids]
        if not records:
            return out
        out = dict(out)
        out[UNIT_ADD_TAG] = records
        _note('unit-storage: response carries %d moved unit record(s)' % len(records))
        return out

    fp.serve_unit_storage = unit_storage_update
    pl.serve_unit_storage = unit_storage_update

    # --- 3b. warehouse rename: the engine has no handler for this request --------------------------
    def unit_storage_rename(spec, req):
        player = State.player
        node = ea._node(req, NAME_TAG) or {}
        number = _num(node.get(NAME_NUMBER))
        name = node.get(NAME_FIELD)
        if (player is None or player.mode == 'frozen' or number is None or number < 1
                or not isinstance(name, str)):
            return ea._refresh(spec)
        name = name.strip()[:NAME_MAX]
        names = dict(player.data.get(STORAGE_NAMES_KEY) or {})
        names[str(number)] = name
        if names != player.data.get(STORAGE_NAMES_KEY, {}):
            player.data[STORAGE_NAMES_KEY] = names
            player.dirty = True
        out = ea._refresh(spec)
        out[NAME_TAG] = [{NAME_USER: str(player.data['identity']['user_id']),
                          NAME_NUMBER: str(number), NAME_FIELD: name}]
        _note('unit-storage: warehouse %d renamed' % number)
        return out

    ea.HANDLERS[NAME_REQUEST] = unit_storage_rename
    print('JP unit fixes: conversion (exeType rules, five-key node), EX unchanged answer, '
          'warehouse records + rename', flush=True)

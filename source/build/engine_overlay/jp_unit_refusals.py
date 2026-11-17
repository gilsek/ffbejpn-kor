"""JP-only safe refusal answers for the awakening (★ / NV / NV+) and fusion (UnitMix) requests,
installed from jp_compat.install() alongside jp_unit_fixes.

Rules taken from the JP offline server (build/out/lapis_audit/cmp/lapis_full/lapis/server):
  * handlers/unit.py:459 _refused_safely -- an awakening refusal must still carry the result node:
    UnitEnhanceClassUpConnectScene::updateEvent runs the result scene whatever the answer, and it
    crashed on a missing new unit (L gate 2026-10-14). The node names NO unit to remove
    (og2GHy49 = ""), keeps the requested unit as the "new" one (5u7VYNEX), and the account's record
    for that unit rides in the incremental group (8gSkPD6b) when the unit exists (unit.py:468-473).
    The empty old id is what the client hook keys on to skip the scene (jp_stage20.js
    classUpConnectEnd), so only that shape keeps a refused awakening from the old crash.
  * handlers/unit.py:312 _restore -- the client takes every material of a fusion out of its own unit
    list BEFORE it asks (UnitMixAutoSelectConnectScene::removeElemUnitInfo, from initialize), so a
    refusal that does not give them back leaves them gone on the screen until the game is restarted
    (tester report 2026-11-04). L answers a refused fusion with those records in 8gSkPD6b and with
    the MessageState error -- M's envelope has NO MessageState field, so M answers with the same
    "nothing changed" result node its success path reads (no Qic38SuC: unit_mix_keys MIX_LV_INFO is
    only sent when a level changed, handlers/unit.py:302).

The engine (ffbe_offline_modfix upstream) is NOT edited. install(server) wraps:
  * exvius_actions.HANDLERS['zf49XKg8']             UnitClassUpRequest   (★, tag sWc7EH69)
  * exvius_actions[_shops].HANDLERS['Pf5C8xjJ']      UnitNvClassUpRequest (tag 6U5w20zk)
  * exvius_actions[_shops].HANDLERS['V8GtMQ2q']      UnitNvpClassUpRequest(tag 6U5w20zk)
  * ffbe_player / ffbe_pipeline .serve_unit_mix      UnitMixRequest       (tag f08du6EW)

A wrapper only fills what the engine left out: a reply that already carries its result tag is
returned untouched, and NO refusal of ★ / UnitMix adds a player group -- a full B71MekS8 roster
replacement is what freed the units a scene was holding on the conversion screen (device
2026-11-16 10:43 and 15:08, see jp_unit_fixes). The NV/NV+ refusal reply already carries the full
groups today (exvius_actions_shops._action -> _reply), the same shape its success path sends; that
is left exactly as it was and only the missing result tag is added.
"""

CLASS_UP_REQUEST = 'zf49XKg8'        # UnitClassUpRequest (m_handlers.txt:93)
NV_CLASS_UP_REQUEST = 'Pf5C8xjJ'     # UnitNvClassUpRequest (m_handlers.txt:96)
NVP_CLASS_UP_REQUEST = 'V8GtMQ2q'    # UnitNvpClassUpRequest (m_handlers.txt:97)

CLASS_UP_TAG = 'sWc7EH69'            # request AND result tag of the ★ awakening (class_up_keys REQ_TAG)
NV_CLASS_UP_TAG = '6U5w20zk'         # request AND result tag of both NV awakenings (class_up_keys NV_REQ_TAG)
MIX_GROUP = 'f08du6EW'               # UnitMixRequest / UnitMixResponse (unit_mix_keys REQ_TAG == MIX_TAG)

UNIT_ADD_TAG = '8gSkPD6b'            # UserUnitInfoList updateObject: incremental unit records

# UserUnitClassUpResult / UnitClassUpResponse fields (class_up_keys.py, mirrored by M's success rows:
# exvius_actions.py:120, exvius_actions_shops.py:778)
RES_UNIT = 'og2GHy49'                # setUserUnitId: the scene removes this unit
RES_UNIT_NEW = '5u7VYNEX'            # setUserUnitIdNew: the awakened unit's id
RES_ELEMS = 'KCk8u0am'               # setElemInfo (the materials used)
RES_ELEM_UNITS = 'WbGYcN17'          # setElemUnitInfo (also UnitMixRequest's materials CSV)
RES_ALT_ELEMS = '02CI3bpE'           # setAltElemInfo
RES_ALL_KIGEN = 'p9Xj4Anc'           # setAllKigenUseFlg

# UnitMixResponse fields (unit_mix_keys.py; M's own success row: ffbe_player.py:723-730)
MIX_BASE = 'og2GHy49'
MIX_MATERIALS = 'WbGYcN17'
MIX_GIL = '7UR4J2SE'
MIX_EXP = 'B6H34Mea'
MIX_LB_EXP = 'UDMIFB72'
MIX_SUCCESS = '1dT7ha9H'
MIX_SP_REWARD = 'E90oBqct'

_installed = False


def _note(message):
    from ffbe_state import _note
    _note(message)


def _class_up_refusal(out, req, tag):
    """The engine's refusal reply plus the unchanged result node L's awakening scenes survive.

    A reply that already carries `tag` (the success path, or an answer filled elsewhere) is
    returned untouched. No player group is added: the refusal must not replace the roster.
    """
    import exvius_actions as ea
    from ffbe_state import State
    if isinstance(out, dict) and out.get(tag):
        return out
    node = ea._node(req, tag) or {}
    old = str(node.get(RES_UNIT, '') or '')
    answer = dict(out) if isinstance(out, dict) else {}
    # L _refused_safely (handlers/unit.py:459-475): name nothing to remove, keep the requested unit
    # as the "new" one, no materials, all-kigen off.
    answer[tag] = [{RES_UNIT: '', RES_UNIT_NEW: old, RES_ELEMS: '', RES_ELEM_UNITS: '',
                    RES_ALT_ELEMS: '', RES_ALL_KIGEN: '0'}]
    player = State.player
    if player is not None and old:
        records = [row for row in player._unit_rows() if str(row.get(RES_UNIT)) == old]
        if records:                        # L unit.py:468-473: only when the account holds it
            answer[UNIT_ADD_TAG] = records
    _note('unit-class-up refusal: %s answered with the unchanged result for unit %s'
          % (tag, old or '?'))
    return answer


def _mix_refusal(out, plaintext):
    """The engine's refusal reply plus what L's _restore sends back (handlers/unit.py:312-328).

    The client dropped the request's materials from its own unit list before asking, so the
    records of the ones the account still holds go back through 8gSkPD6b (incremental, keeps the
    rest of the list). The result node echoes the request with the zero fields so the reply is
    never the empty `{}` that made the client show "Connection error (api call)".
    """
    import exvius_actions as ea
    from ffbe_state import State
    if isinstance(out, dict) and out.get(MIX_GROUP):
        return out                        # fused: the engine's own answer, untouched
    req = ea._request(plaintext)
    # serve_unit_mix is a pipeline step that runs for EVERY request; only a UnitMixRequest carries
    # the f08du6EW group. Without this guard every reply (party edit, equip, ...) got a fake mix
    # result and an empty 8gSkPD6b list (device 2026-11-17: party save in the unit screen failed).
    if not (isinstance(req, dict) and isinstance(req.get(MIX_GROUP), list) and req.get(MIX_GROUP)):
        return out
    node = ea._node(req, MIX_GROUP) or {}
    base = str(node.get(MIX_BASE, '') or '')
    materials = str(node.get(MIX_MATERIALS, '') or '')
    answer = dict(out) if isinstance(out, dict) else {}
    answer[MIX_GROUP] = [{MIX_BASE: base, MIX_MATERIALS: materials,
                          MIX_GIL: '0', MIX_EXP: '0', MIX_LB_EXP: '0',
                          MIX_SUCCESS: '0', MIX_SP_REWARD: '0'}]
    records = []
    player = State.player
    if player is not None:
        wanted = {part.strip() for part in materials.split(',') if part.strip()}
        if wanted:
            records = [row for row in player._unit_rows()
                       if str(row.get(RES_UNIT)) in wanted]
    answer[UNIT_ADD_TAG] = records        # L _restore: the material records, empty list as a
                                          # non-`{}` body when the request named nothing owned
    _note('unit-mix refusal: answered %s with the unchanged result and %d material record(s)'
          % (base or '?', len(records)))
    return answer


PARTY_DECK_GROUP = '5Eb0Rig6'  # ffbe_config.PARTY_DECK_GROUP (UserPartyDeckInfoResponse deck rows)


def _log_party_edit(plaintext):
    import exvius_actions as ea
    from ffbe_state import State
    req = ea._request(plaintext)
    rows = req.get(PARTY_DECK_GROUP) if req else None
    if not isinstance(rows, list) or State.player is None:
        return
    settings = req.get('CN92arJK')
    setting = settings[0] if isinstance(settings, list) and settings and isinstance(settings[0], dict) else {}
    kind = str(setting.get('xBi3L6yR', '1'))
    special = {'7': '7', '8': '8', '11': '11', '50': '11'}.get(kind)
    party = State.player.special_party(special) if special else State.player.data['party']
    decks = {str(d.get('id')): d for d in party.get('decks') or []}
    parts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        did = str(row.get('r21y0YzS'))
        sent = str(row.get('2A6fYiEC') or '')
        deck = decks.get(did)
        if deck is None:
            parts.append('%s:NO-DECK[%s]' % (did, sent))
            continue
        have = ','.join('%s:%s:%s' % (m['member_type'], m['disp_order'], m['instance_id'])
                        for m in deck.get('members') or [])
        if have != sent:
            parts.append('%s:[%s]->[%s]' % (did, have, sent))
    print('jp party-edit: kind=%s active=%s setting_deck=%s rows=%d state_decks=%d diff=%s'
          % (kind, party.get('active_deck'), setting.get('r21y0YzS'), len(rows), len(decks),
             ' | '.join(parts) or 'none'), flush=True)


def install(server):
    import exvius_actions as ea
    import exvius_actions_shops as sh
    import ffbe_player as fp
    import ffbe_pipeline as pl

    global _installed
    if _installed:
        return
    _installed = True

    # --- 1. the three awakening requests ----------------------------------------------------------
    # The NV/NV+ engine handlers are @action-wrapped (Refused -> state rollback + _reply with the
    # result tags popped); wrap THAT pair, the same objects HANDLERS holds.
    original_star = ea.HANDLERS.get(CLASS_UP_REQUEST) or ea.unit_class_up
    original_nv = sh.HANDLERS[NV_CLASS_UP_REQUEST]
    original_nvp = sh.HANDLERS[NVP_CLASS_UP_REQUEST]

    def star_class_up(spec, req):
        return _class_up_refusal(original_star(spec, req), req, CLASS_UP_TAG)

    def nv_class_up(spec, req):
        return _class_up_refusal(original_nv(spec, req), req, NV_CLASS_UP_TAG)

    def nvp_class_up(spec, req):
        return _class_up_refusal(original_nvp(spec, req), req, NV_CLASS_UP_TAG)

    ea.HANDLERS[CLASS_UP_REQUEST] = star_class_up
    ea.HANDLERS[NV_CLASS_UP_REQUEST] = nv_class_up
    ea.HANDLERS[NVP_CLASS_UP_REQUEST] = nvp_class_up
    sh.HANDLERS[NV_CLASS_UP_REQUEST] = nv_class_up
    sh.HANDLERS[NVP_CLASS_UP_REQUEST] = nvp_class_up
    sh.unit_nv_class_up = nv_class_up     # keep the module attributes on the live handler too
    sh.unit_nvp_class_up = nvp_class_up

    # --- 2. UnitMixRequest ------------------------------------------------------------------------
    original_mix = fp.serve_unit_mix

    def unit_mix(spec, plaintext):
        return _mix_refusal(original_mix(spec, plaintext), plaintext)

    fp.serve_unit_mix = unit_mix
    pl.serve_unit_mix = unit_mix

    # --- 3. PartyDeckEditRequest diagnostics (2026-11-17) ---------------------------------------
    # Tablet report: a saved party came back unchanged. The engine prints only the ACTIVE deck, and a
    # row whose deck id the state does not hold is skipped silently, so log every row against the state.
    original_party = pl.apply_party_edit

    def party_edit(plaintext):
        try:
            _log_party_edit(plaintext)
        except Exception as exc:  # noqa: BLE001 - diagnostics must never break the reply
            print('jp party-edit diag failed: %r' % (exc,), flush=True)
        return original_party(plaintext)

    pl.apply_party_edit = party_edit
    print('JP unit refusals: unchanged result nodes for ★ / NV / NV+ awakening and unit fusion',
          flush=True)

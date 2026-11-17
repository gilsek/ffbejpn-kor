"""JP continue count for the "clear without continuing" challenge (condition 38); installed by android_game.start.

Global 9.0.0 reports continues inside MissionEndRequest (L4i4418y[0].6q35TL07, written by
MissionEndRequest::createContinueCountTag). JP 11.0.0 has no such function and its MissionEnd carries no L4i4418y
group (all 23 JP MissionEnd requests on the test tablet, 2026-11-09), so ffbe_battle._cond_no_continue saw None and
never credited the challenge, even without a continue.

JP still sends a request when the player continues (MissionReStartRequest GfI4LaU3, MissionWaveReStartRequest
e9RP8Cto), and one TfaMissionStartRequest/MissionWaveStartRequest (BSq28mwY, mission id jQsE54Iz.qo3PECw6) per
quest attempt. So the engine counts them itself: reset at start, +1 per continue, and condition 38 uses that count
when the client report has none. The count is kept in a small file next to the save so a resumed battle keeps it.
"""
# World icon: on each story mission start the engine writes the story world number (1, 3-7) to
# state/world_icon.txt; the Frida UI hook (jp_ui_override.js) swaps the home world banner to match it.
import json
from pathlib import Path

# TfaMissionStartRequest / MissionWaveStartRequest (JP: once per attempt) and MissionStartRequest: explorations
# (e.g. 1110104 땅의 신전・탐색, 2026-11-10) start with 29JRaDbd only, so the count stayed on the previous mission,
# continue_count returned None and 「컨티뉴 없이 클리어」 failed with 0 continues.
START_IDS = ('BSq28mwY', '29JRaDbd')
CONTINUE_IDS = ('GfI4LaU3', 'e9RP8Cto')   # MissionReStartRequest, MissionWaveReStartRequest
MISSION_GROUP, MISSION_KEY = 'jQsE54Iz', 'qo3PECw6'

_path = None
_state = {'mission': None, 'continues': 0}


def _mission_of(req):
    rows = (req or {}).get(MISSION_GROUP) if isinstance(req, dict) else None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return str(rows[0].get(MISSION_KEY) or '') or None
    return None


def _save():
    if _path is None:
        return
    try:
        _path.write_text(json.dumps(_state), encoding='utf-8')
    except OSError as exc:
        print('JP mission: continue count not saved: ' + str(exc), flush=True)


def _load():
    try:
        data = json.loads(_path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            _state.update(mission=data.get('mission'), continues=int(data.get('continues') or 0))
    except (OSError, ValueError, TypeError):
        pass


_STORY_WORLDS = frozenset(('1', '3', '4', '5', '6', '7'))
_world_table = None   # mission id -> world number text; loaded on first use, tests may set a dict directly


def world_of(mission_id):
    global _world_table
    if mission_id is None:
        return None
    if _world_table is None:
        try:
            import player_state as ps
            raw = ps._load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6')
            _world_table = {str(k): str(row.get('9Pb24aSy') or '') for k, row in raw.items()} if isinstance(raw, dict) else {}
        except Exception as exc:
            _world_table = {}
            print('JP mission: world table not loaded: ' + repr(exc), flush=True)
    val = _world_table.get(str(mission_id))
    return val if val else None


def _note_world(mission_id):
    if _path is None:
        return
    try:
        w = world_of(mission_id)
        if w not in _STORY_WORLDS:
            return
        out_file = _path.parent / 'world_icon.txt'
        try:
            current = out_file.read_text(encoding='utf-8').strip()
        except OSError:
            current = None
        if current == w:
            return
        out_file.write_text(w, encoding='utf-8')
        print('JP mission: world icon -> ' + w + ' (mission ' + str(mission_id) + ')', flush=True)
    except OSError as exc:
        print('JP mission: world icon not saved: ' + repr(exc), flush=True)
    except Exception as exc:
        print('JP mission: note world failed: ' + repr(exc), flush=True)


def on_start(req):
    _state['mission'] = _mission_of(req)
    _state['continues'] = 0
    _save()
    try:
        _note_world(_state['mission'])
    except Exception as exc:
        print('JP mission: on_start note world failed: ' + repr(exc), flush=True)


def on_continue(req):
    _state['continues'] += 1
    _save()
    print('JP mission: continue #' + str(_state['continues']) + ' (mission ' + str(_state['mission']) + ')', flush=True)


def continue_count(mission_id):
    """Counted continues for this attempt, or None when this attempt's start was not seen."""
    if _state['mission'] is None or str(mission_id or '') != str(_state['mission']):
        return None
    return _state['continues']


def install(server_state_file):
    global _path
    import exvius_actions as actions
    import ffbe_battle as battle
    _path = Path(server_state_file).parent / 'jp_continue.json'
    _load()

    handlers = actions._all_handlers()   # merge the mode families first, so wrapping cannot shadow their handlers

    def wrap(rid, hook):
        original = handlers.get(rid)
        def handler(spec, req):
            try:
                hook(req)
            except Exception as exc:     # counting must never break the request itself
                print('JP mission: ' + rid + ' hook failed: ' + repr(exc), flush=True)
            return original(spec, req) if original else spec
        handlers[rid] = handler

    for rid in START_IDS:
        wrap(rid, on_start)
    for rid in CONTINUE_IDS:
        wrap(rid, on_continue)

    original_check = battle.CONDITION_CHECKS['38']
    def no_continue(ctx, param):
        if ctx.get('continue_count') is None:
            count = continue_count(ctx.get('mission_id'))
            if count is not None:
                return count == 0
        return original_check(ctx, param)
    battle.CONDITION_CHECKS['38'] = no_continue
    print('JP mission: continue count from start/continue requests (condition 38)', flush=True)

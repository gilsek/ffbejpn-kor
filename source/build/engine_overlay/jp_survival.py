"""JP 차원의 틈새 서바이벌 이벤트 진입: SurvivalMissionEntryRequest (`cH9DnW03` = iAL25ka3.php).

Installed from jp_compat.install() by ONE line (`jp_survival.install(server)`), after install_events().

WHY THE CLIENT SHOWED 「로컬 게임 데이터를 불러올 수 없습니다」
------------------------------------------------------------
JP 11.0.0 SurvivalEntryScene::initConnect (libgame.so 0x1c571e0) builds `SurvivalMissionEntryRequest`
and calls `GameScene::accessPhp`; the scene's `updateEvent` (0x1c57260) then opens InitialDownloadScene
with `SurvivalResourceCommon::getDownloadMapResourceList` (0x1c575b8) and `changeNextScene` (0x1c57370)
switches to the area scene (scene id 0x6591).  The request's reply has NO `responses.json` entry, and the
English engine's survival step is gated by `SURVIVAL` (default "0"), so the reply spec stayed `None`:
capture_server sends an EMPTY body and the client reports the connection error.  The shape below is the
English engine's `ffbe_player.serve_survival` (written and verified against the English client), which
answers exactly this request with the SurvivalEventInfo list that is the ONLY writer of the client's
`SurvivalEventInfoList` -- the list `SurvivalUtil::isPlayingSurvivalMission(areaId)` (JP 0x1db8e84 /
getObjectWithAreaId) reads.

THE WIRE KEYS ARE THE SAME IN JP 11.0.0 (read from the JP libgame.so, not copied from Global)
----------------------------------------------------------------------------------------------
Every group below was checked against the JP 11.0.0 reader's own strcmp token list:

  SurvivalEventInfoResponse::readParam   JP 0x1dfd2dc (0x608 B), 16 tokens:
      pvS5A4kE, L9IAY8iW, L84eYzxv, uv60hgDW, pAwU2R6W, VjJQ51uG, m8ivD4NX, BGFw7qi4, 2oL4dNFy,
      uwHx3jk0, XY5ZfS0w, 0dh7yRIN, 4yT7FUqj, fSxqkF10, td06MKEX, Z0EN6jSh
  UserSurvivalInfoResponse::readParam    JP 0x1dfd964 (0x128 B), 4 tokens:
      pvS5A4kE, 52ibRBqw, 7SPHKY1j, UbQ26oH4
  SurvivalBattleUnitStateResponse::readParam JP 0x1dfcddc (0x290 B), token 3KJpzuC5 + the flat block
  UserBreakThroughProgressInfoResponse::readParam JP 0x1dfdb0c (0x2f8 B), 12 tokens:
      pvS5A4kE, L9IAY8iW, IRca7hx9, M43f8qUV, CMg9aYh2, ncDi5Hu4, eGy7QdD1, hN57axnr, Tkeh4Ly5,
      8QfZ6NIK, m3Wghr1j, Y58ENcB4

The request table is identical too (translations/reports/request_tables.json: jp1100 `cH9DnW03` /
`nUfp8v2y` / `iAL25ka3.php` == g900), so the client-side dispatch ID already matches the engine's.

WHAT IS DERIVED AND WHAT IS AUTHORED
------------------------------------
DERIVED: the area list. JP F_MISSION_MST has 30 missions with `gQR24kST == 13` (survival) spread over
areas 1000..1007; each area also has F_DUNGEON_MST rows. The list is READ at install time, not typed
(the English code's "the family, not an instance"). Area 1006 = 門松の塔NORMAL (the user's example).
AUTHORED (no shipped table carries them): the event id/pair (11002 / 1 -- a pair the engine's own
`ofp9t72b` SeasonEventScheduleMst reply in responses.json already serves, and 11002 is a real JP
F_SEASON_EVENT_REWARD_MST id), the open window, and the two "no ladder" / "no banner" zeroes (legal
empty per the English notes).

WHY THE GATE ROWS ARE **NOT** SERVED HERE
-----------------------------------------
`serve_survival` also appends `0xkoNP8U` (SpDungeonCondMst) tiles. On the JP build the event archive
(jp_event_archive / jp_compat.install_events, serve_event_gate) ALREADY serves a tile for these areas
(e.g. 1006 is group `season1`, tab 4), and serve_event_gate runs AFTER serve_survival in the pipeline
(ffbe_pipeline.py steps 278 vs 327). Serving our own tile would put TWO rows for the same area id in the
replace-on-read list. The entry reply (`cH9DnW03`) never carried a gate row on the English side either
(it is not in SURVIVAL_COND_CARRIERS), so this module serves only event/user/break/state -- exactly the
four groups the entry reply needs, and no art name, so no null sprite-batch crash risk.

CARRIERS (same set the English step used)
-----------------------------------------
  event + user lists : lEHBdOEf (boot), 6H1R9WID (routine world update), MTf2j9aK (vortex entry),
                       cH9DnW03 (this entry request)
  break list         : 6H1R9WID, cH9DnW03          (destroyed on arrival -> its own carrier set)
  party state        : 6H1R9WID, cH9DnW03          (destroyed on arrival, un-gated)
The event/user lists are re-sent in full on every carrier because the client clears them on read.

NEXT STEPS IN THE SAME FAMILY (already handled by the shared engine, see build/out/survival/survival.md)
-------------------------------------------------------------------------------------------------------
SurvivalMissionStartRequest 67tFRKyo / End 3cuPF20R / Restart p02YN1JA / Retire yW35iC40 /
Return Ge2ZLDC1 are wired in exvius_actions_modes.HANDLERS (survival_start/end/restart/retire/return).
They are generic: they read the same F_MISSION_MST rows (`gQR24kST == 13`), so the JP masters drive them.
No JP overlay is installed for them; JP behaviour was NOT verified on a device (see the doc's 미확인 사항).
"""
import os

# --- request ids -----------------------------------------------------------------------------------
ENTRY_REQUEST = 'cH9DnW03'          # SurvivalMissionEntryRequest (JP == GL, endpoints.json)
LIST_CARRIERS = ('lEHBdOEf', '6H1R9WID', 'MTf2j9aK', ENTRY_REQUEST)
BREAK_CARRIERS = ('6H1R9WID', ENTRY_REQUEST)
STATE_CARRIERS = ('6H1R9WID', ENTRY_REQUEST)

# --- response groups --------------------------------------------------------------------------------
EVENT_TAG = 'NsC8t4Qr'              # SurvivalEventInfoResponse   (DESTRUCTIVE list)
USER_TAG = '65cMLkuQ'               # UserSurvivalInfoResponse    (DESTRUCTIVE list)
BREAK_TAG = 'in6Fpa2y'              # UserBreakThroughProgressInfoResponse (DESTRUCTIVE list)
STATE_TAG = '2w9Iyeaq'              # SurvivalBattleUnitStateResponse      (DESTRUCTIVE, un-gated)
STATE_TOKEN = '3KJpzuC5'            # its one and only token

# --- authored values --------------------------------------------------------------------------------
EVENT_ID = os.environ.get('JP_SURVIVAL_EVENT', '11002')     # pvS5A4kE: shipped F_SEASON_EVENT_REWARD_MST id
EVENT_PAIR = os.environ.get('JP_SURVIVAL_PAIR', '1')        # L9IAY8iW: the `ofp9t72b` schedule row key
EVENT_KIND = '1'                                            # Z0EN6jSh: +0x100 1/2 selector (1 = name the tile)
SUMALLY = '0'                                               # L84eYzxv: 0 = no reward ladder (legal empty)
BANNER = '0'                                                # fSxqkF10: 0 = no reward banner (legal empty)
WINDOW_START = '1577836800'                                 # VjJQ51uG 2020-01-01Z (evergreen)
# m8ivD4NX 2037-12-31 23:59:59Z. 2100-01-01Z (4102444800) overflows the client's 32-bit date read
# (SpDungeonCondMst::getRestTime 0x1c89088 `ldr w8,[x19,#0x60]`), same fix as jp_compat.JP_GATE_WINDOW_END.
WINDOW_END = '2145916799'                                   # 2037-12-31 23:59:59Z
assert int(WINDOW_START) < int(WINDOW_END) < 2 ** 31 - 1   # must fit the client's ldr w8 (signed 32-bit)
BREAK_GATE = '1'                                            # hN57axnr (+0x40) early-return gate != 0
BREAK_PROGRESS = '1'                                        # IRca7hx9 (+0x2c) fallback gate > 0
BREAK_CLAMPED = '2'                                         # Y58ENcB4: +0x64 is clamped to 2..5, min in range
STATE_VERSION = '1'                                         # SEND_DATA_FORMAT_VERSION
SUMMON_GAUGE = '0'                                          # authored: no shipped table carries it

_AREAS = None
_AREA_ERROR = None


def survival_areas():
    """The JP survival areas, derived from F_MISSION_MST (`gQR24kST == 13`), in numeric order.

    `JP_SURVIVAL_AREAS` (comma separated) overrides, for a bisect build.
    """
    override = os.environ.get('JP_SURVIVAL_AREAS')
    if override:
        return tuple(x for x in (s.strip() for s in override.split(',')) if x)
    global _AREAS, _AREA_ERROR
    if _AREAS is not None:
        return _AREAS
    import player_state as ps
    try:
        missions = ps._load_ndjson('F_MISSION_MST.ndjson')['__rows__']
        dungeons = ps._load_ndjson('F_DUNGEON_MST.ndjson')['__rows__']
    except (OSError, KeyError, ValueError) as exc:
        _AREA_ERROR = exc
        _AREAS = tuple()
        return _AREAS
    with_dungeon = {str(row.get('uv60hgDW')) for row in dungeons if row.get('uv60hgDW')}
    areas = {str(row.get('uv60hgDW')) for row in missions
             if str(row.get('gQR24kST')) == '13' and row.get('uv60hgDW')}
    _AREAS = tuple(sorted((a for a in areas if a in with_dungeon), key=int))
    return _AREAS


def area_facts():
    """[(area, first_dungeon, first_mission)] per survival area, READ from the shipped tables.

    "First" is FILE ORDER: the client's list accessors take the first element of each vector. An area
    without a dungeon row is skipped (nothing can be served for it).
    """
    import player_state as ps
    try:
        missions = ps._load_ndjson('F_MISSION_MST.ndjson')['__rows__']
        dungeons = ps._load_ndjson('F_DUNGEON_MST.ndjson')['__rows__']
    except (OSError, KeyError, ValueError):
        return []
    out = []
    for area in survival_areas():
        dgn = next((str(r.get('U9iHsau3')) for r in dungeons
                    if str(r.get('uv60hgDW')) == area and r.get('U9iHsau3')), None)
        if dgn is None:
            continue
        mission = next((str(r.get('qo3PECw6')) for r in missions
                        if str(r.get('U9iHsau3')) == dgn and r.get('qo3PECw6')), None)
        if mission is None:
            continue
        out.append((area, dgn, mission))
    return out


def event_row(area):
    """One SurvivalEventInfoResponse row: exactly the 16 tokens the JP reader strcmp()s."""
    return {
        'pvS5A4kE': EVENT_ID,
        'L9IAY8iW': EVENT_PAIR,
        'L84eYzxv': SUMALLY,
        'uv60hgDW': str(area),          # SubRegionId: THE key isPlayingSurvivalMission matches
        'fSxqkF10': BANNER,
        'VjJQ51uG': WINDOW_START,
        'm8ivD4NX': WINDOW_END,
        'Z0EN6jSh': EVENT_KIND,
        'pAwU2R6W': '0',
        'td06MKEX': '0',
        # the five strings with no reader located in the English client; empty so no raw key is drawn
        '4yT7FUqj': '',
        'BGFw7qi4': '',
        '2oL4dNFy': '',
        'uwHx3jk0': '',
        'XY5ZfS0w': '',
        '0dh7yRIN': '',
    }


def user_row():
    """UserSurvivalInfoResponse: the four tokens the JP reader reads."""
    return {'pvS5A4kE': EVENT_ID, '52ibRBqw': '0', '7SPHKY1j': '0', 'UbQ26oH4': '0'}


def break_row():
    """UserBreakThroughProgressInfoResponse: 12 tokens. `L9IAY8iW` must equal the EVENT row's pair.

    The client's lookup (getObjectWithAreaId) reaches the event list THROUGH the area and then matches
    the two shared fields with the pair SWAPPED (event +0x24/+0x28 vs row +0x28/+0x24), so sourcing
    `L9IAY8iW` from the area id instead is silently inert.
    """
    return {
        'L9IAY8iW': EVENT_PAIR, 'pvS5A4kE': EVENT_ID,
        'hN57axnr': BREAK_GATE, 'IRca7hx9': BREAK_PROGRESS,
        'M43f8qUV': '0', 'CMg9aYh2': '0', 'ncDi5Hu4': '0', 'eGy7QdD1': '0', 'Tkeh4Ly5': '0',
        '8QfZ6NIK': '', 'm3Wghr1j': '0', 'Y58ENcB4': BREAK_CLAMPED,
    }


def state_block(player):
    """`<version>@<summonGauge>(@<pos>|<hp>|<mp>|<lb>|||||)*` for the player's current party.

    The client's parser needs (1) a non-empty value, (2) at least two `@`-blocks, and (3) `<pos>` equal
    to the live `BattleUnit::getPartyPosition()`, i.e. the party slot index. Falls back to the legal
    empty party `1@0` when the state cannot be built (an exception here would fail the whole reply).
    """
    try:
        import player_state as ps
        parts = [STATE_VERSION, SUMMON_GAUGE]
        for pos, iid in enumerate(player.party_instance_ids()):
            row = player.roster_row(iid) or {}
            stats = ps.unit_stats(row.get('master_id'), int(row.get('level') or 1))
            parts.append('|'.join([str(pos), str(stats[0] or 0), str(stats[1] or 0),
                                   str(row.get('lb_level') or 0), '', '', '', '', '']))
        if len(parts) < 3:              # no party: `1@0` is the client's own empty form
            return STATE_VERSION + '@' + SUMMON_GAUGE
        return '@'.join(parts)
    except Exception as exc:            # noqa: BLE001 - the reply must survive a bad party row
        print('JP survival: party state unavailable (%r); serving the empty party' % (exc,), flush=True)
        return STATE_VERSION + '@' + SUMMON_GAUGE


def payload(reply_id):
    """The groups this carrier should carry, or None when the request is not a survival carrier."""
    if reply_id not in LIST_CARRIERS:
        return None
    groups = {EVENT_TAG: [event_row(area) for area, _d, _m in area_facts()],
              USER_TAG: [user_row()]}
    if reply_id in BREAK_CARRIERS:
        groups[BREAK_TAG] = [break_row()]
    if reply_id in STATE_CARRIERS:
        groups[STATE_TAG] = [{STATE_TOKEN: state_block(_player())}]
    return groups


def serve(spec, reply_id):
    """serve_survival replacement: attach the survival groups; other requests pass through untouched."""
    groups = payload(reply_id) if _player() is not None else None
    if groups is None:
        return spec
    out = dict(spec) if isinstance(spec, dict) else {}
    out.update(groups)
    return out


def _player():
    import ffbe_player as fp
    return getattr(fp.State, 'player', None)


def install(server=None):
    """Rebind the engine's survival step on ffbe_player AND ffbe_pipeline (one line from jp_compat)."""
    import ffbe_player as fp
    import ffbe_pipeline as pl
    if getattr(fp, '_jp_survival_installed', False):
        return
    missing = [n for n in ('serve_survival', 'State') if not hasattr(fp, n)]
    if missing:
        raise RuntimeError('jp survival: engine layout changed, missing ' + ','.join(missing))
    areas = survival_areas()
    if not areas:
        print('JP survival: no survival area resolved from the JP masters (%r); NOT installed'
              % (_AREA_ERROR,), flush=True)
        return
    fp.serve_survival = serve
    pl.serve_survival = serve            # ffbe_pipeline holds its own name (ffbe_pipeline.py:50)
    fp._jp_survival_installed = True
    shown = ','.join(areas[:8]) + (',...(%d total)' % len(areas) if len(areas) > 8 else '')
    print('JP survival: entry %s -> %s; areas %s; parts event,user,break,state (no gate rows: the event '
          'archive already serves the tiles); event %s pair %s'
          % (ENTRY_REQUEST, ', '.join((EVENT_TAG, USER_TAG, BREAK_TAG, STATE_TAG)), shown,
             EVENT_ID, EVENT_PAIR), flush=True)

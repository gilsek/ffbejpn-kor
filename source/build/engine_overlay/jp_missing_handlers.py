"""JP 11.0.0 pass-through handlers for requests the English engine never answered.

WHY THIS EXISTS
---------------
`capture_server._handle` chooses a reply from `responses.json` (exact `<reply_id>@<mission>`,
then `<reply_id>`, then `_default`) and only then runs `ffbe_pipeline.reply_pipeline`.
`responses.json` has no `_default` entry, so a request with neither a recorded reply nor an
`exvius_actions.HANDLERS` entry gets `spec = None` -> `body_plain = None` -> an EMPTY body.
The JP client reads an empty body as `MessageState::exist() == false` and shows
「通信エラーが発生しました」 (see ffbe_player.py's emblem block: "a reply must produce at least
one dispatchable group").  The pipeline stages do NOT rescue these requests -- they all receive
`spec=None` and return `None` -- so the report's "7 of these are handled in ffbe_pipeline" is
wrong (only `EquipGrowEntry` has an engine handler, and that one only refreshes the unit list).

This module installs one handler per request.  The goal is exactly what the JP-side reference
server (L) achieves with its `acknowledge` fallback: a valid, non-empty reply that carries the
player's own user-state groups, so the scene can be entered and left.  It does not implement
Chocobo Exploration, account transfer, the item-world run or account deletion.  Where an
action would change state (ExploreStart, Transfer, DeleteUser) the handler changes NOTHING.

REPLY SHAPE
-----------
`{"LhVz6aD2": [{}]}` is the engine's own minimal-ack idiom (`spec.setdefault("LhVz6aD2", [{}])`
in ffbe_player.py's panel/SP claims): the later `apply_to_reply` pipeline step sees
`UserInfoResponse` and projects the twelve player groups plus the team row into the reply, and
the JP client accepts it as a normal user-state answer.  Request-specific groups are added
*before* that projection and are not in `PlayerState.groups()`, so they survive unchanged.

L references (read-only; keys and rules only, no code copied):
  explore.py, explore_keys.py, explore_view.py
  transfer.py, transfer_keys.py
  equip_grow.py, equip_grow_keys.py, equip_grow_flow.py
  map_mission.py (MissionBreak), quest.py (`_error`)
  handlers/user.py (`acknowledge`, the disabled/default answer)

OUT OF SCOPE (deliberately): item-world run progress, Chocobo exploration state, real account
transfer, actual account deletion, Ultimania code issuance.  See
build/out/jp_offline/missing_handlers_notes.md for the per-request table.
"""
from __future__ import annotations

import re

# --- reply tags (JP 11.0.0 response_tags; also used by the engine) ---------------------------------
USER_INFO_TAG = "LhVz6aD2"          # UserInfoResponse -- also the engine's projection trigger
MESSAGE_TAG = "bCf65yoK"            # MessageResponse (JP response_tags_jp.json)

# MessageResponse fields (L handlers/quest.py MSG_*, documented survey §19.1)
MSG_TYPE_FIELD = "D8aznm56"         # setType
MSG_CMD_FIELD = "5oHZM9zK"          # setCmd (2 = back to the previous scene)
MSG_TEXT_FIELD = "Wk1v6upb"         # setMessage
MSG_URL_FIELD = "8o6GLMTw"          # setUrl
MSG_TYPE_ERROR = "1"                # L quest_keys.MSG_TYPE_ERROR
MSG_CMD_BACK = "2"                  # L quest_keys.MSG_CMD_BACK

# Transfer (L transfer_keys.py)
TRANSFER_CODE_FIELD = "c52MWCji"    # UserInfo.accountID -- 12 digits, first digit non-zero
TRANSFER_PASSWORD_FIELD = "D3fzIL1s"  # UserInfo.password -- 4..12 ASCII alphanumerics
TRANSFER_CODE = "123456789012"      # fixed dummy; nothing is stored or checked
DEFAULT_PASSWORD = "1234"
PASSWORD_RE = re.compile(r"[A-Za-z0-9]{4,12}")

# Equip-grow (L equip_grow_keys.py)
EQUIP_GROW_EVENT_TAG = "1P4YjSbT"   # EquipGrowEventInfoResponse (replaces the whole singleton)
EI_CATEGORIES = "h3N2ZU5Q"          # csv of equipment categories
EI_AREA_MISSION = "qhMKRz81"        # "difficulty@<mission id>"; the screen dereferences the mission
EI_GROWING = "J1YX9kmM"             # "<type>:<id>" of the equipment being grown; "" = none
EI_PLAYING = "aXqD3i9J"             # "" = no run in progress
EI_BONUS_CATEGORIES = "93Y6evuT"
EI_TARGET_INFO = "7iJpH5zZ"
EI_RARE_MAP = "1Zsh27mS"
EQUIP_GROW_STATUS_TAG = "81kzGcgF"  # EquipGrowStatusInfoResponse
ST_STATE = "ah9URJd7"               # "0" = event open
ST_ABILITY_FIXED = "cEVau7d8"       # "1" = no ability pick pending
EQUIP_GROW_SNAPSHOT_TAG = "bvd6n4u2"  # clears the client's carried HP/MP of the last floor
SNAPSHOT_KEY = "3KJpzuC5"

# F_MISSION_MST / F_EQUIP_ITEM_MST columns (JP masters; the same tokens the engine uses)
MISSION_KEY = "qo3PECw6"
MISSION_SUBTYPE = "gQR24kST"
MISSION_EQUIP_GROW = "6"            # item-world floor
MISSION_AREA = "U9iHsau3"
EQUIP_ITEM_KEY = "J1YX9kmM"
EQUIP_CATEGORY = "8DZGF4Nn"         # 1..16 weapon, 30s shield, 40s hat, 50s body, 60 accessory
# The first JP item-world floor (area 78601, 鍛鉄城メルフィキア 1F) as a last-resort constant:
# it is a real F_MISSION_MST row, which qhMKRz81 needs, and the table is always shipped.
FALLBACK_EQUIP_GROW_MISSION = "7860101"

# --- request ids (JP 11.0.0 protocol.json; identical to the engine's endpoints) --------------------
EXPLORE_REQUESTS = (
    "Tnkz60cb",   # ExploreEntryRequest
    "f8Q0BJVX",   # ExploreSettingRequest
    "FR4ISN7P",   # ExploreStartRequest
    "t8Yd2Pcy",   # ExploreRetireRequest
    "XG3CwM1N",   # ExploreRewardGetRequest
)
TRANSFER_CODE_ISSUE = "crzI2bA5"    # TransferCodeIssueRequest
TRANSFER_CODE_CHECK = "CY89mIdz"    # TransferCodeCheckRequest
TRANSFER_EXECUTE = "oE5fmZN9"       # TransferRequest
ULTIMANIA_CODE_ISSUE = "D1gXmV3L"   # UltimaniaCodeIssueRequest
DELETE_USER = "5Rsp7xM6"            # DeleteUserRequest
EQUIP_GROW_ENTRY = "U8F0Q25i"       # EquipGrowEntryRequest (already had a unit-refresh handler)
EQUIP_GROW_RESUME = "80R6BXUw"      # EquipGrowAbilitySelectResumeRequest
EQUIP_GROW_FIX = "k8ew94DN"         # EquipGrowAbilityFixRequest
MISSION_BREAK = "17LFJD0b"          # MissionBreakRequest (currently an empty body)


def _ack(spec):
    """The engine's minimal non-empty answer: a seeded UserInfoResponse.

    `apply_to_reply` then adds `PlayerState.groups()` + the team row (the same projection every
    recorded action reply gets).  The sparse row itself is the engine's own idiom; the client
    merges the fields it reads into the identity it already holds.
    """
    out = dict(spec) if isinstance(spec, dict) else {}
    out.setdefault(USER_INFO_TAG, [{}])
    return out


def _refuse(spec, text):
    """Refuse with a MessageResponse (type 1 / cmd 2 = error, return to the previous scene).

    L sends this as `respond_error`: a normal body plus MessageResponse with a non-empty text.
    The engine's own replies never carried one, but `bCf65yoK` is present in the JP 11.0.0
    response table and the create-user note in the audit records that sending it SETS
    MessageState.  The identity group beside it keeps the reply a normal user-state answer if a
    scene ignores the message.
    """
    out = _ack(spec)
    out[MESSAGE_TAG] = [{MSG_TYPE_FIELD: MSG_TYPE_ERROR, MSG_CMD_FIELD: MSG_CMD_BACK,
                         MSG_TEXT_FIELD: text, MSG_URL_FIELD: ""}]
    return out


def _first_row(req, group):
    rows = (req or {}).get(group) if isinstance(req, dict) else None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return {}


# --- Chocobo Exploration (disabled) ----------------------------------------------------------------
def explore_ack(spec, req):
    """Entry/Setting/Start/Retire/RewardGet: L answers its fallback while explore is disabled.

    L returns None from every explore handler unless `explore_enabled` and config/explore.yaml are
    usable, and the fallback (`acknowledge`) then sends the account identity.  Nothing is started,
    retired or claimed here either; the reply is only there so the scene can be entered and left.
    """
    return _ack(spec)


# --- Data Transfer (offline: never moves an account) ----------------------------------------------
def transfer_code_issue(spec, req):
    """Show a fixed dummy 12-digit code; store nothing.

    L stores a code and password hash and requires an existing account.  Offline there is no
    second server to move to, so the code is a constant in the shape the client's numeric box
    accepts (`[1-9][0-9]{11}`, L transfer.py CODE_FORMAT) and the password is echoed only when it
    matches the client's own 4..12 ASCII alphanumeric rule.
    """
    row = _first_row(req, USER_INFO_TAG)
    password = row.get(TRANSFER_PASSWORD_FIELD)
    if not (isinstance(password, str) and PASSWORD_RE.fullmatch(password)):
        password = DEFAULT_PASSWORD
    out = _ack(spec)
    out[USER_INFO_TAG] = [{TRANSFER_CODE_FIELD: TRANSFER_CODE,
                           TRANSFER_PASSWORD_FIELD: password}]
    return out


def transfer_code_check(spec, req):
    """Refuse: nothing to look up, nothing changes."""
    return _refuse(spec, "Account transfer is not available in this offline build.")


def transfer_execute(spec, req):
    """Refuse: the save never leaves this device."""
    return _refuse(spec, "Account transfer is not available in this offline build.")


# --- Account deletion / Ultimania code -------------------------------------------------------------
def delete_user(spec, req):
    """Refuse. This handler never touches State (no save, no roster, no file)."""
    return _refuse(spec, "Deleting the account is not available in this offline build.")


def ultimania_code_issue(spec, req):
    """L has no handler (its fallback acknowledges); do the same and issue nothing."""
    return _ack(spec)


# --- Item world (EquipGrow) "no run in progress" ---------------------------------------------------
def _equip_grow_missions():
    """(first subtype-6 mission id) from the shipped F_MISSION_MST, cached in the caller."""
    import player_state as ps
    rows = ps._load_ndjson("F_MISSION_MST.ndjson", MISSION_KEY)
    floors = [(str(mid), row) for mid, row in rows.items()
              if isinstance(row, dict) and str(row.get(MISSION_SUBTYPE)) == MISSION_EQUIP_GROW]
    if not floors:
        return FALLBACK_EQUIP_GROW_MISSION
    area_786 = [mid for mid, row in floors if str(row.get(MISSION_AREA)) == "78601"]
    pool = area_786 or [mid for mid, _row in floors]
    return min(pool, key=int)


def _equip_grow_categories():
    """The equipment categories the shipped F_EQUIP_ITEM_MST carries (csv of ints, L's rule)."""
    import player_state as ps
    rows = ps._load_ndjson("F_EQUIP_ITEM_MST.ndjson").get("__rows__", [])
    values = {str(row.get(EQUIP_CATEGORY)) for row in rows if isinstance(row, dict)}
    return ",".join(str(v) for v in sorted(int(v) for v in values if v.isdigit()))


_EQUIP_GROW_CACHE = {}


def _equip_grow_derived():
    if not _EQUIP_GROW_CACHE:
        mission, categories = FALLBACK_EQUIP_GROW_MISSION, ""
        try:
            mission = _equip_grow_missions()
            categories = _equip_grow_categories()
        except (OSError, KeyError, ValueError):
            pass                      # masters not readable here: keep the known real mission
        _EQUIP_GROW_CACHE["mission"] = mission
        _EQUIP_GROW_CACHE["categories"] = categories
    return _EQUIP_GROW_CACHE["mission"], _EQUIP_GROW_CACHE["categories"]


def _equip_grow_no_run(spec):
    """EventInfo (no run), StatusInfo (no pending pick), an empty floor snapshot, identity.

    L's run_tags with run=None: growing/playing empty, the area's first mission in
    qhMKRz81 (TopScene::backScene dereferences it), and the empty snapshot record so the client
    drops the previous run's HP/MP.  No run is created and no orb is spent.
    """
    mission, categories = _equip_grow_derived()
    out = _ack(spec)
    out[EQUIP_GROW_EVENT_TAG] = [{EI_CATEGORIES: categories,
                                  EI_AREA_MISSION: "0@" + mission,
                                  EI_GROWING: "", EI_PLAYING: "",
                                  EI_BONUS_CATEGORIES: "", EI_TARGET_INFO: "", EI_RARE_MAP: ""}]
    out[EQUIP_GROW_STATUS_TAG] = [{ST_STATE: "0", ST_ABILITY_FIXED: "1"}]
    out[EQUIP_GROW_SNAPSHOT_TAG] = [{SNAPSHOT_KEY: ""}]
    return out


def equip_grow_entry(spec, req):
    """Enter the item world with no run; replaces the engine's unit-refresh-only handler."""
    return _equip_grow_no_run(spec)


def equip_grow_resume(spec, req):
    """Nothing is waiting; answer the same no-run state so the screen opens and backs out."""
    return _equip_grow_no_run(spec)


def equip_grow_fix(spec, req):
    """A pending pick cannot exist offline; echo the no-run state and change nothing."""
    return _equip_grow_no_run(spec)


# --- Mission break ---------------------------------------------------------------------------------
def mission_break(spec, req):
    """L answers an ack (SignalKeyResponse) after parking the attempt; the engine has no attempt.

    There is no `MissionBreakResponse` class in the JP 11.0.0 response table, so the engine's
    identity projection is the equivalent non-empty ack and lets MapScene continue.
    """
    return _ack(spec)


HANDLERS = {
    **{rid: explore_ack for rid in EXPLORE_REQUESTS},
    TRANSFER_CODE_ISSUE: transfer_code_issue,
    TRANSFER_CODE_CHECK: transfer_code_check,
    TRANSFER_EXECUTE: transfer_execute,
    DELETE_USER: delete_user,
    ULTIMANIA_CODE_ISSUE: ultimania_code_issue,
    EQUIP_GROW_ENTRY: equip_grow_entry,
    EQUIP_GROW_RESUME: equip_grow_resume,
    EQUIP_GROW_FIX: equip_grow_fix,
    MISSION_BREAK: mission_break,
}


def install(server):
    """Register every handler in the engine's dispatch table (call from jp_compat.install)."""
    import exvius_actions as ea
    for rid, fn in HANDLERS.items():
        ea.HANDLERS[rid] = fn     # wins over the family merge: _all_handlers keeps existing ids
    print("JP missing handlers: %d registered (%s)"
          % (len(HANDLERS), ", ".join(sorted(HANDLERS))), flush=True)

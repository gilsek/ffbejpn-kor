"""JP weekly login bonus (F_LOGIN_BONUS_MST) + JP cumulative ladder (F_LOGIN_BONUS_TOTAL_REWARD_MST).

Install: `import jp_login_bonus; jp_login_bonus.install(server)` at the END of jp_compat.install(server).
Nothing here edits the engine: names are rebound on the already-imported modules (the jp_compat pattern,
jp_compat.py:140-144 / 371-372), and capture_server.reply_pipeline is wrapped once (jp_compat.py:441-446).

WHY THE JP CLIENT NEVER SHOWED ITS LOGIN BONUS (full evidence: build/out/login_audit/notes.md)
-----------------------------------------------------------------------------------------------
* HOME sends LoginBonusRequest (`vw9RP3i4`) only while `UserState::loginBonusFlg` (+0x164) is set, and the
  ONLY thing that sets it is `ecK58yUC` in the RoutineHomeUpdateResponse group `QB47tpMF` (request
  `Daud71Hn`). The engine never sends that value as non-zero (it is "0" in responses.json).
* The scene is gated on OpeLoginBonusInfo process day (+0x40) >= 1, fed only by `fHSZ74Qm` in
  OpeLoginBonusUpdateResponse (`yL2jdmM3`). The engine never sends that group at all (the catch-up plan is
  empty while the season is off) and hardcodes process day "0" even when it does.
* `cksL9bW8` non-empty selects the CUMULATIVE (total) scene; empty selects the WEEKLY 7-day scene.
* The weekly scene calls `LoginBonusMstList::getCurrentLoginBonusMst(processDay)` and stores the result
  without a null check (0x1ba1f6c-0x1ba1f80), so a process day with NO F_LOGIN_BONUS_MST window is a crash
  risk. The JP table ends 2026-04-12 -> this module refuses to open the popup unless the engine's own
  F_LOGIN_BONUS_MST (build/out/login_bonus/F_LOGIN_BONUS_MST.ndjson must be deployed beside it) contains one
  of the APPENDED rows (id 508.. or the chosen reward string) covering today. It is a deploy interlock, not
  a client check (the client reads its own files/ copy), and it also keeps an undeployed device on today's
  behaviour instead of crashing it.

WHAT THIS MODULE DOES
---------------------
1. `Daud71Hn`: `QB47tpMF[0].ecK58yUC` = "1" on the first HOME arrival of a CONNECTION that has something to
   show (see CONNECTIONS below), "0" otherwise. Other fields of the row are preserved; the group is added when
   the template lacks it.
2. `vw9RP3i4`: serves `yL2jdmM3` (68Vn2FrK = consecutive days, cksL9bW8 = the tier ROW IDS crossed on THIS
   connection, fHSZ74Qm = today YYYYMMDD in device-local time), `Bbc6pF9Q.1ACjIe9S` (total login days) and
   `Bbc6pF9Q.juA0Z4m7` (the received tiers' switch bits). The SP group `n5W9Et2I` is stripped from this reply
   (it is the campaign's group, not ours, and the user asked that it must not ride here).
3. Rewards are CREDITED, not mailed: the weekly day's entries of WEEKLY_REWARDS and every newly reached JP
   ladder tier are paid through PlayerState._grant_items, the engine's ONE credit path (the same one
   receive_mail/claim paths use, player_state.py:3451). The reply then carries the groups that PROJECT what
   was paid (J3pAG0I5 lapis, 3oU9Ktb7 gil/FP, Md0N5abE type-23, 0dNXQa3R bag, B71MekS8 roster,
   MBPCGT84 equipment), so the client's top bar and lists show the new values immediately.
4. The English 28-day calendar path is turned off (serve_login_bonus / deliver_login_mail -> passthrough):
   JP 11.0.0 has no DailyLoginBonus response class (`f5bA4wFx`/`DM63p52N` occur 0 times in libgame), and
   deliver_login_mail would post Global-only item ids into the JP mailbox (jp_mail.py exists for that crash).

WHY `cksL9bW8` CARRIES ROW IDS AND `juA0Z4m7` MUST RIDE (TotalLoginBonusScene's OK button)
-----------------------------------------------------------------------------------------
`TotalLoginBonusScene`'s confirm button is created DISABLED (`setLayout` 0x1b99c48..0x1b99c5c, vtable+0x538
with 0) and is enabled in only two places: `updateEvent` 0x1b9a170..0x1b9a1a0 when the scene param
[+0x570] == 0x4ce (HomeScene passes 0x64 via `setParams`, 0x164b9d0), or `playEndCallback` 0x1b9a598..0x1b9a5ec
after an SS5 player finishes "loginbonus_st_alreadyget/anime". That player is created only in
`setRewardListLayout` 0x1b9b498..0x1b9b544, for a row where `UserLoginBonusTotalInfo::isValid(row+0x44)`
is TRUE and `row+0x24` (M1nFiTG2, the row id) equals scene+0x58c. The scene constructor (0x1b98e90..0x1b98ebc)
fills scene+0x58c from the LAST integer of `cksL9bW8` -- i.e. the client reads that value as a ROW ID
(`LoginBonusTotalRewardMstList::getObjectWithId` 0x1c9ecc0 compares M1nFiTG2), not as a day. And
`isValid` (0x1d542d4) only reads `UserLoginBonusTotalInfo+0x28` = `Bbc6pF9Q.juA0Z4m7`, an EMPTY string
reports false for every row (0x1d542f4), so without that field no player exists, the animation never runs
and the button stays dead. The bit container is 4 bits per hex digit, MSB first (the same
`_set_switch_bit` encoding `ffbe_battle.py` uses).

CONNECTIONS (the cumulative ladder counts CONNECTIONS, not days)
---------------------------------------------------------------
The user wants the cumulative ladder to advance once per CONNECTION -- app launched, login screen passed, HOME
reached -- not once per device-local day. The weekly 7-day calendar stays once per day. A connection is
detected from the client's own request order, not from a clock: the login chain sends GetUserInfo /
GetUserInfo2 / GetUserInfo3 (`X07iYtp5` / `2eK5Vkr8` / `4rjw5pnv`) between LoginScene and the first
`Daud71Hn`; they are NOT sent when the player walks out of another scene and back to HOME, on the 30-minute
home refresh, or when the app resumes without leaving the process. Evidence (build/out/jp_offline/run1.log,
19 hours, 47 `Daud71Hn`): 39 GetUserInfo each preceded by LoginScene+ConnectScene, 43 of 47 `Daud71Hn` had a
LoginScene/GetUserInfo since the previous HomeScene, and the remaining 4 were exactly returns to HOME from
StepScene/MailTopScene and the periodic refresh. `Initialize` (`75fYdNxq`) rides the same title chain (97
occurrences, every one followed by a LoginScene) and is armed too, so a launch whose GetUserInfo chain is
skipped still counts. See build/out/login_total/notes.md SS8.

A fresh process is armed from the start: the client cannot reach HOME without passing LoginScene, so the first
`Daud71Hn` of a process is a connection even if the observation hook missed the login request. The flag is
consumed by that first `Daud71Hn`, so the refresh/returns/resume never count twice.

WEEKLY AND TOTAL ON THE SAME CONNECTION
---------------------------------------
`HomeScene::checkLoginBonusScene` picks ONE scene per home arrival: `cksL9bW8` empty -> WeeklyLoginBonusScene,
non-empty -> TotalLoginBonusScene (0x164b994..0x164ba68). There is no second popup in the same arrival, so the
two can never be shown together. Both are still PAID: the weekly rows are credited here (the weekly scene only
draws the calendar; it claims nothing) and the ladder tiers are credited here too. The total scene wins the
slot when a tier is crossed on the day's first connection, because its content (the newly received tier, the
alreadyget animation and the enabled confirm button) is the news, while the weekly calendar is static. The
weekly day is NOT skipped or re-rolled: week_day/paid_day advance exactly as before.

Counters are the engine's own player fields (reused, not duplicated): data['catchup'] total_login_days /
serial_days / last_advance / ladder_bit / ladder_tier (player_state.py:3312-3431). `advance_catchup` stays
the once-per-local-day advance; a later connection of a day already advanced gets its own +1 on
total_login_days (see _count_connection), so existing saves keep working: the ladder's idempotence key is
still `ladder_bit`, so an already received tier is never paid again. serial_days stays day-based (it is the
consecutive-DAY counter read as 68Vn2FrK). The weekly day counter and the guards live in
data['jp_login_bonus'].
"""
import json
import os
import time

# --- reply tokens (libgame 11.0.0; see notes.md SS2) -----------------------------------------------------------
HOME_REQUEST = 'Daud71Hn'          # RoutineHomeUpdateRequest
HOME_GROUP = 'QB47tpMF'            # RoutineHomeUpdateRespose
HOME_FLAG = 'ecK58yUC'             # -> UserState::loginBonusFlg (+0x164)
LOGIN_REQUEST = 'vw9RP3i4'         # LoginBonusRequest
OPE_GROUP = 'yL2jdmM3'             # OpeLoginBonusUpdateResponse
OPE_SERIAL = '68Vn2FrK'            # +0x24 serialLoginCnt
OPE_CROSSED = 'cksL9bW8'           # +0x28 loginBonusDayInfo (empty -> weekly scene, else total scene);
                                   # the client uses the LAST value as the reward ROW ID (M1nFiTG2)
OPE_PROCESS_DAY = 'fHSZ74Qm'       # +0x40 process day (YYYYMMDD; 0 = "use device clock" = the gate rejects it)
TOTAL_GROUP = 'Bbc6pF9Q'           # UserLoginBonusTotalInfoResponse (the ladder's axis)
TOTAL_DAYS = '1ACjIe9S'            # total login days
TOTAL_SWITCH = 'juA0Z4m7'          # received-tier bit string (4 bits per hex digit, MSB first)
SP_GROUP = 'n5W9Et2I'              # UserLoginBonusSpInfoResponse -- must NOT ride vw9RP3i4

# --- connection detection (the login chain, and only it -- see the docstring's CONNECTIONS section) -----------
LOGIN_FLOW_IDS = ('X07iYtp5', '2eK5Vkr8', '4rjw5pnv')   # GetUserInfo / GetUserInfo2 / GetUserInfo3
INITIALIZE_ID = '75fYdNxq'         # InitializeRequest: the same title -> login chain, twice per launch

# --- master tables ------------------------------------------------------------------------------------------
BONUS_TABLE = 'F_LOGIN_BONUS_MST.ndjson'
BONUS_ID, BONUS_START, BONUS_END, BONUS_REWARD = 'a3ZcU6gv', 'IFQ70DYS', 'c46Ayz8I', 'dX6cor8j'
FIRST_NEW_ID = 508               # build/add_login_bonus_rows.py appends 508..
TIER_TABLE = 'F_LOGIN_BONUS_TOTAL_REWARD_MST.ndjson'
TIER_ID, TIER_DAYS, TIER_REWARD, TIER_BIT = 'M1nFiTG2', '7oUX6QZK', 'dX6cor8j', 'QLfe23bu'
# Table -> (id token) for the ids a reward row can name. A row whose id is absent is NOT paid (the client
# would draw an empty icon, and for kind 10 a roster row the unit tables cannot resolve).
ID_TABLES = {10: ('F_UNIT_MST.ndjson', '3HriTp6B'),
             20: ('F_ITEM_MST.ndjson', 'tL6G9egd'),
             21: ('F_EQUIP_ITEM_MST.ndjson', 'J1YX9kmM'),
             22: ('F_MATERIA_MST.ndjson', 'H5jBL0Vf'),
             23: ('F_IMPORTANT_ITEM_MST.ndjson', '2dfixko3')}
CURRENCY_KINDS = (30, 50, 51)
WEEK_DAYS = 7

# The weekly calendar the user decided on: `day@kind:id:count` per entry (the JP row format, verified against
# rows 1..507: "1@50:1:100,2@23:100:3,..."). 50 = lapis, id 1, count = lapis. Lapis-heavy by decision.
WEEKLY_REWARDS = '1@50:1:500,2@50:1:500,3@50:1:1000,4@50:1:500,5@50:1:500,6@50:1:1000,7@50:1:3000'
# F_LOGIN_BONUS_MST rows appended by build/add_login_bonus_rows.py, id 508.., 20260413..2035-12-31 (508 rows,
# seven-day windows that do not overlap; the last one is one day). The dialogue column VC9F3eJn is copied from
# row 507. This module does not read them (the client does); the guard below only checks that SOME window covers
# today, and the engine-side copy must be the one carrying them.
STATE_KEY = 'jp_login_bonus'

# Fallback copy of the JP 79-tier ladder (days|switch bit|reward), used only when the engine's own
# F_LOGIN_BONUS_TOTAL_REWARD_MST.ndjson is missing or is still the Global 29-tier table. Frozen from
# build/out/jp_offline/engine/static/mst_decoded/F_LOGIN_BONUS_TOTAL_REWARD_MST.ndjson (79 rows).
_FALLBACK_TIERS = (
    '2|1|30:10000', '3|2|51:2000', '5|3|23:50:1', '7|4|10:900020301:10:100:1', '14|5|50:1:500',
    '30|6|10:904000104:1:100:1:0:100000001', '60|7|10:900000301:1:100:1', '100|8|50:1:500',
    '150|9|10:900001301:1:100:1', '200|10|50:1:500', '250|11|10:900002301:1:100:1',
    '300|12|10:904000105:1:100:1:0:100000002', '350|13|10:900003301:1:100:1', '400|14|50:1:500',
    '450|15|10:900004301:1:100:1', '500|16|50:1:500', '550|17|10:900005301:1:100:1', '600|18|50:1:500',
    '650|19|10:905000104:1:100:1', '700|20|50:1:500', '750|21|10:900000301:1:100:1', '800|22|50:1:500',
    '850|23|10:900001301:1:100:1', '900|24|50:1:500', '950|25|10:900002301:1:100:1', '1000|26|50:1:500',
    '1050|27|10:900003301:1:100:1', '1100|28|50:1:500', '1150|29|10:900004301:1:100:1', '1200|30|50:1:500',
    '1250|31|10:900005301:1:100:1', '1300|32|50:1:500', '1350|33|10:905000104:1:100:1', '1400|34|50:1:500',
    '1450|35|10:900000301:1:100:1', '1500|36|50:1:500', '1550|37|10:900002301:1:100:1', '1600|38|50:1:500',
    '1650|39|10:900003301:1:100:1', '1700|40|50:1:500', '1750|41|10:900004301:1:100:1', '1800|42|50:1:500',
    '1850|43|10:900005301:1:100:1', '1900|44|50:1:500', '1950|45|10:905000104:1:100:1', '2000|46|50:1:500',
    '2050|47|10:900000301:1:100:1', '2100|48|20:106213510:10:100', '2150|49|50:1:500',
    '2200|50|20:106211340:10:100', '2250|51|20:106213510:10:100', '2300|52|50:1:500',
    '2350|53|23:260:10', '2400|54|20:106211340:10:100', '2450|55|20:106213510:10:100',
    '2500|56|50:1:5000', '2550|57|50:1:500', '2600|58|50:1:1000', '2650|59|50:1:500',
    '2700|60|50:1:1000', '2750|61|50:1:500', '2800|62|50:1:1000', '2850|63|50:1:500',
    '2900|64|50:1:1000', '2950|65|50:1:500', '3000|66|50:1:5000', '3050|67|50:1:500',
    '3100|68|50:1:1000', '3150|69|50:1:500', '3200|70|50:1:1000', '3250|71|50:1:500',
    '3300|72|50:1:1000', '3350|73|50:1:500', '3400|74|50:1:1000', '3450|75|50:1:500',
    '3500|76|50:1:5000', '3550|77|50:1:500', '3600|78|50:1:1000', '3650|79|50:1:500',
)

# MST_DIR can be overridden (the local test points it at a directory whose F_LOGIN_BONUS_MST has the new rows);
# otherwise the engine's own data path is used at call time (local_game.py sets FFBE_DATA before the import).
MST_DIR = None

_INSTALLED = False
_ROWS_CACHE = {}
_ID_CACHE = {}
_TIERS_CACHE = None
_WEEKLY_CACHE = None
_BLOCKED_LOGGED = ''
_SERVER = None
# Armed at process start: HOME is unreachable without the login screen, so the first `Daud71Hn` of a fresh
# process is a connection. Consumed by that arrival; re-armed only by the login chain (see _note_login_flow).
_SESSION_ARMED = True


def _note_login_flow(reply_id):
    """Remember that the client is in its login chain; the next `Daud71Hn` is that connection's HOME arrival."""
    global _SESSION_ARMED
    if reply_id in LOGIN_FLOW_IDS or reply_id == INITIALIZE_ID:
        _SESSION_ARMED = True


def _consume_session():
    """True exactly once per login chain: the first HOME arrival after it."""
    global _SESSION_ARMED
    if not _SESSION_ARMED:
        return False
    _SESSION_ARMED = False
    return True


# --- device-local date ---------------------------------------------------------------------------------------
def _now():
    """Seam for the test: the module asks here for 'now' and the test moves the clock."""
    return time.time()


def _utc_offset(epoch=None):
    """Seconds east of UTC for the device. Python under Chaquopy may not see Android's zone (no TZ variable),
    so ask java.util.TimeZone first (same helper as jp_compat.py:36-43)."""
    epoch = _now() if epoch is None else epoch
    try:
        from java.util import TimeZone
        return int(TimeZone.getDefault().getOffset(int(epoch * 1000)) // 1000)
    except Exception:  # noqa: BLE001 - not on Android / no java bridge: fall back to Python's own zone
        try:
            return int(time.localtime(epoch).tm_gmtoff or 0)
        except Exception:  # noqa: BLE001
            return 0


def _local(epoch=None):
    epoch = _now() if epoch is None else epoch
    return time.gmtime(epoch + _utc_offset(epoch))


def _dates(epoch=None):
    """(YYYY-MM-DD, YYYYMMDD) for the device-local day."""
    t = _local(epoch)
    return time.strftime('%Y-%m-%d', t), time.strftime('%Y%m%d', t)


# --- logging (engine stdout does not reach logcat) -----------------------------------------------------------
def _log(server, message):
    print('JP login bonus: ' + message, flush=True)
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(server.st.STATE_FILE)), 'jp_login_bonus.log')
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(time.strftime('%H:%M:%S ') + message + chr(10))
    except Exception:  # noqa: BLE001 - tracing must never break a reply
        pass


# --- master access ------------------------------------------------------------------------------------------
def _mst_rows(name):
    folder = MST_DIR
    if not folder:
        import data_paths
        folder = data_paths.MST_DIR
    path = os.path.join(folder, name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    cache_key = (path, mtime)
    if cache_key in _ROWS_CACHE:
        return _ROWS_CACHE[cache_key]
    rows = []
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        rows = []
    _ROWS_CACHE[cache_key] = rows
    while len(_ROWS_CACHE) > 8:               # a handful of tables is enough; bound the memory
        _ROWS_CACHE.pop(next(iter(_ROWS_CACHE)))
    return rows


def _window_row(ymd):
    """The appended F_LOGIN_BONUS_MST row whose [start, end] contains `ymd`, or None.

    Only a row this project added counts (id >= FIRST_NEW_ID, or the chosen reward string): the deployed
    Global 1-row table has an evergreen window too, and it must not be mistaken for the JP calendar. The
    client reads its own copy of the table, so this is the deploy interlock -- no row here means the popup
    stays closed rather than sending the client into WeeklyLoginBonusScene with a null row.
    """
    for row in _mst_rows(BONUS_TABLE):
        start, end = str(row.get(BONUS_START) or ''), str(row.get(BONUS_END) or '')
        if not (len(start) == 8 and len(end) == 8 and start.isdigit() and end.isdigit()
                and start <= ymd <= end):
            continue
        ident = str(row.get(BONUS_ID) or '')
        if (ident.isdigit() and int(ident) >= FIRST_NEW_ID) or str(row.get(BONUS_REWARD) or '') == WEEKLY_REWARDS:
            return row
    return None


def _id_set(table, token):
    key = (table, token)
    if key not in _ID_CACHE:
        try:
            _ID_CACHE[key] = {str(row.get(token) or '') for row in _mst_rows(table)}
        except Exception:  # noqa: BLE001
            _ID_CACHE[key] = None
    return _ID_CACHE[key]


def _known_reward(kind, iid):
    """Whether the JP masters can resolve this reward id. Unknown tables/kinds are left to _grant_items."""
    if kind in CURRENCY_KINDS:
        return True
    spec = ID_TABLES.get(kind)
    if not spec:
        return True
    ids = _id_set(*spec)
    if not ids:
        return True              # table not deployed: do not block the reward on our own missing data
    return str(iid) in ids


def _tiers():
    """The JP 79-tier ladder as the dicts PlayerState.pay_catchup_ladder wants (days/bit/index/label)."""
    global _TIERS_CACHE
    if _TIERS_CACHE is not None:
        return _TIERS_CACHE
    tiers = []
    for row in _mst_rows(TIER_TABLE):
        try:
            days, bit = int(row.get(TIER_DAYS) or 0), int(row.get(TIER_BIT) or 0)
        except (TypeError, ValueError):
            continue
        reward = str(row.get(TIER_REWARD) or '')
        if days <= 0 or bit <= 0 or not reward:
            continue
        tiers.append({'index': str(row.get(TIER_ID) or ''), 'days': days, 'bit': bit,
                      'reward': reward, 'label': reward})
    if len(tiers) < 50:              # Global 29 tiers, or the table is absent -> the frozen JP copy
        tiers = [{'index': str(i + 1), 'days': int(entry.split('|')[0]),
                  'bit': int(entry.split('|')[1]), 'reward': entry.split('|')[2],
                  'label': entry.split('|')[2]} for i, entry in enumerate(_FALLBACK_TIERS)]
        print('JP login bonus: %s has %d tier(s), using the frozen JP 79-tier copy'
              % (TIER_TABLE, len(_mst_rows(TIER_TABLE))), flush=True)
    _TIERS_CACHE = tiers
    return tiers


def _weekly():
    """{day: [reward row, ...]} for WEEKLY_REWARDS."""
    global _WEEKLY_CACHE
    if _WEEKLY_CACHE is None:
        out = {}
        for part in WEEKLY_REWARDS.split(','):
            day, sep, rest = part.strip().partition('@')
            if not sep or not day.isdigit():
                continue
            rows = _parse_rewards(rest)
            if rows:
                out[int(day)] = rows
        _WEEKLY_CACHE = out
    return _WEEKLY_CACHE


# --- reward strings -----------------------------------------------------------------------------------------
def _switch_bits(indices):
    """`juA0Z4m7`: a bit container with 4 switch bits per hex digit, MSB first inside a digit.

    Same encoding as `ffbe_battle._set_switch_bit` (exvius convention) and the client's
    `UserLoginBonusTotalInfo::isValid` (0x1d542d4 -> 0x152b018 decodes digit `index//4`, bit `3-(index%4)`).
    `[]` -> `''` (the client then reports every row invalid, i.e. "no condition").
    """
    digits = []
    for index in sorted({int(i) for i in indices if int(i) >= 0}):
        digit, bit = divmod(index, 4)
        while len(digits) <= digit:
            digits.append(0)
        digits[digit] |= 8 >> bit
    return ''.join('%x' % digit for digit in digits)


def _parse_rewards(text):
    """`kind:id:count[:...]` rows (comma separated) -> reward dicts, keeping unit level/metadata.

    The native tuple grammar is exvius_rewards.parse (it rejects an unknown shape rather than guessing); the
    two-field currency shorthand `30:10000` / `51:2000` is the shipped form for gil and friend points and is
    read with the same convention the engine uses (_parse_reward, ffbe_player.py:1161-1180): the amount is in
    `id` as well as in `count`.
    """
    out = []
    for part in str(text or '').split(','):
        part = part.strip()
        if not part:
            continue
        fields = part.split(':')
        if len(fields) == 2 and all(f.isdigit() for f in fields):
            kind, iid = int(fields[0]), int(fields[1])
            count = iid if kind in (0, 30, 50, 51) else 0
            if count > 0:
                out.append({'kind': kind, 'id': iid, 'count': count})
            continue
        try:
            import exvius_rewards
            out.extend(exvius_rewards.parse(part))
        except Exception as exc:  # noqa: BLE001 - a malformed shipped row is reported, never guessed
            print('JP login bonus: reward row %r skipped (%r)' % (part, exc), flush=True)
    return out


# --- player state -------------------------------------------------------------------------------------------
def _player():
    import ffbe_player as fp
    return fp.State.player


def _block(player):
    """The module's own counters (weekly day + the guards), created on demand.

    `conn_seq`/`crossed_conn` identify a CONNECTION: the login reply (`vw9RP3i4`) arrives after the HOME reply
    of the same connection, so the rows crossed there are keyed by the connection number, not by the day.
    """
    block = player.data.get(STATE_KEY)
    if not isinstance(block, dict):
        block = {}
        player.data[STATE_KEY] = block
    defaults = {'week_day': 0, 'paid_day': '', 'shown_day': '', 'crossed_day': '', 'crossed': [],
                'credited_day': '', 'credited_kinds': [], 'conn_seq': 0, 'crossed_conn': 0}
    for key, value in defaults.items():
        if key not in block or not isinstance(block.get(key), type(value)):
            block[key] = list(value) if isinstance(value, list) else value
    return block


def _count_connection(player, today):
    """+1 total_login_days for ONE more connection on a day `advance_catchup` has already advanced.

    `advance_catchup` is guarded by `last_advance == today` (player_state.py:3351), so the day's first
    connection is counted there and every later connection needs this +1. Nothing is paid here: the ladder's
    idempotence key is still `ladder_bit` (pay_catchup_ladder), so a tier already received is never re-paid.
    `serial_days` is deliberately left alone -- it is the consecutive-DAY counter (68Vn2FrK).
    """
    cu = player.catchup()                     # read-only accessor: the live block when one exists
    if cu is not player.data.get('catchup'):  # no block yet (never advanced): adopt the fresh one
        player.data['catchup'] = cu
    cu['total_login_days'] = int(cu.get('total_login_days', 0) or 0) + 1
    cu['last_advance'] = str(today)
    cu['prev_advance'] = str(today)
    player.dirty = True


def _save(server, player):
    try:
        player.dirty = True
        player.save(server.st.STATE_FILE)
    except Exception as exc:  # noqa: BLE001 - a failed write must not break the reply
        _log(server, 'state save failed %r' % (exc,))


def _credit(player, rows, where):
    """Credit reward dicts through the engine's one grant path. Returns (credited rows, kinds, skipped)."""
    accepted, skipped = [], []
    for row in rows:
        if _known_reward(int(row.get('kind', 0) or 0), row.get('id', 0)):
            accepted.append(row)
        else:
            skipped.append('%s:%s' % (row.get('kind'), row.get('id')))
    credited = player._grant_items(accepted) if accepted else []
    if skipped:
        print('JP login bonus: %s skipped (not in the JP masters): %s' % (where, ', '.join(skipped)), flush=True)
    kinds = {int(row.get('kind', 0) or 0) for row in credited}
    return credited, kinds, skipped


def _credit_groups(player, kinds):
    """The reply groups that PROJECT what was just credited (so the client sees the new values)."""
    groups = {}
    if kinds & (set(CURRENCY_KINDS) | {23}):
        groups.update(player.currency_groups())      # J3pAG0I5 lapis, 3oU9Ktb7 team, Md0N5abE type 23
    if 20 in kinds:
        groups['0dNXQa3R'] = player.item_rows()
    if 21 in kinds:
        groups['MBPCGT84'] = player.equip_item_rows()
    if 22 in kinds:
        rows = player.materia_rows()
        if rows:
            groups['rL81fVUI'] = rows
    if 10 in kinds:
        groups['B71MekS8'] = player._unit_rows()
    if 27 in kinds:
        rows = player.vision_card_rows()
        if rows:
            groups['4hPYneL3'] = rows
    return groups


def _ensure_day(server, new_session=False):
    """Advance the counters for this request and pay what fell due.

    `new_session` is True only for the FIRST HOME update after the login chain (see _note_login_flow): that is
    the connection's arrival. It counts +1 in total_login_days, advances the weekly calendar if this is the
    day's first connection, pays every newly reached ladder tier and decides the popup. A repeated HOME update,
    a return from another scene or a resume (new_session False) does none of that; it only re-serves what the
    connection already produced, because the login reply (`vw9RP3i4`) arrives after this HOME reply.

    Returns {'blocked'}/None when nothing may be served, else the values the reply groups need:
    today, ymd, serial, total, crossed (tier ROW IDS crossed on THIS connection), popup, bits, credited,
    credited_now, changed, week_day, conn, week_due.
    """
    player = _player()
    if player is None:
        return None
    if str(getattr(player, 'mode', 'live')) != 'live':
        return {'blocked': True, 'reason': 'state mode %r' % (getattr(player, 'mode', ''),)}
    today, ymd = _dates()
    if _window_row(ymd) is None:
        global _BLOCKED_LOGGED
        if _BLOCKED_LOGGED != today:
            _BLOCKED_LOGGED = today
            _log(server, 'no appended %s row covers %s -- popup stays closed (deploy build/out/login_bonus/'
                         'F_LOGIN_BONUS_MST.ndjson to the engine data and Ver63_P3raZX89.dat to the client)'
                 % (BONUS_TABLE, ymd))
        return {'blocked': True, 'reason': 'no master window for ' + ymd}

    block = _block(player)
    changed = False
    credited_kinds = set()
    weekly_due = False
    crossed = []
    conn = int(block.get('conn_seq') or 0)

    if new_session:
        # A CONNECTION: one more number, then the day's advance (a no-op when the engine already advanced today).
        conn += 1
        block['conn_seq'] = conn
        due = player.advance_catchup(today, '', 0)
        if not due.get('advanced'):
            _count_connection(player, today)
        changed = True

        # The weekly 7-day calendar: the day's FIRST connection only, one day per local date.
        if str(block.get('paid_day') or '') != today:
            weekly_due = True
            week_day = int(block.get('week_day') or 0) + 1
            if week_day > WEEK_DAYS:
                week_day = 1
            block['week_day'] = week_day
            block['paid_day'] = today
            rows = _weekly().get(week_day) or []
            credited, kinds, _ = _credit(player, rows, 'weekly day %d' % week_day)
            credited_kinds |= kinds
            _log(server, 'week day %d (%s): %s' % (week_day, today, ', '.join(
                '%d:%d x%d' % (r['kind'], r['id'], r['count']) for r in credited) or 'nothing'))

        # The JP 79-tier cumulative ladder: pay every tier reached and not yet paid (the tier's QLfe23bu bit is
        # the idempotence key). pay_catchup_ladder marks the bits; the credit is ours. `crossed` holds the tier
        # ROW IDS (M1nFiTG2 == QLfe23bu): cksL9bW8 is read as a row id by the client (see the docstring), and the
        # day of a tier is not its row id (2 days -> id 1, 3 days -> id 2, 5 days -> id 3 ...).
        for tier in player.pay_catchup_ladder(_tiers()):
            rows = _parse_rewards(str(tier.get('reward') or ''))
            credited, kinds, _ = _credit(player, rows, 'ladder %s days (%s)' % (tier.get('days'), tier.get('reward')))
            credited_kinds |= kinds
            crossed.append(int(tier.get('index') or 0))
            _log(server, 'ladder tier %s (total %s days): %s' % (tier.get('index'), tier.get('days'), ', '.join(
                '%d:%d x%d' % (r['kind'], r['id'], r['count']) for r in credited) or 'nothing'))

        # What was crossed is remembered PER CONNECTION: the login reply that opens the calendar arrives after
        # this HOME reply, so it must still carry those row ids. A later connection that crosses nothing clears it
        # (and then opens no total popup -- the client shows the total scene only for a non-empty cksL9bW8).
        block['crossed'] = crossed
        block['crossed_conn'] = conn
        block['crossed_day'] = today

    # What was credited TODAY is remembered: the payment lands on the connection's first request (HOME), while
    # the login reply that opens the calendar arrives after it and must still carry the new balances.
    if credited_kinds:
        block['credited_day'] = today
        block['credited_kinds'] = sorted(int(kind) for kind in credited_kinds)
    kinds_today = set(int(kind) for kind in (block.get('credited_kinds') or [])) \
        if str(block.get('credited_day') or '') == today else set()

    if changed:
        _save(server, player)
    catchup = player.catchup()
    total = int(catchup.get('total_login_days', 0) or 0)
    # `juA0Z4m7`: every ladder tier already received (days <= total). The scene needs the row it animates to
    # be valid as well as `cksL9bW8` pointing at it, or its confirm button never enables (docstring).
    received = [int(tier.get('bit') or 0) for tier in _tiers() if int(tier.get('days') or 0) <= total]
    serve = [int(i) for i in (block.get('crossed') or [])] if int(block.get('crossed_conn') or 0) == conn else []
    return {'today': today, 'ymd': ymd,
            'serial': int(catchup.get('serial_days', 0) or 0),
            'total': total,
            'crossed': serve,
            'popup': bool(new_session) and (weekly_due or bool(serve)),
            'bits': _switch_bits(received),
            'credited': kinds_today, 'credited_now': set(int(kind) for kind in credited_kinds),
            'changed': changed, 'week_day': int(block.get('week_day') or 0),
            'conn': conn, 'week_due': weekly_due}



# --- reply handlers -----------------------------------------------------------------------------------------
def _home(server, spec, reply_id):
    """`Daud71Hn`: the login-bonus switch, once per CONNECTION (see CONNECTIONS in the module docstring)."""
    if reply_id != HOME_REQUEST or not isinstance(spec, dict):
        return spec
    new_session = _consume_session()
    player = _player()
    if player is None:
        return spec
    info = _ensure_day(server, new_session)
    out = dict(spec)
    rows = out.get(HOME_GROUP)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        rows = [dict(row) for row in rows]
    else:
        rows = [{}]
    today, _ = _dates()
    changed = bool(info and info.get('changed'))
    if info is not None and not info.get('blocked'):
        if info.get('popup'):
            block = _block(player)
            rows[0][HOME_FLAG] = '1'
            block['shown_day'] = today
            changed = True
            if info.get('crossed'):
                _log(server, 'home popup flag set for connection %s (%s): total ladder row ids %s'
                     % (info.get('conn'), today, info['crossed']))
            else:
                _log(server, 'home popup flag set for connection %s (%s): weekly calendar'
                     % (info.get('conn'), today))
        else:
            rows[0][HOME_FLAG] = '0'
    else:
        rows[0][HOME_FLAG] = '0'         # keep today's behaviour (no popup) until the master is deployed
    out[HOME_GROUP] = rows
    if info and info.get('credited_now'):      # the groups the pipeline built are pre-credit: refresh them
        out.update(_credit_groups(player, info['credited_now']))
    if changed:
        _save(server, player)
    return out


def _serve_login(server, spec, reply_id):
    """`vw9RP3i4`: the process day, the consecutive/total counters and THIS connection's crossed tiers + balance."""
    if reply_id != LOGIN_REQUEST or not isinstance(spec, dict):
        return spec
    player = _player()
    if player is None:
        return spec
    info = _ensure_day(server)
    out = dict(spec)
    out.pop(SP_GROUP, None)              # the campaign group must never ride this reply (notes.md SS2.2)
    if info is None or info.get('blocked'):
        return out
    out[OPE_GROUP] = [{OPE_SERIAL: str(info['serial']),
                       OPE_CROSSED: ','.join(str(day) for day in info['crossed']),
                       OPE_PROCESS_DAY: info['ymd']}]
    total_row = {TOTAL_DAYS: str(info['total'])}
    if info.get('bits'):                 # empty string would mean "no tier received" -- omit it instead
        total_row[TOTAL_SWITCH] = info['bits']
    out[TOTAL_GROUP] = [total_row]
    # The balances always ride this reply: the award was credited on this connection's FIRST request (HOME),
    # and the calendar opens on this one, so the top bar must show the paid lapis here even when nothing was
    # paid now.
    out.update(player.currency_groups())
    if info.get('credited'):
        for tag, rows in _credit_groups(player, info['credited']).items():
            out.setdefault(tag, rows)
    if info.get('changed'):
        _save(server, player)
    _log(server, 'login reply %s (connection %s): serial %s, total %s, crossed %s, week day %s'
         % (info['ymd'], info.get('conn'), info['serial'], info['total'], info['crossed'] or '-',
            info.get('week_day')))
    return out

# --- install ------------------------------------------------------------------------------------------------
def install(server):
    global _INSTALLED, _SERVER
    import capture_server as cs
    import ffbe_player as fp
    import ffbe_pipeline as pl
    if _INSTALLED:
        _log(server, 'already installed')
        return
    _SERVER = server

    def _no_calendar(spec, *args, **kwargs):
        """The Global 28-day calendar path: JP has no response class for it and its rewards are Global ids."""
        return spec

    # ffbe_pipeline imported both names by value (ffbe_pipeline.py:43,49) and its Steps call THOSE objects, so
    # both module names must be replaced (the jp_compat.py:140-144 precedent).
    for module in (fp, pl):
        module.serve_login_bonus = _no_calendar
        module.deliver_login_mail = _no_calendar

    inner = cs.reply_pipeline

    def reply_pipeline(spec, *args, **kwargs):
        reply_id = kwargs.get('reply_id')
        if reply_id is None and args:
            reply_id = args[0]
        _note_login_flow(reply_id)      # the login chain arms the next HOME arrival (a CONNECTION)
        out = inner(spec, *args, **kwargs)
        try:
            out = _home(server, out, reply_id)
            out = _serve_login(server, out, reply_id)
        except Exception as exc:  # noqa: BLE001 - the login bonus must never break a reply
            _log(server, 'reply %s failed: %r' % (reply_id, exc))
        return out

    cs.reply_pipeline = reply_pipeline
    _INSTALLED = True
    _log(server, 'installed: weekly %s lapis calendar (once per local day), JP %d-tier ladder counted per '
                 'CONNECTION, popup on the connection that has something to show (%s), English 28-day calendar off'
         % (WEEKLY_REWARDS, len(_tiers()), '/'.join(LOGIN_FLOW_IDS + (INITIALIZE_ID,))))

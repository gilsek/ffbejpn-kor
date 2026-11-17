"""Global-engine -> JP 11.0.0 reply fixes; installed by android_game.start (2026-11-09).

Special challenges ("퀘스트" screen, SpChallengeEntryRequest MTf2j9aK, ffbe_player.serve_sp_challenge).
The engine's F_SP_CHALLENGE_MST is the JP table (build/out/jp_offline/engine/static, docs/plans/2026-11-09-sp-challenge.md),
so the group/challenge ids below are JP ids.
  * Schedule title. Global builds it client-side from a text key (MST_SPCHALLENGE_SCHEDULE_NAME_<scheduleId>,
    F_TEXT_SPCHALLENGE). JP has no text tables: SpChallengeScheduleMstResponse::readParam (0x1dc5d30) reads the
    title from the row itself, token G4L0YIB2 -> SpChallengeScheduleMst::setName. The engine never sent it.
  * Tab. JP SpChallengeScheduleMst::getCategory (0x1c8c584): dispType(8s9wNSpd) 3/4/5 -> category 4/0/5; else
    resetType(sa1IipR6) != 0 -> 1; else persistent(BbnAH74Z) == 1 -> 2, else 3. SpChallengeTopScene tabs
    (getCategoryWithTab, table 0x25c5a44 = 1,2,4,3,5): REGULAR(정기)=1, EVENT(이벤트)=2, BEGINNER(초심자)=4,
    PERMANENT(상시)=3, SPECIAL(스페셜)=5. The engine sends Global's "persistent=1", which JP files under EVENT.
  * Groups. The engine served only Global 1001/1101. Served now: beginner 1001, permanent 1101/1201/4001,
    regular 3001-3007 (JP day sets, three challenges each).
  * Regular reset. The regular groups' progress and claims are cleared every 12 hours (local 00:00 and 12:00).
  * Ticker (cT7S0ikb). JP SpChallengeTicker::getNextTickerLog (0x1a1cfd0) puts LVG65KBQ/Zmka8t36 straight into
    MISSION_SP_CHALLENGE_TICKER_TEXT, with no text lookup, so the Global keys would be shown raw. Cleared.
"""
import time

SCHEDULE_TAG, TICKER_TAG = 'NI12Hvxy', 'cT7S0ikb'
GROUP, NAME = 'zF6QIY2r', 'G4L0YIB2'
DISP_TYPE, RESET_TYPE, PERSISTENT = '8s9wNSpd', 'sa1IipR6', 'BbnAH74Z'
START, END, REWARD_LIMIT = 'VjJQ51uG', 'm8ivD4NX', '9yEe4dt6'
# (dispType, resetType, persistent) per tab
TAB_FLAGS = {'beginner': ('3', '0', '0'), 'permanent': ('0', '0', '0'), 'regular': ('0', '1', '0')}
GROUPS = ([('1001', 'beginner', '초심자 퀘스트')]
          + [('1101', 'permanent', '상급 퀘스트'), ('1201', 'permanent', '전문가 퀘스트'),
             ('4001', 'permanent', '파라미터 퀘스트')]
          + [(str(3000 + i), 'regular', '정기 퀘스트 %d' % i) for i in range(1, 8)])
REGULAR = [g for g, tab, _ in GROUPS if tab == 'regular']
RESET_HOURS = 12
RESET_KEY = 'jp_sp_regular_window'


def _utc_offset():
    """Seconds east of UTC for the device. Python under Chaquopy may not see Android's zone (no TZ variable),
    so ask java.util.TimeZone first."""
    try:
        from java.util import TimeZone
        return int(TimeZone.getDefault().getOffset(int(time.time() * 1000)) // 1000)
    except Exception:
        return int(time.localtime().tm_gmtoff or 0)


def _local(epoch):
    return time.gmtime(epoch + _utc_offset())


def _window():
    """The current 12-hour window, in device local time (00:00-11:59 / 12:00-23:59)."""
    t = _local(time.time())
    return '%s-%d' % (time.strftime('%Y-%m-%d', t), t.tm_hour // RESET_HOURS)


def _window_bounds():
    """(start, end) epoch seconds of the current 12-hour window, local time."""
    off = _utc_offset()
    span = RESET_HOURS * 3600
    start = (int(time.time()) + off) // span * span - off
    return start, start + span


def _fmt(epoch):
    # The JP client prints the schedule dates as sent (the engine's UTC strings showed 21:46 KST as 12:46),
    # so send device-local time.
    return time.strftime('%Y-%m-%d %H:%M:%S', _local(epoch))


def reset_regular(player):
    """Clear the regular groups' progress and claims once per window. True when something was reset."""
    if player is None:
        return False
    now = _window()
    if player.data.get(RESET_KEY) == now:
        return False
    counters = (player.data.get('quest_progress') or {}).get('counters')
    removed = 0
    if isinstance(counters, dict):
        prefixes = tuple('%s/%s/' % (fam, g) for g in REGULAR for fam in ('spchallenge', 'claimed'))
        for k in [k for k in counters if str(k).startswith(prefixes)]:
            del counters[k]; removed += 1
    player.data[RESET_KEY] = now
    player.dirty = True
    print('JP compat: regular quests reset for window %s (%d counter(s) cleared)' % (now, removed), flush=True)
    return True


def install(server):
    import ffbe_player as fp
    import ffbe_pipeline as pl
    flags = {g: TAB_FLAGS[tab] for g, tab, _ in GROUPS}
    names = {g: n for g, _, n in GROUPS}

    def sp_challenge_picked():
        if fp.State.player is None:
            return []
        groups = fp.sp_challenge_tables()['groups']
        picked = [(g, groups[g]) for g, _, _ in GROUPS if groups.get(g)]
        missing = [g for g, _, _ in GROUPS if not groups.get(g)]
        if missing:
            print('JP compat: sp challenge groups missing from F_SP_CHALLENGE_MST: ' + ','.join(missing), flush=True)
        return picked

    original_serve, original_claim, original_progress = fp.serve_sp_challenge, fp.claim_sp_challenge, fp.apply_progress

    def serve_sp_challenge(spec, reply_id):
        if reply_id == fp.SP_CHALLENGE_REQUEST:
            reset_regular(fp.State.player)
        out = original_serve(spec, reply_id)
        if not isinstance(out, dict) or not isinstance(out.get(SCHEDULE_TAG), list):
            return out
        w_start, w_end = _window_bounds()
        now = time.time()
        for row in out[SCHEDULE_TAG]:
            if not isinstance(row, dict):
                continue
            gid = str(row.get(GROUP, ''))
            if gid in flags:
                row[DISP_TYPE], row[RESET_TYPE], row[PERSISTENT] = flags[gid]
            if gid in REGULAR:      # the period shown is the 12-hour reset window
                row[START], row[END], row[REWARD_LIMIT] = _fmt(w_start), _fmt(w_end), _fmt(w_end)
            else:
                row[START], row[END], row[REWARD_LIMIT] = _fmt(now), _fmt(now + 365 * 86400), _fmt(now + 365 * 86400)
            if not row.get(NAME):
                row[NAME] = names.get(gid) or ('퀘스트 ' + gid)
        if TICKER_TAG in out:
            out[TICKER_TAG] = []
        return out

    def claim_sp_challenge(spec, reply_id, plaintext=None):
        if reply_id == fp.SP_CHALLENGE_CLAIM_REQUEST:
            reset_regular(fp.State.player)
        return original_claim(spec, reply_id, plaintext)

    def apply_progress(spec, reply_id, plaintext=None):
        reset_regular(fp.State.player)      # before scoring, so a new window's first clears are kept
        return original_progress(spec, reply_id, plaintext)

    fp.sp_challenge_picked = sp_challenge_picked
    for mod in (fp, pl):
        mod.serve_sp_challenge = serve_sp_challenge
        mod.claim_sp_challenge = claim_sp_challenge
        mod.apply_progress = apply_progress
    print('JP compat: sp challenge groups %s, JP tabs, names, ticker cleared, regular reset every %dh (utc offset %ds, window %s)'
          % (','.join(g for g, _, _ in GROUPS), RESET_HOURS, _utc_offset(), _window()), flush=True)
    install_story_switches(server)
    install_scene_waves(server)
    install_field_treasures(server)
    install_quest_info(server)
    install_dictionary(server)
    install_resource_all(server)
    install_encount(server)
    install_skill_names(server)
    install_shop(server)
    install_stores(server)
    install_slot_expansion(server)
    install_events(server)
    import jp_login_bonus
    jp_login_bonus.install(server)
    # Chamber of Seals (封印の間): the 0xkoNP8U rows SealUtil::getTabMap reads + one-shot test keys.
    import jp_seal_room
    jp_seal_room.install(server)
    # Dimension-gap survival (차원의 틈새): the SurvivalEventInfo lists SurvivalMissionEntryRequest's empty reply needs.
    import jp_survival
    jp_survival.install(server)
    # Rm (map-type event) mission selection by JP area, not the 영문판 mission type 12.
    install_rm_modes(server)
    # Unit conversion (exeType rules + five-key node), EX awakening no-change answer, warehouse records/rename
    # (rules from the lapis JP server, docs/REPORT_11_LAPIS_HANDLER_COMPARISON.md).
    try:
        import jp_unit_fixes
        jp_unit_fixes.install(server)
    except Exception as exc:  # noqa: BLE001
        print('JP unit fixes NOT installed (%r)' % (exc,), flush=True)
    # Requests the engine left unanswered (empty body = client network error): chocobo exploration, transfer
    # code, delete user (refused, save untouched), item world entry/resume/fix with no run, mission break.
    try:
        import jp_missing_handlers
        jp_missing_handlers.install(server)
    except Exception as exc:  # noqa: BLE001
        print('JP missing handlers NOT installed (%r)' % (exc,), flush=True)
    # Refused awakening (★/NV/NV+) and unit fusion: answer with an unchanged result node and give fusion
    # materials back, instead of an empty body or the full unit list (lapis unit.py _refused_safely/_restore).
    try:
        import jp_unit_refusals
        jp_unit_refusals.install(server)
    except Exception as exc:  # noqa: BLE001
        print('JP unit refusals NOT installed (%r)' % (exc,), flush=True)
    # Units with several LBs (CSV id): without this they are served lb_level 0 and the LB crashes the client.
    try:
        import jp_multi_lb
        jp_multi_lb.install(server)
    except Exception as exc:  # noqa: BLE001
        print('JP multi-LB NOT installed (%r)' % (exc,), flush=True)
    # Post-battle LB EXP, TMR (30% chance of +1%) and trust bonus drop (lapis battle_growth.py).
    try:
        import jp_battle_growth
        jp_battle_growth.install(server)
    except Exception as exc:  # noqa: BLE001
        print('JP battle growth NOT installed (%r)' % (exc,), flush=True)


# --- Treasure chests (2026-11-09) --------------------------------------------------------------------------------
# exvius_field_treasures.serve attaches ALL 2,667 Global chest rows (FieldTreasureMstResponse pDFgB3i0) to the login,
# world, home and resource-load replies. The JP 「보물상자 획득 현황」 screen (TreasureChestObtainStateScene::
# setTreasureChestCount) shows the CURRENT town/dungeon and counts every row it was given (Mitra read 0/1923, 0/377,
# 0/128), and the 宝箱 badge (MapEventUtils::getTreasureChestTotalUnopenCount) counted them all (99+).
# JP: on the resource load of a place (jnw49dUq, mission id = town or mission) serve only that place's chests; other
# replies carry no chest list, so the client keeps the last place's list. A chest belongs to a place when the
# catalogue names the town or mission, its map file is one of the town's maps, or (no location recorded) its 7-digit
# id starts with the 4-digit town id (1101013 = Mitra; ids follow that rule in 455 of 470 town-tagged rows).
_EXP_FIX = None


def _exploration_fix():
    global _EXP_FIX
    if _EXP_FIX is None:
        import json as _json, os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jp_exploration_fix.json')
        try:
            with open(p, encoding='utf-8') as fh:
                _EXP_FIX = _json.load(fh)
        except Exception:
            _EXP_FIX = {}
    return _EXP_FIX


TREASURE_GROUP, RESOURCE_LOAD = 'pDFgB3i0', 'jnw49dUq'
_PLACE = {}    # the last place served a chest list (town 4 digits / mission 7-8 digits)


def install_field_treasures(server):
    import json as _json
    import exvius_field_treasures as ft
    import ffbe_pipeline as pl
    from player_state import _load_ndjson
    original = pl.serve_field_treasures
    fix = _exploration_fix()
    fix_missions = {str(k): [str(x) for x in v] for k, v in (fix.get('mission_treasures') or {}).items()}
    fix_stems = {str(k): [str(x) for x in v] for k, v in (fix.get('stem_treasures') or {}).items()}
    stem_by_tid = {}
    for stem, tids in fix_stems.items():
        for tid in tids:
            stem_by_tid.setdefault(tid, set()).add(stem)
    mid_by_tid = {}
    for rmid, tids in fix_missions.items():
        for tid in tids:
            mid_by_tid.setdefault(tid, set()).add(rmid)

    cat_init = ft.catalogue()
    for iid, row in cat_init.items():
        s_extra = stem_by_tid.get(str(iid))
        if s_extra:
            res = [str(x) for x in (row.get('resources') or [])]
            for stem in sorted(s_extra):
                if stem not in res and (stem + '.cpk') not in res:
                    res.append(stem)
            row['resources'] = res
        m_extra = mid_by_tid.get(str(iid))
        if m_extra and (row.get('mission') or row.get('missions') or row.get('town') or row.get('towns')):
            old_m = row.pop('mission', None)
            ms = [str(x) for x in (row.get('missions') or [])]
            if old_m and str(old_m) not in ms:
                ms.append(str(old_m))
            for rmid in sorted(m_extra):
                if rmid not in ms:
                    ms.append(rmid)
            row['missions'] = ms

    def town_files(loc):
        row = _load_ndjson('F_TOWN_MST.ndjson', 'Gh92V3Tx').get(loc) or {}
        maps = _load_ndjson('F_RESOURCE_MAP_MST.ndjson', 'Nnb20keZ')
        out = set()
        for rid in str(row.get('q4f9IdMs') or '').split(','):
            f = str((maps.get(rid) or {}).get('pJ56sAEo') or '')
            if f:
                out.add(f.replace('.cpk', ''))
        return out

    def mission_files(loc):
        out = set()
        try:
            row = _load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').get(loc) or {}
            maps = _load_ndjson('F_RESOURCE_MAP_MST.ndjson', 'Nnb20keZ')
            res_mst = _load_ndjson('F_RESOURCE_MST.ndjson', '9ZCEWn0z')
            for rid in str(row.get('q4f9IdMs') or '').split(','):
                rid = rid.strip()
                if not rid:
                    continue
                for tbl in (maps, res_mst):
                    f = str((tbl.get(rid) or {}).get('pJ56sAEo') or '')
                    if f:
                        out.add(f.replace('.cpk', ''))
        except Exception:
            pass
        return out

    def belongs(row, loc, files):
        iid = str(row.get('id'))
        towns = [str(x) for x in (row.get('towns') or ([row['town']] if row.get('town') else []))]
        missions = [str(x) for x in (row.get('missions') or ([row['mission']] if row.get('mission') else []))]
        res = set(map(str, row.get('resources') or []))
        if loc in towns or loc in missions or (files & res):
            return True
        return (len(loc) == 4 and len(iid) == 7 and iid.startswith(loc)
                and not towns and not missions and not res)

    import player_state as _ps

    _CARRY_KEYS = ((106100100, 3), (106210100, 1))
    _req_ctx = {'debited': {}, 'refresh_items': False}

    def _sync_carry_keys(player, refill_keys=True):
        if player is None or player.mode == 'frozen':
            return
        inv = player.data.setdefault('inventory', {})
        old = inv.get('carry_items')
        old_list = old if isinstance(old, list) else []
        clean = []
        used_orders = set()
        seen_ids = set()
        for row in old_list:
            if not isinstance(row, dict):
                continue
            try:
                disp = int(row.get('disp_order', -1))
                iid = int(row.get('item_id', 0))
                cnt = int(row.get('count', 0))
            except (TypeError, ValueError):
                continue
            if not (0 <= disp < 10) or iid <= 0 or disp in used_orders or iid in seen_ids:
                continue
            owned = player.item_count(20, iid)
            cnt = min(cnt, owned)
            if cnt <= 0:
                continue
            used_orders.add(disp)
            seen_ids.add(iid)
            clean.append({'disp_order': disp, 'item_id': iid, 'count': cnt})

        by_id = {r['item_id']: r for r in clean}
        for key_id, default_cap in _CARRY_KEYS:
            mst = _ps.item_mst(key_id) or {}
            try:
                cap = int(mst.get('DnCP52Jk') or default_cap)
            except (TypeError, ValueError):
                cap = default_cap
            if cap <= 0:
                cap = default_cap
            owned = player.item_count(20, key_id)
            want = min(owned, cap) if owned > 0 else 0
            if want <= 0:
                continue
            if key_id in by_id:
                by_id[key_id]['count'] = want if refill_keys else min(by_id[key_id]['count'], want)
            else:
                free_order = next((i for i in range(10) if i not in used_orders), None)
                if free_order is not None:
                    used_orders.add(free_order)
                    entry = {'disp_order': free_order, 'item_id': key_id, 'count': want}
                    clean.append(entry)
                    by_id[key_id] = entry

        clean.sort(key=lambda r: r['disp_order'])
        if clean != old_list:
            inv['carry_items'] = clean
            player.dirty = True

    if not getattr(_ps.PlayerState, '_jp_carry_wrapped', False):
        _orig_groups = _ps.PlayerState.groups
        _orig_apply_to_reply = _ps.PlayerState.apply_to_reply

        def _wrapped_groups(self):
            _sync_carry_keys(self)
            out = _orig_groups(self)
            out['nE7pV2wr'] = self.carry_item_rows()
            return out

        def _wrapped_apply_to_reply(self, spec, reply_id=None):
            if str(reply_id or '') == 'UM7hA0Zd':
                return spec
            return _orig_apply_to_reply(self, spec, reply_id=reply_id)

        _ps.PlayerState.groups = _wrapped_groups
        _ps.PlayerState.apply_to_reply = _wrapped_apply_to_reply
        _ps.PlayerState._jp_carry_wrapped = True

    def _parse_carry_entries(request):
        entries = []
        for row in ft._rows(request, 'nE7pV2wr'):
            raw = str(row.get('jsvoa0I2') or '').strip()
            if not raw:
                continue
            for part in raw.split(','):
                part = part.strip()
                if not part:
                    continue
                pieces = part.split(':')
                if len(pieces) < 3:
                    continue
                try:
                    disp = int(pieces[0])
                    iid = int(pieces[1])
                    cnt = int(pieces[2])
                except ValueError:
                    continue
                if 0 <= disp < 10 and iid > 0 and cnt >= 0:
                    entries.append({'disp_order': disp, 'item_id': iid, 'count': cnt})
        return entries

    def _finalize_reply(out, reply_id):
        if not isinstance(out, dict) or ft.State.player is None:
            return out
        if _req_ctx['refresh_items'] or str(reply_id or '') in ('29JRaDbd', 'BSq28mwY', 'jnw49dUq'):
            _sync_carry_keys(ft.State.player)
            out = dict(out)
            out['nE7pV2wr'] = ft.State.player.carry_item_rows()
            if _req_ctx['refresh_items']:
                out['0dNXQa3R'] = ft.State.player.item_rows()
        return out

    def serve(spec, plaintext, reply_id=None):
        _req_ctx['debited'].clear()
        _req_ctx['refresh_items'] = False
        out = original(spec, plaintext, reply_id)
        if not isinstance(out, dict) or TREASURE_GROUP not in out:
            return _finalize_reply(out, reply_id)
        out = dict(out)
        if reply_id != RESOURCE_LOAD:
            out.pop(TREASURE_GROUP, None)
            return _finalize_reply(out, reply_id)
        # The JP request names the place in 1zTjkp5B[0].6uIYE15X (town 1101 or a mission id) and lists the
        # resources it loads in XTz8dp5A (Nnb20keZ = F_RESOURCE_MAP ids, e.g. 211201 -> 111020100.cpk).
        loc, files = '', set()
        try:
            req = _json.JSONDecoder().raw_decode(plaintext)[0] if plaintext else {}
            for group, key in (('1zTjkp5B', '6uIYE15X'), ('jQsE54Iz', 'qo3PECw6')):
                rows = req.get(group)
                if isinstance(rows, list) and rows and isinstance(rows[0], dict) and rows[0].get(key):
                    loc = str(rows[0][key]); break
            maps = _load_ndjson('F_RESOURCE_MAP_MST.ndjson', 'Nnb20keZ')
            for r in req.get('XTz8dp5A') or []:
                f = str((maps.get(str((r or {}).get('Nnb20keZ'))) or {}).get('pJ56sAEo') or '')
                if f:
                    files.add(f.replace('.cpk', ''))
        except (ValueError, TypeError, AttributeError, IndexError):
            pass
        if len(loc) == 4:
            files |= town_files(loc)
        elif len(loc) >= 7:
            files |= mission_files(loc)
        cat = ft.catalogue()
        keep = {iid for iid, row in cat.items() if belongs(row, loc, files)}
        if len(loc) in (7, 8):
            # One map file serves several missions (111010100.cpk: 飛空艇・甲板 1110100, 土の神殿・探索 1110104,
            # 上位探索 1110105), so the catalogue lists every chest of that file for all of them: the exploration
            # showed 15 = 111010101-103 (deck) + 401-407 + 501-505 (上位探索). A 9-digit/10-digit chest id starts with
            # the mission that owns it (map.bin holds 401-407 in the exploration's sub-maps, 501-505 in others; the
            # Earth Shrine Exploration wiki lists 7 chests). Own chests when there are any; otherwise drop chests
            # numbered after another mission of the same file.
            clen = len(loc) + 2
            own = {iid for iid in keep if len(iid) == clen and iid[:len(loc)] == loc}
            if own:
                keep = own
            else:
                keep = {
                    iid for iid in keep
                    if not (len(iid) in (9, 10) and iid[:-2] != loc and iid[:-2] in
                            [str(x) for x in (cat[iid].get('missions') or
                             ([cat[iid]['mission']] if cat[iid].get('mission') else []))])
                }
        if loc in fix_missions:
            keep |= set(fix_missions[loc])
        rows = [r for r in out[TREASURE_GROUP] if str(r.get('4tNM5fGC')) in keep]
        out[TREASURE_GROUP] = rows
        _PLACE['loc'] = loc
        print('JP compat: treasure chests for %s: %d of %d' % (loc or '?', len(rows), len(cat)), flush=True)
        return _finalize_reply(out, reply_id)

    pl.serve_field_treasures = serve

    original_credit = ft._credit

    def _wrapped_credit(iid, row):
        credited = original_credit(iid, row)
        if not credited:
            return False
        pos = switch_position(row.get('switch'))
        if pos and pos[0] in ('410', '411'):
            key = '106100100'
            if pos[0] == '410' and _req_ctx['debited'].get(key, 0) > 0:
                _req_ctx['debited'][key] -= 1
            elif ft.State.player is not None and ft.State.player.item_count(20, 106100100) > 0:
                if ft.State.player.spend_item(20, 106100100, 1):
                    _sync_carry_keys(ft.State.player)
                    _req_ctx['refresh_items'] = True
                    print('JP compat: spent 1x 106100100 (Magic Key) for locked chest %s (%s)' % (iid, pos[0]), flush=True)
        return True

    ft._credit = _wrapped_credit

    # exvius_field_treasures._mission_treasures credits a chest only when its "kind:id:count:switch" is in
    # 09HRWXDf.Z7G0yxXe (or R1kg3EBA). JP MissionEndRequest puts each chest under its reward kind's own field
    # (MissionResultInfo: 20 Z7G0yxXe, 21 Mh1BA4uv, 22 30u6XYiB, 23 95JxZzuG, recipes R1kg3EBA): 1110104 sent
    # Mh1BA4uv "21:302000100:1:40002001" (Broadsword chest 111010401), so equipment/materia chests were never
    # credited, their switch stayed off and the chest counted as unopened. Read every kind field.
    original_mt = ft._mission_treasures
    kind_fields = ('Mh1BA4uv', '30u6XYiB', '95JxZzuG')

    def mission_treasures(out, request):
        player = ft.State.player
        if (
            isinstance(request, dict)
            and '09HRWXDf' in request
            and 'nE7pV2wr' in request
            and player is not None
            and player.mode != 'frozen'
        ):
            nodes = ft._rows(request, 'jQsE54Iz')
            mid = str(nodes[0].get('qo3PECw6') or '') if nodes else ''
            attempt = (player.data.get('exvius_repeat') or {}).get('attempt') or {}
            if (
                mid
                and attempt.get('mid') == mid
                and attempt.get('status') == 'completed'
                and attempt.get('normal_rewards_recorded')
                and not attempt.get('carry_settled')
            ):
                entries = _parse_carry_entries(request)
                before = {}
                for row in (player.data.get('inventory') or {}).get('carry_items') or []:
                    if isinstance(row, dict) and row.get('item_id'):
                        iid = int(row['item_id'])
                        before[iid] = before.get(iid, 0) + max(0, int(row.get('count', 0)))
                after = {}
                for row in entries:
                    iid = int(row['item_id'])
                    after[iid] = after.get(iid, 0) + max(0, int(row['count']))
                for iid, b_cnt in before.items():
                    used = max(0, b_cnt - after.get(iid, 0))
                    if used <= 0:
                        continue
                    spend = min(used, player.item_count(20, iid))
                    if spend > 0 and player.spend_item(20, iid, spend):
                        _req_ctx['debited'][str(iid)] = _req_ctx['debited'].get(str(iid), 0) + spend
                        print('JP compat: spent carry item %d x %d on MissionEnd' % (iid, spend), flush=True)
                player.set_carry_items([r for r in entries if r['count'] > 0])
                _sync_carry_keys(player)
                attempt['carry_settled'] = True
                player.dirty = True
                _req_ctx['refresh_items'] = True

        rows = request.get('09HRWXDf') if isinstance(request, dict) else None
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            parts = [str(rows[0].get(k) or '') for k in ('Z7G0yxXe',) + kind_fields]
            joined = ','.join(p for p in parts if p)
            if joined != str(rows[0].get('Z7G0yxXe') or ''):
                request = dict(request)
                request['09HRWXDf'] = [dict(rows[0], Z7G0yxXe=joined)] + rows[1:]
        result = original_mt(out, request)
        if _req_ctx['refresh_items'] and isinstance(result, dict) and player is not None:
            result = dict(result)
            result['0dNXQa3R'] = player.item_rows()
            result['nE7pV2wr'] = player.carry_item_rows()
        return result

    ft._mission_treasures = mission_treasures

    # Dungeon chest switches are per dungeon. F_SWITCH_TYPE_MST: 400 宝箱_ダンジョン, 410 鍵宝箱_ダンジョン,
    # 500 メダル_ダンジョン (scope 0, like the per-mission メイン_C), while town chests are 401/411/501 (scope 1). JP
    # reuses the ids: the deck (111010101-103) and 1110204 (MissionEnd 05:17 sent "40003001,40003002,40003003") both
    # open 40003001-003. The engine keeps one global bit set, so a chest opened in one dungeon showed as opened in
    # every dungeon using that id. Serve these types from the chests credited IN the mission being played: on its
    # resource load (jnw49dUq, after MissionStart) and on the MissionEnd reply; elsewhere they are empty.
    import ffbe_battle as fb
    from ffbe_config import SWITCH_TYPE_FIELD, SWITCH_BITS_FIELD, SWITCH_CONTAINER_MIN
    from player_state import switch_position
    original_switches = pl.serve_switches
    scoped = ('400', '410', '500')

    def _chest_owners(iid, row):
        owners = {str(row['mission'])} if row.get('mission') else set(map(str, row.get('missions') or []))
        if len(iid) in (9, 10) and iid[:-2] in owners:
            return {iid[:-2]}       # deck 111010101 is listed for 1110100/1110104/1110105: owner 1110100
        return owners

    def _alias_key(row):
        sw = row.get('switch')
        rw = row.get('rewards')
        if not sw or not rw:
            return None
        return (str(sw), _json.dumps(rw, sort_keys=True))

    def mission_bits(mid):
        bits = {t: set() for t in scoped}
        if not mid or fb.State.player is None:
            return bits
        cat = ft.catalogue()
        explicit = set(fix_missions.get(mid, ()))
        mid_aliases = set()
        for eiid in explicit:
            k = _alias_key(cat.get(str(eiid)) or {})
            if k:
                mid_aliases.add(k)
        for iid, row in cat.items():
            if mid in _chest_owners(str(iid), row):
                k = _alias_key(row)
                if k:
                    mid_aliases.add(k)
        for iid in (fb.State.player.data.get('exvius_field_treasures') or []):
            sid = str(iid)
            row = cat.get(sid) or {}
            owned = sid in explicit or mid in _chest_owners(sid, row)
            if not owned:
                k = _alias_key(row)
                owned = bool(k and k in mid_aliases)
            pos = switch_position(row.get('switch')) if owned else None
            if pos and pos[0] in bits:
                bits[pos[0]].add(int(pos[1]))
        return bits

    def container(indices):
        width = max([SWITCH_CONTAINER_MIN] + [i // 4 + 1 for i in indices])
        c = '0' * width
        for i in indices:
            c = fb._set_switch_bit(c, i)
        return c

    def serve_switches(spec, reply_id=None):
        out = original_switches(spec, reply_id)
        if not isinstance(out, dict):
            return out
        loc = _PLACE.get('loc') or ''
        if reply_id == RESOURCE_LOAD:
            mid = loc if len(loc) >= 7 else ''
        elif fb.RESULT_TAG in out:
            mid = str(fb.State.player.data.get('exvius_repeat', {}).get('attempt', {}).get('mid') or '')
        else:
            mid = ''
        groups = [k for k, rows in out.items() if isinstance(rows, list)
                  and any(isinstance(r, dict) and SWITCH_TYPE_FIELD in r for r in rows)]
        if not groups and reply_id != RESOURCE_LOAD:
            return out
        bits = mission_bits(mid)
        out = dict(out)
        for key in groups or ['8J1R5PXG']:
            rows = [dict(r) if isinstance(r, dict) else r for r in out.get(key, [])]
            have = set()
            for r in rows:
                if isinstance(r, dict) and str(r.get(SWITCH_TYPE_FIELD)) in bits:
                    t = str(r[SWITCH_TYPE_FIELD]); have.add(t); r[SWITCH_BITS_FIELD] = container(bits[t])
            rows += [{SWITCH_TYPE_FIELD: t, SWITCH_BITS_FIELD: container(bits[t])} for t in scoped if t not in have]
            out[key] = rows
        if reply_id == RESOURCE_LOAD or fb.RESULT_TAG in out:
            print('JP compat: dungeon chest switches for %s: %s' % (
                mid or '-', {t: sorted(v) for t, v in bits.items() if v}), flush=True)
        return out

    pl.serve_switches = serve_switches
    print('JP compat: treasure chest list scoped to the current town/dungeon; chest rewards read from every kind field;'
          ' dungeon chest switches per mission', flush=True)


# --- Mitra story flags (2026-11-09, docs/plans/2026-11-09-town-map.md) -----------------------------------------
# ffbe_player.serve_switches grants the switch that opens FUNCTION_REEL_DIMENSION (the Vortex home tile) on every
# reply: 10005001 (type 100 index 8). In JP that switch is also the completion flag of the Mitra event where Lid
# shows the party the dimensional rift (111020101_event.bin uses 10004001-10004003 and 10005001). With 10005001 on
# and 10004001 off, the town entry script took a later branch: moveMap(66, 4, 8) onto an empty cell of the inner map
# and nothing followed, so the town stayed black. JP: do not pre-grant it; the client's own UpdateSwitchInfo after
# the event still records it (ffbe_battle.record_pushed_switches is a separate step).
STORY_LOCKED = ('10005001',)
STORY_PREREQ = {'10005001': '10004001'}


# --- Scene-only missions with a non-zero wave count (2026-11-15) ---------------------------------------------------
# capture_server._handle treats a mission as scene-only when gQR24kST is 3/5, Y4VoF8yu is 1 and
# mission_wave_count() (F_MISSION_MST.8xi6Xvyk) is 0; otherwise it demands that many combat phases and answers
# "LOCAL BATTLE UNAVAILABLE ... fewer combat phases than the original mission". In the JP table 184 type-5 missions
# (150 in world 10, the story-event bodies such as 52000101; 34 in world 2) carry 8xi6Xvyk 1 or 2, yet every type-3/5
# mission in F_MISSION_PHASE_MST has 0 combat phases (gou39JeI=2) -- the column counts scene phases there. So the
# count is 0 for them. ffbe_battle needs the same value: mission_result_from() marks a scene mission cleared only
# when the count is 0 (else "mission clear withheld: no successful loaded battle" -> no clear mark, next mission
# stays locked; seen on the tablet 2026-11-15 with 52000101).
def install_scene_waves(server):
    import ffbe_battle as fb
    original = server.mission_wave_count

    def mission_wave_count(mission_id):
        row = server.mission_row(mission_id)
        if row is not None and str(row.get('gQR24kST')) in ('3', '5'):
            return 0
        return original(mission_id)

    server.mission_wave_count = mission_wave_count
    fb.mission_wave_count = mission_wave_count
    print('JP compat: scene missions (type 3/5) count 0 combat waves', flush=True)


def install_story_switches(server):
    import ffbe_player as fp
    import ffbe_pipeline as pl
    from player_state import switch_position
    locked = {sid: switch_position(sid) for sid in STORY_LOCKED}
    original = fp.serve_switches

    def serve_switches(spec, reply_id=None):
        p = fp.State.player
        if p is None:
            return original(spec, reply_id)
        real = p.grant_switch
        def grant(stype, index):
            pos = (str(stype), int(index))
            if pos in locked.values() and int(index) not in p.switches.get(str(stype), set()):
                return              # the forced Vortex grant; the story sets this flag itself
            return real(stype, index)
        p.grant_switch = grant
        try:
            return original(spec, reply_id)
        finally:
            del p.grant_switch

    fp.serve_switches = serve_switches
    pl.serve_switches = serve_switches
    # one-time repair: a save where the completion flag is on but the event's first flag is not
    p = server.State.player
    cleared = []
    if p is not None:
        for sid, pos in locked.items():
            pre = switch_position(STORY_PREREQ[sid])
            if pos and pre and pos[1] in p.switches.get(pos[0], set()) and pre[1] not in p.switches.get(pre[0], set()):
                p.switches[pos[0]].discard(pos[1]); p.dirty = True; cleared.append(sid)
        if cleared:
            p.save(server.st.STATE_FILE, force=True)
    print('JP compat: story switch %s not pre-granted (Vortex), cleared from save: %s'
          % (','.join(STORY_LOCKED), ','.join(cleared) or '-'), flush=True)


# --- Town sub-quests (2026-11-10) --------------------------------------------------------------------------------
# A sub-quest accepted from a Mitra NPC (TownUpdateRequest 1sGiqV9T.i9han5Sz) is saved and sent back as
# UserQuestSubInfoResponse (login hQKAwj18 / update JG96kr5C), but the quest list stayed empty. The JP client also
# reads UserQuestInfoResponse (libgame UserQuestInfoResponse::readParam: Z34jU7ue quest id, 4kcAD9fW state,
# VjJQ51uG start, m8ivD4NX end), which the engine never sends. Its tags sit next to the sub-quest ones in the client
# (XoPQ5Rs3, mk5fza4r, hQKAwj18, JG96kr5C), so: XoPQ5Rs3 goes wherever hQKAwj18 goes and mk5fza4r with JG96kr5C.
# State per quest (F_QUEST_MST id): 2 when every step (F_QUEST_SUB_MST) is done, else 1.
# Another overlay already wraps capture_server.reply_pipeline, so that name is replaced directly (wrapping only
# ffbe_pipeline did nothing). Confirmed on the tablet: 「비밀 수첩」 appears in the quest list (user, 2026-11-10).
# The install line goes to files/exvius/jp_quest_trace.log (engine stdout does not reach logcat).
QUEST_SUB_TAGS = {'hQKAwj18': 'XoPQ5Rs3', 'JG96kr5C': 'mk5fza4r'}


def quest_rows(player):
    from player_state import _load_ndjson
    saved = ((getattr(player, 'data', None) or {}).get('exvius_map') or {}).get('quests') or {}
    steps = _load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')
    by_quest = {}
    for row in saved.values():
        by_quest.setdefault(str(row.get('Z34jU7ue')), []).append(row)
    out = []
    for qid in sorted(by_quest):
        all_steps = [sid for sid, r in steps.items() if str(r.get('Z34jU7ue')) == qid]
        done = all_steps and all(str((saved.get(sid) or {}).get('4kcAD9fW')) == '2' for sid in all_steps)
        out.append({'Z34jU7ue': qid, '4kcAD9fW': '2' if done else '1',
                    'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': '2099-12-31 23:59:59'})
    return out


def install_quest_info(server):
    import ffbe_pipeline as pl
    import ffbe_player as fp
    original = pl.reply_pipeline

    def trace(line):                       # engine stdout does not reach logcat: keep a small file
        try:
            import os, time as _t
            path = os.path.join(os.path.dirname(os.path.dirname(server.st.STATE_FILE)), 'jp_quest_trace.log')
            with open(path, 'a', encoding='utf-8') as f:
                f.write(_t.strftime('%H:%M:%S ') + line + chr(10))
        except Exception as e:             # tracing must never break a reply
            print('JP compat: quest trace failed %r' % (e,), flush=True)

    def reply_pipeline(spec, *args, **kwargs):
        out = original(spec, *args, **kwargs)
        if isinstance(out, dict) and any(t in out for t in QUEST_SUB_TAGS) and fp.State.player is not None:
            rows = quest_rows(fp.State.player)
            out = dict(out)
            for sub_tag, tag in QUEST_SUB_TAGS.items():
                if sub_tag in out:
                    out[tag] = rows
        return out

    pl.reply_pipeline = reply_pipeline
    # capture_server does `from ffbe_pipeline import reply_pipeline`, so its own name must be replaced too
    import capture_server as cs
    was = getattr(cs, 'reply_pipeline', None)
    cs.reply_pipeline = reply_pipeline
    trace('installed: capture_server.reply_pipeline was %s' % ('the pipeline one' if was is original else repr(was)))


# --- Collection (도감) registration (2026-11-10) -----------------------------------------------------------------
# The JP 도감 showed nothing registered: the engine never sends the User*DictionaryResponse groups. Each one carries
# KJv6V7G9 = a hex string, bit (8 >> i%4) of character i//4 set when entry i is registered (UserDictionaryBase::
# isRegistered -> 0x152b018, strtol base 16); entry i = the master's QLfe23bu (UnitMst+0x154, ItemMst/EquipItemMst/
# MateriaMst+0x5c, VisionCardMst+0x15c read by getItemIndex). jp_dictionary_index.json maps id -> index from the JP
# masters (F_UNIT/ITEM/EQUIP_ITEM/MATERIA/VISION_CARD_MST). Everything the player owns now is registered and kept in
# the save (data['jp_dictionary']) so used-up items stay registered. Sent with the full user groups (hQKAwj18).
# Monsters (UserMonsterDictionaryResponse HrVT9C6h): KJv6V7G9 = registered bits, z41pMJvC = libra bits (sent empty),
# 4yk1JQBs = knockdown counts as a comma list indexed by the same QLfe23bu (UserMonsterDictionary::getKnockdownCount).
# Kills come from MissionEndRequest 09HRWXDf: nar74pDu (dictionary ids met), f6M1cJgk (monster id:count, mapped to the
# dictionary id through F_MONSTER_MST V9j8wJcC). Past mission ends are read once from the request log folder.
MONSTER_TAG = 'HrVT9C6h'
DICT_TAGS = {'unit': 'VpWnB21X', 'item': '6RQhbe8m', 'equip': 'm4Bk5ex3', 'materia': 'wiTU2Hy1', 'vision': 'ap9do2GX'}
_DICT_INDEX = None


def _dict_index():
    global _DICT_INDEX
    if _DICT_INDEX is None:
        import json as _json, os
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jp_dictionary_index.json'), encoding='utf-8') as fh:
            _DICT_INDEX = _json.load(fh)
    return _DICT_INDEX


def _bits(indices):
    if not indices:
        return '0'
    nib = [0] * (max(indices) // 4 + 1)
    for i in indices:
        nib[i // 4] |= 8 >> (i % 4)
    return ''.join('%x' % n for n in nib)


def dictionary_groups(player):
    idx = _dict_index()
    data = player.data
    seen = data.setdefault('jp_dictionary', {})
    owned = {k: set(map(str, seen.get(k, []))) for k in DICT_TAGS}
    for u in data.get('roster') or []:
        for key in ('master_id', 'first_get_unit_id'):
            if u.get(key):
                owned['unit'].add(str(u[key]))
    inv = data.get('inventory') or {}
    for row in (inv.get('items') or []) + (inv.get('equipment') or []) + (inv.get('carry_items') or []):
        iid = str(row.get('item_id') or '')
        for kind in ('item', 'equip', 'materia'):
            if iid in idx[kind]:
                owned[kind].add(iid)
    for row in data.get('vision_cards') or []:
        if row.get('vc_id'):
            owned['vision'].add(str(row['vc_id']))
    out = {}
    mon = seen.setdefault('monster', {})
    if not seen.get('monster_boot'):
        _boot_monsters(mon)
        seen['monster_boot'] = 1
        player.dirty = True
    mi = {d: idx['monster'][d] for d in mon if d in idx['monster']}
    counts = [0] * (max(mi.values()) + 1 if mi else 1)
    for d, i in mi.items():
        counts[i] = max(1, int(mon[d]))
    out[MONSTER_TAG] = [{'KJv6V7G9': _bits(list(mi.values())), 'z41pMJvC': '0', '4yk1JQBs': ','.join(map(str, counts))}]
    for kind, tag in DICT_TAGS.items():
        ids = sorted(i for i in owned[kind] if i in idx[kind])
        if ids != sorted(map(str, seen.get(kind, []))):
            seen[kind] = ids
            player.dirty = True
        out[tag] = [{'KJv6V7G9': _bits([idx[kind][i] for i in ids])}]
    return out


def record_kills(mon, plaintext):
    import json as _json
    try:
        req = _json.JSONDecoder().raw_decode(plaintext)[0] if isinstance(plaintext, str) else plaintext
    except (ValueError, TypeError):
        return False
    rows = (req or {}).get('09HRWXDf') if isinstance(req, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return False
    idx, row, changed = _dict_index(), rows[0], False
    for d in str(row.get('nar74pDu') or '').split(','):
        if d in idx['monster'] and d not in mon:
            mon[d] = 0; changed = True
    for part in str(row.get('f6M1cJgk') or '').split(','):
        mid, _, n = part.partition(':')
        d = idx['monster_of'].get(mid)
        if d and n.isdigit():
            mon[d] = int(mon.get(d, 0)) + int(n); changed = True
    return changed


def _boot_monsters(mon):
    import json as _json, os
    try:
        folder = os.path.join(os.path.dirname(_SERVER.st.STATE_FILE), 'requests')
        for name in sorted(os.listdir(folder)):
            try:
                with open(os.path.join(folder, name), encoding='utf-8') as fh:
                    rec = _json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and '09HRWXDf' in str(rec.get('plaintext') or ''):
                record_kills(mon, rec['plaintext'])
    except Exception as e:
        print('JP compat: monster history not read %r' % (e,), flush=True)


_SERVER = None


def install_dictionary(server):
    global _SERVER
    _SERVER = server
    import capture_server as cs
    import ffbe_player as fp
    inner = cs.reply_pipeline

    def reply_pipeline(spec, *args, **kwargs):
        plaintext = kwargs.get('plaintext') if 'plaintext' in kwargs else (args[1] if len(args) > 1 else None)
        if fp.State.player is not None and isinstance(plaintext, str) and '09HRWXDf' in plaintext:
            try:
                seen = fp.State.player.data.setdefault('jp_dictionary', {})
                if record_kills(seen.setdefault('monster', {}), plaintext):
                    fp.State.player.dirty = True
            except Exception as e:
                print('JP compat: kill record failed %r' % (e,), flush=True)
        out = inner(spec, *args, **kwargs)
        if isinstance(out, dict) and 'hQKAwj18' in out and fp.State.player is not None:
            try:
                out = dict(out); out.update(dictionary_groups(fp.State.player))
            except Exception as e:      # the collection must never break a reply
                print('JP compat: dictionary failed %r' % (e,), flush=True)
        return out

    cs.reply_pipeline = reply_pipeline
    print('JP compat: collection (도감) groups for units, items, equipment, materia, vision cards, monsters', flush=True)


# --- Resource "download all" (2026-11-10) -------------------------------------------------------------------------
# 도감 → 비전 카드 and the menu entry under 훈장 send ResourceAllDownloadRequest (i0d5n1Dp) with the same body as a
# dungeon resource load (XTz8dp5A resource ids). The engine had no reply for it, so the client showed 「로컬 게임
# 데이터를 불러올 수 없습니다」. Every resource is already local, so answer with the resource-load carrier
# (jnw49dUq) with no encounter, as for a town or map event.
# Then 비전 카드 sends LibraryVisionCardEntryRequest (Lx8F2iU0, Z3R1Cojv.9ZCEWn0z = resource ids): same answer.
RESOURCE_ALL = ('i0d5n1Dp', 'Lx8F2iU0')


def install_resource_all(server):
    import battle_content
    replies = server.State.replies
    for rid in RESOURCE_ALL:
        if rid not in replies and 'jnw49dUq' in replies:
            replies[rid] = battle_content.story_event_bundle(replies['jnw49dUq'])
    print('JP compat: %s answered with the resource-load carrier' % ','.join(RESOURCE_ALL), flush=True)


# --- Exploration random encounters (2026-11-10) ------------------------------------------------------------------
# Explorations never had random battles (Global Offline too): the client picks them from EncountInfoResponse
# (6v0LPiRe), which the engine never sends. libgame: MapManager::checkEncount rolls the tile's F_ENCOUNT_FIELD_MST
# rate, then checkEncountFiled(field) -> EncountInfoList::drawing(field) = a uniform pick among the distinct
# 2fY1IomW (battle group) of the rows whose YzGa63QM == field; the group must be in BattleGroupMst (it is: the
# exploration bundle carries the mission's groups), and checkEnable(field, group, n) needs a row with
# h4Sjf96p == n, n = EncountLogList::getEncountNum (times met this mission; jp_encount.js pins it to 0).
# The original per-area tables are lost (no datamine has them), so: every field id of the JP F_ENCOUNT_FIELD_MST
# (except 99/100, rate 100 %, event tiles) gets every battle group of the mission (2fY1IomW = mission id + 2 digits)
# that the map binary does not use for its own fixed fights (content/field_group_bindings.json).
ENCOUNT_TAG = '6v0LPiRe'
ENCOUNT_FIELDS = (10, 11, 12, 13, 14, 20, 21, 22, 30, 31, 32, 40, 50, 60, 61, 62, 63, 64, 65, 66, 67, 70, 71, 72, 73, 74,
                  75, 110, 120, 130, 140, 150, 210, 211, 212, 220, 221, 222, 230, 231, 232, 240, 241, 242, 250, 251,
                  252, 260, 261, 262, 270, 271, 272, 280, 281, 282)


_TOP_HP, _SIZE, _BIND, _BAD_GROUPS = {}, {}, {}, set()


def _content():
    import os
    import battle_content
    return os.path.join(os.path.dirname(os.path.abspath(battle_content.__file__)), 'content')


def group_top_hp():
    """group id -> HP of its strongest monster; _SIZE: group id -> monster count (content/battle TSVs)."""
    if not _TOP_HP:
        import os
        base = _content()
        hp, part_ok, mon_ok = {}, set(), set()
        with open(os.path.join(base, 'battle', 'F_MONSTER_PARTS_MST.tsv'), encoding='utf-8') as fh:
            for line in fh:
                c = line.split('\t')
                if c[0].isdigit():
                    part_ok.add(c[0])
                if len(c) > 3 and c[3].isdigit():
                    hp[c[0]] = max(hp.get(c[0], 0), int(c[3]))
        with open(os.path.join(base, 'battle', 'F_MONSTER_MST.tsv'), encoding='utf-8') as fh:
            for line in fh:
                c = line.split('\t')
                if c[0].isdigit():
                    mon_ok.add(c[0])
        with open(os.path.join(base, 'battle', 'F_BATTLE_GROUP_MST.tsv'), encoding='utf-8') as fh:
            for line in fh:
                c = line.split('\t')
                if len(c) > 1 and not line.startswith('#'):
                    if c[1] not in part_ok or c[1] not in mon_ok:
                        _BAD_GROUPS.add(c[0])
                    _TOP_HP[c[0]] = max(_TOP_HP.get(c[0], 0), hp.get(c[1], 0))
                    _SIZE[c[0]] = _SIZE.get(c[0], 0) + 1
        for bg in _BAD_GROUPS:
            _TOP_HP.pop(bg, None)
            _SIZE.pop(bg, None)
    return _TOP_HP


def bindings():
    if not _BIND:
        import json as _json, os
        with open(os.path.join(_content(), 'field_group_bindings.json'), encoding='utf-8') as fh:
            _BIND.update(_json.load(fh))
    return _BIND


def _median(v):
    v = sorted(x for x in v if x)
    return v[len(v) // 2] if v else 0


def exploration_pool(mid):
    """Random-encounter groups of exploration `mid`, from the TSVs (no map list of them survives).

    Default: the groups numbered <mid>NN that no map binary uses for a fixed fight (1110304 ダルナキア洞窟:
    goblins/skeletons/wisps of 156-260 HP), minus rare ones over 5x the pool's median HP.
    LATER ADDITIONS: 土の神殿・探索 1110104 is the first area of the game, but its <mid>NN groups are a later
    rework (Wild Rat/Mercury Bat/Gloom Widow/Goblin Mage/Scorpion/Peeping Bear/Skull Jar at 10-12k HP, Golden Bomb
    205k, Ainsel 250k) while the exploration's own map binary names the story groups 111010101-103 (Wererat 100 HP,
    Steel Bat 90 HP) and the boss 111010306 (Belmodar 250 HP). When the <mid>NN pool's median HP is over 10x the
    median of the dungeon's earlier story groups (missions <dun>01..<mid-1>), use those story groups instead:
    2+ monsters, no scenario boss, no rare one (111010307 Mini Tender 777 HP) -> Wererat/Steel Bat/Tarantula.
    """
    mid = str(mid)
    top, bind = group_top_hp(), bindings()
    bound = set().union(*(set(v) for v in bind['missions'].values()))
    bosses = {l['group'] for v in bind.get('scenario_links', {}).values() for l in v}
    scen_all = {str(g) for v in (_exploration_fix().get('mission_scenario_groups') or {}).values() for g in v}
    pool = sorted(
        g for g in top
        if g.startswith(mid) and len(g) in (len(mid) + 1, len(mid) + 2)
        and g not in bound and g not in scen_all
    )
    median = _median(top[g] for g in pool)
    if median:
        pool = [g for g in pool if top[g] <= 5 * median]
    early = []
    if mid[-2:].isdigit():
        dun = mid[:-2]
        story = {dun + '%02d' % i for i in range(1, int(mid[-2:]))}
        early = sorted(
            g for g in top
            if g[:len(mid)] in story and len(g) in (len(mid) + 1, len(mid) + 2)
            and g not in bosses and g not in scen_all
        )
    pref6_fallback = False
    if len(mid) == 8 and not pool and not early and not mid.startswith('1'):
        pref6 = mid[:6]
        early = sorted(
            g for g in top
            if g.startswith(pref6) and len(g) in (8, 9, 10)
            and g not in bound and g not in bosses and g not in scen_all
        )
        pref6_fallback = bool(early)
    smed = _median(top[g] for g in early)
    if smed and (not pool or median > 10 * smed):
        min_size = 1 if pref6_fallback else 2
        return [g for g in early if _SIZE.get(g, 0) >= min_size and top[g] <= 3 * smed], 'story groups (later rework skipped)'
    return pool, 'own groups'


def encount_rows(mid, out):
    import capture_server as cs
    row = cs.mission_row(mid) if hasattr(cs, 'mission_row') else None
    if str((row or {}).get('Y4VoF8yu')) != '2':          # explorations only
        return []
    groups = {str(r.get('2fY1IomW')) for v in out.values() if isinstance(v, list) for r in v
              if isinstance(r, dict) and r.get('2fY1IomW')}
    pool, why = exploration_pool(mid)
    missing = [g for g in pool if g not in groups]
    pool = [g for g in pool if g in groups]
    print('JP compat: encounters %s from %s: %s%s' % (mid, why, pool, (' (not in bundle: %s)' % missing) if missing else ''),
          flush=True)
    return [{'qo3PECw6': str(mid), 'YzGa63QM': str(f), '2fY1IomW': g, 'h4Sjf96p': '0', 'Z0EN6jSh': '0',
             'xqartN26': '0', '6Yc4RkdM': '0', '9BetM2Ds': '', 'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': '',
             '4K8t5dVh': '1', 'V2mCH5UR': '', '14FMQseU': '0'} for f in ENCOUNT_FIELDS for g in pool]


def install_encount(server):
    import capture_server as cs
    import battle_content as bc
    inner = cs.reply_pipeline
    field_bundle = bc.field_mission_bundle
    orig_derive = bc.derive_mission
    scen_map = {
        str(k): [str(x) for x in v]
        for k, v in (_exploration_fix().get('mission_scenario_groups') or {}).items()
    }

    def derive_mission(mission, source, break_status=None, field_groups=None):
        if field_groups is not None:
            top = group_top_hp()
            field_groups = {g for g in field_groups if str(g) in top and str(g) not in _BAD_GROUPS}
        return orig_derive(mission, source, break_status=break_status, field_groups=field_groups)

    bc.derive_mission = derive_mission

    def field_mission_bundle(carrier, mission):
        # the bundle carries only <mid>NN groups and the map's own list; add the chosen pool's groups (and their
        # monsters/skills) so the client can fight them (story groups 1110101xx/1110103xx for 1110104).
        mid = str(mission.get('qo3PECw6'))
        try:
            top = group_top_hp()
            pool, _ = exploration_pool(mid)
            if bc._FIELD_GROUP_BINDINGS is None:
                bc._FIELD_GROUP_BINDINGS = {k: list(v) for k, v in bindings()['missions'].items()}
            have = bc._FIELD_GROUP_BINDINGS.setdefault(mid, [])
            mid_own = [
                g for g in sorted(top)
                if g.startswith(mid) and len(g) in (len(mid) + 1, len(mid) + 2)
            ]
            scen_own = [g for g in scen_map.get(mid, ()) if g in top]
            for g in pool + mid_own + scen_own:
                if g not in have:
                    have.append(g)
        except Exception as e:
            print('JP compat: encounter groups not added %r' % (e,), flush=True)
        return field_bundle(carrier, mission)

    bc.field_mission_bundle = field_mission_bundle

    def reply_pipeline(spec, *args, **kwargs):
        out = inner(spec, *args, **kwargs)
        mid = kwargs.get('mid')
        if (kwargs.get('reply_id') == 'jnw49dUq' and mid and isinstance(out, dict)
                and isinstance(out.get('Bi6hVv34'), list)):
            try:
                rows = encount_rows(str(mid), out)
                if rows:
                    out = dict(out); out[ENCOUNT_TAG] = rows
                    print('JP compat: encounters for %s: %d groups x %d fields' % (mid, len(rows) // len(ENCOUNT_FIELDS), len(ENCOUNT_FIELDS)), flush=True)
            except Exception as e:
                print('JP compat: encounters failed %r' % (e,), flush=True)
        return out

    cs.reply_pipeline = reply_pipeline
    print('JP compat: exploration random encounters (EncountInfo) enabled', flush=True)


# --- Monster skill names by id, monster names (2026-11-10) ---------------------------------------------------------------------
# jp_korean.localize_skills renames a MonsterSkillMstResponse (Wp39QX52) row only when its name equals the JP source
# text. Bundles derived from content/battle/F_MONSTER_SKILL_MST.tsv (explorations, derived missions) carry the
# Global ENGLISH names (110060 Banish), so nothing matched and skills showed in English. Here: by id only.
def install_skill_names(server):
    import json as _json, os
    import capture_server as cs
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jp_monster_skills_ko.json'), encoding='utf-8') as fh:
        skills = _json.load(fh)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jp_monster_names_ko.json'), encoding='utf-8') as fh:
        names = _json.load(fh)
    inner = cs.reply_pipeline

    def reply_pipeline(spec, *args, **kwargs):
        out = inner(spec, *args, **kwargs)
        rows = out.get('Wp39QX52') if isinstance(out, dict) else None
        if isinstance(rows, list):
            new = []
            for r in rows:
                e = skills.get(str(r.get('6E5u1xrs'))) if isinstance(r, dict) else None
                if e and r.get('G4L0YIB2') != e['translation']:
                    r = dict(r, G4L0YIB2=e['translation'])
                new.append(r)
            out = dict(out); out['Wp39QX52'] = new
        # Monster names (MonsterMst bV34YIJQ, MonsterPartsMst wbet57nF) carry the JP text; jp_korean.localize_monsters
        # wraps server.reply_pipeline, which capture_server does not call (it imported the function), so do it here.
        for g in ('bV34YIJQ', 'wbet57nF'):
            rows = out.get(g) if isinstance(out, dict) else None
            if isinstance(rows, list):
                out = dict(out)
                out[g] = [dict(r, G4L0YIB2=names[r['G4L0YIB2']]) if isinstance(r, dict) and r.get('G4L0YIB2') in names else r
                          for r in rows]
        return out

    cs.reply_pipeline = reply_pipeline
    print('JP compat: monster skill names by id (%d), monster names (%d)' % (len(skills), len(names)), flush=True)


# --- Exchange shop: drop offers the JP client cannot draw (2026-11-10, docs/plans/2026-11-10-jp-shop.md step A) ------
# GachaSelectEntryRequest (6nTcSp4R) -> exvius_shop_catalogue.entry sends the Global catalogue (VIP list, recovered
# permanent_shops.json, Global medal fragments). The Obnixus tab (category 4) offered 12 units missing from the JP
# F_UNIT_MST and 4 conflicting ids; opening it crashed in GameUtils::getUnitParamFromLv (SIGSEGV 11-10 11:27:10).
# Here: catalogue() keeps only offers whose rewards and currency exist in the JP masters (jp_valid_ids.json, made by
# build/make_jp_valid_ids.py) and are not conflicting units; shops left without offers are dropped. entry, purchase
# and labels all read the module-global catalogue(), so the screen and the purchase path use the same list.
def install_shop(server):
    import json as _json, os
    from functools import lru_cache
    import exvius_shop_catalogue as sc
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'jp_valid_ids.json'), encoding='utf-8') as fh:
        data = _json.load(fh)
    with open(os.path.join(here, 'jp_shops.json'), encoding='utf-8') as fh:
        jp_shops = _json.load(fh)
    names = jp_shops['names']
    valid = {int(k): set(v) for k, v in data['kinds'].items()}
    conflict = set(data['conflict_units'])
    original = sc.catalogue
    if hasattr(original, '__wrapped__'):
        original.cache_clear()

    def known(kind, iid):
        kind, iid = int(kind), str(iid)
        if kind == 10 and iid in conflict:
            return False
        ids = valid.get(kind)
        return ids is None or iid in ids     # kinds without a JP table (lapis 50, gil 30, ...) are kept

    @lru_cache(maxsize=1)
    def catalogue():
        details, products, offers = original()
        dropped = {}
        kept_offers = {}
        for pid, offer in offers.items():
            bad = [(r['kind'], r['id']) for r in offer['rewards'] if not known(r['kind'], r['id'])]
            kind, currency = offer['cost']
            if not known(kind, currency):
                bad.append(('cost', currency))
            if bad:
                dropped[pid] = bad
            else:
                kept_offers[pid] = offer
        kept_products = [p for p in products if str(p['jPV7Xc4N']) in kept_offers]
        live = {str(p['3X1gLufw']) for p in kept_products}
        kept_details = [d for d in details if str(d['3X1gLufw']) in live]
        titles = {'VIP Shop': 'VIP 상점', 'EX Coin Shop': 'EX 코인 상점', 'Daily Coin Shop': '데일리 코인 상점'}
        cost_of = {o['detail']: o['cost'] for o in kept_offers.values()}
        for d in kept_details:
            kind, currency = cost_of[str(d['3X1gLufw'])]
            title = titles.get(d['6uvHX2JG']) or (int(kind) == 20 and names.get('20:%s' % currency))
            if title:
                d['6uvHX2JG'] = title
            if d['JV8AIH3n'] == '6':
                d['JV8AIH3n'] = '4'     # JP category 6 is the ギルで購入 tile: gil shop only
        print('JP compat: exchange shops %d/%d, offers %d/%d kept (dropped %d: %s)'
              % (len(kept_details), len(details), len(kept_offers), len(offers), len(dropped),
                 ', '.join('%s=%s' % (pid, bad) for pid, bad in list(dropped.items())[:12])), flush=True)
        # JP permanent shops (jp_shops.json, made by build/make_jp_shops.py from saved guide pages) go first.
        add_d, add_p = [], []
        for index, shop in enumerate(jp_shops['shops']):
            did = str(851000000 + index)
            kind, currency = shop['currency']
            add_d.append({'3X1gLufw': did, 'X1IuZnj2': '0', 'JV8AIH3n': str(shop['category']),
                          'Z0EN6jSh': '0', 'fSxqkF10': '0', 'uYcL8IQ1': '-1', '6uvHX2JG': shop['name'],
                          'VjJQ51uG': sc.START, 'm8ivD4NX': sc.END, '0GgK6ytT': '%d:%s' % (kind, currency)})
            for pos, row in enumerate(shop['products']):
                pid = str(951000000 + index * 1000 + pos)
                limit = int(row['limit'])
                add_p.append({'jPV7Xc4N': pid, '3X1gLufw': did, 'P4puB2ch': row['reward'],
                              'e4mG8jTc': str(row['price']), 'uYcL8IQ1': str(-1 if limit == 2147483647 else limit),
                              'Z0EN6jSh': '0', '6uvHX2JG': '', 'VjJQ51uG': sc.START, 'm8ivD4NX': sc.END,
                              'fbcj5Aq9': '', 'JasF1S3u': ''})
                kept_offers[pid] = {'detail': did, 'rewards': sc.parse(row['reward']), 'cost': (kind, str(currency)),
                                    'price': int(row['price']), 'limit': limit,
                                    'monthly': shop['reset_months'] or False}
        all_d = add_d + kept_details
        all_p = add_p + kept_products
        for n, d in enumerate(all_d):
            d['Z0EN6jSh'] = str(n + 1)
        for n, p in enumerate(all_p):
            p['Z0EN6jSh'] = str(n + 1)
        print('JP compat: JP exchange shops added: %s'
              % ', '.join('%s(cat %s, %d)' % (s['key'], s['category'], len(s['products'])) for s in jp_shops['shops']),
              flush=True)
        return all_d, all_p, kept_offers

    @lru_cache(maxsize=1)
    def labels():
        # Product names for the Frida hook on GachaSelectProductMst (summon_menu.js), in Korean from the JP masters.
        result = {}
        for pid, offer in catalogue()[2].items():
            texts = []
            for row in offer['rewards']:
                name = names.get('%d:%s' % (row['kind'], row['id'])) or str(row['id'])
                if row['count'] > 1:
                    name += ' x' + str(row['count'])
                texts.append(name)
            title = ', '.join(texts)
            result[pid] = {'name': title, 'description': title + '을(를) 교환합니다.'}
        return result

    pay = sc._pay

    def _pay(materials=(), gil=0):
        # The catalogue purchase pays every non-lapis cost through _pay(materials); gil (kind 30) goes to gil=.
        rest = [r for r in materials if int(r['kind']) != 30]
        gil = int(gil) + sum(int(r['count']) for r in materials if int(r['kind']) == 30)
        return pay(rest, gil)

    sc.catalogue = catalogue
    sc.labels = labels
    sc._pay = _pay
    print('JP compat: exchange shop filtered by JP masters (%s), Korean labels %d'
          % (', '.join('%d:%d' % (k, len(v)) for k, v in sorted(valid.items())), len(names)), flush=True)


# --- Event merchants and select prism on JP tables (2026-11-10, docs/plans/2026-11-10-jp-shop.md step B) ----------
# The engine's F_TOWN_STORE_MST, F_STORE_ITEM_MST, F_MEDAL_EXCHANGE_MST, F_SHOP_MST, F_EXCHANGE_SHOP_ITEM_MST and
# F_GACHA_SELECT_UNIT_MST are the JP tables (build/apply_jp_masters.py; Global copies kept as .ndjson.global).
# * archived_store_schedules joined the Global F_GACHA_STORE_MST, which JP does not have. JP: every medal merchant
#   (kaG4xf3I=5) with a linked medal product (136 merchants, one currency each) is open 2020..2099, base = itself.
# * variable_store_check: the hard-coded 7000458 star quartz merchant is not in JP (its stock is the JP 스타쿼츠
#   exchange shop in jp_shops.json); the minister 900122 -> 900105 keeps its Korean lines.
# * Select prism: JP has no F_GACHA_SELECT_PRISM_MST; the request is declined (the engine's own decline row).
STORE_LINES = {'900105': ('내 소장품을 성석의 조각과 기꺼이 바꿔 줄게, 쿠포!',
                          '성석의 조각을 모으면 또 찾아와 줘, 쿠포!')}
FIXED_STORES = (('900122', '900105'),)


def install_stores(server):
    import exvius_actions as ea
    import exvius_actions_shops as sh
    import exvius_gacha_select as gs
    from functools import lru_cache

    @lru_cache(maxsize=1)
    def merchants():
        # {store id: medal currency id} for medal merchants (kaG4xf3I=5) with at least one linked product.
        medals = sh._table('F_MEDAL_EXCHANGE_MST', 'S21FT3L8')
        stores = sh._table('F_TOWN_STORE_MST', 'Z20mNDvL')
        currency = {}
        for row in sh._rows('F_STORE_ITEM_MST'):
            sid = str(row.get('Z20mNDvL'))
            product = medals.get(str(row.get('6uIYE15X'))) if str(row.get('YWF08vZS')) == '50' else None
            if product and stores.get(sid, {}).get('kaG4xf3I') == '5':
                currency.setdefault(sid, str(product['ak2dhKm3']))
        return currency

    def schedule(base, sid):
        hello, bye = STORE_LINES.get(sid, ('', ''))
        return {'Z20mNDvL': base, 'za2xsDj5': sid, 'w7VR6ypY': '0',
                'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': '2099-12-31 23:59:59',
                'suR36Jpm': '20:' + merchants()[sid], '89YmCAzo': hello, '0euar5mZ': bye}

    @lru_cache(maxsize=1)
    def archived_store_schedules():
        fixed = {sid for _, sid in FIXED_STORES}
        return [schedule(sid, sid) for sid in sorted(merchants(), key=int) if sid not in fixed]

    @sh._action
    def variable_store_check(spec, req):
        out = sh._reply(spec)
        out['3VS1Bhmf'] = ([schedule(base, sid) for base, sid in FIXED_STORES if sid in merchants()]
                           + [dict(r) for r in archived_store_schedules()])
        return out

    def select_prism(spec, req):
        sh._note('Select prism: JP has no F_GACHA_SELECT_PRISM_MST; declined')
        out = ea._refresh(spec)
        out['tCq8mcNo'] = [{'UJz5QED2': '', 'oY0vAuE9': '0', 'zoU5J3Kq': '1',
                            'X1IuZnj2': '0', 'nqzG3b2v': '0', 'zJ1A6HXm': '0', '2RtVPS3b': '0'}]
        return out

    sh.archived_store_schedules = archived_store_schedules
    sh.variable_store_check = variable_store_check
    gs.select_prism = select_prism
    for rid, fn in (('i0woEP4B', variable_store_check), ('bgast6dR', select_prism)):
        sh.HANDLERS.get(rid) and sh.HANDLERS.__setitem__(rid, fn)
        gs.HANDLERS.get(rid) and gs.HANDLERS.__setitem__(rid, fn)
        ea.HANDLERS[rid] = fn          # exvius_actions merges family handlers only for ids it does not have yet
    print('JP compat: event merchants %d (JP tables, always open), fixed %s, select prism declined'
          % (len(merchants()), ','.join(i for _, i in FIXED_STORES)), flush=True)


# --- Slot expansion (2026-11-10) ---------------------------------------------------------------------------------
# The shop's 枠拡張 screen sends ShopUseRequest {gdR2tJI9: shop id, Qy5EvcK1: slots to add}; the engine only knew the
# orb rows and refused (device log 13:27:19 shop 11, Qy5EvcK1 425/295). Read from JP 11.0.0 libgame:
#   ShopExtensionSelectScene::initialize 0x192f930: shop "10" UNIT, "11" ITEM, "12" EQUIP, "13" ABILITY (materia),
#     "14" FRIEND, "15" MATERIAL; slider max = (GameUtils::getLimitFrameCnt - getMaxFrameCnt) / ShopMst param.
#   updateLabel 0x1930f54: lapis = useDia * n, slots = param * n. ShopExtensionConfirmScene::touchEnded 0x1932adc:
#     Qy5EvcK1 = param * n.
#   GameUtils::getMaxFrameCnt 0x1484df0 = UserLevelMst base + UserTeamInfo *CntAdd;
#     getLimitFrameCnt 0x1484ef0 = base + *CntExt -> Ext is the most slots that can be added.
#   UserTeamInfoResponse::readParam 0x1dd1fec: T1Lm7WdD +0x58 UnitCntAdd, NULFd7v3 +0x5c StorageCntAdd,
#     tsT4vP7w +0x60 FriendCntAdd, Xu7L1dNM +0x64 EquipItemCntAdd, 4BI0WKjQ +0x68 ItemCntAdd,
#     92LoiU76 +0x6c MateriaCntAdd, 9w3Pi6XJ +0x70 MaterialItemCntAdd (getters 0x1d3d00c..0x1d3d06c).
#   UserLevelMstResponse::readParam 0x1dcdff8: F_TEAM_LV_MST base/ext columns below.
# So T1Lm7WdD / NULFd7v3 are expansion amounts, not the roster size the engine sent (it made the unit box +13).
SLOT_SHOPS = {   # shop id: (counts key, team-row token, F_TEAM_LV_MST base, ext)
    '10': ('unit_add', 'T1Lm7WdD', 'Sp8s3BoH', 'Xek7S1An'),
    '11': ('item', '4BI0WKjQ', 'ceL1tE3J', 'V1ye9G7x'),
    '12': ('equip_item', 'Xu7L1dNM', 'ay2D7mA0', 'z1ehN4mk'),
    '13': ('materia', '92LoiU76', '19ykfMgL', '9fwYE75W'),
    '14': ('friend', 'tsT4vP7w', 'Q7Lwvb9q', 'f14WH76D'),
    '15': ('material_item', '9w3Pi6XJ', '3GFW75z9', 'K3oJ2jwP'),
}


def expand_slots(player, shop_id, slots):
    """Add `slots` to one bag for the shipped lapis price. Returns a short result string; changes nothing on refusal."""
    import player_state as ps
    key, _, base_col, ext_col = SLOT_SHOPS[str(shop_id)]
    row = ps.shop_mst(shop_id) or {}
    try:
        step, price_each, slots = int(row.get(ps.SHOP_PARAM_TOKEN)), int(row.get(ps.SHOP_USE_DIA_TOKEN)), int(slots)
    except (TypeError, ValueError):
        return 'refused: bad row or amount (%r, %r)' % (row, slots)
    lv = ps.team_level_mst(player.data['rank']['level']) or {}
    ext = int(lv.get(ext_col) or 0)
    counts = player.data.setdefault('counts', {})
    now = int(counts.get(key, 0) or 0)
    if step <= 0 or slots <= 0 or slots % step:
        return 'refused: %d slots is not a multiple of %d' % (slots, step)
    if now + slots > ext:
        return 'refused: %s +%d over the cap (now +%d, max +%d)' % (key, slots, now, ext)
    price = price_each * slots // step
    if player.mode == 'frozen' or not player.spend_lapis(price):
        return 'refused: %d lapis needed' % price
    counts[key] = now + slots
    player.dirty = True
    return '%s +%d -> +%d (base %s, max +%d), spent %d lapis' % (key, slots, now + slots, lv.get(base_col), ext, price)


def install_slot_expansion(server):
    import json
    import player_state as ps
    cls = ps.PlayerState
    original_use, original_team = cls.apply_shop_use, cls._team_row

    def apply_shop_use(self, spec, reply_id=None, plaintext=None):
        if str(reply_id) == ps.SHOP_USE_REQUEST and plaintext:
            try:
                body = (json.JSONDecoder().raw_decode(plaintext)[0].get('L5Nj3cKE') or [{}])[0]
            except Exception:  # noqa: BLE001 - an unreadable body falls through to the engine's own handling
                body = {}
            shop = str(body.get(ps.SHOP_ID_TOKEN))
            if shop in SLOT_SHOPS:
                print('    slot expansion: shop %s %s' % (shop, expand_slots(self, shop, body.get('Qy5EvcK1'))),
                      flush=True)
                out = dict(spec) if isinstance(spec, dict) else {}
                out['3oU9Ktb7'] = [self._team_row()]   # apply_to_reply projects the team row and lapis
                return out
        return original_use(self, spec, reply_id, plaintext)

    def _team_row(self):
        row = original_team(self)
        counts = self.data.get('counts', {})
        row['T1Lm7WdD'] = str(int(counts.get('unit_add', 0) or 0))
        row['NULFd7v3'] = str(int(counts.get('storage_add', 0) or 0))
        return row

    cls.apply_shop_use, cls._team_row = apply_shop_use, _team_row
    print('JP compat: slot expansion shops %s (JP F_SHOP_MST price, F_TEAM_LV_MST cap)' % ','.join(SLOT_SHOPS),
          flush=True)


# --- Event gate (2026-11-11) ----------------------------------------------------------------------------------
"""JP event gate: open ONE JP event area on the Event tab (draft, 2026-11-11).

PASTE THIS WHOLE FILE into build/engine_overlay/jp_compat.py (append at the end), then add ONE line to
jp_compat.install(): ``install_events(server)`` (next to install_stores / install_slot_expansion).
It does NOT touch any engine file: it rebinds module attributes of the already-imported English engine,
which is the pattern jp_compat already uses (jp_compat.py:140-144, 371-372, 898-900, 1050).

Why the constants must be rebound on the *importing* module, not on ffbe_config
--------------------------------------------------------------------------------
* ffbe_config.py:1083 ``EVENT_GATE_AREAS`` (default "970,888,734"), :1084 ``EVENT_GATE_TAB``,
  :1085 ``EVENT_GATE_KIND``, :1096 ``EVENT_GATE_ART``, :1109 ``EVENT_CURRENCY`` are built at import time.
* ffbe_player.py:19 and ffbe_battle.py:18 both do ``from ffbe_config import *``, which COPIES the names
  into each module's globals. Rebinding ffbe_config.EVENT_GATE_AREAS afterwards does not change those
  copies, so the names that matter are ``ffbe_player.EVENT_GATE_AREAS`` and ``ffbe_battle.EVENT_CURRENCY``.
* The functions read the module global AT CALL TIME, never a baked default argument:
    - ffbe_player.py:2841 ``for area in (EVENT_GATE_AREAS if areas is None else areas)`` (default is None)
    - ffbe_player.py:2886 ``load_policy(DATA_ROOT, EVENT_GATE_AREAS)``
    - ffbe_player.py:2933-2942 tab / kind / window / ``EVENT_GATE_ART`` / ``event_gate_art(area)``
    - ffbe_battle.py:183-189 ``EVENT_CURRENCY``
  So the rebinding below takes effect on the next reply without touching the pipeline.
* ffbe_pipeline.py:21 also star-imports, and :37-54 imports ``serve_event_gate`` BY NAME; its Step
  (:326-329) calls that function object, whose ``__globals__`` is ffbe_player's dict -- constant patches
  are therefore visible with no wrapper. If you ever WRAP ``serve_event_gate``, assign the wrapper on
  BOTH ``ffbe_player`` and ``ffbe_pipeline`` (precedent: jp_compat.py:141-144).

Why the event ARCHIVE must be switched off here
-----------------------------------------------
* local_game.py:39 sets ``os.environ['FFBE_DATA'] = root`` and :45 ``setdefault('EXVIUS_EVENT_ARCHIVE', 1)``.
  So on the JP app DATA_ROOT IS set and the archive path in ffbe_player.py:2890-2894 is live unless a
  ``state/exvius_events.json`` exists. With the stock constants that path serves the GL
  ``event_archive.json`` (757 areas); simulated locally against the JP masters it produced 8,008 gate
  rows / 5,577,501 bytes per RoutineWorldUpdate reply. Setting the env to '0' here is honoured because
  the check reads ``os.environ`` at call time.
* ``load_policy`` is also rebound to the constant list so a leftover policy file can never override
  ``JP_EVENT_AREAS`` (ffbe_player.py:13 imports it; :2886 is its only caller).

Art
---
* ``event_gate_art`` (ffbe_player.py:2861-2865) returns ``event_art.json``'s GL ``Banner-*.png`` without
  checking that JP ships it -- JP ships none of them, so the tile would 404 (blank plate; see
  capture_server.py:557-574 and the operator report quoted there). Returning None falls back to
  ``EVENT_GATE_ART`` = the client's own dummy plate, ``spd_bn_list_dummy.png``, which IS in the JP pack
  (cpk_extract/common_lang/area/Ver11_spdungeon1_common/) and is served by basename
  (capture_server.py:568, roots ffbe_config.py:59-60). If JP_EVENT_RAID is True the raid menu background
  ``raid_king_mog.png`` is used instead and that file is also shipped
  (cpk_extract/common_lang/area/Ver49_raid1_common/). An EMPTY art string would just 404 the same way
  (blank tile, no crash); the dummy is used because it is a file that exists.
"""

# ---------------------------------------------------------------------------------------------------
# The ONE place the JP event tile list is changed.
# JP_EVENT_AREAS_MODE = 'all' opens every area the gate can serve (computed from the JP masters at install
# time, seal chambers excluded); 'legacy' restores the old single-tile tuple in JP_EVENT_AREAS.
JP_EVENT_AREAS_MODE = 'legacy'
JP_EVENT_AREAS = ('734',)                # JP_EVENT_AREAS_MODE == 'legacy' list (pre-2026-11-12 behaviour)
JP_EVENT_AREA_FILTER = {'9Pb24aSy': '2',    # F_AREA_MST world (getAreaMstList reads world 2)
                        'Esxe71j3': '21'}   # sp dungeon (次元の狭間) subtype
JP_EVENT_TAB = '1'                       # qnUhs32P default = 최신 (GATE_TAB_INFO index 0 -> id 1; JP_EVENT_TAB_RULES)
JP_EVENT_KIND = '1'                      # Z0EN6jSh (+0x100 1/2 selector)
JP_EVENT_ART = 'spd_bn_list_00003.png'   # real banner in the JP spdungeon1.cpk TOC (70,072 B); the old
                                         # spd_bn_list_dummy.png is a blank plate (2026-11-12 crash report)
JP_EVENT_CURRENCY = ''                   # GL item 310001240 does not exist in JP F_ITEM_MST -> off
JP_EVENT_RAID = True                     # 734 raid ON; GL-absent reward rows/banner are pruned (_jp_raid_event)
JP_EVENT_MISSION_LIMIT = 0               # 0 = every mission row (see install_mission_cap's warning)

# Gate row end date. The engine sends ffbe_config.EVENT_GATE_WINDOW_END = "2100-01-01 00:00:00"
# (ffbe_config.py:1098 -> ffbe_player.py:2936-2939 `m8ivD4NX`/`V48um7Jw`/`7Gvw6J82`), and the JP client reads
# that CompletedDate as a 32-BIT epoch: SpDungeonCondMst::getRestTime (libgame.so 0x1c89088) does
# `ldr w8,[x19,#0x60]`, so the 2100 epoch 4102444800 wraps to a negative int and the tile's remaining time
# reads 0 (and the tile can drop out of the list). 2037-12-31 23:59:59 = 2145916799 < 2^31-1 fits.
JP_GATE_WINDOW_END = '2037-12-31 23:59:59'

# Rm (map-type event) areas. `jp_rm_areas.json` beside this file lists every area the gate touch branch can
# open as Rm: rm_areas.tsv rows whose FIRST mission subtype is 3 (the 5040 branch, not the subtype-12 parade
# one) that ship both map_files and a cpk (build/make_jp_rm_areas.py -> 56 areas; 725/729 lack a cpk). The
# file is baked into app.imy; a bare engine without it falls back to the original single test area 5040
# (鳴り止まぬ幼雷, notes: build/out/vortex_season/rm_mode/notes.txt 5절, entry.txt 0/1절).
_RM_AREA_FALLBACK = ('5040',)


def _jp_rm_area_list():
    """The sorted Rm area tuple from jp_rm_areas.json (numeric order), or the 5040 fallback."""
    import json as _json
    from pathlib import Path
    path = Path(__file__).resolve().parent / 'jp_rm_areas.json'
    try:
        rows = _json.loads(path.read_text(encoding='utf-8'))
        areas = tuple(sorted({str(a).strip() for a in rows if str(a).strip()} | {'725', '729'}, key=lambda a: int(a)))
    except (OSError, ValueError, TypeError):
        return _RM_AREA_FALLBACK
    return areas or _RM_AREA_FALLBACK


JP_RM_TEST_AREAS = _jp_rm_area_list()
JP_RM_WINDOW = ('2020-01-01 00:00:00', '2037-12-31 23:59:59')  # VjJQ51uG / m8ivD4NX

# The area the client is entering, written by the Frida gate-touch hook (build/frida/jp_offline.js) because
# RmEntryRequest (wx5sg9ye) carries no area id and RmEventInfo is one singleton. The file sits in the engine's
# writable root beside state/ (android: files/exvius/, local_game.py -> FFBE_DATA). JP_RM_AREA_FILE overrides
# it for tests/debug.
JP_RM_AREA_NAME = 'jp_rm_area.txt'


def _jp_rm_area_path(state_file=None):
    """Path of the Frida-written area file: <writable root>/jp_rm_area.txt (files/exvius on device)."""
    import os
    path = os.environ.get('JP_RM_AREA_FILE')
    if path:
        return path
    if not state_file:
        try:
            import ffbe_state
            state_file = ffbe_state.STATE_FILE
        except Exception:
            return None
    if not state_file:
        return None
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(state_file))), JP_RM_AREA_NAME)


def _jp_rm_area_id(state_file=None):
    """The area id the client just entered, or '' when the file is absent/unreadable."""
    path = _jp_rm_area_path(state_file)
    if not path:
        return ''
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError:
        return ''

# Every tile-art name that is safe to hand the JP client: files the JP pack actually ships (the client
# resolves CRI names, so a name it lacks makes getOrCreateSpriteBatchNode return null). `event_<area>.png`
# (GL raid art) is NOT in this set; _jp_gate_fix_art serves it under a registered stand-in instead
# (build/make_jp_event_art.py -> jp_event_art.json), falling back to JP_EVENT_ART.
JP_GATE_SAFE_ART = frozenset((
    'spd_bn_list_00003.png',             # JP_EVENT_ART; the 226 row's own art
    'spd_bn_top_00003.png',              # the 899 row's own art
    'spd_bn_list_dummy.png', 'spd_bn_top_dummy.png',
))
# 734's raid background `raid_king_mog.png` lives in raid1.cpk, which the gate list has NOT mounted: on device
# (2026-11-14) the season-1 latest tab drew JP_EVENT_ART_MISS "raid_king_mog.png" and a blank card. The tile
# therefore takes its by_area banner like every other row; the raid screens keep the raid background below.
JP_RAID_RANKING_BG = {'734': 'raid_king_mog.png'}

# GateScene main tabs. The id is the value the client compares in `GateScene::setLayoutList` (`libgame.so`
# 0x1bdd904: `cmp w9,[cond+0x28]`), i.e. `SpDungeonCondMst.qnUhs32P`. The display order is NOT the id, and
# the ids 2/5 in GATE_TAB_INFO are never compared: for the two tabs that have a sub-tab bar the filter value
# is computed from the selected SUB tab (0x1bdd6e8-0x1bdd710):
#
#   main index 1 (복각):  qnUhs32P == 6 + m_selectedSubTabIndex    -> 6..10  (이벤트/획득/각성/무기/강화)
#   main index 2 (육성):  qnUhs32P == 11 + m_selectedSubTabIndex   -> 11..12 (육성/브레이브)
#   other indices:        qnUhs32P == GATE_TAB_INFO[index]         -> 최신=1, 강적=3, 스페셜=4
#
# (GATE_TAB_INFO 0x257e9dc is int (0,1),(1,2),(2,5),(3,3),(4,4); `GateUtil::getTabMap` 0x1525c40 builds the
# std::map from it and `setLayoutList` reads the map only in the `other indices` branch. GATE_TAB_NAME_1..5 =
# 최신/복각/육성/강적/스페셜, and setLayoutSubTab 0x1be0ecc builds 5 복각 sub tabs and 2 육성 sub tabs;
# `touchEnded` 0x1be03a4 sets m_selectedMainTabIndex and zeroes m_selectedSubTabIndex, so a main tab opens on
# its FIRST sub tab.)
#
# A row with qnUhs32P 2 or 5 therefore matches NO selectable (main, sub) pair at all -- that is why 복각/육성
# were empty on the tablet (2026-11-12) while 최신/강적/스페셜 drew tiles. The archive keeps the semantic main
# tab 1..5; `_jp_gate_wire_tab` translates it to the value the client actually compares.
# Per-area ids are authored in jp_event_groups.json (`tab`) by build/make_jp_event_groups.py; the rules below
# are only the fallback for an unknown/missing data file. `_jp_gate_tab` consults the archive first.
JP_EVENT_TAB_RULES = {
    'exact': {'734': '1'},                   # the live raid -> 최신 (kept exactly as it ships today)
    'name_contains': (),                     # no name heuristic here: the archive owns tab-special/strong/train
    'default': '1',                          # unknown area -> 최신
}
# Semantic main tab (jp_event_groups `tab`) -> the first qnUhs32P value the client compares. The sub-tab
# index the client adds is 0 whenever a main tab is opened, so the first sub tab is what a volunteer sees.
JP_GATE_WIRE_TAB = {'1': '1', '2': '6', '3': '3', '4': '4', '5': '11'}

# Reward kinds that must resolve in a shipped master before the JP client can draw the mail row. 10/20/22/26/27
# go through the engine's own lookups (player_state.unit_mst/item_mst/emblem_mst/vision_card_mst, _can_credit
# player_state.py:3666); 21/23/60 are the tables _can_credit does not index itself. Kinds not listed here are
# currencies/switches, for which no master row is read, and are left alone.
JP_RAID_MASTER_TABLES = {
    '21': ('F_EQUIP_ITEM_MST.ndjson', 'J1YX9kmM'),
    '22': ('F_MATERIA_MST.ndjson', 'H5jBL0Vf'),
    '23': ('F_IMPORTANT_ITEM_MST.ndjson', '2dfixko3'),
    '60': ('F_RECIPE_BOOK_MST.ndjson', 'staFu8U1'),
}
JP_RAID_BANNER_FILE, JP_RAID_BANNER_KEY = 'F_BANNER_MST.ndjson', 'fSxqkF10'
# JP F_BANNER_MST id for each GL raid event whose GL reward banner JP never shipped. `GateMissionScene::
# setLayoutRaid` (0x1bcc124) only draws the Rewards button when a type-3 banner's BannerScheduleMst row
# (`jBL5XNf6`) is inside its period, so '0' means no button at all. 734's GL 900073401 -> JP 60003
# "一周年ありがとうクポ" (w2A76noc=3, bahamut_raid.php?SumallyId=400107).
JP_RAID_BANNERS = {'734': '60003'}
# F_SUMALLY_REWARD_MST (L84eYzxv) behind each raid event's reward screen. 734: the SumallyId in 60003's URL;
# the JP master has no 400107 rows, so build/patch_raid734_sumally.py writes them from the 734 milestones.
JP_RAID_SUMALLY = {'734': '400107'}
_JP_RAID_BASE = None
_JP_RAID_PRUNE_LOGGED = set()


def _jp_event_policy(data_root, fallback_areas=()):
    """load_policy replacement: only the chosen season's areas are served (jp_event_archive, 2026-11-12).

    serve_event_gate calls this per request, so the selection stored by event_archive.menu() takes effect on
    the next gate request without re-entering the scene.
    """
    import ffbe_player as fp
    import jp_event_archive
    player = getattr(fp.State, 'player', None)
    try:
        areas = jp_event_archive.selected_area_ids(player)
    except Exception as exc:            # data file missing/unreadable -> keep the legacy area list
        print('JP compat: season archive unavailable (%r)' % (exc,), flush=True)
        areas = None
    if not areas:
        areas = [str(a) for a in _jp_event_area_ids()]
    return {'version': 1, 'areas': [str(a) for a in areas], 'permanent': True}


def _jp_event_gate_art(area):
    """No GL Banner-*.png in JP; None -> EVENT_GATE_ART (dummy) or the raid menu background."""
    return None


def _jp_no_personal_raid(mission_id=None, dungeon_id=None):
    """exvius_raid_progress.personal_event replacement while the raid screen is not ready."""
    return None


def _jp_raid_has_reward(row):
    """True when the JP masters can resolve this reward row (the same routing _can_credit grants by)."""
    import player_state as ps
    try:
        kind = str(int(row.get('kind', 0) or 0))
        iid = str(int(row.get('id', 0) or 0))
        if kind == '10':
            return ps.unit_mst(iid) is not None
        if kind == '20':
            return ps.item_mst(iid) is not None
        if kind == '26':
            return ps.emblem_mst(iid) is not None
        if kind == '27':
            return ps.vision_card_mst(iid) is not None
        table = JP_RAID_MASTER_TABLES.get(kind)
        if table is None:
            return True                 # currency / switch: the client reads no master row for it
        rows = ps._load_ndjson(table[0], table[1])
        if kind == '60':
            master = rows.get(iid)
            return bool(master and str(master.get('gJf3zp8a', '')).isdigit())
        return iid in rows
    except OSError:
        # A missing table cannot be checked; keep the row rather than silently deleting a reward. The JP app
        # ships all of these tables, so this is a build problem, not a normal path.
        print('JP compat: raid reward check cannot read the JP masters; reward %r kept' % (row,), flush=True)
        return True


def _jp_raid_banner_ids():
    import player_state as ps
    try:
        return ps._load_ndjson(JP_RAID_BANNER_FILE, JP_RAID_BANNER_KEY)
    except OSError:
        print('JP compat: raid banner check cannot read %s; banner kept' % JP_RAID_BANNER_FILE, flush=True)
        return None


def _jp_raid_event(event):
    """Deep copy of a GL raid event with every reward row the JP masters cannot resolve removed.

    With JP_EVENT_RAID on, personal_event stays alive so the JP raid menu is served: RaidMenuInfoResponse
    `dg5ZV3kQ` (RaidMenuInfoResponse::readParam 0x1df3430 reads K3P1jcu7/R01Wz7fe/F4gkm9Rt/Yc8Mm6y7/
    Mmex5dU8/xfirgH86/7DTnc2Lt) and UserRaidInfoResponse `71ctQHWm` (52ibRBqw/UbQ26oH4). The level-down
    countdown on the raid screen is `Mmex5dU8` -> RaidMenuInfo::setRestTime (+0x58), rendered by
    getRestTimeStr (0x1d876a4) with format "%02d:%02d:%02d" (hours:minutes:seconds; negative -> "00:00:00");
    the engine's authored 2147483647 seconds is "never level down" -> 596523:14:07, it is not a missing field.

    The GL reconstruction carries ids JP never shipped (734: item 1000000003 Y-Potion, 1000000004 Mega
    Ether, 1209000826 Shard of Kelsus at three thresholds) and reward banner 900073401. JP F_ITEM_MST has
    no Y-Potion / Mega Ether / Shard of Kelsus row to substitute, so the rows are DROPPED rather than
    guessed at; a milestone whose every reward is dropped is dropped whole because
    apply_personal_raid_result needs at least one grantable reward. The original dict is never mutated
    (deepcopy), so the module's loader cache keeps the untouched GL table.
    """
    if not event:
        return event
    import copy
    ev = copy.deepcopy(event)
    removed = []

    def prune(milestones):
        kept = []
        for milestone in milestones:
            if not isinstance(milestone, dict):
                kept.append(milestone)
                continue
            listed = milestone.get('rewards')
            single = listed is None and 'reward' in milestone
            rewards = list(listed) if isinstance(listed, list) else ([milestone['reward']] if single else [])
            good = [row for row in rewards if isinstance(row, dict) and _jp_raid_has_reward(row)]
            if len(good) != len(rewards):
                bad = [row for row in rewards if row not in good]
                removed.append((milestone.get('points', milestone.get('threshold')),
                                [(row.get('kind'), row.get('id')) if isinstance(row, dict) else row
                                 for row in bad]))
            if rewards and not good:
                continue                # nothing grantable here: drop the milestone itself
            if listed is not None:
                milestone['rewards'] = good
            elif single:
                milestone['reward'] = good[0]
            kept.append(milestone)
        return kept

    if isinstance(ev.get('personal_milestones'), list):
        ev['personal_milestones'] = prune(ev['personal_milestones'])
    if isinstance(ev.get('shared_milestones'), list):
        ev['shared_milestones'] = prune(ev['shared_milestones'])
    banners = _jp_raid_banner_ids()
    banner = str(ev.get('reward_banner_id') or '')
    if banners is not None and banner and banner not in banners:
        # fSxqkF10 must be a JP F_BANNER_MST id. A mapped JP banner makes serve_event_gate emit its
        # jBL5XNf6 schedule row, which is what creates the Rewards button; '0' keeps the gate row bare.
        mapped = JP_RAID_BANNERS.get(str(ev.get('event_id')), '0')
        ev['reward_banner_id'] = mapped if mapped in banners else '0'
    if removed and ev.get('event_id') not in _JP_RAID_PRUNE_LOGGED:
        # serve_event_gate asks for every open area on every gate reply: log each event once.
        _JP_RAID_PRUNE_LOGGED.add(ev.get('event_id'))
        print('JP compat: raid %s rewards pruned: %s' % (ev.get('event_id'), removed), flush=True)
    # The raid header (RaidMenuInfo xfirgH86) is event['name'] + ' (Solo)' -- the GL English title.
    # Serve the Korean area title instead (translations/names-ko/names_pass2.json); the suffix is
    # removed by _jp_raid_menu_groups.
    name = JP_RAID_NAMES.get(str(ev.get('event_id')))
    if name:
        ev['name'] = name
    # The raid menu background (RaidMenuInfo 7DTnc2Lt, also the ranking row) is a CRI file name. The GL
    # archive names `event_<area>.png`, which JP never shipped: the client gets a null batch node and the
    # jp_event_menu.js guard leaves the slot empty (blank backdrop, 6260 on 2026-11-14). Serve the JP
    # raid1.cpk file instead (jp_raid_bg.json, build/make_jp_raid_bg.py).
    background = _jp_raid_backgrounds().get(str(ev.get('event_id')))
    if background:
        ev['menu_background'] = background
    return ev


_JP_RAID_BG = None
JP_RAID_TRACE_PATH = '/storage/emulated/0/Android/data/com.exvius.jpkorean.app/files/jp_raid_menu.log'


def _jp_raid_menu_trace(inner):
    """RoutineRaidMenuUpdateRequest (g0BjrU5D) wrapper: record which dungeon the client asks for.

    2026-11-14: opening 6070 showed 6260's title and background. personal_raid_menu picks the event from
    request 3uy7DzGB[0].U9iHsau3, so this logs the whole 3uy7DzGB list and the event served (stdout and
    JP_RAID_TRACE_PATH, readable with adb pull on a non-debuggable build).
    """
    def traced(spec, request):
        out = inner(spec, request)
        try:
            import time
            rows = (request or {}).get('3uy7DzGB') or []
            asked = [str(r.get('U9iHsau3')) for r in rows if isinstance(r, dict)]
            served = [str(r.get('xfirgH86')) + '|' + str(r.get('7DTnc2Lt'))
                      for r in ((out or {}).get('dg5ZV3kQ') or []) if isinstance(r, dict)]
            line = '%s raid_menu asked=%s keys=%s served=%s' % (
                time.strftime('%H:%M:%S'), asked, sorted((request or {}).keys()), served)
            print('JP compat: ' + line, flush=True)
            import os
            os.makedirs(os.path.dirname(JP_RAID_TRACE_PATH), exist_ok=True)
            with open(JP_RAID_TRACE_PATH, 'a', encoding='utf-8') as fh:
                fh.write(line + '\n')
        except Exception:
            pass
        return out
    return traced


def _jp_raid_backgrounds():
    """{GL raid event id: JP raid1.cpk background file} from jp_raid_bg.json beside this file, or {}."""
    global _JP_RAID_BG
    if _JP_RAID_BG is None:
        import json
        from pathlib import Path
        try:
            document = json.loads((Path(__file__).resolve().parent / 'jp_raid_bg.json').read_text(encoding='utf-8'))
            _JP_RAID_BG = {str(k): str(v) for k, v in (document.get('by_area') or {}).items() if v}
        except (OSError, ValueError):
            _JP_RAID_BG = {}
        print('JP compat: raid backgrounds %d' % len(_JP_RAID_BG), flush=True)
    return _JP_RAID_BG


# Korean raid header per GL raid event id (= JP area id). 一周年ありがとうクポ -> names_pass2.json.
JP_RAID_NAMES = {'734': '1주년 고마워 쿠포'}
JP_RAID_REST_SECONDS = 2400 * 3600       # level-down countdown shown as 2400:00:00


def _jp_raid_ranking_row(area, background=''):
    """One RaidRankingStateInfoResponse row (readParam 0x1df3838) for a raid area, or None.

    `isRankingExist` (0x1d873c0) is `+0x28 not in (0, 4)`, so C8Qf5bs6='1' makes the raid tab's Rewards
    touch build the native GateMissionRaidRewardScene; otherwise the same touch opens the banner URL web
    view (dead offline). +0x24 (L84eYzxv) is the SumallyId that scene passes to
    SumallyRewardMstList::getRewardList (0x1cac648). The client fills this singleton ONLY from this group,
    and both the gate and the raid menu replies carry it so the value is in place before the touch.
    """
    sumally = JP_RAID_SUMALLY.get(str(area))
    if not sumally:
        return None
    return {'L84eYzxv': sumally,     # SumallyId -> F_SUMALLY_REWARD_MST
            'C8Qf5bs6': '1',        # ranking state: 0/4 = none, anything else = exists
            'BGFw7qi4': '', '2oL4dNFy': '', '0dh7yRIN': '',
            '4yT7FUqj': str(background or ''),
            'td06MKEX': '0'}        # exactly the readParam tags; no extra keys


def _jp_gate_raid_ranking(inner):
    """serve_event_gate wrapper: add `rgGd0q21` when the 734 tile is served.

    GateMissionScene::touchEnded reads RaidRankingStateInfo at touch time, but the group may never ride the
    same reply as the touch; answering it on the gate reply (6H1R9WID) and on the raid menu reply (step 4)
    covers both paths. Rows for other areas are left untouched.
    """
    tag = '0xkoNP8U'                    # ffbe_player.EVENT_GATE_TAG

    def serve_event_gate(spec, reply_id):
        out = inner(spec, reply_id)
        if not isinstance(out, dict) or not isinstance(out.get(tag), list):
            return out
        row = next((r for r in out[tag] if isinstance(r, dict)
                    and str(r.get('uv60hgDW')) in JP_RAID_SUMALLY), None)
        if row is None:
            return out
        ranking = _jp_raid_ranking_row(row.get('uv60hgDW'),
                                       JP_RAID_RANKING_BG.get(str(row.get('uv60hgDW'))) or row.get('4yT7FUqj'))
        if ranking is None:
            return out
        out = dict(out)
        out['rgGd0q21'] = [ranking]
        return out

    return serve_event_gate


def install_rm_modes(server=None):
    """exvius_actions_modes picks Rm missions by F_MISSION_MST.gQR24kST == MODE['rm'] ('12', 영문판).

    JP Rm missions (5040: 50400100.., gQR24kST 3/0) never match, so `_rm` fell back to the 영문판 default
    area: RmEntry replied Q4kJKh8b.uv60hgDW=920 and RmAreaScene -> AreaMapManager::setLayoutAreaMap
    (area=920, 2026-11-13 device trace) loaded map920_1.jpg, which JP lacks -> null Texture2D ->
    SIGSEGV in Texture2D::getContentSize. Rebind `_missions`/`_mission` for name 'rm' to "missions whose
    area is a JP_RM_TEST_AREAS area", drop a stale saved area/Q4kJKh8b outside those areas, and serve
    Q4kJKh8b with the JP date-string window (the gate injector's format, RmEventInfoResponse::readParam).

    RmEventInfo is one singleton and RmEntryRequest carries no area id, so the areas now cover every
    jp_rm_areas.json entry but the saved `exvius_rm.area` still holds ONE at a time. The Frida gate-touch
    hook records the touched area in `jp_rm_area.txt`; RmEntry (wx5sg9ye) reads it and switches `area`,
    clearing the previous area's running dungeon state (progress/cleared records are kept).
    """
    import exvius_actions_modes as am
    if getattr(am, '_jp_rm_installed', False):
        return
    areas = {str(a) for a in JP_RM_TEST_AREAS}
    first_area = sorted(areas, key=int)[0]
    def default_area():
        return '5040' if '5040' in areas else first_area

    state_file = getattr(getattr(server, 'st', None), 'STATE_FILE', None)
    base_missions, base_mission, base_rm = am._missions, am._mission, am._rm
    mst = lambda: am._mst('F_MISSION_MST.ndjson', 'qo3PECw6')

    def _missions(name, dungeon=None):
        if name != 'rm':
            return base_missions(name, dungeon)
        return sorted((r for r in mst().values()
                       if str(r.get('uv60hgDW')) in areas
                       and (dungeon is None or str(r.get('U9iHsau3')) == str(dungeon))),
                      key=lambda r: (am._number(r['Z0EN6jSh']), am._number(r['qo3PECw6'])))

    def _mission(name, mid):
        if name != 'rm':
            return base_mission(name, mid)
        row = mst().get(str(mid))
        am._need(row and str(row.get('uv60hgDW')) in areas, 'mission is not in this mode')
        return row

    def _rm(f, player=None):
        groups = f.setdefault('groups', {})
        if f.get('area') is not None and str(f['area']) not in areas:
            for k in ('area', 'dungeon', 'mission', 'last_completed', 'run', 'active'):
                f.pop(k, None)
            groups.pop('Wmr7y9a0', None)
        if not f.get('area'):
            f['area'] = default_area()
        old = (groups.get('Q4kJKh8b') or [{}])[0]
        if str(old.get('uv60hgDW')) not in areas:
            groups.pop('Q4kJKh8b', None)
        # Story nodes whose scene cpk exists nowhere (jp_rm_noscene.json) are NOT passed over here any more:
        # moving the checkpoint past them (2026-11-14) left the client and the run out of step. They now get a
        # stand-in scene on the client (build/make_jp_noscene_stub.py: resource rows -> 999000101.cpk), so
        # the node is entered, plays a one-line notice and ends through the normal RmEnd.
        base_rm(f, player)
        area = str(groups['Q4kJKh8b'][0].get('uv60hgDW'))
        groups['Q4kJKh8b'] = [{'uv60hgDW': area, 'VjJQ51uG': JP_RM_WINDOW[0], 'm8ivD4NX': JP_RM_WINDOW[1]}]

    # RmEntry: adopt the area the gate-touch hook recorded. The client reaches RmEntryScene only for the
    # tile it touched, and the request has no area, so the file is the only per-entry source. A missing file or
    # an id outside the list keeps the saved area; no saved area -> 5040 (else the first listed area).
    base_entry = am.HANDLERS['wx5sg9ye']

    def rm_entry(spec, req):
        try:
            player = am.State.player
            data = player.data if player is not None else None
            f = data.get('exvius_rm') if isinstance(data, dict) else None
            if isinstance(f, dict):
                entered = _jp_rm_area_id(state_file)
                print('JP rm: entry, area file says %r (saved area %r)' % (entered, f.get('area')), flush=True)
                if entered not in areas:
                    entered = ''
                old_area = str(f.get('area') or '')
                target = entered or (old_area if old_area in areas else default_area())
                if target and target != old_area:
                    if old_area:      # another area: drop that area's in-flight dungeon, keep progress
                        for key in ('area', 'dungeon', 'mission', 'last_completed', 'run', 'active'):
                            f.pop(key, None)
                        groups = f.get('groups')
                        if isinstance(groups, dict):
                            groups.pop('Wmr7y9a0', None)
                            groups.pop('Q4kJKh8b', None)
                        print('JP rm: area %s -> %s, running dungeon state cleared' % (old_area, target),
                              flush=True)
                    f['area'] = target
                    player.dirty = True
        except Exception as e:  # noqa: BLE001 -- never block RmEntry
            print('JP rm: area switch skipped: %r' % (e,), flush=True)
        return base_entry(spec, req)

    base_helper = am._helper

    def _helper(op):
        # The JP helper picker lists helpers the 영문판 friends.yaml roster does not hold, so the strict
        # roster check refused RmDungeonStart (2026-11-13 device: "helper is not in the offline friend
        # roster"). Normal quests (ffbe_battle) never check the roster; do the same here, keep the log.
        try:
            return base_helper(op)
        except am._Refused as e:
            if 'friend roster' not in str(e):
                raise
            helper = str(op.get('dUX7Pt5i') or op.get('w40YsHIz') or '')
            print('JP rm: helper %s (unit %s) not in friends.yaml; accepted like a normal quest'
                  % (helper, op.get('qLke7K8f')), flush=True)
            return helper

    am._missions, am._mission, am._rm, am._helper = _missions, _mission, _rm, _helper

    # RmStart: the 영문판 chain is strictly linear (f['mission'] = next row by Z0EN6jSh), but the JP map
    # lets the client pick a node -- 2026-11-13 device: after RmDungeonStart 504001 (engine expects
    # 50400100, the opening story node) the client sent RmStart 50400101 -> "no matching RM dungeon
    # checkpoint". Accept any mission of the ACTIVE dungeon: retarget the saved checkpoint, then run the
    # original handler unchanged (its own checks still apply).
    base_start = am.HANDLERS['7FyJS3Zn']
    prior_cleared = {}   # mission id -> challenge ids cleared before the running attempt

    def rm_start(spec, req):
        try:
            op = am._node(req, 'jQsE54Iz') or {}
            mid = str(op.get('qo3PECw6') or '')
            data = am.State.player.data if am.State.player is not None else {}
            f = data.get('exvius_rm') or {}
            row = mst().get(mid)
            stale = f.get('active') or {}
            if f.get('run') and row and mid != str(f.get('mission'))                     and str(row.get('U9iHsau3')) == str(f.get('dungeon')) and str(row.get('uv60hgDW')) in areas:
                if stale:
                    # An attempt the client already left (e.g. a story node whose RmEnd was refused by
                    # an older build): the client moved on to another node, so drop it.
                    print('JP rm: dropping unfinished attempt %s' % stale.get('mission'), flush=True)
                    f['active'] = None
                rows = _missions('rm', f['dungeon'])
                pos = next((i for i, r in enumerate(rows) if str(r['qo3PECw6']) == mid), 0)
                print('JP rm: start %s (checkpoint was %s)' % (mid, f.get('mission')), flush=True)
                f['mission'] = mid
                f['last_completed'] = str(rows[pos - 1]['qo3PECw6']) if pos else '0'
        except Exception as e:  # noqa: BLE001 -- never block the original handler
            print('JP rm: start retarget skipped: %r' % (e,), flush=True)
        # Condition 38 (no continue): JP RmEnd carries an EMPTY L4i4418y (2026-11-13 device, 50400102..105),
        # so jp_mission's own count decides -- but RmStart was not one of its attempt starts, the count stayed
        # on the previous mission and returned None ("challenge 504001022 not witnessed"). Start it here.
        try:
            # Challenges already cleared BEFORE this attempt: rm_end reports (now - this) as "cleared by this
            # battle". The mission-end pipeline pays challenges before the Rm handler runs, so the handler's
            # own fresh list is always empty (2026-11-13 device: "fresh=[]" on a first clear).
            op0 = am._node(req, 'jQsE54Iz') or {}
            mid0 = str(op0.get('qo3PECw6') or '')
            done = am.State.player.data['progress']['cleared_challenges'].get(mid0) or ()
            prior_cleared.clear()
            prior_cleared[mid0] = {str(i) for i in done}
        except Exception as e:  # noqa: BLE001
            print('JP rm: prior challenge snapshot skipped: %r' % (e,), flush=True)
        try:
            import jp_mission
            jp_mission.on_start(req)
        except Exception as e:  # noqa: BLE001
            print('JP rm: continue count not reset: %r' % (e,), flush=True)
        return base_start(spec, req)

    # RmEnd of a story-only node: JP Rm maps mix story nodes (F_MISSION_MST.8xi6Xvyk == '0', no battle;
    # 50400100/50400101/50400105..) with battle nodes, and the client uploads no BattleClear log
    # (2urzfX6d.69ieJGhD) for a story node -- 2026-11-13 device: RmEnd 50400101 -> "no witnessed
    # battle-clear log". For such a node only, hand _challenges a one-wave/one-turn clear entry.
    base_challenges = am._challenges

    def _challenges(mid, run, req, base_result=None):
        row = mst().get(str(mid)) or {}
        meta = am._node(req, '2urzfX6d') if isinstance(req, dict) else None
        if str(row.get('uv60hgDW')) in areas and str(row.get('8xi6Xvyk') or '0') == '0'                 and not str((meta or {}).get('69ieJGhD') or ''):
            from copy import deepcopy
            req = deepcopy(req)
            node = req.get('2urzfX6d')
            if not (isinstance(node, list) and node and isinstance(node[0], dict)):
                node = req['2urzfX6d'] = [{}]
            node[0]['69ieJGhD'] = '1:0:1'
            print('JP rm: story node %s ended (no battle log; story-only mission)' % mid, flush=True)
        out = base_challenges(mid, run, req, base_result)
        return out

    # RmEnd reply: the Rm battle-result screen (RmMissionResultChallengeScene::getChallengeState) reads the
    # challenge state from UserChallengeInfoResponse TQ5AJd2K -- qdhWF7z9 = already cleared, wf5Toh4k =
    # provisional (cleared by THIS battle, settled at the dungeon end). The engine's Rm replies carried no
    # TQ5AJd2K at all, so the per-battle result showed no success and only RmDungeonEnd did (2026-11-13
    # device report). Attach every cleared mission's row; for the mission just ended, this battle's fresh
    # ids go to wf5Toh4k and are kept out of qdhWF7z9 so they read as "just cleared".
    base_end = am.HANDLERS['fyp10Rrc']

    def rm_end(spec, req):
        out = base_end(spec, req)
        try:
            op = am._node(req, 'jQsE54Iz') or {}
            mid = str(op.get('qo3PECw6') or '')
            row = mst().get(mid) or {}
            if isinstance(out, dict) and str(row.get('uv60hgDW')) in areas:
                result = (out.get('09HRWXDf') or [{}])[0] or {}
                cleared = am.State.player.data['progress']['cleared_challenges']
                fresh = {c for c in str(result.get('qdhWF7z9') or '').split(',') if c}
                if mid in prior_cleared:
                    fresh |= {str(i) for i in (cleared.get(mid) or ())} - prior_cleared.pop(mid)
                rows = []
                for m, ids in sorted(cleared.items()):
                    ids = {str(i) for i in ids}
                    if str(m) == mid:
                        rows.append({'qo3PECw6': mid, 'qdhWF7z9': ','.join(sorted(ids - fresh)),
                                     'wf5Toh4k': ','.join(sorted(fresh))})
                    elif ids:
                        rows.append({'qo3PECw6': str(m), 'qdhWF7z9': ','.join(sorted(ids)), 'wf5Toh4k': ''})
                if rows:
                    out['TQ5AJd2K'] = rows
                print('JP rm: end %s challenge info: fresh=%s, %d row(s)' % (mid, sorted(fresh), len(rows)),
                      flush=True)
        except Exception as e:  # noqa: BLE001 -- the reply itself must still go out
            print('JP rm: end challenge info skipped: %r' % (e,), flush=True)
        return out

    # RmRetire from the map menu carries mission 0. The engine accepts that only with no attempt running, so
    # giving up inside a story node that never ends was refused ("retire mission mismatch", 2026-11-14
    # device, 8660101) and the player could not leave. Drop the running attempt, then give up as usual.
    base_retire = am.HANDLERS['e0R3iDm1']

    def rm_retire(spec, req):
        try:
            op = am._node(req, 'jQsE54Iz') or {}
            data = am.State.player.data if am.State.player is not None else {}
            f = data.get('exvius_rm') or {}
            if str(op.get('qo3PECw6') or '0') == '0' and f.get('run') and f.get('active'):
                print('JP rm: map give-up while %s was running; attempt dropped'
                      % (f['active'] or {}).get('mission'), flush=True)
                f['active'] = None
                am.State.player.dirty = True
        except Exception as e:  # noqa: BLE001
            print('JP rm: give-up fix skipped: %r' % (e,), flush=True)
        return base_retire(spec, req)

    am.HANDLERS['e0R3iDm1'] = rm_retire
    try:
        import exvius_actions as _ea
        if _ea.HANDLERS.get('e0R3iDm1') is base_retire:
            _ea.HANDLERS['e0R3iDm1'] = rm_retire
    except Exception as e:  # noqa: BLE001
        print('JP rm: retire handler not patched: %r' % (e,), flush=True)

    am._challenges = _challenges
    am.HANDLERS['wx5sg9ye'] = rm_entry
    am.HANDLERS['7FyJS3Zn'] = rm_start
    am.HANDLERS['fyp10Rrc'] = rm_end
    try:
        import exvius_actions as ea
        if ea.HANDLERS.get('wx5sg9ye') is base_entry:
            ea.HANDLERS['wx5sg9ye'] = rm_entry
        if ea.HANDLERS.get('7FyJS3Zn') is base_start:
            ea.HANDLERS['7FyJS3Zn'] = rm_start
        if ea.HANDLERS.get('fyp10Rrc') is base_end:
            ea.HANDLERS['fyp10Rrc'] = rm_end
    except Exception as e:  # noqa: BLE001
        print('JP rm: exvius_actions.HANDLERS not patched: %r' % (e,), flush=True)
    am._jp_rm_installed = True
    first = _missions('rm')
    print('JP rm: %d area(s), %d mission(s), first %s, area file %s'
          % (len(areas), len(first), first[0]['qo3PECw6'] if first else '-',
             _jp_rm_area_path(state_file) or '?'), flush=True)


def _jp_gate_rm_event(inner):
    """serve_event_gate wrapper: add RmEventInfoResponse `Q4kJKh8b` for a JP_RM_TEST_AREAS tile.

    GateScene::touchEnded (0x1be0594) compares the touched tile's AreaMst.areaId with
    RmEventInfo::getAreaId (RmEventInfo+8) and only then opens RmEntryScene (13000); the engine never serves
    the group (0 of 565 responses.json entries), so RmEventInfo.areaId stays 0 and the tile opens
    GateDungeonScene instead. The group rides the routine world update reply (6H1R9WID) that refreshes the
    gate -- notes.txt 5절 Step 1 names this as the most likely carrier; if the device shows the singleton is
    still 0 at touch time, try lEHBdOEf (boot) / MTf2j9aK (vortex entry) next.

    Fields are exactly what the JP RmEventInfoResponse::readParam (0x1db27ac) reads, no others
    (build/out/vortex_season/rm_mode/requests.tsv:117-119):
      uv60hgDW -> RmEventInfo+8   (str w0,[x23,#8] @0x1db27ac, int)
      VjJQ51uG -> RmEventInfo+0x10 (add x0,x24,#0x10 @0x1db282c, string "YYYY-MM-DD HH:MM:SS")
      m8ivD4NX -> RmEventInfo+0x28 (add x0,x21,#0x28 @0x1db2890, string)
    The struct is a SINGLETON written per row, so several areas would leave only the LAST row in place.
    Serve the saved `exvius_rm.area` when its tile is on this gate reply (the area the player is in), else the
    first Rm area present. Other Rm tiles are opened by the Frida hook (build/frida/jp_offline.js), which
    rewrites the singleton at the touch comparison.
    """
    tag = '0xkoNP8U'                    # ffbe_player.EVENT_GATE_TAG
    areas = tuple(str(a) for a in JP_RM_TEST_AREAS)
    carriers = ('lEHBdOEf', '6H1R9WID', '4kA1Ne05', 'Daud71Hn')

    def running_area():
        try:
            import ffbe_state
            player = ffbe_state.State.player
            return str(((getattr(player, 'data', None) or {}).get('exvius_rm') or {}).get('area') or '')
        except Exception:
            return ''

    def serve_event_gate(spec, reply_id):
        out = inner(spec, reply_id)
        if reply_id not in carriers or not isinstance(out, dict) or not isinstance(out.get(tag), list):
            return out
        present = {str(r.get('uv60hgDW')) for r in out[tag] if isinstance(r, dict)}
        candidates = [a for a in areas if a in present]
        if not candidates:
            return out
        running = running_area()
        area = running if running in candidates else candidates[0]
        out = dict(out)
        out['Q4kJKh8b'] = [{'uv60hgDW': area,            # RmEventInfo+8    (0x1db27ac)
                            'VjJQ51uG': JP_RM_WINDOW[0],  # RmEventInfo+0x10 (0x1db282c)
                            'm8ivD4NX': JP_RM_WINDOW[1]}]  # RmEventInfo+0x28 (0x1db2890)
        return out

    return serve_event_gate


_JP_PARADE_AREAS = None


def _jp_parade_area_set():
    """Areas whose FIRST mission (lowest id) has subtype gQR24kST == 12: GateScene::touchEnded's parade branch.

    MissionUtil::getFirstMissionSubType (0x1be0554) -> jump table 0x25edc10, subtype 12 -> 0x1be07f0.
    86 areas in jp_event_groups.json (2026-11-14): Dark Visions seasons, 954, 961, 965 ... none overlap the Rm
    list (those are subtype 3 and are caught earlier at 0x1be0594).
    """
    global _JP_PARADE_AREAS
    if _JP_PARADE_AREAS is None:
        import player_state as ps
        dungeons = ps._load_ndjson('F_DUNGEON_MST.ndjson', 'U9iHsau3')
        first = {}
        for mid, row in ps._load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6').items():
            area = str((dungeons.get(str(row.get('U9iHsau3'))) or {}).get('uv60hgDW') or '')
            if area and (area not in first or int(mid) < int(first[area][0])):
                first[area] = (mid, str(row.get('gQR24kST')))
        _JP_PARADE_AREAS = frozenset(a for a, (_, sub) in first.items() if sub == '12')
        print('JP compat: parade gate areas %d' % len(_JP_PARADE_AREAS), flush=True)
    return _JP_PARADE_AREAS


def _jp_gate_parade_events(inner):
    """serve_event_gate wrapper: ParadeEventInfoResponse `gXrD1h58` rows for the parade tiles on this reply.

    GateScene::touchEnded's subtype-12 branch (0x1be07f0) does ParadeEventInfoList::getObjectWithAreaId(area)
    and returns WITHOUT any feedback when it is null (0x1be07fc cbz -> 0x1be0044): the tile "does nothing"
    (device 2026-11-14, `GATE_TAP area=965`). The engine sends `gXrD1h58` only in its ParadeEntry reply
    (exvius_actions_modes._parade), so no gate tile could reach ParadeEntryScene. With a row present the
    branch checks ParadeUtil::isAvailableToEnter (PARADE_OPEN_TEAM_LV 4 <= rank), then now <= the row's end
    date (+0xa8 = XY5ZfS0w, convertToTime, else notice -3993 and the row is removed), copies RdV4nK8w (+0xf8) to
    UserState+0x1f0 and opens ParadeEntryScene, whose ParadeEntryRequest the engine already serves for any
    subtype-12 area. Row fields = the engine's own _parade() event row (the one 954 has entered with).
    """
    tag = '0xkoNP8U'

    def serve_event_gate(spec, reply_id):
        out = inner(spec, reply_id)
        if not isinstance(out, dict) or not isinstance(out.get(tag), list):
            return out
        try:
            parade = _jp_parade_area_set()
        except Exception as exc:  # noqa: BLE001 - parade rows must never break the gate reply
            print('JP compat: parade gate rows skipped: %r' % (exc,), flush=True)
            return out
        present = []
        for row in out[tag]:
            area = str(row.get('uv60hgDW')) if isinstance(row, dict) else ''
            if area in parade and area not in present:
                present.append(area)
        if not present:
            return out
        out = dict(out)
        out['gXrD1h58'] = [{'uv60hgDW': area, 'L84eYzxv': '650001', 'D1GdY4Vh': '1',
                            'VjJQ51uG': '2020-01-01 00:00:00', 'm8ivD4NX': JP_GATE_WINDOW_END,
                            # +0xa8 is XY5ZfS0w (ParadeEventInfoResponse::readParam 0x1dc3de0), the date
                            # touchEnded compares with now; empty -> 0 -> notice -3993 "최신 개최 정보..."
                            'XY5ZfS0w': JP_GATE_WINDOW_END,
                            'RdV4nK8w': '1', 'td06MKEX': '65000'}
                           for area in sorted(present, key=int)]
        return out

    return serve_event_gate


JP_PARADE_DECKS = 16


def _jp_pad_parade_decks(inner):
    """PlayerState.special_party wrapper: the parade party ('8') always holds decks 0..15.

    PartyDeckUtil::changePartyType (JP libgame 0x1535db8) checks the type-8 UserPartyDeckList and, when
    getCount() <= 15, APPENDS 16 default decks numbered 0..15 to whatever is there. The engine copies the
    10 main decks, so the list became 0..9,0..15 (26, device 2026-11-14 DECK_DIAG) and GameUtils::isDeckUnit,
    which walks getObject(i) for i < getCount() by deck number, got null at 16 and crashed (SIGSEGV in
    BasePartyInfoList::getCount, ParadeUnitChangeScene). 16 decks -> no padding, numbers contiguous.
    New decks copy main deck i if it exists, else deck 0's members.
    """
    import copy

    def special_party(self, kind):
        party = inner(self, kind)
        if str(kind) == '8' and isinstance(party, dict):
            decks = party.setdefault('decks', [])
            have = {str(d.get('id')) for d in decks if isinstance(d, dict)}
            main = {str(d.get('id')): d for d in (self.data.get('party') or {}).get('decks') or []}
            base = (decks[0] if decks else None) or next(iter(main.values()), None) or {'members': []}
            added = 0
            for i in range(JP_PARADE_DECKS):
                if str(i) in have:
                    continue
                src = main.get(str(i)) or base
                decks.append({'id': i, 'name': 'Party %d' % (i + 1),
                              'members': copy.deepcopy(src.get('members') or [])})
                added += 1
            if added:
                decks.sort(key=lambda d: int(d.get('id', 0)))
                self.dirty = True
                print('JP compat: parade party padded to %d decks (+%d)' % (len(decks), added), flush=True)
        return party

    return special_party


def _jp_raid_menu_groups(inner):
    def personal_menu_groups(player, event):
        out = inner(player, event)
        for row in out.get('dg5ZV3kQ') or []:
            title = row.get('xfirgH86')
            if isinstance(title, str) and title.endswith(' (Solo)') and \
                    str(event.get('event_id')) in JP_RAID_NAMES:
                row['xfirgH86'] = title[:-len(' (Solo)')]
            # Level-down countdown (Mmex5dU8, seconds, shown "%02d:%02d:%02d" hours:min:sec). The engine's
            # 2147483647 "never" reads 596523:14:07; 2400:00:00 still says "it does not drop" (user, 2026-11-12).
            row['Mmex5dU8'] = str(JP_RAID_REST_SECONDS)
        ranking = _jp_raid_ranking_row(event.get('event_id'), event.get('menu_background'))
        if ranking is not None:
            out['rgGd0q21'] = [ranking]
        return out
    return personal_menu_groups


def _jp_personal_raid(mission_id=None, dungeon_id=None):
    """personal_event replacement: the GL event, deep-copied and pruned to the ids JP ships."""
    if _JP_RAID_BASE is None:
        return None
    return _jp_raid_event(_JP_RAID_BASE(mission_id=mission_id, dungeon_id=dungeon_id))


# --- open-area list (JP_EVENT_AREAS_MODE = 'all', 2026-11-12) -----------------------------------------------
_JP_AREA_ROWS = None            # F_AREA_MST keyed by uv60hgDW (loaded once from the runtime master dir)
_JP_EVENT_AREAS_ACTIVE = None   # the list install_events served; cached so load_policy is cheap


def _jp_area_master():
    """F_AREA_MST keyed by area id. ps._load_ndjson reads MST_DIR (the runtime master dir, same as the
    rest of this file), and caches the table, so this costs one load per process."""
    global _JP_AREA_ROWS
    if _JP_AREA_ROWS is None:
        import player_state as ps
        _JP_AREA_ROWS = ps._load_ndjson('F_AREA_MST.ndjson', 'uv60hgDW')
    return _JP_AREA_ROWS


def _jp_open_event_areas():
    """Every sp-dungeon area the gate can actually serve, minus the 封印の間 chambers.

    An area needs a dungeon row (F_DUNGEON_MST.uv60hgDW == area) that holds a mission
    (F_MISSION_MST.U9iHsau3 == dungeon): serve_event_gate skips an area without that pair because a tile with
    no dungeon takes no tap (ffbe_player.py:2848-2860). The seal chambers are excluded because
    jp_seal_room.install appends their own 0xkoNP8U rows (same area id would double the tiles).
    """
    import player_state as ps
    import jp_seal_room
    areas = _jp_area_master()
    dungeons = ps._load_ndjson('F_DUNGEON_MST.ndjson', 'U9iHsau3')
    missions = ps._load_ndjson('F_MISSION_MST.ndjson', 'qo3PECw6')
    with_mission = {str(row.get('U9iHsau3') or '') for mid, row in missions.items()
                    if mid and str(row.get('U9iHsau3') or '')}
    servable = {str(row.get('uv60hgDW') or '') for did, row in dungeons.items()
                if str(did) in with_mission and str(row.get('uv60hgDW') or '')}
    chambers = {str(a) for a in jp_seal_room.SEAL_AREAS}
    candidates = excluded = unservable = 0
    opened = []
    for area_id, row in areas.items():
        area_id = str(area_id)
        if any(str(row.get(key)) != value for key, value in JP_EVENT_AREA_FILTER.items()):
            continue
        candidates += 1
        if area_id in chambers:
            excluded += 1
            continue
        if area_id not in servable:
            unservable += 1
            continue
        opened.append(area_id)
    print('JP compat: event gate area scan: %d world-2 subtype-21 areas, %d seal chambers excluded, '
          '%d without a dungeon+mission, %d opened' % (candidates, excluded, unservable, len(opened)),
          flush=True)
    return tuple(opened)


def _jp_event_area_ids():
    """The active gate area list: computed from the masters when JP_EVENT_AREAS_MODE == 'all'."""
    global _JP_EVENT_AREAS_ACTIVE
    if _JP_EVENT_AREAS_ACTIVE is not None:
        return _JP_EVENT_AREAS_ACTIVE
    if str(JP_EVENT_AREAS_MODE).lower() != 'all':
        _JP_EVENT_AREAS_ACTIVE = tuple(str(a) for a in JP_EVENT_AREAS)
        return _JP_EVENT_AREAS_ACTIVE
    try:
        _JP_EVENT_AREAS_ACTIVE = _jp_open_event_areas()
    except OSError as exc:
        print('JP compat: event area masters unavailable (%r); falling back to %s'
              % (exc, JP_EVENT_AREAS), flush=True)
        _JP_EVENT_AREAS_ACTIVE = tuple(str(a) for a in JP_EVENT_AREAS)
    return _JP_EVENT_AREAS_ACTIVE


def _jp_gate_tab(area_row):
    """Semantic GateScene main tab (1..5) for one tile: the archive's per-area tab, else the fallback rules.

    Callers must pass the result through `_jp_gate_wire_tab` before writing qnUhs32P: the client compares
    sub-tab-derived values (6+ / 11+) for 복각/육성, never the bare 2/5.

    jp_event_groups.json carries the authored tab (build/make_jp_event_groups.py: special/strong/training name
    tokens, then the Global event `kind`, then era for plain story events). JP_EVENT_TAB_RULES is only the
    fallback when the data file is absent, so the gate still works with a bare engine build.
    """
    area_row = area_row or {}
    area = str(area_row.get('uv60hgDW') or '')
    try:
        import jp_event_archive as archive
        tab = archive.tab_for(area)
    except Exception:                       # data file missing/unreadable -> fall back below
        tab = None
    if tab:
        return tab
    rules = JP_EVENT_TAB_RULES
    if area in rules['exact']:
        return rules['exact'][area]
    name = str(area_row.get('G4L0YIB2') or '')
    for token, tab in rules['name_contains']:
        if token in name:
            return tab
    return rules['default']


JP_GATE_SUB_TABS = {'2': 5, '5': 2}       # sub-tab count per main tab (setLayoutSubTab 0x1be0ecc)


def _jp_gate_wire_tab(tab, sub=0):
    """Semantic main tab id (1..5) (+ sub-tab index) -> the qnUhs32P value `GateScene::setLayoutList` compares.

    복각(2) and 육성(5) have sub-tab bars: the client compares 6 + sub-tab index and 11 + sub-tab index, so
    their GATE_TAB_INFO values 2/5 match nothing. `sub` is the archive's per-area sub tab (jp_event_groups
    `sub`: 복각 0..4 = イベント/獲得/覚醒/武器/強化); 0 files the row under the first sub tab. See JP_GATE_WIRE_TAB.
    """
    tab = str(tab or '')
    wire = JP_GATE_WIRE_TAB.get(tab, tab or JP_EVENT_TAB)
    try:
        sub = int(sub or 0)
    except (TypeError, ValueError):
        sub = 0
    if tab in JP_GATE_SUB_TABS and 0 < sub < JP_GATE_SUB_TABS[tab]:
        wire = str(int(wire) + sub)
    return wire


def _jp_gate_sub(area_row):
    """Per-area sub-tab index from jp_event_groups.json (0 when unknown or the data file is missing)."""
    try:
        import jp_event_archive as archive
        return archive.sub_for(str((area_row or {}).get('uv60hgDW') or ''))
    except Exception:
        return 0


_JP_EVENT_ART_MAP = None
_JP_EVENT_AREA_MAP = None
_JP_EVENT_ART_NOTE = [False]


def _jp_event_document():
    """jp_event_art.json beside this file (baked into app.imy), or {} when unavailable.

    Version 2 maps by JP area id (`by_area`) to a banner file the JP spdungeon CPKs ship; the old
    `by_global` map (Global `event_<area>.png` name -> stand-in) is kept as an empty legacy key. A missing
    file is not fatal: every row then falls back to JP_EVENT_ART.
    """
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parent / 'jp_event_art.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _jp_event_art_map():
    """Legacy `event_<area>.png` -> stand-in map (empty in the JP-only v2 document)."""
    global _JP_EVENT_ART_MAP, _JP_EVENT_AREA_MAP
    if _JP_EVENT_ART_MAP is not None:
        return _JP_EVENT_ART_MAP
    document = _jp_event_document()
    stamp = document.get('stamp') or '-'
    print('JP compat: event art stamp=%s' % stamp, flush=True)
    _JP_EVENT_ART_MAP = {str(k): str(v) for k, v in (document.get('by_global') or {}).items()}
    _JP_EVENT_AREA_MAP = {str(k): str(v) for k, v in (document.get('by_area') or {}).items()}
    if not _JP_EVENT_ART_MAP and not _JP_EVENT_AREA_MAP and not _JP_EVENT_ART_NOTE[0]:
        _JP_EVENT_ART_NOTE[0] = True
        print('JP compat: jp_event_art.json not found; gate tile art -> %s' % JP_EVENT_ART, flush=True)
    return _JP_EVENT_ART_MAP


def _jp_event_area_map():
    """JP area id -> JP-shipped banner file (build/make_jp_event_art.py, v4 map)."""
    _jp_event_art_map()
    return _JP_EVENT_AREA_MAP or {}


def _jp_gate_gl_only(name):
    """True for a name only the Global pack could ship (`event_<area>.png`, `Banner-*.png`).

    Used outside the season selection as a crash-only guard: the seal room's own rows must keep their
    spd_* art, but a GL-only name there would still return a null batch node.
    """
    name = str(name or '')
    if name.startswith('Banner-'):
        return True
    return name.startswith('event_') and name.endswith('.png') and name[6:-4].isdigit()


def _jp_gate_fix_art(row, full=True):
    """Replace every tile-art name the JP pack cannot draw (crash_analysis.md sections 2/4).

    `4yT7FUqj` (BannerInfo) and `A5efbo71` (BannerBg) are used verbatim as CRI image names. The GL raid
    archive puts `event_<area>.png` there; JP ships none of them, so LayoutUtils::getOrCreateSpriteBatchNode
    fails and GameLayer::addChild(null) SEGVs in Ref::retain. Inside the season selection the row takes the
    area's banner from jp_event_art.json (`by_area`, JP spdungeon CPK files only); elsewhere keep names the
    JP pack ships (JP_GATE_SAFE_ART) and fall back to JP_EVENT_ART.
    `full=False` only rewrites a GL-only name (rows outside the season selection).
    Returns (row, changed); the input row is never mutated.
    """
    art_map = _jp_event_art_map()
    area_map = _jp_event_area_map()
    area = str(row.get('uv60hgDW') or '')
    row, changed = row, False
    for key in ('4yT7FUqj', 'A5efbo71'):
        name = str(row.get(key) or '')
        mapped = area_map.get(area) if full else None
        if mapped:
            # Per-area v4 assignment: replace the engine's generic default plate (JP_EVENT_ART) or any
            # name the JP pack may not ship. A deliberate JP-shipped art (899's top plate, 734's raid
            # background) is left alone.
            if name in JP_GATE_SAFE_ART and name != JP_EVENT_ART:
                continue
            target = mapped
        else:
            if name in JP_GATE_SAFE_ART:
                continue
            if not full and not _jp_gate_gl_only(name):
                continue
            target = art_map.get(name) or JP_EVENT_ART
        if name == target:
            continue
        row = dict(row)
        row[key] = target
        changed = True
    return row, changed


def _jp_gate_served_areas(default):
    """Areas this request's policy actually serves: the season archive's selection, else `default`.

    JP_EVENT_AREAS_MODE stays 'legacy' (its tuple is only the fallback); the gate rows that reach the client
    come from jp_event_archive via _jp_event_policy. The tile-art guard must cover exactly those areas, not
    the install-time tuple -- but it must NOT touch rows outside the selection (the seal room's own rows name
    spd_* files the pack ships, which a blanket rewrite would replace with the default plate).
    """
    try:
        import ffbe_player as fp
        import jp_event_archive as archive
        areas = archive.selected_area_ids(getattr(fp.State, 'player', None))
        if areas:
            return {str(a) for a in areas}
    except Exception:
        pass
    return set(default)


def _jp_gate_tab_rows(inner, selected):
    """serve_event_gate wrapper: per-area tab (qnUhs32P) + JP-safe tile art for the served areas.

    serve_event_gate copies every appended row from the area's first template row and never sets a per-area
    tab (ffbe_player.py:2952-2970), so the client would file every tile under EVENT_GATE_TAB. The rows are
    copied before the write (the engine can hand back a shared template dict) and rows for areas outside this
    request's season selection are left exactly as the engine sent them (the seal room's rows are appended
    after this wrapper). The art rewrite runs even when F_AREA_MST is unavailable: the tab can stay as served,
    but a JP-absent image name must never reach the client.
    """
    tag, tab_tag, area_tag = '0xkoNP8U', 'qnUhs32P', 'uv60hgDW'      # cfg.EVENT_GATE_TAG / qnUhs32P / uv60hgDW
    selected = {str(a) for a in selected}

    def serve_event_gate(spec, reply_id):
        out = inner(spec, reply_id)
        if not isinstance(out, dict) or not isinstance(out.get(tag), list):
            return out
        served = _jp_gate_served_areas(selected)
        try:
            master = _jp_area_master()
        except OSError as exc:
            master = {}
            print('JP compat: gate tab override has no F_AREA_MST (%r); tabs left as served' % (exc,), flush=True)
        changed = False
        rows = []
        for row in out[tag]:
            area = str(row.get(area_tag)) if isinstance(row, dict) else ''
            if not isinstance(row, dict):
                rows.append(row)
                continue
            # Outside the season selection only a GL-only name is rewritten, so the seal room's spd_* art
            # survives while a GL name can never reach the client anywhere.
            row, art_changed = _jp_gate_fix_art(row, full=area in served)
            # `served` (this request's season selection), not the install-time tuple: with the archive on,
            # `selected` is only ('734',) and every season area would keep the engine's single tab.
            area_row = master.get(area) if area in served else None
            if area_row is not None:
                tab = _jp_gate_wire_tab(_jp_gate_tab(area_row), _jp_gate_sub(area_row))
                if row.get(tab_tag) != tab:
                    row = dict(row)
                    row[tab_tag] = tab
                    changed = True
            # PossibleCnt (oY0vAuE9, SpDungeonCondMst+0x174): a broken-piece mission is refused with
            # "挑戦回数が0になりました" when this is not above the challenged count (GateScene::touchEnded
            # 0x1be0768-0x1be0778, MissionUtil::isPassibleBrokenPieceMissionChallenge 0x14fb2c0). The engine
            # writes '0'. LimitType (z0ft1PK8) stays 0, so no other screen reads the count.
            if area in served and str(row.get('oY0vAuE9') or '0') == '0':
                row = dict(row)
                row['oY0vAuE9'] = '99'
                changed = True
            # Tile order inside a tab: release order from the archive (jp_event_archive.order_for).
            if area in served:
                try:
                    import jp_event_archive as archive
                    order = str(archive.order_for(area) or '')
                except Exception:
                    order = ''
                if order and str(row.get('3sv5cRfH') or '') != order:
                    row = dict(row)
                    row['3sv5cRfH'] = order
                    changed = True
            changed = changed or art_changed
            rows.append(row)
        if not changed:
            return out
        out = dict(out)
        out[tag] = rows
        return out

    return serve_event_gate


def install_event_archive():
    """Point the engine's already-imported event_archive at jp_event_archive (no pyc replacement).

    android_game.event_archive() does `from event_archive import menu` at call time, so rebinding the module
    attributes is enough. jp_event_archive reads jp_event_groups.json (build/make_jp_event_groups.py).
    """
    import event_archive as ea
    import jp_event_archive as ja
    for name in ('document', 'events', 'listings', 'area_ids', 'menu', 'activate_mode'):
        setattr(ea, name, getattr(ja, name))
    print('JP compat: event archive menu -> jp_event_archive (%d areas; %s)'
          % (len(ja.area_ids()),
             ','.join('%s:%d' % (g, len(ja.group_area_ids(g))) for g in ja.GROUP_ORDER)), flush=True)


def install_events(server):
    import os
    import ffbe_config as cfg
    import ffbe_player as fp
    import ffbe_battle as fb

    if getattr(fp, '_jp_events_installed', False):
        return
    install_event_archive()
    missing = [n for n in ('EVENT_GATE_AREAS', 'EVENT_GATE_TAB', 'EVENT_GATE_KIND', 'EVENT_GATE_ART',
                           'EVENT_GATE_WINDOW_END', 'event_gate_art', 'load_policy') if not hasattr(fp, n)]
    if missing:
        raise RuntimeError('jp event gate: engine layout changed, missing ' + ','.join(missing))

    areas = tuple(_jp_event_area_ids())

    # 1) The GL archive is ON by default in the JP runtime (local_game.py:45) and would append 757 GL areas.
    os.environ['EXVIUS_EVENT_ARCHIVE'] = '0'

    # 2) The constants the gate functions actually read (see the module docstring).
    for mod in (cfg, fp):
        mod.EVENT_GATE_AREAS = areas
        mod.EVENT_GATE_TAB = JP_EVENT_TAB
        mod.EVENT_GATE_KIND = JP_EVENT_KIND
        mod.EVENT_GATE_ART = JP_EVENT_ART
        # 32-bit end date (see JP_GATE_WINDOW_END): serve_event_gate reads the name in ffbe_player's dict.
        mod.EVENT_GATE_WINDOW_END = JP_GATE_WINDOW_END
        # Pre-populate 0xkoNP8U on Login (Daud71Hn) and HomeScene (4kA1Ne05) so GateScene/SealAreaListScene
        # already have all rows on initial entry without needing a RoutineWorldUpdateRequest spinner.
        mod.EVENT_GATE_CARRIERS = ('lEHBdOEf', '6H1R9WID', '4kA1Ne05', 'Daud71Hn')
    fp.load_policy = _jp_event_policy
    fp.event_gate_art = _jp_event_gate_art

    # 3) ffbe_battle has its own copy of EVENT_CURRENCY (from-import at :18, read at :183).
    cfg.EVENT_CURRENCY = JP_EVENT_CURRENCY
    fb.EVENT_CURRENCY = JP_EVENT_CURRENCY

    # 3b) Per-area tab (test build, 2026-11-12): wrap serve_event_gate and overwrite qnUhs32P from the area's
    #     own F_AREA_MST row (JP_EVENT_TAB_RULES). ffbe_pipeline holds its own `serve_event_gate` name
    #     (ffbe_pipeline.py:48), so the wrapper goes on BOTH modules (same pattern as install_mission_cap).
    import ffbe_pipeline as pl
    fp.serve_event_gate = _jp_gate_tab_rows(fp.serve_event_gate, areas)
    pl.serve_event_gate = fp.serve_event_gate

    # 3c) Raid ranking state (RaidRankingStateInfoResponse `rgGd0q21`): the raid tab's Rewards button opens
    #     the native GateMissionRaidRewardScene only when isRankingExist() is true; without the group the
    #     singleton keeps its constructor zeros and the touch falls back to the (offline-dead) banner URL.
    fp.serve_event_gate = _jp_gate_raid_ranking(fp.serve_event_gate)
    pl.serve_event_gate = fp.serve_event_gate

    # 3d) Rm test (2026-11-13): `Q4kJKh8b` for the 5040 tile, chained AFTER the two wrappers above so all
    #     three run (each only adds its own group; none reads the others' keys).
    fp.serve_event_gate = _jp_gate_rm_event(fp.serve_event_gate)
    pl.serve_event_gate = fp.serve_event_gate

    # 3e) Parade tiles (2026-11-14): `gXrD1h58` so the subtype-12 touch branch finds its ParadeEventInfo.
    fp.serve_event_gate = _jp_gate_parade_events(fp.serve_event_gate)
    pl.serve_event_gate = fp.serve_event_gate

    # 3f) Parade party: 16 decks so the client does not append its own 16 (see _jp_pad_parade_decks).
    import player_state as _ps
    if not getattr(_ps.PlayerState.special_party, '_jp_padded', False):
        _ps.PlayerState.special_party = _jp_pad_parade_decks(_ps.PlayerState.special_party)
        _ps.PlayerState.special_party._jp_padded = True

    # 4) 734 is a raid event: personal_event makes the JP raid menu (RaidMenuInfoResponse `dg5ZV3kQ`,
    #    UserRaidInfoResponse `71ctQHWm`) serve the boss name/level/HP/points and the level-down rest time.
    #    JP lacks 3 of its GL reward ids and reward banner 900073401, so personal_event is WRAPPED: every
    #    caller gets a deep-copied event with the unresolvable rows and the absent banner removed
    #    (_jp_raid_event). JP_EVENT_RAID=False restores the old "no raid screen" behaviour.
    import exvius_raid_progress as rp
    if JP_EVENT_RAID:
        global _JP_RAID_BASE
        _JP_RAID_BASE = rp.personal_event
        rp.personal_event = _jp_personal_raid
        rp.personal_menu_groups = _jp_raid_menu_groups(rp.personal_menu_groups)
        try:
            import exvius_actions as ea
            if 'g0BjrU5D' in ea.HANDLERS:
                ea.HANDLERS['g0BjrU5D'] = _jp_raid_menu_trace(ea.HANDLERS['g0BjrU5D'])
        except Exception as exc:
            print('JP compat: raid menu trace not installed: %r' % (exc,), flush=True)
    else:
        rp.personal_event = _jp_no_personal_raid

    # 5) Optional per-area mission-row cap (default OFF; see install_mission_cap).
    if JP_EVENT_MISSION_LIMIT:
        install_mission_cap(JP_EVENT_MISSION_LIMIT)

    fp._jp_events_installed = True
    shown = ','.join(areas[:8]) + (',...(%d total)' % len(areas) if len(areas) > 8 else '')
    print('JP compat: event gate areas %s (mode %s), tab %s, currency %r, raid %s, art %s, archive off'
          % (shown, JP_EVENT_AREAS_MODE, JP_EVENT_TAB, JP_EVENT_CURRENCY, JP_EVENT_RAID,
             'raid_king_mog' if JP_EVENT_RAID else JP_EVENT_ART), flush=True)


def install_mission_cap(limit):
    """Trim each JP area's gate rows to `limit`. NOT recommended (JP_EVENT_MISSION_LIMIT = 0).

    serve_event_gate appends one `0xkoNP8U` row per mission of the area (ffbe_player.py:2952-2970) because
    GateUtil::isOpenMission needs the mission's OWN row to open its difficulty (the comment at :2952-2954:
    "One row for the first difficulty cannot open ADV, PRO or ELT"). Trimming therefore HIDES difficulties.
    Measured on the JP masters: 734 = 5 rows (~1.5 KB), 888 = 100 rows, and 734+888 = 74,716 bytes;
    adding 5250+746 gives 208 rows / 146,477 bytes. Limit the number of open areas first; use a cap only
    if a single area must be opened partially.
    """
    import ffbe_player as fp
    import ffbe_pipeline as pl
    inner = fp.serve_event_gate
    areas = {str(a) for a in _jp_event_area_ids()}

    def serve_event_gate(spec, reply_id):
        out = inner(spec, reply_id)
        if not isinstance(out, dict):
            return out
        rows = out.get(fp.EVENT_GATE_TAG)
        if not isinstance(rows, list):
            return out
        kept, counts = [], {}
        for row in rows:
            area = str(row.get('uv60hgDW')) if isinstance(row, dict) else ''
            if area in areas:
                seen = counts.get(area, 0)
                if seen >= limit:
                    continue
                counts[area] = seen + 1
            kept.append(row)
        if len(kept) == len(rows):
            return out
        out = dict(out)
        out[fp.EVENT_GATE_TAG] = kept
        return out

    fp.serve_event_gate = serve_event_gate
    pl.serve_event_gate = serve_event_gate     # ffbe_pipeline holds its own name (ffbe_pipeline.py:48)
    print('JP compat: event gate mission cap %d per area (difficulties beyond it stay locked)' % limit,
          flush=True)

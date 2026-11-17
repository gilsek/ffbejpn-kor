"""JP-only summon projection adjustments; installed by android_game.start."""


def normalize_ticket_rarity(rar):
    """Normalize JP F_TICKET_MST.9fW0TePj weighted strings (e.g. '4:95000000,...#4:90000000,...')
    to their minimum guaranteed base rarity integer string so int() casts in roll_gacha succeed."""
    s = str(rar if rar is not None else '').strip()
    if not s or s.isdigit():
        return s
    last_block = s.split('#')[-1].split('@')[0]
    rars = []
    for part in last_block.split(','):
        part = part.strip()
        if ':' in part:
            k, _, weight = part.partition(':')
            k = k.strip()
            weight = weight.strip()
            if k.isdigit() and (not weight.isdigit() or int(weight) > 0):
                rars.append(int(k))
        elif part.isdigit():
            rars.append(int(part))
    return str(min(rars)) if rars else '0'


def _default_gold_button(cost, draws):
    kind = str((cost or {}).get('kind') or 'free')
    if kind == 'friend_point':
        return 'gacha_btn_n'
    if kind == 'free':
        return 'gacha_btns_gold_free_1'
    if kind == 'lapis':
        n = int(draws or 1)
        return f'gacha_btns_gold_{n}' if 1 <= n <= 11 else 'gacha_btn_r_multi'
    if kind in ('item', 'important'):
        return 'gacha_btns_gold_1' if (cost or {}).get('is_coin') else 'gacha_btn_r_ticket'
    return 'gacha_btns_gold_1'


def _detail_button(cost, draws):
    """Buttons sized 304x136 for GachaDetailScene (layout == 0), matching its price/icon geometry."""
    kind = str((cost or {}).get('kind') or ('free' if isinstance(cost, dict) else ''))
    if kind == 'friend_point':
        return 'gacha_btn_n'
    if kind in ('item', 'important'):
        return 'gacha_btn_r_ticket'
    if not kind:
        return 'gacha_btn_r'
    if kind == 'free' or (kind == 'lapis' and int((cost or {}).get('amount') or 0) <= 0):
        return 'gacha_btn_r_free'
    n = int(draws or 1)
    if kind == 'lapis' and 2 <= n <= 7:
        return f'gacha_btn_r_{n}times'
    if kind == 'lapis' and n >= 11:
        return 'gacha_btn_r_multi'
    return 'gacha_btn_r'


def normalize_banner_for_jp(banner, gacha):
    """Route banners between GachaPayDetailScene (layout=1, preview stage + 626x184 banner + 204x96 gold buttons)
    and GachaDetailScene (layout=0, 640x392 banner + 304x136 buttons) without mutating the input."""
    b = dict(banner)
    cost = b.get('cost')
    cost0 = cost[0] if isinstance(cost, list) and cost else (cost if isinstance(cost, dict) else {})
    has_cost = bool(cost)
    has_steps = bool(b.get('steps')) or str(b.get('type')) == 'step'
    has_boxes = bool(b.get('boxes'))
    field_units = gacha.gacha_field_units(b)
    if 'kind' in cost0:
        kind = str(cost0.get('kind') or 'free')
    elif not has_cost and b.get('ticket_group_id'):
        kind = ''
    else:
        kind = 'free'
    if has_steps:
        # 2 = new step-up (isNewStepUpGacha: full-screen bg from GachaDetailMst+0xf0 + 640x220 strip);
        # an authored value (0 = old step-up, 640x420 banner slot) wins (2026-11-16 old-layout test).
        b['gacha_layout'] = int(banner.get('stepup_layout', 2))
        return b
    layout = 1 if (field_units and not has_boxes and kind in ('lapis', 'free')) else 0
    b['gacha_layout'] = layout
    gold_btn = getattr(gacha, '_gold_button', _default_gold_button)
    btn_fn = gold_btn if layout == 1 else _detail_button
    btn_cost = cost0 if (has_cost or not b.get('ticket_group_id')) else None
    b['img_btn_primary'] = btn_fn(btn_cost, b.get('draws', 1))
    sec = b.get('secondary_offer')
    if isinstance(sec, dict) and sec:
        sec_copy = dict(sec)
        sec_copy['img_btn'] = btn_fn(sec_copy.get('cost') or btn_cost, sec_copy.get('draws', 11))
        b['secondary_offer'] = sec_copy
    return b


def wire_type(banner, code, original):
    tab_group = banner.get('tab_group') or banner.get('season')
    if tab_group == 'ffbe':
        return 1
    if tab_group == 'ff_series':
        return 2
    if tab_group == 'collaborations':
        return 3
    # JP has no GL Limited Time tab (50). Box type 7 is already a JP FREE type;
    # changing it to 1 incorrectly moves coin-funded boxes onto the lapis tab.
    value = original(banner, code)
    # GL's explicit tab='limited' wins over item costs in gacha_archive.wire_type.
    # JP files ordinary ticket/coin/free/friend summons on its free tab. Preserve
    # structural step, select/exchange and box codes so their native flows survive.
    costs = banner.get('cost')
    entries = costs if isinstance(costs, list) else [costs or {}]
    if (not banner.get('steps') and not banner.get('selection') and not banner.get('boxes')
            and value not in (5, 6, 7, 8)
            and all(isinstance(c, dict) and c.get('kind', 'free') in ('item', 'important', 'free', 'friend_point') for c in entries)):
        return 0
    return 1 if value == 50 else value


STAR = {1: '★1', 2: '★2', 3: '★3', 4: '★4', 5: '★5', 6: '★6', 7: 'NV', 8: 'NV'}


def rates_page(banner_id):
    """Korean drop-rate page for the JP client's rate WebView (summons_list.php?SummonsId=<id>)."""
    import json as _json
    from html import escape
    from pathlib import Path as _Path
    import ffbe_gacha
    from player_state import expand_pool
    banner = next((b for b in ffbe_gacha.all_banners() if str(b['id']) == str(banner_id)), None)
    if banner is None:
        return None
    global _NAMES_KO
    if _NAMES_KO is None:
        try:
            _NAMES_KO = _json.loads(_Path(__file__).with_name('jp_unit_names_ko.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _NAMES_KO = {}
    pool = [r for r in expand_pool(banner) if r.get('unit_id')]
    total = sum(max(0.0, float(r.get('rate', 0))) for r in pool) or 1.0
    tiers = {}
    for r in pool:
        tiers.setdefault(int(r.get('rarity') or 0), []).append(r)
    body = '<h1>' + escape(str(banner.get('name') or '')) + '</h1><p class="notice">단발과 11연 모두 아래 확률로 뽑습니다. '         '유닛 ' + str(len(pool)) + '종.</p><table><thead><tr><th>등급</th><th>종류</th><th>합계</th></tr></thead><tbody>'
    for rar in sorted(tiers, reverse=True):
        share = sum(float(r['rate']) for r in tiers[rar]) * 100 / total
        body += '<tr><td>%s</td><td>%d</td><td>%.2f%%</td></tr>' % (STAR.get(rar, str(rar)), len(tiers[rar]), share)
    body += '</tbody></table>'
    for rar in sorted(tiers, reverse=True):
        body += '<h2>' + STAR.get(rar, str(rar)) + '</h2><table><tbody>'
        for r in sorted(tiers[rar], key=lambda x: _NAMES_KO.get(str(x['unit_id']), '')):
            uid = str(r['unit_id'])
            body += '<tr><td>%s</td><td>%.4f%%</td></tr>' % (escape(_NAMES_KO.get(uid) or uid),
                                                             float(r['rate']) * 100 / total)
        body += '</tbody></table>'
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>제공 비율</title>'
            '<style>body{margin:0;padding:14px;background:#081d43;color:#fff;font:16px sans-serif}h1{font-size:21px}'
            'h1,h2{color:#ffe398}h2{font-size:18px;margin:18px 0 6px}.notice{padding:12px;background:#15385b;line-height:1.5}'
            'table{width:100%;border-collapse:collapse}th,td{padding:8px;border:1px solid #4b6990;text-align:left}'
            'td:last-child{white-space:nowrap;text-align:right}th{background:#194875}</style></head><body>'
            + body + '</body></html>')


_NAMES_KO = None


def _install_rates_page():
    """The JP client opens .../web/statics/summons_list.php?SummonsId=<id>; the Global engine only knows
    /exvius/gacha-rates/<id>.html and answered 404 (blank rate screen, device log 2026-11-16 09:06)."""
    import re
    import sys
    import gacha_rates
    gacha_rates.page = rates_page
    handlers = {getattr(m, 'Handler', None) for m in list(sys.modules.values())}
    handlers = [h for h in handlers if h is not None and hasattr(h, '_cdn_fetch')]
    for handler in handlers:
        original = handler._cdn_fetch

        def fetch(self, _original=original):
            m = re.search(r'/web/statics/summons_list\.php\?(?:.*&)?SummonsId=(\d+)', self.path)
            if m:
                self.path = '/exvius/gacha-rates/' + m.group(1) + '.html'
            return _original(self)
        handler._cdn_fetch = fetch
    print('JP: summon rate page routed for ' + str(len(handlers)) + ' handler class(es)', flush=True)


def install(gacha):
    original_units = gacha.gacha_field_units
    # Season banners pose every top-rarity unit of the banner (user decision 2026-11-16); the engine's own
    # one-unit limit stays for banners without preview_units.
    # Brave Shift on the field: the client groups units by NV series (F_UNIT_MST JPW8Vs40 -> UnitMst+0x20c)
    # and shift order (I3SKJ4q0 -> +0x214); BRAVE SHIFT steps the shown unit from order 0 to order 1
    # (GachaPayDetailScene::onSceneVisible 0x1ad4cf4, UnitMstList::getNeoVisionShiftUnit 0x1c714e4). Posing
    # the order-1 row (336000127 Alice/Half Nightmare) made it shift into itself, so pose the series' order-0
    # row (336000117 Alice) and let the button reveal the other form. Repeats collapse to one page.
    try:
        import player_state
        unit_mst = player_state.unit_mst
    except Exception as exc:  # noqa: BLE001
        print('JP: gacha field shift base mapping off (%r)' % (exc,), flush=True)
        unit_mst = None

    def shift_base(u):
        if unit_mst is None:
            return str(u)
        r = unit_mst(str(u)) or {}
        series = str(r.get('JPW8Vs40') or '')
        if str(r.get('I3SKJ4q0') or '0') != '0' and series not in ('', '0', str(u)) and unit_mst(series):
            return series
        return str(u)

    def field_units(banner):
        ids = list(banner['preview_units']) if 'preview_units' in banner else original_units(banner)
        seen, out = set(), []
        for u in ids:
            key = shift_base(u)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out or [str(u) for u in ids[:1]]
    gacha.gacha_field_units = field_units
    # GachaPayDetailScene::getUnitInfoList (0x1adeb94) runs parseSetUnitInfo and getBannerInfoList (0x1adec44) runs
    # parseSetBannerInfo on BOTH detail rows (scene +0x5b0 single, +0x5b8 multi) into ONE vector each.
    # Strip field units and bannerInfo from the secondary (11-summon) row so units don't repeat and the small
    # detail banner stays at 1 static entry without swiping.
    original_detail_row = gacha._gacha_detail_row

    def detail_row(b, art, detail_id, *args, **kwargs):
        det = original_detail_row(b, art, detail_id, *args, **kwargs)
        try:
            secondary = (str(detail_id) == str(gacha.gacha_secondary_detail_id(b))
                         and str(detail_id) != str(b.get('detail_id', '')))
        except Exception:  # noqa: BLE001
            secondary = False
        if secondary and isinstance(det, dict):
            for key in ('t6aQ1voV', 'Rw4fS2m1', 'BUW0I4JL', '4yT7FUqj'):
                det.pop(key, None)
        return det
    gacha._gacha_detail_row = detail_row
    original_wgb = getattr(gacha, 'with_global_buttons', None)
    if original_wgb is not None:
        gacha.with_global_buttons = lambda b: normalize_banner_for_jp(original_wgb(b), gacha)
    original_banners = gacha.all_banners
    gacha.all_banners = lambda: [normalize_banner_for_jp(b, gacha) for b in original_banners()]
    original_cost = gacha._gacha_cost_string

    def jp_cost(cost, draws=1, item_id=0):
        wire = original_cost(cost, draws, item_id)
        if not wire and isinstance(cost, dict) and cost.get('kind', 'free') == 'free':
            # JP Confirm treats an empty cost map as a ticket and dereferences a null ItemMst.
            # A zero-lapis entry takes its valid lapis branch. Empty None cost (e.g. 60001 ticket-only) stays ''.
            return '50:1:0:1'
        if not wire and isinstance(cost, list) and cost and all(isinstance(c, dict) and c.get('kind', 'free') == 'free' for c in cost):
            return '50:1:0:1'
        return wire

    gacha._gacha_cost_string = jp_cost
    try:
        import player_state as ps
        if getattr(ps, 'ticket_by_id', None) and getattr(ps, 'ticket_group_items', None):
            orig_tbi = ps.ticket_by_id
            orig_tgi = ps.ticket_group_items
            def _norm_trow(row):
                return (row[0], row[1], normalize_ticket_rarity(row[2])) if row else row
            ps.ticket_by_id = lambda tid: _norm_trow(orig_tbi(tid))
            ps.ticket_group_items = lambda gid: [_norm_trow(r) for r in orig_tgi(gid)]
        if hasattr(ps, 'PlayerState'):
            rare_ticket_ids = (50, 70, 210, 220, 230, 240, 250)
            # 2026-11-17: dev-time refill (below 50 -> 99) disabled from 0.1.2 by user decision.
            # Tickets already in a save are kept and spent normally.
            JP_RARE_TICKET_REFILL = False

            def _ensure_rare_tickets(player):
                if not JP_RARE_TICKET_REFILL:
                    return
                if player is None or getattr(player, 'mode', None) == 'frozen':
                    return
                changed = False
                for iid in rare_ticket_ids:
                    cur = player.item_count(23, iid)
                    if cur < 50:
                        player.grant_item(23, iid, 99 - cur)
                        changed = True
                if changed:
                    player.dirty = True

            orig_imp_rows = ps.PlayerState.important_item_rows
            orig_roll_gacha = ps.PlayerState.roll_gacha

            def jp_imp_rows(self):
                _ensure_rare_tickets(self)
                return orig_imp_rows(self)

            def jp_roll_gacha(self, banner, repeats=1, ticket_id=None, offer=None):
                _ensure_rare_tickets(self)
                if ticket_id not in (None, '', 0, '0') and not offer:
                    banner = dict(banner, cost=None)
                return orig_roll_gacha(self, banner, repeats, ticket_id, offer=offer)

            ps.PlayerState.important_item_rows = jp_imp_rows
            ps.PlayerState.roll_gacha = jp_roll_gacha
    except Exception:
        pass
    # Season x series banners (build/make_jp_season_banners.py, 2026-11-16).
    try:
        import player_state as ps
        # The engine drops pool units without a row in the GLOBAL text table F_TEXT_UNITS_NAME (a nameless award
        # crashed the Global client). The JP client names units from its own data, and 310 JP-only units (18 whole
        # banners) have no Global row, so the filter must not apply here. Pools are validated against JP F_UNIT_MST
        # by the generator.
        ps._only_named = lambda rows: rows
        import gacha_archive as ga
        # A banner that states its own 'season' stays there: the Global collaboration detector also matches art
        # names (WOTV) and would move series banners out of their season and re-sort the collaboration group.
        original_collab = ga._collaboration
        ga._collaboration = lambda banner: '' if banner.get('season') else original_collab(banner)

        def jp_catalogue(banners):
            ids = [str(b['id']) for b in banners]
            return [{'id': 'all', 'label': 'All', 'ids': ids, 'count': len(ids), 'tab': 0}]
        ga.catalogue = jp_catalogue
        ga.visible_banners = lambda player, banners: [
            dict(b, schedule=dict(b.get('schedule') or {}, disp_order=len(banners) - index))
            for index, b in enumerate(banners)
        ]
    except Exception as exc:  # noqa: BLE001
        print(f'JP: season banner patches NOT installed ({exc!r})', flush=True)
    # Step-up moogle + balloon: GachaDetailScene::setStepUpLayout (0x1af8d1c) skips both when GachaMst+0x70
    # (setExplainLong, wire 'VC9F3eJn' -- GachaMstResponse::readParam key order) is empty. The engine never sends
    # it, so authored banners carry 'mog_message' and it is added to their GachaMst row (2026-11-16).
    try:
        original_groups = gacha.gacha_groups

        def jp_groups(banners):
            out = original_groups(banners)
            msgs = {str(b['id']): str(b['mog_message']) for b in banners if b.get('mog_message')}
            if msgs:
                for row in out.get(getattr(gacha, 'GACHA_MST_TAG', 'PcUrGH13'), []):
                    msg = msgs.get(str(row.get('X1IuZnj2')))
                    if msg:
                        row['VC9F3eJn'] = msg
            return out
        gacha.gacha_groups = jp_groups
    except Exception as exc:  # noqa: BLE001
        print(f'JP: step-up moogle message NOT installed ({exc!r})', flush=True)
    try:
        _install_rates_page()
    except Exception as exc:  # noqa: BLE001
        print(f'JP: rates page NOT installed ({exc!r})', flush=True)
    print('JP: normal lapis/ticket costs restored; gacha_layout/button art aligned; ticket rarities normalized', flush=True)

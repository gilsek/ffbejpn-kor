"""Build the JP offline summon list (user decisions 2026-11-08, docs/plans/2026-11-08-jp-gacha-seasons.md).

  * Global banners released up to 2024-08-31 (Global service end): taken from the engine's own Global data
    (catalogue / community / named / standard / authored), grouped later by the engine's gacha_archive seasons.
  * JP banners from 2024-09-01: from the JP client's own banner art (build/jp_gacha_art.json, gacha_YYYYMMDD_*_top.png).
  * Reruns (復刻 / reprint / rerun) are excluded. Exchange / crown / ticket / box / select / free banners are left out
    (separate scope: tickets & exchange).
  * Pool = the banner's ★5 and NV units only (one summonable form per unit family), all at the same rate, no guarantee.
    Units must exist in BOTH the JP client (F_UNIT_MST) and the engine's unit table, or the engine cannot grant them.
  * JP banners: the series comes from the image name (FFBE / FF5 / WOTV ...); NV-only banners (allNV, NV pickup ...) use
    every NV unit. Banners whose series cannot be told are reported, not guessed.

usage: python -I build/make_jp_banners.py [--out DIR]
writes build/engine_overlay/gacha_authored.json (+ empty Global banner files, gacha_only.txt cleared),
       build/engine_overlay/jp_banner_art.json  (Global art file -> device path, read by build/frida/jp_offline.js),
       build/out/jp_offline/gacha/report.json   (counts, unmatched banners, dropped units).
"""
import copy, io, json, os, re, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
SERVER = OLD / 'upstream/source/server'
STATIC = ROOT / 'build/out/jp_offline/engine/static'
OVERLAY = ROOT / 'build/engine_overlay'
REPORT = ROOT / 'build/out/jp_offline/gacha'
GL_END = '2024-08-31'
JP_FROM = '20240901'
SEASON5 = '20241227'          # altema storykouryakuitiran-20949: 5th season added after the 2024-12-27 maintenance
DEVICE_FILES = 'exvius/data/static'   # relative to /data/data/<pkg>/files
# JP F_UNIT_MST id -> different character in the engine's Global F_UNIT_MST (name and stats both differ)
ID_CONFLICT = {
    '401008507',               # JP ヨシキリ / GL Kaito
    '401008607',               # JP スターライトエレナ / GL Godrea
    '401008707',               # JP イバラ / GL Emperor Foo
    '401014207', '401014217',  # JP ダークナイト ディーン / GL Master Machinist Abigail
    '401014307', '401014317',  # JP 不滅の輝きエレナ / GL Curse of Immunity Melissa
    '401014507', '401014517',  # JP ヒョウ&ブラックレイダー / GL Dark Knight Duane
    '401014607', '401014617',  # JP リヒト / GL Ruin Explorer Nora
}

os.environ.update(GACHA_ONLY='all', GACHA_CAMPAIGN='all', GACHA_STANDARD='1', GACHA_CATALOGUE='1',
                  GACHA_COMMUNITY='1', GACHA_NAMED='1', EXVIUS_SUMMON_ARCHIVE='1',
                  FFBE_DATA=str(STATIC.parent))
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(SERVER))
import decode_client_data as D  # noqa: E402

RERUN = re.compile(r'復刻|reprint|rerun|re-run|encore', re.I)
NOT_SUMMON = re.compile(r'exchange|crown|ticket|_box|box_|kakera|select|choice|free|stmogu|start_dash|item', re.I)
VARIANT = re.compile(r'_(single|1500|11ren|22ren)$')
JP_SERIES = [  # (regex on the image theme, JP F_GAME_TITLE_MST id) -- longest names first
    (r'WOTV', '11010'), (r'FFBE', '11001'), (r'FF5', '10005'), (r'FF11', '10011'), (r'FF6', '10006'),
    (r'FF7', '10007'), (r'FF8', '10008'), (r'FF9', '10009'), (r'FF4', '10004'), (r'FF16', '10016'), (r'FF15', '10015'),
]
NV_ONLY = re.compile(r'allNV|^nv|NVpickup|stepup_NV|NV10percent', re.I)


def jp_masters():
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups()); man[n] = (t, k)
    files = {p.stem.split('_', 1)[1]: p for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}
    def jp(n):
        t, k = man[n]; return D.decode(files[t].read_bytes(), k, localized=False)[1]
    return jp('F_UNIT_MST'), {r['tL6G9egd'] for r in jp('F_ITEM_MST')}, {r['2dfixko3'] for r in jp('F_IMPORTANT_ITEM_MST')}


# Tables whose primary ids a reward can name (unit, item, equipment, materia, key item, esper, vision card, recipe ...).
REWARD_TABLES = ('F_ITEM_MST', 'F_EQUIP_ITEM_MST', 'F_MATERIA_MST', 'F_IMPORTANT_ITEM_MST', 'F_UNIT_MST', 'F_BEAST_MST',
                 'F_VISION_CARD_MST', 'F_RECIPE_MST', 'F_EMBLEM_MST', 'F_TICKET_MST', 'F_ITEM_EXT_BEAST_MST')


def jp_universe():
    """Every primary id in the JP reward-capable tables (first column of each row). A reward/unit id outside this set
    is Global-only: the JP client has no row for it (the 8th-anniversary ticket mail crashed the mail list, 2026-11-09)."""
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups()); man[n] = (t, k)
    man.update({e['table']: (t, e['key']) for t, e in D.getter_manifest(native).items()})
    files = {}
    for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat'):
        tok, ver = p.stem.split('_', 1)[1], int(p.stem.split('_')[0][3:])
        if tok not in files or files[tok][0] < ver:
            files[tok] = (ver, p)
    ids = set()
    for n in REWARD_TABLES:
        if n not in man or man[n][0] not in files:
            continue
        for r in D.decode(files[man[n][0]][1].read_bytes(), man[n][1], localized=False)[1]:
            if r:
                ids.add(str(next(iter(r.values()))))
    return ids


def drop_gl_rewards(value, ok, dropped):
    """Remove reward entries ({kind,id,...} or {reward:{kind,id}}) whose id the JP client does not have. In place."""
    if isinstance(value, dict):
        for v in value.values():
            drop_gl_rewards(v, ok, dropped)
    elif isinstance(value, list):
        keep = []
        for e in value:
            r = e.get('reward') if isinstance(e, dict) and isinstance(e.get('reward'), dict) else e
            if isinstance(r, dict) and 'kind' in r and 'id' in r and 'amount' not in r and not ok(r['kind'], r['id']):
                dropped[str(r['id'])] += 1; continue
            drop_gl_rewards(e, ok, dropped); keep.append(e)
        value[:] = keep


def summonable(unit_ids, rarity_of):
    """One form per unit family (id without its last digit): the lowest rarity that is >= 5."""
    best = {}
    for u in unit_ids:
        r = rarity_of.get(u)
        if r is None or r < 5:
            continue
        fam = u[:-1]
        if fam not in best or r < rarity_of[best[fam]]:
            best[fam] = u
    return sorted(best.values())


def fair(units, rarity_of):
    n = len(units)
    return [{'unit_id': u, 'rarity': rarity_of[u], 'rate': 1.0 / n} for u in units]


def preview_unit(banner, keep, english_names, rarity_of):
    """Match named featured families, in banner-name order; never substitute an unrelated unit."""
    community = banner.get('community') or {}
    # the Global featured list as shipped (before Global-only units are filtered out of the field list)
    featured = [str(u) for u in banner.get('_featured_shipped', community.get('unit_ids')) or []]
    if isinstance(banner.get('pool'), dict):
        featured += [str(u) for tier in banner['pool'].get('tiers') or [] for u in tier.get('featured') or []]
    families = {u[:-1]: u for u in keep}
    order = {name.casefold(): i for i, name in enumerate(community.get('units') or [])}
    candidates = [u for u in dict.fromkeys(featured) if u[:-1] in families]
    candidates.sort(key=lambda u: (order.get(english_names.get(u, '').casefold(), len(order)), featured.index(u)))
    if candidates:
        return [families[candidates[0][:-1]]], 'featured family, banner name order'
    if featured:
        return [], 'featured unit absent from JP-compatible pool'
    return sorted(keep, key=lambda u: (-rarity_of[u], u))[:1], 'pool example (no named featured data)'


def lapis_price(draws):
    """Play price (2026-11-17 user decision): single 50 lapis, 11-draw 500; other counts 50 per draw."""
    n = int(draws or 1)
    return 500 if n >= 11 else 50 * n


def one_lapis(value, draws=1):
    """Lapis price by draw count, including secondary offers and steps; other currencies are unchanged.
    A cost dict takes the draws of the banner/offer/step that holds it. (Name kept: callers predate the price.)"""
    if isinstance(value, dict):
        d = value.get('draws', draws)
        return {k: (lapis_price(d) if k == 'amount' and value.get('kind') == 'lapis' else one_lapis(v, d))
                for k, v in value.items()}
    if isinstance(value, list):
        return [one_lapis(v, draws) for v in value]
    return value


def pool_units(pool, base_units):
    """Unit ids a pool can give. A tier without a unit list means "every unit of that rarity" (engine-resolved);
    expand it here to the JP-known units of that base rarity so nothing Global-only can be drawn."""
    if isinstance(pool, list):
        return [str(e['unit_id']) for e in pool if isinstance(e, dict) and e.get('unit_id')]
    if isinstance(pool, dict):
        ids = []
        for t in pool.get('tiers') or []:
            ids += [str(u) for u in (t.get('units') or []) + (t.get('featured') or [])]
            if not t.get('units') and int(t.get('rarity') or 0) >= 5:
                ids += base_units.get(int(t['rarity']), [])
        return ids
    return []


def png_dims(path):
    try:
        with open(path, 'rb') as fh:
            head = fh.read(24)
        if len(head) >= 24 and head[:8] == b'\x89PNG\r\n\x1a\n':
            import struct
            return struct.unpack('>II', head[16:24])
    except OSError:
        pass
    return None


def art_index():
    """basename -> (device-relative path, (w, h)|None) for every Global art file in the engine's static tree."""
    idx = {}
    dims = {}
    roots = [STATIC / 'cpk_extract', STATIC / 'gacha_community', STATIC / 'client/files']
    for r in roots:
        for p in r.rglob('*'):
            if p.suffix.lower() in ('.png', '.jpg') and p.is_file():
                if p.name not in idx:
                    idx[p.name] = DEVICE_FILES + '/' + p.relative_to(STATIC).as_posix()
                    wh = png_dims(p)
                    if wh:
                        dims[p.name] = wh
    return idx, dims


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    idx, file_dims = art_index()
    summon_art = json.loads((SERVER / 'summon_art.json').read_text(encoding='utf-8'))
    img_dims = {k: tuple(v) for k, v in (summon_art.get('images') or {}).items() if isinstance(v, list) and len(v) == 2}
    img_dims.update(file_dims)
    wide_map = summon_art.get('wide') or {}
    jp_units, jp_items, jp_important = jp_masters()
    english_names = {}
    for line in (STATIC / 'text_decoded/F_TEXT_UNITS_NAME.ndjson').read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        english_names[row['key'].removeprefix('MST_UNIT_NAME_')] = row['v'][0]
    jp_names = {r['3HriTp6B']: r.get('G4L0YIB2', '') for r in jp_units}
    engine_units = {}
    for line in open(STATIC / 'mst_decoded/F_UNIT_MST.ndjson', encoding='utf-8'):
        r = json.loads(line); engine_units[r['3HriTp6B']] = r
    # Not summonable (2026-11-09, docs/plans/2026-11-09-unit-id-mismatch.md):
    #  * JP `A86KwrGh` = 0: NPC/guest rows (e.g. 100014905 Madam: all stats 0, no abilities, list icon falls back to Rain)
    #  * ID_CONFLICT: the same id is a different character in JP and in the engine's Global table
    rarity_of = {r['3HriTp6B']: int(r['9fW0TePj']) for r in jp_units
                 if r['3HriTp6B'] in engine_units and str(r.get('9fW0TePj', '')).isdigit()
                 and str(r.get('A86KwrGh', '1')) != '0' and r['3HriTp6B'] not in ID_CONFLICT}
    title_of = {r['3HriTp6B']: r['taQ69cIx'] for r in jp_units}
    fam_min = {}
    for u, r in rarity_of.items():
        fam_min[u[:-1]] = min(r, fam_min.get(u[:-1], 99))
    base_units = {5: sorted(u for u, r in rarity_of.items() if r == 5 and fam_min[u[:-1]] == 5),
                  7: sorted(u for u, r in rarity_of.items() if r == 7 and fam_min[u[:-1]] == 7)}   # 7 = NV
    report = {'dropped_units': Counter(), 'unmatched_jp': [], 'empty_pool': [], 'excluded_rerun': [],
              'excluded_not_summon': [], 'excluded_not_lapis': [], 'preview_audit': [],
              'dropped_field_units': Counter(), 'dropped_rewards': Counter()}
    universe = jp_universe()

    def reward_ok(kind, rid):
        rid = str(rid)
        if str(kind) == '10':                      # unit reward: must be grantable by the engine and drawable by JP
            return rid in rarity_of or (rid in universe and rid in engine_units and rid not in ID_CONFLICT)
        return rid in universe

    import ffbe_gacha as G
    from gacha_archive import catalogue
    gl = G.all_banners()
    groups = catalogue(gl)
    listed = {bid for g in groups for bid in g['ids']}
    out = []
    for b in gl:
        bid = str(b['id'])
        if bid not in listed:
            continue                                   # alias / duplicate the archive already collapses
        rel = str((b.get('community') or {}).get('release') or b.get('release') or '')
        if rel and rel[:10] > GL_END:
            continue
        name = str(b.get('name') or '')
        if RERUN.search(name):
            report['excluded_rerun'].append(name); continue
        cost = b.get('cost'); cost = cost[0] if isinstance(cost, list) and cost else cost
        kind = cost.get('kind') if isinstance(cost, dict) else None
        cid = str((cost or {}).get('item_id') or (cost or {}).get('id') or '') if isinstance(cost, dict) else ''
        ok = (kind in ('lapis', 'friend_point', 'free') or (kind == 'item' and cid in jp_items)
              or (kind == 'important' and cid in jp_important)
              or (not kind and str(b.get('ticket_group_id') or '') == '10010'))
        if not ok:     # a ticket / event currency the JP client does not know: cannot be shown or spent
            report['excluded_not_lapis'].append(f"{bid} {name} ({kind} {cid})"); continue
        b = copy.deepcopy(b)
        # Global-only ids anywhere else in the banner (2026-11-09, docs/plans/2026-11-09-gl-jp-audit.md):
        #  * community.unit_ids = the units posed on the detail field (GachaDetailMst t6aQ1voV)
        #  * bonus / box / reward-pool rewards (granted by the summon itself)
        com = b.get('community')
        if isinstance(com, dict) and com.get('unit_ids'):
            before = [str(u) for u in com['unit_ids']]
            b['_featured_shipped'] = before
            com['unit_ids'] = [u for u in before if u in rarity_of]
            for u in before:
                if u not in rarity_of:
                    report['dropped_field_units'][u] += 1
        rate_sum = sum(float(e.get('rate') or 0) for e in b.get('reward_pool') or [] if isinstance(e, dict))
        drop_gl_rewards(b, reward_ok, report['dropped_rewards'])
        if b.get('reward_pool') and rate_sum:
            left = sum(float(e.get('rate') or 0) for e in b['reward_pool'])
            for e in b['reward_pool']:
                e['rate'] = float(e.get('rate') or 0) * rate_sum / left
        if ('reward_pool' in b and not b['reward_pool']) or ('boxes' in b and not any(b['boxes'])):
            report['empty_pool'].append(f"{bid} {name} (all rewards Global-only)"); continue
        if b.get('pool') is not None and not b.get('steps') and not b.get('boxes') and str(b.get('type')) != 'friend':
            ids = pool_units(b['pool'], base_units)
            keep = summonable([u for u in ids if u in rarity_of], rarity_of)
            for u in ids:
                if u not in rarity_of:
                    report['dropped_units'][u] += 1
            if not keep:
                report['empty_pool'].append(f"{bid} {name}"); continue
            b['preview_units'], basis = preview_unit(b, keep, english_names, rarity_of)
            report['preview_audit'].append({'id': bid, 'banner': name, 'basis': basis,
                'units': [{'id': u, 'english': english_names.get(u, ''), 'jp': jp_names.get(u, '')}
                          for u in b['preview_units']]})
            b['pool'] = fair(keep, rarity_of)
            b.pop('guarantee', None)
            if isinstance(b.get('secondary_offer'), dict):
                b['secondary_offer'].pop('guarantee', None)
        has_preview = bool(b.get('preview_units') if 'preview_units' in b else (b.get('community') or {}).get('unit_ids'))
        if has_preview and not b.get('steps') and not b.get('boxes') and kind in ('lapis', 'free'):
            # GachaPayDetailScene's detail slot (`gacha_pay_main_banner`) is 626x184 wide; swap tall 640x392 detail
            # images for their wide variant (or list banner) when available so they are not pillarboxed or cropped.
            bart = b.get('art') or {}
            detail = str(bart.get('detail_banner') or '')
            dh = (img_dims.get(detail) or (0, 0))[1]
            if dh > 200 or not detail:
                for cand in (wide_map.get(detail), bart.get('banner')):
                    cwh = img_dims.get(str(cand or ''))
                    if cand and str(cand) in idx and cwh and 0 < cwh[1] <= 200:
                        bart['detail_banner'] = str(cand)
                        break
        b.pop('_featured_shipped', None)
        b['source'] = 'global'
        out.append(b)
    n_gl = len(out)

    # ---- JP banners from the JP client's own art ----
    art = json.loads((ROOT / 'build/jp_gacha_art.json').read_text(encoding='utf-8'))
    themes = {}
    for nm in sorted(art):
        m = re.match(r'gacha_(\d{8})_(.+)_top\.png$', nm)
        if not m or m.group(1) < JP_FROM:
            continue
        date, theme = m.groups()
        if RERUN.search(theme):
            report['excluded_rerun'].append(nm); continue
        if NOT_SUMMON.search(theme):
            report['excluded_not_summon'].append(nm); continue
        base = VARIANT.sub('', theme)
        themes.setdefault((date, base), []).append((theme, nm))
    nv_units = base_units[7]
    for i, ((date, base), entries) in enumerate(sorted(themes.items())):
        names = [nm for _, nm in entries]
        top = f'gacha_{date}_{base}_top.png'
        top = top if top in art else names[0]
        title = next((t for rx, t in JP_SERIES if re.search(rx, base)), None)
        if title:
            units = summonable([u for u in rarity_of if title_of.get(u) == title], rarity_of)
        elif NV_ONLY.search(base):
            units = nv_units
        else:
            report['unmatched_jp'].append(top); continue
        if not units:
            report['empty_pool'].append(top); continue
        preview = sorted(units, key=lambda u: (-rarity_of[u], u))[:1]
        wide_cands = [f'gacha_{date}_{base}_single.png']
        for th, _ in entries:
            wide_cands.extend([f'gacha_{date}_{th}_single.png', f'gacha_{date}_{th}_01.png'])
        wide_cands.append(f'gacha_{date}_{base}_01.png')
        if preview:
            # GachaPayDetailScene has a 626x184 wide banner slot; prefer *_single / *_01 or fall back to *_top
            # instead of bare gacha_<date>_<base>.png (which is often 640x392 for GachaDetailScene).
            detail = next((d for d in wide_cands if d in art), top)
        else:
            detail = next((d for d in [f'gacha_{date}_{base}.png'] + wide_cands if d in art), top)
        y, mo, d = date[:4], date[4:6], date[6:]
        out.append({
            'id': str(9800000 + i), 'region': 'jp', 'type': 'normal', 'source': 'jp',
            'name': f'{base} ({y}/{mo}/{d})', 'detail_id': str(9800000 + i), 'exe_type': 'primary',
            'cost': {'kind': 'lapis', 'amount': 500}, 'draws': 1,
            'release': f'{y}-{mo}-{d}', 'season': 'season5' if date >= SEASON5 else 'season4',
            'schedule': {'disp_order': 1, 'banner_type': 0, 'window': {'from': f'{y}-{mo}-{d} 00:00:00', 'to': '2099-12-31 23:59:59'}},
            'art': {'banner': top, 'detail_banner': detail, 'anime_file': 'gacha_animation',
                    'anime_name': 'gacha_moogle_rare/anime', 'img_btn': 'gacha_btn_n'},
            'pool': fair(units, rarity_of),
            'preview_units': preview,
        })
    n_jp = len(out) - n_gl

    # ---- Global art the JP client has to be fed (not in the JP CPKs) ----
    # The JP client only draws names its CRI file system finds, so each Global art file gets a STAND-IN: an existing
    # JP CPK image this list never shows, with a byte size no other indexed image has. The banner is served under the
    # stand-in name; build/frida/jp_offline.js swaps the decoded bytes for the Global PNG (matched by that size).
    sizes = Counter(v['size'] for v in art.values())
    used_jp = {(b.get('art') or {}).get(k) for b in out if b.get('source') == 'jp' for k in ('banner', 'detail_banner')}
    # Only the gacha CPKs: the banner CPKs are not bound while the summon screen loads (run29: list stayed empty).
    pool = [n for n, v in sorted(art.items()) if sizes[v['size']] == 1 and n.endswith('.png') and n not in used_jp
            and v['cpk'].startswith('gacha') and re.match(r'gacha_\d{8}_', n)]
    standin, feed, missing = {}, {}, []
    for b in out:
        if b.get('source') != 'global':
            continue
        a = b.get('art') or {}
        for key in ('banner', 'detail_banner'):
            n = a.get(key)
            if not n or n in art:
                continue
            if n not in idx:
                missing.append(n); continue
            if n not in standin:
                if len(standin) >= len(pool):
                    raise SystemExit('not enough stand-in images (%d)' % len(pool))
                sub = pool[len(standin)]
                standin[n] = sub
                feed[sub] = {'path': idx[n], 'size': art[sub]['size'], 'global': n}
            a[key] = standin[n]
    subs = pool
    # Event/gate tile art (event_<area>.png): the same size-keyed stand-in mechanism, registered by
    # build/make_jp_event_art.py. Keep the entries when this script regenerates the map, or the gate rows
    # would fall back to the dummy plate again (build/out/vortex_season/crash_analysis.md section 4).
    _event_map = ROOT / 'build/engine_overlay/jp_event_art.json'
    if _event_map.is_file():
        feed.update((json.loads(_event_map.read_text(encoding='utf-8')).get('art') or {}))
    authored = json.loads((SERVER / 'gacha_authored.json').read_text(encoding='utf-8'))
    authored['banners'] = out
    authored['_meta'] = dict(authored.get('_meta') or {}, jp_build='build/make_jp_banners.py (Global <= %s + JP >= %s)' % (GL_END, JP_FROM))
    OVERLAY.mkdir(parents=True, exist_ok=True)
    (OVERLAY / 'gacha_authored.json').write_text(json.dumps(authored, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    empty = '{"banners": [], "campaigns": {}, "standard": []}\n'
    for f in ('gacha_catalogue.json', 'gacha_community.json', 'gacha_named.json', 'gacha_standard.json'):
        (OVERLAY / f).write_text(empty, encoding='utf-8')    # everything now lives in gacha_authored.json
    (OVERLAY / 'gacha_only.txt').write_text('', encoding='utf-8')
    # Rewrite only `art`: the other top-level keys (stamp from build/make_jp_event_art.py, note, ...) must survive,
    # or the engine table and the device table would lose their version match.
    art_path = OVERLAY / 'jp_banner_art.json'
    document = {'art': feed}
    if art_path.is_file():
        try:
            existing = json.loads(art_path.read_text(encoding='utf-8'))
        except ValueError:
            existing = None
        if isinstance(existing, dict):
            document = existing
            document['art'] = feed
    art_path.write_text(json.dumps(document, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')

    rep = {'stand_in_pool': len(subs), 'global_banners': n_gl, 'jp_banners': n_jp, 'art_fed': len(feed), 'art_missing': sorted(set(missing)),
           'unmatched_jp': report['unmatched_jp'], 'empty_pool': report['empty_pool'],
           'preview_audit': report['preview_audit'],
           'excluded_rerun': len(report['excluded_rerun']), 'excluded_not_summon': len(report['excluded_not_summon']),
           'dropped_unit_ids': len(report['dropped_units']), 'excluded_not_lapis': report['excluded_not_lapis'],
           'dropped_field_unit_ids': len(report['dropped_field_units']),
           'dropped_reward_ids': dict(report['dropped_rewards']),
           'by_year': dict(sorted(Counter(str((b.get('community') or {}).get('release') or b.get('release') or '----')[:4] for b in out).items()))}
    (REPORT / 'report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in rep.items()}, ensure_ascii=False))


if __name__ == '__main__':
    # --out DIR: write the overlay files and report.json to DIR instead (build/engine_overlay is baked into every
    # APK build, so generate + validate elsewhere first, then copy in one go)
    if len(sys.argv) == 3 and sys.argv[1] == '--out':
        OVERLAY = REPORT = Path(sys.argv[2]).resolve()
    main()

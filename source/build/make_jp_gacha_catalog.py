"""Phase 1 of the JP-original summon rebuild: a read-only catalogue of JP gachas from JP client data.

Sources (all JP, nothing Global):
  * F_BANNER_MST type 4 rows: target (1X65WPLU) = JP gacha id, name, home rotation banner (2017-03 .. 2022-03)
  * F_TICKET_MST: ticket group id == gacha id for per-banner pickup groups (50xxx/72xxx/77xxx ...)
  * F_GACHA_EFFECT_PATTERN_MST: gacha ids that carry their own summon effect rows
  * build/jp_gacha_art.json: art files shipped in the JP client CPKs (gacha1..6, banner1/2/home1)
  * F_UNIT_MST: JP unit names, for featured-unit guesses from the banner name

usage: python -I -X utf8 build/make_jp_gacha_catalog.py
writes build/out/jp_offline/gacha_jp/catalog.json and report.md (no engine/device change).
"""
import collections, io, json, re, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
MST = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
OUT = ROOT / 'build/out/jp_offline/gacha_jp'
ART = json.loads((ROOT / 'build/jp_gacha_art.json').read_text(encoding='utf-8'))
TYPE4_END = '20220318'          # last dated type-4 gacha link in F_BANNER_MST


def load(name):
    return [json.loads(l) for l in (MST / name).read_text(encoding='utf-8').splitlines() if l.strip()]


# id // 1000 -> kind. Families outside this table are events/shops (2xxx-6xxx, 1400xxx-1600xxx) and are skipped.
FAMILY = {11: 'friend', 41: 'free', 42: 'free', 43: 'free', 44: 'free', 50: 'lapis', 51: 'lapis',
          60: 'box', 61: 'step', 71: 'raid', 72: 'special', 77: 'gift', 78: 'box'}
RERUN = re.compile(r'復刻')
NOT_FREE = re.compile(r'半額|ラピス')


def kind_of(gid, name):
    k = FAMILY.get(gid // 1000)
    if k == 'free' and '無料' not in name and NOT_FREE.search(name):
        k = 'lapis'
    if k == 'lapis' and 'ステップアップ' in name:
        k = 'step'
    if k == 'lapis' and 'ボックス' in name:
        k = 'box'
    return k


def date_of(*texts):
    for t in texts:
        m = re.search(r'(20\d{6})', t or '')
        if m:
            return m.group(1)
    # bnr_2021210_* / 2021217 / 2021228: 2021-12의 '1'이 하나 빠진 7자리 표기(이웃 gid 61381/61388/61394의 날짜와 일치).
    for t in texts:
        m = re.search(r'(?<!\d)2021(2\d\d)(?!\d)', t or '')
        if m:
            return '20211' + m.group(1)
    # 8자리가 없으면 월 단위 표기(SP召喚チケット2020/9 등)를 YYYYMM으로 쓴다. 이 값은 일 단위가 아니다.
    for t in texts:
        m = re.search(r'(20\d{2})/(\d{1,2})(?!\d)', t or '')
        if m:
            return f'{m.group(1)}{int(m.group(2)):02d}'
    return ''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    banners = load('F_BANNER_MST.ndjson')
    tickets = load('F_TICKET_MST.ndjson')
    effect_ids = {int(r['X1IuZnj2']) for r in load('F_GACHA_EFFECT_PATTERN_MST.ndjson')}
    imp = {r['2dfixko3']: r.get('G4L0YIB2', '') for r in load('F_IMPORTANT_ITEM_MST.ndjson')}
    items = {r['tL6G9egd']: r.get('G4L0YIB2', '') for r in load('F_ITEM_MST.ndjson')}
    units = load('F_UNIT_MST.ndjson')

    groups = collections.defaultdict(list)
    for t in tickets:
        groups[int(t['zF6QIY2r'])].append(t)

    def ticket_name(t):
        return (imp if t['89EvGKHx'] == '23' else items).get(t['tL6G9egd'], '')

    # JP unit names (collectible, base rarity >= 5) for featured guesses; longest names first.
    fam_min = {}
    for u in units:
        if str(u.get('A86KwrGh', '1')) == '0' or not str(u.get('9fW0TePj', '')).isdigit():
            continue
        fam_min[u['3HriTp6B'][:-1]] = min(int(u['9fW0TePj']), fam_min.get(u['3HriTp6B'][:-1], 99))
    name_units = collections.defaultdict(set)
    for u in units:
        uid, nm = u['3HriTp6B'], (u.get('G4L0YIB2') or '').strip()
        if len(nm) >= 2 and fam_min.get(uid[:-1], 0) >= 5:
            name_units[nm].add(uid[:-1])
    names_sorted = sorted(name_units, key=len, reverse=True)

    # 짧은 이름(イド/リース/ナル 등)은 카타카나 단어 안에 든 경우를 뺀다: レイド召喚, リリース記念, ファイナル.
    # 긴 이름은 앞뒤 경계를 보지 않는다(NVクリスマスシャルロット 같은 붙은 표기를 살리려고).
    KANA = 'ァ-ヶー'
    def featured(text):
        hits, rest = [], text
        for nm in names_sorted:
            pat = re.escape(nm)
            if len(nm) <= 3:
                pat = f'(?<![{KANA}]){pat}(?![{KANA}])'
            rx = re.compile(pat)
            if rx.search(rest):
                hits.append(nm)
                rest = rx.sub('\0', rest)
        return hits

    jp_list_art = collections.defaultdict(list)     # date -> JP gacha_* art files
    for f in ART:
        d = date_of(f) if f.startswith('gacha_') else ''
        if d:
            jp_list_art[d].append(f)

    cat, skipped = [], collections.Counter()
    seen = set()
    for r in banners:
        if r['w2A76noc'] != '4' or not r['1X65WPLU'].isdigit():
            continue
        gid = int(r['1X65WPLU'])
        name = r.get('G4L0YIB2') or ''
        k = kind_of(gid, name)
        if not k:
            skipped[gid // 1000 if gid < 1000000 else gid // 100000 * 100] += 1
            continue
        if gid in seen:
            continue
        seen.add(gid)
        d = date_of(r.get('6Dgaqir0'), name)
        cat.append({'gacha_id': gid, 'source': 'banner_mst', 'name_ja': name, 'kind': k, 'date': d,
                    'rerun': bool(RERUN.search(name)),
                    'home_art': r.get('6Dgaqir0') or '', 'home_art_in_client': (r.get('6Dgaqir0') or '') in ART,
                    'list_art_same_day': sorted(jp_list_art.get(d, [])),
                    'ticket_group': gid if gid in groups else None,
                    'effect_rows': gid in effect_ids,
                    'featured_names': featured(name)})

    # Per-banner ticket groups that no type-4 row names (mostly after 2022-03): the group's own pickup ticket
    # names the banner (e.g. 50247 = FFVIIピックアップ召喚チケット).
    for gid, rows in sorted(groups.items()):
        if gid in seen or gid < 50000:
            continue
        own = [ticket_name(t) for t in rows]
        own = [n for n in own if n and not re.match(r'^(レア|★)', n)] or own
        name = own[-1] if own else ''
        # 아이템 종류 20만으로 된 그룹: 71=레이드, 72/77=SP召喚(스페셜). 예전엔 72/77도 raid로 찍혔다(SP召喚チケット 62개).
        only20 = all(t['89EvGKHx'] == '20' for t in rows)
        tk_kind = 'lapis'
        if only20 and gid // 1000 == 71:
            tk_kind = 'raid'
        elif only20 and gid // 1000 in (72, 77):
            tk_kind = 'special'
        cat.append({'gacha_id': gid, 'source': 'ticket_group', 'name_ja': name,
                    'kind': tk_kind,
                    'date': date_of(name), 'rerun': bool(RERUN.search(name)), 'home_art': '', 'home_art_in_client': False,
                    'list_art_same_day': [], 'ticket_group': gid, 'effect_rows': gid in effect_ids,
                    'ticket_items': [(t['89EvGKHx'], t['tL6G9egd'], ticket_name(t)) for t in rows],
                    'featured_names': featured(name)})
        seen.add(gid)

    # After the type-4 links end: one entry per JP list-art theme (gacha_<date>_<theme>_top.png).
    # 같은 날 '<테마>_single' / '<테마>_1500'은 같은 배너의 다른 뽑기 방식으로 보고 '<테마>'에 합친다(기본 테마가 있을 때만).
    # '_NN ren'(11연/22연 등)은 대상 유닛 구성이 달라서 합치지 않는다.
    raw = []
    for f in sorted(ART):
        m = re.match(r'gacha_(20\d{6})_(.+?)_top\.png$', f)
        if m and m.group(1) > TYPE4_END:
            raw.append((m.group(1), m.group(2), f))
    day_themes = collections.defaultdict(set)
    for d, t, _ in raw:
        day_themes[d].add(t)
    themes = collections.OrderedDict()
    for d, t, f in raw:
        base = re.sub(r'_(single|1500)$', '', t)
        if base != t and base in day_themes[d]:
            t = base
        themes.setdefault((d, t), []).append(f)
    for (d, theme), files in themes.items():
        # 정확한 테마 이름만 본다(예전 `_{theme} in x`는 xeno_exchange_crown이 crown02까지 잡았다). 합친 _single/_1500과 _last 판도 포함.
        sib_rx = re.compile(rf'gacha_{d}_{re.escape(theme)}(_single|_1500)?_top(_last)?\.png$')
        sib = sorted(x for x in jp_list_art[d] if sib_rx.match(x))
        cat.append({'gacha_id': None, 'source': 'jp_art', 'name_ja': theme, 'kind': 'step' if 'stepup' in theme.lower()
                    else ('free' if 'free' in theme.lower() else 'lapis'), 'date': d,
                    'rerun': bool(re.search(r'fukkoku|rerun', theme, re.I)), 'home_art': '', 'home_art_in_client': False,
                    'list_art': files[0], 'list_art_same_day': sib, 'ticket_group': None, 'effect_rows': False,
                    'featured_names': []})

    (OUT / 'catalog.json').write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- report ----
    by_src = collections.Counter(c['source'] for c in cat)
    by_kind = collections.Counter((c['source'], c['kind']) for c in cat)
    by_year = collections.Counter((c['date'][:4] or '????', c['source']) for c in cat)
    a = [c for c in cat if c['source'] == 'banner_mst']
    lines = ['# JP gacha catalogue (phase 1, read-only)', '',
             f'entries: {len(cat)}  ' + ', '.join(f'{k}={v}' for k, v in by_src.items()), '',
             '## by source/kind', *[f'- {s} / {k}: {n}' for (s, k), n in sorted(by_kind.items())], '',
             '## by year', *[f'- {y} {s}: {n}' for (y, s), n in sorted(by_year.items())], '',
             '## banner_mst entries (2017-03 .. 2022-03)',
             f'- with own ticket group: {sum(1 for c in a if c["ticket_group"])}',
             f'- with own effect rows: {sum(1 for c in a if c["effect_rows"])}',
             f'- home rotation art shipped in JP client: {sum(1 for c in a if c["home_art_in_client"])}',
             f'- JP gacha_* art on the same date: {sum(1 for c in a if c["list_art_same_day"])}',
             f'- featured unit name found in banner name: {sum(1 for c in a if c["featured_names"])}',
             f'- reruns (復刻): {sum(1 for c in a if c["rerun"])}', '',
             f'skipped type-4 targets (events/shops) by family: {dict(sorted(skipped.items()))}', '']
    (OUT / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()

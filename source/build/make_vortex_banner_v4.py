# -*- coding: utf-8 -*-
"""차원의 틈새 구역별 일판(JP) 배너 배정 v4.

입력
  build/out/vortex_season/jp_area_banner_map.json      (v3)
  build/out/vortex_season/altema/eventlist.tsv
  build/out/vortex_season/altema/eventlinks.tsv
  build/out/vortex_season/altema/quest_banners.tsv
  build/engine_overlay/jp_event_groups.json            (served/group)
  D:/Downloads/ffbejpdata/ffbejpdata/spdungeon1..9.cpk  (TOC만 읽음, 파일 추출 없음)

출력
  build/out/vortex_season/jp_area_banner_map.json      (v4로 덮어씀)
  build/out/vortex_season/banner_v4_sample.tsv
  build/out/vortex_season/banner_v4.md

영문판 데이터는 사용하지 않는다. 배너 후보는 일판 spdungeon CPK TOC에 있는 png만.
"""
import collections
import datetime
import json
import random
import re
import struct
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(r'C:/Users/USER/Documents/Projects/exvius-offline-ko')
VS = BASE / 'build/out/vortex_season'
ALT = VS / 'altema'
GROUPS = BASE / 'build/engine_overlay/jp_event_groups.json'
JP_CPK_DIR = Path(r'D:/Downloads/ffbejpdata/ffbejpdata')
OUT_MAP = VS / 'jp_area_banner_map.json'
OUT_SAMPLE = VS / 'banner_v4_sample.tsv'
OUT_DOC = VS / 'banner_v4.md'


# ---------------------------------------------------------------- CPK TOC
def _utf_table(data, offset):
    if data[offset:offset + 4] != b'@UTF':
        raise ValueError('Expected an unencrypted @UTF table')
    rows_at, strings_at, binary_at = struct.unpack_from('>III', data, offset + 8)
    columns, row_size, row_count = struct.unpack_from('>HHI', data, offset + 24)
    base = offset + 8

    def string(idx):
        start = base + strings_at + idx
        return data[start:data.index(0, start)].decode('utf-8')

    def value(kind, position):
        formats = {0: '>B', 1: '>b', 2: '>H', 3: '>h', 4: '>I',
                   5: '>i', 6: '>Q', 7: '>q', 8: '>f', 9: '>d'}
        if kind in formats:
            fmt = formats[kind]
            return struct.unpack_from(fmt, data, position)[0], struct.calcsize(fmt)
        if kind == 10:
            return string(struct.unpack_from('>I', data, position)[0]), 4
        if kind == 11:
            index, size = struct.unpack_from('>II', data, position)
            start = base + binary_at + index
            return data[start:start + size], 8
        raise ValueError('Unsupported UTF type: %s' % kind)

    schema = []
    position = offset + 32
    for _ in range(columns):
        flags, name = struct.unpack_from('>BI', data, position)
        position += 5
        storage, kind = flags & 0xf0, flags & 0x0f
        constant = 0
        if storage == 0x30:
            constant, size = value(kind, position)
            position += size
        elif storage not in (0x10, 0x50):
            raise ValueError('Unsupported UTF storage: %s' % storage)
        schema.append((string(name), storage, kind, constant))

    out = []
    for index in range(row_count):
        position = base + rows_at + index * row_size
        row = {}
        for name, storage, kind, constant in schema:
            if storage == 0x50:
                cell, size = value(kind, position)
                position += size
            else:
                cell = constant
            row[name] = cell
        out.append(row)
    return out


def _unmask(buf, off):
    size = struct.unpack_from('<Q', buf, off + 8)[0]
    if buf[off + 16:off + 20] == b'@UTF':
        return
    mask, mult = 0x655f, 0x4115
    for i in range(off + 16, off + 16 + size):
        buf[i] ^= mask & 0xff
        mask = (mask * mult) & 0xffff


def cpk_png_names():
    """spdungeon1..9.cpk TOC에서 png 이름+cpk만 뽑는다(추출 없음)."""
    names = []
    for n in range(1, 10):
        path = JP_CPK_DIR / f'spdungeon{n}.cpk'
        if not path.exists():
            continue
        data = bytearray(path.read_bytes())
        _unmask(data, 0)
        toc = _utf_table(data, 16)[0]['TocOffset']
        _unmask(data, toc)
        for row in _utf_table(data, toc + 16):
            fn = row.get('FileName', '')
            if fn.lower().endswith('.png'):
                names.append({'file': fn, 'cpk': path.name, 'size': row.get('ExtractSize')})
    # 중복 파일명은 CPK 순서상 첫 것을 대표로
    uniq, seen = [], set()
    for rec in names:
        if rec['file'] in seen:
            continue
        seen.add(rec['file'])
        uniq.append(rec)
    return uniq


# ---------------------------------------------------------------- 정규화
PAREN = re.compile(r'[（(【\[）)】\]]')
DROP = ('探索', '攻略', '高難易度', 'クエスト', 'イベント',
        '復刻', 'リバイバル', 'チャレンジ', 'キャンペーン', 'スペシャル')
PUNCT = re.compile(r'[\s\u3000!！?？,、。.:：;；\'"“”「」『』/／\\|｜\-ー~～＋+&＆*※]')


def norm(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFKC', s).lower()
    s = PAREN.sub('', s)
    s = s.replace('・', '')
    for t in DROP:
        s = s.replace(t, '')
    s = s.replace('ex', '')
    return PUNCT.sub('', s)


# ---------------------------------------------------------------- Altema
def parse_period(p):
    m = re.match(r'\s*(\d{4})/(\d{1,2})/(\d{1,2})', p or '')
    if not m:
        return None
    return '%04d%02d%02d' % (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def load_events():
    """eventlist.tsv 468행. 기간 칸의 줄바꿈(0탭 행)을 다음 레코드의 기간 앞에 붙인다."""
    raw = (ALT / 'eventlist.tsv').read_text(encoding='utf-8').split('\n')
    records, pending = [], ''
    for ln in raw:
        if not ln.strip():
            continue
        tabs = ln.count('\t')
        if tabs == 0:
            pending += ln + '\n'
            continue
        if tabs >= 2:
            records.append((pending, ln))
            pending = ''
    events = {}
    for i, (pre, ln) in enumerate(records, start=1):
        parts = ln.split('\t')
        period = parse_period(pre + parts[0])
        blob = parts[1] if len(parts) > 1 else ''
        img = parts[2] if len(parts) > 2 else ''
        f = blob.split('|')
        events[i] = {
            'row': i,
            'period_raw': (pre + parts[0]).strip(),
            'period': period,
            'cat': f[0].strip(),
            'name': f[1].strip() if len(f) > 1 else '',
            'sub': [x.lstrip('・').strip() for x in f[2:]
                    if x.strip() and not x.startswith('・')],
            'units': [x.lstrip('・').strip() for x in f[2:] if x.startswith('・')],
            'image': img.split('~')[0].strip(),
            'alt': img.split('~')[1].strip() if '~' in img else '',
        }
    # eventlinks 기간이 더 정확(468행 전부). 없으면 eventlist 기간 유지.
    for ln in (ALT / 'eventlinks.tsv').read_text(encoding='utf-8').split('\n'):
        p = ln.split('\t')
        if len(p) >= 2 and p[0].isdigit():
            d = parse_period(p[1])
            if d:
                events.setdefault(int(p[0]), {})
                if int(p[0]) in events:
                    events[int(p[0])]['period'] = d
    return events


def load_quests():
    quests = []
    for ln in (ALT / 'quest_banners.tsv').read_text(encoding='utf-8').split('\n'):
        p = ln.rstrip('\n').split('\t')
        if len(p) < 7 or p[0] == 'row':
            continue
        h1 = re.sub(r'^【[^】]*】', '', p[6])
        h1 = re.split(r'[|｜]', h1)[0].replace('の攻略', '').strip()
        quests.append({'row': int(p[0]), 'name': p[1].strip(), 'h1': h1,
                       'img': p[3].strip(), 'url': p[2].strip()})
    return quests


IMG_PREFIX = 'https://img.altema.jp/ffbe/uploads/'


def build_index(events, quests):
    idx = collections.defaultdict(list)          # norm -> [(row, kind, 원문)]
    for r, e in events.items():
        for nm, kind in ((e['name'], 'event'),):
            k = norm(nm)
            if k:
                idx[k].append((r, kind, nm))
        for s in e['sub']:
            k = norm(s)
            if k:
                idx[k].append((r, 'subquest', s))
    for q in quests:
        for nm, kind in ((q['name'], 'quest'), (q['h1'], 'h1')):
            k = norm(nm)
            if k:
                idx[k].append((q['row'], kind, nm))
    return idx


def match_area(name_jp, idx, events):
    """(tier, rows, note) 반환. tier: exact/contains/fuzzy/none"""
    n = norm(name_jp)
    if not n:
        return 'none', [], ''
    hits = idx.get(n, [])
    if hits:
        rows = sorted({h[0] for h in hits})
        kinds = sorted({h[1] for h in hits})
        return 'exact', rows, 'exact norm (%s)' % '+'.join(kinds)
    # containment: 긴 쪽/짧은 쪽, 길이 6 이상, 대표 키 1개만 인정
    best = None
    for k, v in idx.items():
        if len(k) < 6:
            continue
        if k in n or n in k:
            rows = sorted({h[0] for h in v})
            cand = (len(k), k, rows)
            if best is None or cand[0] > best[0]:
                best = cand
    if best and len(best[2]) == 1:
        return 'contains', best[2], 'contains key=%s' % best[1]
    # fuzzy
    import difflib
    scored = []
    for k, v in idx.items():
        if abs(len(k) - len(n)) > 6 or len(k) < 5:
            continue
        ratio = difflib.SequenceMatcher(None, n, k).ratio()
        if ratio >= 0.83:
            scored.append((ratio, k, sorted({h[0] for h in v})))
    scored.sort(key=lambda x: -x[0])
    if scored:
        top = scored[0]
        margin = top[0] - (scored[1][0] if len(scored) > 1 else 0)
        if len(top[2]) == 1 and margin >= 0.03:
            return 'fuzzy', top[2], 'fuzzy %.2f key=%s' % (top[0], top[1])
    if best:
        return 'contains_multi', best[2], 'contains key=%s multi' % best[1]
    return 'none', [], ''


# ---------------------------------------------------------------- 작품/분류 토큰
SERIES_JP = [
    ('ffbe', 'ffbe'), ('ff零式', 'ff0'), ('零式', 'ff0'), ('fft', 'fft'),
    ('幻影戦争', 'wotv'), ('wotv', 'wotv'),
    ('キングダムハーツ', 'kh'), ('kh', 'kh'),
    ('ロトの紋章', 'roto'), ('聖剣伝説lom', 'lom'), ('聖剣伝説3', 'seiken3'),
    ('聖剣伝説', 'seiken'),
    ('ゼノギアス', 'xeno'), ('クロノクロス', 'chronocross'),
    ('ロマンシングサガ', 'saga'), ('サガ', 'saga'),
    ('シノアリス', 'sinoalice'), ('ペルソナ', 'pe'),
    ('ダイの大冒険', 'dai'), ('ドラクエmsl', 'dqmsl'),
    ('ニーア', 'nier'), ('オクトパス', 'octopath'),
]
SUBTYPE_JP = [
    ('心技の試練', 'shingi'), ('真クラウン', 'crown'), ('ウェポン', 'weapon'),
    ('ビジョンズワールド', 'vision'), ('武具強化', 'bugu'),
    ('ダークビジョンズ', 'darkvisions'), ('ストーリーダイジェスト', 'digest'),
    ('ユニット紹介', 'chara'), ('十二武具', '12syuzoku'),
    ('強敵', 'kyukyoku'), ('ボスラッシュ', 'bossrush'),
]


ROMAN = [('xvi', 16), ('xv', 15), ('xiv', 14), ('xiii', 13), ('xii', 12),
         ('xi', 11), ('x', 10), ('ix', 9), ('viii', 8), ('vii', 7),
         ('vi', 6), ('v', 5), ('iv', 4), ('iii', 3), ('ii', 2), ('i', 1)]


def event_tokens(ev):
    text = (ev['cat'] + ' ' + ev['name']).lower()
    text = unicodedata.normalize('NFKC', text)
    toks = set()
    if 'ffviicc' in text:
        toks.add('ccff7r')
    for m in re.finditer(r'ffx?\s*(\d+)', text):
        toks.add('ff' + m.group(1))
    for m in re.finditer(r'ff(\d+(?:[,、]\d+)+)', text):
        for num in re.split(r'[,、]', m.group(1)):
            toks.add('ff' + num)
    for roman, num in ROMAN:
        if re.search(r'ff' + roman + r'(?![a-z0-9])', text):
            toks.add('ff%d' % num)
            break
    for jp, tok in SERIES_JP:
        if jp.lower() in text:
            toks.add(tok)
    for jp, tok in SUBTYPE_JP:
        if jp.lower() in text:
            toks.add(tok)
    return toks


def theme_tokens(theme):
    return {t for t in re.split(r'[_\-]', theme.lower()) if t}


SERIES_TOKENS = {'ffbe', 'wotv', 'kh', 'seiken', 'seiken3', 'lom', 'xeno',
                 'chronocross', 'saga', 'sinoalice', 'pe', 'dai', 'roto',
                 'nier', 'ccff7r', 'dqmsl', 'bf', 'fft'}
SUBTYPE_THEME = {'crown': 'crown', 'weapon': 'weapon', 'wp': 'weapon',
                 'vision': 'vision', 'vison': 'vision', 'vw': 'vision',
                 'shingi': 'shingi', 'shingi2': 'shingi', 'bugu': 'bugu',
                 'digest': 'digest', 'chara': 'chara',
                 'darkvisions': 'darkvisions', '12syuzoku': '12syuzoku',
                 'kyukyoku': 'kyukyoku'}


def theme_series(theme):
    """배너 파일명 테마에서 '작품' 토큰만 뽑는다. 없으면 빈 집합(범용 배너)."""
    theme = theme.lower()
    tt = theme_tokens(theme)
    out = {t for t in tt if t in SERIES_TOKENS}
    for t in tt:
        m = re.match(r'ff(\d+)', t)
        if m:
            out.add('ff' + m.group(1))
        if t.startswith('ffbe'):
            out.add('ffbe')
        if t.startswith('fft'):
            out.add('fft')
        if t.startswith('ccff7'):
            out.add('ccff7r')
        for roman, num in ROMAN:
            if t == 'ff' + roman:
                out.add('ff%d' % num)
    return out


def theme_subtypes(theme):
    tt = theme_tokens(theme.lower())
    return {SUBTYPE_THEME[t] for t in tt if t in SUBTYPE_THEME}


def theme_match(b, toks):
    theme = b['theme'].lower()
    tt = theme_tokens(theme)
    return any(tok in tt or theme.startswith(tok) for tok in toks)


def score_banner(b, toks, area_name, cat):
    theme = b['theme'].lower()
    tt = theme_tokens(theme)
    score = 0
    for tok in toks:
        if tok in tt or theme.startswith(tok):
            score += 5
    if toks & theme_subtypes(theme):
        score += 3
    if b['bn_list']:
        score += 1
    low = area_name + ' ' + cat
    if 'chara' in tt and not ('ユニット' in low or '紹介' in low):
        score -= 3
    if ('wp' in tt or 'weapon' in tt) and 'ウェポン' not in cat and '武具' not in cat:
        score -= 2
    if 'digest' in tt and 'ダイジェスト' not in cat:
        score -= 2
    if 'reprint' in tt and '復刻' not in area_name:
        score -= 1
    return score


def pick_banners(start, banners_by_date, ev, area_name, cat):
    """(delta, candidates, narrowed, note, deltas) 반환. candidates는 dict 목록."""
    if not start:
        return None, [], [], 'no event date', {}
    d0 = _d(start)
    pools = collections.defaultdict(list)
    deltas = {}
    for dd, lst in banners_by_date.items():
        delta = (_d(dd) - d0).days
        if abs(delta) <= 3:
            for b in lst:
                pools[abs(delta)].append(b)
                deltas[b['file']] = delta
    if not pools:
        return None, [], [], 'no JP CPK banner within +/-3d', {}
    absd = min(pools)
    pool = pools[absd]
    nlist = [b for b in pool if b['bn_list']]
    if nlist:
        pool = nlist
    note = 'date %s (window %dd)' % (start, absd)
    if absd == 0:
        note = 'date %s' % start
    toks = event_tokens(ev) if ev else set()
    if len(pool) == 1:
        signed = deltas[pool[0]['file']]
        btoks = theme_series(pool[0]['theme']) | theme_subtypes(pool[0]['theme'])
        if signed != 0 and toks and btoks and not (btoks & toks):
            note += '; single near-date banner, no theme match (date only)'
        elif signed != 0:
            note += '; single near-date banner'
        return signed, pool, pool, note, deltas
    scored = [(score_banner(b, toks, area_name, cat), b) for b in pool]
    top = max(s for s, _ in scored)
    best = [b for s, b in scored if s == top]
    second = max([s for s, _ in scored if s != top], default=None)
    if top > 0 and second is not None and top - second >= 3 and len(best) < len(pool):
        note += '; theme/category narrow %d->%d' % (len(pool), len(best))
        return deltas[best[0]['file']], pool, best, note, deltas
    if top > 0 and second is None:
        note += '; theme/category all-match %d' % len(best)
        return deltas[best[0]['file']], pool, best, note, deltas
    note += '; %d candidates' % len(pool)
    return deltas[pool[0]['file']], pool, pool, note, deltas


def _d(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


# ---------------------------------------------------------------- main
def main():
    map_v3 = json.loads(OUT_MAP.read_text(encoding='utf-8'))
    areas = map_v3['areas']
    groups = json.loads(GROUPS.read_text(encoding='utf-8'))['areas']
    events = load_events()
    quests = load_quests()
    idx = build_index(events, quests)

    # 배너 인덱스 (TOC + unmatched theme/date 보강)
    unmatched = {b['file']: b for b in map_v3.get('unmatched_jp_banners', [])}
    date_re = re.compile(r'(\d{8})')
    banners = []
    for rec in cpk_png_names():
        fn = rec['file']
        m = date_re.search(fn)
        meta = unmatched.get(fn, {})
        theme = meta.get('theme', '')
        if not theme:
            mm = re.search(r'_bn_list_(.+?)(?:_\d+)?\.png$', fn)
            if mm:
                theme = mm.group(1)
            else:
                mm = re.search(r'_bn_top_(.+?)(?:_\d+)?\.png$', fn)
                theme = mm.group(1) if mm else ''
        banners.append({'file': fn, 'cpk': rec['cpk'], 'date': m.group(1) if m else '',
                        'theme': theme, 'bn_list': '_bn_list' in fn,
                        'bn_top': '_bn_top' in fn})
    banners_by_date = collections.defaultdict(list)
    for b in banners:
        if b['date']:
            banners_by_date[b['date']].append(b)
    toc_names = {b['file'] for b in banners}

    # 퀘스트 이미지 보조 인덱스 (row -> img)
    quest_img = collections.defaultdict(list)
    for q in quests:
        quest_img[q['row']].append(q['img'])

    new_areas = {}
    stats = collections.Counter()
    detail = []

    for aid, a in areas.items():
        rec = dict(a)
        rec.pop('v4', None)
        v4 = {'version': 4}
        if aid not in groups:
            v4.update(status='not_served', bucket_v4='not_served')
            rec['v4'] = v4
            new_areas[aid] = rec
            stats['not_served'] += 1
            continue

        g = groups[aid]
        group = g.get('group', '')
        name = a.get('name_jp', '')
        if a.get('bucket') == 'system_no_banner' or group == 'permanent' and a.get('bucket') == 'system_no_banner':
            v4.update(status='system_no_banner', bucket_v4='system_no_banner',
                      group=group)
            rec['v4'] = v4
            new_areas[aid] = rec
            stats['system_no_banner'] += 1
            continue

        tier, rows, mnote = match_area(name, idx, events)
        rows = [r for r in rows if r in events]
        date_rows = sorted({r: events[r]['period'] for r in rows if events[r]['period']}.items(),
                           key=lambda kv: kv[1])
        start = date_rows[0][1] if date_rows else None
        ev = events[rows[0]] if rows else None
        cat = ev['cat'] if ev else ''
        toks = event_tokens(ev) if ev else set()
        reason = mnote
        if len(rows) > 1 and len(date_rows) > 1:
            reason += '; %d matched rows, earliest used' % len(rows)
            v4['matched_rows'] = [{'row': r, 'period': events[r]['period'],
                                   'name': events[r]['name'], 'cat': events[r]['cat']}
                                  for r in rows]
        v4['match_tier'] = tier
        v4['altema_row'] = rows[0] if rows else None
        v4['altema_name'] = ev['name'] if ev else None
        v4['altema_category'] = cat or None
        v4['altema_start'] = start
        v4['altema_period_raw'] = ev['period_raw'] if ev else None
        v4['altema_tokens'] = sorted(toks)

        wiki_img = None
        if ev:
            imgs = quest_img.get(ev['row']) or ([ev['image']] if ev['image'] else [])
            if imgs and imgs[0]:
                wiki_img = IMG_PREFIX + imgs[0]
        v4['wiki_image'] = wiki_img

        delta, cand_all, narrowed, bnote, _deltas = pick_banners(
            start, banners_by_date, ev, name, cat)
        if tier == 'none':
            reason = 'no Altema name match (v3 candidate carried as legacy only)'
        else:
            reason = (reason + '; ' + bnote).strip('; ')

        chosen = None
        confidence = None
        bucket = None
        theme_mismatch = False
        mismatch_note = ''
        if narrowed:
            chosen = narrowed[0]['file']
            adelta = abs(delta or 0)
            # 작품/분류 토큰이 서로 어긋날 때만(배너가 범용이면 판단 보류) 신뢰도를 낮춘다
            ev_series = {t for t in toks
                         if t in SERIES_TOKENS or re.match(r'ff\d+$', t)}
            cand_series = theme_series(narrowed[0]['theme'])
            cand_sub = theme_subtypes(narrowed[0]['theme'])
            series_bad = bool(ev_series) and bool(cand_series) and not (
                ev_series & cand_series)
            sub_bad = bool(cand_sub) and not (cand_sub & toks)
            theme_mismatch = series_bad or sub_bad
            if theme_mismatch:
                parts = []
                if series_bad:
                    parts.append('event %s vs banner %s' % (
                        sorted(ev_series), sorted(cand_series)))
                if sub_bad:
                    parts.append('banner type %s not in event' % sorted(cand_sub))
                mismatch_note = '; theme mismatch: ' + '; '.join(parts)
            if tier == 'exact' and adelta == 0 and len(narrowed) == 1 and not theme_mismatch:
                confidence = 'high'
            elif 'no theme match' in bnote or theme_mismatch:
                confidence = 'low'
            elif tier in ('exact', 'contains') and adelta <= 1 and len(narrowed) <= 3:
                confidence = 'medium'
            elif tier == 'exact' and adelta <= 3 and len(narrowed) <= 2:
                confidence = 'medium'
            else:
                confidence = 'low'
            bucket = 'jp_cpk'
        elif tier != 'none':
            bucket = 'wiki_image_only' if v4['wiki_image'] else 'needs_generation'
            confidence = 'low' if wiki_img else None
        else:
            # 이름 매칭 실패: v3의 알테마 이미지가 있으면 위키 이미지만
            legacy_wiki = a.get('candidate_image_url')
            if legacy_wiki:
                v4['wiki_image'] = legacy_wiki
                v4['wiki_image_source'] = 'v3 altema candidate'
                bucket = 'wiki_image_only'
                confidence = 'low'
            else:
                bucket = 'needs_generation'

        v4['date_delta'] = delta
        v4['candidate_banners'] = [b['file'] for b in cand_all]
        v4['narrowed_banners'] = [b['file'] for b in narrowed]
        v4['chosen_banner_v4'] = chosen
        v4['confidence_v4'] = confidence
        v4['bucket_v4'] = bucket
        v4['evidence_v4'] = reason + mismatch_note
        v4['group'] = group

        # --- 기존 jp_verified 유지 ---
        if a.get('bucket') == 'jp_verified':
            v4['chosen_banner_v4'] = a.get('chosen_banner')
            v4['bucket_v4'] = 'jp_cpk'
            v4['confidence_v4'] = 'high'
            v4['evidence_v4'] = 'kept jp_verified (JP master icon + CPK); ' + reason
            if chosen and chosen != a.get('chosen_banner'):
                v4['conflict'] = {'v3': a.get('chosen_banner'), 'v4_altema': chosen,
                                  'v4_evidence': reason + mismatch_note}
            stats['jp_verified_kept'] += 1
        elif chosen and a.get('source') == 'jp-master' and a.get('chosen_banner') in toc_names:
            # v3가 마스터 아이콘으로 잡은 배너도 TOC에 실재하면 후보로 남긴다
            v4['v3_master_banner_in_pack'] = a.get('chosen_banner')

        stats[v4['bucket_v4']] += 1
        stats['%s/%s' % (v4['bucket_v4'], v4['confidence_v4'])] += 1
        rec['v4'] = v4
        new_areas[aid] = rec
        detail.append((aid, name, v4))

    # ------------------------------------------------------------ 집계
    served = [r for r in new_areas.values() if r.get('v4', {}).get('status') != 'not_served']
    agg = collections.Counter()
    for r in served:
        v = r['v4']
        if v.get('status') == 'system_no_banner':
            agg['system_no_banner'] += 1
        else:
            agg[v.get('bucket_v4', '?')] += 1
            if v.get('bucket_v4') == 'jp_cpk':
                agg['jp_cpk/' + str(v.get('confidence_v4'))] += 1
    out = dict(map_v3)
    out['version'] = 4
    tier_counts = collections.Counter(r['v4'].get('match_tier') for r in served
                                      if r['v4'].get('status') != 'system_no_banner')
    delta_counts = collections.Counter(r['v4'].get('date_delta') for r in served
                                       if r['v4'].get('bucket_v4') == 'jp_cpk'
                                       and not str(r['v4'].get('evidence_v4', '')).startswith('kept'))
    conflicts = sum(1 for r in served if r['v4'].get('conflict'))
    out['v4_match_tiers'] = dict(tier_counts)
    out['policy'] = dict(map_v3.get('policy', {}))
    out['policy']['banner_source'] = ('JP only. English/Global release art is NOT used. '
                                      'v4 banners come from JP spdungeon1..9.cpk TOC only.')
    out['v4_method'] = {
        'altema_match': 'name_jp normalized (NFKC, spaces/punct, 探索/攻略/高難易度/EX/復刻 removed) '
                        'against Altema quest name / h1 / event name / subquests',
        'start_date': 'earliest event start among matched rows (original run, not reprint)',
        'banner_rule': 'filename date spd_YYYYMMDD within +/-3d, bn_list preferred, '
                       'then FF/collab series token + category token narrowing',
        'confidence': {'high': 'name exact + date exact + 1 candidate',
                       'medium': 'exact/contains + date <=1d + <=3 cands, or exact + <=3d + <=2 cands',
                       'low': 'fuzzy/contains, wide window, or many candidates'},
        'kept': 'existing jp_verified kept; conflicts recorded in v4.conflict',
        'sample': 'banner_v4_sample.tsv (20 high + 20 medium, random seed 20261112)',
    }
    out['v4_stats'] = dict(agg)
    out['v4_stats']['served'] = len(served)
    import datetime as _dt
    mt = _dt.datetime.fromtimestamp(GROUPS.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
    out['v4_served_basis'] = ('jp_event_groups.json (%s) -> %d areas; '
                              'the task brief said 1101, the file was regenerated '
                              'by another process during this task' % (mt, len(served)))
    out['areas'] = new_areas
    OUT_MAP.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')

    # ------------------------------------------------------------ 샘플
    rng = random.Random(20261112)
    def sample(conf, n):
        pool = [d for d in detail if d[2].get('bucket_v4') == 'jp_cpk'
                and d[2].get('confidence_v4') == conf]
        pool.sort(key=lambda x: x[0])
        # 같은 배너/같은 알테마 항목이 반복되면 검증에 도움이 안 되므로 먼저 중복 제거
        seen, uniq = set(), []
        shuffled = pool[:]
        rng.shuffle(shuffled)
        for d in shuffled:
            key = (d[2].get('chosen_banner_v4'), d[2].get('altema_name'))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(d)
        return uniq[:n]
    rows_out = []
    for conf in ('high', 'medium'):
        for aid, name, v in sample(conf, 20):
            rows_out.append([aid, name, v.get('altema_name') or '', v.get('altema_start') or '',
                             v.get('chosen_banner_v4') or '', conf,
                             v.get('evidence_v4', '')])
    OUT_SAMPLE.write_text(
        'area_id\tname_jp\taltema_quest\tstart_date\tbanner\tconfidence\tevidence\n' +
        '\n'.join('\t'.join(r) for r in rows_out) + '\n', encoding='utf-8')

    # ------------------------------------------------------------ 문서
    def cnt(k):
        return agg.get(k, 0)
    delta_str = ', '.join('%+d=%d' % (k, v) for k, v in sorted(
        (kv for kv in delta_counts.items() if kv[0] is not None))) or '없음'
    lines = [
        '# 차원의 틈새 구역별 일판 배너 배정 v4',
        '',
        '영문판 데이터는 사용하지 않았다. 배너 후보는 일판 `spdungeon1..9.cpk` TOC의 png만이다.',
        '',
        '## 방법',
        '1. 구역 `name_jp`를 정규화(NFKC, 공백/기호 제거, 探索·攻略·高難易度·EX·復刻 제거)해',
        '   알테마 퀘스트명(`quest_banners.tsv` name/h1), 이벤트명, 하위 퀘스트와 대조했다.',
        '2. 매칭된 이벤트의 개최 시작일(여럿이면 가장 이른 원래 개최)을 기준으로',
        '   파일명 날짜가 ±3일 이내인 일판 CPK 배너를 찾고 `bn_list` 계열을 우선했다.',
        '3. 작품 토큰(FF7/FF10/FFBE/幻影戦争 등)과 분류(クラウン/ウェポン/心技 등)로 후보를 좁혔다.',
        '4. 기존 `jp_verified`는 그대로 유지하고, 새 결과와 다르면 `v4.conflict`에 둘 다 기록했다.',
        '',
        '## 집계 (서빙 %d구역)' % len(served),
        '',
        '기준: `build/engine_overlay/jp_event_groups.json` (%s, %d구역). '
        '작업 중 이 파일이 외부에서 재생성되어(지시서의 1101 → %d) 최신 판으로 집계했다.'
        % (mt, len(served), len(served)),
        '',
        '| 구분 | 구역 수 |',
        '|---|---:|',
        '| 일판 CPK 배너 high | %d |' % cnt('jp_cpk/high'),
        '| 일판 CPK 배너 medium | %d |' % cnt('jp_cpk/medium'),
        '| 일판 CPK 배너 low | %d |' % cnt('jp_cpk/low'),
        '| **일판 CPK 합계** | **%d** |' % cnt('jp_cpk'),
        '| 위키(알테마) 이미지만 | %d |' % cnt('wiki_image_only'),
        '| 생성 필요 | %d |' % cnt('needs_generation'),
        '| 시스템/상시(배너 없음) | %d |' % cnt('system_no_banner'),
        '| 합계 | %d |' % (cnt('jp_cpk') + cnt('wiki_image_only') +
                            cnt('needs_generation') + cnt('system_no_banner')),
        '',
        '## 매칭·날짜 통계',
        '',
        '| 이름 매칭 tier | 구역 수 |',
        '|---|---:|',
        '| exact (정규화 완전 일치) | %d |' % tier_counts.get('exact', 0),
        '| contains (포함 관계) | %d |' % tier_counts.get('contains', 0),
        '| contains_multi (포함, 다중) | %d |' % tier_counts.get('contains_multi', 0),
        '| fuzzy (유사도 >=0.83) | %d |' % tier_counts.get('fuzzy', 0),
        '| none (알테마에 없음) | %d |' % tier_counts.get('none', 0),
        '',
        '날짜 오프셋(일): ' + delta_str,
        '',
        '기존 jp_verified 유지 중 새 결과와 다른 구역: %d (v4.conflict)' % conflicts,
        '',
        '## 한계',
        '- 일판 spdungeon CPK의 날짜 배너는 2016-10-21 이후만 있다. 그 이전 이벤트는 배너가 없다.',
        '- 알테마 eventlist(468건)에 없는 이벤트는 이름 매칭이 불가능해 위키 이미지/생성 필요로 남는다.',
        '- 같은 날짜에 배너가 여럿이면 후보를 모두 `candidate_banners`에 남겼다.',
        '- 검증 샘플: `banner_v4_sample.tsv` (high 20 + medium 20, seed 20261112). 같은 배너/같은 알테마 항목의 중복은 샘플에서 먼저 제거했다.',
        '- 기존 jp_verified는 JP 마스터 아이콘 기준이라 같은 배너를 여러 구역이 공유하는 경우가 있다(예: 다크비전즈 계열). 유지 규칙에 따른 결과다.',
    ]
    OUT_DOC.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print('served', len(served))
    print('agg', dict(agg))
    print('wrote', OUT_MAP, OUT_SAMPLE, OUT_DOC)


if __name__ == '__main__':
    main()

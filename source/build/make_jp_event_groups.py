"""Build build/engine_overlay/jp_event_groups.json: the JP 次元の狭間 (Vortex) season and tab map.

JP-only evidence. The Global (English) event_archive.json is NOT read: the English Offline build is a
different game with a different release calendar, so its `group`/`kind`/`release` cannot classify JP content.

Where the dates come from (no JP master carries an event period: F_AREA_MST has no date column and the tile
period is server-side in SpDungeonCondMst, which the offline client does not ship):

  1. `banner` - the area's own icon row (F_AREA_MST.0HUPxDf1 -> F_ICON_MST.qtkvrS60) names a banner file
     such as `spd_20161121_bn_list_FFBE.png`. JP banner files carry the event's date in the name. Only a
     banner that exactly one served area uses is treated as that area's date (shared banners such as
     `spd_20190729_bn_list_FF10.png` are fallbacks for 176 areas and are ignored).
     `banner-link` - F_BANNER_MST rows whose link column is `2,21,<area>,<dungeon>,<mission>` advertise a
     specific JP gate area; their banner filename date is the JP event date (earliest row = original run).
     That covers 287 served areas and never disagrees with the icon banner at month level.
  2. `altema` - the Japanese wiki event list (build/out/vortex_season/altema/eventlist.tsv, source
     https://altema.jp/ffbe/eventlist-48657) matches the area's JP name against an event name or one of its
     sub-quest names (2015-12..2025-05). The earliest occurrence is used (a name that only appears as a
     reprint keeps the reprint date; when a banner exists too both are recorded).
  3. `id-neighbor` - areas with neither: the median date of the three nearest dated areas sharing the same
     F_MISSION_MST id prefix (mission ids are issued in chronological blocks; prefix 72 = 2016-08..10,
     80 = 2018-01..02, 88 = 2019-03..05, ...). Median error against the dated areas is about 3.6 months.

Season boundaries are the JP main-story part start dates (this is the JP calendar, not the Global one):
  season1 2015-10-22 第1部 ラピス編 (JP service start)
  season2 2017-02-01 第2部 パラデイア編 (Ver.2.6.0, gameranbu.jp; day not published - month only)
  season3 2019-05-30 3rdシーズン (F_BANNER_MST bnr_20190530_3rdset_gacha_rotation.png
                     「3rdシーズン開始記念」; bnr_20190823_story_rotation.png is already 3rd 2章後編)
  season4 2021-05-10 4thシーズン開幕 (F_BANNER_MST bnr_20210510_rotation_4th_season.png
                     「4thシーズン開幕！（新ストーリー追加）」, F_WORLD_MST world 5 start 2021-05-10)
  season5 2024-12-27 第5部/5thシーズン カオス編 (altema; otakuhatanosii.com/ffbe-175 confirms 2024/12/27)
JP therefore has FIVE story seasons, not the Global archive's four; GROUP_ORDER in jp_event_archive.py was
extended to season5 (the Frida menu labels are served from this JSON, so no JS change is needed).

Group rules (first match wins, recorded in `rule`/`season_rule`):
  1. collaboration: the altema category contains コラボ, or the JP name carries an external-IP token.
  2. permanent: the always-open JP halls (経験の間/富豪の間/…, 十二武具の間/降臨の間/挑戦の間, 欠片の試練).
  3. other: recurring system content (Dark Visions, Chronicle/Caravan, towers, transitions, banner
     placeholders, シリーズボスバトル, ...) - not a story season.
  4. otherwise the area's date picks season1..5.
  5. no date at all -> other (`no-date`).

Tab rules (GateScene main tab id; the ids are NOT display order - see the client's GATE_TAB_INFO):
  1. 734 -> 1 (pinned: the one-year anniversary raid must keep working).
  2. JP name token / altema category -> special (4), strong (3), training (5).
  3. otherwise the newest JP season (season5) -> 최신 (1), anything older -> 복각 (2).

Universe = every area the JP gate can serve (world 2 / subtype 21, with a dungeon that has a mission), the
same test jp_compat._jp_open_event_areas uses, minus jp_seal_room.SEAL_AREAS (the 182 JP 封印の間 areas: an
area must appear in exactly one of the two menus, and the seal room owns its areas' rows).

Usage: python -I -X utf8 build/make_jp_event_groups.py [--out build/engine_overlay/jp_event_groups.json]
"""
import argparse
import collections
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTERS = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
DEFAULT_ALTEMA = ROOT / 'build/out/vortex_season/altema/eventlist.tsv'
DEFAULT_OUT = ROOT / 'build/engine_overlay/jp_event_groups.json'
# 복각 sub tab per area (6..10 = イベント/獲得/覚醒/武器/強化, text_ja_1100.csv GATE_TAB_NAME_2_SUB_TAB_1..5).
# JP masters carry no such field (it lived only in the server's SpDungeonCondMst.qnUhs32P); the split is the
# Altema quest-type title of each area (ビジョン解放/蒼き覚醒/ウェポン/クラウン), see reprint_subtab_proposal.md.
DEFAULT_REPRINT_SUB = ROOT / 'build/out/vortex_season/reprint_subtab_proposal.tsv'
REPRINT_SUB_NAMES = ('イベント', '獲得', '覚醒', '武器', '強化')

# JP main-story part starts (see the docstring for the evidence of each date).
SEASON_BOUNDARIES = (
    ('2015-10-22', 'season1'),
    ('2017-02-01', 'season2'),
    ('2019-05-30', 'season3'),
    ('2021-05-10', 'season4'),
    ('2024-12-27', 'season5'),
)
LATEST_SEASON = SEASON_BOUNDARIES[-1][1]
GROUP_KEYS = ('permanent',) + tuple(key for _date, key in SEASON_BOUNDARIES) + ('collaborations', 'other')
GROUP_LABELS = {'permanent': '상시', 'collaborations': '콜라보', 'other': '기타'}
for _i, (_date, _key) in enumerate(SEASON_BOUNDARIES, 1):
    GROUP_LABELS[_key] = '시즌 %d' % _i
GROUPS = tuple((key, GROUP_LABELS[key]) for key in GROUP_KEYS)
DEFAULT_GROUP = 'season1'
AREA_FILTER = {'9Pb24aSy': '2', 'Esxe71j3': '21'}   # F_AREA_MST world 2 / sp-dungeon subtype 21

# GateScene main tabs, keyed by the value the server puts in the gate row's `qnUhs32P` (see the docstring).
TABS = {'1': '최신', '2': '복각', '3': '강적', '4': '스페셜', '5': '육성'}
TAB_LATEST, TAB_REPRINT, TAB_STRONG, TAB_SPECIAL, TAB_TRAIN = '1', '2', '3', '4', '5'
TAB_PINNED = {'734': TAB_LATEST}

# Identical clone/reprint areas (verified identical mission names, stages, and enemy waves against their primary area):
# keep one canonical representative area per identical set and omit the redundant duplicates.
DUPLICATE_CLONE_AREAS = frozenset({
    # 晶石の洞窟 (permanent training, keep 3047)
    '3066', '3073', '3089', '3101', '3115', '3138', '3157', '3166', '3185', '3214',
    # モーグリ王の秘密特訓 (keep 305)
    '307',
    # 非情は七色 (keep 796)
    '866',
    # 全ての始まりにして終わりなる者 (keep 824)
    '874',
    # 真紅のゼノギアス (keep 825)
    '875',
    # ダークビジョンズ identical clones (keep 920)
    '922', '924',
    # ドラゴンクエスト ダイの大冒険 (keep 957)
    '975',
    # 英雄の塔NORMAL 1~4層+天頂 identical clone (keep 1000)
    '1002',
    # season4/5 identical reprints (keep original 4270, 4460, 4510, 4530, 4600, 4670, 4690, 6280, 6420, 6520)
    '4790', '4791', '4800', '4801', '4810', '4811', '4820', '4821', '6600', '6610',
    # system / world-map transition / playback dummy areas (not real events)
    '211', '600', '700', '1391', '1397', '1398', '1399', '1400',
})

# Always-open JP halls (常設). These are not tied to a story season and ride along in every season list.
PERMANENT_TOKENS = (
    '経験の間', '富豪の間', '魔石の間', '創造の間', '覚醒の間', '晶石の間', '輝石の間', '青魔法の間',
    'ボーナスの間', '強き心の修練', 'メタルの間', 'メタルダンジョン', '晶石の洞窟',
    '十二武具の間', '裏十二武具', '降臨の間', '挑戦の間', '欠片の試練', '継承の旅路',
)
# Recurring, non-season system content. Matched against the JP area title. Tokens stay narrow so ordinary
# event titles (e.g. 「破滅をもたらす機神 爆降臨」) are not swallowed.
SYSTEM_TOKENS = (
    'ダークビジョンズ', 'クロニクルバトル', 'キャラバトル', 'ROAD TO GLORY',
    '英雄の塔', '門松の塔', '次元の狭間', '欲望の狭間', '宝物庫', 'モーグリ王', 'お試しバトル',
    '叡智の殿堂', 'クラフト素材エクストラバトル', 'ストーリーダイジェスト', 'playback',
    'イベント予告', 'に遷移', 'に移動', '4thワールド', '5thシーズン', 'みんなdeチョイス',
    '十二種族討伐戦', 'シリーズボスバトル', 'エクストラルールバトル', 'モンスターカーニバル',
    '（バナー）', '復刻ストイベ',
)
# External IPs. `FFBE` is deliberately absent (it is this game, not a collaboration).
COLLAB_TOKENS = (
    'コラボ', 'SINoALICE', 'シノアリス', 'ファミリーマート', 'ファミマ', 'ドラゴンクエスト', 'DQMSL', 'ロトの紋章',
    'FFVII', 'FFVIII', 'FFIX', 'FFX', 'FFXI', 'FFXII', 'FFXIII', 'FFXIV', 'FFXV', 'FFT', 'FF零式', 'FF16',
    'LoM', '聖剣', 'ゼノギアス', 'クロノ', 'サガ', 'マナ', 'NieR', 'ニーア', 'ペルソナ', 'バイオハザード',
    'トゥームレイダー', 'ララクロフト', 'KINGDOM HEARTS', 'キングダムハーツ', 'スターオーシャン', 'SOA',
    'ダイの大冒険', 'ハガレン', '鋼の錬金術師', 'テラバトル', 'ブレイブフロンティア', 'アリアナ',
    'ケイティ・ペリー', 'オクトパストラベル', 'パプワ', 'グルグル', 'アクトレイザー', 'パラサイト・イヴ',
    'ヴァルキリープロファイル', 'VP', '幻影戦争', 'FFRK', 'キングスグレイブ', 'モンハン', 'BD',
)

TAB_SPECIAL_TOKENS = (
    'ダークビジョンズ', 'クロニクルバトル', 'キャラバトル', 'ROAD TO GLORY', '英雄の塔', '門松の塔',
    'みんなdeチョイス', 'お試しバトル', 'ストーリーダイジェスト', 'playback', 'イベント予告',
    '次元の狭間', '欲望の狭間', '4thワールド', '5thシーズン', '継承の旅路', 'に遷移', 'に移動',
    'モンスターカーニバル', '（バナー）', 'シリーズボスバトル', 'エクストラルールバトル',
)
TAB_STRONG_TOKENS = (
    '降臨', '討滅戦', '討伐戦', '煉獄', '蛮神', '心技の試練', '欠片の試練', '挑戦の間', '強敵',
    '修羅', '幻影討伐', 'ボスバトル', '十二武具', '連戦', '神獣戦', 'シリーズボスバトル', '死闘',
    'ボスラッシュ', '高難易度', '高難度', 'チャレンジ',
)
TAB_TRAIN_TOKENS = (
    '経験の間', '富豪の間', '魔石の間', '創造の間', '覚醒の間', '晶石の間', '輝石の間', '青魔法の間',
    'ボーナスの間', '強き心の修練', '強化素材', 'クラフト素材', '叡智の殿堂', '宝物庫', '武具強化',
    '輝源獲得', 'ドリームチャンス', '晶石の洞窟', 'メタルダンジョン', 'メタルの間', '特訓',
)
# altema category -> GateScene tab (only the categorical ones; a plain レイド event is an ordinary new/reprint
# event, so it falls through to the season rule instead of being forced onto 강적).
ALTEMA_TAB = (
    ('心技の試練', TAB_STRONG), ('真クラウンクエスト', TAB_STRONG), ('武具強化', TAB_TRAIN),
    ('ダークビジョンズ', TAB_SPECIAL), ('英雄の塔', TAB_SPECIAL), ('門松の塔', TAB_SPECIAL),
    ('ビジョンズワールド', TAB_SPECIAL),
)


def load_ndjson(path, key):
    rows = {}
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[str(row.get(key, ''))] = row
    return rows


def servable_areas(masters):
    """The gate's universe: world-2 subtype-21 areas with a dungeon that holds a mission."""
    areas = load_ndjson(masters / 'F_AREA_MST.ndjson', 'uv60hgDW')
    dungeons = load_ndjson(masters / 'F_DUNGEON_MST.ndjson', 'U9iHsau3')
    missions = load_ndjson(masters / 'F_MISSION_MST.ndjson', 'qo3PECw6')
    with_mission = {str(row.get('U9iHsau3') or '') for mid, row in missions.items()
                    if mid and str(row.get('U9iHsau3') or '')}
    servable = {str(row.get('uv60hgDW') or '') for did, row in dungeons.items()
                if str(did) in with_mission and str(row.get('uv60hgDW') or '')}
    out = {}
    for area_id, row in areas.items():
        area_id = str(area_id)
        if any(str(row.get(key)) != value for key, value in AREA_FILTER.items()):
            continue
        if area_id in servable:
            out[area_id] = row
    return out


def seal_area_ids():
    import sys
    sys.path.insert(0, str(ROOT / 'build/engine_overlay'))
    import jp_seal_room
    return {str(area) for area in jp_seal_room.SEAL_AREAS}


def mission_prefixes(masters):
    """{area: (first mission id as str)}; mission ids are issued in chronological blocks."""
    out = collections.defaultdict(list)
    with (masters / 'F_MISSION_MST.ndjson').open(encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            area = str(row.get('uv60hgDW') or '')
            mission = str(row.get('qo3PECw6') or '')
            if area and mission.isdigit():
                out[area].append(int(mission))
    return {area: str(sorted(ids)[0]) for area, ids in out.items() if ids}


def banner_names(masters):
    """{area: JP banner file} from F_AREA_MST icon -> F_ICON_MST, falling back to the dungeon icon."""
    icons = load_ndjson(masters / 'F_ICON_MST.ndjson', '0HUPxDf1')
    areas = load_ndjson(masters / 'F_AREA_MST.ndjson', 'uv60hgDW')
    dungeons = load_ndjson(masters / 'F_DUNGEON_MST.ndjson', 'U9iHsau3')
    by_area = collections.defaultdict(list)
    for _did, row in dungeons.items():
        area = str(row.get('uv60hgDW') or '')
        icon = str(row.get('0HUPxDf1') or '')
        if area and icon:
            by_area[area].append(icon)
    out = {}
    for area, row in areas.items():
        names = []
        icon = str(row.get('0HUPxDf1') or '')
        if icon and (icons.get(icon) or {}).get('qtkvrS60'):
            names.append(str(icons[icon]['qtkvrS60']))
        for dungeon_icon in by_area.get(str(area), []):
            name = (icons.get(dungeon_icon) or {}).get('qtkvrS60')
            if name:
                names.append(str(name))
        if names:
            out[str(area)] = names[0]
    return out


def norm(text):
    text = unicodedata.normalize('NFKC', text or '')
    return re.sub(r'[\s　・:：\-—―~〜!！?？「」『』（）()\[\]【】,，.。]', '', text)


def parse_altema(path):
    """Parse the altema event list (tab separated: period, 【cat】|name|sub-quests|・units, banner~alt).

    A few rows have the period and a ※ note split across two lines; those are joined here. Returns
    [(start 'YYYY-MM-DD', category, event name)] ordered by start.
    """
    if not path.is_file():
        return []
    lines = path.read_text(encoding='utf-8').split('\n')
    rows = []
    buffered = None
    for line in lines:
        if not line.strip():
            continue
        tabs = line.count('\t')
        if tabs == 0:
            buffered = line
            continue
        if tabs != 2:
            continue
        if buffered:
            line = buffered + '\n' + line
            buffered = None
        period, middle, _banner = line.split('\t')
        match = re.match(r'(\d{4})/+(\d{1,2})/+(\d{1,2})', period)
        if not match:
            continue
        start = '%04d-%02d-%02d' % (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        parts = [part.strip() for part in middle.split('|')]
        category = parts[0]
        names = [parts[1]] if len(parts) > 1 else []
        names += [part for part in parts[2:] if not part.startswith('・')]
        rows.append((start, category, names))
    rows.sort(key=lambda row: row[0])
    return rows


class Altema(object):
    """JP name -> (start, category, event name); earliest occurrence wins."""

    def __init__(self, rows):
        self.by_name = collections.defaultdict(list)
        self.keys = []
        for start, category, names in rows:
            for name in names:
                key = norm(name)
                if len(key) < 3:
                    continue
                self.by_name[key].append((start, category))
                self.keys.append((key, start, category))

    def match(self, name):
        key = norm(name)
        if key in self.by_name:
            start, category = sorted(self.by_name[key])[0]
            return {'date': start, 'cat': category, 'how': 'exact'}
        if len(key) >= 5:
            hits = [(start, category) for other, start, category in self.keys
                    if len(other) >= 5 and key in other]
            if hits:
                start, category = sorted(hits)[0]
                return {'date': start, 'cat': category, 'how': 'sub'}
        return None


DATE_RE = re.compile(r'spd_(\d{8})')
DATE8_RE = re.compile(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])')


def banner_dates(names, served):
    """{area: 'YYYY-MM-DD'} for banner files that exactly one served area uses."""
    counts = collections.Counter(names.get(area) for area in served)
    out = {}
    for area in served:
        match = DATE_RE.search(names.get(area) or '')
        if match and counts[names[area]] == 1:
            value = match.group(1)
            out[area] = '%s-%s-%s' % (value[:4], value[4:6], value[6:])
    return out


def banner_link_dates(masters):
    """{area: earliest 'YYYY-MM-DD'} from F_BANNER_MST links written as `2,21,<area>,<dungeon>,<mission>`.

    Those banner rows are the JP master's own area advertisement list, so the date in the banner filename is
    the JP event date. The earliest row is the original run (the same area can be re-advertised on a reprint).
    """
    out = collections.defaultdict(list)
    with (masters / 'F_BANNER_MST.ndjson').open(encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            parts = str(row.get('1X65WPLU') or '').split(',')
            if len(parts) < 3 or not all(part.strip().isdigit() for part in parts):
                continue
            ids = [int(part) for part in parts]
            if ids[0] != 2 or ids[1] != 21:
                continue
            match = DATE8_RE.search(str(row.get('6Dgaqir0') or ''))
            if match:
                out[str(ids[2])].append('%s-%s-%s' % (match.group(1), match.group(2), match.group(3)))
    return {area: min(dates) for area, dates in out.items() if dates}


def month_gap(a, b):
    return abs((int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7]))


def nearest_dates(area, prefixes, direct, same_prefix=True):
    """Dates of the three nearest dated areas (same mission prefix when asked), sorted."""
    area_no = int(area)
    prefix = str(prefixes.get(area) or '')[:2]
    if same_prefix:
        same = sorted((abs(int(other) - area_no), other) for other in direct
                      if other != area and str(prefixes.get(other) or '')[:2] == prefix)
        pool = same if same else sorted((abs(int(other) - area_no), other)
                                        for other in direct if other != area)
    else:
        pool = sorted((abs(int(other) - area_no), other) for other in direct if other != area)
    return sorted(direct[other] for _gap, other in pool[:3])


def nearest_date(area, prefixes, direct):
    """Median date of the three nearest dated areas sharing the mission prefix (else globally)."""
    near = nearest_dates(area, prefixes, direct)
    return near[len(near) // 2] if near else ''


def season_for(date):
    chosen = SEASON_BOUNDARIES[0][1]
    for boundary, key in SEASON_BOUNDARIES:
        if date >= boundary:
            chosen = key
    return chosen


def group_for(area_id, name, date, altema):
    for token in sorted(COLLAB_TOKENS, key=len, reverse=True):
        if token in name:
            return 'collaborations', 'collab-name:' + token
    if altema and 'コラボ' in str(altema.get('cat') or ''):
        return 'collaborations', 'collab-cat:' + altema['cat']
    for token in PERMANENT_TOKENS:
        if token in name:
            return 'permanent', 'permanent:' + token
    for token in SYSTEM_TOKENS:
        if token in name:
            return 'other', 'system:' + token
    if date:
        return season_for(date), 'season:' + date
    return 'other', 'no-date'


def tab_for(area_id, name, group, altema):
    pinned = TAB_PINNED.get(str(area_id))
    if pinned:
        return pinned, 'pinned'
    for token in TAB_SPECIAL_TOKENS:
        if token in name:
            return TAB_SPECIAL, 'tab-special:' + token
    for token in TAB_STRONG_TOKENS:
        if token in name:
            return TAB_STRONG, 'tab-strong:' + token
    for token in TAB_TRAIN_TOKENS:
        if token in name:
            return TAB_TRAIN, 'tab-train:' + token
    category = str((altema or {}).get('cat') or '')
    for token, tab in ALTEMA_TAB:
        if token in category:
            return tab, 'tab-cat:' + category
    if group == LATEST_SEASON:
        return TAB_LATEST, 'tab-era:latest'
    return TAB_REPRINT, 'tab-era:reprint'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--masters', type=Path, default=DEFAULT_MASTERS)
    parser.add_argument('--altema', type=Path, default=DEFAULT_ALTEMA)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--reprint-sub', type=Path, default=DEFAULT_REPRINT_SUB)
    args = parser.parse_args()
    masters = args.masters.resolve()
    altema_path = args.altema.resolve()
    if not (masters / 'F_AREA_MST.ndjson').is_file():
        parser.error('JP masters not found: %s' % masters)

    areas = servable_areas(masters)
    chambers = seal_area_ids()
    prefixes = mission_prefixes(masters)
    names = banner_names(masters)
    altema = Altema(parse_altema(altema_path))
    banners = banner_dates(names, areas)
    links = banner_link_dates(masters)

    altema_hits = {}
    for area_id in areas:
        name = str(areas[area_id].get('G4L0YIB2') or '')
        hit = altema.match(name)
        if hit:
            altema_hits[area_id] = hit

    # Evidence per area: the JP master date wins (the area's own banner, then F_BANNER_MST's area link); the
    # altema event date is the fallback. Disagreements are kept on the record.
    direct = {}
    evidence = {}
    for area_id in areas:
        name = str(areas[area_id].get('G4L0YIB2') or '')
        banner = banners.get(area_id) or links.get(area_id) or ''
        hit = altema_hits.get(area_id)
        if banner:
            direct[area_id] = banner
            info = {'date': banner, 'date_rule': 'banner' if area_id in banners else 'banner-link'}
            if hit:
                info['altema_date'] = hit['date']
                info['altema_cat'] = hit['cat']
                if banner != hit['date']:
                    info['date_conflict'] = True
            evidence[area_id] = info
        elif hit:
            direct[area_id] = hit['date']
            evidence[area_id] = {'date': hit['date'], 'date_rule': 'altema-' + hit['how'],
                                 'altema_cat': hit['cat']}

    # JP-master anchored dates only (banner/banner-link) are used to sanity-check an altema-only date; the
    # altema dates are not allowed to vouch for each other.
    anchors = {area: info['date'] for area, info in evidence.items()
               if info.get('date') and info.get('date_rule') in ('banner', 'banner-link')}

    rows = {}
    skipped_chambers = 0
    skipped_clones = 0
    for area_id in sorted(areas, key=int):
        if area_id in chambers:
            skipped_chambers += 1
            continue
        if area_id in DUPLICATE_CLONE_AREAS:
            skipped_clones += 1
            continue
        name = str(areas[area_id].get('G4L0YIB2') or '')
        hit = altema_hits.get(area_id)
        info = dict(evidence.get(area_id) or {})
        neighbor = nearest_date(area_id, prefixes, direct)
        block = nearest_dates(area_id, prefixes, anchors, same_prefix=False)
        older = month_gap(info.get('date'), block[1]) if ('date' in info and len(block) == 3
                                                          and month_gap(block[0], block[2]) <= 3) else 0
        if 'date' in info and info['date_rule'].startswith('altema') and older >= 18 \
                and (info['date'][:7] < block[1][:7]):
            # The wiki lists reprints too, so a name can resolve to its original run while the JP area sits in
            # a much later id/mission block (area ids are issued in chronological batches). Only an altema
            # date OLDER than the block is overridden (a newer one is a Vision World/event that reused an old
            # id range); both values are kept.
            info['altema_date'] = info['date']
            info['altema_cat'] = info.get('altema_cat') or (hit or {}).get('cat') or ''
            info['date'] = block[1]
            info['date_rule'] = 'id-neighbor:altema-conflict'
            info['date_conflict'] = True
        if 'date' not in info:
            info = {'date': neighbor, 'date_rule': 'id-neighbor'} if neighbor else {'date': '', 'date_rule': 'none'}
            if hit:
                info['altema_date'] = hit['date']
                info['altema_cat'] = hit['cat']
        group, rule = group_for(area_id, name, info.get('date') or '', hit)
        tab, tab_rule = tab_for(area_id, name, group, hit)
        record = {'group': group, 'rule': rule, 'season_rule': rule,
                  'tab': tab, 'tab_rule': tab_rule,
                  'date': info.get('date') or '', 'date_rule': info.get('date_rule') or 'none',
                  'name': name}
        for key in ('altema_date', 'altema_cat', 'date_conflict'):
            if key in info:
                record[key] = info[key]
        rows[area_id] = record

    reprint_sub = {}
    if args.reprint_sub.is_file():
        with args.reprint_sub.open(encoding='utf-8', newline='') as handle:
            for row in csv.DictReader(handle, delimiter='	'):
                value = int(row['proposed_value'])
                if not 6 <= value <= 10:
                    raise SystemExit('bad reprint sub value %r for area %s' % (value, row['area']))
                reprint_sub[str(row['area'])] = value - 6
    for area_id, record in rows.items():
        sub = reprint_sub.get(area_id, 0)
        if sub and record['tab'] == '2':
            record['sub'] = sub
            record['sub_rule'] = 'reprint-sub:' + REPRINT_SUB_NAMES[sub]

    if '734' not in rows:
        raise SystemExit('734 (One Year Anniversary, Kupo!) is not in the served universe')
    if rows['734']['group'] != DEFAULT_GROUP:
        raise SystemExit('734 must be in %s, got %s (%s)'
                         % (DEFAULT_GROUP, rows['734']['group'], rows['734']['rule']))
    if rows['734']['tab'] != TAB_PINNED['734']:
        raise SystemExit('734 must stay on tab %s, got %s' % (TAB_PINNED['734'], rows['734']['tab']))
    counts = collections.Counter(row['group'] for row in rows.values())
    missing = [key for key, _label in GROUPS if not counts[key]]
    if missing:
        raise SystemExit('empty group(s): ' + ','.join(missing))

    document = {
        'version': 1,
        'generated_by': 'build/make_jp_event_groups.py',
        'source': {'masters': str(masters),
                   'altema': str(altema_path) if altema_path.is_file() else '',
                   'altema_url': 'https://altema.jp/ffbe/eventlist-48657',
                   'servable': len(areas), 'chambers_skipped': skipped_chambers,
                   'duplicate_clones_skipped': skipped_clones},
        'season_boundaries': [{'season': key, 'start': date} for date, key in SEASON_BOUNDARIES],
        'default': DEFAULT_GROUP,
        'groups': {key: label for key, label in GROUPS},
        'tabs': dict(TABS),
        'areas': rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    print('servable %d, chambers skipped %d, clones skipped %d, mapped %d' % (
        len(areas), skipped_chambers, skipped_clones, len(rows)))
    for key, label in GROUPS:
        rules = collections.Counter(row['rule'] for row in rows.values() if row['group'] == key)
        print('  %-15s %-8s %3d areas  %s' % (key, label, counts[key],
                                               ', '.join('%s=%d' % pair for pair in sorted(rules.items()))))
    print('date rules: ' + ', '.join('%s=%d' % pair for pair in
                                     sorted(collections.Counter(row['date_rule'] for row in rows.values()).items())))
    print('tab rules:  ' + ', '.join('%s=%d' % pair for pair in
                                     sorted(collections.Counter(row['tab_rule'].split(':')[0]
                                                                for row in rows.values()).items())))
    print('reprint sub: ' + ', '.join('%s=%d' % (REPRINT_SUB_NAMES[k], v) for k, v in sorted(collections.Counter(
        row.get('sub', 0) for row in rows.values() if row['tab'] == '2').items())))
    print('wrote %s (%d bytes)' % (args.out, args.out.stat().st_size))


if __name__ == '__main__':
    main()

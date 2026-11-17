"""JP 次元の狭間 (Vortex / GateScene) event seasons: the JP counterpart of the Global `event_archive`.

The Global engine serves one archive module (`event_archive.py` in app.imy) whose `menu()` lists campaigns by
season. JP 11.0.0 ships the same module and `LocalGameBridge.eventArchive` -> `android_game.event_archive` ->
`from event_archive import menu`, so this file is NOT a replacement pyc: `jp_compat.install()` monkey-patches the
already imported `event_archive` module's attributes (see build/out/vortex_season/jp_compat_patch.md). That keeps
the `.py`/`.pyc` precedence question out of the build.

Data: `jp_event_groups.json` beside this file (build/make_jp_event_groups.py). It maps every served area to one
of the groups below and records the rule that assigned it.

Interface kept identical to the Global module that android_game and the Frida menu already parse:
  menu(player, selection='') -> {'groups':[{'id','label','ids','count','tab'}], 'selected', 'area_ids',
                                 'native_modes', 'native_dungeons', 'dungeon_names', 'mode_dungeon_ids',
                                 'area_aliases'}
  selected_area_ids(player)  -> the area ids of the player's chosen group (jp_compat's gate policy reads this)
"""
import json
from pathlib import Path

GROUP_ORDER = ('permanent', 'season1', 'season2', 'season3', 'season4', 'season5',
               'collaborations', 'other')
DEFAULT_GROUP = 'season1'
DEFAULT_LABELS = {'permanent': '상시', 'season1': '시즌 1', 'season2': '시즌 2',
                  'season3': '시즌 3', 'season4': '시즌 4', 'season5': '시즌 5',
                  'collaborations': '콜라보', 'other': '기타'}
# GateScene main tab id (`qnUhs32P`) -> label. The ids are NOT display order: the client maps display index
# 0..4 through GATE_TAB_INFO (0,1),(1,2),(2,5),(3,3),(4,4) to these values (see make_jp_event_groups.py).
DEFAULT_TAB_LABELS = {'1': '최신', '2': '복각', '3': '강적', '4': '스페셜', '5': '육성'}
_DOCUMENT = None


def document():
    global _DOCUMENT
    if _DOCUMENT is None:
        path = Path(__file__).with_name('jp_event_groups.json')
        _DOCUMENT = json.loads(path.read_text(encoding='utf-8'))
    return _DOCUMENT


def GROUPS():
    """(id, label) in menu order; labels live in the JSON so one generator owns them."""
    labels = document().get('groups') or DEFAULT_LABELS
    return tuple((key, str(labels.get(key) or DEFAULT_LABELS[key])) for key in GROUP_ORDER)


def events():
    rows = document().get('areas') or {}
    return [{'area': area, 'group': row['group'], 'rule': row.get('rule', ''),
             'tab': row.get('tab', ''), 'name': row.get('name', '')}
            for area, row in sorted(rows.items(), key=lambda kv: int(kv[0]))]


def tab_labels():
    """{tab id: label} in display order (최신, 복각, 육성, 강적, 스페셜) for callers that want the names."""
    labels = document().get('tabs') or DEFAULT_TAB_LABELS
    return {key: str(labels.get(key) or DEFAULT_TAB_LABELS[key]) for key in DEFAULT_TAB_LABELS}


def tab_for(area, default=None):
    """GateScene tab id assigned to `area` in jp_event_groups.json, or `default` when the area is unknown.

    jp_compat's gate wrapper reads this per row; an unknown area (a seal-room chamber, the shipped 226/899
    template rows when their master row is missing) keeps whatever the engine served.
    """
    row = (document().get('areas') or {}).get(str(area))
    if not row:
        return default
    return str(row.get('tab') or default or '1')


_ORDER = None


def order_for(area):
    """1-based release order of `area` over the whole archive (date, then area id), 0 when unknown.

    Served as SpDungeonCondMst.3sv5cRfH (BannerDispOrder, +0x98): GateUtil::getInSessionAreaList sorts the tiles
    with SortUtil::compAreaMst (libgame 0x14cac14), which compares that value ascending when it is > 0 and falls
    back to AreaMst.DispOrder (+0xa8) otherwise -- the engine never sent it, so every season drew in master
    order with the events mixed (tablet, 2026-11-15). Oldest event first; the tabs filter the same sequence.
    """
    global _ORDER
    if _ORDER is None:
        rows = document().get('areas') or {}
        ranked = sorted(rows, key=lambda a: (str(rows[a].get('date') or '9999-99-99'), int(a)))
        _ORDER = {a: n + 1 for n, a in enumerate(ranked)}
    return _ORDER.get(str(area), 0)


def sub_for(area):
    """Sub-tab index (0-based) inside a main tab that has a sub-tab bar (복각: 0..4), 0 when not authored."""
    row = (document().get('areas') or {}).get(str(area)) or {}
    try:
        return max(0, int(row.get('sub') or 0))
    except (TypeError, ValueError):
        return 0


def area_ids():
    return [row['area'] for row in events()]


def listings():
    """One tile per archive row (the Global module groups repeated campaigns; JP has one row per area)."""
    return [(row, []) for row in events()]


def _members():
    members = {key: [] for key in GROUP_ORDER}
    for row in events():
        members.setdefault(row['group'], []).append(row['area'])
    return members


def _ordered(ids):
    return sorted(ids, key=int)


def group_area_ids(group):
    return _ordered(_members().get(str(group), []))


def _menu_groups():
    members = _members()
    permanent = list(members.get('permanent', []))
    groups = []
    for key, label in GROUPS():
        ids = list(members.get(key, []))
        count = len(ids)
        # Global behaviour: the always-available (permanent) areas ride along in every other list.
        if key != 'permanent':
            ids = list(dict.fromkeys(permanent + ids))
        groups.append({'id': key, 'label': label, 'ids': _ordered(ids),
                       'count': count, 'tab': 0})
    return groups


def _selected_group(player):
    known = {group['id'] for group in _menu_groups()}
    chosen = ''
    if player is not None:
        data = getattr(player, 'data', None) or {}
        chosen = str(data.get('event_archive') or '')
    if chosen not in known:
        chosen = DEFAULT_GROUP
    return next(group for group in _menu_groups() if group['id'] == chosen)


def menu(player, selection=''):
    if ':' in str(selection):
        # The Global module uses 'mode:dungeon' for TFA/Parade; JP ships no native-mode archive.
        raise ValueError('Unknown event season')
    groups = _menu_groups()
    known = {group['id'] for group in groups}
    if selection:
        if str(selection) not in known:
            raise ValueError('Unknown event season')
        if player is not None and getattr(player, 'data', None) is not None:
            if player.data.get('event_archive') != str(selection):
                player.data['event_archive'] = str(selection)
                player.dirty = True
    selected = next(group for group in groups if group['id'] == _selected_group(player)['id'])
    return {'groups': groups, 'selected': selected, 'area_ids': area_ids(),
            'native_modes': {}, 'native_dungeons': {}, 'dungeon_names': {},
            'mode_dungeon_ids': [], 'area_aliases': {}}


def selected_area_ids(player=None):
    """Area ids for the player's chosen season (permanent included), for jp_compat's gate policy."""
    return list(_selected_group(player)['ids'])


def activate_mode(player, selection):
    """The Global archive opens TFA/Parade with 'mode:dungeon'; JP has no such archive entry."""
    raise ValueError('Unknown event season')

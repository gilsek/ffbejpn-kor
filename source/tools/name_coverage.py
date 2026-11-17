"""Korean coverage of JP master NAMES (speakers, units, areas ...) from the Memorial-era name sources.

Sources (ffbe_offline_modfix/artifacts unless noted):
  curated   deployment/build_master_name_patches.py CURATED_NAME_MAP (read with ast, not imported)
  teller    deployment/unified_teller_ko_map.json  name_map (JP/EN name -> KO), npc_id_to_ko, unit_prefix7_to_ko
  equip     ffbeequip-units_ko.json (unit id -> KO), ffbeequip-data_ko.json (equipment/materia id -> KO)
  titles    title-localization-audit/playback-title-ko.csv (jp,ko)
  ch1       chapter1-ko/csv_exports/*.csv (japanese -> korean)
  dict      chapter1-ko/Dict/gpt_dict.txt, name替换表/替換表.csv, this repo translations/story-gap-ko/name替换表.csv
Writes build/out/inventory/name_coverage.json (+ missing_names.json: table -> [unique JP names without Korean]).

usage: python -I tools/name_coverage.py
"""
import ast, csv, json, re, sys, zipfile, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'ffbe_offline_modfix'
A = OLD / 'artifacts'
sys.path.insert(0, str(OLD / 'upstream/source/server'))
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
import decode_client_data as D  # noqa: E402

JP = re.compile(r'[぀-ヿ一-鿿]')
HANGUL = re.compile(r'[가-힣]')
LEFT_JP = re.compile(r'[぀-ヺヽ-ヿ一-鿿]')   # kana/kanji, not '・' or 'ー'
# table -> (id field, [name fields])   ids verified against ffbeequip / Memorial patch code where noted
TABLES = {
    'F_NPC_MST': ('Qvb5N1WT', ['G4L0YIB2']),            # speakers (NPC)
    'F_CHARACTER_MST': ('GBjEs49R', ['G4L0YIB2']),      # speakers (story characters)
    'F_UNIT_MST': ('3HriTp6B', ['G4L0YIB2', 'cnLF6Cz1']),
    'F_GUEST_UNIT_MST': (None, ['9qh17ZUf']),
    'F_EQUIP_ITEM_MST': ('J1YX9kmM', ['G4L0YIB2']),
    'F_MATERIA_MST': ('H5jBL0Vf', ['G4L0YIB2']),
    'F_MONSTER_DICTIONARY_MST': (None, ['G4L0YIB2']),
    'F_MONSTER_SKILL_SET_MST': (None, ['G4L0YIB2']),
    'F_WORLD_MST': (None, ['G4L0YIB2']), 'F_LAND_MST': (None, ['G4L0YIB2']), 'F_AREA_MST': (None, ['G4L0YIB2']),
    'F_TOWN_MST': (None, ['G4L0YIB2']), 'F_DUNGEON_MST': (None, ['G4L0YIB2']), 'F_TELEPO_MST': (None, ['G4L0YIB2']),
    'F_MISSION_MST': (None, ['G4L0YIB2']), 'F_STORY_SUB_MST': (None, ['G4L0YIB2']),
    'F_STORY_EVENT_MST': (None, ['G4L0YIB2']), 'F_QUEST_MST': (None, ['G4L0YIB2']), 'F_QUEST_SUB_MST': (None, ['G4L0YIB2']),
    'F_PLAYBACK_EVENT_MST': (None, ['G4L0YIB2']), 'F_PLAYBACK_MAP_MST': (None, ['G4L0YIB2']),
    'F_PLAYBACK_CHAPTER_MST': (None, ['G4L0YIB2']), 'F_PLAYBACK_SEASON_MST': (None, ['G4L0YIB2']),
}


def equipment_names():
    """FFBE Equip의 한국어 이름만 실제 장비/마테리아 ID에 연결한다."""
    rows = json.loads((A / 'ffbeequip-data_ko.json').read_text(encoding='utf-8'))
    candidates = collections.defaultdict(set)
    for row in rows:
        name = row.get('name', '').strip()
        if HANGUL.search(name) and not LEFT_JP.search(name):
            candidates[str(row['id'])].add(name)
    # 중복 ID의 서로 다른 번역은 임의로 고르지 않는다.
    return {rid: next(iter(values)) for rid, values in candidates.items() if len(values) == 1}


def curated_map():
    src = (A / 'deployment/build_master_name_patches.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'CURATED_NAME_MAP' for t in node.targets):
            out = {}
            for k, v in zip(node.value.keys, node.value.values):   # literal pairs only (a few entries are computed)
                try:
                    out[ast.literal_eval(k)] = ast.literal_eval(v)
                except (ValueError, TypeError):
                    pass
            return out
    return {}


def name_sources():
    by_name, unit_ko, npc_ko, p7 = {}, {}, {}, {}
    def add(jp, ko):
        jp, ko = (jp or '').strip(), (ko or '').strip()
        # half-translated values (e.g. "가가라 사암 동굴・かすかな足跡" in older Memorial data) are not Korean
        if jp and ko and HANGUL.search(ko) and not LEFT_JP.search(ko) and jp not in by_name:
            by_name[jp] = ko
    for k, v in curated_map().items():
        add(k, v)
    t = json.loads((A / 'deployment/unified_teller_ko_map.json').read_text(encoding='utf-8'))
    for k, v in t['name_map'].items():
        add(k, v)
    npc_ko.update(t['npc_id_to_ko']); p7.update(t['unit_prefix7_to_ko'])
    for uid, info in json.loads((A / 'ffbeequip-units_ko.json').read_text(encoding='utf-8')).items():
        if isinstance(info, dict) and info.get('name') and HANGUL.search(info['name']):
            unit_ko[str(uid)] = info['name'].strip()
    for row in csv.reader((A / 'title-localization-audit/playback-title-ko.csv').open(encoding='utf-8-sig')):
        if len(row) >= 2 and row[0] != 'jp':
            add(row[0], row[1])
    for f in (A / 'chapter1-ko/csv_exports').glob('*.csv'):
        for r in csv.DictReader(f.open(encoding='utf-8-sig')):
            add(r.get('japanese'), r.get('korean'))
    for line in (A / 'chapter1-ko/Dict/gpt_dict.txt').read_text(encoding='utf-8').splitlines():
        parts = line.split('\t')
        if len(parts) >= 2:
            add(parts[0], parts[1])
    for f in [A / 'chapter1-ko/name替换表.csv', A / 'chapter1-ko/name替換表.csv', ROOT / 'translations/story-gap-ko/name替换表.csv']:
        if f.exists():
            for row in csv.reader(f.open(encoding='utf-8-sig')):
                if len(row) >= 2 and row[0] not in ('SRC_Name', 'jp'):
                    add(row[0], row[1])
    # 화자 이름 추가 초벌 번역표. 위 출처에 없는 이름만 채운다(먼저 온 항목 우선).
    extra = ROOT / 'translations/names-ko/speaker_extra.csv'
    if extra.exists():
        for row in csv.reader(extra.open(encoding='utf-8')):
            if len(row) >= 2 and row[0] != 'jp':
                add(row[0], row[1])
    return by_name, unit_ko, npc_ko, p7


def masters():
    with zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk') as z:
        native = z.read('lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, tok, k = (v.decode() for v in m.groups()); man[n] = (tok, k)
    for tok, e in D.getter_manifest(native).items():
        man[e['table']] = (tok, e['key'])
    return man


def main():
    by_name, unit_ko, npc_ko, p7 = name_sources()
    equipment_ko = equipment_names()
    man = masters()
    src_dir = OLD / 'downloads/ffbejpdata-archive-org'
    report, missing = {}, {}
    for table, (idf, fields) in TABLES.items():
        if table not in man:
            report[table] = 'no key'; continue
        tok, key = man[table]
        f = next(src_dir.glob(f'Ver*_{tok}.dat'), None)
        if not f:
            report[table] = 'no file'; continue
        _, recs = D.decode(f.read_bytes(), key)
        names = collections.OrderedDict()
        for r in recs:
            rid = str(r.get(idf, '')) if idf else ''
            for fld in fields:
                v = str(r.get(fld) or '').strip()
                if v and JP.search(v):
                    names.setdefault(v, rid)
        have = {}
        for jp, rid in names.items():
            base = re.sub(r'＠.*$', '', jp)
            ko = by_name.get(jp) or by_name.get(base)
            if table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST'):
                ko = equipment_ko.get(rid) or ko
            if not ko and table == 'F_UNIT_MST':
                ko = unit_ko.get(rid) or (p7.get(rid[:7]) if len(rid) == 9 else None)
            if not ko and table == 'F_NPC_MST':
                ko = npc_ko.get(rid) or (p7.get(rid[:7]) if len(rid) == 9 and rid.startswith('1000') else None)
            if ko:
                have[jp] = ko
        miss = [n for n in names if n not in have]
        report[table] = {'rows': len(recs), 'unique_jp_names': len(names), 'with_korean': len(have), 'missing': len(miss),
                         'missing_sample': miss[:8]}
        missing[table] = miss
    out = ROOT / 'build/out/inventory'; out.mkdir(parents=True, exist_ok=True)
    (out / 'name_coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'missing_names.json').write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding='utf-8')
    print('name sources:', len(by_name), 'names,', len(unit_ko), 'unit ids,', len(npc_ko), 'npc ids')
    for t, r in report.items():
        if isinstance(r, dict):
            print(f"  {t}: unique {r['unique_jp_names']}, Korean {r['with_korean']}, missing {r['missing']}  e.g. {r['missing_sample'][:4]}")
        else:
            print(f'  {t}: {r}')


if __name__ == '__main__':
    main()

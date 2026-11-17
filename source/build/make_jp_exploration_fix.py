"""Generate build/engine_overlay/jp_exploration_fix.json from JP CPKs and master tables.

Scans all `.cpk` map/event binaries linked to exploration missions (`F_MISSION_MST.Y4VoF8yu == 2`)
for:
  1. Field treasure chest opcodes (`H`/`M`, 0x48/0x4d) matching `content/field_treasures.json`.
  2. Scripted ScenarioBattle opcodes (`G`, 0x47) mapped via `responses.json[29JRaDbd][YjHhvN65]`
     and verified against `F_BATTLE_GROUP_MST.tsv`.

Usage:
    python -I -X utf8 build/make_jp_exploration_fix.py
"""
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402

APK_DEFAULT = ROOT / 'build/out/jp_e78/play/base.apk'
MST_DIR = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
BATTLE_TSV_DIR = Path('C:/Users/USER/Documents/Projects/ffbe_offline_modfix/upstream/source/server/content/battle')
CPK_DIR = Path('D:/Downloads/ffbejpdata/ffbejpdata')
OUT_PATH = ROOT / 'build/engine_overlay/jp_exploration_fix.json'

TREASURE_RE = re.compile(rb'[HM]\x00\x05(.{4})[\x00\x01]', re.S)
SCENARIO_BATTLE_RE = re.compile(rb'G\x00\x04(.{4})', re.S)


def load_ndjson(name):
    rows = []
    with open(MST_DIR / name, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _read_battle_tsv(name, app):
    p = BATTLE_TSV_DIR / name
    lines = p.read_text(encoding='utf-8').splitlines() if p.is_file() else app.read(f'content/battle/{name}').decode('utf-8').splitlines()
    return [line.split('\t') for line in lines if line and not line.startswith('#')]


def load_battle_groups(app):
    """Return battle group IDs whose rows all reference parts present in both F_MONSTER_PARTS_MST and F_MONSTER_MST."""
    parts_ok = {c[0] for c in _read_battle_tsv('F_MONSTER_PARTS_MST.tsv', app) if c and c[0].isdigit()}
    mons_ok = {c[0] for c in _read_battle_tsv('F_MONSTER_MST.tsv', app) if c and c[0].isdigit()}
    valid_parts = parts_ok & mons_ok
    valid, bad = set(), set()
    for c in _read_battle_tsv('F_BATTLE_GROUP_MST.tsv', app):
        if len(c) < 2 or not c[0].isdigit():
            continue
        if c[1] in valid_parts:
            valid.add(c[0])
        else:
            bad.add(c[0])
    return valid - bad


def scan_cpk(stem, ft_cat, sb_map, valid_bgs, cache):
    if stem in cache:
        return cache[stem]
    p = CPK_DIR / f'{stem}.cpk'
    tids, sbids = set(), set()
    if p.is_file():
        c = cpk.Cpk.load_bytes(p.read_bytes(), encoding='cp932')
        bins = [
            i for i in c.file_infos()
            if i.filename == 'map.bin' or i.filename.endswith('_event.bin')
        ]
        exact_ev = f'{stem}_event.bin'
        has_exact_ev = any(i.filename == exact_ev for i in bins)
        selected = [
            i for i in bins
            if not has_exact_ev or i.filename in ('map.bin', exact_ev)
        ]
        for info in selected:
            data = c.file_bytes(info.toc_index)
            for m in TREASURE_RE.finditer(data):
                tid = str(int.from_bytes(m.group(1), 'big'))
                if tid in ft_cat:
                    tids.add(tid)
            for m in SCENARIO_BATTLE_RE.finditer(data):
                sbid = str(int.from_bytes(m.group(1), 'big'))
                bgid = sb_map.get(sbid)
                if bgid and bgid in valid_bgs:
                    sbids.add(bgid)
    cache[stem] = (sorted(tids), sorted(sbids))
    return cache[stem]


def _row_missions(row):
    out = {str(x) for x in (row.get('missions') or []) if x}
    if row.get('mission'):
        out.add(str(row['mission']))
    return out


def _keep_tid_for_mission(tid, row, mid, all_missions):
    if tid.startswith(mid):
        return True
    if len(tid) == 9 and tid[:7] != mid and tid[:7] in all_missions:
        return False
    if len(tid) == 10 and tid[:8] != mid and tid[:8] in all_missions:
        return False
    ms = _row_missions(row)
    if mid in ms:
        return True
    if row.get('town') or row.get('towns'):
        return False
    if ms:
        return False
    return True


def main():
    with zipfile.ZipFile(APK_DEFAULT) as z:
        with zipfile.ZipFile(io.BytesIO(z.read('assets/chaquopy/app.imy'))) as app:
            ft_list = json.loads(app.read('content/field_treasures.json'))['treasures']
            resp = json.loads(app.read('responses.json'))
            valid_bgs = load_battle_groups(app)

    ft_cat = {str(r['id']): r for r in ft_list}
    sb_map = {
        str(r['ja07xgLF']): str(r['2fY1IomW'])
        for r in resp.get('29JRaDbd', {}).get('YjHhvN65', [])
        if r.get('ja07xgLF') and r.get('2fY1IomW')
    }

    res_mst = {}
    for r in load_ndjson('F_RESOURCE_MST.ndjson'):
        fn = str(r.get('pJ56sAEo') or '')
        if fn.endswith('.cpk'):
            res_mst.setdefault(str(r['9ZCEWn0z']), []).append(r)

    res_map = {}
    map_stems_by_dun = {}
    for r in load_ndjson('F_RESOURCE_MAP_MST.ndjson'):
        fn = str(r.get('pJ56sAEo') or '')
        if fn.endswith('.cpk'):
            res_map.setdefault(str(r['Nnb20keZ']), []).append(r)
            if r.get('drE35YcF') == 'map':
                stem = fn[:-4]
                if stem.endswith('00') and stem[:-2].isdigit():
                    map_stems_by_dun.setdefault(stem[:-2], set()).add(stem)

    map_evt = {}
    for r in load_ndjson('F_MAP_EVENT_MST.ndjson'):
        map_evt.setdefault(str(r['6uIYE15X']), []).append(r)

    all_mission_rows = load_ndjson('F_MISSION_MST.ndjson')
    all_mission_ids = {str(r['qo3PECw6']) for r in all_mission_rows}
    missions = {
        str(r['qo3PECw6']): r
        for r in all_mission_rows
        if str(r.get('Y4VoF8yu')) == '2'
    }

    # Index CPK resources already known for each mission from field_treasures.json (covers Season 1-3 story map.bin files
    # like 111010600, 550450500, 550712200 whose dungeon ID != CPK prefix).
    cat_res_by_mid = {}
    for row in ft_list:
        res_stems = [str(x).replace('.cpk', '') for x in (row.get('resources') or []) if x]
        if not res_stems:
            continue
        row_mids = _row_missions(row)
        tid = str(row['id'])
        if len(tid) in (9, 10):
            pref = tid[:-2]
            if pref in missions:
                row_mids.add(pref)
        for rmid in row_mids:
            cat_res_by_mid.setdefault(rmid, set()).update(res_stems)

    scan_cache = {}
    mission_treasures = {}
    mission_scenario_groups = {}
    stem_treasures = {}

    for mid, m in sorted(missions.items()):
        rids = [x for x in str(m.get('q4f9IdMs') or '').split(',') if x]
        own_stems = set(cat_res_by_mid.get(mid, ()))
        for rid in rids:
            for r in res_mst.get(rid, []):
                own_stems.add(r['pJ56sAEo'][:-4])
            for r in res_map.get(rid, []):
                own_stems.add(r['pJ56sAEo'][:-4])

        # Also check F_MAP_EVENT_MST rows explicitly keyed by mission ID or dungeon ID.
        me_stems = set()
        dun = str(m.get('U9iHsau3') or '')
        for key in {k for k in (mid, dun) if k}:
            for r in map_evt.get(key, []):
                for rid in str(r.get('q4f9IdMs') or '').split(','):
                    for res in res_mst.get(rid, []):
                        me_stems.add(res['pJ56sAEo'][:-4])
                    for res in res_map.get(rid, []):
                        me_stems.add(res['pJ56sAEo'][:-4])

        # Check shared map CPKs (<dun>0100.cpk, <mid[:6]>0100.cpk, <mid>00.cpk) for non-story-1xx dungeons
        # (111060100.cpk is an anniversary map, whereas Gran­shelt Underground 11106 uses 111010600.cpk).
        shared_map_stems = set()
        if not mid.startswith('1'):
            for prefix in {k for k in (dun + '01', mid[:6] + '01', mid) if k}:
                shared_map_stems |= map_stems_by_dun.get(prefix, set())

        tids, sbids = set(), set()
        for stem in sorted(own_stems | me_stems):
            t, sb = scan_cpk(stem, ft_cat, sb_map, valid_bgs, scan_cache)
            sbids.update(sb)
            for tid in t:
                if _keep_tid_for_mission(tid, ft_cat[tid], mid, all_mission_ids):
                    tids.add(tid)

        # Shared map.bin CPKs: keep scenario groups unconditionally, and keep chests
        # if they belong to this mission/dungeon prefix or if own event CPKs had none.
        for stem in sorted(shared_map_stems - own_stems - me_stems):
            t, sb = scan_cpk(stem, ft_cat, sb_map, valid_bgs, scan_cache)
            sbids.update(sb)
            for tid in t:
                if not _keep_tid_for_mission(tid, ft_cat[tid], mid, all_mission_ids):
                    continue
                if not tids or tid.startswith(mid) or (dun and tid.startswith(dun)):
                    tids.add(tid)

        if tids:
            mission_treasures[mid] = sorted(tids)
        if sbids:
            mission_scenario_groups[mid] = sorted(sbids)

    for stem, (tids, _) in sorted(scan_cache.items()):
        if tids:
            stem_treasures[stem] = tids

    # Check if any existing tagged chests in ft_cat should not be dropped when resolving,
    # keeping only what CPK scans actually proved.
    out = {
        'mission_treasures': mission_treasures,
        'stem_treasures': stem_treasures,
        'mission_scenario_groups': mission_scenario_groups,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(
        f'Wrote {OUT_PATH}: '
        f'missions_with_treasures={len(mission_treasures)}, '
        f'stems_with_treasures={len(stem_treasures)}, '
        f'missions_with_scenario_groups={len(mission_scenario_groups)}',
        flush=True,
    )


if __name__ == '__main__':
    main()

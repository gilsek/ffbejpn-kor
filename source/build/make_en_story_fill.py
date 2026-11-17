"""Fill the four map-type event areas that have no story files in the JP data (861/883/888/893)
with the Global offline release's map/scene CPKs, replacing the base text files with the release's
official Korean column, and add the missing map/scene ids to a copy of the JP F_RESOURCE_MAP_MST.

Why: JP 11.0.0 has the ids of these areas only as metadata (F_MISSION_MST.q4f9IdMs); the CPKs and the
F_RESOURCE_MAP_MST rows are absent. The Global offline release (release-2026.11.04.9) still ships all
74 map+scene CPKs, and their `*_text_sg.txt` files carry an official Korean column. The JP client has no
multilingual layer, so only the base file (`*_event_text.txt`, `*_event_teller.txt`, `map_text.txt`,
`map_teller.txt`) is read: we rewrite its rows from the Korean column and keep the JP client's format.

Outputs (re-runnable, deterministic):
  build/out/en_story_fill/flat_ko/<file>.cpk          patched CPKs (images/bins byte-identical)
  build/out/en_story_fill/mst/Ver765_B7LnP2TH.dat     JP master + the added rows (existing rows byte-identical)
  build/out/en_story_fill/resource_map_add.ndjson     the added rows, decoded
  build/out/en_story_fill/report.md                   per-area numbers and the self-check result
Does NOT touch build/out/jp_offline/engine/static/mst_decoded/ (the engine master is applied by hand).

CPK writing reuses tools/cpk_inplace.patch (the same function apply_ko_story.py uses for map_common.cpk);
rebuilding with cricodecs cpk.create drops the ID table and breaks the client, so the CPK layout is kept.
Row text handling reuses apply_ko_story.split_rows/join_rows/COMMA (rows are `id,text` and the client
splits on every ASCII comma, so Korean commas are written as '‚').

usage: PYTHONIOENCODING=utf-8 python -X utf8 build/make_en_story_fill.py
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
sys.path.insert(0, str(ROOT / 'tools/vendor'))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'build'))
sys.path.insert(0, str(OLD / 'upstream/source/server'))
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))

from cricodecs import cpk  # noqa: E402
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16  # noqa: E402
from decode_client_data import decode as decode_master, json_record  # noqa: E402
import apply_ko_story as AKS  # noqa: E402  (split_rows / join_rows / COMMA / HANGUL / JP_CHAR)
import cpk_inplace  # noqa: E402
import name_coverage as NC  # noqa: E402

AREAS = ('861', '883', '888', '893')
STATIC = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
OUT = ROOT / 'build/out/en_story_fill'
JP_PACK = Path(r'D:\Downloads\ffbejpdata\ffbejpdata')
RESOURCE_TABLE = 'F_RESOURCE_MAP_MST'
ID_KEY = 'Nnb20keZ'          # ResourceMapMst.id
KIND_KEY = 'dX0SkK3j'        # 200 = map, 300 = event scene
FILE_KEY = 'pJ56sAEo'        # cpk file name
AREA_KEY = 'uv60hgDW'        # MissionMst.areaId
IDS_KEY = 'q4f9IdMs'         # MissionMst resource id list (2xxxxx map, 3xxxxxxxx scene, 4xxxxx bgm)
VER = re.compile(r'^Ver\d+_')
# Korean base text of the user's own memorial build (com.exvius.memorial.korean, files/side_stories/), used
# only for rows whose official `_sg` Korean cell is empty (all of 893). Copied 2026-11-13.
MEMORIAL = ROOT / 'translations/story-en-fill/memorial_ko'
HANGUL = re.compile(r'[가-힣]')
TAG = re.compile(r'<([A-Za-z_]+)(?:=[^>]*)?>')
HANGUL, JP_CHAR = AKS.HANGUL, AKS.JP_CHAR


def ndjson(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def raw_ndjson(path):
    return [line for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def release_index(release):
    """cpk file name (Ver<N>_ prefix stripped) -> [(zip name, member name, size)]."""
    index = collections.defaultdict(list)
    for z in sorted(release.glob('exvius-data-*.zip')):
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                if info.filename.lower().endswith('.cpk'):
                    index[VER.sub('', Path(info.filename).name)].append((z.name, info.filename, info.file_size))
    return index


def read_release_cpk(release, index, name):
    """Read one cpk from the release zips; common_lang wins, then the largest copy."""
    candidates = index.get(name)
    if not candidates:
        return None, None
    candidates = sorted(candidates, key=lambda c: (0 if '/common_lang/' in c[1] else 1, -c[2]))
    zip_name, member, _ = candidates[0]
    with zipfile.ZipFile(release / zip_name) as zf:
        return zf.read(member), (zip_name, member, len(candidates))


def parse_sg(data):
    return [line.split('^') for line in data.decode('utf-8-sig').splitlines() if line]


def detect_ko_column(sg_texts):
    """The release's `_sg` row is id^en^zh-TW^ko^fr^de^es^en^id. Detect the Korean column from the data:
    per file pick the column with the most Hangul, then take the majority across files."""
    votes = collections.Counter()
    for rows in sg_texts:
        width = max((len(r) for r in rows), default=0)
        counts = [sum(1 for r in rows if len(r) > c and HANGUL.search(r[c])) for c in range(width)]
        if counts and max(counts):
            votes[counts.index(max(counts))] += 1
    if not votes:
        raise SystemExit('self-check failed: no Hangul column in any _sg file')
    column = votes.most_common(1)[0][0]
    return column, votes


def text_kind(filename):
    if filename.endswith('_teller.txt') or filename == 'map_teller.txt':
        return 'teller'
    return 'dialogue'


def memorial_rows(name):
    """{base text file: {row id: body}} of the memorial copy of a cpk, Hangul rows only."""
    path = MEMORIAL / name
    if not path.exists():
        return {}
    package = cpk.Cpk.load_bytes(path.read_bytes(), encoding='utf-8')
    rows = {}
    for info in package.file_infos():
        if info.filename.endswith('.txt') and not info.filename.endswith('_sg.txt'):
            rows[info.filename] = {rid: body for rid, sep, body in text_rows(package.file_bytes(info.toc_index))
                                   if sep and HANGUL.search(body)}
    return rows


def patch_cpk(orig, ko_column, fallback=None):
    """Rewrite every base text file from its `_sg` Korean column. Returns (new bytes, stats)."""
    package = cpk.Cpk.load_bytes(orig, encoding='utf-8')
    infos = list(package.file_infos())
    by_name = {info.filename: info for info in infos}
    replace, stats = {}, collections.defaultdict(int)
    for info in infos:
        name = info.filename
        if not name.endswith('.txt') or name.endswith('_sg.txt'):
            continue
        sg_info = by_name.get(name[:-4] + '_sg.txt')
        if sg_info is None:
            stats['no_sg'] += 1
            continue
        data = package.file_bytes(info.toc_index)
        try:
            data.decode('utf-8-sig')
        except UnicodeDecodeError:
            stats['not_utf8'] += 1
            continue
        korean = {}
        for parts in parse_sg(package.file_bytes(sg_info.toc_index)):
            if len(parts) > ko_column and parts[ko_column].strip():
                korean[parts[0]] = parts[ko_column]
        lines, newline, bom = AKS.split_rows(data)
        out, kind = [], text_kind(name)
        for line in lines:
            if not line:
                out.append(line)
                continue
            row_id, sep, _body = line.partition(',')
            cell = korean.get(row_id) if sep else None
            memo = (fallback or {}).get(name, {}).get(row_id) if sep and cell is None else None
            if memo is not None:
                out.append(row_id + ',' + memo)
                stats[kind + '_memorial'] += 1
                stats[kind + '_translated'] += 1
                if collections.Counter(TAG.findall(memo)) != collections.Counter(TAG.findall(_body)):
                    stats['memorial_tag_diff'] += 1
                continue
            if cell is None:
                out.append(line)
                stats[kind + '_kept'] += 1
                continue
            # Same convention as apply_ko_story: the client splits a row on every ASCII comma.
            out.append(row_id + ',' + cell.replace(',', AKS.COMMA))
            stats[kind + '_translated'] += 1
        replace[info.full_path] = AKS.join_rows(out, newline, bom)
        stats['files'] += 1
    if not replace:
        return None, stats
    return cpk_inplace.patch(orig, replace, encoding='utf-8'), stats


def build_master(jp_dat, add_lines, k16):
    """Insert the added rows into the JP master, sorted by numeric id; existing lines stay byte-identical."""
    original = [line for line in jp_dat.read_bytes().decode('ascii').splitlines() if line.strip()]
    pending = sorted(add_lines.items(), key=lambda kv: int(kv[0]))
    first = cbc_decrypt(k16, original[0])
    pad = first[-1]
    double_pad = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
    added = {rid: cbc_encrypt(k16, line.encode('utf-8'), double_pad=double_pad) for rid, line in pending}
    merged, cursor = [], 0
    for line in original:
        row_id = str(json_record(cbc_decrypt(k16, line)).get(ID_KEY, ''))
        while cursor < len(pending) and int(pending[cursor][0]) < int(row_id):
            merged.append(added[pending[cursor][0]])
            cursor += 1
        merged.append(line)
    merged.extend(added[rid] for rid, _ in pending[cursor:])
    return original, merged, double_pad


def text_rows(blob):
    """[(id, body)] of a base text file."""
    return [line.partition(',') for line in blob.decode('utf-8-sig').splitlines() if line]


def verify(produced, ko_column, master_orig, master_lines, master_rows, mst_path, key):
    """(a)-(d) self-checks. Returns (problems, tag counts)."""
    problems = []
    tag_total = collections.Counter()
    for name, (orig, out) in produced.items():
        p1 = cpk.Cpk.load_bytes(orig, encoding='utf-8')
        p2 = cpk.Cpk.load_bytes(out, encoding='utf-8')
        i1 = list(p1.file_infos())
        i2 = list(p2.file_infos())
        if [e.full_path for e in i1] != [e.full_path for e in i2]:
            problems.append(f'{name}: file list changed')
            continue
        by2 = {e.filename: e for e in i2}
        for a in i1:
            b = by2[a.filename]
            da, db = p1.file_bytes(a.toc_index), p2.file_bytes(b.toc_index)
            if not a.filename.endswith('.txt') or a.filename.endswith('_sg.txt'):
                if da != db:
                    problems.append(f'{name}:{a.filename}: bytes changed')
                continue
            ra, rb = text_rows(da), text_rows(db)
            if [x[0] for x in ra] != [x[0] for x in rb] or len(ra) != len(rb):
                problems.append(f'{name}:{a.filename}: row ids/order changed')
                continue
            sg_info = [e for e in i1 if e.filename == a.filename[:-4] + '_sg.txt']
            if not sg_info:
                problems.append(f'{name}:{a.filename}: no _sg file')
                continue
            sg = {parts[0]: parts[ko_column]
                  for parts in parse_sg(p1.file_bytes(sg_info[0].toc_index))
                  if len(parts) > ko_column}
            memo = memorial_rows(name).get(a.filename, {})
            expected = [(rid, (sg[rid].replace(',', AKS.COMMA) if sg.get(rid, '').strip() else body))
                        for rid, _sep, body in ra]
            for (rid, body_a), (rid_b, body_b) in zip(expected, [(x[0], x[2]) for x in rb]):
                if not sg.get(rid, '').strip() and rid in memo:
                    if body_b != memo[rid]:
                        problems.append(f'{name}:{a.filename}:{rid}: body differs from the memorial row')
                    tag_total.update(TAG.findall(body_b))
                    continue
                if body_a != body_b:
                    problems.append(f'{name}:{a.filename}:{rid}: body differs from the Korean column')
                ta, tb = collections.Counter(TAG.findall(body_a)), collections.Counter(TAG.findall(body_b))
                if ta != tb:
                    problems.append(f'{name}:{a.filename}:{rid}: tag counts differ')
                tag_total.update(tb)
    # (c) master
    if len(master_lines) != len(master_orig) + len(master_rows):
        problems.append(f'master: {len(master_orig)} + {len(master_rows)} != {len(master_lines)}')
    i = 0
    for line in master_lines:
        if i < len(master_orig) and line == master_orig[i]:
            i += 1
    if i != len(master_orig):
        problems.append(f'master: only {i}/{len(master_orig)} original rows kept byte-identical')
    try:
        _mode, rows = decode_master(mst_path.read_bytes(), key)
    except Exception as ex:   # noqa: BLE001 - the decoder reports every failure as ValueError
        problems.append(f'master: decode failed: {ex}')
        rows = []
    if len(rows) != len(master_orig) + len(master_rows):
        problems.append(f'master: decoded {len(rows)} rows')
    have = {str(r.get(ID_KEY)) for r in rows}
    missing = [rid for rid in master_rows if rid not in have]
    if missing:
        problems.append(f'master: added ids not decodable: {missing[:5]}')
    return problems, tag_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', default=str(OLD / 'downloads/release-2026.11.04.9'))
    ap.add_argument('--jp-pack', default=str(JP_PACK))
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    release, jp_pack, out = Path(args.release), Path(args.jp_pack), Path(args.out)
    out.joinpath('flat_ko').mkdir(parents=True, exist_ok=True)
    out.joinpath('mst').mkdir(parents=True, exist_ok=True)

    missions = ndjson(STATIC / 'F_MISSION_MST.ndjson')
    jp_rows = {row[ID_KEY]: row for row in ndjson(STATIC / (RESOURCE_TABLE + '.ndjson'))}
    gl_rows = {row[ID_KEY]: row for row in ndjson(STATIC / (RESOURCE_TABLE + '.ndjson.global'))}
    gl_raw = {json.loads(line)[ID_KEY]: line for line in raw_ndjson(STATIC / (RESOURCE_TABLE + '.ndjson.global'))}
    jp_files = {p.name for p in jp_pack.glob('*.cpk')}

    # 1. ids of the story missions that the JP table lacks but the Global table has
    per_area, no_row, targets = {}, {}, []
    for area in AREAS:
        ids = sorted({rid for row in missions if row.get(AREA_KEY) == area
                      for rid in str(row.get(IDS_KEY, '')).split(',') if rid})
        missing = [rid for rid in ids if rid not in jp_rows]
        no_row[area] = [rid for rid in missing if rid not in gl_rows]
        todo = [rid for rid in missing if rid in gl_rows]
        per_area[area] = {'ids': ids, 'missing': missing, 'todo': todo}
        targets.extend((area, rid) for rid in todo)
    # A file that the JP pack already has (893010100.cpk) is never rewritten.
    skipped = [(area, rid, gl_rows[rid][FILE_KEY]) for area, rid in targets
               if gl_rows[rid][FILE_KEY] in jp_files]
    targets = [(area, rid) for area, rid in targets if gl_rows[rid][FILE_KEY] not in jp_files]

    # 2. read the release CPKs, work out the Korean column from the data
    index = release_index(release)
    orig_bufs, sg_texts, duplicates, not_found = {}, [], {}, []
    for area, rid in targets:
        name = gl_rows[rid][FILE_KEY]
        data, where = read_release_cpk(release, index, name)
        if data is None:
            not_found.append(name)
            continue
        if where[2] > 1:
            duplicates[name] = where
        orig_bufs[name] = data
        pkg = cpk.Cpk.load_bytes(data, encoding='utf-8')
        for info in pkg.file_infos():
            if info.filename.endswith('_sg.txt'):
                sg_texts.append(parse_sg(pkg.file_bytes(info.toc_index)))
    ko_column, votes = detect_ko_column(sg_texts)

    # 3. write the Korean CPKs
    produced, file_stats, anomalies = {}, {}, []
    for area, rid in targets:
        name = gl_rows[rid][FILE_KEY]
        if name not in orig_bufs:
            anomalies.append(f'{name}: release copy not found')
            continue
        new, stats = patch_cpk(orig_bufs[name], ko_column, memorial_rows(name))
        if new is None:
            anomalies.append(f'{name}: no base text file to rewrite')
            continue
        out.joinpath('flat_ko', name).write_bytes(new)
        produced[name] = (orig_bufs[name], new)
        file_stats[name] = dict(stats, area=area, rid=rid)
        stem = name[:-4]
        own_bins = {stem + '_event.bin', 'map.bin'}
        extra = [f for f in cpk.Cpk.load_bytes(orig_bufs[name], encoding='utf-8').file_infos()
                 if f.filename.endswith('.bin') and f.filename not in own_bins]
        if extra:
            anomalies.append(f'{name}: unexpected bin {[e.filename for e in extra]}')

    # 4. the client master: JP F_RESOURCE_MAP_MST + the added ids
    manifest = NC.masters()
    token, key = manifest[RESOURCE_TABLE]
    jp_dats = sorted(jp_pack.glob(f'Ver*_{token}.dat'))
    if len(jp_dats) != 1:
        raise SystemExit(f'expected one JP master for {token}, found {[p.name for p in jp_dats]}')
    jp_dat = jp_dats[0]
    k16 = key16(key)
    added_ids = [rid for _area, rid in targets if rid in gl_raw]
    master_orig, master_lines, double_pad = build_master(
        jp_dat, {rid: gl_raw[rid] for rid in added_ids}, k16)
    mst_out = out / 'mst' / jp_dat.name
    mst_out.write_text('\n'.join(master_lines) + '\n', encoding='ascii')
    out.joinpath('resource_map_add.ndjson').write_text(
        ''.join(gl_raw[rid] + '\n' for rid in sorted(added_ids, key=int)), encoding='utf-8')

    # 5. self-check
    problems, tag_total = verify(produced, ko_column, master_orig,
                                 master_lines, added_ids, mst_out, key)
    # (d) every 2xxxxx/3xxxxxxxx id of the area's story missions: in a table and file present?
    coverage = {}
    for area in AREAS:
        info = per_area[area]
        budget = collections.Counter()
        for rid in info['ids']:
            if rid[:1] not in '23':
                continue
            row = jp_rows.get(rid) or gl_rows.get(rid)
            if row is None:
                budget['no_row'] += 1
                continue
            budget['has_row'] += 1
            if row[FILE_KEY] in jp_files or (out / 'flat_ko' / row[FILE_KEY]).exists():
                budget['has_file'] += 1
            else:
                budget['no_file'] += 1
                problems.append(f'area {area}: {rid} -> {row[FILE_KEY]} missing')
        coverage[area] = budget
    # (e) Japanese/English left in the produced text rows
    leftovers = collections.defaultdict(collections.Counter)
    for name, (_orig, new) in produced.items():
        area = file_stats[name]['area']
        pkg = cpk.Cpk.load_bytes(new, encoding='utf-8')
        for info in pkg.file_infos():
            if not info.filename.endswith('.txt') or info.filename.endswith('_sg.txt'):
                continue
            kind = 'maptext' if info.filename == 'map_text.txt' else text_kind(info.filename)
            for _rid, _sep, body in text_rows(pkg.file_bytes(info.toc_index)):
                if JP_CHAR.search(body):
                    leftovers[area][kind + '_jp'] += 1
                if not HANGUL.search(body):
                    leftovers[area][kind + '_no_hangul'] += 1
    if problems:
        print('SELF-CHECK FAILED:')
        for problem in problems[:20]:
            print('  -', problem)
        raise SystemExit(1)

    # 6. report
    lines = ['# 영문판 오프라인 릴리스로 채운 지도형 이벤트 스토리 (861/883/888/893)', '',
             f'- 대상 테이블: `{RESOURCE_TABLE}` (토큰 `{token}`), JP `{jp_dat.name}`',
             f'- 한글 열: `_sg` 0-based 열 {ko_column} '
             f'(파일별 판정 {dict(votes.most_common())}; 한글이 전혀 없는 파일은 투표에서 빠진다)',
             f'- 더블 패딩: {double_pad}', '',
             '## 지역별', '',
             '| 지역 | cpk | 대사 행 | 한국어 대체 | 영어 유지 | teller 행 | teller 대체 | 영문판에도 없는 id |',
             '|---:|---:|---:|---:|---:|---:|---:|---:|']
    tot = collections.Counter()
    total_cpk = 0
    for area in AREAS:
        files = [n for n in file_stats if file_stats[n]['area'] == area]
        s = collections.Counter()
        for name in files:
            for k, v in file_stats[name].items():
                if isinstance(v, int) and k not in ('area', 'files'):
                    s[k] += v
        total_cpk += len(files)
        dial = s['dialogue_translated'] + s['dialogue_kept']
        tel = s['teller_translated'] + s['teller_kept']
        lines.append(f'| {area} | {len(files)} | {dial} | {s["dialogue_translated"]} | '
                     f'{s["dialogue_kept"]} | {tel} | {s["teller_translated"]} | {len(no_row[area])} |')
        tot.update(s)
    lines += ['', f'합계: cpk {total_cpk}, 대사 행 {tot["dialogue_translated"] + tot["dialogue_kept"]}, '
                  f'한국어 대체 {tot["dialogue_translated"]}, 영어 유지 {tot["dialogue_kept"]}, '
                  f'teller {tot["teller_translated"] + tot["teller_kept"]}행 중 {tot["teller_translated"]}행 대체', '',
              '## 영문판에도 없는 id', '']
    for area in AREAS:
        lines.append(f'- {area}: {no_row[area] or "없음"}')
    lines += ['', '## 검증', '',
              f'- (a) 만든 cpk {len(produced)}개 재개방: 파일 목록 동일, 기본 텍스트 행 수·id 순서 동일, '
              f'그림/bin 바이트 동일 — 통과',
              f'- (b) 태그 종류별 개수 한국어 열과 일치 — 통과 (태그 합계 {dict(sorted(tag_total.items()))})',
              f'- (c) 새 마스터 {len(master_orig)} + {len(added_ids)} = {len(master_lines)}행, 기존 {len(master_orig)}행 바이트 동일, '
              f'추가 id 전부 디코드 조회 가능 — 통과',
              '- (d) 지역별 2xxxxx/3xxxxxxxx id 표·파일 확인: ' +
              ', '.join(f'{a} {dict(sorted(coverage[a].items()))}' for a in AREAS),
              '- (e) 남은 일본어/영어 행:']
    for area in AREAS:
        if leftovers[area]:
            lines.append(f'  - {area}: ' + ', '.join(f'{k} {v}' for k, v in sorted(leftovers[area].items())))
    lines += ['', '## 의심 항목 / 확인 못 한 것', '']
    lines.append(f'- `893010100.cpk`(맵)은 일판 묶음에 이미 있어 건드리지 않았다: '
                 f'{[f"{a}:{r}" for a, r, _n in skipped] or "해당 없음"}.')
    if not_found:
        lines.append(f'- 영문판 zip 에서 못 찾은 cpk: {not_found}')
    if duplicates:
        lines.append(f'- 영문판 zip 에 같은 이름이 여러 번: {duplicates}')
    all_english = sorted(n for n in file_stats
                         if file_stats[n].get('dialogue_kept', 0) and not file_stats[n].get('dialogue_translated', 0))
    lines.append(f'- `_sg` 한국어 열이 비어 있어 대사가 전부 영어로 남는 cpk {len(all_english)}개: '
                 f'{all_english}')
    lines.append('- `map_text_sg` 가 비어 있는 맵 cpk 는 `map_text.txt` 의 원문(일본어)이 그대로 남는다'
                 ' (맵 내부 구역 이름 표시).')
    folder_diff = sorted({(rid, gl_rows[rid]['3LHdc6Qa']) for _a, rid in targets})
    lines.append(f'- 영문판 행의 폴더 값이 일판과 다르다: 예 {folder_diff[:3]} '
                 '(일판 이벤트는 `event/SP4`, 영문판은 `event2/SPR27`). 행은 지시대로 영문판 그대로 넣었으니, '
                 '배포 시 cpk 를 그 폴더 경로에 두거나 폴더 값을 바꿔야 한다.')
    for anomaly in anomalies:
        lines.append(f'- {anomaly}')
    lines.append('- 영문판 cpk 의 `event.bin` 머리(4바이트 big-endian 길이 + 0x00000418)와 맵 `map.bin` 구조는 '
                 '일판 872010101/872010100 과 같은 형식으로 보이나, 일판 엔진이 그대로 읽는지는 기기에서 확인하지 않았다.')
    lines.append(f'- 일판 마스터 옆에 `{token}.i` 행 인덱스가 따로 있다(10바이트 머리 + 12바이트/행 (id, offset, size) 형식으로 보임). '
                 '행을 추가하면 이 인덱스가 어긋나므로 배포 시 재생성하거나 지워야 한다.')
    out.joinpath('report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(f"cpk {len(produced)}개 -> {out / 'flat_ko'}")
    for area in AREAS:
        files = [n for n in file_stats if file_stats[n]['area'] == area]
        s = collections.Counter()
        for name in files:
            for k, v in file_stats[name].items():
                if isinstance(v, int) and k != 'area':
                    s[k] += v
        print(f"  {area}: cpk {len(files)}, 대사 {s['dialogue_translated'] + s['dialogue_kept']}"
              f"(한국어 {s['dialogue_translated']}, 영어 {s['dialogue_kept']}),"
              f" teller {s['teller_translated'] + s['teller_kept']}(한국어 {s['teller_translated']}),"
              f" 영문판에도 없는 id {len(no_row[area])}")
    print(f"master -> {mst_out} ({len(master_orig)} + {len(added_ids)} = {len(master_lines)} rows)")
    print(f"report -> {out / 'report.md'}")
    print('SELF-CHECK OK')


if __name__ == '__main__':
    main()

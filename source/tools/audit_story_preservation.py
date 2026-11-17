"""Inspect story dialogue separately from speaker names and generic UI text."""
import collections
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from audit_complete_release import ROOT, TAG, load_archive
from release_reader import Release

HANGUL = re.compile(r'[\uac00-\ud7a3]')
JAPANESE = re.compile(r'[\u3040-\u30ff]')
CJK = re.compile(r'[\u3400-\u9fff]')
LETTER = re.compile(r'[^\W\d_]', re.UNICODE)


def classify(english, korean):
    en, ko = (TAG.sub('', value).strip() for value in (english, korean))
    if not (LETTER.search(en) or LETTER.search(ko)):
        return 'neutral_no_letters'
    if not ko:
        return 'ko_blank'
    if HANGUL.search(ko):
        if ko == en:
            return 'hangul_shared_with_english'
        if JAPANESE.search(ko):
            return 'hangul_mixed_with_japanese'
        return 'korean_candidate'
    if JAPANESE.search(ko):
        return 'japanese_in_ko'
    if CJK.search(ko):
        return 'cjk_without_hangul_in_ko'
    if ko == en:
        return 'same_as_english_review'
    return 'other_non_korean_review'


def run(folder):
    release = Release(folder)
    resources = {row['Nnb20keZ']: row for row in release.table('F_RESOURCE_MAP_MST')}
    versions = {row['Nnb20keZ']: row['OzT5lSz3'] for row in
                release.table('F_RESOURCE_MAP_VERSION_MST_LOCALIZE')}
    missions = {row['qo3PECw6']: row for row in release.table('F_MISSION_MST')}
    dungeons = {row['U9iHsau3']: row for row in release.table('F_DUNGEON_MST')}
    chapter_names = {row['0J2VIT8w']: row['G4L0YIB2'] for row in release.table('F_STORY_MST')}
    dungeon_chapters = collections.defaultdict(set)
    for row in release.table('F_STORY_SUB_MST'):
        if row['Lxj5u3WB'] == '3':
            dungeon_chapters[row['6uIYE15X']].add(row['0J2VIT8w'])
    links = collections.defaultdict(set)
    link_sources = collections.defaultdict(set)

    def add(entity, resource_list, source):
        if not entity:
            return
        chapters = dungeon_chapters[entity.get('U9iHsau3')]
        for rid in resource_list.split(','):
            if rid:
                links[rid].update(chapters)
                link_sources[rid].add(source)

    for table, field in (('F_MAP_EVENT_MST', 'q4f9IdMs'),
                         ('F_MAP_EXT_RESOURCE_MST', 'Y4PER0gB')):
        for row in release.table(table):
            # Types 1 and 3 are mission and dungeon. Type 2 is not assumed.
            entity = {'1': missions, '3': dungeons}.get(row['Lxj5u3WB'], {}).get(row['6uIYE15X'])
            add(entity, row.get(field, ''), table)
    for entity in list(missions.values()) + list(dungeons.values()):
        add(entity, entity.get('q4f9IdMs', ''), 'entity_resource_list')
    path_chapters = collections.defaultdict(set)
    folder_chapters = collections.defaultdict(set)
    active_paths = set()
    for rid, row in resources.items():
        if not row['3LHdc6Qa'].startswith('event'):
            continue
        path = f"native/common_lang/sd/{row['3LHdc6Qa']}/Ver{versions[rid]}_{row['pJ56sAEo']}"
        active_paths.add(path)
        path_chapters[path].update(links[rid])
        folder_chapters[row['3LHdc6Qa']].update(links[rid])
    all_results = []
    row_inventory = []
    errors = []
    started = time.monotonic()
    targets = [path for path in release.files if
               re.match(r'native/common_lang/sd/event[^/]*/', path) and path.endswith('.cpk')]
    for number, path in enumerate(targets, 1):
        folder_name = '/'.join(path.split('/')[3:5])
        native_main_block = bool(re.fullmatch(r'event[234]?/\d+', folder_name))
        record = {'path': path, 'block': folder_name, 'active_resource_version': path in active_paths,
                  'numeric_main_block': native_main_block,
                  'direct_chapter_ids': sorted(path_chapters[path], key=int),
                  'block_connected_chapter_ids': sorted(folder_chapters[folder_name], key=int),
                  'dialogue': {}, 'speakers': {}, 'tables': []}
        try:
            archive, _ = load_archive(release.read(path))
            for index, member in enumerate(archive.file_infos()):
                name = member.full_path
                kind = ('dialogue' if name.endswith('_event_text_sg.txt') else
                        'speakers' if name.endswith('_event_teller_sg.txt') else None)
                if kind is None:
                    continue
                rows = [line.split('^') for line in archive.file_bytes(index).decode('utf-8-sig').splitlines() if line]
                metrics = collections.Counter()
                signatures = []
                for row in rows:
                    english = row[1] if len(row) > 1 else ''
                    korean = row[3] if len(row) > 3 else ''
                    category = classify(english, korean) if len(row) > 3 else 'ko_column_absent'
                    metrics[category] += 1
                    metrics['rows'] += 1
                    displayed_en = TAG.sub('', english).strip()
                    if category == 'same_as_english_review' and len(displayed_en) >= 25 and len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", displayed_en)) >= 4:
                        metrics['english_sentence_candidate'] += 1
                        if len(row) >= 9 and len({TAG.sub('', cell).strip() for cell in row[1:9]}) == 1:
                            metrics['eight_columns_same_english_sentence'] += 1
                    if HANGUL.search(TAG.sub('', korean)):
                        metrics['any_hangul'] += 1
                    signature = hashlib.sha256((row[0] + '\0' + korean).encode()).hexdigest()
                    signatures.append(signature)
                    row_inventory.append({'path': path, 'member': name, 'kind': kind, 'id': row[0],
                                          'category': category, 'ko_signature': signature})
                record[kind] = dict(collections.Counter(record[kind]) + metrics)
                record['tables'].append({'member': name, 'kind': kind, 'metrics': dict(metrics)})
        except Exception as error:
            errors.append({'path': path, 'error': type(error).__name__ + ': ' + str(error)})
        all_results.append(record)
        if number % 1000 == 0:
            print(json.dumps({'scanned': number, 'total': len(targets), 'seconds': round(time.monotonic()-started)}), flush=True)
    # Chapter links are explicitly many-to-many. Never sum them as unique totals.
    chapters = []
    chapter_ids = set(chapter_names) | set().union(*dungeon_chapters.values())
    for cid in sorted(chapter_ids, key=int):
        title = chapter_names.get(cid, 'Title missing from F_STORY_MST')
        own = [r for r in all_results if cid in r['direct_chapter_ids']]
        counts = collections.Counter()
        for record in own:
            counts.update(record['dialogue'])
        chapters.append({'chapter_id': cid, 'title': title, 'direct_linked_cpks': len(own),
                         'dialogue': dict(counts)})
    blocks = []
    for block in sorted({r['block'] for r in all_results}):
        own = [r for r in all_results if r['block'] == block]
        result = {'block': block, 'cpks': len(own), 'active_cpks': sum(r['active_resource_version'] for r in own),
                  'connected_chapter_ids': sorted(folder_chapters[block], key=int)}
        for kind in ('dialogue', 'speakers'):
            result[kind] = dict(sum((collections.Counter(r[kind]) for r in own), collections.Counter()))
        result['cpks_with_korean_dialogue_candidate'] = sum(bool(r['dialogue'].get('korean_candidate')) for r in own)
        blocks.append(result)
    summary = {'version': release.manifest['version'], 'event_cpks': len(targets),
               'errors': len(errors), 'chapter_link_warning': 'Direct links are incomplete; shared dungeons connect multiple chapters. Block connections are context, not exact assignment.',
               'main_numeric_blocks': [], 'other_blocks': []}
    for prefix in ('event', 'event2', 'event3', 'event4'):
        own = [r for r in all_results if r['numeric_main_block'] and r['block'].split('/')[0] == prefix]
        result = {'resource_family': prefix, 'cpks': len(own),
                  'cpks_with_korean_dialogue_candidate': sum(bool(r['dialogue'].get('korean_candidate')) for r in own)}
        for kind in ('dialogue', 'speakers'):
            result[kind] = dict(sum((collections.Counter(r[kind]) for r in own), collections.Counter()))
        summary['main_numeric_blocks'].append(result)
    others = [r for r in all_results if not r['numeric_main_block']]
    summary['other_blocks'] = {'cpks': len(others), 'dialogue': dict(sum((collections.Counter(r['dialogue']) for r in others), collections.Counter()))}
    direct = [r for r in all_results if r['direct_chapter_ids']]
    summary['direct_chapter_linked_packages'] = {
        'cpks': len(direct),
        'dialogue': dict(sum((collections.Counter(r['dialogue']) for r in direct), collections.Counter())),
        'warning': 'Subset with explicit chapter links; not the full narrative denominator.'}
    numeric_paths = {r['path'] for r in all_results if r['numeric_main_block']}
    korean_numeric = [r for r in row_inventory if r['kind'] == 'dialogue' and r['path'] in numeric_paths and r['category'] == 'korean_candidate']
    summary['numeric_block_unique_korean_row_signatures'] = len({r['ko_signature'] for r in korean_numeric})
    output = {'summary': summary, 'blocks': blocks, 'direct_chapter_links': chapters,
              'packages': all_results, 'errors': errors,
              'method': 'KO column 3, EN column 1. Speaker tables separate. Korean candidate = Hangul, different from English, no kana. Equal English is review, not automatic failure. Numeric resource blocks are not automatically exact story chapters.'}
    (ROOT/'artifacts/story-preservation-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf8')
    with (ROOT/'artifacts/story-row-classification.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['path','member','kind','id','category','ko_signature'])
        writer.writeheader()
        writer.writerows(row_inventory)
    (ROOT/'artifacts/story-preservation-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary), flush=True)
    release.close()


if __name__ == '__main__':
    run(sys.argv[1])

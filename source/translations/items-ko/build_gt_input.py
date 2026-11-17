"""아이템 표시 필드를 추출하고 기존 번역·신규 GalTransl 입력을 고정한다."""
import hashlib
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import item_common as C


def main():
    tables = C.load_tables()
    refs = C.references(tables)
    known = C.N.name_sources()[0]
    for path in sorted((C.ROOT / 'translations/names-ko').glob('names_pass[0-9].json')):
        for jp, ko in C.read(path).items():
            known.setdefault(jp, ko)
    equip = C.N.equipment_names()
    records, locations, reused, counts = {}, [], {}, {}
    for table, (idfield, fields) in C.SPECS.items():
        src, key, rows = tables[table]
        counts[table] = {'file': src.name, 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
                         'rows': len(rows), 'target_fields': 0}
        for index, row in enumerate(rows):
            rowid = str(row[idfield])
            if table in refs and rowid not in refs[table]:
                continue
            for field in fields:
                original = row.get(field, '')
                if not isinstance(original, str) or not C.N.LEFT_JP.search(original):
                    continue
                source = row.get('G4L0YIB2', original) if field == 'cnLF6Cz1' else original
                source_id = C.rid(source)
                loc = {'table': table, 'row': index, 'id': rowid, 'field': field,
                       'source': original, 'translation_id': source_id}
                locations.append(loc)
                counts[table]['target_fields'] += 1
                ko = equip.get(rowid) if table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST') and field in ('G4L0YIB2','cnLF6Cz1') else None
                ko = ko or known.get(source)
                if ko and C.N.HANGUL.search(ko) and not C.N.LEFT_JP.search(ko):
                    reused[source_id] = ko
                if source_id not in records:
                    message, tokens = C.protect(source)
                    records[source_id] = {'ffbe_id': source_id, 'source': source, 'message': message,
                                          'tokens': tokens, 'category': table}
    needed = [v for k,v in records.items() if k not in reused]
    # 파일당 최대 80문구, 긴 설명도 처리할 수 있게 문자 수 8천에서 분할.
    batches, batch, chars = [], [], 0
    for value in needed:
        if batch and (len(batch) >= 80 or chars + len(value['message']) > 8000):
            batches.append(batch); batch, chars = [], 0
        batch.append({'ffbe_id': value['ffbe_id'], 'name': '', 'message': value['message']})
        chars += len(value['message'])
    if batch: batches.append(batch)
    for index, batch in enumerate(batches):
        C.write_checked(C.PROJECT / 'gt_input' / f'items_{index:03}.json', batch)
    manifest = {'tables': counts, 'references': {k: sorted(v) for k,v in refs.items()},
                'locations': locations, 'records': list(records.values()), 'reused': reused,
                'unique_total': len(records), 'unique_new': len(needed),
                'new_characters': sum(len(v['source']) for v in needed), 'files': len(batches)}
    C.write_checked(C.HERE / 'manifest.json', manifest)
    src = C.ROOT / 'build/out/story_gap_gt'
    if not (C.PROJECT/'config.yaml').exists():
        shutil.copyfile(src/'config.yaml', C.PROJECT/'config.yaml')
    if not (C.PROJECT/'Dict').exists():
        shutil.copytree(src/'Dict', C.PROJECT/'Dict')
        # 이름 번역의 확인된 용어를 기존 용어집 뒤에 추가.
        with (C.PROJECT/'Dict/gpt_dict.txt').open('a',encoding='utf-8') as out:
            item_terms = {records[k]['source']: ko for k,ko in reused.items()}
            for jp,ko in sorted(item_terms.items()):
                if len(jp) < 40 and all(x not in jp+ko for x in ('\n','\t','<')):
                    out.write(f'\n{jp}\t{ko}')
    if not (C.PROJECT/'name替换表.csv').exists():
        shutil.copyfile(C.ROOT/'translations/story-gap-ko/name替换表.csv', C.PROJECT/'name替换表.csv')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('tables','locations','records','reused','references')},ensure_ascii=False))
    for table,counts in counts_by_table(manifest).items(): print(table,counts)


def counts_by_table(manifest):
    return {k: v['target_fields'] for k,v in manifest['tables'].items()}


if __name__ == '__main__': main()

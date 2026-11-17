"""Read all effective release CPKs and inventory localized text without changing data."""
import collections
import io
import json
import re
import struct
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'analysis/vendor'))
from cricodecs import cpk
from inspect_cpk import utf_table

LANGUAGES = ('EN', 'ZH', 'KO', 'FR', 'DE', 'ES', 'TH', 'ID')
TAG = re.compile(r'<[^>]*>')


def load_archive(payload):
    try:
        archive = cpk.load(payload)
        # Filename properties themselves are decoded lazily in CriCodecs.
        for member in archive.file_infos():
            member.full_path
        return archive, False
    except (RuntimeError, ValueError):
        # Some TOC filenames contain bytes Windows cannot map. Mask only
        # non-ASCII metadata string bytes in a temporary copy, never member data.
        header = utf_table(payload, 16)[0]
        copy = bytearray(payload)
        for offset in [0] + [header.get(key, 0) for key in
                              ('TocOffset', 'EtocOffset', 'ItocOffset', 'GtocOffset')]:
            position = offset + 16
            if payload[position:position + 4] != b'@UTF':
                continue
            _, strings, binary = struct.unpack_from('>III', payload, position + 8)
            start, end = position + 8 + strings, position + 8 + binary
            if not position <= start <= end <= len(payload):
                raise ValueError('Invalid metadata string bounds')
            for index in range(start, end):
                if copy[index] > 127:
                    copy[index] = 95
        return cpk.load(bytes(copy)), True


def stats(rows, index):
    out = collections.Counter()
    for row in rows:
        out['rows'] += 1
        if len(row) <= index:
            out['column_absent'] += 1
            continue
        text = TAG.sub('', row[index]).strip()
        english = TAG.sub('', row[1]).strip() if len(row) > 1 else ''
        if not text:
            out['blank_after_tags'] += 1
            continue
        out['nonblank_after_tags'] += 1
        out['same_display_as_english' if text == english else 'different_display_from_english'] += 1
        hangul = any('\uac00' <= c <= '\ud7a3' for c in text)
        kana = any('\u3040' <= c <= '\u30ff' for c in text)
        cjk = any('\u3400' <= c <= '\u9fff' for c in text)
        thai = any('\u0e00' <= c <= '\u0e7f' for c in text)
        out['hangul_rows'] += hangul
        out['kana_rows'] += kana
        out['cjk_rows'] += cjk
        out['thai_rows'] += thai
        if not (hangul or kana or cjk or thai):
            out['latin_or_other_script_rows'] += bool(re.search(r'[A-Za-z\u00c0-\u024f]', text))
            out['numbers_symbols_only_rows'] += not bool(re.search(r'[^\W\d_]', text, re.UNICODE))
    return dict(out)


def run(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    verified = json.loads((folder / 'verification.json').read_text())
    if len(verified) != len(manifest['packs']) or not all(row['verified'] for row in verified):
        raise ValueError('Complete verified download required')
    archives = {}
    effective = {}
    overrides = []
    for pack in manifest['packs']:
        name = pack['url'].rsplit('/', 1)[-1]
        archive = zipfile.ZipFile(folder / name)
        archives[pack['id']] = archive
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            if entry.filename in effective:
                overrides.append(entry.filename)
            effective[entry.filename] = (pack['id'], entry)
    targets = [(name, pack, entry) for name, (pack, entry) in effective.items()
               if name.startswith('native/') and name.lower().endswith('.cpk')]
    results = []
    errors = []
    aggregate = {lang: collections.Counter() for lang in LANGUAGES}
    general_texts = []
    started = time.monotonic()
    last_report = started
    for number, (name, pack, entry) in enumerate(targets, 1):
        record = {'path': name, 'pack': pack, 'localized_tables': [], 'text_members': 0}
        try:
            payload = archives[pack].read(entry)  # zipfile checks each ZIP member CRC
            archive, masked = load_archive(payload)
            record['metadata_filename_masked_in_memory'] = masked
            for index, member in enumerate(archive.file_infos()):
                filename = member.full_path
                if not filename.lower().endswith('.txt'):
                    continue
                record['text_members'] += 1
                try:
                    raw = archive.file_bytes(index)
                    try:
                        text = raw.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        if filename.endswith('_sg.txt'):
                            raise
                        text = raw.decode('cp932')
                        record.setdefault('cp932_text_members', []).append(filename)
                except Exception as error:
                    errors.append({'cpk': name, 'member': filename, 'stage': 'text_decode',
                                   'error': type(error).__name__ + ': ' + str(error)[:200]})
                    continue
                if not filename.endswith('_sg.txt'):
                    if any('\uac00' <= c <= '\ud7a3' for c in TAG.sub('', text)):
                        general_texts.append({'cpk': name, 'member': filename,
                                              'hangul_lines': sum(any('\uac00' <= c <= '\ud7a3' for c in line)
                                                                  for line in TAG.sub('', text).splitlines())})
                    continue
                rows = [line.split('^') for line in text.splitlines() if line]
                table = {'member': filename, 'rows': len(rows),
                         'field_counts': dict(collections.Counter(map(len, rows))), 'languages': {}}
                for column, lang in enumerate(LANGUAGES, 1):
                    metrics = stats(rows, column)
                    table['languages'][lang] = metrics
                    aggregate[lang].update(metrics)
                record['localized_tables'].append(table)
        except Exception as error:
            errors.append({'cpk': name, 'stage': 'cpk_load',
                           'error': type(error).__name__ + ': ' + str(error)[:200]})
        results.append(record)
        now = time.monotonic()
        if now - last_report >= 15 or number == len(targets):
            print(json.dumps({'event': 'audit_progress', 'cpks_read': number, 'total': len(targets),
                              'errors': len(errors), 'hangul_rows': aggregate['KO']['hangul_rows'],
                              'elapsed_seconds': round(now - started)}), flush=True)
            last_report = now
    decoded = []
    for name, (pack, entry) in effective.items():
        if not name.startswith('static/text_decoded/') or not name.endswith('.ndjson'):
            continue
        raw = archives[pack].read(entry)
        records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line]
        decoded.append({'path': name, 'rows': len(records),
                        'hangul_rows': sum(any('\uac00' <= c <= '\ud7a3' for c in json.dumps(row, ensure_ascii=False))
                                           for row in records)})
    startup = []
    for name, (pack, entry) in effective.items():
        if name.endswith('game-assets.apk'):
            with zipfile.ZipFile(io.BytesIO(archives[pack].read(entry))) as assets:
                for filename in assets.namelist():
                    if filename.startswith('assets/localized_texts/') and filename.endswith('.csv'):
                        text = assets.read(filename).decode('utf-8-sig')
                        startup.append({'path': filename, 'rows': len(text.splitlines()),
                                        'hangul_lines': sum(any('\uac00' <= c <= '\ud7a3' for c in line)
                                                            for line in text.splitlines())})
    with_korean = [r for r in results if any(t['languages']['KO'].get('hangul_rows', 0)
                                             for t in r['localized_tables'])]
    with_tables = [r for r in results if r['localized_tables']]
    summary = {'version': manifest['version'], 'packs_verified': len(verified),
               'effective_files': len(effective), 'overridden_paths': len(set(overrides)),
               'cpks_inspected': len(results), 'cpks_with_localized_tables': len(with_tables),
               'metadata_filename_recoveries': sum(r.get('metadata_filename_masked_in_memory', False) for r in results),
               'cpks_with_korean_hangul': len(with_korean),
               'localized_tables': sum(len(r['localized_tables']) for r in results),
               'localized_rows': aggregate['EN']['rows'], 'language_counts': {k: dict(v) for k, v in aggregate.items()},
               'errors': len(errors), 'decoded_tables': len(decoded),
               'decoded_rows': sum(r['rows'] for r in decoded),
               'decoded_hangul_rows': sum(r['hangul_rows'] for r in decoded),
               'startup_tables': startup,
               'limitations': 'Scanned all effective native CPKs, their UTF-8 .txt members, decoded engine tables and startup language CSVs. Equal English names/numbers are not classified as missing translations. Images, encrypted native text originals and text embedded in other binary formats are not linguistically decoded.'}
    output = {'summary': summary, 'packages': results, 'errors': errors,
              'other_text_members_with_hangul': general_texts, 'decoded_tables': decoded}
    (ROOT / 'artifacts/complete-language-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'artifacts/complete-language-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'event': 'audit_complete', **{k: v for k, v in summary.items()
                                                   if k not in ('language_counts', 'startup_tables', 'limitations')}}), flush=True)
    for archive in archives.values():
        archive.close()


if __name__ == '__main__':
    run(Path(sys.argv[1]))

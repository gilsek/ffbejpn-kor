"""Read-only, bounded CPK sampling from existing release ZIP indexes."""
import binascii
import concurrent.futures
import json
import struct
import sys
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'analysis/vendor'))
from cricodecs import cpk

LANGUAGES = ('EN', 'ZH', 'KO', 'FR', 'DE', 'ES', 'TH', 'ID')


def inspect(path):
    archive = cpk.load(str(path))
    result = []
    for i, entry in enumerate(archive.file_infos()):
        if not entry.full_path.endswith('_sg.txt'):
            continue
        raw = archive.file_bytes(i)
        rows = [line.split('^') for line in raw.decode('utf-8-sig').splitlines() if line]
        columns = {}
        for j, lang in enumerate(LANGUAGES, 1):
            cells = [(row[j] if len(row) > j else '') for row in rows]
            columns[lang] = {
                'nonblank': sum(bool(cell.strip()) for cell in cells),
                'different_from_english': sum(bool(cell.strip()) and len(row) > 1 and cell != row[1]
                                               for cell, row in zip(cells, rows)),
                'hangul_rows': sum(any('\uac00' <= c <= '\ud7a3' for c in cell) for cell in cells),
            }
        result.append({'member': entry.full_path, 'rows': len(rows), 'columns': columns})
    return {'path': path.name, 'members': result}


def request_range(url, start, end):
    request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 206:
            raise ValueError('Server did not honor bounded Range request')
        data = response.read(end - start + 1)
        if len(data) != end - start + 1:
            raise ValueError('Truncated Range response')
        return data


def fetch(item):
    row, url = item
    target = ROOT / 'artifacts/language-samples' / Path(row['name']).name
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        if target.stat().st_size != row['size']:
            raise ValueError('Cached sample size mismatch')
        return target, row['name'], 0
    offset = row['offset']
    header = struct.unpack('<4s5H3I2H', request_range(url, offset, offset + 29))
    start = offset + 30 + header[9] + header[10]
    packed = request_range(url, start, start + row['compressed'] - 1)
    raw = zlib.decompress(packed, -15) if row['method'] == 8 else packed
    if len(raw) != row['size'] or binascii.crc32(raw) != header[6]:
        raise ValueError('ZIP member size/CRC32 mismatch')
    target.write_bytes(raw)
    return target, row['name'], 30 + len(packed)


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'upstream/data/latest.json').read_text())
    urls = {p['id']: p['url'] for p in manifest['packs']}
    candidates = []
    for index in sorted((ROOT / 'artifacts').glob('data-*-index.json')):
        for row in json.loads(index.read_text()):
            candidates.append((row, urls[index.name.removesuffix('-index.json')]))
    selected = []
    for group, limit, max_size in (('event', 20, 1500000), ('map', 8, 5000000)):
        pool = sorted([item for item in candidates if
                       item[0]['name'].startswith(f'native/common_lang/sd/{group}/') and
                       item[0]['name'].endswith('.cpk') and item[0]['size'] <= max_size],
                      key=lambda item: item[0]['name'])
        indexes = sorted(set(i * (len(pool) - 1) // (limit - 1) for i in range(limit)))
        selected.extend(pool[i] for i in indexes)
    results = []
    received = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for path, name, count in executor.map(fetch, selected):
            result = inspect(path)
            result['release_path'] = name
            results.append(result)
            received += count
            print(json.dumps({'file': path.name, 'tables': len(result['members']),
                              'korean_rows': sum(t['columns']['KO']['hangul_rows'] for t in result['members'])}), flush=True)
    for name in ('Ver48_111020100.cpk', 'Ver53_111010101.cpk'):
        results.append(inspect(ROOT / 'artifacts' / name))
    output = {'method': '20 event + 8 map CPKs spaced across sorted eligible release paths, plus two previously inspected files; not random or exhaustive.',
              'new_download_bytes': received, 'packages': len(results), 'results': results}
    (ROOT / 'artifacts/expanded-language-analysis.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print('COMPLETE', len(results), 'packages; downloaded', received, 'bytes')

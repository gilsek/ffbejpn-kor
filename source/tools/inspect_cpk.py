"""Read-only inspection of plain CRI CPK localized story tables (no dependencies)."""
import hashlib
import json
import struct
import sys
from pathlib import Path


def utf_table(data, offset):
    if data[offset:offset + 4] != b'@UTF':
        raise ValueError('Expected an unencrypted @UTF table')
    rows_at, strings_at, binary_at = struct.unpack_from('>III', data, offset + 8)
    columns, row_size, row_count = struct.unpack_from('>HHI', data, offset + 24)
    base = offset + 8

    def string(index):
        start = base + strings_at + index
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
        raise ValueError(f'Unsupported UTF type: {kind}')

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
            raise ValueError(f'Unsupported UTF storage: {storage}')
        schema.append((string(name), storage, kind, constant))

    rows = []
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
        rows.append(row)
    return rows


def inspect(path):
    data = path.read_bytes()
    if data[:4] != b'CPK ':
        raise ValueError('Expected CPK archive')
    header = utf_table(data, 16)[0]
    toc_at = header['TocOffset']
    base = min(toc_at, header['ContentOffset'])
    summaries = []
    for row in utf_table(data, toc_at + 16):
        name = row['FileName']
        if not name.endswith('_sg.txt'):
            continue
        start = base + row['FileOffset']
        body = data[start:start + row['FileSize']]
        if len(body) != row['FileSize']:
            raise ValueError('Truncated CPK member')
        if row['FileSize'] != row['ExtractSize'] or body.startswith(b'CRILAYLA'):
            summaries.append({'member': name, 'status': 'compressed; not inspected'})
            continue
        lines = [line.split('^') for line in body.decode('utf-8-sig').splitlines() if line]
        columns = []
        for index, lang in enumerate(('EN', 'ZH', 'KO', 'FR', 'DE', 'ES', 'TH', 'ID'), 1):
            cells = [line[index] if index < len(line) else '' for line in lines]
            columns.append({
                'language': lang,
                'nonblank_rows': sum(bool(cell.strip()) for cell in cells),
                'rows_containing_hangul': sum(any('\uac00' <= char <= '\ud7a3' for char in cell) for cell in cells),
                'rows_equal_to_english': sum(bool(cell.strip()) and cell == line[1]
                                             for cell, line in zip(cells, lines) if len(line) > 1),
            })
        summaries.append({'member': name, 'rows': len(lines),
                          'field_counts': sorted(set(map(len, lines))), 'columns': columns})
    return {'archive': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
            'language_order_source': 'upstream/source/exvius/fill_content_from_memorial.py',
            'localized_members': summaries}


if __name__ == '__main__':
    print(json.dumps(inspect(Path(sys.argv[1])), ensure_ascii=False, indent=2))

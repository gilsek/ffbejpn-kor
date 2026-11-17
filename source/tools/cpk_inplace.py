"""Replace files inside a CRI CPK without rebuilding it.

The game breaks on a fully rebuilt CPK (cricodecs `cpk.create`): file IDs are renumbered and the GTOC group
file list (Fdata) is dropped, and dialog/window panels stop rendering (2026-11-09). This keeps the original
header/TOC/ETOC/GTOC layout and only appends the new file bodies at the end, pointing the TOC rows at them.
File/TOC CRC checks are switched off in the header (CRI's CRC algorithm is not zlib crc32).
"""
import struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from cricodecs import utf  # noqa: E402


def _crypt(b):
    m, o = 0x655f, bytearray(b)
    for i in range(len(o)):
        o[i] ^= m & 0xff
        m = (m * 0x4115) & 0xffffffff
    return bytes(o)


def _table(d, off):
    size = struct.unpack_from('<Q', d, off + 8)[0]
    raw = bytes(d[off + 16:off + 16 + size])
    enc = raw[:4] != b'@UTF'
    return utf.Utf.load_bytes(_crypt(raw) if enc else raw), size, enc


def _put(d, off, slot, t, enc):
    raw = t.build()
    raw = _crypt(raw) if enc else raw
    if len(raw) > slot:
        raise ValueError(f'table at {off} grew {len(raw)} > {slot}')
    d[off + 8:off + 16] = struct.pack('<Q', len(raw))
    d[off + 16:off + 16 + slot] = raw + b'\0' * (slot - len(raw))


def patch(orig: bytes, replace: dict, encoding='cp932') -> bytes:
    """replace: {'dir/name.ext': new bytes}. Returns the new CPK bytes."""
    d = bytearray(orig)
    hdr, hsize, henc = _table(d, 0)
    toc_off = hdr.value(0, 'TocOffset')
    align = hdr.value(0, 'Align') or 2048
    toc, tsize, tenc = _table(d, toc_off)
    rows = {}
    for r in range(toc.row_count):
        dn, fn = toc.string_raw(r, 'DirName'), toc.string_raw(r, 'FileName')
        path = (dn.decode(encoding) + '/' if dn else '') + fn.decode(encoding)
        rows[path] = r
    missing = [p for p in replace if p not in rows]
    if missing:
        raise KeyError(f'not in CPK: {missing[:5]}')
    for path, data in replace.items():
        pad = (-len(d)) % align
        d += b'\0' * pad
        pos = len(d)
        d += data
        r = rows[path]
        toc.set(r, 'FileOffset', pos - toc_off)
        toc.set(r, 'FileSize', len(data))
        toc.set(r, 'ExtractSize', len(data))
    d += b'\0' * ((-len(d)) % align)
    content_off = hdr.value(0, 'ContentOffset')
    hdr.set(0, 'ContentSize', len(d) - content_off)
    for col in ('EnableFileCrc', 'EnableTocCrc'):
        if hdr.find_column(col) >= 0:
            hdr.set(0, col, 0)
    _put(d, toc_off, tsize, toc, tenc)
    _put(d, 0, hsize, hdr, henc)
    return bytes(d)

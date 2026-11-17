"""List/extract a plain CRI CPK (read-only analysis). usage: list_cpk.py cpk [outdir]"""
import sys, struct, collections
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from inspect_cpk import utf_table
p = Path(sys.argv[1]); out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
data = p.read_bytes()
def unmask(buf, off):
    size = struct.unpack_from('<Q', buf, off + 8)[0]
    if buf[off + 16:off + 20] == b'@UTF': return
    m, t = 0x655f, 0x4115; b = bytearray(buf)
    for i in range(off + 16, off + 16 + size):
        b[i] ^= m & 0xff; m = (m * t) & 0xffff
    buf[:] = b
data = bytearray(data)
unmask(data, 0)
hdr = utf_table(data, 16)[0]
toc = hdr['TocOffset']; base = min(toc, hdr['ContentOffset'])
unmask(data, toc)
rows = utf_table(data, toc + 16)
print('files', len(rows), 'cols', list(rows[0].keys()))
kinds = collections.Counter(); tot = 0; comp = 0
for r in rows:
    s = base + r['FileOffset']; body = data[s:s + r['FileSize']]
    c = body[:8] == b'CRILAYLA' or r['FileSize'] != r['ExtractSize']
    comp += c; tot += r['ExtractSize']
    ext = Path(r['FileName']).suffix.lower(); kinds[(ext, c)] += 1
    r['_c'] = c; r['_body'] = body
print('compressed', comp, 'extract bytes', tot); print(sorted(kinds.items(), key=lambda x: -x[1]))
if out:
    for r in rows:
        d = out / r.get('DirName', '') / r['FileName']; d.parent.mkdir(parents=True, exist_ok=True); d.write_bytes(r['_body'])
for r in rows[:40]: print(r.get('DirName'), r['FileName'], r['FileSize'], r['ExtractSize'], r['_c'], r['_body'][:8])

"""Minimal read-only DEX parser: class list + method ids (class, name, proto)."""
import struct, sys
def mutf8(d, off):
    while d[off] & 0x80: off += 1   # uleb128 length
    off += 1; e = d.index(0, off); return d[off:e].decode('utf-8', 'replace')
def parse(path):
    d = open(path, 'rb').read()
    sz, = struct.unpack_from('<I', d, 0x38); so, = struct.unpack_from('<I', d, 0x3c)
    strs = [mutf8(d, struct.unpack_from('<I', d, so + 4*i)[0]) for i in range(sz)]
    tn, to = struct.unpack_from('<II', d, 0x40); types = [strs[struct.unpack_from('<I', d, to + 4*i)[0]] for i in range(tn)]
    pn, po = struct.unpack_from('<II', d, 0x48)
    protos = []
    for i in range(pn):
        sh, rt, pa = struct.unpack_from('<III', d, po + 12*i)
        params = []
        if pa:
            n, = struct.unpack_from('<I', d, pa); params = [types[struct.unpack_from('<H', d, pa + 4 + 2*j)[0]] for j in range(n)]
        protos.append(types[rt] + '(' + ''.join(params) + ')')
    mn, mo = struct.unpack_from('<II', d, 0x58)
    methods = []
    for i in range(mn):
        c, p, n = struct.unpack_from('<HHI', d, mo + 8*i); methods.append((types[c], strs[n], protos[p]))
    cn, co = struct.unpack_from('<II', d, 0x60)
    classes = [types[struct.unpack_from('<I', d, co + 32*i)[0]] for i in range(cn)]
    return classes, methods, strs

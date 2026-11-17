"""Re-package a (split) APK under a new applicationId so it installs beside the original.

Patches binary AndroidManifest.xml string pool (package attr, custom permission, provider authorities) and the
ResTable package name in resources.arsc, then writes an unsigned zip (zipalign + apksigner done by the caller).
Class names inside the manifest are left alone: the dex classes keep their original package.
usage: rename_package.py <in.apk> <out.apk> <old.pkg> <new.pkg> [versionCode]   (new must be the same length as old)
"""
import struct, sys, zipfile

RENAME_SUFFIXES = ('.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION', '.firebaseinitprovider',
                   '.mobileadsinitprovider', '.androidx-startup')

def read_pool(d, off):
    typ, hsz, size, nstr, nsty, flags, sstart, ststart = struct.unpack_from('<HHIIIIII', d, off)
    assert typ == 1 and nsty == 0
    utf8 = bool(flags & 0x100); offs = struct.unpack_from('<%dI' % nstr, d, off + hsz)
    strs = []
    for o in offs:
        p = off + sstart + o
        if utf8:
            c = d[p]; p += 2 if c & 0x80 else 1            # char count (unused)
            l = d[p]
            if l & 0x80: ln = ((l & 0x7f) << 8) | d[p + 1]; p += 2
            else: ln = l; p += 1
            strs.append(d[p:p + ln].decode('utf-8'))
        else:
            n = struct.unpack_from('<H', d, p)[0]; p += 2
            if n & 0x8000: n = ((n & 0x7fff) << 16) | struct.unpack_from('<H', d, p)[0]; p += 2
            strs.append(d[p:p + n * 2].decode('utf-16-le'))
    return strs, utf8, size

def write_pool(strs, utf8):
    body = bytearray(); offs = []
    for s in strs:
        offs.append(len(body))
        if utf8:
            b = s.encode('utf-8'); n = len(s)
            body += (bytes([n]) if n < 128 else bytes([0x80 | n >> 8, n & 0xff]))
            body += (bytes([len(b)]) if len(b) < 128 else bytes([0x80 | len(b) >> 8, len(b) & 0xff])) + b + b'\0'
        else:
            n = len(s); body += struct.pack('<H', n) + s.encode('utf-16-le') + b'\0\0'
    while len(body) % 4: body += b'\0'
    hsz = 28; sstart = hsz + 4 * len(strs)
    return struct.pack('<HHIIIIII', 1, hsz, sstart + len(body), len(strs), 0, 0x100 if utf8 else 0, sstart, 0) + b''.join(struct.pack('<I', o) for o in offs) + bytes(body)

def patch_manifest(d, old, new):
    assert struct.unpack_from('<HH', d, 0) == (3, 8)
    pool_off = 8; strs, utf8, psize = read_pool(d, pool_off)
    changed = 0
    for i, s in enumerate(strs):
        if s == old or (s.startswith(old) and s[len(old):] in RENAME_SUFFIXES):
            strs[i] = new + s[len(old):]; changed += 1
    out = write_pool(strs, utf8)
    res = d[:pool_off] + out + d[pool_off + psize:]
    res = res[:4] + struct.pack('<I', len(res)) + res[8:]
    return res, changed

def patch_arsc(d, old, new):
    o16, n16 = old.encode('utf-16-le'), new.encode('utf-16-le')
    assert len(o16) == len(n16)
    return d.replace(o16 + b'\0\0', n16 + b'\0\0', 1), d.count(o16)

def set_version_code(d, code):
    """Set <manifest android:versionCode> in a binary AndroidManifest.xml (splits must match the base)."""
    strs, _, psize = read_pool(d, 8)
    names = {i for i, s in enumerate(strs) if s == 'versionCode'}
    manifest = {i for i, s in enumerate(strs) if s == 'manifest'}
    off, changed = 8, 0
    while off < len(d):
        typ, hsz, size = struct.unpack_from('<HHI', d, off)
        if typ == 0x0102:
            name = struct.unpack_from('<I', d, off + 20)[0]
            attr_start, attr_size, attr_count = struct.unpack_from('<HHH', d, off + 24)
            if name in manifest:
                for k in range(attr_count):
                    a = off + 16 + attr_start + k * attr_size
                    if struct.unpack_from('<I', d, a + 4)[0] in names:
                        d = d[:a + 16] + struct.pack('<I', code) + d[a + 20:]; changed += 1
        off += size
    assert changed == 1, 'versionCode attribute not found exactly once'
    return d

def get_version_code(d):
    strs, _, _ = read_pool(d, 8)
    names = {i for i, s in enumerate(strs) if s == 'versionCode'}
    off = 8
    while off < len(d):
        typ, hsz, size = struct.unpack_from('<HHI', d, off)
        if typ == 0x0102:
            attr_start, attr_size, attr_count = struct.unpack_from('<HHH', d, off + 24)
            for k in range(attr_count):
                a = off + 16 + attr_start + k * attr_size
                if struct.unpack_from('<I', d, a + 4)[0] in names:
                    return struct.unpack_from('<I', d, a + 16)[0]
            return None   # only the root <manifest> element carries it
        off += size
    return None

if __name__ == '__main__':
    src, dst, old, new = sys.argv[1:5]; assert len(old) == len(new)
    version_code = int(sys.argv[5]) if len(sys.argv) > 5 else None
    zin = zipfile.ZipFile(src); zout = zipfile.ZipFile(dst, 'w')
    for i in zin.infolist():
        if i.filename.startswith('META-INF/') and i.filename.rsplit('.', 1)[-1] in ('SF', 'RSA', 'DSA', 'MF', 'EC'): continue
        data = zin.read(i.filename)
        if i.filename == 'AndroidManifest.xml':
            data, c = patch_manifest(data, old, new); print(src, 'manifest strings changed', c)
            if version_code is not None: data = set_version_code(data, version_code)
        elif i.filename == 'resources.arsc':
            data, c = patch_arsc(data, old, new); print(src, 'arsc package occurrences', c)
        zi = zipfile.ZipInfo(i.filename, i.date_time); zi.compress_type = zipfile.ZIP_STORED if i.filename == 'resources.arsc' or i.compress_type == 0 else zipfile.ZIP_DEFLATED
        zi.external_attr = i.external_attr; zout.writestr(zi, data)
    zout.close()

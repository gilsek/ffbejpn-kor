"""Verify a local copy of archive.org item ffbejpdata against ffbejpdata_files.xml (size always, md5 with --md5)."""
import sys, os, hashlib, xml.etree.ElementTree as ET
root = sys.argv[1]; do_md5 = '--md5' in sys.argv
tree = ET.parse(os.path.join(root, 'ffbejpdata_files.xml'))
exp = {}
for f in tree.getroot().findall('file'):
    if f.get('source') != 'original': continue
    exp[f.get('name')] = (int(f.findtext('size') or -1), (f.findtext('md5') or '').lower())
print('expected original files:', len(exp), 'total GB', round(sum(v[0] for v in exp.values())/1e9, 2))
missing, wrong, ok, ok_bytes = [], [], 0, 0
local = set()
for dp, _, fs in os.walk(root):
    for n in fs: local.add(os.path.relpath(os.path.join(dp, n), root).replace(chr(92), '/'))
for n, (sz, md5) in sorted(exp.items()):
    p = os.path.join(root, n)
    if not os.path.exists(p): missing.append(n); continue
    if os.path.getsize(p) != sz: wrong.append((n, os.path.getsize(p), sz)); continue
    if do_md5:
        h = hashlib.md5()
        with open(p, 'rb') as fh:
            for b in iter(lambda: fh.read(1 << 22), b''): h.update(b)
        if md5 and h.hexdigest() != md5: wrong.append((n, 'md5', h.hexdigest(), md5)); continue
    ok += 1; ok_bytes += sz
extra = sorted(local - set(exp))
print('ok', ok, 'GB', round(ok_bytes/1e9, 2), '| missing', len(missing), '| size/md5 mismatch', len(wrong), '| extra(local only)', len(extra))
print('missing sample', missing[:15]); print('wrong sample', wrong[:10]); print('extra sample', extra[:15])

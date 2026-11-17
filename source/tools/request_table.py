"""Extract per-request wire parameters (request id, EncodeKey, url) from libgame.so getters (no execution)."""
import re, struct, zipfile, json, sys
from pathlib import Path
def table(native):
    so, = struct.unpack_from('<Q', native, 40); ss, sc = struct.unpack_from('<HH', native, 58)
    secs = [struct.unpack_from('<IIQQQQIIQQ', native, so + i*ss) for i in range(sc)]
    def foff(a):
        for s in secs:
            if s[3] <= a < s[3] + s[5] and s[1] != 8: return s[4] + a - s[3]
        raise ValueError
    def getter(addr):
        p = foff(addr); adrp, add, ret = struct.unpack_from('<III', native, p)
        if adrp & 0x9f00001f != 0x90000000 or add & 0xffc003ff != 0x91000000 or ret != 0xd65f03c0: raise ValueError
        imm = ((adrp >> 5) & 0x7ffff) << 2 | (adrp >> 29) & 3
        if imm & (1 << 20): imm -= 1 << 21
        t = foff((addr & ~0xfff) + (imm << 12) + ((add >> 10) & 0xfff)); return native[t:native.index(0, t, t+200)].decode()
    out = {}; pat = re.compile(r'_ZNK?\d+([A-Za-z0-9]+?Request)\d+(getEncodeKey|getRequestID|getUrl)Ev$')
    for s in secs:
        if s[1] != 11: continue
        pool = native[secs[s[6]][4]:secs[s[6]][4] + secs[s[6]][5]]
        for p in range(s[4], s[4] + s[5], s[9]):
            no, info, other, idx, addr, size = struct.unpack_from('<IBBHQQ', native, p)
            if not idx: continue
            name = pool[no:pool.index(0, no)].decode('ascii', 'replace'); m = pat.match(name)
            if not m: continue
            try: out.setdefault(m[1], {})[m[2]] = getter(addr)
            except (ValueError, UnicodeError): pass
    return out
if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    n11 = (root/'inputs/jp1100/arm64/lib/arm64-v8a/libgame.so').read_bytes()
    n9 = zipfile.ZipFile(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix\downloads\FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
    t9, t11 = table(n9), table(n11)
    json.dump({'g900': t9, 'jp1100': t11}, open(root/'translations/reports/request_tables.json', 'w'), indent=1)
    sys.stdout.reconfigure(encoding='utf-8')
    gt = json.load(open(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix\upstream\source\server\endpoints.json'))['by_class']
    ok = sum(1 for k, v in t9.items() if k in gt and gt[k]['encode_key'] == v.get('getEncodeKey') and gt[k]['request_id'] == v.get('getRequestID') and gt[k]['url'].endswith(v.get('getUrl', '?') + '.php') or (k in gt and gt[k]['url'] == v.get('getUrl')))
    print('9.0.0 classes', len(t9), 'matching server endpoints.json', ok, 'of', len(gt))
    both = set(t9) & set(t11); same = [k for k in both if t9[k] == t11[k]]
    print('11.0.0 classes', len(t11), 'common', len(both), 'identical triple', len(same), 'differ', len(both) - len(same), 'only in 11', len(set(t11) - set(t9)), 'only in 9', len(set(t9) - set(t11)))
    print('differ sample', [(k, t9[k], t11[k]) for k in both if t9[k] != t11[k]][:3])
    print('only11', sorted(set(t11) - set(t9))[:30])

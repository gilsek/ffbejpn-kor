"""ARM64 xrefs: who BL/B's the given mangled symbols (and which function contains each call). usage: xref.py libgame.so sym..."""
import sys, struct, bisect
from elftools.elf.elffile import ELFFile
sys.stdout.reconfigure(encoding='utf-8')
f = ELFFile(open(sys.argv[1], 'rb'))
syms = {}
for secname in ('.dynsym', '.symtab'):
    s = f.get_section_by_name(secname)
    if s:
        for y in s.iter_symbols():
            if y['st_value'] and y['st_info']['type'] == 'STT_FUNC': syms[y.name] = (y['st_value'], y['st_size'])
starts = sorted((v[0], k) for k, v in syms.items())
addrs = [a for a, _ in starts]
text = f.get_section_by_name('.text'); data = text.data(); base = text['sh_addr']
want = {}
for n in sys.argv[2:]:
    c = [k for k in syms if n in k]
    for k in c: want[syms[k][0]] = k
print('targets:', list(want.values()))
for i in range(0, len(data) - 3, 4):
    w = struct.unpack_from('<I', data, i)[0]
    if (w & 0x7c000000) == 0x14000000:
        imm = w & 0x3ffffff
        if imm & 0x2000000: imm -= 1 << 26
        t = base + i + imm * 4
        if t in want:
            a = base + i; j = bisect.bisect_right(addrs, a) - 1
            print(hex(a), 'BL' if w >> 31 else 'B', '->', want[t][:60], '| in', starts[j][1][:100], hex(starts[j][0]))

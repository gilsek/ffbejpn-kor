"""Find code that materializes the address of a C string (ADRP+ADD) in libgame.so and name the containing function. usage: strxref.py so string"""
import sys, struct, bisect
from elftools.elf.elffile import ELFFile
sys.stdout.reconfigure(encoding='utf-8')
fh = open(sys.argv[1], 'rb'); raw = fh.read(); fh.seek(0); f = ELFFile(fh)
needle = sys.argv[2].encode() + b'\0'
targets = []
for s in f.iter_sections():
    if s['sh_type'] != 'SHT_PROGBITS' or not s['sh_addr'] or s.name in ('.text','.plt'): continue
    d = s.data(); i = d.find(needle)
    while i >= 0:
        if i == 0 or d[i-1] == 0: targets.append(s['sh_addr'] + i)
        i = d.find(needle, i + 1)
print('string addrs', [hex(t) for t in targets])
syms = []
for secname in ('.symtab', '.dynsym'):
    s = f.get_section_by_name(secname)
    if s: syms += [(y['st_value'], y.name) for y in s.iter_symbols() if y['st_value'] and y['st_info']['type'] == 'STT_FUNC']
syms.sort(); addrs = [a for a, _ in syms]
text = f.get_section_by_name('.text'); d = text.data(); base = text['sh_addr']
tset = set(targets)
for i in range(0, len(d) - 7, 4):
    w = struct.unpack_from('<I', d, i)[0]
    if w & 0x9f000000 != 0x90000000: continue
    rd = w & 31; imm = ((w >> 5) & 0x7ffff) << 2 | (w >> 29) & 3
    if imm & (1 << 20): imm -= 1 << 21
    page = ((base + i) & ~0xfff) + (imm << 12)
    for k in range(1, 6):
        if i + 4 * k + 4 > len(d): break
        w2 = struct.unpack_from('<I', d, i + 4 * k)[0]
        if w2 & 0xffc00000 == 0x91000000 and (w2 >> 5) & 31 == rd:
            t = page + ((w2 >> 10) & 0xfff)
            if t in tset:
                a = base + i; j = bisect.bisect_right(addrs, a) - 1
                print(hex(a), 'in', syms[j][1][:120], hex(syms[j][0]))

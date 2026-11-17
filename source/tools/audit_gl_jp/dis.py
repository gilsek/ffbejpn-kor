"""dis.py <libgame.so> <symbol substring>...  : disassemble exported functions, resolve PLT calls and string literals."""
import sys, re, capstone
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
L = sys.argv[1]; f = open(L, 'rb'); e = ELFFile(f)
dyn = e.get_section_by_name('.dynsym')
syms = {s.name: s for s in dyn.iter_symbols() if s['st_value']}
addr2 = {s['st_value']: n for n, s in syms.items()}
plt = e.get_section_by_name('.plt'); rel = e.get_section_by_name('.rela.plt')
got2name = {r['r_offset']: dyn.get_symbol(r['r_info_sym']).name for r in rel.iter_relocations()}
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
def read(va, n):
    for seg in e.iter_segments():
        if seg['p_type'] == 'PT_LOAD' and seg['p_vaddr'] <= va < seg['p_vaddr'] + seg['p_filesz']:
            f.seek(seg['p_offset'] + va - seg['p_vaddr']); return f.read(n)
    return b''
pltname = {}
pb = read(plt['sh_addr'], plt['sh_size'])
ins = list(md.disasm(pb, plt['sh_addr']))
for k in range(len(ins) - 2):
    a, b = ins[k], ins[k + 1]
    if a.mnemonic == 'adrp' and b.mnemonic == 'ldr':
        page = int(a.op_str.split('#')[1], 16); off = re.search(r'#(0x[0-9a-f]+)\]', b.op_str)
        if off: pltname[a.address] = got2name.get(page + int(off.group(1), 16), '?')
def cstr(va):
    b = read(va, 120); b = b.split(b'\0')[0]
    try: return b.decode('utf-8')
    except: return None
for pat in sys.argv[2:]:
    for n, s in syms.items():
        if pat not in n or s['st_info']['type'] != 'STT_FUNC': continue
        print('=====', n, hex(s['st_value']), s['st_size'])
        regs = {}
        for i in md.disasm(read(s['st_value'], min(s['st_size'], 0x3000)), s['st_value']):
            t = i.op_str; extra = ''
            if i.mnemonic == 'adrp': regs[t.split(',')[0]] = int(t.split('#')[1], 16)
            elif i.mnemonic == 'add' and '#' in t:
                p = [x.strip() for x in t.split(',')]
                if p[1] in regs:
                    v = regs[p[1]] + int(p[2].lstrip('#'), 16); c = cstr(v)
                    if c and len(c) >= 2 and c.isprintable(): extra = '  "' + c + '"'
            elif i.mnemonic in ('bl', 'b') and t.startswith('#'):
                tgt = int(t[1:], 16); extra = '  ' + (addr2.get(tgt) or pltname.get(tgt, ''))
            print(hex(i.address), i.mnemonic, t, extra)

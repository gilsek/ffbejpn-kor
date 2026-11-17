"""GameResponseFactory::createResponseData tag -> response class map for an arm64 libgame.so.
usage: python -I tools/response_tags.py <libgame.so> <out.json>"""
import sys, re, json
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
f, out = sys.argv[1], sys.argv[2]
d = open(f, 'rb').read(); e = ELFFile(open(f, 'rb')); dyn = e.get_section_by_name('.dynsym')
fn = next(s for s in dyn.iter_symbols() if s.name.startswith('_ZN19GameResponseFactory18createResponseDataEPKc'))
got2name = {r['r_offset']: dyn.get_symbol(r['r_info_sym']).name for r in e.get_section_by_name('.rela.plt').iter_relocations()}
plt = e.get_section_by_name('.plt'); md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
pins = list(md.disasm(plt.data(), plt['sh_addr'])); pltname = {}
for a, b in zip(pins, pins[1:]):
    if a.mnemonic == 'adrp' and b.mnemonic == 'ldr':
        m = re.search(r'#(0x[0-9a-f]+)\]', b.op_str)
        if m: pltname[a.address] = got2name.get(int(a.op_str.split('#')[1], 16) + int(m[1], 16), '?')
local = {s['st_value']: s.name for s in dyn.iter_symbols() if s['st_value']}
start, size = fn['st_value'], fn['st_size']
ins = list(md.disasm(d[start:start + size], start)); by_addr = {x.address: k for k, x in enumerate(ins)}
regs = {}; last_str = None; cases = []
for x in ins:
    if x.mnemonic == 'adrp': regs[x.op_str.split(',')[0]] = int(x.op_str.split('#')[1], 16)
    elif x.mnemonic == 'add' and '#' in x.op_str:
        r = x.op_str.split(',')[0]; src = x.op_str.split(',')[1].strip()
        if src in regs and r == 'x1':
            a = regs[src] + int(x.op_str.split('#')[1], 16); last_str = d[a:a + 16].split(b'\0')[0].decode('latin1')
    elif x.mnemonic == 'cbz' and last_str is not None:
        cases.append((last_str, int(x.op_str.split('#')[1], 16))); last_str = None
res = {}
for tag, tgt in cases:
    k = by_addr.get(tgt)
    if k is None: continue
    for y in ins[k:k + 8]:
        if y.mnemonic == 'bl':
            t = int(y.op_str[1:], 16); n = pltname.get(t) or local.get(t, hex(t))
            if 'Response' in n and ('C1' in n or 'C2' in n):
                res[tag] = re.sub(r'^_ZN\d+', '', n).split('C1')[0].split('C2')[0]; break
json.dump(res, open(out, 'w'), indent=1, sort_keys=True); print(len(cases), 'tags,', len(res), 'mapped')

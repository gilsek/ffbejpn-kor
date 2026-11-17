"""tokens.py <libgame.so> <out.json> : for every *Response::readParam and *Request::createBody/getRequestID, the 8-char
tokens referenced as string literals (adrp+add). Read-only static analysis."""
import sys, re, json, capstone
from elftools.elf.elffile import ELFFile
L, OUT = sys.argv[1], sys.argv[2]
f = open(L, 'rb'); e = ELFFile(f)
dyn = e.get_section_by_name('.dynsym')
segs = [(s['p_vaddr'], s['p_filesz'], s['p_offset']) for s in e.iter_segments() if s['p_type'] == 'PT_LOAD']
data = open(L, 'rb').read()
def read(va, n):
    for v, sz, off in segs:
        if v <= va < v + sz: return data[off + va - v: off + va - v + n]
    return b''
def cstr(va):
    b = read(va, 64).split(b'\0')[0]
    try: return b.decode('ascii')
    except: return None
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
TOK = re.compile(r'^[A-Za-z0-9]{8}$')
PAT = re.compile(r'^_ZN(\d+)(\w+?(Response|Request))(9readParamEiiPKcS1_b|10createBodyEv|12getRequestIDEv|12getEncodeKeyEv)$')
res = {}
for s in dyn.iter_symbols():
    m = PAT.match(s.name)
    if not m or not s['st_value']: continue
    cls, kind = m.group(2)[:int(m.group(1))], m.group(4)
    regs = {}; toks = []
    for i in md.disasm(read(s['st_value'], min(s['st_size'], 0x8000)), s['st_value']):
        t = i.op_str
        if i.mnemonic == 'adrp': regs[t.split(',')[0]] = int(t.split('#')[1], 16)
        elif i.mnemonic == 'add' and '#' in t:
            p = [x.strip() for x in t.split(',')]
            if p[1] in regs:
                c = cstr(regs[p[1]] + int(p[2].lstrip('#'), 16))
                if c and TOK.match(c): toks.append(c)
    k = {'9readParamEiiPKcS1_b': 'read', '10createBodyEv': 'body', '12getRequestIDEv': 'id', '12getEncodeKeyEv': 'key'}[kind]
    res.setdefault(cls, {})[k] = toks
json.dump(res, open(OUT, 'w'), indent=0, sort_keys=True)
print(L, len(res), 'classes')

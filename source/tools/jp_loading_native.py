"""로딩 조사용 읽기 전용 ELF 역어셈블: 심볼 정규식, PLT 이름과 문자열 참조 출력."""
import argparse
import io
import re
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('elf')
p.add_argument('pattern')
p.add_argument('--out', required=True)
p.add_argument('--range', nargs=2, type=lambda v: int(v, 0), metavar=('ADDRESS', 'SIZE'), help='심볼 없는 함수의 제한된 정적 분석 범위')
a = p.parse_args()
raw = Path(a.elf).read_bytes()
e = ELFFile(io.BytesIO(raw))
symbols = list(e.get_section_by_name('.dynsym').iter_symbols())
names = {s['st_value']: s.name for s in symbols if s['st_value']}
rel = e.get_section_by_name('.rela.plt')
plt = e.get_section_by_name('.plt')
if rel and plt:
    for i, r in enumerate(rel.iter_relocations()):
        names[plt['sh_addr'] + 32 + i * 16] = symbols[r['r_info_sym']].name + '@plt'

def data(addr, count):
    for seg in e.iter_segments():
        if seg['p_vaddr'] <= addr < seg['p_vaddr'] + seg['p_filesz']:
            off = seg['p_offset'] + addr - seg['p_vaddr']
            return raw[off:off + count]
    return b''

cs = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
lines = []
for s in symbols:
    if s['st_info']['type'] != 'STT_FUNC' or not re.search(a.pattern, s.name):
        continue
    lines.append(f'\n{s["st_value"]:#x} size={s["st_size"]:#x} {s.name}')
    pages = {}
    for ins in cs.disasm(data(s['st_value'], s['st_size']), s['st_value']):
        annotation = ''
        if ins.mnemonic in ('bl', 'b') and ins.op_str.startswith('#'):
            annotation = names.get(int(ins.op_str[1:], 16), '')
        parts = ins.op_str.split(', ')
        if ins.mnemonic == 'adrp':
            pages[parts[0]] = int(parts[1][1:], 16)
        elif ins.mnemonic == 'add' and len(parts) == 3 and parts[1] in pages and parts[2].startswith('#'):
            ref = pages[parts[1]] + int(parts[2][1:], 16)
            b = data(ref, 150).split(b'\0')[0]
            if b and all(32 <= c < 127 for c in b):
                annotation += ' string=' + repr(b.decode())
        lines.append(f'{ins.address:#x} {ins.mnemonic} {ins.op_str} {annotation}')
if a.range:
    start, size = a.range
    if not 0 < size <= 16384:
        p.error('범위 크기는 1..16384바이트')
    for ins in cs.disasm(data(start, size), start):
        annotation = ''
        if ins.mnemonic in ('bl', 'b') and ins.op_str.startswith('#'):
            annotation = names.get(int(ins.op_str[1:], 16), '')
        lines.append(f'{ins.address:#x} {ins.mnemonic} {ins.op_str} {annotation}')
Path(a.out).write_text('\n'.join(lines), encoding='utf-8')
print(f'{len(lines)} lines -> {a.out}')

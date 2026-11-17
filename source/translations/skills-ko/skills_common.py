"""유닛 기술 번역 대상과 기존 아이템 패치의 보존 계약."""
import sys
import re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'items-ko'))
import item_common as I

ROOT,N = I.ROOT,I.N
HERE = Path(__file__).resolve().parent
PROJECT = ROOT/'build/out/skills_gt'
JP,TAG,VARIABLE,MARKER = I.JP,I.TAG,I.VARIABLE,I.MARKER
read,write_checked,protect,restore,clean = I.read,I.write_checked,I.protect,I.restore,I.clean
raw_numbers,numbers = I.raw_numbers,I.numbers
SPECS = {
    'F_ABILITY_MST': ('Ga5V42LZ',['G4L0YIB2','Ha9G5sCS']),
    'F_ABILITY_EXPLAIN_MST': ('Ga5V42LZ',['T7aEx3Mj']),
    'F_MAGIC_MST': ('QV1HE7Wq',['G4L0YIB2']),
    'F_MAGIC_EXPLAIN_MST': ('QV1HE7Wq',['T7aEx3Mj']),
    'F_LIMITBURST_MST': ('PR2HIc71',['G4L0YIB2','6uvHX2JG','Ha9G5sCS']),
    'F_LIMITBURST_LV_MST': ('PR2HIc71',['Ha9G5sCS']),
    'F_SEASON_EVENT_ABILITY_MST': ('3rXE9wdp',['G4L0YIB2']),
    'F_SEASON_EVENT_ABILITY_TYPE_MST': ('7WYvz1Ep',['G4L0YIB2','6uvHX2JG']),
}
EFFECT = 'Ha9G5sCS'
SEPARATOR = re.compile(r'([,@&])')

def rid(source):
    return I.rid(source).replace('item_','skill_',1)

def manifest(): return read(HERE/'manifest.json')

def load_tables():
    masters=N.masters(); result={}
    for table in SPECS:
        tok,key=masters[table]
        src=next((N.OLD/'downloads/ffbejpdata-archive-org').glob(f'Ver*_{tok}.dat'))
        result[table]=(src,key,N.D.decode(src.read_bytes(),key)[1])
    return result

def human(text):
    if not isinstance(text,str): return False
    if JP.search(text): return True
    if not re.search('[A-Za-z]',text): return False
    # 순수 능력치 표기는 이름으로 그대로 사용한다.
    return not re.fullmatch(r'(?:HP|MP|ATK|DEF|MAG|SPR|LB|EXP)(?:[+\-]\d+(?:\.\d+)?%?)?',text)

def pieces(field,text):
    if field==EFFECT:
        return [(i,v) for i,v in enumerate(SEPARATOR.split(text)) if JP.search(v)]
    return [(None,text)] if human(text) else []

def wire(field,text):
    text=clean(text)
    if field==EFFECT:
        text=text.replace(',','‚').replace(':','：').replace('@','＠').replace('&','＆')
    return text

def patched_value(field,original,locations,translations):
    if field!=EFFECT:
        assert len(locations)==1
        return wire(field,translations[locations[0]['translation_id']])
    parts=SEPARATOR.split(original)
    for loc in locations:
        assert parts[loc['part']]==loc['source']
        parts[loc['part']]=wire(field,translations[loc['translation_id']])
    return ''.join(parts)

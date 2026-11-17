"""아이템 계열 표·참조 범위·번역 입출력의 공통 계약."""
import hashlib
import json
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import name_coverage as N

HERE = Path(__file__).resolve().parent
PROJECT = ROOT / 'build/out/items_gt'
# 검색용 cnLF6Cz1은 별도 가나 번역 대신 해당 행의 표시 이름을 사용한다.
SPECS = {
    'F_ITEM_MST': ('tL6G9egd', ['G4L0YIB2']),
    'F_ITEM_EXPLAIN_MST': ('tL6G9egd', ['T7aEx3Mj', 'VC9F3eJn']),
    'F_EQUIP_ITEM_MST': ('J1YX9kmM', ['G4L0YIB2', 'cnLF6Cz1']),
    'F_EQUIP_ITEM_EXPLAIN_MST': ('J1YX9kmM', ['T7aEx3Mj', 'VC9F3eJn']),
    'F_MATERIA_MST': ('H5jBL0Vf', ['G4L0YIB2', 'cnLF6Cz1']),
    'F_IMPORTANT_ITEM_MST': ('2dfixko3', ['G4L0YIB2']),
    'F_IMPORTANT_ITEM_EXPLAIN_MST': ('2dfixko3', ['T7aEx3Mj', 'VC9F3eJn', 'ShTbN3q9']),
    'F_VISION_CARD_MST': ('5giCMUd2', ['G4L0YIB2', 'cnLF6Cz1']),
    'F_VISION_CARD_EXPLAIN_MST': ('5giCMUd2', ['T7aEx3Mj', 'VC9F3eJn', 'fYhnz5N9',
                                                'J5QKLzW7', 'BGWpF0i2', 'ShTbN3q9', '1ux5sP4L']),
    'F_VISION_CARD_ABILITY_ACT_COND_MST': ('5giCMUd2', ['6uvHX2JG']),
    'F_EMBLEM_ITEM_MST': ('0w6XzofV', ['G4L0YIB2', 'T7aEx3Mj']),
    'F_RECIPE_BOOK_MST': ('staFu8U1', ['G4L0YIB2']),
    'F_RECIPE_MST': ('MpNE6gB5', ['VC9F3eJn']),
    'F_EXCHANGE_SHOP_ITEM_MST': ('wpM08VZ7', ['G4L0YIB2']),
    'F_ABILITY_MST': ('Ga5V42LZ', ['G4L0YIB2']),
    'F_ABILITY_EXPLAIN_MST': ('Ga5V42LZ', ['T7aEx3Mj']),
    'F_MAGIC_MST': ('QV1HE7Wq', ['G4L0YIB2']),
    'F_MAGIC_EXPLAIN_MST': ('QV1HE7Wq', ['T7aEx3Mj']),
}
JP = re.compile(r'[぀-ヺヽ-ヿ一-鿿ｦ-ﾟ]')
TAG = re.compile(r'<[^>]+>')
NUMBER = re.compile(r'\d+(?:[.,]\d+)*')
PROTECT = re.compile(r'<[^>]+>|\{[^{}]+\}|%(?:\d+\$)?[-+0-9.]*[sdfiu]|\d+(?:[.,]\d+)*(?:[%％])?')
MARKER = re.compile(r'__FFBE_\d{3}__')
VARIABLE = re.compile(r'\{[^{}]+\}|%(?:\d+\$)?[-+0-9.]*[sdfiu]')


def raw_numbers(text):
    return NUMBER.findall(unicodedata.normalize('NFKC',text))


def numbers(text):
    """일본어 차수 표기와 전각 숫자는 같은 값의 아라비아 숫자로 비교한다."""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'FF\s*영식', 'FF0式', text)
    text = text.replace('ゼロ式', '0式').replace('제로식', '0式')
    text = text.replace('여섯 신', '6神')
    text = text.replace('십이무구', '12武具')
    digits = {'〇':0,'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,
              '壱':1,'弐':2,'参':3,'伍':5}
    units = {'十':10,'百':100,'千':1000,'万':10000,'億':100000000}
    def convert(match):
        s = match.group()
        if not any(c in units for c in s):
            return ''.join(str(digits[c]) for c in s)
        total,section,number = 0,0,0
        for c in s:
            if c in digits:
                number = number*10+digits[c]
            elif units[c] < 10000:
                section += (number or 1)*units[c]; number = 0
            else:
                total += (section+number or 1)*units[c]; section = number = 0
        return str(total+section+number)
    text = re.sub(r'(?<![数何幾])[〇零一二三四五六七八九十百千万億壱弐参伍]+',convert,text)
    text = re.sub(r'(?<![A-Z])II(?=世)', '2',text)
    return NUMBER.findall(text)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def manifest():
    data = read(HERE/'manifest.json')
    supplement = HERE/'supplement.json'
    if supplement.exists():
        extra = read(supplement)
        records = {r['ffbe_id']: r for r in data['records']}
        for rec in extra['records']:
            if rec['ffbe_id'] in records:
                assert records[rec['ffbe_id']]['source'] == rec['source']
            else:
                records[rec['ffbe_id']] = rec
        data['records'] = list(records.values())
        data['locations'].extend(extra['locations'])
        data['reused'].update(extra['translations'])
        for loc in extra['locations']:
            data['tables'][loc['table']]['target_fields'] += 1
        data['unique_total'] = len(data['records'])
    return data


def write_checked(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=1) + '\n'
    if path.exists() and path.read_text(encoding='utf-8-sig') != text:
        raise ValueError('다른 기존 입력을 덮어쓰지 않음: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def load_tables():
    manifest = N.masters()
    result = {}
    for table in list(SPECS) + ['F_VISION_CARD_LV_ACQUIRE_MST']:
        token, key = manifest[table]
        src = next((N.OLD / 'downloads/ffbejpdata-archive-org').glob(f'Ver*_{token}.dat'))
        result[table] = (src, key, N.D.decode(src.read_bytes(), key)[1])
    return result


def references(tables):
    # GiBvPK84=마법 ID 목록, t42Xb3jV=어빌리티 ID 목록.
    # 첫 마테리아 라이브라 10010, HP+10% 100010을 각각 실제 마법/기술 기본키와 대조했다.
    magic, ability = set(), set()
    for table in ('F_EQUIP_ITEM_MST', 'F_MATERIA_MST'):
        for row in tables[table][2]:
            magic.update(re.findall(r'\d+', row.get('GiBvPK84', '')))
            ability.update(re.findall(r'\d+', row.get('t42Xb3jV', '')))
    for row in tables['F_VISION_CARD_LV_ACQUIRE_MST'][2]:
        ability.update(re.findall(r'\d+', row.get('1Zsh27mS', '')))
        magic.update(re.findall(r'\d+', row.get('i6kc1jN0', '')))
    for row in tables['F_VISION_CARD_ABILITY_ACT_COND_MST'][2]:
        ability.update(re.findall(r'\d+', row.get('a4hXTIm0', '')))
    magic.discard('0'); ability.discard('0')
    return {'F_MAGIC_MST': magic, 'F_MAGIC_EXPLAIN_MST': magic,
            'F_ABILITY_MST': ability, 'F_ABILITY_EXPLAIN_MST': ability}


def protect(source):
    tokens = []
    def replace(match):
        tokens.append(match.group())
        return f'__FFBE_{len(tokens)-1:03}__'
    return PROTECT.sub(replace, source), tokens


def restore(text, tokens):
    for i, token in enumerate(tokens):
        text = text.replace(f'__FFBE_{i:03}__', token)
    return text


def rid(source):
    return 'item_' + hashlib.sha256(source.encode('utf-8')).hexdigest()[:20]


def clean(text):
    # 네이티브 JSON 리더는 이스케이프된 큰따옴표/역슬래시를 지원하지 않는다.
    # 아이템 본문은 전투 명령과 다르므로 쉼표·콜론 구분자는 강제 치환하지 않는다.
    text = text.replace('"', '”').replace('\\', '＼')
    return text.replace('\r\n', '<br>').replace('\n', '<br>').replace('\r', '<br>')


@lru_cache(maxsize=1)
def _skill_layer():
    folder=ROOT/'translations/skills-ko'
    if not (folder/'patches.json').exists():return {},{}
    return read(folder/'manifest.json')['tables'],read(folder/'patches.json')


def skill_overlay(table,source):
    """기술 전체 적용 후 아이템을 재생성해도 같은 기술 표를 되돌리지 않는다."""
    tables,patches=_skill_layer()
    if table not in patches:return {}
    assert hashlib.sha256(source.read_bytes()).hexdigest()==tables[table]['sha256']
    allowed={'F_ABILITY_MST':{'G4L0YIB2','Ha9G5sCS'},'F_ABILITY_EXPLAIN_MST':{'T7aEx3Mj'},
             'F_MAGIC_MST':{'G4L0YIB2'},'F_MAGIC_EXPLAIN_MST':{'T7aEx3Mj'}}
    assert table in allowed
    assert all(set(v)<=allowed[table] for v in patches[table].values())
    return patches[table]

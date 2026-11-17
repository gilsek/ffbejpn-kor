"""적 기술 전체 표시 이름의 번역·검수 계약. 영문도 번역 대상이다."""
import hashlib
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build'))
import make_ko_monster_skills as M
I,N=M.I,M.N
HERE=Path(__file__).resolve().parent
PROJECT=ROOT/'build/out/monster_skills_gt'
JP,TAG,VARIABLE,MARKER=I.JP,I.TAG,I.VARIABLE,I.MARKER
read,write_checked,protect,restore,clean=I.read,I.write_checked,I.protect,I.restore,I.clean
raw_numbers,numbers=I.raw_numbers,I.numbers

def rid(source):return 'monster_'+hashlib.sha256(source.encode('utf-8')).hexdigest()[:20]
def manifest():return read(HERE/'manifest.json')
def source_path():return N.OLD/'upstream/source/server/content/battle/F_MONSTER_SKILL_MST.tsv'
def load_rows():return M.B.read_index_table(str(source_path()),'F_MONSTER_SKILL_MST')
def human(source):
    # 카운트다운 숫자는 표시 그대로 보존한다. 영문·일문 이름/문장은 전부 대상이다.
    return bool(re.search(r'[A-Za-z가-힣぀-ヿ一-鿿ｦ-ﾟ]',source))

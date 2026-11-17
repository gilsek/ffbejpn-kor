"""차원의 틈새(GateScene) 타일 배너를 일판 배너 연결표 v4 + 알테마 위키 이미지로 배정한다.

입력 (읽기 전용)
  * build/out/vortex_season/jp_area_banner_map.json   구역별 v4 판정(bucket_v4 / confidence_v4 /
                                                       chosen_banner_v4 / conflict / evidence_v4 / wiki_image)
  * build/engine_overlay/jp_event_groups.json         서빙 구역(탭/시즌) 목록
  * build/out/seal_room/banner_files.tsv              기기 일판 spdungeon1..9.cpk TOC (파일명/크기/cpk)
  * build/out/vortex_season/altema/quest_banners.tsv  알테마 퀘스트 페이지 이미지(img: uploads 상대 경로)
  * build/out/vortex_season/altema/img/<img>          build/fetch_altema_banners.py 로 받은 jpg/png
  * build/out/vortex_season/match_v5/originals_B.tsv  원본 유지 구역(area/banner/score/name_jp).
                                                      구역의 배너를 일판 CPK 원본으로 고정한다(--originals)
  * build/out/vortex_season/match_v5/nonbanner/exclude.txt  비배너 이미지 sha16 목록(한 줄에 하나,
                                                      '#' 주석 허용). EXCLUDED_IMAGES 와 합쳐 제외한다
                                                      (--exclude-images)

출력
  * build/engine_overlay/jp_event_art.json            {"art": {배너: {size, cpk[, path]}},
                                                       "by_area": {구역: 배너}, "by_global": {}}
  * build/engine_overlay/jp_banner_art.json           영문판 event_*.png 항목 제거 + 생성 배너(교체용) 병합
  * build/out/jp_offline/engine/static/client/files/ko/vortex_banner/<hash>.png
                                                      640x240 PNG8 (Real-ESRGAN 4배 업스케일 후 단색
                                                      테두리를 잘라 내고 가운데 621x206 상자를 꽉
                                                      채운) 알테마 배너
  * build/out/jp_offline/engine/static/client/files/ko/vortex_banner/name_<area>.png
                                                      그림이 없는 구역마다 일판 빈 판 위에 한국어
                                                      구역 이름을 그린 640x240 PNG8 배너
  * build/out/vortex_season/altema/assignments.tsv    구역별 근거(매칭 tier / 알테마 항목 / 배너)

배정 규칙 (사용자 결정 2026-11-12)
  * 이미 일판 CPK 배너가 붙은 구역(현재 by_area != 중립, 188개)은 그대로 둔다.
  * 나머지 구역 중 v4 가 알테마 퀘스트와 exact/contains 로 매칭된 구역은 그 퀘스트 페이지 이미지를 쓴다.
    fuzzy 는 정규화 이름이 포함 관계이거나 유사도 >= 0.85 일 때만, contains_multi 는 쓰지 않는다.
  * 매칭되는 이미지가 없거나 파일을 못 받은 구역은 일판 빈 판(spd_bn_list_dummy.png) 위에 한국어
    구역 이름을 그린 배너(name_<area>.png)를 구역마다 하나씩 쓴다(사용자 결정 2026-11-13). 이름은
    build/apply_ko_names.py 와 같은 순서로 translations/names-ko/names_pass1..3.json ->
    translations/masters-ko/translated.json 에서 찾고(＠ 접미사 규칙 동일), 없으면 접두 일치의
    한국어 앞부분을 쓰고, 그래도 없으면 일본어 원문을 그대로 쓴다(목록은 name_banner_missing.tsv).
    이름 끝의 (배너)/(バナー) 접미는 지우고, 한 줄이 38px 미만이면 두 줄로 나눈다.
  * 봉인의 방(jp_seal_room.SEAL_AREAS)은 서빙 구역이 아니라 대상이 아니다.
  * 원본 유지 목록(--originals)의 구역은 알테마 경로를 쓰지 않고 그 배너를 그대로 쓴다. 배너가 일판
    CPK TOC 에 없으면 덮어쓰지 않고 경고로 남기고, served 에 없는 구역은 무시하고 개수만 센다.
  * 비배너 제외 목록(--exclude-images)의 sha16 이미지도 EXCLUDED_IMAGES 처럼 제외해, 그 이미지를
    쓰던 구역은 이름 배너(name banner) 경로로 간다.
  * 영문판(Global) 배너/경로는 읽지도 쓰지도 않는다. 예외: GL_EXCEPTIONS 의 구역(사용자 결정 2026-11-14)은
    일판 원본·알테마·트위터 어디에도 없고 일판 마스터가 가리키는 같은 이름의 파일이 영문판 팩에만 있어,
    그 영문판 640x240 배너를 변환 없이 쓴다(트위터 배너보다 먼저).
  * 대역(stand-in) 배정은 직전 jp_event_art.json / jp_banner_art.json 의 path(`<DEVICE_REL>/<hash>.png`,
    `<DEVICE_REL>/name_<area>.png`)를 거꾸로 읽어 같은 이미지/구역에 재사용한다. 그래야 이미지 하나가
    늘어도 뒤 대역이 한 칸씩 밀리지 않는다. 재사용할 수 없는 대역과 쓰이지 않게 된 옛 대역은 풀에서
    빼고 새 이미지/구역에 주지 않는다. `--fresh` 는 예전처럼 정렬된 풀에서 순서대로 배정한다.
  * jp_event_art.json 최상위 `stamp` 는 by_area 와 art(정렬 직렬화)의 sha1 앞 12자이며,
    jp_banner_art.json 에도 같은 값을 써서 엔진 표와 기기 표의 버전을 맞춘다.

클라이언트 로드 경로
  by_area 값은 클라이언트가 CRI(criFsBinder_Find)로 찾는 파일 **이름**이다. 그래서 알테마 이미지는
  일판 CPK TOC 안의 서로 다른 spd_*_bn_list 파일을 대역(stand-in)으로 쓰고, 그 파일의 디코드 바이트
  길이를 키로 build/frida/jp_offline.js 의 Image::initWithImageData 갈아끼우기(가챠 배너와 같은 방식)가
  변환 PNG 로 바꿔 준다. 파일은 기기 files/exvius/data/static/client/files/ko/vortex_banner/ 에 있고,
  art 항목의 `path` 가 jp_banner_art.json 으로 병합되어 훅이 읽는다.

usage: python -I -X utf8 build/make_jp_event_art.py [--dry-run] [--fresh] [--reuse-banners]
                                                    [--esrgan-cache DIR]
                                                    [--originals FILE] [--exclude-images FILE]
"""
import argparse
import collections
import csv
import difflib
import hashlib
import shutil
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'build/engine_overlay'
VS = ROOT / 'build/out/vortex_season'
ALT = VS / 'altema'
BANNER_V4 = VS / 'jp_area_banner_map.json'
GROUPS = OVERLAY / 'jp_event_groups.json'
TOC = ROOT / 'build/out/seal_room/banner_files.tsv'
EVENT_MAP = OVERLAY / 'jp_event_art.json'
BANNER_MAP = OVERLAY / 'jp_banner_art.json'
QUEST = ALT / 'quest_banners.tsv'
IMG_DIR = ALT / 'img'
ORIGINALS_TSV = VS / 'match_v5/originals_v7.tsv'          # 원본 유지 구역(area/banner/score/name_jp)
DEMOTE_TSV = VS / 'match_v5/demote_C.tsv'                # 날짜만으로 원본이 붙은 구역: 원본 대신 알테마/이름 배너로 내린다
EXCLUDE_IMAGES_TXT = VS / 'match_v5/nonbanner/exclude.txt'   # 비배너 이미지 sha16 목록
ASSIGN_TSV = ALT / 'assignments.tsv'
BANNER_DIR = ROOT / 'build/out/jp_offline/engine/static/client/files/ko/vortex_banner'
DEVICE_ROOT = 'exvius/data/static'         # same root as build/make_jp_banners.py (FILES + this)
DEVICE_REL = DEVICE_ROOT + '/client/files/ko/vortex_banner'

# 구역 이름 배너: 그림이 없는 중립 구역마다 일판 빈 판(spd_bn_list_dummy.png) 위에 한국어 이름을 그린다.
# 글자는 판 안쪽 (40,40)-(600,200) 상자에 흰색 + 짙은 테두리로 가운데 정렬한다.
NAME_PLATE = VS / 'cpk_dump/raw/spd_bn_list_dummy.png'
RIBBON_PLATE = VS / 'cpk_dump/raw/spd_20181120_bn_list_tower.png'
KO_FONT = ROOT / 'build/out/ko_font/ko_game_font.ttf'
KO_NAMES = ROOT / 'translations/names-ko'      # names_pass1..3.json (build/apply_ko_names.py sources)
KO_TRANSLATIONS = ROOT / 'translations/masters-ko/translated.json'
NAME_MISSING = VS / 'name_banner_missing.tsv'  # Korean name not found (area, name_jp)
# 접두 일치로 한국어 앞부분을 잘라 낼 때 경계로 보는 문자들.
NAME_SEPARATORS = '　（）()［］[]「」『』＠:：/・- '
NAME_TEXT_BOX = (40, 40, 600, 200)          # (x0, y0, x1, y1) 글자 영역
NAME_FONT_START = 44                       # 기본 글자 크기(px)
NAME_FONT_MIN = 28                         # 넘칠 때 줄일 수 있는 최소 크기
NAME_SINGLE_MIN = 38                       # 한 줄을 허용하는 최소 크기(이보다 작아지면 두 줄)
NAME_STROKE = 4                            # 큰 글자 테두리 두께
NAME_STROKE_MIN = 3                        # 작은 글자 테두리 두께
NAME_LINE_GAP = 6                          # 두 줄일 때 줄 사이 간격
NAME_SPLIT_MARKS = '~〜-－—–「『（(［['    # 두 줄 분할에서 공백보다 우선하는 구분 기호
# 이름 끝의 (배너)/(バナー) 같은 판 표시 접미는 그리지 않는다.
NAME_SUFFIX = re.compile(r'\s*[（(]\s*(?:バナー|배너)\s*[)）]\s*$')
TAG = re.compile(r'<[^>]+>')

# 공통 중립 배너: 일판 spdungeon1.cpk TOC 에 있는 빈 판(22,909 B). 이벤트/시설 이름이 없다.
NEUTRAL = 'spd_bn_list_dummy.png'
NEUTRAL_NOTE = ('blank plate shipped in the JP spdungeon1.cpk; no event/facility title '
                '(not spd_bn_list_00003.png, which reads 経験の間)')
# 일판 타일 배너 실측 크기: engine/static 의 spd_*_bn_list_*.png 다수가 640x240 PNG8(팔레트).
# 그림이 들어갈 몸통(알파 255) 영역의 최빈값은 (16,16)-(624,224), 608x208 이다
# (build/out/vortex_season/altema/size_vs_orig.tsv 의 op_x0/op_y0/op_x1/op_y1 최빈값).
# 잘라 낸 그림을 이 상자에 채우고 바깥만 투명으로 둔다. 예전 621x206 추정식(97%/86%)은 폐기.
TARGET = (640, 240)
BOX = (608, 208)          # (16,16)-(624,224) 몸통 영역
BOX_LEFT = 16
BOX_TOP = 16
# 테두리 제거: 자르는 대상은 (a) RGB 가 모두 235 이상인 흰 줄(행/열의 98% 이상)과 (b) 알파 0 줄뿐이다.
# 검정/회색/금색 같은 다른 단색은 배너의 장식 프레임일 수 있으므로 자르지 않는다.
# 흰 줄은 한 변에서 연속 4px 이상일 때만 자르고(3px 이하는 프레임 선), 각 변 25%를 넘으면 자르지 않는다.
BORDER_WHITE_MIN = 235
BORDER_SOLID_FRACTION = 0.98
BORDER_MAX_CUT = 0.25
BORDER_WHITE_MIN_PX = 4
# 상자 채우기: 원본/상자 비율 차이가 8% 이내면 비율을 무시하고 늘린다. 그보다 크면 비율을 맞추려고
# 최대 8%까지 비틀어 줄인 뒤(cover) 남는 쪽을 가운데 기준으로 잘라 낸다.
ASPECT_STRETCH_TOL = 0.08
COVER_DISTORT_LIMIT = 0.08
# cover 로 맞추려면 잘라 내야 하는 비율이 이 값을 넘으면, 잘라 내지 않고 비율을 유지한 채
# (contain) 상자 가운데에 넣고 바깥을 투명으로 둔다. 탭이 없는 배너에도 똑같이 적용한다.
CONTAIN_CROP_LIMIT = 0.15

# 공지(공지 배너) 형식 탭 제거. 알테마 배너 위쪽에는 탭 띠가 붙어 있다: 가운데 빨간 라벨,
# 그 좌우 남색 띠, 왼쪽 위 NEW. 흰 여백을 자른 직후의 업스케일 이미지 위쪽 20%를 검사한다.
TAB_SCAN_FRACTION = 0.20
TAB_RED_MAX = (150, 80, 80)          # R >, G <, B <
TAB_RED_CENTER = (0.30, 0.70)        # 라벨을 찾는 가운데 폭 구간
TAB_RED_MIN_FRACTION = 0.20          # 행 안에서 빨간 픽셀이 차지해야 하는 최소 비율(라벨 확인용)
TAB_RED_SUPPORT = 0.04               # 흰 글자 때문에 빨간 비율이 떨어지는 행까지 라벨로 이어 붙이는 하한
TAB_RED_BRIDGE = 0.055               # 라벨 안 흰 글자 구간을 건너뛸 수 있는 최대 끊김(그림 높이 대비)
TAB_RED_MIN_ROWS = 8                 # 빨간 라벨 띠로 인정할 최소 연속 행(업스케일 기준, 원본 ~2px)
TAB_NAVY = (6, 8, 49)                # 남색 띠 기준색
TAB_NAVY_DIST = 40                   # 채널별 최대 거리
TAB_NAVY_SIDES = ((0.02, 0.28), (0.72, 0.98))
TAB_NAVY_MIN_FRACTION = 0.85         # 좌/우 구간 각각에서 남색이 차지해야 하는 최소 비율
TAB_NAVY_BAND_MIN_ROWS = 20          # 남색 띠는 행 단위로 충분히 두꺼워야 한다
TAB_BAND_MAX_START = 0.08            # 띠는 그림 맨 위쪽(8% 이내)에서 시작해야 한다
TAB_GAP_ROWS = 2                     # 띠 안에서 허용하는 짧은 끊김
TAB_YELLOW_MIN = (200, 180, 100)     # NEW 노란 글자 기준 (R >, G >, B <)
TAB_YELLOW_WIDTH = 0.15              # 왼쪽 위 15% 폭 안
TAB_YELLOW_MIN_FRACTION = 0.01
TAB_NEW_EXTRA_FRACTION = 0.08        # NEW 가 탭 경계보다 내려올 수 있는 최대 추가 높이
TAB_MAX_CUT_FRACTION = 0.22          # 그림 높이 대비 탭을 자를 수 있는 최대 비율
# 공지 배너가 아닌 원본(게임 스크린샷/캐릭터 일러스트 등). 매칭에서 제외해 빈 배너로 돌린다.
# 값은 알테마 상대 경로의 sha1 앞 16자(출력 파일명과 같은 규칙)다.
EXCLUDED_IMAGES = frozenset({
    '08f33469832ecb93', '11d48fc99167db03', '5be415118cee05fc', 'b488653b8517ca71',
    'fdd429573e129c3d',
})
# Real-ESRGAN(ncnn) 4배 업스케일. 입력 폴더에 쓰지 않도록 임시 폴더에 중간 파일을 만든다.
ESRGAN_EXE = Path(r'D:\Util\realesrgan-ncnn-vulkan-20210901-windows\realesrgan-ncnn-vulkan.exe')
ESRGAN_MODEL = 'realesrgan-x4plus'
# WordPress 썸네일 접미사(-300x97.jpg). 같은 폴더에 접미사를 뺀 원본이 있으면 그쪽을 쓴다.
THUMB_SUFFIX = re.compile(r'-\d+x\d+(\.(?:jpe?g|png))$', re.I)
# 설치하지 않는 클라이언트가 이름으로 직접 찾는 안전 목록(중립/톱/00003/레이드 배경). 크기 충돌 금지.
SAFE_ART = ('spd_bn_list_00003.png', 'spd_bn_top_00003.png', 'spd_bn_list_dummy.png',
            'spd_bn_top_dummy.png', 'raid_king_mog.png')
# 봉인의 방 등 다른 화면이 직접 이름으로 쓰는 별칭. 이 이름들은 대역(stand-in)으로 쓰면 안 된다.
REFERENCE_SOURCES = (OVERLAY / 'jp_seal_room.py', OVERLAY / 'jp_compat.py',
                     OVERLAY / 'jp_event_menu.py', ROOT / 'build/frida')
SPD_NAME = re.compile(r'spd_[A-Za-z0-9_]*\.png')


def referenced_banner_names():
    names = set()
    for source in REFERENCE_SOURCES:
        files = [source] if source.is_file() else (
            sorted(source.glob('*.js')) if source.is_dir() else [])
        for path in files:
            names.update(SPD_NAME.findall(path.read_text(encoding='utf-8', errors='replace')))
    return names


def load_toc():
    """{파일명: (extract size, cpk)}. 같은 이름이 여러 cpk 에 있으면 첫 행."""
    toc = {}
    with open(TOC, encoding='utf-8') as fh:
        for row in csv.DictReader(fh, delimiter='\t'):
            toc.setdefault(row['file'], (int(row['size']), row['cpk']))
    return toc


def load_served():
    document = json.loads(GROUPS.read_text(encoding='utf-8'))
    return document['areas']


def load_original_banners(path):
    """원본 유지 TSV(area/banner/score/name_jp) -> [(area, banner, name_jp)].

    파일이 없으면 조용히 빈 목록을 돌려준다(기존 동작 유지).
    """
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    with open(path, encoding='utf-8') as fh:
        for row in csv.DictReader(fh, delimiter='\t'):
            area = str(row.get('area') or '').strip()
            banner = str(row.get('banner') or '').strip()
            if area and banner:
                rows.append((area, banner, str(row.get('name_jp') or '').strip()))
    return rows


def load_excluded_hashes(path):
    """비배너 제외 목록: 한 줄에 sha16(image_sha() 앞 16자). '#' 주석과 빈 줄은 무시한다."""
    path = Path(path)
    if not path.is_file():
        return set()
    hashes = set()
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        value = line.split('#', 1)[0].strip().lower()
        if value:
            hashes.add(value)
    return hashes


def choose(v4, toc):
    """(banner, category) for one area's v4 record; category feeds the report."""
    bucket = v4.get('bucket_v4')
    confidence = v4.get('confidence_v4')
    chosen = v4.get('chosen_banner_v4')
    kept = str(v4.get('evidence_v4') or '').startswith('kept jp_verified')
    if bucket == 'jp_cpk' and chosen and (confidence in ('high', 'medium') or kept):
        if chosen in toc:
            return chosen, 'jp_verified' if kept else str(confidence)
        return NEUTRAL, 'chosen banner not in client TOC'
    return NEUTRAL, 'bucket=%s' % bucket


def _norm_name(value):
    text = unicodedata.normalize('NFKC', str(value or '')).lower()
    return re.sub(r'探索|攻略|高難易度|まとめ|イベント|クエスト|【.*?】|[\s・:：\-—~〜「」『』（）()の]',
                  '', text)


def fuzzy_is_solid(name_jp, altema_name):
    """fuzzy 매칭을 쓸 만한 근거: 정규화 이름의 포함 관계 또는 유사도 0.85 이상.

    예: アスガルド丘陵 / アスガルド丘陵攻略まとめ -> 포함, 第二のゲート / 第二ゲート -> 'の' 제거 후 일치,
    魔晄都市で闘う者達 / 魔晄都市で戦う者達 -> 0.889. 裏切りの炎神 / 裏切りの神官(0.80)은 탈락.
    """
    a, b = _norm_name(name_jp), _norm_name(altema_name)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def altema_target(record):
    """(image url, tier) when v4 says this area belongs to an Altema quest page, else None."""
    v4 = record.get('v4') or {}
    tier = v4.get('match_tier')
    image = v4.get('wiki_image')
    if not image:
        return None
    if tier in ('exact', 'contains'):
        return image, tier
    if tier == 'fuzzy' and fuzzy_is_solid(record.get('name_jp'), v4.get('altema_name')):
        return image, 'fuzzy'
    return None


X_PREFIX = 'x:'
GL_PREFIX = 'gl:'
GL_BANNER_SRC = ROOT / 'build/out/jp_offline/engine/static/cpk_extract/en/area/Ver461_spdungeon1'
# area -> 영문판 배너 파일. 일판 F_ICON_MST 가 같은 이름을 가리키지만 일판 팩엔 없다(사용자 결정 2026-11-14).
NEWS_DIR = 'build/out/vortex_season/websearch/news_ok/'
MEM_DIR = 'build/out/vortex_season/memorial_banner_fixes/png/'   # 메모리얼 banner-fixes-v208 팩의 일판 공식 배너(640x240 캔버스판)
TW_DIR = 'build/out/vortex_season/websearch/tw_extra_ok/'   # 공식 트위터 추가 배너(일판), 640x240으로 맞춘 것
FANDOM_DIR = 'build/out/vortex_season/websearch/fandom_manual/'   # ROOT 기준, '/' 가 든 값은 이 경로로 읽는다


def gl_src(name):
    """GL_EXCEPTIONS 값 -> 원본 PNG 경로. '/'가 있으면 ROOT 기준 경로, 없으면 영문판 spdungeon1 추출본."""
    return ROOT / name if '/' in name else GL_BANNER_SRC / name


GL_EXCEPTIONS = {
    '711': 'spd_bn_list_FFBE.png',   # 記憶の回廊 / Memories from the Aquapolis (영어 글자 그대로)
    # 2026-11-14 사용자 결정: 이름판 10칸 + 알테마 그림 10칸을 영문판 자기 배너로(판독 OK만,
    # 734·767은 배너 글자가 다른 이벤트라 제외). 아이콘이 4구역 이상 공용인 것은 넣지 않는다.
    '792': 'spd_20171120_bn_list_DQMSL.png',         # エスタークチャレンジ
    '844': 'spd_20180910_bn_list_NieR_02.png',       # The Formidable Engels
    '852': 'spd_20181023_bn_list_goldbomb_02.png',   # Golden Bomb Battle!
    '853': 'spd_20181030_bn_list_FF13.png',          # The Gapra Whitewood
    '858': 'spd_20181120_bn_list_ff5_02.png',        # Fork Tower - Black Tower
    '860': 'spd_20181130_bn_list_FF5_02.png',        # エクスデス城・探索
    '861': 'spd_20181211_bn_list_fanfan.png',        # Fun With Physalis
    '863': 'spd_20181220_kh_bn_list.png',            # Heartless: Darkside
    '865': 'spd_20181227_bn_list_FF6_02.png',        # 炭坑都市ナルシェ・探索
    '871': 'spd_20190131_ff2_bn_list_02.png',        # Castle Palamecia - Exploration
    '890': 'spd_20190520_bn_list_ff15_02.png',       # The Treacherous Infernian
    '892': 'spd_20190530_ff4_bn_list_02.png',        # Tower of Zot - Exploration
    '3028': 'spd_20190831_bn_list_DQXI_S_04.png',    # Vs. Calasmos
    '3035': 'spd_20190920_bn_list_ff11_02.png',      # Distorter of Time Atomos
    '3042': 'spd_20190930_bn_list_FFBE_02.png',      # Siren's Tower - Exploration
    # 2026-11-14 사용자 결정: 영문판 위키(exvius.fandom.com) 배너, 사용자가 직접 받아 PNG로 변환. 판독 OK만.
    # 제외: 3091·3133(위키 배너는 Unit Intro Quest라 다른 종류), 919(일판은 裏十二武具 이동 구역인데 위키는 할로윈 던전).
    '3048': FANDOM_DIR + '3048_Banner-Rampaging_Shiva.png',
    '3049': FANDOM_DIR + '3049_Banner-Rampaging_Odin.png',
    '3050': FANDOM_DIR + '3050_Banner-Rampaging_Tetra_Sylphid.png',
    '3051': FANDOM_DIR + '3051_Banner-Rampaging_Alexander.png',
    '3052': FANDOM_DIR + '3052_Banner-Rampaging_Fenrir.png',
    '3019': FANDOM_DIR + '3019_Banner-Zanarkand_Dome.png',
    # 2026-11-14: 일판 공지 배너(게임 뉴스 기사 이미지, agy 웹 탐색). 판독 OK만, 764는 512x192 -> 640x240 확대.
    # 제외: プレイアブルクエスト 6칸(찾은 그림은 같은 작품의 輝源獲得·シリーズイベント 구역 배너라 다른 구역).
    '764': NEWS_DIR + '764.png',
    '3037': NEWS_DIR + '3037.png',
    '3072': NEWS_DIR + '3072.png',
    '3084': NEWS_DIR + '3084.png',
    '3113': NEWS_DIR + '3113.png',
    '3114': NEWS_DIR + '3114.png',
    '3136': NEWS_DIR + '3136.png',
    '3137': NEWS_DIR + '3137.png',
    '756': NEWS_DIR + '756.png',   # 2차 탐색(gamebiz, Social Game Info 워터마크 있음), 첫 미션 氷炎の騎士ラスウェル
    # 트위터 추가 배너 판독 OK(2026-11-14 Haiku, twitter/extra_area_match.tsv), 세로가 짧은 띠 배너 등.
    # 731 은 ALTEMA_OVERRIDES(정식 은색 테두리 원본), 750/755/761/770/775/780 은 x_banners.tsv 정식 640x240 원본 사용.
    '722': TW_DIR + '722.png',
    '748': TW_DIR + '748.png',
    '3001': TW_DIR + '3001.png',
    '3021': TW_DIR + '3021.png',
    '3024': TW_DIR + '3024.png',
    '3044': TW_DIR + '3044.png',
    '309': TW_DIR + '309.png',
    '702': NEWS_DIR + '702.png',   # 알테마 「七英雄 襲来！」(378x126→640x240). 기존 자동 배정은 742의 四魔貴族 그림이었다(이름 부분 일치 오배정)
    # 2026-11-15: 마지막 남은 순수 제목 배너 12종 교체(영문판 CPK 3133 + 공식 트위터/CPK 소재 기반 정식 프레임 배너 11종)
    '885': TW_DIR + '885.png',
    '3043': TW_DIR + '3043.png',
    '3055': TW_DIR + '3055.png',
    '3057': TW_DIR + '3057.png',
    '3075': TW_DIR + '3075.png',
    '3085': TW_DIR + '3085.png',
    '3105': TW_DIR + '3105.png',
    '3109': TW_DIR + '3109.png',
    '3119': TW_DIR + '3119.png',
    '3132': TW_DIR + '3132.png',
    '3133': 'spd_20200331_bn_list_FF9_03.png',
    '3153': TW_DIR + '3153.png',
}
ALTEMA_OVERRIDES = {
    '731': '2018/06/2018y06m14d_1643114916.PNG',
    '782': '2017/09/2017y09m23d_1643039989.jpg',
    '3003': '2019/06/2019y06m27d_1238011297.jpg',
    '3011': '2019/07/2019y07m08d_1119262363.jpg',
    '835': '2018/07/2018y07m23d_0943309221.jpg',
    '3110': '2020/02/2020y02m13d_1836590823.jpg',
}
X_BANNERS_TSV = ROOT / 'build/out/vortex_season/x_banners/x_banners.tsv'
X_BANNER_SRC = Path('D:/Archive/gallery-dl/twitter/FFRS_JP_banners_640x240')


def load_x_banners(path, src_dir):
    """area -> 트위터 배너 파일명. 파일이 없거나 640x240 PNG/JPEG 가 아닌 행은 버린다."""
    path = Path(path)
    if not path.is_file():
        return {}
    rows = {}
    with open(path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh, delimiter='\t'):
            area, name = (row.get('area') or '').strip(), (row.get('file') or '').strip()
            src = Path(src_dir) / name
            if not area or not name or not src.is_file():
                continue
            with Image.open(src) as image:
                if image.format not in ('PNG', 'JPEG') or image.size != (640, 240):
                    continue
            rows[area] = name
    return rows


def image_rel_url(url):
    marker = '/ffbe/uploads/'
    if marker not in url:
        return None
    return url.split(marker, 1)[1]


def image_sha(rel):
    """알테마 상대 경로 -> 출력 파일명/제외 목록에 쓰는 sha1 앞 16자."""
    return hashlib.sha1(rel.encode('utf-8')).hexdigest()[:16]


def esrgan_upscale(src, workdir):
    """Real-ESRGAN 4배 업스케일 결과 PNG 경로. 중간 파일은 workdir(임시 폴더)에만 만든다."""
    dst = Path(workdir) / (Path(src).stem + '.png')
    subprocess.run([str(ESRGAN_EXE), '-i', str(src), '-o', str(dst), '-n', ESRGAN_MODEL],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dst


def _cut_from_top(arr):
    """arr(HxWx4, int32)의 첫 줄부터 안쪽으로 연속된 잘라 낼 테두리 줄 수와 알파 여부.

    자르는 대상은 (a) RGB 가 모두 235 이상인 흰 줄(줄의 98% 이상), (b) 알파 0 줄뿐이다.
    검정/회색 등 다른 단색은 장식 프레임일 수 있어 자르지 않는다. 흰 줄은 연속 4줄 이상일
    때만 자르고(3줄 이하는 남긴다), 알파 0 줄은 길이와 무관하게 자른다. 한 변에서 25%를
    넘게 이어지면 그 변은 자르지 않는다. (자른 줄 수, 알파테두리여부) 를 돌려준다.
    """
    height = arr.shape[0]
    limit = int(height * BORDER_MAX_CUT)
    if limit < 1:
        return 0, False
    run = 0
    has_alpha = False
    for k in range(limit):
        line_rgb = arr[k, :, :3]
        line_alpha = arr[k, :, 3]
        if (line_alpha == 0).mean() >= BORDER_SOLID_FRACTION:
            has_alpha = True
        elif ((line_rgb >= BORDER_WHITE_MIN).all(axis=1)).mean() >= BORDER_SOLID_FRACTION:
            pass
        else:
            break
        run = k + 1
    if run == 0 or run >= limit:
        return 0, has_alpha
    if not has_alpha and run < BORDER_WHITE_MIN_PX:
        return 0, False
    return run, has_alpha


def trim_borders(image):
    """RGBA 이미지에서 흰 여백/알파 0 테두리를 잘라 낸다.

    한 번에 네 변을 자르면 옆 테두리가 행/열 판정을 방해할 수 있어, 자른 결과에서 다시
    검사해 더 잘릴 것이 없을 때까지(최대 8회) 반복한다. 각 변 누적 자름은 원본 크기의
    25%를 넘지 않는다. (잘라낸 이미지, 변별 전체 px, 변별 흰 여백 px) 를 돌려준다.
    """
    import numpy as np
    arr = np.asarray(image.convert('RGBA'), dtype=np.int32)
    orig_h, orig_w = arr.shape[:2]
    total = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}
    white = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}
    for _ in range(8):
        height, width = arr.shape[:2]
        found = {
            'top': _cut_from_top(arr),
            'bottom': _cut_from_top(arr[::-1]),
            'left': _cut_from_top(np.transpose(arr, (1, 0, 2))),
            'right': _cut_from_top(np.transpose(arr[:, ::-1], (1, 0, 2))),
        }
        cuts = {side: value for side, (value, _alpha) in found.items()}
        # 누적 25% 상한. 넘으면 그 변은 이번에도 자르지 않는다.
        for side, size in (('top', orig_h), ('bottom', orig_h),
                           ('left', orig_w), ('right', orig_w)):
            if total[side] + cuts[side] > int(size * BORDER_MAX_CUT):
                cuts[side] = 0
        if not any(cuts.values()):
            break
        top, bottom, left, right = cuts['top'], cuts['bottom'], cuts['left'], cuts['right']
        if height - top - bottom < 1 or width - left - right < 1:
            break
        for side, value in cuts.items():
            total[side] += value
            if not found[side][1]:
                white[side] += value
        arr = arr[top:height - bottom, left:width - right]
    return image.crop((total['left'], total['top'],
                       image.width - total['right'], image.height - total['bottom'])), total, white


def tab_band_cut(image):
    """상단 공지 탭 띠를 감지해 잘라 낼 행 수를 돌려준다. (자를 행, 정보 dict)

    흰 여백을 자른 직후 이미지의 위쪽 20%만 본다. 사용자 결정(2026-11-13)에 따라 가운데
    30~70% 폭에 빨간 라벨(R>150,G<80,B<80)이 띠 형태로 있으면 탭을 자르지 않는다(남색 띠/NEW가
    있어도 보존). 빨간 라벨이 없고 남색 띠가 행 단위로 두껍게 있으면 그 띠만 자르고, NEW 노란
    글자가 남색 띠 경계보다 아래로 내려와 있으면 그 아래까지 자른다. 자르는 양은 높이의 22% 이내.
    """
    import numpy as np
    arr = np.asarray(image.convert('RGBA'), dtype=np.int32)
    height, width = arr.shape[:2]
    if height < 8 or width < 8:
        return 0, {'tab': False}
    top = max(1, int(height * TAB_SCAN_FRACTION))
    alpha = arr[:, :, 3] > 0
    red = ((arr[:, :, 0] > TAB_RED_MAX[0]) & (arr[:, :, 1] < TAB_RED_MAX[1])
           & (arr[:, :, 2] < TAB_RED_MAX[2]) & alpha)
    navy = ((np.abs(arr[:, :, :3] - np.array(TAB_NAVY)).max(axis=2) <= TAB_NAVY_DIST) & alpha)
    yellow = ((arr[:, :, 0] > TAB_YELLOW_MIN[0]) & (arr[:, :, 1] > TAB_YELLOW_MIN[1])
              & (arr[:, :, 2] < TAB_YELLOW_MIN[2]) & alpha)

    def merged_bands(flags):
        """flags(행별 bool)에서 짧은 끊김(<=TAB_GAP_ROWS)을 합친 (시작, 끝) 띠 목록."""
        runs = []
        start = last = None
        for y in range(top):
            if flags[y]:
                if start is None:
                    start = y
                last = y
            elif start is not None and y - last > TAB_GAP_ROWS:
                runs.append((start, last))
                start = last = None
        if start is not None:
            runs.append((start, last))
        return runs

    def band_end(flags, min_rows):
        """맨 위(8% 이내)에서 시작하는, 길이 min_rows 이상인 첫 띠의 마지막 행."""
        max_start = height * TAB_BAND_MAX_START
        for start, end in merged_bands(flags):
            if start > max_start:
                return None
            if end - start + 1 >= min_rows:
                return end
        return None

    def red_band_end():
        """빨간 라벨의 아래 경계. 흰 글자가 빨간 비율을 떨어뜨리는 구간은 support 하한으로 이어 붙인다."""
        core = red_rows
        max_start = height * TAB_BAND_MAX_START
        for start, end in merged_bands(core):
            if start > max_start:
                return None
            if end - start + 1 < TAB_RED_MIN_ROWS:
                continue
            y, gap = end, 0
            bridge = max(TAB_GAP_ROWS, int(height * TAB_RED_BRIDGE))
            while y + 1 < top:
                y += 1
                if red_support[y]:
                    end, gap = y, 0
                else:
                    gap += 1
                    if gap > bridge:
                        break
            return end
        return None

    rx0, rx1 = int(width * TAB_RED_CENTER[0]), int(width * TAB_RED_CENTER[1])
    red_center = red[:, rx0:rx1].mean(axis=1)
    red_rows = red_center >= TAB_RED_MIN_FRACTION
    red_support = red_center >= TAB_RED_SUPPORT
    (lx0, lx1), (rxx0, rxx1) = TAB_NAVY_SIDES
    navy_rows = ((navy[:, int(width * lx0):int(width * lx1)].mean(axis=1) >= TAB_NAVY_MIN_FRACTION)
                 & (navy[:, int(width * rxx0):int(width * rxx1)].mean(axis=1) >= TAB_NAVY_MIN_FRACTION))
    red_end = red_band_end()
    navy_end = band_end(navy_rows, TAB_NAVY_BAND_MIN_ROWS)

    yellow_end = None
    yw = max(1, int(width * TAB_YELLOW_WIDTH))
    yrows = [y for y in range(top) if yellow[y, :yw].mean() >= TAB_YELLOW_MIN_FRACTION]
    if yrows:
        yellow_end = max(yrows)

    # 사용자 결정(2026-11-13): 빨간 라벨이 감지되면 그 배너는 탭을 자르지 않는다(남색 띠/NEW가
    # 함께 있어도 보존). 빨간 라벨이 없고 남색 띠만 있으면 그 띠만 잘라 낸다.
    if red_end is not None:
        return 0, {'tab': False, 'red_label': True, 'red_end': red_end,
                   'navy_end': navy_end, 'yellow_end': yellow_end, 'cut': 0,
                   'height': height, 'capped': False}

    tab = navy_end is not None
    boundary = navy_end if navy_end is not None else -1
    if tab and yellow_end is not None:
        # NEW 배지는 남색 띠 경계보다 조금 아래까지 내려올 수 있다. 그 이상은 무시한다.
        boundary = max(boundary, min(yellow_end, boundary + int(height * TAB_NEW_EXTRA_FRACTION)))

    cut = boundary + 1 if boundary >= 0 else 0
    limit = int(height * TAB_MAX_CUT_FRACTION)
    capped = cut > limit
    if capped:
        cut = limit
    return cut, {'tab': bool(tab), 'red_label': False, 'red_end': None, 'navy_end': navy_end,
                 'yellow_end': yellow_end, 'cut': cut, 'height': height,
                 'capped': capped}


def _white_edge_fraction(image):
    """이미지 네 변 1px 줄에서 RGB 가 모두 240 이상인 픽셀 비율의 합(최소화 대상)."""
    import numpy as np
    arr = np.asarray(image.convert('RGBA'), dtype=np.int32)
    if arr.size == 0:
        return 1e9
    lines = (arr[0, :, :3], arr[-1, :, :3], arr[:, 0, :3], arr[:, -1, :3])
    return float(sum(((line >= 240).all(axis=1)).mean() for line in lines))


def fill_box(image, box=BOX):
    """잘라 낸 그림을 box 크기로 꽉 채운다. (채운 이미지, 크롭 비율, 방식) 을 돌려준다.

    원본과 상자의 비율 차이가 8% 이내면 비율을 무시하고 box 크기로 늘리거나 줄인다(LANCZOS).
    그보다 크면 cover 로 상자에 맞춘 뒤 넘치는 축을 최대 8%까지만 비틀어 줄이고, 그래도 남는
    부분을 가운데 기준으로 잘라 낸다. 가운데에서 ±3px 안쪽에 흰 1px 줄을 피하는 위치가 있으면
    그쪽으로 조금 치우쳐 자른다(테두리 제거 후 드러난 흰 줄이 상자 가장자리에 남지 않게).
    크롭 비율은 그 축에서 잘려 나간 비율이다.
    """
    import numpy as np
    bw, bh = box
    width, height = image.size
    if abs((width / height) / (bw / bh) - 1.0) <= ASPECT_STRETCH_TOL:
        return image.resize((bw, bh), Image.LANCZOS), 0.0, 'stretch'
    scale = max(bw / width, bh / height)
    # cover 로 맞추려면 잘라 내야 하는 비율. 15%를 넘으면 contain(비율 유지, 상자 중앙)으로 넣는다.
    if width * scale > bw:
        crop_needed = 1.0 - bw / (width * scale)
    else:
        crop_needed = 1.0 - bh / (height * scale)
    if crop_needed > CONTAIN_CROP_LIMIT:
        inner_scale = min(bw / width, bh / height)
        nw = max(1, int(round(width * inner_scale)))
        nh = max(1, int(round(height * inner_scale)))
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(image.resize((nw, nh), Image.LANCZOS), ((bw - nw) // 2, (bh - nh) // 2))
        return canvas, crop_needed, 'contain'
    scaled_w, scaled_h = width * scale, height * scale
    if scaled_w > bw:                    # 그림이 상자보다 넓다 -> 폭을 줄이고 가운데 크롭
        target_w = max(bw, scaled_w * (1.0 - COVER_DISTORT_LIMIT))
        resized = image.resize((max(bw, int(round(target_w))), bh), Image.LANCZOS)
        excess = resized.width - bw
        best, best_score = excess // 2, None
        for offset in range(max(0, excess // 2 - 3), min(excess, excess // 2 + 3) + 1):
            score = _white_edge_fraction(resized.crop((offset, 0, offset + bw, bh)))
            candidate = (score, abs(offset - excess / 2))
            if best_score is None or candidate < best_score:
                best, best_score = offset, candidate
        crop = excess / resized.width
        return resized.crop((best, 0, best + bw, bh)), crop, 'cover'
    if scaled_h > bh:                    # 그림이 상자보다 세로로 길다 -> 높이를 줄이고 가운데 크롭
        target_h = max(bh, scaled_h * (1.0 - COVER_DISTORT_LIMIT))
        resized = image.resize((bw, max(bh, int(round(target_h)))), Image.LANCZOS)
        excess = resized.height - bh
        best, best_score = excess // 2, None
        for offset in range(max(0, excess // 2 - 3), min(excess, excess // 2 + 3) + 1):
            score = _white_edge_fraction(resized.crop((0, offset, bw, offset + bh)))
            candidate = (score, abs(offset - excess / 2))
            if best_score is None or candidate < best_score:
                best, best_score = offset, candidate
        crop = excess / resized.height
        return resized.crop((0, best, bw, best + bh)), crop, 'cover'
    return image.resize((bw, bh), Image.LANCZOS), 0.0, 'stretch'


def _seal_edges(image, depth=8):
    """상자에 붙일 그림의 가장자리에 남은 반투명/투명 줄을 안쪽 색으로 덮는다.

    알파가 있는 원본(PNG)은 테두리를 잘라도 안티에일리어싱된 반투명 띠가 남고, cover 크롭이
    투명한 줄을 상자 가장자리로 끌어올 수 있다. 그러면 알파 bbox 가 상자보다 작아진다.
    바깥 1px 고리가 불투명해질 때까지 안쪽 줄 색을 복사해 그림이 상자를 꽉 채우게 한다.
    """
    import numpy as np
    arr = np.array(image.convert('RGBA'))
    height, width = arr.shape[:2]
    for k in range(1, min(depth, height, width)):
        for edge, source in ((arr[0], arr[k]), (arr[-1], arr[-1 - k]),
                             (arr[:, 0], arr[:, k]), (arr[:, -1], arr[:, -1 - k])):
            mask = edge[:, 3] < 255
            if mask.any():
                edge[mask] = source[mask]
    for edge in (arr[0], arr[-1], arr[:, 0], arr[:, -1]):
        edge[edge[:, 3] < 255, 3] = 255
    return Image.fromarray(arr, 'RGBA')


def _quantize_png8(canvas, keep_mask):
    """255색(FASTOCTREE, FLOYDSTEINBERG) PNG8 로 줄이고 keep_mask 바깥을 투명(255)으로 칠한다."""
    import numpy as np
    flat = canvas.quantize(colors=255, method=Image.Quantize.FASTOCTREE,
                           dither=Image.Dither.FLOYDSTEINBERG)
    palette = list(flat.getpalette() or [])
    palette = (palette + [0, 0, 0] * (256 - len(palette) // 3))[:768]
    indices = np.array(flat)
    indices[~keep_mask] = 255
    flat = Image.fromarray(indices, 'P')
    flat.putpalette(palette)
    flat.info['transparency'] = 255
    return flat


def _flood_bg(cand, forbidden, seed_mask=None):
    """바깥 네 변·네 모서리 및 추가 시드에서 4방향으로 연결된 배경 후보 픽셀을 찾는다(forbidden 내부는 보호)."""
    import numpy as np
    height, width = cand.shape
    bg = np.zeros((height, width), dtype=bool)
    queue = collections.deque()
    if seed_mask is not None:
        ys, xs = np.where(seed_mask)
        for y, x in zip(ys.tolist(), xs.tolist()):
            bg[y, x] = True
            queue.append((y, x))
    for y in range(height):
        for x in (0, width - 1):
            if cand[y, x] and not forbidden[y, x] and not bg[y, x]:
                bg[y, x] = True
                queue.append((y, x))
    for x in range(width):
        for y in (0, height - 1):
            if cand[y, x] and not forbidden[y, x] and not bg[y, x]:
                bg[y, x] = True
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < height and 0 <= nx < width and not bg[ny, nx]:
                if cand[ny, nx] and not forbidden[ny, nx]:
                    bg[ny, nx] = True
                    queue.append((ny, nx))
    return bg


def _finalize_png8(rgba, keep):
    """투명 영역 RGB 를 (0, 0, 0, 0) 으로 초기화하고 불투명 영역을 PNG8(인덱스 255 투명)로 양자화한다."""
    cleaned = rgba.copy()
    cleaned[~keep] = (0, 0, 0, 0)
    cleaned[keep, 3] = 255
    return _quantize_png8(Image.fromarray(cleaned, 'RGBA'), keep)


def _ribbon_core_mask():
    """상단 공지 리본 포함 배너의 기본 불투명 영역 마스크."""
    import numpy as np
    core = np.zeros((TARGET[1], TARGET[0]), dtype=bool)
    core[BOX_TOP:BOX_TOP + BOX[1], BOX_LEFT:BOX_LEFT + BOX[0]] = True
    if RIBBON_PLATE.is_file():
        with Image.open(RIBBON_PLATE) as plate:
            rib_alpha = np.asarray(plate.convert('RGBA'))[:, :, 3]
        core[:BOX_TOP] |= (rib_alpha[:BOX_TOP] >= 128)
    else:
        core[3:16, 154:487] = True
    return core


def normalize_banner_image(image):
    """영문판/트위터/공지 640x240 배너를 투명 여백 PNG8(인덱스 255 투명)로 정규화한다.

    이미 네 모서리가 투명(alpha == 0)인 PNG8 이면 None 을 돌려줘 원본 바이트를 유지한다.
    """
    import numpy as np
    if image.size != TARGET:
        flat, _cuts, _white, _crop, _mode, _tab = compose_banner(image.convert('RGBA'))
        return flat
    rgba = np.array(image.convert('RGBA'))
    alpha = rgba[:, :, 3]
    corners = (int(alpha[0, 0]), int(alpha[0, -1]), int(alpha[-1, 0]), int(alpha[-1, -1]))
    if max(corners) == 0:
        if image.mode == 'P' and isinstance(image.info.get('transparency'), int):
            return None
        return _finalize_png8(rgba, alpha >= 128)
    if max(corners) < 128:
        # 양자화 잔여 반투명 모서리(alpha 1..3): 불투명 픽셀을 침식하지 않고 PNG8 로 양자화한다.
        return _finalize_png8(rgba, alpha >= 128)

    rgb = rgba[:, :, :3]
    left_strip = rgb[:, :10]
    tl_strip = rgb[:12, :140]
    frac_black = ((left_strip.max(axis=2) <= 20).mean() + (tl_strip.max(axis=2) <= 20).mean()) / 2.0
    frac_white = ((left_strip.min(axis=2) >= 240).mean() + (tl_strip.min(axis=2) >= 240).mean()) / 2.0

    core = np.zeros((TARGET[1], TARGET[0]), dtype=bool)
    core[BOX_TOP:BOX_TOP + BOX[1], BOX_LEFT:BOX_LEFT + BOX[0]] = True
    has_ribbon = ((rgb[6:14, 200:440, 0] > 120) & (rgb[6:14, 200:440, 1] < 80)).mean() > 0.25
    if has_ribbon:
        core = _ribbon_core_mask()

    if frac_black >= 0.85:
        bg = _flood_bg(rgb.max(axis=2) <= 58, core)
        enclosed = (~core) & (rgb.max(axis=2) <= 35)
        keep = ~(bg | enclosed)
        return _finalize_png8(rgba, keep)

    if frac_white >= 0.85:
        diff = rgb.max(axis=2).astype(np.int32) - rgb.min(axis=2).astype(np.int32)
        bg = _flood_bg((diff <= 24) & (rgb.min(axis=2) >= 58), core)
        keep = ~bg
        if (rgb[225:238, 495:638].min(axis=2) < 55).sum() >= 50:
            # 747 등 하단 프레임 바로 아래에 붙은 ©SQUARE ENIX 스탬프와 흰 테두리 보존
            badge = np.zeros((TARGET[1], TARGET[0]), dtype=bool)
            badge[220:237, 500:630] = (rgb[220:237, 500:630].min(axis=2) < 120)
            for _ in range(2):
                dilated = badge.copy()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ys = slice(max(0, dy), min(TARGET[1], TARGET[1] + dy))
                        xs = slice(max(0, dx), min(TARGET[0], TARGET[0] + dx))
                        dilated[max(0, -dy):min(TARGET[1], TARGET[1] - dy),
                                max(0, -dx):min(TARGET[0], TARGET[0] - dx)] |= badge[ys, xs]
                badge = dilated
            keep |= badge
        return _finalize_png8(rgba, keep)

    # 여백 없이 640x240 전체가 찬 그림은 표준 몸통 영역(608x208)에 맞춰 외곽 16px을 비운다.
    inner = image.convert('RGBA').resize(BOX, Image.LANCZOS)
    canvas = Image.new('RGBA', TARGET, (0, 0, 0, 0))
    canvas.paste(inner, (BOX_LEFT, BOX_TOP))
    keep = np.zeros((TARGET[1], TARGET[0]), dtype=bool)
    keep[BOX_TOP:BOX_TOP + BOX[1], BOX_LEFT:BOX_LEFT + BOX[0]] = True
    return _quantize_png8(canvas, keep)


def save_normalized_banner(src, dst):
    """원본 배너 파일을 읽어 640x240 투명 여백 PNG8 로 dst 에 저장한다."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as image:
        normalized = normalize_banner_image(image)
        if normalized is None:
            if image.format == 'PNG':
                shutil.copyfile(src, dst)
            else:
                image.save(dst, format='PNG', optimize=True)
            return
    normalized.save(dst, format='PNG', optimize=True)


def overlay_silver_frame(image, plate_path=NAME_PLATE):
    """테두리가 없는 640x240 공지 배너 위에 일판 빈 판(spd_bn_list_dummy.png)의 은색 테두리와 코너 문양을 합성한다."""
    import numpy as np
    with Image.open(plate_path) as plate:
        dummy_rgb = np.array(plate.convert('RGBA'), dtype=np.float32)[:, :, :3]
    rgba = image.convert('RGBA')
    body = rgba.crop((BOX_LEFT, BOX_TOP, BOX_LEFT + BOX[0], BOX_TOP + BOX[1]))
    body = body.resize((BOX[0] - 16, BOX[1] - 16), Image.LANCZOS)
    canvas = Image.new('RGBA', TARGET, (0, 0, 0, 0))
    canvas.paste(body, (24, 24))
    out = np.array(canvas, dtype=np.float32)

    ring = np.zeros((TARGET[1], TARGET[0]), dtype=bool)
    ring[16:27, 16:624] = True
    ring[213:224, 16:624] = True
    ring[16:224, 16:27] = True
    ring[16:224, 613:624] = True
    out[ring, :3] = dummy_rgb[ring]
    out[ring, 3] = 255.0

    # dummy 내부 남색(0,0,70) 위 무채색 문양·외곽선(alpha*fg + (1-alpha)*(0,0,70))에서 alpha 와 premult R 추출
    for y0, y1, x0, x1 in ((27, 75, 27, 75), (165, 213, 565, 613)):
        sub_d = dummy_rgb[y0:y1, x0:x1]
        sub_o = out[y0:y1, x0:x1, :3]
        diff = sub_d[:, :, 2] - sub_d[:, :, 0]
        pure = diff <= 8
        alpha = np.clip((68.0 - diff) / 60.0, 0.0, 1.0)
        alpha[pure] = 1.0
        blended = (1.0 - alpha[:, :, None]) * sub_o + sub_d[:, :, 0:1]
        blended[pure] = sub_d[pure]
        out[y0:y1, x0:x1, :3] = blended
        out[y0:y1, x0:x1, 3] = 255.0

    keep = np.zeros((TARGET[1], TARGET[0]), dtype=bool)
    keep[BOX_TOP:BOX_TOP + BOX[1], BOX_LEFT:BOX_LEFT + BOX[0]] = True
    return _quantize_png8(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA'), keep)


def compose_banner(image, box=BOX, target=TARGET):
    """업스케일된 RGBA 이미지를 640x240 PNG8 배너로 만든다.

    테두리를 잘라 내고, 위쪽 공지 탭 띠가 있으면 잘라 낸 뒤 box 를 채운다. contain 으로 들어간
    그림은 바깥이 투명이어야 하므로 가장자리 밀봉(_seal_edges)을 하지 않는다. 상자 가운데
    (BOX_LEFT, BOX_TOP)에 붙이고 256색(FASTOCTREE, FLOYDSTEINBERG)으로 저장 가능한 P 모드로 만든다.
    (P 이미지, 변별 자른 px, 변별 흰 여백 px, 크롭 비율, 방식, 탭 정보) 을 돌려준다.
    """
    import numpy as np
    trimmed, cuts, white = trim_borders(image)
    tab_cut, tab_info = tab_band_cut(trimmed)
    if tab_cut:
        trimmed = trimmed.crop((0, tab_cut, trimmed.width, trimmed.height))
    inner, crop, mode = fill_box(trimmed, box)
    if mode != 'contain':
        inner = _seal_edges(inner)
    canvas = Image.new('RGBA', target, (0, 0, 0, 0))
    canvas.paste(inner, (BOX_LEFT, BOX_TOP))   # 빈 캔버스라 RGBA(원본 알파 포함)가 그대로 복사된다
    # 알파가 그라데이션인 PNG 는 256색 양자화에서 투명(0)이 1 등으로 뭉개져 바깥 여백이 불투명해진다.
    # 그래서 255색으로 줄이고 팔레트의 마지막 칸(255)을 투명 전용으로 붙여 바깥을 그 인덱스로 칠한다.
    keep = np.zeros((target[1], target[0]), dtype=bool)
    keep[BOX_TOP:BOX_TOP + BOX[1], BOX_LEFT:BOX_LEFT + BOX[0]] = True
    flat = _quantize_png8(canvas, keep)
    return flat, cuts, white, crop, mode, tab_info


def convert(src, dst, upscaled=None):
    """알테마 원본을 Real-ESRGAN 으로 4배 업스케일한 뒤 테두리를 잘라 내고 640x240 투명 캔버스의
    가운데 621x206 상자를 꽉 채워 PNG8(256색 팔레트)로 저장한다.

    WordPress 썸네일(-300x97.jpg)은 접미사를 뺀 원본이 같은 폴더에 있으면 그 원본을 쓴다.
    upscaled 가 주어지면(이미 4배 업스케일된 PNG) 새로 업스케일하지 않고 그 파일을 쓴다.
    """
    src = Path(src)
    if upscaled is None and THUMB_SUFFIX.search(src.name):
        original = src.with_name(THUMB_SUFFIX.sub(r'\1', src.name))
        if original.is_file():
            src = original
    if upscaled is not None:
        upscaled = Path(upscaled)
        if not upscaled.is_file():
            raise FileNotFoundError(str(upscaled))
        with Image.open(upscaled) as image:
            flat, _cuts, _white, _crop, _mode, _tab = compose_banner(image.convert('RGBA'))
    else:
        with tempfile.TemporaryDirectory() as workdir:
            upscaled = esrgan_upscale(src, workdir)
            with Image.open(upscaled) as image:
                flat, _cuts, _white, _crop, _mode, _tab = compose_banner(image.convert('RGBA'))
    dst.parent.mkdir(parents=True, exist_ok=True)
    flat.save(dst, format='PNG', optimize=True)


def _standin_ok(name, toc, reserved_names, reserved_sizes, size_counts):
    """A JP spd_*_bn_list file usable as a swap key: in the TOC, free, unique decoded size."""
    if not (name.startswith('spd_') and 'bn_list' in name):
        return False
    if name in reserved_names or name not in toc:
        return False
    size = toc[name][0]
    return size not in reserved_sizes and size_counts[size] == 1


def free_standins(toc, reserved_names, reserved_sizes, excluded=()):
    """Sorted (name, size, cpk) stand-ins no reservation or excluded (=already used) name claims."""
    size_counts = collections.Counter(size for size, _cpk in toc.values())
    skip = set(reserved_names) | set(excluded)
    pool = []
    for name, (size, cpk) in toc.items():
        if name in skip:
            continue
        if not _standin_ok(name, toc, reserved_names, reserved_sizes, size_counts):
            continue
        pool.append((name, size, cpk))
    pool.sort()
    return pool


def previous_standins(rels):
    """Undo the last run's stand-in map from jp_event_art.json / jp_banner_art.json.

    A stand-in entry has `path` = `<DEVICE_REL>/<sha1(rel)[:16]>.png` (Altema image) or
    `<DEVICE_REL>/name_<area>.png` (name plate). Returns
    (image rel -> stand-in, area -> stand-in, all art names, previous by_area, previous stand-in
    names). Every name in the old art maps is returned so a name that is no longer used is never
    handed to a different image, and the next run's allocation cannot shift.
    """
    rel_by_hash = {image_sha(rel): rel for rel in rels}
    by_image, by_name = {}, {}
    names, standin_names = set(), set()
    by_area_prev = {}
    documents = []
    for path in (EVENT_MAP, BANNER_MAP):
        if not path.is_file():
            continue
        try:
            documents.append(json.loads(path.read_text(encoding='utf-8')))
        except ValueError:
            continue
    for document in documents:
        for name, entry in (document.get('art') or {}).items():
            if not isinstance(entry, dict):
                continue
            names.add(name)
            device = str(entry.get('path') or '')
            if not device.startswith(DEVICE_REL + '/'):
                continue
            standin_names.add(name)
            base = device[len(DEVICE_REL) + 1:]
            stem = base[:-4] if base.endswith('.png') else base
            if stem.startswith('name_'):
                by_name.setdefault(stem[len('name_'):], name)
            elif len(stem) == 16 and stem in rel_by_hash:
                by_image.setdefault(rel_by_hash[stem], name)
        for area, banner in (document.get('by_area') or {}).items():
            by_area_prev.setdefault(str(area), banner)
    return by_image, by_name, names, by_area_prev, standin_names


def allocate_standins(toc, reserved_names, reserved_sizes, images, name_areas,
                      reuse_images=None, reuse_names=None, used_names=(), fresh=False):
    """(by_image, by_name, reused, new) stand-in assignments.

    Default: keep the last run's stand-in for the same Altema image / name plate when it is still
    free (not reserved, still in the TOC, still the only file with that decoded size), then give
    only the new images/areas the next sorted free names. `used_names` are excluded from the pool,
    so an old stand-in that is no longer used is never reassigned. `fresh` restores the old
    behaviour (no reuse, names handed out in sorted pool order).
    """
    size_counts = collections.Counter(size for size, _cpk in toc.values())
    by_image, by_name = {}, {}
    taken = set()
    pending = []                      # ('image', rel) / ('name', area) still needing a stand-in
    reused = 0
    if not fresh:
        for rel in images:
            name = (reuse_images or {}).get(rel)
            if (name and name not in taken
                    and _standin_ok(name, toc, reserved_names, reserved_sizes, size_counts)):
                by_image[rel] = (name, toc[name][0], toc[name][1])
                taken.add(name)
                reused += 1
            else:
                pending.append(('image', rel))
        for area in name_areas:
            name = (reuse_names or {}).get(area)
            if (name and name not in taken
                    and _standin_ok(name, toc, reserved_names, reserved_sizes, size_counts)):
                by_name[area] = (name, toc[name][0], toc[name][1])
                taken.add(name)
                reused += 1
            else:
                pending.append(('name', area))
    else:
        pending = [('image', rel) for rel in images] + [('name', area) for area in name_areas]
    excluded = set() if fresh else (set(used_names) | taken)
    pool = free_standins(toc, reserved_names, reserved_sizes, excluded=excluded)
    if len(pool) < len(pending):
        raise SystemExit('not enough free stand-in banners: %d < %d' % (len(pool), len(pending)))
    for (kind, key), (name, size, cpk) in zip(pending, pool):
        if kind == 'image':
            by_image[key] = (name, size, cpk)
        else:
            by_name[key] = (name, size, cpk)
    return by_image, by_name, reused, len(pending)


def clean_name(text):
    """<br> 같은 태그와 전각 공백(　)을 일반 공백으로 바꾸고 연속 공백을 하나로 줄인다."""
    text = TAG.sub(' ', str(text or '')).replace('　', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def load_ko_name_sources():
    """(names_pass 병합, names_pass + translated.json 병합).

    build/apply_ko_names.py 와 같은 순서·규칙: names_pass1 -> pass2 -> pass3 (먼저 나온 값 우선,
    setdefault) 다음에 translated.json 을 채운다.
    """
    names = {}
    for path in sorted(KO_NAMES.glob('names_pass[0-9].json')):
        for jp, ko in json.loads(path.read_text(encoding='utf-8')).items():
            names.setdefault(jp, ko)
    table = dict(names)
    for jp, ko in json.loads(KO_TRANSLATIONS.read_text(encoding='utf-8')).items():
        table.setdefault(jp, ko)
    return names, table


def known_name(table, value):
    """apply_ko_names.korean() 과 같은 ＠ 접미사 규칙으로 정확히 일치하는 번역을 찾는다."""
    base, at, rest = value.partition('＠')
    ko = table.get(value) or table.get(base.strip())
    if ko and at:
        return ko + at + rest
    return ko


def _common_prefix_ko(name_jp, key, ko):
    """name_jp 가 key 의 앞부분일 때, 한국어 값에서 대응하는 앞부분만 잘라 낸다.

    예: name_jp=ジャボテン砂漠, key=ジャボテン砂漠　入口, ko=점보텐 사막　입구 -> 점보텐 사막.
    """
    suffix = key[len(name_jp):]
    if not suffix:
        return ko
    target = len(ko) * len(name_jp) / float(len(key))
    cuts = [i for i, ch in enumerate(ko) if ch in NAME_SEPARATORS and i > 0]
    if cuts:
        cut = min(cuts, key=lambda i: abs(i - target))
        if abs(cut - target) <= 3 and ko[:cut].strip():
            return ko[:cut].strip()
    return ko[:max(1, int(round(target)))].strip() or ko


def prefix_name(name_jp, names):
    """정확 일치가 없을 때만 접두 일치. (한국어 공통 부분, 맞춘 일본어 키) 또는 (None, None)."""
    if not name_jp:
        return None, None
    shorter = [key for key in names if key.startswith(name_jp) and key != name_jp]
    if shorter:
        key = min(shorter, key=len)
        return _common_prefix_ko(name_jp, key, names[key]), key
    longer = [key for key in names if name_jp.startswith(key) and key != name_jp]
    if longer:
        key = max(longer, key=len)
        return names[key], key
    return None, None


def area_name_ko(name_jp, names, table):
    """(배너에 그릴 이름, 찾은 방법, 끝의 (배너) 접미를 지웠는지). 방법은 exact / prefix / none.

    정확 일치(＠ 규칙 포함) -> names_pass 접두 일치 -> 일본어 원문 순서. 마지막에 (배너)/(バナー)
    같은 판 표시 접미를 지운다.
    """
    value = str(name_jp or '')
    hit = known_name(table, value)
    if hit:
        text, how = clean_name(hit), 'exact'
    else:
        ko, _key = prefix_name(value, names)
        if ko:
            text, how = clean_name(ko), 'prefix'
        else:
            text, how = clean_name(value), 'none'
    removed = bool(NAME_SUFFIX.search(text))
    if removed:
        text = NAME_SUFFIX.sub('', text).strip()
    return text or clean_name(value), how, removed


def _text_metrics(draw, text, font, stroke):
    """(폭, 높이, bbox). 테두리 두께를 포함한 실제로 그려질 크기."""
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return box[2] - box[0], box[3] - box[1], box


def split_two_lines(text):
    """두 줄 분할점. '~', '-', '「' 같은 구분 기호가 있으면 그 앞을 우선하고, 없으면 가운데에
    가장 가까운 공백, 그것도 없으면 글자 중간에서 나눈다."""
    middle = len(text) / 2.0
    marks = [i for i, char in enumerate(text) if char in NAME_SPLIT_MARKS]
    if marks:
        cut = min(marks, key=lambda i: abs(i - middle))
        left, right = text[:cut].strip(), text[cut:].strip()
        if left and right:
            return [left, right]
    spaces = [i for i, char in enumerate(text) if char == ' ']
    if spaces:
        cut = min(spaces, key=lambda i: abs(i - middle))
        left, right = text[:cut].strip(), text[cut + 1:].strip()
        if left and right:
            return [left, right]
    cut = max(1, len(text) // 2)
    return [text[:cut].strip(), text[cut:].strip()]


def layout_name(draw, text):
    """(줄 목록, 글자 크기, 줄 수). 한 줄은 38px 이상일 때만 허용하고(44px 부터 시도), 그보다
    작아져야 들어가면 두 줄로 나눈다. 두 줄은 44px 부터 28px 까지 시도하고, 28px 에서도 넘치면
    그 크기로 둔다."""
    x0, y0, x1, y1 = NAME_TEXT_BOX
    max_w, max_h = x1 - x0, y1 - y0
    from PIL import ImageFont
    for size in range(NAME_FONT_START, NAME_SINGLE_MIN - 1, -1):
        stroke = NAME_STROKE if size >= 36 else NAME_STROKE_MIN
        font = ImageFont.truetype(str(KO_FONT), size)
        width, height, _box = _text_metrics(draw, text, font, stroke)
        if width <= max_w and height <= max_h:
            return [(text, font, stroke)], size, 1
    lines = split_two_lines(text)
    for size in range(NAME_FONT_START, NAME_FONT_MIN - 1, -1):
        stroke = NAME_STROKE if size >= 36 else NAME_STROKE_MIN
        font = ImageFont.truetype(str(KO_FONT), size)
        metrics = [_text_metrics(draw, line, font, stroke) for line in lines]
        if max(width for width, _h, _b in metrics) <= max_w and (
                sum(height for _w, height, _b in metrics) + NAME_LINE_GAP <= max_h):
            return [(line, font, stroke) for line in lines], size, 2
    stroke = NAME_STROKE_MIN
    font = ImageFont.truetype(str(KO_FONT), NAME_FONT_MIN)
    return [(line, font, stroke) for line in lines], NAME_FONT_MIN, 2


def draw_name_banner(name_ko, dst):
    """빈 판 위에 한국어 이름을 그려 640x240 PNG8(FASTOCTREE, 투명도 유지)로 저장한다.
    (그린 이름, 줄 수, 글자 크기) 를 돌려준다."""
    from PIL import ImageDraw
    import numpy as np
    with Image.open(NAME_PLATE) as plate_file:
        base = plate_file.convert('RGBA')
        base_alpha = np.asarray(base)[:, :, 3].copy()
    canvas = base.copy()
    draw = ImageDraw.Draw(canvas)
    lines, size, line_count = layout_name(draw, name_ko)
    x0, y0, x1, y1 = NAME_TEXT_BOX
    center_x = (x0 + x1) / 2.0
    metrics = [_text_metrics(draw, line, font, stroke) for line, font, stroke in lines]
    block_h = sum(height for _w, height, _b in metrics) + NAME_LINE_GAP * (line_count - 1)
    top = (y0 + y1) / 2.0 - block_h / 2.0
    for (line, font, stroke), (width, height, box) in zip(lines, metrics):
        draw.text((center_x - (box[0] + box[2]) / 2.0, top - box[1]), line, font=font,
                  fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(10, 12, 30, 255))
        top += height + NAME_LINE_GAP
    # 255색으로 줄이고 마지막 칸(255)을 투명 전용으로 쓴다(빈 판의 바깥 여백은 그대로 투명).
    flat = _quantize_png8(canvas, base_alpha >= 128)
    dst.parent.mkdir(parents=True, exist_ok=True)
    flat.save(dst, format='PNG', optimize=True)
    return name_ko, line_count, size


CHALLENGE_ICON_DIR = ROOT / 'inputs/challenge_icons'
CHALLENGE_BASE_BANNER = ROOT / 'inputs/jp_cpk_banners/spd_bn_top_00004.png'
CUSTOM_NAME_SPECS = {
    '902': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': ['unit_ills_903001102.png', 'unit_ills_903001502.png'],
        'quartz': True,
    },
    '903': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': ['unit_ills_903001202.png', 'unit_ills_903001602.png'],
        'quartz': True,
    },
    '904': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': ['unit_ills_903001302.png', 'unit_ills_903001102.png'],
        'quartz': True,
    },
    '905': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': ['unit_ills_903001402.png', 'unit_ills_903001202.png'],
        'quartz': True,
    },
    '930': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': [],
        'quartz': True,
    },
    '931': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': [],
        'quartz': True,
    },
    '932': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': [],
        'quartz': True,
    },
    '933': {
        'base': CHALLENGE_BASE_BANNER,
        'doors': [],
        'quartz': True,
    },
    '950': {
        'base': ROOT / 'inputs/jp_cpk_banners/spd_20221129_bn_kakera.png',
        'bubble_text': '출격한 NV 유닛의 조각 획득!',
    },
    '3288': {
        'base': ROOT / 'inputs/jp_cpk_banners/spd_20240411_bn_kakera_isekai.png',
        'bubble_text': '[이세계의 강자] 카테고리 한정',
    },
    '3298': {
        'base': ROOT / 'inputs/jp_cpk_banners/spd_20240930_bn_kakera_hanki.png',
        'bubble_text': '[반기를 든 자들] 카테고리 한정',
    },
    '3300': {
        'base': ROOT / 'inputs/jp_cpk_banners/spd_20250421_bn_kakera_crystal.png',
        'bubble_text': '[크리스탈의 가호] 카테고리 한정',
    },
    **{
        _area: {'prebuilt': ROOT / f'inputs/ko_custom_banners/name_{_area}.png'}
        for _area in (
            '3037', '3038', '403', '404',
            '312', '313', '314', '315',
            '3255', '3256', '3257',
            '3081', '3092', '3093',
        )
    },
}


def _composite_with_shadow(canvas, icon, pos):
    """배경 배너 위에서도 아이콘이 또렷하게 보이도록 얇은 어두운 그림자 후 알파 합성한다."""
    from PIL import ImageFilter
    x, y = pos
    alpha = icon.getchannel('A')
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(2.5))
    shadow = Image.new('RGBA', icon.size, (0, 0, 0, 0))
    black = Image.new('RGBA', icon.size, (8, 10, 20, 210))
    shadow.paste(black, (0, 0), shadow_alpha)
    canvas.alpha_composite(shadow, (x + 2, y + 2))
    canvas.alpha_composite(icon, (x, y))


def draw_custom_name_banner(spec, dst):
    """원본 배너 + 드랍 아이콘(도전의 방) 또는 부제 배너(야신 토멸전)를 640x240 PNG8로 저장한다."""
    if spec.get('prebuilt'):
        import shutil
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec['prebuilt'], dst)
        return (dst.name, 1, 0)
    from PIL import ImageDraw, ImageFont
    import numpy as np
    base_path = spec.get('base') or NAME_PLATE
    with Image.open(base_path) as plate_file:
        base = plate_file.convert('RGBA')
        base_alpha = np.asarray(base)[:, :, 3].copy()
    canvas = base.copy()

    if spec.get('base'):
        # 일본판 원본 도전의 방 배너 우측 말풍선 아래(y=122..160)의 하단 문구 위쪽 공간에 드랍 아이콘을 작게 나열한다.
        doors = spec.get('doors') or []
        if doors:
            for idx, dname in enumerate(doors):
                im = Image.open(CHALLENGE_ICON_DIR / dname).convert('RGBA')
                bbox = im.getbbox()
                if bbox:
                    im = im.crop(bbox)
                scale = 38.0 / max(im.height, 1)
                nw = max(1, int(round(im.width * scale)))
                nh = max(1, int(round(im.height * scale)))
                im = im.resize((nw, nh), Image.Resampling.LANCZOS)
                px = 396 + idx * 42 + max(0, (38 - nw) // 2)
                py = 122 + max(0, (38 - nh) // 2)
                _composite_with_shadow(canvas, im, (px, py))
            if spec.get('quartz'):
                qim = Image.open(CHALLENGE_ICON_DIR / 'item_9216.png').convert('RGBA')
                qbbox = qim.getbbox()
                if qbbox:
                    qim = qim.crop(qbbox)
                qim = qim.resize((34, 34), Image.Resampling.LANCZOS)
                _composite_with_shadow(canvas, qim, (480, 125))
        elif spec.get('quartz'):
            qim = Image.open(CHALLENGE_ICON_DIR / 'item_9216.png').convert('RGBA')
            qbbox = qim.getbbox()
            if qbbox:
                qim = qim.crop(qbbox)
            qim = qim.resize((38, 38), Image.Resampling.LANCZOS)
            _composite_with_shadow(canvas, qim, (436, 122))
        bubble_text = spec.get('bubble_text')
        if bubble_text:
            draw = ImageDraw.Draw(canvas, 'RGBA')
            b_size = 21
            while b_size >= 14:
                bfont = ImageFont.truetype(str(KO_FONT), b_size)
                bb = draw.textbbox((0, 0), bubble_text, font=bfont, stroke_width=1)
                if (bb[2] - bb[0]) <= 320:
                    break
                b_size -= 1
            bx = 353.0 - (bb[0] + bb[2]) / 2.0
            by = 172.0 - (bb[1] + bb[3]) / 2.0
            draw.text((bx, by), bubble_text, font=bfont, fill=(52, 30, 14, 255),
                      stroke_width=1, stroke_fill=(255, 250, 236, 220))
        meta = (dst.name, 1, 0)
    else:
        draw = ImageDraw.Draw(canvas, 'RGBA')
        text_x0, text_x1 = 32, 604
        center_x = (text_x0 + text_x1) / 2.0
        title = spec['title']
        t_size = 42
        while t_size >= 24:
            tfont = ImageFont.truetype(str(KO_FONT), t_size)
            tb = draw.textbbox((0, 0), title, font=tfont, stroke_width=4)
            if (tb[2] - tb[0]) <= (text_x1 - text_x0 - 8):
                break
            t_size -= 1

        subs = spec.get('sub') or []
        s_size = 28
        sfont = ImageFont.truetype(str(KO_FONT), s_size)

        tb = draw.textbbox((0, 0), title, font=tfont, stroke_width=4)
        th = tb[3] - tb[1]
        s_metrics = [draw.textbbox((0, 0), s, font=sfont, stroke_width=3) for s in subs]
        sh_total = sum(b[3] - b[1] for b in s_metrics) + (6 * max(0, len(subs) - 1))
        divider_gap = 20
        total_h = th + divider_gap + sh_total
        top_y = 120 - total_h / 2.0

        tx = center_x - (tb[0] + tb[2]) / 2.0
        ty = top_y - tb[1]
        draw.text((tx, ty), title, font=tfont, fill=(255, 255, 255, 255),
                  stroke_width=4, stroke_fill=(10, 12, 30, 255))

        div_y = int(round(top_y + th + divider_gap / 2.0))
        line_half = int((text_x1 - text_x0) * 0.43)
        draw.line([(int(center_x) - line_half, div_y), (int(center_x) + line_half, div_y)],
                  fill=(215, 180, 95, 200), width=2)

        cur_y = top_y + th + divider_gap
        for s, sb in zip(subs, s_metrics):
            sx = center_x - (sb[0] + sb[2]) / 2.0
            sy = cur_y - sb[1]
            draw.text((sx, sy), s, font=sfont, fill=(255, 232, 155, 255),
                      stroke_width=3, stroke_fill=(10, 12, 30, 255))
            cur_y += (sb[3] - sb[1]) + 6
        meta = (title, 1 + len(subs), t_size)

    flat = _quantize_png8(canvas, base_alpha >= 128)
    dst.parent.mkdir(parents=True, exist_ok=True)
    flat.save(dst, format='PNG', optimize=True)
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='print the plan; write nothing')
    parser.add_argument('--fresh', action='store_true',
                        help="do not reuse the previous run's stand-ins (old sorted-pool allocation)")
    parser.add_argument('--reuse-banners', action='store_true',
                        help='keep the composed PNGs already in the banner folder; do not run ESRGAN')
    parser.add_argument('--esrgan-cache', metavar='DIR',
                        help='reuse precomputed <sha1>.png 4x upscales from DIR instead of running ESRGAN')
    parser.add_argument('--originals', metavar='TSV', default=str(ORIGINALS_TSV),
                        help='areas kept on their JP CPK banner (area/banner/score/name_jp TSV)')
    parser.add_argument('--demote', metavar='TSV', default=str(DEMOTE_TSV),
                        help='areas whose JP CPK banner was picked by date only; send them to Altema/name banners')
    parser.add_argument('--exclude-images', metavar='TXT', default=str(EXCLUDE_IMAGES_TXT),
                        help='non-banner Altema images (sha16 per line) to exclude, on top of EXCLUDED_IMAGES')
    parser.add_argument('--x-banners', metavar='TSV', default=str(X_BANNERS_TSV),
                        help='area/file rows: 640x240 Twitter(FFRS_JP) banners for areas without a CPK original')
    parser.add_argument('--x-dir', metavar='DIR', default=str(X_BANNER_SRC),
                        help='folder holding the 640x240 Twitter banner PNGs')
    args = parser.parse_args()

    toc = load_toc()
    if NEUTRAL not in toc:
        raise SystemExit('neutral banner %s is missing from %s' % (NEUTRAL, TOC))
    served = load_served()
    v4_areas = json.loads(BANNER_V4.read_text(encoding='utf-8'))['areas']
    gacha = json.loads(BANNER_MAP.read_text(encoding='utf-8')).get('art') if BANNER_MAP.is_file() else {}
    gacha = gacha or {}

    # 1) per-area intent: the JP CPK assignments the v4 rule already resolved (the live 188), then
    # the Altema layer for every other served area. Deriving the 188 from v4 (not from the previous
    # JSON) keeps a from-scratch regeneration identical.
    kept_banners = {}
    for area in sorted(served, key=int):
        banner, _category = choose((v4_areas.get(area) or {}).get('v4') or {}, toc)
        if banner != NEUTRAL:
            kept_banners[area] = banner
    kept_names = set(kept_banners.values())
    # 1a) 원본 유지 목록: v4/알테마 판정과 무관하게 그 구역을 일판 CPK 원본 배너로 고정한다.
    original_rows = load_original_banners(args.originals)
    originals_applied = 0
    originals_not_served = 0
    originals_not_in_toc = []          # (area, banner, name_jp): TOC 에 없어 덮어쓰지 않은 행
    for area, banner, name_jp in original_rows:
        if area not in served:
            originals_not_served += 1
            continue
        if banner not in toc:
            originals_not_in_toc.append((area, banner, name_jp))
            continue
        kept_banners[area] = banner
        originals_applied += 1
    # 1a') 날짜만으로 원본이 붙은 구역은 v4 배정을 버리고 알테마(없으면 이름 배너)로 보낸다.
    #      원본 유지 목록(--originals)에 있는 구역은 내리지 않는다.
    original_areas = {area for area, _b, _n in original_rows}
    #      TSV 열: area / to(altema|name) / name_jp / note. to=name 이면 알테마도 건너뛰고 이름 배너로 보낸다.
    demoted = 0
    force_name = set()
    if args.demote and Path(args.demote).is_file():
        with open(args.demote, encoding='utf-8') as fh:
            for row in csv.DictReader(fh, delimiter='	'):
                area = str(row.get('area') or '').strip()
                to = (row.get('to') or '').strip()
                if not area or (area in original_areas and to != 'name'):
                    continue
                if kept_banners.pop(area, None) is not None:
                    demoted += 1
                if to == 'name':
                    force_name.add(area)
    # 직접 제작한 커스텀 배너(도전의 방·조각의 시련·야신 토멸전 등)는 원본 유지 목록보다 우선한다.
    for area in CUSTOM_NAME_SPECS:
        kept_banners.pop(area, None)
    print('demote %d areas from date-only JP banners, %d forced to name banners (%s)' % (
        demoted, len(force_name), args.demote))
    # 원본 유지로 새로 예약된 배너 이름. 이 이름이 예전에 다른 그림의 대역이었으면 그 그림은
    # reserved_names 때문에 재사용에 실패하고 새 대역을 받는다(allocate_standins).
    originals_new_names = set(kept_banners.values()) - kept_names
    # 1b) 비배너 제외 목록: EXCLUDED_IMAGES 와 합집합으로 쓴다.
    extra_excluded = load_excluded_hashes(args.exclude_images)
    excluded_images = set(EXCLUDED_IMAGES) | extra_excluded
    altema = {}                       # area -> {'image': rel, 'tier', 'altema_name'}
    x_banners = load_x_banners(args.x_banners, args.x_dir)   # area -> file name
    skipped = []                      # (area, name_jp, reason)
    for area in sorted(served, key=int):
        if area in kept_banners or area in CUSTOM_NAME_SPECS:
            continue
        record = v4_areas.get(area) or {}
        if area in GL_EXCEPTIONS and gl_src(GL_EXCEPTIONS[area]).is_file():
            altema[area] = {'image': GL_PREFIX + GL_EXCEPTIONS[area], 'tier': 'global', 'altema_name': None}
            continue
        if area in force_name:
            skipped.append((area, record.get('name_jp'), 'forced name banner (demote list)'))
            continue
        if area in x_banners:
            # 트위터 공식 배너(이미 640x240 게임 규격)가 알테마 그림·이름판 강제보다 먼저다.
            altema[area] = {'image': X_PREFIX + x_banners[area], 'tier': 'twitter', 'altema_name': None}
            continue
        if area in ALTEMA_OVERRIDES:
            rel = ALTEMA_OVERRIDES[area]
            if not (IMG_DIR / rel).is_file():
                skipped.append((area, record.get('name_jp'), 'image missing: %s' % rel))
                continue
            altema[area] = {'image': rel, 'tier': 'manual',
                            'altema_name': (record.get('v4') or {}).get('altema_name')}
            continue
        target = altema_target(record)
        if not target:
            continue
        url, tier = target
        rel = image_rel_url(url)
        if not rel or not (IMG_DIR / rel).is_file():
            skipped.append((area, record.get('name_jp'), 'image missing: %s' % rel))
            continue
        if image_sha(rel) in excluded_images:
            skipped.append((area, record.get('name_jp'), 'excluded non-banner: %s' % rel))
            continue
        altema[area] = {'image': rel, 'tier': tier,
                        'altema_name': (record.get('v4') or {}).get('altema_name')}

    images = sorted({entry['image'] for entry in altema.values()})
    print('served %d; kept %d; altema areas %d; distinct images %d; skipped %d' % (
        len(served), len(kept_banners), len(altema), len(images), len(skipped)))
    print('originals %d rows: applied %d, not served %d, not in TOC %d' % (
        len(original_rows), originals_applied, originals_not_served, len(originals_not_in_toc)))
    for row in originals_not_in_toc[:10]:
        print('  originals ignored (banner not in TOC): %s %s %s' % row)
    if extra_excluded:
        print('exclude-images: %d sha16 from %s (built-in EXCLUDED_IMAGES %d)' % (
            len(extra_excluded), args.exclude_images, len(EXCLUDED_IMAGES)))
    if skipped:
        for row in skipped[:10]:
            print('  skip %s %s (%s)' % row)

    # 2) convert one PNG per distinct image.
    converted = {}                    # area-image rel -> output file name
    conversion_failures = []
    for rel in images:
        name = image_sha(rel) + '.png'
        converted[rel] = name
        dst = BANNER_DIR / name
        if args.dry_run:
            continue
        if rel.startswith(GL_PREFIX):
            # 영문판 예외·보강 배너도 640x240 외곽 투명 PNG8 규격으로 맞춘다.
            if not dst.is_file():
                save_normalized_banner(gl_src(rel[len(GL_PREFIX):]), dst)
            continue
        if rel.startswith(X_PREFIX):
            # 트위터 배너도 JPEG/비정규 PNG 를 640x240 외곽 투명 PNG8 로 맞춘다.
            if not dst.is_file():
                save_normalized_banner(Path(args.x_dir) / rel[len(X_PREFIX):], dst)
            continue
        if args.reuse_banners:
            # Keep the already composed PNG byte-for-byte; re-running ESRGAN would only reproduce it.
            if not dst.is_file():
                conversion_failures.append((rel, 'composed banner missing: %s' % name))
                converted.pop(rel, None)
            continue
        cached = (Path(args.esrgan_cache) / name) if args.esrgan_cache else None
        try:
            convert(IMG_DIR / rel, dst, upscaled=cached)
        except Exception as exc:      # decode errors
            conversion_failures.append((rel, '%s: %s' % (type(exc).__name__, exc)))
            converted.pop(rel, None)
    # areas whose image failed to convert fall back to neutral
    for area in list(altema):
        if altema[area]['image'] not in converted:
            skipped.append((area, altema[area]['altema_name'], 'conversion failed'))
            altema.pop(area)
    unique_images = sorted(converted)

    # 2b) 그림이 없는 구역: 일판 빈 판 위에 한국어 구역 이름을 그린 배너를 구역마다 하나 만든다.
    name_areas = [area for area in sorted(served, key=int)
                  if area not in kept_banners and area not in altema]
    name_sources, ko_table = load_ko_name_sources() if name_areas else ({}, {})
    names_ko = {}
    untranslated = []                    # (area, name_jp): Japanese left as-is
    prefix_hits = []                     # (area, name_jp): Korean came from a prefix match
    suffix_removed = 0                   # names whose (배너)/(バナー) suffix was dropped
    for area in name_areas:
        name_jp = (v4_areas.get(area) or {}).get('name_jp')
        text, how, had_suffix = area_name_ko(name_jp, name_sources, ko_table)
        names_ko[area] = text or str(area)
        suffix_removed += int(had_suffix)
        if how == 'prefix':
            prefix_hits.append((area, name_jp))
        elif how == 'none':
            untranslated.append((area, name_jp))
    name_files = {}                   # area -> output file name
    name_meta = {}                    # area -> (그린 이름, 줄 수, 글자 크기)
    name_failures = []
    for area in list(name_areas):
        out = 'name_%s.png' % area
        name_files[area] = out
        if args.dry_run:
            continue
        try:
            if area in CUSTOM_NAME_SPECS:
                name_meta[area] = draw_custom_name_banner(CUSTOM_NAME_SPECS[area], BANNER_DIR / out)
            else:
                name_meta[area] = draw_name_banner(names_ko[area], BANNER_DIR / out)
        except Exception as exc:      # font/plate problems: leave the area neutral
            name_failures.append((area, '%s: %s' % (type(exc).__name__, exc)))
            name_files.pop(area, None)
            name_areas.remove(area)
    print('name banner names: exact %d, prefix %d, untranslated %d, suffix removed %d' % (
        len(name_areas) - len(prefix_hits) - len(untranslated), len(prefix_hits),
        len(untranslated), suffix_removed))
    if untranslated:
        print('  untranslated (e.g. %s)' % (
            ', '.join(str(name) for _area, name in untranslated[:5])))
    if not args.dry_run:
        NAME_MISSING.parent.mkdir(parents=True, exist_ok=True)
        with open(NAME_MISSING, 'w', encoding='utf-8', newline='') as fh:
            writer = csv.writer(fh, delimiter='\t', lineterminator='\n')
            writer.writerow(['area', 'name_jp'])
            for area, name_jp in untranslated:
                writer.writerow([area, name_jp])

    # 3) one stand-in JP banner per distinct image (unique decoded byte size). Reserve every name
    # another screen resolves directly (kept by_area values, seal room art, safety list) and every
    # size a swap key would collide with (gacha feed, current map).
    reserved_names = set(kept_banners.values()) | set(SAFE_ART) | referenced_banner_names()
    reserved_sizes = set()
    for name in reserved_names:
        if name in toc:
            reserved_sizes.add(toc[name][0])
        entry = gacha.get(name) or {}
        if isinstance(entry.get('size'), int):
            reserved_sizes.add(entry['size'])
    for entry in gacha.values():
        if isinstance(entry.get('size'), int) and not str(entry.get('path') or '').startswith(DEVICE_REL):
            reserved_sizes.add(entry['size'])
    # Reuse the previous run's stand-in for the same image/area so one added image cannot shift every
    # later assignment; only new images/areas take a free name, images first then name plates.
    if args.fresh:
        reuse_images, reuse_names, previous_names = {}, {}, set()
        previous_by_area, previous_standins_set = {}, set()
    else:
        reuse_images, reuse_names, previous_names, previous_by_area, previous_standins_set = (
            previous_standins(unique_images))
    by_image, by_name, reused, new_standins = allocate_standins(
        toc, reserved_names, reserved_sizes, unique_images, name_areas,
        reuse_images=reuse_images, reuse_names=reuse_names,
        used_names=previous_names, fresh=args.fresh)
    # 원본 유지로 배너 이름이 예약되면서, 그 이름을 대역으로 쓰던 그림이 새 대역을 받은 수.
    displaced_images = 0
    if not args.fresh and originals_new_names:
        displaced_images = sum(1 for rel in unique_images
                               if reuse_images.get(rel) in originals_new_names)

    # 4) compose the maps.
    by_area = {}
    art = {}
    categories = collections.Counter()
    for area in sorted(served, key=int):
        if area in kept_banners:
            banner = kept_banners[area]
            categories['kept JP CPK banner'] += 1
            art.setdefault(banner, {'size': toc[banner][0], 'cpk': toc[banner][1]})
        elif area in altema:
            rel = altema[area]['image']
            name, size, cpk = by_image[rel]
            out = converted[rel]
            banner = name
            art[name] = {'size': size, 'cpk': cpk, 'path': DEVICE_REL + '/' + out}
            categories['altema ' + altema[area]['tier']] += 1
        elif area in name_files:
            name, size, cpk = by_name[area]
            banner = name
            art[name] = {'size': size, 'cpk': cpk, 'path': DEVICE_REL + '/' + name_files[area]}
            categories['name banner'] += 1
        else:
            banner = NEUTRAL
            categories['neutral'] += 1
        by_area[area] = banner
    art.setdefault(NEUTRAL, {'size': toc[NEUTRAL][0], 'cpk': toc[NEUTRAL][1]})

    missing = [name for name in art if name not in toc]
    if missing:
        raise SystemExit('banners missing from the JP CPK TOC: %r' % (missing,))

    # Version stamp shared by the engine table (app.imy) and the device table (files/exvius): the
    # engine prints it and jp_offline.js logs it, so a stale pair is visible in the logs at once.
    # Same inputs -> same stamp; it does not feed back into the stand-in allocation.
    canonical = json.dumps({'by_area': by_area, 'art': art}, sort_keys=True)
    stamp = hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:12]

    document = {
        'version': 3,
        'stamp': stamp,
        'note': 'build/make_jp_event_art.py; JP spdungeon CPK banners (real or stand-in) plus Altema '
                'wiki images for areas without one. jp_compat reads by_area; art.path is the Frida '
                'size-keyed swap source. by_global is the legacy (empty) map.',
        'neutral': NEUTRAL,
        'neutral_note': NEUTRAL_NOTE,
        'art': art,
        'by_area': by_area,
        'by_global': {},
    }
    summary = {
        'served': len(by_area),
        'event_banners': sum(1 for value in by_area.values() if value != NEUTRAL),
        'neutral': sum(1 for value in by_area.values() if value == NEUTRAL),
        'distinct_banners': len(art),
        'generated_banners': len(unique_images),
        'name_banners': len(name_files),
        'name_banners_prefix': len(prefix_hits),
        'name_banners_untranslated': len(untranslated),
        'name_banners_suffix_removed': suffix_removed,
        'name_banners_two_lines': sum(1 for meta in name_meta.values() if meta[1] >= 2),
        'categories': dict(sorted(categories.items())),
        'skipped': len(skipped),
        'originals_applied': originals_applied,
        'originals_not_served': originals_not_served,
        'originals_not_in_toc': len(originals_not_in_toc),
        'excluded_sha16_extra': len(extra_excluded),
        'displaced_images': displaced_images,
        'conversion_failures': conversion_failures,
        'name_failures': name_failures,
    }
    print(json.dumps(summary, ensure_ascii=False))
    changed = sum(1 for area, banner in by_area.items()
                  if previous_by_area.get(area) != banner
                  and (area in altema or area in name_files
                       or previous_by_area.get(area) in previous_standins_set))
    print('대역 재사용 %d, 신규 %d, 대역 바뀐 구역 %d, 원본 유지로 밀려 새 대역 %d' % (
        reused, new_standins, changed, displaced_images))
    if args.dry_run:
        return

    EVENT_MAP.write_text(json.dumps(document, ensure_ascii=False, indent=0, sort_keys=True) + '\n',
                         encoding='utf-8')

    banners = json.loads(BANNER_MAP.read_text(encoding='utf-8')) if BANNER_MAP.is_file() else {'art': {}}
    art_map = banners.get('art') or {}
    removed = sorted(key for key, entry in art_map.items()
                     if str(entry.get('global') or '').startswith('event_')
                     and str(entry.get('global') or '').endswith('.png'))
    for key in removed:
        art_map.pop(key)
    # Drop the previous generation first: the stand-in names are recomputed from the current inputs.
    for key in [k for k, v in art_map.items() if str(v.get('path') or '').startswith(DEVICE_REL)]:
        art_map.pop(key)
    # Generated banners: the Frida feeder (build/frida/jp_offline.js) keys Image::initWithImageData
    # by decoded byte size, so the entry needs the stand-in size and the on-device path.
    for name, entry in art.items():
        if 'path' in entry:
            art_map[name] = {'global': name, 'path': entry['path'], 'size': entry['size']}
    # Keep every other top-level key (build/make_jp_banners.py owns `art` entries for gacha art; it
    # rewrites this file from its own feed, and only this generator adds `stamp`).
    banners['art'] = art_map
    banners['stamp'] = stamp
    BANNER_MAP.write_text(json.dumps(banners, ensure_ascii=False, indent=0, sort_keys=True),
                          encoding='utf-8')

    with open(ASSIGN_TSV, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh, delimiter='\t', lineterminator='\n')
        writer.writerow(['area', 'name_jp', 'kind', 'tier', 'altema_name', 'image', 'banner', 'size'])
        for area in sorted(by_area, key=int):
            record = v4_areas.get(area) or {}
            entry = altema.get(area)
            if entry:
                name, size, _cpk = by_image[entry['image']]
                writer.writerow([area, record.get('name_jp'), 'altema', entry['tier'],
                                 entry['altema_name'], entry['image'], name, size])
            elif area in kept_banners:
                writer.writerow([area, record.get('name_jp'), 'jp_cpk', '', '', '', by_area[area],
                                 toc[by_area[area]][0]])
            elif area in name_files:
                writer.writerow([area, record.get('name_jp'), 'name', '', '', '', by_area[area],
                                 toc[by_area[area]][0]])
            else:
                writer.writerow([area, record.get('name_jp'), 'neutral', '', '', '', NEUTRAL,
                                 toc[NEUTRAL][0]])

    print('wrote', EVENT_MAP, BANNER_MAP, ASSIGN_TSV, sep='\n  ')
    print('removed English event stand-ins from %s: %d (left %d)' % (
        BANNER_MAP.name, len(removed), len(art_map)))

    # jp_art_dims.json (build/make_jp_art_dims.py) must cover every stand-in in the map just written;
    # it reads jp_banner_art.json + the JP TOC + the decrypted static tree (no network).
    dims = subprocess.run([sys.executable, '-I', '-X', 'utf8',
                           str(ROOT / 'build/make_jp_art_dims.py')], cwd=str(ROOT))
    if dims.returncode:
        print('WARN make_jp_art_dims.py exited %d; %s may be stale' % (
            dims.returncode, OVERLAY / 'jp_art_dims.json'))


if __name__ == '__main__':
    main()

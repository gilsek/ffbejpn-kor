#!/usr/bin/env python3
"""124개 시즌/콜라보 가챠 배너의 고유 그림(덤프/트위터/카드) 생성 및 자리표시자·오버레이 갱신."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date as _date
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build'

OVERLAY = BUILD / 'engine_overlay'
STATIC_DIR = BUILD / 'out/jp_offline/engine/static'
UNIT_CPKS = BUILD / 'out/challenge/unitcpk'
BANNERISH = ('gacha_', 'spd_', 'banner_', 'homeBanner', 'bn_')
GACHA_JP = BUILD / 'out/jp_offline/gacha_jp'
GACHA_OUT = BUILD / 'out/jp_offline/gacha'
SEASON_ART_DIR = GACHA_OUT / 'season_art'
TWITTER_DIR = Path('D:/Archive/gallery-dl/twitter/FFRS_JP')
DUMP_DIR = (
    ROOT
    / 'inputs/discord/_r_FFBraveExvius - FFBE-Japan - data_assets_dump [705109657517031591].json_Files/gacha'
)
DUMP_HASH_RX = re.compile(r'-[0-9a-f]{16}(\.\w+)$', re.I)
DUMP_TOP_RX = re.compile(r'^gacha_(\d{8})_(.+)_top\.png$', re.I)
DUMP_SKIP_STEM_RX = re.compile(
    r'(?:^|_)(?:1500|1500_01|1500_02|exchange\d*|box|event_box|raid_box|vision_box|'
    r'free|daily|omake|ticket\d*|spticket|nvticket\d*|kakera|nvkakera\d*|kakutei|nvkakutei|'
    r'r\d+_kakutei|30percent|allnv|nv\d+|coin|shukusaiseki|'
    r'select|cp|campaign|anniv|countdown|thank|darkvisions|dv|vc|vision|master|'
    r'crown|leader|element|cgl|story|season|newyear|xmas|valentine|whiteday|'
    r'summer|gw|golden|special|nvspecial|summon|eomsp)(?:_|$)',
    re.I,
)
UMBRELLA_FF_TOPS = {
    'gacha_20230511_FF_pickup_top.png',
    'gacha_20230612_FF_pickup1_top.png',
    'gacha_20230612_FF_pickup2_top.png',
    'gacha_20230620_FF_pickup_top.png',
}
EXPLICIT_DUMP_SERIES: dict[str, str] = {
    'gacha_20240111_saga_pickup1_top.png': 'RomancingSa・Ga2',
    'gacha_20240111_saga_pickup2_top.png': 'RomancingSa・Ga',
    'gacha_20240111_saga_pickup3_top.png': 'RomancingSa・Ga3',
    'gacha_20240119_saga_pickup1_top.png': 'SaGa Frontier',
    'gacha_20240119_saga_pickup2_top.png': 'SaGa Frontier2',
    'gacha_20220411_seiken_pickup_top.png': '聖剣伝説',
    'gacha_20230720_seiken_pickup1_top.png': '聖剣伝説2',
    'gacha_20230720_seiken_pickup2_top.png': '聖剣伝説2',
    'gacha_20210219_stepup_seiken3_top.png': '聖剣伝説3',
    'gacha_20211119_FF13_reprint_02_top.png': 'LR FF13',
    'gacha_20230410_FF13_reprint_top.png': 'LR FF13',
    'gacha_20230612_FF_pickup1_top.png': 'FF6',
    'gacha_20230612_FF_pickup2_top.png': 'FFV',
    'gacha_20230620_FF_pickup_top.png': 'FFIV',
    'gacha_20230511_FF_pickup_top.png': 'FFI',
    'gacha_20240620_SO2_pickup1_top.png': 'SO2R',
    'gacha_20240620_SO2_pickup2_top.png': 'SO2',
    'gacha_20241227_SO2_pickup1_top.png': 'SO2R',
    'gacha_20241227_SO2_pickup2_top.png': 'SO2',
}
SERIES_DUMP_TOKENS: dict[str, list[str]] = {
    'FFBE': ['FFBE'],
    'FFI': ['FF1'],
    'FFII': ['FF2'],
    'FFIII': ['FF3'],
    'FFIV': ['FF4'],
    'FFV': ['FF5'],
    'FF6': ['FF6'],
    'FFVII': ['FF7', 'FF7R'],
    'FFVIII': ['FF8'],
    'FFIX': ['FF9'],
    'FFX': ['FF10'],
    'FFX-2': ['FF10-2'],
    'FF11': ['FF11'],
    'FFXII': ['FF12'],
    'FF13': ['FF13'],
    'FF13-2': ['FF13-2'],
    'LR FF13': ['LRFF13'],
    'FF14': ['FF14'],
    'FF15': ['FF15'],
    'FF16': ['FF16'],
    'FFT': ['FFT'],
    'FF零式': ['FF0', 'zero'],
    'FFBE幻影戦争': ['WOTV', 'genei'],
    'CCFF7': ['CCFF7', 'CCFF7R'],
    'FF4TA': ['FF4TA'],
    'FF7AC': ['FF7AC'],
    '聖剣伝説': [],
    '聖剣伝説2': [],
    '聖剣伝説3': ['seiken3'],
    '聖剣伝説LoM': ['LoM', 'LOM'],
    '聖剣伝説 VoM': ['VoM'],
    'RomancingSa・Ga': [],
    'RomancingSa・Ga2': [],
    'RomancingSa・Ga3': ['romasaga3'],
    'SaGa Frontier': [],
    'SaGa Frontier2': [],
    'ゼノギアス': ['xeno'],
    'クロノ・クロス': ['ChronoCross'],
    'NieR:Automata': ['NieR'],
    'SINoALICE': ['sinoalice'],
    '鋼の錬金術師': ['FA'],
    'DQMSL': ['DQMSL'],
    'DQXIS': ['DQ11S'],
    'ドラゴンクエスト ダイの大冒険': ['dai', 'dqdai'],
    'ドラゴンクエスト列伝 ロトの紋章': ['ROTO', 'roto'],
    'パラサイト・イヴ': ['PE'],
    '南国少年パプワくん': ['papuwa'],
    '魔法陣グルグル': ['guruguru'],
    'SO2R': [],
    'SO2': [],
}

DEVICE_SEASON_ART_REL = 'exvius/data/static/client/files/ko/season_art'
LIST_SIZE = (640, 320)
DETAIL_SIZE = (626, 184)

EXPLICIT_BANNER_PAIR: dict[str, tuple[str, str]] = {
    '99100001': ('gacha_20250411_FFBE_pickup_top.png', 'gacha_20250411_FFBE_pickup_01.png'),
    '99100002': ('gacha_20241220_FFBE_pickup_top.png', 'gacha_20241220_FFBE_pickup_01.png'),
    '99100003': ('gacha_20250630_FFBE_pickup1_top.png', 'gacha_20250630_FFBE_pickup1_01.png'),
    '99100004': ('gacha_20210730_FFBE_pickup_top.png', 'gacha_20210730_FFBE_pickup_01.png'),
    '99100005': ('gacha_20250430_FFBE_pickup1_top.png', 'gacha_20250430_FFBE_pickup1_01.png'),
    '99100006': ('gacha_20210930_FFBE_pickup1_top.png', 'gacha_20210930_FFBE_pickup1_01.png'),
    '99100007': ('gacha_20240831_FFBE_pickup1_top.png', 'gacha_20240831_FFBE_pickup1_01.png'),
    '99100008': ('gacha_20221031_FFBE_pickup1_top.png', 'gacha_20221031_FFBE_pickup1_01.png'),
    '99100009': ('gacha_20241031_FFBE_pickup1_top.png', 'gacha_20241031_FFBE_pickup1_01.png'),
    '99100010': ('gacha_20210721_FFBE_pickup01_top.png', 'gacha_20210721_FFBE_pickup01.png'),
    '99100011': ('gacha_20211217_FFBE_pickup1_top.png', 'gacha_20211217_FFBE_pickup1.png'),
    '99100012': ('gacha_20211228_FFBEnewyear_pickup1_top.png', 'gacha_20211228_FFBEnewyear_pickup1_01.png'),
    '99100013': ('gacha_20240819_FFBE_pickup1_top.png', 'gacha_20240819_FFBE_pickup1_01.png'),
}

EXPLICIT_TWITTER_PAIR: dict[str, tuple[str, str]] = {
    '99210014': ('2017-03-21_844101130246373376_1.png', '2019-07-29_1155780301030711296_1.png'),
    '99920028': ('2018-12-20_1075665858809212928_1.png', '2019-08-24_1165171887015485441_1.png'),
    '99920036': ('2021-11-28_1464942157157081093_4.jpg', '2021-11-30_1465596460301385734_1.png'),
    '99911011': ('2020-02-13_1227864990113239046_1.png', '2020-02-13_1227864987852406790_1.png'),
    '99920013': ('2017-07-21_888314092108296193_1.png', '2017-07-21_888314125352394752_1.png'),
    '99920015': ('2017-07-21_888326049490116608_1.jpg', '2017-07-19_887582804795572226_1.jpg'),
    '99920014': ('2017-07-21_888336712362901504_1.png', '2017-07-21_888336712362901504_1.png'),
    '99920001': ('2016-01-14_687454151614296065_1.jpg', '2015-12-28_681370248285655040_1.png'),
    '99920026': ('2018-06-19_1009014642549485573_1.jpg', '2020-06-24_1275743164628791297_1.jpg'),
}

COMM_ART_DIR = STATIC_DIR / 'gacha_community/art'
JP_SPD_DIR = ROOT / 'inputs/jp_cpk_banners'

EXPLICIT_LOCAL_PAIR: dict[str, tuple[Path, Path]] = {
    '99920012': (
        TWITTER_DIR / '2021-02-19_1362678306378637321_1.png',
        DUMP_DIR / 'gacha_20210219_seiken3_pickup-295a866c46b7c5a6.png',
    ),
    '99920033': (
        TWITTER_DIR / '2020-07-28_1288113228539715584_1.png',
        COMM_ART_DIR / 'Gacha-Sora KH3.png',
    ),
    '99920009': (
        STATIC_DIR / 'cpk_extract/en/area/Ver461_spdungeon1/spd_bn_list_dangerous_woman_tour.png',
        COMM_ART_DIR / 'Gacha-Performers-Charming Kitty Ariana.png',
    ),
    '99920023': (
        STATIC_DIR / 'cpk_extract/en/banner/Ver328_banner1/generalpu_bn_gacha1_TombRaider.png',
        COMM_ART_DIR / 'Gacha-NV Lara Croft.png',
    ),
}

EXPLICIT_WIDE_DETAIL: dict[str, Path] = {
    '99920029': COMM_ART_DIR / 'Gacha-Mordegon.png',
    '99920022': COMM_ART_DIR / 'Gacha-VPL-Lenneth.png',
    '99920010': COMM_ART_DIR / 'Gacha-NieR Automata.png',
    '99920033': COMM_ART_DIR / 'Gacha-Sora KH3.png',
    '99920003': COMM_ART_DIR / 'Gacha-Brave Frontier-2.png',
    '99920025': COMM_ART_DIR / 'Gacha-Olberic.png',
    '99920021': COMM_ART_DIR / "Gacha-King's Knight-Ray Jack.png",
    '99920031': COMM_ART_DIR / 'Gacha-A.I. Katy.png',
    '99920034': JP_SPD_DIR / 'spd_20200729_bn_list_KH_01.png',
}

MERGE_FF_SERIES = {
    'FF4TA': 'FFIV',
    'FF7AC': 'FFVII',
    'FF13-2': 'FF13',
    'LR FF13': 'FF13',
    'SO1': 'SO2R',
    'SO2': 'SO2R',
    'SO3': 'SO2R',
    'SO4': 'SO2R',
    'SO5': 'SO2R',
}

CARD_BACKDROP = BUILD / 'out/vortex_season/cpk_dump/raw/spd_bn_list_dummy.png'
FONT_CANDIDATES = (
    BUILD / 'out/ko_font/ko_game_font.ttf',
    BUILD / 'out/ko_font/ko_ui_font.ttf',
    Path('C:/Windows/Fonts/malgunbd.ttf'),
)

SEASON_KEYS = {
    'S1': 'season1',
    'S2': 'season2',
    'S3': 'season3',
    'S4': 'season4',
    'S5': 'season5',
}
SEASON_BOUNDS = {
    'season1': ('0000-00-00', '2017-02-27'),
    'season2': ('2017-02-28', '2019-05-29'),
    'season3': ('2019-05-30', '2021-05-09'),
    'season4': ('2021-05-10', '2024-12-26'),
    'season5': ('2024-12-27', '9999-99-99'),
}

TITLE_SERIES_PATTERNS: dict[str, list[str]] = {
    'FFBE': [r'BRAVE\s*EXVIUS(?!\s*幻影戦争)', r'\bFF\s*BE\b(?!\s*幻影戦争)'],
    'FFBE幻影戦争': [r'幻影戦争', r'WAR\s*OF\s*THE\s*VISIONS'],
    'FFI': [r'FINAL\s*FANTASY\s+I(?![IVX0-9])', r'I・II・III', r'^FFI$'],
    'FFII': [r'FINAL\s*FANTASY\s+II(?![IVX0-9])', r'I・II・III', r'^FFII$'],
    'FFIII': [r'FINAL\s*FANTASY\s+III(?![IVX0-9])', r'I・II・III', r'^FFIII$'],
    'FFIV': [r'FINAL\s*FANTASY\s+IV(?![IVX0-9]|.*AFTER)', r'IV・V・VI', r'^FFIV$'],
    'FF4TA': [r'AFTER\s*YEARS', r'FF4TA'],
    'FFV': [r'FINAL\s*FANTASY\s+V(?![IVX0-9])', r'IV・V・VI', r'^FFV$'],
    'FF6': [r'FINAL\s*FANTASY\s+VI(?![IVX0-9])', r'IV・V・VI', r'^FFVI$'],
    'FFVII': [
        r'(?<!CRISIS\sCORE\s)FINAL\s*FANTASY[\.\s]*VII(?![IVX0-9])(?!\s*(?:AC|ADVENT))',
        r'FFVII\s*RE(?:MAKE|BIRTH)',
        r'^FFVII$',
    ],
    'CCFF7': [r'CRISIS\s*CORE'],
    'FF7AC': [r'ADVENT\s*CHILDREN', r'FFVII\s*AC'],
    'FFVIII': [r'FINAL\s*FANTASY[\.\s]*VIII(?![IVX0-9])', r'^FFVIII$'],
    'FFIX': [r'FINAL\s*FANTASY\s+IX(?![IVX0-9])', r'^FFIX$'],
    'FFX': [r'FINAL\s*FANTASY\s+X(?![-IVX0-9])', r'^FFX$'],
    'FFX-2': [r'X-2'],
    'FF11': [r'FINAL\s*FANTASY[®\s]*XI(?![IVX0-9])'],
    'FFXII': [r'(?:FINAL\s*FANTASY|ファイナルファンタジー)\s*XII(?![IVX0-9])'],
    'FF13': [r'FINAL\s*FANTASY\s+XIII(?![IVX0-9]|-2|.*LIGHTNING)', r'^FFXIII$'],
    'FF13-2': [r'XIII-2'],
    'LR FF13': [r'LIGHTNING\s*RETURNS'],
    'FF14': [r'FINAL\s*FANTASY.*XIV(?![IVX0-9])', r'^FFXIV'],
    'FF15': [r'FINAL\s*FANTASY[\?\s]*XV(?![IVX0-9])', r'^FFXV$'],
    'FF16': [r'FINAL\s*FANTASY\s*XVI(?![IVX0-9])'],
    'FFT': [r'TACTICS'],
    'FF零式': [r'零式', r'TYPE-0'],
    'WOFF': [r'WORLD\s*OF\s*FINAL\s*FANTASY'],
    'ゼノギアス': [r'Xenogears', r'ゼノギアス'],
    '聖剣伝説': [r'聖剣伝説(?!\s*[23]|.*(?:LoM|LEGEND|VISIONS|TRIALS))'],
    '聖剣伝説2': [r'聖剣伝説\s*2', r'SECRET\s*of\s*MANA', r'聖剣伝説.*COLLECTION', r'聖剣伝説\s*シリーズ'],
    '聖剣伝説3': [r'聖剣伝説\s*3', r'TRIALS\s*of\s*MANA', r'聖剣伝説.*COLLECTION', r'聖剣伝説\s*シリーズ'],
    '聖剣伝説LoM': [r'LEGEND\s*OF\s*MANA', r'聖剣伝説\s*LoM'],
    '聖剣伝説 VoM': [r'VISIONS\s*of\s*MANA'],
    '鋼の錬金術師': [r'鋼の錬金術師', r'FULLMETAL'],
    'ドラゴンクエスト ダイの大冒険': [r'ダイの大冒険'],
    'ドラゴンクエスト列伝 ロトの紋章': [r'ロトの紋章'],
    'DQMSL': [r'MONSTERS.*SUPER\s*LIGHT', r'DQMSL'],
    'DQXIS': [r'DRAGON\s*QUEST\s*XI'],
    'ヴァルキリープロファイル': [r'VALKYRIE\s*PROFILE', r'ヴァルキリー'],
    'オクトパストラベラー': [r'OCTOPATH', r'オクトパス'],
    'クロノ・クロス': [r'CHRONO\s*CROSS', r'クロノ'],
    'NieR:Automata': [r'NieR', r'ニーア'],
    'KH': [r'KINGDOM\s*HEARTS(?!.*(?:III|3|Dark\s*Road))'],
    'キングダム ハーツIII': [r'KINGDOM\s*HEARTS.*(?:III|3)'],
    'キングダム ハーツ ダーク ロード': [r'Dark\s*Road', r'ダーク\s*ロード'],
    'パラサイト・イヴ': [r'parasite\s*eve', r'パラサイト'],
    'ブレイブ フロンティア': [r'ブレイブ\s*フロンティア', r'BRAVE\s*FRONTIER'],
    'アクトレイザー': [r'アクトレイザー', r'ACTRAISER'],
    '魔法陣グルグル': [r'グルグル'],
    '南国少年パプワくん': [r'パプワ'],
    'ImperialSaGa': [r'Imperial\s*SaGa', r'インペリアル'],
    'RomancingSa・Ga': [r'ロマンシング\s*サ[・･]?ガ(?![23])', r'「サガ」シリーズ'],
    'RomancingSa・Ga2': [r'ロマンシング\s*サ[・･]?ガ\s*2', r'「サガ」シリーズ'],
    'RomancingSa・Ga3': [r'ロマンシング\s*サ[・･]?ガ\s*3', r'「サガ」シリーズ'],
    'SaGa Frontier': [r'サガ\s*フロンティア(?![2])', r'「サガ」シリーズ'],
    'SaGa Frontier2': [r'サガ\s*フロンティア\s*2', r'「サガ」シリーズ'],
    'SO1': [r'STAR\s*OCEAN.*(?:anamnesis|アナムネシス|1|FIRST)'],
    'SO2': [r'STAR\s*OCEAN.*(?:2(?![R])|anamnesis|アナムネシス)'],
    'SO2R': [r'STAR\s*OCEAN.*(?:SECOND\s*STORY\s*R|2R)'],
    'SO3': [r'STAR\s*OCEAN.*(?:3|anamnesis|アナムネシス)'],
    'SO4': [r'STAR\s*OCEAN.*(?:4|anamnesis|アナムネシス)'],
    'SO5': [r'STAR\s*OCEAN.*(?:5|anamnesis|アナムネシス)'],
    'BRAVELYDEFAULT': [r'BRAVELY\s*DEFAULT(?!.*FE|.*II|.*2)', r'ブレイブリーシリーズ'],
    'BRAVELYDEFAULTFE': [r'BRAVELY\s*DEFAULT.*F', r'ブレイブリーシリーズ'],
    'BRAVELYSECOND': [r'BRAVELY\s*SECOND', r'ブレイブリーシリーズ'],
    'SINoALICE': [r'SINoALICE', r'シノアリス'],
    'TERRA BATTLE': [r'TERRA\s*BATTLE'],
    'CRYSTAL DEFENDERS': [r'CRYSTAL\s*DEFENDERS'],
    'FINAL FANTASY Record Keeper': [r'Record\s*Keeper', r'FFRK'],
    'ARIANA GRANDE': [r'ARIANA', r'アリアナ'],
    'KATY PERRY': [r'KATY', r'ケイティ'],
    'キングスナイト WoDD': [r'KING.?S\s*KNIGHT', r'キングスナイト'],
    'モンスターハンターエクスプロア': [r'モンスターハンター', r'MONSTER\s*HUNTER'],
    'ララ・クロフト アンド テンプル オブ オシリス': [r'LARA\s*CROFT', r'ララ'],
    'リコドキッ！': [r'リコドキ'],
}

FRANCHISE_GROUP: dict[str, str] = {
    'KH': 'KH', 'キングダム ハーツIII': 'KH', 'キングダム ハーツ ダーク ロード': 'KH',
    'SO1': 'SO', 'SO2': 'SO', 'SO2R': 'SO', 'SO3': 'SO', 'SO4': 'SO', 'SO5': 'SO',
    '聖剣伝説': 'MANA', '聖剣伝説2': 'MANA', '聖剣伝説3': 'MANA', '聖剣伝説LoM': 'MANA', '聖剣伝説 VoM': 'MANA',
    'BRAVELYDEFAULT': 'BD', 'BRAVELYDEFAULTFE': 'BD', 'BRAVELYSECOND': 'BD',
    'FFVII': 'FF7', 'CCFF7': 'FF7', 'FF7AC': 'FF7',
    'FFX': 'FF10', 'FFX-2': 'FF10',
    'FF13': 'FF13', 'FF13-2': 'FF13', 'LR FF13': 'FF13',
    'FFIV': 'FF4', 'FF4TA': 'FF4',
}

PUNCT_RX = re.compile(r'[\s\u3000・･\-－—–~〜:：/／!！?？「」『』（）()［］\[\]★☆※&＆+＋.。,，\'\"’”“™®©]+')
NOISE_SUFFIX = re.compile(r'(?:-?Neo\s*Vision-|NV|\(FF[^)]+\)|\(BD\)|\(KH[^)]*\)|\(WOFF\))$', re.I)
KATA = 'ァ-ヶー'
TOP_STANDIN_RX = re.compile(r'^gacha_\d{8}_.+_top\.png$')

CARD_ACCENTS = [
    (66, 133, 244), (52, 168, 83), (234, 67, 53), (251, 188, 5),
    (171, 71, 188), (0, 172, 193), (255, 112, 67), (92, 107, 192),
    (38, 166, 154), (236, 64, 122),
]


def load_ko_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    raise FileNotFoundError(f'한국어 폰트를 찾을 수 없음: {FONT_CANDIDATES}')


def in_season(date_str: str, season_key: str) -> bool:
    if season_key not in SEASON_BOUNDS:
        return True
    lo, hi = SEASON_BOUNDS[season_key]
    return lo <= date_str <= hi


def norm_compact(s: str) -> str:
    return PUNCT_RX.sub('', unicodedata.normalize('NFKC', str(s or ''))).casefold()


def norm_spaced(s: str) -> str:
    return ' ' + PUNCT_RX.sub(' ', unicodedata.normalize('NFKC', str(s or ''))).strip().casefold() + ' '


def strip_suffix(s: str) -> str:
    return NOISE_SUFFIX.sub('', unicodedata.normalize('NFKC', str(s or '')).strip()).strip()


def series_matches(title: str, img_series: str) -> bool:
    if not img_series:
        return False
    s = unicodedata.normalize('NFKC', img_series).replace('\n', ' ')
    if title == 'FFBE' and ('幻影戦争' in s or 'WAR OF THE VISIONS' in s.upper()):
        return False
    if title == 'FFVII' and 'CRISIS CORE' in s.upper():
        return False
    return any(re.search(p, s, re.I) for p in TITLE_SERIES_PATTERNS.get(title, []))


def name_matches(u_name: str, tw_name: str) -> tuple[bool, bool, int]:
    nu, nt = norm_compact(u_name), norm_compact(tw_name)
    if not nu or not nt:
        return False, False, 0
    if nu == nt:
        return True, True, len(nu)
    nu_s, nt_s = norm_compact(strip_suffix(u_name)), norm_compact(strip_suffix(tw_name))
    if nu_s and nt_s and nu_s == nt_s:
        return True, True, len(nu_s)
    shorter, longer = (nu, nt) if len(nu) <= len(nt) else (nt, nu)
    if len(shorter) <= 3:
        su, st = norm_spaced(u_name), norm_spaced(tw_name)
        if f' {shorter} ' in (st if len(nu) <= len(nt) else su):
            return True, False, len(shorter)
        if re.fullmatch(rf'[{KATA}]+', shorter):
            longer_raw = unicodedata.normalize('NFKC', tw_name if len(nu) <= len(nt) else u_name).casefold()
            pat = rf'(?<![{KATA}a-z0-9]){re.escape(shorter)}(?![{KATA}a-z0-9])'
            if re.search(pat, longer_raw):
                return True, False, len(shorter)
        return False, False, 0
    if shorter in longer:
        return True, False, len(shorter)
    if nu_s and nt_s and len(min(nu_s, nt_s, key=len)) >= 4:
        s2, l2 = (nu_s, nt_s) if len(nu_s) <= len(nt_s) else (nt_s, nu_s)
        if s2 in l2:
            return True, False, len(s2)
    return False, False, 0


STEPUP_RX = re.compile(r'ステップ|STEP\s*\d|step\s*up', re.I)


def is_stepup_notice(rec: dict) -> bool:
    text = ' '.join([rec.get('title') or ''] + list(rec.get('subtitles') or []) + list(rec.get('prices') or []))
    return bool((rec.get('step_count') or 0) > 0 or STEPUP_RX.search(text))


def load_twitter_pool() -> list[dict]:
    verdicts: dict[str, dict] = {}
    for line in (GACHA_JP / 'twitter_verdict.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            rec = json.loads(line)
            verdicts[str(rec['id'])] = rec

    merged: dict[str, dict] = {}
    for fname in ('twitter_identify.jsonl', 'twitter_identify_agy.jsonl'):
        for line in (GACHA_JP / fname).read_text(encoding='utf-8').splitlines():
            if line.strip():
                rec = json.loads(line)
                merged[rec['file']] = rec

    pool: list[dict] = []
    for rec in merged.values():
        if rec.get('kind') != 'gacha':
            continue
        # 스텝업 공지 그림은 일반 소환 배너에 쓰지 않는다(2026-11-16 사용자 결정, 스텝업은 보류).
        if is_stepup_notice(rec):
            continue
        tid = rec['file'].split('_')[1]
        if verdicts.get(tid, {}).get('verdict') not in ('확정', '이미지만'):
            continue
        tw_path = TWITTER_DIR / rec['file']
        if not tw_path.exists():
            continue
        item = dict(rec)
        item['_date'] = rec['file'][:10]
        item['_sha256'] = hashlib.sha256(tw_path.read_bytes()).hexdigest()
        pool.append(item)
    return pool


def load_banner_units() -> dict[tuple[str, str], list[str]]:
    draft = json.loads((GACHA_JP / 'banner_plan_draft.json').read_text(encoding='utf-8'))
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rec in draft:
        if rec['group'] == 'collab':
            key = ('collaborations', MERGE_FF_SERIES.get(rec['title'], rec['title']))
        elif rec['title'] == 'FFBE':
            key = ('ffbe', 'FFBE')
        else:
            merged = MERGE_FF_SERIES.get(rec['title'], rec['title'])
            key = ('ff_series', merged)
        if rec['name'] not in by_key[key]:
            by_key[key].append(rec['name'])
    return by_key


def find_detail_for_top(
    top_clean: str,
    index: dict[str, Path],
    dump_dims: dict[str, tuple[int, int]],
) -> str | None:
    """_top 배너(640x320/170)에 대응하는 626x186 상세 배너 파일명을 찾는다."""
    m = DUMP_TOP_RX.match(top_clean)
    if not m:
        return None
    d, stem = m.group(1), m.group(2)
    if re.search(r'_(single|half)\d*$', stem, re.I):
        base = re.sub(r'_(single|half)\d*$', '', stem, flags=re.I)
        cands = [
            f'gacha_{d}_{stem}.png',
            f'gacha_{d}_{base}_01.png',
            f'gacha_{d}_{base}.png',
        ]
    else:
        cands = [
            f'gacha_{d}_{stem}_01.png',
            f'gacha_{d}_{stem}.png',
            f'gacha_{d}_{stem}_single.png',
            f'gacha_{d}_{stem}_half.png',
        ]
        sm = re.match(r'^stepup\d*_(.+)$', stem, re.I)
        if sm:
            x = sm.group(1)
            cands.extend([
                f'gacha_{d}_{x}_pickup.png',
                f'gacha_{d}_{x}_pickup1.png',
                f'gacha_{d}_{x}_pickup01.png',
                f'gacha_{d}_{x}_pickup_01.png',
            ])
    for cand in cands:
        dims = dump_dims.get(cand)
        if dims and dims[0] == DETAIL_SIZE[0] and dims[1] <= 200 and cand != top_clean:
            return cand
    return None


def dump_series_matches(clean_top: str, stem: str, series: str) -> bool:
    """덤프 _top 배너가 해당 시리즈 슬롯과 일치하는지 판정한다."""
    if clean_top in EXPLICIT_DUMP_SERIES:
        return EXPLICIT_DUMP_SERIES[clean_top] == series
    for tok in SERIES_DUMP_TOKENS.get(series, []):
        if tok[-1].isdigit():
            pat = re.compile(rf'(?:^|_){re.escape(tok)}(?![0-9])(?:_|$|[a-z])', re.I)
        else:
            pat = re.compile(rf'(?:^|_){re.escape(tok)}(?:_|$|\d)', re.I)
        if not pat.search(stem):
            continue
        if tok.upper() in ('FF10', 'FF13', 'FF4', 'FF7'):
            after = re.compile(rf'(?:^|_){re.escape(tok)}[-_]*(?:2|TA|AC|R|LR)', re.I)
            if tok.upper() != 'FF7' and after.search(stem):
                continue
            if tok.upper() == 'FF7' and re.search(r'FF7[-_]*AC|CCFF7', stem, re.I):
                continue
        return True
    return False


def load_dump_pool() -> dict:
    """gacha 덤프의 해시 제거 파일 색인, 치수, 그리고 정식 (목록 _top, 상세 626x186) 쌍을 수집한다."""
    index: dict[str, Path] = {}
    dump_dims: dict[str, tuple[int, int]] = {}
    if DUMP_DIR.is_dir():
        for p in sorted(DUMP_DIR.iterdir()):
            if not (p.is_file() and p.suffix.lower() == '.png'):
                continue
            clean = DUMP_HASH_RX.sub(r'\1', p.name)
            if clean in index:
                continue
            index[clean] = p
            try:
                with Image.open(p) as im:
                    dump_dims[clean] = im.size
            except Exception:
                pass

    pairs: list[dict] = []
    for clean_top in sorted(index):
        m = DUMP_TOP_RX.match(clean_top)
        if not m:
            continue
        top_dims = dump_dims.get(clean_top)
        if not top_dims or top_dims[0] != 640 or top_dims[1] not in (170, 320):
            continue
        d, stem = m.group(1), m.group(2)
        if DUMP_SKIP_STEM_RX.search(stem):
            continue
        detail_clean = find_detail_for_top(clean_top, index, dump_dims)
        if not detail_clean:
            continue

        low = stem.lower()
        is_reprint = 'reprint' in low
        is_stepup = 'stepup' in low
        is_sub = bool(re.search(r'_(?:single|half)\d*$', stem, re.I)) or 'event_pickup' in low
        is_umbrella_ff = clean_top in UMBRELLA_FF_TOPS
        rank = 0 if (top_dims[1] >= 300 and not is_umbrella_ff) else 1
        if is_reprint:
            rank += 1
        if is_stepup:
            rank += 2
        if is_sub:
            rank += 3

        parts = stem.split('_')
        ev_tok = 'stepup_' + parts[1] if (parts[0].lower().startswith('stepup') and len(parts) > 1) else parts[0]
        pairs.append({
            'name': clean_top,
            'detail': detail_clean,
            'stem': stem,
            'date': f'{d[:4]}-{d[4:6]}-{d[6:]}',
            'token': ev_tok,
            'rank': rank,
            'top_h': top_dims[1],
            'is_reprint': is_reprint,
            'is_stepup': is_stepup,
        })
    return {'index': index, 'dims': dump_dims, 'pairs': pairs}


def dump_candidates(banner: dict, dump: dict) -> list[dict]:
    """배너 시리즈(전 시즌 포함)에 일치하는 덤프 (목록, 상세) 쌍을 반환한다."""
    series = banner['title']
    return [c for c in dump.get('pairs', []) if dump_series_matches(c['name'], c['stem'], series)]


def image_hashes(list_img: Image.Image, detail_img: Image.Image) -> tuple[str, str]:
    """픽셀 기준 출력 해시(같은 픽셀이면 저장 PNG도 같다)."""
    lh = hashlib.sha256(
        f'{list_img.width}x{list_img.height}'.encode() + list_img.convert('RGBA').tobytes()
    ).hexdigest()
    dh = hashlib.sha256(
        f'{detail_img.width}x{detail_img.height}'.encode() + detail_img.convert('RGBA').tobytes()
    ).hexdigest()
    return lh, dh


def source_path(pick: dict) -> str | None:
    if pick['source'] == 'dump':
        return pick.get('_dump_list_path')
    if pick['source'] == 'twitter':
        return str(TWITTER_DIR / pick['orig_file'])
    if pick['source'] == 'client':
        return pick.get('_local_list_path')
    return None


DUMP_ANCHOR_DAYS = 45
SEASON_PRIO = {
    'ffbe': 0,
    'collaborations': 1,
    'ff_series': 2,
    'season5': 3,
    'season4': 4,
    'season3': 5,
    'season2': 6,
    'season1': 7,
}
SEASON_MIDPOINTS = {
    'ffbe': _date(2023, 5, 15),
    'ff_series': _date(2023, 5, 15),
    'season1': _date(2016, 10, 15),
    'season2': _date(2018, 11, 15),
    'season3': _date(2020, 10, 30),
    'season4': _date(2023, 5, 15),
    'season5': _date(2025, 5, 15),
    'collaborations': _date(2023, 1, 1),
}


def select_twitter_art(
    report_banners: list[dict],
    units_by_key: dict[tuple[str, str], list[str]],
    tw_pool: list[dict],
    dump: dict | None = None,
) -> dict[int, dict]:
    all_titles = sorted({b['title'] for b in report_banners})
    for img in tw_pool:
        img['_series_set'] = {t for t in all_titles if series_matches(t, img.get('series', ''))}

    cands_by_bid: dict[int, list[tuple]] = {}
    for b in report_banners:
        bid, season, title = b['id'], b['season'], b['title']
        u_names = units_by_key.get((season, title), [])
        b_fran = FRANCHISE_GROUP.get(title, title)
        cands: list[tuple] = []
        for img in tw_pool:
            img_sers = img['_series_set']
            ser_ok = title in img_sers
            ser_fran_ok = ser_ok or any(FRANCHISE_GROUP.get(t, t) == b_fran for t in img_sers)
            ser_conflict = bool(img_sers) and not ser_fran_ok
            tw_names = img.get('unit_names') or []

            matched_u: list[str] = []
            exact_cnt = 0
            for u in u_names:
                best = (False, False, 0)
                for tw in tw_names:
                    m, ex, slen = name_matches(u, tw)
                    if m and not (ser_conflict and slen <= 3):
                        best = (True, best[1] or ex, max(best[2], slen))
                if best[0]:
                    matched_u.append(u)
                    if best[1]:
                        exact_cnt += 1

            in_s = in_season(img['_date'], season)
            if matched_u:
                tier = 3 if in_s else 1
                how = 'unit_in_season' if in_s else 'unit_out_of_season'
                score = (tier, len(matched_u), exact_cnt, int(ser_ok), img['file'])
                cands.append((score, img['file'], img['_sha256'], matched_u, how))
            elif in_s and ser_ok:
                score = (2, 0, 0, 1, img['file'])
                cands.append((score, img['file'], img['_sha256'], [], 'series_in_season'))

        cands.sort(key=lambda x: x[0], reverse=True)
        cands_by_bid[bid] = cands

    used_files: set[str] = set()
    used_hashes: set[str] = set()
    used_list_hashes: set[str] = set()
    used_detail_hashes: set[str] = set()
    used_events: set[tuple[str, str]] = set()
    picks: dict[int, dict] = {}

    dump = dump or {'index': {}, 'dims': {}, 'pairs': []}

    # Pass 0: 배너 ID 기반 고정 정식 덤프/트위터 쌍(FFBE 13테마, FF14 등).
    for b in report_banners:
        bid = b['id']
        s_bid = str(bid)
        if s_bid in EXPLICIT_BANNER_PAIR:
            name, detail_name = EXPLICIT_BANNER_PAIR[s_bid]
            path = dump['index'].get(name)
            dpath = dump['index'].get(detail_name)
            if path is None or dpath is None:
                raise FileNotFoundError(f'Missing explicit dump pair for {bid}: {name} -> {detail_name}')
            fhash = hashlib.sha256(path.read_bytes()).hexdigest()
            dhash = hashlib.sha256(dpath.read_bytes()).hexdigest()
            with Image.open(path) as src:
                list_img = list_native(src)
            with Image.open(dpath) as dsrc:
                detail_rgba = dsrc.convert('RGBA')
            lh, dh = image_hashes(list_img, fit_inside(detail_rgba, DETAIL_SIZE))
            used_files.update((name, detail_name))
            used_hashes.update((fhash, dhash))
            used_list_hashes.add(lh)
            used_detail_hashes.add(dh)
            picks[bid] = {
                'source': 'dump',
                'orig_file': name,
                'dump_detail': detail_name,
                'matched_units': [],
                'match_how': 'dump_explicit',
                '_dump_list_path': str(path),
                '_dump_detail_path': str(dpath),
            }
        elif s_bid in EXPLICIT_TWITTER_PAIR:
            list_fn, det_fn = EXPLICIT_TWITTER_PAIR[s_bid]
            lp = TWITTER_DIR / list_fn
            dp = TWITTER_DIR / det_fn
            if not lp.is_file() or not dp.is_file():
                raise FileNotFoundError(f'Missing explicit twitter pair for {bid}: {lp} -> {dp}')
            fhash = hashlib.sha256(lp.read_bytes()).hexdigest()
            dhash = hashlib.sha256(dp.read_bytes()).hexdigest()
            with Image.open(lp) as lsrc:
                list_img = list_native(lsrc, lp.name)
            with Image.open(dp) as dsrc:
                detail_img = fit_inside(dsrc, DETAIL_SIZE)
            lh, dh = image_hashes(list_img, detail_img)
            used_files.update((list_fn, det_fn))
            used_hashes.update((fhash, dhash))
            used_list_hashes.add(lh)
            used_detail_hashes.add(dh)
            picks[bid] = {
                'source': 'twitter',
                'orig_file': list_fn,
                'detail_file': det_fn,
                'matched_units': [],
                'match_how': 'twitter_explicit',
            }
        elif s_bid in EXPLICIT_LOCAL_PAIR:
            lp, dp = EXPLICIT_LOCAL_PAIR[s_bid]
            if not lp.is_file() or not dp.is_file():
                raise FileNotFoundError(f'Missing explicit local pair for {bid}: {lp} -> {dp}')
            fhash = hashlib.sha256(lp.read_bytes()).hexdigest()
            dhash = hashlib.sha256(dp.read_bytes()).hexdigest()
            with Image.open(lp) as lsrc:
                list_img = list_native(lsrc, lp.name)
            with Image.open(dp) as dsrc:
                detail_img = fit_inside(dsrc, DETAIL_SIZE)
            lh, dh = image_hashes(list_img, detail_img)
            used_files.update((lp.name, dp.name))
            used_hashes.update((fhash, dhash))
            used_list_hashes.add(lh)
            used_detail_hashes.add(dh)
            picks[bid] = {
                'source': 'client',
                'orig_file': lp.name,
                'detail_file': dp.name,
                'matched_units': [],
                'match_how': 'local_explicit',
                '_local_list_path': str(lp),
                '_local_detail_path': str(dp),
            }

    # Pass 1: 디스코드 gacha 덤프의 정식 (배너이미지 640x320, 상세 이미지 626x186) 쌍 배정.
    dump_cands = {
        b['id']: ([] if b['id'] in picks else dump_candidates(b, dump))
        for b in report_banners
    }
    dump_order = sorted(
        (b for b in report_banners if dump_cands[b['id']]),
        key=lambda b: (SEASON_PRIO.get(b['season'], 9), len(dump_cands[b['id']]), -b['disp_order']),
    )
    for b in dump_order:
        bid = b['id']
        season = b['season']
        cs = dump_cands[bid]
        unit_dates = [
            _date.fromisoformat(fn[:10])
            for _, fn, _, _, how in cands_by_bid[bid]
            if how == 'unit_in_season'
        ]
        if unit_dates:
            b['_dump_anchor'] = unit_dates[0].isoformat()
        midpoint = SEASON_MIDPOINTS.get(season, _date(2023, 1, 1))

        def sort_key(c: dict, _s: str = season, _dates: list[_date] = unit_dates, _mid: _date = midpoint) -> tuple:
            in_s_flag = 0 if (_s in ('collaborations', 'ff_series', 'ffbe') or in_season(c['date'], _s)) else 1
            tall_flag = 0 if c.get('top_h', 0) >= 300 else 1
            d_obj = _date.fromisoformat(c['date'])
            arank = len(_dates)
            if in_s_flag == 0 and _dates:
                for i, a in enumerate(_dates):
                    if abs((d_obj - a).days) <= DUMP_ANCHOR_DAYS:
                        arank = i
                        break
            fresh_ev = 0 if (c['date'], c['token']) not in used_events else 1
            dist = abs((d_obj - _mid).days)
            return (in_s_flag, tall_flag, c['rank'], arank, fresh_ev, dist, c['name'])

        chosen = None
        for c in sorted(cs, key=sort_key):
            name, detail_name = c['name'], c['detail']
            if name in used_files or detail_name in used_files:
                continue
            path = dump['index'].get(name)
            dpath = dump['index'].get(detail_name)
            if path is None or dpath is None:
                continue
            fhash = hashlib.sha256(path.read_bytes()).hexdigest()
            dhash = hashlib.sha256(dpath.read_bytes()).hexdigest()
            if fhash in used_hashes or dhash in used_hashes:
                continue
            with Image.open(path) as src:
                list_img = list_native(src)
            with Image.open(dpath) as dsrc:
                detail_rgba = dsrc.convert('RGBA')
            lh, dh = image_hashes(list_img, fit_inside(detail_rgba, DETAIL_SIZE))
            if lh in used_list_hashes or dh in used_detail_hashes:
                continue
            used_files.add(name)
            used_files.add(detail_name)
            used_hashes.add(fhash)
            used_hashes.add(dhash)
            used_list_hashes.add(lh)
            used_detail_hashes.add(dh)
            used_events.add((c['date'], c['token']))
            how = 'dump_reprint' if c['is_reprint'] else ('dump_stepup' if c['is_stepup'] else 'dump_pickup')
            chosen = {
                'source': 'dump',
                'orig_file': name,
                'dump_detail': detail_name,
                'matched_units': [],
                'match_how': how,
                '_dump_list_path': str(path),
                '_dump_detail_path': str(dpath),
            }
            break
        if chosen is not None:
            picks[bid] = chosen

    # 2순위: 트위터 공지 이미지, 3순위: 카드 자리표시자. 후보가 적은 배너부터 배정한다.
    order = sorted(
        (b for b in report_banners if b['id'] not in picks),
        key=lambda b: (len(cands_by_bid[b['id']]), -b['disp_order']),
    )
    for b in order:
        bid = b['id']
        chosen = None
        for _, fn, fhash, matched_u, how in cands_by_bid[bid]:
            if fn in used_files or fhash in used_hashes:
                continue
            with Image.open(TWITTER_DIR / fn) as src:
                list_img = list_native(src, fn)
                wide_det = EXPLICIT_WIDE_DETAIL.get(str(bid))
                if wide_det is not None:
                    with Image.open(wide_det) as dsrc:
                        detail_img = fit_inside(dsrc, DETAIL_SIZE)
                else:
                    detail_img = fit_inside(src, DETAIL_SIZE)
            lh, dh = image_hashes(list_img, detail_img)
            if lh in used_list_hashes or dh in used_detail_hashes:
                continue
            used_files.add(fn)
            used_hashes.add(fhash)
            used_list_hashes.add(lh)
            used_detail_hashes.add(dh)
            chosen = {
                'source': 'twitter',
                'orig_file': fn,
                'detail_file': wide_det.name if wide_det else fn,
                'matched_units': matched_u,
                'match_how': how,
            }
            if wide_det:
                chosen['_wide_detail_path'] = str(wide_det)
            break
        if chosen is None:
            chosen = {
                'source': 'card',
                'orig_file': None,
                'detail_file': None,
                'matched_units': [],
                'match_how': 'card',
            }
        picks[bid] = chosen
    return picks


def list_native(img: Image.Image, orig_name: str = '') -> Image.Image:
    """덤프 배너는 원본을 유지하고, 그 외 배너는 인위적 테두리 없이 실제 폭만 578px(x=31..609)로 맞춘다."""
    src = img.convert('RGBA')
    if not orig_name or orig_name.startswith('gacha_'):
        w, h = src.size
        if w > 640:
            src = src.resize((640, round(h * 640 / w)), Image.Resampling.LANCZOS)
            w, h = src.size
        if w == 640:
            return src
        canvas = Image.new('RGBA', (640, h), (0, 0, 0, 0))
        canvas.paste(src, ((640 - w) // 2, 0))
        return canvas

    alpha_full = np.array(src)[:, :, 3]
    ys0, xs0 = np.where(alpha_full > 16)
    if src.size == LIST_SIZE and xs0.size and (int(xs0.min()), int(xs0.max() + 1)) == (31, 609):
        return src

    if '1288113228539715584_1' in orig_name or '1288113228556296198_1' in orig_name:
        src = src.crop((0, 0, src.width, min(360, src.height)))

    alpha = np.array(src)[:, :, 3]
    ys, xs = np.where(alpha > 16)
    if ys.size and xs.size:
        src = src.crop((int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)))

    target_w = 578
    target_h = max(1, round(src.height * target_w / src.width))
    resized = src.resize((target_w, target_h), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (640, target_h + 32), (0, 0, 0, 0))
    canvas.paste(resized, (31, 16))
    return canvas


def fit_inside(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """자르지 않고 전체가 들어가게 비율 유지 축소, 남는 곳은 투명."""
    src = img.convert('RGBA')
    tw, th = target_size
    scale = min(tw / src.width, th / src.height)
    nw, nh = max(1, round(src.width * scale)), max(1, round(src.height * scale))
    canvas = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    canvas.paste(src.resize((nw, nh), Image.Resampling.LANCZOS), ((tw - nw) // 2, (th - nh) // 2))
    return canvas


def cover_crop_resize(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """비율 유지 cover crop + LANCZOS 리사이즈."""
    tw, th = target_size
    src = img.convert('RGBA')
    sw, sh = src.size
    src_ratio = sw / sh
    tgt_ratio = tw / th
    if src_ratio > tgt_ratio:
        crop_w = max(1, int(round(sh * tgt_ratio)))
        left = (sw - crop_w) // 2
        box = (left, 0, left + crop_w, sh)
    else:
        crop_h = max(1, int(round(sw / tgt_ratio)))
        top = (sh - crop_h) // 2
        box = (0, top, sw, top + crop_h)
    return src.crop(box).resize((tw, th), Image.Resampling.LANCZOS)


def wrap_banner_title(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    if ' - ' in title:
        left, right = title.split(' - ', 1)
        lines = [left.strip(), right.strip()]
    else:
        lines = [title]

    wrapped: list[str] = []
    for seg in lines:
        if draw.textlength(seg, font=font) <= max_w:
            wrapped.append(seg)
            continue
        cur = ''
        for ch in seg:
            if cur and draw.textlength(cur + ch, font=font) > max_w:
                wrapped.append(cur.rstrip())
                cur = ch.lstrip()
            else:
                cur += ch
        if cur:
            wrapped.append(cur.rstrip())
    return wrapped[:3]


def _card_backdrop(target_size: tuple[int, int], card_idx: int) -> tuple[Image.Image, tuple[int, int, int]]:
    tw, th = target_size
    if CARD_BACKDROP.exists():
        raw = Image.open(CARD_BACKDROP).convert('RGBA')
        # spd_bn_list_dummy.png 외곽 16px 투명 여백 제거
        if raw.size == (640, 240):
            raw = raw.crop((16, 16, 624, 224))
        base = cover_crop_resize(raw, target_size)
    else:
        base = Image.new('RGBA', target_size, (26, 34, 68, 255))

    accent = CARD_ACCENTS[card_idx % len(CARD_ACCENTS)]
    overlay = Image.new('RGBA', target_size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    # 상·하단 미세 테두리 및 배너별 고유 색띠
    odraw.rectangle((0, 0, tw - 1, 5), fill=accent + (230,))
    odraw.rectangle((0, th - 6, tw - 1, th - 1), fill=accent + (230,))
    odraw.rectangle((8, 12, 16, th - 13), fill=accent + (230,))
    odraw.rectangle((tw - 17, 12, tw - 9, th - 13), fill=accent + (230,))
    odraw.rectangle((24, 14, tw - 25, th - 15), fill=(10, 14, 34, 155), outline=accent + (180,), width=2)
    base = Image.alpha_composite(base, overlay)
    return base, accent


def render_card(banner: dict, target_size: tuple[int, int], card_idx: int) -> Image.Image:
    tw, th = target_size
    base, _ = _card_backdrop(target_size, card_idx)

    draw = ImageDraw.Draw(base)
    name = banner['name']
    max_w = tw - 80
    font = load_ko_font(28)
    for sz in (30, 27, 24, 21):
        cand = load_ko_font(sz)
        lines = wrap_banner_title(draw, name, cand, max_w)
        if all(draw.textlength(l, font=cand) <= max_w for l in lines) and len(lines) <= 2:
            font = cand
            break
    else:
        lines = wrap_banner_title(draw, name, font, max_w)

    line_h = font.size + 8
    total_h = line_h * len(lines) + 22
    y = max(18, (th - total_h) // 2)
    sub_font = load_ko_font(15)
    sub = f"{banner['title']}  ·  #{banner['id']}"
    sw = draw.textlength(sub, font=sub_font)
    draw.text(((tw - sw) / 2, y), sub, font=sub_font, fill=(195, 212, 255, 240), stroke_width=2, stroke_fill=(8, 10, 24, 255))
    y += 24
    for idx_l, line in enumerate(lines):
        lw = draw.textlength(line, font=font)
        fill = (255, 232, 150, 255) if idx_l == 0 and len(lines) > 1 else (255, 255, 255, 255)
        draw.text(((tw - lw) / 2, y), line, font=font, fill=fill, stroke_width=3, stroke_fill=(8, 12, 30, 255))
        y += line_h
    return base


def render_card_with_inset(banner: dict, src_img: Image.Image, target_size: tuple[int, int], card_idx: int) -> Image.Image:
    """얇은 트위터 원본(<250px)을 자르지 않고 상단 제목 + 하단 큰 목록 배너(640x320) 카드로 합성."""
    tw, th = target_size
    base, _ = _card_backdrop(target_size, card_idx)
    draw = ImageDraw.Draw(base)

    sub_font = load_ko_font(14)
    sub = f"{banner['title']}  ·  #{banner['id']}"
    sw = draw.textlength(sub, font=sub_font)
    draw.text(((tw - sw) / 2, 24), sub, font=sub_font, fill=(195, 212, 255, 240), stroke_width=2, stroke_fill=(8, 10, 24, 255))

    max_w = tw - 76
    name = banner['name']
    font = load_ko_font(20)
    lines = [name]
    for sz in (26, 23, 20, 18):
        cand = load_ko_font(sz)
        cand_lines = wrap_banner_title(draw, name, cand, max_w)
        if all(draw.textlength(l, font=cand) <= max_w for l in cand_lines) and len(cand_lines) <= 2:
            font = cand
            lines = cand_lines
            break

    y = 46 if len(lines) >= 2 else 56
    line_h = font.size + 4
    for idx_l, line in enumerate(lines[:2]):
        lw = draw.textlength(line, font=font)
        fill = (255, 232, 150, 255) if idx_l == 0 and len(lines) > 1 else (255, 255, 255, 255)
        draw.text(((tw - lw) / 2, y), line, font=font, fill=fill, stroke_width=3, stroke_fill=(8, 12, 30, 255))
        y += line_h

    inset_top = max(112, y + 6)
    inset_h = max(60, th - inset_top - 18)
    inset = fit_inside(src_img, (tw - 64, inset_h))
    base.paste(inset, (32, inset_top), inset)
    return base


def render_banner_pngs(report_banners: list[dict], picks: dict[int, dict]) -> None:
    SEASON_ART_DIR.mkdir(parents=True, exist_ok=True)
    for pattern in ('*_list.png', '*_detail.png', 'contact_sheet_*.png'):
        for stale in SEASON_ART_DIR.glob(pattern):
            stale.unlink()

    card_idx = 0
    for b in report_banners:
        bid = b['id']
        pick = picks[bid]
        list_path = SEASON_ART_DIR / f'{bid}_list.png'
        detail_path = SEASON_ART_DIR / f'{bid}_detail.png'

        if pick['source'] == 'dump':
            with Image.open(pick['_dump_list_path']) as src:
                list_native(src).save(list_path, format='PNG', optimize=True)
            with Image.open(pick['_dump_detail_path']) as src:
                fit_inside(src, DETAIL_SIZE).save(detail_path, format='PNG', optimize=True)
        elif pick['source'] == 'twitter':
            with Image.open(TWITTER_DIR / pick['orig_file']) as src:
                list_native(src, pick['orig_file']).save(list_path, format='PNG', optimize=True)
            det_path = Path(pick['_wide_detail_path']) if pick.get('_wide_detail_path') else (TWITTER_DIR / (pick.get('detail_file') or pick['orig_file']))
            with Image.open(det_path) as dsrc:
                fit_inside(dsrc, DETAIL_SIZE).save(detail_path, format='PNG', optimize=True)
        elif pick['source'] == 'client':
            with Image.open(pick['_local_list_path']) as src:
                list_native(src, Path(pick['_local_list_path']).name).save(list_path, format='PNG', optimize=True)
            with Image.open(pick['_local_detail_path']) as dsrc:
                fit_inside(dsrc, DETAIL_SIZE).save(detail_path, format='PNG', optimize=True)
        else:
            render_card(b, LIST_SIZE, card_idx).save(list_path, format='PNG', optimize=True)
            render_card(b, DETAIL_SIZE, card_idx).save(detail_path, format='PNG', optimize=True)
            card_idx += 1


def static_png_names() -> set[str]:
    names: set[str] = set()
    for sub in ('cpk_extract', 'gacha_community', 'client/files'):
        base = STATIC_DIR / sub
        if base.is_dir():
            for p in base.rglob('*.png'):
                names.add(p.name)
    return names


def non_banner_unit_sizes() -> set[int]:
    """make_jp_art_dims.non_banner_sizes() 와 동일하게 유닛 CPK 내 비배너 PNG 크기를 수집."""
    sizes: set[int] = set()
    vendor = ROOT / 'tools/vendor'
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    try:
        from cricodecs import cpk
    except ImportError:
        return sizes
    seen: set[str] = set()
    for path in sorted(UNIT_CPKS.glob('unit*.cpk')):
        try:
            c = cpk.Cpk.load_bytes(path.read_bytes())
        except Exception:
            continue
        for e in c.files:
            name = (e.filename or '').rsplit('/', 1)[-1]
            if not name.lower().endswith('.png') or name.startswith(BANNERISH) or name in seen:
                continue
            seen.add(name)
            sz = int(getattr(e, 'extract_size', 0) or getattr(e, 'file_size', 0) or 0)
            if sz > 0:
                sizes.add(sz)
    return sizes


def allocate_standins(
    banner_count: int,
    preserved_art: dict[str, dict],
) -> list[tuple[str, int, str | None]]:
    """중복 바이트 크기 및 유닛 시트 충돌이 없는 gacha_*_top.png 자리표시자 2*N개 배정."""
    jp_art = json.loads((BUILD / 'jp_gacha_art.json').read_text(encoding='utf-8'))
    size_counts = Counter(v['size'] for v in jp_art.values())
    non_banner = non_banner_unit_sizes()
    static_names = static_png_names()

    used_keys = set(preserved_art.keys())
    used_sizes = {v['size'] for v in preserved_art.values() if isinstance(v, dict) and 'size' in v}

    candidates: list[tuple[int, str, int, str | None]] = []
    for key, meta in sorted(jp_art.items()):
        if not TOP_STANDIN_RX.match(key):
            continue
        if not str(meta.get('cpk', '')).startswith('gacha'):
            continue
        if key in used_keys:
            continue
        sz = meta['size']
        if size_counts[sz] != 1 or sz in non_banner or sz in used_sizes:
            continue
        if not (30000 <= sz <= 350000):
            continue
        in_static = 0 if key in static_names else 1
        candidates.append((in_static, key, sz, key if key in static_names else None))

    candidates.sort(key=lambda x: (x[0], x[1]))
    need = banner_count * 2
    if len(candidates) < need:
        raise RuntimeError(f'사용 가능한 자리표시자 부족: need={need}, have={len(candidates)}')
    return [(k, sz, glb) for _, k, sz, glb in candidates[:need]]


def update_overlays(
    report_banners: list[dict],
    picks: dict[int, dict],
) -> dict[int, tuple[str, str]]:
    ba_path = OVERLAY / 'jp_banner_art.json'
    ba_data = json.loads(ba_path.read_text(encoding='utf-8'))
    existing_art = ba_data.get('art') or {}

    preserved_art = {
        k: v
        for k, v in existing_art.items()
        if not (isinstance(v, dict) and str(v.get('path', '')).startswith(f'{DEVICE_SEASON_ART_REL}/'))
    }
    standins = allocate_standins(len(report_banners), preserved_art)

    assignments: dict[int, tuple[str, str]] = {}
    new_art = dict(preserved_art)
    for idx, b in enumerate(report_banners):
        bid = b['id']
        list_key, list_sz, list_glb = standins[2 * idx]
        detail_key, detail_sz, detail_glb = standins[2 * idx + 1]
        assignments[bid] = (list_key, detail_key)

        list_entry: dict[str, object] = {
            'path': f'{DEVICE_SEASON_ART_REL}/{bid}_list.png',
            'size': list_sz,
        }
        if list_glb:
            list_entry['global'] = list_glb
        detail_entry: dict[str, object] = {
            'path': f'{DEVICE_SEASON_ART_REL}/{bid}_detail.png',
            'size': detail_sz,
        }
        if detail_glb:
            detail_entry['global'] = detail_glb
        new_art[list_key] = list_entry
        new_art[detail_key] = detail_entry

    out_ba = dict(ba_data)
    out_ba['art'] = new_art
    ba_path.write_text(json.dumps(out_ba, ensure_ascii=False, indent=1), encoding='utf-8')

    authored_path = OVERLAY / 'gacha_authored.json'
    authored = json.loads(authored_path.read_text(encoding='utf-8'))
    for b in authored.get('banners') or []:
        bid = b['id']
        if bid in assignments:
            lk, dk = assignments[bid]
            b['art'] = {'banner': lk, 'detail_banner': dk}
    authored_path.write_text(json.dumps(authored, ensure_ascii=False, indent=1), encoding='utf-8')
    return assignments


def build_contact_sheets(report_banners: list[dict], picks: dict[int, dict]) -> list[str]:
    by_season: dict[str, list[dict]] = defaultdict(list)
    for b in report_banners:
        by_season[b['season']].append(b)

    cols = 4
    thumb_w, thumb_h = 320, 196
    pad_x, pad_y = 14, 14
    cap_h = 44
    cell_w = thumb_w + pad_x
    cell_h = thumb_h + cap_h + pad_y
    header_h = 44
    font_hdr = load_ko_font(20)
    font_cap = load_ko_font(13)

    written: list[str] = []
    for season, items in by_season.items():
        rows = (len(items) + cols - 1) // cols
        W = pad_x + cols * cell_w
        H = header_h + pad_y + rows * cell_h
        sheet = Image.new('RGB', (W, H), (18, 20, 32))
        draw = ImageDraw.Draw(sheet)
        draw.text((pad_x, 12), f'{season} ({len(items)}개 배너)', font=font_hdr, fill=(240, 244, 255))

        for i, b in enumerate(items):
            r, c = divmod(i, cols)
            x = pad_x + c * cell_w
            y = header_h + pad_y + r * cell_h
            bid = b['id']
            with Image.open(SEASON_ART_DIR / f'{bid}_list.png') as im:
                thumb = im.convert('RGB')
                thumb.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x, y))
            src_tag = picks[bid]['source']
            cap1 = f"{bid} [{src_tag}]"
            if src_tag == 'dump':
                cap1 += ' ' + Path(picks[bid]['orig_file']).stem
            while draw.textlength(cap1, font=font_cap) > thumb_w - 4 and len(cap1) > 4:
                cap1 = cap1[:-2] + '…'
            cap2 = b['name']
            while draw.textlength(cap2, font=font_cap) > thumb_w - 4 and len(cap2) > 4:
                cap2 = cap2[:-2] + '…'
            draw.text((x + 2, y + thumb_h + 4), cap1, font=font_cap, fill=(160, 195, 255))
            draw.text((x + 2, y + thumb_h + 21), cap2, font=font_cap, fill=(235, 238, 248))

        out_path = SEASON_ART_DIR / f'contact_sheet_{season}.png'
        sheet.save(out_path, format='PNG', optimize=True)
        written.append(out_path.name)
    return written


def write_reports(
    report_banners: list[dict],
    picks: dict[int, dict],
    assignments: dict[int, tuple[str, str]],
    sheets: list[str],
) -> dict:
    source_counts = Counter(picks[b['id']]['source'] for b in report_banners)
    how_counts = Counter(picks[b['id']]['match_how'] for b in report_banners)
    rows = []
    for b in report_banners:
        bid = b['id']
        pick = picks[bid]
        lk, dk = assignments[bid]
        rows.append({
            'id': bid,
            '이름': b['name'],
            '시즌': b['season'],
            '원천': pick['source'],
            '매칭_방식': pick['match_how'],
            '원본 파일': pick['orig_file'],
            '원본 경로': source_path(pick),
            '상세 원본': pick.get('dump_detail') if pick['source'] == 'dump' else (pick.get('detail_file') or pick['orig_file']),
            '겹친 유닛 수': len(pick['matched_units']),
            '겹친_유닛_예시': pick['matched_units'][:5],
            '자리표시자 이름': lk,
            '상세_자리표시자': dk,
        })

    list_hashes = {
        hashlib.sha256((SEASON_ART_DIR / f"{b['id']}_list.png").read_bytes()).hexdigest()
        for b in report_banners
    }
    detail_hashes = {
        hashlib.sha256((SEASON_ART_DIR / f"{b['id']}_detail.png").read_bytes()).hexdigest()
        for b in report_banners
    }

    report = {
        'summary': {
            'total_banners': len(report_banners),
            'by_source': dict(source_counts),
            'by_match_how': dict(how_counts),
            'unique_list_png_sha256': len(list_hashes),
            'unique_detail_png_sha256': len(detail_hashes),
            'contact_sheets': sheets,
        },
        'banners': rows,
    }
    (SEASON_ART_DIR / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    notes_lines = [
        '# 시즌/콜라보 가챠 배너 그림 매칭 및 자리표시자 배정 메모',
        '',
        f"- 전체 배너: {len(report_banners)}개",
        f"- 원천별: twitter={source_counts.get('twitter', 0)}, dump={source_counts.get('dump', 0)}, client={source_counts.get('client', 0)}, card={source_counts.get('card', 0)}",
        f"- 매칭 방식별: {dict(how_counts)}",
        f"- 목록 PNG 고유 해시: {len(list_hashes)}/{len(report_banners)}, 상세 PNG 고유 해시: {len(detail_hashes)}/{len(report_banners)}",
        '- 자리표시자 풀: build/jp_gacha_art.json 중 gacha*.cpk의 고유 크기 gacha_*_top.png (유닛 시트 및 기존 854개 이벤트 배너와 크기 충돌 없음)',
        '- 기대 크기: 목록(_list.png) 640x160 (layout_gachaTop_* common_banner), 상세(_detail.png) 626x184 (layout_gachaPayDetail_640x960 gacha_pay_main_banner)',
        '- 기기 오버라이드 경로: /data/local/tmp/ffbe/art/<배너id>_{list,detail}.png (jp_offline.js BANNER_ART가 run-as 없이 우선 읽음)',
        f"- 접촉 시트: {', '.join(sheets)}",
    ]
    (SEASON_ART_DIR / 'notes.md').write_text('\n'.join(notes_lines) + '\n', encoding='utf-8')
    return report['summary']


def main() -> None:
    rep = json.loads((GACHA_OUT / 'season_banners_report.json').read_text(encoding='utf-8'))
    report_banners = rep['banners']
    units_by_key = load_banner_units()
    tw_pool = load_twitter_pool()
    dump = load_dump_pool()
    picks = select_twitter_art(report_banners, units_by_key, tw_pool, dump)
    render_banner_pngs(report_banners, picks)
    assignments = update_overlays(report_banners, picks)
    subprocess.run([sys.executable, '-I', '-X', 'utf8', str(BUILD / 'make_jp_art_dims.py')], check=True)
    sheets = build_contact_sheets(report_banners, picks)
    summary = write_reports(report_banners, picks, assignments, sheets)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()

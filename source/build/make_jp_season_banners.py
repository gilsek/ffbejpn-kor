"""Build season x series and collaboration gacha banners for the JP offline build.

Reads `build/out/jp_offline/gacha_jp/banner_plan_draft.json` (1,648 unit families),
groups FFBE/FF families by (season, series) and collab families by title, selects
each family's lowest-rarity summonable form present in both JP F_UNIT_MST and the
engine unit table (excluding non-collectible A86KwrGh=0 and ID_CONFLICT ids),
applies provisional tier weights (low 40% / mid 30% / high NV 30%, renormalized
over present tiers), assigns JP banner art from `build/jp_gacha_art.json` with a
generic JP fallback, and writes the engine overlay + `season_banners_report.json`.

usage: python -I -X utf8 build/make_jp_season_banners.py [--out DIR]
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_jp_banners as M  # noqa: E402

ROOT = M.ROOT
SERVER = M.SERVER
STATIC = M.STATIC
OVERLAY = M.OVERLAY
REPORT = M.REPORT

FFBE_TAB_GROUP = 'ffbe'
FF_SERIES_TAB_GROUP = 'ff_series'
COLLAB_SEASON_KEY = 'collaborations'

SUMMER_NAME_RX = re.compile(r'夏|水着|バカンス|渚|常夏|爽涼', re.I)
HOLIDAY_NAME_RX = re.compile(
    r'クリスマス|聖夜|サンタ|正月|晴れ着|新春|バレンタイン|ハロウィン|浴衣|令和|グリムロード|イリュージョニスト|ドレスアップ',
    re.I,
)

MERGE_FF_SERIES = {
    'FF4TA': 'FFIV',
    'FF7AC': 'FFVII',
    'FF13-2': 'FF13',
    'LR FF13': 'FF13',
}
CANONICAL_TITLE_IDS = {
    'FFIV': '10004',
    'FFVII': '10007',
    'FF13': '10013',
}
MERGE_COLLAB_SERIES = {
    'SO1': 'SO2R',
    'SO2': 'SO2R',
    'SO3': 'SO2R',
    'SO4': 'SO2R',
    'SO5': 'SO2R',
}
CANONICAL_COLLAB_TITLE_IDS = {
    'SO2R': '20048',
}

FFBE_THEMES = [
    ('ffbe_s1', '99100001', '1st 시즌 - 라피스 편'),
    ('ffbe_s2', '99100002', '2nd 시즌 - 팔라디아 편'),
    ('ffbe_s3', '99100003', '3rd 시즌 - 할로우 편'),
    ('ffbe_s4', '99100004', '4th 시즌 - 리보니아 편'),
    ('ffbe_s5', '99100005', '5th 시즌 - 카오스 편'),
    ('ffbe_anniv_1', '99100006', '주년 스토리 I - 재림의 제전'),
    ('ffbe_anniv_2', '99100007', '주년 스토리 II - 망국의 역습'),
    ('ffbe_lineage', '99100008', '마장의 계보'),
    ('ffbe_esper', '99100009', '환수·십이무구'),
    ('ffbe_summer', '99100010', '수영복·여름 스페셜'),
    ('ffbe_holiday', '99100011', '시즌·기념 스페셜'),
    ('ffbe_orig_1', '99100012', '오리지널 I - 왕국의 기사'),
    ('ffbe_orig_2', '99100013', '오리지널 II - 이계의 강자'),
]
FFBE_THEME_META = {k: (bid, label) for k, bid, label in FFBE_THEMES}

FF_SERIES_NAMES_KO = {
    'FF零式': 'FF 영식',
    'FFBE幻影戦争': 'FFBE 환영전쟁',
}

COLLAB_NAMES_KO = {
    'ゼノギアス': '제노기어스',
    'ドラゴンクエスト ダイの大冒険': '드래곤 퀘스트 타이의 대모험',
    '鋼の錬金術師': '강철의 연금술사',
    'DQMSL': '드래곤 퀘스트 몬스터즈 슈퍼 라이트',
    'ドラゴンクエスト列伝 ロトの紋章': '드래곤 퀘스트 열전 로토의 문장',
    '聖剣伝説3': '성검전설 3',
    'DQXIS': '드래곤 퀘스트 XI S',
    '聖剣伝説2': '성검전설 2',
    'ヴァルキリープロファイル': '발키리 프로파일',
    '聖剣伝説LoM': '성검전설 레전드 오브 마나',
    'モンスターハンターエクスプロア': '몬스터 헌터 익스플로어',
    'NieR:Automata': '니어: 오토마타',
    'RomancingSa・Ga3': '로맨싱 사가 3',
    'SO2R': '스타 오션 시리즈',
    'キングダム ハーツIII': '킹덤 하츠 III',
    'クロノ・クロス': '크로노 크로스',
    'SINoALICE': '시노앨리스',
    'ブレイブ フロンティア': '브레이브 프론티어',
    'BRAVELYDEFAULT': '브레이블리 디폴트',
    'KH': '킹덤 하츠',
    'オクトパストラベラー': '옥토패스 트래블러',
    'キングスナイト WoDD': '킹스 나이트',
    'CRYSTAL DEFENDERS': '크리스탈 디펜더즈',
    'ImperialSaGa': '임페리얼 사가',
    'WOFF': '월드 오브 파이널 판타지',
    '聖剣伝説 VoM': '성검전설 비전스 오브 마나',
    'BRAVELYSECOND': '브레이블리 세컨드',
    'RomancingSa・Ga': '로맨싱 사가',
    'RomancingSa・Ga2': '로맨싱 사가 2',
    'SO3': '스타 오션 3',
    'SaGa Frontier': '사가 프론티어',
    'SaGa Frontier2': '사가 프론티어 2',
    'アクトレイザー': '액트레이저',
    'パラサイト・イヴ': '패러사이트 이브',
    '南国少年パプワくん': '남국소년 파푸와군',
    '聖剣伝説': '성검전설',
    '魔法陣グルグル': '마법진 구루구루',
    'ARIANA GRANDE': '아리아나 그란데',
    'BRAVELYDEFAULTFE': '브레이블리 디폴트 페어리즈 이펙트',
    'FINAL FANTASY Record Keeper': '파이널 판타지 레코드 키퍼',
    'KATY PERRY': '케이티 페리',
    'SO1': '스타 오션 1',
    'SO2': '스타 오션 2',
    'SO4': '스타 오션 4',
    'SO5': '스타 오션 5',
    'TERRA BATTLE': '테라 배틀',
    'キングダム ハーツ ダーク ロード': '킹덤 하츠 다크 로드',
    'ララ・クロフト アンド テンプル オブ オシリス': '라라 크로프트와 오시리스의 사원',
    'リコドキッ！': '리코도키!',
}

COLLAB_SERIES_ORDER = [
    # 1. FF 외전 / 스퀘어 에닉스 FF 연관
    'WOFF',
    'FINAL FANTASY Record Keeper',
    'CRYSTAL DEFENDERS',
    'キングスナイト WoDD',
    # 2. 드래곤 퀘스트 시리즈
    'DQXIS',
    'DQMSL',
    'ドラゴンクエスト ダイの大冒険',
    'ドラゴンクエスト列伝 ロトの紋章',
    # 3. 성검전설 시리즈
    '聖剣伝説',
    '聖剣伝説2',
    '聖剣伝説3',
    '聖剣伝説LoM',
    '聖剣伝説 VoM',
    # 4. 사가 시리즈
    'RomancingSa・Ga',
    'RomancingSa・Ga2',
    'RomancingSa・Ga3',
    'SaGa Frontier',
    'SaGa Frontier2',
    'ImperialSaGa',
    # 5. 킹덤 하츠 시리즈
    'KH',
    'キングダム ハーツIII',
    'キングダム ハーツ ダーク ロード',
    # 6. 브레이블리 시리즈
    'BRAVELYDEFAULT',
    'BRAVELYSECOND',
    'BRAVELYDEFAULTFE',
    # 7. 니어 / 시노앨리스
    'NieR:Automata',
    'SINoALICE',
    # 8. 스퀘어 에닉스 명작 RPG
    'ゼノギアス',
    'クロノ・クロス',
    'ヴァルキリープロファイル',
    'SO2R',
    'オクトパストラベラー',
    'アクトレイザー',
    'パラサイト・イヴ',
    # 9. 만화 / 애니메이션 콜라보
    '鋼の錬金術師',
    '魔法陣グルグル',
    '南国少年パプワくん',
    'リコドキッ！',
    # 10. 타사 게임 / 아티스트 콜라보
    'モンスターハンターエクスプロア',
    'ブレイブ フロンティア',
    'TERRA BATTLE',
    'ララ・クロフト アンド テンプル オブ オシリス',
    'ARIANA GRANDE',
    'KATY PERRY',
]
COLLAB_ORDER_MAP = {title: idx for idx, title in enumerate(COLLAB_SERIES_ORDER)}

TIER_WEIGHTS = {
    'low': 0.40,   # base ★3-★4 (plus ★1-★2 placed into low tier)
    'mid': 0.30,   # base ★5 (plus ★6 placed into mid tier)
    'high': 0.30,  # base ★7 (NV)
}

DEFAULT_JP_ART_TOP = 'gacha_20250630_allNVplus_11ren_top.png'

# Regexes matching JP `gacha_<date>_<theme>_top.png` themes (excluding NOT_SUMMON).
SERIES_ART_RX = {
    'FFBE': r'(?<![A-Z0-9])FFBE(?!幻|anniv)',
    'FFBE幻影戦争': r'WOTV',
    'FFI': r'(?<![A-Z0-9])FF1(?![0-9])',
    'FFII': r'(?<![A-Z0-9])FF2(?![0-9])',
    'FFIII': r'(?<![A-Z0-9])FF3(?![0-9])',
    'FFIV': r'(?<![A-Z0-9])FF4(?![0-9]|TA)',
    'FFV': r'(?<![A-Z0-9])FF5(?![0-9])',
    'FF6': r'(?<![A-Z0-9])FF6(?![0-9])',
    'FFVII': r'(?<![A-Z0-9])FF7(?!R|AC|[0-9])',
    'FFVIII': r'(?<![A-Z0-9])FF8(?![0-9])',
    'FFIX': r'(?<![A-Z0-9])FF9(?![0-9])',
    'FFX': r'(?<![A-Z0-9])FF10(?![0-9])',
    'FF11': r'(?<![A-Z0-9])FF11(?![0-9])',
    'FFXII': r'(?<![A-Z0-9])FF12(?![0-9])',
    'FF13': r'(?<![A-Z0-9])FF13(?![0-9])',
    'FF14': r'(?<![A-Z0-9])FF14(?![0-9])',
    'FF15': r'(?<![A-Z0-9])FF15(?![0-9])',
    'FF16': r'(?<![A-Z0-9])FF16(?![0-9])',
    'FFT': r'(?<![A-Z0-9])FFT(?![A-Z0-9])',
    'FF零式': r'(?<![A-Z0-9])FF0(?![0-9])',
    'CCFF7': r'CCFF7',
    'FF7AC': r'FF7AC',
    'FFX-2': r'FF10-2|FFX-2',
    'FF13-2': r'FF13-2',
    'LR FF13': r'LRFF13',
    'FF4TA': r'FF4TA',
    'ゼノギアス': r'xeno',
    '聖剣伝説LoM': r'LoM',
}


def tier_for_rarity(rarity):
    if 1 <= rarity <= 4:
        return 'low'
    if 5 <= rarity <= 6:
        return 'mid'
    if rarity == 7:
        return 'high'
    raise ValueError(f'Unsupported base rarity: {rarity}')


def pick_detail_banner(top_name, art):
    m = re.match(r'^gacha_(\d{8})_(.+)_top\.png$', top_name)
    if not m:
        return top_name
    date, theme = m.groups()
    base = M.VARIANT.sub('', theme)
    cands = [
        f'gacha_{date}_{base}_single.png',
        f'gacha_{date}_{theme}_single.png',
        f'gacha_{date}_{theme}_01.png',
        f'gacha_{date}_{base}_01.png',
    ]
    return next((c for c in cands if c in art), top_name)


def build_art_selector(art):
    tops = [
        n for n in sorted(art)
        if re.match(r'^gacha_\d{8}_.+_top\.png$', n)
        and art[n].get('cpk', '').startswith('gacha')
        and not M.NOT_SUMMON.search(n)
    ]

    def choose(title):
        rx = SERIES_ART_RX.get(title)
        if rx:
            matches = [
                n for n in tops
                if re.search(rx, re.sub(r'^gacha_\d{8}_|_top\.png$', '', n), re.I)
            ]
            non_rerun = [n for n in matches if not M.RERUN.search(n)]
            pool = non_rerun or matches
            if pool:
                no_variant = [n for n in pool if not M.VARIANT.search(re.sub(r'^gacha_\d{8}_|_top\.png$', '', n))]
                top = (no_variant or pool)[-1]
                return top, pick_detail_banner(top, art), False
        return DEFAULT_JP_ART_TOP, pick_detail_banner(DEFAULT_JP_ART_TOP, art), True

    return choose


def find_nva_normal_nv(rows, jp_by_id, jp_by_fam, engine_units):
    """NVA 유닛의 shift=1 분리 family를 통상(shift=0) NV 폼으로 복원한다."""
    for r in rows:
        if (
            r['3HriTp6B'] in engine_units
            and str(r.get('9fW0TePj', '')).isdigit()
            and str(r.get('A86KwrGh', '1')) != '0'
            and str(r.get('I3SKJ4q0', '0')) != '0'
        ):
            ser_id = str(r.get('JPW8Vs40') or '')
            ser_row = jp_by_id.get(ser_id)
            if (
                ser_row
                and ser_id in engine_units
                and ser_id not in M.ID_CONFLICT
                and str(ser_row.get('9fW0TePj', '')).isdigit()
                and str(ser_row.get('A86KwrGh', '1')) != '0'
                and str(ser_row.get('I3SKJ4q0', '0')) == '0'
            ):
                base_rows = jp_by_fam.get(ser_row['woghJa61'], ())
                min_r = min(
                    (int(x['9fW0TePj']) for x in base_rows if str(x.get('9fW0TePj', '')).isdigit()),
                    default=7,
                )
                if min_r < 7:
                    return ser_row
    return None


def classify_exclusion(rows, engine_units):
    if not rows:
        return 'missing_in_jp'
    in_engine = [r for r in rows if r['3HriTp6B'] in engine_units]
    if not in_engine:
        return 'not_in_engine'
    collectible = [r for r in in_engine if str(r.get('A86KwrGh', '1')) != '0']
    if not collectible:
        return 'not_collectible'
    non_shift = [r for r in collectible if str(r.get('I3SKJ4q0', '0')) == '0']
    if not non_shift:
        return 'brave_shift_form'
    non_conflict = [r for r in non_shift if r['3HriTp6B'] not in M.ID_CONFLICT]
    if not non_conflict:
        return 'id_conflict'
    return 'invalid_rarity'


def make_banner_id(tab_group, title_id_or_theme):
    if tab_group == FFBE_TAB_GROUP:
        return FFBE_THEME_META[title_id_or_theme][0]
    if not re.fullmatch(r'\d{5}', str(title_id_or_theme)):
        raise ValueError(f'Unexpected title_id {title_id_or_theme!r}')
    s_digit = '9' if tab_group == COLLAB_SEASON_KEY else '2'
    return f'99{s_digit}{title_id_or_theme}'


def classify_ffbe_theme(rec, fam_u):
    """FFBE 유닛 계열을 비-중복 테마(1st~5th, 주년 I/II, 마장의 계보, 환수·십이무구, 수영복, 시즌, 오리지널 I/II)로 분류한다."""
    all_names = ' '.join(fu.get('G4L0YIB2') or '' for fu in fam_u)
    scs = set()
    for fu in fam_u:
        for tok in re.split(r'[,:]', str(fu.get('GPUkhv72', ''))):
            tok = tok.strip()
            if tok:
                scs.add(tok)
    if SUMMER_NAME_RX.search(all_names):
        return 'ffbe_summer'
    if HOLIDAY_NAME_RX.search(all_names):
        return 'ffbe_holiday'
    if '40000013' in scs:
        return 'ffbe_lineage'
    if '40000012' in scs:
        return '_anniv_pending'
    if '武神参詣' in all_names:
        return '_orig_pending'
    if any(x in scs for x in ('40000017', '40000025', '40000014')):
        return 'ffbe_esper'
    if '40000035' in scs or rec.get('season') == 'S5':
        return 'ffbe_s5'
    if '40000004' in scs:
        return 'ffbe_s4'
    if '40000003' in scs:
        return 'ffbe_s3'
    if '40000002' in scs:
        return 'ffbe_s2'
    if '40000001' in scs:
        return 'ffbe_s1'
    return '_orig_pending'


def compute_pool(chosen_rows):
    """Build explicit pool entries using provisional tier weights renormalized over present tiers."""
    by_tier = collections.defaultdict(list)
    for row in chosen_rows:
        rarity = int(row['9fW0TePj'])
        by_tier[tier_for_rarity(rarity)].append((row['3HriTp6B'], rarity))
    present_weight = sum(TIER_WEIGHTS[t] for t in by_tier)
    if present_weight <= 0:
        raise ValueError('No valid tiers in banner')
    entries = []
    for tier, items in by_tier.items():
        per_unit_rate = (TIER_WEIGHTS[tier] / present_weight) / len(items)
        for uid, rarity in items:
            entries.append({'unit_id': uid, 'rarity': rarity, 'rate': per_unit_rate})
    entries.sort(key=lambda e: (-e['rarity'], e['unit_id']))
    tier_counts = {t: len(by_tier.get(t, ())) for t in ('low', 'mid', 'high')}
    rarity_counts = dict(sorted(collections.Counter(e['rarity'] for e in entries).items()))
    return entries, tier_counts, rarity_counts


def run_self_checks(banners, draft, excluded, jp_by_id, engine_units, art, uid_to_draft_fam):
    checks = {}

    ids = [b['id'] for b in banners]
    assert len(ids) == len(set(ids)), 'Duplicate banner id'
    checks['unique_banner_ids'] = len(ids)

    max_rate_err = 0.0
    for b in banners:
        s = sum(float(e['rate']) for e in b['pool'])
        err = abs(s - 1.0)
        max_rate_err = max(max_rate_err, err)
        assert err <= 1e-6, f'Rate sum mismatch on {b["id"]}: {s}'
    checks['max_rate_sum_error'] = max_rate_err

    seen_uids = set()
    seen_families = {}
    pool_unit_count = 0
    for b in banners:
        pool_ids = set()
        for e in b['pool']:
            uid = str(e['unit_id'])
            assert uid not in seen_uids, f'Unit {uid} duplicated across pools'
            seen_uids.add(uid)
            pool_ids.add(uid)
            pool_unit_count += 1
            assert uid in jp_by_id, f'Unit {uid} missing in JP F_UNIT_MST'
            assert uid in engine_units, f'Unit {uid} missing in engine F_UNIT_MST'
            assert str(jp_by_id[uid].get('A86KwrGh', '1')) != '0', f'Non-collectible {uid}'
            assert str(jp_by_id[uid].get('I3SKJ4q0', '0')) == '0', f'Brave shift form {uid}'
            assert uid not in M.ID_CONFLICT, f'ID_CONFLICT {uid}'
            fam = uid_to_draft_fam[uid]
            assert fam not in seen_families, f'Family {fam} duplicated in {seen_families[fam]} and {b["id"]}'
            seen_families[fam] = b['id']
        assert set(b.get('preview_units') or []) <= pool_ids, f'Preview outside pool in {b["id"]}'
    checks['unique_pool_families'] = len(seen_families)
    checks['total_pool_units'] = pool_unit_count

    for b in banners:
        for key in ('banner', 'detail_banner'):
            img = (b.get('art') or {}).get(key)
            assert img in art, f'Art {img} missing from jp_gacha_art.json'
            assert art[img].get('cpk', '').startswith('gacha'), f'Art {img} not in gacha CPK'
    checks['all_art_in_jp_gacha_art'] = True

    draft_fams = {r['family'] for r in draft}
    excl_fams = {e['family'] for e in excluded}
    assert len(draft) == len(draft_fams), 'Duplicate family in draft'
    assert not (set(seen_families) & excl_fams), 'Overlap between included and excluded families'
    assert set(seen_families) | excl_fams == draft_fams, 'Family partition mismatch'
    assert len(draft) == len(seen_families) + len(excl_fams), 'Count mismatch'
    checks['draft_partition'] = {
        'draft': len(draft),
        'included': len(seen_families),
        'excluded': len(excl_fams),
    }
    checks['all_passed'] = True
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='Write overlay and report files to DIR instead of default paths')
    args = parser.parse_args()

    overlay_dir = args.out.resolve() if args.out else OVERLAY
    report_dir = args.out.resolve() if args.out else REPORT
    overlay_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    draft = json.loads((ROOT / 'build/out/jp_offline/gacha_jp/banner_plan_draft.json').read_text(encoding='utf-8'))
    art = json.loads((ROOT / 'build/jp_gacha_art.json').read_text(encoding='utf-8'))
    assert DEFAULT_JP_ART_TOP in art, f'Missing fallback art {DEFAULT_JP_ART_TOP}'

    jp_units, _, _ = M.jp_masters()
    jp_by_id = {r['3HriTp6B']: r for r in jp_units}
    jp_by_fam = collections.defaultdict(list)
    for r in jp_units:
        jp_by_fam[r['woghJa61']].append(r)

    engine_units = {}
    with open(STATIC / 'mst_decoded/F_UNIT_MST.ndjson', encoding='utf-8') as fh:
        for line in fh:
            r = json.loads(line)
            engine_units[r['3HriTp6B']] = r

    # Compute collab totals and canonical FF/collab title ids; FFBE splits into 13 thematic pools,
    # non-FFBE series merge across seasons (with small spin-offs merged into main entries).
    collab_totals = collections.Counter()
    for rec in draft:
        if rec['group'] == 'collab':
            collab_totals[MERGE_COLLAB_SERIES.get(rec['title'], rec['title'])] += 1

    grouped = collections.defaultdict(list)
    title_ids = {}
    anniv_pending = []
    orig_pending = []
    excluded = []
    fallback_base_forms = []
    uid_to_draft_fam = {}
    r1_r2_into_low = 0
    r6_into_mid = 0

    for rec in draft:
        fam = rec['family']
        rows = jp_by_fam.get(fam, [])
        usable = [
            r for r in rows
            if r['3HriTp6B'] in engine_units
            and str(r.get('9fW0TePj', '')).isdigit()
            and str(r.get('A86KwrGh', '1')) != '0'
            and str(r.get('I3SKJ4q0', '0')) == '0'
            and r['3HriTp6B'] not in M.ID_CONFLICT
        ]
        if usable:
            chosen = min(
                usable,
                key=lambda r: (
                    int(r['9fW0TePj']),
                    r['3HriTp6B'] != fam,
                    int(r.get('aU3o2D4t') or 0),
                    r['3HriTp6B'],
                ),
            )
            if chosen['3HriTp6B'] != fam:
                fallback_base_forms.append({
                    'family': fam,
                    'chosen_id': chosen['3HriTp6B'],
                    'name': rec['name'],
                    'reason': 'base form in ID_CONFLICT; used non-conflict form',
                })
        else:
            chosen = find_nva_normal_nv(rows, jp_by_id, jp_by_fam, engine_units)
        if chosen is None:
            excluded.append({
                'family': fam,
                'name': rec['name'],
                'title': rec['title'],
                'group': rec['group'],
                'season': rec['season'],
                'reason': classify_exclusion(rows, engine_units),
                'jp_unit_ids': [r['3HriTp6B'] for r in rows],
            })
            continue
        uid = chosen['3HriTp6B']
        assert uid not in uid_to_draft_fam, f'Duplicate unit_id {uid} for families {uid_to_draft_fam[uid]} and {fam}'
        uid_to_draft_fam[uid] = fam
        r_val = int(chosen['9fW0TePj'])
        if r_val in (1, 2):
            r1_r2_into_low += 1
        elif r_val == 6:
            r6_into_mid += 1

        if rec['group'] == 'collab':
            merged_collab = MERGE_COLLAB_SERIES.get(rec['title'], rec['title'])
            key = (COLLAB_SEASON_KEY, merged_collab)
            grouped[key].append(chosen)
            tid = CANONICAL_COLLAB_TITLE_IDS.get(merged_collab) or chosen['taQ69cIx']
            if key in title_ids and title_ids[key] != tid:
                raise ValueError(f'Multiple title_ids for {key}: {title_ids[key]} vs {tid}')
            title_ids[key] = tid
        elif rec['title'] == 'FFBE':
            bucket = classify_ffbe_theme(rec, rows)
            sort_item = (rec.get('first_seen') or '9999-99-99', int(fam), chosen)
            if bucket == '_anniv_pending':
                anniv_pending.append(sort_item)
            elif bucket == '_orig_pending':
                orig_pending.append(sort_item)
            else:
                grouped[(FFBE_TAB_GROUP, bucket)].append(chosen)
        else:
            merged_title = MERGE_FF_SERIES.get(rec['title'], rec['title'])
            key = (FF_SERIES_TAB_GROUP, merged_title)
            grouped[key].append(chosen)
            tid = CANONICAL_TITLE_IDS.get(merged_title) or chosen['taQ69cIx']
            if key in title_ids and title_ids[key] != tid:
                raise ValueError(f'Multiple title_ids for {key}: {title_ids[key]} vs {tid}')
            title_ids[key] = tid

    anniv_pending.sort()
    mid_anniv = len(anniv_pending) // 2
    for _, _, chosen in anniv_pending[:mid_anniv]:
        grouped[(FFBE_TAB_GROUP, 'ffbe_anniv_1')].append(chosen)
    for _, _, chosen in anniv_pending[mid_anniv:]:
        grouped[(FFBE_TAB_GROUP, 'ffbe_anniv_2')].append(chosen)

    by_orig_tier = collections.defaultdict(list)
    for first_seen, _, chosen in orig_pending:
        by_orig_tier[tier_for_rarity(int(chosen['9fW0TePj']))].append(
            (first_seen, int(chosen['3HriTp6B']), chosen)
        )
    for tier in ('high', 'mid', 'low'):
        tier_items = sorted(by_orig_tier[tier], key=lambda item: (item[0], item[1]))
        mid_orig = len(tier_items) // 2
        for _, _, chosen in tier_items[:mid_orig]:
            grouped[(FFBE_TAB_GROUP, 'ffbe_orig_1')].append(chosen)
        for _, _, chosen in tier_items[mid_orig:]:
            grouped[(FFBE_TAB_GROUP, 'ffbe_orig_2')].append(chosen)

    ffbe_keys = [(FFBE_TAB_GROUP, k) for k, _, _ in FFBE_THEMES if (FFBE_TAB_GROUP, k) in grouped]
    ff_series_sort_order = {
        '11012': (10007, 1),  # CCFF7 directly after FFVII
        '11004': (10010, 1),  # FFX-2 directly after FFX
    }
    ff_series_keys = sorted(
        (k for k in grouped if k[0] == FF_SERIES_TAB_GROUP),
        key=lambda k: (ff_series_sort_order.get(str(title_ids[k]), (int(title_ids[k]), 0)), k[1]),
    )
    collab_keys = sorted(
        (k for k in grouped if k[0] == COLLAB_SEASON_KEY),
        key=lambda k: (COLLAB_ORDER_MAP.get(k[1], 999), -collab_totals[k[1]], k[1]),
    )
    ordered_keys = ffbe_keys + ff_series_keys + collab_keys

    choose_art = build_art_selector(art)
    banners = []
    report_banners = []
    total_banners = len(ordered_keys)

    for idx, key in enumerate(ordered_keys):
        tab_group, sub_key = key
        chosen_rows = grouped[key]
        if tab_group == FFBE_TAB_GROUP:
            bid = make_banner_id(tab_group, sub_key)
            name = FFBE_THEME_META[sub_key][1]
            title = 'FFBE'
        elif tab_group == FF_SERIES_TAB_GROUP:
            bid = make_banner_id(tab_group, title_ids[key])
            name = FF_SERIES_NAMES_KO.get(sub_key, sub_key)
            title = sub_key
        else:
            bid = make_banner_id(tab_group, title_ids[key])
            name = COLLAB_NAMES_KO.get(sub_key, sub_key)
            title = sub_key

        pool, tier_counts, rarity_counts = compute_pool(chosen_rows)
        # 상세 화면 무대 대표 유닛: NV 배너는 NV 전원을 세우고, NV가 없는 구 배너는 ★5(없으면 최고 등급)를 세운다.
        top_rarity = max(int(p['rarity']) for p in pool)
        floor = 7 if top_rarity == 7 else (5 if top_rarity >= 5 else top_rarity)
        preview = [
            p['unit_id']
            for p in sorted(pool, key=lambda p: (-int(p['rarity']), str(p['unit_id'])))
            if int(p['rarity']) >= floor
        ]
        top_art, detail_art, used_default_art = choose_art(title)
        disp_order = total_banners - idx

        banner = M.one_lapis({
            'id': bid,
            'region': 'jp',
            'type': 'normal',
            'source': 'jp',
            'name': name,
            'detail_id': bid,
            'exe_type': 'primary',
            'ticket_group_id': 10020,
            'cost': {'kind': 'lapis', 'amount': 500},
            'draws': 1,
            'secondary_offer': {
                'cost': {'kind': 'lapis', 'amount': 5000},
                'draws': 11,
                'exe_count': 1,
                'img_btn': 'gacha_btns_gold_11',
            },
            'release': '2025-01-01',
            'season': tab_group,
            'tab_group': tab_group,
            'schedule': {
                'disp_order': disp_order,
                'banner_type': 0,
                'window': {'from': '2025-01-01 00:00:00', 'to': '2099-12-31 23:59:59'},
            },
            'art': {
                'banner': top_art,
                'detail_banner': detail_art,
                'anime_file': 'gacha_animation',
                'anime_name': 'gacha_moogle_rare/anime',
                'img_btn': 'gacha_btn_n',
            },
            'pool': pool,
            'preview_units': preview,
        })
        banners.append(banner)
        report_banners.append({
            'id': bid,
            'name': name,
            'season': tab_group,
            'tab_group': tab_group,
            'title': title,
            'theme_key': sub_key if tab_group == FFBE_TAB_GROUP else None,
            'disp_order': disp_order,
            'family_count': len(pool),
            'tier_counts': tier_counts,
            'rarity_counts': {str(k): v for k, v in rarity_counts.items()},
            'art': {'banner': top_art, 'detail_banner': detail_art},
            'default_art': used_default_art,
        })

    checks = run_self_checks(banners, draft, excluded, jp_by_id, engine_units, art, uid_to_draft_fam)

    authored = json.loads((SERVER / 'gacha_authored.json').read_text(encoding='utf-8'))
    authored['banners'] = banners
    authored['_meta'] = dict(
        authored.get('_meta') or {},
        jp_build='build/make_jp_season_banners.py (3tab ffbe+ff_series+collab)',
    )
    (overlay_dir / 'gacha_authored.json').write_text(
        json.dumps(authored, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8',
    )
    empty_doc = '{"banners": [], "campaigns": {}, "standard": []}\n'
    for fn in ('gacha_catalogue.json', 'gacha_community.json', 'gacha_named.json', 'gacha_standard.json'):
        (overlay_dir / fn).write_text(empty_doc, encoding='utf-8')
    (overlay_dir / 'gacha_only.txt').write_text('', encoding='utf-8')

    feed = {}
    event_map_path = OVERLAY / 'jp_event_art.json'
    if event_map_path.is_file():
        feed.update(json.loads(event_map_path.read_text(encoding='utf-8')).get('art') or {})

    art_doc = {'art': feed}
    existing_art_path = (overlay_dir / 'jp_banner_art.json') if (overlay_dir / 'jp_banner_art.json').is_file() else (OVERLAY / 'jp_banner_art.json')
    if existing_art_path.is_file():
        try:
            existing = json.loads(existing_art_path.read_text(encoding='utf-8'))
            if isinstance(existing, dict):
                art_doc = existing
                art_doc['art'] = feed
        except ValueError:
            pass
    (overlay_dir / 'jp_banner_art.json').write_text(
        json.dumps(art_doc, ensure_ascii=False, indent=0, sort_keys=True),
        encoding='utf-8',
    )

    by_season = dict(sorted(collections.Counter(b['season'] for b in report_banners).items()))
    excl_by_reason = dict(sorted(collections.Counter(e['reason'] for e in excluded).items()))
    default_art_banners = [b['id'] for b in report_banners if b['default_art']]
    rep = {
        'summary': {
            'total_banners': len(report_banners),
            'by_season': by_season,
            'ffbe_banners': len(ffbe_keys),
            'ff_series_banners': len(ff_series_keys),
            'collab_banners': len(collab_keys),
            'draft_families': len(draft),
            'included_families': checks['unique_pool_families'],
            'excluded_families': len(excluded),
            'excluded_by_reason': excl_by_reason,
            'r1_r2_into_low_tier': r1_r2_into_low,
            'r6_into_mid_tier': r6_into_mid,
            'default_art_banner_count': len(default_art_banners),
            'series_art_banner_count': len(report_banners) - len(default_art_banners),
            'fallback_base_form_families': fallback_base_forms,
            'jp_banner_art_entries': len(feed),
        },
        'banners': report_banners,
        'excluded_families': excluded,
        'checks': checks,
    }
    (report_dir / 'season_banners_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=1),
        encoding='utf-8',
    )
    print(json.dumps(rep['summary'], ensure_ascii=False))
    if args.out is None:
        import make_jp_season_banner_art
        make_jp_season_banner_art.main()


if __name__ == '__main__':
    main()

"""Refine OCR results with strict filtering and precise UI dictionary matching.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / 'build/out/sprite_work'
CACHE_DIR = WORK_DIR / 'cache'
TARGETS_DIR = ROOT / 'build/out/sprite_targets'

JP_CHAR_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]')
NON_JP_RE = re.compile(r'^[0-9A-Za-z\s\.,:;!\?_/\-\+\*=\(\)\[\]#%&~`"\'×©™★☆●○◆◇▲▼◀▶←→↑↓]+$')

PAIR_SUFFIXES = [
    '_on.png', '_off.png', '_s1.png', '_s2.png', '_l1.png', '_l2.png',
    '_1.png', '_2.png', '_3.png', '_4.png', '_press.png', '_selected.png',
    '_dis.png', '_active.png', '_normal.png', '-on.png', '-off.png'
]

# Obvious non-text prefixes/patterns that are purely graphics or numbers
EXCLUDE_PREFIXES = [
    'direction_', 'item_frame', 'minimap_', 'virtualpad_', 'charastand_',
    'wavebg_', 'battlenum_', 'cursor_', 'sys_signal', 'sys_battery',
    'gacha_label_rarity', 'gacha_label_step', 'colo_round', 'battle_result',
    'cre_pickup', 'dic_no_', 'dic_libra_mini', 'friend_icon_', 'battle_com_icon_',
    'battle_com_mini_', 'lgb_itemnum_', 'button_middle_growequipment',
    'battle_multipleparty_unit_hp', 'unit_raritystar_', 'unit_charastand_',
    'colosseum_btn_normal', 'Button_harf_rankingbattle'
]

# Manual corrections for OCR-distorted text on genuine UI sprites
CORRECTIONS = {
    'arena_party_icon1.png': ('アリーナパーティ', '아레나 파티'),
    'arena_party_icon2.png': ('アリーナパーティ', '아레나 파티'),
    'copy_party_icon1.png': ('パーティコピー', '파티 복사'),
    'copy_party_icon2.png': ('パーティコピー', '파티 복사'),
    'batchselection_party_icon1.png': ('一括選択', '일괄 선택'),
    'batchselection_party_icon2.png': ('一括選択', '일괄 선택'),
    'awakening_transform_icon1.png': ('覚醒変換', '각성 변환'),
    'awakening_transform_icon2.png': ('覚醒変換', '각성 변환'),
    'largebutton_label_warehouse.png': ('倉庫', '창고'),
    'largebutton_round_label_fragmentshop.png': ('欠片ショップ', '조각 상점'),
    'middlebutton_label_change.png': ('入替', '교체'),
    'middlebutton_label_status.png': ('ステータス', '스테이터스'),
    'unit_awakening_icon1.png': ('ユニット覚醒', '유닛 각성'),
    'unit_awakening_icon2.png': ('ユニット覚醒', '유닛 각성'),
    'largebutton_label_ability_powerup.png': ('アビリティ強化', '어빌리티 강화'),
    'largebutton_label_evo.png': ('ユニット覚醒', '유닛 각성'),
    'largebutton_label_list.png': ('一覧', '목록'),
    'largebutton_label_powerup.png': ('ユニット強化', '유닛 강화'),
    'largebutton_label_sale.png': ('売却', '매각'),
    'middlebutton_label_conversion.png': ('変換', '변환'),
    'middlebutton_label_powerup_awake.png': ('強化/覚醒', '강화/각성'),
    'middlebutton_s_label_display_switch.png': ('表示切替', '표시 전환'),
    'middlebutton_s_label_equipcopy.png': ('装備同期', '장비 동기화'),
    'middlebutton_s_label_equipfav.png': ('お気に入り登録', '즐겨찾기 등록'),
    'unit_leaderskillbg.png': ('リーダースキル', '리더 스킬'),
    'unit_notequipped.png': ('専用装備未装備', '전용 장비 미장착'),
    'unit_party_arena.png': ('アリーナ', '아레나'),
    'unit_party_arena_atk.png': ('アリーナ攻撃', '아레나 공격'),
    'unit_party_arena_def.png': ('アリーナ防衛', '아레나 방어'),
    'unit_party_colosseum.png': ('コロシアム', '콜로세움'),
    'battle_tower_button_label_party1.png': ('パーティ1', '파티 1'),
    'battle_tower_button_label_party2.png': ('パーティ2', '파티 2'),
    'battle_tower_button_label_party3.png': ('パーティ3', '파티 3'),
    'battle_tower_change_party1.png': ('出撃パーティ変更', '출격 파티 변경'),
    'battle_tower_change_party2.png': ('出撃パーティ変更', '출격 파티 변경'),
    'battle_multipleparty_decision_btn1.png': ('決定', '결정'),
    'battle_multipleparty_decision_btn2.png': ('決定', '결정'),
    'battle_multipleparty_reset_btn1.png': ('リセット', '리셋'),
    'battle_multipleparty_reset_btn2.png': ('リセット', '리셋'),
    'battle_multipleparty_shift_btn1.png': ('入れ替え', '교체'),
    'battle_multipleparty_shift_btn2.png': ('入れ替え', '교체'),
    'battle_multipleparty_shift.png': ('入れ替え', '교체'),
    'battle_multipleparty_replace_choosing.png': ('選択中', '선택 중'),
    'battle_multipleparty_tab_sortie_1.png': ('出撃ユニット', '출격 유닛'),
    'battle_multipleparty_tab_sortie_2.png': ('出撃ユニット', '출격 유닛'),
    'battle_multipleparty_tab_wait_1.png': ('待機ユニット', '대기 유닛'),
    'battle_multipleparty_tab_wait_2.png': ('待機ユニット', '대기 유닛'),
    'battle_com_targetparty_btn1.png': ('パーティ選択', '파티 선택'),
    'battle_com_targetparty_btn2.png': ('パーティ選択', '파티 선택'),
}


def load_records():
    idx_path = ROOT / 'build/out/sprite_sheets/index.json'
    rec_path = TARGETS_DIR / 'records.txt'
    records_map = {}
    if idx_path.exists() and rec_path.exists():
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        for line in rec_path.read_text(encoding='utf-8').splitlines():
            p = line.split('|')
            if len(p) == 4:
                sheet, cell, ja, ko = p[0].strip(), int(p[1].strip()), p[2].strip(), p[3].strip()
                if sheet in idx and cell - 1 < len(idx[sheet]):
                    spr_name = idx[sheet][cell - 1]
                    records_map[spr_name] = (ja, ko)
    return records_map


def load_glossary():
    glossary = {}
    gpath = WORK_DIR / 'glossary.tsv'
    if gpath.exists():
        for line in gpath.read_text(encoding='utf-8').splitlines():
            p = line.split('\t')
            if len(p) >= 2 and p[0].strip() and p[1].strip():
                glossary[p[0].strip()] = p[1].strip()
    return glossary


def load_official_ui():
    ja_path = ROOT / 'build/out/text_ja.csv'
    ko_path = ROOT / 'translations/ui-ko/text_ko_memorial.csv'
    official = {}
    if ja_path.exists() and ko_path.exists():
        ja_map = {}
        for r in csv.reader(open(ja_path, encoding='utf-8-sig')):
            if len(r) >= 2 and r[0].strip():
                ja_map[r[0].strip()] = r[1].strip()
        ko_map = {}
        for r in csv.reader(open(ko_path, encoding='utf-8-sig')):
            if len(r) >= 2 and r[0].strip():
                ko_map[r[0].strip()] = r[1].strip()
        for k, j in ja_map.items():
            if k in ko_map and j and ko_map[k]:
                k_val = re.sub(r'<[^>]+>', '', ko_map[k]).strip()
                j_val = re.sub(r'<[^>]+>', '', j).strip()
                if j_val and k_val and len(j_val) <= 20:
                    official[j_val] = k_val
    return official


EXTRA_TERMS = {
    '昇順': '오름차순',
    '降順': '내림차순',
    'フレンド登録日': '친구 등록일',
    'アビリティ1': '어빌리티 1',
    'アビリティ2': '어빌리티 2',
    'アビリティ3': '어빌리티 3',
    'アビリティ4': '어빌리티 4',
    'アクセ1': '악세 1',
    'アクセ2': '악세 2',
    '獣': '야수',
    '鳥': '조류',
    '悪魔': '악마',
    '竜': '용',
    '人系': '인간계',
    '虫系': '곤충계',
    '植物系': '식물계',
    '死霊系': '사령계',
    '水棲': '수서',
    'からだ': '몸',
    '限界突破': '한계돌파',
    'バーストストーン上昇量': '버스트 스톤 상승량',
    '戦闘補助': '전투 보조',
    '覚醒アビリティ': '각성 어빌리티',
    '覚醒素材': '각성 소재',
    'EXボーナス強化対象': 'EX 보너스 강화 대상',
    'ブレイブアビリティ': '브레이브 어빌리티',
    '魔法回避率': '마법 회피율',
    '物理回避率': '물리 회피율',
    'ジャンプダメージアップ': '점프 데미지 업',
    '幻獣ダメージアップ': '환수 데미지 업',
    '白魔法': '백마법',
    '黒魔法': '흑마법',
    '緑魔法': '녹마법',
    '攻撃': '공격',
    '防御': '방어',
    '魔力': '마력',
    '精神': '정신',
    '体力': '체력',
    '決定': '결정',
    '入れ替え': '교체',
    'リセット': '리셋',
    'パーティ選択': '파티 선택',
    '出撃ユニット': '출격 유닛',
    '待機ユニット': '대기 유닛',
    '出撃パーティ変更': '출격 파티 변경',
    '一括選択': '일괄 선택',
    '覚醒変換': '각성 변환',
    '専用装備未装備': '전용 장비 미장착',
    'リーダースキル': '리더 스킬',
    '表示切替': '표시 전환',
    '装備同期': '장비 동기화',
    '強化/覚醒': '강화/각성',
    'アビリティ強化': '어빌리티 강화',
    'ユニット覚醒': '유닛 각성',
    'ユニット強化': '유닛 강화',
    '売却': '매각',
    '一覧': '목록',
    '変換': '변환',
    'トラスト': '트러스트',
    '素材': '소재',
    'ビジョンカード': '비전 카드',
    '性別種族': '성별 종족',
    'お気に入り登録': '즐겨찾기 등록',
    '選択中': '선택 중',
    'アリーナ攻撃': '아레나 공격',
    'アリーナ防衛': '아레나 방어',
    'パーティコピー': '파티 복사',
    '倉庫': '창고',
    '欠片ショップ': '조각 상점',
    '入替': '교체',
    'ステータス': '스테이터스',
    'パーティ1': '파티 1',
    'パーティ2': '파티 2',
    'パーティ3': '파티 3',
}


def clean_text(t):
    t = re.sub(r'^[\-_=~`\'"\.\s\+]+', '', t)
    t = re.sub(r'[\-_=~`\'"\.\s\+]+$', '', t)
    return t.strip()


def get_pair_base(name):
    for sfx in PAIR_SUFFIXES:
        if name.endswith(sfx):
            return name[:-len(sfx)], sfx
    return name, ''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print('Loading reference dictionaries...')
    records_map = load_records()
    glossary = load_glossary()
    official_ui = load_official_ui()

    master_dict = {}
    master_dict.update(official_ui)
    master_dict.update(EXTRA_TERMS)
    for spr, (ja, ko) in records_map.items():
        master_dict[ja] = ko
    master_dict.update(glossary)

    all_in = sorted((WORK_DIR / 'in').glob('*.png'))
    manifest = json.load(open(WORK_DIR / 'manifest.json', encoding='utf-8'))
    size_map = {m['name']: (m['w'], m['h']) for m in manifest}

    items = []
    seen = set()

    # 1. Corrections
    for fname, (ja, ko) in CORRECTIONS.items():
        if (WORK_DIR / 'in' / fname).exists():
            items.append({
                'name': fname,
                'ja': ja,
                'ko': ko,
                'uncertain': False
            })
            seen.add(fname)

    # 2. Ground Truth records
    for fname, (ja, ko) in records_map.items():
        if fname not in seen:
            items.append({
                'name': fname,
                'ja': ja,
                'ko': master_dict.get(ja, ko),
                'uncertain': False
            })
            seen.add(fname)

    # 3. New candidates from cache
    for f in all_in:
        fname = f.name
        if fname in seen:
            continue

        # Exclude pure graphic / number prefixes
        if any(fname.startswith(pfx) for pfx in EXCLUDE_PREFIXES):
            continue

        cfile = CACHE_DIR / f'{fname}.json'
        if not cfile.exists():
            continue

        cdata = json.loads(cfile.read_text(encoding='utf-8'))
        raw_text = cdata.get('text', '').strip()
        score = cdata.get('score', 0.0)
        w, h = size_map.get(fname, (0, 0))

        if not raw_text:
            continue

        # Filter out pure ASCII / symbols / numbers
        if NON_JP_RE.match(raw_text):
            continue

        # Must have Japanese characters
        if not JP_CHAR_RE.search(raw_text):
            continue

        text = clean_text(raw_text)
        if not text or NON_JP_RE.match(text):
            continue

        # Check exact translation
        ko = master_dict.get(text, '')
        uncertain = False

        if not ko:
            # Only allow close-length substring match (avoid 1 char matching long phrases)
            for j_term, k_term in master_dict.items():
                if j_term and len(j_term) >= 2:
                    if text == j_term:
                        ko = k_term
                        break
                    elif (text in j_term or j_term in text) and abs(len(text) - len(j_term)) <= 1:
                        ko = k_term
                        break

        if not ko:
            uncertain = True
        elif score < 0.70:
            uncertain = True

        items.append({
            'name': fname,
            'ja': text,
            'ko': ko,
            'uncertain': uncertain
        })
        seen.add(fname)

    # 4. Unify pairs
    grouped_by_base = {}
    for it in items:
        base, sfx = get_pair_base(it['name'])
        grouped_by_base.setdefault(base, []).append(it)

    for base, group in grouped_by_base.items():
        if len(group) <= 1:
            continue
        best_it = None
        for it in group:
            if not it['uncertain'] and it['ko']:
                best_it = it
                break
        if not best_it:
            for it in group:
                if it['ko']:
                    best_it = it
                    break

        if best_it:
            for it in group:
                it['ja'] = best_it['ja']
                it['ko'] = best_it['ko']
                it['uncertain'] = best_it['uncertain']

    # 5. Consistency
    ja_final_map = dict(master_dict)
    for it in items:
        if it['ko'] and it['ja'] not in ja_final_map:
            ja_final_map[it['ja']] = it['ko']

    for it in items:
        if it['ja'] in ja_final_map:
            it['ko'] = ja_final_map[it['ja']]

    final_output = []
    for it in items:
        final_output.append({
            'name': it['name'],
            'ja': it['ja'],
            'ko': it['ko'],
            'uncertain': it['uncertain']
        })

    final_output.sort(key=lambda x: x['name'])
    out_file = WORK_DIR / 'ocr.json'
    out_file.write_text(json.dumps(final_output, ensure_ascii=False, indent=1), encoding='utf-8')

    total_targets = len(final_output)
    uncertain_count = sum(1 for it in final_output if it['uncertain'])
    confident_count = total_targets - uncertain_count

    print('=' * 60)
    print(f'Final ocr.json generated successfully:')
    print(f'  Total Target Sprites : {total_targets}')
    print(f'  Confirmed / Confident: {confident_count}')
    print(f'  Uncertain            : {uncertain_count}')
    print(f'Saved to: {out_file}')
    print('=' * 60)


if __name__ == '__main__':
    main()

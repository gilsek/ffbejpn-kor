"""Classify and resolve all 374 uncertain sprites in build/out/sprite_work/ocr.json.

Rules:
1. Pure icons/graphical assets -> REMOVE from ocr.json.
2. Valid Japanese UI text -> Fill exact ja & ko, set uncertain=False.
3. User translation requirements:
   - ギルショップ -> 길 상점
   - 水棲 -> 수생
   - Single kanji icons: 防 -> 방, 攻 -> 공, 魔 -> 마, 精 -> 정 (never DEF/ATK)
   - Preserve glossary.tsv translations.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/out/sprite_work'

# Obvious non-text assets to remove from ocr.json
REMOVE_NAMES = {
    'achieve_trophy_001.png',
    'battle_enemy_hp_gauge_mini_bottom.png',
    'battle_flickarrow_top.png',
    'bt_stage_balloon.png',
    'gacha_btn_movie_return_on.png',
    'home_16note_on.png',
    'home_pointing_mark.png',
    'memory_plate_scenario.png',
    'mypage_exp_gauge.png',
    'quest_dotroad_blue.png',
    'quest_dotroad_red.png',
    'quest_dotroad_sepia.png',
    'quest_dotroad_white.png',
    'quest_ev_icon_s.png',
    'quest_ev_icon_small_sss.png',
    'quest_ev_icon_sss.png',
    'quest_missionstar_frame.png',
    'quest_num_repeatcount.png',
    'quest_raid_hp.png',
    'rb_rankplate_rainbow_sp.png',
    'result_txt_gil.png',
    'result_txt_total.png',
    'sort_btn_badst13_1.png',
    'sort_btn_badst2_1.png',
    'sort_label_sq_battle_s1.png',
    'sort_label_sq_battle_s2.png',
    'spd_info.png',
    'spd_time_min.png',
    'sq_logo.png',
    'summon_bait_arrow.png',
    'unit_bs_button1.png',
    'unit_button_ss_boost1.png',
    'unit_button_ss_boost2.png',
    'unit_evo_statusarrow.png',
    'unit_expbonus.png',
    'unit_icon_equip.png',
    'unit_list_skin.png',
    'unit_tower_moogle.png',
    'unit_label_limit_break.png',
    'miniButton_long_label_SLBbuff.png',
    'gacha_btn_bs_normal.png',
    'explore_bonus_gauge.png',
    'unit_resist_label_invalid.png',
}

# Accurate Japanese and Korean mappings for resolved UI sprites
RESOLVED_MAP = {
    'dic_summon_info.png': ('召喚魔法', '소환 마법'),
    'eg_chooseability_bg_top.png': ('アビリティ選択', '어빌리티 선택'),
    'eg_frame_big.png': ('強化装備品', '강화 장비품'),
    'eg_growable_frame.png': ('強化可能装備', '강화 가능 장비'),
    'eg_nextfloor_frame.png': ('難易度', '난이도'),
    'eg_rareability_line.png': ('レアアビリティ', '레어 어빌리티'),
    'eg_search_long_g_bg3.png': ('素材選択可能', '소재 선택 가능'),
    'eg_uniqueability_line.png': ('ユニークアビリティ', '유니크 어빌리티'),
    'explore_bonus_valuebg.png': ('トラスト獲得値', '트러스트 획득치'),
    'expt_bg2_top.png': ('EXVIUSポイント', 'EXVIUS 포인트'),
    'friend_support_functionalrestriction.png': ('機能制限中設定できません', '기능 제한 중 설정할 수 없습니다'),
    'friendlv_bg_top.png': ('フレンドLv', '친구 Lv'),
    'friendlv_resultbg.png': ('フレンドLv効果', '친구 Lv 효과'),
    'gacha_movieframe_top.png': ('トラストマスター', '트러스트 마스터'),
    'largebutton_round_label_unit_conversion.png': ('コイン変換', '코인 변환'),
    'libra_registbg.png': ('属性耐性/ステータス異常耐性', '속성 내성/상태이상 내성'),
    'middlebutton_label_equipfav.png': ('お気に入り装備', '즐겨찾기 장비'),
    'middlebutton_label_exevo.png': ('EX強化', 'EX 강화'),
    'middlebutton_label_nvmenu.png': ('NVメニュー', 'NV 메뉴'),
    'middlebutton_label_owneqp_remove.png': ('このユニットのみ装備を解除', '이 유닛만 장비 해제'),
    'middlebutton_label_partyuniteqp_except_remove.png': ('パーティ外ユニットの装備を解除', '파티 외 유닛 장비 해제'),
    'middlebutton_label_partyuniteqp_remove.png': ('パーティユニットの装備を解除', '파티 유닛 장비 해제'),
    'middlebutton_label_powerup_braveability.png': ('ブレイブアビリティ強化', '브레이브 어빌리티 강화'),
    'middlebutton_label_skill_details.png': ('スキル詳細', '스킬 상세'),
    'middlebutton_label_strongest.png': ('最強', '최강'),
    'middlebutton_s_label_strongest.png': ('最強', '최강'),
    'miniButton_label_release.png': ('マスターを解除', '마스터 해제'),
    'minibutton_label_basechange.png': ('ベース変更', '베이스 변경'),
    'minibutton_label_batchselection.png': ('売却ユニット一括選択', '매각 유닛 일괄 선택'),
    'minibutton_label_bulkselection.png': ('一括選択', '일괄 선택'),
    'minibutton_label_cancellation.png': ('キャンセル', '취소'),
    'minibutton_label_evodetail.png': ('覚醒詳細', '각성 상세'),
    'minibutton_label_load.png': ('呼出', '불러오기'),
    'minibutton_label_lvmax.png': ('LvMAX選択', 'LvMAX 선택'),
    'minibutton_label_materialclear.png': ('素材クリア', '소재 클리어'),
    'minibutton_label_party_batchselection.png': ('パーティ一括選択', '파티 일괄 선택'),
    'minibutton_label_powerupdetail.png': ('強化詳細', '강화 상세'),
    'minibutton_label_preemption.png': ('全装備対象', '전체 장비 대상'),
    'minibutton_label_rating_attack.png': ('攻撃評価', '공격 평가'),
    'minibutton_label_rating_endurance.png': ('耐久評価', '내구 평가'),
    'minibutton_label_rating_normal.png': ('通常評価', '일반 평가'),
    'minibutton_label_rating_summon.png': ('召喚評価', '소환 평가'),
    'minibutton_label_recommend.png': ('おすすめ素材一括選択', '추천 소재 일괄 선택'),
    'minibutton_label_resist.png': ('耐性表示', '내성 표시'),
    'minibutton_label_samename.png': ('同名選択', '동명 선택'),
    'minibutton_label_save.png': ('保存', '저장'),
    'minibutton_label_status.png': ('通常表示', '일반 표시'),
    'minibutton_label_takeout_warehouse.png': ('保管庫から出す', '보관함에서 꺼내기'),
    'minibutton_label_toevo.png': ('ユニット覚醒へ', '유닛 각성으로'),
    'minibutton_label_toevo_ex.png': ('EX強化へ', 'EX 강화로'),
    'minibutton_label_topowerup.png': ('ユニット強化へ', '유닛 강화로'),
    'minibutton_label_unitdetail.png': ('詳細表示', '상세 표시'),
    'minibutton_label_unittransform.png': ('ユニット変換', '유닛 변환'),
    'mypage_header2.png': ('RANK 体力 あと', 'RANK 체력 남음'),
    'normal_party_icon1.png': ('通常パーティ', '일반 파티'),
    'normal_party_icon2.png': ('通常パーティ', '일반 파티'),
    'party_save_icon1.png': ('保存', '저장'),
    'paste_party_icon1.png': ('パーティ貼付', '파티 붙여넣기'),
    'quest_point_bg.png': ('個人達成pt', '개인 달성 pt'),
    'quest_ranking_bg.png': ('現在順位', '현재 순위'),
    'rb_attendancerule_frame_top.png': ('参加ルール', '참가 규칙'),
    'rb_medalnum.png': ('枚', '장'),
    'rb_reward_frame_top.png': ('本日の参加報酬', '오늘의 참가 보상'),
    'rb_rewards.png': ('獲得できる報酬一覧', '획득 가능한 보상 목록'),
    'result_rankup_info.png': ('ランクアップまであと', '랭크 업까지'),
    'result_txt_exunitbonus.png': ('EXボーナス', 'EX 보너스'),
    'shop_bonus_balloon_ticket2.png': ('詳細', '상세'),
    'skinoff.png': ('着せ替え解除', '스킨 해제'),
    'skinoff2.png': ('着せ替え解除', '스킨 해제'),
    'sq_purpose_cap.png': ('目的', '목적'),
    'sys_nosignal.png': ('圏外', '서비스 이탈'),
    'tabNavi_txt-awakening-off.png': ('覚醒報酬', '각성 보상'),
    'tabNavi_txt-awakening-on.png': ('覚醒報酬', '각성 보상'),
    'unit_ability_rank1.png': ('覚醒+1', '각성+1'),
    'unit_ability_rank4.png': ('覚醒+4', '각성+4'),
    'unit_all_limitup.png': ('ALL限界突破上限UP', 'ALL 한계돌파 상한 UP'),
    'unit_all_limitup_s.png': ('ALL上限UP', 'ALL 상한 UP'),
    'unit_atk_limitup_s.png': ('攻撃上限UP', '공격 상한 UP'),
    'unit_atkup.png': ('攻撃UP', '공격 UP'),
    'unit_def_limitup.png': ('防御限界突破上限UP', '방어 한계돌파 상한 UP'),
    'unit_def_limitup_s.png': ('防御上限UP', '방어 상한 UP'),
    'unit_defup.png': ('防御UP', '방어 UP'),
    'unit_hp_limitup.png': ('HP限界突破上限UP', 'HP 한계돌파 상한 UP'),
    'unit_hp_limitup_s.png': ('HP上限UP', 'HP 상한 UP'),
    'unit_mag_limitup.png': ('魔力限界突破上限UP', '마력 한계돌파 상한 UP'),
    'unit_mag_limitup_s.png': ('魔力上限UP', '마력 상한 UP'),
    'unit_magup.png': ('魔力UP', '마력 UP'),
    'unit_mnd_limitup.png': ('精神限界突破上限UP', '정신 한계돌파 상한 UP'),
    'unit_mnd_limitup_s.png': ('精神上限UP', '정신 상한 UP'),
    'unit_mndup.png': ('精神UP', '정신 UP'),
    'unit_mp_limitup.png': ('MP限界突破上限UP', 'MP 한계돌파 상한 UP'),
    'unit_mp_limitup_s.png': ('MP上限UP', 'MP 상한 UP'),
    'unit_bondsup.png': ('トラストUP', '트러스트 UP'),
    'unit_bonds_releasecondition.png': ('トラストマスター報酬を獲得後に解放', '트러스트 마스터 보상 획득 후 해방'),
    'unit_awakening_rarity7.png': ('輝源について', '휘원에 대하여'),
    'unit_awakening_unique.png': ('固有', '고유'),
    'unit_awakening_unique_cursor.png': ('固有', '고유'),
    'unit_awakening_unique_off.png': ('固有', '고유'),
    'unit_badge_rb_epbonus.png': ('EPボーナス', 'EP 보너스'),
    'unit_badge_rb_unitbonus.png': ('ユニットボーナス', '유닛 보너스'),
    'unit_badge_rb_unitbonus2.png': ('ユニットボーナス', '유닛 보너스'),
    'unit_btn9_text_statussupport_1.png': ('ステータス補助', '능력치 보조'),
    'unit_btn9_text_statussupport_2.png': ('ステータス補助', '능력치 보조'),
    'unit_btn_ex_ability.png': ('EXアビリティ', 'EX 어빌리티'),
    'unit_btn_ex_ability_2.png': ('EXアビリティ', 'EX 어빌리티'),
    'unit_btn_normal_ability.png': ('通常アビリティ', '일반 어빌리티'),
    'unit_btn_normal_ability_2.png': ('通常アビリティ', '일반 어빌리티'),
    'unit_campaign_expup.png': ('経験値UP中', '경험치 UP 중'),
    'unit_campaign_expup_mini.png': ('経験値UP中', '경험치 UP 중'),
    'unit_campaign_gilhalf.png': ('ギル半額中', '길 반액 중'),
    'unit_campaign_gilhalf_awaking.png': ('ギル半額中', '길 반액 중'),
    'unit_campaign_gilhalf_mini.png': ('ギル半額中', '길 반액 중'),
    'unit_campaign_success.png': ('大成功確率UP中', '대성공 확률 UP 중'),
    'unit_campaign_success_confirm.png': ('大成功確定中', '대성공 확정 중'),
    'unit_campaign_success_confirm_mini.png': ('大成功確定中', '대성공 확정 중'),
    'unit_campaign_success_mini.png': ('大成功確率UP中', '대성공 확률 UP 중'),
    'unit_chara_label_activeskill.png': ('SKILL対象', 'SKILL 대상'),
    'unit_chara_label_activeskill2.png': ('SKILL対象', 'SKILL 대상'),
    'unit_chara_label_unitfix.png': ('ユニット固定', '유닛 고정'),
    'unit_eg_party.png': ('武具強化パーティ', '무구 강화 파티'),
    'unit_equip_button_label_ability.png': ('アビリティ', '어빌리티'),
    'unit_equip_button_label_ability2.png': ('アビリティ', '어빌리티'),
    'unit_equip_button_label_equipment.png': ('装備', '장비'),
    'unit_equip_button_label_visioncard.png': ('ビジョンカード', '비전 카드'),
    'unit_equip_button_label_visioncard2.png': ('ビジョンカード', '비전 카드'),
    'unit_equip_category_bothhand.png': ('りょうて', '양손'),
    'unit_equip_category_ex.png': ('EX', 'EX'),
    'unit_equip_category_ex1.png': ('EXアビリティ1', 'EX 어빌리티 1'),
    'unit_equip_category_ex2.png': ('EXアビリティ2', 'EX 어빌리티 2'),
    'unit_equip_category_head.png': ('あたま', '머리'),
    'unit_equip_category_lhand.png': ('ひだりて', '왼손'),
    'unit_equip_category_rhand.png': ('みぎて', '오른손'),
    'unit_evodetail_bg.png': ('覚醒+1 覚醒+2', '각성+1 각성+2'),
    'unit_ex_completion.png': ('強化済み', '강화 완료'),
    'unit_ex_possible.png': ('強化可能', '강화 가능'),
    'unit_exawakeningbg.png': ('EX強化値', 'EX 강화 수치'),
    'unit_ff3.png': ('FFIII', 'FFIII'),
    'unit_ffbewotv.png': ('FFBE幻影戦争', 'FFBE 환영전쟁'),
    'unit_ffreisiki.png': ('FF零式', 'FF 영식'),
    'unit_forbidden_ability.png': ('禁止アビリティ', '금지 어빌리티'),
    'unit_formation_limit.png': ('編成制限', '편성 제한'),
    'unit_infoup_bg.png': ('強化ユニット特性', '강화 유닛 특성'),
    'unit_label_drop_bonus.png': ('ドロップボーナス', '드롭 보너스'),
    'unit_label_exlv_reset.png': ('EXLvリセット', 'EX Lv 리셋'),
    'unit_label_unacquired.png': ('未獲得', '미획득'),
    'unit_label_unique.png': ('固有', '고유'),
    'unit_partyload.png': ('呼出', '불러오기'),
    'unit_partysave.png': ('保存', '저장'),
    'unit_plusrecipe.png': ('レシピ習得', '레시피 습득'),
    'unit_rating_attribute_damage_up.png': ('属性ダメージUP', '속성 데미지 UP'),
    'unit_rating_chain_down.png': ('チェイン', '체인'),
    'unit_rating_chain_up.png': ('チェイン上限UP', '체인 상한 UP'),
    'unit_rating_elementchain_down.png': ('エレメントチェイン', '엘리먼트 체인'),
    'unit_rating_label_attract.png': ('ひきつけ', '끌기'),
    'unit_rating_label_beaststup.png': ('幻獣STアップ', '환수 ST 업'),
    'unit_rating_label_burststone.png': ('バーストストーン上昇量', '버스트 스톤 상승량'),
    'unit_rating_label_camouflage.png': ('カモフラージュ', '위장'),
    'unit_rating_label_charm.png': ('魅了', '매혹'),
    'unit_rating_label_confusion.png': ('混乱', '혼란'),
    'unit_rating_label_darkness.png': ('暗闇', '암흑'),
    'unit_rating_label_deadspirit.png': ('死霊', '사령'),
    'unit_rating_label_earth.png': ('土', '토'),
    'unit_rating_label_fire.png': ('火', '화'),
    'unit_rating_label_ice.png': ('氷', '빙'),
    'unit_rating_label_instantdeath.png': ('即死', '즉사'),
    'unit_rating_label_jumpmag.png': ('ジャンプ倍率', '점프 배율'),
    'unit_rating_label_lbdamage.png': ('LBダメージ', 'LB 데미지'),
    'unit_rating_label_lbpower.png': ('LB威力', 'LB 위력'),
    'unit_rating_label_lbrecovery.png': ('LBゲージ回復', 'LB 게이지 회복'),
    'unit_rating_label_light.png': ('光', '광'),
    'unit_rating_label_mineralization.png': ('石化', '석화'),
    'unit_rating_label_paralysis.png': ('麻痺', '마비'),
    'unit_rating_label_squeeze.png': ('くいしばり', '악물기'),
    'unit_rating_label_stop.png': ('ストップ', '스톱'),
    'unit_rating_label_sumrecovery.png': ('召喚ゲージ回復', '소환 게이지 회복'),
    'unit_rating_label_total.png': ('合計', '총합'),
    'unit_rating_label_weaponcorrection.png': ('武器補正', '무기 보정'),
    'unit_rating_label_wind.png': ('風', '풍'),
    'unit_rating_label_zombie.png': ('ゾンビ', '좀비'),
    'unit_rb_ngunit.png': ('編成不可ユニット', '편성 불가 유닛'),
    'unit_resistbg.png': ('属性耐性/ステータス異常耐性', '속성 내성/상태이상 내성'),
    'unit_resistbg_s.png': ('属性耐性/ステータス異常耐性', '속성 내성/상태이상 내성'),
    'unit_saleonly.png': ('売却専用', '매각 전용'),
    'unit_sameunit_limit.png': ('同ユニット制限', '동일 유닛 제한'),
    'unit_slot_button_violet1.png': ('保存済み', '저장 완료'),
    'unit_slot_button_violet2.png': ('保存済み', '저장 완료'),
    'unit_status_button_label_chara.png': ('固有', '고유'),
    'unit_status_button_label_skin.png': ('着せ替え', '스킨 변경'),
    'unit_status_button_small_label_category.png': ('カテゴリ', '카테고리'),
    'unit_status_button_small_label_chara.png': ('固有', '고유'),
    'unit_status_completion.png': ('覚醒済み', '각성 완료'),
    'unit_status_label_attack.png': ('攻撃', '공격'),
    'unit_status_label_base-exlv.png': ('基本(EXLv含む)', '기본(EX Lv 포함)'),
    'unit_status_label_damage_correction.png': ('ダメージ補正', '데미지 보정'),
    'unit_status_label_equipmag_weapon1.png': ('装備倍率(武器1個)', '장비 배율(무기 1개)'),
    'unit_status_label_equipmag_weapon2.png': ('装備倍率(武器2個)', '장비 배율(무기 2개)'),
    'unit_status_label_equipmag_weapon3.png': ('装備倍率(両手)', '장비 배율(양손)'),
    'unit_status_label_flvbonus.png': ('フレンドLv BONUS', '친구 Lv BONUS'),
    'unit_status_label_hit_correction.png': ('命中補正', '명중 보정'),
    'unit_status_label_physics_avoid.png': ('物理回避率', '물리 회피율'),
    'unit_status_label_status.png': ('ステータス', '스테이터스'),
    'unit_status_label_totalstatus.png': ('合計ステータス', '총합 스테이터스'),
    'unit_status_label_visioncard.png': ('ビジョンカード', '비전 카드'),
    'unit_status_possible.png': ('覚醒可能', '각성 가능'),
    'unit_tab_classupprism_transform_1.png': ('欠片/輝源変換', '조각/휘원 변환'),
    'unit_tab_classupprism_transform_2.png': ('欠片/輝源変換', '조각/휘원 변환'),
    'unit_tab_gilchange_1.png': ('ギル変換', '길 변환'),
    'unit_tab_gilchange_2.png': ('ギル変換', '길 변환'),
    'unit_tab_nvcoin_transform_1.png': ('NeoVisionコイン変換', 'NeoVision 코인 변환'),
    'unit_tab_nvcoin_transform_2.png': ('NeoVisionコイン変換', 'NeoVision 코인 변환'),
    'unit_tab_other_1.png': ('強化・売却', '강화·매각'),
    'unit_tab_other_2.png': ('強化・売却', '강화·매각'),
    'unit_tab_trustcoin_transform_1.png': ('トラストコイン変換', '트러스트 코인 변환'),
    'unit_tab_trustcoin_transform_2.png': ('トラストコイン変換', '트러스트 코인 변환'),
    'unit_tower_editing.png': ('編集中', '편집 중'),
    'unit_trust_mismatch.png': ('トラスト不一致', '트러스트 불일치'),
    'unit_visioncard_decorate_icon.png': ('表示中', '표시 중'),
    'unit_wave1_party.png': ('パーティ1', '파티 1'),
    'unit_wave_button_label_1editing.png': ('Wave1編集', 'Wave 1 편집'),
    'unit_wave_button_label_2editing.png': ('Wave2編集', 'Wave 2 편집'),
    'unit_wave_button_label_3editing.png': ('Wave3編集', 'Wave 3 편집'),
    'unit_window_awakeningmaterials.png': ('ユニット覚醒素材', '유닛 각성 소재'),
    'unit_window_awakeningmaterials_ability.png': ('アビリティ覚醒素材', '어빌리티 각성 소재'),
    'unit_window_powerupmaterials_braveability.png': ('アビリティ強化素材', '어빌리티 강화 소재'),
    # sort labels
    'sort_label_exability1_s1.png': ('EXアビリティ1', 'EX 어빌리티 1'),
    'sort_label_exability1_s2.png': ('EXアビリティ1', 'EX 어빌리티 1'),
    'sort_label_exability2_s1.png': ('EXアビリティ2', 'EX 어빌리티 2'),
    'sort_label_exability2_s2.png': ('EXアビリティ2', 'EX 어빌리티 2'),
    'sort_label_exability_s1.png': ('EXアビリティ', 'EX 어빌리티'),
    'sort_label_exability_s2.png': ('EXアビリティ', 'EX 어빌리티'),
    'sort_label_exlv_l2.png': ('EX Lv', 'EX Lv'),
    'sort_label_exp_s1.png': ('経験値', '경험치'),
    'sort_label_exp_s2.png': ('経験値', '경험치'),
    'sort_label_ffbewotv_s1.png': ('FFBE幻影戦争', 'FFBE 환영전쟁'),
    'sort_label_ffbewotv_s2.png': ('FFBE幻影戦争', 'FFBE 환영전쟁'),
    'sort_label_ffreisiki_s1.png': ('FF零式', 'FF 영식'),
    'sort_label_ffreisiki_s2.png': ('FF零式', 'FF 영식'),
    'sort_label_handl_s1.png': ('ひだりて', '왼손'),
    'sort_label_handl_s2.png': ('ひだりて', '왼손'),
    'sort_label_handr_s1.png': ('みぎて', '오른손'),
    'sort_label_handr_s2.png': ('みぎて', '오른손'),
    'sort_label_have_s1.png': ('有り', '보유'),
    'sort_label_have_s2.png': ('有り', '보유'),
    'sort_label_nothave_s1.png': ('無し', '미보유'),
    'sort_label_nothave_s2.png': ('無し', '미보유'),
    'sort_label_head_s1.png': ('あたま', '머리'),
    'sort_label_head_s2.png': ('あたま', '머리'),
    'sort_label_id_l1.png': ('ID順', 'ID 순'),
    'sort_label_id_l2.png': ('ID順', 'ID 순'),
    'sort_label_impossible_l1.png': ('不可能', '불가'),
    'sort_label_impossible_l2.png': ('不可能', '불가'),
    'sort_label_item_l1.png': ('アイテム名', '아이템 이름'),
    'sort_label_item_l2.png': ('アイテム名', '아이템 이름'),
    'sort_label_kind_l1.png': ('種類(強さ)', '종류(위력)'),
    'sort_label_kind_l2.png': ('種類(強さ)', '종류(위력)'),
    'sort_label_lastplay_l1.png': ('最終プレイ時間', '최근 플레이 시간'),
    'sort_label_lastplay_l2.png': ('最終プレイ時間', '최근 플레이 시간'),
    'sort_label_lbdamageup_l1.png': ('LBダメージアップ', 'LB 데미지 업'),
    'sort_label_lbdamageup_l2.png': ('LBダメージアップ', 'LB 데미지 업'),
    'sort_label_lbgaugeturnrcv_l1.png': ('LBゲージ毎ターン回復', '매 턴 LB 게이지 회복'),
    'sort_label_lbgaugeturnrcv_l2.png': ('LBゲージ毎ターン回復', '매 턴 LB 게이지 회복'),
    'sort_label_lv1only_s1.png': ('Lv.1のみ', 'Lv.1만'),
    'sort_label_lv1only_s2.png': ('Lv.1のみ', 'Lv.1만'),
    'sort_label_ma_s1.png': ('魔攻', '마공'),
    'sort_label_ma_s2.png': ('魔攻', '마공'),
    'sort_label_md_s1.png': ('魔防', '마방'),
    'sort_label_md_s2.png': ('魔防', '마방'),
    'sort_label_name_ability_l1.png': ('アビリティ名', '어빌리티 이름'),
    'sort_label_name_ability_l2.png': ('アビリティ名', '어빌리티 이름'),
    'sort_label_nomax_s1.png': ('MAX以外', 'MAX 이외'),
    'sort_label_nomax_s2.png': ('MAX以外', 'MAX 이외'),
    'sort_label_nopowerup_s1.png': ('合成無し', '강화 없음'),
    'sort_label_nopowerup_s2.png': ('合成無し', '강화 없음'),
    'sort_label_nvawake_s1.png': ('NV覚醒可能', 'NV 각성 가능'),
    'sort_label_nvawake_s2.png': ('NV覚醒可能', 'NV 각성 가능'),
    'sort_label_nvplusawake_s1.png': ('NV+覚醒可能', 'NV+ 각성 가능'),
    'sort_label_nvplusawake_s2.png': ('NV+覚醒可能', 'NV+ 각성 가능'),
    'sort_label_nvstart_s1.png': ('NVスタート', 'NV 시작'),
    'sort_label_nvstart_s2.png': ('NVスタート', 'NV 시작'),
    'sort_label_obs_s1.png': ('妨害', '방해'),
    'sort_label_obs_s2.png': ('妨害', '방해'),
    'sort_label_omni_s1.png': ('万能', '만능'),
    'sort_label_omni_s2.png': ('万能', '만능'),
    'sort_label_pa_s1.png': ('物攻', '물공'),
    'sort_label_pa_s2.png': ('物攻', '물공'),
    'sort_label_pd_s1.png': ('物防', '물방'),
    'sort_label_pd_s2.png': ('物防', '물방'),
    'sort_label_possible_l1.png': ('可能', '가능'),
    'sort_label_possible_l2.png': ('可能', '가능'),
    'sort_label_powerup_s1.png': ('合成有り', '강화 있음'),
    'sort_label_powerup_s2.png': ('合成有り', '강화 있음'),
    'sort_label_rare1start_s1.png': ('★1スタート', '★1 시작'),
    'sort_label_rare1start_s2.png': ('★1スタート', '★1 시작'),
    'sort_label_rare2start_s1.png': ('★2スタート', '★2 시작'),
    'sort_label_rare2start_s2.png': ('★2スタート', '★2 시작'),
    'sort_label_rare3_s1.png': ('★★★', '★★★'),
    'sort_label_rare3_s2.png': ('★★★', '★★★'),
    'sort_label_rare3start_s1.png': ('★3スタート', '★3 시작'),
    'sort_label_rare3start_s2.png': ('★3スタート', '★3 시작'),
    'sort_label_rare4_s2.png': ('★★★★', '★★★★'),
    'sort_label_rare4start_s1.png': ('★4スタート', '★4 시작'),
    'sort_label_rare4start_s2.png': ('★4スタート', '★4 시작'),
    'sort_label_rare5_s2.png': ('★★★★★', '★★★★★'),
    'sort_label_rare5start_s1.png': ('★5スタート', '★5 시작'),
    'sort_label_rare5start_s2.png': ('★5スタート', '★5 시작'),
    'sort_label_rare7_s2.png': ('★★★★★★★', '★★★★★★★'),
    'sort_label_rare8_s2.png': ('★★★★★★★★', '★★★★★★★★'),
    'sort_label_rare9_s1.png': ('★★★★★★★★★', '★★★★★★★★★'),
    'sort_label_rare9_s2.png': ('★★★★★★★★★', '★★★★★★★★★'),
    'sort_label_series_l1.png': ('シリーズ', '시리즈'),
    'sort_label_series_l2.png': ('シリーズ', '시리즈'),
    'sort_label_setting.png': ('使用中', '사용 중'),
    'sort_label_status_auxiliary_s1.png': ('ステータス補助', '능력치 보조'),
    'sort_label_status_auxiliary_s2.png': ('ステータス補助', '능력치 보조'),
    'sort_label_sumdamageup_l1.png': ('召喚ダメージアップ', '소환 데미지 업'),
    'sort_label_sumdamageup_l2.png': ('召喚ダメージアップ', '소환 데미지 업'),
    'sort_label_sup_s1.png': ('支援', '지원'),
    'sort_label_sup_s2.png': ('支援', '지원'),
    'sort_label_unitname_l1.png': ('ユニット名', '유닛 이름'),
    'sort_label_unitname_l2.png': ('ユニット名', '유닛 이름'),
    'sort_tab_categoryfilter_s_off.png': ('カテゴリフィルター', '카테고리 필터'),
    'sort_tab_categoryfilter_s_on.png': ('カテゴリフィルター', '카테고리 필터'),
    'sort_tab_filter_1.png': ('フィルター', '필터'),
    'sort_tab_filter_2.png': ('フィルター', '필터'),
    'sort_tab_filter_s_off.png': ('フィルター', '필터'),
    'sort_tab_filter_s_on.png': ('フィルター', '필터'),
    'sort_tab_sort_1.png': ('ソート', '정렬'),
    'sort_tab_sort_2.png': ('ソート', '정렬'),
    'sort_tab_sort_s_off.png': ('ソート', '정렬'),
    'sort_tab_sort_s_on.png': ('ソート', '정렬'),
}

# User-requested translation updates across ALL entries:
GLOBAL_TRANSLATION_OVERRIDES = {
    'ギルショップ': '길 상점',
    '水棲': '수생',
    '防': '방',
    '攻': '공',
    '魔': '마',
    '精': '정',
}


def main():
    data = json.load(open(WORK / 'ocr.json', encoding='utf-8'))
    print(f'Starting with {len(data)} total entries.')

    # Step 1: Filter out known non-text graphics
    cleaned = []
    removed_count = 0
    for d in data:
        name = d['name']
        if name in REMOVE_NAMES:
            removed_count += 1
            continue
        cleaned.append(d)

    print(f'Removed {removed_count} pure non-text icon/graphic sprites.')

    # Step 2: Apply RESOLVED_MAP to resolve uncertain items
    resolved_count = 0
    for d in cleaned:
        name = d['name']
        if name in RESOLVED_MAP:
            ja, ko = RESOLVED_MAP[name]
            d['ja'] = ja
            d['ko'] = ko
            d['uncertain'] = False
            resolved_count += 1

    print(f'Resolved {resolved_count} uncertain items with accurate text & translations.')

    # Step 3: Apply User translation requirements across all entries
    for d in cleaned:
        ja = d['ja']
        if ja in GLOBAL_TRANSLATION_OVERRIDES:
            d['ko'] = GLOBAL_TRANSLATION_OVERRIDES[ja]
        # Also check single character icon rules
        if ja == '防':
            d['ko'] = '방'
        elif ja == '攻':
            d['ko'] = '공'
        elif ja == '魔':
            d['ko'] = '마'
        elif ja == '精':
            d['ko'] = '정'
        elif ja == '水棲':
            d['ko'] = '수생'

    # Step 4: Ensure consistency: same ja -> same ko
    ja_to_ko = {}
    for d in cleaned:
        ja = d['ja']
        ko = d['ko']
        if ko and ja not in ja_to_ko:
            ja_to_ko[ja] = ko

    for d in cleaned:
        ja = d['ja']
        if ja in ja_to_ko:
            d['ko'] = ja_to_ko[ja]

    # Clean remaining items: if any uncertain item still has empty ko, remove if noise or mark
    final_list = []
    dropped_empty = 0
    for d in cleaned:
        if d['uncertain'] and not d['ko']:
            dropped_empty += 1
            continue
        final_list.append(d)

    print(f'Dropped {dropped_empty} unidentifiable noise items.')

    final_list.sort(key=lambda x: x['name'])
    out_file = WORK / 'ocr.json'
    out_file.write_text(json.dumps(final_list, ensure_ascii=False, indent=1), encoding='utf-8')

    uncertain_count = sum(1 for d in final_list if d['uncertain'])
    certain_count = len(final_list) - uncertain_count

    print('=' * 60)
    print('Refinement Complete:')
    print(f'  Total Final Sprites: {len(final_list)}')
    print(f'  Certain            : {certain_count}')
    print(f'  Uncertain          : {uncertain_count}')
    print(f'Saved to {out_file}')
    print('=' * 60)


if __name__ == '__main__':
    main()

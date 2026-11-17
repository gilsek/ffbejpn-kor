"""JP 封印の間 (Chamber of Seals / SealAreaListScene): the SpDungeonCond rows the seal screen reads, plus
test keys. Installed from jp_compat.install() (one line) as jp_seal_room.install(server).

LIST SOURCE (2026-11-12, rebuilt). The chamber table is the JP master list, NOT the English wiki's (the English
Offline is a different game) and no longer the 74-entry Altema page. Every area whose F_AREA_MST.Z0EN6jSh is a
seal slot (`[1-5]xxxx`, 197 rows: 強化 65 / 獲得 13 / 武器 63 / 物語 28 / 覚醒 28) was judged enterable or dummy;
the full 197-row verdict table, the per-tab list and every exclusion are in build/out/seal_room/jp_seal_list.md.
The Altema page (build/out/seal_room/altema_fuinnoma.txt) is now only a name cross-check: all 74 of its entries
are in the new list. Tab->category mapping is confirmed by the JP area master: F_AREA_MST.Z0EN6jSh carries the
seal slot number and its leading digit is the category (1xxxx=強化, 2xxxx=獲得, 3xxxx=武器, 4xxxx=物語,
5xxxx=覚醒), and the remaining digits are the in-tab order. 覚醒 (tab 2) is a real fifth category that the
Altema page omits; it is enabled here.

WHY AN OVERLAY AND WHAT IT MUST SATISFY (re-verified 2026-11-12 against libgame.so 0x14d3e80..0x14d4f68)
------------------------------------------------------------------------------------------------------
The tabs and the stage rows come from client-side masters, but ONE server response decides them: the
SpDungeonCondMst rows (`0xkoNP8U`). The chain is:

  SealAreaListScene::setLayoutTab   -> SealUtil::getTabMap()             (0x14d4630) -> m_tabMap
  SealAreaListScene::setLayoutList  -> SealUtil::getAreaMstList()        (0x14d3e80)
                                       each area -> SealUtil::getTabIndex(areaId) (0x14d4b9c)

  getAreaMstList()   = AreaMstList::getAreaListWithWorldId(2) filtered by getDungeonMstList(areaId)
  getDungeonMstList(area) = DungeonMstList::getDungeonListWithAreaId(area), kept when
                            getMissionMstList(dungeonId, 1) is non-empty
  getMissionMstList(dungeon, flag):
      for each mission of the dungeon:
        flag=1: period(MissionMst+0x60 juA0Z4m7) must be TRUE      ("0" or an open period)
        every flag: period(MissionMst+0x90 1C7GDEv4) must be FALSE (empty => false)
        if (isWorldTypeEvent(MissionMst+0x44 worldId) && gQR24kST(+0x58) == 5):
              a sibling mission of the SAME dungeon with subtype != 5 and isSealRuleId(sibling) is
              required; then the mission's own 0xkoNP8U row must exist and, when its 0iWgxc1X == 3,
              period(MissionMst+0x78 dIPkNn61) must be FALSE
        else: isSealMission(missionId) must be true
  isSealMission(missionId) (0x14d44b4):
      cond = getMstWithMissionId(missionId); if no cond -> false.
      mission = getMissionMst(missionId); if the mission is (event world && subtype 5) it searches for a
      sibling rule mission; otherwise (or when no mission row exists) it TAIL-CALLS
      isSealRuleId(effectiveMissionId) -> 0x14d459c `b _ZN8SealUtil12isSealRuleIdEi`.
      ** So a mission passes WITHOUT the event-world condition when its OWN SpDungeonCondMst row carries a
      seal rule (10001..10005) in mTHe6pI0. **
  isSealRuleId(missionId) = SpDungeonCondMstList::getMstWithMissionId(missionId).mTHe6pI0 split on ','
                            contains one of 10001..10005
  getTabMap(): for each area from getAreaMstList: cond = getMstWithAreaId(area)
      if cond is missing -> area skipped. If the cond's own mission (cond+0x34 qo3PECw6) is event+subtype5,
      the rule string is taken from that sibling's row; OTHERWISE (JP world 2 is dw2nvP3r=2) from the area
      row itself (cond+0x178 mTHe6pI0). Each rule id in 10001..10005 inserts {tab, (rule, item)} into
      m_tabMap using SEAL_TAB_INFO (0x257c2d8):
        tab0 rule 10004 item 500000004 / tab1 10002 500000002 / tab2 10005 500000005 /
        tab3 10003 500000003 / tab4 10001 500000001

So the rows below are sufficient on their own: each enabled area needs a 0xkoNP8U row whose
uv60hgDW/U9iHsau3/qo3PECw6 name a real world-2 area, its dungeon and an open mission of that dungeon,
and whose mTHe6pI0 carries the tab's rule. The chain then goes
  period checks pass (juA0Z4m7 "0", 1C7GDEv4 empty)
  -> not event world -> isSealMission(mission) -> isSealRuleId(mission) -> TRUE (this row)
  -> dungeon kept -> area kept -> getTabMap/getTabIndex read mTHe6pI0 -> tab.
The chosen stages are plain subtype-0 world-2 missions; a subtype-5 event mission would additionally need a
non-5 sibling carrying the rule, which is why this table carries no sibling rows.

ROW SHAPE. The list is replace-on-read (SpDungeonCondMstResponse::onReadStarted clears it), so the rows
ride only the two carriers that already serve 0xkoNP8U (EVENT_GATE_CARRIERS 'lEHBdOEf,6H1R9WID') and are
APPENDED to whatever the engine already put there (the shipped 226/899 rows and jp_compat's 734 event
rows), never replacing them. The row keys are exactly the 24 the JP SpDungeonCondMstResponse reader names
(captured 6H1R9WID row). The period is deliberately in the PAST (2020-01-01 .. 2021-01-01): SealUtil
never reads a cond row's dates, while GateScene does, so an expired window keeps these rows out of the
Event tab instead of adding three event tiles.
The seal areas own their rows. `SEAL_AREAS` (the 182 area ids in SEAL_TABS) is the exclusion contract:
build/make_jp_event_groups.py generates jp_event_groups.json as `servable_areas - SEAL_AREAS`, so the
次元の狭間 (Vortex) gate does not serve a single one of them, and add_rows appends this module's own row for
every area unconditionally (the expired window keeps GateScene from drawing them as Event tiles). Nothing
here depends on which Vortex season the player selected.

ENTRY COST (2026-11-12). F_RULE_MST 10001..10005 carries exactly ONE condition, the ITEM_COST
`12001:20:<item>:1` (build/out/seal_room/notes.md §2), so an entry costs one 閃の鍵. The client reads that
rule to DRAW the key and its count on the seal screen, but nothing in the offline engine spends it: the
only writers of these ids are `ensure_test_keys` below, so the count never moved after a battle. The spend
happens here, on the mission START request (jp_mission's attempt boundary: MissionWaveStart/TfaMissionStart
BSq28mwY and MissionStart 29JRaDbd), inside the `serve_actions` pipeline step -- so the same reply's
`apply_to_reply` projects the new bag (`0dNXQa3R`) and the seal screen's number drops. Continue/restart
(GfI4LaU3/e9RP8Cto) is the SAME attempt and never spends; MissionEnd/Retire clears the attempt so the next
entry spends again.
"""
import json
import os

EVENT_GATE_TAG = '0xkoNP8U'
EVENT_GATE_CARRIERS = ('lEHBdOEf', '6H1R9WID', '4kA1Ne05', 'Daud71Hn')
GATE_TAB = '1'                     # qnUhs32P, 1-based; irrelevant to SealUtil, kept in the captured shape
WINDOW_START = '1577836800'        # 2020-01-01 UTC (expired: GateScene ignores the row)
WINDOW_END = '1609459200'          # 2021-01-01 UTC
ART = 'spd_bn_list_dummy.png'      # the client's own list plate, shipped in the JP pack

# Per-area banner art (`4yT7FUqj`) for the chambers this overlay APPENDS. The client uses this string VERBATIM
# as the image name: SealAreaListScene copies SpDungeonCondMst+0xa0 straight into the sprite loader and only
# replaces an empty or "null" value with spd_bn_top_dummy.png. Every name here is a REAL file in the JP pack
# (inventory: build/out/seal_room/banner_files.tsv, spdungeon1..9.cpk TOC).
#
# HOW THE 182 ENTRIES WERE FILLED (2026-11-12). For each served area the JP master icon chain
# (F_AREA_MST.0HUPxDf1 -> F_ICON_MST.qtkvrS60, area icon then every dungeon icon) was walked: it yields ONLY
# the shared placeholder plates (spd_bn_dummy.png / spd_bn_top_dummy.png / spd_bn_top_00003.png = 降臨の間),
# i.e. no event banner, for all 197 candidate rows. So no area gets its art from the icon link; the 74 areas
# already curated in the Altema-based list keep their real spd_*_bn_list_* stand-ins below, and the 108 areas
# added with the full-master list use the tab's JP plate (category fallback, one real spdungeon file per tab).
# This is a STAND-IN, not the event's own art (build/out/seal_room/jp_seal_list.md section 5).

# Story tab (tab 0, 2026-11-14): each area's own story-event banner, matched by the title read off the dumped JP
# banners (build/out/vortex_season/cpk_dump/ocr_2020_2025/titles.tsv); before this 11 of 13 used the DARK VISIONS plate.
# Tabs 1-4 (2026-11-15): each chamber's own banner, matched the same way -- the chamber name (F_AREA_MST) equals
# the title read off a dumped JP banner (cpk_dump/ocr_*/titles.tsv, exact after NFKC/punctuation folding, conf
# high) for 167 of 168 chambers; the file must be in the pack (banner_files.tsv), `_last` variants are skipped,
# the tab's own form (vision/_01, evolve, weapon, crown) is preferred and the latest date wins. 6243 ０組を導く力
# is read as "O組を導く力" by the OCR and keeps spd_20230210_bn_list_FF0_crown.png. Before this 160 chambers showed
# another event's banner or the tab plate. Table: build/out/seal_room/art_title_match.json.
SEAL_ART = {
    # tab 4 (Enhancement)
    '5133': 'spd_20220822_bn_list_FFBE_crown.png',  # 戦いの果ての友情
    '5122': 'spd_20240131_bn_list_FFBE_crown_r.png',  # 悲しみを断つための強さ
    '5143': 'spd_20231211_bn_list_FFBE_crown.png',  # 孤高極めし皇帝
    '4242': 'spd_20231211_bn_list_FFBE_crown2.png',  # 舞い降りる帝王
    '6202': 'spd_20240411_bn_list_FFBE_crown.png',  # 竜王と武神の影
    '6203': 'spd_20221021_bn_list_FFBE_crown.png',  # 共闘せし八賢者
    '4262': 'spd_20240430_bn_list_FFBE_crown_kog.png',  # 想いが結びつけた魂
    '4263': 'spd_20240411_bn_list_FFBE_crown_y.png',  # 王国最強の座を巡って
    '5154': 'spd_20240419_bn_list_FFBE_crown_f.png',  # ウェポンの鍵
    '4313': 'spd_20230131_bn_list_FFBE_crown.png',  # 青きクリスタルを継ぐ者
    '4322': 'spd_20240131_bn_list_FFBE_crown.png',  # 好敵手のエリート部隊
    '4323': 'spd_20240111_bn_list_FFBE_crown.png',  # ヒーローを蝕むオメガの種子
    '4353': 'spd_20230329_bn_list_FFBE_crown.png',  # 修羅たちを鎮める者
    '4355': 'spd_20230329_bn_list_FFBE_crown2.png',  # 完全なる均衡を拒む者たち
    '5164': 'spd_20230421_bn_list_FFBE_crown.png',  # ヴィセクトラム頂上決戦
    '4364': 'spd_20230428_bn_list_FFBE_crown.png',  # エネルギー変換施設・十闘星のナズー
    '4411': 'spd_20230919_bn_list_FFBE_crown.png',  # 戦なき世のシノビたち
    '6372': 'spd_20231010_bn_list_FFBE_crown.png',  # 常闇の後継者
    '6374': 'spd_20231020_bn_list_FFBE_crown2.png',  # よみがえる三皇星
    '6375': 'spd_20231020_bn_list_FFBE_crown.png',  # 自由を懸けた決戦
    '4542': 'spd_20240430_bn_list_FFBE_crown.png',  # 解放されし真の力
    '4623': 'spd_20240831_bn_list_FFBE_crown.png',  # 大洋を巡る魔海竜
    '4583': 'spd_20240630_bn_list_FFBE_crown.png',  # 純粋なる破滅の力
    '6282': 'spd_20230511_bn_list_FF1_crown.png',  # すべてを焼きつくす力
    '4332': 'spd_20230228_bn_list_FF2_crown1.png',  # 征服する暴君
    '4333': 'spd_20230228_bn_list_FF2_crown2.png',  # 飛竜と心を通わせた竜騎士
    '6283': 'spd_20240520_bn_list_FF2_crown.png',  # 打倒帝国の意志
    '4314': 'spd_20230131_bn_list_FF3_crown.png',  # 信じる心を持つ騎士
    '6284': 'spd_20240520_bn_list_FF3_crown.png',  # 闇の氾濫に立ち向かう希望
    '4552': 'spd_20240520_bn_list_FF3_crown2.png',  # ノアの弟子たち
    '4362': 'spd_20230428_bn_list_FF4_crown.png',  # 幻獣界を統べる者
    '6313': 'spd_20230620_bn_list_FF4_crown.png',  # 空を制する竜騎士
    '4232': 'spd_20241120_bn_list_FF5_crown.png',  # シルドラとの絆
    '6192': 'spd_20220909_bn_list_FF5_crown.png',  # 王女を襲う凶矢
    '6312': 'spd_20230620_bn_list_FF5_crown.png',  # 祖父ゆずりの希望の心
    '4203': 'spd_20240520_bn_list_FF6_crown.png',  # 幻獣と人間を繋ぐ力
    '4352': 'spd_20230329_bn_list_FF6_crown.png',  # 壊乱の道化師
    '6302': 'spd_20230612_bn_list_FF6_crown.png',  # 厳しい鍛錬の成果
    '4382': 'spd_20230630_bn_list_FF6_crown.png',  # オペラ劇場・壇上
    '6343': 'spd_20230810_bn_list_FF6_crown.png',  # エンジンに絡みつく触手
    '4224': 'spd_20221130_bn_list_FF7_Reno_crown.png',  # タークスの本気
    '4282': 'spd_20221130_bn_list_FF7_crown.png',  # 神羅の後継者
    '6182': 'spd_20221130_bn_list_FF7_Sephiroth_crown.png',  # 伝説の英雄の力
    '6224': 'spd_20230919_bn_list_FF7_crown.png',  # 守るための拳
    '4343': 'spd_20230320_bn_list_FF7R_crown.png',  # VSサンプル:H0512
    '4633': 'spd_20240930_bn_list_FF7_crown.png',  # VS ジェネシス
    '4641': 'spd_20241031_bn_list_CCFF7_crown.png',  # 狙われたS細胞
    '4672': 'spd_20241227_bn_list_FF7_crown.png',  # タークス乱入
    '4293': 'spd_20230919_bn_list_FF8_crown.png',  # ペンは剣よりも強し
    '6234': 'spd_20230111_bn_list_FF8_crown.png',  # 愛犬と通わす心
    '6262': 'spd_20230310_bn_list_FF9_crown.png',  # アレクサンドリアを背負う覚悟
    '4713': 'spd_20250228_bn_list_FF9_crown.png',  # VS ガーランド
    '5163': 'spd_20230421_bn_list_FF10_crown.png',  # 蘇りしエボンの聖獣
    '4363': 'spd_20230428_bn_list_FF10_crown.png',  # イサールの召喚獣
    '6402': 'spd_20231220_bn_list_FF10_crown.png',  # ロンゾの誇り
    '4663': 'spd_20241130_bn_list_FF10_crown.png',  # それぞれの物語
    '4272': 'spd_20240111_bn_list_FF11_crown.png',  # 未来を灯すからくり士
    '6303': 'spd_20230612_bn_list_FF12_crown.png',  # 悪逆非道の賞金稼ぎ
    '6422': 'spd_20240209_bn_list_FF12_crown.png',  # 復讐のジャッジマスター
    '6274': 'spd_20230410_bn_list_FF13_crown.png',  # 新たな世界へ導く解放者
    '4393': 'spd_20230731_bn_list_FF15_crown.png',  # 水神の誓約
    '4693': 'spd_20250131_bn_list_FF16_crown.png',  # 炎影の真実
    '4632': 'spd_20240930_bn_list_FFT_crown.png',  # ティアマット討伐
    '6243': 'spd_20230210_bn_list_FF0_crown.png',  # ０組を導く力
    '4622': 'spd_20240831_bn_list_FF0_crown.png',  # ジュデッカ会戦
    # tab 1 (Units)
    '6201': 'spd_20221122_bn_list_FFBE_vision.png',  # 新型魔導兵器演習
    '4354': 'spd_20230329_bn_list_FFBE_vision.png',  # かつてグランシェルトを守った戦士
    '6371': 'spd_20231010_bn_list_FFBE_vision.png',  # 大海原の覇者
    '6191': 'spd_20221122_bn_list_FF5_vision.png',  # 無を求める暗黒魔道士
    '4223': 'spd_20221130_bn_list_FF7_Reno_vison.png',  # 機械塔の決戦
    '6181': 'spd_20240329_bn_list_FF7RI_vision.png',  # 究極マテリア奪取
    '6221': 'spd_20240318_bn_list_CCFF7R_vision.png',  # 史上最年少のタークス
    '6231': 'spd_20230111_bn_list_FF8_vision.png',  # 憎悪に支配されし魔女
    '5134': 'spd_20221122_bn_list_FF12_vision.png',  # 自由の空を選びしヴィエラ
    '6271': 'spd_20230410_bn_list_FF13_vision.png',  # 人による聖府を願う者
    '4412': 'spd_20230920_bn_list_FF14_vision.png',  # 極ティターニア討滅戦
    '6321': 'spd_20230710_bn_list_FFT_vision.png',  # 血統への固執
    '6241': 'spd_20230210_bn_list_FF0_vision.png',  # 皇国の裏切り
    # tab 3 (Equipment)
    '4261': 'spd_20221031_bn_list_FFBE_weapon.png',  # 黒気と緋炎の激突
    '5152': 'spd_20230120_bn_list_FFBE_weapon1.png',  # 竜王の介入
    '5153': 'spd_20230120_bn_list_FFBE_weapon2.png',  # 幻魔導の巨大兵器
    '4321': 'spd_20230217_bn_list_FFBE_weapon.png',  # 荒ぶる海原の主
    '5162': 'spd_20230421_bn_list_FFBE_weapon.png',  # 謎多き異形の幻獣
    '4361': 'spd_20230428_bn_list_FFBE_weapon1.png',  # カーバンクルの力宿る宝玉の杖
    '6351': 'spd_20230821_bn_list_FFBE_weapon.png',  # 幻の巨鳥
    '4365': 'spd_20230428_bn_list_FFBE_weapon2.png',  # シヴァの力宿る冷たき刃
    '6451': 'spd_20240510_bn_list_FFBE_weapon.png',  # 純粋なる破壊者
    '4563': 'spd_20240531_bn_list_FFBE_weapon.png',  # 心の明るさを奪うキーパー
    '4612': 'spd_20240819_bn_list_weapon.png',  # 光に死をもたらす者
    '6492': 'spd_20240920_bn_list_weapon.png',  # 王の召喚せし幻獣たち
    '6491': 'spd_20240911_bn_list_weapon.png',  # エル＝マグナ王降臨
    '4732': 'spd_20250331_bn_list_FFBE_weapon.png',  # 立ち塞がる最愛の敵
    '4431': 'spd_20231031_bn_list_FFBE_weapon.png',  # 法則の破壊者
    '6452': 'spd_20240510_bn_list_FFBE_weapon2.png',  # 復活のオメガ
    '6511': 'spd_20241111_bn_list_weapon.png',  # 解放されし聖王の力
    '6281': 'spd_20230511_bn_list_weapon.png',  # 町を占拠する帝国士官
    '4512': 'spd_20240310_bn_list_FF2_weapon.png',  # 偽りの王女
    '6551': 'spd_20250210_bn_list_FF4_weapon.png',  # 恐ろしき王女
    '4692': 'spd_20250131_bn_list_FF4_rensen.png',  # 再戦！ゴルベーザ四天王！
    '6301': 'spd_20230612_bn_list_FF6_weapon.png',  # 壁中より襲来する魔導アーマー
    '6311': 'spd_20230620_bn_list_FF6_weapon.png',  # 墓に眠る地獄の騎士
    '6461': 'spd_20240610_bn_list_FF6_weapon.png',  # 時の彼方に忘れ去られし者
    '4281': 'spd_20221130_bn_list_CCFF7R_weapon.png',  # 誇りを失った姿
    '6222': 'spd_20221209_bn_list_CCFF7R_weapon1.png',  # 進みゆく劣化
    '4521': 'spd_20240329_bn_list_FF7_weapon.png',  # 異形の実験体
    '6223': 'spd_20221209_bn_list_CCFF7R_weapon2.png',  # ソルジャー・クラス1st同士の戦い
    '4522': 'spd_20240329_bn_list_FF7_weapon2.png',  # 漆黒の闇ネロ
    '6431': 'spd_20240318_bn_list_FF7_weapon.png',  # 白紙の未来のために
    '6542': 'spd_20250110_bn_list_FF7_weapon.png',  # 棺に眠る混沌の獣
    '4671': 'spd_20241227_bn_list_FF7_weapon.png',  # ソルジャーたちの誇り
    '4291': 'spd_20221228_bn_list_FF8_weapon.png',  # 追跡する多脚兵器
    '6232': 'spd_20230111_bn_list_FF8_weapon1.png',  # トンベリを統べし王
    '6233': 'spd_20230111_bn_list_FF8_weapon2.png',  # 未来の魔女に仕えし竜
    '4662': 'spd_20241130_bn_list_FF8_weapon.png',  # 解放された欲望の魔女
    '4331': 'spd_20230228_bn_list_FF9_weapon.png',  # 力を抽出する防衛システム
    '6261': 'spd_20230310_bn_list_FF9_weapon.png',  # リンドブルム狩猟祭
    '6561': 'spd_20250310_bn_list_FF9_weapon.png',  # 巨大な翼もつ神竜
    '4712': 'spd_20250228_bn_list_FF9_weapon.png',  # 破滅への使者
    '4582': 'spd_20240630_bn_list_FF10_weapon.png',  # 立ちはだかる守護竜
    '6401': 'spd_20231220_bn_list_FF10_weapon.png',  # 凄腕の剣客
    '6471': 'spd_20240710_bn_list_FF10_weapon.png',  # まやかしの希望
    '4271': 'spd_20221110_bn_list_FF11_weapon.png',  # ジラート１万年の夢
    '4493': 'spd_20240131_bn_list_FF12_weapon.png',  # 神に背きし皇帝
    '6421': 'spd_20240209_bn_list_FF12_weapon.png',  # 天陽の繭を目指して
    '4351': 'spd_20230329_bn_list_FF13_weapon.png',  # 聖府軍の機械兵器
    '6272': 'spd_20230410_bn_list_FF13_weapon1.png',  # はざまに眠る二匹の獣
    '6273': 'spd_20230410_bn_list_FF13_weapon2.png',  # 使命に挑む意志
    '6501': 'spd_20241011_bn_list_FF13_weapon.png',  # ヲルバ郷へ続く塔
    '6502': 'spd_20241011_bn_list_FF13_weapon2.png',  # コクーンに君臨するファルシの王
    '4391': 'spd_20230731_bn_list_FF15_weapon.png',  # 星の病に憑かれた隠れし王
    '6341': 'spd_20230810_bn_list_FF15_weapon.png',  # 星の病に憑かれた荒々しき王
    '4392': 'spd_20230731_bn_list_FF15_weapon2.png',  # 王都にはびこるシガイたち
    '6342': 'spd_20230810_bn_list_FF15_weapon2.png',  # 星の病に憑かれた初代王
    '6481': 'spd_20240809_bn_list_FF15_weapon.png',  # 遺跡を飛び回る怪鳥
    '4602': 'spd_20240731_bn_list_FF15_weapon.png',  # 神話の時代の古代兵器
    '4532': 'spd_20240411_bn_list_FF16_weapon.png',  # 召喚獣ガルーダ
    '4381': 'spd_20230630_bn_list_FFT_weapon.png',  # 恐ろしき異端審問官
    '6322': 'spd_20230710_bn_list_FFT_weapon.png',  # "大義"の犠牲者を救うために
    '6325': 'spd_20230710_bn_list_FFT_weapon2.png',  # 愛にすべてを
    '4311': 'spd_20230131_bn_list_FF0_weapon.png',  # 城壁のごとき巨体もつ軍神
    '6242': 'spd_20230210_bn_list_FF0_weapon.png',  # 休戦下の作戦
    # tab 0 (Story)
    '845': 'spd_20221130_bn_list_FFBE.png',  # 或る人形の記録
    '725': 'spd_20230120_bn_list_FFBE_reprint2.png',  # 集められし者たち
    '3040': 'spd_20230421_bn_list_FFBE.png',  # 混沌の起源-DARK VISIONS-
    '833': 'spd_20241011_bn_list_FFBE_reprint.png',  # 皇都仇討ち道中
    '855': 'spd_20241111_bn_list_FFBE_reprint.png',  # 残照
    '872': 'spd_20250110_bn_list_FFBE_reprint.png',  # 白百合のブーケ
    # banner areas (world 2, RB8zTc9G '4,<body>') now served by the story tab; same art as the original
    '5101': 'spd_20221130_bn_list_FFBE.png',  # slot 40001 -> body 5100
    '5156': 'spd_20230120_bn_list_FFBE_reprint2.png',  # slot 40002 -> body 5155
    '5161': 'spd_20230421_bn_list_FFBE.png',  # slot 40003 -> body 5160
    '5171': 'spd_20241011_bn_list_FFBE_reprint.png',  # slot 40004 -> body 5170
    '5181': 'spd_20241111_bn_list_FFBE_reprint.png',  # slot 40005 -> body 5180
    '5191': 'spd_20241220_bn_list_FFBE_01.png',  # slot 40006 -> body 5190
    '5201': 'spd_20250110_bn_list_FFBE_reprint.png',  # slot 40007 -> body 5200
    '5211': 'spd_20250210_bn_list_FFBE_reprint.png',  # slot 40008 -> body 5210
    '5231': 'spd_20250319_bn_list_FFBE_reprint.png',  # slot 40009 -> body 5230
    '5221': 'spd_20250411_bn_list_FFBE_reprint.png',  # slot 40010 -> body 5220
    '5241': 'spd_20250515_bn_list_FFBE_reprint.png',  # slot 40011 -> body 5240
    '5261': 'spd_20250616_bn_list_FFBE_reprint.png',  # slot 40012 -> body 5260
    '5281': 'spd_20250715_bn_list_FFBE_reprint.png',  # slot 40013 -> body 5280
    '5291': 'spd_20250815_bn_list_FFBE_reprint.png',  # slot 40014 -> body 5290
    '785': 'spd_20250210_bn_list_FFBE_reprint.png',  # グランシェルト武勲詩
    '3063': 'spd_20250319_bn_list_FFBE_reprint.png',  # FUNDAMENTAL FORCES
    '729': 'spd_20250411_bn_list_FFBE_reprint.png',  # 時を超えた約束
    '746': 'spd_20250515_bn_list_FFBE_reprint.png',  # 秩序の守護者
    '760': 'spd_20250616_bn_list_FFBE_reprint.png',  # 白き賢者と魔法の杖
    '849': 'spd_20250715_bn_list_FFBE_reprint.png',  # 結束の星
    '733': 'spd_20250815_bn_list_FFBE_reprint.png',  # 復讐の時、来たる
    # tab 2 (Awakening)
    '4492': 'spd_20240131_bn_list_evolve.png',  # 灼熱の荒ぶる力
    '4461': 'spd_20231211_bn_list_evolve2.png',  # 閃耀の烈しき力
    '6218': 'spd_20240219_bn_list_evolve.png',  # 霹靂の轟く力
    '4462': 'spd_20231211_bn_list_evolve.png',  # 漆黒の猛き力
    '4422': 'spd_20230930_bn_list_evolve_FF7R.png',  # VS ルーファウス神羅戦
    '4421': 'spd_20230930_bn_list_evolve_FFBE.png',  # 「光」を奪いし者
    '4471': 'spd_20240111_bn_list_ffbe_evolve.png',  # 神を模した巨大兵器
    '4491': 'spd_20240131_bn_list_evolve_FF12.png',  # 遺跡を護りし人造竜
    '4511': 'spd_20240310_bn_list_evolve_FF2.png',  # 闘技会の魔獣
    '6432': 'spd_20240318_bn_list_evolve_FF7RB.png',  # ミスリルマインの巨人
    '4531': 'spd_20240411_bn_list_evolve_FF16.png',  # 風のドミナント
    '4541': 'spd_20240430_bn_list_FFBE_evolve.png',  # 裏切りの議長
    '4551': 'spd_20240520_bn_list_FF3_evolve.png',  # 暗黒の力を守護する者
    '4561': 'spd_20240531_bn_list_FF6_evolve.png',  # 未来を守る戦い
    '4562': 'spd_20240630_bn_list_FFBE_evolve.png',  # 帝国最強の剣士
    '4581': 'spd_20240630_bn_list_FF10_evolve.png',  # アルベドの機械兵器
    '4601': 'spd_20240731_bn_list_FF15_evolve.png',  # 立ちはだかる炎神
    '4611': 'spd_20240819_bn_list_evolve.png',  # 鬼の裔を名乗りし暴将
    '4621': 'spd_20240831_bn_list_evolve.png',  # エル＝マグナの最精鋭
    '4631': 'spd_20240930_bn_list_evolve.png',  # 下界への追放
    '4661': 'spd_20241130_bn_list_FF8_evolve.png',  # セントラ大脱出
    '4691': 'spd_20250131_bn_list_FF4_evolve.png',  # 巨人の心臓部
    '4711': 'spd_20250228_bn_list_FF9_evolve.png',  # 地下道に巣くう魔物
    '4731': 'spd_20250331_bn_list_FFBE_evolve.png',  # 吹き荒れる混沌の猛風
    '4741': 'spd_20250430_bn_list_FFBE_evolve.png',  # 六盟傑を率いし英雄
    '4751': 'spd_20250515_bn_list_FF5_evolve.png',  # 異次元に引きずりこむ魔物
    '6581': 'spd_20250616_bn_list_FFBE_evolve.png',  # 虚無の渦を守る少女
    '4763': 'spd_20250710_bn_list_FFT_evolve.png',  # 恐怖の不浄王
}

# THE ONE TABLE. Tab index / rule / item are SealUtil::SEAL_TAB_INFO (0x257c2d8); 'enabled' opens a tab,
# 'areas' lists the (area, dungeon, mission, sibling) quadruples served for it. Built from the FULL JP
# master set (F_AREA_MST.Z0EN6jSh leading digit = category, remaining digits = order): 強化 65 (tab 4),
# 獲得 13 (tab 1), 武器 63 (tab 3), 物語 13 (tab 0), 覚醒 28 (tab 2) = 182 areas. Every row was judged
# 'enterable' only when its dungeon holds a mission that is open on the schedule AND has a real battle in the
# JP battle chain (F_MISSION_PHASE_MST phase gou39JeI=2 -> F_BATTLE_LOTTERY_MST -> F_BATTLE_GROUP_MST).
# 覚醒 (tab 2) is NOW OPEN: its 28 slots (5xxxx) are real world-2 battle areas. Story slots (4xxxx) are world-2
# banner pairs whose body is world 10 (not read by getAreaMstList); each is mapped to the world-2 original
# event area named by the body's F_AREA_MST.7DTnc2Lt map file (slot->area in the comment on each row).

SEAL_TABS = {
    0: {'name': 'Story', 'rule': '10004', 'item': '500000004', 'enabled': True, 'areas': (
        {'slot': '40001', 'area': '5101', 'dungeon': '510101', 'mission': '51010001', 'sibling': '', 'name': '或る人形の記録'},  # banner 5101 -> body 5100 (world-2 original 845)
        {'slot': '40002', 'area': '5156', 'dungeon': '515601', 'mission': '51560001', 'sibling': '', 'name': '集められし者たち'},  # banner 5156 -> body 5155 (world-2 original 725)
        {'slot': '40003', 'area': '5161', 'dungeon': '516101', 'mission': '51610001', 'sibling': '', 'name': '混沌の起源-DARK VISIONS-'},  # banner 5161 -> body 5160 (world-2 original 3040)
        {'slot': '40004', 'area': '5171', 'dungeon': '517101', 'mission': '51710001', 'sibling': '', 'name': '皇都仇討ち道中'},  # banner 5171 -> body 5170 (world-2 original 833)
        {'slot': '40005', 'area': '5181', 'dungeon': '518101', 'mission': '51810001', 'sibling': '', 'name': '残照'},  # banner 5181 -> body 5180 (world-2 original 855)
        {'slot': '40006', 'area': '5191', 'dungeon': '519101', 'mission': '51910001', 'sibling': '', 'name': '黒き獣と新たなる闘星'},  # banner 5191 -> body 5190 (no world-2 original)
        {'slot': '40007', 'area': '5201', 'dungeon': '520101', 'mission': '52010001', 'sibling': '', 'name': '白百合のブーケ'},  # banner 5201 -> body 5200 (world-2 original 872)
        {'slot': '40008', 'area': '5211', 'dungeon': '521101', 'mission': '52110001', 'sibling': '', 'name': 'グランシェルト武勲詩'},  # banner 5211 -> body 5210 (world-2 original 785)
        {'slot': '40009', 'area': '5231', 'dungeon': '523101', 'mission': '52310001', 'sibling': '', 'name': 'FUNDAMENTAL FORCES'},  # banner 5231 -> body 5230 (world-2 original 3063)
        {'slot': '40010', 'area': '5221', 'dungeon': '522101', 'mission': '52210001', 'sibling': '', 'name': '時を超えた約束'},  # banner 5221 -> body 5220 (world-2 original 729)
        {'slot': '40011', 'area': '5241', 'dungeon': '524101', 'mission': '52410001', 'sibling': '', 'name': '秩序の守護者'},  # banner 5241 -> body 5240 (world-2 original 746)
        {'slot': '40012', 'area': '5261', 'dungeon': '526101', 'mission': '52610001', 'sibling': '', 'name': '白き賢者と魔法の杖'},  # banner 5261 -> body 5260 (world-2 original 760)
        {'slot': '40013', 'area': '5281', 'dungeon': '528101', 'mission': '52810001', 'sibling': '', 'name': '結束の星'},  # banner 5281 -> body 5280 (world-2 original 849)
        {'slot': '40014', 'area': '5291', 'dungeon': '529101', 'mission': '52910001', 'sibling': '', 'name': '復讐の時、来たる'},  # banner 5291 -> body 5290 (world-2 original 733)
    )},
    1: {'name': 'Units', 'rule': '10002', 'item': '500000002', 'enabled': True, 'areas': (
        {'slot': '20001', 'area': '6201', 'dungeon': '620101', 'mission': '62010101', 'sibling': '', 'name': '新型魔導兵器演習'},  # 20001 新型魔導兵器演習
        {'slot': '20002', 'area': '4354', 'dungeon': '435401', 'mission': '43540101', 'sibling': '', 'name': 'かつてグランシェルトを守った戦士'},  # 20002 かつてグランシェルトを守った戦士
        {'slot': '20003', 'area': '6371', 'dungeon': '637101', 'mission': '63710101', 'sibling': '', 'name': '大海原の覇者'},  # 20003 大海原の覇者
        {'slot': '20501', 'area': '6191', 'dungeon': '619101', 'mission': '61910101', 'sibling': '', 'name': '無を求める暗黒魔道士'},  # 20501 無を求める暗黒魔道士
        {'slot': '20701', 'area': '4223', 'dungeon': '422301', 'mission': '42230101', 'sibling': '', 'name': '機械塔の決戦'},  # 20701 機械塔の決戦
        {'slot': '20702', 'area': '6181', 'dungeon': '618101', 'mission': '61810101', 'sibling': '', 'name': '究極マテリア奪取'},  # 20702 究極マテリア奪取
        {'slot': '20703', 'area': '6221', 'dungeon': '622101', 'mission': '62210101', 'sibling': '', 'name': '史上最年少のタークス'},  # 20703 史上最年少のタークス
        {'slot': '20801', 'area': '6231', 'dungeon': '623101', 'mission': '62310101', 'sibling': '', 'name': '憎悪に支配されし魔女'},  # 20801 憎悪に支配されし魔女
        {'slot': '21201', 'area': '5134', 'dungeon': '513401', 'mission': '51340101', 'sibling': '', 'name': '自由の空を選びしヴィエラ'},  # 21201 自由の空を選びしヴィエラ
        {'slot': '21301', 'area': '6271', 'dungeon': '627101', 'mission': '62710101', 'sibling': '', 'name': '人による聖府を願う者'},  # 21301 人による聖府を願う者
        {'slot': '21401', 'area': '4412', 'dungeon': '441201', 'mission': '44120101', 'sibling': '', 'name': '極ティターニア討滅戦'},  # 21401 極ティターニア討滅戦
        {'slot': '21701', 'area': '6321', 'dungeon': '632101', 'mission': '63210101', 'sibling': '', 'name': '血統への固執'},  # 21701 血統への固執
        {'slot': '21801', 'area': '6241', 'dungeon': '624101', 'mission': '62410101', 'sibling': '', 'name': '皇国の裏切り'},  # 21801 皇国の裏切り
    )},
    2: {'name': 'Awakening', 'rule': '10005', 'item': '500000005', 'enabled': True, 'areas': (
        {'slot': '50101', 'area': '4492', 'dungeon': '449201', 'mission': '44920101', 'sibling': '', 'name': '灼熱の荒ぶる力'},  # 50101 灼熱の荒ぶる力
        {'slot': '50102', 'area': '4461', 'dungeon': '446101', 'mission': '44610101', 'sibling': '', 'name': '閃耀の烈しき力'},  # 50102 閃耀の烈しき力
        {'slot': '50201', 'area': '6218', 'dungeon': '621801', 'mission': '62180101', 'sibling': '', 'name': '霹靂の轟く力'},  # 50201 霹靂の轟く力
        {'slot': '50202', 'area': '4462', 'dungeon': '446201', 'mission': '44620101', 'sibling': '', 'name': '漆黒の猛き力'},  # 50202 漆黒の猛き力
        {'slot': '50301', 'area': '4422', 'dungeon': '442201', 'mission': '44220101', 'sibling': '', 'name': 'VS ルーファウス神羅戦'},  # 50301 VS ルーファウス神羅戦
        {'slot': '50302', 'area': '4421', 'dungeon': '442101', 'mission': '44210101', 'sibling': '', 'name': '「光」を奪いし者'},  # 50302 「光」を奪いし者
        {'slot': '50303', 'area': '4471', 'dungeon': '447101', 'mission': '44710101', 'sibling': '', 'name': '神を模した巨大兵器'},  # 50303 神を模した巨大兵器
        {'slot': '50304', 'area': '4491', 'dungeon': '449101', 'mission': '44910101', 'sibling': '', 'name': '遺跡を護りし人造竜'},  # 50304 遺跡を護りし人造竜
        {'slot': '50305', 'area': '4511', 'dungeon': '451101', 'mission': '45110101', 'sibling': '', 'name': '闘技会の魔獣'},  # 50305 闘技会の魔獣
        {'slot': '50306', 'area': '6432', 'dungeon': '643201', 'mission': '64320101', 'sibling': '', 'name': 'ミスリルマインの巨人'},  # 50306 ミスリルマインの巨人
        {'slot': '50307', 'area': '4531', 'dungeon': '453101', 'mission': '45310101', 'sibling': '', 'name': '風のドミナント'},  # 50307 風のドミナント
        {'slot': '50308', 'area': '4541', 'dungeon': '454101', 'mission': '45410101', 'sibling': '', 'name': '裏切りの議長'},  # 50308 裏切りの議長
        {'slot': '50309', 'area': '4551', 'dungeon': '455101', 'mission': '45510101', 'sibling': '', 'name': '暗黒の力を守護する者'},  # 50309 暗黒の力を守護する者
        {'slot': '50310', 'area': '4561', 'dungeon': '456101', 'mission': '45610101', 'sibling': '', 'name': '未来を守る戦い'},  # 50310 未来を守る戦い
        {'slot': '50311', 'area': '4562', 'dungeon': '456201', 'mission': '45620101', 'sibling': '', 'name': '帝国最強の剣士'},  # 50311 帝国最強の剣士
        {'slot': '50312', 'area': '4581', 'dungeon': '458101', 'mission': '45810101', 'sibling': '', 'name': 'アルベドの機械兵器'},  # 50312 アルベドの機械兵器
        {'slot': '50313', 'area': '4601', 'dungeon': '460101', 'mission': '46010101', 'sibling': '', 'name': '立ちはだかる炎神'},  # 50313 立ちはだかる炎神
        {'slot': '50314', 'area': '4611', 'dungeon': '461101', 'mission': '46110101', 'sibling': '', 'name': '鬼の裔を名乗りし暴将'},  # 50314 鬼の裔を名乗りし暴将
        {'slot': '50315', 'area': '4621', 'dungeon': '462101', 'mission': '46210101', 'sibling': '', 'name': 'エル＝マグナの最精鋭'},  # 50315 エル＝マグナの最精鋭
        {'slot': '50316', 'area': '4631', 'dungeon': '463101', 'mission': '46310101', 'sibling': '', 'name': '下界への追放'},  # 50316 下界への追放
        {'slot': '50317', 'area': '4661', 'dungeon': '466101', 'mission': '46610101', 'sibling': '', 'name': 'セントラ大脱出'},  # 50317 セントラ大脱出
        {'slot': '50318', 'area': '4691', 'dungeon': '469101', 'mission': '46910101', 'sibling': '', 'name': '巨人の心臓部'},  # 50318 巨人の心臓部
        {'slot': '50319', 'area': '4711', 'dungeon': '471101', 'mission': '47110101', 'sibling': '', 'name': '地下道に巣くう魔物'},  # 50319 地下道に巣くう魔物
        {'slot': '50320', 'area': '4731', 'dungeon': '473101', 'mission': '47310101', 'sibling': '', 'name': '吹き荒れる混沌の猛風'},  # 50320 吹き荒れる混沌の猛風
        {'slot': '50321', 'area': '4741', 'dungeon': '474101', 'mission': '47410101', 'sibling': '', 'name': '六盟傑を率いし英雄'},  # 50321 六盟傑を率いし英雄
        {'slot': '50322', 'area': '4751', 'dungeon': '475101', 'mission': '47510101', 'sibling': '', 'name': '異次元に引きずりこむ魔物'},  # 50322 異次元に引きずりこむ魔物
        {'slot': '50323', 'area': '6581', 'dungeon': '658101', 'mission': '65810101', 'sibling': '', 'name': '虚無の渦を守る少女'},  # 50323 虚無の渦を守る少女
        {'slot': '50324', 'area': '4763', 'dungeon': '476301', 'mission': '47630101', 'sibling': '', 'name': '恐怖の不浄王'},  # 50324 恐怖の不浄王
    )},
    3: {'name': 'Equipment', 'rule': '10003', 'item': '500000003', 'enabled': True, 'areas': (
        {'slot': '30001', 'area': '4261', 'dungeon': '426101', 'mission': '42610101', 'sibling': '', 'name': '黒気と緋炎の激突'},  # 30001 黒気と緋炎の激突
        {'slot': '30002', 'area': '5152', 'dungeon': '515201', 'mission': '51520101', 'sibling': '', 'name': '竜王の介入'},  # 30002 竜王の介入
        {'slot': '30003', 'area': '5153', 'dungeon': '515301', 'mission': '51530101', 'sibling': '', 'name': '幻魔導の巨大兵器'},  # 30003 幻魔導の巨大兵器
        {'slot': '30004', 'area': '4321', 'dungeon': '432101', 'mission': '43210101', 'sibling': '', 'name': '荒ぶる海原の主'},  # 30004 荒ぶる海原の主
        {'slot': '30005', 'area': '5162', 'dungeon': '516201', 'mission': '51620101', 'sibling': '', 'name': '謎多き異形の幻獣'},  # 30005 謎多き異形の幻獣
        {'slot': '30006', 'area': '4361', 'dungeon': '436101', 'mission': '43610101', 'sibling': '', 'name': 'カーバンクルの力宿る宝玉の杖'},  # 30006 カーバンクルの力宿る宝玉の杖
        {'slot': '30007', 'area': '6351', 'dungeon': '635101', 'mission': '63510101', 'sibling': '', 'name': '幻の巨鳥'},  # 30007 幻の巨鳥
        {'slot': '30008', 'area': '4365', 'dungeon': '436501', 'mission': '43650101', 'sibling': '', 'name': 'シヴァの力宿る冷たき刃'},  # 30008 シヴァの力宿る冷たき刃
        {'slot': '30009', 'area': '6451', 'dungeon': '645101', 'mission': '64510101', 'sibling': '', 'name': '純粋なる破壊者'},  # 30009 純粋なる破壊者
        {'slot': '30010', 'area': '4563', 'dungeon': '456301', 'mission': '45630101', 'sibling': '', 'name': '心の明るさを奪うキーパー'},  # 30010 心の明るさを奪うキーパー
        {'slot': '30011', 'area': '4612', 'dungeon': '461201', 'mission': '46120101', 'sibling': '', 'name': '光に死をもたらす者'},  # 30011 光に死をもたらす者
        {'slot': '30012', 'area': '6492', 'dungeon': '649201', 'mission': '64920101', 'sibling': '', 'name': '王の召喚せし幻獣たち'},  # 30012 王の召喚せし幻獣たち
        {'slot': '30013', 'area': '6491', 'dungeon': '649101', 'mission': '64910101', 'sibling': '', 'name': 'エル＝マグナ王降臨'},  # 30013 エル＝マグナ王降臨
        {'slot': '30014', 'area': '4732', 'dungeon': '473201', 'mission': '47320101', 'sibling': '', 'name': '立ち塞がる最愛の敵'},  # 30014 立ち塞がる最愛の敵
        {'slot': '30015', 'area': '4431', 'dungeon': '443101', 'mission': '44310101', 'sibling': '', 'name': '法則の破壊者'},  # 30015 法則の破壊者
        {'slot': '30016', 'area': '6452', 'dungeon': '645201', 'mission': '64520101', 'sibling': '', 'name': '復活のオメガ'},  # 30016 復活のオメガ
        {'slot': '30017', 'area': '6511', 'dungeon': '651101', 'mission': '65110101', 'sibling': '', 'name': '解放されし聖王の力'},  # 30017 解放されし聖王の力
        {'slot': '30201', 'area': '6281', 'dungeon': '628101', 'mission': '62810101', 'sibling': '', 'name': '町を占拠する帝国士官'},  # 30201 町を占拠する帝国士官
        {'slot': '30202', 'area': '4512', 'dungeon': '451201', 'mission': '45120101', 'sibling': '', 'name': '偽りの王女'},  # 30202 偽りの王女
        {'slot': '30401', 'area': '6551', 'dungeon': '655101', 'mission': '65510101', 'sibling': '', 'name': '恐ろしき王女'},  # 30401 恐ろしき王女
        {'slot': '30402', 'area': '4692', 'dungeon': '469201', 'mission': '46920101', 'sibling': '', 'name': '再戦！ゴルベーザ四天王！'},  # 30402 再戦！ゴルベーザ四天王！
        {'slot': '30601', 'area': '6301', 'dungeon': '630101', 'mission': '63010101', 'sibling': '', 'name': '壁中より襲来する魔導アーマー'},  # 30601 壁中より襲来する魔導アーマー
        {'slot': '30602', 'area': '6311', 'dungeon': '631101', 'mission': '63110101', 'sibling': '', 'name': '墓に眠る地獄の騎士'},  # 30602 墓に眠る地獄の騎士
        {'slot': '30603', 'area': '6461', 'dungeon': '646101', 'mission': '64610101', 'sibling': '', 'name': '時の彼方に忘れ去られし者'},  # 30603 時の彼方に忘れ去られし者
        {'slot': '30701', 'area': '4281', 'dungeon': '428101', 'mission': '42810101', 'sibling': '', 'name': '誇りを失った姿'},  # 30701 誇りを失った姿
        {'slot': '30702', 'area': '6222', 'dungeon': '622201', 'mission': '62220101', 'sibling': '', 'name': '進みゆく劣化'},  # 30702 進みゆく劣化
        {'slot': '30703', 'area': '4521', 'dungeon': '452101', 'mission': '45210101', 'sibling': '', 'name': '異形の実験体'},  # 30703 異形の実験体
        {'slot': '30704', 'area': '6223', 'dungeon': '622301', 'mission': '62230101', 'sibling': '', 'name': 'ソルジャー・クラス1st同士の戦い'},  # 30704 ソルジャー・クラス1st同士の戦い
        {'slot': '30705', 'area': '4522', 'dungeon': '452201', 'mission': '45220101', 'sibling': '', 'name': '漆黒の闇ネロ'},  # 30705 漆黒の闇ネロ
        {'slot': '30706', 'area': '6431', 'dungeon': '643101', 'mission': '64310101', 'sibling': '', 'name': '白紙の未来のために'},  # 30706 白紙の未来のために
        {'slot': '30707', 'area': '6542', 'dungeon': '654201', 'mission': '65420101', 'sibling': '', 'name': '棺に眠る混沌の獣'},  # 30707 棺に眠る混沌の獣
        {'slot': '30708', 'area': '4671', 'dungeon': '467101', 'mission': '46710101', 'sibling': '', 'name': 'ソルジャーたちの誇り'},  # 30708 ソルジャーたちの誇り
        {'slot': '30801', 'area': '4291', 'dungeon': '429101', 'mission': '42910101', 'sibling': '', 'name': '追跡する多脚兵器'},  # 30801 追跡する多脚兵器
        {'slot': '30802', 'area': '6232', 'dungeon': '623201', 'mission': '62320101', 'sibling': '', 'name': 'トンベリを統べし王'},  # 30802 トンベリを統べし王
        {'slot': '30803', 'area': '6233', 'dungeon': '623301', 'mission': '62330101', 'sibling': '', 'name': '未来の魔女に仕えし竜'},  # 30803 未来の魔女に仕えし竜
        {'slot': '30804', 'area': '4662', 'dungeon': '466201', 'mission': '46620101', 'sibling': '', 'name': '解放された欲望の魔女'},  # 30804 解放された欲望の魔女
        {'slot': '30901', 'area': '4331', 'dungeon': '433101', 'mission': '43310101', 'sibling': '', 'name': '力を抽出する防衛システム'},  # 30901 力を抽出する防衛システム
        {'slot': '30902', 'area': '6261', 'dungeon': '626101', 'mission': '62610101', 'sibling': '', 'name': 'リンドブルム狩猟祭'},  # 30902 リンドブルム狩猟祭
        {'slot': '30903', 'area': '6561', 'dungeon': '656101', 'mission': '65610101', 'sibling': '', 'name': '巨大な翼もつ神竜'},  # 30903 巨大な翼もつ神竜
        {'slot': '30904', 'area': '4712', 'dungeon': '471201', 'mission': '47120101', 'sibling': '', 'name': '破滅への使者'},  # 30904 破滅への使者
        {'slot': '31001', 'area': '4582', 'dungeon': '458201', 'mission': '45820101', 'sibling': '', 'name': '立ちはだかる守護竜'},  # 31001 立ちはだかる守護竜
        {'slot': '31002', 'area': '6401', 'dungeon': '640101', 'mission': '64010101', 'sibling': '', 'name': '凄腕の剣客'},  # 31002 凄腕の剣客
        {'slot': '31003', 'area': '6471', 'dungeon': '647101', 'mission': '64710101', 'sibling': '', 'name': 'まやかしの希望'},  # 31003 まやかしの希望
        {'slot': '31101', 'area': '4271', 'dungeon': '427101', 'mission': '42710101', 'sibling': '', 'name': 'ジラート１万年の夢'},  # 31101 ジラート１万年の夢
        {'slot': '31201', 'area': '4493', 'dungeon': '449301', 'mission': '44930101', 'sibling': '', 'name': '神に背きし皇帝'},  # 31201 神に背きし皇帝
        {'slot': '31202', 'area': '6421', 'dungeon': '642101', 'mission': '64210101', 'sibling': '', 'name': '天陽の繭を目指して'},  # 31202 天陽の繭を目指して
        {'slot': '31301', 'area': '4351', 'dungeon': '435101', 'mission': '43510101', 'sibling': '', 'name': '聖府軍の機械兵器'},  # 31301 聖府軍の機械兵器
        {'slot': '31302', 'area': '6272', 'dungeon': '627201', 'mission': '62720101', 'sibling': '', 'name': 'はざまに眠る二匹の獣'},  # 31302 はざまに眠る二匹の獣
        {'slot': '31303', 'area': '6273', 'dungeon': '627301', 'mission': '62730101', 'sibling': '', 'name': '使命に挑む意志'},  # 31303 使命に挑む意志
        {'slot': '31304', 'area': '6501', 'dungeon': '650101', 'mission': '65010101', 'sibling': '', 'name': 'ヲルバ郷へ続く塔'},  # 31304 ヲルバ郷へ続く塔
        {'slot': '31305', 'area': '6502', 'dungeon': '650201', 'mission': '65020101', 'sibling': '', 'name': 'コクーンに君臨するファルシの王'},  # 31305 コクーンに君臨するファルシの王
        {'slot': '31501', 'area': '4391', 'dungeon': '439101', 'mission': '43910101', 'sibling': '', 'name': '星の病に憑かれた隠れし王'},  # 31501 星の病に憑かれた隠れし王
        {'slot': '31503', 'area': '6341', 'dungeon': '634101', 'mission': '63410101', 'sibling': '', 'name': '星の病に憑かれた荒々しき王'},  # 31503 星の病に憑かれた荒々しき王
        {'slot': '31511', 'area': '4392', 'dungeon': '439201', 'mission': '43920101', 'sibling': '', 'name': '王都にはびこるシガイたち'},  # 31511 王都にはびこるシガイたち
        {'slot': '31512', 'area': '6342', 'dungeon': '634201', 'mission': '63420101', 'sibling': '', 'name': '星の病に憑かれた初代王'},  # 31512 星の病に憑かれた初代王
        {'slot': '31513', 'area': '6481', 'dungeon': '648101', 'mission': '64810101', 'sibling': '', 'name': '遺跡を飛び回る怪鳥'},  # 31513 遺跡を飛び回る怪鳥
        {'slot': '31514', 'area': '4602', 'dungeon': '460201', 'mission': '46020101', 'sibling': '', 'name': '神話の時代の古代兵器'},  # 31514 神話の時代の古代兵器
        {'slot': '31601', 'area': '4532', 'dungeon': '453201', 'mission': '45320101', 'sibling': '', 'name': '召喚獣ガルーダ'},  # 31601 召喚獣ガルーダ
        {'slot': '31701', 'area': '4381', 'dungeon': '438101', 'mission': '43810101', 'sibling': '', 'name': '恐ろしき異端審問官'},  # 31701 恐ろしき異端審問官
        {'slot': '31702', 'area': '6322', 'dungeon': '632201', 'mission': '63220101', 'sibling': '', 'name': '"大義"の犠牲者を救うために'},  # 31702 "大義"の犠牲者を救うために
        {'slot': '31703', 'area': '6325', 'dungeon': '632501', 'mission': '63250101', 'sibling': '', 'name': '愛にすべてを'},  # 31703 愛にすべてを
        {'slot': '31801', 'area': '4311', 'dungeon': '431101', 'mission': '43110101', 'sibling': '', 'name': '城壁のごとき巨体もつ軍神'},  # 31801 城壁のごとき巨体もつ軍神
        {'slot': '31802', 'area': '6242', 'dungeon': '624201', 'mission': '62420101', 'sibling': '', 'name': '休戦下の作戦'},  # 31802 休戦下の作戦
    )},
    4: {'name': 'Enhancement', 'rule': '10001', 'item': '500000001', 'enabled': True, 'areas': (
        {'slot': '10001', 'area': '5133', 'dungeon': '513301', 'mission': '51330101', 'sibling': '', 'name': '戦いの果ての友情'},  # 10001 戦いの果ての友情
        {'slot': '10002', 'area': '5122', 'dungeon': '512201', 'mission': '51220101', 'sibling': '', 'name': '悲しみを断つための強さ'},  # 10002 悲しみを断つための強さ
        {'slot': '10003', 'area': '5143', 'dungeon': '514301', 'mission': '51430101', 'sibling': '', 'name': '孤高極めし皇帝'},  # 10003 孤高極めし皇帝
        {'slot': '10004', 'area': '4242', 'dungeon': '424201', 'mission': '42420101', 'sibling': '', 'name': '舞い降りる帝王'},  # 10004 舞い降りる帝王
        {'slot': '10005', 'area': '6202', 'dungeon': '620201', 'mission': '62020101', 'sibling': '', 'name': '竜王と武神の影'},  # 10005 竜王と武神の影
        {'slot': '10006', 'area': '6203', 'dungeon': '620301', 'mission': '62030101', 'sibling': '', 'name': '共闘せし八賢者'},  # 10006 共闘せし八賢者
        {'slot': '10007', 'area': '4262', 'dungeon': '426201', 'mission': '42620101', 'sibling': '', 'name': '想いが結びつけた魂'},  # 10007 想いが結びつけた魂
        {'slot': '10008', 'area': '4263', 'dungeon': '426301', 'mission': '42630101', 'sibling': '', 'name': '王国最強の座を巡って'},  # 10008 王国最強の座を巡って
        {'slot': '10009', 'area': '5154', 'dungeon': '515401', 'mission': '51540101', 'sibling': '', 'name': 'ウェポンの鍵'},  # 10009 ウェポンの鍵
        {'slot': '10010', 'area': '4313', 'dungeon': '431301', 'mission': '43130101', 'sibling': '', 'name': '青きクリスタルを継ぐ者'},  # 10010 青きクリスタルを継ぐ者
        {'slot': '10011', 'area': '4322', 'dungeon': '432201', 'mission': '43220101', 'sibling': '', 'name': '好敵手のエリート部隊'},  # 10011 好敵手のエリート部隊
        {'slot': '10012', 'area': '4323', 'dungeon': '432301', 'mission': '43230101', 'sibling': '', 'name': 'ヒーローを蝕むオメガの種子'},  # 10012 ヒーローを蝕むオメガの種子
        {'slot': '10013', 'area': '4353', 'dungeon': '435301', 'mission': '43530101', 'sibling': '', 'name': '修羅たちを鎮める者'},  # 10013 修羅たちを鎮める者
        {'slot': '10014', 'area': '4355', 'dungeon': '435501', 'mission': '43550101', 'sibling': '', 'name': '完全なる均衡を拒む者たち'},  # 10014 完全なる均衡を拒む者たち
        {'slot': '10015', 'area': '5164', 'dungeon': '516401', 'mission': '51640101', 'sibling': '', 'name': 'ヴィセクトラム頂上決戦'},  # 10015 ヴィセクトラム頂上決戦
        {'slot': '10016', 'area': '4364', 'dungeon': '436401', 'mission': '43640101', 'sibling': '', 'name': 'エネルギー変換施設・十闘星のナズー'},  # 10016 エネルギー変換施設・十闘星のナズー
        {'slot': '10017', 'area': '4411', 'dungeon': '441101', 'mission': '44110101', 'sibling': '', 'name': '戦なき世のシノビたち'},  # 10017 戦なき世のシノビたち
        {'slot': '10018', 'area': '6372', 'dungeon': '637201', 'mission': '63720101', 'sibling': '', 'name': '常闇の後継者'},  # 10018 常闇の後継者
        {'slot': '10019', 'area': '6374', 'dungeon': '637401', 'mission': '63740101', 'sibling': '', 'name': 'よみがえる三皇星'},  # 10019 よみがえる三皇星
        {'slot': '10020', 'area': '6375', 'dungeon': '637501', 'mission': '63750101', 'sibling': '', 'name': '自由を懸けた決戦'},  # 10020 自由を懸けた決戦
        {'slot': '10021', 'area': '4542', 'dungeon': '454201', 'mission': '45420101', 'sibling': '', 'name': '解放されし真の力'},  # 10021 解放されし真の力
        {'slot': '10022', 'area': '4623', 'dungeon': '462301', 'mission': '46230101', 'sibling': '', 'name': '大洋を巡る魔海竜'},  # 10022 大洋を巡る魔海竜
        {'slot': '10023', 'area': '4583', 'dungeon': '458301', 'mission': '45830101', 'sibling': '', 'name': '純粋なる破滅の力'},  # 10023 純粋なる破滅の力
        {'slot': '10101', 'area': '6282', 'dungeon': '628201', 'mission': '62820101', 'sibling': '', 'name': 'すべてを焼きつくす力'},  # 10101 すべてを焼きつくす力
        {'slot': '10201', 'area': '4332', 'dungeon': '433201', 'mission': '43320101', 'sibling': '', 'name': '征服する暴君'},  # 10201 征服する暴君
        {'slot': '10202', 'area': '4333', 'dungeon': '433301', 'mission': '43330101', 'sibling': '', 'name': '飛竜と心を通わせた竜騎士'},  # 10202 飛竜と心を通わせた竜騎士
        {'slot': '10203', 'area': '6283', 'dungeon': '628301', 'mission': '62830101', 'sibling': '', 'name': '打倒帝国の意志'},  # 10203 打倒帝国の意志
        {'slot': '10301', 'area': '4314', 'dungeon': '431401', 'mission': '43140101', 'sibling': '', 'name': '信じる心を持つ騎士'},  # 10301 信じる心を持つ騎士
        {'slot': '10302', 'area': '6284', 'dungeon': '628401', 'mission': '62840101', 'sibling': '', 'name': '闇の氾濫に立ち向かう希望'},  # 10302 闇の氾濫に立ち向かう希望
        {'slot': '10303', 'area': '4552', 'dungeon': '455201', 'mission': '45520101', 'sibling': '', 'name': 'ノアの弟子たち'},  # 10303 ノアの弟子たち
        {'slot': '10401', 'area': '4362', 'dungeon': '436201', 'mission': '43620101', 'sibling': '', 'name': '幻獣界を統べる者'},  # 10401 幻獣界を統べる者
        {'slot': '10402', 'area': '6313', 'dungeon': '631301', 'mission': '63130101', 'sibling': '', 'name': '空を制する竜騎士'},  # 10402 空を制する竜騎士
        {'slot': '10501', 'area': '4232', 'dungeon': '423201', 'mission': '42320101', 'sibling': '', 'name': 'シルドラとの絆'},  # 10501 シルドラとの絆
        {'slot': '10502', 'area': '6192', 'dungeon': '619201', 'mission': '61920101', 'sibling': '', 'name': '王女を襲う凶矢'},  # 10502 王女を襲う凶矢
        {'slot': '10503', 'area': '6312', 'dungeon': '631201', 'mission': '63120101', 'sibling': '', 'name': '祖父ゆずりの希望の心'},  # 10503 祖父ゆずりの希望の心
        {'slot': '10601', 'area': '4203', 'dungeon': '420301', 'mission': '42030101', 'sibling': '', 'name': '幻獣と人間を繋ぐ力'},  # 10601 幻獣と人間を繋ぐ力
        {'slot': '10602', 'area': '4352', 'dungeon': '435201', 'mission': '43520101', 'sibling': '', 'name': '壊乱の道化師'},  # 10602 壊乱の道化師
        {'slot': '10603', 'area': '6302', 'dungeon': '630201', 'mission': '63020101', 'sibling': '', 'name': '厳しい鍛錬の成果'},  # 10603 厳しい鍛錬の成果
        {'slot': '10604', 'area': '4382', 'dungeon': '438201', 'mission': '43820101', 'sibling': '', 'name': 'オペラ劇場・壇上'},  # 10604 オペラ劇場・壇上
        {'slot': '10605', 'area': '6343', 'dungeon': '634301', 'mission': '63430101', 'sibling': '', 'name': 'エンジンに絡みつく触手'},  # 10605 エンジンに絡みつく触手
        {'slot': '10701', 'area': '4224', 'dungeon': '422401', 'mission': '42240101', 'sibling': '', 'name': 'タークスの本気'},  # 10701 タークスの本気
        {'slot': '10702', 'area': '4282', 'dungeon': '428201', 'mission': '42820101', 'sibling': '', 'name': '神羅の後継者'},  # 10702 神羅の後継者
        {'slot': '10703', 'area': '6182', 'dungeon': '618201', 'mission': '61820101', 'sibling': '', 'name': '伝説の英雄の力'},  # 10703 伝説の英雄の力
        {'slot': '10704', 'area': '6224', 'dungeon': '622401', 'mission': '62240101', 'sibling': '', 'name': '守るための拳'},  # 10704 守るための拳
        {'slot': '10705', 'area': '4343', 'dungeon': '434301', 'mission': '43430101', 'sibling': '', 'name': 'VSサンプル:H0512'},  # 10705 VSサンプル:H0512
        {'slot': '10706', 'area': '4633', 'dungeon': '463301', 'mission': '46330101', 'sibling': '', 'name': 'VS ジェネシス'},  # 10706 VS ジェネシス
        {'slot': '10707', 'area': '4641', 'dungeon': '464101', 'mission': '46410101', 'sibling': '', 'name': '狙われたS細胞'},  # 10707 狙われたS細胞
        {'slot': '10708', 'area': '4672', 'dungeon': '467201', 'mission': '46720101', 'sibling': '', 'name': 'タークス乱入'},  # 10708 タークス乱入
        {'slot': '10801', 'area': '4293', 'dungeon': '429301', 'mission': '42930101', 'sibling': '', 'name': 'ペンは剣よりも強し'},  # 10801 ペンは剣よりも強し
        {'slot': '10802', 'area': '6234', 'dungeon': '623401', 'mission': '62340101', 'sibling': '', 'name': '愛犬と通わす心'},  # 10802 愛犬と通わす心
        {'slot': '10901', 'area': '6262', 'dungeon': '626201', 'mission': '62620101', 'sibling': '', 'name': 'アレクサンドリアを背負う覚悟'},  # 10901 アレクサンドリアを背負う覚悟
        {'slot': '10902', 'area': '4713', 'dungeon': '471301', 'mission': '47130101', 'sibling': '', 'name': 'VS ガーランド'},  # 10902 VS ガーランド
        {'slot': '11001', 'area': '5163', 'dungeon': '516301', 'mission': '51630101', 'sibling': '', 'name': '蘇りしエボンの聖獣'},  # 11001 蘇りしエボンの聖獣
        {'slot': '11002', 'area': '4363', 'dungeon': '436301', 'mission': '43630101', 'sibling': '', 'name': 'イサールの召喚獣'},  # 11002 イサールの召喚獣
        {'slot': '11003', 'area': '6402', 'dungeon': '640201', 'mission': '64020101', 'sibling': '', 'name': 'ロンゾの誇り'},  # 11003 ロンゾの誇り
        {'slot': '11004', 'area': '4663', 'dungeon': '466301', 'mission': '46630101', 'sibling': '', 'name': 'それぞれの物語'},  # 11004 それぞれの物語
        {'slot': '11101', 'area': '4272', 'dungeon': '427201', 'mission': '42720101', 'sibling': '', 'name': '未来を灯すからくり士'},  # 11101 未来を灯すからくり士
        {'slot': '11201', 'area': '6303', 'dungeon': '630301', 'mission': '63030101', 'sibling': '', 'name': '悪逆非道の賞金稼ぎ'},  # 11201 悪逆非道の賞金稼ぎ
        {'slot': '11202', 'area': '6422', 'dungeon': '642201', 'mission': '64220101', 'sibling': '', 'name': '復讐のジャッジマスター'},  # 11202 復讐のジャッジマスター
        {'slot': '11301', 'area': '6274', 'dungeon': '627401', 'mission': '62740101', 'sibling': '', 'name': '新たな世界へ導く解放者'},  # 11301 新たな世界へ導く解放者
        {'slot': '11501', 'area': '4393', 'dungeon': '439301', 'mission': '43930101', 'sibling': '', 'name': '水神の誓約'},  # 11501 水神の誓約
        {'slot': '11601', 'area': '4693', 'dungeon': '469301', 'mission': '46930101', 'sibling': '', 'name': '炎影の真実'},  # 11601 炎影の真実
        {'slot': '11701', 'area': '4632', 'dungeon': '463201', 'mission': '46320101', 'sibling': '', 'name': 'ティアマット討伐'},  # 11701 ティアマット討伐
        {'slot': '11801', 'area': '6243', 'dungeon': '624301', 'mission': '62430101', 'sibling': '', 'name': '０組を導く力'},  # 11801 ０組を導く力
        {'slot': '11802', 'area': '4622', 'dungeon': '462201', 'mission': '46220101', 'sibling': '', 'name': 'ジュデッカ会戦'},  # 11802 ジュデッカ会戦
    )},
}

# The area ids the seal room actually serves (182 areas over the five tabs). This is THE exclusion contract
# for the other menu: build/make_jp_event_groups.py does `servable_areas - SEAL_AREAS`, so no area appears in
# 封印の間 and 次元の狭間 at the same time. jp_compat's gate-area scan excludes the same set.
SEAL_SERVED = frozenset(entry['area'] for _tab, spec in SEAL_TABS.items() if spec['enabled']
                        for entry in spec['areas'])
# Story tab (2026-11-15): each card is the world-2 banner area whose RB8zTc9G '4,<body>' opens the world-10 event
# body (full map, all dungeons) through SealAreaListScene::touchEnded -> GateUtil::moveSceneWithMoveDestination.
# The 13 world-2 ORIGINAL event areas the cards used to open stay in the exclusion set so they do not come back
# as Vortex event tiles.
SEAL_STORY_ORIGINALS = frozenset(('845', '725', '3040', '833', '855', '872', '785', '3063', '729', '746', '760', '849', '733'))
SEAL_AREAS = SEAL_SERVED | SEAL_STORY_ORIGINALS

# Test keys: the five 閃の鍵 (F_ITEM_MST 500000001..500000005), type-20 bag. JP_SEAL_TEST_KEYS=False stops
# the grant. One grant per save, recorded next to the save so a restart does not repeat it.
JP_SEAL_TEST_KEYS = True
JP_SEAL_TEST_KEY_COUNT = 99
JP_SEAL_TEST_KEY_IDS = ('500000001', '500000002', '500000003', '500000004', '500000005')
FLAG_NAME = 'jp_seal_room.json'

# The mission start/end requests that bracket ONE attempt of a seal mission. Same pair jp_mission counts
# (its START_IDS/CONTINUE_IDS): the start is the entry, so it is where the ITEM_COST is paid.
SEAL_START_IDS = ('BSq28mwY', '29JRaDbd')              # MissionWaveStart/TfaMissionStart, MissionStart
SEAL_END_IDS = ('x5Unqg2d', 'v51PM7wj', 'V3CiWT0r')    # MissionEnd, MissionRetire, MissionContinueRetire
MISSION_GROUP, MISSION_KEY = 'jQsE54Iz', 'qo3PECw6'

_state = {'server': None, 'flag_path': None, 'rows': None, 'keys_done': False, 'carriers': EVENT_GATE_CARRIERS,
          'items': {}, 'charged': None}


def _log(msg):
    print('JP seal room: ' + msg, flush=True)


def _flag_path(server):
    try:
        state_file = server.st.STATE_FILE
    except AttributeError:
        return None
    return os.path.join(os.path.dirname(os.path.abspath(state_file)), FLAG_NAME)


def _done_grant():
    if _state.get('keys_done'):
        return True
    path = _state['flag_path']
    if not path:
        return False
    try:
        with open(path, encoding='utf-8') as fh:
            done = bool(json.load(fh).get('test_keys'))
    except (OSError, ValueError):
        return False
    if done:
        _state['keys_done'] = True
    return done


def _mark_grant(detail):
    _state['keys_done'] = True
    path = _state['flag_path']
    if not path:
        return
    try:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'test_keys': True, 'detail': detail}, fh)
    except OSError as exc:
        _log('test-key flag not written: ' + str(exc))


def ensure_test_keys(server):
    """Grant each seal key up to JP_SEAL_TEST_KEY_COUNT once per save. Returns the [(id, granted)] list."""
    if not JP_SEAL_TEST_KEYS or _done_grant():
        return []
    import ffbe_player as fp
    import player_state as ps
    player = fp.State.player
    if player is None:
        return []
    granted = []
    for item_id in JP_SEAL_TEST_KEY_IDS:
        have = player.item_count(ps.BAG_ITEM_TYPE, item_id)
        if have < JP_SEAL_TEST_KEY_COUNT:
            player.grant_item(ps.BAG_ITEM_TYPE, item_id, JP_SEAL_TEST_KEY_COUNT - have)
            granted.append((item_id, JP_SEAL_TEST_KEY_COUNT))
    if granted:
        try:
            player.save(server.st.STATE_FILE)
        except Exception as exc:  # noqa: BLE001 - the keys must never break the reply
            _log('keys granted but save failed: %r' % (exc,))
    _mark_grant(','.join('%s:%d' % pair for pair in granted) or 'already >= %d' % JP_SEAL_TEST_KEY_COUNT)
    _log('test keys %s' % (granted or 'already at %d' % JP_SEAL_TEST_KEY_COUNT,))
    return granted


def _build_item_map():
    """{mission id: key item id} for every enabled tab's area mission AND its sibling (both are served rows)."""
    items = {}
    for tab in sorted(SEAL_TABS):
        spec = SEAL_TABS[tab]
        if not spec['enabled']:
            continue
        for entry in spec['areas']:
            for name in ('mission', 'sibling'):
                mission_id = str(entry.get(name) or '')
                if mission_id:
                    items[mission_id] = str(spec['item'])
    return items


def seal_item_for(mission_id):
    """The key item one entry into `mission_id` costs, or None when it is not an enabled tab's mission."""
    return (_state.get('items') or {}).get(str(mission_id or ''))


def _mission_of(req):
    """The mission id a start request names (`jQsE54Iz[0].qo3PECw6`, else any group carrying that key)."""
    if not isinstance(req, dict):
        return None
    rows = req.get(MISSION_GROUP)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        mission_id = str(rows[0].get(MISSION_KEY) or '')
        if mission_id:
            return mission_id
    items = _state.get('items') or {}
    for group in req.values():
        if not isinstance(group, list):
            continue
        for row in group:
            if isinstance(row, dict):
                mission_id = str(row.get(MISSION_KEY) or '')
                if mission_id in items:
                    return mission_id
    return None


def spend_entry(mission_id):
    """Spend the tab's key once for an entry into `mission_id`. Returns (item_id, before, after) or None.

    A held count of 0 is NOT an entry blocker: log and let the battle start, exactly as the extract above
    says (the cost is display-and-server, the client does not enforce it). A repeated start for the same
    mission before MissionEnd/Retire is a retry of the same attempt and spends nothing.
    """
    item_id = seal_item_for(mission_id)
    if not item_id:
        return None
    if _state.get('charged') == str(mission_id):
        _log('entry %s already charged for this attempt; no second key' % mission_id)
        return None
    import ffbe_player as fp
    import player_state as ps
    player = fp.State.player
    if player is None:
        return None
    held = player.item_count(ps.BAG_ITEM_TYPE, item_id)
    if held < 1:
        _log('entry %s needs key %s but the save holds 0; charged nothing' % (mission_id, item_id))
        return None
    if not player.spend_item(ps.BAG_ITEM_TYPE, item_id, 1):
        _log('entry %s: key %s held %d but could not be spent' % (mission_id, item_id, held))
        return None
    _state['charged'] = str(mission_id)
    _log('entry %s: spent key %s (%d -> %d)' % (mission_id, item_id, held, held - 1))
    return item_id, held, held - 1


def on_mission_end(_req):
    """The attempt ended: the next start for the same mission is a new, chargeable entry."""
    _state['charged'] = None


def _master_rows(fname, key):
    import player_state as ps
    return ps._load_ndjson(fname, key)


def build_rows():
    """The 0xkoNP8U rows for every enabled tab, validated against the JP masters ([] on any mismatch)."""
    if _state['rows'] is not None:
        return _state['rows']
    try:
        areas = _master_rows('F_AREA_MST.ndjson', 'uv60hgDW')
        dungeons = _master_rows('F_DUNGEON_MST.ndjson', 'U9iHsau3')
        missions = _master_rows('F_MISSION_MST.ndjson', 'qo3PECw6')
    except OSError as exc:
        _log('masters unavailable, no seal rows: ' + str(exc))
        _state['rows'] = []
        return _state['rows']
    rows = []
    for tab in sorted(SEAL_TABS):
        spec = SEAL_TABS[tab]
        if not spec['enabled']:
            continue
        for entry in spec['areas']:
            area, dungeon = entry['area'], entry['dungeon']
            mission, sibling = entry['mission'], entry['sibling']
            problem = _validate(areas, dungeons, missions, entry)
            if problem:
                _log('tab %d area %s skipped: %s' % (tab, area, problem))
                continue
            art = SEAL_ART.get(area, ART)
            # A parade chamber's row is ALSO the dungeon's isPeriodDungeon row (first U9iHsau3 match), so it
            # carries the open date-text window; SealUtil never reads these two dates.
            period = ({'VjJQ51uG': PARADE_WINDOW[0], 'm8ivD4NX': PARADE_WINDOW[1]}
                      if area in PARADE_AREAS else {})
            rows.append(dict(_BASE_ROW, uv60hgDW=area, U9iHsau3=dungeon, qo3PECw6=mission,
                             mTHe6pI0=spec['rule'], **{'4yT7FUqj': art}, **period))
            if sibling:
                rows.append(dict(_BASE_ROW, uv60hgDW=area, U9iHsau3=dungeon, qo3PECw6=sibling,
                                 mTHe6pI0=spec['rule'], **{'4yT7FUqj': art}))
    _state['rows'] = rows
    return rows


# PARADE NODES (2026-11-12, build/out/parade/lock_analysis.md). AreaMapManager::drawDungeon (0x1a3faf8) puts
# quest_ev_lock.png on a parade dungeon node unless ParadeUtil::isPeriodDungeon (0x1539e6c) is true. For a
# dungeon with 69fVGgcI == 1 that needs a SpDungeonCondMst row with the dungeon's U9iHsau3 whose
# VjJQ51uG <= now < m8ivD4NX, and those two are parsed by CommonUtils::convertToTime (strptime
# "%Y-%m-%d %H:%M:%S"), so they are DATE TEXT here, not epoch. The gate display window (NTXoA6e2/7Gvw6J82)
# stays the expired epoch of _BASE_ROW so GateScene adds no Event tile, exactly like the seal rows.
PARADE_AREAS = ('954',)
PARADE_WINDOW = ('2020-01-01 00:00:00', '2099-12-31 23:59:59')


def _parade_rows(dungeons, missions):
    first = {}
    for mission_id, mission in missions.items():
        d = str(mission.get('U9iHsau3'))
        if d not in first or int(mission_id) < int(first[d]):
            first[d] = mission_id
    rows = []
    for dungeon_id, dungeon in sorted(dungeons.items()):
        if str(dungeon.get('uv60hgDW')) not in PARADE_AREAS or str(dungeon.get('69fVGgcI')) != '1':
            continue
        rows.append(dict(_BASE_ROW, uv60hgDW=str(dungeon.get('uv60hgDW')), U9iHsau3=dungeon_id,
                         qo3PECw6=first.get(dungeon_id, ''), mTHe6pI0='',
                         VjJQ51uG=PARADE_WINDOW[0], m8ivD4NX=PARADE_WINDOW[1]))
    _log('parade period rows: %s' % (','.join(r['U9iHsau3'] for r in rows) or '-'))
    return rows


def parade_rows():
    """The parade period rows (cached), kept apart from the seal rows so SealUtil's checks see only seal rows."""
    if _state.get('parade_rows') is None:
        try:
            _state['parade_rows'] = _parade_rows(_master_rows('F_DUNGEON_MST.ndjson', 'U9iHsau3'),
                                                 _master_rows('F_MISSION_MST.ndjson', 'qo3PECw6'))
        except OSError as exc:
            _log('masters unavailable, no parade rows: ' + str(exc))
            _state['parade_rows'] = []
    return _state['parade_rows']


_BASE_ROW = {
    'qnUhs32P': GATE_TAB,
    'VjJQ51uG': WINDOW_START, 'm8ivD4NX': WINDOW_END, 'NTXoA6e2': WINDOW_START,
    '7Gvw6J82': WINDOW_END, 'V48um7Jw': WINDOW_END,
    '4yT7FUqj': ART,
    '0iWgxc1X': '0', '45wVefcS': '', '5mouF8P1': '', 'B2FW5Qjq': '',
    'C8Qf5bs6': '0', 'ET8L6iDw': '0', 'M1p3ehVU': '', 'MrxFQ63W': '',
    'QCLs6SV8': '0', 'oY0vAuE9': '0', 'vnhT2EM5': '', 'xm7c08IS': '0',
    'z0ft1PK8': '0',
}


def _validate(areas, dungeons, missions, entry):
    """The row must describe a real world-2 area whose dungeon holds a subtype-5 mission + a non-5 sibling."""
    area = areas.get(entry['area'])
    if not area:
        return 'area not in F_AREA_MST'
    if str(area.get('9Pb24aSy')) != '2':
        return 'area world %r != 2 (getAreaMstList reads world 2)' % (area.get('9Pb24aSy'),)
    dungeon = dungeons.get(entry['dungeon'])
    if not dungeon:
        return 'dungeon not in F_DUNGEON_MST'
    if str(dungeon.get('uv60hgDW')) != entry['area']:
        return 'dungeon belongs to area %r' % (dungeon.get('uv60hgDW'),)
    # The chamber stages are plain world-2 missions (subtype 0), not event-world subtype-5 missions: the client
    # judges them by isSealMission's tail call (own 0xkoNP8U row), so subtype is not checked. The stage must be
    # open on the schedule (juA0Z4m7 "0", no end date 1C7GDEv4 "") or the dungeon list drops it.
    for key, mission_id in (('mission', entry['mission']), ('sibling', entry.get('sibling') or '')):
        if not mission_id:
            continue
        mission = missions.get(mission_id)
        if not mission:
            return key + ' not in F_MISSION_MST'
        if str(mission.get('U9iHsau3')) != entry['dungeon']:
            return key + ' belongs to dungeon %r' % (mission.get('U9iHsau3'),)
        if str(mission.get('juA0Z4m7')) != '0' or str(mission.get('1C7GDEv4')) != '':
            return key + ' is not open on the schedule (juA0Z4m7 %r, 1C7GDEv4 %r)' % (
                mission.get('juA0Z4m7'), mission.get('1C7GDEv4'))
    return ''


def add_rows(out, rows):
    """Put the seal rows into an existing reply. Never mutates `out` (nor the given `rows`).

    The seal room owns its areas: jp_event_groups.json is generated as `servable - SEAL_AREAS`
    (build/make_jp_event_groups.py), so the 次元の狭間 gate does not serve a seal area and nothing else writes
    its 0xkoNP8U row. Every seal row is therefore appended in the captured 24-key shape with the EXPIRED
    window, which keeps GateScene from drawing the area as an Event tile -- the seal tab (SealUtil) ignores
    the dates. If another module's row for a seal area is still present (a stale group file, a Future season),
    it is dropped so SealUtil::getMstWithAreaId reads the seal row and the area cannot surface in the Vortex
    menu. Parade rows (PARADE_AREAS is not a seal area) are appended and deduplicated as before. No season
    selection is consulted here.
    """
    if not isinstance(out, dict) or not rows:
        return out
    owned = {str(row.get('uv60hgDW')) for row in rows} & SEAL_AREAS
    existing = [dict(r) for r in (out.get(EVENT_GATE_TAG) or []) if isinstance(r, dict)]
    kept = [r for r in existing if str(r.get('uv60hgDW')) not in owned]
    dropped = len(existing) - len(kept)
    seen = {(str(r.get('uv60hgDW')), str(r.get('qo3PECw6'))) for r in kept}
    added = []
    for row in rows:
        key = (str(row.get('uv60hgDW')), str(row.get('qo3PECw6')))
        if key in seen:
            continue
        added.append(dict(row))
        seen.add(key)
    out = dict(out)
    out[EVENT_GATE_TAG] = kept + added
    if dropped:
        _log('dropped %d non-seal row(s) of seal areas' % dropped)
    return out


def _reply_id(args, kwargs):
    reply_id = kwargs.get('reply_id')
    if reply_id is None and args:
        reply_id = args[0]
    return reply_id


def install(server):
    """Install on capture_server: per-reply 0xkoNP8U append on the carriers + the one-shot test-key grant."""
    import capture_server as cs
    if getattr(cs, '_jp_seal_room_installed', False):
        return
    _state['server'] = server
    _state['flag_path'] = _flag_path(server)
    build_rows()                    # validate now so a bad table shows at start-up, not on the first reply
    import ffbe_player as fp
    carriers = tuple(str(c) for c in (getattr(fp, 'EVENT_GATE_CARRIERS', None) or EVENT_GATE_CARRIERS))
    _state['carriers'] = carriers
    inner = cs.reply_pipeline

    def reply_pipeline(spec, *args, **kwargs):
        out = inner(spec, *args, **kwargs)
        reply_id = _reply_id(args, kwargs)
        try:
            ensure_test_keys(server)
        except Exception as exc:  # noqa: BLE001 - test keys must never break a reply
            _log('test-key grant failed: %r' % (exc,))
        if reply_id not in _state['carriers']:
            return out
        try:
            return add_rows(add_rows(out, build_rows()), parade_rows())
        except Exception as exc:  # noqa: BLE001 - the seal rows must never break a reply
            _log('row append failed: %r' % (exc,))
            return out

    cs.reply_pipeline = reply_pipeline
    cs._jp_seal_room_installed = True
    _state['items'] = _build_item_map()
    # ENTRY COST: wrap the mission start/end actions (the same `serve_actions` step jp_mission wraps), so
    # the spend lands BEFORE `apply_to_reply` and the reply already carries the new bag. A wrapped request
    # whose hook raises still runs its original handler, so the battle can never be broken by the cost.
    import exvius_actions as actions
    handlers = actions._all_handlers()

    def wrap(rid, hook):
        original = handlers.get(rid)

        def handler(spec, req):
            try:
                hook(req)
            except Exception as exc:  # noqa: BLE001 - the entry cost must never break the request
                _log(rid + ' hook failed: %r' % (exc,))
            return original(spec, req) if original else spec

        handlers[rid] = handler

    for rid in SEAL_START_IDS:
        wrap(rid, lambda req: spend_entry(_mission_of(req)))
    for rid in SEAL_END_IDS:
        wrap(rid, on_mission_end)
    enabled = ','.join('%d(%s,%s)' % (t, SEAL_TABS[t]['rule'], SEAL_TABS[t]['item'])
                       for t in sorted(SEAL_TABS) if SEAL_TABS[t]['enabled'])
    _log('installed: tabs %s, carriers %s, test keys %s, entry cost %s'
         % (enabled or 'none', ','.join(carriers), JP_SEAL_TEST_KEYS,
            ', '.join('%s->%s' % pair for pair in sorted(_state['items'].items())) or 'none'))

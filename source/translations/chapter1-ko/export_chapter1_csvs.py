"""
Export Chapter 1 (Grandshelt Isles: 111*, 112*, 113*) script-driven in-game text
into 5 purpose-separated, cleanly structured CSV spreadsheets with:
- id, category/context, japanese, english, korean
UTF-8 BOM (utf-8-sig) encoded for direct opening in Excel and Google Sheets.
"""

import os
import sys
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT / "analysis"))
sys.path.append(str(ROOT / "artifacts/chapter1-ko"))
from release_reader import Release
from ch1_monster_dict import CH1_MONSTER_TRANSLATIONS

OUT_DIR = ROOT / "artifacts/chapter1-ko/csv_exports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def clean_tags(text):
    if not text:
        return ""
    t = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return t.strip()

# -------------------------------------------------------------------------
# Spell & Ability Dictionary for Challenges
# -------------------------------------------------------------------------
SPELL_DICT = {
    'ファイア': '파이어', 'ファイラ': '파이라', 'ファイガ': '파이가',
    'ブリザド': '블리자드', 'ブリザラ': '블리자라', 'ブリザガ': '블리자가',
    'サンダー': '선더', 'サンダラ': '선더라', 'サンダガ': '선더가',
    'ウォータ': '워터', 'ウォタラ': '워터라', 'ウォタガ': '워터가',
    'ウォータ剣': '워터검', 'ファイア剣': '파이어검', 'ブリザド剣': '블리자드검', 'サンダー剣': '선더검',
    'エアロ': '에어로', 'エアロラ': '에어로라', 'エアロガ': '에어로가',
    'ストーン': '스톤', 'ストンラ': '스톤라', 'ストンガ': '스톤가',
    'ケアル': '케알', 'ケアルラ': '케알라', 'ケアルガ': '케알가',
    'プロテス': '프로테스', 'シェル': '셸', 'フェイス': '페이스', 'ブレイブ': '브레이브',
    'ポイゾナ': '포이조나', 'ブラナ': '블라인나', 'サイレナ': '사일레나', 'ストナ': '스토나',
    'エスナ': '에스나', 'ディスペル': '디스펠', 'レイズ': '레이즈', 'アレイズ': '아레이즈',
    'バファイ': '바파이', 'バファイラ': '바파이라', 'バブリザ': '바블리자', 'バブリザラ': '바블리자라',
    'バサンダ': '바선더', 'バサンダラ': '바선더라', 'バウォタ': '바워터', 'バウォタラ': '바워터라',
    'バエアロ': '바에어로', 'バエアロラ': '바에어로라', 'バストン': '바스톤', 'バストンラ': '바스톤라',
    'バイオ': '바이오', 'バイオラ': '바이오라', 'バイオブラスター': '바이오 블래스터',
    'ポーション': '포션', 'ハイポーション': '하이포션', 'エーテル': '에테르',
    'バニシュ': '바니슈', 'バニシュラ': '바니슈라', 'バニシュガ': '바니슈가',
    '明鏡': '명경', '醒夢': '성몽', 'いのり': '기도', 'たくす': '양도', 'ぬすむ': '훔치기',
    'はげます': '격려', 'まもり': '방어', '白': '백', '黒': '흑', '緑': '녹', '回復': '회복',
    'イフリート': '이프리트', 'セイレーン': '세이렌', 'ゴーレム': '골렘', 'シヴァ': '시바',
    'ラムウ': '라무', 'ディアボロス': '디아볼로스', 'カーバンクル': '카벙클', 'オーディン': '오딘',
    'タイタン': '타이탄', 'ラクシュミ': '라크슈미', 'テトラシルフィード': '테트라 실피드',
    'バハムート': '바하무트', 'フェンリル': '펜리르', '阿修羅': '아수라', 'アレキサンダー': '알렉산더',
    'フェニックス': '피닉스', 'リヴァイアサン': '리바이어선',
    'レイン': '레인', 'ラスウェル': '라스웰', 'フィーナ': '피나', 'リド': '리드'
}

ELEMENT_DICT = {
    '火': '불', '氷': '얼음', '雷': '번개', '水': '물',
    '風': '바람', '土': '땅', '光': '빛', '闇': '어둠'
}

def translate_elem(m_str):
    parts = m_str.split('・')
    ko_parts = [ELEMENT_DICT.get(p, p) for p in parts]
    return '・'.join(ko_parts)

# -------------------------------------------------------------------------
# 1. Export: chapter1_story_dialogue.csv
# -------------------------------------------------------------------------
def export_story_dialogue():
    print("=== [1/5] Exporting chapter1_story_dialogue.csv ===")
    meta_path = ROOT / "artifacts/chapter1-ko/chapter1_meta.json"
    gt_dir = ROOT / "artifacts/chapter1-ko/gt_output"
    
    with open(meta_path, "r", encoding="utf-8") as f:
        meta_list = json.load(f)
        
    gt_lookup = {}
    for jf in gt_dir.glob("*.json"):
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            gt_lookup[jf.name] = {item.get("ffbe_id"): item for item in data}

    out_file = OUT_DIR / "chapter1_story_dialogue.csv"
    count = 0
    with open(out_file, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["id", "scene_id", "cpk_name", "speaker_name", "japanese", "english", "korean", "notes"])
        
        for item in meta_list:
            ffbe_id = str(item.get("ffbe_id"))
            cpk_name = item.get("cpk_name")
            scene_id = item.get("scene_id")
            speaker_ko = item.get("speaker_ko", "")
            clean_jp = item.get("clean_jp", "").strip()
            clean_en = item.get("english_clean", "").strip()
            
            json_file = cpk_name.replace(".cpk", ".json")
            ko_text = ""
            if json_file in gt_lookup and ffbe_id in gt_lookup[json_file]:
                trans = gt_lookup[json_file][ffbe_id]
                ko_text = trans.get("message", "").strip()
            if not ko_text:
                ko_text = item.get("official_ko_clean", "").strip()
                
            writer.writerow([
                ffbe_id,
                scene_id,
                cpk_name,
                speaker_ko,
                clean_jp,
                clean_en,
                ko_text,
                "Story Event Cutscene"
            ])
            count += 1
            
    print(f"Exported {count} rows to {out_file.name}")

# -------------------------------------------------------------------------
# 2. Export: chapter1_battle_missions.csv
# -------------------------------------------------------------------------
def export_battle_missions(rel):
    print("=== [2/5] Exporting chapter1_battle_missions.csv ===")
    
    dungeons_mst = {r["U9iHsau3"]: r for r in rel.table("F_DUNGEON_MST")}
    dungeons_text = {r["key"]: r["v"][0] for r in rel.table("F_TEXT_DUNGEON_NAME", text=True)}
    
    missions_mst = {r["qo3PECw6"]: r for r in rel.table("F_MISSION_MST")}
    missions_text = {r["key"]: r["v"][0] for r in rel.table("F_TEXT_MISSION", text=True)}
    
    challenges_mst = rel.table("F_CHALLENGE_MST")
    challenges_text = {r["key"]: r["v"][0] for r in rel.table("F_TEXT_CHALLENGE_NAME", text=True)}
    
    name_dict_ko = {
        "土の神殿": "흙의 신전",
        "ラティウスの森": "라티우스 숲",
        "ミトラの町": "미트라 마을",
        "王都グランシェルト": "왕도 그란셸트",
        "ダルナキア洞窟": "달나키아 동굴",
        "ダルナキア平原": "달나키아 평원",
        "フラン街道": "프랑 가도",
        "ポート・シティ・ローディン": "항구도시 로딘",
        "港町ローディン": "항구도시 로딘",
        "オルドル港": "오르돌 항구",
        "グランシェルト城": "그란셸트 성",
        "グランシェルト地下道": "그란셸트 지하도",
        "ザデール砂漠": "자델 사막",
        "ザデール砂漠・西部": "자델 사막 서부",
        "ランゼルト山脈・上層": "란제트 산맥 상층",
        "ランゼルト山脈・下層": "란제트 산맥 하층",
        "ランゼルト河": "란제트 강",
        "ランゼルト河・上流": "란제트 강 상류",
        "ランゼルト河・下流": "란제트 강 하류",
        "ランゼルト遺跡": "란제트 유적",
        "コルの村": "콜 마을",
        "マルロの隠れ里": "마를로의 숨겨진 마을",
        "雪狼の洞窟": "설랑의 동굴",
        "コロボス岩礁": "콜로보스 암초",
        "コロボス湿地": "콜로보스 습지",
        "亡霊の府コロボス": "망령의 항구 콜로보스",
        "フェリシタスタウン": "펠리시타스 마을",
        "マダインの村": "마다인 마을",
        "ナシャル崖": "나샬 절벽",
        "飛空艇・甲板": "비공정・갑판",
        "Vault of Hidden Treasures": "숨겨진 보물고",
        "セイレーンの塔": "세이렌의 탑",
        "幻妖の試練": "환요의 시련",
        "上位探索・深淵への探求": "상위 탐색・심연으로의 탐구",
        "王都を照らす希望の光": "왕도를 비추는 희망의 빛",
        "飢えたチョコボを救え！": "굶주린 초코보를 구하라!",
        "粉骨砕身の騎士": "분골쇄신의 기사",
        "異次元からの来訪者": "이차원으로부터 온 방문자",
        "アルドールタワー天頂": "알도르 타워 천정",
        "アルドールタワー上層": "알도르 타워 상층",
        "アルドールタワー外縁部": "알도르 타워 외연부",
        "アルドールタワー": "알도르 타워",
        "孤島の森": "고도의 숲",
        "さびれた街道": "황폐한 가도",
        "港町ローディーン": "항구도시 로딘",
        "港町リディラ": "항구도시 리디라",
        "アイリーン編": "아이린 편",
        "制限区域": "제한구역",
        "中枢部": "중추부",
        "親衛隊の包囲": "친위대의 포위",
        "機動部隊の反攻": "기동부대의 반격",
        "四闘星のヒョウ": "4투성의 효",
        "ジェイクの疑問": "제이크의 의문",
        "獣潜む木立": "야수가 숨은 숲",
        "目覚めし古竜": "깨어난 고룡",
        "ジュラガのこだわり": "주라가의 집착",
        "兵のひしめく通路": "병사들이 들끓는 통로",
        "不満爆発": "불만 폭발",
        "以前の記憶": "이전의 기억",
        "長き因縁": "오랜 인연",
        "防衛網": "방어망",
        "その先にあるもの": "그 앞에 있는 것",
        "フィーナとフィーナ": "피나와 피나",
        "フィーナの成長？": "피나의 성장?",
        "二人の決意": "두 사람의 결의",
        "エリート部隊の襲撃": "엘리트 부대의 습격",
        "怪速の巨鳥": "괴속의 거조",
        "重武装の哨戒兵器": "중무장 순찰 병기",
        "唸りを上げる軍機": "포효하는 군용기",
        "悩めるマイロ": "고뇌하는 마일로",
        "憎しみに打ち勝つ者": "증오를 극복한 자",
        "北東部": "북동부",
        "南西部": "남서부",
        "北西部": "북서부",
        "南東部": "남동부",
        "ランゼルト山脈": "란제트 산맥",
        "ランゼルト雪原": "란제트 설원",
        "ランゼルト雪山": "란제트 설산",
        "コロボス廃港": "콜로보스 폐항",
        "コル荒野": "콜 황야",
        "雪狼の牙": "설랑의 송곳니",
        "水神の座": "수신의 자리",
        "水神の試練": "수신의 시련",
        "氷魔の試練": "빙마의 시련",
        "炎獣の試練": "염수의 시련",
        "狼牙の試練": "낭아의 시련",
        "賢者の試練": "현자의 시련",
        "守護神の試練": "수호신의 시련",
        "魔霊の森": "마령의 숲",
        "地下制御施設": "지하 제어 시설",
        "天頂の間": "천정의 방",
        "移送ゲート": "이송 게이트",
        "移送空間": "이송 공간",
        "ティリムの森": "티림 숲",
        "ナトゥリアの大樹": "나투리아의 거목",
        "ファルファ丘陵": "파르파 구릉",
        "ブドゥン密林地帯": "부둔 밀림 지대",
        "ヘズヌド川": "헤즈누드 강",
        "ベスタ街廃墟": "베스타 거리 폐허",
        "ペトラ幻想林": "페트라 환상림",
        "ペトラ幻想林帰路": "페트라 환상림 귀로",
        "メドス終身収容所": "메도스 종신 수용소",
        "ルタル廃坑": "루탈 폐광",
        "レキオス丘陵": "레키오스 구릉",
        "ヴラド": "블라드",
        "名もなき荒野": "이름 없는 황야",
        "咆哮の岩山": "포효의 바위산",
        "孤軍奮闘の騎士": "고군분투의 기사",
        "崩壊した駅舎": "붕괴한 역사",
        "巨木樹林帯": "거목 수림대",
        "廃線区間": "폐선 구간",
        "建設中支線": "건설 중인 지선",
        "強制労働場内部": "강제 노동장 내부",
        "強制労働場外周": "강제 노동장 외곽",
        "決戦場": "결전장",
        "炎風の洞窟": "염풍의 동굴",
        "禁断の地": "금단의 땅",
        "腐敗した神殿": "부패한 신전",
        "鉄道橋": "철도교",
        "雷鳴響く頂": "뇌명 울리는 정상",
        "高架下": "고가 아래",
        "魔瘴岩洞窟": "마장암 동굴",
        "ウク平原": "우크 평원",
        "エネルギー変換施設": "에너지 변환 시설",
        "ガガラ砂岩洞窟": "가가라 사암 동굴",
        "グランセーノ湖": "그란세노 호수",
        "グランドール": "그란돌",
        "コパン遺跡群": "코판 유적군",
        "コンビナート地区": "콤비나트 지구",
        "ゴーザス山嶺": "고자스 산령",
        "ゴーザス岸壁": "고자스 암벽",
        "ゴーザス峡谷": "고자스 협곡",
        "ザハル処刑場": "자하르 처형장",
        "ジオールバリア発生施設": "지올 배리어 발생 시설",
        "ジオール鉄道": "지올 철도",
        "ジオール駐屯地跡": "지올 주둔지 터",
        "ダナデア廃工場": "다나데아 폐공장",
        "Alexander's Test": "알렉산더의 시험",
        "Carbuncle's Test": "카벙클의 시험",
        "Diabolos's Test": "디아볼로스의 시험",
        "Fenrir's Test": "펜리르의 시험",
        "Golem's Test": "골렘의 시험",
        "Ifrit's Test": "이프리트의 시험",
        "Leviathan's Test": "리바이어선의 시험",
        "Phoenix's Test": "피닉스의 시험",
        "Ramuh's Test": "라무의 시험",
        "Shiva's Test": "시바의 시험",
        "Siren's Test": "세이렌의 시험",
        "Tetra Sylphid's Test": "테트라 실피드의 시험"
    }
    
    def translate_mission_title(jp_text, en_text):
        src = jp_text or en_text
        if not src:
            return ""
        t = src
        for k, v in name_dict_ko.items():
            t = t.replace(k, v)
        m_day = re.search(r'Day\s*(\d+)', t, re.IGNORECASE)
        if m_day and '보물고' in t:
            t = f"숨겨진 보물고 - {m_day.group(1)}일차"
        t = t.replace("・入口", "・입구").replace("・最深部", "・최심부").replace("・探索", "・탐색")
        t = t.replace("・上層", "・상층").replace("・下層", "・하층").replace("・中層", "・중층")
        t = t.replace("・最上階", "・최상층").replace("・西部", "・서부")
        t = t.replace("・東部", "・동부").replace("・南部", "・남부").replace("・北部", "・북부")
        t = t.replace("・中央", "・중앙").replace("・出口", "・출구").replace("・調達", "・조달")
        t = t.replace(" 改", " 개")
        return t

    def translate_challenge(jp_text, en_text):
        src = jp_text or en_text
        if not src:
            return ""
            
        exact_map = {
            "クエストをクリア": "퀘스트 클리어",
            "Complete the quest": "퀘스트 클리어",
            "コンティニューせずにクリア": "컨티뉴 없이 클리어",
            "No continues": "컨티뉴 없이 클리어",
            "誰も戦闘不能になることなくクリア": "아군이 쓰러지지 않고 클리어",
            "Clear without an ally being KO'd": "아군이 쓰러지지 않고 클리어",
            "アイテムを使用せずにクリア": "아이템을 사용하지 않고 클리어",
            "アイテム（鍵以外）を使用せずにクリア": "아이템(열쇠 제외)을 사용하지 않고 클리어",
            "No items": "아이템을 사용하지 않고 클리어",
            "No items (except keys)": "아이템(열쇠 제외)을 사용하지 않고 클리어",
            "魔法を使用せずにクリア": "마법을 사용하지 않고 클리어",
            "No magic": "마법을 사용하지 않고 클리어",
            "アビリティを使用せずにクリア": "어빌리티를 사용하지 않고 클리어",
            "No abilities": "어빌리티를 사용하지 않고 클리어",
            "リミットバーストを使用せずにクリア": "리미트 버스트를 사용하지 않고 클리어",
            "No limit bursts": "리미트 버스트를 사용하지 않고 클리어",
            "召喚魔法を使用してクリア": "소환마법을 사용하여 클리어",
            "幻獣を召喚してクリア": "환수를 소환하고 클리어",
            "幻獣を召喚せずにクリア": "환수를 소환하지 않고 클리어",
            "No espers": "환수를 소환하지 않고 클리어",
            "バトルで逃げずにクリア": "전투에서 도망치지 않고 클리어",
            "No escapes": "전투에서 도망치지 않고 클리어",
            "「白」「黒」魔法を使用してクリア": "「백」「흑」마법을 사용하여 클리어",
            "「白」魔法を使用してクリア": "「백」마법을 사용하여 클리어",
            "「白」魔法を使用せずにクリア": "「백」마법을 사용하지 않고 클리어",
            "「黒」魔法を使用してクリア": "「흑」마법을 사용하여 클리어",
            "「黒」魔法を使用せずにクリア": "「흑」마법을 사용하지 않고 클리어",
            "「緑」魔法を使用してクリア": "「녹」마법을 사용하여 클리어",
            "「緑」魔法を使用せずにクリア": "「녹」마법을 사용하지 않고 클리어",
            "「回復」魔法を使用せずにクリア": "「회복」마법을 사용하지 않고 클리어",
            "「たくす」を使用してクリア": "「양도」를 사용하여 클리어",
            "「ぬすむ」を使用してクリア": "「훔치기」를 사용하여 클리어",
            "「はげます」を使用してクリア": "「격려」를 사용하여 클리어",
            "「まもり」を使用してクリア": "「방어」를 사용하여 클리어",
            "「いのり」を使用してクリア": "「기도」를 사용하여 클리어"
        }
        if src in exact_map:
            return exact_map[src]
        if en_text in exact_map:
            return exact_map[en_text]

        # Multi-element and element patterns
        m = re.match(r'(.+?)属性で各(\d+)回以上敵にダメージを与える', src)
        if m:
            elem = translate_elem(m.group(1))
            return f"{elem} 속성으로 각 {m.group(2)}회 이상 대미지 주기"
        m = re.match(r'(.+?)属性で(\d+)回以上敵にダメージを与える', src)
        if m:
            elem = translate_elem(m.group(1))
            return f"{elem} 속성으로 적에게 {m.group(2)}회 이상 대미지 주기"
        m = re.match(r'(.+?)属性で敵にダメージを与える', src)
        if m:
            elem = translate_elem(m.group(1))
            return f"{elem} 속성으로 적에게 대미지 주기"
        m = re.match(r'(.+?)属性でダメージを与える', src)
        if m:
            elem = translate_elem(m.group(1))
            return f"{elem} 속성으로 대미지 주기"

        # Espers
        m = re.match(r'幻獣を(\d+)回以上召喚してクリア', src)
        if m:
            return f"환수를 {m.group(1)}회 이상 소환하고 클리어"
        m = re.match(r'(.+?)を召喚してクリア', src)
        if m:
            esp = m.group(1).strip('「」')
            esp_ko = SPELL_DICT.get(esp, esp)
            return f"「{esp_ko}」을(를) 소환하고 클리어"

        # Party composition
        m = re.match(r'(.+?)をパーティに編成（同行者含む）', src)
        if m:
            pname = m.group(1).strip('「」')
            pname_ko = SPELL_DICT.get(pname, pname)
            return f"{pname_ko} 파티에 편성 (동행자 포함)"

        m = re.match(r'パーティ人数(\d+)人以上（同行者含む）', src)
        if m:
            return f"파티 인원 {m.group(1)}명 이상 (동행자 포함)"
        m = re.match(r'パーティ人数(\d+)人以下（同行者含む）', src)
        if m:
            return f"파티 인원 {m.group(1)}명 이하 (동행자 포함)"
        m = re.match(r'(\d+)ターン以内でクリア', src)
        if m:
            return f"{m.group(1)}턴 이내로 클리어"
        m = re.match(r'(\d+)ターン以上でクリア', src)
        if m:
            return f"{m.group(1)}턴 이상으로 클리어"
        m = re.match(r'1ターンに(\d+)CHAIN以上してクリア', src)
        if m:
            return f"1턴에 {m.group(1)}체인 이상 달성하고 클리어"
        m = re.match(r'ELEMENT CHAINを1ターンに(\d+)回以上発生させる', src)
        if m:
            return f"엘리먼트 체인을 1턴에 {m.group(1)}회 이상 발생"
            
        m = re.match(r'「(.+?)」を使用してクリア', src)
        if m:
            tgt = m.group(1)
            tgt_ko = SPELL_DICT.get(tgt, CH1_MONSTER_TRANSLATIONS.get(tgt, tgt))
            return f"「{tgt_ko}」을(를) 사용하여 클리어"

        m = re.match(r'「(.+?)」を使用せずにクリア', src)
        if m:
            tgt = m.group(1)
            tgt_ko = SPELL_DICT.get(tgt, CH1_MONSTER_TRANSLATIONS.get(tgt, tgt))
            return f"「{tgt_ko}」을(를) 사용하지 않고 클리어"

        m = re.match(r'「(.+?)」を幻獣(.+?)でフィニッシュ', src)
        if m:
            tgt, esp = m.group(1), m.group(2)
            tgt_ko = CH1_MONSTER_TRANSLATIONS.get(tgt, tgt)
            esp_ko = SPELL_DICT.get(esp, esp)
            return f"「{tgt_ko}」을(를) 환수 {esp_ko}(으)로 피니시"

        m = re.match(r'「(.+?)」を幻獣でフィニッシュ', src)
        if m:
            tgt = m.group(1)
            tgt_ko = CH1_MONSTER_TRANSLATIONS.get(tgt, tgt)
            return f"「{tgt_ko}」을(를) 환수로 피니시"

        m = re.match(r'「(.+?)」をＬＢでフィニッシュ', src)
        if m:
            tgt = m.group(1)
            tgt_ko = CH1_MONSTER_TRANSLATIONS.get(tgt, tgt)
            return f"「{tgt_ko}」을(를) LB로 피니시"

        m = re.match(r'「(.+?)」を魔法でフィニッシュ', src)
        if m:
            tgt = m.group(1)
            tgt_ko = CH1_MONSTER_TRANSLATIONS.get(tgt, tgt)
            return f"「{tgt_ko}」을(를) 마법으로 피니시"

        m = re.match(r'「(.+?)」戦を(\d+)ターン以内でクリア', src)
        if m:
            tgt = m.group(1)
            tgt_ko = CH1_MONSTER_TRANSLATIONS.get(tgt, tgt)
            turns = m.group(2)
            return f"「{tgt_ko}」전을 {turns}턴 이내로 클리어"

        # English-based fallbacks
        if en_text:
            m_en = re.match(r'Defeat (.+?) with a limit burst', en_text, re.IGNORECASE)
            if m_en:
                return f"「{m_en.group(1)}」을(를) LB로 피니시"
            m_en = re.match(r'Defeat (.+?) with magic', en_text, re.IGNORECASE)
            if m_en:
                return f"「{m_en.group(1)}」을(를) 마법으로 피니시"
            m_en = re.match(r'Defeat (.+?) with an esper', en_text, re.IGNORECASE)
            if m_en:
                return f"「{m_en.group(1)}」을(를) 환수로 피니시"
            m_en = re.match(r'Evoke (.+)', en_text, re.IGNORECASE)
            if m_en:
                esp_name = m_en.group(1).strip()
                return f"「{esp_name}」을(를) 소환하고 클리어"
            m_en = re.match(r'Use (.+)', en_text, re.IGNORECASE)
            if m_en:
                return f"「{m_en.group(1)}」을(를) 사용하여 클리어"
            m_en = re.match(r'Deal (.+?) damage (\d+) times or more to an enemy', en_text, re.IGNORECASE)
            if m_en:
                return f"{m_en.group(1)} 속성으로 적에게 {m_en.group(2)}회 이상 대미지 주기"
            m_en = re.match(r'Deal (.+?) damage to an enemy', en_text, re.IGNORECASE)
            if m_en:
                return f"{m_en.group(1)} 속성으로 적에게 대미지 주기"
                
        return en_text if en_text else src

    out_file = OUT_DIR / "chapter1_battle_missions.csv"
    count = 0
    with open(out_file, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["id", "mission_id", "dungeon_id", "category", "type", "japanese", "english", "korean"])
        
        ch1_mission_ids = set()
        for mid, mrow in sorted(missions_mst.items()):
            if mid.startswith(("111", "112", "113")):
                ch1_mission_ids.add(mid)
                did = mrow.get("U9iHsau3", "")
                d_jp = dungeons_mst.get(did, {}).get("G4L0YIB2", "")
                d_en = dungeons_text.get("MST_DUNGEONS_NAME_" + did, d_jp)
                d_ko = translate_mission_title(d_jp, d_en)
                
                m_jp = mrow.get("G4L0YIB2", "")
                m_en = missions_text.get("MST_MISSION_NAME_" + mid, m_jp)
                m_ko = translate_mission_title(m_jp, m_en)
                
                category = f"Grandshelt Isles / {d_ko}"
                writer.writerow([
                    mid,
                    mid,
                    did,
                    category,
                    "Mission Stage",
                    m_jp,
                    m_en,
                    m_ko
                ])
                count += 1
                
        for crow in challenges_mst:
            mid = crow.get("qo3PECw6", "")
            if mid in ch1_mission_ids:
                cid = crow.get("V36ygRYs", "")
                c_jp = crow.get("G4L0YIB2", "")
                c_en = challenges_text.get("MST_CHALLENGE_NAME_" + cid, "")
                c_ko = translate_challenge(c_jp, c_en)
                stage_name = crow.get("6uvHX2JG", "")
                
                writer.writerow([
                    cid,
                    mid,
                    "",
                    f"Stage Challenge ({stage_name})",
                    "Challenge Objective",
                    c_jp,
                    c_en,
                    c_ko
                ])
                count += 1

    print(f"Exported {count} rows to {out_file.name}")

# -------------------------------------------------------------------------
# 3. Export: chapter1_monsters.csv
# -------------------------------------------------------------------------
def export_monsters(rel):
    print("=== [3/5] Exporting chapter1_monsters.csv ===")
    
    with open(ROOT / "upstream/source/server/content/battle/F_MISSION_MST.tsv", "r", encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        ch1_missions = set(row[0] for row in r if row[0].startswith(("111", "112", "113")))

    bg_ids = set()
    with open(ROOT / "upstream/source/server/content/battle/F_MISSION_PHASE_MST.tsv", "r", encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        for row in r:
            if row[0] in ch1_missions:
                bg_ids.add(row[8])

    monster_ids = set()
    with open(ROOT / "upstream/source/server/content/battle/F_BATTLE_GROUP_MST.tsv", "r", encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        for row in r:
            if row[0] in bg_ids:
                monster_ids.add(row[1])

    with open(ROOT / "upstream/source/server/content/battle/F_MONSTER_MST.tsv", "r", encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        m_mst = {row[0]: row for row in r}

    text_mon = {r["key"]: r["v"][0] for r in rel.table("F_TEXT_MONSTER_NAME", text=True)}

    def translate_monster(jp_name, en_name):
        if jp_name in CH1_MONSTER_TRANSLATIONS:
            return CH1_MONSTER_TRANSLATIONS[jp_name]
        for k, v in CH1_MONSTER_TRANSLATIONS.items():
            if k in jp_name:
                return jp_name.replace(k, v)
        return en_name if en_name else jp_name

    out_file = OUT_DIR / "chapter1_monsters.csv"
    count = 0
    with open(out_file, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["id", "monster_id", "base_id", "area", "japanese", "english", "korean"])
        
        for mid in sorted(monster_ids):
            row = m_mst.get(mid, [mid, mid, mid])
            m_jp = row[1] if len(row) > 1 else mid
            base_id = row[2] if len(row) > 2 else ""
            m_en = text_mon.get("MST_MONSTER_NAME_" + mid, m_jp)
            m_ko = translate_monster(m_jp, m_en)
            
            area = "Grandshelt Isles (Chapter 1)"
            writer.writerow([
                mid,
                mid,
                base_id,
                area,
                m_jp,
                m_en,
                m_ko
            ])
            count += 1
            
    print(f"Exported {count} rows to {out_file.name}")

# -------------------------------------------------------------------------
# 4. Export: chapter1_battle_skills.csv
# -------------------------------------------------------------------------
def export_battle_skills(rel):
    print("=== [4/5] Exporting chapter1_battle_skills.csv ===")
    
    with open(ROOT / "upstream/source/server/content/battle_skill_translations.json", "r", encoding="utf-8") as f:
        notices = json.load(f)["names"]
        
    with open(ROOT / "upstream/source/server/content/battle/F_MONSTER_SKILL_MST.tsv", "r", encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        skills_mst = {row[0]: row[1] for row in r}

    skill_dict_ko = {
        "Fire": "파이어",
        "Blizzard": "블리자드",
        "Thunder": "선더",
        "Water": "워터",
        "Aero": "에어로",
        "Stone": "스톤",
        "Fira": "파이라",
        "Blizzara": "블리자라",
        "Thundara": "선더라",
        "Watera": "워터라",
        "Aerora": "에어로라",
        "Stonra": "스톤라",
        "Firaga": "파이가",
        "Blizzaga": "블리자가",
        "Thundaga": "선더가",
        "Waterga": "워터가",
        "Cure": "케알",
        "Cura": "케알라",
        "Curaga": "케알가",
        "Curaja": "케알쟈",
        "Esuna": "에스나",
        "Dispel": "디스펠",
        "Raise": "레이즈",
        "Arise": "아레이즈",
        "Protect": "프로테스",
        "Shell": "셸",
        "Faith": "페이스",
        "Bravery": "브레이브",
        "Silence": "사일레스",
        "Sleep": "슬리플",
        "Blind": "블라인드",
        "Poison": "포이즌",
        "Bio": "바이오",
        "Biora": "바이오라",
        "Gravity": "그라비데",
        "Graviga": "그라비가",
        "Death": "데스",
        "Meteor": "메테오",
        "Flare": "플레어",
        "Holy": "홀리",
        "Drain": "드레인",
        "Osmose": "아스필",
        "Bite": "물어뜯기",
        "Bloodfeast": "흡혈",
        "Charge": "돌진",
        "Self-Destruct": "자폭",
        "Goblin Punch": "고블린 펀치",
        "Aqua Breath": "아쿠아 브레스",
        "Flash": "플래시",
        "Double Sweep": "2연속 휘두르기",
        "Incinerate": "모두 태우기",
        "Atomic Flare": "아토믹 플레어",
        "Zombie Powder": "좀비 파우더",
        "Dark Touch": "다크 터치",
        "Thunder Blow": "선더 블로우",
        "Stun Blow": "스턴 블로우",
        "Storm Slash": "스톰 슬래시",
        "Mighty Guard": "마이티 가드",
        "Tentacle Sweep": "촉수 휘두르기",
        "Dark Aura": "어둠의 오라",
        "Shadow Ball": "섀도 볼",
        "Curse of Darkness": "어둠의 저주",
        "Rime Strike": "무빙격",
        "Pounce": "덮치기",
        "Mocking Laughter": "비웃음",
        "Rampage": "날뛰기",
        "Scratch": "할퀴기",
        "Roar": "포효"
    }

    def translate_notice(jp_text, en_text):
        if "パーティにゾンビ状態を付与" in jp_text:
            return "파티에 좀비 상태를 부여!"
        if "パーティにリジェネを付与" in jp_text:
            return "파티에 리젠을 부여!"
        if "強化効果を解除" in jp_text:
            return "일부 강화 효과를 해제!"
        if "弱体効果を解除" in jp_text:
            return "일부 약체 효과를 해제!"
        if "カウンターを準備" in jp_text:
            return "물리・마법 공격 카운터 준비!"
        if "気力を奪った" in jp_text or "MP was drained" in en_text:
            return "파티의 기력을 대량으로 흡수했다!"
        if "かばう、ひきつけ不可" in jp_text or "ignores cover" in en_text:
            return "감싸기 및 도발 불가 공격!"
        if "かばう不可" in jp_text:
            return "감싸기 불가 공격!"
        if "状態異常 病気になった" in jp_text:
            return "적에게 질병 상태이상 부여!"
        if "病気で1ターン動けない" in jp_text:
            return "적은 질병으로 1턴 동안 행동 불가!"
        if "上空へ舞い上がった" in jp_text:
            return "상공으로 날아올랐다!"
        if "耐性がダウン" in jp_text:
            return "파티의 속성 저항력이 감소!"
        if "解除不能" in jp_text:
            return "적의 물리 명중률 증가. 해제 불가!"
        if "魔力供給が絶たれた" in jp_text:
            return "마력 공급이 끊어졌다!"
        if "ガ達が蘇る" in jp_text:
            return "가고일들이 되살아난다……!"
            
        for k, v in skill_dict_ko.items():
            if k in en_text:
                return v
        return en_text

    out_file = OUT_DIR / "chapter1_battle_skills.csv"
    count = 0
    with open(out_file, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["id", "category", "japanese", "english", "korean"])
        
        for i, (jp, en) in enumerate(sorted(notices.items()), 1):
            sid = f"NOTICE_{i:04d}"
            ko = translate_notice(jp, en)
            writer.writerow([
                sid,
                "Battle Announcement / Gimmick Notice",
                jp,
                en,
                ko
            ])
            count += 1
            
        for sid, sname in sorted(skills_mst.items()):
            if int(sid) < 300000:
                ko = skill_dict_ko.get(sname, sname)
                writer.writerow([
                    f"SKILL_{sid}",
                    "Monster Combat Skill",
                    sname,
                    sname,
                    ko
                ])
                count += 1

    print(f"Exported {count} rows to {out_file.name}")

# -------------------------------------------------------------------------
# 5. Export: chapter1_town_npcs_and_shops.csv
# -------------------------------------------------------------------------
def export_town_npcs_and_shops(rel):
    print("=== [5/5] Exporting chapter1_town_npcs_and_shops.csv ===")
    
    town_stores = {r["key"]: r["v"][0] for r in rel.table("F_TEXT_TOWN_STORE", text=True)}
    comments = {r["key"]: r["v"][0] for r in rel.table("F_TEXT_TOWN_STORE_COMMENT", text=True)}
    
    with open(ROOT / "upstream/source/server/content/dialogue_en.json", "r", encoding="utf-8") as f:
        dialogue = json.load(f).get("translations", {})
        
    town_dict_ko = {
        "1101": ("미트라 마을", "Town of Mitra", "ミトラの町"),
        "1102": ("왕도 그란셸트", "Royal Capital Grandshelt", "王都グランシェルト"),
        "1103": ("항구도시 로딘", "Port City Lodin", "港町ローディン"),
        "1104": ("오르돌 항구", "Ordol Port", "オルドル港"),
        "1201": ("항구도시 리디라", "Port City Lydira", "港町リディラ"),
        "1202": ("콜 마을", "Village of Kol", "コルの村"),
        "1203": ("그랜드포트", "Grandport", "グランドポート"),
        "1204": ("마를로의 숨겨진 마을", "Lost Village of Marlo", "マルロの隠れ里"),
        "1301": ("망령의 항구 콜로보스", "Ghost Port Kolobos", "亡霊の府コロボス"),
        "1302": ("펠리시타스 마을", "Felicitas Town", "フェリシタスタウン")
    }

    store_type_ko = {
        "Tool Shop": "도구점",
        "Weaponsmith": "무기점",
        "Armorer": "방어구점",
        "Ability Shop": "어빌리티점",
        "Forge": "대장간",
        "Abilities": "어빌리티 상점",
        "Synthesis": "합성소",
        "Gunsmith": "총기점"
    }

    shop_comment_map = {
        "A pleasure!": ("감사합니다!", "毎度あり！"),
        "Ah! A customer!": ("아! 손님이시군요!", "おや！お客さんかい！"),
        "All set, are you?": ("준비는 다 되셨나요?", "準備はいいかい？"),
        "Always appreciated!": ("언제나 감사드립니다!", "いつもありがとう！"),
        "Best weapons in town!": ("마을 최고의 무기들입니다!", "町で一番の武器だよ！"),
        "Come again soon!": ("곧 또 들러주세요!", "また来てね！"),
        "Come back anytime!": ("언제든 또 들러주세요!", "いつでもまた来てくれよ！"),
        "Come back anytime.": ("언제든 또 들러주세요.", "いつでもまた来てくれよ。"),
        "Come back soon, you hear?": ("얼른 또 와야 해, 알겠지?", "またすぐおいで！"),
        "Come on in!": ("어서 들어오세요!", "いらっしゃい！"),
        "Don't be a stranger!": ("자주 찾아주세요!", "また寄ってくれよな！"),
        "Don't be a stranger, eh?": ("자주 찾아주게, 알겠나?", "また寄ってくれよな！"),
        "Don't be a stranger, okay?": ("자주 찾아와 줘, 응?", "また寄ってね！"),
        "Got somethin' good?": ("좋은 물건이라도 가져오셨나요?", "何かいい物でも仕入れたかい？"),
        "Got somethin', do ye?": ("좋은 물건이라도 있으신가요?", "何かいい物でもあるかい？"),
        "Got something to sell?": ("팔 물건이라도 있으신가요?", "何か売る物はあるかい？"),
        "Happy to be of service!": ("도움이 되어 기쁩니다!", "お役に立てて光栄です！"),
        "Heh heh, something you're lookin' for?": ("헤헤, 찾으시는 물건이라도 있으신가요?", "へへっ、探し物かい？"),
        "I'll take that off your hands.": ("그 물건은 제가 사들이겠습니다.", "そいつを買い取らせてもらうよ。"),
        "Let's see what you have.": ("어떤 물건을 가지고 계신지 한번 볼까요.", "何を持ってるか見せておくれ。"),
        "Make yourself comfortable!": ("편하게 둘러보세요!", "ごゆっくりどうぞ！"),
        "Never hurts to get stronger, eh?": ("강해져서 손해 볼 건 없지, 안 그래?", "強くなって損はないからな！"),
        "Pleasure doing business!": ("거래해 주셔서 감사합니다!", "毎度どうも！"),
        "Pleasure's mine!": ("제가 더 기쁩니다!", "こちらこそありがとう！"),
        "Sell me anything!": ("무엇이든 사들입니다!", "何でも買い取るよ！"),
        "Show me what you've got.": ("가지고 계신 걸 보여주세요.", "何を持ってるか見せてくれ。"),
        "Trade star quartz for an item?": ("스타 쿼츠를 아이템과 교환하시겠습니까?", "スタークォーツとアイテムを交換するかい？"),
        "Until next time!": ("다음에 또 뵙겠습니다!", "また次回に！"),
        "Welcome to the vaults.": ("보물고에 오신 것을 환영합니다.", "宝物庫へようこそ。"),
        "Welcome!": ("어서 오세요!", "いらっしゃい！"),
        "Welcome!<br>What might you be after?": ("어서 오세요! 어떤 물건을 찾으시나요?", "いらっしゃい！何をお求めかい？"),
        "Whaddaya got?": ("뭘 가져왔어?", "何を持ってきたんだい？"),
        "What are you lookin' to sell?": ("어떤 물건을 파시겠어요?", "何を売りたいんだい？"),
        "What can I do ye for?": ("무엇을 도와드릴까요?", "何をご用かい？"),
        "What can I take off your hands?": ("어떤 물건을 사드릴까요?", "何を買い取ろうかい？"),
        "What do ye have for me?": ("어떤 물건을 파시겠어요?", "何か持ってきたかい？"),
        "What do you have for me?": ("어떤 물건을 파시겠어요?", "何か持ってきたかい？"),
        "What'll you be needing?": ("무엇이 필요하신가요?", "何が必要なんだい？"),
        "Which strongbox will you open?": ("어느 보물함을 여시겠습니까?", "どの宝箱を開けるかい？")
    }

    out_file = OUT_DIR / "chapter1_town_npcs_and_shops.csv"
    count = 0
    with open(out_file, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["id", "town_id", "category", "japanese", "english", "korean"])
        
        for tid, (ko, en, jp) in sorted(town_dict_ko.items()):
            writer.writerow([
                f"TOWN_{tid}",
                tid,
                "Town Name",
                jp,
                en,
                ko
            ])
            count += 1
            
        for key, en_val in sorted(town_stores.items()):
            tid = key.replace("MST_TOWNSTORE_NAME_", "")[:4]
            if tid in town_dict_ko:
                ko_val = store_type_ko.get(en_val, en_val)
                town_ko = town_dict_ko[tid][0]
                writer.writerow([
                    key,
                    tid,
                    f"{town_ko} Store Name",
                    en_val,
                    en_val,
                    ko_val
                ])
                count += 1

        for key, en_val in sorted(comments.items()):
            tid = key.replace("MST_TOWNSTORE_COMMENT_", "")[:4]
            if tid in town_dict_ko:
                ko_val, jp_val = shop_comment_map.get(en_val, (en_val, en_val))
                town_ko = town_dict_ko[tid][0]
                writer.writerow([
                    key,
                    tid,
                    f"{town_ko} Shopkeeper Dialogue",
                    jp_val,
                    en_val,
                    ko_val
                ])
                count += 1

        for k, v in dialogue.items():
            sc = v.get("scene") or ""
            ref = v.get("reference") or ""
            if any(re.search(r"11[1-3]02\d+", str(x)) for x in [sc, ref]):
                src = v.get("source", "")
                eng = v.get("english", "")
                row_id = v.get("id", k[:10])
                
                jp_clean = clean_tags(src)
                en_clean = clean_tags(eng)
                
                ko_clean = en_clean
                if "目薬" in src or "eye drops" in eng:
                    ko_clean = "안약을 건네시겠습니까?\n여행자님, 혹시 안약 가지고 계신가요? 도구점에서 구할 수 있을 텐데, 가져와 주시면 하이포션으로 교환해 드릴게요."
                elif "ヒミツの本" in src or "secret book" in eng.lower():
                    ko_clean = "그란셸트의 기사라고 들어서 부탁이 있는데……\n흙의 신전에 떨어진 책을 하나 찾아와 줬으면 해.\n무슨 책이냐고? 그건…… 비밀의 책이야!\n부탁해! 절대 안을 들여다보지는 말고!"
                elif "王都グランシェルト" in src:
                    ko_clean = en_clean.replace("Royal Capital Grandshelt", "왕도 그란셸트")
                
                writer.writerow([
                    f"NPC_{row_id}",
                    sc[:4] if sc else "TOWN",
                    f"Town NPC Dialogue ({sc})",
                    jp_clean,
                    en_clean,
                    ko_clean
                ])
                count += 1

    print(f"Exported {count} rows to {out_file.name}")

# -------------------------------------------------------------------------
# Main runner
# -------------------------------------------------------------------------
def main():
    print("Loading release assets...")
    rel = Release(ROOT / "downloads/release-2026.11.04.9")
    
    export_story_dialogue()
    export_battle_missions(rel)
    export_monsters(rel)
    export_battle_skills(rel)
    export_town_npcs_and_shops(rel)
    
    rel.close()
    print("\n[SUCCESS] All 5 Chapter 1 CSV files successfully exported to:")
    print(str(OUT_DIR))

if __name__ == "__main__":
    main()

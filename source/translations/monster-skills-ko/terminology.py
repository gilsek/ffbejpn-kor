"""파판 기본 마법의 영문 대응어를 프로젝트의 기존 일본어→한국어 명칭에 연결한다."""
import monster_common as C

ALIASES={
    'Fire':'ファイア','Fira':'ファイラ','Firaga':'ファイガ','Firaja':'ファイジャ',
    'Blizzard':'ブリザド','Blizzara':'ブリザラ','Blizzaga':'ブリザガ','Blizzaja':'ブリザジャ',
    'Thunder':'サンダー','Thundara':'サンダラ','Thundaga':'サンダガ','Thundaja':'サンダジャ',
    'Water':'ウォータ','Watera':'ウォタラ','Waterga':'ウォタガ','Waterja':'ウォタジャ',
    'Aero':'エアロ','Aerora':'エアロラ','Aeroga':'エアロガ','Aeroja':'エアロジャ',
    'Stone':'ストーン','Stonra':'ストンラ','Stonga':'ストンガ','Stonja':'ストンジャ',
    'Cure':'ケアル','Cura':'ケアルラ','Curaga':'ケアルガ','Curaja':'ケアルジャ',
    'Protect':'プロテス','Shell':'シェル','Faith':'フェイス','Brave':'ブレイブ',
    'Poisona':'ポイゾナ','Blindna':'ブラナ','Silena':'サイレナ','Stona':'ストナ',
    'Esuna':'エスナ','Dispel':'ディスペル','Dispelga':'デスペガ','Raise':'レイズ','Arise':'アレイズ',
    'Bio':'バイオ','Biora':'バイオラ','Bioga':'バイオガ','Bio Blaster':'バイオブラスター',
    'Banish':'バニシュ','Banishra':'バニシュラ','Banishga':'バニシュガ',
    'Ultima':'アルテマ','Flare':'フレア','Holy':'ホーリー','Meteor':'メテオ',
    'Quake':'クエイク','Tornado':'トルネド','Reflect':'リフレク','Drain':'ドレイン',
    'Osmose':'アスピル','Death':'デス','Stop':'ストップ','Haste':'ヘイスト',
    'Slow':'スロウ','Regen':'リジェネ',
}

def canonical_terms():
    # 이름 표기 근거는 기존 공식 명칭 표시가 있는 용어집을 우선하고,
    # 그 밖에는 검수·게시된 아군 기술 번역의 정확한 일본어 원문을 이용한다.
    root=C.ROOT/'translations/skills-ko'
    manifest=C.read(root/'manifest.json');translated=C.read(root/'translated.json')
    known={v['source']:(translated[v['ffbe_id']],'게시된 아군 기술 번역') for v in manifest['records']}
    path=C.ROOT/'translations/chapter1-ko/Dict/gpt_dict.txt'
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        fields=line.split('\t')
        if len(fields)>=3 and '공식 한글판 명칭' in fields[2]:
            # 기존 용어집 원문 키에 한글 '레'가 섞인 오타만 대응시킨다. 원본은 보존한다.
            japanese='サイレナ' if fields[0]=='サイ레ナ' else fields[0]
            known[japanese]=(fields[1],'기존 프로젝트 용어집의 공식 명칭 표기')
    result={}
    for english,japanese in ALIASES.items():
        assert japanese in known,(english,japanese,'기존 한국어 표기 근거 없음')
        korean,origin=known[japanese]
        assert C.N.HANGUL.search(korean) and not C.JP.search(korean)
        result[english]={'japanese':japanese,'translation':korean,'origin':origin}
    return result

def normalize_families(source,text):
    import re
    # 영어 고유 마법명이 실제 원문에 있을 때만 표기 차이를 바로잡는다.
    # Fire/Death 같은 일반 단어의 합성 기술명을 무조건 마법명으로 바꾸지 않는다.
    if re.search(r'\bBanish(?:ra|ga)?\b',source,re.I):
        text=text.replace('배니시','바니슈').replace('바니시','바니슈')
    if re.search(r'\bUltima\b',source,re.I):
        for variant in ('얼티마','울티마','알티마'):text=text.replace(variant,'알테마')
    return text

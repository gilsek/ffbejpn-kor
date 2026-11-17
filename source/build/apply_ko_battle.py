"""기존 번역만 JP 전투 대사 마스터와 전투 응답 이름에 연결한다.

python -I -X utf8 build/apply_ko_battle.py
명령 번호/인자/구분자는 보존하고, 정확히 일치하는 번역만 사용한다.
"""
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'build'))
import name_coverage as NC
from apply_ko_names import safe
from apply_ko_story import load_translations
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16
import ko_line_fit as LF

TOKEN, KEY = 'i7STtbw8', 'o28ckLUb'
FIELD = 'c1GnEF38'
OUT = ROOT / 'build/out/ko_battle'


def normalize(text):
    return re.sub(r'<br\s*/?>', '\n', text.replace('\r', ''), flags=re.I).strip()


def split_chunk(chunk):
    """대사 조각을 (액터, 화자, 본문, 꼬리)로 나눈다. 대사 형식이 아니면 None.

    3필드(액터,화자,본문)와 본문 뒤에 숫자/빈 플래그가 붙은 4필드 이상
    (액터,화자,본문,1 / 액터,화자,본문,)을 다룬다. 본문 자체에 ASCII 쉼표가 있는
    조각은 번역문으로 바꾸면 명령 인자 수가 달라지므로 손대지 않는다.
    """
    parts = chunk.split(',')
    if len(parts) < 3 or not parts[0].isdigit():
        return None
    if len(parts) >= 4 and (parts[-1].isdigit() or parts[-1] == ''):
        body, tail = ','.join(parts[2:-1]), parts[-1]
    else:
        body, tail = ','.join(parts[2:]), None
    if ',' in body:
        return None
    return parts[0], parts[1], body, tail


def join_chunk(actor, speaker, body, tail=None):
    """split_chunk이 돌려준 꼬리 플래그를 원래 모양 그대로 다시 붙인다."""
    if tail is None:
        return ','.join((actor, speaker, body))
    return ','.join((actor, speaker, body, tail))


def wire(text):
    # ASCII comma/colon are battle-command delimiters, not printable punctuation.
    return safe(text).replace(',', '‚').replace(':', '：').replace('\r', '').replace('\n', '<br>')


def translations(include_battle=True):
    candidates = defaultdict(set)
    exported = {}
    def add(jp, ko):
        if jp and ko and NC.HANGUL.search(ko) and not NC.LEFT_JP.search(ko):
            candidates[normalize(jp)].add(wire(ko))
    for f in sorted((ROOT / 'translations/chapter1-ko/csv_exports').glob('*story_dialogue.csv')):
        for row in csv.DictReader(f.open(encoding='utf-8-sig')):
            add(row.get('japanese'), row.get('korean'))
            if row.get('korean') and NC.HANGUL.search(row['korean']) and not NC.LEFT_JP.search(row['korean']):
                exported[normalize(row['japanese'])] = wire(row['korean'])
    # 이전 번역의 원문과 현재 gt_output을 (장면, 행 ID)로 결합한다.
    db = NC.A / 'chapter1-ko/script_meta.sqlite'
    translated = load_translations()
    with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        for scene, rid, jp in conn.execute('select cpk_name, ffbe_id, clean_jp from script_meta'):
            row = translated.get(Path(scene).stem.lower(), {}).get(str(rid))
            if row:
                add(jp, row.get('message'))
    result = {jp: next(iter(values)) for jp, values in candidates.items() if len(values) == 1}
    # 1장 CSV의 명시적 일문→한국어 대응을 우선한다. 장면 재번역과의 문체 차이로
    # 이미 확인한 전투 대사가 충돌 항목으로 빠지지 않도록 한다.
    result.update(exported)
    if include_battle:
        manifest = ROOT / 'translations/battle-ko/manifest.json'
        if manifest.exists():
            source = {r['ffbe_id']: r['source'] for r in json.loads(manifest.read_text(encoding='utf-8'))['records']}
            fits_path = ROOT / 'translations/battle-ko/line_fits.json'
            fits = json.loads(fits_path.read_text(encoding='utf-8')) if fits_path.exists() else {}
            for f in sorted((ROOT / 'translations/battle-ko/gt_output').glob('*.json')):
                for row in json.loads(f.read_text(encoding='utf-8-sig')):
                    jp = source.get(row.get('ffbe_id'))
                    ko = row.get('message', '')
                    # 대사 창(2줄 × 24자)에 맞게 줄인 문장. 원번역이 바뀌었으면 쓰지 않는다.
                    fit = fits.get(row.get('ffbe_id'))
                    if fit and fit['ko'] == ko:
                        ko = fit['fit']
                    if jp and NC.HANGUL.search(ko) and not NC.LEFT_JP.search(ko):
                        result[normalize(jp)] = wire(ko)
    return result


def patch_row(row, dialogue, names, counts, missing):
    result = dict(row)
    chunks = row.get(FIELD, '').split(':')
    for i, chunk in enumerate(chunks):
        parsed = split_chunk(chunk)
        # 알려진 대사 형식만 처리. 알 수 없는 명령/복합 인자는 그대로 둔다.
        if parsed is None:
            continue
        actor, speaker, body, tail = parsed
        ko = dialogue.get(normalize(body))
        if ko and ko != body:
            # 대사 창 줄 맞춤(원문 2줄 이하인 대사만). 맞출 수 없으면 그대로 두고 집계.
            if body.count('<br>') < 2:
                fitted = LF.fit(ko, sep='<br>')
                if fitted is None:
                    counts['dialogues_overflow'] += 1
                elif fitted != ko:
                    counts['dialogues_rewrapped'] += 1
                    ko = fitted
            body = ko
            counts['dialogues_changed'] += 1
        elif NC.JP.search(body):
            missing.add(body)
            counts['dialogues_left_japanese'] += 1
        ko_name = names.get(speaker) or names.get(speaker.strip())
        if ko_name and ko_name != speaker:
            speaker = wire(ko_name)
            counts['speakers_changed'] += 1
        chunks[i] = join_chunk(actor, speaker, body, tail)
    result[FIELD] = ':'.join(chunks)
    # 모든 명령의 위치와 쉼표 인자 수가 보존되어야 한다.
    old = row.get(FIELD, '').split(':')
    assert len(old) == len(chunks)
    for before, after in zip(old, chunks):
        assert before.count(',') == after.count(',')
        if before != after:
            assert before.split(',')[0] == after.split(',')[0]
    assert {k: v for k, v in result.items() if k != FIELD} == {k: v for k, v in row.items() if k != FIELD}
    return result


def main():
    dialogue = translations()
    names = NC.name_sources()[0]
    for f in sorted((ROOT / 'translations/names-ko').glob('names_pass[0-9].json')):
        for jp, ko in json.loads(f.read_text(encoding='utf-8')).items():
            names.setdefault(jp, ko)
    names = {jp: safe(ko) for jp, ko in names.items() if NC.HANGUL.search(ko) and not NC.LEFT_JP.search(ko)}
    src = next((NC.OLD / 'downloads/ffbejpdata-archive-org').glob(f'Ver*_{TOKEN}.dat'))
    lines = src.read_text(encoding='ascii').splitlines()
    k16 = key16(KEY)
    first = cbc_decrypt(k16, lines[0]); pad = first[-1]
    double = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad
    counts = defaultdict(int); missing = set(); out = []
    for line in lines:
        row = NC.D.json_record(cbc_decrypt(k16, line))
        updated = patch_row(row, dialogue, names, counts, missing)
        if updated != row:
            counts['rows_changed'] += 1
            encoded = cbc_encrypt(k16, json.dumps(updated, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), double_pad=double)
            assert NC.D.json_record(cbc_decrypt(k16, encoded)) == updated
            out.append(encoded)
        else:
            out.append(line)
    dest = ROOT / 'build/out/ko_names/mst_ko'; dest.mkdir(parents=True, exist_ok=True)
    (dest / src.name).write_text('\n'.join(out) + '\n', encoding='ascii')
    # 몬스터 표/CSV에 실제로 있는 이름으로 배포 사전을 한정한다.
    monster_names = set()
    manifest = NC.masters()
    for table in ('F_MONSTER_DICTIONARY_MST', 'F_MONSTER_SKILL_SET_MST'):
        tok, key = manifest[table]
        original = next((NC.OLD / 'downloads/ffbejpdata-archive-org').glob(f'Ver*_{tok}.dat'))
        for row in NC.D.decode(original.read_bytes(), key)[1]:
            monster_names.add(row.get('G4L0YIB2', ''))
    for row in csv.DictReader((ROOT / 'translations/chapter1-ko/csv_exports/chapter1_monsters.csv').open(encoding='utf-8-sig')):
        monster_names.add(row['japanese'])
    names = {jp: ko for jp, ko in names.items() if jp in monster_names}
    # 수신 데이터의 몬스터 이름 전용. 능력치·드롭·ID는 변경하지 않는다.
    overlay = ROOT / 'build/engine_overlay/jp_monster_names_ko.json'
    overlay.write_text(json.dumps(names, ensure_ascii=False, sort_keys=True, indent=1) + '\n', encoding='utf-8')
    OUT.mkdir(parents=True, exist_ok=True)
    counts.setdefault('dialogues_left_japanese', 0)
    counts.setdefault('dialogues_overflow', 0)
    report = dict(counts, rows=len(lines), file=src.name, exact_translation_pairs=len(dialogue), monster_name_pairs=len(names))
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'missing_dialogue.json').write_text(json.dumps(sorted(missing), ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()

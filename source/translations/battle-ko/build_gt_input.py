"""미연결 JP 전투 대사 전체를 중복 제거해 GalTransl 입력으로 추출한다.

python -I -X utf8 translations/battle-ko/build_gt_input.py
4필드(본문 뒤 플래그) 조각만 뽑을 때는 --tail-only와 별도 --project를 쓴다.
토큰이 있는 설정은 build/out 작업 폴더 안에서만 복사한다.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
import apply_ko_battle as B


def write_checked(path, data):
    """진행 중 번역의 입력을 다른 내용으로 덮어쓰지 않는다."""
    text = json.dumps(data, ensure_ascii=False, indent=1) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') != text:
        raise ValueError('기존 입력과 다른 추출 결과: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=ROOT / 'build/out/battle_gt')
    ap.add_argument('--config-from', type=Path, default=ROOT / 'build/out/story_gap_gt')
    ap.add_argument('--tail-only', action='store_true',
                    help='본문 뒤 플래그가 붙은 4필드 조각만 추출한다(3필드 기존 범위 제외)')
    args = ap.parse_args()
    project = args.project.resolve()
    src = next((B.NC.OLD / 'downloads/ffbejpdata-archive-org').glob(f'Ver*_{B.TOKEN}.dat'))
    rows = B.NC.D.decode(src.read_bytes(), B.KEY)[1]
    # 전투 전용 gt_output을 아직 읽지 않아도 되는 원래 번역 범위.
    # 꼬리 플래그 몫은 이미 전투 번역에 있는 본문까지 메모리로 보고 중복을 뺀다.
    existing = B.translations(include_battle=args.tail_only)
    names = B.NC.name_sources()[0]
    records, occurrences = {}, 0
    for row_index, row in enumerate(rows):
        for segment, chunk in enumerate(row.get(B.FIELD, '').split(':')):
            parsed = B.split_chunk(chunk)
            if parsed is None:
                continue
            actor, speaker, body, tail = parsed
            if (tail is not None) != args.tail_only:
                continue
            jp = B.normalize(body)
            if not B.NC.LEFT_JP.search(jp) or jp in existing:
                continue
            rid = 'battle_' + hashlib.sha256(jp.encode('utf-8')).hexdigest()[:20]
            if rid not in records:
                records[rid] = {'ffbe_id': rid, 'source': jp, 'speaker_jp': speaker,
                                'name': names.get(speaker, speaker).strip(), 'locations': []}
            assert records[rid]['source'] == jp
            records[rid]['locations'].append({'row': row_index, 'script': row.get('V2mCH5UR'),
                                             'segment': segment, 'actor': actor, 'speaker': speaker})
            occurrences += 1
    values = list(records.values())
    for i in range(0, len(values), 100):
        batch = [{'ffbe_id': r['ffbe_id'], 'name': r['name'], 'message': r['source']} for r in values[i:i+100]]
        write_checked(project / 'gt_input' / f'battle_{i//100:03}.json', batch)
    manifest = {'source_file': src.name, 'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
                'occurrences': occurrences, 'unique_messages': len(values),
                'characters': sum(len(r['source']) for r in values), 'records': values}
    # 꼬리 플래그 몫은 기존 3필드 manifest를 덮어쓰지 않도록 별도 파일에 둔다.
    manifest_path = ROOT / 'translations/battle-ko' / ('manifest_tail.json' if args.tail_only else 'manifest.json')
    write_checked(manifest_path, manifest)
    # 설정 내용/토큰을 출력하지 않는다. build/out은 Git 제외 경로다.
    config = project / 'config.yaml'
    if not config.exists():
        shutil.copyfile(args.config_from / 'config.yaml', config)
    if not (project / 'Dict').exists():
        shutil.copytree(args.config_from / 'Dict', project / 'Dict')
    if not (project / 'name替换表.csv').exists():
        shutil.copyfile(ROOT / 'translations/story-gap-ko/name替换表.csv', project / 'name替换表.csv')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'records'}, ensure_ascii=False))
    print('입력 파일', len(list((project / 'gt_input').glob('*.json'))), '설정·용어집 준비 완료')


if __name__ == '__main__':
    main()

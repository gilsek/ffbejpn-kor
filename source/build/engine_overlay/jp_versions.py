"""JP는 버전 응답을 다운로드 지시로 해석하므로 미적용 버전만 응답한다."""
from pathlib import Path
import xml.etree.ElementTree as ET


# 클라이언트 사본을 다시 받게 할 마스터: {표 이름: 새 버전}. 플레이용 빌드는 run-as가 안 돼 files/ 사본을 직접
# 못 바꾸므로, 버전을 올려 클라이언트가 mst/Ver<새 버전>_<token>.dat 를 다시 받게 한다(기기 mst_ko/ 에 그 이름으로 둔다).
# F_RESOURCE_MAP_MST 766 = 장면 없는 Rm 노드의 대체 장면 행(build/make_jp_noscene_stub.py, 2026-11-14).
VERSION_BUMP = {'F_RESOURCE_MAP_MST': 766, 'F_MISSION_MST': 2029}


def bump_versions(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get('c1qYg84Q'), list):
        return spec
    rows = []
    for row in spec['c1qYg84Q']:
        if isinstance(row, dict) and row.get('a4hXTIm0') in VERSION_BUMP:
            new = VERSION_BUMP[row['a4hXTIm0']]
            print('JP_VERSION_BUMP %s %s -> %s' % (row['a4hXTIm0'], row.get('wM9AfX6I'), new), flush=True)
            row = dict(row, wM9AfX6I=type(row.get('wM9AfX6I'))(new) if row.get('wM9AfX6I') is not None else str(new))
        rows.append(row)
    return dict(spec, c1qYg84Q=rows)


def pending_versions(spec, prefs_path):
    if not isinstance(spec, dict) or not isinstance(spec.get('c1qYg84Q'), list):
        return spec
    try:
        prefs = {node.attrib.get('name'): node.text for node in ET.parse(prefs_path).getroot()
                 if node.tag == 'string'}
    except (OSError, ET.ParseError):
        return spec  # 저장값을 읽지 못하면 원래 설치 절차 유지.
    rows = []
    for row in spec['c1qYg84Q']:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        name, version = row.get('a4hXTIm0'), row.get('wM9AfX6I')
        # parent 버전은 다운로드 파일이 아니라 전체 버전 메타데이터다.
        if (name in ('F_RSC_VERSION', 'F_MST_VERSION') or not isinstance(name, str)
                or version is None or prefs.get('key' + name) != str(version)):
            rows.append(row)
    return dict(spec, c1qYg84Q=rows)


def install(native_files):
    import ffbe_pipeline
    original = ffbe_pipeline.serve_version_table
    prefs = Path(native_files).parent / 'shared_prefs' / 'gamedata.xml'

    def serve(spec):
        full = bump_versions(original(spec))
        result = pending_versions(full, prefs)
        if isinstance(full, dict) and isinstance(full.get('c1qYg84Q'), list):
            print('JP_VERSION_DELTA full=' + str(len(full['c1qYg84Q']))
                  + ' pending=' + str(len(result['c1qYg84Q'])), flush=True)
        return result

    ffbe_pipeline.serve_version_table = serve

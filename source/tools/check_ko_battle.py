"""전투 번역 산출물의 명령 구조와 실제 엔진 응답 계약을 검사한다."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build'))
sys.path.insert(0, str(ROOT / 'build/engine_overlay'))
import apply_ko_battle as B
import jp_korean as K


def main():
    src = B.NC.OLD / 'downloads/ffbejpdata-archive-org/Ver797_i7STtbw8.dat'
    dst = ROOT / 'build/out/ko_names/mst_ko' / src.name
    before = B.NC.D.decode(src.read_bytes(), B.KEY)[1]
    after = B.NC.D.decode(dst.read_bytes(), B.KEY)[1]
    assert len(before) == len(after) == 4848
    changed = 0
    for a, b in zip(before, after):
        assert {k: v for k, v in a.items() if k != B.FIELD} == {k: v for k, v in b.items() if k != B.FIELD}
        x, y = a[B.FIELD].split(':'), b[B.FIELD].split(':')
        assert len(x) == len(y)
        for p, q in zip(x, y):
            assert p.count(',') == q.count(',')
            if p != q:
                assert p.split(',')[0] == q.split(',')[0]
        changed += a != b
    tutorial = next(r for r in after if r['V2mCH5UR'] == '111010101')
    assert '100000102,레인,곤란한데.<br>별똥별 구경하다 마물 같은 걸 만나다니.' in tutorial[B.FIELD]
    names = json.loads((ROOT / 'build/engine_overlay/jp_monster_names_ko.json').read_text(encoding='utf-8'))
    replies = json.loads((B.NC.OLD / 'upstream/source/server/responses.json').read_text(encoding='utf-8'))
    sample = replies['jnw49dUq@1110100']
    snapshot = copy.deepcopy(sample)
    localized = K.localize_monsters(sample, names)
    assert sample == snapshot  # 공유 원본 응답을 변형하지 않는다.
    for group in K.GROUPS:
        assert localized[group][0]['G4L0YIB2'] == '스틸 배트'
        for a, b in zip(sample[group], localized[group]):
            assert {k: v for k, v in a.items() if k != 'G4L0YIB2'} == {k: v for k, v in b.items() if k != 'G4L0YIB2'}
    for tag in sample.keys() - set(K.GROUPS):
        assert localized[tag] == sample[tag]
    assert K.localize_monsters(None, names) is None
    unknown = {'bV34YIJQ': [{'G4L0YIB2': '未登録', 'hp': 10}], 'wbet57nF': None}
    assert K.localize_monsters(unknown, names) == unknown
    # 실기기와 같은 직접 import 바인딩을 통한 설치도 검증한다.
    from types import SimpleNamespace
    server = SimpleNamespace(reply_pipeline=lambda *a, **kw: sample)
    K.install(server)
    assert server.reply_pipeline(sample)['bV34YIJQ'][0]['G4L0YIB2'] == '스틸 배트'
    print(f'PASS: {len(after)}행 구조·암호화 왕복, 변경 {changed}행, 튜토리얼 대사, 응답 두 그룹 이름만 변경, 호출자 바인딩')


if __name__ == '__main__':
    main()

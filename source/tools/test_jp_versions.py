"""JP 버전 응답의 재설치 방지·초기 설치 경계 검사(기기 데이터 변경 없음)."""
import importlib.util
from pathlib import Path
import tempfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('jp_versions', root / 'build/engine_overlay/jp_versions.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows = [{'a4hXTIm0': name, 'wM9AfX6I': ver} for name, ver in
        [('F_RSC_VERSION', '1'), ('F_MST_VERSION', '4493'), ('F_SAME', '7'), ('F_CHANGED', '8'), ('F_NEW', '2')]]
response = {'c1qYg84Q': rows, 'other': 'preserved'}
with tempfile.TemporaryDirectory() as folder:
    prefs = Path(folder) / 'gamedata.xml'
    assert module.pending_versions(response, prefs) is response
    prefs.write_text('<map><string name="keyF_SAME">7</string><string name="keyF_CHANGED">6</string></map>', encoding='utf-8')
    result = module.pending_versions(response, prefs)
    assert [r['a4hXTIm0'] for r in result['c1qYg84Q']] == ['F_RSC_VERSION', 'F_MST_VERSION', 'F_CHANGED', 'F_NEW']
    assert len(response['c1qYg84Q']) == 5 and result['other'] == 'preserved'
    prefs.write_text('<map>', encoding='utf-8')
    assert module.pending_versions(response, prefs) is response
print('PASS: 동일/변경/누락 버전, parent 보존, prefs 없음/손상, 원본 응답 보존')

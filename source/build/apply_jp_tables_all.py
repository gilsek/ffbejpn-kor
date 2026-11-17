"""엔진 정적 표 중 JP 마스터에 있는 표를 JP로 교체한다 (docs/plans/2026-11-10-jp-engine-tables.md).

usage: python -I -X utf8 build/apply_jp_tables_all.py [--dry]
KEEP(검수 대상)과 JP에 없는 표는 건드리지 않는다. 영문판 원본은 <name>.ndjson.global로 한 번만 보관.
"""
import subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
STATIC = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
KEEP = ('F_DEFINE_MST', 'F_FUNCTION_MST', 'F_SWITCH_TYPE_MST', 'F_RB_DEFINE_MST',
        'F_CLSM_ROUND_MST', 'F_CLSM_PROGRESS_MST', 'F_DIAMOND_MST')
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(OLD / 'upstream/source/server'))
import decode_client_data as D  # noqa: E402


def targets():
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read(
        'lib/arm64-v8a/libgame.so')
    man = {m.group(1).decode(): m.group(2).decode() for m in D.TRIPLET.finditer(native)}
    have = {p.stem.split('_', 1)[1] for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}
    return [p.stem for p in sorted(STATIC.glob('*.ndjson'))
            if p.stem not in KEEP and man.get(p.stem) in have]


def main():
    names = targets()
    print(len(names), 'tables')
    if '--dry' in sys.argv:
        print(' '.join(names))
        return
    for i in range(0, len(names), 40):
        subprocess.run([sys.executable, '-I', '-X', 'utf8', str(ROOT / 'build/apply_jp_masters.py'), *names[i:i + 40]],
                       check=True)


if __name__ == '__main__':
    main()

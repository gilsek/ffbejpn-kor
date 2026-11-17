"""엔진 정적 표(mst_decoded)를 JP 11.0.0 마스터와 대조한다.

usage: python -I -X utf8 tools/audit_engine_tables.py
출력: build/out/audit/engine_tables.json, 화면 요약
분류:
  same       JP와 행 단위로 같음
  jp         이미 JP로 교체됨(.global 보관본 있음, 내용 = JP)
  differs    같은 열, 행 내용이 다름
  columns    열 구성이 다름(엔진 코드가 쓰는 열이 JP에 없을 수 있음)
  no_jp      JP 마스터에 표가 없음(영문판 전용)
used = 엔진 소스(.py)에서 표 이름이 나오는 파일 수.
"""
import io, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix')
STATIC = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
SRC_DIRS = (OLD / 'upstream/source/server', ROOT / 'build/engine_overlay')
OUT = ROOT / 'build/out/audit/engine_tables.json'
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))
sys.path.insert(0, str(OLD / 'upstream/source/server'))
import decode_client_data as D  # noqa: E402


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    native = zipfile.ZipFile(OLD / 'downloads/FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read(
        'lib/arm64-v8a/libgame.so')
    man = {}
    for m in D.TRIPLET.finditer(native):
        n, t, k = (v.decode() for v in m.groups())
        man[n] = (t, k)
    files = {p.stem.split('_', 1)[1]: p for p in (OLD / 'downloads/ffbejpdata-archive-org').glob('Ver*_*.dat')}
    sources = [(p, p.read_text(encoding='utf-8', errors='replace')) for d in SRC_DIRS for p in d.glob('*.py')]
    out = []
    for path in sorted(STATIC.glob('*.ndjson')):
        table = path.stem
        eng = [json.loads(l) for l in path.open(encoding='utf-8') if l.strip()]
        used = sorted(p.name for p, text in sources if table in text)
        rec = {'table': table, 'rows': len(eng), 'used': used}
        tok = man.get(table)
        src = files.get(tok[0]) if tok else None
        if src is None:
            rec['class'] = 'no_jp'
        else:
            jp = D.decode(src.read_bytes(), tok[1], localized=False)[1]
            rec['jp_rows'] = len(jp)
            ec = set().union(*map(set, eng)) if eng else set()
            jc = set().union(*map(set, jp)) if jp else set()
            if eng == jp:
                rec['class'] = 'jp' if path.with_name(path.name + '.global').exists() else 'same'
            elif ec != jc:
                rec['class'] = 'columns'
                rec['eng_only_cols'] = sorted(ec - jc)
                rec['jp_only_cols'] = sorted(jc - ec)
            else:
                rec['class'] = 'differs'
                es = {json.dumps(r, sort_keys=True) for r in eng}
                js = {json.dumps(r, sort_keys=True) for r in jp}
                rec['eng_only_rows'] = len(es - js)
                rec['jp_only_rows'] = len(js - es)
        out.append(rec)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    by = {}
    for r in out:
        by.setdefault(r['class'], []).append(r)
    for c in ('jp', 'same', 'differs', 'columns', 'no_jp'):
        rs = by.get(c, [])
        print('== %s %d (엔진 코드 사용 %d)' % (c, len(rs), sum(1 for r in rs if r['used'])))
        for r in rs:
            if c in ('same', 'jp'):
                continue
            extra = ''
            if c == 'differs':
                extra = 'eng-only %d / jp-only %d' % (r['eng_only_rows'], r['jp_only_rows'])
            elif c == 'columns':
                extra = 'eng-only cols %s / jp-only cols %s' % (r['eng_only_cols'][:4], r['jp_only_cols'][:4])
            print('  %-34s rows %5s jp %5s used %-2d %s' % (r['table'], r['rows'], r.get('jp_rows', '-'),
                                                         len(r['used']), extra))
    print('->', OUT)


if __name__ == '__main__':
    main()

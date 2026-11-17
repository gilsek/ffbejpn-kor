"""CPK 루트에 넣은 파일(add_item_icons.py)을 TOC 정렬 위치로 옮기고 APK를 다시 서명한다. (2026-11-12, e9)

usage:
  python -I -X utf8 build/sort_cpk_root_files.py \
      --source build/out/jp_shop/e8-apk --out build/out/jp_shop/e9-apk

왜:
  * CPK 헤더 Sorted=1. TOC 행은 전체 경로 순으로 정렬돼 있고, 게임의 이름 검색
    (criFsBinder_Find -> cpkCore_GetGroupFileInfoWithFilename)은 그 순서를 전제로 한다.
  * add_item_icons.py 는 image/test_thums.png, image/tex_test.png 행(34/35)을 루트 파일
    raid_king_mog.png / item_8224.png 로 바꿨다. 행 위치가 image/ 사이 그대로라 정렬이 깨져
    기기에서 existsFile -> 0 (logcat5: loaderFetch "raid_king_mog.png" -> 0x0).
  * 같은 CPK 의 원래 루트 파일(common.cpk fill.png 행 22, 'edge/..' 와 'font/..' 사이)은 찾아진다.

동작:
  * DirName=='' 인 행 중 이웃과 순서가 어긋난 행만 정렬 위치로 옮긴다(나머지 행 상대 순서 불변).
  * TOC 행 전체(이름/크기/오프셋/ID/CRC)를 같이 옮기고, GTOC Fdata 의 Child(노드->행)는
    새 행 번호로 바꾸고 SortFlink(k) = node_of_row[k-1] 불변식을 다시 맞춘다. Next 체인은 그대로.
  * TOC/GTOC 바이트 크기는 바뀌지 않아야 한다(아니면 중단). 본문 데이터는 손대지 않는다.
"""
import argparse
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / 'build', ROOT / 'tools', ROOT / 'tools' / 'vendor'):
    sys.path.insert(0, str(p))

import jp_offline_build as B  # noqa: E402
import cpk_inplace as C  # noqa: E402
from cricodecs import cpk, utf  # noqa: E402
from add_item_icons import PARTS, is_signature, sha  # noqa: E402

COLS = ('DirName', 'FileName', 'FileSize', 'ExtractSize', 'FileOffset', 'ID', 'CRC')


def path_of(toc, r):
    return '/'.join(x for x in (toc.value(r, 'DirName'), toc.value(r, 'FileName')) if x)


def key(p):
    return p.upper().encode()   # 원본 위반 사례(dictionary < dic_, windowR < window_)는 대문자 비교에서만 정렬됨


def write_table(d, off, t, size, enc):
    raw = t.build()
    raw = C._crypt(raw) if enc else raw
    if len(raw) != size and len(raw) > size:
        raise SystemExit(f'테이블이 슬롯을 넘음 @0x{off:x}: {len(raw)} > {size}')
    d[off + 8:off + 16] = struct.pack('<Q', len(raw))
    d[off + 16:off + 16 + size] = raw + b'\0' * (size - len(raw))


def sort_roots(cpk_bytes):
    d = bytearray(cpk_bytes)
    hdr, _, _ = C._table(d, 0)
    toff = hdr.value(0, 'TocOffset')
    toc, tsize, tenc = C._table(d, toff)
    n = toc.row_count
    paths = [path_of(toc, r) for r in range(n)]
    misplaced = []
    for r in range(n):
        if toc.value(r, 'DirName') != '':
            continue
        lo = r == 0 or key(paths[r - 1]) < key(paths[r])
        hi = r == n - 1 or key(paths[r]) < key(paths[r + 1])
        if not (lo and hi):
            misplaced.append(r)
    if not misplaced:
        return bytes(d), []
    order = [r for r in range(n) if r not in misplaced]           # 새 순서의 옛 행 번호
    for r in misplaced:
        k = key(paths[r])
        pos = next((i for i, o in enumerate(order) if key(paths[o]) > k), len(order))
        order.insert(pos, r)
    new_of_old = {o: i for i, o in enumerate(order)}
    rows = [{c: toc.value(o, c) for c in COLS} for o in order]
    for i, row in enumerate(rows):
        for c in COLS:
            toc.set(i, c, row[c])
    write_table(d, toff, toc, tsize, tenc)

    goff = hdr.value(0, 'GtocOffset')
    gt, gsize, genc = C._table(d, goff)
    fd = utf.Utf.load_bytes(gt.data(0, 'Fdata'))
    old_len = len(gt.data(0, 'Fdata'))
    for k in range(1, n + 1):
        fd.set(k, 'Child', new_of_old[fd.value(k, 'Child')])
    node_of_row = {fd.value(k, 'Child'): k for k in range(1, n + 1)}
    for k in range(1, n + 1):
        fd.set(k, 'SortFlink', node_of_row[k - 1] if k - 1 in node_of_row else fd.value(k, 'SortFlink'))
    # 노드 0 의 SortFlink 는 노드 수(N)라 그대로 둔다(원본 common 321/resources 236)
    fraw = fd.build()
    if len(fraw) != old_len:
        raise SystemExit(f'Fdata 크기 변경 {old_len} -> {len(fraw)}')
    ref = gt.data_ref(0, 'Fdata') if hasattr(gt, 'data_ref') else gt.value(0, 'Fdata')
    # Fdata 는 GTOC 테이블 데이터 영역 안의 원시 바이트: 같은 크기로 제자리 교체
    gdata = bytes(d[goff:goff + 16 + gsize])
    plain = C._crypt(gdata[16:]) if genc else gdata[16:]
    old_f = gt.data(0, 'Fdata')
    at = plain.find(old_f)
    assert at >= 0 and plain.find(old_f, at + 1) < 0, 'Fdata 위치 특정 실패'
    plain = plain[:at] + fraw + plain[at + len(fraw):]
    d[goff + 16:goff + 16 + gsize] = C._crypt(plain) if genc else plain
    return bytes(d), [(paths[r], r, new_of_old[r]) for r in misplaced]


def verify(old, new):
    co = cpk.Cpk.load_bytes(old, encoding='cp932')
    cn = cpk.Cpk.load_bytes(new, encoding='cp932')
    io = {i.full_path: i for i in co.file_infos()}
    inn = {i.full_path: i for i in cn.file_infos()}
    assert set(io) == set(inn)
    for p in io:
        assert co.file_bytes(io[p].toc_index) == cn.file_bytes(inn[p].toc_index), p
    hdr, _, _ = C._table(new, 0)
    toc, _, _ = C._table(new, hdr.value(0, 'TocOffset'))
    paths = [path_of(toc, r) for r in range(toc.row_count)]
    viol = [i for i in range(1, len(paths)) if key(paths[i - 1]) > key(paths[i])]
    gt, _, _ = C._table(new, hdr.value(0, 'GtocOffset'))
    fd = utf.Utf.load_bytes(gt.data(0, 'Fdata'))
    n = toc.row_count
    node_of_row = {fd.value(k, 'Child'): k for k in range(1, n + 1)}
    assert sorted(node_of_row) == list(range(n))
    assert all(fd.value(k, 'Next') == (k + 1 if k < n else 0) for k in range(1, n + 1))
    assert all(fd.value(k, 'SortFlink') == node_of_row[k - 1] for k in range(1, n + 1))
    return len(io), viol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cpk', action='append', default=[], help='기본: assets/cpk/resources.cpk')
    a = ap.parse_args()
    src, out = a.source.resolve(), a.out.resolve()
    assert src != out
    entries = a.cpk or ['assets/cpk/resources.cpk']
    new = {}
    with zipfile.ZipFile(src / 'base.apk') as z:
        for e in entries:
            old = z.read(e)
            nb, moved = sort_roots(old)
            files, viol = verify(old, nb)
            print(f'{e}: 이동 {moved} | 엔트리 {files}개 내용 동일 | 정렬 위반(대문자 비교) {len(viol)}건')
            new[e] = nb
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    unsigned = out / 'base-unsigned.apk'
    with zipfile.ZipFile(src / 'base.apk') as z, zipfile.ZipFile(unsigned, 'w') as w:
        for i in z.infolist():
            if is_signature(i.filename):
                continue
            w.writestr(i, new.get(i.filename) or z.read(i.filename))
    B.align_sign(unsigned, out / 'base.apk')
    for p in PARTS[1:]:
        shutil.copyfile(src / f'{p}.apk', out / f'{p}.apk')
    for e, b in new.items():
        print(f'  {e} sha256 {sha(b)}')


if __name__ == '__main__':
    main()

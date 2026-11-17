"""아이템 아이콘을 CPK 루트 파일로 넣고 APK를 새로 서명한다. (2026-11-12, e7)

usage:
  python -I -X utf8 build/add_item_icons.py \
      --source build/out/jp_shop/e6p-apk --out build/out/jp_shop/e7-apk \
      --icons inputs/item_icons/white_purecryst

왜 아틀라스(item.plist)가 아니라 CPK 파일인가 (libgame.orig.so 근거):
  * SealAreaListScene 의 아이콘 갱신 코드(0x199ef9c~0x199f064):
      itemId = SealUtil::getRequiredItemIdWithTabIndex(tab)
      name   = GameUtils::getItemIconImageName(itemId, 20, true)   # 0x1486d60
               -> GameUtils::getItemMst(id,20) -> ItemMst::getIconId()
               -> IconMstList::getFileName(iconId)               # "item_8224.png"
      if (TextureUtil::isExist(name))                                 # 0x15a2874
          LayoutUtils::createGameSpriteByImage(name, ...)             # 0x1547c18
  * TextureUtil::isExist 는 CriFs 쪽 0x15ddafc 로 들어가며(내부 0x15d711c),
    결국 criFsBinder_Find(0x1fb8e7c -> 코어 0x1124ea0=cpkCore_GetGroupFileInfoWithFilename)
    로 간다. 즉 SpriteFrameCache/plist 프레임이 아니라 **CPK 안의 파일 이름**을 찾는다.
    크기(20)는 ImageMst 종류일 뿐 아이콘마다 경로가 붙지 않는다(이름이 그대로 파일명).
  * 게임이 마운트하는 CPK 는 assets/cpk/{common,resources,layout,spritestudio}.cpk 네 개뿐이고
    (0x15d4934 생성자, 0x258d604/613/625/634 경로 문자열), 이 JP 판에는 item_*.png 파일이 없다.
    그래서 흰 사각형이 뜬다.

동작:
  * --source 폴더는 읽기만 한다. base.apk 의 assets/cpk/resources.cpk 에서 아이콘 PNG 를
    **CPK 루트 이름 그대로**(예: item_8224.png) 넣는다.
  * CPK 의 TOC 행 수/ID/GTOC/ETOC 는 건드리지 않는다. 이름 없는 테스트 자산
    (기본 image/tex_test.png, --placeholder 로 변경) 한 줄을 재사용해
    DirName='' + FileName=아이콘 파일명 + 본문(끝에 정렬 추가)으로 바꾼다.
    GTOC Flink(Next/Child/SortFlink)는 TOC 행 인덱스만 참조하므로 그대로 유효하고,
    이름 비교는 TOC 의 DirName/FileName 을 읽으므로 새 루트 이름으로 검색된다.
  * EnableFileCrc/EnableTocCrc 가 켜진 CPK 면 거부한다(CRC 재계산 안 함).
  * base.apk 의 META-INF 서명만 걷어내 zipalign + apksigner 로 다시 서명한다.
    AndroidManifest(debuggable=false)는 손대지 않는다. split 3개는 그대로 복사한다.

재실행: 같은 --out 폴더가 있으면 지우고 새로 만든다(원본 --source 는 불변).
"""
import argparse
import hashlib
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

CPK_ENTRY = 'assets/cpk/resources.cpk'
PARTS = ('base', 'split_config.arm64_v8a', 'split_config.ja', 'split_config.xhdpi')
SIGNATURE_SUFFIX = {'MF', 'SF', 'RSA', 'DSA', 'EC'}

# 이름이 게임 코드/레이아웃 CSV 어디에서도 참조되지 않는 테스트 자산
DEFAULT_PLACEHOLDERS = ('image/tex_test.png', 'image/test_thums.png')


def is_signature(name):
    return name.startswith('META-INF/') and name.rsplit('.', 1)[-1].upper() in SIGNATURE_SUFFIX


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _norm(v):
    return (v.offset, v.size) if hasattr(v, 'offset') else v


def put_root_file(cpk_bytes, png, name, placeholder):
    """TOC 행 하나를 루트 파일로 재사용한다. (TOC/GTOC/ETOC 구조 불변)"""
    d = bytearray(cpk_bytes)
    hdr, hsize, henc = C._table(d, 0)
    if hdr.value(0, 'EnableFileCrc'):
        raise SystemExit('EnableFileCrc=1: CRC 재계산이 필요해 중단')
    toc_off = hdr.value(0, 'TocOffset')
    align = hdr.value(0, 'Align') or 2048
    toc, tsize, tenc = C._table(d, toc_off)
    rows = [r for r in range(toc.row_count)
            if toc.value(r, 'DirName') == placeholder[0]
            and toc.value(r, 'FileName') == placeholder[1]]
    if len(rows) != 1:
        raise SystemExit(f'자리표시자 {placeholder} 가 정확히 하나가 아님: {rows}')
    r = rows[0]
    old = {n: toc.value(r, n) for n in
           ('DirName', 'FileName', 'FileSize', 'ExtractSize', 'FileOffset', 'ID')}

    pad = (-len(d)) % align
    d += b'\0' * pad
    body_off = len(d)
    d += png

    toc.set(r, 'DirName', '')
    toc.set(r, 'FileName', name)
    toc.set(r, 'FileSize', len(png))
    toc.set(r, 'ExtractSize', len(png))
    toc.set(r, 'FileOffset', body_off - toc_off)

    raw = toc.build()
    raw = C._crypt(raw) if tenc else raw
    if len(raw) > tsize:
        raise SystemExit(f'TOC 가 슬롯을 넘음: {len(raw)} > {tsize} (행 추가 방식으로 바꿔야 함)')
    d[toc_off + 8:toc_off + 16] = struct.pack('<Q', len(raw))
    d[toc_off + 16:toc_off + 16 + tsize] = raw + b'\0' * (tsize - len(raw))

    hdr.set(0, 'ContentSize', len(d) - hdr.value(0, 'ContentOffset'))
    hraw = hdr.build()
    hraw = C._crypt(hraw) if henc else hraw
    if len(hraw) > hsize:
        raise SystemExit('헤더 테이블이 슬롯을 넘음')
    d[8:16] = struct.pack('<Q', len(hraw))
    d[16:16 + hsize] = hraw + b'\0' * (hsize - len(hraw))

    return bytes(d), {'row': r, 'old': old, 'body_off': body_off, 'toc_size': len(raw)}


def verify_cpk(old, new, icons):
    """CPK: 아이콘 외 모든 엔트리/구조 불변."""
    from cricodecs import cpk, utf
    ho, so, eo = C._table(old, 0)
    hn, sn, en = C._table(new, 0)
    assert (so, eo) == (sn, en), '헤더 모양 변경'
    changed = [ho.column_name(i) for i in range(ho.column_count)
               if _norm(ho.value(0, ho.column_name(i))) != _norm(hn.value(0, hn.column_name(i)))]
    assert changed == ['ContentSize'], f'헤더 필드 변경: {changed}'
    toff = ho.value(0, 'TocOffset')
    to, tso, teo = C._table(old, toff)
    tn, tsn, ten = C._table(new, toff)
    assert (to.row_count, teo) == (tn.row_count, ten)
    diffs = []
    for r in range(to.row_count):
        a = [_norm(to.value(r, n)) for n in ('DirName', 'FileName', 'FileSize', 'ExtractSize',
                                             'FileOffset', 'ID', 'UserString', 'CRC')]
        b = [_norm(tn.value(r, n)) for n in ('DirName', 'FileName', 'FileSize', 'ExtractSize',
                                             'FileOffset', 'ID', 'UserString', 'CRC')]
        if a != b:
            diffs.append((r, a, b))
    assert len(diffs) == len(icons), f'바뀐 TOC 행 {len(diffs)} != 아이콘 {len(icons)}'
    by_name = {name: png for _icon, name, png in icons}
    for r, a, b in diffs:
        assert b[0] == '' and b[1] in by_name, (a, b)
        assert b[2] == len(by_name[b[1]]) == b[3]
        assert b[5] == a[5] and b[6] == a[6], 'ID/UserString 은 보존해야 함'

    co = cpk.Cpk.load_bytes(old, encoding='cp932')
    cn = cpk.Cpk.load_bytes(new, encoding='cp932')
    idx_o = {i.full_path: i for i in co.file_infos()}
    idx_n = {i.full_path: i for i in cn.file_infos()}
    removed = set(idx_o) - set(idx_n)
    added = set(idx_n) - set(idx_o)
    assert added == set(by_name), (added, set(by_name))
    assert len(removed) == len(icons)

    # 기존 엔트리는 CPK 안의 원시 바이트(압축 포함)까지 같아야 한다
    same = 0
    for p in sorted(set(idx_o) - removed):
        assert co.file_bytes(idx_o[p].toc_index) == cn.file_bytes(idx_n[p].toc_index), p
        same += 1
    for name, png in by_name.items():
        assert cn.file_bytes(idx_n[name].toc_index) == png, name
    g = ho.value(0, 'GtocOffset')
    assert new[g:ho.value(0, 'ContentOffset')] == old[g:ho.value(0, 'ContentOffset')], 'GTOC 변경'
    e = ho.value(0, 'EtocOffset')
    assert new[e:e + ho.value(0, 'EtocSize')] == old[e:e + ho.value(0, 'EtocSize')], 'ETOC 변경'
    assert new[16 + sn:toff] == old[16 + so:toff], '헤더 뒤 패딩 변경'

    # GTOC Flink 불변식(원본 그대로)
    ga, gs, ge = C._table(old, g)
    fd = utf.Utf.load_bytes(ga.data(0, 'Fdata'))
    rows = [(fd.value(i, 'Next'), fd.value(i, 'Child'), fd.value(i, 'SortFlink'))
            for i in range(fd.row_count)]
    node_of_row = {rows[k][1]: k for k in range(1, to.row_count + 1)}
    assert sorted(node_of_row) == list(range(to.row_count))
    assert all(rows[k][0] == (k + 1 if k < to.row_count else 0) for k in range(1, to.row_count + 1))
    assert all(rows[k][2] == node_of_row[k - 1] for k in range(1, to.row_count + 1))
    return {'same_entries': same, 'removed': sorted(removed), 'added': sorted(added),
            'toc_size': tsn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--icons', type=Path, required=True)
    ap.add_argument('--glob', default='item_*.png', help='넣을 PNG 패턴 (기본 item_*.png)')
    ap.add_argument('--placeholder', action='append', default=[],
                    help='재사용할 CPK 경로 (기본: ' + ', '.join(DEFAULT_PLACEHOLDERS) + ')')
    args = ap.parse_args()
    src, out, icons_dir = args.source.resolve(), args.out.resolve(), args.icons.resolve()
    assert src != out and src not in out.parents and out not in src.parents, '입력/출력 폴더를 분리한다'
    assert (src / 'base.apk').is_file()
    files = sorted(icons_dir.glob(args.glob))
    if not files:
        raise SystemExit(f'아이콘 없음: {icons_dir}/{args.glob}')
    raw_ph = args.placeholder or list(DEFAULT_PLACEHOLDERS)
    placeholders = []
    for p in raw_ph:
        parts = p.split('/')
        placeholders.append(('/'.join(parts[:-1]), parts[-1]))
    if len(files) > len(placeholders):
        raise SystemExit(f'아이콘 {len(files)}개 > 자리표시자 {len(placeholders)}개')

    with zipfile.ZipFile(src / 'base.apk') as z:
        cpk_orig = z.read(CPK_ENTRY)
    cpk_new = cpk_orig
    icons = []
    for icon, ph in zip(files, placeholders):
        png = icon.read_bytes()
        if png[:8] != b'\x89PNG\r\n\x1a\n':
            raise SystemExit(f'PNG 아님: {icon}')
        cpk_new, info = put_root_file(cpk_new, png, icon.name, ph)
        icons.append((icon, icon.name, png))
        print(f'  {icon.name}: {ph[0]}/{ph[1]} 행 {info["row"]} 재사용, '
              f'본문 @0x{info["body_off"]:x}, TOC {info["toc_size"]} bytes')

    stats = verify_cpk(cpk_orig, cpk_new, icons)
    print(f'PASS: CPK 엔트리 {stats["same_entries"]}개 바이트 동일 | '
          f'자리표시자 {stats["removed"]} -> {stats["added"]} | GTOC/ETOC/헤더 불변')

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    unsigned = out / 'base-unsigned.apk'
    with zipfile.ZipFile(src / 'base.apk') as z, zipfile.ZipFile(unsigned, 'w') as w:
        for i in z.infolist():
            if is_signature(i.filename):
                continue
            w.writestr(i, cpk_new if i.filename == CPK_ENTRY else z.read(i.filename))
    B.align_sign(unsigned, out / 'base.apk')
    for p in PARTS[1:]:
        shutil.copyfile(src / f'{p}.apk', out / f'{p}.apk')

    same = 0
    with zipfile.ZipFile(src / 'base.apk') as zo, zipfile.ZipFile(out / 'base.apk') as zn:
        assert zo.namelist() == zn.namelist(), 'base.apk 엔트리 목록/순서 변경'
        for n in zo.namelist():
            if n == CPK_ENTRY or n.startswith('META-INF/'):
                continue
            assert zo.read(n) == zn.read(n), n
            same += 1
        assert zo.read('AndroidManifest.xml') == zn.read('AndroidManifest.xml'), 'AndroidManifest 변경됨'
        assert zn.read(CPK_ENTRY) == cpk_new, '출력 CPK 불일치'
    for p in PARTS[1:]:
        assert sha((src / f'{p}.apk').read_bytes()) == sha((out / f'{p}.apk').read_bytes())
    print(f'PASS: base.apk CPK/META-INF 외 {same}개 엔트리·AndroidManifest 바이트 동일, '
          f'split {len(PARTS) - 1}개 sha256 동일')
    print(f'  base.apk {out / "base.apk"} ({sha((out / "base.apk").read_bytes())[:16]}...)')
    print(f'  resources.cpk sha256 {sha(cpk_new)}')


if __name__ == '__main__':
    main()

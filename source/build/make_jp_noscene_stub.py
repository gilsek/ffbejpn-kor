#!/usr/bin/env python3
"""장면 자료가 없는 Rm 스토리 노드(build/engine_overlay/jp_rm_noscene.json)에 짧은 대체 장면을 연결한다.

이 노드들은 F_MISSION_MST.q4f9IdMs의 장면 id(3xxxxxxxx)가 F_RESOURCE_MAP_MST에 없고, 260개는 지도 id(29xxxx)도
없다. 서버가 노드를 건너뛰게 한 방식(2026-11-14)은 진행이 어긋났다. 대신 클라이언트가 실제로 재생하고 스스로
끝내는 장면을 준다: 들어가면 안내 문구가 나오고 RmEnd가 정상으로 올라와 클리어된다.

  장면: 일판 737060701.cpk(미션 7370607, event.bin 2653바이트, 대사 6행)을 복사해 이름을 STUB로 바꾸고
        대사를 안내 문구로 교체. 없는 장면 id 전부가 이 파일 하나를 가리킨다.
  지도: 그 장면의 짝인 151010100.cpk(리소스 251101). 지도 id도 없는 노드는 이 파일을 가리킨다.
        지도 id가 이미 있는 노드(59개)는 원래 지도 위에서 대체 장면이 재생된다.

산출(재실행 가능): build/out/jp_noscene_stub/flat_ko/<STUB>.cpk, mst/Ver765_B7LnP2TH.dat(채우기 마스터 + 추가 행),
resource_map_add.ndjson. 기기: flat_ko/ 와 mst_ko/ 에 넣는다.

실행: PYTHONIOENCODING=utf-8 python -X utf8 build/make_jp_noscene_stub.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'build'))
import make_en_story_fill as F  # noqa: E402  (build_master, cpk, cpk_inplace, key16, NC, decode_master)

MST = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
FILL = ROOT / 'build/out/en_story_fill'
NOSCENE = ROOT / 'build/engine_overlay/jp_rm_noscene.json'
OUT = ROOT / 'build/out/jp_noscene_stub'
SRC_SCENE = '737060701'          # template scene cpk stem (resource 397370602)
SRC_SCENE_ROW = '397370602'
SRC_MAP_ROW = '251101'           # its map
RESOURCE_VERSION = 766           # jp_versions.VERSION_BUMP: the client re-downloads the table
STUB = '999000101'               # same length as SRC_SCENE: the client reads <cpk stem>_event.bin
NOTICE = '(이 이야기의 장면 자료는 남아 있지 않습니다.)<wait=120>'
REST = '……<wait=40>'


def ndjson(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main():
    res = {str(r['Nnb20keZ']): r for r in ndjson(MST / 'F_RESOURCE_MAP_MST.ndjson')}
    res.update({str(r['Nnb20keZ']): r for r in ndjson(FILL / 'resource_map_add.ndjson')})
    missions = {str(r['qo3PECw6']): r for r in ndjson(MST / 'F_MISSION_MST.ndjson')}
    noscene = json.loads(NOSCENE.read_text(encoding='utf-8'))['missions']
    scene_row, map_row = res[SRC_SCENE_ROW], res[SRC_MAP_ROW]
    assert scene_row['pJ56sAEo'] == SRC_SCENE + '.cpk' and STUB + '.cpk' not in {r['pJ56sAEo'] for r in res.values()}

    # 1. stub scene cpk: replace the text, then rename the three inner files (same-length byte replace)
    orig = (F.JP_PACK / scene_row['pJ56sAEo']).read_bytes()
    pack = F.cpk.Cpk.load_bytes(orig, encoding='utf-8')
    infos = {e.filename: e for e in pack.file_infos()}
    text_name = SRC_SCENE + '_event_text.txt'
    rows = F.text_rows(pack.file_bytes(infos[text_name].toc_index))
    first = min(rows, key=lambda r: int(r[0]))[0]
    new_text = ''.join('%s,%s\n' % (rid, NOTICE if rid == first else REST) for rid, _sep, _body in rows)
    patched = F.cpk_inplace.patch(orig, {infos[text_name].full_path: new_text.encode('utf-8')}, encoding='utf-8')
    # The TOC is an XOR-masked @UTF table (cpk_inplace._crypt, position-keyed): unmask, swap the stem, mask again.
    ci, d = F.cpk_inplace, bytearray(patched)
    hdr, _hsize, _henc = ci._table(d, 0)
    toc_off = hdr.value(0, 'TocOffset')
    _toc, tsize, tenc = ci._table(d, toc_off)
    raw = bytes(d[toc_off + 16:toc_off + 16 + tsize])
    plain = ci._crypt(raw) if tenc else raw
    assert plain.count(SRC_SCENE.encode()) == len(infos), 'template stem count differs from the file count'
    plain = plain.replace(SRC_SCENE.encode(), STUB.encode())
    d[toc_off + 16:toc_off + 16 + tsize] = ci._crypt(plain) if tenc else plain
    stub = bytes(d)
    check = F.cpk.Cpk.load_bytes(stub, encoding='utf-8')
    names = sorted(e.filename for e in check.file_infos())
    assert names == sorted(n.replace(SRC_SCENE, STUB) for n in infos), names
    for e in check.file_infos():
        old = pack.file_bytes(infos[e.filename.replace(STUB, SRC_SCENE)].toc_index)
        new = check.file_bytes(e.toc_index)
        assert (new == new_text.encode('utf-8')) if e.filename.endswith('_event_text.txt') else (new == old), e.filename
    (OUT / 'flat_ko').mkdir(parents=True, exist_ok=True)
    (OUT / 'flat_ko' / (STUB + '.cpk')).write_bytes(stub)

    # 2. resource rows: every missing scene id -> stub; every 29xxxx-style map id with no row -> template map
    def line(rid, like, name):
        row = dict(like)
        row['Nnb20keZ'], row['pJ56sAEo'] = rid, name
        return json.dumps(row, ensure_ascii=False, separators=(',', ':'))

    add, kept_map = {}, 0
    for mid, info in sorted(noscene.items()):
        ids = [x for x in str(missions[mid].get('q4f9IdMs') or '').split(',') if x]
        has_map = False
        for rid in ids:
            if rid in info['scenes']:
                add[rid] = line(rid, scene_row, STUB + '.cpk')
            elif rid in res:
                has_map = has_map or res[rid]['dX0SkK3j'] == '200'
            elif rid[0] == '2' and len(rid) == 6:
                add[rid] = line(rid, map_row, map_row['pJ56sAEo'])
                has_map = True
            else:
                raise SystemExit('mission %s: unexpected id %s without a resource row' % (mid, rid))
        if not has_map:
            raise SystemExit('mission %s has no map id' % mid)
        kept_map += all(rid in res or rid in info['scenes'] for rid in ids)
    assert not set(add) & set(res)

    # 3. client master = fill master + the added rows
    token, key = F.NC.masters()[F.RESOURCE_TABLE]
    base = FILL / 'mst' / ('Ver765_%s.dat' % token)
    orig_lines, merged, _pad = F.build_master(base, add, F.key16(key))
    (OUT / 'mst').mkdir(parents=True, exist_ok=True)
    out_dat = OUT / 'mst' / ('Ver%d_%s.dat' % (RESOURCE_VERSION, token))
    out_dat.write_text('\n'.join(merged) + '\n', encoding='ascii')
    (OUT / 'resource_map_add.ndjson').write_text(
        ''.join(add[rid] + '\n' for rid in sorted(add, key=int)), encoding='utf-8')
    _mode, decoded = F.decode_master(out_dat.read_bytes(), key)
    got = {str(r[F.ID_KEY]): r for r in decoded}
    assert len(decoded) == len(orig_lines) + len(add) and set(orig_lines) <= set(merged)
    assert all(got[rid][F.FILE_KEY] == json.loads(add[rid])[F.FILE_KEY] for rid in add)
    scenes = sum(1 for v in add.values() if json.loads(v)['dX0SkK3j'] == '300')
    # The mission master is NOT touched. Two attempts on 2026-11-14 broke the device: pointing nodes at the
    # template map raised the MapScene::initialize notice, and MxLFKZ13 is the node's position on the area
    # map (changing it moved the nodes). Clearing on entry is done in the client hook instead.
    print('nodes %d: scene rows %d, map rows %d, nodes on their own map %d' %
          (len(noscene), scenes, len(add) - scenes, kept_map))
    print('master %d -> %d rows: %s' % (len(orig_lines), len(decoded), out_dat))
    print('stub %s (%d bytes), text rows %d' % (OUT / 'flat_ko' / (STUB + '.cpk'), len(stub), len(rows)))


if __name__ == '__main__':
    main()

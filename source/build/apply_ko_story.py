"""Korean story: rebuild the JP scene CPKs with the Korean translations.

Port of the Memorial BatchStoryPatcher (ffbe_offline_modfix/artifacts/chapter1-ko/BatchStoryPatcher.cs):
  *_event_text.txt  row id in the translation -> keep the leading <name=...>(<br>) tag and the trailing
                    <wait>/<keywait>/<invalid_touchwait> tags of the original, body = Korean with
                    [PAGE] -> <page><br>, newline -> <br>.  (BatchStoryPatcher dropped a trailing <keywait>.)
  *_event_teller.txt speaker id -> Korean name (from the translation rows' "name" for that id, else the name table).
Translations: translations/chapter1-ko/gt_output (Memorial) + translations/story-gap-ko/gt_output (2026-11-09).
Output: build/out/ko_story/flat_ko/<scene>.cpk (+ report.json). build/deploy_ko_story.py puts them on the device.

usage: python -I build/apply_ko_story.py [--archive D:/Downloads/ffbejpdata/ffbejpdata] [--only 111010101,...]
"""
import argparse, csv, json, re, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402

HANGUL = re.compile(r'[\uac00-\ud7a3]')
JP_CHAR = re.compile(r'[\u3040-\u30fa\u30fd-\u30ff\u4e00-\u9fff]')   # \ubc88\uc5ed \ud589\uc758 name\uc774 \uc77c\ubcf8\uc5b4\ub85c \ub0a8\uc544 \uc788\uc73c\uba74 \uc774\ub984\ud45c\ub85c \ub118\uae34\ub2e4
NAME_TAG = re.compile(r'^((?:<invalid_touchwait>)?[\r\n \t\u3000]*<name(?:_npc)?=([^>]+)>(?:<br>)?)', re.IGNORECASE)
TAIL = re.compile(r'((?:<wait=\d+>|<keywait>|<invalid_touchwait>)+)$', re.IGNORECASE)
OUT = ROOT / 'build/out/ko_story'


def load_translations():
    tr = {}
    for src in (ROOT / 'translations/chapter1-ko/gt_output', ROOT / 'translations/story-gap-ko/gt_output'):
        for f in sorted(src.glob('*.json')):
            try:
                rows = json.loads(f.read_text(encoding='utf-8-sig'))
            except Exception:
                continue
            d = tr.setdefault(f.stem.split('__', 1)[0].lower(), {})
            for r in rows:
                if isinstance(r, dict) and r.get('ffbe_id') is not None and HANGUL.search(r.get('message', '')):
                    d[str(r['ffbe_id'])] = r   # later sources (story-gap) fill what the Memorial set lacks
    return tr


def load_names():
    names = {}
    for p in (ROOT / 'translations/story-gap-ko/name替换表.csv',):
        for row in csv.reader(p.open(encoding='utf-8-sig')):
            if len(row) >= 2 and row[0] != 'SRC_Name' and row[1]:
                names[row[0]] = row[1]
    return names


def split_rows(data):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:   # 5 old scenes store Shift-JIS; Korean can only be written as UTF-8
        text = data.decode('cp932')
    nl = '\r\n' if '\r\n' in text else '\n'
    return text.split(nl), nl, data.startswith(b'\xef\xbb\xbf')


def join_rows(lines, nl, bom):
    b = nl.join(lines).encode('utf-8')
    return b'\xef\xbb\xbf' + b if bom else b


COMMA = '‚'   # rows are "id,text" and the client splits on every ASCII comma (no JP row has one in its text)


def ko_body(msg, page='<page><br>'):
    msg = msg.replace('\r', '').replace(',', COMMA)
    return msg.replace('[PAGE]\n', page).replace('[PAGE]', page).replace('\n', '<br>')


def patch_scene(data, rows, names, stats):
    try:
        pkg = cpk.Cpk.load_bytes(data, encoding='cp932')
        infos = list(pkg.file_infos())
        [i.full_path for i in infos]   # names decode lazily; fail here, not halfway through the rebuild
        renamed = []
    except RuntimeError:
        # File names that are not valid CP932 on Windows (143 Dropbox "競合コピー" junk copies, 3 real names):
        # read with those bytes as '_' (same byte length), rebuild, then put the original name bytes back.
        data, renamed = sanitize_names(data)
        pkg = cpk.Cpk.load_bytes(data, encoding='cp932')
        infos = list(pkg.file_infos())
    replace, speaker_ko = {}, {}
    for info in infos:
        if not info.filename.endswith('_event_text.txt'):
            continue
        lines, nl, bom = split_rows(pkg.file_bytes(info.toc_index))
        out = []
        for line in lines:
            rid, sep, body = line.partition(',')
            r = rows.get(rid.strip()) if sep else None
            if r is None:
                out.append(line); continue
            m = NAME_TAG.match(body)
            prefix = m.group(1) if m else ''
            if m and r.get('name') and not JP_CHAR.search(r['name']):
                speaker_ko.setdefault(m.group(2), r['name'])
            t = TAIL.search(body)
            page = '<keywait><page><br>' if '<keywait><page>' in body.lower() else '<page><br>'  # pause before a page turn
            out.append(rid + ',' + prefix + ko_body(r['message'], page) + (t.group(1) if t else ''))
            stats['rows'] += 1
        replace[info.full_path] = join_rows(out, nl, bom)
    for info in infos:
        if not info.filename.endswith('_event_teller.txt'):
            continue
        lines, nl, bom = split_rows(pkg.file_bytes(info.toc_index))
        out = []
        for line in lines:
            sid, sep, name = line.partition(',')
            ko = speaker_ko.get(sid.strip()) or names.get(name.strip()) if sep else None
            if ko and JP_CHAR.search(ko):   # 일본어 name은 버리고 이름표를 다시 본다
                ko = names.get(name.strip())
            if sep and ko:
                out.append(sid + ',' + ko.replace(',', COMMA)); stats['speakers'] += 1
            else:
                out.append(line)
        replace[info.full_path] = join_rows(out, nl, bom)
    if not replace:
        return None
    new = cpk.create(preset=cpk.CpkPreset.FILENAME_GROUP, align=pkg.alignment, encoding='cp932')
    for info in infos:
        new.add_bytes(replace.get(info.full_path, pkg.file_bytes(info.toc_index)), info.full_path, compress=False, id=None)
    out = new.save_bytes()
    return restore_names(out, renamed) if renamed else out


def utf_mask(buf):
    """CRI @UTF table mask (XOR stream; applying it twice restores the input)."""
    out, m = bytearray(buf), 0x655f
    for i in range(len(out)):
        out[i] ^= m & 0xff
        m = (m * 0x4115) & 0xffffffff
    return bytes(out)


def toc_strings(buf):
    """(table start, table size, masked?, plain table) of the TOC chunk."""
    i = buf.find(b'TOC ', 0x10)
    size = struct.unpack('<Q', buf[i + 8:i + 16])[0]
    t = bytes(buf[i + 16:i + 16 + size])
    masked = t[:4] != b'@UTF'
    return i + 16, size, masked, (utf_mask(t) if masked else t)


# whole CP932 double-byte characters: a trail byte can be ASCII (ソ = 83 5C, i.e. a '\' path separator)
CP932_MB = re.compile(rb'[\x81-\x9f\xe0-\xfc][\x40-\xfc]|[\x80-\xff]')


def blank(b):
    return CP932_MB.sub(lambda m: b'_' * len(m.group()), b)


def sanitize_names(data):
    buf = bytearray(data)
    start, size, masked, t = toc_strings(buf)
    so, do = struct.unpack('>II', t[12:20])
    t = bytearray(t); renamed = []
    for name in bytes(t[8 + so:8 + do]).split(b'\0'):
        if re.search(rb'[\x80-\xff]', name):
            renamed.append((blank(name), name))
    t[8 + so:8 + do] = blank(bytes(t[8 + so:8 + do]))
    buf[start:start + size] = utf_mask(bytes(t)) if masked else bytes(t)
    return bytes(buf), renamed


def restore_names(data, renamed):
    buf = bytearray(data)
    start, size, masked, t = toc_strings(buf)
    for placeholder, original in renamed:
        t = t.replace(b'\0' + placeholder + b'\0', b'\0' + original + b'\0', 1)
    buf[start:start + size] = utf_mask(t) if masked else t
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', default='D:/Downloads/ffbejpdata/ffbejpdata')
    ap.add_argument('--only', default='')
    args = ap.parse_args()
    tr, names = load_translations(), load_names()
    # 장면 teller 화자 이름도 이름표(name_sources + names_pass)를 쓴다. 기존 name替换表 CSV가 우선.
    sys.path.insert(0, str(ROOT / 'tools'))
    import name_coverage as NC
    known = dict(NC.name_sources()[0])
    for f in sorted((ROOT / 'translations/names-ko').glob('names_pass[0-9].json')):
        for jp, ko in json.loads(f.read_text(encoding='utf-8')).items():
            if HANGUL.search(ko) and not NC.LEFT_JP.search(ko):
                known.setdefault(jp, ko)
    known.update(names)
    names = known
    only = {s.strip().lower() for s in args.only.split(',') if s.strip()}
    dest = OUT / 'flat_ko'; dest.mkdir(parents=True, exist_ok=True)
    stats = {'scenes': 0, 'rows': 0, 'speakers': 0, 'bytes': 0, 'errors': []}
    for path in sorted(Path(args.archive).glob('*.cpk')):
        stem = path.stem.lower()
        if stem not in tr or (only and stem not in only):
            continue
        try:
            data = patch_scene(path.read_bytes(), tr[stem], names, stats)
        except Exception as ex:
            stats['errors'].append(f'{path.name}: {str(ex)[:100]}'); continue
        if data:
            (dest / path.name).write_bytes(data)
            stats['scenes'] += 1; stats['bytes'] += len(data)
    # Fixed speakers: <name=100000..100014> (Rain, Lasswell, Fina ...) are not in the scene tellers; the client
    # reads them from map_common.cpk common_teller.txt (MapDrawManager::initCommonData, group "common").
    common = Path(args.archive) / 'map_common.cpk'
    pkg = cpk.Cpk.load_bytes(common.read_bytes(), encoding='cp932')
    infos = list(pkg.file_infos()); replace = {}
    for info in infos:
        if info.filename == 'common_teller.txt':
            lines, nl, bom = split_rows(pkg.file_bytes(info.toc_index))
            out = []
            for line in lines:
                sid, sep, name = line.partition(',')
                ko = known.get(name.strip()) if sep else None
                out.append(sid + ',' + ko.replace(',', COMMA) if ko else line)
                stats['speakers'] += bool(ko)
            replace[info.full_path] = join_rows(out, nl, bom)
    # In place, NOT cpk.create: a rebuilt map_common.cpk lost its ID table (ITOC) and changed CpkMode 2 -> 3, and the
    # town map then drew nothing but the minimap (2026-11-09, docs/plans/2026-11-09-town-map.md).
    import cpk_inplace
    (dest / common.name).write_bytes(cpk_inplace.patch(common.read_bytes(), replace))
    stats['common_teller'] = 'map_common.cpk'
    (OUT / 'report.json').write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"scenes {stats['scenes']}, rows {stats['rows']}, speaker names {stats['speakers']}, "
          f"{stats['bytes'] / 1e6:.1f} MB, errors {len(stats['errors'])} -> {dest}")


if __name__ == '__main__':
    main()

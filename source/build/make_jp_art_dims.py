"""Record the stand-in images' real PNG size for the summon/event banner art feeder.

  build/frida/jp_offline.js swaps the decoded bytes of a stand-in JP image for a Global/ko banner when the
  decoded byte length matches an entry of jp_banner_art.json. Byte length is not unique: unit sprite sheets
  can be exactly as large as a banner (unit_anime_100032817.png = 118,699 B = gacha_20230821_FFBE_event_box_
  reprint_01.png; 14 clashes over 11 units, build/out/summon_sprite/rain_lasswell.md). The hook therefore also
  checks the incoming PNG IHDR (w,h) against the stand-in's real size, which this script records.

  inputs (read only)
    * build/engine_overlay/jp_banner_art.json   {"art": {stand-in name: {size, path|cpk, ...}}}
    * build/out/jp_offline/engine/static/**     decrypted Global art (cpk_extract / gacha_community / client/files)
    * build/out/seal_room/banner_files.tsv      JP spdungeon TOC (name, size, cpk) - size cross-check
    * build/out/jp_offline/engine/static/cpk_extract/common_lang/area/Ver11_spdungeon1_common/spd_bn_list_dummy.png
                                                JP spdungeon tile placeholder: 640x240 (native tile size)
  output
    * build/engine_overlay/jp_art_dims.json
        {"dims":   {<stand-in name>: {"w": 640, "h": 240, "src": "spd_bn_list"}},
         "by_size":{"<extract size>": {"w": 640, "h": 240, "name": <stand-in name>}}}

  Dims sources, in order:
    1. `spd_*bn_list*` stand-ins -> 640x240. A JP spdungeon tile banner is natively 640x240 (the layout slot and
       the common_lang placeholder above; confirmed for the 322 merged altema entries, 2026-11-12).
    2. A same-named decrypted file in the engine static tree -> that PNG's IHDR. JP and Global ship different
       revisions of the same banner (byte sizes differ) but the same layout slot, so this is a close estimate.
       When the guess is wrong the hook simply falls back to the Find name (an exact match allows the swap).
    3. Otherwise no entry: the hook requires the criFsBinder_Find name.
    * An entry whose size is shared by a NON-banner file (the unit CPK sprite sheets, 14 clashes over 11 units
      in build/out/summon_sprite/rain_lasswell.md) gets NO dims at all, so those loads can only ever swap on an
      exact Find name - a byte-length coincidence alone must not replace a sprite sheet.

  The JP CPK bodies are encrypted per file (cricodecs file_bytes() returns ciphertext, CRILAYLA bodies do not
  decode), so the TOC gives only sizes - exact dims cannot be read statically (build/out/vortex_season/
  first_entry_and_art.md 6.4, build/out/summon_sprite/rain_lasswell.md 1).

usage: python -I -X utf8 build/make_jp_art_dims.py [--dry-run]
"""
import argparse
import io
import json
import struct
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'build/engine_overlay'
BANNER_MAP = OVERLAY / 'jp_banner_art.json'
OUT = OVERLAY / 'jp_art_dims.json'
STATIC = ROOT / 'build/out/jp_offline/engine/static'
TOC = ROOT / 'build/out/seal_room/banner_files.tsv'
UNIT_CPKS = ROOT / 'build/out/challenge/unitcpk'
SPD_TILE = (640, 240)
# Names the image hook may legitimately see as stand-ins; anything else in a CPK is a non-banner image.
BANNERISH = ('gacha_', 'spd_', 'banner_', 'homeBanner', 'bn_')


def png_dims(path):
    try:
        with open(path, 'rb') as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w, h = struct.unpack('>II', head[16:24])
    return (w, h) if w > 0 and h > 0 else None


def static_index():
    """basename -> decrypted PNG path in the engine's Global static tree (first hit wins)."""
    idx = {}
    for sub in ('cpk_extract', 'gacha_community', 'client/files'):
        base = STATIC / sub
        if not base.is_dir():
            continue
        for p in base.rglob('*.png'):
            idx.setdefault(p.name, p)
    return idx


def toc_sizes():
    """JP spdungeon TOC: file name -> extract size (first row when a name repeats across CPKs)."""
    out = {}
    if not TOC.is_file():
        return out
    with open(TOC, encoding='utf-8') as fh:
        head = fh.readline()
        cols = head.rstrip('\n').split('\t')
        for line in fh:
            row = dict(zip(cols, line.rstrip('\n').split('\t')))
            name = row.get('file') or ''
            if name and name not in out:
                try:
                    out[name] = int(row.get('size') or 0)
                except ValueError:
                    pass
    return out


def non_banner_sizes():
    """PNG extract size -> names of non-banner images (unit sprite sheets) in the JP unit CPKs."""
    out = {}
    sys.path.insert(0, str(ROOT / 'tools/vendor'))
    try:
        from cricodecs import cpk
    except ImportError:
        print('WARN cricodecs missing; skipping the unit-sheet collision scan')
        return out
    seen = set()
    for path in sorted(UNIT_CPKS.glob('unit*.cpk')):
        try:
            c = cpk.Cpk.load_bytes(path.read_bytes())
            files = c.files
        except Exception as exc:  # noqa: BLE001 - a broken CPK must not stop the map
            print('WARN %s: %s' % (path.name, exc))
            continue
        for e in files:
            name = e.filename or ''
            if not name.lower().endswith('.png') or name.startswith(BANNERISH) or name in seen:
                continue
            seen.add(name)
            size = int(getattr(e, 'extract_size', 0) or getattr(e, 'file_size', 0) or 0)
            if size > 0:
                out.setdefault(size, []).append(name)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    art = json.loads(BANNER_MAP.read_text(encoding='utf-8')).get('art') or {}
    idx = static_index()
    spd_toc = toc_sizes()
    unit_png = non_banner_sizes()   # size -> non-banner PNG names in the JP unit CPKs

    dims, by_size = {}, {}
    stats = {'spd_bn_list': 0, 'global_same_name': 0, 'unknown': 0, 'collision_name_only': 0}
    size_mismatch, collisions = [], []
    for name, entry in sorted(art.items()):
        if not isinstance(entry, dict):
            continue
        size = entry.get('size')
        d = None
        if name.startswith('spd_') and 'bn_list' in name:
            d = SPD_TILE + ('spd_bn_list',)
            # cross-check: the JP TOC size for this stand-in must equal the size the hook keys on
            if size and name in spd_toc and spd_toc[name] != size:
                size_mismatch.append((name, size, spd_toc[name]))
        if d is None and name in idx:
            px = png_dims(idx[name])
            if px and px[0] > 0:
                d = px + ('global_same_name',)
        if d is None:
            if isinstance(size, int) and size in unit_png:
                collisions.append((name, size, unit_png[size], 'no dims'))
            stats['unknown'] += 1
            continue
        w, h, src = d
        if src == 'global_same_name' and isinstance(size, int) and size in unit_png:
            # The gacha dims above are an estimate; when the byte length is shared with a sprite sheet, keep no
            # dims so only the exact Find name can authorize the swap. (spd 640x240 is exact and stays.)
            collisions.append((name, size, unit_png[size], 'name-only'))
            stats['collision_name_only'] += 1
            continue
        stats[src] += 1
        dims[name] = {'w': w, 'h': h, 'src': src}
        if isinstance(size, int) and size > 0:
            if str(size) in by_size:
                print('WARN duplicate stand-in size %d: %s / %s' % (size, by_size[str(size)]['name'], name))
            by_size[str(size)] = {'w': w, 'h': h, 'name': name}

    payload = {
        'note': ('stand-in PNG sizes for build/frida/jp_offline.js banner feeding. Regenerate with '
                 'python -I -X utf8 build/make_jp_art_dims.py after jp_banner_art.json changes. '
                 'JP CPK bodies are encrypted; spd tiles are 640x240, gacha names use the Global same-name PNG. '
                 'Entries whose byte size collides with a unit sprite sheet are omitted on purpose.'),
        'version': 1,
        'stats': dict(stats, entries=len(art), recorded=len(dims)),
        'dims': dims,
        'by_size': by_size,
    }

    print('entries %d  recorded %d  (%s)' %
          (len(art), len(dims), ', '.join('%s=%d' % kv for kv in sorted(stats.items()))))
    print('unit-sheet size collisions: %d' % len(collisions))
    for name, size, others, how in collisions:
        print('  %d %s [%s] <= %s' % (size, name, how, ', '.join(others[:3]) + (' ...' if len(others) > 3 else '')))
    if size_mismatch:
        print('SIZE MISMATCH vs banner_files.tsv:', size_mismatch[:10])
    else:
        print('size cross-check vs banner_files.tsv: ok')
    if args.dry_run:
        print('dry run; not writing', OUT)
        return
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=0, sort_keys=True) + '\n', encoding='utf-8')
    print('wrote', OUT)


if __name__ == '__main__':
    main()

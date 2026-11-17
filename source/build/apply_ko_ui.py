"""Korean UI: rebuild the JP APK's assets/cpk/common.cpk and resources.cpk with Korean text and sprites.

Port of the Memorial Edition script (ffbe_offline_modfix/scratch/deploy_full_korean_ui.py), which patched the
same JP client CPKs. Inputs (translations/ui-ko/):
  text_ko_memorial.csv  Memorial Korean text_ja.csv (keyed rows; 2,358 of the 2,372 JP 11.0.0 keys)
  text_ko_extra.csv     JP 11.0.0 keys the Memorial file lacks (translated here)
  buff_desc_ko.json     BUFF_DESC_<line> -> Korean (buff_desc.txt lines)
  sprites/official/     official Korean UI sprites + official_index.json (sprite, plist path)
  sprites/custom/       Memorial hand-made Korean sprites (placed wherever a plist has a frame of that name)
Output: build/out/ko_ui/{common,resources}.cpk (+ report.json); jp_offline_build.py copies them into the APK.
libgame.so is not touched (the Memorial script's libgame string patches are not ported).

usage: python -I build/apply_ko_ui.py
"""
import hashlib, io, json, os, plistlib, re, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402
sys.path.insert(0, str(ROOT / 'tools'))
import cpk_inplace  # noqa: E402

SRC = ROOT / 'build/out/jp_offline/dec/assets/cpk'
KO = ROOT / 'translations/ui-ko'
OUT = ROOT / 'build/out/ko_ui'
COMMA = '‚'
# Official Korean art for these has no text but is much fainter than the JP 11.0.0 art (alpha 0.8 -> 0.4, or ~0),
# which made the dialog/window panels (560px wide caption/section/line_under) and list bars disappear. Keep the JP originals.
KEEP_JP = {
    'window_caption.png', 'window_section.png', 'window_line_under.png', 'element_bg.png', 'title_bg.png',
    'menu_option_border.png', 'bottomline.png', 'menu_line.png', 'line_silver.png', 'positionmark_bg.png',
    'gradation.png', 'common_rb_frame_eff.png', 'windowR_headlineBg.png',
    'commonR_btnH90_bg-navy-off.png', 'commonR_btnM_bg-navy-off.png', 'commonR_btnS_bg-navy-off.png',
    'commonR_btnSquare-on.png', 'commonR_btnSquare-M.png', 'commonR_btnSquare-L.png',
    'commonR_btnDiamondM-on.png', 'commonR_btnDiamondL-on.png',
}
BAD_STATES_KO = ['독', '암흑', '수면', '침묵', '마비', '혼란', '질병', '석화', '전투 불능']


def keyed(path):
    rows = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, sep, value = line.partition(',')
        if sep and key:
            rows[key] = value
    return rows


def korean_text(original: bytes, ko: dict, report):
    bom = original.startswith(b'\xef\xbb\xbf')
    text = original.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    out, replaced, kept = [], 0, []
    for line in text.split(newline):
        key, sep, _ = line.partition(',')
        if sep and key in ko:
            val = ko[key]
            body = val.rstrip(',')
            # the client splits rows on every ASCII comma: keep only the row-terminating ones, use U+201A inside the text
            out.append(key + ',' + body.replace(',', COMMA) + val[len(body):]); replaced += 1
        else:
            out.append(line)
            if sep and key:
                kept.append(key)
    report['text_rows_replaced'] = replaced
    report['text_rows_kept_japanese'] = kept
    data = newline.join(out).encode('utf-8')
    return (b'\xef\xbb\xbf' + data) if bom else data


def parse_rect(text):
    n = [int(float(x)) for x in re.findall(r'-?\d+(?:\.\d+)?', text)]
    return n[0], n[1], n[2], n[3]


def frame_info(meta):
    if 'textureRect' in meta:
        return parse_rect(meta['textureRect']), bool(meta.get('textureRotated', False))
    if 'frame' in meta:
        return parse_rect(meta['frame']), bool(meta.get('rotated', False))
    return tuple(int(meta.get(k, 0)) for k in ('x', 'y', 'width', 'height')), False


def patch_atlas(atlas: Image.Image, frames: dict, sprites: dict, report_list):
    atlas = atlas.convert('RGBA')
    for name, path in sprites.items():
        (x, y, w, h), rotated = frame_info(frames[name])
        im = Image.open(path).convert('RGBA')
        if im.size != (w, h):
            report_list.append(f'{name}: resized {im.size} -> {(w, h)}')
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        if rotated:  # cocos2d-x/TexturePacker store rotated frames turned 90 degrees clockwise
            im = im.rotate(-90, expand=True)
        atlas.paste(Image.new('RGBA', im.size, (0, 0, 0, 0)), (x, y))
        if path.parent.name == 'labels':
            atlas.paste(im, (x, y))
        else:
            atlas.paste(im, (x, y), im)
    return atlas


def main():
    ko = keyed(KO / 'text_ko_memorial.csv')
    ko.update(keyed(KO / 'text_ko_extra.csv'))
    buff_ko = json.loads((KO / 'buff_desc_ko.json').read_text(encoding='utf-8'))
    extra = KO / 'buff_desc_extra_ko.json'
    if extra.exists():
        buff_ko.update({key: row['translation'] for key, row in json.loads(extra.read_text(encoding='utf-8')).items()})
    official = json.loads((KO / 'sprites/official_index.json').read_text(encoding='utf-8'))
    custom = sorted((KO / 'sprites/custom').glob('*.png'))
    labels = KO / 'sprites/labels_manifest.json'
    if labels.exists():
        for name, entry in json.loads(labels.read_text(encoding='utf-8')).items():
            path = KO / 'sprites/labels' / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], name
            custom.append(path)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'sprites_patched': {}, 'sprites_missing': [], 'resized': []}

    cpks = {}
    for name in ('common', 'resources'):
        c = cpk.Cpk.load_bytes((SRC / f'{name}.cpk').read_bytes(), encoding='cp932')
        infos = list(c.file_infos())
        cpks[name] = (c, infos, {i.full_path: i for i in infos})

    # Sprite plan: (cpk, plist full path) -> {frame name: image path}
    plists = {}  # (cpk, plist path) -> frames dict
    for cname, (c, infos, by_path) in cpks.items():
        for info in infos:
            if info.full_path.endswith('.plist'):
                try:
                    pl = plistlib.loads(c.file_bytes(info.toc_index))
                except Exception:
                    continue
                if isinstance(pl, dict) and isinstance(pl.get('frames'), dict):
                    plists[(cname, info.full_path)] = pl
    plan = {}
    for row in official:
        if row['sprite'] in KEEP_JP:
            continue
        hits = [k for k in plists if k[1] == row['plist'] and row['sprite'] in plists[k]['frames']]
        if not hits:
            report['sprites_missing'].append(row['plist'] + ':' + row['sprite']); continue
        for k in hits:
            plan.setdefault(k, {})[row['sprite']] = KO / row['file']
    for path in custom:
        hits = [k for k, pl in plists.items() if path.name in pl['frames']]
        if not hits:
            report['sprites_missing'].append('custom:' + path.name)
        for k in hits:
            plan.setdefault(k, {})[path.name] = path

    for cname, (c, infos, by_path) in cpks.items():
        replace = {}
        for (pc, plist_path), sprites in plan.items():
            if pc != cname:
                continue
            pl = plists[(pc, plist_path)]
            tex = (pl.get('metadata') or {}).get('textureFileName') or Path(plist_path).with_suffix('.png').name
            png_path = str(Path(plist_path).parent / tex).replace('\\', '/')
            if png_path not in by_path:
                report['sprites_missing'].append(f'{plist_path}: atlas {png_path} not found'); continue
            atlas = Image.open(io.BytesIO(c.file_bytes(by_path[png_path].toc_index)))
            new = patch_atlas(atlas, pl['frames'], sprites, report['resized'])
            buf = io.BytesIO(); new.save(buf, format='PNG')
            replace[png_path] = buf.getvalue()
            report['sprites_patched'][png_path] = len(sprites)
        if cname == 'common':
            for info in infos:
                if info.filename in ('text_ja.csv', 'text_en.csv'):
                    replace[info.full_path] = korean_text(c.file_bytes(info.toc_index), ko, report)
                elif info.filename == 'buff_desc.txt':
                    lines = c.file_bytes(info.toc_index).decode('utf-8-sig').splitlines()
                    ko_lines = [buff_ko.get(f'BUFF_DESC_{i}') or line for i, line in enumerate(lines)]
                    replace[info.full_path] = ('\r\n'.join(ko_lines) + '\r\n').encode('utf-8-sig')
                    report['buff_desc'] = f'{sum(1 for i in range(len(lines)) if f"BUFF_DESC_{i}" in buff_ko)}/{len(lines)}'
                elif info.filename == 'bad_state_desc.txt':
                    lines = c.file_bytes(info.toc_index).decode('utf-8-sig').splitlines()
                    if len(lines) == len(BAD_STATES_KO):
                        replace[info.full_path] = ('\r\n'.join(BAD_STATES_KO) + '\r\n').encode('utf-8-sig')
                        report['bad_state_desc'] = 'replaced'
                    else:
                        report['bad_state_desc'] = f'kept ({len(lines)} lines, expected {len(BAD_STATES_KO)})'
        # debug bisect: KO_UI_ONLY=repack (no changes) | text (text files only) | sprites (atlases only)
        only = os.environ.get('KO_UI_ONLY')
        if only == 'repack':
            replace = {}
        elif only == 'text':
            replace = {k: v for k, v in replace.items() if not k.endswith('.png')}
        elif only == 'sprites':
            replace = {k: v for k, v in replace.items() if k.endswith('.png')}
        # patch in place: a cpk.create() rebuild renumbers file IDs and drops the GTOC group list, which made
        # every dialog/window panel disappear in game (2026-11-09). tools/cpk_inplace.py keeps the original layout.
        new_bytes = cpk_inplace.patch((SRC / f'{cname}.cpk').read_bytes(),
                                      {k.replace(chr(92), '/'): v for k, v in replace.items()})
        out = OUT / f'{cname}.cpk'
        out.write_bytes(new_bytes)
        print(cname, '->', out, out.stat().st_size, 'bytes;', len(replace), 'files replaced')

    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('text rows replaced', report.get('text_rows_replaced'), '(kept JP:', len(report.get('text_rows_kept_japanese', [])), ')',
          'buff', report.get('buff_desc'), 'bad_state', report.get('bad_state_desc'),
          'sprites', sum(report['sprites_patched'].values()), 'in', len(report['sprites_patched']), 'atlases;',
          'missing', len(report['sprites_missing']), 'resized', len(report['resized']))


if __name__ == '__main__':
    main()

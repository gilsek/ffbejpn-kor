"""영문판 APK 한국어 CPK(assets/cpk/ko/sd/resources/resources_pretutorial.cpk) 스프라이트 목록.

usage: python -I -X utf8 tools/catalog_gl_ko_sprites.py [--jp-apk build/out/jp_shop/q1-apk/base.apk]
입력: inputs/global900_ko_cpk/ (list_cpk.py로 푼 것, plist는 CRILAYLA 압축)
출력: build/out/gl_ko/frames/<atlas>/<frame>.png, build/out/gl_ko/catalog.json,
      build/out/gl_ko/sheet_<atlas>_<n>.png (번호 붙인 확인용 시트)
catalog 항목: atlas, frame, size, jp(같은 이름 프레임의 JP 아틀라스·크기 목록), pinned(labels_manifest에 있음)
"""
import argparse, io, json, plistlib, sys, types, zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
KO = ROOT / 'inputs/global900_ko_cpk'
OUT = ROOT / 'build/out/gl_ko'
sys.path.insert(0, str(ROOT / 'build'))
import apply_ko_ui as U  # noqa: E402

_src = (ROOT / 'tools/crilayla_probe.py').read_text(encoding='utf-8').split('\nentries = cpk_entries')[0]
_C = types.ModuleType('crilayla')
exec(compile(_src.split('if __name__')[0], 'crilayla_probe', 'exec'), _C.__dict__)


def load_plist(raw):
    return plistlib.loads(_C.crilayla(raw) if raw[:8] == b'CRILAYLA' else raw)


def crops(pl, atlas):
    for name, meta in pl['frames'].items():
        (x, y, w, h), rot = U.frame_info(meta)
        im = atlas.crop((x, y, x + (h if rot else w), y + (w if rot else h)))
        yield name, (im.rotate(90, expand=True) if rot else im)


def jp_frames(apk):
    out = {}
    with zipfile.ZipFile(apk) as z:
        for cname in ('common', 'resources'):
            c = U.cpk.Cpk.load_bytes(z.read(f'assets/cpk/{cname}.cpk'), encoding='cp932')
            for info in c.file_infos():
                if not info.full_path.endswith('.plist'):
                    continue
                try:
                    pl = plistlib.loads(c.file_bytes(info.toc_index))
                except Exception:  # noqa: BLE001
                    continue
                for name, meta in pl.get('frames', {}).items():
                    try:
                        (_, _, w, h), _ = U.frame_info(meta)
                    except Exception:  # noqa: BLE001
                        continue
                    out.setdefault(name, []).append({'atlas': f'{cname}:{info.full_path}', 'size': [w, h]})
    return out


def sheet(items, path, scale=1):
    font = ImageFont.truetype('malgun.ttf', 12)
    cols, cell = 6, 220
    rows = -(-len(items) // cols)
    sh = Image.new('RGB', (cols * cell, rows * cell), (40, 40, 50))
    d = ImageDraw.Draw(sh)
    for i, (n, im) in enumerate(items):
        x, y = i % cols * cell, i // cols * cell
        t = im.copy()
        t.thumbnail((cell - 10, cell - 30))
        bg = Image.new('RGBA', t.size, (40, 40, 50, 255))
        bg.alpha_composite(t.convert('RGBA'))
        sh.paste(bg.convert('RGB'), (x + 5, y + 22))
        d.text((x + 4, y + 3), f'#{n}', fill=(255, 255, 0), font=font)
    sh.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jp-apk', type=Path, default=ROOT / 'build/out/jp_shop/q1-apk/base.apk')
    a = ap.parse_args()
    jp = jp_frames(a.jp_apk)
    pinned = json.loads((ROOT / 'translations/ui-ko/sprites/labels_manifest.json').read_text(encoding='utf-8'))
    cat, no = [], 0
    for pl_path in sorted(KO.rglob('*.plist')):
        atlas_png = pl_path.with_suffix('.png')
        if not atlas_png.exists():
            continue
        rel = pl_path.relative_to(KO).as_posix()
        pl = load_plist(pl_path.read_bytes())
        atlas = Image.open(atlas_png).convert('RGBA')
        items = []
        for name, im in sorted(crops(pl, atlas)):
            no += 1
            d = OUT / 'frames' / Path(rel).stem
            d.mkdir(parents=True, exist_ok=True)
            im.save(d / name)
            cat.append({'no': no, 'atlas': rel, 'frame': name, 'size': list(im.size),
                        'jp': jp.get(name, []), 'pinned': name in pinned})
            items.append((no, im))
        for k in range(0, len(items), 36):
            sheet(items[k:k + 36], OUT / f'sheet_{Path(rel).stem}_{k // 36}.png')
    (OUT / 'catalog.json').write_text(json.dumps(cat, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    same = sum(1 for r in cat if any(j['size'] == r['size'] for j in r['jp']))
    print('frames', len(cat), 'JP 같은 이름', sum(1 for r in cat if r['jp']), 'JP 같은 이름·크기', same)


if __name__ == '__main__':
    main()

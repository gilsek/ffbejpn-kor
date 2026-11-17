"""Export every not-yet-Korean atlas sprite as an individual PNG (original size) for OCR + image translation.

out: build/out/sprite_work/in/<sprite>.png, manifest.json (name, atlas, w, h), glossary.tsv (ja<TAB>ko seed).
usage: python -E -P tools/export_sprites_for_ocr.py
"""
import io, json, plistlib, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from sprite_contact_sheets import SRC, done, frame, MIN_SIDE  # noqa: E402
from cricodecs import cpk  # noqa: E402

OUT = ROOT / 'build/out/sprite_work'


def main():
    (OUT / 'in').mkdir(parents=True, exist_ok=True)
    manifest, seen = [], {}
    for cname in ('common.cpk', 'resources.cpk'):
        pkg = cpk.Cpk.load_bytes((SRC / cname).read_bytes(), encoding='cp932')
        files = {i.full_path.replace('\\', '/'): i for i in pkg.file_infos()}
        for path in sorted(files):
            if not path.endswith('.plist') or path[:-6] + '.png' not in files:
                continue
            pl = plistlib.loads(pkg.file_bytes(files[path].toc_index))
            atlas = Image.open(io.BytesIO(pkg.file_bytes(files[path[:-6] + '.png'].toc_index))).convert('RGBA')
            for sname, meta in sorted(pl.get('frames', {}).items()):
                x, y, w, h, rot = frame(meta)
                if sname in done or (min(w, h) < MIN_SIDE and max(w, h) < 60):
                    continue
                if sname in seen:
                    print('dup name', sname, seen[sname], path); continue
                seen[sname] = path
                img = atlas.crop((x, y, x + (h if rot else w), y + (w if rot else h)))
                if rot:
                    img = img.rotate(90, expand=True)
                img.save(OUT / 'in' / sname)
                manifest.append({'name': sname, 'atlas': cname + ':' + path, 'w': img.width, 'h': img.height})
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    # glossary seed from the eyeballed records (ja -> ko)
    g = {}
    rec = ROOT / 'build/out/sprite_targets/records.txt'
    if rec.exists():
        for line in rec.read_text(encoding='utf-8').splitlines():
            p = line.split('|')
            if len(p) == 4 and p[2] and p[3]:
                g.setdefault(p[2].strip(), p[3].strip())
    (OUT / 'glossary.tsv').write_text(''.join(f'{k}\t{v}\n' for k, v in sorted(g.items())), encoding='utf-8')
    print({'sprites': len(manifest), 'glossary': len(g)})


if __name__ == '__main__':
    main()

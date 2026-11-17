"""Extract local/device-copied evidence art to a fresh directory and create contact sheets."""
import io
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/vendor'))
from cricodecs import cpk
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
out = root / 'build/out/jp_offline/gacha'
index = json.loads((root / 'build/jp_gacha_art.json').read_text(encoding='utf-8'))
unmatched = json.loads((out / 'report.json').read_text(encoding='utf-8'))['unmatched_jp']
dest = out / (sys.argv[1] if len(sys.argv) > 1 else 'art-evidence')
dest.mkdir(exist_ok=False)
archives = {}
for filename in sorted({index[n]['cpk'] for n in unmatched}):
    archives[filename] = cpk.Cpk.load_bytes((out / 'source-cpk' / (filename + '.cpk')).read_bytes())
diagnostics = []
for page in range(0, len(unmatched), 8):
    sheet = Image.new('RGB', (1200, 4 * 230), '#eee')
    draw = ImageDraw.Draw(sheet)
    for offset, name in enumerate(unmatched[page:page+8]):
        archive = archives[index[name]['cpk']]
        i = next(i for i, e in enumerate(archive.files) if e.filename == name)
        data = archive.file_bytes(archive.files[i].toc_index)
        x, y = (offset % 2) * 600, (offset // 2) * 230
        draw.text((x+5, y+5), f'{page+offset+1}. {name}', fill='black')
        try:
            im = Image.open(io.BytesIO(data)).convert('RGB')
        except Image.UnidentifiedImageError:
            diagnostics.append({'file': name, 'status': 'not_decoded', 'bytes': len(data), 'first16': data[:16].hex()})
            draw.text((x+5, y+30), 'Not decoded; no visual identity conclusion', fill='black')
            continue
        (dest / name).write_bytes(data)
        im.thumbnail((590, 200))
        sheet.paste(im, (x, y+25))
        diagnostics.append({'file': name, 'status': 'decoded'})
    sheet.save(dest / f'contact-{page//8+1}.jpg')
(dest / 'diagnostics.json').write_text(json.dumps(diagnostics, indent=1), encoding='utf-8')
print(json.dumps({'output': str(dest), 'decoded': sum(d['status'] == 'decoded' for d in diagnostics), 'not_decoded': sum(d['status'] != 'decoded' for d in diagnostics)}))

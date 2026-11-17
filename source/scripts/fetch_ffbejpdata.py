# Download archive.org item ffbejpdata (resumable, size-verified, small master files first).
import json, os, sys, urllib.request, urllib.parse, subprocess
from concurrent.futures import ThreadPoolExecutor
ITEM = 'ffbejpdata'
out = sys.argv[1]
meta = json.load(urllib.request.urlopen(f'https://archive.org/metadata/{ITEM}', timeout=120))
files = [f for f in meta['files'] if f.get('source') == 'original' and f.get('size')]
json.dump(meta, open(os.path.join(out, '_metadata.json'), 'w', encoding='utf-8'))
order = {'.i': 0, '.dat': 0, '.sqlite': 0, '.xml': 0, '.cpk': 1, '.acb': 2, '.usm': 3}
files.sort(key=lambda f: (order.get(os.path.splitext(f['name'])[1].lower(), 1), f['name']))
def get(f):
    name, size = f['name'], int(f['size'])
    dst = os.path.join(out, name)
    for _ in range(6):
        if os.path.exists(dst) and os.path.getsize(dst) == size:
            return name, True
        url = f'https://archive.org/download/{ITEM}/' + urllib.parse.quote(name)
        subprocess.run(['curl', '-sS', '-L', '-C', '-', '--retry', '3', '-m', '3600', '-o', dst, url])
    return name, os.path.exists(dst) and os.path.getsize(dst) == size
bad = []
with ThreadPoolExecutor(4) as ex:
    for i, (n, ok) in enumerate(ex.map(get, files), 1):
        if not ok: bad.append(n)
        if i % 100 == 0 or not ok: print(i, len(files), 'bad' if not ok else '', n, flush=True)
print('DONE failed:', bad, flush=True)

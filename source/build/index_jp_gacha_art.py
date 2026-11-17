"""Index the JP gacha/banner CPKs (names + extracted sizes) -> build/jp_gacha_art.json.
usage: python -I build/index_jp_gacha_art.py <dir with gacha1..6.cpk, banner1/2.cpk>
The CPKs are the ones the JP client reads from /data/local/tmp/ffbe/flat/ (pulled with adb)."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk
src = Path(sys.argv[1])
out = {}
for f in ['gacha%d' % i for i in range(1, 7)] + ['banner1', 'banner2', 'banner_home1']:
    p = src / (f + '.cpk')
    if not p.is_file():
        print('missing', p); continue
    c = cpk.Cpk.load_bytes(p.read_bytes())
    for e in c.files:
        out[e.filename] = {'cpk': f, 'size': int(getattr(e, 'extract_size', 0) or getattr(e, 'file_size', 0) or 0)}
(ROOT / 'build/jp_gacha_art.json').write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding='utf-8')
print(len(out), 'entries ->', ROOT / 'build/jp_gacha_art.json')

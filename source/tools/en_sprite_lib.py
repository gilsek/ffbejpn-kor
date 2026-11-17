"""영문판 APK(ffbe-memorial-english-v208) CPK에서 같은 이름의 UI 프레임을 꺼내는 도우미 (2026-11-10)."""
import io, plistlib, re, sys, types
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from cricodecs import cpk  # noqa: E402
_src = (ROOT / 'tools/crilayla_probe.py').read_text(encoding='utf-8').split('\nentries = cpk_entries')[0]
_C = types.ModuleType('crilayla'); exec(compile(_src.split('if __name__')[0], 'crilayla_probe', 'exec'), _C.__dict__)
EN_DIR = ROOT.parent / 'ffbe_offline_modfix/artifacts/korean-display-test/english-decoded/assets/cpk'
JP_DIR = ROOT / 'build/out/jp_offline/dec/assets/cpk'
def _un(raw): return _C.crilayla(raw) if raw[:8] == b'CRILAYLA' else raw
class Atlases:
    """frames[(cpk, plist)] -> {frame name: PIL image}; by_name[name] -> [(cpk, plist)]"""
    def __init__(self, directory, cpks=('common', 'resources')):
        self.frames, self.by_name = {}, {}
        for n in cpks:
            c = cpk.Cpk.load_bytes((Path(directory) / f'{n}.cpk').read_bytes(), encoding='cp932')
            by = {i.full_path: i for i in c.file_infos()}
            for path, info in by.items():
                if not path.endswith('.plist'): continue
                try: pl = plistlib.loads(_un(c.file_bytes(info.toc_index)))
                except Exception: continue
                if not isinstance(pl.get('frames'), dict): continue
                tex = (pl.get('metadata') or {}).get('textureFileName') or (pl.get('texture') or {}).get('realTextureFileName')
                tp = [k for k in by if k.endswith('/' + tex)] if tex else []
                if not tp: continue
                try: at = Image.open(io.BytesIO(_un(c.file_bytes(by[tp[0]].toc_index)))).convert('RGBA')
                except Exception: continue
                d = {}
                for name, f in pl['frames'].items():
                    x, y, w, h = [int(v) for v in re.findall(r'-?\d+', f.get('frame') or f.get('textureRect'))]
                    rot = f.get('rotated') or f.get('textureRotated')
                    im = at.crop((x, y, x + (h if rot else w), y + (w if rot else h)))
                    d[name] = im.transpose(Image.ROTATE_90) if rot else im
                    self.by_name.setdefault(name, []).append((n, path))
                self.frames[(n, path)] = d
    def get(self, name):
        return [(k, self.frames[k][name]) for k in self.by_name.get(name, [])]

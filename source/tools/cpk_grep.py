"""Search decompressed text-ish contents of CPKs. usage: cpk_grep.py needle -- cpk..."""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
from cricodecs import cpk
i = sys.argv.index('--'); needles = sys.argv[1:i]
for p in sys.argv[i+1:]:
    c = cpk.Cpk.load_bytes(open(p, 'rb').read())
    for e in c.files:
        if e.filename.rsplit('.',1)[-1].lower() not in ('csv','txt','plist','json','xml','html'): continue
        try: b = c.file_bytes(e.toc_index)
        except Exception as ex: print('ERR', e.full_path, ex); continue
        for n in needles:
            for enc in ('utf-8','cp932'):
                k = n.encode(enc)
                if k in b:
                    t = b.decode(enc, 'replace'); j = t.find(n)
                    print(Path(p).name, e.full_path, enc, repr(t[max(0,j-80):j+120]))

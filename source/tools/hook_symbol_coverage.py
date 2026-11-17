import sys,re,zipfile,glob,os
sys.stdout.reconfigure(encoding='utf-8')
n11=open('inputs/jp1100/arm64/lib/arm64-v8a/libgame.so','rb').read()
n9=zipfile.ZipFile(r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix\downloads\FINAL+FANTASY++BRAVE+EXVIUS_9.0.0_APKPure.apk').read('lib/arm64-v8a/libgame.so')
S=r'C:\Users\USER\Documents\Projects\ffbe_offline_modfix\upstream\source\exvius'
syms={}; txt=''
for f in glob.glob(S+'/*.js'):
    if 'test_' in os.path.basename(f): continue
    t=open(f,encoding='utf-8').read(); txt+=t
    for m in set(re.findall(r"'(_Z[A-Za-z0-9_]+)'",t)): syms.setdefault(m,set()).add(os.path.basename(f))
print('symbols referenced by hooks',len(syms))
m9=[s for s in syms if s.encode() not in n9]; m11=[s for s in syms if s.encode() not in n11]
print('missing in 9.0.0',len(m9),'missing in 11.0.0',len(m11))
for s in m11[:40]: print(' ',s,sorted(syms[s]))
print('hardcoded offsets',len(re.findall(r'base\.add\((0x[0-9a-f]+)\)',txt)))

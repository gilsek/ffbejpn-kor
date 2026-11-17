import sys,plistlib,io,re
from pathlib import Path
sys.path.insert(0,str(Path('build').resolve()))
import apply_ko_ui as U
from PIL import Image
c=U.cpk.Cpk.load_bytes(Path('build/out/ko_ui/resources.cpk').read_bytes(),encoding='cp932')
files={i.full_path:i for i in c.file_infos()}
want={'image/ui/home/home.plist':['homeBanner_01_blank.png','homeBanner_03_blank.png','homeBanner_04_blank.png','home_icon_news.png','home_submenu_mail_off.png','home_submenu_mission_off.png'],
'image/ui/home/mypage.plist':['mypage_world1.png','mypage_icon_news1.png']}
out=Path('build/out/ko_ui_generated/home7/src')
for pl,names in want.items():
    d=plistlib.loads(c.file_bytes(files[pl].toc_index))
    base=pl.rsplit('/',1)[0]+'/'+d['metadata']['textureFileName']
    print(pl,base,base in files)
    atlas=Image.open(io.BytesIO(c.file_bytes(files[base].toc_index))).convert('RGBA')
    for n in names:
        f=d['frames'][n]; x,y,w,h=map(int,re.findall(r'-?\d+',f['textureRect']))
        if f['textureRotated']: w,h=h,w
        im=atlas.crop((x,y,x+w,y+h))
        if f['textureRotated']: im=im.rotate(90,expand=True)
        im.save(out/n); print(n,im.size)

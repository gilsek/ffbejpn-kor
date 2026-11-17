"""영문판 같은 이름 UI 프레임을 translations/ui-ko/sprites/labels/ 로 가져오고 labels_manifest.json 에 고정한다.

usage: python -I -X utf8 tools/import_en_sprites.py name1.png,name2.png ...   (또는 --file 목록.json: [{"name":..,"ja":..}])
일본어판 같은 이름 프레임과 크기가 같은 영문판 프레임만 가져온다(같은 plist 우선). 이미 고정된 이름은 건너뛴다.
"""
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import en_sprite_lib as L
ROOT = L.ROOT; LAB = ROOT / 'translations/ui-ko/sprites/labels'; MAN = ROOT / 'translations/ui-ko/sprites/labels_manifest.json'
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('names', nargs='?'); ap.add_argument('--file'); a = ap.parse_args()
    items = ([{'name': n} for n in a.names.split(',')] if a.names else json.loads(Path(a.file).read_text(encoding='utf-8')))
    en, jp = L.Atlases(L.EN_DIR), L.Atlases(L.JP_DIR)
    man = json.loads(MAN.read_text(encoding='utf-8')); done = []
    for it in items:
        n = it['name']
        if n in man: print('skip pinned', n); continue
        j = jp.get(n); e = en.get(n)
        pick = None
        for (k, im) in e:
            for (jk, jm) in j:
                if im.size == jm.size and (k == jk or pick is None): pick = im
        if pick is None: print('no same-size', n); continue
        LAB.mkdir(exist_ok=True); p = LAB / n; pick.save(p)
        man[n] = {'translation': it.get('ja') and f"EN<-{it['ja']}" or 'EN', 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                  'source': '영문판 ffbe-memorial-english-v208 resources/common.cpk 같은 이름 프레임 (영어 그대로, 사용자 결정 2026-11-10)'}
        done.append(n)
    MAN.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8'); print('imported', len(done)); print(','.join(done))
main()

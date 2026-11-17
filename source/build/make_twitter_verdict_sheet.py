"""twitter_verdict.jsonl 전체를 한 장짜리 HTML 시트로 만든다(배너 썸네일은 로컬 원본을 file:// 로 참조).

usage: python -I -X utf8 build/make_twitter_verdict_sheet.py
writes build/out/jp_offline/gacha_jp/twitter_verdict_sheet.html
"""
import json, os, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'build/out/jp_offline/gacha_jp'
SRC = Path('D:/Archive/gallery-dl/twitter/FFRS_JP')

content = {}
for name in os.listdir(SRC):
    if name.endswith('.json'):
        parts = name[:-5].split('_')
        if len(parts) >= 2:
            try:
                content[parts[1]] = json.loads((SRC / name).read_text(encoding='utf-8')).get('content') or ''
            except Exception:
                pass

full = {}
for fn in ('twitter_identify.jsonl', 'twitter_identify_agy.jsonl'):
    p = D / fn
    if p.exists():
        for l in p.read_text(encoding='utf-8').splitlines():
            if l.strip():
                r = json.loads(l)
                full[r['file']] = r

rows = []
for l in (D / 'twitter_verdict.jsonl').read_text(encoding='utf-8').splitlines():
    r = json.loads(l)
    ev = {}
    for e in r['evidence']:
        ev.setdefault(e['file'], set()).add(e['type'])
    rows.append({
        'id': r['id'], 'd': r['date'] or '', 'v': r['verdict'], 'r': r['reason'], 'p': r.get('phase') or '',
        't': content.get(r['id'], ''),
        'g': [[g['name'] or '', g.get('type') or '', g.get('start_iso') or '', g.get('end_iso') or '', g['units']]
              for g in r['text_gachas']],
        'i': [[im['file'], im['kind'], im['title'], im['unit_names'], (full.get(im['file']) or {}).get('series') or '',
               sorted(ev.get(im['file'], []))] for im in r['images']],
    })
rows.sort(key=lambda x: (x['d'], x['id']))

HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>FFRS_JP 소환 트윗 판정 시트</title>
<style>
body{font:13px/1.45 "Malgun Gothic","Yu Gothic UI",sans-serif;margin:0;background:#f4f4f1;color:#1c1c1c}
#bar{position:sticky;top:0;z-index:5;background:#22262b;color:#eee;padding:8px 12px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
#bar label{cursor:pointer;white-space:nowrap}#bar input[type=text]{width:240px;padding:3px 6px}
#bar select{padding:2px}#cnt{margin-left:auto;font-weight:bold}
table{border-collapse:collapse;width:100%;table-layout:fixed}
th,td{border:1px solid #cfcfc8;padding:5px 7px;vertical-align:top;word-break:break-all}
th{background:#e4e4dd;position:sticky;top:38px;z-index:4;text-align:left}
tr.v0{background:#eef7ea}tr.v1{background:#eaf1fa}tr.v2{background:#fbf6e2}tr.v3{background:#f3e9f5}tr.v4{background:#eee;color:#777}
.tag{display:inline-block;padding:0 6px;border-radius:3px;color:#fff;font-size:12px}
.t0{background:#2f8a3b}.t1{background:#2c69b0}.t2{background:#a67c00}.t3{background:#8a4a99}.t4{background:#888}
.sub{color:#666;font-size:12px}.g{margin-bottom:5px}.u{color:#7a3d00}.k{color:#888;font-size:11px}
.im{margin-bottom:8px}.im img{max-width:100%;max-height:150px;display:block;border:1px solid #999;background:#ddd}
.ev{color:#2f8a3b;font-size:11px;font-weight:bold}.tw{white-space:pre-wrap;font-size:12px;max-height:13em;overflow:auto}
a{color:#1a56a6}
</style></head><body>
<div id="bar"><span id="vs"></span>
<select id="yr"><option value="">전체 연도</option></select>
<select id="rs"><option value="">전체 사유</option></select>
<input type="text" id="q" placeholder="검색(소환명·유닛·본문·id)">
<span id="cnt"></span></div>
<table><colgroup><col style="width:92px"><col style="width:120px"><col style="width:24%"><col style="width:26%"><col></colgroup>
<thead><tr><th>날짜 / 트윗</th><th>판정</th><th>본문에서 뽑은 소환</th><th>트윗 본문</th><th>배너 판독</th></tr></thead><tbody id="tb"></tbody></table>
<script>
const R=__DATA__, IMG=__IMG__, V=["확정","이미지만","텍스트만","별도-무료","제외"];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const vs=document.getElementById('vs'),yr=document.getElementById('yr'),rs=document.getElementById('rs'),q=document.getElementById('q');
V.forEach((v,i)=>{const n=R.filter(r=>r.v===v).length;
 vs.insertAdjacentHTML('beforeend',`<label><input type="checkbox" value="${v}" ${i<3?'checked':''}> <span class="tag t${i}">${v}</span> ${n}</label> `)});
[...new Set(R.map(r=>r.d.slice(0,4)))].sort().forEach(y=>yr.insertAdjacentHTML('beforeend',`<option>${y}</option>`));
[...new Set(R.map(r=>r.r))].sort().forEach(y=>rs.insertAdjacentHTML('beforeend',`<option>${esc(y)}</option>`));
function row(r){const vi=V.indexOf(r.v);
 const g=r.g.map(x=>`<div class="g"><b>${esc(x[0]||'(이름 없음)')}</b> <span class="k">${esc(x[1])}</span>`+
  ((x[2]||x[3])?`<div class="sub">${esc(x[2])} ~ ${esc(x[3])}</div>`:'')+(x[4].length?`<div class="u">${esc(x[4].join(' / '))}</div>`:'')+`</div>`).join('')||'<span class="k">(없음)</span>';
 const im=r.i.map(x=>`<div class="im"><a href="${IMG+x[0]}" target="_blank"><img loading="lazy" src="${IMG+x[0]}"></a>`+
  `<b>${esc(x[2]||'(제목 없음)')}</b> <span class="k">${esc(x[1])}${x[4]?' · '+esc(x[4]):''}</span>`+(x[5].length?` <span class="ev">대조: ${x[5].join(',')}</span>`:'')+
  (x[3].length?`<div class="u">${esc(x[3].join(' / '))}</div>`:'')+`</div>`).join('')||'<span class="k">(판독한 이미지 없음)</span>';
 return `<tr class="v${vi}"><td>${r.d}<br><a href="https://x.com/FFRS_JP/status/${r.id}" target="_blank" class="k">${r.id}</a></td>`+
  `<td><span class="tag t${vi}">${r.v}</span><div class="sub">${esc(r.r)}</div><div class="k">${esc(r.p)}</div></td><td>${g}</td><td><div class="tw">${esc(r.t)}</div></td><td>${im}</td></tr>`}
R.forEach(r=>{r.s=(r.id+' '+r.t+' '+JSON.stringify(r.g)+' '+JSON.stringify(r.i)).toLowerCase()});
function draw(){const on=new Set([...vs.querySelectorAll('input:checked')].map(x=>x.value)),y=yr.value,s=rs.value,k=q.value.trim().toLowerCase();
 const L=R.filter(r=>on.has(r.v)&&(!y||r.d.startsWith(y))&&(!s||r.r===s)&&(!k||r.s.includes(k)));
 document.getElementById('tb').innerHTML=L.map(row).join('');document.getElementById('cnt').textContent=L.length+' / '+R.length+'건'}
vs.onchange=yr.onchange=rs.onchange=draw;let tm;q.oninput=()=>{clearTimeout(tm);tm=setTimeout(draw,250)};draw();
</script></body></html>'''

out = D / 'twitter_verdict_sheet.html'
out.write_text(HTML.replace('__DATA__', json.dumps(rows, ensure_ascii=False).replace('</', '<\\/'))
               .replace('__IMG__', json.dumps(SRC.as_uri() + '/')), encoding='utf-8')
print(out, len(rows), 'rows', out.stat().st_size // 1024, 'KB', 'no-content', sum(1 for r in rows if not r['t']))

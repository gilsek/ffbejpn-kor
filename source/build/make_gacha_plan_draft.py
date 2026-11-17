"""Draft of the season x series gacha line-up (read-only planning aid).

Unit -> series comes from F_UNIT_MST.taQ69cIx (F_GAME_TITLE_MST). Unit -> season comes from the first date the unit
is named as a featured unit in a gacha tweet (gacha_jp/unit_first_seen_twitter.json, built from
twitter_text_hydrogen.jsonl). Units never named in a gacha tweet are listed as unassigned, not guessed.
usage: python -I -X utf8 build/make_gacha_plan_draft.py
"""
import collections, io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
MST = ROOT / 'build/out/jp_offline/engine/static/mst_decoded'
OUT = ROOT / 'build/out/jp_offline/gacha_jp'
SEASONS = [('S1', '2015-01-01'), ('S2', '2017-02-28'), ('S3', '2019-05-30'), ('S4', '2021-05-10'), ('S5', '2024-12-27')]

COLLAB_TITLES = {'FINAL FANTASY Record Keeper'}   # 1xxxx title id but a separate game: FFRK collab, 2020-02

def rows(n): return [json.loads(l) for l in (MST / n).open(encoding='utf-8')]
def season(d): return [s for s, start in SEASONS if d >= start][-1]

titles = {r['taQ69cIx']: r['G4L0YIB2'] for r in rows('F_GAME_TITLE_MST.ndjson')}
fam = collections.defaultdict(list)
for u in rows('F_UNIT_MST.ndjson'): fam[u['woghJa61']].append(u)
# Not units: F_UNIT_MST.wSB84Usi == 0 marks growth pots, sell-only items, trust moogles, doors, battle NPCs.
excluded = {f: v for f, v in fam.items() if v[0]['wSB84Usi'] == '0'}
for f in excluded: del fam[f]
(OUT / 'banner_plan_excluded.json').write_text(json.dumps(
    [{'family': f, 'name': v[-1]['G4L0YIB2']} for f, v in sorted(excluded.items())], ensure_ascii=False, indent=0), encoding='utf-8')
first = json.loads((OUT / 'unit_first_seen_twitter.json').read_text(encoding='utf-8'))
grid, collab, unassigned, plan = collections.defaultdict(list), collections.defaultdict(list), collections.Counter(), []
# Units never named in a gacha tweet: take the date of the nearest dated unit by id inside the same id block
# (first 4 digits = one series block; ids rise with release order). Marked basis='id_order'.
basis = {f: 'tweet' for f in first}
blocks = collections.defaultdict(list)
for f in fam: blocks[f[:4]].append(f)
for b, fs in blocks.items():
    dated = sorted((int(f), first[f]) for f in fs if f in first)
    if not dated: continue
    for f in fs:
        if f in first: continue
        lower = [d for i, d in dated if i < int(f)]
        first[f] = lower[-1] if lower else dated[0][1]
        basis[f] = 'id_order'
for f, v in fam.items():
    tid = v[0]['taQ69cIx']; t = titles.get(tid, tid)
    group = 'FFBE' if t == 'FFBE' else ('FF' if tid.startswith('1') and t not in COLLAB_TITLES else 'collab')
    name = max(v, key=lambda u: int(u['9fW0TePj']))['G4L0YIB2']
    if group == 'collab' and basis.get(f) != 'tweet':      # a collab banner needs no season: keep the unit, no date
        rec = {'family': f, 'name': name, 'title': t, 'group': group, 'first_seen': None, 'season': None,
               'max_rarity': max(int(u['9fW0TePj']) for u in v), 'basis': 'title_only'}
        plan.append(rec); collab[t].append(rec); continue
    if f not in first:
        unassigned[(group, t)] += 1; continue
    rec = {'family': f, 'name': name, 'title': t, 'group': group, 'first_seen': first[f], 'season': season(first[f]),
           'max_rarity': max(int(u['9fW0TePj']) for u in v), 'basis': basis[f]}
    plan.append(rec)
    (collab[t] if group == 'collab' else grid[(rec['season'], t)]).append(rec)
ss = [s for s, _ in SEASONS]
ts = sorted({t for _, t in grid}, key=lambda t: (t != 'FFBE', -sum(len(grid.get((s, t), [])) for s in ss)))
L = ['# 가챠 구성 초안: 시즌 x 시리즈', '', '시즌 경계(트윗 기준): ' + ', '.join(f'{s} {d}~' for s, d in SEASONS), '',
     '## 시즌별 시리즈 배너 (칸 = 그 배너에 들어갈 유닛 계열 수)', '', '| 시리즈 | ' + ' | '.join(ss) + ' | 합 |', '|---|' + '---|' * (len(ss) + 1)]
for t in ts:
    c = [len(grid.get((s, t), [])) for s in ss]
    L.append(f'| {t} | ' + ' | '.join(str(x or "") for x in c) + f' | {sum(c)} |')
tot = [sum(len(grid.get((s, t), [])) for t in ts) for s in ss]
L += ['| **합** | ' + ' | '.join(map(str, tot)) + f' | {sum(tot)} |', '',
      f'배너 수(유닛 1개 이상인 칸): {sum(1 for k in grid if grid[k])}', '', '## 콜라보 배너 (작품별 1개)', '', '| 작품 | 유닛 계열 | 첫 등장 |', '|---|---|---|']
def fs(v): return min([r['first_seen'] for r in v if r['first_seen']] or ['?'])
for t, v in sorted(collab.items(), key=lambda kv: fs(kv[1])):
    L.append(f'| {t} | {len(v)} | {fs(v)} |')
nb = collections.Counter(r['basis'] for r in plan)
L += ['', f'시즌 근거: 트윗 날짜 {nb["tweet"]}, 유닛 번호 순서로 추정 {nb["id_order"]}']
L += ['', f'유닛이 아니어서 뺀 계열: {len(excluded)}']
L += ['', f'콜라보 배너 수: {len(collab)}, 유닛 계열 {sum(len(v) for v in collab.values())}', '',
      '## 같은 번호대에 날짜가 붙은 유닛이 하나도 없어 남은 계열 (미배정)', '']
for g in ('FFBE', 'FF', 'collab'):
    L.append(f'- {g}: {sum(n for (gg, _), n in unassigned.items() if gg == g)}')
(OUT / 'banner_plan_draft.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
(OUT / 'banner_plan_draft.json').write_text(json.dumps(plan, ensure_ascii=False, indent=0), encoding='utf-8')
print('\n'.join(L))

import sqlite3
import glob
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('artifacts/chapter1-ko/script_meta.sqlite')
cursor = conn.cursor()

cursor.execute('''
    SELECT 
        substr(scene_id, 1, 2) as prefix,
        count(distinct scene_id) as scene_count,
        count(*) as row_count
    FROM script_meta
    GROUP BY prefix
    ORDER BY scene_count DESC;
''')
meta_breakdown = cursor.fetchall()

# Now check completed files in gt_output
completed_files = set(os.path.splitext(os.path.basename(f))[0] for f in glob.glob('artifacts/chapter1-ko/gt_output/*.json'))

cursor.execute('SELECT scene_id, count(*) FROM script_meta GROUP BY scene_id;')
scene_row_counts = dict(cursor.fetchall())

completed_by_prefix = {}
completed_rows_by_prefix = {}

for sid, rows in scene_row_counts.items():
    p = sid[:2]
    if sid in completed_files:
        completed_by_prefix[p] = completed_by_prefix.get(p, 0) + 1
        completed_rows_by_prefix[p] = completed_rows_by_prefix.get(p, 0) + rows

# Category mapping based on FFBE scene ID structure
category_names = {
    '11': '1부 1장: 그랑셸트 제도 (Grandshelt)',
    '12': '1부 2장: 란젤트 대륙 (Lanzelt)',
    '13': '1부 3장: 코로보스 섬 (Kolobos)',
    '14': '1부 4장: 디르나도 제국 (Dirnado)',
    '15': '1부 5장: 올데리온 연방 (Olderion)',
    '16': '1부 6장: 졸다트 제국 (Zoldaad)',
    '17': '1부 7장: 마도도서관 / 고라도',
    '18': '1부 8장: 미시디아 (Mysidia)',
    '19': '1부 9장: 부유대륙 / 그론도아',
    '20': '1부 최종장: 크리스탈 타워',
    '21': '1부 에필로그 / 막간 스토리',
    '30': '2부 1장: 팔라디아 대륙 (Paladia)',
    '31': '2부 2장: 게헤나 / 르샤티',
    '32': '2부 3장: 크리스타 / 알도어',
    '33': '2부 4장: 팔라디아 중심부',
    '40': '3부: 이계의 마법 세계 (Fina & Hollow)',
    '41': '3부: 공허의 세계 후반',
    '42': '3부: 공허의 결전',
    '50': '단편 스토리 / 캐릭터 퀘스트 1',
    '55': '스토리 이벤트 / 캐릭터 외전 (Story Events)',
    '60': '강림 / 보스 이벤트',
    '61': '콜라보레이션 스토리',
    '65': '십이무구 / 무구 이벤트',
    '70': '시즌 4 스토리 프롤로그',
    '90': '회상의 방 / 레이드 / 튜토리얼 / 시스템',
    '10': '테스트 / 시스템 이벤트'
}

print("=== FFBE Entire Script Scope Breakdown ===")
total_scenes = 0
total_rows = 0
total_comp_scenes = 0
total_comp_rows = 0

print(f"{'Prefix':<6} | {'Category Description':<38} | {'Scenes':<14} | {'Rows':<16} | {'Status'}")
print("-" * 95)

for p, s_count, r_count in meta_breakdown:
    comp_s = completed_by_prefix.get(p, 0)
    comp_r = completed_rows_by_prefix.get(p, 0)
    total_scenes += s_count
    total_rows += r_count
    total_comp_scenes += comp_s
    total_comp_rows += comp_r
    
    cat = category_names.get(p, f"기타 이벤트 ({p}xx)")
    pct = (comp_s / s_count * 100) if s_count > 0 else 0
    status_str = f"{pct:5.1f}% ({comp_s}/{s_count})"
    
    print(f"{p:<6} | {cat:<38} | {s_count:<14} | {r_count:<16} | {status_str}")

print("-" * 95)
print(f"TOTAL  | {'전체 대사 스크립트 합계':<38} | {total_scenes:<14} | {total_rows:<16} | {total_comp_scenes/total_scenes*100:5.1f}% ({total_comp_scenes}/{total_scenes})")
print(f"Total Rows Completed: {total_comp_rows} / {total_rows} ({total_comp_rows/total_rows*100:5.1f}%)")

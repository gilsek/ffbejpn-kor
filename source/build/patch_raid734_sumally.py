"""Write the JP F_SUMALLY_REWARD_MST rows for raid 734 (SumallyId 400107).

Why: the raid tab's Rewards button opens GateMissionRaidRewardScene, and its ranking tab
(RAID_REWARD_TAB 1, getRewardInfoList 0x1bd81b4) reads
`SumallyRewardMstList::getRewardList(SumallyId)` (0x1cac648) from the native master F_SUMALLY_REWARD_MST.
JP 11.0.0 ships no 400107 rows even though banner 60003's URL points at SumallyId=400107
(`bahamut_raid.php?SumallyId=400107`), so the list would be empty. This script rebuilds the six rank bands
from the 734 event's own post-prune personal milestones (upstream raid_rewards.json through
jp_compat._jp_raid_event, the same source the raid mail uses) and re-encrypts the JP master.

Row shape copied from the shipped 4001xx rows (SumallyRewardMstResponse::readParam 0x1de0604):
  L84eYzxv SumallyId (+0x24) | ip94Nqb7 rank low (+0x28) | XM4Ca3PF rank high (+0x2c)
  dX6cor8j rewards (+0x30: ','-split, each entry RbUtil::getItemParamFromItemInfo 0x14dfa80)
  fbcj5Aq9 title (+0x48) | Wk1v6upb desc (+0x60) | E93RGBky '-' (+0x78)
  vs48LZrt reward frame 0 (+0x90) | q8z1w5No display order (+0x94)
Reward entry format per getItemParamFromItemInfo: kind 10 reads id/count/type where type is the 5th
integer, so units are "10:id:count:100:1"; every other kind reads id/count only (20 looks up F_ITEM_MST
itself), so "kind:id:count:100" matches the shipped rows. Every reward id is first checked against the JP
masters with jp_compat._jp_raid_has_reward.

Bands/grouping: the 50 pruned milestones are sorted by points and split 9/9/8/8/8/8; the top-scoring group
fills the best rank band, so the table mirrors the event's progression. Each band's reward string is at most
9 entries, within the shipped maximum (9).

Output (device NOT touched; deploy separately):
  build/out/raid734/mst_ko/Ver128_RU2MH9o5.dat   -> /data/local/tmp/ffbe/mst_ko/ (jp_offline.js localize)
  build/out/raid734/F_SUMALLY_REWARD_MST.400107.ndjson
  build/out/raid734/sumally_400107_report.json

usage: python -I -X utf8 build/patch_raid734_sumally.py
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'ffbe_offline_modfix'
UPSTREAM = OLD / 'upstream/source/server'
SRC_DIR = OLD / 'downloads/ffbejpdata-archive-org'
JP_STATIC = ROOT / 'build/out/jp_offline/engine/static'
OUT = ROOT / 'build/out/raid734'

TOKEN, KEY = 'RU2MH9o5', '8HXr5ZMb'      # name_coverage.masters()['F_SUMALLY_REWARD_MST']
SUMALLY_ID = '400107'                    # 60003 banner URL: bahamut_raid.php?SumallyId=400107
TITLE = '1주년 고마워 쿠포 랭킹 보상'
# The six bands of the shipped 4001xx rows, best rank first.
BANDS = [(1, 1000), (1001, 10000), (10001, 30000), (30001, 50000), (50001, 100000), (100001, 9999999)]
MAX_ENTRIES = 9                          # the master's largest shipped reward string

os.environ.setdefault('MST_DIR', str(JP_STATIC / 'mst_decoded'))
os.environ.setdefault('TEXT_DIR', str(JP_STATIC / 'text_decoded'))
sys.path.insert(0, str(UPSTREAM))        # ffbe_crypto
sys.path.insert(0, str(ROOT / 'tools/upstream_ref'))   # decode_client_data
sys.path.insert(0, str(ROOT / 'build/engine_overlay'))  # jp_compat

import jp_compat                                    # noqa: E402
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16   # noqa: E402
from decode_client_data import json_record          # noqa: E402


def entry_text(entry):
    """One reward string entry, formatted the way the shipped rows do (see module docstring)."""
    kind, iid, count = entry['kind'], entry['id'], entry['count']
    if kind == 10:                      # unit: 5th integer is the type field
        return '10:%d:%d:100:1' % (iid, count)
    return '%d:%d:%d:100' % (kind, iid, count)


def pruned_rewards():
    """(points, reward row) for every 734 reward the JP masters can resolve, ascending by points."""
    table = json.loads((UPSTREAM / 'raid_rewards.json').read_text(encoding='utf-8'))
    event = next(e for e in table['events'] if str(e.get('event_id')) == '734')
    pruned = jp_compat._jp_raid_event(event)
    out = []
    milestones = list(pruned.get('personal_milestones') or []) + list(pruned.get('shared_milestones') or [])
    for milestone in milestones:
        threshold = milestone.get('points', milestone.get('threshold'))
        if threshold is None:
            continue
        for reward in (milestone.get('rewards') or [milestone.get('reward')]):
            if not isinstance(reward, dict):
                continue
            kind, iid = int(reward.get('kind', 0) or 0), int(reward.get('id', 0) or 0)
            count = int(reward.get('count', 1) or 1)
            if not kind or not iid or count <= 0:
                raise SystemExit('734 milestone reward is not grantable: %r' % (reward,))
            if not jp_compat._jp_raid_has_reward(reward):
                raise SystemExit('734 milestone reward does not resolve in the JP masters: %r' % (reward,))
            out.append((int(threshold), {'kind': kind, 'id': iid, 'count': count}))
    out.sort(key=lambda pair: pair[0])
    return out


def build_rows(rewards):
    count = len(rewards)
    base, rem = divmod(count, len(BANDS))
    sizes = [base + 1] * rem + [base] * (len(BANDS) - rem)
    groups, start = [], 0
    for size in sizes:
        groups.append(rewards[start:start + size])
        start += size
    rows = []
    for order, ((low, high), group) in enumerate(zip(BANDS, reversed(groups)), 1):
        merged, seen = [], {}
        for threshold, reward in group:
            key = (reward['kind'], reward['id'])
            if key in seen:
                seen[key]['count'] += reward['count']
                continue
            item = dict(reward)
            item['threshold'] = threshold
            seen[key] = item
            merged.append(item)
        if len(merged) > MAX_ENTRIES:
            raise SystemExit('rank band %d-%d needs %d reward entries (shipped max %d)'
                             % (low, high, len(merged), MAX_ENTRIES))
        rows.append({'L84eYzxv': SUMALLY_ID, 'ip94Nqb7': str(low), 'XM4Ca3PF': str(high),
                     'dX6cor8j': ','.join(entry_text(item) for item in merged),
                     'fbcj5Aq9': TITLE, 'Wk1v6upb': '', 'vs48LZrt': '0',
                     'E93RGBky': '-', 'q8z1w5No': str(order)})
    return rows


def main():
    rows = build_rows(pruned_rewards())
    source = next(SRC_DIR.glob('Ver*_%s.dat' % TOKEN), None)
    if source is None:
        raise SystemExit('JP release master not found: %s/Ver*_%s.dat' % (SRC_DIR, TOKEN))
    k16 = key16(KEY)
    original = [line for line in source.read_text(encoding='ascii').splitlines() if line.strip()]
    first = cbc_decrypt(k16, original[0])
    pad = first[-1]
    double_pad = 1 <= pad <= 16 and first[-pad:] == bytes([pad]) * pad

    kept, dropped = [], 0
    for line in original:
        if str(json_record(cbc_decrypt(k16, line)).get('L84eYzxv')) == SUMALLY_ID:
            dropped += 1
            continue
        kept.append(line)
    added = [cbc_encrypt(k16, json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                         double_pad=double_pad) for row in rows]
    dest = OUT / 'mst_ko' / source.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('\n'.join(kept + added) + '\n', encoding='ascii')

    # Re-read the artifact: the unchanged lines must be byte-identical and the six rows must decrypt back.
    produced = [line for line in dest.read_text(encoding='ascii').splitlines() if line.strip()]
    if produced[:len(kept)] != kept:
        raise SystemExit('artifact check failed: unchanged master lines were rewritten')
    decoded = [json_record(cbc_decrypt(k16, line)) for line in produced]
    got = [row for row in decoded if str(row.get('L84eYzxv')) == SUMALLY_ID]
    if len(produced) != len(original) - dropped + len(rows) or len(got) != len(rows):
        raise SystemExit('artifact check failed: %d lines / %d 400107 rows' % (len(produced), len(got)))
    if got != rows:
        raise SystemExit('artifact check failed: 400107 rows differ after re-encryption')

    OUT.joinpath('F_SUMALLY_REWARD_MST.400107.ndjson').write_text(
        '\n'.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) for row in rows) + '\n',
        encoding='utf-8')
    report = {
        'table': 'F_SUMALLY_REWARD_MST', 'sumally_id': SUMALLY_ID,
        'source': str(source), 'source_rows': len(original),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'artifact': str(dest), 'artifact_rows': len(produced),
        'artifact_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
        'replaced_rows': dropped, 'added_rows': len(rows), 'double_pad': double_pad,
        'bands': [{'rank_low': row['ip94Nqb7'], 'rank_high': row['XM4Ca3PF'],
                   'rewards': row['dX6cor8j']} for row in rows],
        'deploy': 'adb push %s /data/local/tmp/ffbe/mst_ko/ ; adb shell chmod 644 '
                  '/data/local/tmp/ffbe/mst_ko/%s' % (dest.name, dest.name),
    }
    OUT.joinpath('sumally_400107_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for row in rows:
        print('%s-%s: %s' % (row['ip94Nqb7'], row['XM4Ca3PF'], row['dX6cor8j']))
    print('wrote %s (%d rows kept, %d 400107 rows added)' % (dest, len(kept), len(rows)))


if __name__ == '__main__':
    main()

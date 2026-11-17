"""Append the JP weekly login-bonus windows to F_LOGIN_BONUS_MST (client .dat + engine ndjson).

The JP table is a list of weekly campaigns: id, start YMD, end YMD, rewards `day@kind:id:count,...`, kuplo
dialogue. Its last row is 507 (20260406-20260412), so today has NO row and WeeklyLoginBonusScene's
`getCurrentLoginBonusMst(processDay)` returns null (the scene stores it with no null check: notes.md SS2.4).
This script appends 508.. covering 20260413 through 2035-12-31 in non-overlapping seven-day windows with the
lapis rewards the user chose.

KOREAN DIALOGUE (2026-11-12). The `VC9F3eJn` (kuplo) column is Japanese in the JP archive, and an earlier run
of this script copied row 507's Japanese dialogue into every appended row AND re-encrypted rows 1..507 from
the JP source, wiping the Korean that had already been deployed. The dialogue is now restored:
  * rows 1..507: `translations/events-ko/patches.json` -> F_LOGIN_BONUS_MST (patch key = row id - 1, ids 59..507),
    falling back to build/out/ko_names/mst_ko.bak_grades/Ver63_P3raZX89.dat (the old Korean deployment);
  * rows 508..1015: a row whose Japanese dialogue equals a 1..507 Japanese dialogue reuses that row's Korean
    (whole string first, then line by line on the `@`-separated lines). Anything that cannot be matched stays
    Japanese and is listed in report.json `unmatched_rows` -- no other row's translation is substituted.
Every patched row is checked against its Japanese original for the same `@`, <br>, <color=...>, </color> and
<next> counts (a mismatch aborts the run), and all other columns and the row count/order are left untouched.

Outputs (ONLY under build/out/login_bonus/ plus the two deployed copies below):
  Ver63_P3raZX89.dat          the CLIENT master (rows 1..507 Korean + 508.. new, re-encrypted per row).
  Ver63_P3raZX89.dat.ja_bak   the Korean-deployment copy that was replaced (kept from the first run only).
  F_LOGIN_BONUS_MST.ndjson    the ENGINE data copy (mst_decoded) = the existing rows + the new ones.
  F_LOGIN_BONUS_MST.ndjson.ja_bak  the engine copy that was replaced (kept from the first run only).
  rows_add.ndjson             only the new rows.
  report.json                 counts, windows, Korean/Japanese row counts, unmatched ids, deploy commands.
The script also refreshes build/out/ko_names/mst_ko/Ver63_P3raZX89.dat (client) and the engine
mst_decoded/F_LOGIN_BONUS_MST.ndjson so a rerun cannot silently go back to Japanese.

Deploy (this script never touches the device):
  python -I build/deploy_ko_names.py --serial <adb> --only P3raZX89
  (deploy_ko_names overwrites files/Ver63_P3raZX89.dat when present and removes files/P3raZX89.i, the
  row-offset index, which must be rebuilt after the row lengths change)
  engine: tar -cf build/out/jp_offline/engine_static.tar -C build/out/jp_offline/engine static
          then push/extract engine_static.tar as usual (docs/REPORT_09..., install step 2)

usage: python -I build/add_login_bonus_rows.py [--src DIR] [--out DIR]
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'build' / 'engine_overlay'))
import name_coverage as NC  # noqa: E402  (puts the decoder + crypto on sys.path)
from ffbe_crypto import cbc_decrypt, cbc_encrypt, key16  # noqa: E402
from decode_client_data import json_record  # noqa: E402
from jp_login_bonus import WEEKLY_REWARDS  # noqa: E402  (one home for the chosen rewards)

TOKEN, FILE_KEY, VERSION = 'P3raZX89', '8xQP3fUZ', 63      # JP client: gamedata.xml F_LOGIN_BONUS_MST=63
FIRST_ID = 508
FIRST_START = date(2026, 4, 13)
LAST_END = date(2035, 12, 31)
SPAN_DAYS = 7
OUT = ROOT / 'build' / 'out' / 'login_bonus'
ENGINE_NDJSON = ROOT / 'build' / 'out' / 'jp_offline' / 'engine' / 'static' / 'mst_decoded' / 'F_LOGIN_BONUS_MST.ndjson'
ID_FIELD, START_FIELD, END_FIELD, REWARD_FIELD, DIALOGUE_FIELD = (
    'a3ZcU6gv', 'IFQ70DYS', 'c46Ayz8I', 'dX6cor8j', 'VC9F3eJn')
LAST_ROW_ID = '507'

# Korean dialogue sources / deployment copies (see the module docstring).
PATCHES = ROOT / 'translations' / 'events-ko' / 'patches.json'
KO_BACKUP_DIR = ROOT / 'build' / 'out' / 'ko_names' / 'mst_ko.bak_grades'
KO_DEPLOY = ROOT / 'build' / 'out' / 'ko_names' / 'mst_ko'
CLIENT_NAME = 'Ver%d_%s.dat' % (VERSION, TOKEN)
KO_BACKUP = KO_BACKUP_DIR / CLIENT_NAME
KO_CLIENT = KO_DEPLOY / CLIENT_NAME
JA_BAK = OUT / (CLIENT_NAME + '.ja_bak')
ENGINE_JA_BAK = OUT / (ENGINE_NDJSON.name + '.ja_bak')
COLOR_TAG = re.compile(r'<color=[^>]*>')
HANGUL = re.compile(r'[가-힣]')
JP_TEXT = re.compile(r'[぀-ヺヽ-ヿ一-鿿]')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def windows():
    """[(id, start, end)] non-overlapping seven-day windows, 20260413..2035-12-31 (last one may be shorter)."""
    out, ident, cur = [], FIRST_ID, FIRST_START
    while cur <= LAST_END:
        end = min(cur + timedelta(days=SPAN_DAYS - 1), LAST_END)
        out.append((ident, cur, end))
        ident += 1
        cur = end + timedelta(days=1)
    return out


def check_rewards():
    """The chosen string must be the JP `day@kind:id:count` shape with exactly one entry per day 1..7."""
    days = {}
    for part in WEEKLY_REWARDS.split(','):
        day, sep, rest = part.strip().partition('@')
        fields = rest.split(':')
        assert sep and day.isdigit(), part
        assert len(fields) == 3 and all(f.isdigit() for f in fields), part
        assert int(fields[0]) == 50 and int(fields[1]) == 1, 'weekly rewards are lapis (50:1:count): ' + part
        assert int(fields[2]) > 0, part
        assert int(day) not in days, 'duplicate day ' + day
        days[int(day)] = int(fields[2])
    assert sorted(days) == list(range(1, 8)), 'days must be 1..7: %s' % sorted(days)
    return days


def strip_manual_pad(plain):
    """The decrypted row as UTF-8 text WITHOUT its manual pad byte block (cbc_decrypt strips only one layer)."""
    pad = plain[-1] if plain else 0
    if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
        return plain[:-pad].decode('utf-8')
    return plain.decode('utf-8')


def dat_plains(path, k16):
    """The decrypted rows of a client .dat (one base64 ciphertext per line)."""
    if not path.is_file():
        return []
    return [cbc_decrypt(k16, line) for line in path.read_text(encoding='ascii').splitlines() if line.strip()]


def load_ko_dialogues(k16):
    """row id -> Korean VC9F3eJn: patches.json first (key = row id - 1), then the old Korean deployment."""
    ko = {}
    patches = json.loads(PATCHES.read_text(encoding='utf-8')).get('F_LOGIN_BONUS_MST', {})
    for key, entry in patches.items():
        if str(key).isdigit() and isinstance(entry, dict):
            value = entry.get(DIALOGUE_FIELD)
            if value:
                ko[str(int(key) + 1)] = value     # patch key 58..506 -> row id 59..507
    for plain in dat_plains(KO_BACKUP, k16):
        row = json_record(plain)
        ident, value = str(row.get(ID_FIELD)), row.get(DIALOGUE_FIELD)
        if value and ident not in ko:
            ko[ident] = value
    return ko


def build_dialogue_maps(jp_rows, ko_by_id):
    """Japanese dialogue -> Korean, whole string and per `@` line; conflicting mappings are dropped."""
    whole, line_map, bad_whole, bad_line = {}, {}, set(), set()
    for row in jp_rows:
        ident = str(row.get(ID_FIELD))
        jp, ko = str(row.get(DIALOGUE_FIELD) or ''), ko_by_id.get(ident)
        if not jp or not ko:
            continue
        if jp in whole and whole[jp] != ko:
            bad_whole.add(jp)
        whole.setdefault(jp, ko)
        jp_parts, ko_parts = jp.split('@'), ko.split('@')
        if len(jp_parts) != len(ko_parts):
            continue
        for a, b in zip(jp_parts, ko_parts):
            if a in line_map and line_map[a] != b:
                bad_line.add(a)
            line_map.setdefault(a, b)
    for key in bad_whole:
        del whole[key]
    for key in bad_line:
        line_map.pop(key, None)
    return whole, line_map


def translate_dialogue(jp_text, whole, line_map):
    """Korean for a Japanese dialogue, or None when it cannot be matched (leave the Japanese untouched)."""
    if not jp_text:
        return ''
    if jp_text in whole:
        return whole[jp_text]
    parts = []
    for part in jp_text.split('@'):
        value = line_map.get(part)
        if value is None:
            return None
        parts.append(value)
    return '@'.join(parts)


def check_tags(jp_text, ko_text, where):
    """`@`, <br>, <color=...>, </color> and <next> counts must be identical to the Japanese original."""
    def counts(text):
        return {'@': text.count('@'), '<br>': text.count('<br>'), '</color>': text.count('</color>'),
                '<next>': text.count('<next>'), '<color=...>': len(COLOR_TAG.findall(text))}
    jp_counts, ko_counts = counts(jp_text), counts(ko_text)
    assert jp_counts == ko_counts, '%s: tag counts %s != %s' % (where, jp_counts, ko_counts)


def set_field(raw, field, value):
    """Replace one string value in a raw JSON record, keeping every other byte (key order, escapes) as is."""
    needle = '"%s":"' % field
    assert raw.count(needle) == 1, '%s: field not found exactly once' % field
    start = raw.index(needle) + len(needle)
    pos = start
    while True:
        pos = raw.index('"', pos)
        backslashes, scan = 0, pos - 1
        while scan >= start and raw[scan] == '\\':
            backslashes += 1
            scan -= 1
        if backslashes % 2 == 0:
            break
        pos += 1
    return raw[:start] + json.dumps(value, ensure_ascii=False)[1:-1] + raw[pos:]


def patch_dialogue(raw, jp_text, ko_text, where):
    """Raw row text with its dialogue replaced; every other column is verified unchanged."""
    check_tags(jp_text, ko_text, where)
    patched = set_field(raw, DIALOGUE_FIELD, ko_text)
    before, after = json.loads(raw), json.loads(patched)
    assert after.get(DIALOGUE_FIELD) == ko_text, where
    before.pop(DIALOGUE_FIELD, None)
    after.pop(DIALOGUE_FIELD, None)
    assert before == after, '%s: another column changed' % where
    return patched


def new_row_texts(rows, base_plain, base_row):
    """Reward/date/id substitution on row 507's OWN raw JSON text.

    The dialogue column carries JSON escapes (`<\\/color>`), so re-serialising the parsed dict would change
    bytes the client has always read; the text is spliced instead of rebuilt. `base_plain` is the decrypted
    row WITHOUT its manual pad (cbc_encrypt adds that back with double_pad=True).
    """
    pad = base_plain[-1]
    assert 1 <= pad <= 16 and base_plain[-pad:] == bytes([pad]) * pad, 'row 507: no manual pad'
    text = base_plain[:-pad].decode('utf-8')
    out = []
    for ident, start, end in rows:
        row_text = text
        for field, old, new in ((ID_FIELD, LAST_ROW_ID, str(ident)),
                                (START_FIELD, base_row[START_FIELD], start.strftime('%Y%m%d')),
                                (END_FIELD, base_row[END_FIELD], end.strftime('%Y%m%d'))):
            needle = '"%s":"%s"' % (field, old)
            assert row_text.count(needle) == 1, 'row 507: %s not found exactly once' % field
            row_text = row_text.replace(needle, '"%s":"%s"' % (field, new))
        row_text, n = re.subn(r'"%s":"[^"]*"' % REWARD_FIELD,
                              '"%s":"%s"' % (REWARD_FIELD, WEEKLY_REWARDS), row_text)
        assert n == 1, 'row 507: reward field not found exactly once'
        out.append((ident, start, end, row_text))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=str(NC.OLD / 'downloads' / 'ffbejpdata-archive-org'))
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()
    src_dir, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    day_lapis = check_rewards()

    sources = sorted(src_dir.glob('Ver*_%s.dat' % TOKEN))
    assert len(sources) == 1, 'expected one Ver*_%s.dat in %s, found %d' % (TOKEN, src_dir, len(sources))
    source = sources[0]
    k16 = key16(FILE_KEY)
    lines = [line for line in source.read_text(encoding='ascii').splitlines() if line.strip()]
    plains = [cbc_decrypt(k16, line) for line in lines]
    first_plain = plains[0]
    pad = first_plain[-1]
    double_pad = 1 <= pad <= 16 and first_plain[-pad:] == bytes([pad]) * pad
    rows = [json_record(plain) for plain in plains]
    assert len(rows) == 507, 'unexpected row count %d' % len(rows)
    assert [str(r.get(ID_FIELD)) for r in rows] == [str(i) for i in range(1, 508)], 'ids are not 1..507'
    base_row = rows[-1]
    assert str(base_row.get(ID_FIELD)) == LAST_ROW_ID
    assert base_row.get(START_FIELD) == '20260406' and base_row.get(END_FIELD) == '20260412', base_row
    base_plain = plains[-1]
    dialogue_parts = str(base_row.get(DIALOGUE_FIELD) or '').split('@')
    assert len(dialogue_parts) == 7 and all('<next>' in part for part in dialogue_parts), 'row 507 dialogue shape'

    # --- Korean dialogue: patches.json + the old Korean deployment, matched onto every row -------------
    ko_by_id = load_ko_dialogues(k16)
    whole, line_map = build_dialogue_maps(rows, ko_by_id)
    unmatched = []          # row ids that stay Japanese (no source matched); reported, never substituted
    korean = 0

    def localise(raw, jp_text, ident):
        """Raw row text with the Korean dialogue, or the original text when nothing matches."""
        nonlocal korean
        ko_text = ko_by_id.get(ident) or translate_dialogue(jp_text, whole, line_map)
        if not jp_text:
            assert not ko_text, 'row %s: Korean without Japanese source' % ident
            return raw
        if ko_text is None:
            unmatched.append(ident)
            return raw
        korean += 1
        return patch_dialogue(raw, jp_text, ko_text, 'row %s' % ident)

    client_lines, changed_rows = [], 0
    for encoded, plain, row in zip(lines, plains, rows):
        ident = str(row.get(ID_FIELD))
        jp_text = str(row.get(DIALOGUE_FIELD) or '')
        raw = strip_manual_pad(plain)
        localised = localise(raw, jp_text, ident)
        if localised == raw:
            client_lines.append(encoded)                     # keep the bytes the client already reads
        else:
            changed_rows += 1
            client_lines.append(cbc_encrypt(k16, localised.encode('utf-8'), double_pad=double_pad))

    plan = windows()
    built = new_row_texts(plan, base_plain, base_row)
    encrypted = []
    for ident, start, end, plain in built:
        row = json.loads(plain)
        assert str(row.get(ID_FIELD)) == str(ident), row
        assert row.get(START_FIELD) == start.strftime('%Y%m%d') and row.get(END_FIELD) == end.strftime('%Y%m%d')
        assert row.get(REWARD_FIELD) == WEEKLY_REWARDS
        assert row.get(DIALOGUE_FIELD) == base_row.get(DIALOGUE_FIELD), 'dialogue changed'
        jp_text = str(row.get(DIALOGUE_FIELD) or '')
        plain = localise(plain, jp_text, str(ident))
        encrypted.append(cbc_encrypt(k16, plain.encode('utf-8'), double_pad=double_pad))

    client = out / CLIENT_NAME
    client.write_text('\n'.join(client_lines + encrypted) + '\n', encoding='ascii')

    # the engine's own copy: existing rows with id < 508, then the new ones in the same json formatting
    engine_rows = []
    if ENGINE_NDJSON.is_file():
        with open(ENGINE_NDJSON, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and str(row.get(ID_FIELD, '')).isdigit() and int(row[ID_FIELD]) < FIRST_ID:
                    engine_rows.append(row)
    assert len(engine_rows) == 507, 'engine ndjson has %d old rows' % len(engine_rows)
    for row in engine_rows:                                  # the engine copy gets the same Korean column
        ident = str(row.get(ID_FIELD))
        jp_text = str(row.get(DIALOGUE_FIELD) or '')
        ko_text = ko_by_id.get(ident) or translate_dialogue(jp_text, whole, line_map)
        if ko_text:
            check_tags(jp_text, ko_text, 'engine row %s' % ident)
            row[DIALOGUE_FIELD] = ko_text
    base_jp = str(base_row.get(DIALOGUE_FIELD) or '')
    base_ko = ko_by_id.get(LAST_ROW_ID) or translate_dialogue(base_jp, whole, line_map) or base_jp
    add = [dict(engine_rows[-1], **{ID_FIELD: str(ident), START_FIELD: start.strftime('%Y%m%d'),
                                    END_FIELD: end.strftime('%Y%m%d'), REWARD_FIELD: WEEKLY_REWARDS,
                                    DIALOGUE_FIELD: base_ko})
           for ident, start, end in plan]
    dump = lambda row: json.dumps(row, ensure_ascii=False, separators=(',', ':'))
    (out / 'rows_add.ndjson').write_text(''.join(dump(row) + '\n' for row in add), encoding='utf-8')
    engine_merged = out / ENGINE_NDJSON.name
    engine_merged.write_text(''.join(dump(row) + '\n' for row in engine_rows + add), encoding='utf-8')

    # integrity: covered days are contiguous, sorted and do not overlap; today must be inside one window
    today = date.today()
    covered, cursor = [], FIRST_START
    for ident, start, end in plan:
        assert start == cursor, 'gap/overlap before %s' % start
        assert end >= start
        cursor = end + timedelta(days=1)
        covered.append((ident, start, end))
    assert cursor - timedelta(days=1) == LAST_END, 'coverage ends %s' % (cursor - timedelta(days=1))
    assert any(start <= today <= end for _, start, end in covered), 'today is not covered'

    # --- verify what was written: row count/order, Korean rows, Japanese rows left ------------------
    result = [json_record(plain) for plain in dat_plains(client, k16)]
    assert len(result) == len(client_lines) + len(encrypted), 'result row count %d' % len(result)
    assert [str(r.get(ID_FIELD)) for r in result] == [str(i) for i in range(1, len(result) + 1)], 'result ids'
    korean_found = sum(1 for r in result if HANGUL.search(str(r.get(DIALOGUE_FIELD) or '')))
    jp_found = sum(1 for r in result if JP_TEXT.search(str(r.get(DIALOGUE_FIELD) or '')))
    empty_found = sum(1 for r in result if not r.get(DIALOGUE_FIELD))
    assert korean_found == korean, 'Korean rows %d != patched %d' % (korean_found, korean)
    assert jp_found == len(unmatched), 'Japanese rows left %d != unmatched %d' % (jp_found, len(unmatched))
    assert empty_found == sum(1 for r in rows if not r.get(DIALOGUE_FIELD)), 'empty dialogue rows changed'

    # refresh the deployed copies; keep the file that was there (Japanese) as *.ja_bak, once
    def refresh_copy(target, backup):
        if target.is_file() and not backup.is_file() and target.read_bytes() != client.read_bytes():
            shutil.copyfile(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(client, target)
        assert target.read_bytes() == client.read_bytes(), target

    refresh_copy(KO_CLIENT, JA_BAK)
    if ENGINE_NDJSON.is_file():
        if not ENGINE_JA_BAK.is_file() and ENGINE_NDJSON.read_bytes() != engine_merged.read_bytes():
            shutil.copyfile(ENGINE_NDJSON, ENGINE_JA_BAK)
        shutil.copyfile(engine_merged, ENGINE_NDJSON)
        assert ENGINE_NDJSON.read_bytes() == engine_merged.read_bytes(), ENGINE_NDJSON

    report = {
        'source': str(source), 'source_sha256': sha(source), 'source_rows': len(rows),
        'client_file': client.name, 'client_sha256': sha(client), 'client_rows': len(lines) + len(encrypted),
        'double_pad': bool(double_pad), 'engine_ndjson': str(ENGINE_NDJSON),
        'dialogue_source': [str(PATCHES), str(KO_BACKUP)],
        'korean_rows': korean_found, 'japanese_rows_left': jp_found, 'empty_rows': empty_found,
        'changed_existing_rows': changed_rows, 'unmatched_rows': unmatched,
        'ko_client': str(KO_CLIENT), 'ko_client_sha256': sha(KO_CLIENT),
        'ja_bak': str(JA_BAK) if JA_BAK.is_file() else '',
        'engine_ja_bak': str(ENGINE_JA_BAK) if ENGINE_JA_BAK.is_file() else '',
        'new_rows': len(plan), 'first': [plan[0][0], plan[0][1].isoformat(), plan[0][2].isoformat()],
        'last': [plan[-1][0], plan[-1][1].isoformat(), plan[-1][2].isoformat()],
        'weekly_rewards': WEEKLY_REWARDS, 'weekly_lapis': day_lapis,
        'dialogue_parts': len(dialogue_parts),
        'today': today.isoformat(), 'today_row': next(('' if not (s <= today <= e) else
                                                       '%s %s..%s' % (i, s, e)) for i, s, e in covered
                                                      if s <= today <= e),
        'deploy': [
            'python -I build/deploy_ko_names.py --serial <adb> --only P3raZX89',
            'tar -cf build/out/jp_offline/engine_static.tar -C build/out/jp_offline/engine static',
            'push/extract engine_static.tar to the app data root (docs/REPORT_09 install step 2)',
        ],
    }
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('rows %d..%d, %d new row(s), %d -> %d client rows' % (plan[0][0], plan[-1][0], len(plan),
                                                               len(lines), len(lines) + len(encrypted)))
    print('windows %s..%s / %s..%s, today %s inside %s' % (plan[0][1], plan[0][2], plan[-1][1], plan[-1][2],
                                                           today, report['today_row']))
    print('dialogue: %d Korean rows, %d Japanese left%s, %d empty' %
          (korean_found, jp_found, (' (' + ', '.join(unmatched) + ')') if unmatched else '', empty_found))
    print('wrote', client.name, ', F_LOGIN_BONUS_MST.ndjson, rows_add.ndjson, report.json in', out)
    print('refreshed', KO_CLIENT, 'and', ENGINE_NDJSON)


if __name__ == '__main__':
    main()

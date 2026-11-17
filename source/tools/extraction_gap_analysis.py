import collections
import json
import re
import struct
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"
TAG = re.compile(r"<[^>]+>")
HANGUL = re.compile(r"[\uac00-\ud7a3]")


def read_u16be(data, offset):
    return int.from_bytes(data[offset : offset + 2], "big")


def read_u32be(data, offset):
    return int.from_bytes(data[offset : offset + 4], "big")


def read_u64be(data, offset):
    return int.from_bytes(data[offset : offset + 8], "big")


def decrypt_utf_if_needed(data, offset, length):
    raw = bytes(data[offset : offset + length])
    if raw[:4] == b"@UTF":
        return raw
    multiplier = 0x0000655F
    factor = 0x00004115
    value = bytearray(raw)
    for index in range(length):
        value[index] ^= multiplier & 0xFF
        multiplier = (multiplier * factor) & 0xFFFFFFFF
    return bytes(value)


def utf_layout(data):
    rows_at = read_u32be(data, 8)
    strings_at = read_u32be(data, 12)
    columns = read_u16be(data, 24)
    row_size = read_u16be(data, 26)
    row_count = read_u32be(data, 28)
    strings_base = 8 + strings_at
    columns_at = 32
    column_offsets = {}
    row_offset = 0
    for _ in range(columns):
        flags = data[columns_at]
        name_index = read_u32be(data, columns_at + 1)
        columns_at += 5
        name_start = strings_base + name_index
        name_end = data.find(b"\0", name_start)
        name = data[name_start:name_end].decode("utf-8")
        storage = flags & 0xF0
        kind = flags & 0x0F
        size = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 10: 4, 11: 8}[kind]
        if storage == 0x30:
            columns_at += size
        elif storage == 0x50:
            column_offsets[name] = row_offset
            row_offset += size
    return column_offsets, 8 + rows_at, row_size, row_count, strings_base


def cpk_entries(data):
    header_size = int.from_bytes(data[8:12], "little")
    header = decrypt_utf_if_needed(data, 16, header_size)
    header_columns, header_rows, _, header_row_count, _ = utf_layout(header)
    if header_row_count < 1:
        return {}
    content_offset = read_u64be(header, header_rows + header_columns["ContentOffset"])
    toc_offset = read_u64be(header, header_rows + header_columns["TocOffset"])
    base_offset = min(content_offset, toc_offset)
    toc_packet_offset = int(toc_offset) + 16
    toc_size = int.from_bytes(data[int(toc_offset) + 8 : int(toc_offset) + 12], "little")
    toc = decrypt_utf_if_needed(data, toc_packet_offset, toc_size)
    toc_columns, toc_rows, toc_row_size, toc_row_count, toc_strings = utf_layout(toc)
    entries = {}
    for row in range(toc_row_count):
        row_at = toc_rows + row * toc_row_size
        name_index = read_u32be(toc, row_at + toc_columns["FileName"])
        name_at = toc_strings + name_index
        name_end = toc.find(b"\0", name_at)
        name = toc[name_at:name_end].decode("utf-8")
        size = read_u32be(toc, row_at + toc_columns["FileSize"])
        offset = read_u64be(toc, row_at + toc_columns["FileOffset"])
        start = int(base_offset + offset)
        entries[name] = data[start : start + size]
    return entries


def crilayla(src):
    if src[:8] != b"CRILAYLA":
        return src
    usize, csize = struct.unpack_from("<II", src, 8)
    if len(src) < 0x10 + csize + 0x100:
        raise ValueError("truncated CRILAYLA block")
    out = bytearray(0x100 + usize)
    out[:0x100] = src[0x10 + csize : 0x10 + csize + 0x100]
    pos = 0x10 + csize - 1
    pool = 0
    left = 0
    done = 0
    end = 0x100 + usize - 1

    def bits(count):
        nonlocal pos, pool, left
        value = 0
        got = 0
        while got < count:
            if left == 0:
                pool = src[pos]
                left = 8
                pos -= 1
            take = min(left, count - got)
            value = (value << take) | ((pool >> (left - take)) & ((1 << take) - 1))
            left -= take
            got += take
        return value

    while done < usize:
        if bits(1):
            ref = end - done + bits(13) + 3
            length = 3
            for level in (2, 3, 5):
                value = bits(level)
                length += value
                if value != (1 << level) - 1:
                    break
            else:
                while True:
                    value = bits(8)
                    length += value
                    if value != 0xFF:
                        break
            for _ in range(length):
                out[end - done] = out[ref]
                ref -= 1
                done += 1
        else:
            out[end - done] = bits(8)
            done += 1
    return bytes(out)


def decode_entry(value):
    return crilayla(value) if value[:8] == b"CRILAYLA" else value


def parse_separator_rows(value, separator):
    text = decode_entry(value).decode("utf-8", errors="replace")
    rows = {}
    for line in text.splitlines():
        if not line:
            continue
        ident, mark, body = line.partition(separator)
        if mark and ident.strip():
            rows[ident.strip()] = body
    return rows


def parse_sg_rows(value):
    text = decode_entry(value).decode("utf-8", errors="replace")
    rows = {}
    for line in text.splitlines():
        if not line:
            continue
        fields = line.split("^")
        if fields and fields[0].strip():
            rows[fields[0].strip()] = fields[1:]
    return rows


def clean_text(value):
    text = TAG.sub("", str(value or ""))
    return re.sub(r"\s+", " ", text.replace("…", "...")).strip()


def input_stem(path):
    return path.stem.split("__", 1)[0].lower()


input_rows = {}
input_by_cpk = collections.defaultdict(dict)
for path in sorted((PROJECT / "gt_input").glob("*.json")):
    stem = input_stem(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    input_rows[stem] = len(value)
    input_by_cpk[stem] = {str(row["ffbe_id"]): row for row in value}

meta = json.loads((PROJECT / "script_meta.json").read_text(encoding="utf-8"))
meta_by_cpk = collections.defaultdict(dict)
for row in meta:
    stem = Path(row.get("cpk_name", "")).stem.lower()
    ident = str(row.get("ffbe_id", ""))
    if stem and ident and ident not in meta_by_cpk[stem]:
        meta_by_cpk[stem][ident] = row

missing_ids = {}
missing_chars = 0
missing_with_source = 0
extra_inputs = {}
comparison_files = 0
for stem, rows in meta_by_cpk.items():
    inputs = input_by_cpk.get(stem, {})
    extra = sorted(set(rows) - set(inputs))
    if extra:
        missing_ids[stem] = extra
        missing_with_source += sum(
            bool(rows[ident].get("clean_jp") or rows[ident].get("official_ko_clean"))
            for ident in extra
        )
        missing_chars += sum(
            len(rows[ident].get("clean_jp") or rows[ident].get("english_clean") or "")
            for ident in extra
        )
    if stem in input_by_cpk:
        comparison_files += 1
        only_input = sorted(set(inputs) - set(rows))
        if only_input:
            extra_inputs[stem] = only_input

target = "ngh...enemies...enemies are"


def screenshot_candidate(text):
    text = text.lower()
    return target in text or (
        "ngh" in text and "enemies" in text and text.count("enemies") >= 2
    )


phrase_matches = []
for row in meta:
    if screenshot_candidate(clean_text(row.get("english_clean", ""))):
        phrase_matches.append(
            {
                key: row.get(key)
                for key in (
                    "cpk_name",
                    "ffbe_id",
                    "speaker_jp",
                    "speaker_ko",
                    "clean_jp",
                    "official_ko_clean",
                    "english_clean",
                    "input_file",
                )
            }
        )

result = {
    "gt_input": {
        "files": len(input_by_cpk),
        "rows": sum(len(rows) for rows in input_by_cpk.values()),
    },
    "script_meta": {
        "records": len(meta),
        "cpks": len(meta_by_cpk),
        "unique_records": sum(len(rows) for rows in meta_by_cpk.values()),
    },
    "meta_vs_input": {
        "cpks_compared": comparison_files,
        "missing_record_count": sum(len(rows) for rows in missing_ids.values()),
        "missing_files": len(missing_ids),
        "missing_with_source_text": missing_with_source,
        "missing_source_chars": missing_chars,
        "input_extra_record_count": sum(len(rows) for rows in extra_inputs.values()),
    },
    "screenshot_phrase": {
        "normalized_target": target,
        "meta_matches": phrase_matches,
    },
}

dialogue_path = ROOT.parent / "upstream" / "source" / "server" / "content" / "dialogue_en.json"
if dialogue_path.exists():
    dialogue = json.loads(dialogue_path.read_text(encoding="utf-8"))
    translations = dialogue.get("translations", {})
    dialogue_matches = []
    for key, row in translations.items():
        english = clean_text(row.get("english", "")).lower()
        if screenshot_candidate(english):
            dialogue_matches.append(
                {
                    "key": key,
                    "scene": row.get("scene"),
                    "reference": row.get("reference"),
                    "source": row.get("source"),
                    "english": row.get("english"),
                }
            )
    result["dialogue_en"] = {
        "records": len(translations),
        "screenshot_matches": dialogue_matches,
    }

archive_path = ROOT.parent / "downloads" / "ffbe-jp-ldplayer-assetpacks-11.1.2-verified.tar"
if archive_path.exists():
    scan = collections.Counter()
    extra_characters = 0
    extra_with_korean = 0
    extra_without_korean = 0
    extra_by_cpk = {}
    phrase_hits = []
    with tarfile.open(archive_path, mode="r:") as archive:
        cpk_members = [
            member
            for member in archive
            if member.isfile() and member.name.lower().endswith(".cpk")
        ]
        grouped = collections.defaultdict(list)
        for member in cpk_members:
            grouped[Path(member.name).stem.lower()].append(member)
        target_members = {}
        for stem in input_by_cpk:
            choices = grouped.get(stem, [])
            if choices:
                target_members[stem] = max(choices, key=lambda item: item.size)
        scan_members = {
            stem: max(choices, key=lambda item: item.size)
            for stem, choices in grouped.items()
        }
        scan["archive_cpk_files"] = len(cpk_members)
        scan["archive_unique_cpk_stems"] = len(grouped)
        scan["target_input_cpks"] = len(input_by_cpk)
        scan["target_cpks_found_in_archive"] = len(target_members)
        scan["target_cpks_missing_from_archive"] = len(input_by_cpk) - len(target_members)
        scan["unscoped_archive_cpk_stems"] = len(set(grouped) - set(input_by_cpk))
        parse_error_members = []
        unscoped_counts = {}
        unscoped_korean_characters = 0
        unscoped_unique_messages = set()
        unscoped_samples = {}

        unscoped_text_ids = {}
        for stem, member in scan_members.items():
            handle = archive.extractfile(member)
            if handle is None:
                scan["cpk_read_errors"] += 1
                continue
            try:
                data = handle.read()
                entries = cpk_entries(data)
                scan["cpks_parsed"] += 1
            except Exception:
                scan["cpk_parse_errors"] += 1
                parse_error_members.append(
                    {"member": member.name, "size": member.size}
                )
                continue

            text_entry = next(
                (
                    value
                    for name, value in entries.items()
                    if name.endswith("_event_text.txt")
                ),
                None,
            )
            sg_entry = next(
                (
                    value
                    for name, value in entries.items()
                    if name.endswith("_event_text_sg.txt")
                ),
                None,
            )
            event_bins = [value for name, value in entries.items() if name.endswith("_event.bin")]
            scan["event_bin_entries"] += len(event_bins)
            if event_bins:
                scan["cpks_with_event_bin"] += 1
                if text_entry is None:
                    scan["cpks_with_event_bin_no_text"] += 1
            text_rows = {}
            sg_rows = {}
            if text_entry is not None:
                try:
                    text_rows = parse_separator_rows(text_entry, ",")
                    scan["text_entry_ok"] += 1
                    scan["text_rows"] += len(text_rows)
                except Exception:
                    scan["text_decode_errors"] += 1
            if sg_entry is not None:
                try:
                    sg_rows = parse_sg_rows(sg_entry)
                    scan["sg_entry_ok"] += 1
                    scan["sg_rows"] += len(sg_rows)
                except Exception:
                    scan["sg_decode_errors"] += 1

            inputs = input_by_cpk.get(stem, {})
            text_ids = set(text_rows)
            sg_ids = set(sg_rows)
            if stem not in input_by_cpk and text_ids:
                scan["unscoped_cpks_with_text"] += 1
                scan["unscoped_text_rows"] += len(text_ids)
                scan["unscoped_text_characters"] += sum(
                    len(clean_text(body)) for body in text_rows.values()
                )
                unscoped_counts[stem] = len(text_ids)
                unscoped_text_ids[stem] = len(text_ids)
                scan["unscoped_korean_gap_rows"] += sum(
                    bool(HANGUL.search(body)) is False for body in text_rows.values()
                )
                for ident in text_ids:
                    columns = sg_rows.get(ident, [])
                    korean = columns[2] if len(columns) > 2 else ""
                    if HANGUL.search(korean):
                        scan["unscoped_sg_korean_rows"] += 1
                        unscoped_korean_characters += len(clean_text(korean))
                    else:
                        scan["unscoped_rows_without_korean"] += 1
                unscoped_unique_messages.update(
                    clean_text(body) for body in text_rows.values()
                )
                if len(unscoped_samples) < 5:
                    unscoped_samples[stem] = [
                        {
                            "ffbe_id": ident,
                            "text": clean_text(text_rows[ident]),
                            "sg_english": clean_text(
                                sg_rows.get(ident, ["", ""])[0]
                            ),
                            "sg_korean": clean_text(
                                sg_rows.get(ident, ["", "", ""])[2]
                            ),
                        }
                        for ident in list(text_rows)[:3]
                    ]
            scan["text_ids_extra_to_input"] += len(text_ids - set(inputs))
            scan["sg_ids_extra_to_input"] += len(sg_ids - set(inputs))
            scan["sg_ids_missing_from_input"] += len(sg_ids - set(inputs))
            scan["sg_ids_missing_compared_with_text"] += len(sg_ids - text_ids)
            extra_ids = sorted((text_ids | sg_ids) - set(inputs))
            if extra_ids:
                extra_by_cpk[stem] = extra_ids
                scan["cpks_with_extra_ids"] += 1
            for ident in extra_ids:
                rows = sg_rows.get(ident, [])
                english = rows[0] if rows else text_rows.get(ident, "")
                korean = rows[2] if len(rows) > 2 else ""
                extra_characters += len(clean_text(english))
                if HANGUL.search(korean):
                    extra_with_korean += 1
                else:
                    extra_without_korean += 1

            for source, rows in (("text", text_rows), ("sg", sg_rows)):
                for ident, row in rows.items():
                    payload = row if isinstance(row, str) else "^".join(row)
                    normalized = clean_text(payload).lower()
                    if screenshot_candidate(normalized):
                        phrase_hits.append(
                            {
                                "cpk": stem,
                                "ffbe_id": ident,
                                "source_table": source,
                                "text": payload,
                            }
                        )

    scan["extra_character_count"] = extra_characters
    scan["extra_rows_with_korean_already"] = extra_with_korean
    scan["extra_rows_without_korean"] = extra_without_korean
    scan["unscoped_sg_korean_characters"] = unscoped_korean_characters
    scan["unscoped_unique_messages"] = len(unscoped_unique_messages)
    result["original_cpk_scan"] = dict(scan)
    result["original_cpk_extra_summary"] = {
        "cpks_with_extra_ids": len(extra_by_cpk),
        "extra_ids": sum(len(value) for value in extra_by_cpk.values()),
    }
    result["original_cpk_unscoped_text_summary"] = {
        "cpks_with_text": len(unscoped_counts),
        "largest": sorted(
            unscoped_counts.items(), key=lambda item: item[1], reverse=True
        )[:20],
    }
    result["original_cpk_parse_errors"] = parse_error_members[:100]
    result["original_cpk_unscoped_samples"] = unscoped_samples
    result["original_cpk_phrase_hits"] = phrase_hits

print(json.dumps(result, ensure_ascii=False, indent=2))

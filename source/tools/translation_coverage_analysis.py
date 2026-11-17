import collections
import csv
import json
import re
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"
HANGUL = re.compile(r"[\uac00-\ud7a3]")
KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
LATIN = re.compile(r"[A-Za-z]")


def load_rows(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def row_key(row):
    return str(row.get("ffbe_id", ""))


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
        size = {
            0: 1,
            1: 1,
            2: 2,
            3: 2,
            4: 4,
            5: 4,
            6: 8,
            7: 8,
            10: 4,
            11: 8,
        }.get(kind)
        if size is None:
            raise ValueError("Unsupported UTF column kind")
        if storage == 0x30:
            columns_at += size
        elif storage == 0x50:
            column_offsets[name] = row_offset
            row_offset += size
    return column_offsets, 8 + rows_at, row_size, row_count, strings_base


def cpk_entries(data):
    header_size = int.from_bytes(data[8:12], "little")
    header = decrypt_utf_if_needed(data, 16, header_size)
    header_columns, header_rows, header_row_size, header_row_count, _ = utf_layout(header)
    if header_row_count < 1:
        return {}
    content_offset = read_u64be(header, header_rows + header_columns["ContentOffset"])
    toc_offset = read_u64be(header, header_rows + header_columns["TocOffset"])
    base_offset = min(content_offset, toc_offset)
    toc_packet_offset = int(toc_offset) + 16
    toc_size = int.from_bytes(
        data[int(toc_offset) + 8 : int(toc_offset) + 12], "little"
    )
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


status_path = PROJECT / "runtime" / "file_status.csv"
with status_path.open(encoding="utf-8-sig", newline="") as handle:
    status_rows = list(csv.DictReader(handle))

status_summary = {
    "files": len(status_rows),
    "rows": sum(int(row["row_count"]) for row in status_rows),
    "completed_rows": sum(int(row["completed_rows"]) for row in status_rows),
    "japanese_rows": sum(int(row["japanese_rows"]) for row in status_rows),
    "output_files": sum(row["output_exists"] == "True" for row in status_rows),
    "cache_files": sum(row["cache_exists"] == "True" for row in status_rows),
    "status_files": dict(collections.Counter(row["status"] for row in status_rows)),
    "issue_rows": sum(int(row["issue_count"]) for row in status_rows),
    "incomplete_files": [
        {
            "file": row["file"],
            "rows": int(row["row_count"]),
            "completed_rows": int(row["completed_rows"]),
        }
        for row in status_rows
        if int(row["row_count"]) != int(row["completed_rows"])
    ],
}

message_stats = collections.Counter()
name_stats = collections.Counter()
output_files_with_korean = 0
output_files_scanned = 0
input_names = set()
input_rows_by_name = {}

for input_path in sorted((PROJECT / "gt_input").glob("*.json")):
    input_rows = load_rows(input_path)
    input_names.add(input_path.stem.lower())
    input_rows_by_name[input_path.name] = len(input_rows)
    output_path = PROJECT / "gt_output" / input_path.name
    output_rows = load_rows(output_path)
    output_files_scanned += bool(output_rows)
    if any(HANGUL.search(str(row.get("message", ""))) for row in output_rows):
        output_files_with_korean += 1
    source_by_id = {row_key(row): str(row.get("message", "")) for row in input_rows}
    for row in output_rows:
        message = str(row.get("message", ""))
        source = source_by_id.get(row_key(row), "")
        if HANGUL.search(message):
            message_stats["korean"] += 1
        elif KANA.search(message):
            message_stats["kana_remaining"] += 1
        elif LATIN.search(message):
            message_stats["english_only"] += 1
        else:
            message_stats["neutral_or_blank"] += 1
        if message == source and (KANA.search(source) or LATIN.search(source)):
            message_stats["identical_source"] += 1
        name = str(row.get("name", ""))
        if HANGUL.search(name):
            name_stats["korean"] += 1
        elif name:
            name_stats["non_korean"] += 1
        else:
            name_stats["empty"] += 1

payload_names = set()
payload_sizes = collections.defaultdict(set)
payload_cpk_files = []
payload_entries = 0
payload_unique = 0
with tarfile.open(PROJECT / "story_patch_payload.tar") as archive:
    for member in archive:
        if member.isfile() and member.name.lower().endswith(".cpk"):
            payload_entries += 1
            stem = Path(member.name).stem.lower()
            payload_names.add(stem)
            payload_sizes[stem].add(member.size)
            payload_cpk_files.append((stem, member))
payload_unique = len(payload_names)

input_names_lower = set(input_names)
payload_matches = input_names_lower & payload_names
missing_from_payload = sorted(input_names_lower - payload_names)
payload_rows = sum(
    input_rows_by_name[name + ".json"]
    for name in input_names
    if name in payload_matches and name + ".json" in input_rows_by_name
)

result = {
    "status_summary": status_summary,
    "message_stats": dict(message_stats),
    "name_stats": dict(name_stats),
    "output_files_scanned": output_files_scanned,
    "output_files_with_korean": output_files_with_korean,
    "patch_payload": {
        "cpk_entries": payload_entries,
        "unique_cpk_names": payload_unique,
        "matched_input_files": len(payload_matches),
        "matched_input_rows": payload_rows,
        "input_file_match_pct": round(
            len(payload_matches) * 100 / max(1, len(input_names)), 2
        ),
        "input_row_match_pct": round(
            payload_rows * 100 / max(1, status_summary["rows"]), 2
        ),
        "missing_input_files": len(missing_from_payload),
    },
}

cpk_scan = collections.Counter()
cpk_sg_stems = set()
entry_name_counts = collections.Counter()
for stem, member in payload_cpk_files:
    try:
        with tarfile.open(PROJECT / "story_patch_payload.tar") as archive:
            handle = archive.extractfile(member)
            data = handle.read() if handle else b""
        entries = cpk_entries(data)
        names = list(entries)
        for name in names:
            normalized = re.sub(r"^\d+", "<id>", Path(name).name)
            entry_name_counts[normalized] += 1
        has_text = any(name.endswith("_text.txt") for name in names)
        has_sg = any(name.endswith("_text_sg.txt") for name in names)
        cpk_scan["files_scanned"] += 1
        cpk_scan["text"] += has_text
        cpk_scan["text_sg"] += has_sg
        cpk_scan["text_and_sg"] += has_text and has_sg
        if has_sg:
            cpk_sg_stems.add(stem)
            sg = next(
                value
                for name, value in entries.items()
                if name.endswith("_text_sg.txt")
            )
            cpk_scan["text_sg_crilayla"] += sg.startswith(b"CRILAYLA")
            cpk_scan["text_sg_plain"] += not sg.startswith(b"CRILAYLA")
            cpk_scan["text_sg_plain_korean"] += (
                not sg.startswith(b"CRILAYLA")
                and bool(HANGUL.search(sg.decode("utf-8", errors="ignore")))
            )
    except Exception:
        cpk_scan["parse_errors"] += 1
result["cpk_internal"] = dict(cpk_scan)
result["cpk_internal"]["text_sg_stems"] = len(cpk_sg_stems)
result["cpk_internal"]["entry_name_counts"] = entry_name_counts.most_common(100)

try:
    remote = subprocess.run(
        [
            "adb",
            "shell",
            "find /data/data/com.exvius.memorial.korean/files -type f "
            "-name '*.cpk' -printf '%s\\t%p\\n'",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    remote_rows = []
    for line in remote.splitlines():
        size, _, path = line.partition("\t")
        if size.isdigit() and path:
            remote_rows.append((int(size), Path(path).stem.lower(), path))
    remote_matches = [
        row for row in remote_rows if row[0] in payload_sizes.get(row[1], set())
    ]
    remote_matched_stems = {row[1] for row in remote_matches}
    installed_stems = {row[1] for row in remote_rows}
    installed_story_rows = sum(
        input_rows_by_name[stem + ".json"]
        for stem in installed_stems
        if stem + ".json" in input_rows_by_name
    )
    installed_matched_rows = sum(
        input_rows_by_name[stem + ".json"]
        for stem in remote_matched_stems
        if stem + ".json" in input_rows_by_name
    )
    result["installed_data"] = {
        "cpk_files": len(remote_rows),
        "unique_cpk_stems": len({row[1] for row in remote_rows}),
        "payload_size_matches": len(remote_matches),
        "payload_size_match_unique_stems": len(remote_matched_stems),
        "payload_size_match_rows": installed_matched_rows,
        "installed_story_rows": installed_story_rows,
        "payload_size_match_pct_of_install": round(
            len(remote_matches) * 100 / max(1, len(remote_rows)), 2
        ),
        "payload_size_match_pct_of_installed_story_rows": round(
            installed_matched_rows * 100 / max(1, installed_story_rows), 2
        ),
        "payload_size_match_input_row_pct": round(
            installed_matched_rows * 100 / max(1, status_summary["rows"]), 2
        ),
    }
except Exception as exc:
    result["installed_data"] = {"error": str(exc)}

print(json.dumps(result, ensure_ascii=False, indent=2))

import collections
import csv
import io
import json
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
JP_ASSETPACKS = ROOT / "jp-memorial-11.1.2-original" / "assetpacks"
PROJECT = ROOT / "chapter1-ko"
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "555"
LABEL = sys.argv[2] if len(sys.argv) > 2 else "chapter5"
OUTPUT = ROOT / f"{LABEL}-gap"
KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
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


def text_rows(payload):
    payload = crilayla(payload) if payload[:8] == b"CRILAYLA" else payload
    rows = {}
    for line in payload.decode("utf-8", errors="replace").splitlines():
        if not line:
            continue
        ident, separator, body = line.partition(",")
        if separator and ident.strip():
            rows[ident.strip()] = body
    return rows


def sg_rows(payload):
    payload = crilayla(payload) if payload[:8] == b"CRILAYLA" else payload
    rows = {}
    for line in payload.decode("utf-8", errors="replace").splitlines():
        if not line:
            continue
        fields = line.split("^")
        if fields and fields[0].strip():
            rows[fields[0].strip()] = fields[1:]
    return rows


def assetpack_members():
    members = {}
    for path in JP_ASSETPACKS.rglob(f"{PREFIX}*.cpk"):
        members.setdefault(path.name.lower(), []).append(path)
    return {
        name: max(paths, key=lambda path: path.stat().st_size)
        for name, paths in members.items()
    }


current_inputs = {
    path.stem.split("__", 1)[0].lower()
    for path in (PROJECT / "gt_input").glob("*.json")
}

rows = []
for name, path in sorted(assetpack_members().items()):
    entry = {
        "cpk": name,
        "path": path.as_posix(),
        "in_current_input": name[:-4] in current_inputs,
        "file_size": path.stat().st_size,
        "text_rows": 0,
        "sg_rows": 0,
        "text_characters": 0,
        "japanese_rows": 0,
        "korean_rows": 0,
        "parse_error": "",
    }
    try:
        entries = cpk_entries(path.read_bytes())
        text_entry = next(
            (value for key, value in entries.items() if key.endswith("_event_text.txt")),
            None,
        )
        sg_entry = next(
            (value for key, value in entries.items() if key.endswith("_event_text_sg.txt")),
            None,
        )
        text = text_rows(text_entry) if text_entry else {}
        sg = sg_rows(sg_entry) if sg_entry else {}
        entry["text_rows"] = len(text)
        entry["sg_rows"] = len(sg)
        entry["text_characters"] = sum(len(re.sub(r"<[^>]+>", "", value)) for value in text.values())
        entry["japanese_rows"] = sum(bool(KANA.search(value)) for value in text.values())
        entry["korean_rows"] = sum(
            bool(HANGUL.search(fields[2])) for fields in sg.values() if len(fields) > 2
        )
    except Exception as error:
        entry["parse_error"] = f"{type(error).__name__}: {error}"
    rows.append(entry)

OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / f"{LABEL}_manifest.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (OUTPUT / f"{LABEL}_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

summary = {
    "cpks": len(rows),
    "cpks_with_text": sum(row["text_rows"] > 0 for row in rows),
    "cpks_without_text": sum(row["text_rows"] == 0 for row in rows),
    "cpks_in_current_input": sum(row["in_current_input"] for row in rows),
    "text_rows": sum(row["text_rows"] for row in rows),
    "sg_rows": sum(row["sg_rows"] for row in rows),
    "text_characters": sum(row["text_characters"] for row in rows),
    "japanese_rows": sum(row["japanese_rows"] for row in rows),
    "korean_rows_in_source_sg": sum(row["korean_rows"] for row in rows),
    "parse_errors": sum(bool(row["parse_error"]) for row in rows),
    "groups": dict(
        sorted(
            collections.Counter(row["cpk"][:5] for row in rows).items()
        )
    ),
    "manifest_json": str(OUTPUT / f"{LABEL}_manifest.json"),
    "manifest_csv": str(OUTPUT / f"{LABEL}_manifest.csv"),
}

group_stats = {}
for group in sorted({row["cpk"][:5] for row in rows}):
    selected = [row for row in rows if row["cpk"].startswith(group)]
    group_stats[group] = {
        "cpks": len(selected),
        "cpks_with_text": sum(row["text_rows"] > 0 for row in selected),
        "rows": sum(row["text_rows"] for row in selected),
        "characters": sum(row["text_characters"] for row in selected),
        "japanese_rows": sum(row["japanese_rows"] for row in selected),
        "in_current_input": sum(row["in_current_input"] for row in selected),
    }
summary["group_stats"] = group_stats

try:
    command = (
    "find /storage/emulated/0/Android/data/com.exvius.memorial.korean/"
        f"files/assetpacks -type f -name '{PREFIX}*.cpk' -printf '%f\\t%s\\n'"
    )
    output = subprocess.run(
        ["adb", "-s", "emulator-5558", "shell", command],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    current = {}
    for line in output.splitlines():
        name, separator, size = line.partition("\t")
        if separator and size.isdigit():
            current[name.lower()] = int(size)
    expected = {row["cpk"] for row in rows}
    summary["korean_client"] = {
        "cpk_count": len(current),
        "bytes": sum(current.values()),
        "missing_from_client": sorted(expected - set(current)),
    }
except Exception as error:
    summary["korean_client"] = {"error": f"{type(error).__name__}: {error}"}

print(json.dumps(summary, ensure_ascii=False, indent=2))

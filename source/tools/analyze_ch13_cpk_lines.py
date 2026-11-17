import collections
import re
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "ch13-debug"
OUT.mkdir(parents=True, exist_ok=True)
SERIAL = "emulator-5558"
REMOTE_ROOT = (
    "/storage/emulated/0/Android/data/com.exevius.memorial.korean/files/assetpacks"
)
REMOTE_ROOT = REMOTE_ROOT.replace("exevius", "exvius")


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


command = (
    f"find {REMOTE_ROOT} -type f -name '55413*.cpk' "
    "-printf '%p\\t%s\\n'"
)
output = subprocess.run(
    ["adb", "-s", SERIAL, "shell", command],
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
).stdout
paths = []
for line in output.splitlines():
    path, separator, size = line.partition("\t")
    if separator and size.isdigit() and int(size) < 1_000_000:
        paths.append(path)

results = []
for remote in paths:
    name = Path(remote).name
    local = OUT / name
    subprocess.run(
        ["adb", "-s", SERIAL, "pull", remote, str(local)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    entries = cpk_entries(local.read_bytes())
    file_lines = []
    for entry_name, payload in entries.items():
        if not entry_name.endswith(".txt"):
            continue
        try:
            decoded = crilayla(payload)
        except Exception:
            continue
        for line in decoded.splitlines():
            file_lines.append(
                {
                    "entry": entry_name,
                    "bytes": len(line),
                    "text": line.decode("utf-8", errors="replace"),
                }
            )
    file_lines.sort(key=lambda item: item["bytes"], reverse=True)
    results.append(
        {
            "cpk": name,
            "max_bytes": file_lines[0]["bytes"] if file_lines else 0,
            "over_240": [item for item in file_lines if item["bytes"] > 240],
            "top": file_lines[:3],
        }
    )

results.sort(key=lambda item: item["max_bytes"], reverse=True)
print(
    __import__("json").dumps(
        {
            "cpks": len(results),
            "over_240_total": sum(len(item["over_240"]) for item in results),
            "largest": results,
        },
        ensure_ascii=False,
        indent=2,
    )
)

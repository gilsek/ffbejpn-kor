import struct
import hashlib
import json
import re
import zipfile
import zlib
from pathlib import Path

import requests


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
        extract_size = read_u32be(toc, row_at + toc_columns["ExtractSize"])
        offset = read_u64be(toc, row_at + toc_columns["FileOffset"])
        start = int(base_offset + offset)
        entries[name] = (data[start : start + size], size, extract_size)
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


cpk = Path("artifacts/725040601.current.cpk")
entries = cpk_entries(cpk.read_bytes())
for name, (value, stored_size, extract_size) in entries.items():
    if not name.endswith((".txt", ".bin")):
        continue
    print(f"=== {name} stored={stored_size} extract={extract_size} raw={len(value)} prefix={value[:8]!r}")
    if value[:8] == b"CRILAYLA":
        print(f"header_le={struct.unpack_from('<II', value, 8)} header_be={struct.unpack_from('>II', value, 8)} head_hex={value[:32].hex()}")
    try:
        plain = crilayla(value)
        print(f"decoded={len(plain)}")
        needle = b"enemies are"
        offset = plain.find(needle)
        if offset >= 0:
            start = max(0, offset - 160)
            end = min(len(plain), offset + 320)
            print(f"MATCH offset={offset} context={plain[start:end]!r}")
        if name.endswith(".txt"):
            print(plain[:4000].decode("utf-8", errors="replace"))
        if name.endswith("_event.bin"):
            candidates = [
                value.decode("ascii")
                for value in re.findall(rb"[\x20-\x7e]{12,}", plain)
                if len(value.split()) >= 3 and sum(c.isalpha() for c in value) >= 12
            ]
            print(f"PRINTABLE_CANDIDATES={candidates[:50]}")
    except Exception as error:
        print(f"decode_error={error!r}")

print("=== original delivery entry")
with zipfile.ZipFile("artifacts/korean-packaged/ffbe-korean-memorial-final.apk") as apk:
    manifest = apk.read("assets/content_delivery.tsv").decode("utf-8")
row = next(
    line
    for line in manifest.splitlines()
    if line.startswith("side_stories/725040601.cpk\t")
)
fields = row.split("\t")
url = fields[3].split("#", 1)[0]
range_spec = fields[3].split("#ffbe-range=", 1)[1]
offset, length, _ = (int(value) for value in range_spec.split(":"))
response = requests.get(
    url,
    headers={"Range": f"bytes={offset}-{offset + length - 1}"},
    timeout=60,
)
print(f"range_status={response.status_code} bytes={len(response.content)} expected={length}")
response.raise_for_status()
if len(response.content) != length:
    raise RuntimeError("Unexpected range length")
print(f"sha256={hashlib.sha256(response.content).hexdigest()} expected={fields[1]}")
original = zlib.decompress(response.content, -15)
print(
    f"source_bytes={len(original)} expected={fields[2]} "
    f"sha256={hashlib.sha256(original).hexdigest()}"
)
original_entries = cpk_entries(original)
for name, (value, stored_size, extract_size) in original_entries.items():
    if name.endswith("_text_sg.txt"):
        print(
            f"ORIGINAL {name} stored={stored_size} extract={extract_size} raw={len(value)} prefix={value[:8]!r} "
            f"header_le={struct.unpack_from('<II', value, 8)}"
        )
        try:
            plain = crilayla(value)
            print(f"ORIGINAL decoded={len(plain)}")
            print(plain[:4000].decode("utf-8", errors="replace"))
        except Exception as error:
            print(f"ORIGINAL decode_error={error!r}")

print("=== script_meta exact phrase candidates")
meta = json.loads(Path("artifacts/chapter1-ko/script_meta.json").read_text(encoding="utf-8"))
for record in meta:
    english = str(record.get("english_clean", ""))
    if "enemies" in english and ("Ngh" in english or "Ngh" in str(record.get("raw_jp", ""))):
        print(
            {
                key: record.get(key)
                for key in (
                    "cpk_name",
                    "ffbe_id",
                    "speaker_jp",
                    "speaker_ko",
                    "clean_jp",
                    "official_ko_clean",
                    "english_clean",
                    "block",
                )
            }
        )

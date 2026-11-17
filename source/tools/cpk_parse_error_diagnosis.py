import collections
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / "downloads" / "ffbe-jp-ldplayer-assetpacks-11.1.2-verified.tar"


def ascii_head(value):
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in value)


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


def parse_cpk(data):
    header_size = int.from_bytes(data[8:12], "little")
    header = decrypt_utf_if_needed(data, 16, header_size)
    header_columns, header_rows, _, header_row_count, _ = utf_layout(header)
    if header_row_count < 1:
        raise ValueError("header has no rows")
    content_offset = read_u64be(header, header_rows + header_columns["ContentOffset"])
    toc_offset = read_u64be(header, header_rows + header_columns["TocOffset"])
    base_offset = min(content_offset, toc_offset)
    toc_packet_offset = int(toc_offset) + 16
    toc_size = int.from_bytes(data[int(toc_offset) + 8 : int(toc_offset) + 12], "little")
    toc = decrypt_utf_if_needed(data, toc_packet_offset, toc_size)
    toc_columns, toc_rows, toc_row_size, toc_row_count, toc_strings = utf_layout(toc)
    for row in range(toc_row_count):
        row_at = toc_rows + row * toc_row_size
        name_index = read_u32be(toc, row_at + toc_columns["FileName"])
        name_at = toc_strings + name_index
        name_end = toc.find(b"\0", name_at)
        name = toc[name_at:name_end].decode("utf-8")
        size = read_u32be(toc, row_at + toc_columns["FileSize"])
        offset = read_u64be(toc, row_at + toc_columns["FileOffset"])
        start = int(base_offset + offset)
        if start + size > len(data):
            raise ValueError(
                f"entry {name} points past EOF ({start}+{size}>{len(data)})"
            )


def classify(member, data, error):
    if len(data) < 16:
        return "too-small"
    if data[:4] != b"CPK ":
        return "not-standard-cpk-magic"
    header_size = int.from_bytes(data[8:12], "little")
    if header_size <= 0 or 16 + header_size > len(data):
        return "invalid-header-size"
    header = data[16 : 16 + header_size]
    if header[:4] not in (b"@UTF", b"\x1f\x9e\xf3\xf5"):
        return "unexpected-header-signature"
    return f"parser-error:{type(error).__name__}"


with tarfile.open(ARCHIVE, "r:") as archive:
    grouped = collections.defaultdict(list)
    for member in archive:
        if member.isfile() and member.name.lower().endswith(".cpk"):
            grouped[Path(member.name).stem.lower()].append(member)

    chosen = {
        stem: max(members, key=lambda item: item.size)
        for stem, members in grouped.items()
    }
    errors = []
    for stem, member in chosen.items():
        handle = archive.extractfile(member)
        data = handle.read() if handle else b""
        try:
            parse_cpk(data)
        except Exception as error:
            text_preview = data[:240].decode("utf-8", errors="replace")
            errors.append(
                {
                    "cpk": stem,
                    "member": member.name,
                    "size": member.size,
                    "magic": ascii_head(data[:8]),
                    "hex": data[:64].hex(),
                    "category": classify(member, data, error),
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "preview": text_preview,
                }
            )

category_counts = collections.Counter(item["category"] for item in errors)
prefix_counts = collections.Counter(item["cpk"][:3] for item in errors)
result = {
    "count": len(errors),
    "categories": dict(category_counts),
    "prefixes": dict(prefix_counts),
    "errors": errors,
}
print(json.dumps(result, ensure_ascii=False, indent=2))

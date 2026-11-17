"""Rebuild the translated chapter 13 event CPKs with a valid CPK writer.

The legacy CpkPatcher rewrote offsets manually and produced chunk headers that
the game could not always read.  This script starts from the unmodified release
CPK and uses cricodecs to replace only the translated text tables.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ROOT = PROJECT_DIR.parents[1]
RELEASE_DIR = ROOT / "downloads" / "release-2026.11.04.9"
GT_OUTPUT = PROJECT_DIR / "gt_output"
OUTPUT_DIR = PROJECT_DIR / "ch13-rebuilt"
VENDOR_DIR = ROOT / "analysis" / "vendor"

PREFIX = "55413"
NAME_TAG = re.compile(r"^(<name(?:_npc)?=[^>]+>(?:<br>)?)", re.IGNORECASE)
WAIT_SUFFIX = re.compile(r"(<wait=\d+>)+$", re.IGNORECASE)


def load_translations(stem: str) -> tuple[dict[str, str], dict[str, str]]:
    path = GT_OUTPUT / f"{stem}.json"
    if not path.exists():
        return {}, {}

    messages: dict[str, str] = {}
    names: dict[str, str] = {}
    for row in json.loads(path.read_text(encoding="utf-8-sig")):
        row_id = str(row["ffbe_id"])
        messages[row_id] = str(row.get("message") or "")
        name = row.get("name")
        if name:
            names[row_id] = str(name)
    return messages, names


def format_message(message: str) -> str:
    return (
        message.replace("\r", "")
        .replace("[PAGE]\n", "<page><br>")
        .replace("[PAGE]", "<page><br>")
        .replace("\n", "<br>")
    )


def replace_text_table(text: str, translations: dict[str, str]) -> bytes:
    output: list[str] = []
    for line in text.splitlines():
        row_id, separator, body = line.partition(",")
        if separator and row_id in translations:
            prefix_match = NAME_TAG.match(body)
            suffix_match = WAIT_SUFFIX.search(body)
            prefix = prefix_match.group(1) if prefix_match else ""
            suffix = suffix_match.group(1) if suffix_match else ""
            body = prefix + format_message(translations[row_id]) + suffix
        output.append(f"{row_id},{body}" if separator else line)
    return ("\r\n".join(output) + "\r\n").encode("utf-8")


def replace_sg_table(text: str, translations: dict[str, str]) -> bytes:
    output: list[str] = []
    for line in text.splitlines():
        fields = line.split("^")
        if len(fields) > 3 and fields[0] in translations:
            source = fields[1]
            prefix_match = NAME_TAG.match(source)
            suffix_match = WAIT_SUFFIX.search(source)
            prefix = prefix_match.group(1) if prefix_match else ""
            suffix = suffix_match.group(1) if suffix_match else ""
            formatted = prefix + format_message(translations[fields[0]]) + suffix
            fields[1] = formatted
            fields[3] = formatted
        output.append("^".join(fields))
    return ("\r\n".join(output) + "\r\n").encode("utf-8")


def release_cpks() -> dict[str, tuple[Path, str]]:
    found: dict[str, tuple[Path, str]] = {}
    for zip_path in sorted(RELEASE_DIR.glob("exvius-data-*.zip")):
        with zipfile.ZipFile(zip_path) as archive:
            for entry_name in archive.namelist():
                if "/event4/13/" not in entry_name or not entry_name.endswith(".cpk"):
                    continue
                raw_stem = Path(entry_name).stem
                clean_stem = re.sub(r"^Ver\d+_", "", raw_stem)
                if clean_stem.startswith(PREFIX) and clean_stem not in found:
                    found[clean_stem] = (zip_path, entry_name)
    return found


def rebuild() -> list[dict[str, object]]:
    sys.path.insert(0, str(VENDOR_DIR))
    from cricodecs import cpk  # type: ignore[import-not-found]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = release_cpks()
    results: list[dict[str, object]] = []

    for stem in sorted(GT_OUTPUT.glob(f"{PREFIX}*.json")):
        clean_stem = stem.stem
        source = sources.get(clean_stem)
        if source is None:
            results.append({"cpk": f"{clean_stem}.cpk", "status": "source-missing"})
            continue

        translations, _ = load_translations(clean_stem)
        zip_path, entry_name = source
        with zipfile.ZipFile(zip_path) as archive:
            original = archive.read(entry_name)

        archive_cpk = cpk.Cpk.load_bytes(original)
        entries = {item.filename: item for item in archive_cpk.file_infos()}
        replaced: list[str] = []

        text_name = f"{clean_stem}_event_text.txt"
        if text_name in entries:
            text = archive_cpk.file_bytes(entries[text_name].toc_index).decode("utf-8-sig")
            archive_cpk.replace_bytes(
                entries[text_name].toc_index,
                replace_text_table(text, translations),
                compress=False,
            )
            replaced.append(text_name)

        sg_name = f"{clean_stem}_event_text_sg.txt"
        if sg_name in entries:
            text = archive_cpk.file_bytes(entries[sg_name].toc_index).decode("utf-8-sig")
            archive_cpk.replace_bytes(
                entries[sg_name].toc_index,
                replace_sg_table(text, translations),
                compress=False,
            )
            replaced.append(sg_name)

        output_path = OUTPUT_DIR / f"{clean_stem}.cpk"
        archive_cpk.save(output_path)

        # Reload from disk so verification exercises the same serialized bytes.
        verified = cpk.Cpk.load(output_path)
        for item in verified.file_infos():
            data = verified.file_bytes(item.toc_index)
            if item.filename.endswith(".txt") and data.startswith(b"CRILAYLA"):
                raise ValueError(f"{output_path.name}: compressed bytes exposed as {item.filename}")

        results.append(
            {
                "cpk": output_path.name,
                "status": "ok",
                "bytes": output_path.stat().st_size,
                "replaced": replaced,
                "rows": len(translations),
            }
        )

    return results


if __name__ == "__main__":
    print(json.dumps(rebuild(), ensure_ascii=False, indent=2))

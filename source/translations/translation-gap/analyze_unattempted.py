"""Find Japanese story rows that never reached gt_input.

The existing gt_input/gt_output comparison answers whether extracted rows were
translated.  This audit instead compares every Japanese event-text row with the
IDs actually present in gt_input, exposing source content that was never
extracted and therefore could not be translated.
"""

from __future__ import annotations

import collections
import csv
import json
import re
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ROOT = PROJECT_DIR.parents[1]
INPUT_DIR = ROOT / "artifacts" / "chapter1-ko" / "gt_input"
OUTPUT_DIR = ROOT / "artifacts" / "chapter1-ko" / "gt_output"
JP_ASSET_DIR = (
    ROOT / "artifacts" / "jp-memorial-11.1.2-original" / "assetpacks"
)
VENDOR_DIR = ROOT / "analysis" / "vendor"

NAME_TAG = re.compile(r"<name(?:_npc)?=([^>]+)>(?:<br>)?", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"[ \t\u3000]+")


def input_stem(path: Path) -> str:
    return path.stem.split("__", 1)[0].lower()


def clean_source(text: str) -> str:
    text = re.sub(r"(?i)<invalid_touchwait>", "", text)
    text = text.lstrip("\r\n \t\u3000")
    text = NAME_TAG.sub("", text, count=1)
    text = re.sub(r"(?i)<page>(?:<br>)?", "[PAGE]\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<wait=\d+>", "", text)
    text = re.sub(r"(?i)<speed=\d+>", "", text)
    text = re.sub(r"(?i)<keywait>", "", text)
    return text.replace("\\n", "\n").strip()


def parse_text_table(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8-sig")
    rows: dict[str, str] = {}
    for line in text.splitlines():
        row_id, separator, body = line.partition(",")
        if separator and row_id.strip():
            rows[row_id.strip()] = body
    return rows


def parse_teller_table(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in data.decode("utf-8-sig").splitlines():
        speaker_id, separator, name = line.partition(",")
        if separator and speaker_id.strip():
            result[speaker_id.strip()] = name.strip()
    return result


def source_candidates() -> dict[str, Path]:
    candidates: dict[str, Path] = {}
    for path in JP_ASSET_DIR.rglob("*.cpk"):
        stem = path.stem.lower()
        previous = candidates.get(stem)
        if previous is None or path.stat().st_size > previous.stat().st_size:
            candidates[stem] = path
    return candidates


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze() -> None:
    sys.path.insert(0, str(VENDOR_DIR))
    from cricodecs import cpk  # type: ignore[import-not-found]

    OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)

    input_files = sorted(INPUT_DIR.glob("*.json"))
    output_files = sorted(OUTPUT_DIR.glob("*.json"))
    input_ids: dict[str, set[str]] = collections.defaultdict(set)
    input_rows = 0
    for path in input_files:
        stem = input_stem(path)
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
        input_rows += len(rows)
        input_ids[stem].update(str(row["ffbe_id"]) for row in rows)

    missing_rows: list[dict[str, object]] = []
    missing_cpks: list[dict[str, object]] = []
    parse_errors: list[dict[str, object]] = []
    group_stats: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    source_text_cpks = 0
    source_text_rows = 0
    matched_rows = 0
    candidates = source_candidates()

    for index, (stem, path) in enumerate(sorted(candidates.items()), 1):
        try:
            package = cpk.Cpk.load(path)
        except Exception as error:
            parse_errors.append(
                {
                    "cpk": f"{stem}.cpk",
                    "path": str(path.relative_to(ROOT)),
                    "size": path.stat().st_size,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            continue

        text_entries = [
            item
            for item in package.file_infos()
            if item.filename.endswith("_event_text.txt")
        ]
        if not text_entries:
            continue

        source_text_cpks += 1
        known_ids = input_ids.get(stem, set())
        cpk_missing: list[dict[str, object]] = []
        cpk_source_rows: set[str] = set()
        teller_entries = [
            item
            for item in package.file_infos()
            if item.filename.endswith("_event_teller.txt")
        ]
        tellers: dict[str, str] = {}
        for item in teller_entries:
            try:
                tellers.update(parse_teller_table(package.file_bytes(item.toc_index)))
            except Exception:
                continue
        for item in text_entries:
            try:
                table = parse_text_table(package.file_bytes(item.toc_index))
            except Exception as error:
                parse_errors.append(
                    {
                        "cpk": f"{stem}.cpk",
                        "path": str(path.relative_to(ROOT)),
                        "size": path.stat().st_size,
                        "entry": item.filename,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
                continue

            for row_id, raw_source in table.items():
                if row_id in cpk_source_rows:
                    continue
                cpk_source_rows.add(row_id)
                source_text_rows += 1
                if row_id in known_ids:
                    matched_rows += 1
                    continue

                cleaned = clean_source(raw_source)
                name_match = NAME_TAG.search(raw_source)
                speaker_tag = name_match.group(0) if name_match else ""
                speaker_id = name_match.group(1) if name_match else ""
                row = {
                    "cpk": f"{stem}.cpk",
                    "ffbe_id": row_id,
                    "source_entry": item.filename,
                    "source_jp_raw": raw_source,
                    "source_jp_clean": cleaned,
                    "speaker_tag": speaker_tag,
                    "speaker_id": speaker_id,
                    "speaker_jp": tellers.get(speaker_id, ""),
                    "is_blank": not bool(cleaned),
                    "source_jp_bytes": len(cleaned.encode("utf-8")),
                    "source_jp_characters": len(cleaned),
                    "group": stem[:5],
                    "input_presence": "partial-cpk" if stem in input_ids else "whole-cpk",
                    "source_path": str(path.relative_to(ROOT)),
                }
                missing_rows.append(row)
                cpk_missing.append(row)

        if cpk_missing:
            total_bytes = sum(int(row["source_jp_bytes"]) for row in cpk_missing)
            missing_cpks.append(
                {
                    "cpk": f"{stem}.cpk",
                    "group": stem[:5],
                    "input_presence": (
                        "partial-cpk" if stem in input_ids else "whole-cpk"
                    ),
                    "missing_rows": len(cpk_missing),
                    "source_rows": len(cpk_source_rows),
                    "missing_bytes": total_bytes,
                    "ffbe_ids": ",".join(
                        str(row["ffbe_id"])
                        for row in sorted(
                            cpk_missing, key=lambda item: str(item["ffbe_id"])
                        )
                    ),
                    "source_path": str(path.relative_to(ROOT)),
                }
            )
            stats = group_stats[stem[:5]]
            stats["cpks"] += 1
            stats["rows"] += len(cpk_missing)
            stats["bytes"] += total_bytes
            stats["whole_cpks"] += int(stem not in input_ids)
            stats["partial_cpks"] += int(stem in input_ids)

        if index % 250 == 0:
            print(
                f"scanned {index}/{len(candidates)} CPKs; "
                f"missing rows={len(missing_rows)}",
                file=sys.stderr,
                flush=True,
            )

    missing_rows.sort(key=lambda row: (str(row["group"]), str(row["cpk"]), str(row["ffbe_id"])))
    missing_cpks.sort(key=lambda row: (str(row["group"]), str(row["cpk"])))
    unique_messages = {
        str(row["source_jp_clean"]) for row in missing_rows if row["source_jp_clean"]
    }
    summary = {
        "inputs": {
            "files": len(input_files),
            "outputs": len(output_files),
            "missing_outputs": len(
                [path for path in input_files if not (OUTPUT_DIR / path.name).exists()]
            ),
            "rows": input_rows,
            "cpk_stems": len(input_ids),
        },
        "japanese_assets": {
            "unique_cpk_stems": len(candidates),
            "cpks_with_event_text": source_text_cpks,
            "event_text_rows": source_text_rows,
            "rows_already_in_input": matched_rows,
            "parse_errors": len(parse_errors),
        },
        "unattempted": {
            "cpks": len(missing_cpks),
            "whole_cpks": sum(
                row["input_presence"] == "whole-cpk" for row in missing_cpks
            ),
            "partial_cpks": sum(
                row["input_presence"] == "partial-cpk" for row in missing_cpks
            ),
            "rows": len(missing_rows),
            "unique_messages": len(unique_messages),
            "blank_rows": sum(bool(row["is_blank"]) for row in missing_rows),
            "characters": sum(
                int(row["source_jp_characters"]) for row in missing_rows
            ),
            "utf8_bytes": sum(int(row["source_jp_bytes"]) for row in missing_rows),
        },
        "groups": {
            group: dict(stats) for group, stats in sorted(group_stats.items())
        },
    }

    (PROJECT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (PROJECT_DIR / "missing-cpks.json").write_text(
        json.dumps(missing_cpks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (PROJECT_DIR / "missing-rows.json").write_text(
        json.dumps(missing_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (PROJECT_DIR / "parse-errors.json").write_text(
        json.dumps(parse_errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(
        PROJECT_DIR / "missing-cpks.csv",
        missing_cpks,
        [
            "group",
            "cpk",
            "input_presence",
            "source_rows",
            "missing_rows",
            "missing_bytes",
            "ffbe_ids",
            "source_path",
        ],
    )
    write_csv(
        PROJECT_DIR / "missing-rows.csv",
        missing_rows,
        [
            "group",
            "cpk",
            "ffbe_id",
            "source_entry",
            "input_presence",
            "source_jp_bytes",
            "source_jp_characters",
            "speaker_tag",
            "speaker_id",
            "speaker_jp",
            "is_blank",
            "source_jp_clean",
            "source_jp_raw",
            "source_path",
        ],
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    analyze()

"""Build GalTransl input JSON files for the untranslated source scenes."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ROOT = PROJECT_DIR.parents[1]
MISSING_CPKS = PROJECT_DIR / "missing-cpks.json"
MISSING_ROWS = PROJECT_DIR / "missing-rows.json"
OUTPUT_DIR = PROJECT_DIR / "gt_input-new"
VENDOR_DIR = ROOT / "analysis" / "vendor"

NAME_TAG = re.compile(r"<name(?:_npc)?=([^>]+)>(?:<br>)?", re.IGNORECASE)


def clean_ffbe_dialogue(raw: str) -> str:
    text = re.sub(r"(?i)<invalid_touchwait>", "", raw or "")
    text = text.lstrip("\r\n \t\u3000")
    text = NAME_TAG.sub("", text, count=1)
    text = re.sub(r"(?i)<page>(?:<br>)?", "[PAGE]\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<wait=\d+>", "", text)
    text = re.sub(r"(?i)<speed=\d+>", "", text)
    text = re.sub(r"(?i)<keywait>", "", text)
    return text.replace("\\n", "\n").strip()


def parse_text_rows(data: bytes) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in data.decode("utf-8-sig").splitlines():
        row_id, separator, body = line.partition(",")
        if separator and row_id.strip():
            rows.append((row_id.strip(), body))
    return rows


def parse_tellers(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in data.decode("utf-8-sig").splitlines():
        speaker_id, separator, name = line.partition(",")
        if separator and speaker_id.strip():
            result[speaker_id.strip()] = name.strip()
    return result


def build() -> None:
    sys.path.insert(0, str(VENDOR_DIR))
    from cricodecs import cpk  # type: ignore[import-not-found]

    missing_cpks = json.loads(MISSING_CPKS.read_text(encoding="utf-8"))
    missing_rows = json.loads(MISSING_ROWS.read_text(encoding="utf-8"))
    missing_ids: dict[str, set[str]] = {}
    for row in missing_rows:
        missing_ids.setdefault(row["cpk"], set()).add(str(row["ffbe_id"]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_files: list[dict[str, object]] = []
    written_rows = 0
    skipped_blank: list[dict[str, str]] = []

    for item in missing_cpks:
        cpk_name = str(item["cpk"])
        source_path = ROOT / str(item["source_path"])
        package = cpk.Cpk.load(source_path)
        entries = {entry.filename: entry for entry in package.file_infos()}

        text_name = next(
            (name for name in entries if name.endswith("_event_text.txt")), None
        )
        if text_name is None:
            raise FileNotFoundError(f"{cpk_name}: event_text entry missing")
        text_rows = parse_text_rows(
            package.file_bytes(entries[text_name].toc_index)
        )

        teller_name = next(
            (name for name in entries if name.endswith("_event_teller.txt")), None
        )
        tellers = (
            parse_tellers(package.file_bytes(entries[teller_name].toc_index))
            if teller_name
            else {}
        )

        wanted_ids = missing_ids.get(cpk_name, set())
        output_rows: list[dict[str, str]] = []
        for row_id, raw_source in text_rows:
            if row_id not in wanted_ids:
                continue
            message = clean_ffbe_dialogue(raw_source)
            if not message:
                skipped_blank.append(
                    {"cpk": cpk_name, "ffbe_id": row_id, "raw": raw_source}
                )
                continue
            record = {"ffbe_id": row_id}
            normalized_source = re.sub(
                r"(?i)<invalid_touchwait>", "", raw_source
            ).lstrip("\r\n \t\u3000")
            name_match = NAME_TAG.search(normalized_source)
            speaker_id = name_match.group(1) if name_match else ""
            if speaker_id and tellers.get(speaker_id):
                record["name"] = tellers[speaker_id]
            record["message"] = message
            output_rows.append(record)

        involved_ids = {row_id for row_id, _ in text_rows} & wanted_ids
        seen_ids = {row["ffbe_id"] for row in output_rows}
        if seen_ids | {row["ffbe_id"] for row in skipped_blank if row["cpk"] == cpk_name} != involved_ids:
            raise ValueError(f"{cpk_name}: row accounting mismatch")

        output_path = OUTPUT_DIR / f"{Path(cpk_name).stem}.json"
        output_path.write_text(
            json.dumps(output_rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written_rows += len(output_rows)
        generated_files.append(
            {
                "file": output_path.name,
                "cpk": cpk_name,
                "rows": len(output_rows),
                "skipped_blank_rows": sum(
                    row["cpk"] == cpk_name for row in skipped_blank
                ),
                "source_path": item["source_path"],
            }
        )

    expected_files = len(missing_cpks)
    if len(generated_files) != expected_files:
        raise ValueError(
            f"file count mismatch: generated={len(generated_files)} expected={expected_files}"
        )
    if written_rows != len(missing_rows) - len(skipped_blank):
        raise ValueError(
            f"row count mismatch: generated={written_rows} "
            f"expected={len(missing_rows) - len(skipped_blank)}"
        )

    manifest = {
        "source_manifest": str(MISSING_CPKS.relative_to(ROOT)),
        "generated_files": generated_files,
        "files": len(generated_files),
        "rows": written_rows,
        "skipped_blank_rows": skipped_blank,
    }
    (PROJECT_DIR / "gt_input-import-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output_dir": str(OUTPUT_DIR),
                "files": len(generated_files),
                "rows": written_rows,
                "skipped_blank_rows": len(skipped_blank),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    build()

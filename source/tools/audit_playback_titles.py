import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "upstream" / "source" / "exvius"))
sys.path.insert(0, str(ROOT / "upstream" / "source" / "server"))

from decode_client_data import decode  # noqa: E402


JP_DIR = (
    ROOT
    / "artifacts"
    / "jp-memorial-11.1.2-original"
    / "assetpacks"
    / "on_demand_asset"
    / "201"
    / "201"
    / "assets"
)
CURRENT_DIR = ROOT / "artifacts" / "title-table-current" / "story_ports"
PLATE_DIR = (
    ROOT
    / "artifacts"
    / "korean-packaged"
    / "no-check-build"
    / "assets"
    / "plate_pack"
)
OUTPUT_DIR = ROOT / "artifacts" / "title-localization-audit"

TABLES = (
    {
        "name": "F_PLAYBACK_CHAPTER_MST",
        "token": "Nm36woZx",
        "key": "gHLE4DM0",
        "row_id": "M9mwe2cu",
    },
    {
        "name": "F_PLAYBACK_MAP_MST",
        "token": "9Zdr5ap0",
        "key": "ZdM9VQb0",
        "row_id": "vG1hSm79",
    },
    {
        "name": "F_PLAYBACK_EVENT_MST",
        "token": "IL78hX09",
        "key": "qWr8ZE2D",
        "row_id": "VMkv7S9R",
    },
)
NAME_FIELD = "G4L0YIB2"
HANGUL = re.compile(r"[가-힣]")
JAPANESE = re.compile(r"[ぁ-んァ-ヶ]")


def records(path: Path, key: str) -> list[dict]:
    _, rows = decode(path.read_bytes(), key, localized=False)
    return rows


def grouped(rows: list[dict], id_field: str) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(str(row.get(id_field, "")), []).append(row)
    return result


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    audit_rows = []
    table_summary = {}
    all_source_names = set()

    for table in TABLES:
        token = table["token"]
        jp_rows = records(JP_DIR / f"{token}.dat", table["key"])
        current_rows = records(CURRENT_DIR / f"{token}.dat", table["key"])
        jp_by_id = grouped(jp_rows, table["row_id"])
        current_by_id = grouped(current_rows, table["row_id"])
        ids = sorted(set(jp_by_id) | set(current_by_id))

        for row_id in ids:
            jp_values = sorted(
                {str(row.get(NAME_FIELD, "")) for row in jp_by_id.get(row_id, [])}
            )
            current_values = sorted(
                {
                    str(row.get(NAME_FIELD, ""))
                    for row in current_by_id.get(row_id, [])
                }
            )
            jp = " | ".join(jp_values)
            current = " | ".join(current_values)
            if any(HANGUL.search(value) for value in current_values):
                status = "korean"
            elif not current.strip():
                status = "empty"
            elif any(JAPANESE.search(value) for value in jp_values):
                status = "needs_translation"
            else:
                status = "review_non_japanese"
            all_source_names.update(value for value in jp_values if value.strip())
            audit_rows.append(
                {
                    "table": table["name"],
                    "row_id": row_id,
                    "jp": jp,
                    "current": current,
                    "status": status,
                }
            )

        current_unique = {
            str(row.get(NAME_FIELD, ""))
            for row in current_rows
            if str(row.get(NAME_FIELD, "")).strip()
        }
        jp_unique = {
            str(row.get(NAME_FIELD, ""))
            for row in jp_rows
            if str(row.get(NAME_FIELD, "")).strip()
        }
        status_counts = Counter(
            row["status"] for row in audit_rows if row["table"] == table["name"]
        )
        table_summary[table["name"]] = {
            "token": token,
            "jp_rows": len(jp_rows),
            "current_rows": len(current_rows),
            "audit_ids": len(ids),
            "jp_unique_names": len(jp_unique),
            "jp_names_with_japanese": sum(
                bool(JAPANESE.search(name)) for name in jp_unique
            ),
            "current_unique_names": len(current_unique),
            "current_names_with_hangul": sum(
                bool(HANGUL.search(name)) for name in current_unique
            ),
            "status_counts": dict(sorted(status_counts.items())),
        }

    with (OUTPUT_DIR / "playback-title-audit.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("table", "row_id", "jp", "current", "status")
        )
        writer.writeheader()
        writer.writerows(audit_rows)

    plate_rows = []
    for plate in sorted(PLATE_DIR.glob("memory_plate_chapter_*.png")):
        match = re.match(r"memory_plate_chapter_(\d+)_", plate.name)
        plate_rows.append(
            {
                "filename": plate.name,
                "season": match.group(1) if match else "",
                "bytes": plate.stat().st_size,
                "status": "image_text_requires_visual_translation",
            }
        )
    with (OUTPUT_DIR / "chapter-plates.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("filename", "season", "bytes", "status"),
        )
        writer.writeheader()
        writer.writerows(plate_rows)

    summary = {
        "source": {
            "japanese": str(JP_DIR),
            "current": str(CURRENT_DIR),
            "chapter_plates": str(PLATE_DIR),
        },
        "tables": table_summary,
        "all_unique_source_names": len(all_source_names),
        "all_unique_names_with_japanese": sum(
            bool(JAPANESE.search(name)) for name in all_source_names
        ),
        "all_unique_non_japanese_names": sum(
            not JAPANESE.search(name) for name in all_source_names
        ),
        "chapter_plate_count": len(plate_rows),
        "chapter_plate_counts_by_season": dict(
            sorted(Counter(row["season"] for row in plate_rows).items())
        ),
        "unresolved_ui_labels": ["Battle", "Yes"],
        "notes": [
            "The current playback tables contain no Hangul.",
            "Chapter card text is baked into PNG images.",
            "The generic UI text table does not contain the Battle/Yes labels seen on the playback row.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Apply deterministic QA fixes to the newly translated scenes."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ROOT = PROJECT_DIR.parents[1]
BASE = ROOT / "artifacts" / "chapter1-ko"
INPUT_DIR = BASE / "gt_input"
OUTPUT_DIR = BASE / "gt_output"
CACHE_DIR = BASE / "transl_cache"
BACKUP_DIR = PROJECT_DIR / "qa-before"

TRAILING_BR = re.compile(r"(?:\s*<br\s*/?>){1,}\s*$", re.IGNORECASE)

# Preserve the elongated delivery of the Japanese line without leaving kana.
MANUAL_MESSAGES = {
    ("429406302.json", "210018"): "레인…… 거짓말이야!\n레이───인!",
    ("429406501.json", "210002"): "큭…… 으아아아아───!",
    (
        "429406602.json",
        "210001",
    ): (
        "좋아, 부유 도시의 낙하 속도가 줄어들었어.\n"
        "이거라면 해볼 만해.\n"
        "우오오오오오오오오오오오───!"
    ),
    ("554140113.json", "210050"): "레프티아───!",
    (
        "555020203.json",
        "210016",
    ): "용서 못 해!\n절대로 용서 못 한다───!",
    ("555020503.json", "210050"): "레이───인!",
    ("555040503.json", "210022"): "하────하하하하하하하하하하하!",
    (
        "554150111.json",
        "210040",
    ): "로카 님───!\n로카 님, 로카 님───!",
}


def backup(path: Path) -> None:
    target = BACKUP_DIR / path.relative_to(BASE)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(path, target)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def repair() -> dict[str, object]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, list[tuple[int, str]]] = {}
    for (file_name, row_id), message in MANUAL_MESSAGES.items():
        by_file.setdefault(file_name, []).append((int(row_id), message))

    changes: list[dict[str, object]] = []
    for input_path in sorted(INPUT_DIR.glob("*.json")):
        file_name = input_path.name
        output_path = OUTPUT_DIR / file_name
        cache_path = CACHE_DIR / file_name
        input_rows = json.loads(input_path.read_text(encoding="utf-8"))
        output_rows = json.loads(output_path.read_text(encoding="utf-8"))
        output_by_id = {str(row["ffbe_id"]): row for row in output_rows}
        manual = dict(by_file.get(file_name, []))
        file_changes: list[tuple[str, str, str]] = []

        for source_row in input_rows:
            row_id = str(source_row["ffbe_id"])
            target = output_by_id[row_id]
            before = str(target.get("message", ""))
            after = manual.get(int(row_id), before)
            after = TRAILING_BR.sub("", after).rstrip()
            if after != before:
                target["message"] = after
                file_changes.append((row_id, before, after))

        if not file_changes:
            continue

        backup(output_path)
        write_json(output_path, output_rows)

        if cache_path.exists():
            backup(cache_path)
            cache_rows = json.loads(cache_path.read_text(encoding="utf-8"))
            indexed = {int(row.get("index", 0)): row for row in cache_rows}
            for row_id, _, after in file_changes:
                input_index = next(
                    index
                    for index, row in enumerate(input_rows, 1)
                    if str(row["ffbe_id"]) == row_id
                )
                cache_row = indexed.get(input_index)
                if cache_row is not None:
                    cache_row["pre_dst"] = after
                    cache_row["post_dst_preview"] = after
            write_json(cache_path, cache_rows)

        for row_id, before, after in file_changes:
            changes.append(
                {
                    "file": file_name,
                    "ffbe_id": row_id,
                    "before": before,
                    "after": after,
                    "reason": (
                        "manual-kana-normalization"
                        if int(row_id) in manual
                        else "trailing-br"
                    ),
                }
            )

    report = {
        "files_changed": len({row["file"] for row in changes}),
        "rows_changed": len(changes),
        "changes": changes,
    }
    write_json(PROJECT_DIR / "qa-repair-report.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(repair(), ensure_ascii=False, indent=2))

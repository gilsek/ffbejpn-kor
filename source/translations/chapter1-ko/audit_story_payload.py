"""Audit every patched story CPK in story_patch_payload.tar.

Classifies the packaging defects that can make the game crash or display
compressed bytes as story text.  Duplicate emulator paths are collapsed by
content hash so each unique patched CPK is examined once.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import tarfile
from collections import Counter
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
ROOT = PROJECT_DIR.parents[1]
PAYLOAD = PROJECT_DIR / "story_patch_payload.tar"
OUTPUT_DIR = PROJECT_DIR / "story-audit"
VENDOR_DIR = ROOT / "analysis" / "vendor"

TAG = re.compile(r"<[^>]+>")


def text_field_sizes(filename: str, data: bytes) -> list[dict[str, object]]:
    text = data.decode("utf-8-sig")
    sizes: list[dict[str, object]] = []

    if filename.endswith("_event_text.txt"):
        for line_number, line in enumerate(text.splitlines(), 1):
            row_id, separator, body = line.partition(",")
            if separator:
                sizes.append(
                    {
                        "kind": "text",
                        "line": line_number,
                        "id": row_id,
                        "column": None,
                        "bytes": len(body.encode("utf-8")),
                        "plain_bytes": len(TAG.sub("", body).encode("utf-8")),
                    }
                )
    elif filename.endswith("_event_text_sg.txt"):
        for line_number, line in enumerate(text.splitlines(), 1):
            fields = line.split("^")
            for column, body in enumerate(fields[1:], 1):
                sizes.append(
                    {
                        "kind": "sg",
                        "line": line_number,
                        "id": fields[0],
                        "column": column,
                        "bytes": len(body.encode("utf-8")),
                        "plain_bytes": len(TAG.sub("", body).encode("utf-8")),
                    }
                )
    return sizes


def audit() -> None:
    sys.path.insert(0, str(VENDOR_DIR))
    from cricodecs import cpk  # type: ignore[import-not-found]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seen_hashes: set[str] = set()
    rows: list[dict[str, object]] = []
    longest: list[dict[str, object]] = []
    categories: Counter[str] = Counter()

    with tarfile.open(PAYLOAD, "r") as archive:
        members = [
            member
            for member in archive
            if member.isfile() and member.name.lower().endswith(".cpk")
        ]
        for index, member in enumerate(members, 1):
            stream = archive.extractfile(member)
            if stream is None:
                continue
            blob = stream.read()
            digest = hashlib.sha256(blob).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)

            cpk_name = Path(member.name).name
            row: dict[str, object] = {
                "cpk": cpk_name,
                "tar_path": member.name,
                "bytes": len(blob),
                "sha256": digest,
                "status": "ok",
                "entry_errors": [],
                "raw_compressed_text": [],
                "max_text_bytes": 0,
                "max_sg_bytes": 0,
                "max_plain_bytes": 0,
                "text_rows": 0,
            }

            try:
                package = cpk.Cpk.load_bytes(blob)
            except Exception as error:
                row["status"] = "cpk_load_fail"
                row["error"] = f"{type(error).__name__}: {error}"
                categories["cpk_load_fail"] += 1
                rows.append(row)
                continue

            for item in package.file_infos():
                if not item.filename.endswith(".txt"):
                    continue
                try:
                    data = package.file_bytes(item.toc_index)
                except Exception as error:
                    row["entry_errors"].append(
                        f"{item.filename}: {type(error).__name__}: {error}"
                    )
                    continue

                if data.startswith(b"CRILAYLA"):
                    row["raw_compressed_text"].append(item.filename)
                    continue

                try:
                    sizes = text_field_sizes(item.filename, data)
                except UnicodeDecodeError as error:
                    row["entry_errors"].append(f"{item.filename}: UTF-8: {error}")
                    continue

                row["text_rows"] = int(row["text_rows"]) + len(sizes)
                for size in sizes:
                    field = {
                        "cpk": cpk_name,
                        "filename": item.filename,
                        **size,
                    }
                    if size["kind"] == "text":
                        row["max_text_bytes"] = max(
                            int(row["max_text_bytes"]), int(size["bytes"])
                        )
                    else:
                        row["max_sg_bytes"] = max(
                            int(row["max_sg_bytes"]), int(size["bytes"])
                        )
                    row["max_plain_bytes"] = max(
                        int(row["max_plain_bytes"]), int(size["plain_bytes"])
                    )
                    if (
                        int(size["bytes"]) >= 120
                        or int(size["plain_bytes"]) >= 120
                    ):
                        longest.append(field)

            if row["raw_compressed_text"]:
                row["status"] = "raw_compressed_text"
                categories["raw_compressed_text"] += 1
            elif row["entry_errors"]:
                row["status"] = "entry_error"
                categories["entry_error"] += 1
            else:
                categories["ok"] += 1
            rows.append(row)

            if index % 250 == 0:
                print(
                    f"scanned tar members={index}/{len(members)} "
                    f"unique={len(rows)} failures="
                    f"{categories['cpk_load_fail'] + categories['raw_compressed_text'] + categories['entry_error']}",
                    file=sys.stderr,
                    flush=True,
                )

    rows.sort(key=lambda item: (item["status"] == "ok", str(item["cpk"])))
    longest.sort(
        key=lambda item: (int(item["bytes"]), int(item["plain_bytes"])),
        reverse=True,
    )

    report = {
        "tar_members": len(members),
        "unique_cpks": len(rows),
        "categories": dict(categories),
        "max_text_bytes": max((int(row["max_text_bytes"]) for row in rows), default=0),
        "max_sg_bytes": max((int(row["max_sg_bytes"]) for row in rows), default=0),
        "over_255_text": sum(int(row["max_text_bytes"]) > 255 for row in rows),
        "over_255_sg": sum(int(row["max_sg_bytes"]) > 255 for row in rows),
        "long_fields_over_119": len(longest),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "cpk-audit.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "long-fields.json").write_text(
        json.dumps(longest[:5000], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (OUTPUT_DIR / "cpk-audit.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "cpk",
                "status",
                "bytes",
                "text_rows",
                "max_text_bytes",
                "max_sg_bytes",
                "max_plain_bytes",
                "tar_path",
                "sha256",
                "error",
                "entry_errors",
                "raw_compressed_text",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    audit()

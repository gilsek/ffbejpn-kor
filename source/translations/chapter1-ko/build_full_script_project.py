"""Build a GalTransl input inventory for every script-bearing event CPK.

The existing gt_input files are treated as completed seed files and are never
rewritten. New scene inputs are written atomically into gt_input.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tarfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJECT_DIR.parents[1]
ANALYSIS_DIR = ROOT_DIR / "analysis"
sys.path.insert(0, str(ANALYSIS_DIR))
sys.path.insert(0, str(ANALYSIS_DIR / "vendor"))

from audit_complete_release import load_archive  # noqa: E402
from release_reader import Release  # noqa: E402


AUDIT_PATH = ROOT_DIR / "artifacts" / "story-preservation-audit.json"
RELEASE_DIR = ROOT_DIR / "downloads" / "release-2026.11.04.9"
JP_TAR_PATH = ROOT_DIR / "downloads" / "ffbe-jp-ldplayer-assetpacks-11.1.2-verified.tar"
INPUT_DIR = PROJECT_DIR / "gt_input"
SCRIPT_META_PATH = PROJECT_DIR / "script_meta.json"
SCRIPT_META_DB_PATH = PROJECT_DIR / "script_meta.sqlite"
SCRIPT_MANIFEST_PATH = PROJECT_DIR / "script_manifest.json"
RUNTIME_SCOPE_PATH = PROJECT_DIR / "runtime" / "scope_summary.json"

KANA_RE = re.compile(r"[\u3040-\u30ff]")
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
NAME_TAG_RE = re.compile(r"^(<name(?:_npc)?=([^>]+)>)(?:<br>)?", re.IGNORECASE)
SOURCE_LINE_RE = re.compile(r"^(\d+)[\^,](.*)$")
TAG_RE = re.compile(r"<[^>]*>")


def clean_ffbe_dialogue(raw: str) -> str:
    text = NAME_TAG_RE.sub("", raw or "")
    text = re.sub(r"(?i)<page>(?:<br>)?", "[PAGE]\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<wait=\d+>", "", text)
    text = re.sub(r"(?i)<speed=\d+>", "", text)
    text = re.sub(r"(?i)<keywait>", "", text)
    return text.replace("\\n", "\n").strip()


def decoded_member(archive: Any, suffix: str) -> str:
    for index, member in enumerate(archive.file_infos()):
        if member.full_path.endswith(suffix):
            try:
                return archive.file_bytes(index).decode("utf-8-sig")
            except UnicodeDecodeError:
                return archive.file_bytes(index).decode("cp932")
    return ""


def parse_jp_rows(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        match = SOURCE_LINE_RE.match(line)
        if match:
            rows.append(
                {
                    "ffbe_id": match.group(1).lstrip("\ufeff"),
                    "raw_jp": match.group(2),
                }
            )
    return rows


def parse_sg_rows(text: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    dialogue: dict[str, dict[str, str]] = {}
    speakers: dict[str, str] = {}
    for line in text.splitlines():
        columns = line.split("^")
        if not columns:
            continue
        ffbe_id = columns[0].lstrip("\ufeff")
        dialogue[ffbe_id] = {
            "english": columns[1] if len(columns) > 1 else "",
            "korean": columns[3] if len(columns) > 3 else "",
        }
        if len(columns) > 3:
            speakers[ffbe_id] = columns[3]
    return dialogue, speakers


def parse_teller_rows(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        columns = line.split(",", 1)
        if len(columns) == 2:
            result[columns[0].strip().lstrip("\ufeff")] = columns[1]
    return result


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def load_targets() -> list[dict[str, Any]]:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    targets = []
    for package in audit.get("packages", []):
        dialogue = package.get("dialogue") or {}
        rows = int(dialogue.get("rows") or 0)
        path = str(package.get("path") or "")
        if rows <= 0 or not path.endswith(".cpk"):
            continue
        scene_id = re.sub(r"^Ver\d+_", "", Path(path).stem)
        targets.append(
            {
                "scene_id": scene_id,
                "path": path,
                "block": package.get("block", ""),
                "chapter_ids": package.get("direct_chapter_ids", []),
                "expected_rows": rows,
            }
        )
    targets = sorted(targets, key=lambda item: item["scene_id"])
    counts = Counter(item["scene_id"] for item in targets)
    for target in targets:
        if counts[target["scene_id"]] > 1:
            block = re.sub(r"[^A-Za-z0-9]+", "_", target["block"]).strip("_")
            target["input_name"] = f"{target['scene_id']}__{block}.json"
        else:
            target["input_name"] = f"{target['scene_id']}.json"
    return targets


def scan_japanese_tar(
    targets: list[dict[str, Any]],
    limit: int | None,
) -> tuple[dict[str, dict[str, Any]], int]:
    wanted = {item["scene_id"]: item for item in targets}
    found: dict[str, dict[str, Any]] = {}
    started = time.monotonic()
    last_report = started
    scanned = 0
    with tarfile.open(JP_TAR_PATH, "r|") as archive:
        for member in archive:
            scanned += 1
            if not member.isfile() or not member.name.lower().endswith(".cpk"):
                continue
            scene_id = re.sub(r"^Ver\d+_", "", Path(member.name).stem)
            if scene_id not in wanted or scene_id in found:
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            payload = source.read()
            try:
                cpk_archive, _masked = load_archive(payload)
                dialogue_text = decoded_member(cpk_archive, "_event_text.txt")
                teller_text = decoded_member(cpk_archive, "_event_teller.txt")
                if dialogue_text:
                    found[scene_id] = {
                        "rows": parse_jp_rows(dialogue_text),
                        "tellers": parse_teller_rows(teller_text),
                    }
            except Exception:
                pass
            now = time.monotonic()
            if now - last_report >= 15:
                print(
                    json.dumps(
                        {
                            "event": "jp_scan",
                            "members_scanned": scanned,
                            "scripts_found": len(found),
                            "wanted": len(wanted),
                            "elapsed_seconds": round(now - started),
                        }
                    ),
                    flush=True,
                )
                last_report = now
            if limit is not None and len(found) >= limit:
                break
    print(
        json.dumps(
            {
                "event": "jp_scan_complete",
                "members_scanned": scanned,
                "scripts_found": len(found),
                "elapsed_seconds": round(time.monotonic() - started),
            }
        ),
        flush=True,
    )
    return found, scanned


def build(args: argparse.Namespace) -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = {path.stem for path in INPUT_DIR.glob("*.json")}
    all_targets = load_targets()
    pending_targets = [
        item for item in all_targets if Path(item["input_name"]).stem not in existing
    ]
    if args.limit:
        pending_targets = pending_targets[: args.limit]

    print(
        json.dumps(
            {
                "event": "scope",
                "all_script_cpks": len(all_targets),
                "existing_inputs": len(existing),
                "pending_targets": len(pending_targets),
            }
        ),
        flush=True,
    )
    if pending_targets:
        jp_sources, tar_members = scan_japanese_tar(pending_targets, args.limit)
    else:
        jp_sources, tar_members = {}, 0
    release = Release(RELEASE_DIR)
    new_meta: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    name_pairs: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    written = 0
    missing_jp = 0
    missing_global = 0
    started = time.monotonic()
    last_report = started

    try:
        for number, target in enumerate(pending_targets, 1):
            scene_id = target["scene_id"]
            global_path = target["path"]
            jp_source = jp_sources.get(scene_id, {})
            jp_rows = jp_source.get("rows", [])
            jp_tellers = jp_source.get("tellers", {})
            if not jp_rows:
                missing_jp += 1

            global_dialogue: dict[str, dict[str, str]] = {}
            global_tellers: dict[str, str] = {}
            base_jp_text = ""
            if global_path in release.files:
                try:
                    global_archive, _masked = load_archive(release.read(global_path))
                    sg_text = decoded_member(global_archive, "_event_text_sg.txt")
                    teller_sg = decoded_member(global_archive, "_event_teller_sg.txt")
                    base_jp_text = decoded_member(global_archive, "_event_text.txt")
                    global_dialogue, global_tellers = parse_sg_rows(sg_text)
                    for speaker_id, speaker_ko in global_tellers.items():
                        speaker_jp = jp_tellers.get(speaker_id)
                        if (
                            speaker_jp
                            and speaker_ko
                            and HANGUL_RE.search(speaker_ko)
                            and not KANA_RE.search(speaker_ko)
                        ):
                            name_pairs[speaker_jp] = speaker_ko
                except Exception as exc:
                    errors.append(
                        {
                            "scene_id": scene_id,
                            "path": global_path,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    missing_global += 1
            else:
                missing_global += 1

            if not jp_rows:
                fallback_rows = []
                fallback_rows.extend(parse_jp_rows(base_jp_text))
                for ffbe_id, values in global_dialogue.items():
                    korean = values.get("korean", "")
                    english = values.get("english", "")
                    if KANA_RE.search(korean):
                        fallback_rows.append({"ffbe_id": ffbe_id, "raw_jp": korean})
                    elif KANA_RE.search(english):
                        fallback_rows.append({"ffbe_id": ffbe_id, "raw_jp": english})
                jp_rows = fallback_rows

            if not jp_rows:
                errors.append(
                    {
                        "scene_id": scene_id,
                        "path": global_path,
                        "error": "No Japanese source rows found",
                    }
                )
                continue

            items = []
            for row in jp_rows:
                ffbe_id = row["ffbe_id"]
                raw_jp = row["raw_jp"]
                name_match = NAME_TAG_RE.match(raw_jp)
                speaker_id = name_match.group(2) if name_match else ""
                speaker_jp = jp_tellers.get(speaker_id, "")
                speaker_ko = name_pairs.get(speaker_jp, "")
                reference = global_dialogue.get(ffbe_id, {})
                english = clean_ffbe_dialogue(reference.get("english", ""))
                official_ko = clean_ffbe_dialogue(reference.get("korean", ""))
                has_official_ko = bool(
                    official_ko
                    and HANGUL_RE.search(official_ko)
                    and not KANA_RE.search(official_ko)
                    and official_ko != english
                )
                clean_jp = clean_ffbe_dialogue(raw_jp)
                item: dict[str, Any] = {"ffbe_id": ffbe_id}
                if speaker_jp:
                    item["name"] = speaker_jp
                item["message"] = clean_jp
                items.append(item)
                new_meta.append(
                    {
                        "input_file": target["input_name"],
                        "cpk_name": f"{scene_id}.cpk",
                        "scene_id": scene_id,
                        "global_path": global_path,
                        "ffbe_id": ffbe_id,
                        "orig_index": len(items),
                        "bin_offset": None,
                        "speaker_tag": name_match.group(1) if name_match else "",
                        "speaker_jp": speaker_jp,
                        "speaker_ko": speaker_ko,
                        "raw_jp": raw_jp,
                        "clean_jp": clean_jp,
                        "official_ko_raw": reference.get("korean", ""),
                        "official_ko_clean": official_ko if has_official_ko else "",
                        "english_clean": english,
                        "has_official_ko": has_official_ko,
                        "chapter_ids": target["chapter_ids"],
                        "block": target["block"],
                    }
                )

            if not items:
                continue
            atomic_write(
                INPUT_DIR / target["input_name"],
                json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            )
            manifest.append(
                {
                    **target,
                    "input_file": target["input_name"],
                    "actual_rows": len(items),
                    "source": "jp_tar" if jp_source else "global_fallback",
                }
            )
            written += 1

            now = time.monotonic()
            if now - last_report >= 15 or number == len(pending_targets):
                print(
                    json.dumps(
                        {
                            "event": "build",
                            "processed": number,
                            "total": len(pending_targets),
                            "written": written,
                            "rows": len(new_meta),
                            "missing_jp": missing_jp,
                            "missing_global": missing_global,
                            "errors": len(errors),
                            "elapsed_seconds": round(now - started),
                        }
                    ),
                    flush=True,
                )
                last_report = now
    finally:
        release.close()

    existing_meta: list[dict[str, Any]] = []
    meta_source_path = (
        SCRIPT_META_PATH
        if SCRIPT_META_PATH.exists()
        else PROJECT_DIR / "chapter1_meta.json"
    )
    if meta_source_path.exists():
        try:
            loaded = json.loads(meta_source_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                rebuilt_scenes = {item["scene_id"] for item in pending_targets}
                existing_meta = [
                    row
                    for row in loaded
                    if isinstance(row, dict)
                    and str(row.get("scene_id") or "") not in rebuilt_scenes
                ]
        except (OSError, json.JSONDecodeError):
            pass
    combined_meta = existing_meta + new_meta
    atomic_write(
        SCRIPT_META_PATH,
        json.dumps(combined_meta, ensure_ascii=False, indent=2) + "\n",
    )
    db_temp_path = SCRIPT_META_DB_PATH.with_suffix(".sqlite.tmp")
    db_temp_path.unlink(missing_ok=True)
    connection = sqlite3.connect(db_temp_path)
    try:
        connection.execute(
            """
            CREATE TABLE script_meta (
                cpk_name TEXT NOT NULL,
                scene_id TEXT NOT NULL,
                ffbe_id TEXT NOT NULL,
                speaker_jp TEXT,
                speaker_ko TEXT,
                clean_jp TEXT,
                english_clean TEXT,
                global_path TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO script_meta (
                cpk_name, scene_id, ffbe_id, speaker_jp, speaker_ko,
                clean_jp, english_clean, global_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    row.get("cpk_name", ""),
                    row.get("scene_id", ""),
                    str(row.get("ffbe_id", "")),
                    row.get("speaker_jp", ""),
                    row.get("speaker_ko", ""),
                    row.get("clean_jp", ""),
                    row.get("english_clean", ""),
                    row.get("global_path", ""),
                )
                for row in combined_meta
            ),
        )
        connection.execute(
            "CREATE INDEX idx_script_meta_scene_id_id ON script_meta(scene_id, ffbe_id)"
        )
        connection.commit()
    finally:
        connection.close()
    db_temp_path.replace(SCRIPT_META_DB_PATH)
    scope_targets = []
    for target in all_targets:
        input_path = INPUT_DIR / target["input_name"]
        rows = 0
        japanese_rows = 0
        if input_path.exists():
            try:
                items = json.loads(input_path.read_text(encoding="utf-8"))
                if isinstance(items, list):
                    rows = len(items)
                    japanese_rows = sum(
                        bool(
                            KANA_RE.search(str(item.get("message") or ""))
                            or re.search(
                                r"[\u3400-\u4dbf\u4e00-\u9fff]",
                                str(item.get("message") or ""),
                            )
                        )
                        for item in items
                        if isinstance(item, dict)
                    )
            except (OSError, json.JSONDecodeError):
                pass
        scope_targets.append(
            {
                **target,
                "input_file": target["input_name"],
                "input_exists": input_path.exists(),
                "actual_rows": rows,
                "japanese_rows": japanese_rows,
                "output_exists": (PROJECT_DIR / "gt_output" / target["input_name"]).exists(),
            }
        )
    atomic_write(
        SCRIPT_MANIFEST_PATH,
        json.dumps(
            {
                "scope": "all_script_bearing_event_cpks",
                "all_script_cpks": len(all_targets),
                "existing_inputs": len(existing),
                "new_inputs_written": written,
                "total_rows_in_scope": sum(item["expected_rows"] for item in all_targets),
                "new_rows_written": len(new_meta),
                "jp_tar_members_scanned": tar_members,
                "missing_japanese_source": missing_jp,
                "missing_global_source": missing_global,
                "errors": errors,
                "targets": scope_targets,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    atomic_write(
        RUNTIME_SCOPE_PATH,
        json.dumps(
            {
                "scope": "all_script_bearing_event_cpks",
                "target_cpks": len(all_targets),
                "target_rows": sum(item["expected_rows"] for item in all_targets),
                "input_files": len(list(INPUT_DIR.glob("*.json"))),
                "new_files_written": written,
                "errors": len(errors),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    print(
        json.dumps(
            {
                "event": "complete",
                "target_cpks": len(all_targets),
                "new_inputs_written": written,
                "new_rows_written": len(new_meta),
                "input_files": len(list(INPUT_DIR.glob("*.json"))),
                "errors": len(errors),
            }
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Only build the first N missing scenes")
    build(parser.parse_args())


if __name__ == "__main__":
    main()

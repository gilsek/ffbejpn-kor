import collections
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"


def input_stem(path):
    return path.stem.split("__", 1)[0].lower()


inputs = {
    input_stem(path)
    for path in (PROJECT / "gt_input").glob("55413*.json")
}

payload_sizes = collections.defaultdict(set)
with tarfile.open(PROJECT / "story_patch_payload.tar") as archive:
    for member in archive:
        if member.isfile() and member.name.lower().endswith(".cpk"):
            payload_sizes[Path(member.name).stem.lower()].add(member.size)

command = (
    "find /storage/emulated/0/Android/data/com.exvius.memorial.korean/"
    "files/assetpacks -type f -name '55413*.cpk' -printf '%p\\t%s\\n'"
)
output = subprocess.run(
    ["adb", "-s", "emulator-5558", "shell", command],
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
).stdout
current = {}
for line in output.splitlines():
    path, separator, size = line.partition("\t")
    if separator and size.isdigit():
        current[Path(path).name.lower()] = {
            "path": path,
            "size": int(size),
        }

manifest = {
    row["cpk"]: row
    for row in json.loads(
        (ROOT / "season4-gap" / "season4_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    if row["cpk"].startswith("55413")
}

rows = []
for cpk in sorted(set(manifest) | {name + ".cpk" for name in inputs}):
    stem = Path(cpk).stem
    item = manifest.get(cpk, {})
    live = current.get(cpk)
    expected = payload_sizes.get(stem, set())
    rows.append(
        {
            "cpk": cpk,
            "in_input": stem in inputs,
            "text_rows": item.get("text_rows"),
            "jp_file_size": item.get("file_size"),
            "payload_sizes": sorted(expected),
            "current_size": live["size"] if live else None,
            "install_size_matches_payload": bool(
                live and live["size"] in expected
            ),
            "current_path": live["path"] if live else None,
        }
    )

print(json.dumps(rows, ensure_ascii=False, indent=2))

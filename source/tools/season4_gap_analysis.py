import collections
import json
import re
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"
HANGUL = re.compile(r"[\uac00-\ud2a3]")


def input_stem(path):
    return path.stem.split("__", 1)[0].lower()


payload_sizes = collections.defaultdict(set)
with tarfile.open(PROJECT / "story_patch_payload.tar") as archive:
    for member in archive:
        if member.isfile() and member.name.lower().endswith(".cpk"):
            payload_sizes[Path(member.name).stem.lower()].add(member.size)

group_stats = collections.defaultdict(collections.Counter)
input_names = set()
for input_path in sorted((PROJECT / "gt_input").glob("554*.json")):
    name = input_stem(input_path)
    group = name[:5]
    input_names.add(name)
    inputs = json.loads(input_path.read_text(encoding="utf-8-sig"))
    outputs = json.loads(
        (PROJECT / "gt_output" / input_path.name).read_text(encoding="utf-8-sig")
    )
    group_stats[group]["cpks"] += 1
    group_stats[group]["rows"] += len(inputs)
    group_stats[group]["output_rows"] += len(outputs)
    group_stats[group]["payload_cpks"] += bool(payload_sizes.get(name))
    group_stats[group]["korean_rows"] += sum(
        bool(HANGUL.search(str(row.get("message", "")))) for row in outputs
    )

command = (
    "find /storage/emulated/0/Android/data/com.exvius.memorial.korean/"
    "files/assetpacks -type f -name '554*.cpk' -printf '%f\\t%s\\n'"
)
output = subprocess.run(
    ["adb", "-s", "emulator-5558", "shell", command],
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
).stdout
current_sizes = {}
for line in output.splitlines():
    name, separator, size = line.partition("\t")
    if separator and size.isdigit():
        current_sizes[name.lower()] = int(size)

missing_payload = []
installed_mismatch = []
installed_match = []
for name in sorted(input_names):
    cpk = name + ".cpk"
    expected = payload_sizes.get(name, set())
    current = current_sizes.get(cpk)
    if not expected:
        missing_payload.append(cpk)
    elif current is None:
        installed_mismatch.append({"cpk": cpk, "reason": "not-installed"})
    elif current not in expected:
        installed_mismatch.append(
            {
                "cpk": cpk,
                "reason": "size-mismatch",
                "current_size": current,
                "payload_sizes": sorted(expected),
            }
        )
    else:
        installed_match.append(cpk)

result = {
    "groups": {
        group: dict(stats)
        for group, stats in sorted(group_stats.items())
    },
    "totals": {
        "input_cpks": len(input_names),
        "input_rows": sum(stats["rows"] for stats in group_stats.values()),
        "korean_output_rows": sum(
            stats["korean_rows"] for stats in group_stats.values()
        ),
        "payload_cpks": sum(
            bool(payload_sizes.get(name)) for name in input_names
        ),
        "missing_from_payload": len(missing_payload),
        "installed_size_match": len(installed_match),
        "installed_mismatch": len(installed_mismatch),
    },
    "missing_payload": missing_payload,
    "installed_mismatch": installed_mismatch,
}
print(json.dumps(result, ensure_ascii=False, indent=2))

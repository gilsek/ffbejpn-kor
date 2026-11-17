import collections
import json
import re
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"
HANGUL = re.compile(r"[\uac00-\ud7a3]")
LATIN = re.compile(r"[A-Za-z]")


def stem(path):
    return path.stem.split("__", 1)[0].lower()


with tarfile.open(PROJECT / "story_patch_payload.tar") as archive:
    payload_names = {
        Path(member.name).stem.lower()
        for member in archive
        if member.isfile() and member.name.lower().endswith(".cpk")
    }

stats = collections.defaultdict(collections.Counter)
for input_path in sorted((PROJECT / "gt_input").glob("*.json")):
    name = stem(input_path)
    prefix = name[:3]
    inputs = json.loads(input_path.read_text(encoding="utf-8-sig"))
    outputs = json.loads(
        (PROJECT / "gt_output" / input_path.name).read_text(encoding="utf-8-sig")
    )
    stats[prefix]["input_files"] += 1
    stats[prefix]["input_rows"] += len(inputs)
    stats[prefix]["output_rows"] += len(outputs)
    stats[prefix]["payload_files"] += name in payload_names
    for row in outputs:
        message = str(row.get("message", ""))
        if HANGUL.search(message):
            stats[prefix]["korean_rows"] += 1
        elif LATIN.search(message):
            stats[prefix]["english_rows"] += 1
        else:
            stats[prefix]["neutral_rows"] += 1

result = {
    prefix: dict(values)
    for prefix, values in sorted(stats.items())
    if values["input_rows"] > 0
}
print(json.dumps(result, ensure_ascii=False, indent=2))

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"
TAG = re.compile(r"<[^>]+>")
TARGET = "but right before it vanished"


def normalize(value):
    text = TAG.sub("", str(value or ""))
    return re.sub(r"\s+", " ", text.replace("…", "...")).strip().lower()


matches = []
for folder in ("gt_input", "gt_output"):
    for path in sorted((PROJECT / folder).glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8-sig")):
            message = row.get("message", "")
            if TARGET in normalize(message):
                matches.append(
                    {
                        "source": folder,
                        "file": path.name,
                        "ffbe_id": row.get("ffbe_id"),
                        "message": message,
                    }
                )

for row in json.loads((PROJECT / "script_meta.json").read_text(encoding="utf-8")):
    values = {
        "clean_jp": row.get("clean_jp"),
        "official_ko_clean": row.get("official_ko_clean"),
        "english_clean": row.get("english_clean"),
    }
    if any(TARGET in normalize(value) for value in values.values()):
        matches.append(
            {
                "source": "script_meta",
                "file": row.get("cpk_name"),
                "ffbe_id": row.get("ffbe_id"),
                **values,
            }
        )

print(json.dumps(matches, ensure_ascii=False, indent=2))

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "chapter1-ko"
TAG = re.compile(r"<[^>]+>")


def formatted(message):
    return (
        str(message)
        .replace("\r", "")
        .replace("[PAGE]\n", "<page><br>")
        .replace("[PAGE]", "<page><br>")
        .replace("\n", "<br>")
    )


rows = []
for output_path in sorted((PROJECT / "gt_output").glob("55413*.json")):
    for row in json.loads(output_path.read_text(encoding="utf-8-sig")):
        message = formatted(row.get("message", ""))
        name = str(row.get("name", ""))
        rows.append(
            {
                "file": output_path.name,
                "ffbe_id": str(row.get("ffbe_id")),
                "name": name,
                "characters": len(message),
                "utf8_bytes": len(message.encode("utf-8")),
                "plain_characters": len(TAG.sub("", message)),
                "message": message,
            }
        )

rows.sort(key=lambda row: row["utf8_bytes"], reverse=True)
print(
    json.dumps(
        {
            "files": len({row["file"] for row in rows}),
            "rows": len(rows),
            "over_200_bytes": sum(row["utf8_bytes"] > 200 for row in rows),
            "over_255_bytes": sum(row["utf8_bytes"] > 255 for row in rows),
            "exactly_256_bytes": sum(row["utf8_bytes"] == 256 for row in rows),
            "top": rows[:100],
        },
        ensure_ascii=False,
        indent=2,
    )
)

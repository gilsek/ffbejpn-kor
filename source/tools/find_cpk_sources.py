import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGETS = {
    "111020112.cpk",
    "111020116.cpk",
    "111020220.cpk",
    "112020111.cpk",
    "112020112.cpk",
    "112020113.cpk",
}
SEARCH_ROOTS = [ROOT.parent / "downloads", ROOT / "korean-packaged"]


def inspect_bytes(name, payload):
    return {
        "target": name,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "magic": payload[:8].decode("ascii", errors="replace"),
        "valid_cpk": payload[:4] == b"CPK ",
    }


results = []
for search_root in SEARCH_ROOTS:
    if not search_root.exists():
        continue
    for archive_path in search_root.rglob("*"):
        if not archive_path.is_file() or archive_path.suffix.lower() not in {
            ".zip",
            ".tar",
            ".apk",
        }:
            continue
        try:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path) as archive:
                    for member in archive.infolist():
                        name = Path(member.filename).name
                        if name in TARGETS:
                            results.append(
                                {
                                    "archive": str(archive_path),
                                    "member": member.filename,
                                    **inspect_bytes(name, archive.read(member)),
                                }
                            )
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path, "r:*") as archive:
                    for member in archive:
                        name = Path(member.name).name
                        if member.isfile() and name in TARGETS:
                            handle = archive.extractfile(member)
                            payload = handle.read() if handle else b""
                            results.append(
                                {
                                    "archive": str(archive_path),
                                    "member": member.name,
                                    **inspect_bytes(name, payload),
                                }
                            )
        except Exception as error:
            results.append(
                {
                    "archive": str(archive_path),
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )

print(json.dumps(results, ensure_ascii=False, indent=2))

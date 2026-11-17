import collections
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
JP_ASSETPACKS = ROOT / "jp-memorial-11.1.2-original" / "assetpacks"
EN_SERIAL = "emulator-5558"
EN_EXTERNAL = "/storage/emulated/0/Android/data/com.square_enix.ffbejpn/files/assetpacks"
EN_INTERNAL = "/data/data/com.square_enix.ffbejpn/files"


def adb_inventory(path):
    command = (
        f"find {path} -type f -printf '%p\\t%s\\n'"
    )
    output = subprocess.run(
        ["adb", "-s", EN_SERIAL, "shell", command],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    result = {}
    for line in output.splitlines():
        absolute, separator, size = line.partition("\t")
        if separator and size.isdigit():
            prefix = path.rstrip("/") + "/"
            relative = (
                absolute[len(prefix) :]
                if absolute.startswith(prefix)
                else absolute
            )
            result[relative] = int(size)
    return result


def local_inventory(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_size
        for path in root.rglob("*")
        if path.is_file()
    }


def cpk_map(items):
    mapped = {}
    for relative, size in items.items():
        path = Path(relative)
        if path.suffix.lower() == ".cpk":
            mapped.setdefault(path.name.lower(), []).append((relative, size))
    return mapped


def prefix_counts(names):
    return collections.Counter(name[:3] for name in names)


jp_external = local_inventory(JP_ASSETPACKS)
en_external = adb_inventory(EN_EXTERNAL)
en_internal = adb_inventory(EN_INTERNAL)

jp_paths = set(jp_external)
en_paths = set(en_external)
common_paths = jp_paths & en_paths
different_sizes = [
    relative
    for relative in common_paths
    if jp_external[relative] != en_external[relative]
]

jp_cpks = cpk_map(jp_external)
en_external_cpks = cpk_map(en_external)
en_internal_cpks = cpk_map(en_internal)

jp_cpk_names = set(jp_cpks)
en_external_cpk_names = set(en_external_cpks)
en_internal_cpk_names = set(en_internal_cpks)
en_extra_internal_names = en_internal_cpk_names - jp_cpk_names

internal_suffix_counts = collections.Counter(
    Path(relative).suffix.lower() for relative in en_internal
)

sample_size_differences = sorted(
    (
        {
            "path": relative,
            "jp_size": jp_external[relative],
            "en_size": en_external[relative],
        }
        for relative in different_sizes
    ),
    key=lambda item: abs(item["en_size"] - item["jp_size"]),
    reverse=True,
)[:30]

cpk_size_differences = []
for name in sorted(jp_cpk_names & en_external_cpk_names):
    jp_size = max(size for _, size in jp_cpks[name])
    en_size = max(size for _, size in en_external_cpks[name])
    if jp_size != en_size:
        cpk_size_differences.append(
            {"cpk": name, "jp_size": jp_size, "en_size": en_size}
        )
cpk_size_differences.sort(
    key=lambda item: abs(item["en_size"] - item["jp_size"]), reverse=True
)

result = {
    "jp_external_assetpacks": {
        "files": len(jp_external),
        "bytes": sum(jp_external.values()),
        "cpk_files": sum(
            Path(path).suffix.lower() == ".cpk" for path in jp_external
        ),
        "unique_cpk_names": len(jp_cpks),
    },
    "en_external_assetpacks": {
        "files": len(en_external),
        "bytes": sum(en_external.values()),
        "cpk_files": sum(
            Path(path).suffix.lower() == ".cpk" for path in en_external
        ),
        "unique_cpk_names": len(en_external_cpks),
    },
    "external_comparison": {
        "sample_jp_paths": sorted(jp_paths)[:10],
        "sample_en_paths": sorted(en_paths)[:10],
        "only_jp_paths": len(jp_paths - en_paths),
        "only_en_paths": len(en_paths - jp_paths),
        "same_path_different_size": len(different_sizes),
        "only_jp_cpk_names": sorted(jp_cpk_names - en_external_cpk_names),
        "only_en_cpk_names": sorted(en_external_cpk_names - jp_cpk_names),
        "same_cpk_names": len(jp_cpk_names & en_external_cpk_names),
        "cpk_size_differences": len(cpk_size_differences),
        "cpk_size_difference_samples": cpk_size_differences[:30],
        "largest_size_differences": sample_size_differences,
    },
    "en_internal_files": {
        "files": len(en_internal),
        "bytes": sum(en_internal.values()),
        "extensions": dict(internal_suffix_counts),
        "cpk_files": sum(
            Path(path).suffix.lower() == ".cpk" for path in en_internal
        ),
        "unique_cpk_names": len(en_internal_cpks),
    },
    "en_internal_extra_cpks": {
        "count": len(en_extra_internal_names),
        "prefix_counts": dict(prefix_counts(en_extra_internal_names)),
        "sample": sorted(en_extra_internal_names)[:100],
    },
}

print(json.dumps(result, ensure_ascii=False, indent=2))

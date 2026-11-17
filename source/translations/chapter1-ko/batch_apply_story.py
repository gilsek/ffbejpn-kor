"""
High-speed batch story patcher:
1. Matches emulator story CPKs with gt_output/*.json (3,433 translated scenes).
2. Reads base CPKs directly from local release zips (downloads/release-2026.11.04.9/*.zip).
3. Patches text and teller files using BatchStoryPatcher.exe.
4. Packages patched CPKs and deploys to LDPlayer via single tar stream.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile

WORKSPACE = Path(r"c:\Users\USER\Documents\Projects\ffbe_offline_modfix")
RELEASE_DIR = WORKSPACE / "downloads/release-2026.11.04.9"
GT_OUTPUT = WORKSPACE / "artifacts/chapter1-ko/gt_output"
PATCHER_EXE = WORKSPACE / "artifacts/chapter1-ko/BatchStoryPatcher.exe"
STAGE_DIR = WORKSPACE / "artifacts/chapter1-ko/patched_staging"

def collect_emulator_targets():
    # Read both emulator cpk lists
    targets = {} # clean_stem -> list of emulator full paths
    
    for list_file in [
        WORKSPACE / "artifacts/chapter1-ko/emulator_cpk_list.txt",
        WORKSPACE / "artifacts/chapter1-ko/assetpacks_cpk_list.txt"
    ]:
        if not list_file.exists():
            continue
        with open(list_file, "r", encoding="utf-16", errors="ignore") as f:
            for line in f:
                p = line.strip()
                if not p or not p.endswith(".cpk"):
                    continue
                stem = Path(p).stem
                clean = re.sub(r"^Ver\d+_", "", stem)
                if clean not in targets:
                    targets[clean] = []
                if p not in targets[clean]:
                    targets[clean].append(p)
                    
    return targets

def index_release_zips():
    # clean_stem -> (zip_path, entry_name)
    zip_index = {}
    for zpath in RELEASE_DIR.glob("*.zip"):
        with zipfile.ZipFile(zpath, "r") as z:
            for entry in z.namelist():
                if entry.endswith(".cpk"):
                    stem = Path(entry).stem
                    clean = re.sub(r"^Ver\d+_", "", stem)
                    if clean not in zip_index:
                        zip_index[clean] = (zpath, entry)
    return zip_index

def run_batch():
    targets = collect_emulator_targets()
    print(f"Total unique CPK stems in emulator: {len(targets)}")
    
    gt_files = {p.stem: p for p in GT_OUTPUT.glob("*.json")}
    print(f"Total translated JSON files available: {len(gt_files)}")
    
    to_patch = set(targets.keys()) & set(gt_files.keys())
    print(f"Direct matching scenes to patch: {len(to_patch)}")
    
    print("\nIndexing local release zips...")
    zip_index = index_release_zips()
    print(f"Total CPKs indexed in release zips: {len(zip_index)}")
    
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    temp_in = STAGE_DIR / "_temp_in.cpk"
    
    patched_count = 0
    skipped_count = 0
    
    # We will build a tar archive directly: tar_data mapping emu_path -> patched_bytes
    tar_path = WORKSPACE / "artifacts/chapter1-ko/story_patch_payload.tar"
    if tar_path.exists():
        tar_path.unlink()
        
    print(f"\nPatching CPK files using {PATCHER_EXE.name}...")
    
    with tarfile.open(tar_path, "w") as tar:
        for idx, stem in enumerate(sorted(to_patch), 1):
            if stem not in zip_index:
                skipped_count += 1
                continue
                
            zpath, entry_name = zip_index[stem]
            json_path = gt_files[stem]
            
            # Extract orig cpk bytes
            with zipfile.ZipFile(zpath, "r") as z:
                orig_bytes = z.read(entry_name)
                
            temp_in.write_bytes(orig_bytes)
            temp_out = STAGE_DIR / f"{stem}.cpk"
            
            # Run patch-one
            cmd = [str(PATCHER_EXE), "patch-one", str(temp_in), str(json_path), str(temp_out)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not temp_out.exists():
                print(f"  [ERROR] Failed to patch {stem}: {res.stderr}")
                skipped_count += 1
                continue
                
            patched_bytes = temp_out.read_bytes()
            temp_out.unlink()
            
            # Add to tar for every emulator destination path
            for emu_path in targets[stem]:
                # Tar entry path: relative path without leading slash
                rel_tar_path = emu_path.lstrip("/")
                ti = tarfile.TarInfo(name=rel_tar_path)
                ti.size = len(patched_bytes)
                ti.mode = 0o666
                tar.addfile(ti, io.BytesIO(patched_bytes))
                
            patched_count += 1
            if idx % 100 == 0 or idx == len(to_patch):
                print(f"  Processed {idx}/{len(to_patch)} scenes (Patched: {patched_count})...")
                
    if temp_in.exists():
        temp_in.unlink()
        
    print(f"\n==========================================")
    print(f"Successfully generated story payload tar:")
    print(f"  Path: {tar_path}")
    print(f"  Size: {tar_path.stat().st_size:,} bytes")
    print(f"  Patched scenes: {patched_count} / {len(to_patch)}")
    print(f"==========================================")
    
    # Deploy to emulator via ADB
    print("\nDeploying payload tar to LDPlayer (emulator-5558)...")
    cmd_push = ["adb", "-s", "emulator-5558", "push", str(tar_path), "/data/local/tmp/story_patch.tar"]
    subprocess.run(cmd_push, check=True)
    print("  -> Uploaded tar to /data/local/tmp/story_patch.tar")
    
    # Extract tar in emulator root directory
    cmd_untar = ["adb", "-s", "emulator-5558", "shell", "su -c 'tar -xf /data/local/tmp/story_patch.tar -C / && rm -f /data/local/tmp/story_patch.tar'"]
    subprocess.run(cmd_untar, check=True)
    print("  -> Extracted all patched CPKs into game directories!")
    
    # Restart FFBE app
    print("\nRestarting FFBE app...")
    subprocess.run(["adb", "-s", "emulator-5558", "shell", "am force-stop com.exvius.memorial.korean"], check=True)
    subprocess.run(["adb", "-s", "emulator-5558", "shell", "am start -n com.exvius.memorial.korean/com.square_enix.ffbejpn.Lapis"], check=True)
    print("  -> FFBE app restarted with Korean story patch!")
    print("\n[ALL TASKS COMPLETED SUCCESSFULLY!]")

if __name__ == "__main__":
    run_batch()

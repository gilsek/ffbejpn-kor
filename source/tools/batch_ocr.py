"""Orchestrate chunked OCR runs in parallel processes with real-time progress.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / 'build/out/sprite_work'
IN_DIR = WORK_DIR / 'in'
CACHE_DIR = WORK_DIR / 'cache'

NUM_CHUNKS = 4


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_files = list(IN_DIR.glob('*.png'))
    total_files = len(all_files)
    print(f'Starting OCR for {total_files} sprites across {NUM_CHUNKS} parallel worker processes...', flush=True)

    procs = []
    for c in range(NUM_CHUNKS):
        cmd = [
            sys.executable, '-u', str(ROOT / 'tools/run_sprite_ocr.py'),
            '--chunk-id', str(c),
            '--num-chunks', str(NUM_CHUNKS)
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        procs.append(p)

    # Monitor progress by counting cache files
    t0 = time.time()
    while True:
        alive = sum(1 for p in procs if p.poll() is None)
        cached = len(list(CACHE_DIR.glob('*.png.json')))
        elapsed = time.time() - t0
        speed = cached / max(elapsed, 0.001)
        remaining = (total_files - cached) / max(speed, 0.001) if speed > 0 else 0
        print(f'Progress: {cached}/{total_files} ({cached*100.0/total_files:.1f}%) | {speed:.1f} imgs/s | est remaining: {remaining/60.0:.1f} min | workers alive: {alive}', flush=True)

        if alive == 0 or cached >= total_files:
            break
        time.sleep(5)

    print('All workers finished. Running merge step...', flush=True)
    subprocess.run([sys.executable, '-u', str(ROOT / 'tools/run_sprite_ocr.py'), '--merge'], check=True)
    print('OCR pipeline complete!', flush=True)


if __name__ == '__main__':
    main()

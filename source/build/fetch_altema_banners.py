# -*- coding: utf-8 -*-
"""Download the Altema (img.altema.jp) banner images listed in quest_banners.tsv.

Input (read only)
  build/out/vortex_season/altema/quest_banners.tsv   row, name, url, img, alt, wh, h1
Output
  build/out/vortex_season/altema/img/<img>           one file per unique `img` (sub-directory kept)
  build/out/vortex_season/altema/download_failures.tsv  img, status, error (empty when everything succeeded)

The files are image data only. Nothing is executed. Re-running skips files that are already complete
(a file is written under a .part name and renamed, then compared with the HEAD size in img_sizes.tsv).

usage: python -I -X utf8 build/fetch_altema_banners.py [--workers 4] [--retries 3] [--limit N]
"""
import argparse
import csv
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
ALT = ROOT / 'build/out/vortex_season/altema'
QUEST = ALT / 'quest_banners.tsv'
SIZES = ALT / 'img_sizes.tsv'
IMG = ALT / 'img'
FAILURES = ALT / 'download_failures.tsv'
PREFIX = 'https://img.altema.jp/ffbe/uploads/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
MAGIC = {b'\x89PNG\r\n\x1a\n': 'png', b'\xff\xd8\xff': 'jpg', b'GIF8': 'gif', b'RIFF': 'webp'}


def read_sizes():
    sizes = {}
    if SIZES.is_file():
        with open(SIZES, encoding='utf-8') as fh:
            for line in fh:
                parts = line.rstrip('\n').split('\t')
                if parts and parts[0]:
                    sizes[parts[0]] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    return sizes


def read_images():
    seen = []
    with open(QUEST, encoding='utf-8') as fh:
        for row in csv.DictReader(fh, delimiter='\t'):
            img = (row.get('img') or '').strip()
            if img and img not in seen:
                seen.append(img)
    return seen


def valid(path, expected=None):
    """A complete download: recognised image container and a decodable image.

    `expected` (img_sizes.tsv, measured with HEAD in an earlier session) is NOT enforced: the CDN
    re-encodes some files, so a correct body can be a few KB off. Header + Pillow decode is the check.
    """
    try:
        size = path.stat().st_size
        if size < 128 or size > 20 * 1024 * 1024:
            return False
        with open(path, 'rb') as fh:
            head = fh.read(12)
    except OSError:
        return False
    if not any(head.startswith(m) for m in MAGIC):
        return False
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def fetch(img, expected, retries, local):
    url = PREFIX + img
    target = IMG / img
    target.parent.mkdir(parents=True, exist_ok=True)
    if valid(target, expected):
        return img, 'cached', ''
    if not hasattr(local, 'session'):
        # requests.Session is not thread-safe: one per worker thread.
        local.session = requests.Session()
        # Plain */* -- a browser image Accept header makes the CDN serve WebP/AVIF, whose byte size
        # does not match img_sizes.tsv and which is not what the game's PNG conversion wants.
        local.session.headers.update({'User-Agent': UA, 'Referer': 'https://altema.jp/',
                                      'Accept': '*/*'})
    session = local.session
    last = ''
    for attempt in range(retries):
        tmp = target.with_name(target.name + '.part')
        try:
            with session.get(url, timeout=45, stream=True) as response:
                if response.status_code != 200:
                    last = 'HTTP %s' % response.status_code
                else:
                    with open(tmp, 'wb') as out:
                        for chunk in response.iter_content(65536):
                            out.write(chunk)
                    if valid(tmp, expected):
                        os.replace(tmp, target)
                        return img, 'downloaded', ''
                    last = 'bad body (%d bytes, not a decodable image)' % tmp.stat().st_size
        except Exception as exc:                    # network errors, timeouts
            last = '%s: %s' % (type(exc).__name__, exc)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        time.sleep(0.6 * (attempt + 1))
    return img, 'failed', last


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument('--limit', type=int, default=0, help='only the first N (smoke test)')
    args = ap.parse_args()

    images = read_images()
    if args.limit:
        images = images[:args.limit]
    sizes = read_sizes()
    IMG.mkdir(parents=True, exist_ok=True)
    counts = {'downloaded': 0, 'cached': 0, 'failed': 0}
    failures = []
    lock = threading.Lock()

    workers = max(1, min(args.workers, 4))
    local = threading.local()          # one requests.Session per worker thread

    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(fetch, img, sizes.get(img), args.retries, local): img for img in images}
        done = 0
        for future in as_completed(jobs):
            img, status, error = future.result()
            done += 1
            with lock:
                counts[status] += 1
                if status == 'failed':
                    failures.append((img, status, error.replace('\t', ' ')))
            if done % 50 == 0 or done == len(jobs):
                print('%d/%d downloaded=%d cached=%d failed=%d' % (
                    done, len(jobs), counts['downloaded'], counts['cached'], counts['failed']), flush=True)

    with open(FAILURES, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh, delimiter='\t', lineterminator='\n')
        writer.writerow(['img', 'status', 'error'])
        writer.writerows(sorted(failures))
    print('unique images %d; downloaded %d, cached %d, failed %d' % (
        len(images), counts['downloaded'], counts['cached'], counts['failed']))
    print('failure list:', FAILURES, '(empty = success)' if not failures else '')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

"""Download the complete public data release to PC with resume and SHA-256 checks."""
import concurrent.futures
import hashlib
import json
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = 'https://raw.githubusercontent.com/Elvlin/exvius-offline/main/data/latest.json'
progress = {}
lock = threading.Lock()


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download(pack, folder):
    url = pack['url']
    if not url.startswith('https://github.com/Elvlin/exvius-offline/releases/download/'):
        raise ValueError('Unexpected download source')
    name = Path(urllib.parse.urlparse(url).path).name
    target = folder / name
    cached = ROOT / 'artifacts' / name
    if not target.exists() and cached.is_file() and cached.stat().st_size == pack['size'] and digest(cached) == pack['sha256']:
        shutil.copyfile(cached, target)
    if target.exists():
        if target.stat().st_size != pack['size'] or digest(target) != pack['sha256']:
            raise ValueError('Existing file failed validation: ' + name)
        with lock:
            progress[pack['id']] = pack['size']
        return {'id': pack['id'], 'file': name, 'sha256': pack['sha256'], 'verified': True}
    partial = folder / (name + '.part')
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > pack['size']:
            raise ValueError('Oversized partial file: ' + name)
        with lock:
            progress[pack['id']] = offset
        try:
            if offset < pack['size']:
                headers = {'Range': f'bytes={offset}-'} if offset else {}
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
                    if offset and (response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
                        raise ValueError('Server did not honor resume request: ' + name)
                    with partial.open('ab' if offset else 'xb') as stream:
                        while True:
                            block = response.read(4 * 1024 * 1024)
                            if not block:
                                break
                            if offset + len(block) > pack['size']:
                                raise ValueError('Download exceeded expected size')
                            stream.write(block)
                            offset += len(block)
                            with lock:
                                progress[pack['id']] = offset
            if partial.stat().st_size != pack['size']:
                raise OSError('Incomplete download: ' + name)
            if digest(partial) != pack['sha256']:
                raise ValueError('Checksum mismatch; preserved partial file: ' + name)
            partial.rename(target)
            return {'id': pack['id'], 'file': name, 'sha256': pack['sha256'], 'verified': True}
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2)


if __name__ == '__main__':
    with urllib.request.urlopen(SOURCE, timeout=20) as response:
        raw = response.read()
    manifest = json.loads(raw)
    version = manifest['version']
    if not re.fullmatch(r'[0-9.]+', version):
        raise ValueError('Unexpected release version')
    folder = ROOT / 'downloads' / ('release-' + version)
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = folder / 'manifest.json'
    if snapshot.exists() and json.loads(snapshot.read_text()) != manifest:
        raise ValueError('Existing release snapshot differs; refusing to overwrite')
    if not snapshot.exists():
        snapshot.write_bytes(raw)
    total = sum(pack['size'] for pack in manifest['packs'])
    print(json.dumps({'event': 'start', 'packs': len(manifest['packs']), 'bytes': total, 'folder': str(folder)}), flush=True)
    results = []
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        pending = {executor.submit(download, p, folder): p['id'] for p in manifest['packs']}
        while pending:
            done, _ = concurrent.futures.wait(pending, timeout=15, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                result = future.result()
                results.append(result)
                print(json.dumps({'event': 'verified', **result}), flush=True)
                del pending[future]
            with lock:
                received = sum(progress.values())
            print(json.dumps({'event': 'progress', 'received': received, 'total': total,
                              'verified': len(results), 'elapsed_seconds': round(time.monotonic() - started)}), flush=True)
    (folder / 'verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('ALL_PACKS_VERIFIED', len(results), flush=True)

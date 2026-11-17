"""Serve build/out/release over HTTP with Range support for the local download test.

usage: python -I build/serve_release_local.py [--port 8000] [--drop-after-mib N]
Writes build/out/release/latest_local.json (pack URLs -> http://127.0.0.1:<port>/v0.1.0/...).
Use with `adb reverse tcp:<port> tcp:<port>` and a test APK built with
  --manifest-url http://127.0.0.1:<port>/latest_local.json --assets-prefix http://127.0.0.1:<port>/
--drop-after-mib cuts the FIRST full (non-Range) response after N MiB to exercise resume.
"""
import argparse, json, os, re, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'build/out/release'
state = {'drop': None, 'lock': threading.Lock()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args), flush=True)

    def do_HEAD(self):
        self.handle_get(head=True)

    def do_GET(self):
        self.handle_get(head=False)

    def handle_get(self, head):
        rel = self.path.split('?', 1)[0].lstrip('/')
        path = (ROOT / rel).resolve()
        if ROOT.resolve() not in path.parents or not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end, code = 0, size - 1, 200
        rng = self.headers.get('Range')
        if rng:
            m = re.fullmatch(r'bytes=(\d+)-(\d*)', rng.strip())
            if not m or int(m[1]) >= size:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            start = int(m[1])
            end = int(m[2]) if m[2] else size - 1
            code = 206
        self.send_response(code)
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        if code == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if head:
            return
        limit = None
        with state['lock']:
            if code == 200 and state['drop'] is not None and path.suffix == '.zip':
                limit, state['drop'] = state['drop'], None
        sent = 0
        with open(path, 'rb') as fh:
            fh.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)
                sent += len(chunk)
                if limit is not None and sent >= limit:
                    print(f'** dropping connection after {sent >> 20} MiB of {rel}', flush=True)
                    self.close_connection = True
                    self.connection.shutdown(2)
                    return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--drop-after-mib', type=int)
    ap.add_argument('--device-port', type=int, help='port the APK uses (adb reverse tcp:<device> tcp:<port>)')
    args = ap.parse_args()
    if args.drop_after_mib:
        state['drop'] = args.drop_after_mib << 20
    manifest = json.loads((ROOT / 'v0.1.0/latest.json').read_text(encoding='utf-8'))
    base = f'http://127.0.0.1:{args.device_port or args.port}/'
    for pack in manifest['packs']:
        pack['url'] = base + 'v0.1.0/' + pack['url'].rsplit('/', 1)[1]
    (ROOT / 'latest_local.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    print('serving', ROOT, 'on', base, flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()

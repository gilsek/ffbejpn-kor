"""Receive the jp_cpk_dump.js export stream (adb reverse) into build/out/vortex_season/cpk_dump/raw/.

Usage: adb reverse tcp:38917 tcp:38917, start this, then restart the app with deploy_jp_frida.py --cpk-dump.
Stream: per file b"F\\t<name>\\t<size>\\n" + bytes, then b"END\\n". Then run collect_cpk_banner_dump.py.
"""
import argparse
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_line(f):
    line = f.readline()
    if not line:
        raise EOFError('stream ended before END')
    return line.decode('utf-8').rstrip('\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=38917)
    ap.add_argument('--out', default=str(ROOT / 'build/out/vortex_season/cpk_dump/raw'))
    ap.add_argument('--timeout', type=int, default=600)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', args.port))
    srv.listen(1)
    srv.settimeout(args.timeout)
    print('listening 127.0.0.1:%d -> %s' % (args.port, out), flush=True)
    conn, _ = srv.accept()
    conn.settimeout(120)
    f = conn.makefile('rb')
    n = total = 0
    while True:
        line = read_line(f)
        if line == 'END':
            break
        tag, name, size = line.split('\t')
        size = int(size)
        if tag != 'F' or '/' in name or '\\' in name or name.startswith('..'):
            raise ValueError('bad header %r' % line)
        data = f.read(size)
        if len(data) != size:
            raise EOFError('short read %s %d/%d' % (name, len(data), size))
        (out / name).write_bytes(data)
        n += 1
        total += size
    print('received files=%d bytes=%d' % (n, total), flush=True)


if __name__ == '__main__':
    main()

"""Start or stop this project's local server without shell scripts or remote code."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

import psutil

ROOT = Path(__file__).resolve().parent


@contextlib.contextmanager
def launch_lock(path):
    with path.open('a+b') as handle:
        handle.seek(0)
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('A launch/stop operation is in progress. Try again shortly.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def owned_process(record):
    try:
        state = json.loads(record.read_text())
        process = psutil.Process(state['pid'])
        if abs(process.create_time() - state['created']) < 0.01 and str(ROOT / 'app.py') in process.cmdline():
            return process
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return None


def healthy(url):
    try:
        # Local health checks must not use a system HTTP proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + '/_stcore/health', timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def stop_process(process):
    children = process.children(recursive=True)
    for child in reversed(children):
        with contextlib.suppress(psutil.Error):
            child.terminate()
    with contextlib.suppress(psutil.Error):
        process.terminate()
    _, alive = psutil.wait_procs(children + [process], timeout=5)
    for remaining in alive:
        with contextlib.suppress(psutil.Error):
            remaining.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8501)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    runtime = ROOT / '.data'
    runtime.mkdir(exist_ok=True)
    record = runtime / f'launcher-{args.port}.json'
    url = f'http://127.0.0.1:{args.port}'
    try:
        with launch_lock(runtime / f'launcher-{args.port}.lock'):
            existing = owned_process(record)
            if args.stop:
                if existing:
                    stop_process(existing)
                record.unlink(missing_ok=True)
                print('Subtitle Translator stopped.')
                return 0
            if existing:
                if not healthy(url):
                    raise RuntimeError('Server is still starting. Retry shortly or use the stop launcher.')
                if not args.no_browser:
                    webbrowser.open(url)
                print(f'Already running: {url}')
                return 0
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1', args.port)) == 0:
                    raise RuntimeError(f'Port {args.port} is occupied by another process. Choose another port.')
            with (runtime / 'server.log').open('a', encoding='utf-8') as log:
                process = subprocess.Popen(
                    [sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                     '--server.headless=true', '--server.address=127.0.0.1', f'--server.port={args.port}'],
                    cwd=ROOT, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    start_new_session=os.name != 'nt',
                )
            owned = psutil.Process(process.pid)
            record.write_text(json.dumps({'pid': process.pid, 'created': owned.create_time()}))
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Server exited. See .data/server.log.')
                if healthy(url):
                    if not args.no_browser:
                        webbrowser.open(url)
                    print(f'Ready: {url}')
                    return 0
                time.sleep(0.2)
            stop_process(owned)
            record.unlink(missing_ok=True)
            raise RuntimeError('Startup timed out. See .data/server.log.')
    except Exception as exc:
        with (runtime / 'launcher-error.log').open('a', encoding='utf-8') as log:
            log.write(f'{type(exc).__name__}: {exc}\n')
        print(f'Launch failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

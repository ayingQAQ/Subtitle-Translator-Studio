import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def app_url(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    runtime = tmp_path_factory.mktemp('browser-runtime')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(APP_DB_PATH=str(runtime / 'memory.db'),
               APP_SECRET_STORE_PATH=str(runtime / 'secrets.enc'),
               APP_SECRET_KEY_PATH=str(runtime / 'secrets.key'))
    url = f'http://127.0.0.1:{port}'
    with (runtime / 'server.log').open('w') as log:
        process = subprocess.Popen(
            [sys.executable, '-m', 'streamlit', 'run', 'app.py', '--server.headless=true',
             '--server.address=127.0.0.1', f'--server.port={port}'],
            cwd=root, env=env, stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail((runtime / 'server.log').read_text())
                try:
                    with urllib.request.urlopen(url + '/_stcore/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                pytest.fail('Streamlit did not become healthy')
            yield url
        finally:
            process.terminate()
            process.wait(timeout=15)

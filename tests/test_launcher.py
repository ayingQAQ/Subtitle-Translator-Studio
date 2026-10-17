import json
from pathlib import Path
import socket
import subprocess
import sys

import psutil


def test_launcher_reuses_and_stops_its_server():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [sys.executable, str(root / 'launcher.py'), '--port', str(port), '--no-browser']
    record = root / '.data' / f'launcher-{port}.json'
    try:
        first = subprocess.run(command, capture_output=True, text=True, timeout=75)
        assert first.returncode == 0, first.stderr
        state = json.loads(record.read_text())
        second = subprocess.run(command, capture_output=True, text=True, timeout=15)
        assert second.returncode == 0, second.stderr
        assert 'Already running' in second.stdout
        assert json.loads(record.read_text())['pid'] == state['pid']
        stopped = subprocess.run(command + ['--stop'], capture_output=True, text=True, timeout=15)
        assert stopped.returncode == 0, stopped.stderr
        assert not psutil.pid_exists(state['pid']) or psutil.Process(state['pid']).status() == psutil.STATUS_ZOMBIE
    finally:
        subprocess.run(command + ['--stop'], capture_output=True, timeout=15)


def test_launcher_does_not_stop_unrelated_listener():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        port = sock.getsockname()[1]
        result = subprocess.run([sys.executable, str(root / 'launcher.py'), '--port', str(port), '--no-browser'],
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 1
        assert 'occupied' in result.stderr
        assert sock.fileno() != -1

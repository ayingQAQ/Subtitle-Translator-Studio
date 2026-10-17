import os
import socket
import subprocess
import sys
import time
import urllib.request
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def fake_api():
    state = {'fail': set(), 'calls': [], 'block': set(), 'entered': threading.Event(), 'release': threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def send_json(self, payload, status=200):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def do_GET(self):
            self.send_json({'object': 'list', 'data': [{'id': 'test-model', 'object': 'model'}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            payload = json.loads(body['messages'][-1]['content'])
            texts = [item['text'] for item in payload['items']]
            state['calls'].extend(texts)
            if any(text in state['block'] for text in texts):
                state['entered'].set()
                state['release'].wait(timeout=15)
            if any(text in state['fail'] for text in texts):
                self.send_json({'error': {'message': 'Simulated auth failure', 'type': 'authentication_error'}}, 401)
                return
            translated = {'translations': [{'id': item['id'], 'text': item['text'] + ' translated'} for item in payload['items']]}
            self.send_json({'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'test-model',
                            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(translated)}, 'finish_reason': 'stop'}]})
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state['url'] = f'http://127.0.0.1:{server.server_port}/v1'
    yield state
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture(scope='session')
def app_url(tmp_path_factory, fake_api):
    root = Path(__file__).resolve().parents[2]
    runtime = tmp_path_factory.mktemp('browser-runtime')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(APP_DB_PATH=str(runtime / 'memory.db'),
               APP_SECRET_STORE_PATH=str(runtime / 'secrets.enc'),
               APP_SECRET_KEY_PATH=str(runtime / 'secrets.key'),
               DEEPSEEK_API_KEY='fake-browser-test-key', DEEPSEEK_MODEL='test-model',
               DEEPSEEK_BASE_URL=fake_api['url'], APP_BATCH_SIZE='1')
    env['NO_PROXY'] = env.get('NO_PROXY', '') + ',127.0.0.1,localhost'
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

from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError, AuthenticationError

from subtitle_translator.jobs import TranslationJob, restore_checkpoint
from subtitle_translator.secret_store import SecretStore, SecretStoreError, DPAPI_PREFIX
from subtitle_translator.translator import OpenAICompatibleTranslatorProvider, TranslationError, ProviderSettings, _request_any_json
from test_translation import document, Provider


def llm_with_create(monkeypatch, create):
    monkeypatch.setattr('openai.OpenAI', lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    return OpenAICompatibleTranslatorProvider('test', 'fake-key', 'model')


def test_auth_error_is_not_retried_without_json(monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        raise AuthenticationError('bad key', response=httpx.Response(401, request=httpx.Request('POST', 'https://example.test')), body={})
    provider = llm_with_create(monkeypatch, create)
    with pytest.raises(TranslationError, match='Invalid API key'):
        provider.translate_batch(['Hello'], source_language='en', target_language='zh', glossary=[])
    assert len(calls) == 1


def test_only_unsupported_response_format_falls_back(monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if 'response_format' in kwargs:
            raise BadRequestError('unsupported', response=httpx.Response(400, request=httpx.Request('POST', 'https://example.test')),
                                  body={'message': 'response_format is not supported'})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"translations":[{"id":"0","text":"你好"}]}'))])
    provider = llm_with_create(monkeypatch, create)
    assert provider.translate_batch(['Hello'], source_language='en', target_language='zh', glossary=[]) == ['你好']
    assert len(calls) == 2


def test_job_checkpoints_and_resumes(monkeypatch, tmp_path):
    provider = Provider()
    monkeypatch.setattr('subtitle_translator.jobs.build_translator_provider', lambda settings: provider)
    checkpoint = tmp_path / 'job.json'
    config = SimpleNamespace(db_path=tmp_path / 'memory.db', batch_size=1)
    settings = ProviderSettings('custom-openai', 'do-not-store-this', 'test')
    job = TranslationJob(document(), settings, config, 'en', 'zh', [], checkpoint).start()
    job.thread.join(timeout=5)
    assert job.snapshot()['status'] == 'failed'
    assert 'do-not-store-this' not in checkpoint.read_text()
    restored, failures = restore_checkpoint(checkpoint, document())
    assert restored.segments[0].translated_text == 'Hello translated'
    assert failures
    provider.calls.clear()
    provider.fail = False
    resumed = TranslationJob(restored, settings, config, 'en', 'zh', [], checkpoint).start()
    resumed.thread.join(timeout=5)
    assert resumed.snapshot()['status'] == 'completed'
    assert provider.calls == ['World']


def test_secrets_reopen_delete_and_missing_key(tmp_path):
    path, key = tmp_path / 'secrets.enc', tmp_path / 'secrets.key'
    SecretStore(path, key).set('provider', 'test-secret')
    assert b'test-secret' not in path.read_bytes()
    assert SecretStore(path, key).get('provider') == 'test-secret'
    SecretStore(path, key).delete('provider')
    assert SecretStore(path, key).get('provider') == ''
    key.unlink()
    with pytest.raises(SecretStoreError, match='missing'):
        SecretStore(path, key).get('provider')


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Windows DPAPI')
def test_windows_migrates_legacy_fernet_key(tmp_path):
    from cryptography.fernet import Fernet
    path, key = tmp_path / 'secrets.enc', tmp_path / 'secrets.key'
    raw = Fernet.generate_key()
    key.write_bytes(raw)
    path.write_bytes(Fernet(raw).encrypt(b'{"provider":"secret"}'))
    assert SecretStore(path, key).get('provider') == 'secret'
    assert key.read_bytes().startswith(DPAPI_PREFIX)
    assert raw not in key.read_bytes()
    assert SecretStore(path, key).get('provider') == 'secret'


def test_http_retries_transient_errors_without_exposing_key(monkeypatch):
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        return httpx.Response(503 if len(calls) < 3 else 200, json={'ok': True},
                              request=httpx.Request('GET', 'https://example.test?key=private-key'))
    monkeypatch.setattr('subtitle_translator.translator.httpx.request', request)
    monkeypatch.setattr('subtitle_translator.translator.sleep', lambda seconds: None)
    assert _request_any_json('GET', 'https://example.test', params=None, headers=None, timeout_seconds=1) == {'ok': True}
    assert len(calls) == 3
    calls.clear()
    monkeypatch.setattr('subtitle_translator.translator.httpx.request', lambda **kwargs: httpx.Response(
        401, request=httpx.Request('GET', 'https://example.test?key=private-key')))
    with pytest.raises(TranslationError) as error:
        _request_any_json('GET', 'https://example.test', params=None, headers=None, timeout_seconds=1)
    assert '401' in str(error.value)
    assert 'private-key' not in str(error.value)


def test_running_job_is_reused_after_page_refresh(monkeypatch, tmp_path):
    import threading
    release, entered = threading.Event(), threading.Event()
    class SlowProvider(Provider):
        def translate_batch(self, texts, **kwargs):
            entered.set()
            release.wait(timeout=5)
            return texts
    monkeypatch.setattr('subtitle_translator.jobs.build_translator_provider', lambda settings: SlowProvider())
    config = SimpleNamespace(db_path=tmp_path / 'memory.db', batch_size=1)
    settings = ProviderSettings('custom-openai', 'fake', 'test')
    checkpoint = tmp_path / 'job.json'
    job = TranslationJob(document(), settings, config, 'en', 'zh', [], checkpoint).start()
    try:
        assert entered.wait(timeout=3)
        duplicate = TranslationJob(document(), settings, config, 'en', 'zh', [], checkpoint).start()
        assert duplicate is job
    finally:
        release.set()
        job.thread.join(timeout=5)

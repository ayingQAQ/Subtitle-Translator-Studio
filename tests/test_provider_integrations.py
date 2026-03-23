from __future__ import annotations

from typing import Any

from subtitle_translator.translator import (
    DeepLTranslatorProvider,
    GoogleTranslateProvider,
    GoogleTranslateWebProvider,
    ProviderSettings,
    build_translator_provider,
    probe_provider_connection,
)


class DummyResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_google_translate_provider_uses_expected_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request(*, method, url, params, json, headers, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse(
            {
                "data": {
                    "translations": [
                        {"translatedText": "\u4f60\u597d"},
                        {"translatedText": "\u4e16\u754c"},
                    ]
                }
            }
        )

    monkeypatch.setattr("subtitle_translator.translator.httpx.request", fake_request)

    provider = GoogleTranslateProvider(api_key="g-key", timeout_seconds=12)
    result = provider.translate_batch(
        ["hello", "world"],
        source_language="en",
        target_language="zh",
        glossary=[],
    )

    assert result == ["\u4f60\u597d", "\u4e16\u754c"]
    assert captured["method"] == "POST"
    assert captured["url"] == "https://translation.googleapis.com/language/translate/v2"
    assert captured["params"] == {"key": "g-key"}
    assert captured["json"]["source"] == "en"
    assert captured["json"]["target"] == "zh-CN"


def test_deepl_provider_uses_auth_header(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request(*, method, url, params, json, headers, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse({"translations": [{"text": "\u3053\u3093\u306b\u3061\u306f"}]})

    monkeypatch.setattr("subtitle_translator.translator.httpx.request", fake_request)

    provider = DeepLTranslatorProvider(
        api_key="d-key",
        base_url="https://api-free.deepl.com/v2/translate",
        timeout_seconds=7,
    )
    result = provider.translate_batch(
        ["hello"],
        source_language="en",
        target_language="ja",
        glossary=[],
    )

    assert result == ["\u3053\u3093\u306b\u3061\u306f"]
    assert captured["method"] == "POST"
    assert captured["headers"]["Authorization"] == "DeepL-Auth-Key d-key"
    assert captured["json"]["source_lang"] == "EN"
    assert captured["json"]["target_lang"] == "JA"


def test_build_translator_provider_returns_google_provider() -> None:
    provider = build_translator_provider(
        ProviderSettings(
            provider_id="google-translate",
            api_key="g-key",
            timeout_seconds=30,
        )
    )

    assert provider.provider_name == "google-translate"
    assert provider.model_name == "google-translate-basic-v2"


def test_build_translator_provider_returns_google_web_without_key() -> None:
    provider = build_translator_provider(
        ProviderSettings(
            provider_id="google-web",
            api_key="",
            timeout_seconds=30,
        )
    )

    assert provider.provider_name == "google-web"
    assert provider.model_name == "google-web-unofficial"


def test_google_web_provider_parses_list_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_request(*, method, url, params, json, headers, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return DummyResponse([[["你好", "hello", None, None, 10]], None, "en"])

    monkeypatch.setattr("subtitle_translator.translator.httpx.request", fake_request)

    provider = GoogleTranslateWebProvider(timeout_seconds=8)
    result = provider.translate_batch(
        ["hello"],
        source_language="en",
        target_language="zh",
        glossary=[],
    )

    assert result == ["你好"]
    assert captured["method"] == "GET"
    assert "translate_a/single" in captured["url"]
    assert captured["params"]["client"] == "gtx"
    assert captured["params"]["sl"] == "en"
    assert captured["params"]["tl"] == "zh-CN"


def test_build_translator_provider_llm_initializes_client(monkeypatch) -> None:
    class DummyOpenAI:
        def __init__(self, *, api_key, base_url, timeout):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout

    monkeypatch.setattr("openai.OpenAI", DummyOpenAI)

    provider = build_translator_provider(
        ProviderSettings(
            provider_id="deepseek",
            api_key="ds-key",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            timeout_seconds=10,
        )
    )

    assert provider.provider_name == "deepseek"
    assert provider.model_name == "deepseek-chat"
    assert provider._client.api_key == "ds-key"


def test_probe_provider_connection_google_success(monkeypatch) -> None:
    def fake_request(*, method, url, params, json, headers, timeout):
        assert method == "GET"
        assert "languages" in url
        return DummyResponse({"data": {"languages": [{"language": "en"}, {"language": "zh-CN"}]}})

    monkeypatch.setattr("subtitle_translator.translator.httpx.request", fake_request)

    ok, message, _ = probe_provider_connection(
        ProviderSettings(
            provider_id="google-translate",
            api_key="g-key",
            timeout_seconds=5,
        )
    )

    assert ok is True
    assert "languages endpoint ok" in message


def test_probe_provider_connection_google_web_success(monkeypatch) -> None:
    def fake_request(*, method, url, params, json, headers, timeout):
        assert method == "GET"
        assert "translate_a/single" in url
        return DummyResponse([[["你好", "hello", None, None, 10]], None, "en"])

    monkeypatch.setattr("subtitle_translator.translator.httpx.request", fake_request)

    ok, message, _ = probe_provider_connection(
        ProviderSettings(
            provider_id="google-web",
            api_key="",
            timeout_seconds=5,
        )
    )

    assert ok is True
    assert "web endpoint ok" in message

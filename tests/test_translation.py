from types import SimpleNamespace

import pytest

from subtitle_translator.encoding import decode_subtitle_bytes
from subtitle_translator.identity import memory_identity, connection_identity
from subtitle_translator.memory import TranslationMemory
from subtitle_translator.models import GlossaryTerm
from subtitle_translator.subtitle_io import load_subtitle_document
from subtitle_translator.translator import TranslationService, TranslationError, TranslationCancelled, bounded_batches


def document():
    return load_subtitle_document('test.srt', b'1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n\n')


class Provider:
    provider_name, model_name, base_url = 'test', 'model', 'https://example.test'
    def __init__(self):
        self.calls = []
        self.fail = True
    def translate_batch(self, texts, **kwargs):
        self.calls.extend(texts)
        if self.fail and texts == ['World']:
            raise TranslationError('temporary failure')
        return [text + ' translated' for text in texts]


def test_resume_only_failed_lines(tmp_path):
    doc, provider = document(), Provider()
    with TranslationMemory(tmp_path / 'memory.db') as memory:
        service = TranslationService(provider, memory, batch_size=1)
        service.translate_document(doc, source_language='en', target_language='zh', glossary=[])
        assert doc.segments[0].translated_raw_text == 'Hello translated'
        assert 1 in service.failures
        provider.calls.clear()
        provider.fail = False
        service.translate_document(doc, source_language='en', target_language='zh', glossary=[])
        assert provider.calls == ['World']
        assert not service.failures


def test_cancel_keeps_completed(tmp_path):
    doc, provider = document(), Provider()
    with TranslationMemory(tmp_path / 'memory.db') as memory:
        service = TranslationService(provider, memory, batch_size=1)
        with pytest.raises(TranslationCancelled):
            service.translate_document(doc, source_language='en', target_language='zh', glossary=[],
                                       cancel_requested=lambda: bool(provider.calls))
        assert doc.segments[0].translated_raw_text


def test_cache_separates_glossary_endpoint_credentials():
    doc, provider = document(), Provider()
    initial = memory_identity(provider, [], doc)
    assert initial != memory_identity(provider, [GlossaryTerm('term', 'translation')], doc)
    provider.base_url += '/other'
    assert initial != memory_identity(provider, [], doc)
    a = SimpleNamespace(provider_id='test', base_url='https://example.test', api_key='one')
    b = SimpleNamespace(provider_id='test', base_url='https://example.test', api_key='two')
    assert connection_identity(a) != connection_identity(b)


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-8-sig', 'cp932', 'gb18030', 'big5'])
def test_manual_encoding_newlines(encoding):
    text = 'Hello\r\nWorld\r\n'
    decoded = decode_subtitle_bytes(text.encode(encoding), encoding)
    assert decoded.text == text
    assert decoded.newline == '\r\n'


def test_utf16_bom_newline():
    assert decode_subtitle_bytes('日本語\r\n字幕'.encode('utf-16')).newline == '\r\n'


def test_batches_bound_length_and_count():
    assert list(bounded_batches(['aaaa', 'bbbb', 'cc'], 3, 6)) == [['aaaa'], ['bbbb', 'cc']]

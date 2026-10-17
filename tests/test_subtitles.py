from subtitle_translator.subtitle_io import load_subtitle_document, export_subtitle_document
from subtitle_translator.subtitle_io import apply_subtitle_edits, SubtitleIOError
import pytest


def test_subtitle_timing_roundtrip():
    data = b'1\n00:00:01,000 --> 00:00:02,000\nHello\n\n'
    doc = load_subtitle_document('sample.srt', data)
    result = export_subtitle_document(doc, target_language='zh')
    assert b'00:00:01,000 --> 00:00:02,000' in result.content
    assert result.file_name == 'sample.zh.srt'


def test_edit_preserves_tags_and_falls_back_encoding():
    doc = load_subtitle_document('sample.srt', b'1\n00:00:01,000 --> 00:00:02,000\n<i>Hello</i>\n\n', 'ascii')
    with pytest.raises(SubtitleIOError):
        apply_subtitle_edits(doc, {0: 'Lost tags'})
    assert doc.segments[0].translated_text is None
    apply_subtitle_edits(doc, {0: '<i>你好</i>'})
    output = export_subtitle_document(doc, target_language='zh')
    assert output.encoding == 'utf-8-sig'
    assert '<i>你好</i>' in output.content.decode('utf-8-sig')


def test_unchanged_partial_edit_does_not_mark_as_completed():
    doc = load_subtitle_document('sample.srt', b'1\n00:00:01,000 --> 00:00:02,000\nHello\n\n')
    apply_subtitle_edits(doc, {0: 'Hello'})
    assert doc.segments[0].translated_raw_text is None

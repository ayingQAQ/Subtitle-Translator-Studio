from subtitle_translator.subtitle_io import load_subtitle_document, export_subtitle_document


def test_subtitle_timing_roundtrip():
    data = b'1\n00:00:01,000 --> 00:00:02,000\nHello\n\n'
    doc = load_subtitle_document('sample.srt', data)
    result = export_subtitle_document(doc, target_language='zh')
    assert b'00:00:01,000 --> 00:00:02,000' in result.content
    assert result.file_name == 'sample.zh.srt'

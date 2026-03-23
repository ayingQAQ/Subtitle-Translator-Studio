from subtitle_translator.subtitle_io import (
    SubtitleIOError,
    export_subtitle_document,
    load_subtitle_document,
    placeholders_are_preserved,
    protect_subtitle_text,
    restore_subtitle_text,
)


def test_load_srt_document_roundtrip_preserves_text_and_newline() -> None:
    payload = (
        "1\r\n"
        "00:00:01,000 --> 00:00:02,000\r\n"
        "<i>Hello</i> world\r\n"
        "\r\n"
    ).encode("utf-8-sig")

    document = load_subtitle_document("sample.srt", payload)
    exported = export_subtitle_document(document, target_language="zh")

    assert document.format == "srt"
    assert document.encoding == "utf-8-sig"
    assert document.newline == "\r\n"
    assert exported.content.decode(exported.encoding) == payload.decode("utf-8-sig")


def test_load_ass_document_preserves_override_tags() -> None:
    payload = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\i1}Hello{\\i0}\\Nworld\n"
    ).encode("utf-8")

    document = load_subtitle_document("sample.ass", payload)
    segment = document.segments[0]

    assert segment.style_tokens == ("{\\i1}", "{\\i0}", "\\N")
    assert segment.plain_text == "Hello\nworld"


def test_protect_and_restore_tags() -> None:
    raw = "{\\i1}<b>Hello</b>\\Nworld{\\i0}"
    protected, tokens = protect_subtitle_text(raw)

    assert placeholders_are_preserved(protected, len(tokens)) is True
    assert restore_subtitle_text(protected, tokens) == raw


def test_image_subtitles_are_rejected() -> None:
    try:
        load_subtitle_document("sample.sup", b"")
    except SubtitleIOError as exc:
        assert "Image-based subtitles" in str(exc)
    else:
        raise AssertionError("Expected image subtitle extension to be rejected.")

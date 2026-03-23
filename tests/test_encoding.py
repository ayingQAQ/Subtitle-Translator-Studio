from subtitle_translator.encoding import can_encode, decode_subtitle_bytes


def test_decode_utf8_sig_and_preserve_newline() -> None:
    data = "第一行\r\n第二行\r\n".encode("utf-8-sig")

    decoded = decode_subtitle_bytes(data)

    assert decoded.encoding == "utf-8-sig"
    assert decoded.newline == "\r\n"
    assert decoded.text.startswith("第一行")


def test_decode_cp932_japanese_text() -> None:
    data = "こんにちは\n世界\n".encode("cp932")

    decoded = decode_subtitle_bytes(data)

    assert "こんにちは" in decoded.text
    assert decoded.newline == "\n"


def test_utf8_fallback_for_unencodable_text() -> None:
    assert can_encode("plain ascii", "cp932") is True
    assert can_encode("简体中文 and 日本語", "ascii") is False

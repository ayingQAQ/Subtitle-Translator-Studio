from pathlib import Path

from subtitle_translator.memory import TranslationMemory
from subtitle_translator.models import GlossaryTerm
from subtitle_translator.subtitle_io import load_subtitle_document
from subtitle_translator.translator import TranslationService


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self) -> None:
        self.batch_calls: list[list[str]] = []

    def translate_batch(self, texts, *, source_language, target_language, glossary):
        self.batch_calls.append(list(texts))
        mapping = {
            "\u3053\u3093\u306b\u3061\u306f": "\u4f60\u597d",
            "world": "\u4e16\u754c",
            "Hello": "\u4f60\u597d",
            "[[[P0]]]Hello[[[P1]]] world": "\u4f60\u597d \u4e16\u754c",
            "Bye": "\u518d\u89c1",
            "\u59d0\u59d0": "sister",
        }
        return [mapping.get(text, f"{text}::{target_language}") for text in texts]


def test_translation_service_uses_memory_for_duplicate_lines(tmp_path: Path) -> None:
    payload = (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "\u3053\u3093\u306b\u3061\u306f\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "\u3053\u3093\u306b\u3061\u306f\n"
        "\n"
    ).encode("utf-8")
    document = load_subtitle_document("dup.srt", payload)
    provider = FakeProvider()

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        service = TranslationService(provider, memory, batch_size=10)
        translated = service.translate_document(
            document,
            source_language="ja",
            target_language="zh",
            glossary=[],
        )

    translated_lines = [segment.translated_text for segment in translated.segments if segment.is_translatable]
    assert translated_lines == ["\u4f60\u597d", "\u4f60\u597d"]
    assert len(provider.batch_calls) == 1


def test_placeholder_fallback_preserves_tags(tmp_path: Path) -> None:
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
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\i1}Hello{\\i0} world\n"
    ).encode("utf-8")
    document = load_subtitle_document("tagged.ass", payload)
    provider = FakeProvider()

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        service = TranslationService(provider, memory, batch_size=10)
        translated = service.translate_document(
            document,
            source_language="en",
            target_language="zh",
            glossary=[],
        )

    translated_event = translated.subtitles[0].text
    assert translated_event == "{\\i1}\u4f60\u597d{\\i0} \u4e16\u754c"
    assert translated.segments[0].translated_text == "\u4f60\u597d \u4e16\u754c"


def test_exact_glossary_match_short_circuits_simple_segment(tmp_path: Path) -> None:
    payload = (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "\u59d0\u59d0\n"
        "\n"
    ).encode("utf-8")
    document = load_subtitle_document("glossary.srt", payload)
    provider = FakeProvider()

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        service = TranslationService(provider, memory, batch_size=10)
        translated = service.translate_document(
            document,
            source_language="zh",
            target_language="en",
            glossary=[GlossaryTerm(source="\u59d0\u59d0", target="sister", notes="")],
        )

    assert translated.segments[0].translated_text == "sister"
    assert provider.batch_calls == []

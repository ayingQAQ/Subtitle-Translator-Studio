from __future__ import annotations

import re
from pathlib import Path

from pysubs2 import SSAFile
from pysubs2.exceptions import UnknownFPSError

from subtitle_translator.encoding import EncodingDetectionError, can_encode, decode_subtitle_bytes, normalize_newlines
from subtitle_translator.models import ExportedSubtitle, SubtitleDocument, SubtitleSegment


SUPPORTED_FORMATS = {
    ".ass": "ass",
    ".ssa": "ssa",
    ".srt": "srt",
    ".vtt": "vtt",
    ".sub": "microdvd",
    ".txt": "tmp",
    ".ttml": "ttml",
    ".smi": "sami",
    ".sami": "sami",
}

IMAGE_SUBTITLE_EXTENSIONS = {".sup", ".idx"}
PLACEHOLDER_PATTERN = re.compile(r"\[\[\[P(\d+)\]\]\]")
PROTECTED_TOKEN_PATTERN = re.compile(r"(\{\\[^}]*\}|\\[Nnh]|</?[^>]+?>)")


class SubtitleIOError(ValueError):
    """Raised when subtitle input cannot be loaded or exported."""


def resolve_format(file_name: str) -> str | None:
    return SUPPORTED_FORMATS.get(Path(file_name).suffix.lower())


def protect_subtitle_text(raw_text: str) -> tuple[str, tuple[str, ...]]:
    tokens: list[str] = []

    def replace(match: re.Match[str]) -> str:
        placeholder = f"[[[P{len(tokens)}]]]"
        tokens.append(match.group(0))
        return placeholder

    protected = PROTECTED_TOKEN_PATTERN.sub(replace, raw_text)
    return protected, tuple(tokens)


def restore_subtitle_text(protected_text: str, tokens: tuple[str, ...]) -> str:
    restored = protected_text
    for index, token in enumerate(tokens):
        restored = restored.replace(f"[[[P{index}]]]", token)
    return restored


def placeholders_are_preserved(candidate_text: str, token_count: int) -> bool:
    placeholders = [int(value) for value in PLACEHOLDER_PATTERN.findall(candidate_text)]
    return placeholders == list(range(token_count))


def load_subtitle_document(file_name: str, data: bytes, encoding: str | None = None) -> SubtitleDocument:
    extension = Path(file_name).suffix.lower()
    if extension in IMAGE_SUBTITLE_EXTENSIONS:
        raise SubtitleIOError("Image-based subtitles are not supported in this MVP.")

    format_identifier = resolve_format(file_name)
    if format_identifier is None:
        raise SubtitleIOError(f"Unsupported subtitle file extension: {extension or '<none>'}")

    try:
        decoded = decode_subtitle_bytes(data, encoding)
    except EncodingDetectionError as exc:
        raise SubtitleIOError(str(exc)) from exc
    parser_kwargs = {}
    if format_identifier in {"srt", "vtt"}:
        parser_kwargs.update(keep_html_tags=True, keep_unknown_html_tags=True)

    try:
        subtitles = SSAFile.from_string(decoded.text, format_=format_identifier, **parser_kwargs)
    except UnknownFPSError as exc:
        raise SubtitleIOError("This MicroDVD file needs FPS metadata before it can be translated.") from exc
    except Exception as exc:  # noqa: BLE001
        raise SubtitleIOError(f"Failed to parse subtitle file as {format_identifier}.") from exc

    actual_format = subtitles.format or format_identifier
    fps = getattr(subtitles, "fps", None)
    segments: list[SubtitleSegment] = []
    warnings: list[str] = []

    for index, event in enumerate(subtitles):
        protected_text, style_tokens = protect_subtitle_text(event.text)
        plain_text = event.plaintext
        is_translatable = bool(plain_text.strip()) and not event.is_comment and not event.is_drawing
        segments.append(
            SubtitleSegment(
                index=index,
                start_ms=event.start,
                end_ms=event.end,
                raw_text=event.text,
                plain_text=plain_text,
                translatable_text=protected_text,
                style_tokens=style_tokens,
                is_translatable=is_translatable,
            )
        )

    if actual_format in {"microdvd", "tmp", "mpl2", "ttml", "sami"}:
        warnings.append(f"{actual_format} support is best effort in this MVP.")

    return SubtitleDocument(
        file_name=file_name,
        original_extension=extension,
        format=actual_format,
        encoding=decoded.encoding,
        newline=decoded.newline,
        fps=fps,
        subtitles=subtitles,
        segments=segments,
        warnings=warnings,
    )


def apply_translated_segments(document: SubtitleDocument, translated_protected_texts: dict[int, str]) -> None:
    for segment in document.segments:
        if segment.index not in translated_protected_texts:
            continue

        translated_protected = translated_protected_texts[segment.index]
        restored_text = restore_subtitle_text(translated_protected, segment.style_tokens)
        subtitle_event = document.subtitles[segment.index]
        subtitle_event.text = restored_text

        segment.translated_raw_text = restored_text
        segment.translated_text = subtitle_event.plaintext


def build_output_file_name(original_file_name: str, target_language: str) -> str:
    path = Path(original_file_name)
    suffix = path.suffix
    return f"{path.stem}.{target_language}{suffix}"


def export_subtitle_document(document: SubtitleDocument, *, target_language: str) -> ExportedSubtitle:
    save_kwargs = {}
    if document.format == "srt":
        save_kwargs["keep_ssa_tags"] = True

    rendered = document.subtitles.to_string(format_=document.format, fps=document.fps, **save_kwargs)
    rendered = normalize_newlines(rendered, document.newline)

    export_encoding = document.encoding if can_encode(rendered, document.encoding) else "utf-8-sig"

    return ExportedSubtitle(
        file_name=build_output_file_name(document.file_name, target_language),
        content=rendered.encode(export_encoding),
        encoding=export_encoding,
        metadata={"format": document.format},
    )


def format_timestamp(ms: int) -> str:
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

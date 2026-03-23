from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pysubs2 import SSAFile


@dataclass(slots=True)
class GlossaryTerm:
    source: str
    target: str
    notes: str = ""


@dataclass(slots=True)
class TranslationMemoryEntry:
    source_text: str
    source_language: str
    target_language: str
    translated_text: str
    provider: str
    model: str


@dataclass(slots=True)
class SubtitleSegment:
    index: int
    start_ms: int
    end_ms: int
    raw_text: str
    plain_text: str
    translatable_text: str
    style_tokens: tuple[str, ...] = ()
    translated_text: str | None = None
    translated_raw_text: str | None = None
    is_translatable: bool = True


@dataclass(slots=True)
class SubtitleDocument:
    file_name: str
    original_extension: str
    format: str
    encoding: str
    newline: str
    fps: float | None
    subtitles: SSAFile
    segments: list[SubtitleSegment]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExportedSubtitle:
    file_name: str
    content: bytes
    encoding: str
    metadata: dict[str, Any] = field(default_factory=dict)

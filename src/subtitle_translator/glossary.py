from __future__ import annotations

import csv
from io import StringIO

from subtitle_translator.encoding import decode_subtitle_bytes
from subtitle_translator.models import GlossaryTerm


class GlossaryFormatError(ValueError):
    """Raised when glossary CSV cannot be parsed."""


def parse_glossary_csv(data: bytes) -> list[GlossaryTerm]:
    if not data:
        return []

    decoded = decode_subtitle_bytes(data)
    reader = csv.DictReader(StringIO(decoded.text))
    expected_headers = {"source", "target", "notes"}

    if reader.fieldnames is None:
        raise GlossaryFormatError("Glossary CSV is empty.")

    normalized_headers = {header.strip() for header in reader.fieldnames if header}
    if not expected_headers.issubset(normalized_headers):
        raise GlossaryFormatError("Glossary CSV must include source,target,notes headers.")

    terms: list[GlossaryTerm] = []
    for row in reader:
        source = (row.get("source") or "").strip()
        target = (row.get("target") or "").strip()
        notes = (row.get("notes") or "").strip()
        if source and target:
            terms.append(GlossaryTerm(source=source, target=target, notes=notes))

    return terms


def select_relevant_glossary_terms(glossary: list[GlossaryTerm], texts: list[str], limit: int = 50) -> list[GlossaryTerm]:
    if not glossary:
        return []

    lowered_texts = [text.lower() for text in texts]
    selected: list[GlossaryTerm] = []
    for term in glossary:
        source_lower = term.source.lower()
        if any(source_lower in text for text in lowered_texts):
            selected.append(term)
        if len(selected) >= limit:
            break

    return selected


def find_exact_glossary_match(text: str, glossary: list[GlossaryTerm]) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    for term in glossary:
        if normalized == term.source.strip():
            return term.target

    return None

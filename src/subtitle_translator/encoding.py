from __future__ import annotations

import codecs
import unicodedata
from dataclasses import dataclass

from charset_normalizer import from_bytes


UTF8_BOM = codecs.BOM_UTF8
UTF16_LE_BOM = codecs.BOM_UTF16_LE
UTF16_BE_BOM = codecs.BOM_UTF16_BE

TEXT_FIRST_ENCODINGS = ("utf-8", "gb18030", "big5", "cp932")


@dataclass(slots=True)
class DecodedText:
    text: str
    encoding: str
    newline: str


class EncodingDetectionError(ValueError):
    """Raised when subtitle bytes cannot be decoded safely."""


def detect_newline(data: bytes) -> str:
    if b"\r\n" in data:
        return "\r\n"
    if b"\r" in data:
        return "\r"
    return "\n"


def detect_bom_encoding(data: bytes) -> str | None:
    if data.startswith(UTF8_BOM):
        return "utf-8-sig"
    if data.startswith(UTF16_LE_BOM) or data.startswith(UTF16_BE_BOM):
        return "utf-16"
    return None


def _normalize_encoding_name(name: str) -> str:
    return codecs.lookup(name).name


def _iter_encoding_candidates(data: bytes) -> list[str]:
    candidates: list[str] = []
    bom_encoding = detect_bom_encoding(data)
    has_null_bytes = b"\x00" in data
    if bom_encoding:
        candidates.append(bom_encoding)

    best_guess = from_bytes(data).best()
    if best_guess and best_guess.encoding:
        guessed = _normalize_encoding_name(best_guess.encoding)
        if bom_encoding or not guessed.startswith("utf-16") or has_null_bytes:
            candidates.append(guessed)

    candidates.extend(TEXT_FIRST_ENCODINGS)
    candidates.append("utf-16")

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            canonical = _normalize_encoding_name(candidate)
        except LookupError:
            continue

        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)

    return normalized


def decode_subtitle_bytes(data: bytes) -> DecodedText:
    newline = detect_newline(data)
    bom_encoding = detect_bom_encoding(data)
    has_null_bytes = b"\x00" in data

    if not data:
        return DecodedText(text="", encoding="utf-8", newline=newline)

    best_decoded: DecodedText | None = None
    best_score = float("-inf")
    last_error: UnicodeDecodeError | None = None
    for encoding in _iter_encoding_candidates(data):
        try:
            decoded_text = data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        score = _score_decoded_text(
            decoded_text,
            encoding=encoding,
            has_bom=bool(bom_encoding),
            has_null_bytes=has_null_bytes,
        )
        if score > best_score:
            best_score = score
            best_decoded = DecodedText(text=decoded_text, encoding=encoding, newline=newline)

    if best_decoded is not None:
        return best_decoded

    raise EncodingDetectionError("Unable to decode subtitle file with supported encodings.") from last_error


def can_encode(text: str, encoding: str) -> bool:
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    return True


def normalize_newlines(text: str, newline: str) -> str:
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return canonical.replace("\n", newline)


def _score_decoded_text(text: str, *, encoding: str, has_bom: bool, has_null_bytes: bool) -> int:
    score = 0
    kana_count = 0
    control_count = 0
    replacement_count = text.count("\ufffd")

    for char in text:
        if char in "\r\n\t":
            score += 1
            continue

        category = unicodedata.category(char)
        if category.startswith("C"):
            control_count += 1
        else:
            score += 2

        codepoint = ord(char)
        if 0x3040 <= codepoint <= 0x30FF:
            kana_count += 1

    score -= control_count * 10
    score -= replacement_count * 20

    if encoding in {"utf-8", "utf-8-sig"}:
        score += 30
    if encoding == "cp932":
        score += kana_count * 6
    if encoding in {"gb18030", "big5"}:
        score -= kana_count * 2
    if encoding.startswith("utf-16") and not has_bom and not has_null_bytes:
        score -= 50

    return score

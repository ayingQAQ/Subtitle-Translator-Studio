from __future__ import annotations

import sqlite3
from pathlib import Path

from subtitle_translator.models import TranslationMemoryEntry


class TranslationMemory:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._connection = sqlite3.connect(db_path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_text TEXT NOT NULL,
                source_language TEXT NOT NULL,
                target_language TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_text, source_language, target_language, provider, model)
            )
            """
        )
        self._connection.commit()

    def get(
        self,
        *,
        source_text: str,
        source_language: str,
        target_language: str,
        provider: str,
        model: str,
    ) -> str | None:
        row = self._connection.execute(
            """
            SELECT translated_text
            FROM translation_memory
            WHERE source_text = ?
              AND source_language = ?
              AND target_language = ?
              AND provider = ?
              AND model = ?
            """,
            (source_text, source_language, target_language, provider, model),
        ).fetchone()
        return None if row is None else str(row["translated_text"])

    def upsert(self, entry: TranslationMemoryEntry) -> None:
        self._connection.execute(
            """
            INSERT INTO translation_memory (
                source_text,
                source_language,
                target_language,
                translated_text,
                provider,
                model
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_text, source_language, target_language, provider, model)
            DO UPDATE SET translated_text = excluded.translated_text
            """,
            (
                entry.source_text,
                entry.source_language,
                entry.target_language,
                entry.translated_text,
                entry.provider,
                entry.model,
            ),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "TranslationMemory":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

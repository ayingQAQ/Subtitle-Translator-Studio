from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AppConfig:
    env: dict[str, str]
    db_path: Path
    batch_size: int
    max_file_size_bytes: int
    request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        db_path = Path(os.getenv("APP_DB_PATH", ".data/translation_memory.sqlite3"))

        return cls(
            env={key: value.strip() for key, value in os.environ.items()},
            db_path=db_path,
            batch_size=max(1, int(os.getenv("APP_BATCH_SIZE", "20"))),
            max_file_size_bytes=max(1, int(os.getenv("APP_MAX_FILE_SIZE_MB", "5"))) * 1024 * 1024,
            request_timeout_seconds=max(5.0, float(os.getenv("APP_REQUEST_TIMEOUT_SECONDS", "60"))),
        )

    def ensure_runtime_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: str = "") -> str:
        return self.env.get(key, default).strip()

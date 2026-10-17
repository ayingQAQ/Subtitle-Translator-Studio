from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AppConfig:
    env: dict[str, str]
    db_path: Path
    secret_store_path: Path
    secret_key_path: Path
    batch_size: int
    max_file_size_bytes: int
    request_timeout_seconds: float
    max_batch_chars: int = 6000

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        db_path = Path(os.getenv("APP_DB_PATH", ".data/translation_memory.sqlite3"))
        secret_store_path = Path(os.getenv("APP_SECRET_STORE_PATH", ".data/secret_store.enc"))
        secret_key_path = Path(os.getenv("APP_SECRET_KEY_PATH", ".data/secret_store.key"))

        return cls(
            env={key: value.strip() for key, value in os.environ.items()},
            db_path=db_path,
            secret_store_path=secret_store_path,
            secret_key_path=secret_key_path,
            batch_size=max(1, int(os.getenv("APP_BATCH_SIZE", "20"))),
            max_file_size_bytes=max(1, int(os.getenv("APP_MAX_FILE_SIZE_MB", "5"))) * 1024 * 1024,
            request_timeout_seconds=max(5.0, float(os.getenv("APP_REQUEST_TIMEOUT_SECONDS", "60"))),
            max_batch_chars=max(100, int(os.getenv('APP_MAX_BATCH_CHARS', '6000'))),
        )

    def ensure_runtime_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret_key_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: str = "") -> str:
        return self.env.get(key, default).strip()

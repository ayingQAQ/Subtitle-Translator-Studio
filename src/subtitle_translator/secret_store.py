from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class SecretStoreError(RuntimeError):
    """Raised when encrypted credential store cannot be read or written."""


@dataclass(slots=True)
class SecretStore:
    encrypted_path: Path
    key_path: Path
    _fernet: Fernet | None = field(default=None, init=False, repr=False)
    _cache: dict[str, str] | None = field(default=None, init=False, repr=False)

    def get(self, key: str) -> str:
        data = self._load_all()
        return data.get(key, "")

    def set(self, key: str, value: str) -> None:
        data = self._load_all()
        data[key] = value
        self._save_all(data)

    def delete(self, key: str) -> None:
        data = self._load_all()
        if key in data:
            data.pop(key, None)
            self._save_all(data)

    def _load_all(self) -> dict[str, str]:
        if self._cache is not None:
            return dict(self._cache)

        if not self.encrypted_path.exists():
            self._cache = {}
            return {}

        encrypted_bytes = self.encrypted_path.read_bytes()
        if not encrypted_bytes:
            self._cache = {}
            return {}

        try:
            payload = self._get_fernet().decrypt(encrypted_bytes)
        except InvalidToken as exc:
            raise SecretStoreError("Encrypted API key storage cannot be decrypted.") from exc

        try:
            loaded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecretStoreError("Encrypted API key storage payload is invalid.") from exc

        if not isinstance(loaded, dict):
            raise SecretStoreError("Encrypted API key storage must contain a JSON object.")

        clean: dict[str, str] = {}
        for item_key, item_value in loaded.items():
            if isinstance(item_key, str) and isinstance(item_value, str):
                clean[item_key] = item_value

        self._cache = clean
        return dict(clean)

    def _save_all(self, data: dict[str, str]) -> None:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        encrypted = self._get_fernet().encrypt(payload)
        self.encrypted_path.write_bytes(encrypted)
        self._cache = dict(data)

    def _get_fernet(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet

        key = self._load_or_create_key()
        self._fernet = Fernet(key)
        return self._fernet

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
            self._validate_key(key)
            return key

        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        return key

    def _validate_key(self, key: bytes) -> None:
        try:
            Fernet(key)
        except Exception as exc:
            raise SecretStoreError("API key encryption key is invalid.") from exc


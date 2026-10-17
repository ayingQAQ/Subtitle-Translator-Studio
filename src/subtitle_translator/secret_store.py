from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


DPAPI_PREFIX = b'DPAPI1:'


def _windows_protect(data: bytes, *, decrypt: bool = False) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise SecretStoreError('Windows credential protection failed for the current user.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def _atomic_write(path: Path, data: bytes) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        if os.name != 'nt':
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class SecretStoreError(RuntimeError):
    """Raised when encrypted credential store cannot be read or written."""


@dataclass(slots=True)
class SecretStore:
    encrypted_path: Path
    key_path: Path
    _fernet: Fernet | None = field(default=None, init=False, repr=False)
    _cache: dict[str, str] | None = field(default=None, init=False, repr=False)

    def get(self, key: str) -> str:
        try:
            data = self._load_all()
        except OSError as exc:
            raise SecretStoreError('Cannot read encrypted credentials.') from exc
        return data.get(key, "")

    def set(self, key: str, value: str) -> None:
        try:
            data = self._load_all()
            data[key] = value
            self._save_all(data)
        except OSError as exc:
            raise SecretStoreError('Cannot save encrypted credentials.') from exc

    def delete(self, key: str) -> None:
        try:
            data = self._load_all()
            if key in data:
                data.pop(key, None)
                self._save_all(data)
        except OSError as exc:
            raise SecretStoreError('Cannot remove encrypted credentials.') from exc

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
        _atomic_write(self.encrypted_path, encrypted)
        self._cache = dict(data)

    def _get_fernet(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet

        key = self._load_or_create_key()
        self._fernet = Fernet(key)
        return self._fernet

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            stored = self.key_path.read_bytes()
            if stored.startswith(DPAPI_PREFIX):
                if os.name != 'nt':
                    raise SecretStoreError('This key is protected by Windows. Open it under the original Windows account.')
                key = _windows_protect(stored[len(DPAPI_PREFIX):], decrypt=True)
            else:
                key = stored.strip()
            self._validate_key(key)
            if os.name == 'nt' and not stored.startswith(DPAPI_PREFIX):
                _atomic_write(self.key_path, DPAPI_PREFIX + _windows_protect(key))
            return key

        if self.encrypted_path.exists() and self.encrypted_path.stat().st_size:
            raise SecretStoreError('Encryption key is missing. Restore it from backup before opening credentials.')
        key = Fernet.generate_key()
        stored = DPAPI_PREFIX + _windows_protect(key) if os.name == 'nt' else key
        _atomic_write(self.key_path, stored)
        return key

    def _validate_key(self, key: bytes) -> None:
        try:
            Fernet(key)
        except Exception as exc:
            raise SecretStoreError("API key encryption key is invalid.") from exc


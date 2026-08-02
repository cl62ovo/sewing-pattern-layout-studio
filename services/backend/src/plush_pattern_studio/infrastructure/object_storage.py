from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class StoredObject:
    key: str
    byte_size: int
    sha256: str


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Object key must be a safe relative POSIX path.")
        path = self.root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Object key escapes the storage root.")
        return path

    def put_bytes(self, key: str, payload: bytes) -> StoredObject:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(payload)
            Path(temporary_name).replace(destination)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return StoredObject(
            key=key,
            byte_size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def path_for(self, key: str) -> Path:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def health_check(self) -> None:
        key = ".health/storage-probe"
        payload = b"plush-pattern-studio"
        self.put_bytes(key, payload)
        try:
            if self.read_bytes(key) != payload:
                raise OSError("Object storage probe content did not round-trip.")
        finally:
            self.delete(key)

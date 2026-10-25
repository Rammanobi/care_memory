"""Storage port for original uploaded files. LocalStorage writes under UPLOAD_DIR (default data/uploads)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from cm.core.config import REPO_ROOT

_SCHEME = "local://"
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StorageError(Exception):
    """Any storage failure (bad key, I/O)."""


class StoragePort(Protocol):
    def put(self, key: str, data: bytes) -> str: ...
    def get(self, uri: str) -> bytes: ...
    def exists(self, uri: str) -> bool: ...


class LocalStorage:
    """Content-addressed files: key = <patient_token>/<sha256>. Traversal-safe, atomic writes."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root or os.environ.get("UPLOAD_DIR") or REPO_ROOT / "data" / "uploads").resolve()

    def _path(self, key: str) -> Path:
        parts = key.split("/")
        if not 1 <= len(parts) <= 3 or not all(
            _SEGMENT.fullmatch(p) and ".." not in p for p in parts
        ):
            raise StorageError("invalid storage key")
        path = self.root.joinpath(*parts).resolve()
        if self.root not in path.parents:
            raise StorageError("invalid storage key")
        return path

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        tmp = ""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except OSError as exc:
            raise StorageError("could not write file") from exc
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
        return _SCHEME + key

    @staticmethod
    def _key(uri: str) -> str:
        if not uri.startswith(_SCHEME):
            raise StorageError("unknown storage uri")
        return uri[len(_SCHEME) :]

    def get(self, uri: str) -> bytes:
        try:
            return self._path(self._key(uri)).read_bytes()
        except OSError as exc:
            raise StorageError("could not read file") from exc

    def exists(self, uri: str) -> bool:
        try:
            return self._path(self._key(uri)).is_file()
        except StorageError:
            return False


def get_storage() -> StoragePort:
    return LocalStorage()

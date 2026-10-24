"""Lane A: structured logging helper (key=value kwargs, never PII)."""

from __future__ import annotations

import logging as _logging
from typing import Any


class _Log:
    def __init__(self, name: str) -> None:
        self._log = _logging.getLogger(name)

    def _emit(self, level: int, msg: str, **kw: Any) -> None:
        extra = " ".join(f"{k}={v}" for k, v in kw.items())
        self._log.log(level, "%s %s", msg, extra)

    def info(self, msg: str, **kw: Any) -> None:
        self._emit(_logging.INFO, msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._emit(_logging.WARNING, msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._emit(_logging.ERROR, msg, **kw)


def get_logger(name: str = "cm") -> _Log:
    return _Log(name)

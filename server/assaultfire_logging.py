#!/usr/bin/env python3
"""Small thread-safe logger for the Assault Fire emulator.

Console verbosity is user-selectable. The development log always keeps DEBUG+
records so a quiet console never destroys diagnostic evidence.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
}
DEFAULT_CONSOLE_LEVEL = "INFO"
FILE_CAPTURE_LEVEL = "DEBUG"

_LOCK = threading.RLock()


def _normalize_level(value: str | None, *, default: str = "INFO") -> str:
    name = str(value or default).strip().upper()
    if name == "WARN":
        name = "WARNING"
    if name not in LEVELS:
        valid = ", ".join(LEVELS)
        raise ValueError(f"invalid log level {value!r}; expected one of: {valid}")
    return name


def console_level(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return _normalize_level(
        env.get("AF_LOG_LEVEL") or env.get("AF_CONSOLE_LOG_LEVEL"),
        default=DEFAULT_CONSOLE_LEVEL,
    )


def default_log_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = (env.get("AF_LOG_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().with_name("af_server_live.log")


def infer_level(label: str, message: str) -> str:
    label_u = str(label or "").upper()
    msg_u = str(message or "").lstrip().upper()

    if label_u.endswith("-DEBUG") or label_u == "DEBUG":
        return "DEBUG"
    if msg_u.startswith(("ERROR:", "FAILED:", "FAIL:", "FATAL:")):
        return "ERROR"
    if msg_u.startswith(("WARNING:", "WARN:")):
        return "WARNING"
    return "INFO"


class AFLogger:
    def __init__(
        self,
        *,
        console_level_name: str | None = None,
        path: Path | None = None,
        env: dict[str, str] | None = None,
    ):
        self._env = os.environ if env is None else env
        self.console_level_name = _normalize_level(
            console_level_name or console_level(self._env),
            default=DEFAULT_CONSOLE_LEVEL,
        )
        self.path = (
            Path(path).expanduser().resolve()
            if path is not None
            else default_log_path(self._env)
        )
        self._file_error_reported = False

    def should_print(self, level: str) -> bool:
        level = _normalize_level(level)
        return LEVELS[level] >= LEVELS[self.console_level_name]

    def format_line(self, label: str, message: str, level: str) -> str:
        level = _normalize_level(level)
        return (
            f"[{time.strftime('%H:%M:%S')}] "
            f"[{level}] [{label}] {message}"
        )

    def emit(
        self,
        label: str,
        message: str,
        *,
        level: str | None = None,
    ) -> str:
        level_name = _normalize_level(
            level or infer_level(label, message),
            default="INFO",
        )
        line = self.format_line(label, message, level_name)

        # File capture is intentionally independent from the console threshold.
        # Since FILE_CAPTURE_LEVEL is DEBUG, every normal logger call is kept.
        with _LOCK:
            if LEVELS[level_name] >= LEVELS[FILE_CAPTURE_LEVEL]:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as fp:
                        fp.write(line + "\n")
                except OSError as exc:
                    if not self._file_error_reported:
                        self._file_error_reported = True
                        print(
                            f"[LOGGER] WARNING: could not write debug log "
                            f"{self.path}: {exc}",
                            flush=True,
                        )

            if self.should_print(level_name):
                print(line, flush=True)

        return line


def build_logger(
    *,
    console_level_name: str | None = None,
    path: Path | None = None,
    env: dict[str, str] | None = None,
) -> AFLogger:
    return AFLogger(
        console_level_name=console_level_name,
        path=path,
        env=env,
    )

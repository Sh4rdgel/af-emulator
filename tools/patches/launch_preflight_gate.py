#!/usr/bin/env python3
"""Shared launch gate for Assault Fire PH compatibility helpers."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Callable, Mapping

PREFLIGHT_STATUS_SCHEMA = 1
REQUIRED_CHECKS = (
    "client_root",
    "tcls_validated_build",
    "apclient_exact_bytes",
    "same_rsa_key",
    "rsa_1024",
    "apclient_272_bytes",
    "hosts",
)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


class LaunchGateError(RuntimeError):
    pass


def default_status_path() -> Path:
    override = (os.environ.get("AF_PREFLIGHT_STATUS_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "runtime" / "preflight_status.json"


def load_status(path: Path | None = None) -> tuple[dict, Path]:
    target = (
        Path(path).expanduser().resolve()
        if path is not None
        else default_status_path()
    )
    if not target.is_file():
        raise LaunchGateError(
            "server preflight status is missing. Start "
            "server/assaultfire_server_v143b.py first and fix every "
            "[PREFLIGHT] failure before launching the game. "
            f"Expected status: {target}"
        )
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LaunchGateError(
            f"server preflight status is unreadable: {target}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise LaunchGateError(f"invalid server preflight status format: {target}")
    return data, target


def _windows_pid_alive(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_uint32(0)
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return int(code.value) == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def default_pid_alive(pid: int) -> bool:
    if int(pid) <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(int(pid))
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def validate_status(
    data: Mapping,
    *,
    pid_alive: Callable[[int], bool] = default_pid_alive,
) -> list[str]:
    errors: list[str] = []

    if data.get("schema") != PREFLIGHT_STATUS_SCHEMA:
        errors.append(
            f"unsupported preflight status schema {data.get('schema')!r}; "
            f"expected {PREFLIGHT_STATUS_SCHEMA}"
        )

    checks = data.get("checks")
    if not isinstance(checks, Mapping):
        checks = {}
        errors.append("preflight status has no checks map")

    failed = [name for name in REQUIRED_CHECKS if checks.get(name) is not True]
    if failed:
        errors.append("required checks are not PASS: " + ", ".join(failed))

    if data.get("passed") is not True:
        errors.append("server preflight result is FAILED")

    server_pid = data.get("server_pid")
    try:
        server_pid = int(server_pid)
    except (TypeError, ValueError):
        server_pid = 0
    if not server_pid or not pid_alive(server_pid):
        errors.append(
            f"server process from preflight is not running (PID={server_pid or 'missing'})"
        )

    if not data.get("client_root"):
        errors.append("preflight client root is missing")
    if not data.get("tcls_path"):
        errors.append("preflight TCLS path is missing")

    for item in data.get("errors") or []:
        msg = str(item).strip()
        if msg and msg not in errors:
            errors.append(msg)

    return errors


def require_launch_ready(
    path: Path | None = None,
    *,
    pid_alive: Callable[[int], bool] = default_pid_alive,
) -> dict:
    data, target = load_status(path)
    errors = validate_status(data, pid_alive=pid_alive)
    if errors:
        detail = "\n".join(f"  - {item}" for item in errors)
        raise LaunchGateError(
            "GAME LAUNCH BLOCKED: server preflight has not passed.\n"
            f"Status: {target}\n"
            f"{detail}\n"
            "Start/restart the server and do not continue until every "
            "[PREFLIGHT] line is YES and 'game launch gate : UNLOCKED'."
        )
    return data


def _normalized_windows_path(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def require_loaded_tcls_matches(status: Mapping, loaded_tcls_path: str) -> None:
    expected = status.get("tcls_path")
    if not expected:
        raise LaunchGateError("GAME LAUNCH BLOCKED: preflight TCLS path is missing")
    if _normalized_windows_path(str(expected)) != _normalized_windows_path(loaded_tcls_path):
        raise LaunchGateError(
            "GAME LAUNCH BLOCKED: client.exe loaded a different TCLS.dll than "
            "the one that passed server preflight.\n"
            f"  preflight: {expected}\n"
            f"  loaded   : {loaded_tcls_path}\n"
            "Set AF_CLIENT_ROOT to the client you are actually launching, "
            "restart the server, and wait for preflight PASS."
        )

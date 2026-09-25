#!/usr/bin/env python3
"""Strict startup preflight for the supported Assault Fire PH local setup."""
from __future__ import annotations

import hashlib
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from cryptography.hazmat.primitives import serialization

VALIDATED_TCLS_SHA256 = "3ff351e0adb594d7544e28db2e966a6d6eb548e9df70daaf4daf58f2ee438d56"
ORIGINAL_TCLS_SHA256 = "13ead403452e0f25cf00658369bf4bf5ff34ed1b16027f7833fb27d398386cd1"

REQUIRED_HOSTS = (
    "tversion.levelupgames.ph",
    "tauthproxy.levelupgames.ph",
    "tdir.levelupgames.ph",
)
LOOPBACK_IPV4 = "127.0.0.1"


@dataclass(frozen=True)
class KeyCheck:
    apclient_sha256: str
    derived_public_sha256: str
    exact_bytes_match: bool
    same_rsa_key: bool
    apclient_length: int
    rsa_key_size: int | None


@dataclass
class PreflightReport:
    client_root: Path | None = None
    tcls_path: Path | None = None
    apclient_path: Path | None = None
    private_key_path: Path | None = None
    tcls_sha256: str | None = None
    tcls_class: str = "unavailable"
    key_check: KeyCheck | None = None
    host_file_path: Path | None = None
    host_file_values: dict[str, list[str]] = field(default_factory=dict)
    host_resolved_values: dict[str, str | None] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_tcls_hash(sha256_hex: str) -> str:
    value = sha256_hex.lower()
    if value == VALIDATED_TCLS_SHA256:
        return "validated-raw-pem-patched"
    if value == ORIGINAL_TCLS_SHA256:
        return "original-needs-raw-pem-patch"
    return "unknown"


def derive_public_pem(private_key_path: Path) -> tuple[bytes, int | None]:
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    public_key = private_key.public_key()
    return (
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        getattr(public_key, "key_size", None),
    )


def public_key_numbers(pem: bytes):
    key = serialization.load_pem_public_key(pem)
    public_numbers = getattr(key, "public_numbers", None)
    if public_numbers is None:
        raise ValueError("PEM does not contain a supported public key")
    nums = public_numbers()
    return (getattr(nums, "n", None), getattr(nums, "e", None))


def check_key_pair(private_key_path: Path, apclient_path: Path) -> KeyCheck:
    apclient = apclient_path.read_bytes()
    derived, key_size = derive_public_pem(private_key_path)
    try:
        same_rsa_key = public_key_numbers(apclient) == public_key_numbers(derived)
    except (ValueError, TypeError):
        same_rsa_key = False
    return KeyCheck(
        apclient_sha256=hashlib.sha256(apclient).hexdigest(),
        derived_public_sha256=hashlib.sha256(derived).hexdigest(),
        exact_bytes_match=(apclient == derived),
        same_rsa_key=same_rsa_key,
        apclient_length=len(apclient),
        rsa_key_size=key_size,
    )


def resolve_client_root(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env

    explicit = (env.get("AF_CLIENT_ROOT") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    game_dir = (env.get("AF_GAME_DIR") or "").strip()
    if game_dir:
        path = Path(game_dir).expanduser().resolve()
        if path.name.lower() == "win32" and path.parent.name.lower() == "binaries":
            return path.parent.parent

    raise ValueError(
        'client root is unknown; set AF_CLIENT_ROOT to the Assault Fire PH root '
        '(example: $env:AF_CLIENT_ROOT = "D:\\AssaultFirePH"). '
        "For PvE, AF_GAME_DIR=...\\Binaries\\Win32 can also supply it."
    )


def default_hosts_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    system_root = (env.get("SystemRoot") or env.get("WINDIR") or "").strip()
    if not system_root:
        raise ValueError("SystemRoot/WINDIR is unavailable; cannot locate the Windows hosts file")
    return Path(system_root) / "System32" / "drivers" / "etc" / "hosts"


def parse_hosts_file(path: Path) -> dict[str, list[str]]:
    found = {name: [] for name in REQUIRED_HOSTS}
    text = path.read_text(encoding="utf-8", errors="replace")

    for raw_line in text.splitlines():
        content = raw_line.split("#", 1)[0].strip()
        if not content:
            continue
        parts = content.split()
        if len(parts) < 2:
            continue

        address = parts[0]
        names = {name.lower() for name in parts[1:]}
        for required in REQUIRED_HOSTS:
            if required in names:
                found[required].append(address)

    return found


def evaluate_preflight(
    *,
    private_key_path: Path,
    client_root: Path | None = None,
    hosts_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    resolver: Callable[[str], str] = socket.gethostbyname,
    validated_tcls_sha256: str = VALIDATED_TCLS_SHA256,
) -> PreflightReport:
    report = PreflightReport(private_key_path=Path(private_key_path).expanduser().resolve())

    try:
        report.client_root = (
            Path(client_root).expanduser().resolve()
            if client_root is not None
            else resolve_client_root(env)
        )
    except Exception as exc:
        report.errors.append(str(exc))
        return report

    report.tcls_path = report.client_root / "TCLS" / "Tenio" / "TCLS.dll"
    report.apclient_path = report.client_root / "TCLS" / "config" / "APClient.dat"

    for label, path in (
        ("TCLS.dll", report.tcls_path),
        ("APClient.dat", report.apclient_path),
        ("PRIVATE.PEM", report.private_key_path),
    ):
        if not path.is_file():
            report.errors.append(f"{label} not found: {path}")

    if report.tcls_path.is_file():
        try:
            report.tcls_sha256 = sha256_file(report.tcls_path)
            if report.tcls_sha256.lower() == validated_tcls_sha256.lower():
                report.tcls_class = "validated-raw-pem-patched"
            else:
                report.tcls_class = classify_tcls_hash(report.tcls_sha256)
                if report.tcls_class == "original-needs-raw-pem-patch":
                    report.errors.append(
                        "TCLS.dll is the verified original/pre-patch build; "
                        "apply tools/patches/patch_tcls_apclient_raw_pem.py first"
                    )
                else:
                    report.errors.append(
                        "TCLS.dll is not the validated raw-PEM-compatible PH build "
                        f"(SHA256={report.tcls_sha256.upper()})"
                    )
        except Exception as exc:
            report.errors.append(f"could not hash TCLS.dll: {exc}")

    if report.apclient_path.is_file() and report.private_key_path.is_file():
        try:
            report.key_check = check_key_pair(
                report.private_key_path, report.apclient_path
            )
            if not report.key_check.exact_bytes_match:
                report.errors.append(
                    "APClient.dat exact byte match is NO; regenerate/install the matching public key"
                )
            if not report.key_check.same_rsa_key:
                report.errors.append(
                    "APClient.dat and PRIVATE.PEM same RSA key is NO"
                )
            if report.key_check.rsa_key_size != 1024:
                report.errors.append(
                    f"RSA key size is {report.key_check.rsa_key_size!r}, expected 1024 bits"
                )
            if report.key_check.apclient_length != 272:
                report.errors.append(
                    f"APClient.dat is {report.key_check.apclient_length} bytes, expected 272"
                )
        except Exception as exc:
            report.errors.append(f"could not parse/compare RSA material: {exc}")

    try:
        report.host_file_path = (
            Path(hosts_path).expanduser().resolve()
            if hosts_path is not None
            else default_hosts_path(env)
        )
        report.host_file_values = parse_hosts_file(report.host_file_path)
    except Exception as exc:
        report.errors.append(f"could not read Windows hosts file: {exc}")
        report.host_file_values = {name: [] for name in REQUIRED_HOSTS}

    for name in REQUIRED_HOSTS:
        values = report.host_file_values.get(name, [])
        if values != [LOOPBACK_IPV4]:
            if not values:
                report.errors.append(
                    f"hosts entry missing: {LOOPBACK_IPV4} {name}"
                )
            else:
                report.errors.append(
                    f"hosts entry for {name} must be exactly {LOOPBACK_IPV4}; found {values}"
                )

        try:
            resolved = resolver(name)
        except Exception:
            resolved = None
        report.host_resolved_values[name] = resolved
        if resolved != LOOPBACK_IPV4:
            report.errors.append(
                f"{name} resolves to {resolved!r}, expected {LOOPBACK_IPV4}"
            )

    return report


def print_preflight_report(report: PreflightReport) -> None:
    print("[PREFLIGHT] Assault Fire PH startup checks", flush=True)
    print(f"[PREFLIGHT] client root             : {report.client_root}", flush=True)

    if report.tcls_path is not None:
        print(f"[PREFLIGHT] TCLS.dll                : {report.tcls_path}", flush=True)
    print(
        "[PREFLIGHT] TCLS validated build    : "
        + ("YES" if report.tcls_class == "validated-raw-pem-patched" else "NO"),
        flush=True,
    )
    if report.tcls_sha256:
        print(f"[PREFLIGHT] TCLS SHA256             : {report.tcls_sha256.upper()}", flush=True)

    check = report.key_check
    print(
        "[PREFLIGHT] APClient exact bytes    : "
        + ("YES" if check and check.exact_bytes_match else "NO"),
        flush=True,
    )
    print(
        "[PREFLIGHT] same RSA key            : "
        + ("YES" if check and check.same_rsa_key else "NO"),
        flush=True,
    )
    if check:
        print(
            f"[PREFLIGHT] RSA/APClient format     : "
            f"{check.rsa_key_size}-bit / {check.apclient_length} bytes",
            flush=True,
        )

    if report.host_file_path is not None:
        print(f"[PREFLIGHT] hosts file              : {report.host_file_path}", flush=True)
    for name in REQUIRED_HOSTS:
        file_values = report.host_file_values.get(name, [])
        resolved = report.host_resolved_values.get(name)
        passed = file_values == [LOOPBACK_IPV4] and resolved == LOOPBACK_IPV4
        print(
            f"[PREFLIGHT] hosts {name:<27}: "
            f"{'YES' if passed else 'NO'} "
            f"(file={file_values or 'missing'}, resolved={resolved})",
            flush=True,
        )

    if report.ok:
        print("[PREFLIGHT] PASS - all required checks succeeded.", flush=True)
        return

    print("[PREFLIGHT] FAILED - server listeners will NOT start.", flush=True)
    for error in report.errors:
        print(f"[PREFLIGHT]   - {error}", flush=True)


def run_server_preflight(private_key_path: Path) -> bool:
    report = evaluate_preflight(private_key_path=private_key_path)
    print_preflight_report(report)
    return report.ok

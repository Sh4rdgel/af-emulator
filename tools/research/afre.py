#!/usr/bin/env python3
"""AFRE: read-only reverse-engineering helper for Assault Fire PH v1.0.0.24.

Version 1 deliberately does not attach to or modify a process. It provides a
single validated build fingerprint, central symbol/layout catalog, PE summary,
symbol lookup, and address-to-symbol resolution for future research tooling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "af_symbols_10024.json"


class AfreError(RuntimeError):
    pass


def parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(value.strip(), 0)


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AfreError(f"cannot load symbol catalog {path}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise AfreError(f"unsupported catalog schema: {data.get('schema_version')!r}")
    return data


def iter_symbols(catalog: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for group, entries in catalog.get("symbols", {}).items():
        for name, meta in entries.items():
            yield group, name, meta


def lookup_symbol(
    catalog: dict[str, Any], query: str
) -> tuple[str, str, dict[str, Any]]:
    needle = query.casefold()
    exact = []
    partial = []
    for group, name, meta in iter_symbols(catalog):
        full = f"{group}.{name}"
        if needle in {name.casefold(), full.casefold()}:
            exact.append((group, name, meta))
        elif needle in name.casefold() or needle in full.casefold():
            partial.append((group, name, meta))
    if len(exact) == 1:
        return exact[0]
    matches = exact or partial
    if not matches:
        raise AfreError(f"symbol not found: {query}")
    if len(matches) > 1:
        names = ", ".join(f"{g}.{n}" for g, n, _ in matches[:12])
        raise AfreError(f"ambiguous symbol {query!r}: {names}")
    return matches[0]


def nearest_symbol(
    catalog: dict[str, Any], address: int
) -> tuple[str, str, dict[str, Any], int]:
    candidates = []
    for group, name, meta in iter_symbols(catalog):
        if "va" not in meta:
            continue
        va = parse_int(meta["va"])
        if va <= address:
            candidates.append((va, group, name, meta))
    if not candidates:
        raise AfreError(f"no catalog symbol at or below 0x{address:08X}")
    va, group, name, meta = max(candidates, key=lambda row: row[0])
    return group, name, meta, address - va


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _unpack_from(fmt: str, data: bytes, offset: int) -> tuple[Any, ...]:
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(data):
        raise AfreError(f"truncated PE while reading offset 0x{offset:X}")
    return struct.unpack_from(fmt, data, offset)


def parse_pe(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AfreError(f"cannot read {path}: {exc}") from exc
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise AfreError("not a DOS/PE image (missing MZ)")
    pe_off = _unpack_from("<I", data, 0x3C)[0]
    if pe_off + 24 > len(data) or data[pe_off:pe_off + 4] != b"PE\0\0":
        raise AfreError("invalid PE signature")
    machine, sections, _, _, _, opt_size, characteristics = _unpack_from(
        "<HHIIIHH", data, pe_off + 4
    )
    opt = pe_off + 24
    magic = _unpack_from("<H", data, opt)[0]
    if magic != 0x10B:
        raise AfreError(f"expected PE32 optional header, got magic 0x{magic:04X}")
    entry_rva = _unpack_from("<I", data, opt + 16)[0]
    image_base = _unpack_from("<I", data, opt + 28)[0]
    size_of_image = _unpack_from("<I", data, opt + 56)[0]
    sec_off = opt + opt_size
    rows = []
    for index in range(sections):
        off = sec_off + index * 40
        raw_name = data[off:off + 8]
        if len(raw_name) != 8:
            raise AfreError("truncated PE section table")
        name = raw_name.split(b"\0", 1)[0].decode("ascii", errors="replace")
        virtual_size, virtual_address, raw_size, raw_offset = _unpack_from(
            "<IIII", data, off + 8
        )
        sec_characteristics = _unpack_from("<I", data, off + 36)[0]
        rows.append(
            {
                "name": name,
                "rva": virtual_address,
                "va": image_base + virtual_address,
                "virtual_size": virtual_size,
                "raw_offset": raw_offset,
                "raw_size": raw_size,
                "characteristics": sec_characteristics,
            }
        )
    return {
        "machine": machine,
        "number_of_sections": sections,
        "characteristics": characteristics,
        "entry_rva": entry_rva,
        "entry_va": image_base + entry_rva,
        "image_base": image_base,
        "size_of_image": size_of_image,
        "sections": rows,
    }


def default_exe() -> Path | None:
    game_dir = os.environ.get("AF_GAME_DIR", "").strip()
    if not game_dir:
        return None
    base = Path(game_dir)
    for name in ("TGame_AFDEV.exe", "TGame.exe"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return base / "TGame_AFDEV.exe"


def validate_build(
    path: Path, catalog: dict[str, Any]
) -> tuple[bool, list[str], dict[str, Any]]:
    pe = parse_pe(path)
    build = catalog["build"]
    actual_hash = sha256_file(path)
    checks = [
        ("sha256", actual_hash, build["sha256"].lower()),
        ("image_base", pe["image_base"], parse_int(build["image_base"])),
        ("size_of_image", pe["size_of_image"], parse_int(build["size_of_image"])),
        ("entry_rva", pe["entry_rva"], parse_int(build["oep_rva"])),
    ]
    messages = []
    ok = True
    for name, actual, expected in checks:
        passed = actual == expected
        ok &= passed
        if isinstance(actual, int):
            messages.append(
                f"{name:14} {'OK' if passed else 'MISMATCH':8} "
                f"actual=0x{actual:08X} expected=0x{expected:08X}"
            )
        else:
            messages.append(
                f"{name:14} {'OK' if passed else 'MISMATCH':8} "
                f"actual={actual} expected={expected}"
            )
    return ok, messages, pe


def fmt_symbol(group: str, name: str, meta: dict[str, Any]) -> str:
    va = meta.get("va", "-")
    status = meta.get("status", "-")
    kind = meta.get("kind", "")
    suffix = f" {kind}" if kind else ""
    return f"{group}.{name:28} {va:>10} {status}{suffix}"


def cmd_status(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    path = Path(args.exe) if args.exe else default_exe()
    if path is None:
        raise AfreError("no EXE supplied; use --exe or set AF_GAME_DIR")
    print(f"[AFRE] exe: {path}")
    ok, messages, pe = validate_build(path, catalog)
    for line in messages:
        print(line)
    print(f"sections       {pe['number_of_sections']}")
    print(f"result         {'VALIDATED BUILD' if ok else 'REFUSED / UNKNOWN BUILD'}")
    return 0 if ok else 2


def cmd_sections(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del catalog
    path = Path(args.exe) if args.exe else default_exe()
    if path is None:
        raise AfreError("no EXE supplied; use --exe or set AF_GAME_DIR")
    pe = parse_pe(path)
    print("name       VA         RVA        vsize      raw_off    raw_size   flags")
    for sec in pe["sections"]:
        print(
            f"{sec['name']:<10} 0x{sec['va']:08X} 0x{sec['rva']:08X} "
            f"0x{sec['virtual_size']:08X} 0x{sec['raw_offset']:08X} "
            f"0x{sec['raw_size']:08X} 0x{sec['characteristics']:08X}"
        )
    return 0


def cmd_symbols(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    needle = (args.filter or "").casefold()
    count = 0
    for group, name, meta in iter_symbols(catalog):
        hay = f"{group}.{name}".casefold()
        if needle and needle not in hay:
            continue
        print(fmt_symbol(group, name, meta))
        count += 1
    if not count:
        raise AfreError(f"no symbols match {args.filter!r}")
    return 0


def cmd_symbol(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    group, name, meta = lookup_symbol(catalog, args.name)
    print(fmt_symbol(group, name, meta))
    if "expected" in meta:
        print(f"expected bytes: {meta['expected']}")
    return 0


def cmd_resolve(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    address = parse_int(args.address)
    group, name, meta, delta = nearest_symbol(catalog, address)
    va = parse_int(meta["va"])
    print(f"0x{address:08X} -> {group}.{name} + 0x{delta:X} (0x{va:08X})")
    return 0


def cmd_layout(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    layouts = catalog.get("layouts", {})
    if args.type_name:
        matches = [k for k in layouts if args.type_name.casefold() in k.casefold()]
        if not matches:
            raise AfreError(f"layout not found: {args.type_name}")
    else:
        matches = sorted(layouts)
    for type_name in matches:
        print(f"[{type_name}]")
        for field, meta in layouts[type_name].items():
            print(f"  {field:28} {meta['offset']:>8} {meta.get('type', '')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Assault Fire PH v1.0.0.24 RE helper"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="symbol catalog (default: beside this script)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="fingerprint and validate TGame/AFDEV")
    p.add_argument("--exe")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("sections", help="show PE section layout")
    p.add_argument("--exe")
    p.set_defaults(func=cmd_sections)

    p = sub.add_parser("symbols", help="list known absolute symbols")
    p.add_argument("--filter")
    p.set_defaults(func=cmd_symbols)

    p = sub.add_parser("symbol", help="look up one symbol")
    p.add_argument("name")
    p.set_defaults(func=cmd_symbol)

    p = sub.add_parser("resolve", help="resolve an address to nearest known symbol")
    p.add_argument("address")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("layout", help="show known structure offsets")
    p.add_argument("type_name", nargs="?")
    p.set_defaults(func=cmd_layout)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        return int(args.func(args, catalog))
    except AfreError as exc:
        print(f"[AFRE] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

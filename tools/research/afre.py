#!/usr/bin/env python3
"""AFRE: read-only reverse-engineering helper for Assault Fire PH v1.0.0.24.

Version 1 deliberately does not attach to or modify a process. It provides a
single validated build fingerprint, central symbol/layout catalog, PE summary,
symbol lookup, and address-to-symbol resolution for future research tooling.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from pathlib import Path
import struct
import sys
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "af_symbols_10024.json"
DEFAULT_OBJECTS = HERE / "af_objects_10024.json"


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



def load_object_db(path: Path = DEFAULT_OBJECTS) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AfreError(f"cannot load object database {path}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise AfreError(
            f"unsupported object database schema: {data.get('schema_version')!r}"
        )
    return data


def iter_objects(
    db: dict[str, Any]
) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for group in ("reflection", "objects", "native_classes", "script_classes"):
        for name, meta in db.get(group, {}).items():
            yield group, name, meta


def lookup_object(
    db: dict[str, Any], query: str
) -> tuple[str, str, dict[str, Any]]:
    needle = query.casefold()
    exact = []
    partial = []
    for group, name, meta in iter_objects(db):
        full = f"{group}.{name}"
        if needle in {name.casefold(), full.casefold()}:
            exact.append((group, name, meta))
        elif needle in name.casefold() or needle in full.casefold():
            partial.append((group, name, meta))
    if len(exact) == 1:
        return exact[0]
    matches = exact or partial
    if not matches:
        raise AfreError(f"object/class not found: {query}")
    if len(matches) > 1:
        names = ", ".join(f"{g}.{n}" for g, n, _ in matches[:16])
        raise AfreError(f"ambiguous object/class {query!r}: {names}")
    return matches[0]


def object_db_errors(db: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    errors = []
    if db.get("build", {}).get("sha256") != catalog.get("build", {}).get("sha256"):
        errors.append("object DB build SHA does not match symbol catalog")
    for group, name, meta in iter_objects(db):
        fields = meta.get("fields", {})
        for field_name, field_meta in fields.items():
            if not isinstance(field_meta, dict) or "offset" not in field_meta:
                continue
            try:
                offset = parse_int(field_meta["offset"])
            except (TypeError, ValueError):
                errors.append(
                    f"invalid offset: {group}.{name}.{field_name}="
                    f"{field_meta.get('offset')!r}"
                )
                continue
            if offset < 0 or offset > 0x100000:
                errors.append(
                    f"implausible offset: {group}.{name}.{field_name}=0x{offset:X}"
                )
        for key in ("constructor", "vtable"):
            if key in meta:
                try:
                    parse_int(meta[key])
                except (TypeError, ValueError):
                    errors.append(
                        f"invalid {key}: {group}.{name}={meta[key]!r}"
                    )
    return errors


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



AUDIT_BINDINGS = {
    "GIS_EDITOR_VA": ("symbols", "globals", "GIsEditor", "va"),
    "GIS_CLIENT_VA": ("symbols", "globals", "GIsClient", "va"),
    "GIS_SERVER_VA": ("symbols", "globals", "GIsServer", "va"),
    "GLOG_PTR_VA": ("symbols", "globals", "GLog", "va"),
    "GENGINE_PTR_VA": ("symbols", "globals", "GEngine", "va"),
    "GWORLD_PTR_VA": ("symbols", "globals", "GWorld", "va"),
    "IS_BOOT_FROM_TCLS_VA": ("symbols", "globals", "IsBootFromTCLS", "va"),
    "V72_AES_SETKEY": ("symbols", "functions", "AES_SetKey", "va"),
    "STOP_LOADING_MOVIE_VA": ("symbols", "functions", "StopLoadingMovie", "va"),
    "AF_SHOW_LOADING_MOVIE_VA": ("symbols", "functions", "AF_ShowLoadingMovie", "va"),
    "TGAMEENGINE_EXEC_VA": ("symbols", "functions", "UTGameEngine_Exec", "va"),
    "DEVLOGIN_VA": ("symbols", "functions", "TGTenio_DevLogin", "va"),
    "DSM_VTABLE_VA": ("symbols", "vtables", "TGDsDsmNetHandler", "va"),
    "PVE_PC_VTABLE_V24": ("symbols", "vtables", "PVEPlayerController", "va"),
    "LOGININFO_FAIL_VA": ("symbols", "patch_sites", "LoginInfoFail", "va"),
    "GIS_CLIENT_FINAL_WRITE_VA": (
        "symbols", "patch_sites", "GIsClientFinalWrite", "va"
    ),
    "GIS_SERVER_FINAL_RESET_VA": (
        "symbols", "patch_sites", "GIsServerFinalReset", "va"
    ),
    "GAMEPLAYERS_OFFSET": ("layouts", "UGameEngine", "GamePlayers", "offset"),
    "LOCALPLAYER_PC_OFFSET": (
        "layouts", "ULocalPlayer", "PlayerController", "offset"
    ),
    "V72_OFF_WORLD_NETDRIVER": ("layouts", "UWorld", "NetDriver", "offset"),
    "CONTROLLER_PAWN_OFFSET": ("layouts", "AController", "Pawn", "offset"),
    "PC_PLAYER_OFFSET": ("layouts", "APlayerController", "Player", "offset"),
    "PC_CAMERA_OFFSET": ("layouts", "APlayerController", "PlayerCamera", "offset"),
    "PC_ACK_PAWN_OFFSET": (
        "layouts", "APlayerController", "AcknowledgedPawn", "offset"
    ),
    "PVE_PC_PRI_OFFSET_V24": (
        "layouts", "PVEPlayerController", "PlayerReplicationInfo", "offset"
    ),
    "V72_OFF_NETDRIVER_SOCKET": ("layouts", "UNetDriver", "Socket", "offset"),
}


def catalog_value(catalog: dict[str, Any], path: tuple[str, ...]) -> int:
    node: Any = catalog
    for key in path:
        node = node[key]
    return parse_int(node)


def extract_int_constants(path: Path) -> dict[str, int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError) as exc:
        raise AfreError(f"cannot parse loader {path}: {exc}") from exc
    out: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            out[target.id] = int(value.value)
    return out


def audit_loader_constants(
    catalog: dict[str, Any], loader_path: Path
) -> list[tuple[str, int | None, int]]:
    constants = extract_int_constants(loader_path)
    mismatches = []
    for const_name, cat_path in AUDIT_BINDINGS.items():
        expected = catalog_value(catalog, cat_path)
        actual = constants.get(const_name)
        if actual != expected:
            mismatches.append((const_name, actual, expected))
    return mismatches


ADDRESS_RE = re.compile(r"0x[0-9A-Fa-f]{6,8}")


def annotate_text(
    text: str, catalog: dict[str, Any], max_delta: int = 0x400
) -> str:
    build = catalog["build"]
    image_lo = parse_int(build["image_base"])
    image_hi = image_lo + parse_int(build["size_of_image"])
    out = []
    for line in text.splitlines():
        annotations = []
        seen = set()
        for token in ADDRESS_RE.findall(line):
            address = parse_int(token)
            if not (image_lo <= address < image_hi):
                continue
            try:
                group, name, _, delta = nearest_symbol(catalog, address)
            except AfreError:
                continue
            if delta > max_delta:
                continue
            label = f"{token}={group}.{name}+0x{delta:X}"
            if label not in seen:
                annotations.append(label)
                seen.add(label)
        if annotations:
            out.append(line + "    [AFRE " + "; ".join(annotations) + "]")
        else:
            out.append(line)
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + suffix


def flatten_json(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten_json(value[key], child))
    else:
        out[prefix] = value
    return out


def diff_json(before: Any, after: Any) -> list[tuple[str, Any, Any]]:
    a = flatten_json(before)
    b = flatten_json(after)
    keys = sorted(set(a) | set(b))
    return [
        (key, a.get(key), b.get(key))
        for key in keys
        if a.get(key) != b.get(key)
    ]



def catalog_errors(catalog: dict[str, Any]) -> list[str]:
    errors = []
    build = catalog.get("build", {})
    try:
        image_lo = parse_int(build["image_base"])
        image_hi = image_lo + parse_int(build["size_of_image"])
    except (KeyError, TypeError, ValueError) as exc:
        return [f"invalid build geometry: {exc}"]

    seen_names = set()
    for group, name, meta in iter_symbols(catalog):
        key = f"{group}.{name}"
        if key in seen_names:
            errors.append(f"duplicate symbol name: {key}")
        seen_names.add(key)
        if "va" not in meta:
            errors.append(f"symbol has no VA: {key}")
            continue
        try:
            va = parse_int(meta["va"])
        except (TypeError, ValueError):
            errors.append(f"invalid VA for {key}: {meta.get('va')!r}")
            continue
        if not (image_lo <= va < image_hi):
            errors.append(
                f"symbol outside image: {key}=0x{va:08X} "
                f"range=0x{image_lo:08X}-0x{image_hi:08X}"
            )
    return errors


def label_name(group: str, name: str) -> str:
    raw = f"{group}__{name}"
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


def render_labels(catalog: dict[str, Any], fmt: str) -> str:
    rows = sorted(
        (
            parse_int(meta["va"]),
            group,
            name,
            meta,
        )
        for group, name, meta in iter_symbols(catalog)
        if "va" in meta
    )
    if fmt == "csv":
        lines = ["va,group,name,label,status"]
        for va, group, name, meta in rows:
            lines.append(
                f"0x{va:08X},{group},{name},{label_name(group, name)},"
                f"{meta.get('status', '')}"
            )
        return "\n".join(lines) + "\n"

    if fmt == "idc":
        lines = [
            '#include <idc.idc>',
            '',
            'static main()',
            '{',
        ]
        for va, group, name, _ in rows:
            label = label_name(group, name)
            lines.append(f'  set_name(0x{va:08X}, "{label}", SN_NOWARN);')
        lines.extend(['}', ''])
        return "\n".join(lines)

    raise AfreError(f"unsupported label format: {fmt}")


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



def cmd_audit_loader(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    mismatches = audit_loader_constants(catalog, Path(args.loader))
    if not mismatches:
        print("[AFRE] loader/catalog constants match")
        return 0
    for name, actual, expected in mismatches:
        actual_text = "MISSING" if actual is None else f"0x{actual:X}"
        print(f"{name}: loader={actual_text} catalog=0x{expected:X}")
    print(f"[AFRE] {len(mismatches)} mismatch(es)")
    return 2


def cmd_annotate(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    path = Path(args.log)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AfreError(f"cannot read log {path}: {exc}") from exc
    output = annotate_text(text, catalog, parse_int(args.max_delta))
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"[AFRE] annotated: {args.out}")
    else:
        print(output, end="")
    return 0


def cmd_json_diff(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del catalog
    try:
        before = json.loads(Path(args.before).read_text(encoding="utf-8"))
        after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AfreError(f"cannot read JSON snapshots: {exc}") from exc
    changes = diff_json(before, after)
    if not changes:
        print("[AFRE] no changes")
        return 0
    for key, old, new in changes:
        print(f"{key}: {old!r} -> {new!r}")
    print(f"[AFRE] {len(changes)} changed field(s)")
    return 0



def cmd_audit_catalog(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del args
    errors = catalog_errors(catalog)
    if not errors:
        count = sum(1 for _ in iter_symbols(catalog))
        print(f"[AFRE] catalog OK ({count} symbols)")
        return 0
    for error in errors:
        print(error)
    print(f"[AFRE] {len(errors)} catalog error(s)")
    return 2


def cmd_export_labels(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    output = render_labels(catalog, args.format)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"[AFRE] labels: {args.out}")
    else:
        print(output, end="")
    return 0



def cmd_objects(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del catalog
    db = load_object_db(args.objects_db)
    needle = (args.filter or "").casefold()
    count = 0
    for group, name, meta in iter_objects(db):
        hay = f"{group}.{name}".casefold()
        if needle and needle not in hay:
            continue
        status = meta.get("status", "-")
        extras = []
        if "vtable" in meta:
            extras.append(f"vt={meta['vtable']}")
        if "constructor" in meta:
            extras.append(f"ctor={meta['constructor']}")
        if "native_size" in meta:
            extras.append(f"size={meta['native_size']}")
        tail = (" " + " ".join(extras)) if extras else ""
        print(f"{group}.{name:30} {status}{tail}")
        count += 1
    if not count:
        raise AfreError(f"no objects/classes match {args.filter!r}")
    return 0


def cmd_object(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del catalog
    db = load_object_db(args.objects_db)
    group, name, meta = lookup_object(db, args.name)
    print(f"[{group}.{name}]")
    print(json.dumps(meta, indent=2))
    return 0


def cmd_field(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del catalog
    db = load_object_db(args.objects_db)
    group, name, meta = lookup_object(db, args.object_name)
    fields = meta.get("fields", {})
    needle = args.field.casefold()
    matches = [
        (field_name, field_meta)
        for field_name, field_meta in fields.items()
        if needle == field_name.casefold() or needle in field_name.casefold()
    ]
    if not matches:
        raise AfreError(f"field not found: {name}.{args.field}")
    for field_name, field_meta in matches:
        print(f"{group}.{name}.{field_name}")
        print(json.dumps(field_meta, indent=2))
    return 0


def cmd_conflicts(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    del catalog
    db = load_object_db(args.objects_db)
    conflicts = db.get("conflicts", [])
    if not conflicts:
        print("[AFRE] no recorded object-layout conflicts")
        return 0
    for item in conflicts:
        print(f"[{item.get('id', 'conflict')}] {item.get('status', '-')}")
        print(item.get("description", ""))
        for variant in item.get("variants", []):
            print(f"  {variant.get('name', 'variant')}:")
            for field, offset in variant.get("fields", {}).items():
                print(f"    {field:24} {offset}")
    return 0


def cmd_audit_objects(args: argparse.Namespace, catalog: dict[str, Any]) -> int:
    db = load_object_db(args.objects_db)
    errors = object_db_errors(db, catalog)
    if not errors:
        count = sum(1 for _ in iter_objects(db))
        print(f"[AFRE] object DB OK ({count} objects/classes)")
        return 0
    for error in errors:
        print(error)
    print(f"[AFRE] {len(errors)} object DB error(s)")
    return 2


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
    parser.add_argument(
        "--objects-db",
        type=Path,
        default=DEFAULT_OBJECTS,
        help="object database (default: beside this script)",
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

    p = sub.add_parser("audit-loader", help="check loader constants against catalog")
    p.add_argument(
        "--loader",
        default="tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py",
    )
    p.set_defaults(func=cmd_audit_loader)

    p = sub.add_parser("annotate", help="annotate TGame addresses in a text log")
    p.add_argument("log")
    p.add_argument("--out")
    p.add_argument("--max-delta", default="0x400")
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("json-diff", help="diff two JSON snapshots")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(func=cmd_json_diff)

    p = sub.add_parser("audit-catalog", help="validate catalog geometry and symbols")
    p.set_defaults(func=cmd_audit_catalog)

    p = sub.add_parser("export-labels", help="export known addresses for static analysis")
    p.add_argument("--format", choices=("idc", "csv"), default="idc")
    p.add_argument("--out")
    p.set_defaults(func=cmd_export_labels)

    p = sub.add_parser("objects", help="list known UE3/game objects and classes")
    p.add_argument("--filter")
    p.set_defaults(func=cmd_objects)

    p = sub.add_parser("object", help="show one object/class definition")
    p.add_argument("name")
    p.set_defaults(func=cmd_object)

    p = sub.add_parser("field", help="show a known field on an object/class")
    p.add_argument("object_name")
    p.add_argument("field")
    p.set_defaults(func=cmd_field)

    p = sub.add_parser("conflicts", help="show unresolved object-layout conflicts")
    p.set_defaults(func=cmd_conflicts)

    p = sub.add_parser("audit-objects", help="validate the object database")
    p.set_defaults(func=cmd_audit_objects)
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

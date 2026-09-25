"""Temporary local AP initialization workaround for Assault Fire PH v1.0.0.24.

The stock client's native initial AP/GamePoint population is not yet understood.
For local preservation/testing only, this helper copies the authoritative server
wallet AP into the already-verified live client field:

    TGOnlineClient + 0x2C8 -> LocalPlayerData
    LocalPlayerData + 0x84 -> GamePoint / visible AP

The helper writes only GamePoint. It does not patch executable code, install
hooks, or alter purchase/inventory logic. Remove this module once the native
login/TP balance initialization path is implemented.
"""

from __future__ import annotations

import csv
import ctypes
from ctypes import wintypes
import io
import os
import struct
import subprocess
import threading
from typing import Callable, Mapping

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

TGONLINECLIENT_VTABLE = 0x01DA3A50
LOCAL_PLAYER_DATA_OFF = 0x2C8
GAMEPOINT_OFF = 0x84
GOLDPOINT_OFF = 0x88
HAPPYPOINT_OFF = 0x90
LEVEL_OFF = 0xA0
MAX_USER_ADDR = 0x70000000


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class LocalAPSync:
    """Seed the local PH client's initial GamePoint from the server wallet."""

    def __init__(
        self,
        wallet_provider: Callable[[], Mapping[str, int]],
        *,
        enabled: bool | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        if enabled is None:
            enabled = (
                os.environ.get("AF_LOCAL_AP_SYNC", "1").strip().lower()
                not in {"0", "false", "no", "off"}
            )
        self.enabled = bool(enabled)
        self._wallet_provider = wallet_provider
        self._logger = logger or (lambda message: print(message, flush=True))
        self._lock = threading.Lock()
        self._done: dict[int, dict[str, int]] = {}
        self._stop = threading.Event()
        self._started = False

    def describe(self) -> str:
        if not self.enabled:
            return "disabled by AF_LOCAL_AP_SYNC=0"
        if os.name != "nt":
            return "disabled on non-Windows host"
        return (
            "TEMPORARY local workaround enabled: authoritative wallet AP -> "
            "LocalPlayerData.GamePoint(+0x84), once per TGame PID"
        )

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        if not self.enabled:
            self._log("[AP-SYNC] disabled by AF_LOCAL_AP_SYNC=0")
            return
        if os.name != "nt":
            self._log("[AP-SYNC] disabled: local workaround is Windows-only")
            return

        self._log(
            "[AP-SYNC] TEMPORARY workaround enabled: "
            "wallet AP -> LocalPlayerData.GamePoint(+0x84), once per TGame PID"
        )
        threading.Thread(
            target=self._monitor,
            name="AFLocalAPSync",
            daemon=True,
        ).start()

    def stop(self) -> None:
        self._stop.set()

    def request(self, reason: str = "manual") -> None:
        """Request an immediate non-blocking sync for all local TGame processes."""
        if not self.enabled or os.name != "nt":
            return
        threading.Thread(
            target=self._sync_all,
            args=(reason, False),
            name="AFLocalAPSyncNow",
            daemon=True,
        ).start()

    def _log(self, message: str) -> None:
        self._logger(str(message))

    def _wallet(self) -> Mapping[str, int]:
        return self._wallet_provider()

    @staticmethod
    def _tasklist_tgame_pids() -> list[int]:
        try:
            cp = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=5,
            )
        except Exception:
            return []

        result: list[int] = []
        for row in csv.reader(io.StringIO(cp.stdout)):
            if len(row) < 2 or row[0].strip().lower() != "tgame.exe":
                continue
            try:
                result.append(int(row[1].replace(",", "").strip()))
            except Exception:
                pass
        return sorted(set(result))

    @staticmethod
    def _kernel32():
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        k32.ReadProcessMemory.restype = wintypes.BOOL
        k32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        k32.WriteProcessMemory.restype = wintypes.BOOL
        k32.VirtualQueryEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION),
            ctypes.c_size_t,
        ]
        k32.VirtualQueryEx.restype = ctypes.c_size_t
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        return k32

    def _open_process(self, pid: int):
        k32 = self._kernel32()
        rights = (
            PROCESS_QUERY_INFORMATION
            | PROCESS_VM_READ
            | PROCESS_VM_WRITE
            | PROCESS_VM_OPERATION
        )
        handle = k32.OpenProcess(rights, False, int(pid))
        if not handle:
            raise OSError(
                ctypes.get_last_error(),
                f"OpenProcess({pid}) failed",
            )
        return k32, handle

    @staticmethod
    def _read_mem(k32, handle, address: int, size: int) -> bytes | None:
        if not address or size <= 0:
            return None
        buf = (ctypes.c_ubyte * int(size))()
        got = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(
            handle,
            ctypes.c_void_p(int(address)),
            ctypes.byref(buf),
            int(size),
            ctypes.byref(got),
        )
        if not ok or got.value != int(size):
            return None
        return bytes(buf)

    def _u32(self, k32, handle, address: int) -> int | None:
        raw = self._read_mem(k32, handle, address, 4)
        return struct.unpack("<I", raw)[0] if raw else None

    @staticmethod
    def _write_u32(k32, handle, address: int, value: int) -> None:
        raw = struct.pack("<I", int(value) & 0xFFFFFFFF)
        buf = (ctypes.c_ubyte * 4).from_buffer_copy(raw)
        wrote = ctypes.c_size_t(0)
        ok = k32.WriteProcessMemory(
            handle,
            ctypes.c_void_p(int(address)),
            ctypes.byref(buf),
            4,
            ctypes.byref(wrote),
        )
        if not ok or wrote.value != 4:
            raise OSError(
                ctypes.get_last_error(),
                f"WriteProcessMemory(0x{int(address):08X}) failed",
            )

    @staticmethod
    def _plausible_ptr(value: int | None) -> bool:
        return (
            isinstance(value, int)
            and 0x00010000 <= value < MAX_USER_ADDR
        )

    def _scan_exact_vtable(self, k32, handle, max_hits: int = 32) -> list[int]:
        pat = struct.pack("<I", TGONLINECLIENT_VTABLE)
        hits: list[int] = []
        address = 0x00010000
        mbi = MEMORY_BASIC_INFORMATION()
        mbi_size = ctypes.sizeof(mbi)

        while address < MAX_USER_ADDR and len(hits) < max_hits:
            got = k32.VirtualQueryEx(
                handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                mbi_size,
            )
            if not got:
                address += 0x10000
                continue

            base = int(mbi.BaseAddress or 0)
            size = int(mbi.RegionSize or 0)
            next_address = base + max(size, 0x1000)

            readable = (
                mbi.State == MEM_COMMIT
                and mbi.Type in (MEM_PRIVATE, MEM_IMAGE)
                and not (mbi.Protect & PAGE_GUARD)
                and (mbi.Protect & 0xFF) != PAGE_NOACCESS
                and size > 0
            )

            if readable:
                pos = base
                end = min(base + size, MAX_USER_ADDR)
                carry = b""

                while pos < end and len(hits) < max_hits:
                    count = min(0x100000, end - pos)
                    raw = self._read_mem(k32, handle, pos, count)
                    if raw:
                        data = carry + raw
                        origin = pos - len(carry)
                        start = 0
                        while len(hits) < max_hits:
                            found = data.find(pat, start)
                            if found < 0:
                                break
                            va = origin + found
                            if (va & 3) == 0:
                                hits.append(va)
                            start = found + 1
                        carry = data[-3:]
                    else:
                        carry = b""
                    pos += count

            address = max(next_address, address + 0x1000)

        return sorted(set(hits))

    def _pick_local_player_data(self, k32, handle):
        rows = []
        server_gp = int(self._wallet().get("gp", 0))

        for client in self._scan_exact_vtable(k32, handle):
            pdata = self._u32(
                k32,
                handle,
                client + LOCAL_PLAYER_DATA_OFF,
            )
            if not self._plausible_ptr(pdata):
                continue

            header = self._read_mem(k32, handle, pdata, 0x38)
            walletish = self._read_mem(k32, handle, pdata, 0xA4)
            if not header or not walletish:
                continue

            outer = struct.unpack_from("<I", header, 0x28)[0]
            cls = struct.unpack_from("<I", header, 0x34)[0]
            game = struct.unpack_from("<I", walletish, GAMEPOINT_OFF)[0]
            gold = struct.unpack_from("<I", walletish, GOLDPOINT_OFF)[0]
            happy = struct.unpack_from("<I", walletish, HAPPYPOINT_OFF)[0]
            level = struct.unpack_from("<I", walletish, LEVEL_OFF)[0]

            score = 10
            if outer == client:
                score += 100
            if self._plausible_ptr(cls):
                score += 20
            if gold == server_gp:
                score += 40
            elif gold <= 100000000:
                score += 5
            if game <= 100000000:
                score += 5
            if happy <= 100000000:
                score += 5
            if 1 <= level <= 1000:
                score += 25

            rows.append(
                {
                    "score": score,
                    "client": client,
                    "pdata": pdata,
                    "game": game,
                    "gold": gold,
                    "level": level,
                }
            )

        rows.sort(key=lambda row: (-row["score"], row["client"]))
        if not rows or rows[0]["score"] < 120:
            return None
        if (
            len(rows) > 1
            and rows[1]["score"] == rows[0]["score"]
            and rows[1]["pdata"] != rows[0]["pdata"]
        ):
            return None
        return rows[0]

    def _sync_pid(self, pid: int, *, reason: str) -> bool:
        k32 = None
        handle = None
        try:
            k32, handle = self._open_process(pid)
            row = self._pick_local_player_data(k32, handle)
            if not row:
                return False

            desired = max(0, int(self._wallet().get("ap", 0))) & 0xFFFFFFFF
            current = int(row["game"])
            if current != desired:
                self._write_u32(
                    k32,
                    handle,
                    int(row["pdata"]) + GAMEPOINT_OFF,
                    desired,
                )

            verify = self._u32(
                k32,
                handle,
                int(row["pdata"]) + GAMEPOINT_OFF,
            )
            if verify != desired:
                return False

            with self._lock:
                self._done[int(pid)] = {
                    "pdata": int(row["pdata"]),
                    "ap": desired,
                }

            self._log(
                "[AP-SYNC] TEMPORARY "
                f"reason={reason} PID={pid} "
                f"TGOnlineClient=0x{int(row['client']):08X} "
                f"LocalPlayerData=0x{int(row['pdata']):08X} "
                f"GamePoint {current}->{desired} "
                f"GP={row['gold']} level={row['level']}"
            )
            return True
        except Exception as exc:
            if reason != "startup-retry":
                self._log(
                    f"[AP-SYNC] PID={pid} reason={reason} failed: {exc}"
                )
            return False
        finally:
            if handle and k32:
                try:
                    k32.CloseHandle(handle)
                except Exception:
                    pass

    def _sync_all(self, reason: str, startup_only: bool) -> None:
        for pid in self._tasklist_tgame_pids():
            if startup_only:
                with self._lock:
                    if pid in self._done:
                        continue
            self._sync_pid(pid, reason=reason)

    def _monitor(self) -> None:
        while not self._stop.is_set():
            pids = self._tasklist_tgame_pids()
            live = set(pids)

            with self._lock:
                for old_pid in list(self._done):
                    if old_pid not in live:
                        self._done.pop(old_pid, None)

            for pid in pids:
                with self._lock:
                    done = pid in self._done
                if done:
                    continue
                self._sync_pid(pid, reason="startup-retry")

            self._stop.wait(0.75)

"""Small, dependency-free, read-only Windows process-memory wrapper.

The module intentionally exposes no write, allocation, remote-thread, or injection
operations.  If Windows refuses access, callers receive an exception and stop.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import struct
from typing import Iterable, Iterator


if os.name != "nt":
    raise OSError("shadowverse_tracker.memory.win32 is only available on Windows")


TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260
MAX_MODULE_NAME32 = 255
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80
PAGE_GUARD = 0x100


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * (MAX_MODULE_NAME32 + 1)),
        ("szExePath", wintypes.WCHAR * MAX_PATH),
    ]


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


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32FirstW.restype = wintypes.BOOL
kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
kernel32.Module32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


class Win32Error(OSError):
    """Windows API failure with the original error code."""


def _raise_last_error(operation: str) -> None:
    code = ctypes.get_last_error()
    raise Win32Error(code, f"{operation} failed: {ctypes.FormatError(code).strip()}")


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: str
    base_address: int
    size: int


@dataclass(frozen=True)
class MemoryRegion:
    base_address: int
    size: int
    state: int
    protect: int
    type: int

    @property
    def readable(self) -> bool:
        return (
            self.state == MEM_COMMIT
            and not self.protect & PAGE_NOACCESS
            and not self.protect & PAGE_GUARD
        )

    @property
    def writable(self) -> bool:
        base_protect = self.protect & 0xFF
        return self.readable and base_protect in {
            PAGE_READWRITE,
            PAGE_WRITECOPY,
            PAGE_EXECUTE_READWRITE,
            PAGE_EXECUTE_WRITECOPY,
        }


class _Snapshot:
    def __init__(self, flags: int, pid: int = 0) -> None:
        self.handle = kernel32.CreateToolhelp32Snapshot(flags, pid)
        if self.handle == INVALID_HANDLE_VALUE:
            _raise_last_error("CreateToolhelp32Snapshot")

    def __enter__(self) -> wintypes.HANDLE:
        return self.handle

    def __exit__(self, *_: object) -> None:
        kernel32.CloseHandle(self.handle)


def iter_processes() -> Iterator[ProcessInfo]:
    with _Snapshot(TH32CS_SNAPPROCESS) as snapshot:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            _raise_last_error("Process32FirstW")
        while True:
            yield ProcessInfo(pid=int(entry.th32ProcessID), name=entry.szExeFile)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break


def find_process(executable_name: str) -> ProcessInfo:
    matches = [p for p in iter_processes() if p.name.casefold() == executable_name.casefold()]
    if not matches:
        raise ProcessLookupError(f"process not found: {executable_name}")
    if len(matches) > 1:
        pids = ", ".join(str(p.pid) for p in matches)
        raise ProcessLookupError(f"multiple {executable_name} processes found: {pids}; pass --pid")
    return matches[0]


def find_process_candidates(executable_names: Iterable[str]) -> tuple[ProcessInfo, ...]:
    """Return matching processes in the requested preference order.

    The Windows and China-client builds use different process names.  A
    caller should pass names in preference order; this helper keeps the
    existing ambiguity protection of :func:`find_process` while allowing a
    tracker to try another supported build when one is not running.  The
    process list is captured once so a rapidly starting/stopping emulator
    cannot produce a mixture of snapshots from different enumerations.
    """
    names = tuple(dict.fromkeys(name.strip() for name in executable_names if name and name.strip()))
    if not names:
        raise ValueError("at least one executable name is required")
    processes = tuple(iter_processes())
    matches_by_name: list[ProcessInfo] = []
    for name in names:
        matches = tuple(
            process for process in processes if process.name.casefold() == name.casefold()
        )
        if len(matches) == 1:
            matches_by_name.append(matches[0])
        elif len(matches) > 1:
            pids = ", ".join(str(process.pid) for process in matches)
            raise ProcessLookupError(f"multiple {name} processes found: {pids}; pass --pid")
    if not matches_by_name:
        raise ProcessLookupError(f"process not found: {', '.join(names)}")
    return tuple(matches_by_name)


def iter_modules(pid: int) -> Iterator[ModuleInfo]:
    flags = TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32
    with _Snapshot(flags, pid) as snapshot:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Module32FirstW(snapshot, ctypes.byref(entry)):
            _raise_last_error("Module32FirstW")
        while True:
            base = ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value
            yield ModuleInfo(
                name=entry.szModule,
                path=entry.szExePath,
                base_address=int(base or 0),
                size=int(entry.modBaseSize),
            )
            if not kernel32.Module32NextW(snapshot, ctypes.byref(entry)):
                break


class ProcessReader:
    """A process handle limited to query and read permissions."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
            False,
            pid,
        )
        if not self._handle:
            _raise_last_error(f"OpenProcess({pid})")

    @classmethod
    def for_executable(cls, executable_name: str) -> "ProcessReader":
        return cls(find_process(executable_name).pid)

    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "ProcessReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def module(self, module_name: str) -> ModuleInfo:
        for module in iter_modules(self.pid):
            if module.name.casefold() == module_name.casefold():
                return module
        raise LookupError(f"module not loaded in PID {self.pid}: {module_name}")

    def iter_memory_regions(self) -> Iterator[MemoryRegion]:
        """Yield the process virtual-memory map without modifying the target."""
        address = 0
        maximum_address = (1 << 47) - 1
        while address < maximum_address:
            info = MEMORY_BASIC_INFORMATION()
            result = kernel32.VirtualQueryEx(
                self._handle,
                ctypes.c_void_p(address),
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not result:
                break
            base = int(info.BaseAddress or 0)
            size = int(info.RegionSize)
            if size <= 0:
                break
            yield MemoryRegion(
                base_address=base,
                size=size,
                state=int(info.State),
                protect=int(info.Protect),
                type=int(info.Type),
            )
            next_address = base + size
            if next_address <= address:
                break
            address = next_address

    def read(self, address: int, size: int) -> bytes:
        if address <= 0 or size < 0:
            raise ValueError("invalid memory range")
        if size == 0:
            return b""
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        ok = kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read),
        )
        if not ok or bytes_read.value != size:
            _raise_last_error(f"ReadProcessMemory(0x{address:X}, 0x{size:X})")
        return buffer.raw

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read(address, 8))[0]

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def read_i32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]

    def read_c_string(self, address: int, maximum: int = 512) -> str:
        if not address:
            return ""
        data = self.read(address, maximum)
        end = data.find(b"\0")
        if end < 0:
            raise ValueError(f"unterminated string at 0x{address:X}")
        return data[:end].decode("utf-8", errors="replace")

    def iter_read(self, address: int, size: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        offset = 0
        while offset < size:
            amount = min(chunk_size, size - offset)
            yield self.read(address + offset, amount)
            offset += amount

"""Exact filesystem dates, kept separate from embedded image metadata."""
from __future__ import annotations

import ctypes
import errno
import os
from dataclasses import dataclass
from pathlib import Path

NANOSECONDS = 1_000_000_000
FILETIME_EPOCH = 116_444_736_000_000_000


def _windows_creation_time(path: Path, value: int) -> None:
    """Set creation time through a write-attributes handle, not a content rewrite."""
    from ctypes import wintypes

    ticks, remainder = divmod(value, 100)
    ticks += FILETIME_EPOCH
    if remainder or not 0 < ticks < 2**64 - 1:
        raise OSError(f"Creation time cannot be represented by Windows FILETIME: {path}")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileTime.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel.SetFileTime.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x100, 7, None, 3, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created = wintypes.FILETIME(ticks & 0xFFFFFFFF, ticks >> 32)
        if not kernel.SetFileTime(handle, ctypes.byref(created), None, None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if not kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def _creation_ns(info: os.stat_result) -> int | None:
    created = getattr(info, "st_birthtime_ns", None)
    if created is not None:
        return created
    if os.name == "nt":
        return info.st_ctime_ns
    return None


@dataclass(frozen=True)
class FileTimes:
    """Original UTC epoch nanoseconds; an absent date is never inferred."""

    modified_ns: int
    created_ns: int | None = None
    accessed_ns: int | None = None

    @classmethod
    def read(cls, path: Path) -> FileTimes:
        """Capture filesystem dates before reading file content."""
        info = path.stat()
        return cls(info.st_mtime_ns, _creation_ns(info), info.st_atime_ns)

    @property
    def ordering_ns(self) -> int:
        """Use original creation time, falling back to modification explicitly."""
        return self.created_ns if self.created_ns is not None else self.modified_ns

    def restore(self, path: Path) -> None:
        """Restore dates and reject unrepresentable creation/modification times."""
        try:
            accessed = self.accessed_ns if self.accessed_ns is not None else path.stat().st_atime_ns
            os.utime(path, ns=(accessed, self.modified_ns))
            if self.created_ns is not None:
                if os.name == "nt":
                    _windows_creation_time(path, self.created_ns)
                else:
                    raise OSError(errno.ENOTSUP, "This platform cannot restore a known creation time")
            actual = path.stat()
            if actual.st_mtime_ns != self.modified_ns:
                raise OSError("Destination filesystem changed modification-time precision")
            if self.created_ns is not None and _creation_ns(actual) != self.created_ns:
                raise OSError("Destination filesystem did not preserve the original creation time")
        except (OSError, OverflowError, ValueError) as ex:
            raise OSError(f"Cannot preserve original file dates for {path}: {ex}") from ex

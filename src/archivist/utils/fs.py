"""Stateless filesystem helpers (no business rules)."""
import os
import stat
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path


def is_hidden(path: Path) -> bool:
    """Hidden = dot-prefixed name or Windows hidden/system attribute."""
    if path.name.startswith("."):
        return True
    attrs = getattr(os.stat(path), "st_file_attributes", 0)
    return bool(attrs & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))


def is_readonly(path: Path) -> bool:
    """True if the path is not writable (read-only attribute on Windows)."""
    return not os.access(path, os.W_OK)


def is_link(path: Path) -> bool:
    """Symlink, or on Windows any reparse point such as a directory junction (is_symlink() misses those)."""
    if path.is_symlink():
        return True
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def make_writable(path: Path) -> None:
    """Clear the read-only flag."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def iter_tree(folder: Path):
    """Yield folder and everything below it (without following symlinks)."""
    yield folder
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        for name in dirnames + filenames:
            yield Path(dirpath) / name


def find_files(root: Path, pattern: str) -> Iterator[Path]:
    """Files under root whose name matches the glob pattern in any case (plain globs are case-sensitive on Linux)."""
    pattern = pattern.lower()
    for path in root.rglob("*"):
        if fnmatchcase(path.name.lower(), pattern) and not path.is_symlink() and path.is_file():
            yield path


def format_size(size: float) -> str:
    """Human-readable size in powers of 1024, e.g. 1536 -> '1.5 KB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

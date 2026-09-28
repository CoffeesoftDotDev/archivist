"""Read-only image discovery, including bounded inspection of nested ZIPs."""
from __future__ import annotations

import io
import os
import stat
import struct
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..core import get_logger
from ..core.config import IMAGE_EXTENSIONS
from ..utils import FileTimes, is_link
from ..utils.timestamps import FILETIME_EPOCH, NANOSECONDS
from .zip_extractor import BOMB_MIN_SIZE, MAX_DEPTH, MAX_RATIO

log = get_logger("images")

MAX_ARCHIVE_ENTRIES = 100_000
MAX_NESTED_ZIP_BYTES = 64 * 1024**2
MAX_NESTED_TOTAL_BYTES = 256 * 1024**2
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class ImageWorkflowError(RuntimeError):
    """An image workflow cannot safely continue."""


def checked_path(path: Path) -> Path:
    """Resolve a path only after rejecting link or junction components."""
    absolute = Path(os.path.abspath(path.expanduser()))
    for part in (*reversed(absolute.parents), absolute):
        if is_link(part):
            raise ImageWorkflowError(f"Links and junctions are not supported: {part}")
    return absolute.resolve()


@dataclass(frozen=True)
class Snapshot:
    """Identity and modification state used to bind a plan to its original source."""

    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def read(cls, path: Path) -> Snapshot:
        """Read a regular file without following links."""
        checked_path(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ImageWorkflowError(f"Not a regular source file: {path}")
        return cls(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def verify(self, path: Path) -> None:
        """Reject a source changed since inventory."""
        if self != self.read(path):
            raise ImageWorkflowError(f"Source changed since inventory; run again: {path}")


def member_path(member: zipfile.ZipInfo) -> Path:
    """Return a portable relative member path, never a sanitized unsafe path."""
    name = member.orig_filename.replace("\\", "/")
    pieces = name.rstrip("/").split("/")
    if (
        not name or name.startswith("/") or "\x00" in name
        or any(
            part in ("", ".", "..") or part.endswith((" ", "."))
            or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            or part.split(".")[0].casefold() in WINDOWS_RESERVED
            for part in pieces
        )
    ):
        raise ImageWorkflowError(f"Unsafe ZIP member name: {member.orig_filename!r}")
    kind = stat.S_IFMT(member.external_attr >> 16)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise ImageWorkflowError(f"Unsupported ZIP link/special member: {name!r}")
    if member.flag_bits & 1:
        raise ImageWorkflowError(f"Encrypted ZIP member is unsupported: {name!r}")
    if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
        raise ImageWorkflowError(f"Unsupported ZIP compression method for {name!r}: {member.compress_type}")
    return Path(*pieces)


def _extra_times(extra: bytes, *, central: bool) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    offset = 0
    while offset < len(extra):
        if offset + 4 > len(extra):
            raise ImageWorkflowError("Truncated ZIP extra-field header")
        tag, length = struct.unpack_from("<HH", extra, offset)
        data = extra[offset + 4:offset + 4 + length]
        if len(data) != length:
            raise ImageWorkflowError("Truncated ZIP timestamp metadata")
        offset += 4 + length
        values: dict[str, tuple[int, int]] = {}
        if tag == 0x000A:
            if len(data) < 4:
                raise ImageWorkflowError("Truncated ZIP NTFS metadata")
            pos = 4
            while pos < len(data):
                if pos + 4 > len(data):
                    raise ImageWorkflowError("Truncated ZIP NTFS attribute")
                attribute, size = struct.unpack_from("<HH", data, pos)
                value = data[pos + 4:pos + 4 + size]
                if len(value) != size or (attribute == 1 and size != 24):
                    raise ImageWorkflowError("Invalid ZIP NTFS timestamp attribute")
                if attribute == 1:
                    for name, ticks in zip(("modified_ns", "accessed_ns", "created_ns"), struct.unpack("<QQQ", value)):
                        if ticks:
                            values[name] = (2, (ticks - FILETIME_EPOCH) * 100)
                pos += 4 + size
        elif tag == 0x5455:
            if not data:
                raise ImageWorkflowError("Missing ZIP extended timestamp flags")
            pos = 1
            for bit, name in enumerate(("modified_ns", "accessed_ns", "created_ns")):
                if central and bit:
                    break  # Central flags describe local fields, not central payload.
                if data[0] & (1 << bit):
                    if pos + 4 > len(data):
                        raise ImageWorkflowError("Truncated ZIP extended timestamp")
                    values[name] = (1, struct.unpack_from("<i", data, pos)[0] * NANOSECONDS)
                    pos += 4
        for name, value in values.items():
            if name in result and result[name][0] == value[0] and result[name] != value:
                raise ImageWorkflowError(f"Conflicting ZIP timestamp metadata: {name}")
            if name not in result or value[0] > result[name][0]:
                result[name] = value
    return result


def zip_times(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> FileTimes:
    """Read precise UTC extras, including dates stored only in the local header."""
    stream = archive.fp
    if stream is None:
        raise ImageWorkflowError("Cannot inspect timestamps of a closed ZIP")
    position = stream.tell()
    try:
        stream.seek(member.header_offset)
        header = stream.read(30)
        if len(header) != 30 or header[:4] != b"PK\x03\x04":
            raise ImageWorkflowError(f"Invalid ZIP local header: {member.filename!r}")
        name_length, extra_length = struct.unpack_from("<HH", header, 26)
        stream.seek(name_length, 1)
        extra = stream.read(extra_length)
        if len(extra) != extra_length:
            raise ImageWorkflowError(f"Truncated ZIP local metadata: {member.filename!r}")
    finally:
        stream.seek(position)
    dates = _extra_times(member.extra, central=True)
    for name, value in _extra_times(extra, central=False).items():
        if name in dates and dates[name][0] == value[0] and dates[name] != value:
            raise ImageWorkflowError(f"Conflicting local/central ZIP dates: {member.filename!r}")
        if name not in dates or value[0] > dates[name][0]:
            dates[name] = value
    modified = dates.get("modified_ns")
    modified_ns = modified[1] if modified is not None else int(datetime(*member.date_time).timestamp()) * NANOSECONDS
    return FileTimes(
        modified_ns,
        dates["created_ns"][1] if "created_ns" in dates else None,
        dates["accessed_ns"][1] if "accessed_ns" in dates else None,
    )


def metadata_name(path: Path) -> bool:
    """Identify known thumbnail/AppleDouble metadata rather than user pictures."""
    return any(part.casefold() == "@eadir" or part.startswith("._") for part in path.parts)


@dataclass
class ArchiveRecord:
    """Validated archive metadata retaining its physical source and nested provenance."""

    outer: Path
    chain: tuple[str, ...]
    members: tuple[zipfile.ZipInfo, ...]
    children: list[ArchiveRecord] = field(default_factory=list)
    timestamps: dict[str, FileTimes] = field(default_factory=dict)

    @property
    def location(self) -> str:
        return " :: ".join((str(self.outer), *self.chain))

    @property
    def unpacked_size(self) -> int:
        return sum(member.file_size for member in self.members) + sum(child.unpacked_size for child in self.children)

    def walk(self) -> Iterator[ArchiveRecord]:
        """Yield this archive and all nested archives in extraction order."""
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class ImageItem:
    """One on-disk or archived image occurrence, with original timestamp provenance."""

    path: Path
    name: str
    extension: str
    size: int
    dates: FileTimes
    archive: ArchiveRecord | None = None
    member: zipfile.ZipInfo | None = None

    @property
    def timestamp(self) -> float:
        return self.dates.ordering_ns / NANOSECONDS

    @property
    def timestamp_source(self) -> str:
        return "creation" if self.dates.created_ns is not None else "modification (fallback)"

    @property
    def location(self) -> str:
        if self.archive is not None and self.member is not None:
            return f"{self.archive.location} :: {self.member.filename}"
        return str(self.path)


@dataclass
class Inventory:
    """Selected items, full archive manifests and visible discovery problems."""

    root: Path
    items: list[ImageItem] = field(default_factory=list)
    archives: list[ArchiveRecord] = field(default_factory=list)
    snapshots: dict[Path, Snapshot] = field(default_factory=dict)
    protected_sources: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    archive_entries: int = 0
    nested_bytes: int = 0

    def verify(self) -> None:
        """Check all planned physical sources against their inventory snapshots."""
        for path, snapshot in self.snapshots.items():
            snapshot.verify(path)


class ImageInventory:
    """Scan ordinary files and ZIP directories without writing extracted files."""

    def __init__(self, extensions: tuple[str, ...] | None = None):
        self.extensions = frozenset(extensions or IMAGE_EXTENSIONS)

    def scan(self, root: Path) -> Inventory:
        """Return all discoverable matches; problems mean the inventory is incomplete."""
        result = Inventory(checked_path(root))
        for folder, directories, files in os.walk(result.root, followlinks=False, onerror=lambda ex: result.problems.append(str(ex))):
            for name in sorted(directories):
                path = Path(folder) / name
                if is_link(path) or metadata_name(path.relative_to(result.root)):
                    directories.remove(name)
                    result.skipped.append(f"Skipped link or metadata directory: {path}")
            directories.sort()
            for name in sorted(files):
                path = Path(folder) / name
                extension = path.suffix[1:].lower()
                if is_link(path) or metadata_name(path.relative_to(result.root)):
                    result.skipped.append(f"Skipped link or metadata file: {path}")
                    continue
                if extension not in IMAGE_EXTENSIONS and extension != "zip":
                    continue
                result.protected_sources.append(path)
                try:
                    snapshot = Snapshot.read(path)
                    if extension == "zip":
                        result.snapshots[path] = snapshot
                        with zipfile.ZipFile(path) as archive:
                            record = self._archive(archive, path, (), result)
                        result.archives.append(record)
                    elif extension in self.extensions:
                        info = path.stat()
                        result.items.append(ImageItem(
                            path, name, extension, info.st_size, FileTimes.read(path),
                        ))
                        result.snapshots[path] = snapshot
                    snapshot.verify(path)
                except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, NotImplementedError, OverflowError, zlib.error) as ex:
                    result.problems.append(f"{path}: {ex}")
        result.items.sort(key=lambda item: item.location)
        return result

    def _archive(
        self, archive: zipfile.ZipFile, outer: Path, chain: tuple[str, ...], inventory: Inventory,
    ) -> ArchiveRecord:
        if len(chain) >= MAX_DEPTH:
            raise ImageWorkflowError(f"ZIP nesting limit ({MAX_DEPTH}) reached at {chain!r}")
        members = tuple(archive.infolist())
        inventory.archive_entries += len(members)
        if inventory.archive_entries > MAX_ARCHIVE_ENTRIES:
            raise ImageWorkflowError(f"Archive entry limit ({MAX_ARCHIVE_ENTRIES}) exceeded")
        size = sum(member.file_size for member in members)
        packed = max(sum(member.compress_size for member in members), 1)
        if size > BOMB_MIN_SIZE and size / packed > MAX_RATIO:
            raise ImageWorkflowError("Possible ZIP bomb: archive expansion ratio exceeded")
        paths: dict[str, bool] = {}
        for member in members:
            relative = member_path(member)
            key = relative.as_posix().casefold()
            if key in paths:
                raise ImageWorkflowError(f"Duplicate/case-conflicting ZIP member: {member.filename!r}")
            paths[key] = member.is_dir()
        for name in paths:
            parent = name.rpartition("/")[0]
            while parent:
                if parent in paths and not paths[parent]:
                    raise ImageWorkflowError(f"ZIP file/directory conflict: {name!r}")
                parent = parent.rpartition("/")[0]
        record = ArchiveRecord(outer, chain, members)
        for member in members:
            if member.is_dir():
                continue
            dates = zip_times(archive, member)
            record.timestamps[member.filename] = dates
            relative = member_path(member)
            extension = relative.suffix[1:].lower()
            if extension == "zip":
                if member.file_size > MAX_NESTED_ZIP_BYTES:
                    raise ImageWorkflowError(f"Nested ZIP exceeds {MAX_NESTED_ZIP_BYTES} bytes: {member.filename}")
                inventory.nested_bytes += member.file_size
                if inventory.nested_bytes > MAX_NESTED_TOTAL_BYTES:
                    raise ImageWorkflowError(f"Nested ZIP inspection budget ({MAX_NESTED_TOTAL_BYTES} bytes) exceeded")
                with archive.open(member) as stream:
                    payload = stream.read(MAX_NESTED_ZIP_BYTES + 1)
                if len(payload) != member.file_size or len(payload) > MAX_NESTED_ZIP_BYTES:
                    raise ImageWorkflowError(f"Nested ZIP size mismatch: {member.filename}")
                with zipfile.ZipFile(io.BytesIO(payload)) as nested:
                    record.children.append(self._archive(nested, outer, (*chain, member.filename), inventory))
            elif extension in self.extensions and not metadata_name(relative) and not any(metadata_name(Path(name)) for name in chain):
                inventory.items.append(ImageItem(
                    outer, relative.name, extension, member.file_size, dates, record, member,
                ))
        return record

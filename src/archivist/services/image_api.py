"""Versioned, non-mutating image inventory and transfer previews for Python callers."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ..core.config import IMAGE_EXTENSIONS, parse_image_filter
from .image_inventory import (
    MAX_ARCHIVE_ENTRIES, ArchiveRecord, ImageInventory, ImageItem, ImageWorkflowError,
    Inventory, checked_path, member_path,
)
from .image_transfer import overlaps, prepare_images

SCHEMA_VERSION = 1
TransferMode = Literal["move", "copy"]


class ImageApiError(ImageWorkflowError):
    """An explicit request or preparation failure with a stable adapter-facing code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InventoryRequest:
    """A read-only scan; an omitted filter selects all supported image extensions."""

    root: Path
    extensions: tuple[str, ...] | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class TransferRequest:
    """Requested effects only, never an approval or a command to execute."""

    root: Path
    destination: Path
    mode: TransferMode = "move"
    extensions: tuple[str, ...] | None = None
    leave_zip: bool = False
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class SourceLocation:
    """Unambiguous provenance; display delimiters are not used as identifiers."""

    path: str
    archive_chain: tuple[str, ...] = ()
    member: str | None = None


@dataclass(frozen=True)
class ImageRecord:
    """Detached image metadata, without payload bytes or mutable ZIP objects."""

    source: SourceLocation
    name: str
    extension: str
    size_bytes: int
    created_ns: int | None
    modified_ns: int
    ordering_timestamp_source: str


@dataclass(frozen=True)
class ArchiveInfo:
    """Counts for one archive, including nested archive provenance."""

    source: SourceLocation
    direct_images: int
    direct_members: int
    unpacked_bytes: int


@dataclass(frozen=True)
class InventoryCounts:
    """Selected occurrence counts, with each nested archive counted once."""

    disk_images: int
    archived_images: int
    selected_images: int
    outer_archives: int
    total_archives: int
    source_folders: int


@dataclass(frozen=True)
class InventoryResult:
    """A detached snapshot; complete=False is partial discovery, not zero-match success."""

    schema_version: int
    root: str
    extensions: tuple[str, ...]
    items: tuple[ImageRecord, ...]
    archives: tuple[ArchiveInfo, ...]
    counts: InventoryCounts
    complete: bool
    problems: tuple[str, ...]
    notices: tuple[str, ...]


@dataclass(frozen=True)
class TransferMapping:
    """An exact planned destination for one original image occurrence."""

    image: ImageRecord
    destination: str


@dataclass(frozen=True)
class ExtractionMember:
    """A full-extraction member and its disposition after a successful transfer."""

    source: SourceLocation
    relative_path: str
    size_bytes: int
    is_directory: bool
    selected_image: bool
    disposition: Literal["transferred", "retained", "temporary"]


@dataclass(frozen=True)
class ArchiveExtraction:
    """Complete extraction effects; copy staging has no allocated absolute path."""

    source: SourceLocation
    target: str | None
    staging_relative_path: str
    storage: Literal["source_sibling", "private_temporary"]
    archive_disposition: Literal["keep_original", "remove_after_success", "retain_extracted_container"]
    members: tuple[ExtractionMember, ...]


@dataclass(frozen=True)
class TransferPreview:
    """Immutable observations, not execution authority or a filesystem lock."""

    schema_version: int
    plan_id: str
    inventory: InventoryResult
    destination: str
    mode: TransferMode
    leave_zip: bool
    transfers: tuple[TransferMapping, ...]
    extractions: tuple[ArchiveExtraction, ...]


def _extensions(value: tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return tuple(sorted(IMAGE_EXTENSIONS))
    if not isinstance(value, tuple) or not value or any(not isinstance(part, str) or "," in part for part in value):
        raise ImageApiError("invalid_filter", "extensions must be a nonempty tuple of individual image extensions")
    try:
        return parse_image_filter(",".join(value))
    except ValueError as ex:
        raise ImageApiError("invalid_filter", str(ex)) from ex


def _path(value: Path, field: str) -> Path:
    if not isinstance(value, Path):
        raise ImageApiError("invalid_request", f"{field} must be a pathlib.Path")
    try:
        return checked_path(value)
    except (OSError, RuntimeError, ValueError) as ex:
        raise ImageApiError("invalid_path", f"Cannot use {field}: {ex}") from ex


def _version(value: int) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise ImageApiError("unsupported_version", f"schema_version must be {SCHEMA_VERSION}")


def _image(item: ImageItem) -> ImageRecord:
    return ImageRecord(
        SourceLocation(
            str(item.path), item.archive.chain if item.archive is not None else (),
            item.member.filename if item.member is not None else None,
        ),
        item.name, item.extension, item.size, item.dates.created_ns, item.dates.modified_ns,
        item.timestamp_source,
    )


def _inventory(raw: Inventory, extensions: tuple[str, ...]) -> InventoryResult:
    counts = Counter(id(item.archive) for item in raw.items if item.archive is not None)
    archives = tuple(
        ArchiveInfo(
            SourceLocation(str(record.outer), record.chain),
            counts[id(record)], len(record.members), record.unpacked_size,
        )
        for outer in raw.archives for record in outer.walk()
    )
    disk = sum(item.archive is None for item in raw.items)
    return InventoryResult(
        SCHEMA_VERSION, str(raw.root), extensions, tuple(_image(item) for item in raw.items), archives,
        InventoryCounts(
            disk, len(raw.items) - disk, len(raw.items), len(raw.archives), len(archives),
            len({item.path.parent for item in raw.items}),
        ),
        not raw.problems, tuple(raw.problems), tuple(raw.skipped),
    )


def _extractions(
    records: list[ArchiveRecord], raw: Inventory, *, copy: bool, leave_zip: bool,
) -> tuple[ArchiveExtraction, ...]:
    selected = {
        (item.archive.outer, item.archive.chain, item.member.filename)
        for item in raw.items if item.archive is not None and item.member is not None
    }
    result: list[ArchiveExtraction] = []
    for outer in records:
        for record in outer.walk():
            relative = Path()
            for component in record.chain:
                relative /= Path(component.replace("\\", "/")).with_suffix("")
            target = None if copy else str(outer.outer.with_suffix("") / relative)
            members: list[ExtractionMember] = []
            for member in record.members:
                matched = (record.outer, record.chain, member.filename) in selected
                members.append(ExtractionMember(
                    SourceLocation(str(record.outer), record.chain, member.filename),
                    (relative / member_path(member)).as_posix(),
                    member.file_size, member.is_dir(), matched,
                    "temporary" if copy else "transferred" if matched else "retained",
                ))
            disposition: Literal["keep_original", "remove_after_success", "retain_extracted_container"] = (
                "retain_extracted_container" if record.chain and not copy
                else "keep_original" if copy or leave_zip else "remove_after_success"
            )
            result.append(ArchiveExtraction(
                SourceLocation(str(record.outer), record.chain), target, relative.as_posix(),
                "private_temporary" if copy else "source_sibling", disposition, tuple(members),
            ))
    return tuple(result)


class ImageService:
    """Read-only core service; adapters must add operator access policy before exposure."""

    def __init__(
        self, *, max_entries: int | None = None, max_archive_entries: int = MAX_ARCHIVE_ENTRIES,
        source_guard: Callable[[Path], None] | None = None,
        destination_guard: Callable[[Path], None] | None = None,
    ):
        self.max_entries = max_entries
        self.max_archive_entries = max_archive_entries
        self.source_guard = source_guard
        self.destination_guard = destination_guard

    def _scan(self, root: Path, extensions: tuple[str, ...]) -> Inventory:
        root = _path(root, "root")
        if not root.is_dir():
            raise ImageApiError("invalid_root", f"Source root must be an existing directory: {root}")
        try:
            return ImageInventory(
                extensions, max_entries=self.max_entries,
                max_archive_entries=self.max_archive_entries, path_guard=self.source_guard,
            ).scan(root)
        except (OSError, ImageWorkflowError, ValueError) as ex:
            raise ImageApiError("inventory_failed", f"Cannot inventory source: {ex}") from ex

    def inventory(self, request: InventoryRequest) -> InventoryResult:
        """Read metadata only; discovery problems are retained in an incomplete result."""
        if not isinstance(request, InventoryRequest):
            raise ImageApiError("invalid_request", "Expected InventoryRequest")
        _version(request.schema_version)
        extensions = _extensions(request.extensions)
        return _inventory(self._scan(request.root, extensions), extensions)

    def prepare_transfer(self, request: TransferRequest) -> TransferPreview:
        """Plan exact effects without prompting, reporting, staging or applying them."""
        if not isinstance(request, TransferRequest):
            raise ImageApiError("invalid_request", "Expected TransferRequest")
        _version(request.schema_version)
        if request.mode not in ("move", "copy") or type(request.leave_zip) is not bool:
            raise ImageApiError("invalid_request", "mode must be move/copy and leave_zip must be boolean")
        extensions = _extensions(request.extensions)
        root = _path(request.root, "root")
        destination = _path(request.destination, "destination")
        if overlaps(root, destination):
            raise ImageApiError("invalid_destination", "Source and destination must be disjoint")
        raw = self._scan(root, extensions)
        if raw.problems:
            raise ImageApiError("incomplete_inventory", "Inventory is incomplete; inspect inventory problems before preparing a plan")
        try:
            prepared = prepare_images(
                raw, destination, copy=request.mode == "copy", max_entries=self.max_entries,
                source_guard=self.source_guard, destination_guard=self.destination_guard,
            )
            result = TransferPreview(
                SCHEMA_VERSION, uuid4().hex, _inventory(raw, extensions), str(destination),
                request.mode, request.leave_zip,
                tuple(TransferMapping(_image(entry.item), str(entry.destination)) for entry in prepared.images),
                _extractions(prepared.archives, raw, copy=request.mode == "copy", leave_zip=request.leave_zip),
            )
            raw.verify()
            return result
        except (OSError, ImageWorkflowError, ValueError) as ex:
            raise ImageApiError("preparation_failed", f"Cannot prepare transfer: {ex}") from ex

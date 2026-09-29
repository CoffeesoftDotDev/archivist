"""Operator-controlled, bounded read access for local adapters (not an OS sandbox)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Literal
from uuid import uuid4

from .image_api import (
    SCHEMA_VERSION, ImageApiError, ImageService, InventoryRequest, InventoryResult,
    TransferPreview, TransferRequest,
)
from .image_inventory import MAX_ARCHIVE_ENTRIES, checked_path

Operation = Literal["inventory", "transfer"]
Role = Literal["source", "destination"]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ReadLimits:
    """Finite operator limits; byte budgets measure encoded state, not process RSS."""

    max_entries: int = 10_000
    max_archive_entries: int = MAX_ARCHIVE_ENTRIES
    page_records: int = 100
    page_bytes: int = 64 * 1024
    snapshot_bytes: int = 8 * 1024**2
    total_bytes: int = 32 * 1024**2
    snapshots: int = 16
    ttl_seconds: int = 300

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value <= 0:
                raise ImageApiError("invalid_policy", f"{field.name} must be a positive integer")
        if self.max_archive_entries > MAX_ARCHIVE_ENTRIES:
            raise ImageApiError("invalid_policy", "Archive entry limit cannot exceed the existing safety ceiling")
        try:
            float(self.ttl_seconds)
        except OverflowError as ex:
            raise ImageApiError("invalid_policy", "ttl_seconds must fit the monotonic clock range") from ex


@dataclass(frozen=True)
class AccessPolicy:
    """Startup-only allowlists; empty roots deny the corresponding access."""

    source_roots: tuple[Path, ...] = ()
    destination_roots: tuple[Path, ...] = ()
    limits: ReadLimits = ReadLimits()

    def __post_init__(self) -> None:
        if not isinstance(self.limits, ReadLimits):
            raise ImageApiError("invalid_policy", "limits must be ReadLimits")
        for name in ("source_roots", "destination_roots"):
            roots = getattr(self, name)
            if not isinstance(roots, tuple) or any(not isinstance(root, Path) for root in roots):
                raise ImageApiError("invalid_policy", f"{name} must be a tuple of pathlib.Path directories")
            canonical: list[Path] = []
            for root in roots:
                path = _canonical(root)
                if not path.is_dir():
                    raise ImageApiError("invalid_policy", "Configured roots must be existing directories")
                canonical.append(path)
            object.__setattr__(self, name, tuple(canonical))


def _canonical(path: Path) -> Path:
    if not isinstance(path, Path):
        raise ImageApiError("invalid_request", "Filesystem paths must be pathlib.Path values")
    try:
        return checked_path(path, strict=True)
    except (OSError, RuntimeError, ValueError) as ex:
        raise ImageApiError("access_denied", "Path has an inaccessible, linked or invalid component") from ex


@dataclass(frozen=True)
class _PathState:
    path: Path
    role: Role
    identity: tuple[int, ...] | None

    @classmethod
    def read(cls, path: Path, role: Role) -> _PathState:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return cls(path, role, None)
        except OSError as ex:
            raise ImageApiError("access_denied", "Cannot inspect path metadata") from ex
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ImageApiError("access_denied", "Only regular files and directories are supported")
        return cls(path, role, (
            info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns,
        ))


class _Observation:
    def __init__(self, policy: AccessPolicy):
        self.policy = policy
        self.paths: dict[tuple[Path, Role], _PathState] = {}

    def guard(self, path: Path, role: Role) -> None:
        if not isinstance(path, Path):
            raise ImageApiError("invalid_request", "Filesystem paths must be pathlib.Path values")
        roots = self.policy.source_roots if role == "source" else self.policy.destination_roots
        if not roots:
            raise ImageApiError("access_denied", f"No {role} roots are configured")
        try:
            absolute = Path(os.path.abspath(path.expanduser()))
        except (OSError, RuntimeError, ValueError) as ex:
            raise ImageApiError("invalid_path", "Cannot expand the requested path") from ex
        if not any(absolute == root or root in absolute.parents for root in roots):
            raise ImageApiError("access_denied", f"Path is outside configured {role} roots")
        canonical = _canonical(absolute)
        if not any(canonical == root or root in canonical.parents for root in roots):
            raise ImageApiError("access_denied", f"Path is outside configured {role} roots")
        for component in (*reversed(canonical.parents), canonical):
            if not any(component == root or root in component.parents for root in roots):
                continue
            state = _PathState.read(component, role)
            key = component, role
            if key in self.paths and self.paths[key] != state:
                raise ImageApiError("stale_snapshot", "Filesystem changed; request a new observation")
            self.paths[key] = state

    def verify(self) -> None:
        for state in tuple(self.paths.values()):
            self.guard(state.path, state.role)


@dataclass(frozen=True)
class ReadPage:
    """Immutable encoded records; to_json returns the bounded wire-ready envelope."""

    snapshot_id: str
    operation: Operation
    inventory_complete: bool
    records: tuple[str, ...]
    next_cursor: str | None

    def to_json(self) -> str:
        """Serialize metadata records as JSON objects, not double-encoded strings."""
        header = _json({
            "schema_version": SCHEMA_VERSION, "snapshot_id": self.snapshot_id,
            "operation": self.operation, "inventory_complete": self.inventory_complete,
            "next_cursor": self.next_cursor,
        })
        return header[:-1] + ',"records":[' + ",".join(self.records) + "]}"


@dataclass(frozen=True)
class _Stored:
    snapshot_id: str
    operation: Operation
    complete: bool
    records: tuple[str, ...]
    paths: tuple[_PathState, ...]
    size: int
    expires: float


def _records(result: InventoryResult | TransferPreview) -> Iterator[str]:
    inventory = result.inventory if isinstance(result, TransferPreview) else result
    yield _json({
        "kind": "summary", "root": inventory.root, "extensions": inventory.extensions,
        "counts": asdict(inventory.counts),
    })
    for image in inventory.items:
        yield _json({"kind": "image", "value": asdict(image)})
    for archive in inventory.archives:
        yield _json({"kind": "archive", "value": asdict(archive)})
    for message in inventory.problems:
        yield _json({"kind": "problem", "message": message})
    for message in inventory.notices:
        yield _json({"kind": "notice", "message": message})
    if isinstance(result, TransferPreview):
        yield _json({
            "kind": "transfer_summary", "plan_id": result.plan_id,
            "destination": result.destination, "mode": result.mode, "leave_zip": result.leave_zip,
        })
        for transfer in result.transfers:
            yield _json({"kind": "transfer", "value": asdict(transfer)})
        for extraction in result.extractions:
            yield _json({
                "kind": "extraction", "source": asdict(extraction.source),
                "target": extraction.target, "staging_relative_path": extraction.staging_relative_path,
                "storage": extraction.storage, "archive_disposition": extraction.archive_disposition,
            })
            for member in extraction.members:
                yield _json({"kind": "extraction_member", "value": asdict(member)})


class BoundedImageService:
    """Metadata-only facade with per-instance roots, quotas and cursor state."""

    def __init__(self, policy: AccessPolicy):
        if not isinstance(policy, AccessPolicy):
            raise ImageApiError("invalid_policy", "Expected startup AccessPolicy")
        self._policy = policy
        self._secret = secrets.token_bytes(32)
        self._stored: dict[str, _Stored] = {}
        self._lock = RLock()
        self._roots = (
            tuple(_PathState.read(_canonical(root), "source") for root in policy.source_roots)
            + tuple(_PathState.read(_canonical(root), "destination") for root in policy.destination_roots)
        )

    def inventory(self, request: InventoryRequest) -> ReadPage:
        """Create a bounded inventory observation, explicitly retaining scan problems."""
        if not isinstance(request, InventoryRequest):
            raise ImageApiError("invalid_request", "Expected InventoryRequest")
        return self._create(request)

    def prepare_transfer(self, request: TransferRequest) -> ReadPage:
        """Create a bounded transfer observation without approval or execution."""
        if not isinstance(request, TransferRequest):
            raise ImageApiError("invalid_request", "Expected TransferRequest")
        return self._create(request)

    def _check_roots(self) -> None:
        for root in self._roots:
            current = _PathState.read(_canonical(root.path), root.role)
            if current.identity is None or root.identity is None or current.identity[:3] != root.identity[:3]:
                raise ImageApiError("access_denied", "A configured root changed; restart with reviewed policy")

    def _expire(self) -> None:
        now = monotonic()
        for key in tuple(self._stored):
            if self._stored[key].expires <= now:
                del self._stored[key]

    def _create(self, request: InventoryRequest | TransferRequest) -> ReadPage:
        with self._lock:
            self._check_roots()
            self._expire()
            limits = self._policy.limits
            if len(self._stored) >= limits.snapshots:
                raise ImageApiError("capacity_exceeded", "Observation count limit reached; wait for expiration")
            observation = _Observation(self._policy)
            observation.guard(request.root, "source")
            transfer = isinstance(request, TransferRequest)
            if isinstance(request, TransferRequest):
                observation.guard(request.destination, "destination")
            service = ImageService(
                max_entries=limits.max_entries, max_archive_entries=limits.max_archive_entries,
                source_guard=lambda path: observation.guard(path, "source"),
                destination_guard=lambda path: observation.guard(path, "destination"),
            )
            result = service.prepare_transfer(request) if isinstance(request, TransferRequest) else service.inventory(request)
            encoded: list[str] = []
            paths = tuple(observation.paths.values())
            size = len(_json([
                (str(state.path), state.role, state.identity) for state in paths
            ]).encode("utf-8"))
            for record in _records(result):
                size += len(record.encode("utf-8"))
                if size > limits.snapshot_bytes:
                    raise ImageApiError("snapshot_too_large", "Observation exceeds encoded snapshot limit; narrow the request")
                encoded.append(record)
            if size + sum(stored.size for stored in self._stored.values()) > limits.total_bytes:
                raise ImageApiError("capacity_exceeded", "Encoded memory limit reached; wait or narrow the request")
            complete = result.inventory.complete if isinstance(result, TransferPreview) else result.complete
            stored = _Stored(
                uuid4().hex, "transfer" if transfer else "inventory", complete, tuple(encoded),
                paths, size, 0,
            )
            # Reject an oversized later record before exposing a cursor that cannot advance.
            for index in range(len(stored.records)):
                self._page(stored, index, single=True)
            page = self._page(stored, 0)
            observation.verify()
            self._check_roots()
            self._stored[stored.snapshot_id] = replace(stored, expires=monotonic() + limits.ttl_seconds)
            return page

    def _cursor(self, snapshot_id: str, offset: int) -> str:
        data = f"{snapshot_id}.{offset}"
        signature = hmac.new(self._secret, data.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{data}.{signature}"

    def _page(self, stored: _Stored, offset: int, *, single: bool = False) -> ReadPage:
        limits = self._policy.limits
        selected: list[str] = []
        last: ReadPage | None = None
        count = 1 if single else limits.page_records
        for index in range(offset, min(offset + count, len(stored.records))):
            selected.append(stored.records[index])
            cursor = self._cursor(stored.snapshot_id, index + 1) if index + 1 < len(stored.records) else None
            candidate = ReadPage(stored.snapshot_id, stored.operation, stored.complete, tuple(selected), cursor)
            if len(candidate.to_json().encode("utf-8")) > limits.page_bytes:
                break
            last = candidate
        if last is None:
            raise ImageApiError("response_too_large", "A metadata record exceeds the response limit; narrow the request")
        return last

    def page(self, cursor: str) -> ReadPage:
        """Read the same observation; foreign, expired or stale cursors fail explicitly."""
        with self._lock:
            if not isinstance(cursor, str) or len(cursor) > 128 or not cursor.isascii():
                raise ImageApiError("invalid_cursor", "Expected a cursor issued by this service instance")
            parts = cursor.split(".")
            if len(parts) != 3 or not parts[1].isascii() or not parts[1].isdigit():
                raise ImageApiError("invalid_cursor", "Malformed cursor")
            snapshot_id, offset_text, _ = parts
            offset = int(offset_text)
            expected = self._cursor(snapshot_id, offset) if snapshot_id.isascii() else ""
            if not expected or not hmac.compare_digest(cursor, expected):
                raise ImageApiError("invalid_cursor", "Cursor does not belong to this service instance")
            stored = self._stored.get(snapshot_id)
            if stored is not None and stored.expires <= monotonic():
                self._expire()
                raise ImageApiError("expired_cursor", "Observation expired; request a new one")
            self._expire()
            if stored is None:
                raise ImageApiError("unknown_cursor", "Observation is no longer available")
            if not 0 < offset < len(stored.records):
                raise ImageApiError("invalid_cursor", "Cursor offset is outside the observation")
            self._check_roots()
            observation = _Observation(self._policy)
            observation.paths = {(state.path, state.role): state for state in stored.paths}
            observation.verify()
            return self._page(stored, offset)

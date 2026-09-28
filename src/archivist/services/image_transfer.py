"""Approval-bound image plans, complete archive extraction, and non-overwriting transfers."""
from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import tempfile
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

from ..core import Config, get_logger
from ..core.config import IMAGE_EXTENSIONS
from ..utils import FileTimes, is_readonly, make_remover
from .image_inventory import (
    ArchiveRecord, ImageInventory, ImageItem, ImageWorkflowError, Inventory, Snapshot, checked_path, member_path, zip_times,
)
from .zip_extractor import FREE_SPACE_RESERVE

log = get_logger("images")
ConfirmImages = Callable[[str], bool]


def overlaps(left: Path, right: Path) -> bool:
    """Whether two resolved paths are equal or one contains the other."""
    return left == right or left in right.parents or right in left.parents


@dataclass(frozen=True)
class PlannedImage:
    """An original occurrence and its exact approved destination."""

    item: ImageItem
    destination: Path


def plan_names(items: list[ImageItem], destination: Path) -> list[PlannedImage]:
    """Allocate oldest-first collision names, reserving existing and incoming names."""
    occupied = {entry.name.casefold() for entry in destination.iterdir()} if destination.exists() else set()
    groups: dict[str, list[ImageItem]] = defaultdict(list)
    for item in items:
        member_path(zipfile.ZipInfo(item.name))
        groups[item.name.casefold()].append(item)
    reserved = occupied | set(groups)
    result: list[PlannedImage] = []
    for key, group in sorted(groups.items()):
        for item in sorted(group, key=lambda value: (value.dates.ordering_ns, value.location)):
            if len(group) == 1 and key not in occupied:
                name = item.name
            else:
                original = Path(item.name)
                number = 1
                while True:
                    name = f"{original.stem} ({number:03d}){original.suffix}"
                    if name.casefold() not in reserved:
                        break
                    number += 1
            reserved.add(name.casefold())
            result.append(PlannedImage(item, destination / name))
    return result


def copy_bytes(source: BinaryIO, destination: BinaryIO, expected: int) -> None:
    """Stream exactly the expected bytes, failing on size drift or corrupt ZIP reads."""
    written = 0
    while chunk := source.read(min(1024**2, expected - written + 1)):
        written += len(chunk)
        if written > expected:
            raise ImageWorkflowError("Source exceeds its approved size")
        destination.write(chunk)
    if written != expected:
        raise ImageWorkflowError(f"Source size changed: expected {expected}, read {written}")


class ImageRun:
    """State shared by inventory, approval, extraction and transfer workflow commands."""

    def __init__(self, config: Config, confirm: ConfirmImages | None = None):
        self.config = config
        self.confirm = confirm
        self.inventory: Inventory | None = None
        self.destination: Path | None = None
        self.report_path: Path | None = None
        self.report_stream: TextIO | None = None
        self.plan: list[PlannedImage] = []
        self.selected_archives: list[ArchiveRecord] = []
        self.targets: dict[Path, Path] = {}
        self.materialized: dict[str, Path] = {}
        self.materialized_snapshots: dict[str, Snapshot] = {}
        self.archives_to_delete: list[Path] = []
        self.temporary: tempfile.TemporaryDirectory | None = None
        self.approved = False
        self.completed = 0
        self.extracted = 0
        self.deleted = 0
        self.failed = 0
        self.exit_code = 0

    def emit(self, message: str, *, error: bool = False) -> None:
        """Emit the same escaped inventory/execution information to console and report."""
        (log.error if error else log.info)(message)
        if self.report_stream is not None:
            try:
                self.report_stream.write(message + "\n")
                self.report_stream.flush()
            except OSError as ex:
                stream, self.report_stream = self.report_stream, None
                try:
                    stream.close()
                except OSError as close_error:
                    log.error(f"Could not close failed report: {close_error}")
                raise ImageWorkflowError(f"Cannot write inventory report {self.report_path}: {ex}") from ex

    def list(self, root: Path) -> dict[str, int]:
        """Inventory and report only; no destination or extraction directory is created."""
        self.config.validate_actions()
        root = checked_path(root)
        if self.config.destination is not None:
            self.destination = checked_path(self.config.destination)
            if overlaps(root, self.destination):
                raise ImageWorkflowError("Source and destination must be disjoint (neither may contain the other)")
            if self.destination.exists() and not self.destination.is_dir():
                raise ImageWorkflowError(f"Destination is not a directory: {self.destination}")
        self.inventory = ImageInventory(self.config.image_filter).scan(root)
        self._open_report()
        self.emit("=== Picture inventory ===")
        self.emit("name | type | full source location | ordering timestamp source")
        for item in self.inventory.items:
            self.emit(json.dumps({
                "name": item.name, "type": item.extension, "path": item.location,
                "ordering_timestamp": item.timestamp, "timestamp_source": item.timestamp_source,
                "creation_time_ns": item.dates.created_ns, "modification_time_ns": item.dates.modified_ns,
            }, ensure_ascii=True))
        for outer in self.inventory.archives:
            for archive in outer.walk():
                count = sum(item.archive is archive for item in self.inventory.items)
                self.emit(f"Archive images (direct entries): {count} | {json.dumps(archive.location)}")
        for notice in self.inventory.skipped:
            self.emit(notice)
        for problem in self.inventory.problems:
            self.emit(f"INCOMPLETE: {problem}", error=True)
        counts = self._inventory_counts()
        for label, count in counts.items():
            self.emit(f"{label}: {count}")
        self.emit(f"Inventory report: {self.report_path}" if self.report_path else "Inventory report: console only")
        if self.inventory.problems:
            raise ImageWorkflowError("Inventory is incomplete; no extraction or transfer is permitted")
        return counts

    def _open_report(self) -> None:
        assert self.inventory is not None
        if self.config.log_file is None:
            return
        raw = self.config.log_file
        candidate = Path(raw).expanduser() if raw else self.inventory.root / "pictures.log"
        if raw and (candidate.is_dir() or raw.endswith(("/", "\\"))):
            candidate /= "pictures.log"
        candidate = checked_path(candidate)
        if candidate.suffix[1:].lower() in IMAGE_EXTENSIONS | {"zip"}:
            raise ImageWorkflowError(f"Report must not target an image or ZIP: {candidate}")
        if self.destination is not None and (candidate == self.destination or self.destination in candidate.parents):
            raise ImageWorkflowError("Report cannot create or alter the picture destination before approval")
        if candidate.exists():
            if not candidate.is_file():
                raise ImageWorkflowError(f"Report is not a regular file: {candidate}")
            if any(candidate.samefile(source) for source in self.inventory.protected_sources):
                raise ImageWorkflowError(f"Report is a hardlink to a source image or ZIP: {candidate}")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        checked_path(candidate)
        identities = {(source.stat().st_dev, source.stat().st_ino) for source in self.inventory.protected_sources}
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags, 0o666)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) in identities:
                raise ImageWorkflowError(f"Report opened a source or nonregular file: {candidate}")
            self.report_stream = os.fdopen(descriptor, "a", encoding="utf-8")
        except BaseException:
            os.close(descriptor)
            raise
        self.report_path = candidate

    def _inventory_counts(self) -> dict[str, int]:
        assert self.inventory is not None
        return {
            "Images on disk": sum(item.archive is None for item in self.inventory.items),
            "Images inside ZIPs": sum(item.archive is not None for item in self.inventory.items),
            "Images selected": len(self.inventory.items),
            "Source folders impacted": len({item.path.parent for item in self.inventory.items}),
            "Inventory errors": len(self.inventory.problems),
        }

    def approve(self, root: Path) -> dict[str, int]:
        """Prepare exact effects and require a human decision before any extraction."""
        assert self.inventory is not None
        config = self.config
        if not config.apply:
            return {}
        if config.move_images and not self.inventory.items:
            self.emit("No matching pictures; no extraction, transfer, or ZIP deletion.")
            return {}
        self.inventory.verify()
        if config.move_images:
            assert self.destination is not None
            self.plan = plan_names(self.inventory.items, self.destination)
        selected_outer = {item.path for item in self.inventory.items if item.archive is not None}
        self.selected_archives = [
            archive for archive in self.inventory.archives
            if not config.move_images or archive.outer in selected_outer
        ]
        for archive in self.selected_archives:
            self._check_nested_targets(archive)
            if not config.copy:
                target = archive.outer.with_suffix("")
                member_path(zipfile.ZipInfo(target.name))
                checked_path(target)
                if os.path.lexists(target):
                    raise ImageWorkflowError(f"Extraction target already exists; no merge/overwrite permitted: {target}")
                self.targets[archive.outer] = target
        self._verify_targets()
        mode = "COPY" if config.copy else "MOVE" if config.move_images else "EXTRACT"
        self.emit(f"Planned mode: {mode}")
        self.emit(f"Source root: {self.inventory.root}")
        for label, count in self._inventory_counts().items():
            self.emit(f"{label}: {count}")
        self.emit(f"Extensions: {dict(sorted(Counter(item.extension for item in self.inventory.items).items()))}")
        self.emit(f"Destination: {self.destination or '(archive sibling folders)'}")
        for entry in self.plan:
            self.emit(f"Planned {mode}: {json.dumps(entry.item.location)} -> {json.dumps(str(entry.destination))}")
        self.emit("Extraction: all archive contents; all extraction finishes before picture transfer.")
        for archive in self.selected_archives:
            self.emit(f"Extract: {json.dumps(str(archive.outer))} -> {'temporary storage outside source' if config.copy else self.targets[archive.outer]}")
        deletion = not config.copy and not config.leave_zip
        self.emit(f"ZIP disposition: {'delete only after complete extraction and successful transfer' if deletion else 'keep originals'}")
        if deletion:
            for archive in self.selected_archives:
                self.emit(f"May remove ZIP after success: {json.dumps(str(archive.outer))}")
        if self.confirm is None or not self.confirm(f"Proceed with {mode} and the effects listed above? [y/N]: "):
            self.emit("Not approved; no extraction or transfer performed.")
            self.exit_code = 1
            return {"Approval declined": 1}
        self.inventory.verify()
        self._verify_targets()
        self.approved = True
        return {"Approval granted": 1}

    @staticmethod
    def _check_nested_targets(archive: ArchiveRecord) -> None:
        names = {member_path(member).as_posix().casefold() for member in archive.members}
        for child in archive.children:
            member = next(member for member in archive.members if member.filename == child.chain[-1])
            target = member_path(member).with_suffix("").as_posix().casefold()
            if target in names or any(name.startswith(target + "/") for name in names):
                raise ImageWorkflowError(f"Nested extraction target conflicts with archive content: {child.location}")
            ImageRun._check_nested_targets(child)

    def _verify_targets(self) -> None:
        if self.destination is not None:
            checked_path(self.destination)
            if self.destination.exists() and not self.destination.is_dir():
                raise ImageWorkflowError(f"Destination changed: {self.destination}")
            existing = {path.name.casefold() for path in self.destination.iterdir()} if self.destination.exists() else set()
            for entry in self.plan:
                if entry.destination.name.casefold() in existing:
                    raise ImageWorkflowError(f"Planned destination is now occupied; run again: {entry.destination}")
        for target in self.targets.values():
            checked_path(target)
            if os.path.lexists(target):
                raise ImageWorkflowError(f"Planned extraction target is now occupied: {target}")

    def extract(self, root: Path) -> dict[str, int]:
        """Fully materialize approved archives before allowing the transfer stage."""
        if not self.approved:
            return {}
        assert self.inventory is not None
        self.inventory.verify()
        self._verify_targets()
        if self.config.copy and self.selected_archives:
            temp_parent = checked_path(Path(tempfile.gettempdir()))
            if self.inventory.root == temp_parent or self.inventory.root in temp_parent.parents:
                temp_parent = self.inventory.root.parent
            if self.destination is not None and (self.destination == temp_parent or self.destination in temp_parent.parents):
                raise ImageWorkflowError("No safe temporary directory outside source and destination")
            self.temporary = tempfile.TemporaryDirectory(prefix="archivist-images-", dir=temp_parent)
        for index, archive in enumerate(self.selected_archives):
            self.inventory.snapshots[archive.outer].verify(archive.outer)
            target = (
                Path(self.temporary.name) / str(index) if self.temporary is not None
                else self.targets[archive.outer]
            )
            parent = target.parent
            free = shutil.disk_usage(parent).free
            if archive.unpacked_size * 2 + FREE_SPACE_RESERVE > free:
                raise ImageWorkflowError(f"Not enough space to fully extract {archive.outer}")
            with tempfile.TemporaryDirectory(prefix=".archivist-images-", dir=parent) as temporary:
                staged = Path(temporary) / "contents"
                staged.mkdir()
                archive_paths: dict[str, Path] = {}
                self._extract_archive(archive, archive.outer, staged, archive_paths)
                self.inventory.snapshots[archive.outer].verify(archive.outer)
                checked_path(target)
                if os.path.lexists(target):
                    raise ImageWorkflowError(f"Extraction target appeared after approval: {target}")
                # mkdir is exclusive on every platform; never replace an existing tree.
                target.mkdir()
                original_dates = {
                    f"{record.location} :: {name}": dates
                    for record in archive.walk() for name, dates in record.timestamps.items()
                }
                self._publish_extraction(staged, target, {
                    path: original_dates[location] for location, path in archive_paths.items()
                })
                for location, path in archive_paths.items():
                    actual = target / path.relative_to(staged)
                    self.materialized[location] = actual
            # Removing staging hardlinks changes POSIX ctime, so snapshot after cleanup.
            for location in archive_paths:
                self.materialized_snapshots[location] = Snapshot.read(self.materialized[location])
            self.extracted += sum(1 for _ in archive.walk())
            self.archives_to_delete.append(archive.outer)
            self.emit(f"Fully extracted: {json.dumps(str(archive.outer))}")
        return {"ZIPs fully extracted": self.extracted}

    @staticmethod
    def _publish_extraction(staged: Path, target: Path, dates: dict[Path, FileTimes]) -> None:
        """Publish staged files without replacing anything added by another process."""
        for source in sorted(staged.rglob("*")):
            destination = target / source.relative_to(staged)
            checked_path(destination.parent)
            if source.is_dir():
                destination.mkdir()
                continue
            try:
                os.link(source, destination)
            except OSError as ex:
                if ex.errno not in (errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS):
                    raise
                with source.open("rb") as incoming, destination.open("xb") as outgoing:
                    copy_bytes(incoming, outgoing, source.stat().st_size)
                shutil.copystat(source, destination)
            dates[source].restore(destination)

    def _extract_archive(
        self, record: ArchiveRecord, source: Path, target: Path, paths: dict[str, Path],
    ) -> None:
        with zipfile.ZipFile(source) as archive:
            current = archive.infolist()
            signatures = lambda members: [(m.filename, m.CRC, m.file_size, m.compress_size, m.date_time, m.extra) for m in members]
            if signatures(current) != signatures(record.members):
                raise ImageWorkflowError(f"Archive directory changed: {record.location}")
            for member in current:
                destination = target / member_path(member)
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                dates = zip_times(archive, member)
                if dates != record.timestamps[member.filename]:
                    raise ImageWorkflowError(f"Archive timestamps changed: {record.location} :: {member.filename}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as incoming, destination.open("xb") as outgoing:
                    copy_bytes(incoming, outgoing, member.file_size)
                dates.restore(destination)
                paths[f"{record.location} :: {member.filename}"] = destination
        for child in record.children:
            nested_member = next(member for member in record.members if member.filename == child.chain[-1])
            nested = target / member_path(nested_member)
            nested_target = nested.with_suffix("")
            nested_target.mkdir()
            self._extract_archive(child, nested, nested_target, paths)

    def transfer(self, root: Path) -> dict[str, int]:
        """Copy exclusively, then remove move sources, stopping on the first failure."""
        if not self.approved:
            return {}
        assert self.inventory is not None
        self.inventory.verify()
        if self.plan:
            assert self.destination is not None
            checked_path(self.destination)
            self._verify_destination_names()
            self.destination.mkdir(parents=True, exist_ok=True)
        for entry in self.plan:
            item = entry.item
            source = self.materialized[item.location] if item.archive is not None else item.path
            snapshot = self.materialized_snapshots[item.location] if item.archive is not None else self.inventory.snapshots[item.path]
            snapshot.verify(source)
            checked_path(entry.destination.parent)
            existing = {path.name.casefold() for path in entry.destination.parent.iterdir()}
            if entry.destination.name.casefold() in existing:
                raise ImageWorkflowError(f"Destination appeared after approval: {entry.destination}")
            if not self.config.copy and is_readonly(source):
                raise ImageWorkflowError(f"Move source is read-only; left untouched: {source}")
            created = False
            destination_complete = False
            try:
                with source.open("rb") as incoming, entry.destination.open("xb") as outgoing:
                    created = True
                    copy_bytes(incoming, outgoing, item.size)
                snapshot.verify(source)
                shutil.copystat(source, entry.destination)
                item.dates.restore(entry.destination)
                destination_complete = True
                if not self.config.copy:
                    source.unlink()
            except BaseException:
                if destination_complete:
                    self.emit(f"Complete destination retained after transfer failure; check source before retrying: {entry.destination}", error=True)
                elif created:
                    # Only our incomplete destination is removed; never a preexisting file.
                    try:
                        entry.destination.unlink()
                    except OSError as cleanup_error:
                        self.emit(f"Could not remove incomplete destination {entry.destination}: {cleanup_error}", error=True)
                raise
            self.completed += 1
            self.emit(f"{'Copied' if self.config.copy else 'Moved'}: {json.dumps(item.location)} -> {json.dumps(str(entry.destination))}")
        self._dispose_archives()
        return self.outcomes()

    def _verify_destination_names(self) -> None:
        assert self.destination is not None
        existing = {path.name.casefold() for path in self.destination.iterdir()} if self.destination.exists() else set()
        for entry in self.plan:
            if entry.destination.name.casefold() in existing:
                raise ImageWorkflowError(f"Planned destination is occupied: {entry.destination}")

    def _dispose_archives(self) -> None:
        if self.config.copy or self.config.leave_zip:
            return
        assert self.inventory is not None
        # Verify every original before deleting any of them.
        for path in self.archives_to_delete:
            self.inventory.snapshots[path].verify(path)
            if is_readonly(path) and not self.config.force_readonly:
                raise ImageWorkflowError(f"ZIP is read-only; all not-yet-removed originals retained: {path}")
        remover = make_remover(to_trash=self.config.send_to_bin, force_readonly=self.config.force_readonly)
        for path in self.archives_to_delete:
            if not remover.remove_file(path):
                raise ImageWorkflowError(f"ZIP could not be removed (read-only); retained: {path}")
            self.deleted += 1
            self.emit(f"{remover.verb} ZIP after success: {json.dumps(str(path))}")

    def outcomes(self) -> dict[str, int]:
        """Return actual transfer progress, never planned counts as completed counts."""
        if not self.config.apply or not (self.config.move_images or self.config.extract_zip):
            return {"Workflow errors": self.failed}
        planned = len(self.inventory.items) if self.inventory is not None and self.config.move_images else 0
        return {
            "Images planned": planned,
            "Images copied" if self.config.copy else "Images moved": self.completed,
            "Images remaining": planned - self.completed,
            "Workflow errors": self.failed,
            "ZIPs fully extracted": self.extracted,
            "ZIPs removed": self.deleted,
        }

    def cleanup(self) -> None:
        """Remove only this run's private copy-mode staging."""
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None

    def close(self) -> None:
        """Close the inventory/execution report."""
        if self.report_stream is not None:
            self.report_stream.close()

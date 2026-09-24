"""ZIP extraction service."""
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core import get_logger
from ..utils import Remover, find_files, format_size, is_link, is_readonly

log = get_logger("zip")

MAX_DEPTH = 10  # stops archives that contain themselves
MAX_RATIO = 100  # photos and videos barely compress; ZIP bombs expand 1000x or more
BOMB_MIN_SIZE = 1024**3  # the ratio check only applies above 1 GB, so small text files never trip it
FREE_SPACE_RESERVE = 100 * 1024**2  # always leave at least 100 MB free
STAGING_SUFFIX = ".archivist-tmp"

ConfirmMerge = Callable[[Path, Path], bool]
"""(zip_path, existing_folder) -> True to extract the archive into the folder, overwriting its files."""


@dataclass
class ExtractionResult:
    found: int = 0
    extracted: int = 0
    skipped_existing: int = 0  # target folder (or file) already there, and not merged
    overwritten: int = 0  # files replaced while extracting into existing folders


class ZipExtractor:
    """Finds ZIP archives and extracts each into a sibling folder."""

    def __init__(
        self,
        remover: Remover,
        delete_archive: bool = True,
        dry_run: bool = False,
        confirm_merge: ConfirmMerge | None = None,
    ):
        self.remover = remover
        self.delete_archive = delete_archive
        self.dry_run = dry_run
        self.confirm_merge = confirm_merge  # None: never extract into an existing folder

    def find_archives(self, root: Path) -> list[Path]:
        return sorted(find_files(root, "*.zip"))

    def extract_all(self, root: Path) -> ExtractionResult:
        """Extract every ZIP under root, then the ZIPs that come out of them."""
        result = ExtractionResult()
        pending = self.find_archives(root)
        log.info(f"Found {len(pending)} archive(s).")
        depth = 0
        while pending:
            if depth == MAX_DEPTH:
                log.warning(f"Stopped at nesting depth {MAX_DEPTH}: {len(pending)} archive(s) left unextracted.")
                break
            log.info("")
            nested: list[Path] = []
            blocked: list[Path] = []
            for index, zip_path in enumerate(pending, start=1):
                log.info(f"[{index}/{len(pending)}]")
                target_folder = zip_path.with_suffix("")
                if os.path.lexists(target_folder):
                    log.info(f"[ZIP] {zip_path}")
                    log.warning(" Target already exists -> listed after this pass")
                    blocked.append(zip_path)
                elif self.extract(zip_path):
                    result.extracted += 1
                    # A dry run creates no folder, so there is nothing nested to find.
                    if not self.dry_run:
                        nested += self.find_archives(target_folder)
            nested += self._handle_existing(blocked, result)
            result.found += len(pending)
            depth += 1
            pending = nested
            if pending:
                log.info("")
                log.info(f"Found {len(pending)} nested archive(s).")
        return result

    def _handle_existing(self, blocked: list[Path], result: ExtractionResult) -> list[Path]:
        """List the archives whose target exists, offer to merge them, and return the ZIPs merged in."""
        if not blocked:
            return []
        log.info("")
        log.info(f"{len(blocked)} archive(s) skipped because the target already exists:")
        mergeable = []
        for zip_path in blocked:
            target = zip_path.with_suffix("")
            if target.is_dir() and not is_link(target):
                mergeable.append(zip_path)
                log.info(f"  {zip_path} -> existing folder {target.name}")
            else:
                log.info(f"  {zip_path} -> {target.name} is a file or link, not a folder")
        if mergeable and self.dry_run:
            log.info(" Would ask whether to extract them into the existing folders")
        elif mergeable and self.confirm_merge is None:
            log.info(" Run Archivist in a terminal to choose whether to extract them into the existing folders")

        nested: list[Path] = []
        for zip_path in blocked:
            merged = None
            if zip_path in mergeable and not self.dry_run and self.confirm_merge is not None:
                if self.confirm_merge(zip_path, zip_path.with_suffix("")):
                    merged = self.merge(zip_path)
                else:
                    log.info(f"[ZIP] {zip_path}: skipped, existing folder kept")
            if merged is None:
                result.skipped_existing += 1
                continue
            written, overwritten = merged
            result.extracted += 1
            result.overwritten += overwritten
            nested += sorted(path for path in written if path.suffix.lower() == ".zip")
        return nested

    def merge(self, zip_path: Path) -> tuple[list[Path], int] | None:
        """
        Extract zip_path into its existing sibling folder, overwriting files with the same name.
        Everything is extracted and checked before the folder is touched.
        Returns (files written, files overwritten), or None when the archive was skipped.
        """
        target_folder = zip_path.with_suffix("")
        log.info(f"[ZIP] {zip_path}")
        log.info(f" Extracting into the existing folder {target_folder}")
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                problem = self._check(archive, zip_path.parent)
                if problem:
                    log.error(f" Skipped: {problem}")
                    return None
                staging = self._new_staging(target_folder)
                try:
                    self._extract_members(archive, staging)
                    problem = self._merge_problem(staging, target_folder)
                    if problem:
                        log.error(f" Skipped, existing folder unchanged: {problem}")
                        return None
                    written, overwritten = self._move_into(staging, target_folder)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging, ignore_errors=True)
        except Exception as ex:
            log.error(f" ERROR: {ex}")
            return None
        log.info(f" Extraction completed ({overwritten} file(s) overwritten)")
        self._dispose(zip_path)
        return written, overwritten

    def _merge_problem(self, staging: Path, target_folder: Path) -> str | None:
        """Why the staged files cannot be moved into target_folder, or None."""
        for staged in sorted(staging.rglob("*")):
            existing = target_folder / staged.relative_to(staging)
            if not os.path.lexists(existing):
                continue
            if is_link(existing):
                return f"{existing} is a link or junction"
            if staged.is_dir() != existing.is_dir():
                kinds = ("a folder", "a file") if staged.is_dir() else ("a file", "a folder")
                return f"{existing} is {kinds[1]} in the existing folder but {kinds[0]} in the ZIP"
            if existing.is_file() and is_readonly(existing) and not self.remover.force_readonly:
                return f"{existing} is read-only (use --force-readonly-deletion)"
        return None

    def _move_into(self, staging: Path, target_folder: Path) -> tuple[list[Path], int]:
        written: list[Path] = []
        overwritten = 0
        for staged in sorted(staging.rglob("*")):  # parents sort before their children
            destination = target_folder / staged.relative_to(staging)
            if staged.is_dir():
                destination.mkdir(exist_ok=True)
                continue
            if not destination.exists():
                shutil.move(staged, destination)
            else:
                # Bring the new copy next to the old one first: if that fails, the old copy is untouched.
                incoming = destination.with_name(f".{destination.name}.{os.getpid()}{STAGING_SUFFIX}")
                shutil.move(staged, incoming)
                try:
                    if not self.remover.remove_file(destination):
                        raise PermissionError(f"{destination} is read-only")
                except BaseException:
                    incoming.unlink(missing_ok=True)
                    raise
                os.replace(incoming, destination)
                log.info(f" Overwritten: {destination} (old copy: {self.remover.verb.lower()})")
                overwritten += 1
            written.append(destination)
        return written, overwritten

    def extract(self, zip_path: Path) -> bool:
        """Extract zip_path into a sibling folder, restore timestamps, then remove or keep the ZIP."""
        target_folder = zip_path.with_suffix("")
        log.info(f"[ZIP] {zip_path}")

        if target_folder.exists():
            log.warning(" Target folder already exists -> skipping")
            return False

        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                problem = self._check(archive, zip_path.parent)
                if problem:
                    log.error(f" Skipped: {problem}")
                    return False
                if self.dry_run:
                    self._preview(archive, target_folder)
                else:
                    self._extract_to(archive, target_folder)
        except Exception as ex:
            log.error(f" ERROR: {ex}")
            return False

        self._dispose(zip_path)
        return True

    def _extract_to(self, archive: zipfile.ZipFile, target_folder: Path) -> None:
        """Extract into a hidden staging folder renamed at the end, so a failure leaves nothing behind."""
        staging = self._new_staging(target_folder)
        try:
            self._extract_members(archive, staging)
            staging.rename(target_folder)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        log.info(" Extraction completed")

    @staticmethod
    def _new_staging(target_folder: Path) -> Path:
        staging = target_folder.with_name(f".{target_folder.name}{STAGING_SUFFIX}")
        if staging.exists():
            shutil.rmtree(staging)  # left by a run that was killed
        staging.mkdir()
        return staging

    def _extract_members(self, archive: zipfile.ZipFile, staging: Path) -> None:
        for member in archive.infolist():
            # Use the returned path: zipfile strips "../" from member names.
            extracted = Path(archive.extract(member, staging))
            if extracted.is_file():
                self._restore_timestamp(member, extracted)

    @staticmethod
    def _check(archive: zipfile.ZipFile, destination: Path) -> str | None:
        """Why the archive must not be extracted, or None."""
        members = archive.infolist()
        size = sum(m.file_size for m in members)
        packed = max(sum(m.compress_size for m in members), 1)
        if size > BOMB_MIN_SIZE and size / packed > MAX_RATIO:
            return f"it would expand {size / packed:.0f}x to {format_size(size)} (possible ZIP bomb)"
        free = shutil.disk_usage(destination).free
        if size + FREE_SPACE_RESERVE > free:
            return (
                f"it needs {format_size(size)} plus {format_size(FREE_SPACE_RESERVE)} spare, "
                f"and only {format_size(free)} is free"
            )
        return None

    def _dispose(self, zip_path: Path) -> None:
        if not self.delete_archive:
            log.info(" ZIP kept")
            return
        try:
            if self.remover.remove_file(zip_path):
                log.info(f" {self.remover.verb}: {zip_path.name}")
            else:
                log.warning(" ZIP is read-only -> kept (use --force-readonly-deletion)")
        except Exception as ex:
            log.error(f" Could not remove {zip_path.name}: {ex}")

    @staticmethod
    def _preview(archive: zipfile.ZipFile, target_folder: Path) -> None:
        members = archive.infolist()
        size = format_size(sum(m.file_size for m in members))
        nested = sum(m.filename.lower().endswith(".zip") for m in members)
        note = f", including {nested} nested ZIP(s)" if nested else ""
        log.info(f" Would extract {len(members)} item(s) ({size}) to {target_folder}{note}")

    @staticmethod
    def _restore_timestamp(zip_info: zipfile.ZipInfo, path: Path) -> None:
        try:
            ts = datetime(*zip_info.date_time).timestamp()
            os.utime(path, (ts, ts))
        except Exception as ex:
            log.warning(f" Warning: could not restore timestamp for {path}: {ex}")

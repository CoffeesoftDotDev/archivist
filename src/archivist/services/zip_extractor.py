"""ZIP extraction service."""
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from ..core import get_logger
from ..utils import Remover, find_files, format_size

log = get_logger("zip")

MAX_DEPTH = 10  # stops archives that contain themselves
MAX_RATIO = 100  # photos and videos barely compress; ZIP bombs expand 1000x or more
BOMB_MIN_SIZE = 1024**3  # the ratio check only applies above 1 GB, so small text files never trip it
FREE_SPACE_RESERVE = 100 * 1024**2  # always leave at least 100 MB free
STAGING_SUFFIX = ".archivist-tmp"


class ZipExtractor:
    """Finds ZIP archives and extracts each into a sibling folder."""

    def __init__(self, remover: Remover, delete_archive: bool = True, dry_run: bool = False):
        self.remover = remover
        self.delete_archive = delete_archive
        self.dry_run = dry_run

    def find_archives(self, root: Path) -> list[Path]:
        return sorted(find_files(root, "*.zip"))

    def extract_all(self, root: Path) -> tuple[int, int]:
        """Extract every ZIP under root, then the ZIPs that come out of them. Returns (found, extracted)."""
        pending = self.find_archives(root)
        log.info(f"Found {len(pending)} archive(s).")
        found = extracted = depth = 0
        while pending:
            if depth == MAX_DEPTH:
                log.warning(f"Stopped at nesting depth {MAX_DEPTH}: {len(pending)} archive(s) left unextracted.")
                break
            log.info("")
            new_folders = []
            for index, zip_path in enumerate(pending, start=1):
                log.info(f"[{index}/{len(pending)}]")
                if self.extract(zip_path):
                    extracted += 1
                    new_folders.append(zip_path.with_suffix(""))
            found += len(pending)
            depth += 1
            # Nested archives can only be in folders this pass created, and a dry run creates none.
            pending = [] if self.dry_run else [z for folder in new_folders for z in self.find_archives(folder)]
            if pending:
                log.info("")
                log.info(f"Found {len(pending)} nested archive(s).")
        return found, extracted

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
        staging = target_folder.with_name(f".{target_folder.name}{STAGING_SUFFIX}")
        if staging.exists():
            shutil.rmtree(staging)  # left by a run that was killed
        try:
            staging.mkdir()
            for member in archive.infolist():
                # Use the returned path: zipfile strips "../" from member names.
                extracted = Path(archive.extract(member, staging))
                if extracted.is_file():
                    self._restore_timestamp(member, extracted)
            staging.rename(target_folder)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        log.info(" Extraction completed")

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

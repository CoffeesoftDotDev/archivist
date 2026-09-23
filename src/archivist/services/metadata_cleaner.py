"""Cleanup service for macOS (._*, .DS_Store), Windows (Thumbs.db, desktop.ini) and Synology (@eaDir) metadata."""
from pathlib import Path

from ..core import get_logger
from ..utils import Remover, find_files, is_hidden

log = get_logger("cleaner")


class MetadataCleaner:
    """Finds metadata files/folders; the remover decides if they are deleted, binned or only reported."""

    def __init__(self, remover: Remover):
        self.remover = remover

    # ---- public actions -------------------------------------------------

    def remove_appledouble_files(self, root: Path, max_size: int) -> int:
        """Remove '._*' files of max_size bytes or less."""
        return self._remove_files(root, "._*", max_size=max_size)

    def remove_files_named(self, root: Path, filename: str) -> int:
        """Remove every file called filename, in any case (e.g. Thumbs.db)."""
        return self._remove_files(root, filename)

    def remove_metadata_folders(self, root: Path) -> int:
        """Remove '._*' folders that contain no visible files (deepest first)."""
        removed = 0
        folders = sorted(
            (p for p in root.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for folder in folders:
            if not folder.exists() or not self._is_removable_metadata_folder(folder):
                continue
            try:
                self.remover.remove_tree(folder)
                log.info(f"[CLEANUP] {self.remover.verb}: {folder}")
                removed += 1
            except Exception as ex:
                log.error(f"[CLEANUP] Failed: {folder} ({ex})")
        return removed

    def remove_eadir_folders(self, root: Path) -> int:
        """Remove all Synology '@eaDir' folders; shallowest first, so a nested one counts once."""
        removed: list[Path] = []
        for folder in sorted(root.rglob("@eaDir"), key=lambda p: len(p.parts)):
            if not folder.is_dir() or any(parent in removed for parent in folder.parents):
                continue
            try:
                self.remover.remove_tree(folder)
                log.info(f"[INFO] {self.remover.verb} @eaDir: {folder}")
                removed.append(folder)
            except Exception as ex:
                log.error(f"[ERROR] Failed to remove {folder}: {ex}")
        return len(removed)

    def _remove_files(self, root: Path, pattern: str, max_size: int | None = None) -> int:
        removed = 0
        for file in find_files(root, pattern):
            try:
                if max_size is not None and file.stat().st_size > max_size:
                    continue
                if not self.remover.remove_file(file):
                    log.warning(f"[CLEANUP] Skipped read-only: {file} (use --force-readonly-deletion)")
                    continue
                log.info(f"[CLEANUP] {self.remover.verb} file: {file}")
                removed += 1
            except Exception as ex:
                log.error(f"[CLEANUP] Failed: {file} ({ex})")
        return removed

    # ---- rules ----------------------------------------------------------

    def _is_removable_metadata_folder(self, folder: Path) -> bool:
        return folder.name.startswith("._") and not self._contains_visible_files(folder)

    def _contains_visible_files(self, folder: Path) -> bool:
        """
        Recursively check for at least one non-hidden file.
        Unreadable folders count as containing visible files (safe default).
        """
        try:
            entries = list(folder.iterdir())
        except OSError as ex:
            log.warning(f"[CLEANUP] Cannot read {folder} ({ex}) -> keeping it")
            return True

        for entry in entries:
            if entry.is_symlink():
                continue  # never follow links outside the folder
            if entry.is_dir():
                if self._contains_visible_files(entry):
                    return True
            elif not is_hidden(entry):
                return True
        return False

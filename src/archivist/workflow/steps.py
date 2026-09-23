"""Workflow steps (Command pattern): each one does a single job and returns its report lines."""
from abc import ABC, abstractmethod
from pathlib import Path

from ..core import get_logger
from ..services import MetadataCleaner, ZipExtractor

log = get_logger()


class Step(ABC):
    """A workflow stage: `title` is logged before it runs, `run()` returns report label -> count."""

    title: str

    @abstractmethod
    def run(self, root: Path) -> dict[str, int]: ...


class ExtractArchives(Step):
    title = "Scanning for ZIP archives..."

    def __init__(self, extractor: ZipExtractor):
        self.extractor = extractor

    def run(self, root: Path) -> dict[str, int]:
        found, extracted = self.extractor.extract_all(root)
        return {"ZIP files found": found, "ZIP files extracted": extracted}


class RemoveAppleDoubleFiles(Step):
    def __init__(self, cleaner: MetadataCleaner, max_size: int):
        self.cleaner = cleaner
        self.max_size = max_size
        self.title = f"Removing small ._ files (<= {max_size} bytes)..."

    def run(self, root: Path) -> dict[str, int]:
        return {"._ files removed": self.cleaner.remove_appledouble_files(root, self.max_size)}


class RemoveFilesNamed(Step):
    """Removes every file with one name, like .DS_Store or Thumbs.db."""

    def __init__(self, cleaner: MetadataCleaner, filename: str):
        self.cleaner = cleaner
        self.filename = filename
        self.title = f"Removing {filename} files..."

    def run(self, root: Path) -> dict[str, int]:
        return {f"{self.filename} files removed": self.cleaner.remove_files_named(root, self.filename)}


class RemoveAppleDoubleFolders(Step):
    title = "Running metadata-folder cleanup..."

    def __init__(self, cleaner: MetadataCleaner):
        self.cleaner = cleaner

    def run(self, root: Path) -> dict[str, int]:
        return {"._ folders removed": self.cleaner.remove_metadata_folders(root)}


class RemoveEaDirFolders(Step):
    title = "=== Removing @eaDir folders ==="

    def __init__(self, cleaner: MetadataCleaner):
        self.cleaner = cleaner

    def run(self, root: Path) -> dict[str, int]:
        removed = self.cleaner.remove_eadir_folders(root)
        log.info(f"[OK] {self.cleaner.remover.verb}: {removed} @eaDir folder(s)")
        return {"@eaDir folders removed": removed}

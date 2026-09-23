"""Removal strategies: delete permanently, send to the bin, or only report (dry run)."""
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from send2trash import send2trash

from .fs import is_readonly, iter_tree, make_writable


class Remover(ABC):
    """Applies the read-only rules the same way for every strategy; subclasses decide what happens."""

    verb: str

    def __init__(self, force_readonly: bool = False):
        self.force_readonly = force_readonly

    def remove_file(self, file: Path) -> bool:
        """Return False, without touching the file, when it is read-only and forcing is off."""
        readonly = is_readonly(file)
        if readonly and not self.force_readonly:
            return False
        self._remove_file(file, readonly)
        return True

    def remove_tree(self, folder: Path) -> None:
        """Raise PermissionError, before touching anything, when the tree holds read-only items and forcing is off."""
        readonly = [p for p in iter_tree(folder) if not p.is_symlink() and is_readonly(p)]
        if readonly and not self.force_readonly:
            raise PermissionError(
                f"{len(readonly)} read-only item(s) inside, e.g. {readonly[0]} "
                f"(use --force-readonly-deletion)"
            )
        self._remove_tree(folder, readonly)

    @abstractmethod
    def _remove_file(self, file: Path, readonly: bool) -> None: ...

    @abstractmethod
    def _remove_tree(self, folder: Path, readonly: list[Path]) -> None: ...


class PermanentRemover(Remover):
    verb = "Removed"

    def _remove_file(self, file: Path, readonly: bool) -> None:
        if readonly:
            make_writable(file)
        file.unlink()

    def _remove_tree(self, folder: Path, readonly: list[Path]) -> None:
        for item in readonly:
            make_writable(item)
        shutil.rmtree(folder, onerror=_retry_writable if self.force_readonly else None)


class TrashRemover(Remover):
    verb = "Sent to bin"

    def _remove_file(self, file: Path, readonly: bool) -> None:
        if readonly:
            make_writable(file)
        send2trash(file)

    def _remove_tree(self, folder: Path, readonly: list[Path]) -> None:
        for item in readonly:
            make_writable(item)
        send2trash(folder)


class DryRunRemover(Remover):
    verb = "Would remove"

    def _remove_file(self, file: Path, readonly: bool) -> None:
        pass

    def _remove_tree(self, folder: Path, readonly: list[Path]) -> None:
        pass


def make_remover(*, dry_run: bool = False, to_trash: bool = False, force_readonly: bool = False) -> Remover:
    """A dry run wins over the bin, which wins over permanent deletion."""
    if dry_run:
        return DryRunRemover(force_readonly)
    if to_trash:
        return TrashRemover(force_readonly)
    return PermanentRemover(force_readonly)


def _retry_writable(func, path, _exc_info):
    """shutil.rmtree error handler: clear the read-only flag and retry."""
    make_writable(Path(path))
    func(path)

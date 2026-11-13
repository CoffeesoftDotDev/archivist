"""Avoid linked paths and publish completed files without overwriting."""
import os
import stat
from pathlib import Path

from ..core.models import ExportError


def is_link(path: Path) -> bool:
    """Recognize symbolic links and Windows reparse points, including junctions."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def safe_path(path: Path) -> Path:
    """Reject links in any existing path component without resolving them away."""
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        if os.path.lexists(component) and is_link(component):
            raise ExportError("A filesystem path is a link or junction; it was not opened.")
    return path


def publish_new(temporary: Path, target: Path) -> None:
    """Atomically link the completed sibling into place; never clobber a target."""
    safe_path(target)
    try:
        os.link(temporary, target)
    except FileExistsError:
        raise ExportError("A file already occupies the photo destination; it was not overwritten.") from None

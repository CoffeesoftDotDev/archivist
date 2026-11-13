"""Append-only private picture report, mirrored to the console."""
import json
import sys
from pathlib import Path
from typing import TextIO
from uuid import UUID

from ..utils.files import safe_path


class ExportReport:
    """Keep acquisition rows compatible and destination rows additive."""

    def __init__(self, destination: Path, console: TextIO | None = None):
        destination = safe_path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        self.path = safe_path(destination / "pictures.log")
        self.file = self.path.open("a", encoding="utf-8")
        self.console = sys.stdout if console is None else console

    def write(self, message: str) -> None:
        """Fail visibly on any report sink failure."""
        self.file.write(message + "\n")
        self.file.flush()
        self.console.write(message + "\n")
        self.console.flush()

    def photo(self, photo_id: UUID, status: str, path: Path | None = None, destination: str | None = None) -> None:
        """Write one machine-readable photo outcome."""
        row = {"id": str(photo_id), "status": status, "path": str(path) if path is not None else None}
        if destination is not None:
            row["destination"] = destination
        self.write(json.dumps(row, ensure_ascii=True))

    def close(self) -> None:
        """Close the report file, leaving stdout owned by its caller."""
        self.file.close()

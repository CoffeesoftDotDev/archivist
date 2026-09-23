import io
import logging
import os
import zipfile
from pathlib import Path

import pytest

from archivist.core import setup_logging


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    """Ignore the caller's ARCHIVIST_* variables and never touch the real Recycle Bin."""
    for name in list(os.environ):
        if name.startswith("ARCHIVIST_"):
            monkeypatch.delenv(name)

    def refuse(path):
        raise AssertionError(f"test tried to use the real Recycle Bin: {path}")

    monkeypatch.setattr("archivist.utils.removers.send2trash", refuse)
    yield
    setup_logging(console=False)  # closes report.log so Windows can delete the temp folder


@pytest.fixture
def logs(caplog):
    """Records from the archivist loggers, which do not propagate to the root logger."""
    logger = logging.getLogger("archivist")
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)
    yield caplog
    logger.removeHandler(caplog.handler)


def _zip_bytes(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, _zip_bytes(content) if isinstance(content, dict) else content)
    return buffer.getvalue()


@pytest.fixture
def make_zip():
    """make_zip(path, {"a.jpg": "x", "inner.zip": {...}}): a nested dict becomes a nested ZIP."""
    def make(path: Path, files: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_zip_bytes(files))
        return path
    return make


@pytest.fixture
def write_file():
    def write(path: Path, content: str | bytes = "x") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path
    return write


@pytest.fixture
def listing():
    """Sorted relative paths under a folder, to compare a tree before and after a run."""
    def list_tree(root: Path) -> list[str]:
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    return list_tree

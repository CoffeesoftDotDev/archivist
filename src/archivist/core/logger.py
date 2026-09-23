"""Central logging configuration for archivist."""
import logging
import sys
from pathlib import Path

LOGGER_NAME = "archivist"
REPORT_FILENAME = "report.log"

CONSOLE_FORMAT = "%(message)s"
FILE_FORMAT = "%(asctime)s [%(levelname)-7s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the archivist logger (or a child, e.g. get_logger('cleaner'))."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def resolve_log_path(root: Path, log_file: str | None) -> Path | None:
    """
    None      -> no file logging
    ""        -> <root>/report.log
    folder    -> <folder>/report.log
    file path -> that file (parent folders are created)
    """
    if log_file is None:
        return None
    if log_file == "":
        return root / REPORT_FILENAME
    path = Path(log_file).expanduser()
    if path.is_dir() or log_file.endswith(("/", "\\")):
        path = path / REPORT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(console: bool = True, log_file: Path | None = None) -> None:
    """
    (Re)configure outputs. Safe to call several times:
    existing handlers are replaced.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if console:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        logger.addHandler(stream)

    if log_file is not None:
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        logger.addHandler(file_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

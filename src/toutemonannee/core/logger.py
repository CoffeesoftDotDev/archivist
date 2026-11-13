"""Private operation logging with daily rotation and observable sink failures."""
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from .config import Config, LOG_LEVELS
from ..utils.files import safe_path


class FileHandler(logging.FileHandler):
    """Date-named rolling logs with a shared retention bound across invocations."""

    def __init__(self, path: Path):
        self.path = path
        self.day = datetime.now().date()
        super().__init__(self._dated_path(), encoding="utf-8")
        self._prune()

    def _dated_path(self) -> Path:
        return safe_path(self.path.with_name(self.path.stem + self.day.strftime("%Y%m%d") + self.path.suffix))

    def _prune(self) -> None:
        pattern = re.compile(re.escape(self.path.stem) + r"[0-9]{8}" + re.escape(self.path.suffix))
        logs = sorted(p for p in self.path.parent.iterdir() if pattern.fullmatch(p.name))
        for path in logs[:-14]:
            safe_path(path).unlink()

    def emit(self, record: logging.LogRecord) -> None:
        """Switch at midnight even in a long-lived export."""
        today = datetime.now().date()
        if today != self.day:
            if self.stream is not None:
                self.stream.close()
            self.day = today
            self.baseFilename = str(self._dated_path())
            self.stream = self._open()
            self._prune()
        super().emit(record)

    def handleError(self, record: logging.LogRecord) -> None:
        raise OSError("Operation logging failed; check disk space and log permissions.")


def setup_logging(config: Config) -> logging.Logger:
    """Initialize a dedicated logger before opening any browser."""
    path = safe_path(config.log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("toutemonannee")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    file_handler = FileHandler(path)
    console = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, console):
        handler.setFormatter(logging.Formatter("[%(asctime)s %(levelname)s] %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    logger.info("Initializing export operation logging.")
    logger.setLevel(LOG_LEVELS[config.log_level])
    return logger

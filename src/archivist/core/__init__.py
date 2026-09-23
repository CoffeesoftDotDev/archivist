"""App-wide infrastructure: configuration model and logging."""
from .config import APPLEDOUBLE_MAX_SIZE, Config
from .logger import get_logger, resolve_log_path, setup_logging

__all__ = ["APPLEDOUBLE_MAX_SIZE", "Config", "get_logger", "resolve_log_path", "setup_logging"]

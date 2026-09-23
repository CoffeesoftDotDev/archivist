"""Console entry point: folder prompt, logging outputs, exit codes."""
import sys
from pathlib import Path

from ..core import get_logger, resolve_log_path, setup_logging
from ..workflow import WorkflowBuilder
from .parser import parse_config

log = get_logger()


def resolve_root(parent_folder: Path | None) -> Path | None:
    """Use --parent-folder if given, otherwise prompt for it."""
    if parent_folder is not None:
        root = parent_folder
    else:
        if not sys.stdin or not sys.stdin.isatty():
            log.error("No parent folder given. Use --parent-folder or ARCHIVIST_PARENT_FOLDER.")
            return None
        root_path = input("Parent folder path: ").strip().strip('"')
        if not root_path:
            log.error("No path provided.")
            return None
        root = Path(root_path)
    if not root.is_dir():
        log.error(f"The specified path does not exist or is not a folder: {root}")
        return None
    return root


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point; returns the process exit code."""
    try:
        return _run(argv)
    except KeyboardInterrupt:
        log.info("")
        log.warning("Cancelled by user.")
        return 1


def _run(argv: list[str] | None) -> int:
    config = parse_config(argv)

    # Console first (root unknown yet); the file handler is added once root is resolved.
    setup_logging(console=True)

    root = resolve_root(config.parent_folder)
    if root is None:
        return 2

    try:
        log_path = resolve_log_path(root, config.log_file)
        setup_logging(console=True, log_file=log_path)
    except OSError as ex:
        log.error(f"Cannot open log file '{config.log_file}': {ex}")
        return 2

    log.info("======================")
    log.info("Archivist run started")
    log.info("======================")
    log.info(f"Parent folder      : {root.resolve()}")
    for line in config.summary().splitlines()[1:]:  # skip the "Parent folder" line
        log.info(line)
    if log_path:
        log.info(f"Report file        : {log_path}")

    WorkflowBuilder(config).build().run(root)
    return 0

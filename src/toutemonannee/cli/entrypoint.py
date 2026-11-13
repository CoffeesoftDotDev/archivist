"""Console lifecycle and sanitized exit-code boundaries."""
import sys
from collections.abc import Sequence

import httpx
from playwright.sync_api import Error as BrowserError

from ..core import ExportError
from ..core.logger import setup_logging
from .parser import parse_config


def _diagnostic(logger, level: str, message: str, *args: object) -> None:
    try:
        getattr(logger, level)(message, *args)
    except OSError:
        print("Operation logging failed; check disk space and log permissions.", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Run tma; return 0/1/2/130 for complete/operation/config/cancellation."""
    try:
        config = parse_config(argv)
        logger = setup_logging(config)
    except SystemExit as exc:
        return int(exc.code or 0)
    except KeyboardInterrupt:
        return 130
    except (ExportError, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ExportError) else "Configuration/log initialization failed; check settings and writable log path."
        print(message, file=sys.stderr)
        return 2
    try:
        from ..workflow import WorkflowBuilder

        return WorkflowBuilder(config).build().run()
    except KeyboardInterrupt:
        _diagnostic(logger, "warning", "Cancelled. Completed operations remain; an interrupted remote asset may already exist.")
        return 130
    except ExportError as exc:
        _diagnostic(logger, "error", "%s", exc)
        return 1
    except (httpx.HTTPError, BrowserError, OSError, ValueError) as exc:
        _diagnostic(logger, "error", "Export failed (%s). Check browser installation, connectivity and permissions; no URLs or response bodies are logged.", type(exc).__name__)
        return 1
    finally:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

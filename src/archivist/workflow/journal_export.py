"""Host adapter for the optional TouteMonAnnee export workflow."""
import logging
from dataclasses import replace
from pathlib import Path

from ..core import Config, get_logger, resolve_log_path, setup_logging

log = get_logger()
_OPTIONAL_MODULES = {"httpx", "PIL", "playwright", "toutemonannee"}


class JournalExportWorkflow:
    """Keep journal export isolated and make preview a strict no-op."""

    def __init__(self, config: Config):
        self.config = config
        self.exit_code = 0

    def run(self, root: Path | None = None) -> int:
        """Only execute the exporter when Archivist's explicit apply consent is present."""
        if not self.config.apply:
            log.info("TouteMonAnnee journal export selected.")
            log.info("Dry run: no browser, network, report, or destination changes were made.")
            log.info("Run again with --apply to start the export.")
            return 0

        try:
            from toutemonannee.cli.parser import parse_config
            from toutemonannee.core import ExportError
            from toutemonannee.workflow import WorkflowBuilder as ExportWorkflowBuilder
            import httpx
            from playwright.sync_api import Error as BrowserError
        except ModuleNotFoundError as exc:
            if exc.name not in _OPTIONAL_MODULES:
                raise
            log.error("TouteMonAnnee export dependencies are missing; install with `uv sync --extra toutemonannee`.")
            self.exit_code = 2
            return self.exit_code

        try:
            args = ["--config", str(self.config.journal_config)] if self.config.journal_config else []
            export_config = parse_config(args)
            destination = root or self.config.journal_destination
            if destination is not None:
                export_config = replace(export_config, destination=destination)
            export_config.validate()
            workflow = ExportWorkflowBuilder(export_config).build()
        except ExportError as exc:
            log.error("Invalid TouteMonAnnee configuration: %s", exc)
            self.exit_code = 2
            return self.exit_code

        try:
            log_path = resolve_log_path(export_config.destination, self.config.log_file)
            setup_logging(console=True, log_file=log_path)
        except OSError as exc:
            log.error("Cannot open the journal export log: %s", exc)
            self.exit_code = 2
            return self.exit_code

        exporter_logger = logging.getLogger("toutemonannee")
        previous_handlers = exporter_logger.handlers[:]
        previous_level = exporter_logger.level
        previous_propagate = exporter_logger.propagate
        bridge = _ArchivistLogHandler()
        exporter_logger.handlers = [bridge]
        exporter_logger.setLevel(logging.INFO)
        exporter_logger.propagate = False
        try:
            self.exit_code = workflow.run()
        except KeyboardInterrupt:
            log.warning("TouteMonAnnee export cancelled; completed operations were retained.")
            self.exit_code = 130
        except ExportError as exc:
            log.error("TouteMonAnnee export failed: %s", exc)
            self.exit_code = 1
        except (httpx.HTTPError, BrowserError, OSError, ValueError) as exc:
            log.error("TouteMonAnnee export failed (%s); check browser installation, connectivity and permissions.", type(exc).__name__)
            self.exit_code = 1
        finally:
            exporter_logger.handlers = previous_handlers
            exporter_logger.setLevel(previous_level)
            exporter_logger.propagate = previous_propagate
            bridge.close()
        return self.exit_code


class _ArchivistLogHandler(logging.Handler):
    """Forward exporter operation logs through Archivist's configured sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        log.log(record.levelno, record.getMessage())

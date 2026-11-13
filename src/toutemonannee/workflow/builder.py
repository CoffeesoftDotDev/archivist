"""Compose the export independently of the standalone or future Archivist CLI."""
from dataclasses import replace
from pathlib import Path

import httpx

from ..core import Config
from ..services.browser import open_session
from ..services.destinations import ImmichPhotoDestination, LocalPhotoDestination, PhotoDestination
from ..services.immich import ImmichClient
from ..services.journal import JournalClient
from ..services.media import PhotoDownloader
from ..services.report import ExportReport
from ..services.screenshot import PhotoScreenshotter
from .runner import ExportCommand


class ExportWorkflow:
    """Synchronous run(root)/exit_code adapter compatible with Archivist's invoker."""

    def __init__(self, config: Config):
        self.config = config
        self.exit_code = 0

    def run(self, root: Path | None = None) -> int:
        """Run this workflow only, never archive extraction or metadata cleanup."""
        config = replace(self.config, destination=root) if root is not None else self.config
        config.validate()
        self.exit_code = 1
        with open_session(config) as session:
            with httpx.Client(timeout=config.request_timeout_seconds, follow_redirects=False, trust_env=False) as media:
                with httpx.Client(timeout=config.request_timeout_seconds, follow_redirects=False, trust_env=False) as upload:
                    report = ExportReport(config.destination)
                    screenshotter = PhotoScreenshotter(session.context, session.journal_id, timeout=session.timeout) if config.screenshot_restricted else None
                    try:
                        destinations: list[PhotoDestination] = []
                        if not config.no_local:
                            destinations.append(LocalPhotoDestination())
                        if config.immich_enabled:
                            if config.immich_url is None or config.immich_api_key is None or config.immich_album is None:
                                raise RuntimeError("Immich configuration was not validated.")
                            destinations.append(ImmichPhotoDestination(
                                ImmichClient(upload, config.immich_url, config.immich_api_key, config.immich_album),
                            ))
                        journal = JournalClient(session, session.journal_id, page_size=config.page_size,
                                                capture_restricted=config.screenshot_restricted)
                        command = ExportCommand(journal, PhotoDownloader(media, config.destination), destinations,
                                                report, screenshotter=screenshotter)
                        self.exit_code = command.run()
                        return self.exit_code
                    finally:
                        try:
                            if screenshotter is not None:
                                screenshotter.close()
                        finally:
                            report.close()


class WorkflowBuilder:
    """Select the isolated export workflow from already validated configuration."""

    def __init__(self, config: Config):
        self.config = config

    def build(self) -> ExportWorkflow:
        """Build without opening a browser, making API calls or touching output."""
        self.config.validate()
        return ExportWorkflow(self.config)

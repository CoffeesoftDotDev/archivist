"""Permission-aware export orchestration and truthful partial-outcome reporting."""
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..core import ExportError, Photo
from ..services.content import PhotoContent
from ..services.destinations import PhotoDestination
from ..services.media import PhotoDownloader, Screenshotter
from ..services.report import ExportReport

log = logging.getLogger("toutemonannee")
OPERATION_ERRORS = (ExportError, httpx.HTTPError, OSError, ValueError)


class PhotoSource(Protocol):
    """A journal or synthetic fixture yielding validated photos."""

    def photos(self) -> Iterable[Photo]: ...


@dataclass
class DestinationStatistics:
    """Per-destination totals independent of acquisition counts."""

    destination: PhotoDestination
    completed: int = 0
    duplicates: int = 0
    failed: int = 0


@dataclass
class Counts:
    """Per-photo outcome counts; one failed count even if several targets fail."""

    downloaded: int = 0
    screenshots: int = 0
    reused: int = 0
    restricted: int = 0
    failed: int = 0

    @property
    def acquired(self) -> int:
        """Include new in-memory content as well as existing files."""
        return self.downloaded + self.screenshots + self.reused


class ExportCommand:
    """Enumerate once, acquire once per photo, execute additive destinations."""

    def __init__(self, journal: PhotoSource, downloader: PhotoDownloader, destinations: Iterable[PhotoDestination],
                 report: ExportReport, *, screenshotter: Screenshotter | None = None):
        self.journal = journal
        self.downloader = downloader
        self.destinations = list(destinations)
        self.report = report
        self.screenshotter = screenshotter
        if not self.destinations or len({d.name for d in self.destinations}) != len(self.destinations):
            raise ExportError("At least one destination is required and destination names must be unique.")

    def _error(self, error: BaseException, photo: Photo, destination: str) -> None:
        reason = str(error) if isinstance(error, ExportError) else f"operation failed ({type(error).__name__}); no URLs or response bodies are logged"
        log.error("Photo %s, destination %s: %s", photo.id, destination, reason)

    def run(self) -> int:
        """Return incomplete for restricted, failed or empty exports."""
        counts = Counts()
        transfers = [DestinationStatistics(destination) for destination in self.destinations]
        completed = False
        self.report.write("=== Photo export ===")
        self.report.write("Destinations: " + ", ".join(d.name for d in self.destinations))
        try:
            for photo in self.journal.photos():
                if not photo.can_download and self.screenshotter is None:
                    counts.restricted += 1
                    log.warning("Skipping photo %s: website download permission is disabled.", photo.id)
                    try:
                        existing = self.downloader.find_existing(photo.id)
                    except OPERATION_ERRORS as exc:
                        counts.failed += 1
                        self._error(exc, photo, "existing lookup")
                        self.report.photo(photo.id, "failed")
                    else:
                        if existing is not None:
                            counts.reused += 1
                            self.report.photo(photo.id, "existing", existing)
                    self.report.photo(photo.id, "restricted")
                    continue
                self._export_photo(photo, transfers, counts)
            completed = True
        except KeyboardInterrupt:
            self.report.write("Cancelled; completed operations were retained. An interrupted remote asset may already exist.")
            raise
        except OPERATION_ERRORS as exc:
            reason = str(exc) if isinstance(exc, ExportError) else type(exc).__name__
            self.report.write(f"Workflow stopped: {reason}")
            raise
        finally:
            self._summary(counts, transfers, completed)
        return 0 if counts.failed == 0 and counts.restricted == 0 and counts.acquired > 0 else 1

    def _export_photo(self, photo: Photo, transfers: list[DestinationStatistics], counts: Counts) -> None:
        content = PhotoContent(photo, self.downloader, self.screenshotter)
        reported = False
        photo_failed = False
        try:
            for transfer in transfers:
                result = None
                try:
                    result = transfer.destination.export(content)
                except OPERATION_ERRORS as exc:
                    self._error(exc, photo, transfer.destination.name)
                finally:
                    if content.prepared and not reported:
                        self._acquisition(content, counts)
                        reported = True
                if result is None:
                    if not photo_failed:
                        counts.failed += 1
                    photo_failed = True
                    transfer.failed += 1
                    self.report.photo(photo.id, "failed", content.local_path, transfer.destination.name)
                    if not content.prepared:
                        break
                else:
                    if result.duplicate:
                        transfer.duplicates += 1
                    else:
                        transfer.completed += 1
                    self.report.photo(photo.id, result.status, content.local_path, transfer.destination.name)
        finally:
            content.close()

    def _acquisition(self, content: PhotoContent, counts: Counts) -> None:
        if content.reused:
            counts.reused += 1
            status = "existing"
        elif content.photo.can_download:
            counts.downloaded += 1
            status = "downloaded"
        else:
            counts.screenshots += 1
            status = "screenshot"
        self.report.photo(content.photo.id, status, content.local_path)
        log.info("Photo %s: %s, activity date %s.", content.photo.id, status, content.photo.activity_date)

    def _summary(self, counts: Counts, transfers: list[DestinationStatistics], completed: bool) -> None:
        self.report.write(f"Photos downloaded: {counts.downloaded}")
        self.report.write(f"Screenshots captured: {counts.screenshots}")
        self.report.write(f"Photos already present: {counts.reused}")
        for transfer in transfers:
            self.report.write(f"{transfer.destination.completed_summary}: {transfer.completed}")
            self.report.write(f"{transfer.destination.duplicate_summary}: {transfer.duplicates}")
            self.report.write(f"Destination {transfer.destination.name} failures: {transfer.failed}")
        self.report.write(f"Restricted photos: {counts.restricted}")
        self.report.write(f"Failed photos: {counts.failed}")
        self.report.write("Operation completed" if completed and counts.failed == 0 and counts.restricted == 0 and counts.acquired > 0 else "Incomplete")
        self.report.write(f"Report: {self.report.path}")

"""Dependency-ordered image commands sharing one inventory and approved plan."""
import zipfile
import zlib
from pathlib import Path

from ..core import get_logger
from ..services import ImageRun
from .runner import Report, Workflow
from .steps import Step


class ImageStep(Step):
    def __init__(self, run: ImageRun):
        self.context = run


class ListImages(ImageStep):
    title = "Inventorying pictures on disk and inside ZIPs..."

    def run(self, root: Path) -> dict[str, int]:
        return self.context.list(root)


class ConfirmImagePlan(ImageStep):
    title = "Reviewing the extraction and picture plan..."

    def run(self, root: Path) -> dict[str, int]:
        return self.context.approve(root)


class ExtractImageArchives(ImageStep):
    title = "Extracting approved archives completely..."

    def run(self, root: Path) -> dict[str, int]:
        return self.context.extract(root)


class TransferImages(ImageStep):
    title = "Finishing approved picture transfers and archive disposition..."

    def run(self, root: Path) -> dict[str, int]:
        return self.context.transfer(root)


class ImageWorkflow(Workflow):
    """Stop on failure, report actual progress and always clean private staging."""

    def __init__(self, steps: list[Step], context: ImageRun):
        super().__init__(steps, dry_run=not context.config.apply)
        self.context = context

    def run(self, root: Path) -> Report:
        report: Report = {}
        try:
            for step in self.steps:
                report.update(step.run(root))
        except (KeyboardInterrupt, OSError, RuntimeError, ValueError, OverflowError, zipfile.BadZipFile, zlib.error) as ex:
            message = (
                "Cancelled; completed operations were not rolled back. Unremoved ZIPs are retained."
                if isinstance(ex, KeyboardInterrupt) else f"Workflow stopped: {ex}"
            )
            self._stop(message)
        finally:
            try:
                self.context.cleanup()
            except OSError as ex:
                self._stop(f"Private staging cleanup failed: {ex}")
            report.update(self.context.outcomes())
            try:
                for label, count in self.context.outcomes().items():
                    self.context.emit(f"{label}: {count}")
                status = (
                    "Incomplete or not approved" if self.context.exit_code
                    else "Operation completed" if self.context.approved
                    else "Inventory completed; collection unchanged (report write only)"
                )
                self.context.emit(status)
            except (OSError, RuntimeError) as ex:
                self.context.failed += 1
                self.context.exit_code = 1
                get_logger().error(f"Could not finish the image report: {ex}")
            finally:
                try:
                    self.context.close()
                except OSError as ex:
                    self.context.failed += 1
                    self.context.exit_code = 1
                    get_logger().error(f"Report close failed: {ex}")
        report.update(self.context.outcomes())
        self.exit_code = self.context.exit_code
        return report

    def _stop(self, message: str) -> None:
        self.context.failed += 1
        self.context.exit_code = 1
        try:
            self.context.emit(message, error=True)
        except (OSError, RuntimeError) as ex:
            get_logger().error(f"Could not record workflow failure: {ex}")

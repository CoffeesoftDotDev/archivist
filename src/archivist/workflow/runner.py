"""Runs the workflow steps in order and logs the report."""
from pathlib import Path

from ..core import get_logger
from .steps import Step

log = get_logger()

Report = dict[str, int]  # report label -> count, in step order


class Workflow:
    """The invoker of the Command pattern: runs each step in order and logs the combined report."""

    def __init__(self, steps: list[Step], dry_run: bool = False):
        self.steps = steps
        self.dry_run = dry_run

    def run(self, root: Path) -> Report:
        report: Report = {}
        for step in self.steps:
            log.info("")
            log.info(step.title)
            report.update(step.run(root))
        self._log_report(report)
        return report

    def _log_report(self, report: Report) -> None:
        log.info("")
        log.info("======================")
        log.info("Dry run completed: nothing was changed" if self.dry_run else "Operation completed")
        log.info("======================")
        width = max(map(len, report), default=0)
        for label, count in report.items():
            log.info(f"{label:<{width}} : {count}")
        if self.dry_run:
            log.info("")
            log.info("Run again with --apply to make these changes.")

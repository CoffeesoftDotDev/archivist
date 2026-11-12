"""The archivist algorithm: steps (Command pattern) picked by a builder and run in order."""
from .builder import WorkflowBuilder
from .runner import Report, Workflow
from .steps import (
    ExtractArchives,
    RemoveAppleDoubleFiles,
    RemoveAppleDoubleFolders,
    RemoveEaDirFolders,
    RemoveFilesNamed,
    RemoveMacosxFolders,
    Step,
)

__all__ = [
    "ExtractArchives",
    "RemoveAppleDoubleFiles",
    "RemoveAppleDoubleFolders",
    "RemoveEaDirFolders",
    "RemoveFilesNamed",
    "RemoveMacosxFolders",
    "Report",
    "Step",
    "Workflow",
    "WorkflowBuilder",
]

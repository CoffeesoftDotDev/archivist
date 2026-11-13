"""Small immutable contracts shared by services and workflows."""
from dataclasses import dataclass
from datetime import date
from uuid import UUID


class ExportError(Exception):
    """An expected failure whose message is safe for operational diagnostics."""


@dataclass(frozen=True)
class Photo:
    """Journal identity, activity date, permission and viewer observations."""

    journal_id: UUID
    post_id: int
    id: UUID
    activity_date: date
    extension: str
    source: str | None
    can_download: bool
    post_image_count: int = 0
    source_ambiguous: bool = False

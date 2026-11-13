"""Composable destination strategies, with no destination-specific runner branches."""
from dataclasses import dataclass
from typing import Protocol

from .content import PhotoContent
from .immich import ImmichClient


@dataclass(frozen=True)
class DestinationResult:
    """Report a completed transfer only after all of its operations succeed."""

    status: str
    duplicate: bool = False


class PhotoDestination(Protocol):
    """Extension point; the runner enforces restricted-photo opt-in first."""

    name: str
    completed_summary: str
    duplicate_summary: str

    def export(self, content: PhotoContent) -> DestinationResult: ...


class LocalPhotoDestination:
    """Save or reuse a receipt-verified local copy."""

    name = "local"
    completed_summary = "Photos saved locally"
    duplicate_summary = "Local copies reused"

    def export(self, content: PhotoContent) -> DestinationResult:
        """Use the shared streaming/receipt path."""
        content.save_locally()
        return DestinationResult("local_reused" if content.reused else "saved", content.reused)


class ImmichPhotoDestination:
    """Send an independent read stream to Immich."""

    name = "immich"
    completed_summary = "Photos uploaded"
    duplicate_summary = "Immich duplicates"

    def __init__(self, client: ImmichClient):
        self.client = client

    def export(self, content: PhotoContent) -> DestinationResult:
        """Count success only after album association succeeds."""
        with content.open_read() as source:
            duplicate = self.client.upload(content.photo, content.file_name, source)
        return DestinationResult("immich_duplicate" if duplicate else "uploaded", duplicate)

"""Validated configuration, independent of argument parsing and browser startup."""
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from .models import ExportError

RESOLUTIONS = frozenset({"1280x720", "1920x1080", "2560x1080", "3440x1440", "3840x2160"})
LOG_LEVELS = {"Verbose": 5, "Debug": 10, "Information": 20, "Warning": 30, "Error": 40, "Fatal": 50}


def boolean(value: object) -> bool:
    """Read explicit booleans without Python's truthy-string conversion."""
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ExportError("A boolean setting must be true or false.")


def integer(value: object) -> int:
    """Read integers without silently truncating floats or accepting booleans."""
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ExportError("A numeric setting must be a whole number.")


def validate_immich_url(value: str) -> str:
    """Allow HTTPS or literal loopback HTTP, without URL-carried credentials."""
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        _ = url.port
        valid = (
            bool(host) and (url.scheme == "https" or (url.scheme == "http" and loopback))
            and url.username is None and url.password is None and not url.query and not url.fragment
            and not any(ord(c) < 33 or ord(c) == 127 for c in value) and "\\" not in value
        )
    except ValueError:
        valid = False
    if not valid:
        raise ExportError("Immich URL must use HTTPS (HTTP only on loopback), without credentials, query or fragment.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Config:
    """All runtime options; JSON keys and TMA_ variables remain compatible."""

    destination: Path = Path(".")
    journal_id: UUID | None = None
    browser_channel: str = "msedge"
    reuse_session: bool = True
    screenshot_restricted: bool = False
    no_local: bool = False
    resolution: str = "1920x1080"
    login_timeout_seconds: int = 300
    request_timeout_seconds: int = 120
    page_size: int = 100
    log_path: Path = Path(".tma/logs/export-.log")
    log_level: str = "Information"
    immich_enabled: bool = False
    immich_url: str | None = None
    immich_api_key: str | None = field(default=None, repr=False)
    immich_album: str | None = None

    @property
    def viewport(self) -> dict[str, int]:
        """Return the browser viewport and emulated screen dimensions."""
        width, height = self.resolution.split("x")
        return {"width": int(width), "height": int(height)}

    def validate(self) -> None:
        """Reject invalid configuration before any operational side effect."""
        if self.browser_channel not in {"msedge", "chromium"}:
            raise ExportError("BrowserChannel must be msedge or chromium.")
        if self.resolution not in RESOLUTIONS:
            raise ExportError("Resolution must be one of: " + ", ".join(sorted(RESOLUTIONS)))
        if self.log_level not in LOG_LEVELS:
            raise ExportError("LogLevel is invalid.")
        for value in (self.login_timeout_seconds, self.request_timeout_seconds):
            if type(value) is not int or not 1 <= value <= 3600:
                raise ExportError("Timeouts must be between 1 and 3600 seconds.")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 100:
            raise ExportError("PageSize must be between 1 and 100.")
        for value in (self.reuse_session, self.screenshot_restricted, self.no_local, self.immich_enabled):
            if type(value) is not bool:
                raise ExportError("A boolean setting must be true or false.")
        if self.journal_id is not None and not isinstance(self.journal_id, UUID):
            raise ExportError("JournalId must be a journal UUID.")
        if self.no_local and not self.immich_enabled:
            raise ExportError("At least one destination is required. Remove --no-local or enable --immich.")
        if self.immich_enabled:
            if not all(isinstance(v, str) and v.strip() for v in
                       (self.immich_url, self.immich_api_key, self.immich_album)):
                raise ExportError("Immich export requires a URL, an API key and an album name.")
            if self.immich_url is not None:
                validate_immich_url(self.immich_url)
            for value in (self.immich_api_key, self.immich_album):
                if value is not None and any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise ExportError("Immich API key or album contains invalid control characters.")

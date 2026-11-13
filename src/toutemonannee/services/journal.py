"""Strict journal enumeration; no permission or activity-date fallbacks."""
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from typing import Protocol, TypeVar, cast
from urllib.parse import urlsplit
from uuid import UUID

from ..core import ExportError, Photo

EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "avif"})
MONTHS = (
    ("jan", "janv", "janvier"), ("fev", "fevr", "fevrier"), ("mar", "mars"),
    ("avr", "avril"), ("mai",), ("juin",), ("juil", "juill", "juillet"),
    ("aou", "aout"), ("sep", "sept", "septembre"), ("oct", "octobre"),
    ("nov", "novembre"), ("dec", "decembre"),
)
T = TypeVar("T")


class JournalTransport(Protocol):
    """Transport must return decoded JSON for a selected-journal relative path."""

    def get(self, relative_path: str) -> object: ...


def field(data: object, key: str, expected: type[T]) -> T:
    """Require a JSON field with its exact type (bool is not an integer)."""
    if not isinstance(data, dict) or key not in data:
        raise ExportError(f"Journal API response is missing required field '{key}'.")
    value = data[key]
    if type(value) is not expected or (expected is str and not value.strip()):
        raise ExportError(f"Journal API field '{key}' has an invalid type or value.")
    return cast(T, value)


def validate_source(value: str) -> str:
    """Only public HTTPS TouteMonAnnee S3 media hosts, without user info."""
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        valid = (
            url.scheme == "https" and url.port in (None, 443) and url.username is None
            and url.password is None and host.lower().endswith(".s3.toutemonannee.com")
            and re.fullmatch(r"[a-zA-Z0-9.-]+", host) is not None
            and "\\" not in value and not any(ord(c) < 33 or ord(c) == 127 for c in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ExportError("Image URL is outside the expected HTTPS TouteMonAnnee media hosts.")
    return value


def validate_extension(value: str) -> str:
    """Require a supported image suffix."""
    value = value.lower()
    if value not in EXTENSIONS:
        raise ExportError("Journal API returned an unsupported image extension.")
    return value


def parse_activity_date(value: object) -> date:
    """Parse French activity dates without substituting upload dates."""
    day = field(value, "day", str)
    raw = unicodedata.normalize("NFD", field(value, "month", str))
    month = "".join(c for c in raw if unicodedata.category(c) != "Mn").strip().rstrip(".").lower()
    number = next((i for i, names in enumerate(MONTHS, 1) if month in names), 0)
    if not number and month.isascii() and month.isdecimal():
        number = int(month)
    year = field(value, "year", int)
    try:
        if not day.isascii() or not day.isdecimal():
            raise ValueError
        return date(year, number, int(day))
    except (ValueError, OverflowError):
        raise ExportError("Journal API returned an unsupported activity date; no upload-date fallback is used.") from None


def _viewer_source(data: object) -> str | None:
    source = data.get("src") if isinstance(data, dict) else None
    if not isinstance(source, str):
        return None
    try:
        return validate_source(source)
    except ExportError:
        # Restricted src is optional viewer metadata, never a download fallback.
        return None


class JournalClient:
    """Enumerate posts and complete photo pages with consistency checks."""

    def __init__(self, transport: JournalTransport, journal_id: UUID, *, page_size: int = 100,
                 capture_restricted: bool = False):
        self.transport = transport
        self.journal_id = journal_id
        self.page_size = page_size
        self.capture_restricted = capture_restricted

    def photos(self) -> Iterator[Photo]:
        """Yield unique photos, buffering full posts for screenshot ambiguity checks."""
        seen_posts: set[int] = set()
        page = 1
        while True:
            root = self.transport.get(f"/journal/{self.journal_id}/posts/list?published_date_order=1&page={page}")
            self._require_page(root, page)
            for post in field(root, "data", list):
                if field(post, "model", str) != "post":
                    continue
                post_id = field(post, "id", int)
                if not 0 < post_id <= 2**63 - 1:
                    raise ExportError("Journal API returned an invalid post ID.")
                if post_id in seen_posts:
                    continue
                seen_posts.add(post_id)
                if not isinstance(post, dict) or "activity_date_detailed" not in post:
                    raise ExportError("Journal API is missing the activity date.")
                activity = parse_activity_date(post["activity_date_detailed"])
                count = field(post, "images_count", int)
                if not 0 <= count <= 2**31 - 1:
                    raise ExportError("Journal API returned an invalid image count.")
                if count:
                    yield from self._post_photos(post_id, activity, count)
            if not isinstance(root, dict) or "next_page" not in root:
                raise ExportError("Journal API response is missing next_page.")
            following = root["next_page"]
            if following is None:
                return
            if type(following) is not int or following != page + 1:
                raise ExportError("Journal API returned non-sequential post pagination.")
            page = following

    @staticmethod
    def _require_page(root: object, expected: int) -> None:
        if field(root, "current_page", int) != expected:
            raise ExportError("Journal API returned a repeated or unexpected page.")

    def _post_photos(self, post_id: int, activity: date, count: int) -> Iterator[Photo]:
        seen: set[UUID] = set()
        buffered: list[Photo] = []
        observations: list[tuple[UUID, str | None]] = []
        page = 1
        last_page: int | None = None
        while True:
            root = self.transport.get(f"/journal/{self.journal_id}/posts/photos/{post_id}?page={page}&per_page={self.page_size}")
            self._require_page(root, page)
            for item in field(root, "data", list):
                if field(item, "type", str) != "image":
                    continue
                try:
                    photo_id = UUID(field(item, "uuid", str))
                except ValueError:
                    raise ExportError("Journal API returned an invalid image UUID.") from None
                if photo_id in seen and not self.capture_restricted:
                    continue
                if field(item, "post_id", int) != post_id:
                    raise ExportError("Journal API returned an image from a different post.")
                if photo_id in seen:
                    observations.append((photo_id, _viewer_source(item)))
                    continue
                seen.add(photo_id)
                allowed = field(item, "can_download", bool)
                source = validate_source(field(item, "src", str)) if allowed else _viewer_source(item) if self.capture_restricted else None
                extension = validate_extension(field(item, "extension", str)) if allowed else ""
                photo = Photo(self.journal_id, post_id, photo_id, activity, extension, source, allowed, count)
                if self.capture_restricted:
                    observations.append((photo_id, source))
                    buffered.append(photo)
                else:
                    yield photo
            last = field(root, "last_page", int)
            if not page <= last <= 2**31 - 1 or (last_page is not None and last != last_page):
                raise ExportError("Journal API returned invalid photo pagination.")
            last_page = last
            if last == page:
                break
            page += 1
        if len(seen) != count:
            raise ExportError("The photo list does not match the post's image count; rerun to avoid an incomplete export.")
        if self.capture_restricted:
            first: dict[UUID, str | None] = {}
            owners: dict[str, UUID] = {}
            ambiguous: set[UUID] = set()
            for photo_id, source in observations:
                if photo_id in first and first[photo_id] != source:
                    ambiguous.add(photo_id)
                first.setdefault(photo_id, source)
                if source is not None:
                    if source in owners and owners[source] != photo_id:
                        ambiguous.update((photo_id, owners[source]))
                    owners.setdefault(source, photo_id)
            for photo in buffered:
                yield replace(photo, source_ambiguous=photo.id in ambiguous)

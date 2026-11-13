"""Streaming local acquisition, GUID reuse, and legacy-compatible integrity receipts."""
import hashlib
import io
import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID

import httpx
from PIL import Image, UnidentifiedImageError

from ..core import ExportError, Photo
from ..utils.files import is_link, publish_new, safe_path
from .journal import EXTENSIONS, validate_extension, validate_source

GUID_TOKEN = re.compile(r"(?<![A-Za-z0-9])(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32})(?![A-Za-z0-9])", re.I)
EXPORTED_NAME = re.compile(r"^[0-9a-f]{32}_[1-9][0-9]*_([0-9a-f]{32})$", re.I)


class Screenshotter(Protocol):
    """Authorized viewer strategy; implementations return complete PNG bytes."""

    def capture(self, photo: Photo) -> bytes: ...


@dataclass(frozen=True)
class DownloadResult:
    """A complete local image and whether it was already present."""

    path: Path
    reused: bool


def filename(photo: Photo) -> str:
    """Use stable identifiers, never personal journal titles."""
    extension = validate_extension(photo.extension) if photo.can_download else "png"
    return f"{photo.journal_id.hex}_{photo.post_id}_{photo.id.hex}.{extension}"


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(81920), b""):
            result.update(chunk)
    return result.hexdigest().upper()


def screenshot_png(photo: Photo, screenshotter: Screenshotter) -> bytes:
    """Decode a complete PNG and add an explicitly approximate activity-date EXIF."""
    if photo.can_download:
        raise ExportError("A downloadable photo must use the download path.")
    png = screenshotter.capture(photo)
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or not png.endswith(b"\0\0\0\0IEND\xaeB`\x82"):
        raise ExportError("The viewer did not return a complete PNG screenshot.")
    try:
        with Image.open(io.BytesIO(png)) as image:
            if image.format != "PNG":
                raise ExportError("The viewer did not return a PNG screenshot.")
            image.load()
            exif = image.getexif()
            stamp = photo.activity_date.strftime("%Y:%m:%d") + " 12:00:00"
            exif[306] = stamp
            nested = exif.get_ifd(34665)
            nested[36867] = stamp
            nested[36868] = stamp
            exif[34665] = nested
            with io.BytesIO() as output:
                image.save(output, format="PNG", exif=exif)
                return output.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ExportError("Viewer PNG could not be decoded for date metadata; no screenshot was saved.") from None


class PhotoDownloader:
    """Acquire images without rewriting existing files or trusted originals."""

    def __init__(self, http: httpx.Client, destination: Path):
        self.http = http
        self.destination = safe_path(destination)
        self._index: dict[UUID, list[Path]] | None = None

    def _photo_index(self) -> dict[UUID, list[Path]]:
        if self._index is not None:
            return self._index
        index: dict[UUID, list[Path]] = {}
        directories = [self.destination] if self.destination.exists() else []
        while directories:
            directory = directories.pop()
            safe_path(directory)
            for path in sorted(directory.iterdir()):
                if is_link(path):
                    continue
                if path.is_dir():
                    if not (directory == self.destination and path.name.lower() == ".tma"):
                        directories.append(path)
                    continue
                if path.suffix.lower().lstrip(".") not in EXTENSIONS:
                    continue
                exported = EXPORTED_NAME.fullmatch(path.stem)
                ids = {UUID(exported[1])} if exported else {UUID(m[0]) for m in GUID_TOKEN.finditer(path.stem)}
                for photo_id in ids:
                    index.setdefault(photo_id, []).append(path)
        self._index = index
        return index

    def _receipt(self, path: Path) -> tuple[int, str] | None:
        safe_path(path)
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8-sig") as file:
                receipt = json.load(file)
            length = receipt["Length"]
            sha = receipt["Sha256"]
            if type(length) is not int or length <= 0 or not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha):
                raise ValueError
            return length, sha.upper()
        except (ValueError, KeyError, TypeError):
            raise ExportError("A download receipt is invalid. Inspect .tma/receipts before retrying.") from None

    def find_existing(self, photo_id: UUID) -> Path | None:
        """Verify every matching copy, even when a valid duplicate also exists."""
        reusable: Path | None = None
        for path in self._photo_index().get(photo_id, []):
            safe_path(path)
            if not path.exists():
                continue
            receipt = self._receipt(self.destination / ".tma" / "receipts" / (str(path.relative_to(self.destination)) + ".json"))
            length = path.stat().st_size
            if length == 0 or (receipt is not None and (length != receipt[0] or _hash(path) != receipt[1])):
                raise ExportError("An existing photo failed its integrity check; it was not downloaded or overwritten.")
            reusable = reusable or path
        return reusable

    def download_to(self, photo: Photo, output: BinaryIO) -> None:
        """Stream a permitted image; reject redirects, HTML and incomplete content."""
        if not photo.can_download or photo.source is None:
            raise ExportError("Website does not permit downloading this photo.")
        source = validate_source(photo.source)
        validate_extension(photo.extension)
        with self.http.stream("GET", source, follow_redirects=False) as response:
            if not 200 <= response.status_code < 300:
                raise ExportError(f"Photo server returned HTTP {response.status_code}; redirects are not followed.")
            if not response.headers.get("content-type", "").lower().startswith("image/"):
                raise ExportError("Photo server did not return an image.")
            total = 0
            for chunk in response.iter_bytes():
                output.write(chunk)
                total += len(chunk)
            expected = response.headers.get("content-length")
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            wire_length = response.num_bytes_downloaded if encoding != "identity" else total
            try:
                valid_length = expected is None or int(expected) == wire_length
            except ValueError:
                valid_length = False
            if total == 0 or not valid_length:
                raise ExportError("Downloaded photo is empty or incomplete.")

    def acquire_to(self, photo: Photo, output: BinaryIO, screenshotter: Screenshotter | None = None) -> None:
        """Use the permission-appropriate strategy exactly once."""
        if photo.can_download:
            self.download_to(photo, output)
        elif screenshotter is None:
            raise ExportError("Restricted photos require an authorized screenshot strategy.")
        else:
            output.write(screenshot_png(photo, screenshotter))

    def save(self, photo: Photo, write: Callable[[BinaryIO], None]) -> DownloadResult:
        """Publish a complete file and receipt from unique temporary sibling files."""
        folder = safe_path(self.destination / photo.activity_date.isoformat())
        path = safe_path(folder / filename(photo))
        receipt_path = safe_path(self.destination / ".tma" / "receipts" / photo.activity_date.isoformat() / (filename(photo) + ".json"))
        self._receipt(receipt_path)
        index = self._photo_index()
        if path.exists() and path not in index.get(photo.id, []):
            index.setdefault(photo.id, []).append(path)
        existing = self.find_existing(photo.id)
        if existing is not None:
            return DownloadResult(existing, True)
        folder.mkdir(parents=True, exist_ok=True)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        receipt_temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=path.name + ".", suffix=".part", dir=folder, delete=False) as file:
                temporary = Path(file.name)
                write(file)
            length = temporary.stat().st_size
            if length == 0:
                raise ExportError("Photo output is empty.")
            receipt = {"Length": length, "Sha256": _hash(temporary)}
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=receipt_path.name + ".", suffix=".part",
                                             dir=receipt_path.parent, delete=False) as file:
                receipt_temporary = Path(file.name)
                json.dump(receipt, file)
            safe_path(receipt_path)
            receipt_temporary.replace(receipt_path)
            publish_new(temporary, path)
            index.setdefault(photo.id, []).append(path)
            return DownloadResult(path, False)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if receipt_temporary is not None:
                receipt_temporary.unlink(missing_ok=True)

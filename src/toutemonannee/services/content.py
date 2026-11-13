"""One lazy acquisition shared by additive destination strategies."""
import io
import shutil
from pathlib import Path
from typing import BinaryIO

from ..core import Photo
from .media import PhotoDownloader, Screenshotter, filename


class PhotoContent:
    """Own in-memory bytes; each consumer owns an independent read stream."""

    def __init__(self, photo: Photo, downloader: PhotoDownloader, screenshotter: Screenshotter | None = None):
        self.photo = photo
        self.downloader = downloader
        self.screenshotter = screenshotter
        self.local_path: Path | None = None
        self.reused = False
        self.prepared = False
        self._buffer: io.BytesIO | None = None

    @property
    def file_name(self) -> str:
        """Preserve the suffix of an existing GUID match."""
        return self.local_path.name if self.local_path else filename(self.photo)

    def open_read(self) -> BinaryIO:
        """Acquire only once, reusing verified local content even in remote-only mode."""
        if not self.prepared:
            self.local_path = self.downloader.find_existing(self.photo.id)
            self.reused = self.local_path is not None
            if self.local_path is None:
                self._buffer = io.BytesIO()
                self.downloader.acquire_to(self.photo, self._buffer, self.screenshotter)
            self.prepared = True
        if self.local_path is not None:
            return self.local_path.open("rb")
        if self._buffer is None:
            raise RuntimeError("Prepared photo has neither local content nor a buffer.")
        return io.BytesIO(self._buffer.getvalue())

    def save_locally(self) -> None:
        """Keep local streaming unless another destination already acquired the bytes."""
        if self.local_path is not None:
            return
        if self.prepared:
            with self.open_read() as source:
                result = self.downloader.save(self.photo, lambda output: shutil.copyfileobj(source, output))
        else:
            result = self.downloader.save(
                self.photo, lambda output: self.downloader.acquire_to(self.photo, output, self.screenshotter),
            )
        self.local_path, self.reused = result.path, result.reused
        self.prepared = True

    def close(self) -> None:
        """Release remote-only image memory after each photo, including failed transfers."""
        if self._buffer is not None:
            self._buffer.close()
            self._buffer = None

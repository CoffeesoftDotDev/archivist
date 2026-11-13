"""Immich multipart upload and exact-name album membership verification."""
from contextlib import closing
from typing import BinaryIO
from uuid import UUID

import httpx

from ..core import ExportError, Photo
from ..core.config import validate_immich_url
from .journal import validate_extension


def _uuid(value: object, label: str) -> UUID:
    try:
        result = UUID(value) if isinstance(value, str) else UUID(int=0)
    except ValueError:
        result = UUID(int=0)
    if result.int == 0:
        raise ExportError(f"Immich returned an invalid {label} identifier.")
    return result


class ImmichClient:
    """Fail a transfer if upload succeeds but album membership does not."""

    def __init__(self, http: httpx.Client, server: str, api_key: str, album: str):
        self.http = http
        root = validate_immich_url(server)
        self.endpoint = root if root.lower().endswith("/api") else root + "/api"
        self._api_key = api_key
        self.album = album
        self._album_id: UUID | None = None

    def _request(self, method: str, path: str, statuses: tuple[int, ...], operation: str, **kwargs) -> object:
        with closing(self.http.request(method, self.endpoint + path, headers={"x-api-key": self._api_key},
                                       follow_redirects=False, **kwargs)) as response:
            if response.status_code not in statuses:
                raise ExportError(f"Immich {operation} returned HTTP {response.status_code}; check API permissions and server version.")
            try:
                return response.json()
            except ValueError:
                raise ExportError(f"Immich returned malformed {operation} JSON.") from None

    def _resolve_album(self) -> UUID:
        albums = self._request("GET", "/albums", (200,), "album lookup")
        if not isinstance(albums, list):
            raise ExportError("Immich returned an unexpected album list.")
        match: UUID | None = None
        for album in albums:
            if not isinstance(album, dict) or not isinstance(album.get("albumName"), str):
                raise ExportError("Immich returned an unexpected album list.")
            if album["albumName"] != self.album:
                continue
            if match is not None:
                raise ExportError("Multiple Immich albums have the requested name; rename them to make the destination unambiguous.")
            match = _uuid(album.get("id"), "album")
        if match is not None:
            return match
        created = self._request("POST", "/albums", (201,), "album creation", json={"albumName": self.album})
        if not isinstance(created, dict) or created.get("albumName") != self.album:
            raise ExportError("Immich returned an unexpected created album.")
        return _uuid(created.get("id"), "album")

    def upload(self, photo: Photo, file_name: str, content: BinaryIO) -> bool:
        """Upload and associate the asset, returning True for an Immich duplicate."""
        if self._album_id is None:
            self._album_id = self._resolve_album()
        timestamp = photo.activity_date.isoformat() + "T12:00:00Z"
        suffix = validate_extension(file_name.rsplit(".", 1)[-1])
        mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else "image/" + suffix
        uploaded = self._request(
            "POST", "/assets", (200, 201), "upload",
            data={
                "fileCreatedAt": timestamp, "fileModifiedAt": timestamp,
                "deviceAssetId": f"tma-{photo.journal_id.hex}-{photo.post_id}-{photo.id.hex}",
                "deviceId": "toutemonannee-cli", "filename": file_name,
            }, files={"assetData": (file_name, content, mime)},
        )
        if not isinstance(uploaded, dict) or not isinstance(uploaded.get("status"), str) or uploaded["status"] not in {"created", "duplicate"}:
            raise ExportError("Immich returned an unexpected upload response.")
        asset_id = _uuid(uploaded.get("id"), "asset")
        result = self._request("PUT", f"/albums/{self._album_id}/assets", (200,), "album assignment",
                               json={"ids": [str(asset_id)]})
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            raise ExportError("Immich returned an unexpected album assignment response.")
        item = result[0]
        if _uuid(item.get("id"), "asset") != asset_id or type(item.get("success")) is not bool:
            raise ExportError("Immich returned an unexpected album assignment response.")
        if not item["success"] and item.get("error") != "duplicate":
            raise ExportError("Immich could not add the photo to the album. The asset may exist; fix permissions and rerun.")
        return uploaded["status"] == "duplicate"

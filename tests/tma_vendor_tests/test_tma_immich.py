"""HTTP request contracts including duplicate assets, exact albums and failures."""
import io
import json
from uuid import uuid4

import httpx
import pytest

from toutemonannee.core import ExportError
from toutemonannee.services.immich import ImmichClient


@pytest.mark.parametrize("exists,status,member", [(True, "created", True), (False, "duplicate", False)])
def test_upload_and_album_contracts(photo, exists, status, member):
    album_id, asset_id = uuid4(), uuid4()
    calls = []
    def handle(request):
        calls.append(request)
        assert request.headers["x-api-key"] == "private"
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": str(album_id), "albumName": "School"}] if exists else [])
        if request.url.path == "/api/albums":
            assert json.loads(request.content) == {"albumName": "School"}
            return httpx.Response(201, json={"id": str(album_id), "albumName": "School"})
        if request.url.path == "/api/assets":
            assert b'name="assetData"' in request.content
            assert b"Content-Type: image/png" in request.content
            assert request.content.count(b"2026-11-06T12:00:00Z") == 2
            assert f"tma-{photo.journal_id.hex}-42-{photo.id.hex}".encode() in request.content
            return httpx.Response(201, json={"id": str(asset_id), "status": status})
        assert str(album_id) in request.url.path
        assert json.loads(request.content) == {"ids": [str(asset_id)]}
        return httpx.Response(200, json=[{"id": str(asset_id), "success": member, "error": "duplicate"}])
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = ImmichClient(http, "https://photos.example/api", "private", "School")
        for _ in range(2):
            assert client.upload(photo, "image.png", io.BytesIO(b"png")) == (status == "duplicate")
    assert sum(r.method == "GET" for r in calls) == 1
    assert sum(r.method == "PUT" for r in calls) == 2


@pytest.mark.parametrize("mode", ["ambiguous", "lookup", "create", "upload", "status", "id", "assignment", "member", "malformed"])
def test_failures_are_not_success_and_never_echo_body(photo, mode):
    album_id, asset_id = uuid4(), uuid4()
    uploaded = []
    def handle(request):
        if request.method == "GET":
            if mode == "lookup":
                return httpx.Response(403, text="private secret body")
            albums = [{"id": str(album_id), "albumName": "School"}]
            return httpx.Response(200, json=albums * 2 if mode == "ambiguous" else [] if mode == "create" else albums)
        if request.url.path.endswith("/albums"):
            return httpx.Response(500, text="private secret body")
        if request.url.path.endswith("/assets") and request.method == "POST":
            uploaded.append(request)
            if mode == "upload":
                return httpx.Response(302, headers={"location": "https://evil.com/private"}, text="private secret body")
            return httpx.Response(201, json={"id": "bad" if mode == "id" else str(asset_id),
                                           "status": "invalid" if mode == "status" else "created"})
        if mode == "assignment":
            return httpx.Response(403, text="private secret body")
        if mode == "malformed":
            return httpx.Response(200, text="private secret body")
        return httpx.Response(200, json=[{"id": str(asset_id), "success": False, "error": "private secret body"}])
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(ExportError) as error:
            ImmichClient(http, "https://photos.example", "key", "School").upload(photo, "image.jpg", io.BytesIO(b"photo"))
        assert "private" not in str(error.value)
    if mode in {"ambiguous", "lookup", "create"}:
        assert not uploaded

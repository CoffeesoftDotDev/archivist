"""Byte preservation, receipts, shared content and truthful reports."""
import hashlib
import gzip
import io
import json
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from toutemonannee.core import Config, ExportError
from toutemonannee.services.destinations import DestinationResult, LocalPhotoDestination
from toutemonannee.services.media import PhotoDownloader, filename
from toutemonannee.services.report import ExportReport
from toutemonannee.workflow.runner import ExportCommand


class Source:
    def __init__(self, *photos):
        self.items = photos

    def photos(self):
        yield from self.items


class Capture:
    def __init__(self, png):
        self.png = png
        self.calls = 0

    def capture(self, photo):
        self.calls += 1
        return self.png


class Destination:
    completed_summary = "Transfers"
    duplicate_summary = "Duplicates"

    def __init__(self, name="custom", *, failure=None):
        self.name = name
        self.failure = failure
        self.payloads = []

    def export(self, content):
        with content.open_read() as first, content.open_read() as second:
            a, b = first.read(), second.read()
            assert a == b and a
            self.payloads.append(a)
        if self.failure:
            raise self.failure
        return DestinationResult("transferred")


def client(payload=b"original", *, content_type="image/jpeg", status=200, length=None):
    calls = []

    def handle(request):
        calls.append(request)
        headers = {"content-type": content_type}
        if length is not None:
            headers["content-length"] = str(length)
        return httpx.Response(status, content=payload, headers=headers)
    return httpx.Client(transport=httpx.MockTransport(handle)), calls


def run(tmp_path, photo, downloader, destinations, screenshotter=None):
    report = ExportReport(tmp_path, io.StringIO())
    try:
        result = ExportCommand(Source(photo), downloader, destinations, report, screenshotter=screenshotter).run()
    finally:
        report.close()
    return result, (tmp_path / "pictures.log").read_text()


def test_local_bytes_receipts_guid_reuse_and_corruption(tmp_path, photo, png):
    http, calls = client(png)
    with http:
        downloader = PhotoDownloader(http, tmp_path)
        result, report = run(tmp_path, photo, downloader, [LocalPhotoDestination()])
        path = tmp_path / "2026-11-06" / filename(photo)
        assert result == 0 and path.read_bytes() == png
        receipt = json.loads((tmp_path / ".tma/receipts/2026-11-06" / (filename(photo) + ".json")).read_text())
        assert receipt == {"Length": len(png), "Sha256": hashlib.sha256(png).hexdigest().upper()}
        assert len(calls) == 1 and "Photos downloaded: 1" in report
        changed = replace(photo, post_id=99)
        result, report = run(tmp_path, changed, downloader, [LocalPhotoDestination()])
        assert result == 0 and len(calls) == 1 and '"status": "existing"' in report
        path.write_bytes(b"corrupt")
        result, report = run(tmp_path, photo, downloader, [LocalPhotoDestination()])
        assert result == 1 and len(calls) == 1 and path.read_bytes() == b"corrupt"
        assert "Incomplete" in report


@pytest.mark.parametrize("name,match", [
    ("copy_{id}.jpg", True), ("copy_{hex}.PNG", True), ("X{id}Y.jpg", False),
    ("{id}.txt", False), ("{journal}_42_{other}.jpg", False),
])
def test_guid_tokens_and_export_filename_do_not_reuse_journal_id(tmp_path, photo, name, match):
    name = name.format(id=photo.id, hex=photo.id.hex, journal=photo.id.hex, other=uuid4().hex)
    folder = tmp_path / "old"
    folder.mkdir()
    path = folder / name
    path.write_bytes(b"existing")
    http, _ = client()
    with http:
        assert PhotoDownloader(http, tmp_path).find_existing(photo.id) == (path if match else None)


def test_corrupt_duplicate_fails_even_with_a_good_untracked_match(tmp_path, photo):
    good = tmp_path / f"good_{photo.id}.jpg"
    bad = tmp_path / f"bad_{photo.id}.jpg"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")
    receipt = tmp_path / ".tma/receipts" / (bad.name + ".json")
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"Length": 3, "Sha256": "0" * 64}))
    http, _ = client()
    with http, pytest.raises(ExportError, match="integrity"):
        PhotoDownloader(http, tmp_path).find_existing(photo.id)


@pytest.mark.parametrize("mode", ["html", "empty", "truncated", "redirect", "cancel", "invalid-receipt"])
def test_failed_acquisition_never_promotes_or_leaves_temporary_files(tmp_path, photo, mode):
    http, calls = client(b"" if mode == "empty" else b"abc", content_type="text/html" if mode == "html" else "image/jpeg",
                         status=302 if mode == "redirect" else 200, length=100 if mode == "truncated" else None)
    with http:
        downloader = PhotoDownloader(http, tmp_path)
        if mode == "invalid-receipt":
            receipt = tmp_path / ".tma/receipts/2026-11-06" / (filename(photo) + ".json")
            receipt.parent.mkdir(parents=True)
            receipt.write_text('{"Length":true,"Sha256":"invalid"}')
        def acquire(output):
            if mode == "cancel":
                output.write(b"partial")
                raise KeyboardInterrupt
            downloader.download_to(photo, output)
        with pytest.raises((ExportError, httpx.HTTPError, KeyboardInterrupt)):
            downloader.save(photo, acquire)
        assert not list(tmp_path.rglob("*.part"))
        assert not list(tmp_path.rglob("*.jpg"))


def test_screenshot_png_exif_and_reuse_without_recapture(tmp_path, photo, png):
    photo = replace(photo, can_download=False, extension="")
    capture = Capture(png)
    http, calls = client()
    with http:
        downloader = PhotoDownloader(http, tmp_path)
        result, _ = run(tmp_path, photo, downloader, [LocalPhotoDestination()], capture)
        assert result == 0
        path = tmp_path / "2026-11-06" / filename(photo)
        with Image.open(path) as image:
            assert image.size == (23, 17)
            assert image.getexif()[306] == "2026:11:06 12:00:00"
            assert image.getexif().get_ifd(34665)[36867] == "2026:11:06 12:00:00"
        assert run(tmp_path, photo, downloader, [LocalPhotoDestination()], capture)[0] == 0
        assert capture.calls == 1 and not calls


@pytest.mark.parametrize("screenshot", [False, True])
def test_additive_strategies_share_one_acquisition_and_can_save_after_remote(tmp_path, photo, png, screenshot):
    photo = replace(photo, can_download=not screenshot)
    capture = Capture(png)
    remote = Destination()
    http, calls = client(png)
    with http:
        result, _ = run(tmp_path, photo, PhotoDownloader(http, tmp_path), [remote, LocalPhotoDestination()], capture)
        assert result == 0 and len(remote.payloads) == 1
        assert capture.calls == int(screenshot) and len(calls) == int(not screenshot)
        assert len(list(tmp_path.rglob("*.png" if screenshot else "*.jpg"))) == 1


@pytest.mark.parametrize("screenshot", [False, True])
def test_remote_only_uses_memory_and_reports_null_path(tmp_path, photo, png, screenshot):
    photo = replace(photo, can_download=not screenshot)
    remote = Destination()
    http, calls = client(png)
    with http:
        result, report = run(tmp_path, photo, PhotoDownloader(http, tmp_path), [remote], Capture(png) if screenshot else None)
    assert result == 0 and remote.payloads
    assert not list(tmp_path.rglob("*.jpg")) and not list(tmp_path.rglob("*.png"))
    assert not (tmp_path / ".tma").exists()
    rows = [json.loads(line) for line in report.splitlines() if line.startswith("{")]
    assert rows[0]["path"] is None
    assert rows[0]["status"] == ("screenshot" if screenshot else "downloaded")


def test_restricted_opt_in_is_enforced_before_custom_destinations(tmp_path, photo):
    photo = replace(photo, can_download=False)
    remote = Destination()
    http, calls = client()
    with http:
        result, report = run(tmp_path, photo, PhotoDownloader(http, tmp_path), [remote])
    assert result == 1 and not remote.payloads and not calls
    assert "Restricted photos: 1" in report and "Incomplete" in report


def test_transfer_failure_preserves_local_and_allows_later_destinations(tmp_path, photo, caplog):
    good = Destination("last")
    http, calls = client()
    with http:
        result, report = run(tmp_path, photo, PhotoDownloader(http, tmp_path),
                             [LocalPhotoDestination(), Destination(failure=httpx.ConnectError("private URL")), good])
    assert result == 1 and len(good.payloads) == 1 and len(calls) == 1
    assert len(list(tmp_path.rglob("*.jpg"))) == 1
    assert "Failed photos: 1" in report and "Destination custom failures: 1" in report
    assert "private URL" not in caplog.text


def test_cancellation_and_journal_failure_leave_incomplete_appended_reports(tmp_path, photo):
    http, _ = client()
    with http:
        downloader = PhotoDownloader(http, tmp_path)
        run(tmp_path, photo, downloader, [LocalPhotoDestination()])
        for error in (KeyboardInterrupt(), ExportError("Journal changed")):
            class Broken:
                def photos(self):
                    raise error
            report = ExportReport(tmp_path, io.StringIO())
            try:
                with pytest.raises(type(error)):
                    ExportCommand(Broken(), downloader, [LocalPhotoDestination()], report).run()
            finally:
                report.close()
    text = (tmp_path / "pictures.log").read_text()
    assert text.count("=== Photo export ===") == 3 and text.count("Incomplete") == 2


def test_empty_and_duplicate_destinations_fail_before_enumeration(tmp_path):
    http, _ = client()
    report = ExportReport(tmp_path, io.StringIO())
    try:
        for destinations in ([], [LocalPhotoDestination(), LocalPhotoDestination()]):
            with pytest.raises(ExportError):
                ExportCommand(Source(), PhotoDownloader(http, tmp_path), destinations, report)
        assert ExportCommand(Source(), PhotoDownloader(http, tmp_path), [LocalPhotoDestination()], report).run() == 1
    finally:
        http.close()
        report.close()


def test_existing_restricted_is_reported_but_never_uploaded_without_opt_in(tmp_path, photo):
    existing = tmp_path / f"{photo.id}.png"
    existing.write_bytes(b"existing")
    remote = Destination()
    http, calls = client()
    with http:
        result, report = run(tmp_path, replace(photo, can_download=False), PhotoDownloader(http, tmp_path), [remote])
    assert result == 1 and not remote.payloads and not calls
    assert '"status": "existing"' in report and '"status": "restricted"' in report


def test_symlink_entries_are_not_reused_or_overwritten(tmp_path, photo):
    target = tmp_path / "target"
    target.write_bytes(b"private")
    link = tmp_path / f"{photo.id}.jpg"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires Windows Developer Mode or elevated privileges")
    http, _ = client()
    with http:
        assert PhotoDownloader(http, tmp_path).find_existing(photo.id) is None
        directory = tmp_path / "2026-11-06"
        directory.mkdir()
        destination = directory / filename(photo)
        destination.symlink_to(target)
        with pytest.raises(ExportError, match="link"):
            PhotoDownloader(http, tmp_path).save(photo, lambda out: out.write(b"new"))
    assert target.read_bytes() == b"private"


@pytest.mark.parametrize("no_local,member_ok", [(False, True), (True, True), (False, False), (True, False)])
def test_composed_workflow_downloads_uploads_and_reports_album_failure(tmp_path, photo, png, monkeypatch, no_local, member_ok):
    from test_tma_journal import Transport, image, pages
    from toutemonannee.workflow import builder

    album_id, asset_id = uuid4(), uuid4()
    session = Transport(pages([image()]))
    session.journal_id = photo.journal_id
    requests = []
    @contextmanager
    def open_session(config):
        yield session
    real_client = httpx.Client
    def handle(request):
        requests.append(request)
        if ".s3.toutemonannee.com" in request.url.host:
            assert "x-api-key" not in request.headers and "cookie" not in request.headers
            return httpx.Response(200, content=png, headers={"content-type": "image/png"})
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": str(album_id), "albumName": "School"}])
        if request.method == "POST":
            return httpx.Response(201, json={"id": str(asset_id), "status": "created"})
        return httpx.Response(200, json=[{"id": str(asset_id), "success": member_ok, "error": "forbidden"}])
    monkeypatch.setattr(builder, "open_session", open_session)
    monkeypatch.setattr(builder.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    config = Config(destination=tmp_path / "ignored", immich_enabled=True, no_local=no_local,
                    immich_url="https://photos.example", immich_api_key="key", immich_album="School")
    workflow = builder.WorkflowBuilder(config).build()
    assert workflow.run(tmp_path) == workflow.exit_code == (0 if member_ok else 1)
    assert len(requests) == 4
    assert len(list(tmp_path.rglob("*.jpg"))) == (0 if no_local else 1)
    text = (tmp_path / "pictures.log").read_text()
    assert f"Photos uploaded: {int(member_ok)}" in text
    assert ("Incomplete" in text) == (not member_ok)


@pytest.mark.parametrize("extra_length", [0, 10])
def test_compressed_media_validates_wire_length_and_preserves_image_bytes(tmp_path, photo, png, extra_length):
    compressed = gzip.compress(png)
    class WireStream(httpx.SyncByteStream):
        def __iter__(self):
            yield compressed[:10]
            yield compressed[10:]
    def handle(request):
        return httpx.Response(200, stream=WireStream(), headers={
            "content-type": "image/png", "content-encoding": "gzip",
            "content-length": str(len(compressed) + extra_length),
        })
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        downloader = PhotoDownloader(http, tmp_path)
        if extra_length:
            with pytest.raises(ExportError, match="incomplete"):
                downloader.save(photo, lambda out: downloader.download_to(photo, out))
            assert not list(tmp_path.rglob("*.jpg")) and not list(tmp_path.rglob("*.part"))
        else:
            result = downloader.save(photo, lambda out: downloader.download_to(photo, out))
            assert result.path.read_bytes() == png

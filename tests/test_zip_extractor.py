import os
import shutil
import types
import zipfile
from datetime import datetime

from archivist.services import ZipExtractor
from archivist.utils import DryRunRemover, PermanentRemover


def extractor(**options) -> ZipExtractor:
    return ZipExtractor(PermanentRemover(), **options)


def test_extracts_next_to_the_zip_and_deletes_it(tmp_path, make_zip):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x", "sub/b.jpg": "y"})
    assert extractor().extract(zip_path) is True
    assert (tmp_path / "photos" / "a.jpg").read_text() == "x"
    assert (tmp_path / "photos" / "sub" / "b.jpg").is_file()
    assert not zip_path.exists()


def test_restores_file_timestamps(tmp_path):
    zip_path = tmp_path / "photos.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("a.jpg", date_time=(2020, 5, 17, 10, 30, 0)), "x")
    extractor().extract(zip_path)
    mtime = (tmp_path / "photos" / "a.jpg").stat().st_mtime
    assert datetime.fromtimestamp(mtime) == datetime(2020, 5, 17, 10, 30, 0)


def test_leave_zip_keeps_the_archive(tmp_path, make_zip):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    assert extractor(delete_archive=False).extract(zip_path) is True
    assert zip_path.exists() and (tmp_path / "photos" / "a.jpg").exists()


def test_skips_when_the_target_folder_exists(tmp_path, make_zip):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    (tmp_path / "photos").mkdir()
    assert extractor().extract(zip_path) is False
    assert zip_path.exists() and not (tmp_path / "photos" / "a.jpg").exists()


def test_corrupt_zip_is_kept_and_leaves_no_folder(tmp_path):
    zip_path = tmp_path / "broken.zip"
    zip_path.write_bytes(b"not a zip")
    assert extractor().extract(zip_path) is False
    assert zip_path.exists() and not (tmp_path / "broken").exists()


def test_extracts_nested_zips_in_one_run(tmp_path, make_zip):
    make_zip(tmp_path / "outer.zip", {"a.jpg": "x", "inner.zip": {"b.jpg": "y"}})
    assert extractor().extract_all(tmp_path) == (2, 2)
    assert (tmp_path / "outer" / "inner" / "b.jpg").is_file()
    assert not list(tmp_path.rglob("*.zip"))


def test_kept_zips_are_not_extracted_twice(tmp_path, make_zip):
    make_zip(tmp_path / "outer.zip", {"inner.zip": {"b.jpg": "y"}})
    assert extractor(delete_archive=False).extract_all(tmp_path) == (2, 2)
    assert (tmp_path / "outer.zip").exists() and (tmp_path / "outer" / "inner.zip").exists()


def test_stops_at_the_nesting_limit(tmp_path, make_zip, monkeypatch, logs):
    monkeypatch.setattr("archivist.services.zip_extractor.MAX_DEPTH", 2)
    make_zip(tmp_path / "l1.zip", {"l2.zip": {"l3.zip": {"deep.jpg": "x"}}})
    assert extractor().extract_all(tmp_path) == (2, 2)
    assert (tmp_path / "l1" / "l2" / "l3.zip").exists()
    assert "Stopped at nesting depth 2" in logs.text


def test_dry_run_only_reports(tmp_path, make_zip, logs):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x", "inner.zip": {"b.jpg": "y"}})
    dry = ZipExtractor(DryRunRemover(), dry_run=True)
    assert dry.extract_all(tmp_path) == (1, 1)
    assert zip_path.exists() and not (tmp_path / "photos").exists()
    assert "Would extract 2 item(s)" in logs.text
    assert "including 1 nested ZIP(s)" in logs.text
    assert "Would remove: photos.zip" in logs.text


def test_finds_and_extracts_zips_in_any_case(tmp_path, make_zip):
    make_zip(tmp_path / "PHOTOS.ZIP", {"a.jpg": "x"})
    assert extractor().extract_all(tmp_path) == (1, 1)
    assert (tmp_path / "PHOTOS" / "a.jpg").is_file()


def test_failed_extraction_leaves_only_the_zip(tmp_path, make_zip):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "first", "b.jpg": "second-file"})
    zip_path.write_bytes(zip_path.read_bytes().replace(b"second-file", b"SECOND-FILE"))  # bad CRC
    assert extractor().extract(zip_path) is False
    assert [p.name for p in tmp_path.iterdir()] == ["photos.zip"]


def test_staging_folder_left_by_a_killed_run_is_replaced(tmp_path, make_zip, write_file):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    write_file(tmp_path / ".photos.archivist-tmp" / "half-written.jpg")
    assert extractor().extract(zip_path) is True
    assert [p.name for p in (tmp_path / "photos").iterdir()] == ["a.jpg"]
    assert not (tmp_path / ".photos.archivist-tmp").exists()


def test_member_paths_cannot_reach_files_outside_the_target(tmp_path, write_file):
    outside = write_file(tmp_path / "outside.txt", "keep")
    os.utime(outside, (1_000_000_000, 1_000_000_000))
    zip_path = tmp_path / "photos.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("../outside.txt", date_time=(2020, 1, 1, 0, 0, 0)), "evil")
    assert extractor().extract(zip_path) is True
    assert outside.read_text() == "keep"
    assert outside.stat().st_mtime == 1_000_000_000
    assert (tmp_path / "photos" / "outside.txt").read_text() == "evil"


def test_skips_archives_that_do_not_fit(tmp_path, make_zip, monkeypatch, logs):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    monkeypatch.setattr(shutil, "disk_usage", lambda path: types.SimpleNamespace(free=1024))
    for dry_run in (False, True):
        assert ZipExtractor(PermanentRemover(), dry_run=dry_run).extract(zip_path) is False
    assert zip_path.exists() and not (tmp_path / "photos").exists()
    assert "only 1.0 KB is free" in logs.text


def test_skips_zip_bombs(tmp_path, monkeypatch, logs):
    monkeypatch.setattr("archivist.services.zip_extractor.BOMB_MIN_SIZE", 1000)
    zip_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("zeros.bin", b"\0" * 1_000_000)
    assert extractor().extract(zip_path) is False
    assert zip_path.exists() and not (tmp_path / "bomb").exists()
    assert "possible ZIP bomb" in logs.text

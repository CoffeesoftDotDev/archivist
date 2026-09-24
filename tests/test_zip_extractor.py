import os
import shutil
import stat
import types
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from archivist.services import ExtractionResult, ZipExtractor
from archivist.utils import DryRunRemover, PermanentRemover, TrashRemover


def extractor(**options) -> ZipExtractor:
    return ZipExtractor(PermanentRemover(), **options)


def counts(result: ExtractionResult) -> tuple[int, int]:
    return result.found, result.extracted


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
    assert counts(extractor().extract_all(tmp_path)) == (2, 2)
    assert (tmp_path / "outer" / "inner" / "b.jpg").is_file()
    assert not list(tmp_path.rglob("*.zip"))


def test_kept_zips_are_not_extracted_twice(tmp_path, make_zip):
    make_zip(tmp_path / "outer.zip", {"inner.zip": {"b.jpg": "y"}})
    assert counts(extractor(delete_archive=False).extract_all(tmp_path)) == (2, 2)
    assert (tmp_path / "outer.zip").exists() and (tmp_path / "outer" / "inner.zip").exists()


def test_stops_at_the_nesting_limit(tmp_path, make_zip, monkeypatch, logs):
    monkeypatch.setattr("archivist.services.zip_extractor.MAX_DEPTH", 2)
    make_zip(tmp_path / "l1.zip", {"l2.zip": {"l3.zip": {"deep.jpg": "x"}}})
    assert counts(extractor().extract_all(tmp_path)) == (2, 2)
    assert (tmp_path / "l1" / "l2" / "l3.zip").exists()
    assert "Stopped at nesting depth 2" in logs.text


def test_dry_run_only_reports(tmp_path, make_zip, logs):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x", "inner.zip": {"b.jpg": "y"}})
    dry = ZipExtractor(DryRunRemover(), dry_run=True)
    assert counts(dry.extract_all(tmp_path)) == (1, 1)
    assert zip_path.exists() and not (tmp_path / "photos").exists()
    assert "Would extract 2 item(s)" in logs.text
    assert "including 1 nested ZIP(s)" in logs.text
    assert "Would remove: photos.zip" in logs.text


def test_finds_and_extracts_zips_in_any_case(tmp_path, make_zip):
    make_zip(tmp_path / "PHOTOS.ZIP", {"a.jpg": "x"})
    assert counts(extractor().extract_all(tmp_path)) == (1, 1)
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

# ---- archives whose target already exists (#5) ---------------------------


class Answers:
    """A ConfirmMerge callback that records its calls and replies with a fixed answer."""

    def __init__(self, answer: bool):
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def __call__(self, zip_path, folder) -> bool:
        self.calls.append((zip_path.name, folder.name))
        return self.answer


def test_existing_folder_is_listed_and_counted_without_a_terminal(tmp_path, make_zip, write_file, logs):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    result = extractor().extract_all(tmp_path)
    assert (result.found, result.extracted, result.skipped_existing) == (1, 0, 1)
    assert zip_path.exists() and (tmp_path / "photos" / "a.jpg").read_text() == "old"
    assert "1 archive(s) skipped because the target already exists" in logs.text
    assert f"{zip_path} -> existing folder photos" in logs.text
    assert "Run Archivist in a terminal" in logs.text


def test_confirmed_archive_is_extracted_into_the_existing_folder(tmp_path, make_zip, write_file):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "new", "sub/b.jpg": "b"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    write_file(tmp_path / "photos" / "keep.jpg", "mine")
    answers = Answers(True)
    result = extractor(confirm_merge=answers).extract_all(tmp_path)
    assert answers.calls == [("photos.zip", "photos")]
    assert (result.extracted, result.skipped_existing, result.overwritten) == (1, 0, 1)
    folder = tmp_path / "photos"
    assert (folder / "a.jpg").read_text() == "new"
    assert (folder / "sub" / "b.jpg").read_text() == "b"
    assert (folder / "keep.jpg").read_text() == "mine"
    assert not zip_path.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["photos"]  # no staging folder left


def test_merged_files_keep_their_zip_timestamps(tmp_path, write_file):
    write_file(tmp_path / "photos" / "a.jpg", "old")
    with zipfile.ZipFile(tmp_path / "photos.zip", "w") as archive:
        archive.writestr(zipfile.ZipInfo("a.jpg", date_time=(2020, 5, 17, 10, 30, 0)), "new")
    extractor(confirm_merge=Answers(True)).extract_all(tmp_path)
    mtime = (tmp_path / "photos" / "a.jpg").stat().st_mtime
    assert datetime.fromtimestamp(mtime) == datetime(2020, 5, 17, 10, 30, 0)


def test_declined_archive_leaves_the_folder_and_the_zip_alone(tmp_path, make_zip, write_file, listing, logs):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    before = listing(tmp_path)
    result = extractor(confirm_merge=Answers(False)).extract_all(tmp_path)
    assert (result.extracted, result.skipped_existing) == (0, 1)
    assert listing(tmp_path) == before and zip_path.exists()
    assert "skipped, existing folder kept" in logs.text


def test_a_file_at_the_target_path_is_listed_but_never_offered(tmp_path, make_zip, write_file, logs):
    make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    write_file(tmp_path / "photos", "a file named like the folder")
    answers = Answers(True)
    result = extractor(confirm_merge=answers).extract_all(tmp_path)
    assert answers.calls == [] and result.skipped_existing == 1
    assert "photos is a file or link, not a folder" in logs.text


def test_dry_run_lists_existing_folders_without_asking(tmp_path, make_zip, write_file, listing, logs):
    make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    before = listing(tmp_path)
    answers = Answers(True)
    result = ZipExtractor(DryRunRemover(), dry_run=True, confirm_merge=answers).extract_all(tmp_path)
    assert answers.calls == [] and result.skipped_existing == 1
    assert listing(tmp_path) == before
    assert "Would ask whether to extract them into the existing folders" in logs.text


def test_type_clash_skips_the_merge_before_touching_the_folder(tmp_path, make_zip, write_file, listing, logs):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "new", "sub/b.jpg": "b"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    write_file(tmp_path / "photos" / "sub", "a file where the ZIP has a folder")
    before = listing(tmp_path)
    result = extractor(confirm_merge=Answers(True)).extract_all(tmp_path)
    assert (result.extracted, result.skipped_existing, result.overwritten) == (0, 1, 0)
    assert listing(tmp_path) == before and zip_path.exists()
    assert (tmp_path / "photos" / "a.jpg").read_text() == "old"
    assert "is a file in the existing folder but a folder in the ZIP" in logs.text


def test_read_only_file_blocks_the_merge_unless_forced(tmp_path, make_zip, write_file, logs):
    make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    locked = write_file(tmp_path / "photos" / "a.jpg", "old")
    os.chmod(locked, stat.S_IREAD)
    try:
        result = extractor(confirm_merge=Answers(True)).extract_all(tmp_path)
        assert result.skipped_existing == 1 and locked.read_text() == "old"
        assert "is read-only (use --force-readonly-deletion)" in logs.text

        forced = ZipExtractor(PermanentRemover(force_readonly=True), confirm_merge=Answers(True))
        assert forced.extract_all(tmp_path).overwritten == 1
        assert locked.read_text() == "new"
    finally:
        if locked.exists():
            os.chmod(locked, stat.S_IWRITE | stat.S_IREAD)


def test_overwritten_files_go_to_the_bin_with_send_to_bin(tmp_path, make_zip, write_file, monkeypatch, logs):
    binned = []
    monkeypatch.setattr("archivist.utils.removers.send2trash", lambda path: binned.append(Path(path).name) or Path(path).unlink())
    make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    ZipExtractor(TrashRemover(), confirm_merge=Answers(True)).extract_all(tmp_path)
    assert binned == ["a.jpg", "photos.zip"]
    assert (tmp_path / "photos" / "a.jpg").read_text() == "new"
    assert "(old copy: sent to bin)" in logs.text


def test_only_zips_from_the_merged_archive_are_extracted_next(tmp_path, make_zip, write_file):
    make_zip(tmp_path / "photos.zip", {"inner.zip": {"b.jpg": "y"}})
    make_zip(tmp_path / "photos" / "old.zip", {"c.jpg": "z"})  # already there, found by the first scan
    answers = Answers(True)
    result = extractor(delete_archive=False, confirm_merge=answers).extract_all(tmp_path)
    assert answers.calls == [("photos.zip", "photos")]  # old.zip is not offered again in the next pass
    assert (result.found, result.extracted) == (3, 3)
    assert (tmp_path / "photos" / "old" / "c.jpg").is_file()
    assert (tmp_path / "photos" / "inner" / "b.jpg").is_file()


def make_link(link, target) -> None:
    """A directory junction on Windows (no admin rights needed), a symlink elsewhere."""
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("where", ["inside the folder", "the folder itself"])
def test_links_and_junctions_are_never_written_through(tmp_path, make_zip, write_file, where, logs):
    outside = write_file(tmp_path / "outside" / "important.txt", "keep").parent
    root = tmp_path / "root"
    if where == "the folder itself":
        root.mkdir()
        make_link(root / "photos", outside)
        make_zip(root / "photos.zip", {"important.txt": "from zip"})
    else:
        (root / "photos").mkdir(parents=True)
        make_link(root / "photos" / "sub", outside)
        make_zip(root / "photos.zip", {"sub/important.txt": "from zip", "sub/new.txt": "x"})
    answers = Answers(True)
    result = extractor(confirm_merge=answers).extract_all(root)
    assert result.skipped_existing == 1 and result.overwritten == 0
    assert [p.name for p in outside.iterdir()] == ["important.txt"]
    assert (outside / "important.txt").read_text() == "keep"
    assert (root / "photos.zip").exists()
    if where == "the folder itself":
        assert answers.calls == [] and "is a file or link, not a folder" in logs.text
    else:
        assert "is a link or junction" in logs.text


def test_old_copy_survives_when_it_cannot_be_removed(tmp_path, make_zip, write_file, monkeypatch, listing):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    write_file(tmp_path / "photos" / "a.jpg", "old")

    def fail(self, file, readonly):
        raise OSError("disk says no")

    monkeypatch.setattr(PermanentRemover, "_remove_file", fail)
    result = extractor(confirm_merge=Answers(True)).extract_all(tmp_path)
    assert result.skipped_existing == 1
    assert (tmp_path / "photos" / "a.jpg").read_text() == "old"
    assert listing(tmp_path) == ["photos", "photos.zip", "photos/a.jpg"]  # no temporary copy left behind
    assert zip_path.exists()

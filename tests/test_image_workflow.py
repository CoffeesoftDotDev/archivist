import errno
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path

import pytest

from archivist import cli
from archivist.cli.prompts import ImagePrompt
from archivist.core import Config
from archivist.services.image_transfer import ImageRun
from archivist.utils import FileTimes
from archivist.utils.timestamps import FILETIME_EPOCH
from archivist.workflow import WorkflowBuilder


def execute(root, *, approve=lambda question: True, **options):
    workflow = WorkflowBuilder(Config(log_file=None, **options), confirm_images=approve).build()
    report = workflow.run(root)
    return workflow, report


def source_state(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in root.rglob("*") if path.is_file()
    }


def test_copy_keeps_source_tree_bytes_metadata_and_archives(tmp_path, make_zip, write_file):
    root = tmp_path / "source"
    write_file(root / "on-disk.jpg", "ordinary")
    write_file(root / ".DS_Store", "keep")
    make_zip(root / "sub" / "album.zip", {"a.png": "a", "notes.txt": "notes", "inner.zip": {"b.ARW": "b"}})
    before = source_state(root)
    destination = tmp_path / "output"
    workflow, report = execute(root, move_images=True, copy=True, extract_zip=True, apply=True, destination=destination)
    assert workflow.exit_code == 0
    assert source_state(root) == before
    assert sorted(path.name for path in destination.iterdir()) == ["a.png", "b.ARW", "on-disk.jpg"]
    assert (destination / "b.ARW").read_bytes() == b"b"
    assert report["Images copied"] == 3 and report["Images remaining"] == 0
    assert report["ZIPs removed"] == 0
    assert not (root / "sub" / "album").exists()


@pytest.mark.parametrize("copy", [False, True])
def test_disk_exif_and_original_dates_survive_transfer(tmp_path, write_file, exif_photo, copy):
    root = tmp_path / "source"
    source = write_file(root / "photo.jpg", exif_photo)
    created = 1_234_567_800_123_456_700 if os.name == "nt" or sys.platform == "darwin" else None
    dates = FileTimes(1_400_000_000_987_654_300, created, 1_500_000_000_000_000_000)
    dates.restore(source)
    original = FileTimes.read(source)
    destination = tmp_path / "out"
    workflow, report = execute(root, move_images=True, copy=copy, apply=True, destination=destination)
    assert workflow.exit_code == 0 and report["Images copied" if copy else "Images moved"] == 1
    output = destination / "photo.jpg"
    actual = FileTimes.read(output)
    assert actual.modified_ns == original.modified_ns and actual.created_ns == original.created_ns
    assert output.read_bytes() == exif_photo
    tiff = output.read_bytes().split(b"Exif\0\0", 1)[1]
    assert struct.unpack_from("<HHII", tiff, 28) == (0x9003, 2, 20, 56)
    assert tiff[56:76] == b"2001:02:03 04:05:06\0"
    assert source.exists() == copy
    if copy:
        assert source.read_bytes() == exif_photo
        assert FileTimes.read(source).created_ns == original.created_ns
        assert FileTimes.read(source).modified_ns == original.modified_ns


@pytest.mark.parametrize("copy", [False, True])
@pytest.mark.parametrize("publication_copy", [False, True])
def test_nested_zip_exif_and_precise_dates_survive_every_stage(
    tmp_path, make_zip, exif_photo, monkeypatch, copy, publication_copy,
):
    root = tmp_path / "source"
    created = 1_234_567_800_123_456_700 if os.name == "nt" or sys.platform == "darwin" else None
    dates = FileTimes(1_400_000_000_987_654_300, created, 1_500_000_000_000_000_000)
    ticks = lambda value: value // 100 + FILETIME_EPOCH if value is not None else 0
    payload = b"\0" * 4 + struct.pack("<HHQQQ", 1, 24, ticks(dates.modified_ns), ticks(dates.accessed_ns), ticks(dates.created_ns))
    info = zipfile.ZipInfo("photo.jpg", (2020, 1, 1, 0, 0, 0))
    info.extra = struct.pack("<HH", 0x000A, len(payload)) + payload
    archive = make_zip(root / "album.zip", {"inner.zip": {info: exif_photo}})
    original_zip = archive.read_bytes()
    if publication_copy:
        def no_hardlinks(*args):
            raise OSError(errno.EXDEV, "Simulated cross-device publication")
        monkeypatch.setattr("archivist.services.image_transfer.os.link", no_hardlinks)
    output = tmp_path / "out"
    workflow, report = execute(root, move_images=True, copy=copy, apply=True, destination=output)
    assert workflow.exit_code == 0 and report["ZIPs fully extracted"] == 2
    destination = output / "photo.jpg"
    actual = FileTimes.read(destination)
    assert actual.modified_ns == dates.modified_ns
    if created is not None:
        assert actual.created_ns == created
    assert destination.read_bytes() == exif_photo
    assert archive.exists() == copy
    if copy:
        assert archive.read_bytes() == original_zip and not (root / "album").exists()


@pytest.mark.parametrize("failure_stage", ["extraction", "publication", "transfer"])
def test_metadata_failure_retains_originals_and_blocks_zip_disposal(
    tmp_path, make_zip, write_file, monkeypatch, logs, failure_stage,
):
    root = tmp_path / "source"
    source = write_file(root / "on-disk.jpg", b"ordinary")
    archive = make_zip(root / "album.zip", {"photo.jpg": b"archived"})
    original_zip = archive.read_bytes()
    output = tmp_path / "out"
    restore = FileTimes.restore

    def fail_at_stage(dates, path):
        is_extraction = ".archivist-images-" in str(path)
        is_publication = root / "album" in path.parents
        is_transfer = output in path.parents
        if (
            (failure_stage == "extraction" and is_extraction)
            or (failure_stage == "publication" and is_publication)
            or (failure_stage == "transfer" and is_transfer)
        ):
            raise OSError("Cannot preserve original file dates: simulated unsupported filesystem")
        return restore(dates, path)

    monkeypatch.setattr(FileTimes, "restore", fail_at_stage)
    workflow, report = execute(root, move_images=True, apply=True, destination=output)
    assert workflow.exit_code == 1 and report["Images moved"] == 0 and report["ZIPs removed"] == 0
    assert source.read_bytes() == b"ordinary" and archive.read_bytes() == original_zip
    assert "Cannot preserve original file dates" in logs.text
    assert not output.exists() or not list(output.iterdir())


def test_local_timestamp_change_after_approval_prevents_extraction(tmp_path, make_zip, monkeypatch, logs):
    from archivist.services.image_inventory import Snapshot

    info = zipfile.ZipInfo("photo.jpg")
    info.extra = struct.pack("<HHBi", 0x5455, 5, 1, 1_400_000_000)
    archive = make_zip(tmp_path / "album.zip", {info: b"photo"})
    original_verify = Snapshot.verify

    def approve(question):
        payload = bytearray(archive.read_bytes())
        # Change only the local timestamp; preserve source stat checks to exercise
        # the independent timestamp-manifest comparison, not just snapshot drift.
        struct.pack_into("<i", payload, 30 + len(info.filename) + 5, 1_400_000_001)
        archive.write_bytes(payload)
        monkeypatch.setattr(Snapshot, "verify", lambda *args: None)
        return True

    workflow, report = execute(tmp_path, list_images=True, extract_zip=True, apply=True, approve=approve)
    monkeypatch.setattr(Snapshot, "verify", original_verify)
    assert workflow.exit_code == 1 and report["ZIPs removed"] == 0
    assert archive.exists() and "Conflicting local/central ZIP dates" in logs.text


def test_move_fully_extracts_before_transfer_and_delays_zip_deletion(tmp_path, make_zip, write_file, monkeypatch):
    root = tmp_path / "source"
    write_file(root / "ordinary.jpg", "first")
    archive = make_zip(root / "sub" / "album.zip", {"photo.jpg": "archived", "notes.txt": "retain"})
    destination = tmp_path / "out"
    original = ImageRun.transfer

    def check_before_transfer(run, folder):
        assert archive.exists() and (root / "ordinary.jpg").exists()
        assert (root / "sub" / "album" / "notes.txt").read_text() == "retain"
        assert not destination.exists()
        return original(run, folder)

    monkeypatch.setattr(ImageRun, "transfer", check_before_transfer)
    workflow, report = execute(root, move_images=True, apply=True, destination=destination)
    assert workflow.exit_code == 0 and report["Images moved"] == 2
    assert report["ZIPs removed"] == 1 and not archive.exists()
    assert not (root / "ordinary.jpg").exists()
    assert (destination / "photo.jpg").read_text() == "archived"
    assert (root / "sub" / "album" / "notes.txt").exists()


def test_move_leave_zip_keeps_original(tmp_path, make_zip):
    root = tmp_path / "source"
    archive = make_zip(root / "album.zip", {"a.jpg": "image"})
    workflow, _ = execute(root, move_images=True, leave_zip=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 0 and archive.exists()


@pytest.mark.parametrize("approve", [None, lambda question: False, ImagePrompt(lambda question: "")])
def test_decline_or_no_interactive_callback_preserves_all(tmp_path, make_zip, approve):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"a.jpg": "image"})
    before = source_state(root)
    destination = tmp_path / "out"
    workflow, report = execute(root, move_images=True, apply=True, destination=destination, approve=approve)
    assert workflow.exit_code == 1 and report["Images moved"] == 0
    assert source_state(root) == before and not destination.exists()


def test_prompt_eof_declines():
    def closed(question):
        raise EOFError
    assert ImagePrompt(closed)("Proceed?") is False


def test_preview_and_listing_reports_match_and_append(tmp_path, make_zip, write_file):
    root = tmp_path / "source"
    write_file(root / "ordinary.JPG", "disk")
    make_zip(root / "album.zip", {"a.PNG": "zip"})
    before = source_state(root)
    actions = [
        ["--list-pictures"],
        ["--move-pictures", "--dry-run"],
        ["--move-pictures", "--copy", "--dry-run"],
        ["--list-images", "--extract-zip", "--dry-run"],
    ]
    for action in actions:
        assert cli.main(["--parent-folder", str(root), "--filter", "JPG,PNG", *action]) == 0
    reports = (root / "pictures.log").read_text(encoding="utf-8").split("=== Picture inventory ===\n")[1:]
    assert len(reports) == 4 and len(set(reports)) == 1
    after = source_state(root)
    after.pop("pictures.log")
    assert after == before and not (root / "report.log").exists()


def test_listing_never_applies_without_extract_even_with_apply_env(tmp_path, make_zip, monkeypatch):
    make_zip(tmp_path / "album.zip", {"a.jpg": "image"})
    monkeypatch.setenv("ARCHIVIST_APPLY", "true")
    assert cli.main(["--parent-folder", str(tmp_path), "--list-images", "--no-log-file"]) == 0
    assert not (tmp_path / "album").exists()


def test_list_approve_extract_order_without_transfer(tmp_path, make_zip, logs):
    archive = make_zip(tmp_path / "album.zip", {"a.jpg": "image", "notes.txt": "notes"})
    calls = []

    def approve(question):
        assert "Images inside ZIPs: 1" in logs.text
        assert "ZIP disposition: delete only after" in logs.text
        assert not (tmp_path / "album").exists()
        calls.append(question)
        return True

    workflow, _ = execute(tmp_path, list_images=True, extract_zip=True, apply=True, approve=approve)
    assert workflow.exit_code == 0 and len(calls) == 1
    assert (tmp_path / "album" / "a.jpg").exists() and not archive.exists()


@pytest.mark.parametrize("mode", ["copy", "move"])
@pytest.mark.parametrize("failure", [OSError("simulated extraction failure"), KeyboardInterrupt()])
def test_extraction_failure_prevents_all_transfers_and_keeps_archives(tmp_path, make_zip, write_file, monkeypatch, mode, failure):
    root = tmp_path / "source"
    write_file(root / "ordinary.jpg")
    archive = make_zip(root / "album.zip", {"a.jpg": "image"})
    before = source_state(root)
    def broken(*args):
        raise failure
    monkeypatch.setattr(ImageRun, "_extract_archive", broken)
    workflow, report = execute(root, move_images=True, copy=mode == "copy", apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and report["Workflow errors"] == 1
    assert archive.exists() and not (tmp_path / "out").exists()
    assert source_state(root) == before


@pytest.mark.parametrize("failure", [OSError("copy failed"), KeyboardInterrupt()])
def test_failed_or_interrupted_copy_preserves_original_and_removes_partial_output(tmp_path, write_file, monkeypatch, failure):
    root = tmp_path / "source"
    write_file(root / "ordinary.jpg", "photo")
    before = source_state(root)
    def broken(incoming, outgoing, size):
        outgoing.write(b"partial")
        raise failure
    monkeypatch.setattr("archivist.services.image_transfer.copy_bytes", broken)
    workflow, report = execute(root, move_images=True, copy=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and report["Images copied"] == 0
    assert source_state(root) == before
    assert not (tmp_path / "out" / "ordinary.jpg").exists()


def test_partial_transfer_retains_zip_and_reports_remaining(tmp_path, make_zip, write_file, monkeypatch):
    root = tmp_path / "source"
    write_file(root / "a.jpg", "first")
    archive = make_zip(root / "album.zip", {"z.jpg": "last"})
    original_unlink = Path.unlink
    def cannot_remove_last(path, *args, **kwargs):
        if path == root / "album" / "z.jpg":
            raise PermissionError("simulated cross-volume source removal failure")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", cannot_remove_last)
    workflow, report = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and archive.exists()
    assert report["Images moved"] == 1 and report["Images remaining"] == 1
    assert report["ZIPs fully extracted"] == 1
    assert (tmp_path / "out" / "a.jpg").exists()
    assert (tmp_path / "out" / "z.jpg").read_text() == "last"
    assert (root / "album" / "z.jpg").exists()


def test_changed_sources_or_new_destination_after_approval_stop(tmp_path, write_file):
    root = tmp_path / "source"
    source = write_file(root / "a.jpg", "original")
    def change(question):
        source.write_text("new content")
        return True
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out", approve=change)
    assert workflow.exit_code == 1 and source.read_text() == "new content"
    assert not (tmp_path / "out").exists()


def test_destination_collision_appearing_after_approval_is_not_overwritten(tmp_path, write_file):
    root = tmp_path / "source"
    source = write_file(root / "a.jpg", "original")
    destination = tmp_path / "out"
    def occupy(question):
        write_file(destination / "a.jpg", "someone else's file")
        return True
    workflow, _ = execute(root, move_images=True, apply=True, destination=destination, approve=occupy)
    assert workflow.exit_code == 1
    assert source.exists() and (destination / "a.jpg").read_text() == "someone else's file"


@pytest.mark.parametrize("destination_kind", ["same", "inside", "ancestor"])
def test_overlap_rejected_before_report_or_destination_creation(tmp_path, write_file, destination_kind):
    root = tmp_path / "source"
    write_file(root / "a.jpg")
    destination = {"same": root, "inside": root / "out", "ancestor": tmp_path}[destination_kind]
    before = source_state(tmp_path)
    assert cli.main(["--parent-folder", str(root), "--move-images", "--copy", "--destination", str(destination)]) != 0
    assert source_state(tmp_path) == before


def test_hardlinked_report_cannot_modify_source_even_filtered_out(tmp_path, write_file):
    source = write_file(tmp_path / "source.png", "precious")
    os.link(source, tmp_path / "alias.log")
    assert cli.main(["--list-images", "--filter", "jpg", "--parent-folder", str(tmp_path), "--log-file", str(tmp_path / "alias.log")]) != 0
    assert source.read_text() == "precious"


def test_report_cannot_target_source_image_or_create_destination(tmp_path, write_file):
    root = tmp_path / "source"
    image = write_file(root / "a.jpg", "precious")
    assert cli.main(["--list-images", "--parent-folder", str(root), "--log-file", str(image)]) != 0
    assert image.read_text() == "precious"
    destination = tmp_path / "out"
    assert cli.main(["--move-images", "--parent-folder", str(root), "--destination", str(destination), "--log-file", str(destination / "run.log")]) != 0
    assert not destination.exists()


def test_bad_archive_is_incomplete_and_apply_never_prompts(tmp_path, write_file):
    root = tmp_path / "source"
    write_file(root / "a.jpg")
    write_file(root / "broken.zip", "invalid")
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out", approve=lambda question: pytest.fail("must not prompt"))
    assert workflow.exit_code == 1 and not (tmp_path / "out").exists()


def test_existing_extraction_folder_is_never_merged(tmp_path, make_zip, write_file):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"a.jpg": "new"})
    write_file(root / "album" / "a.jpg", "old")
    before = source_state(root)
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and source_state(root) == before


def test_zero_match_move_does_not_extract_or_delete_archives(tmp_path, make_zip):
    root = tmp_path / "source"
    archive = make_zip(root / "album.zip", {"notes.txt": "retain"})
    workflow, report = execute(root, move_images=True, apply=True, destination=tmp_path / "out", approve=lambda question: pytest.fail("no-op"))
    assert workflow.exit_code == 0 and report["Images moved"] == 0
    assert archive.exists() and not (root / "album").exists() and not (tmp_path / "out").exists()


def test_relative_destination_and_noninteractive_cli_safety(tmp_path, write_file, monkeypatch):
    root = tmp_path / "source"
    write_file(root / "a.jpg", "photo")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("archivist.cli.entrypoint.is_interactive", lambda: False)
    argv = ["--move-pictures", "--parent-folder", str(root), "--destination", "output", "--apply", "--no-log-file"]
    assert cli.main(argv) == 1 and not (tmp_path / "output").exists()
    monkeypatch.setattr("archivist.cli.entrypoint.is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda question: "yes")
    assert cli.main(argv) == 0 and (tmp_path / "output" / "a.jpg").exists()


def test_crc_failure_in_nonselected_member_keeps_zip_and_all_pictures(tmp_path, make_zip, write_file):
    root = tmp_path / "source"
    write_file(root / "ordinary.jpg", "keep")
    archive = make_zip(root / "album.zip", {"a.jpg": "image", "notes.txt": "UNSELECTED_PAYLOAD"})
    archive.write_bytes(archive.read_bytes().replace(b"UNSELECTED_PAYLOAD", b"CORRUPTED_PAYLOAD!"))
    before = source_state(root)
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and source_state(root) == before
    assert not (tmp_path / "out").exists()


def test_original_archive_mtime_fallback_orders_destination_copies(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    with zipfile.ZipFile(root / "dates.zip", "w") as archive:
        archive.writestr(zipfile.ZipInfo("new/photo.jpg", (2024, 1, 1, 0, 0, 0)), "new")
        archive.writestr(zipfile.ZipInfo("old/photo.jpg", (2010, 1, 1, 0, 0, 0)), "old")
    before = source_state(root)
    workflow, _ = execute(root, move_images=True, copy=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 0 and source_state(root) == before
    assert (tmp_path / "out" / "photo (001).jpg").read_text() == "old"
    assert (tmp_path / "out" / "photo (002).jpg").read_text() == "new"


def test_missing_space_prevents_extraction_and_transfer(tmp_path, make_zip, monkeypatch):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"a.jpg": "image"})
    before = source_state(root)
    real = shutil.disk_usage(tmp_path)
    monkeypatch.setattr("archivist.services.image_transfer.shutil.disk_usage", lambda path: type(real)(real.total, real.used, 0))
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and source_state(root) == before
    assert not (tmp_path / "out").exists()


def test_publication_without_hardlink_support_remains_exclusive(tmp_path, make_zip, monkeypatch):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"a.jpg": "image"})
    def no_links(*args, **kwargs):
        raise OSError(errno.EOPNOTSUPP, "hardlinks unavailable")
    monkeypatch.setattr("archivist.services.image_transfer.os.link", no_links)
    workflow, _ = execute(root, move_images=True, copy=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 0 and (tmp_path / "out" / "a.jpg").read_text() == "image"


def test_readonly_move_source_fails_without_clearing_attributes(tmp_path, write_file, monkeypatch):
    root = tmp_path / "source"
    source = write_file(root / "a.jpg", "keep")
    monkeypatch.setattr("archivist.services.image_transfer.is_readonly", lambda path: path == source)
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and source.read_text() == "keep"
    assert not (tmp_path / "out" / "a.jpg").exists()


def test_archive_disposal_failure_reports_incomplete_after_successful_transfer(tmp_path, make_zip, monkeypatch):
    root = tmp_path / "source"
    archive = make_zip(root / "album.zip", {"a.jpg": "image"})
    monkeypatch.setattr("archivist.services.image_transfer.is_readonly", lambda path: path == archive)
    workflow, report = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and report["Images moved"] == 1
    assert report["ZIPs removed"] == 0 and archive.exists()


def test_new_sources_after_approval_are_not_added_to_transfer(tmp_path, write_file):
    root = tmp_path / "source"
    write_file(root / "a.jpg")
    def add_file(question):
        write_file(root / "new.jpg")
        return True
    workflow, report = execute(root, move_images=True, apply=True, destination=tmp_path / "out", approve=add_file)
    assert workflow.exit_code == 0 and report["Images moved"] == 1
    assert (root / "new.jpg").exists() and not (tmp_path / "out" / "new.jpg").exists()


@pytest.mark.parametrize("target", ["report", "source"])
def test_link_paths_are_rejected_without_following_them(tmp_path, write_file, target):
    root = tmp_path / "source"
    write_file(root / "a.jpg", "keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside if target == "report" else root, target_is_directory=True)
    except OSError as ex:
        pytest.skip(f"Creating a symlink requires host privileges: {ex}")
    folder = link if target == "source" else root
    args = ["--list-images", "--parent-folder", str(folder)]
    if target == "report":
        args += ["--log-file", str(link / "new" / "report.log")]
    assert cli.main(args) != 0
    assert list(outside.iterdir()) == []
    assert not (root / "pictures.log").exists()


def test_custom_image_report_folder_and_environment_disable(tmp_path, write_file, monkeypatch):
    root = tmp_path / "source"
    write_file(root / "a.jpg")
    logs = tmp_path / "logs"
    assert cli.main(["--list-images", "--parent-folder", str(root), "--log-file", str(logs) + os.sep]) == 0
    assert (logs / "pictures.log").exists() and not (root / "pictures.log").exists()
    monkeypatch.setenv("ARCHIVIST_LOG_FILE", "false")
    assert cli.main(["--list-pictures", "--parent-folder", str(root)]) == 0
    assert not (root / "pictures.log").exists()


def test_cancellation_after_source_unlink_never_removes_last_copy(tmp_path, write_file, monkeypatch):
    root = tmp_path / "source"
    source = write_file(root / "a.jpg", "must survive")
    original = Path.unlink
    def interrupted_unlink(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == source:
            raise KeyboardInterrupt
    monkeypatch.setattr(Path, "unlink", interrupted_unlink)
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and not source.exists()
    assert (tmp_path / "out" / "a.jpg").read_text() == "must survive"


@pytest.mark.parametrize("fail_on_error_only", [False, True])
def test_report_write_failure_returns_nonzero_without_unhandled_exception(tmp_path, make_zip, monkeypatch, fail_on_error_only):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"a.jpg": "keep"})
    before = source_state(root)
    class BrokenReport:
        def write(self, text):
            if not fail_on_error_only or "Workflow stopped" in text:
                raise OSError("report disk full")
        def flush(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(ImageRun, "_open_report", lambda run: setattr(run, "report_stream", BrokenReport()))
    if fail_on_error_only:
        def fail_extract(*args):
            raise OSError("extraction failed too")
        monkeypatch.setattr(ImageRun, "_extract_archive", fail_extract)
    workflow, report = execute(root, move_images=True, copy=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and report["Workflow errors"] >= 1
    assert source_state(root) == before
    assert not (tmp_path / "out").exists()


def test_private_cleanup_failure_is_not_reported_as_completion(tmp_path, make_zip, monkeypatch, logs):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"a.jpg": "keep"})
    cleanup = ImageRun.cleanup
    def fail_cleanup(run):
        cleanup(run)
        raise OSError("cleanup failed")
    monkeypatch.setattr(ImageRun, "cleanup", fail_cleanup)
    workflow, report = execute(root, move_images=True, copy=True, apply=True, destination=tmp_path / "out")
    assert workflow.exit_code == 1 and report["Images copied"] == 1
    assert "Operation completed" not in logs.text
    assert "cleanup failed" in logs.text


def test_nested_extraction_collision_is_rejected_before_approval(tmp_path, make_zip):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"inner.zip": {"a.jpg": "keep"}, "inner/notes.txt": "conflict"})
    before = source_state(root)
    def unexpected_approval(question):
        pytest.fail("Conflicting extraction must not be offered for approval")
    workflow, _ = execute(root, move_images=True, apply=True, destination=tmp_path / "out", approve=unexpected_approval)
    assert workflow.exit_code == 1 and source_state(root) == before

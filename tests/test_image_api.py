import json
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from uuid import UUID

import pytest

from archivist.core import Config
from archivist.services.image_api import (
    ImageApiError, ImageService, InventoryRequest, TransferRequest,
)
from archivist.services.image_transfer import ImageRun


def tree_state(root):
    return {
        str(path.relative_to(root)): (
            path.is_dir(), None if path.is_dir() else path.read_bytes(),
            None if path.is_dir() else path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
    }


def test_inventory_detached_nested_metadata_and_counts(tmp_path, make_zip, write_file):
    write_file(tmp_path / "disk.JPG", b"disk")
    make_zip(tmp_path / "album.zip", {"a.jpg": "a", "movie.mp4": "m", "inner.zip": {"b.ARW": "b"}})
    result = ImageService().inventory(InventoryRequest(tmp_path, ("JPG", ".ARW")))
    assert result.schema_version == 1 and result.complete and not result.problems
    assert result.extensions == ("arw", "jpg")
    assert result.counts.disk_images == 1 and result.counts.archived_images == 2
    assert result.counts.selected_images == 3 and result.counts.total_archives == 2
    assert [archive.direct_images for archive in result.archives] == [1, 1]
    nested = next(item for item in result.items if item.name == "b.ARW")
    assert nested.source.archive_chain == ("inner.zip",) and nested.source.member == "b.ARW"
    assert nested.created_ns is None and nested.ordering_timestamp_source == "modification (fallback)"
    assert isinstance(nested.modified_ns, int)
    assert json.loads(json.dumps(asdict(result)))["counts"]["selected_images"] == 3
    with pytest.raises(FrozenInstanceError):
        nested.name = "changed"
    with pytest.raises(FrozenInstanceError):
        nested.source.member = "changed"


@pytest.mark.parametrize("mode", ["move", "copy"])
def test_preview_writes_nothing_and_does_not_prompt(tmp_path, make_zip, write_file, monkeypatch, capsys, mode):
    root = tmp_path / "source"
    write_file(root / "disk.jpg", b"disk")
    make_zip(root / "album.zip", {"a.jpg": "a", "movie.mp4": "m", "inner.zip": {"b.jpg": "b"}})
    destination = tmp_path / "output"
    before = tree_state(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("write/prompt attempted")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", forbidden)
        patch.setattr("builtins.input", forbidden)
        patch.setattr(ImageRun, "_open_report", forbidden)
        patch.setattr(ImageRun, "extract", forbidden)
        patch.setattr(ImageRun, "transfer", forbidden)
        service = ImageService()
        service.inventory(InventoryRequest(root))
        result = service.prepare_transfer(TransferRequest(root, destination, mode=mode))
    assert tree_state(tmp_path) == before
    assert not destination.exists() and capsys.readouterr().out == ""
    assert len(result.transfers) == 3 and len(result.extractions) == 2
    assert UUID(result.plan_id).version == 4
    assert result.inventory.complete
    json.dumps(asdict(result))


@pytest.mark.parametrize("mode,leave_zip,disposition", [
    ("move", False, "remove_after_success"),
    ("move", True, "keep_original"),
    ("copy", False, "keep_original"),
])
def test_full_mixed_archive_effects(tmp_path, make_zip, mode, leave_zip, disposition):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {
        "folder/": "", "folder/photo.jpg": "p", "movie.mp4": "m", "inner.zip": {"day/nested.jpg": "n"},
    })
    result = ImageService().prepare_transfer(TransferRequest(
        root, tmp_path / "out", mode=mode, extensions=("JPG",), leave_zip=leave_zip,
    ))
    outer, nested = result.extractions
    assert outer.archive_disposition == disposition
    assert len(outer.members) == 4 and len(nested.members) == 1
    assert nested.members[0].relative_path == "inner/day/nested.jpg"
    if mode == "copy":
        assert outer.target is None and nested.target is None
        assert outer.storage == "private_temporary"
        assert all(member.disposition == "temporary" for effect in result.extractions for member in effect.members)
    else:
        assert nested.target == str(root / "album" / "inner")
        assert nested.archive_disposition == "retain_extracted_container"
        assert {member.relative_path for member in outer.members if member.disposition == "retained"} == {
            "folder", "movie.mp4", "inner.zip",
        }
        assert nested.members[0].disposition == "transferred"


@pytest.mark.parametrize("mode", ["move", "copy"])
def test_preview_mapping_matches_cli_preparation(tmp_path, make_zip, write_file, mode):
    root = tmp_path / "source"
    write_file(root / "a" / "photo.jpg", b"a")
    write_file(root / "b" / "photo.jpg", b"b")
    make_zip(root / "album.zip", {"photo.jpg": "z", "other.png": "p"})
    destination = tmp_path / "out"
    write_file(destination / "PHOTO.JPG", b"exists")
    write_file(destination / "photo (001).jpg", b"exists")
    service = ImageService()
    request = TransferRequest(root, destination, mode=mode, extensions=("jpg",))
    preview = service.prepare_transfer(request)
    run = ImageRun(Config(
        move_images=True, copy=mode == "copy", apply=True, destination=destination,
        image_filter=("jpg",), log_file=None,
    ), confirm=lambda question: False)
    run.list(root)
    run.approve(root)
    assert [entry.destination for entry in preview.transfers] == [str(entry.destination) for entry in run.plan]
    assert all(" (00" in entry.destination for entry in preview.transfers)
    assert not run.approved
    assert service.prepare_transfer(request).plan_id != preview.plan_id


def test_dates_and_bytes_remain_original(tmp_path, write_file, exif_photo):
    from archivist.utils import FileTimes

    root = tmp_path / "source"
    source = write_file(root / "photo.jpg", exif_photo)
    original = FileTimes.read(source)
    result = ImageService().prepare_transfer(TransferRequest(root, tmp_path / "out", mode="copy"))
    item, = result.inventory.items
    assert item.created_ns == original.created_ns and item.modified_ns == original.modified_ns
    assert source.read_bytes() == exif_photo
    with pytest.raises(FrozenInstanceError):
        result.transfers[0].destination = "elsewhere"


def test_no_matches_is_complete_and_has_no_extraction(tmp_path, make_zip):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"movie.mp4": "m"})
    result = ImageService().prepare_transfer(TransferRequest(root, tmp_path / "out"))
    assert result.inventory.complete
    assert result.inventory.counts.selected_images == 0 and not result.transfers and not result.extractions


def test_corrupt_inventory_is_explicitly_partial_and_blocks_preview(tmp_path, write_file):
    root = tmp_path / "source"
    write_file(root / "good.jpg", b"p")
    write_file(root / "bad.zip", b"not zip")
    service = ImageService()
    result = service.inventory(InventoryRequest(root))
    assert not result.complete and result.problems and result.counts.disk_images == 1
    with pytest.raises(ImageApiError) as error:
        service.prepare_transfer(TransferRequest(root, tmp_path / "out"))
    assert error.value.code == "incomplete_inventory"


@pytest.mark.parametrize("field,value,code", [
    ("root", "not a Path", "invalid_request"),
    ("extensions", (), "invalid_filter"),
    ("extensions", ("jpg,png",), "invalid_filter"),
    ("extensions", ("mp4",), "invalid_filter"),
    ("extensions", ["jpg"], "invalid_filter"),
    ("schema_version", 2, "unsupported_version"),
    ("schema_version", True, "unsupported_version"),
])
def test_inventory_rejects_invalid_contracts(tmp_path, field, value, code):
    with pytest.raises(ImageApiError) as error:
        ImageService().inventory(replace(InventoryRequest(tmp_path), **{field: value}))
    assert error.value.code == code


@pytest.mark.parametrize("field,value", [("mode", "delete"), ("leave_zip", 1), ("destination", "out")])
def test_transfer_rejects_invalid_contracts(tmp_path, field, value):
    with pytest.raises(ImageApiError) as error:
        ImageService().prepare_transfer(replace(TransferRequest(tmp_path, tmp_path.parent / "out"), **{field: value}))
    assert error.value.code == "invalid_request"


def test_missing_and_file_roots_do_not_report_zero_matches(tmp_path, write_file):
    service = ImageService()
    for path in [tmp_path / "missing", write_file(tmp_path / "file", "x")]:
        with pytest.raises(ImageApiError) as error:
            service.inventory(InventoryRequest(path))
        assert error.value.code == "invalid_root"


def test_wrong_request_types_are_explicit(tmp_path):
    service = ImageService()
    with pytest.raises(ImageApiError, match="InventoryRequest"):
        service.inventory({})
    with pytest.raises(ImageApiError, match="TransferRequest"):
        service.prepare_transfer(InventoryRequest(tmp_path))


def test_destination_overlap_and_file_are_rejected(tmp_path, write_file):
    root = tmp_path / "source"
    write_file(root / "photo.jpg")
    service = ImageService()
    for destination in [root, root / "child", tmp_path]:
        with pytest.raises(ImageApiError) as error:
            service.prepare_transfer(TransferRequest(root, destination))
        assert error.value.code == "invalid_destination"
    with pytest.raises(ImageApiError) as error:
        service.prepare_transfer(TransferRequest(root, write_file(tmp_path / "file")))
    assert error.value.code == "preparation_failed"


def test_existing_extraction_target_blocks_move_but_not_copy(tmp_path, make_zip):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"photo.jpg": "p"})
    (root / "album").mkdir()
    service = ImageService()
    with pytest.raises(ImageApiError, match="target already exists"):
        service.prepare_transfer(TransferRequest(root, tmp_path / "out"))
    assert service.prepare_transfer(TransferRequest(root, tmp_path / "out", mode="copy")).extractions


def test_nested_target_conflict_is_not_hidden_by_preview(tmp_path, make_zip):
    root = tmp_path / "source"
    make_zip(root / "album.zip", {"inner.zip": {"photo.jpg": "p"}, "inner/note.txt": "n"})
    with pytest.raises(ImageApiError, match="Nested extraction target conflicts"):
        ImageService().prepare_transfer(TransferRequest(root, tmp_path / "out", mode="copy"))


def test_unsafe_zip_and_model_package_are_not_treated_as_successful_images(tmp_path, make_zip):
    root = tmp_path / "source"
    make_zip(root / "model.3mf", {"hidden.jpg": "not a collection image"})
    result = ImageService().inventory(InventoryRequest(root))
    assert result.complete and not result.items and not result.archives
    make_zip(root / "unsafe.zip", {"../escape.jpg": "x"})
    result = ImageService().inventory(InventoryRequest(root))
    assert not result.complete and result.problems

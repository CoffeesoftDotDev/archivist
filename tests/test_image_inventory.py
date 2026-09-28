import stat
import struct
import zipfile
from datetime import datetime
from itertools import permutations
from pathlib import Path

import pytest

from archivist.cli import parse_config
from archivist.core import Config
from archivist.services.image_inventory import (
    ImageInventory, ImageItem, ImageWorkflowError, member_path,
)
from archivist.services.image_transfer import plan_names
from archivist.utils.timestamps import FileTimes
from archivist.workflow import WorkflowBuilder


def test_disk_nested_archives_filter_counts_and_no_extraction(tmp_path, make_zip, write_file, listing):
    write_file(tmp_path / "ordinary.JPG")
    write_file(tmp_path / "skip.png")
    write_file(tmp_path / "._metadata.JPG")
    write_file(tmp_path / "@eaDir" / "thumbnail.JPG")
    make_zip(tmp_path / "sub" / "album.zip", {
        "first.JPG": "one", "notes.txt": "notes", "inner.zip": {"day/second.ARW": "two"},
    })
    before = listing(tmp_path)
    inventory = ImageInventory(("jpg", "arw")).scan(tmp_path)
    assert [item.name for item in inventory.items] == ["ordinary.JPG", "first.JPG", "second.ARW"]
    assert len(inventory.archives) == 1
    assert len(list(inventory.archives[0].walk())) == 2
    assert "album.zip :: inner.zip :: day/second.ARW" in inventory.items[-1].location
    assert not inventory.problems
    assert inventory.skipped
    assert listing(tmp_path) == before


@pytest.mark.parametrize("raw,expected", [
    ("JPG, Png,.Jpeg,ARW,jpg", ("arw", "jpeg", "jpg", "png")),
    (".TIFF", ("tiff",)),
])
def test_filter_cli_and_environment_normalize(raw, expected):
    assert parse_config(["--list-images", "--filter", raw], {}).image_filter == expected
    assert parse_config([], {"ARCHIVIST_LIST_IMAGES": "true", "ARCHIVIST_FILTER": raw}).image_filter == expected


@pytest.mark.parametrize("raw", ["", "JPG,", ",PNG", "txt", "*.jpg", "etc.", "jp g"])
def test_filter_rejects_empty_or_unknown_tokens(raw):
    with pytest.raises(SystemExit):
        parse_config(["--list-images", "--filter", raw], {})


@pytest.mark.parametrize("flags", [
    ["--copy"], ["--destination", "out"], ["--filter", "jpg"],
    ["--move-images", "--apply"], ["--move-images", "--copy", "--force"],
    ["--move-images", "--copy", "--send-to-bin"],
])
def test_invalid_action_combinations_are_explicit(flags):
    with pytest.raises(SystemExit, match="Invalid action configuration"):
        parse_config(flags, {})


def test_dry_run_beats_environment_apply_for_new_actions():
    config = parse_config(["--move-pictures", "--copy", "--dry-run"], {"ARCHIVIST_APPLY": "true"})
    assert config.move_images and config.copy and not config.apply


@pytest.mark.parametrize("name", ["../escape.jpg", "/absolute.jpg", "C:/photo.jpg", "x:stream.jpg", "CON.jpg", "a/../x.jpg", "a./b.jpg"])
def test_unsafe_members_are_reported_before_extraction(tmp_path, name):
    with zipfile.ZipFile(tmp_path / "unsafe.zip", "w") as archive:
        archive.writestr(name, b"image")
    inventory = ImageInventory().scan(tmp_path)
    assert inventory.problems and "Unsafe ZIP member" in inventory.problems[0]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["unsafe.zip"]


def test_symlink_archive_member_is_rejected():
    member = zipfile.ZipInfo("link.jpg")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ImageWorkflowError, match="link/special"):
        member_path(member)


@pytest.mark.parametrize("names", [("same.jpg", "SAME.JPG"), ("folder", "folder/pic.jpg")])
def test_ambiguous_archive_targets_report_incomplete(tmp_path, names):
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as archive:
        for name in names:
            archive.writestr(name, b"data")
    assert ImageInventory().scan(tmp_path).problems


def test_bad_and_encrypted_archives_are_not_zero_image_success(tmp_path, write_file):
    write_file(tmp_path / "broken.zip", "not a zip")
    inventory = ImageInventory().scan(tmp_path)
    assert len(inventory.problems) == 1
    member = zipfile.ZipInfo("secret.jpg")
    member.flag_bits = 1
    with pytest.raises(ImageWorkflowError, match="Encrypted"):
        member_path(member)


@pytest.mark.parametrize("constant,value", [
    ("MAX_DEPTH", 1), ("MAX_ARCHIVE_ENTRIES", 1),
    ("MAX_NESTED_ZIP_BYTES", 1), ("MAX_NESTED_TOTAL_BYTES", 1),
])
def test_nested_limits_report_incomplete(tmp_path, make_zip, monkeypatch, constant, value):
    make_zip(tmp_path / "outer.zip", {"first.jpg": "one", "inner.zip": {"second.jpg": "two"}})
    monkeypatch.setattr(f"archivist.services.image_inventory.{constant}", value)
    assert ImageInventory().scan(tmp_path).problems


def test_zip_creation_timestamp_and_modification_fallback(tmp_path):
    created = datetime(2010, 1, 1).timestamp()
    ntfs = b"\0" * 4 + struct.pack("<HHQQQ", 1, 24, 0, 0, int((created + 11_644_473_600) * 10_000_000))
    info = zipfile.ZipInfo("photo.jpg", (2020, 1, 1, 0, 0, 0))
    info.extra = struct.pack("<HH", 0x000A, len(ntfs)) + ntfs
    with zipfile.ZipFile(tmp_path / "dated.zip", "w") as archive:
        archive.writestr(info, b"photo")
        archive.writestr("fallback.jpg", b"other")
    items = {item.name: item for item in ImageInventory().scan(tmp_path).items}
    assert items["photo.jpg"].timestamp == created
    assert items["photo.jpg"].timestamp_source == "creation"
    assert items["fallback.jpg"].timestamp_source == "modification (fallback)"


def image(path: Path, timestamp: float) -> ImageItem:
    return ImageItem(path, path.name, path.suffix[1:].lower(), 1, FileTimes(int(timestamp * 1_000_000_000), int(timestamp * 1_000_000_000)))


def test_collision_all_numbered_oldest_first_and_ties_by_source(tmp_path, write_file):
    write_file(tmp_path / "photo.jpg", "existing")
    write_file(tmp_path / "photo (001).jpg", "existing suffix")
    items = [
        image(Path("z") / "photo.jpg", 3),
        image(Path("b") / "photo.jpg", 1),
        image(Path("a") / "photo.jpg", 1),
        image(Path("c") / "photo (002).jpg", 5),
    ]
    planned = {entry.item.location: entry.destination.name for entry in plan_names(items, tmp_path)}
    assert planned[str(Path("a") / "photo.jpg")] == "photo (003).jpg"
    assert planned[str(Path("b") / "photo.jpg")] == "photo (004).jpg"
    assert planned[str(Path("z") / "photo.jpg")] == "photo (005).jpg"
    assert planned[str(Path("c") / "photo (002).jpg")] == "photo (002).jpg"


def test_incoming_collisions_never_take_free_bare_name(tmp_path):
    items = [image(Path("new") / "photo.jpg", 2), image(Path("old") / "photo.jpg", 1)]
    assert [entry.destination.name for entry in plan_names(items, tmp_path)] == ["photo (001).jpg", "photo (002).jpg"]


def test_collision_order_retains_sub_microsecond_creation_precision(tmp_path):
    newer = ImageItem(Path("a") / "photo.jpg", "photo.jpg", "jpg", 1, FileTimes(0, 1_700_000_000_000_000_100))
    older = ImageItem(Path("z") / "photo.jpg", "photo.jpg", "jpg", 1, FileTimes(0, 1_700_000_000_000_000_000))
    assert plan_names([newer, older], tmp_path)[0].item is older


def test_case_insensitive_existing_names_and_suffixes_beyond_999(tmp_path, write_file):
    write_file(tmp_path / "PHOTO.JPG")
    for number in range(1, 1000):
        write_file(tmp_path / f"photo ({number:03d}).jpg")
    entry, = plan_names([image(Path("in") / "photo.jpg", 1)], tmp_path)
    assert entry.destination.name == "photo (1000).jpg"


def test_explicit_stage_composition_and_copy_prerequisites(tmp_path):
    config = Config(move_images=True, list_images=True, extract_zip=True, copy=True, destination=tmp_path, apply=True)
    steps = WorkflowBuilder(config).build().steps
    assert [type(step).__name__ for step in steps] == [
        "ListImages", "ConfirmImagePlan", "ExtractImageArchives", "TransferImages",
    ]
    assert [type(step).__name__ for step in WorkflowBuilder(Config(list_images=True, extract_zip=True)).build().steps] == ["ListImages"]
    assert [type(step).__name__ for step in WorkflowBuilder(Config(extract_zip=True)).build().steps] == ["ExtractArchives"]


@pytest.mark.parametrize("actions", list(permutations(["--list-images", "--extract-zip", "--move-pictures", "--copy"])))
def test_action_argument_order_keeps_one_dependency_order(tmp_path, actions):
    config = parse_config([*actions, "--apply", "--destination", str(tmp_path)], {})
    assert [type(step).__name__ for step in WorkflowBuilder(config).build().steps] == [
        "ListImages", "ConfirmImagePlan", "ExtractImageArchives", "TransferImages",
    ]


def test_unsupported_zip_compression_is_an_inventory_error():
    member = zipfile.ZipInfo("photo.jpg")
    member.compress_type = 99
    with pytest.raises(ImageWorkflowError, match="Unsupported ZIP compression"):
        member_path(member)


def test_archive_bomb_ratio_rejected_before_extraction(tmp_path, monkeypatch):
    with zipfile.ZipFile(tmp_path / "large.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("photo.jpg", b"0" * 10000)
    monkeypatch.setattr("archivist.services.image_inventory.BOMB_MIN_SIZE", 100)
    assert "expansion ratio" in ImageInventory().scan(tmp_path).problems[0]


def test_filesystem_without_birth_time_uses_mtime_not_ctime(tmp_path, write_file, monkeypatch):
    from types import SimpleNamespace
    from archivist.utils import timestamps

    source = write_file(tmp_path / "a.jpg")
    original_stat = Path.stat

    def without_birthtime(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        if path == source:
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_") and not name.startswith("st_birthtime")}
            values["st_ctime"] = 1
            values["st_mtime"] = 2
            values["st_mtime_ns"] = 2_000_000_000
            return SimpleNamespace(**values)
        return info

    monkeypatch.setattr(Path, "stat", without_birthtime)
    # Only timestamp capture changes platform, not pathlib's platform choice.
    monkeypatch.setattr(timestamps, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(timestamps, "sys", SimpleNamespace(platform="linux"))
    item, = ImageInventory().scan(tmp_path).items
    assert item.timestamp == 2 and item.timestamp_source == "modification (fallback)"

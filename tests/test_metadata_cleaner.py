import os
import stat

import pytest

from archivist.services import MetadataCleaner
from archivist.utils import DryRunRemover, PermanentRemover, TrashRemover


def cleaner(remover=None) -> MetadataCleaner:
    return MetadataCleaner(remover or PermanentRemover())


def test_removes_only_small_appledouble_files(tmp_path, write_file):
    small = write_file(tmp_path / "album" / "._a.jpg", b"x" * 2048)
    large = write_file(tmp_path / "._big", b"x" * 2049)
    normal = write_file(tmp_path / "a.jpg")
    assert cleaner().remove_appledouble_files(tmp_path, max_size=2048) == 1
    assert not small.exists()
    assert large.exists() and normal.exists()


def test_removes_appledouble_folders_without_visible_files(tmp_path, write_file):
    write_file(tmp_path / "._meta" / ".hidden")
    (tmp_path / "._meta" / "empty").mkdir()
    write_file(tmp_path / "._keep" / "deep" / "photo.jpg")
    write_file(tmp_path / "album" / ".hidden")
    assert cleaner().remove_metadata_folders(tmp_path) == 1
    assert not (tmp_path / "._meta").exists()
    assert (tmp_path / "._keep" / "deep" / "photo.jpg").exists()
    assert (tmp_path / "album").exists()


def test_removes_eadir_folders_and_counts_nested_ones_once(tmp_path, write_file):
    write_file(tmp_path / "album" / "@eaDir" / "thumb.jpg")
    write_file(tmp_path / "album" / "@eaDir" / "@eaDir" / "x")
    write_file(tmp_path / "other" / "@eaDir" / "y")
    assert cleaner().remove_eadir_folders(tmp_path) == 2
    assert not list(tmp_path.rglob("@eaDir"))


def test_removes_named_files_in_any_case(tmp_path, write_file):
    for name in ("Thumbs.db", "a/thumbs.db", "b/THUMBS.DB"):
        write_file(tmp_path / name)
    write_file(tmp_path / "Thumbs.db.bak")
    assert cleaner().remove_files_named(tmp_path, "Thumbs.db") == 3
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["Thumbs.db.bak"]


def test_dry_run_counts_the_same_but_changes_nothing(tmp_path, write_file, listing):
    write_file(tmp_path / "._a")
    write_file(tmp_path / "._meta" / ".x")
    write_file(tmp_path / "album" / "@eaDir" / "@eaDir" / "t")
    before = listing(tmp_path)
    dry = cleaner(DryRunRemover())
    assert dry.remove_appledouble_files(tmp_path, max_size=2048) == 1
    assert dry.remove_metadata_folders(tmp_path) == 1
    assert dry.remove_eadir_folders(tmp_path) == 1
    assert listing(tmp_path) == before


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write read-only files")
def test_read_only_file_is_skipped_unless_forced(tmp_path, write_file):
    file = write_file(tmp_path / "._locked")
    os.chmod(file, stat.S_IREAD)
    assert cleaner().remove_appledouble_files(tmp_path, max_size=2048) == 0
    assert file.exists()
    assert cleaner(PermanentRemover(force_readonly=True)).remove_appledouble_files(tmp_path, max_size=2048) == 1
    assert not file.exists()


@pytest.mark.parametrize("remover", [PermanentRemover(), DryRunRemover()])
def test_removes_macosx_trees_and_counts_nested_ones_once(tmp_path, write_file, listing, remover):
    write_file(tmp_path / "_MACOSX" / "visible.jpg", b"x" * 4096)
    write_file(tmp_path / "_MACOSX" / "deep" / "__MACOSX" / "metadata")
    write_file(tmp_path / "album" / "__MACOSX" / "deep" / "content")
    (tmp_path / "empty" / "__MACOSX").mkdir(parents=True)
    kept = [
        write_file(tmp_path / "album" / "photo.jpg"),
        write_file(tmp_path / "__MACOSX.bak" / "content"),
        write_file(tmp_path / "files" / "_MACOSX"),
        write_file(tmp_path / "files" / "__MACOSX"),
    ]
    before = listing(tmp_path)

    assert cleaner(remover).remove_macosx_folders(tmp_path) == 3

    assert all(path.exists() for path in kept)
    if isinstance(remover, DryRunRemover):
        assert listing(tmp_path) == before
    else:
        assert not (tmp_path / "_MACOSX").exists()
        assert not (tmp_path / "album" / "__MACOSX").exists()
        assert not (tmp_path / "empty" / "__MACOSX").exists()


def test_macosx_cleanup_uses_trash_for_the_whole_tree(tmp_path, write_file, monkeypatch):
    folder = tmp_path / "__MACOSX"
    content = write_file(folder / "deep" / "file")
    sent = []
    monkeypatch.setattr("archivist.utils.removers.send2trash", sent.append)

    assert cleaner(TrashRemover()).remove_macosx_folders(tmp_path) == 1
    assert sent == [folder]
    assert content.exists()  # the fake trash strategy records, rather than deletes


def test_macosx_cleanup_logs_removal_errors_and_continues(tmp_path, write_file, monkeypatch, logs):
    write_file(tmp_path / "_MACOSX" / "file")
    write_file(tmp_path / "album" / "__MACOSX" / "file")
    remover = PermanentRemover()
    remove_tree = remover.remove_tree

    def fail_one(folder):
        if folder.name == "_MACOSX":
            raise PermissionError("access denied")
        remove_tree(folder)

    monkeypatch.setattr(remover, "remove_tree", fail_one)

    assert cleaner(remover).remove_macosx_folders(tmp_path) == 1
    assert (tmp_path / "_MACOSX" / "file").exists()
    assert not (tmp_path / "album" / "__MACOSX").exists()
    assert "Failed:" in logs.text and "access denied" in logs.text


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write read-only files")
def test_macosx_readonly_tree_is_kept_unless_forced(tmp_path, write_file, logs):
    locked = write_file(tmp_path / "__MACOSX" / "deep" / "locked")
    os.chmod(locked, stat.S_IREAD)
    try:
        assert cleaner().remove_macosx_folders(tmp_path) == 0
        assert locked.exists()
        assert "--force-readonly-deletion" in logs.text
        assert cleaner(PermanentRemover(force_readonly=True)).remove_macosx_folders(tmp_path) == 1
        assert not locked.exists()
    finally:
        if locked.exists():
            os.chmod(locked, stat.S_IWRITE | stat.S_IREAD)


@pytest.mark.parametrize("link_name", ["__MACOSX", "linked-album"])
def test_macosx_cleanup_never_follows_directory_links(tmp_path, write_file, link_name):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    content = write_file(outside / "__MACOSX" / "keep")
    link = root / link_name
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as ex:
        pytest.skip(f"Creating a symlink requires host privileges: {ex}")

    assert cleaner().remove_macosx_folders(root) == 0
    assert content.exists() and link.is_symlink()

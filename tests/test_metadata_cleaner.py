import os
import stat

import pytest

from archivist.services import MetadataCleaner
from archivist.utils import DryRunRemover, PermanentRemover


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

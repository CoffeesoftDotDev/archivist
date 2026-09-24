import os
import stat
import sys
from pathlib import Path

import pytest

from archivist.utils import (
    DryRunRemover,
    PermanentRemover,
    TrashRemover,
    find_files,
    is_link,
    format_size,
    is_hidden,
    is_readonly,
    make_remover,
)

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write read-only files"
)


def make_readonly(path: Path) -> Path:
    os.chmod(path, stat.S_IREAD)
    return path


def test_dot_files_are_hidden(tmp_path, write_file):
    assert is_hidden(write_file(tmp_path / ".DS_Store"))
    assert is_hidden(write_file(tmp_path / "._photo.jpg"))
    assert not is_hidden(write_file(tmp_path / "photo.jpg"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file attributes")
def test_windows_hidden_attribute_counts_as_hidden(tmp_path, write_file):
    import ctypes

    file = write_file(tmp_path / "Thumbs.db")
    ctypes.windll.kernel32.SetFileAttributesW(str(file), stat.FILE_ATTRIBUTE_HIDDEN)
    assert is_hidden(file)


def test_find_files_ignores_case_and_skips_folders(tmp_path, write_file):
    for name in ("a.zip", "b.ZIP", "sub/c.Zip", "notes.txt"):
        write_file(tmp_path / name)
    (tmp_path / "folder.zip").mkdir()
    found = sorted(p.relative_to(tmp_path).as_posix() for p in find_files(tmp_path, "*.zip"))
    assert found == ["a.zip", "b.ZIP", "sub/c.Zip"]


@pytest.mark.parametrize(
    ("size", "text"),
    [(0, "0 B"), (1023, "1023 B"), (1536, "1.5 KB"), (5 * 1024**3, "5.0 GB"), (3 * 1024**4, "3.0 TB")],
)
def test_format_size(size, text):
    assert format_size(size) == text


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, PermanentRemover),
        ({"to_trash": True}, TrashRemover),
        ({"dry_run": True}, DryRunRemover),
        ({"dry_run": True, "to_trash": True}, DryRunRemover),
    ],
)
def test_make_remover_picks_the_strategy(options, expected):
    assert type(make_remover(**options)) is expected


def test_permanent_remover_deletes(tmp_path, write_file):
    file = write_file(tmp_path / "a")
    folder = tmp_path / "tree"
    write_file(folder / "sub" / "b")
    remover = PermanentRemover()
    assert remover.remove_file(file) is True
    remover.remove_tree(folder)
    assert not file.exists() and not folder.exists()


def test_trash_remover_sends_to_the_bin(tmp_path, write_file, monkeypatch):
    sent = []
    monkeypatch.setattr("archivist.utils.removers.send2trash", sent.append)
    file = write_file(tmp_path / "a")
    folder = tmp_path / "tree"
    write_file(folder / "b")
    remover = TrashRemover()
    assert remover.remove_file(file) is True
    remover.remove_tree(folder)
    assert sent == [file, folder]


def test_dry_run_remover_changes_nothing(tmp_path, write_file):
    file = write_file(tmp_path / "a")
    folder = tmp_path / "tree"
    write_file(folder / "b")
    remover = DryRunRemover()
    assert remover.remove_file(file) is True
    remover.remove_tree(folder)
    assert file.exists() and (folder / "b").exists()


@needs_non_root
def test_read_only_file_is_kept_unless_forced(tmp_path, write_file):
    file = make_readonly(write_file(tmp_path / "a"))
    assert is_readonly(file)
    assert PermanentRemover().remove_file(file) is False
    assert file.exists()
    assert PermanentRemover(force_readonly=True).remove_file(file) is True
    assert not file.exists()


@needs_non_root
def test_tree_with_a_read_only_item_is_left_whole_unless_forced(tmp_path, write_file):
    folder = tmp_path / "tree"
    write_file(folder / "a")
    make_readonly(write_file(folder / "b"))
    with pytest.raises(PermissionError):
        PermanentRemover().remove_tree(folder)
    assert (folder / "a").exists() and (folder / "b").exists()
    PermanentRemover(force_readonly=True).remove_tree(folder)
    assert not folder.exists()


@needs_non_root
def test_dry_run_reports_read_only_items_without_clearing_the_flag(tmp_path, write_file):
    file = make_readonly(write_file(tmp_path / "a"))
    assert DryRunRemover().remove_file(file) is False
    assert DryRunRemover(force_readonly=True).remove_file(file) is True
    assert is_readonly(file)


def test_is_link_catches_symlinks_and_windows_junctions(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        assert not link.is_symlink()  # the case is_symlink() misses
    else:
        link.symlink_to(target, target_is_directory=True)
    assert is_link(link)
    assert not is_link(target)
    assert not is_link(tmp_path / "missing")

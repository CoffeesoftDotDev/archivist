"""The option declarations on Config drive both the ARCHIVIST_* variables and the flags (#1)."""
import argparse
from pathlib import Path

import pytest

from archivist.cli import build_parser, parse_config
from archivist.cli.parser import add_generated_option
from archivist.core import Config
from archivist.core.config import Option

# The full --help text at a fixed width. It was captured from the hand-written parser before #1, and is
# identical on Python 3.10 and 3.13; generating the flags must not change a character of it.
HELP = """\
usage: archivist [-h] [--parent-folder PARENT_FOLDER] [--leave-zip] [--leave-appledouble]
                 [--leave-eadir] [--leave-ds-store] [--leave-thumbs-db] [--leave-desktop-ini]
                 [--max-size APPLEDOUBLE_MAX_SIZE] [--force-readonly-deletion] [--send-to-bin]
                 [--apply] [--log-file [PATH] | --no-log-file]

Extract ZIPs recursively and clean macOS, Windows and Synology metadata.

options:
  -h, --help            show this help message and exit
  --parent-folder PARENT_FOLDER
                        Parent folder to process. If omitted or empty, you will be prompted.
  --leave-zip           Keep ZIP archives after extraction (default: they are deleted).
  --leave-appledouble   Do not remove macOS AppleDouble metadata (small '._' files and '._'
                        folders with no visible files).
  --leave-eadir         Do not remove Synology '@eaDir' folders.
  --leave-ds-store      Do not remove macOS '.DS_Store' files.
  --leave-thumbs-db     Do not remove Windows 'Thumbs.db' thumbnail caches.
  --leave-desktop-ini   Do not remove Windows 'desktop.ini' files (they hold custom folder icons
                        and names).
  --max-size APPLEDOUBLE_MAX_SIZE
                        Max size in bytes for '._' files to be removed (default: 2048).
  --force-readonly-deletion, --force
                        Clear the read-only flag and delete read-only files/folders (default:
                        read-only items are skipped).
  --send-to-bin         Send removed items to the Recycle Bin / Trash instead of deleting them
                        permanently.
  --apply               Make the changes: extract, move and delete. Without it, Archivist only
                        shows what it would do.
  --log-file [PATH]     Write the report to PATH (a file, or a folder that will contain
                        report.log). Default: <parent-folder>/report.log. The console always shows
                        the report.
  --no-log-file         Do not write the report to a file (console only).
"""

# A value to give each generated option, by field type, and the raw text that produces it
SAMPLES = {bool: ([], "true", True), int: (["7"], "7", 7), Path | None: (["photos"], "photos", Path("photos"))}

GENERATED = [(f.name, f.type, opt) for f, opt in Config.options() if opt.flags]


def test_help_text_is_unchanged(monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    assert build_parser(Config()).format_help() == HELP


def test_every_field_is_declared_with_a_unique_variable():
    names = [opt.env for _, opt in Config.options()]
    assert len(names) == len(Config.__dataclass_fields__)
    assert len(set(names)) == len(names)


@pytest.mark.parametrize(("name", "kind", "opt"), GENERATED, ids=[name for name, _, _ in GENERATED])
def test_each_generated_option_is_set_by_every_flag_and_by_its_variable(name, kind, opt):
    args, raw, expected = SAMPLES[kind]
    assert getattr(parse_config([], environ={}), name) == getattr(Config(), name)
    for flag in opt.flags:  # aliases too, such as --force
        assert getattr(parse_config([flag, *args], environ={}), name) == expected
    assert getattr(parse_config([], environ={f"ARCHIVIST_{opt.env}": raw}), name) == expected


def test_hand_written_options_have_no_generated_flag():
    hand_written = [f.name for f, opt in Config.options() if not opt.flags]
    assert hand_written == ["apply", "log_file"]


def test_a_type_without_a_flag_shape_is_refused():
    with pytest.raises(TypeError, match="hand-written flag"):
        add_generated_option(argparse.ArgumentParser(), "name", str, Option(("--name",), "NAME", "", None), "")

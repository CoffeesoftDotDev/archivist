"""The option declarations on Config drive both the ARCHIVIST_* variables and the flags (#1)."""
import argparse
from pathlib import Path

import pytest

from archivist.cli import build_parser, parse_config
from archivist.cli.parser import add_generated_option
from archivist.core import Config
from archivist.core.config import Option

# The full --help text at a fixed width, including generated flags and aliases.
HELP = """\
usage: archivist [-h] [--parent-folder PARENT_FOLDER] [--list-images] [--move-images]
                 [--extract-zip] [--destination DESTINATION] [--copy] [--leave-zip]
                 [--leave-appledouble] [--leave-eadir] [--leave-ds-store] [--leave-thumbs-db]
                 [--leave-desktop-ini] [--max-size APPLEDOUBLE_MAX_SIZE]
                 [--force-readonly-deletion] [--send-to-bin] [--filter EXTENSIONS] [--apply]
                 [--log-file [PATH] | --no-log-file]

Inventory and transfer pictures, extract ZIPs, and clean filesystem metadata.

options:
  -h, --help            show this help message and exit
  --parent-folder PARENT_FOLDER
                        Parent folder to process. If omitted or empty, you will be prompted.
  --list-images, --list-pictures
                        List pictures on disk and inside ZIPs; write pictures.log.
  --move-images, --move-pictures
                        Inventory, ask for approval, extract ZIPs, then move pictures.
  --extract-zip         Select ZIP extraction explicitly, without implicit metadata cleanup.
  --destination DESTINATION
                        Flat picture destination; relative paths use the current directory.
  --copy                With --move-images, copy instead; preserve source pictures and ZIPs.
  --leave-zip           Keep ZIP archives after extraction (default: they are deleted).
  --leave-appledouble   Do not remove AppleDouble metadata (small '._' files and '._' folders with
                        no visible files).
  --leave-eadir         Do not remove Synology '@eaDir' folders.
  --leave-ds-store      Do not remove '.DS_Store' files.
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
  --filter EXTENSIONS   Comma-separated image extensions, e.g. JPG,Png,Jpeg,ARW.
  --apply               Make the changes: extract, move and delete. Without it, Archivist only
                        shows what it would do.
  --log-file [PATH]     Write the report to PATH (a file, or a folder that will contain
                        report.log, or pictures.log for image workflows). Default: <parent-
                        folder>/report.log (pictures.log for images). The console always shows the
                        report.
  --no-log-file         Do not write the report to a file (console only).
"""

# A value to give each generated option, by field type, and the raw text that produces it
SAMPLES = {bool: ([], "true", True), int: (["7"], "7", 7), Path | None: (["photos"], "photos", Path("photos"))}

GENERATED = [(f.name, f.type, opt) for f, opt in Config.options() if opt.flags]


def test_help_text_matches_declared_options(monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    assert build_parser(Config()).format_help() == HELP


def test_every_field_is_declared_with_a_unique_variable():
    names = [opt.env for _, opt in Config.options()]
    assert len(names) == len(Config.__dataclass_fields__)
    assert len(set(names)) == len(names)


@pytest.mark.parametrize(("name", "kind", "opt"), GENERATED, ids=[name for name, _, _ in GENERATED])
def test_each_generated_option_is_set_by_every_flag_and_by_its_variable(name, kind, opt):
    args, raw, expected = SAMPLES[kind]
    prerequisites = ["--move-images"] if name in ("destination", "copy") else []
    assert getattr(parse_config([], environ={}), name) == getattr(Config(), name)
    for flag in opt.flags:  # aliases too, such as --force
        assert getattr(parse_config([*prerequisites, flag, *args], environ={}), name) == expected
    assert getattr(parse_config(prerequisites, environ={f"ARCHIVIST_{opt.env}": raw}), name) == expected


def test_hand_written_options_have_no_generated_flag():
    hand_written = [f.name for f, opt in Config.options() if not opt.flags]
    assert hand_written == ["image_filter", "apply", "log_file"]


def test_a_type_without_a_flag_shape_is_refused():
    with pytest.raises(TypeError, match="hand-written flag"):
        add_generated_option(argparse.ArgumentParser(), "name", str, Option(("--name",), "NAME", "", None), "")

"""Command-line flags: one per Config field, with the ARCHIVIST_* variables as defaults."""
import argparse
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path

from ..core import Config


def build_parser(defaults: Config) -> argparse.ArgumentParser:
    """One flag per Config field; `defaults` already include the ARCHIVIST_* variables."""
    parser = argparse.ArgumentParser(
        prog="archivist",
        description="Extract ZIPs recursively and clean macOS, Windows and Synology metadata.",
    )
    parser.add_argument(
        "--parent-folder",
        dest="parent_folder",
        # Empty means "not given" (as for ARCHIVIST_* variables), never the current folder
        type=lambda value: Path(value) if value.strip() else defaults.parent_folder,
        default=defaults.parent_folder,
        help="Parent folder to process. If omitted or empty, you will be prompted.",
    )
    parser.add_argument(
        "--leave-zip",
        dest="leave_zip",
        action="store_true",
        default=defaults.leave_zip,
        help="Keep ZIP archives after extraction (default: they are deleted).",
    )
    parser.add_argument(
        "--leave-appledouble",
        dest="leave_appledouble",
        action="store_true",
        default=defaults.leave_appledouble,
        help="Do not remove macOS AppleDouble metadata "
             "(small '._' files and '._' folders with no visible files).",
    )
    parser.add_argument(
        "--leave-eadir",
        dest="leave_eadir",
        action="store_true",
        default=defaults.leave_eadir,
        help="Do not remove Synology '@eaDir' folders.",
    )
    parser.add_argument(
        "--leave-ds-store",
        dest="leave_ds_store",
        action="store_true",
        default=defaults.leave_ds_store,
        help="Do not remove macOS '.DS_Store' files.",
    )
    parser.add_argument(
        "--leave-thumbs-db",
        dest="leave_thumbs_db",
        action="store_true",
        default=defaults.leave_thumbs_db,
        help="Do not remove Windows 'Thumbs.db' thumbnail caches.",
    )
    parser.add_argument(
        "--leave-desktop-ini",
        dest="leave_desktop_ini",
        action="store_true",
        default=defaults.leave_desktop_ini,
        help="Do not remove Windows 'desktop.ini' files (they hold custom folder icons and names).",
    )
    parser.add_argument(
        "--max-size",
        dest="appledouble_max_size",
        type=int,
        default=defaults.appledouble_max_size,
        help="Max size in bytes for '._' files to be removed (default: %(default)s).",
    )
    parser.add_argument(
        "--force-readonly-deletion",
        "--force",
        dest="force_readonly",
        action="store_true",
        default=defaults.force_readonly,
        help="Clear the read-only flag and delete read-only files/folders "
             "(default: read-only items are skipped).",
    )
    parser.add_argument(
        "--send-to-bin",
        dest="send_to_bin",
        action="store_true",
        default=defaults.send_to_bin,
        help="Send removed items to the Recycle Bin / Trash instead of "
             "deleting them permanently.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=defaults.dry_run,
        help="Show what would be extracted and removed without changing anything.",
    )
    add_log_file_options(parser, defaults.log_file)
    return parser


def add_log_file_options(parser: argparse.ArgumentParser, default: str | None) -> None:
    """
    --log-file [PATH] and --no-log-file, the one option with three states (see Config.log_file).
    Kept hand-written on purpose: a flag with an optional value, plus a second flag writing the same
    field, can't be generated from a settings class, so this function is added to the generated parser.
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--log-file",
        dest="log_file",
        nargs="?",
        const="",
        default=default,
        metavar="PATH",
        help="Write the report to PATH (a file, or a folder that will contain "
             "report.log). Default: <parent-folder>/report.log. "
             "The console always shows the report.",
    )
    group.add_argument(
        "--no-log-file",
        dest="log_file",
        action="store_const",
        const=None,
        default=default,
        help="Do not write the report to a file (console only).",
    )


def parse_config(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> Config:
    """Precedence: CLI flag > ARCHIVIST_* variable > built-in default."""
    try:
        defaults = Config.from_env(environ)
    except ValueError as ex:
        raise SystemExit(f"Invalid environment configuration: {ex}") from None
    ns = build_parser(defaults).parse_args(argv)
    return Config(**{f.name: getattr(ns, f.name) for f in fields(Config)})

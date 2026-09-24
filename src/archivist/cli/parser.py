"""Command-line flags: generated from the Config declarations, plus the hand-written ones."""
import argparse
import os
import sys
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

from ..core import Config
from ..core.config import ENV_PREFIX, Option

# Default for flags in a mutually exclusive group. Python 3.10's argparse (still in CI) only spots a clash
# when a flag's value differs from its default ("is not"), so a bare --log-file ("") next to a "" default
# went unnoticed. Nothing a flag can produce is this object; parse_config() swaps in the real default.
NOT_GIVEN = object()


def build_parser(defaults: Config) -> argparse.ArgumentParser:
    """Flags generated from the Config declarations, then the hand-written ones; `defaults` include the variables."""
    parser = argparse.ArgumentParser(
        prog="archivist",
        description="Extract ZIPs recursively and clean macOS, Windows and Synology metadata.",
    )
    for f, opt in Config.options():
        if opt.flags:
            add_generated_option(parser, f.name, f.type, opt, getattr(defaults, f.name))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        dest="apply",
        action="store_const",
        const=True,
        default=NOT_GIVEN,
        help="Make the changes: extract, move and delete. "
             "Without it, Archivist only shows what it would do.",
    )
    # Kept so older scripts still work; a dry run is now the default.
    mode.add_argument("--dry-run", dest="legacy_dry_run", action="store_true", help=argparse.SUPPRESS)
    add_log_file_options(parser)
    return parser


def add_generated_option(parser: argparse.ArgumentParser, dest: str, kind: Any, opt: Option, default: Any) -> None:
    """One flag from a Config declaration, shaped by the field type."""
    if kind is bool:
        parser.add_argument(*opt.flags, dest=dest, action="store_true", default=default, help=opt.help)
    elif kind is int:
        parser.add_argument(*opt.flags, dest=dest, type=int, default=default, help=opt.help)
    elif kind == Path | None:
        # Empty means "not given" (as for ARCHIVIST_* variables), never the current folder
        parser.add_argument(
            *opt.flags, dest=dest, default=default, help=opt.help,
            type=lambda value: Path(value) if value.strip() else default,
        )
    else:
        raise TypeError(f"No flag shape for {dest}: {kind}. Give it a hand-written flag instead.")


def add_log_file_options(parser: argparse.ArgumentParser) -> None:
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
        default=NOT_GIVEN,
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
        default=NOT_GIVEN,
        help="Do not write the report to a file (console only).",
    )


def parse_config(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> Config:
    """Precedence: CLI flag > ARCHIVIST_* variable > built-in default."""
    try:
        defaults = Config.from_env(environ)
    except ValueError as ex:
        raise SystemExit(f"Invalid environment configuration: {ex}") from None
    ns = build_parser(defaults).parse_args(argv)
    for name in ("apply", "log_file"):
        if getattr(ns, name) is NOT_GIVEN:
            setattr(ns, name, getattr(defaults, name))
    if ns.legacy_dry_run:
        # --dry-run must also beat ARCHIVIST_APPLY=true, as it did before --apply existed.
        ns.apply = False
    return Config(**{f.name: getattr(ns, f.name) for f in fields(Config)})


def legacy_notes(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> list[str]:
    """Warnings for options that used to change files by default and no longer do."""
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if environ is None else environ
    notes = []
    if "--dry-run" in argv:
        notes.append("--dry-run is no longer needed: a dry run is now the default. Use --apply to make changes.")
    if ENV_PREFIX + "DRY_RUN" in env:
        notes.append(
            f"{ENV_PREFIX}DRY_RUN is no longer used and was ignored: a dry run is now the default. "
            f"Set {ENV_PREFIX}APPLY=true or pass --apply to make changes."
        )
    return notes

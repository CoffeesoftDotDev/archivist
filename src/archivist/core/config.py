"""The Config model: each option is declared once, on its field, with option()."""
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import Field, dataclass, field, fields
from pathlib import Path
from typing import Any

APPLEDOUBLE_MAX_SIZE = 2048  # bytes (2 KB)
ENV_PREFIX = "ARCHIVIST_"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class Option:
    """How a Config field is set from outside: its flags (none = hand-written in the parser) and variable."""
    flags: tuple[str, ...]
    env: str  # without the ARCHIVIST_ prefix
    help: str
    parse: Callable[[str], Any] | None  # None: chosen from the field type


def option(default: Any, *flags: str, env: str, help: str = "", parse: Callable[[str], Any] | None = None) -> Any:
    """Declare a Config field together with its flags, its ARCHIVIST_* variable and its help text."""
    return field(default=default, metadata={Option: Option(flags, env, help, parse)})


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError("is not a boolean (use true/false)")


def _parse_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ValueError("is not a whole number") from None


def parse_log_file(raw: str) -> str | None:
    """
    The ARCHIVIST_LOG_FILE converter: false/no/off/0 -> None (no file),
    empty or true/yes/on/1 -> "" (<parent>/report.log), anything else -> that path.
    """
    value = raw.strip()
    if not value or value.lower() in _TRUE:
        return ""
    if value.lower() in _FALSE:
        return None
    return value


# Converters by field type, for options that don't bring their own
_PARSERS: dict[Any, Callable[[str], Any]] = {bool: _parse_bool, int: _parse_int, Path | None: Path}


@dataclass(frozen=True)
class Config:
    """
    Runtime options for the extractor/cleaner. Every bool defaults to False, like its flag.
    Fields are in --help order; see CONTRIBUTING.md, "Adding an option".
    """
    parent_folder: Path | None = option(
        None, "--parent-folder", env="PARENT_FOLDER",
        help="Parent folder to process. If omitted or empty, you will be prompted.",
    )
    leave_zip: bool = option(
        False, "--leave-zip", env="LEAVE_ZIP",
        help="Keep ZIP archives after extraction (default: they are deleted).",
    )
    leave_appledouble: bool = option(
        False, "--leave-appledouble", env="LEAVE_APPLEDOUBLE",
        help="Do not remove macOS AppleDouble metadata "
             "(small '._' files and '._' folders with no visible files).",
    )
    leave_eadir: bool = option(
        False, "--leave-eadir", env="LEAVE_EADIR",
        help="Do not remove Synology '@eaDir' folders.",
    )
    leave_ds_store: bool = option(
        False, "--leave-ds-store", env="LEAVE_DS_STORE",
        help="Do not remove macOS '.DS_Store' files.",
    )
    leave_thumbs_db: bool = option(
        False, "--leave-thumbs-db", env="LEAVE_THUMBS_DB",
        help="Do not remove Windows 'Thumbs.db' thumbnail caches.",
    )
    leave_desktop_ini: bool = option(
        False, "--leave-desktop-ini", env="LEAVE_DESKTOP_INI",
        help="Do not remove Windows 'desktop.ini' files (they hold custom folder icons and names).",
    )
    appledouble_max_size: int = option(
        APPLEDOUBLE_MAX_SIZE, "--max-size", env="MAX_SIZE",
        help="Max size in bytes for '._' files to be removed (default: %(default)s).",
    )
    force_readonly: bool = option(
        False, "--force-readonly-deletion", "--force", env="FORCE_READONLY_DELETION",
        help="Clear the read-only flag and delete read-only files/folders "
             "(default: read-only items are skipped).",
    )
    send_to_bin: bool = option(
        False, "--send-to-bin", env="SEND_TO_BIN",
        help="Send removed items to the Recycle Bin / Trash instead of deleting them permanently.",
    )
    # Hand-written flags (no flags here): --apply shares a group with the hidden --dry-run
    apply: bool = option(False, env="APPLY")
    # Three states, with a hand-written converter and flag pair (#3):
    # None = no file (--no-log-file), "" = <parent>/report.log (default, --log-file), otherwise a file or folder
    log_file: str | None = option("", env="LOG_FILE", parse=parse_log_file)

    @staticmethod
    def options() -> Iterator[tuple[Field, Option]]:
        """Every field with its Option, in declaration order."""
        for f in fields(Config):
            yield f, f.metadata[Option]

    def log_file_label(self) -> str:
        if self.log_file is None:
            return "disabled"
        return self.log_file or "<parent-folder>/report.log"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Config":
        """Built-in defaults overridden by ARCHIVIST_* variables (read from os.environ unless given)."""
        env = os.environ if environ is None else environ
        values = {}
        for f, opt in cls.options():
            raw = env.get(ENV_PREFIX + opt.env)
            if raw is None or raw.strip() == "":
                continue  # unset or empty keeps the default
            parse = opt.parse or _PARSERS[f.type]
            try:
                values[f.name] = parse(raw)
            except ValueError as ex:
                raise ValueError(f"{ENV_PREFIX}{opt.env}={raw!r} {ex}") from None
        return cls(**values)

    def summary(self) -> str:
        on_off = lambda v: "ENABLED" if v else "disabled"
        return "\n".join([
            f"Parent folder      : {self.parent_folder or '(prompt)'}",
            f"Delete ZIPs        : {on_off(not self.leave_zip)}",
            f"Read-only deletion : {on_off(self.force_readonly)}",
            f"Send to bin        : {on_off(self.send_to_bin)}",
            f"Mode               : {'APPLY (files will be changed)' if self.apply else 'dry run (nothing will be changed, use --apply to make the changes)'}",
            f"Remove AppleDouble : {on_off(not self.leave_appledouble)} (._ files <= {self.appledouble_max_size} bytes, empty ._ folders)",
            f"Remove .DS_Store   : {on_off(not self.leave_ds_store)}",
            f"Remove Thumbs.db   : {on_off(not self.leave_thumbs_db)}",
            f"Remove desktop.ini : {on_off(not self.leave_desktop_ini)}",
            f"Remove @eaDir      : {on_off(not self.leave_eadir)}",
            f"Log to file        : {self.log_file_label()}",
        ])

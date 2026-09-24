import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APPLEDOUBLE_MAX_SIZE = 2048  # bytes (2 KB)
ENV_PREFIX = "ARCHIVIST_"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(ENV_PREFIX + name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{ENV_PREFIX}{name}={raw!r} is not a boolean (use true/false)")


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(ENV_PREFIX + name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{ENV_PREFIX}{name}={raw!r} is not a whole number") from None


def _env_path(env: Mapping[str, str], name: str, default: Path | None) -> Path | None:
    raw = env.get(ENV_PREFIX + name)
    return default if raw is None or raw.strip() == "" else Path(raw)


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


def _env_log_file(env: Mapping[str, str], default: str | None) -> str | None:
    raw = env.get(ENV_PREFIX + "LOG_FILE")
    return default if raw is None or raw.strip() == "" else parse_log_file(raw)


@dataclass(frozen=True)
class Config:
    """Runtime options for the extractor/cleaner. Every bool defaults to False, like its flag."""
    force_readonly: bool = False
    leave_appledouble: bool = False
    leave_eadir: bool = False
    leave_ds_store: bool = False
    leave_thumbs_db: bool = False
    leave_desktop_ini: bool = False
    appledouble_max_size: int = APPLEDOUBLE_MAX_SIZE
    parent_folder: Path | None = None
    leave_zip: bool = False
    send_to_bin: bool = False
    apply: bool = False  # off: only show what would change (dry run)
    # Three states, kept as one field with a hand-written converter and CLI pair (issue #3):
    # None = no file (--no-log-file), "" = <parent>/report.log (default, --log-file), otherwise a file or folder
    log_file: str | None = ""

    def log_file_label(self) -> str:
        if self.log_file is None:
            return "disabled"
        return self.log_file or "<parent-folder>/report.log"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Config":
        """Built-in defaults overridden by ARCHIVIST_* variables (read from os.environ unless given)."""
        env = os.environ if environ is None else environ
        d = cls()
        return cls(
            force_readonly=_env_bool(env, "FORCE_READONLY_DELETION", d.force_readonly),
            leave_appledouble=_env_bool(env, "LEAVE_APPLEDOUBLE", d.leave_appledouble),
            leave_eadir=_env_bool(env, "LEAVE_EADIR", d.leave_eadir),
            leave_ds_store=_env_bool(env, "LEAVE_DS_STORE", d.leave_ds_store),
            leave_thumbs_db=_env_bool(env, "LEAVE_THUMBS_DB", d.leave_thumbs_db),
            leave_desktop_ini=_env_bool(env, "LEAVE_DESKTOP_INI", d.leave_desktop_ini),
            appledouble_max_size=_env_int(env, "MAX_SIZE", d.appledouble_max_size),
            parent_folder=_env_path(env, "PARENT_FOLDER", d.parent_folder),
            leave_zip=_env_bool(env, "LEAVE_ZIP", d.leave_zip),
            send_to_bin=_env_bool(env, "SEND_TO_BIN", d.send_to_bin),
            apply=_env_bool(env, "APPLY", d.apply),
            log_file=_env_log_file(env, d.log_file),
        )

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

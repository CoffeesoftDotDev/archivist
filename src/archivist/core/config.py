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


def _env_log_file(env: Mapping[str, str], default: str | None) -> str | None:
    """unset/false -> default (no file), true -> "" (<parent>/report.log), else a path."""
    raw = env.get(ENV_PREFIX + "LOG_FILE")
    if raw is None:
        return default
    value = raw.strip()
    if value.lower() in _FALSE:
        return None
    if value.lower() in _TRUE:
        return ""
    return value


@dataclass(frozen=True)
class Config:
    """Runtime options for the extractor/cleaner."""
    force_readonly: bool = False
    appledouble: bool = True
    eadir: bool = True
    ds_store: bool = True
    thumbs_db: bool = True
    desktop_ini: bool = True
    appledouble_max_size: int = APPLEDOUBLE_MAX_SIZE
    parent_folder: Path | None = None
    delete_zip: bool = True
    send_to_bin: bool = False
    dry_run: bool = False
    # None = no file logging, "" = default <parent>/report.log, otherwise a custom path
    log_file: str | None = None

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
            appledouble=not _env_bool(env, "LEAVE_APPLEDOUBLE", not d.appledouble),
            eadir=not _env_bool(env, "LEAVE_EADIR", not d.eadir),
            ds_store=not _env_bool(env, "LEAVE_DS_STORE", not d.ds_store),
            thumbs_db=not _env_bool(env, "LEAVE_THUMBS_DB", not d.thumbs_db),
            desktop_ini=not _env_bool(env, "LEAVE_DESKTOP_INI", not d.desktop_ini),
            appledouble_max_size=_env_int(env, "MAX_SIZE", d.appledouble_max_size),
            parent_folder=_env_path(env, "PARENT_FOLDER", d.parent_folder),
            delete_zip=not _env_bool(env, "LEAVE_ZIP", not d.delete_zip),
            send_to_bin=_env_bool(env, "SEND_TO_BIN", d.send_to_bin),
            dry_run=_env_bool(env, "DRY_RUN", d.dry_run),
            log_file=_env_log_file(env, d.log_file),
        )

    def summary(self) -> str:
        on_off = lambda v: "ENABLED" if v else "disabled"
        return "\n".join([
            f"Parent folder      : {self.parent_folder or '(prompt)'}",
            f"Delete ZIPs        : {on_off(self.delete_zip)}",
            f"Read-only deletion : {on_off(self.force_readonly)}",
            f"Send to bin        : {on_off(self.send_to_bin)}",
            f"Dry run            : {'ENABLED (nothing will be changed)' if self.dry_run else 'disabled'}",
            f"Remove AppleDouble : {on_off(self.appledouble)} (._ files <= {self.appledouble_max_size} bytes, empty ._ folders)",
            f"Remove .DS_Store   : {on_off(self.ds_store)}",
            f"Remove Thumbs.db   : {on_off(self.thumbs_db)}",
            f"Remove desktop.ini : {on_off(self.desktop_ini)}",
            f"Remove @eaDir      : {on_off(self.eadir)}",
            f"Log to file        : {self.log_file_label()}",
        ])

"""Compatibility-preserving settings precedence with sanitized parse errors."""
import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import UUID

from ..core.config import Config, boolean, integer
from ..core.models import ExportError

# Public keys, CLI flags and conversion live together.
OPTIONS = {
    "Destination": ("destination", "--destination", Path),
    "JournalId": ("journal_id", "--journal-id", UUID),
    "BrowserChannel": ("browser_channel", "--browser-channel", str),
    "ReuseSession": ("reuse_session", "--reuse-session", boolean),
    "ScreenshotRestricted": ("screenshot_restricted", "--screenshot-restricted", boolean),
    "NoLocal": ("no_local", "--no-local", boolean),
    "Resolution": ("resolution", "--res", str),
    "LoginTimeoutSeconds": ("login_timeout_seconds", "--login-timeout-seconds", integer),
    "RequestTimeoutSeconds": ("request_timeout_seconds", "--request-timeout-seconds", integer),
    "PageSize": ("page_size", "--page-size", integer),
    "LogPath": ("log_path", "--log-path", Path),
    "LogLevel": ("log_level", "--log-level", str),
    "Immich:Enabled": ("immich_enabled", "--immich", boolean),
    "Immich:Url": ("immich_url", "--immich-url", str),
    "Immich:ApiKey": ("immich_api_key", "--immich-api-key", str),
    "Immich:Album": ("immich_album", "--immich-album", str),
}


class Parser(argparse.ArgumentParser):
    """Do not echo unknown arguments, which may contain secrets."""

    def error(self, message: str) -> None:
        raise ExportError("Invalid command line. Run with --help for supported options and values.")


def _flatten(data: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in data.items():
        name = f"{prefix}{key}".lower()
        if isinstance(value, dict):
            result.update(_flatten(value, name + ":"))
        else:
            result[name] = value
    return result


def parse_config(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> Config:
    """Load defaults < JSON < TMA_ environment < command line."""
    parser = Parser(
        prog="tma", allow_abbrev=False,
        description="TouteMonAnnee photo exporter (Python/uv). Open the journal in the dedicated browser.",
        epilog="Precedence: defaults < JSON < TMA_ environment < CLI. Exit: 0 complete, 1 incomplete/error, 2 config, 130 cancelled.",
        argument_default=argparse.SUPPRESS,
    )
    parser.add_argument("--config", help="JSON settings (default: optional ./appsettings.json)")
    for key, (attribute, flag, convert) in OPTIONS.items():
        kwargs: dict[str, object] = {"dest": attribute, "help": key}
        if flag in {"--immich", "--no-local", "--screenshot-restricted"}:
            kwargs.update(nargs="?", const="true")
        parser.add_argument(flag, **kwargs)
    args = vars(parser.parse_args(argv))
    explicit = args.pop("config", None)
    config_path = Path(explicit) if explicit is not None else Path("appsettings.json")
    settings: dict[str, object] = {}
    if explicit is not None or config_path.exists():
        try:
            with config_path.open(encoding="utf-8-sig") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ExportError("Configuration JSON must be an object.")
            settings = _flatten(data)
        except (OSError, ValueError):
            raise ExportError("Cannot read configuration JSON; check the file and JSON syntax.") from None
    for key, value in (os.environ if environ is None else environ).items():
        if key.upper().startswith("TMA_"):
            settings[key[4:].replace("__", ":").lower()] = value
    if "localonly" in settings:
        raise ExportError("LocalOnly is no longer supported. Local is default; explicitly enable or disable Immich.")
    converted: dict[str, object] = {}
    for key, (attribute, flag, convert) in OPTIONS.items():
        value = args.get(attribute, settings.get(key.lower()))
        if value is None:
            continue
        if value == "" and key in {"Immich:Url", "Immich:ApiKey", "Immich:Album"} and attribute not in args:
            continue
        if not isinstance(value, (str, bool, int)) or (isinstance(value, str) and not value.strip()):
            raise ExportError(f"Setting {key} has an invalid or empty value.")
        if convert in (str, Path, UUID) and not isinstance(value, str):
            raise ExportError(f"Setting {key} must be a string.")
        try:
            converted[attribute] = convert(value)
        except (ValueError, TypeError, AttributeError):
            raise ExportError(f"Setting {key} has an invalid value.") from None
    config = Config(**converted)
    config.validate()
    return config

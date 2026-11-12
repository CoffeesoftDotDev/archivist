"""Optional read-only MCP adapter; importing Archivist never imports the SDK."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import fields
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .. import __version__
from ..services.image_access import AccessPolicy, BoundedImageService, ReadLimits
from ..services.image_api import ImageApiError


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as ex:
        raise argparse.ArgumentTypeError("must be a positive integer") from ex
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def _configured_root(value: str) -> Path:
    if not value.strip():
        raise argparse.ArgumentTypeError("must be an explicit nonempty directory path")
    return Path(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Archivist MCP server (stdio only).")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (the default).")
    parser.add_argument("--version", action="store_true", help="Print runtime versions to stderr and exit.")
    parser.add_argument("--source-root", action="append", type=_configured_root, default=[], help="Trusted source directory (repeatable).")
    parser.add_argument("--destination-root", action="append", type=_configured_root, default=[], help="Trusted preview destination directory (repeatable).")
    defaults = ReadLimits()
    for field in fields(ReadLimits):
        parser.add_argument(
            "--" + field.name.replace("_", "-"), type=_positive_integer,
            default=getattr(defaults, field.name), help=f"Positive {field.name} limit (default: %(default)s).",
        )
    return parser


def _runtime_information() -> str:
    from mcp.types import LATEST_PROTOCOL_VERSION

    try:
        sdk_version = version("mcp")
    except PackageNotFoundError:
        sdk_version = "unknown"
    return (
        f"Archivist {__version__}; MCP SDK {sdk_version}; protocol {LATEST_PROTOCOL_VERSION}; "
        f"Python {sys.version.split()[0]}; supported Python >=3.10; SDK >=1.28,<2\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Start the optional stdio adapter with immutable trusted-operator policy."""
    parser = _parser()
    # argparse help normally uses stdout; keep every nonprotocol message on stderr.
    try:
        if argv is None:
            argv = sys.argv[1:]
        if "-h" in argv or "--help" in argv:
            parser.print_help(file=sys.stderr)
            return 0
        args = parser.parse_args(argv)
        try:
            runtime_information = _runtime_information()
            from .server import run
        except ModuleNotFoundError as ex:
            if ex.name is not None and (ex.name == "mcp" or ex.name.startswith("mcp.")):
                sys.stderr.write("Archivist MCP requires the optional extra; install this source with [mcp].\n")
                return 2
            raise
        if args.version:
            sys.stderr.write(runtime_information)
            return 0
        if not args.source_root:
            parser.error("at least one --source-root is required (empty access policy denies all reads)")
        limits = ReadLimits(**{field.name: getattr(args, field.name) for field in fields(ReadLimits)})
        policy = AccessPolicy(tuple(args.source_root), tuple(args.destination_root), limits)
        service = BoundedImageService(policy)
        sys.stderr.write(runtime_information)
        import anyio
        anyio.run(run, service)
        return 0
    except ImageApiError as ex:
        sys.stderr.write(f"Archivist MCP startup failed [{ex.code}]: {ex}\n")
        return 2
    except (OSError, ValueError) as ex:
        sys.stderr.write(f"Archivist MCP startup failed: {ex}\n")
        return 2
    except KeyboardInterrupt:
        return 130

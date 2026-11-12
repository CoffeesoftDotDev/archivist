"""Opt-in clean uvx smoke; never installed or invoked by ordinary pytest.

Run ``python scripts/mcp_smoke.py --commit <reviewed 40-character GitHub SHA>``.
For an already committed local checkout, add ``--git-url <absolute repo path>``.
Both references are immutable; the default is the project's owned GitHub source.
Fixture creation is confined to a temporary child of the current directory.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

OWNED_GIT_URL = "https://github.com/CoffeesoftDotDev/archivist.git"


def _snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_ino, info.st_dev, path.read_bytes() if path.is_file() else None,
        )
    return result


def _entry_point(name: str) -> str:
    executable = Path(sys.executable).parent / (name + (".exe" if os.name == "nt" else ""))
    if not executable.is_file():
        raise RuntimeError(f"Installed console entry point is missing: {executable}")
    return str(executable)


def _environment(root: Path) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("ARCHIVIST_")
    }
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(root / "scratch"), TMP=str(root / "scratch"), TMPDIR=str(root / "scratch"),
    )
    return environment


def _fixture(root: Path) -> None:
    for name in ("source", "destination", "scratch", "work"):
        (root / name).mkdir()
    (root / "source" / "photo.jpg").write_bytes(b"fixture image")
    with zipfile.ZipFile(root / "source" / "album.zip", "w") as archive:
        archive.writestr("photo.jpg", b"archive image")
        archive.writestr("notes.txt", b"nonimage retained by move")


def _cli_probe(root: Path) -> None:
    if importlib.util.find_spec("mcp") is not None:
        raise AssertionError("The no-extra installation unexpectedly contains the MCP SDK")
    before = _snapshot(root)
    completed = subprocess.run(
        [
            _entry_point("archivist"), "--parent-folder", str(root / "source"),
            "--no-log-file", "--list-images",
        ],
        cwd=root / "work", env=_environment(root),
        capture_output=True, text=True, timeout=30, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Ordinary CLI failed without MCP SDK: {completed.stderr}")
    assert completed.stdout, "CLI produced no inventory"
    assert _snapshot(root) == before, "CLI preview wrote to the fixture"


async def _mcp_probe(root: Path) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    before = _snapshot(root)
    parameters = StdioServerParameters(
        command=_entry_point("archivist-mcp"),
        args=[
            "--source-root", str(root / "source"),
            "--destination-root", str(root / "destination"),
            "--page-records", "1", "--page-bytes", "4096",
        ],
        cwd=str(root / "work"), env=_environment(root),
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(
            reader, writer, read_timeout_seconds=timedelta(seconds=30),
        ) as session:
            await session.initialize()
            catalog = await session.list_tools()
            assert {tool.name for tool in catalog.tools} == {"inventory", "prepare_transfer"}
            for name in ("inventory", "prepare_transfer"):
                arguments = {"root": str(root / "source")}
                if name == "prepare_transfer":
                    arguments.update(destination=str(root / "destination" / "not-created"), mode="copy")
                records = []
                snapshot_id = None
                cursors = set()
                while True:
                    response = await session.call_tool(name, arguments)
                    assert not response.isError, response
                    assert response.content == [], "Bounded pages must not be duplicated into text content"
                    page = response.structuredContent
                    assert page is not None and page["schema_version"] == 1
                    assert set(page) == {
                        "schema_version", "snapshot_id", "operation",
                        "inventory_complete", "records", "next_cursor",
                    }
                    assert page["inventory_complete"] is True
                    assert page["operation"] == ("inventory" if name == "inventory" else "transfer")
                    assert len(page["records"]) <= 1
                    if snapshot_id is None:
                        snapshot_id = page["snapshot_id"]
                    assert page["snapshot_id"] == snapshot_id
                    records.extend(page["records"])
                    cursor = page["next_cursor"]
                    if cursor is None:
                        break
                    assert cursor not in cursors
                    cursors.add(cursor)
                    arguments = {"cursor": cursor}
                assert sum(record["kind"] == "image" for record in records) == 2
                if name == "prepare_transfer":
                    assert sum(record["kind"] == "transfer" for record in records) == 2
            denied = await session.call_tool("inventory", {
                "root": str(root / "source"), "apply": True,
            })
            assert denied.isError and denied.structuredContent is not None
            assert denied.structuredContent["schema_version"] == 1
            assert set(denied.structuredContent["error"]) == {"code", "message"}
    assert _snapshot(root) == before, "MCP startup, calls or shutdown wrote to the fixture"


def _reference(git_url: str, commit: str, *, extra: bool) -> str:
    path = Path(git_url)
    if path.is_dir():
        source = path.resolve().as_uri()
    elif git_url.rstrip("/") == OWNED_GIT_URL:
        source = OWNED_GIT_URL
    else:
        raise ValueError(f"Use the owned repository {OWNED_GIT_URL} or an existing local Git checkout")
    return f"archivist{'[mcp]' if extra else ''} @ git+{source}@{commit}"


def main() -> int:
    """Run explicit network-enabled isolated installs, or the internal installed probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="Reviewed immutable 40-character Git commit SHA")
    parser.add_argument("--git-url", default=OWNED_GIT_URL, help="Owned GitHub URL or absolute local checkout")
    parser.add_argument("--python", default=f"{sys.version_info.major}.{sys.version_info.minor}")
    parser.add_argument("--lane", choices=("all", "cli", "mcp"), default="all")
    parser.add_argument("--probe", choices=("cli", "mcp"), help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.probe:
        with tempfile.TemporaryDirectory(prefix="archivist-smoke-", dir=Path.cwd()) as directory:
            root = Path(directory)
            _fixture(root)
            if arguments.probe == "cli":
                _cli_probe(root)
            else:
                asyncio.run(_mcp_probe(root))
        print(json.dumps({
            "lane": arguments.probe, "python": sys.version.split()[0],
            "platform": sys.platform, "archivist": importlib.metadata.version("archivist"),
            "sdk": importlib.metadata.version("mcp") if arguments.probe == "mcp" else None,
            "result": "passed",
        }))
        return 0
    if not arguments.commit or not re.fullmatch(r"[0-9a-fA-F]{40}", arguments.commit):
        parser.error("--commit must be a reviewed immutable 40-character Git commit SHA")
    uvx = shutil.which("uvx")
    if uvx is None:
        parser.error("uvx is required; install uv separately before running this opt-in smoke")
    lanes = ("cli", "mcp") if arguments.lane == "all" else (arguments.lane,)
    for lane in lanes:
        try:
            reference = _reference(arguments.git_url, arguments.commit, extra=lane == "mcp")
        except ValueError as error:
            parser.error(str(error))
        command = [
            uvx, "--isolated", "--python", arguments.python, "--from", reference,
            "python", str(Path(__file__).resolve()), "--probe", lane,
        ]
        print(json.dumps({"lane": lane, "source": reference, "python": arguments.python}), flush=True)
        subprocess.run(command, check=True, timeout=300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

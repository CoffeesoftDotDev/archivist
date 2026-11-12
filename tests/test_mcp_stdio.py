"""Wire-level coverage of the optional, read-only MCP adapter."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="Install archivist[mcp] to run SDK integration tests")

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import JSONRPCMessage

from archivist.services.image_access import AccessPolicy, BoundedImageService, ReadLimits
from archivist.services.image_api import InventoryRequest, TransferRequest


def snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    """Include bytes and mutation metadata, but not OS read-access bookkeeping."""
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_ino, info.st_dev, path.read_bytes() if path.is_file() else None,
        )
    return result


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "observed"
    for name in ("source", "destination", "scratch", "work"):
        (root / name).mkdir(parents=True)
    return root


def server_arguments(workspace: Path, *limits: str) -> list[str]:
    return [
        "-m", "archivist.mcp", "--stdio",
        "--source-root", str(workspace / "source"),
        "--destination-root", str(workspace / "destination"),
        "--page-records", "1", "--page-bytes", "4096", *limits,
    ]


def server_environment(workspace: Path) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("ARCHIVIST_")
    }
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        TMP=str(workspace / "scratch"),
        TEMP=str(workspace / "scratch"),
        TMPDIR=str(workspace / "scratch"),
    )
    return environment


@asynccontextmanager
async def session_for(workspace: Path, *limits: str):
    parameters = StdioServerParameters(
        command=sys.executable, args=server_arguments(workspace, *limits),
        cwd=str(workspace / "work"), env=server_environment(workspace),
    )
    with (workspace.parent / "server.stderr").open("w", encoding="utf-8") as stderr:
        async with stdio_client(parameters, errlog=stderr) as (reader, writer):
            async with ClientSession(
                reader, writer, read_timeout_seconds=timedelta(seconds=20),
            ) as session:
                initialized = await session.initialize()
                assert initialized.protocolVersion
                assert initialized.capabilities.tools is not None
                yield session


async def collect(session: ClientSession, tool: str, arguments: dict) -> list[dict]:
    records = []
    snapshot_id = None
    seen = set()
    while True:
        response = await session.call_tool(tool, arguments)
        assert not response.isError, response
        assert response.content == [], "Do not duplicate the bounded page into text content"
        page = response.structuredContent
        assert page is not None
        assert set(page) == {
            "schema_version", "snapshot_id", "operation", "inventory_complete",
            "records", "next_cursor",
        }
        assert page["schema_version"] == 1
        assert page["operation"] == ("inventory" if tool == "inventory" else "transfer")
        assert type(page["inventory_complete"]) is bool
        assert len(page["records"]) <= 1
        encoded = json.dumps(page, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        assert len(encoded.encode("utf-8")) <= 4096
        if snapshot_id is None:
            snapshot_id = page["snapshot_id"]
        assert page["snapshot_id"] == snapshot_id
        records.extend(page["records"])
        cursor = page["next_cursor"]
        if cursor is None:
            return records
        assert cursor not in seen
        seen.add(cursor)
        arguments = {"cursor": cursor}


def expected_records(workspace: Path, tool: str, arguments: dict) -> list[dict]:
    service = BoundedImageService(AccessPolicy(
        (workspace / "source",), (workspace / "destination",),
        ReadLimits(page_records=1, page_bytes=4096),
    ))
    values = dict(arguments)
    values["root"] = Path(values["root"])
    if "extensions" in values:
        values["extensions"] = tuple(values["extensions"])
    if tool == "inventory":
        page = service.inventory(InventoryRequest(**values))
    else:
        values["destination"] = Path(values["destination"])
        page = service.prepare_transfer(TransferRequest(**values))
    records = []
    while True:
        records.extend(json.loads(page.to_json())["records"])
        if page.next_cursor is None:
            return records
        page = service.page(page.next_cursor)


def without_plan_ids(records: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in record.items() if key != "plan_id"}
        for record in records
    ]


def test_sdk_initialize_and_exact_read_only_tool_catalog(workspace):
    async def exercise():
        async with session_for(workspace) as session:
            catalog = await session.list_tools()
            assert {tool.name for tool in catalog.tools} == {"inventory", "prepare_transfer"}
            assert catalog.nextCursor is None
            for tool in catalog.tools:
                assert tool.annotations is not None
                assert tool.annotations.readOnlyHint is True
                assert tool.annotations.destructiveHint is False
                encoded = json.dumps(tool.inputSchema)
                assert "cursor" in encoded and "schema_version" in encoded
                assert "source_roots" not in encoded and "page_records" not in encoded
            records = await collect(session, "inventory", {"root": str(workspace / "source")})
            assert records[0]["counts"]["selected_images"] == 0
            assert_error(await session.call_tool("inventory", {}), "invalid_request")
            assert_error(await session.call_tool("prepare_transfer", {}), "invalid_request")

    before = snapshot(workspace)
    asyncio.run(exercise())
    assert snapshot(workspace) == before


@pytest.mark.parametrize("tool,mode,leave_zip", [
    ("inventory", None, False),
    ("prepare_transfer", "move", False),
    ("prepare_transfer", "move", True),
    ("prepare_transfer", "copy", False),
    ("prepare_transfer", "copy", True),
])
def test_mixed_nested_archive_collision_preview_parity_and_no_writes(
    workspace, make_zip, write_file, tool, mode, leave_zip,
):
    source, destination = workspace / "source", workspace / "destination"
    write_file(source / "one" / "same.jpg", b"first")
    write_file(source / "two" / "same.jpg", b"second")
    write_file(destination / "same.jpg", b"occupied")
    write_file(destination / "same (001).jpg", b"also occupied")
    make_zip(source / "mixed.zip", {
        "same.jpg": "image", "movie.mp4": "nonimage",
        "nested.zip": {"deep.jpg": "nested image", "notes.txt": "retained"},
    })
    make_zip(source / "model.3mf", {"not-an-image.jpg": "opaque model"})
    arguments = {"root": str(source), "extensions": ["jpg"], "schema_version": 1}
    if mode:
        arguments.update(destination=str(destination), mode=mode, leave_zip=leave_zip)
    before = snapshot(workspace)
    expected = expected_records(workspace, tool, arguments)

    async def exercise():
        async with session_for(workspace) as session:
            return await collect(session, tool, arguments)

    records = asyncio.run(exercise())
    assert without_plan_ids(records) == without_plan_ids(expected)
    assert sum(record["kind"] == "image" for record in records) == 4
    assert not any("not-an-image.jpg" in json.dumps(record) for record in records)
    if mode:
        members = [record["value"] for record in records if record["kind"] == "extraction_member"]
        movie = next(member for member in members if member["relative_path"] == "movie.mp4")
        assert movie["disposition"] == ("temporary" if mode == "copy" else "retained")
        targets = [record["value"]["destination"] for record in records if record["kind"] == "transfer"]
        assert len(targets) == len(set(targets)) == 4
        assert str(destination / "same.jpg") not in targets
    assert snapshot(workspace) == before


@pytest.mark.parametrize("tool", ["inventory", "prepare_transfer"])
def test_no_matching_images_is_success_without_destination_creation(workspace, make_zip, tool):
    make_zip(workspace / "source" / "none.zip", {"notes.txt": "not an image"})
    arguments = {"root": str(workspace / "source"), "extensions": ["png"]}
    if tool == "prepare_transfer":
        arguments.update(destination=str(workspace / "destination" / "missing"), mode="copy")

    async def exercise():
        async with session_for(workspace) as session:
            records = await collect(session, tool, arguments)
            assert records[0]["counts"]["selected_images"] == 0
            assert not any(record["kind"] in {"transfer", "extraction"} for record in records)

    before = snapshot(workspace)
    asyncio.run(exercise())
    assert snapshot(workspace) == before


def assert_error(response, code: str | None = None) -> None:
    assert response.isError is True
    payload = response.structuredContent
    assert payload is not None and set(payload) == {"schema_version", "error"}
    assert payload["schema_version"] == 1
    assert set(payload["error"]) == {"code", "message"}
    assert isinstance(payload["error"]["message"], str) and payload["error"]["message"]
    assert isinstance(payload["error"]["code"], str) and payload["error"]["code"]
    if code:
        assert payload["error"]["code"] == code


@pytest.mark.parametrize("tool,arguments,code", [
    ("execute", {}, None),
    ("inventory", {"apply": True}, None),
    ("inventory", {"source_roots": []}, None),
    ("inventory", {"page_records": 1000}, None),
    ("inventory", {"extensions": "jpg"}, None),
    ("inventory", {"extensions": []}, "invalid_request"),
    ("inventory", {"extensions": ["jpg,png"]}, "invalid_filter"),
    ("inventory", {"extensions": ["exe"]}, "invalid_filter"),
    ("inventory", {"extensions": [1]}, None),
    ("inventory", {"schema_version": 2}, "invalid_request"),
    ("inventory", {"schema_version": True}, None),
    ("inventory", {"cursor": "forged"}, None),
    ("prepare_transfer", {"action": "execute"}, None),
    ("prepare_transfer", {"mode": "delete"}, None),
    ("prepare_transfer", {"leave_zip": "yes"}, None),
])
def test_strict_requests_have_structured_errors_and_leave_session_usable(
    workspace, tool, arguments, code,
):
    values = {"root": str(workspace / "source"), **arguments}
    if tool == "prepare_transfer":
        values["destination"] = str(workspace / "destination")

    async def exercise():
        async with session_for(workspace) as session:
            assert_error(await session.call_tool(tool, values), code)
            assert len((await session.list_tools()).tools) == 2

    before = snapshot(workspace)
    asyncio.run(exercise())
    assert snapshot(workspace) == before


def test_outside_roots_cursor_tampering_and_source_mutation(workspace, write_file):
    photo = write_file(workspace / "source" / "photo.jpg", b"initial")

    async def exercise():
        async with session_for(workspace) as session:
            assert_error(await session.call_tool("inventory", {"root": str(workspace)}), "access_denied")
            page = await session.call_tool("inventory", {"root": str(workspace / "source")})
            cursor = page.structuredContent["next_cursor"]
            assert cursor
            assert_error(await session.call_tool("inventory", {"cursor": cursor + "x"}), "invalid_cursor")
            assert_error(await session.call_tool("inventory", {"cursor": cursor, "root": str(workspace / "source")}))
            assert_error(await session.call_tool("inventory", {"cursor": cursor, "schema_version": 1}), "invalid_request")
            assert_error(await session.call_tool("prepare_transfer", {"cursor": cursor}))
            transfer = await session.call_tool("prepare_transfer", {
                "root": str(workspace / "source"),
                "destination": str(workspace / "destination"), "mode": "copy",
            })
            assert not transfer.isError
            assert_error(await session.call_tool("prepare_transfer", {
                "cursor": transfer.structuredContent["next_cursor"], "schema_version": 1,
            }), "invalid_request")
            photo.write_bytes(b"deliberate test mutation")
            assert_error(await session.call_tool("inventory", {"cursor": cursor}), "stale_snapshot")

    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["unsafe", "unsafe_backslash", "unsafe_absolute", "corrupt", "nested_budget"])
def test_partial_archives_never_become_executable_previews(workspace, make_zip, write_file, fault):
    source = workspace / "source"
    limits = ()
    if fault.startswith("unsafe"):
        member = {
            "unsafe": "../escape.jpg",
            "unsafe_backslash": "..\\escape.jpg",
            "unsafe_absolute": "/escape.jpg",
        }[fault]
        make_zip(source / "bad.zip", {member: "escape", "ok.jpg": "photo"})
    elif fault == "corrupt":
        write_file(source / "bad.zip", b"not a zip file")
    else:
        make_zip(source / "nested.zip", {"inner.zip": {"photo.jpg": "photo"}})
        limits = ("--max-archive-entries", "1")

    async def exercise():
        async with session_for(workspace, *limits) as session:
            page = await session.call_tool("inventory", {"root": str(source)})
            assert not page.isError
            assert page.structuredContent["inventory_complete"] is False
            records = await collect(session, "inventory", {"root": str(source)})
            assert any(record["kind"] == "problem" for record in records)
            assert_error(await session.call_tool("prepare_transfer", {
                "root": str(source), "destination": str(workspace / "destination"), "mode": "copy",
            }), "incomplete_inventory")

    before = snapshot(workspace)
    asyncio.run(exercise())
    assert snapshot(workspace) == before


def test_sdk_cancellation_and_disconnect_do_not_write(workspace, write_file):
    for index in range(100):
        write_file(workspace / "source" / f"{index}.jpg", b"photo")

    async def exercise():
        async with session_for(workspace) as session:
            request = asyncio.create_task(session.call_tool(
                "inventory", {"root": str(workspace / "source")},
            ))
            await asyncio.sleep(0)
            request.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await request
            assert len((await session.list_tools()).tools) == 2
        # A fresh process works after the cancelled client's transport disconnects.
        async with session_for(workspace) as session:
            assert len((await session.list_tools()).tools) == 2

    before = snapshot(workspace)
    asyncio.run(exercise())
    assert snapshot(workspace) == before


@pytest.mark.parametrize("initialized", [False, True])
def test_eof_shutdown_is_clean_and_stdout_contains_only_protocol(workspace, initialized):
    messages = []
    if initialized:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "archivist-wire-test", "version": "1"},
            }},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
    before = snapshot(workspace)
    completed = subprocess.run(
        [sys.executable, *server_arguments(workspace)], cwd=workspace / "work",
        env=server_environment(workspace), input="".join(json.dumps(value) + "\n" for value in messages),
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    for reply in replies:
        JSONRPCMessage.model_validate(reply)
    if initialized:
        assert any(reply.get("id") == 1 and "result" in reply for reply in replies)
    else:
        assert replies == []
    assert snapshot(workspace) == before

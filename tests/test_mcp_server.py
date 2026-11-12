"""Direct contract and policy tests for the optional read-only MCP adapter."""
import builtins
import json
import threading

import pytest

pytest.importorskip("mcp")
import anyio
from jsonschema import Draft202012Validator
from mcp.types import CallToolRequest, ListToolsRequest

from archivist.mcp import main
from archivist.mcp.schemas import ERROR_SCHEMA, input_schema, output_schema
from archivist.mcp.server import ReadOnlyTools, create_server
from archivist.services.image_access import AccessPolicy, BoundedImageService, ReadLimits


def _tools(source, destination=None, **limits):
    return ReadOnlyTools(BoundedImageService(AccessPolicy(
        (source,), (destination,) if destination else (), ReadLimits(**limits),
    )))


def _call(tools, name, arguments):
    return anyio.run(tools.call_tool, name, arguments)


def _assert_error(result, code):
    assert result.isError is True
    assert result.content == []
    Draft202012Validator(ERROR_SCHEMA).validate(result.structuredContent)
    assert result.structuredContent["error"]["code"] == code


def test_exact_discovery_annotations_and_explicit_schemas(tmp_path):
    tools = _tools(tmp_path)
    discovered = anyio.run(tools.list_tools)
    assert [tool.name for tool in discovered] == ["inventory", "prepare_transfer"]
    for tool in discovered:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
        assert tool.inputSchema["additionalProperties"] is False
        for variant in tool.inputSchema["oneOf"]:
            assert variant["additionalProperties"] is False
        Draft202012Validator.check_schema(tool.inputSchema)
        Draft202012Validator.check_schema(tool.outputSchema)
    server = create_server(BoundedImageService(AccessPolicy((tmp_path,))))
    assert CallToolRequest in server.request_handlers
    assert ListToolsRequest in server.request_handlers


@pytest.mark.parametrize("transfer", [False, True])
def test_input_schema_valid_initial_and_continuation(transfer):
    schema = Draft202012Validator(input_schema(transfer=transfer))
    initial = {"root": "source"}
    if transfer:
        initial.update(destination="destination", mode="copy")
    for arguments in (
        initial, {**initial, "schema_version": 1, "extensions": ["jpg", ".png"]},
        {"cursor": "opaque"},
    ):
        schema.validate(arguments)


@pytest.mark.parametrize("arguments", [
    None, [], {}, {"root": ""}, {"root": 5}, {"root": "x", "schema_version": True},
    {"root": "x", "schema_version": 2}, {"root": "x", "extensions": []},
    {"root": "x", "extensions": "jpg"}, {"root": "x", "extensions": [2]},
    {"root": "x", "apply": True}, {"root": "x", "source_roots": ["x"]},
    {"root": "x", "cursor": "opaque"}, {"cursor": ""}, {"cursor": "a" * 129},
    {"cursor": "x", "extensions": ["jpg"]}, {"root": "x", "leave_zip": True},
    {"cursor": "opaque", "schema_version": 1},
])
def test_inventory_strict_invalid_requests(tmp_path, arguments):
    _assert_error(_call(_tools(tmp_path), "inventory", arguments), "invalid_request")


@pytest.mark.parametrize("changes", [
    {"mode": "execute"}, {"mode": None}, {"leave_zip": 1}, {"cleanup": True},
    {"destination": ""}, {"cursor": "opaque"}, {"schema_version": 0},
])
def test_transfer_strict_invalid_requests(tmp_path, changes):
    args = {"root": str(tmp_path), "destination": str(tmp_path / "out"), "mode": "move"}
    _assert_error(_call(_tools(tmp_path), "prepare_transfer", {**args, **changes}), "invalid_request")


@pytest.mark.parametrize("name", ["execute", "apply", "cleanup", "shell", "INVENTORY", ""])
def test_unknown_tools_rejected(tmp_path, name):
    _assert_error(_call(_tools(tmp_path), name, {}), "invalid_request")


def test_transfer_requires_destination_and_mode(tmp_path):
    tools = _tools(tmp_path)
    for args in ({"root": str(tmp_path)}, {"root": str(tmp_path), "destination": "x"}):
        _assert_error(_call(tools, "prepare_transfer", args), "invalid_request")


def test_errors_preserve_service_codes_and_no_success_fallback(tmp_path):
    tools = _tools(tmp_path)
    for args, code in [
        ({"root": str(tmp_path.parent)}, "access_denied"),
        ({"root": str(tmp_path), "extensions": ["exe"]}, "invalid_filter"),
        ({"cursor": "malformed"}, "invalid_cursor"),
    ]:
        _assert_error(_call(tools, "inventory", args), code)
    _assert_error(_call(tools, "prepare_transfer", {
        "root": str(tmp_path), "destination": str(tmp_path.parent / "out"), "mode": "move",
    }), "access_denied")


@pytest.mark.parametrize("transfer", [False, True])
def test_paginated_full_schemas_bounded_structured_only_and_no_writes(
    tmp_path, make_zip, write_file, transfer,
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    write_file(source / "one.jpg", b"one")
    write_file(destination / "one.jpg", b"existing")
    make_zip(source / "mixed.zip", {
        "picture.png": b"picture", "other.txt": b"other",
        "inner.zip": {"nested.jpg": b"nested"},
    })
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    tree = sorted(str(path) for path in tmp_path.rglob("*"))
    tools = _tools(source, destination, page_records=1, page_bytes=2048)
    name = "prepare_transfer" if transfer else "inventory"
    arguments = {"root": str(source), "schema_version": 1}
    if transfer:
        arguments.update(destination=str(destination), mode="copy", leave_zip=True)
    records = []
    count = 0
    while True:
        result = _call(tools, name, arguments)
        assert result.isError is False
        assert result.content == []
        payload = result.structuredContent
        Draft202012Validator(output_schema(transfer=transfer)).validate(payload)
        assert len(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()) <= 2048
        records.extend(payload["records"])
        count += 1
        if payload["next_cursor"] is None:
            break
        arguments = {"cursor": payload["next_cursor"]}
        assert count < 100
    assert count > 1
    assert len([record for record in records if record["kind"] == "image"]) == 3
    if transfer:
        assert {"extraction", "extraction_member", "transfer", "transfer_summary"} <= {
            record["kind"] for record in records
        }
    assert sorted(str(path) for path in tmp_path.rglob("*")) == tree
    assert {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_cursor_operation_scope_in_both_directions(tmp_path, write_file):
    source, destination = tmp_path / "source", tmp_path / "destination"
    write_file(source / "one.jpg")
    destination.mkdir()
    tools = _tools(source, destination, page_records=1)
    inventory = _call(tools, "inventory", {"root": str(source)})
    transfer = _call(tools, "prepare_transfer", {
        "root": str(source), "destination": str(destination), "mode": "move",
    })
    for name, result in [("inventory", transfer), ("prepare_transfer", inventory)]:
        _assert_error(_call(tools, name, {"cursor": result.structuredContent["next_cursor"]}), "invalid_cursor")


def test_no_matches_is_explicit_summary(tmp_path):
    result = _call(_tools(tmp_path), "inventory", {"root": str(tmp_path)})
    assert result.isError is False
    assert result.structuredContent["records"][0]["counts"]["selected_images"] == 0


def test_unexpected_error_is_structured(tmp_path, monkeypatch):
    service = BoundedImageService(AccessPolicy((tmp_path,)))
    def fail(request):
        raise RuntimeError("private details")
    monkeypatch.setattr(service, "inventory", fail)
    result = _call(ReadOnlyTools(service), "inventory", {"root": str(tmp_path)})
    _assert_error(result, "internal_error")
    assert "private details" not in json.dumps(result.structuredContent)


def test_cancellation_responsive_and_no_parallel_background_scans(tmp_path, monkeypatch):
    service = BoundedImageService(AccessPolicy((tmp_path,)))
    entered, finish, exited = threading.Event(), threading.Event(), threading.Event()
    original = service.inventory

    def blocked(request):
        entered.set()
        try:
            assert finish.wait(5)
            return original(request)
        finally:
            exited.set()

    monkeypatch.setattr(service, "inventory", blocked)
    tools = ReadOnlyTools(service)

    async def exercise():
        with anyio.move_on_after(0.1) as scope:
            await tools.call_tool("inventory", {"root": str(tmp_path)})
        assert scope.cancel_called
        assert entered.is_set()
        _assert_error(await tools.call_tool("inventory", {"root": str(tmp_path)}), "capacity_exceeded")
        finish.set()
        with anyio.fail_after(5):
            while not exited.is_set() or tools._busy.locked():
                await anyio.sleep(0.01)
        result = await tools.call_tool("inventory", {"root": str(tmp_path)})
        assert result.isError is False

    try:
        anyio.run(exercise)
    finally:
        finish.set()


def test_startup_version_help_and_fail_closed(tmp_path, capsys):
    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    for label in ("Archivist", "MCP SDK", "protocol", "supported Python >=3.10"):
        assert label in captured.err
    assert main(["--help"]) == 0
    assert capsys.readouterr().out == ""
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code != 0
    assert capsys.readouterr().out == ""
    assert main(["--source-root", str(tmp_path / "missing")]) != 0
    assert "startup failed" in capsys.readouterr().err


@pytest.mark.parametrize("flag", [
    "--max-entries", "--max-archive-entries", "--page-records", "--page-bytes",
    "--snapshot-bytes", "--total-bytes", "--snapshots", "--ttl-seconds",
])
def test_startup_limit_flags_are_positive(tmp_path, capsys, flag):
    with pytest.raises(SystemExit) as error:
        main(["--source-root", str(tmp_path), flag, "0"])
    assert error.value.code != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "positive integer" in captured.err


def test_missing_sdk_install_hint_stderr_only(monkeypatch, capsys):
    original = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == "server":
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    assert main([]) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[mcp]" in captured.err


def test_oversized_response_preserves_explicit_error(tmp_path, write_file):
    write_file(tmp_path / "image.jpg")
    result = _call(_tools(tmp_path, page_bytes=1), "inventory", {"root": str(tmp_path)})
    _assert_error(result, "response_too_large")


def test_startup_policy_limit_ceiling_fails_closed(tmp_path, capsys):
    assert main([
        "--source-root", str(tmp_path), "--max-archive-entries", "999999999",
    ]) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid_policy" in captured.err


@pytest.mark.parametrize("flag", ["--source-root", "--destination-root"])
@pytest.mark.parametrize("value", ["", " ", "\t\r\n"])
def test_empty_startup_roots_never_become_working_directory(tmp_path, capsys, flag, value):
    with pytest.raises(SystemExit) as error:
        main(["--source-root", str(tmp_path), flag, value])
    assert error.value.code != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "explicit nonempty directory path" in captured.err


def test_successful_startup_reports_runtime_metadata_without_roots_or_stdout(
    tmp_path, monkeypatch, capsys,
):
    async def idle(service):
        assert isinstance(service, BoundedImageService)

    monkeypatch.setattr("archivist.mcp.server.run", idle)
    assert main(["--source-root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert str(tmp_path) not in captured.err
    for label in ("Archivist", "MCP SDK", "protocol", "Python", "supported Python >=3.10"):
        assert label in captured.err

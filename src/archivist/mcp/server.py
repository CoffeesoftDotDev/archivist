"""Official SDK stdio transport for bounded, metadata-only observations."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Event, Lock
from typing import Any

import anyio
from jsonschema import Draft202012Validator
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool, ToolAnnotations

from .. import __version__
from ..services.image_access import BoundedImageService, ReadPage
from ..services.image_api import ImageApiError, InventoryRequest, TransferRequest
from .schemas import input_schema, output_schema

_LOG = logging.getLogger(__name__)


def _error(code: str, message: str) -> CallToolResult:
    return CallToolResult(
        content=[], isError=True,
        structuredContent={"schema_version": 1, "error": {"code": code, "message": message}},
    )


class ReadOnlyTools:
    """Two typed tools sharing one startup policy and bounded observation store."""

    def __init__(self, service: BoundedImageService):
        self._service = service
        self._busy = Lock()
        self._tools = [
            Tool(
                name=name, description=description,
                inputSchema=input_schema(transfer=transfer),
                outputSchema=output_schema(transfer=transfer),
                annotations=ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=False,
                ),
            )
            for name, description, transfer in (
                ("inventory", "Read bounded image metadata from allowed roots; cursor continues the same observation.", False),
                ("prepare_transfer", "Preview bounded move/copy effects only; never apply a transfer. Cursor continues the same preview.", True),
            )
        ]
        self._validators = {
            tool.name: Draft202012Validator(tool.inputSchema) for tool in self._tools
        }

    async def list_tools(self) -> list[Tool]:
        """Advertise exactly the two read-only contracts."""
        return self._tools

    def _read(self, name: str, arguments: dict[str, Any], cancelled: Event) -> ReadPage:
        if not self._busy.acquire(blocking=False):
            raise ImageApiError("capacity_exceeded", "Another read is still running; retry after it finishes")
        try:
            if cancelled.is_set():
                raise ImageApiError("cancelled", "Read request was cancelled")
            if "cursor" in arguments:
                page = self._service.page(arguments["cursor"])
                expected = "inventory" if name == "inventory" else "transfer"
                if page.operation != expected:
                    raise ImageApiError("invalid_cursor", "Cursor belongs to a different operation")
                return page
            extensions = tuple(arguments["extensions"]) if "extensions" in arguments else None
            if name == "inventory":
                return self._service.inventory(InventoryRequest(
                    Path(arguments["root"]), extensions,
                ))
            return self._service.prepare_transfer(TransferRequest(
                Path(arguments["root"]), Path(arguments["destination"]),
                mode=arguments["mode"], extensions=extensions,
                leave_zip=arguments.get("leave_zip", False),
            ))
        finally:
            # Cancellation abandons the awaiting task, not filesystem I/O. Keep
            # admission closed until that worker really ends to bound work.
            self._busy.release()

    async def call_tool(self, name: str, arguments: object) -> CallToolResult:
        """Validate strictly, offload reads, and preserve the bounded page once."""
        validator = self._validators.get(name)
        if validator is None:
            return _error("invalid_request", "Unknown tool; expected inventory or prepare_transfer")
        if not isinstance(arguments, dict) or not validator.is_valid(arguments):
            return _error("invalid_request", "Arguments do not match the declared tool input schema")
        if self._busy.locked():
            return _error("capacity_exceeded", "Another read is still running; retry after it finishes")
        cancelled = Event()

        def read() -> ReadPage:
            return self._read(name, arguments, cancelled)

        try:
            page = await anyio.to_thread.run_sync(read, abandon_on_cancel=True)
            return CallToolResult(content=[], structuredContent=json.loads(page.to_json()))
        except ImageApiError as ex:
            return _error(ex.code, str(ex))
        except anyio.get_cancelled_exc_class():
            cancelled.set()
            raise
        except Exception:
            _LOG.exception("Read-only MCP request failed")
            return _error("internal_error", "Read request failed unexpectedly")


def create_server(service: BoundedImageService) -> Server:
    """Build the asynchronous low-level SDK server without starting transport."""
    server = Server(
        "archivist", version=__version__,
        instructions="Inventory and prepare_transfer only read local metadata. Previews never authorize or apply changes.",
    )
    tools = ReadOnlyTools(service)
    server.list_tools()(tools.list_tools)
    server.call_tool(validate_input=False)(tools.call_tool)
    return server


async def run(service: BoundedImageService) -> None:
    """Serve MCP over stdin/stdout until disconnect, without CLI side effects."""
    server = create_server(service)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

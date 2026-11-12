"""Explicit version-one contracts for the two metadata-only tools."""
from __future__ import annotations

from typing import Any


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object", "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


_STRING = {"type": "string"}
_PATH = {"type": "string", "minLength": 1}
_INTEGER = {"type": "integer", "minimum": 0}
_NULLABLE_STRING = {"type": ["string", "null"]}
_VERSION = {"type": "integer", "const": 1}
_EXTENSIONS = {"type": "array", "items": _PATH, "minItems": 1}


def input_schema(*, transfer: bool) -> dict[str, Any]:
    """Return mutually exclusive initial-request and continuation contracts."""
    properties = {"root": _PATH, "extensions": _EXTENSIONS, "schema_version": _VERSION}
    required = ["root"]
    if transfer:
        properties.update({
            "destination": _PATH, "mode": {"type": "string", "enum": ["move", "copy"]},
            "leave_zip": {"type": "boolean"},
        })
        required += ["destination", "mode"]
    continuation = {"cursor": {"type": "string", "minLength": 1, "maxLength": 128}}
    # Top-level closure also makes the allowlist visible to clients that inspect properties.
    return {
        "type": "object", "properties": {**properties, **continuation},
        "additionalProperties": False,
        "oneOf": [_object(properties, required), _object(continuation, ["cursor"])],
    }


_SOURCE = _object({
    "path": _STRING, "archive_chain": {"type": "array", "items": _STRING},
    "member": _NULLABLE_STRING,
})
_IMAGE = _object({
    "source": _SOURCE, "name": _STRING, "extension": _STRING, "size_bytes": _INTEGER,
    "created_ns": {"type": ["integer", "null"]}, "modified_ns": {"type": "integer"},
    "ordering_timestamp_source": _STRING,
})
_COUNTS = _object({name: _INTEGER for name in (
    "disk_images", "archived_images", "selected_images", "outer_archives",
    "total_archives", "source_folders",
)})


def _record(kind: str, properties: dict[str, Any]) -> dict[str, Any]:
    return _object({"kind": {"type": "string", "const": kind}, **properties})


_INVENTORY_RECORDS = [
    _record("summary", {
        "root": _STRING, "extensions": {"type": "array", "items": _STRING}, "counts": _COUNTS,
    }),
    _record("image", {"value": _IMAGE}),
    _record("archive", {"value": _object({
        "source": _SOURCE, "direct_images": _INTEGER, "direct_members": _INTEGER,
        "unpacked_bytes": _INTEGER,
    })}),
    *[_record(kind, {"message": _STRING}) for kind in ("problem", "notice")],
]
_TRANSFER_RECORDS = [
    _record("transfer_summary", {
        "plan_id": _STRING, "destination": _STRING,
        "mode": {"type": "string", "enum": ["move", "copy"]}, "leave_zip": {"type": "boolean"},
    }),
    _record("transfer", {"value": _object({"image": _IMAGE, "destination": _STRING})}),
    _record("extraction", {
        "source": _SOURCE, "target": _NULLABLE_STRING, "staging_relative_path": _STRING,
        "storage": {"type": "string", "enum": ["source_sibling", "private_temporary"]},
        "archive_disposition": {"type": "string", "enum": [
            "keep_original", "remove_after_success", "retain_extracted_container",
        ]},
    }),
    _record("extraction_member", {"value": _object({
        "source": _SOURCE, "relative_path": _STRING, "size_bytes": _INTEGER,
        "is_directory": {"type": "boolean"}, "selected_image": {"type": "boolean"},
        "disposition": {"type": "string", "enum": ["transferred", "retained", "temporary"]},
    })}),
]

ERROR_SCHEMA = _object({
    "schema_version": _VERSION, "error": _object({"code": _STRING, "message": _STRING}),
})


def output_schema(*, transfer: bool) -> dict[str, Any]:
    """Describe the exact bounded service page, or a structured error envelope."""
    records = _INVENTORY_RECORDS + (_TRANSFER_RECORDS if transfer else [])
    page = _object({
        "schema_version": _VERSION, "snapshot_id": _STRING,
        "operation": {"type": "string", "const": "transfer" if transfer else "inventory"},
        "inventory_complete": {"type": "boolean"},
        "next_cursor": _NULLABLE_STRING,
        "records": {"type": "array", "items": {"oneOf": records}},
    })
    return {
        "type": "object",
        "properties": {**page["properties"], **ERROR_SCHEMA["properties"]},
        "additionalProperties": False,
        "oneOf": [page, ERROR_SCHEMA],
    }

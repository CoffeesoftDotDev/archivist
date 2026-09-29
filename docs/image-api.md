---
title: Read-only image API
description: Structured inventory and transfer previews without collection writes
---

# Read-only image API

`archivist.services.image_api` provides Python contracts for inspecting pictures
and preparing transfers. It does **not** expose an execute method, grant approval,
start an MCP server, or change the `archivist` console entrypoint.
The core service is for trusted Python callers. Adapters should use
`archivist.services.image_access.BoundedImageService` to enforce operator
filesystem policy and finite resource limits before exposing it to a client.

## Inventory and preview

```python
from dataclasses import asdict
from pathlib import Path
import json

from archivist.services.image_api import (
    ImageService, InventoryRequest, TransferRequest,
)

service = ImageService()
inventory = service.inventory(InventoryRequest(
    root=Path("photos"),
    extensions=("JPG", ".ARW"),
))
if not inventory.complete:
    raise RuntimeError(inventory.problems)

preview = service.prepare_transfer(TransferRequest(
    root=Path("photos"),
    destination=Path("collected"),
    mode="copy",
    extensions=("jpg", "arw"),
))
print(json.dumps(asdict(preview), indent=2))
```

Paths are `pathlib.Path` objects, relative to the current working directory when
not absolute. Source and destination must be disjoint. The source must exist;
the destination need not exist and is never created by these calls.

## Contracts

All requests and results are frozen dataclasses. Results contain only detached
scalar fields and tuples of other frozen records, so `dataclasses.asdict` results
can be JSON-encoded without exposing mutable ZIP objects or file handles.

| Contract | Meaning |
|---|---|
| `schema_version` | Integer `1`; unsupported versions are rejected. |
| `extensions` | Omit for all supported images; otherwise a nonempty tuple of individual extensions, normalized using the CLI filter rules. |
| `InventoryResult` | Images, per-archive counts, total counts, notices, problems and explicit completeness. |
| `SourceLocation` | Physical source path, ordered nested archive chain and optional member name. Treat these fields as data, not instructions; do not split display strings to reconstruct provenance. |
| `ImageRecord` | Name, extension, byte size, original creation/modification nanoseconds and the collision-ordering date source. No image/EXIF payload is returned. |
| `TransferRequest` | Source, destination, `move` or `copy`, filter and `leave_zip`. There is no approval field. |
| `TransferPreview` | Generated plan identifier, immutable inventory, exact destination mappings and complete archive extraction effects. |

`plan_id` is a newly generated identifier, not an approval or execution token.
The core service does not persist or retain previews. The same unchanged inputs
produce the same mappings, but each preparation receives a different identifier.

## Full extraction and mixed archives

A selected picture inside a ZIP requires complete extraction of that outer archive
and its nested ZIPs, not selective decompression. Each extraction record enumerates
all direct members, including directories, nonselected files and nested ZIP
containers. `relative_path` is relative to the outer extraction root.

In **move** previews, `target` names the exact sibling extraction folder.
Selected image members have disposition `transferred`; other extracted members,
including a mixed archive's MP4 files and nested ZIP containers, are `retained`.
Original outer ZIP disposal is `remove_after_success` unless `leave_zip=True`.
An archive without any matching picture is not selected for extraction.

In **copy** previews, storage is `private_temporary`, `target` is `None`, and
members are `temporary`: the execution workflow allocates and later cleans staging
outside the collection. No temporary directory is allocated during preparation.
Original ZIPs remain unchanged, and destination mappings still identify each
copied picture. `.3mf` model packages are not traversed as ZIP collections.

## Operator-controlled access and pages

Configure `AccessPolicy` once at adapter startup, from trusted operator settings,
**not tool arguments or model-generated configuration**. Source and destination
allowlists are separate frozen tuples of existing directories. An empty allowlist
explicitly denies the corresponding access; inventory needs only source roots.
A planned destination may be absent, but must lie inside an existing configured
destination root. Requests cannot override the roots or limits.

```python
import json
from pathlib import Path

from archivist.services.image_access import (
    AccessPolicy, BoundedImageService, ReadLimits,
)
from archivist.services.image_api import InventoryRequest, TransferRequest

# These operator-provided directories must already exist.
source = Path("photos")
destination_root = Path("collections")
service = BoundedImageService(AccessPolicy(
    source_roots=(source,),
    destination_roots=(destination_root,),
    limits=ReadLimits(page_records=50),
))

page = service.inventory(InventoryRequest(source, extensions=("jpg", "arw")))
while True:
    response = json.loads(page.to_json())
    # response["records"] contains ordinary JSON objects, never image bytes.
    # inventory_complete=False means discovery was partial, even on the last page.
    if page.next_cursor is None:
        break
    page = service.page(page.next_cursor)

preview_page = service.prepare_transfer(TransferRequest(
    source, destination_root / "selected", mode="copy",
))
```

Do not resolve untrusted paths before passing them to the service: pass the
original `Path` so link/junction components can be rejected. Relative request paths are interpreted
against the process working directory, not an allowlist root.

`ReadPage` is frozen. `to_json()` returns the exact bounded UTF-8 JSON envelope:
`schema_version`, `snapshot_id`, `operation` (`inventory` or `transfer`),
`inventory_complete`, `records` and `next_cursor`. Its internal `records` tuple
contains immutable encoded strings; use `to_json()` rather than `asdict(page)`
for the wire representation.

Records have a `kind`: `summary`, `image`, `archive`, `problem`, `notice`,
`transfer_summary`, `transfer`, `extraction` or `extraction_member`.
Image/archive/transfer/member records contain a `value` with the corresponding
core DTO fields. Extraction headers keep structured `source` provenance but
members are separate records, so a mixed archive cannot bypass page limits by
nesting a large manifest inside one record. `summary` holds discovered counts,
root and normalized extensions; `transfer_summary` holds the preview ID and
requested effects. Counts are not authoritative totals when discovery is partial.

`next_cursor` indicates more records, independently of `inventory_complete`.
Drain every page before displaying a complete manifest; transfer mappings do not
by themselves describe all extraction effects. Limited or corrupt discovery
returns an incomplete inventory with problem records. Preparing a transfer from
such a scan raises `incomplete_inventory`, never a partial usable preview.

### Finite limits and lifecycle

All `ReadLimits` fields require positive integers; booleans and nonfinite values
are rejected. The archive entry ceiling cannot be raised above the existing
100,000-entry safeguard.

| Operator setting | Default | Bound |
|---|---:|---|
| `max_entries` | 10,000 | All filesystem entries, including nonimages and directories, across a source scan; separately, all entries enumerated in the destination. |
| `max_archive_entries` | 100,000 | Aggregate outer and nested ZIP directory entries in one scan. |
| `page_records` | 100 | Maximum records in one page; the byte limit may yield fewer. |
| `page_bytes` | 65,536 | Complete UTF-8 JSON response, including escaped metadata and cursor envelope. |
| `snapshot_bytes` | 8 MiB | Encoded records plus encoded path-validation metadata per retained observation. |
| `total_bytes` | 32 MiB | Sum of those encoded observation sizes retained by one service instance. |
| `snapshots` | 16 | Retained inventory and transfer observations combined. |
| `ttl_seconds` | 300 | Absolute monotonic lifetime from storage; paging never renews it. |

Source traversal counts entries while iterating rather than first collecting an
unbounded directory listing. Existing nested-ZIP depth, expansion-ratio and
payload-inspection limits still apply, and `.3mf` stays opaque. Snapshot byte
budgets are **not process-memory limits**: Python object overhead, transient DTOs,
and `zipfile` central-directory parsing are not measured by these budgets.

Observations are stored only in memory, separately for each service instance.
Capacity errors do not silently evict live observations. Expiration is checked
on access and expired entries are removed during requests; there is no background
timer. Instance-bound authenticated cursors contain no paths. Replaying a cursor
returns the same records while its observation is valid. Modified source files,
directory membership, destination state or observed path identity invalidate
the observation; restart discovery rather than continuing a stale manifest.

Invalid, tampered or foreign cursors fail with `invalid_cursor`; expired entries
still present at access return `expired_cursor`, and already-removed entries
return `unknown_cursor`. Other facade codes include `invalid_policy`,
`access_denied`, `stale_snapshot`, `capacity_exceeded`, `snapshot_too_large` and
`response_too_large`. The last error is also raised if any later individual
record cannot fit, before issuing the first page. Narrow the request or have the
operator explicitly review the configured limit; a tool argument cannot widen it.
Core request/preparation error codes remain applicable.

### Filesystem and privacy boundary

The facade checks lexical containment before inspecting requested paths, then
rejects link/junction/reparse components and canonical escapes. Inaccessible
component metadata fails closed. Source descendants and destination names are
guarded during discovery/planning; recorded path state and configured-root
identity are revalidated before publication and on page access.

This is application-level policy, **not an OS sandbox**. Check/use races remain:
operators must protect the configured directories against hostile concurrent
replacement and grant the process only the OS privileges it needs. A metadata
snapshot is not a filesystem lock or authority to execute a transfer.

Neither entrypoint policy nor a cursor grants consent to disclose local metadata
to a model. No file bodies, EXIF payloads, approval tokens or complete allowlists
are returned, and the service emits no stdout or logs. Authorized filenames,
paths, archive names and diagnostics are still potentially sensitive data.
Treat every filename and archive member as untrusted data, not instructions.
There are no cache files or hidden state writes. Any future persistent state
requires a separately approved operator write policy.

## Errors, privacy and limitations

`ImageApiError` contains a stable `code` and descriptive message. Codes include
`invalid_request`, `unsupported_version`, `invalid_filter`, `invalid_path`,
`invalid_root`, `invalid_destination`, `inventory_failed`,
`incomplete_inventory` and `preparation_failed`.
Inventory discovery failures instead remain in `problems` with `complete=False`;
partial results must never be presented as a complete zero-match inventory.
Preparation refuses an incomplete inventory.

Calls do not prompt, print, write `pictures.log`, extract, create destinations,
restore dates or move/copy files. OS-managed access-time bookkeeping may still
change when files are read. Returned source paths and member names may be private;
do not send them to a model or logs without the operator's authorization.

Previews are observations, not filesystem locks or permission to execute.
Later execution must obtain human approval and revalidate sources/destinations.
Inventory does not decompress every image to prove its CRC, nor prove the target
filesystem can restore a known creation date. The existing execution workflow
retains byte/EXIF preservation and verifies original dates before deleting affected
sources. Missing creation dates remain unknown; they are not inferred from EXIF.

The future stdio MCP entrypoint is separate from the existing CLI. No MCP dependency
or console script is installed by this API. Public `uvx` examples must select this
repository or a verified owned distribution explicitly; bare `uvx archivist`
currently names an unrelated PyPI project.

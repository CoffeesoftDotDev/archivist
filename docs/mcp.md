---
title: Read-only MCP and Copilot integration
description: Local stdio inventory and transfer previews with explicit filesystem roots
---

# Read-only MCP and Copilot integration

The v0.3 MCP adapter exposes exactly two tools: `inventory` and
`prepare_transfer`. It runs locally over stdio, without a terminal, and uses the
[bounded image API](image-api.md). It does not extract, move, copy, delete,
approve or execute a plan, create a destination, or write `pictures.log`.
OS-managed access-time bookkeeping may still change during reads.

This is the **v0.3 candidate contract**, not an announcement of a published
release. The implementation is merged and hosted Windows/Linux checks passed;
authenticated Copilot acceptance and a human release decision remain pending.
See [Acceptance and release gates](#acceptance-and-release-gates).
The existing `archivist` CLI and its approval rules are unchanged.
There is no AG-UI, model-provider or agent-framework dependency.

## Runtime and installation boundary

* Python 3.10 or later on Windows or Linux.
* [uv](https://docs.astral.sh/uv/), including `uvx`, and Git for a direct Git source.
* The optional `archivist[mcp]` extra installs the official Python SDK,
  `mcp>=1.28,<2`. Ordinary CLI installations do not need MCP.
* `archivist-mcp` is the separate console entry point; `--stdio` is optional and
  stdio is the only supported transport. It is not a switch on `archivist`.

For development in this checkout, after installing the optional extra:

```powershell
uv run --extra mcp archivist-mcp --help
uv run --extra mcp archivist-mcp --stdio --source-root "C:\photos" --destination-root "D:\collections"
```

The second command waits for an MCP client on stdin; it is not an interactive
photo command. Configure a client to launch it rather than typing requests in a
terminal.

### Public launches use a tested immutable commit

Do not use bare `uvx archivist`: that PyPI name must not be assumed to belong to
this repository. These examples select the repository explicitly. Do not replace
the pin with `main`, another branch, a mutable tag, or an abbreviated SHA.

```powershell
# Merged implementation from PR #30; tested on Windows and Linux.
$env:ARCHIVIST_REVIEWED_COMMIT = "d92909fccb11624c490781df2d6a4d3eac719658"
if ($env:ARCHIVIST_REVIEWED_COMMIT -notmatch '\A[0-9a-fA-F]{40}\z') {
    throw "A reviewed immutable server commit is required."
}
$package = "archivist[mcp] @ git+https://github.com/CoffeesoftDotDev/archivist.git@$env:ARCHIVIST_REVIEWED_COMMIT"
uvx --from $package archivist-mcp --stdio --source-root "C:\photos" --destination-root "D:\collections"
```

The sample pins the public merge commit from
[PR #30](https://github.com/CoffeesoftDotDev/archivist/pull/30), containing the
extra, entry point, adapter and tests. It does not track later changes on `main`.
Review the selected code and access policy before using your own collections;
replace the sample paths with existing directories you explicitly authorize.
Selecting this commit does not approve a transfer or publish a v0.3 release.
For a later revision, record its full SHA and acceptance evidence rather than
substituting a branch or tag.

First use normally needs network access to GitHub, package indexes and possibly
Python distribution downloads. uv creates environments and caches outside the
collection: collection read-only does not mean installation writes nothing.
Offline startup requires a compatible installed Python, uv/Git and the exact
source revision, build dependencies and resolved runtime dependencies already
available in uv's cache. Warm and test that exact command on the target machine
before disconnecting; `uvx --offline --from $package ...` fails rather than
fetching missing material. A full source pin does not lock every transitive
dependency; retain resolved versions with acceptance evidence.

## Operator configuration

Both allowlists are configured at process startup, not by the model. At least
one `--source-root` is required to start the adapter.
Repeat `--source-root PATH` or `--destination-root PATH` for separate authorized
trees. Configured roots must be existing directories. An absent destination
allowlist denies previews requiring destination access; it does not prevent
source-only inventory. A proposed destination may not exist yet, but must be
inside a configured destination root. Source and destination must be disjoint.
Use absolute paths to avoid process-working-directory ambiguity.

An empty facade allowlist denies that access; the server rejects startup without
a source root rather than adding one. There is no whole-drive or home-directory
fallback. Link/junction/reparse paths and escapes are rejected by the facade.
These checks are application policy, **not an OS sandbox**: restrict process
privileges and protect roots from concurrent replacement.

Startup limit flags are the [ReadLimits](image-api.md#finite-limits-and-lifecycle)
field names with underscores replaced by hyphens:

| Flag | Default |
|---|---:|
| `--max-entries` | 10,000 |
| `--max-archive-entries` | 100,000 |
| `--page-records` | 100 |
| `--page-bytes` | 65,536 |
| `--snapshot-bytes` | 8,388,608 |
| `--total-bytes` | 33,554,432 |
| `--snapshots` | 16 |
| `--ttl-seconds` | 300 |

Values must be positive integers, and archive entries cannot exceed the existing
100,000-entry safeguard. Nested ZIP depth, payload and expansion limits still
apply. Byte budgets bound encoded retained observations, not total process
memory or every transient ZIP-parser allocation. Tool arguments cannot change
roots, limits or startup settings. CLI `ARCHIVIST_*` apply/logging settings do not
grant execution authority to this adapter.

## Tool and page contract

Use MCP initialization followed by `tools/list` as the runtime machine-readable
inventory. It advertises each tool's input and output JSON Schema.
Export machine-readable schema evidence through the implementation as described
under [Contributor checks](#contributor-checks); do not maintain a second,
hand-written JSON Schema in a plugin.

| Tool | Initial request | Continuation |
|---|---|---|
| `inventory` | `root`, optional `extensions`, optional `schema_version` (integer `1`) | `cursor` only |
| `prepare_transfer` | `root`, `destination`, `mode` (`move` or `copy`), optional `extensions`, `leave_zip`, `schema_version` (integer `1`) | `cursor` only |

`extensions` is a list of individual supported extensions, not the CLI's
comma-separated `--filter` string. Omit it for all supported images; an empty
list or unsupported extension is an error. Initial calls and cursor-only calls
are distinct: do not resend roots, filters, mode or schema version with a cursor.
There is no `apply`, approval, execution, arbitrary-shell or cleanup field/tool.
Unknown action fields are rejected, not silently ignored.

Successful tool results reuse the `ReadPage` JSON envelope: `schema_version`,
`snapshot_id`, `operation` (`inventory` or `transfer`), `inventory_complete`,
`records`, and `next_cursor`. Read the structured result, not a reconstructed
display string. Records distinguish summaries, images, archives, problems,
notices, transfers, extraction headers and extraction members.

Follow `next_cursor` with the **same tool** and a cursor-only request until it is
null. Pagination completion and inventory completeness are different:
`inventory_complete=false` is partial discovery, never a successful zero-match
answer. Drain all pages before presenting a complete inventory or effects
manifest. A transfer page without its later extraction members is not the whole
preview. Preparation refuses incomplete discovery.

Cursors are opaque, instance-bound and short-lived. Paging does not renew
expiry. Changed source/destination state invalidates an observation. On stale,
expired or invalid cursors, start a new initial request; do not combine pages
from different observations. Capacity and size failures require narrowing the
request or operator review, not model-driven policy expansion.

Schema/protocol failures and tool failures are errors, not success-shaped empty
collections. Inspect MCP `isError` and structured diagnostics where provided;
do not assume every validation error has the same envelope as `ReadPage`.
The shared API documents stable failure codes and incomplete-inventory problems.
stdout belongs exclusively to MCP; diagnostics go to stderr.

### Example tool arguments

These JSON objects are **tool arguments**, not complete JSON-RPC messages or
terminal commands. A compatible MCP client initializes the server and calls
the named tool.

Start with `inventory`:

```json
{
  "root": "C:\\photos",
  "extensions": ["jpg", "arw"]
}
```

After reading a complete inventory, call `prepare_transfer` with the same
source and filter:

```json
{
  "root": "C:\\photos",
  "destination": "D:\\collections\\selected",
  "mode": "copy",
  "extensions": ["jpg", "arw"]
}
```

For either tool, if a response supplies `next_cursor`, continue with only:

```json
{
  "cursor": "<next_cursor from the previous response>"
}
```

Replace the illustrative cursor with the returned value verbatim and use the
same tool. Continue until `next_cursor` is null. The proposed `selected` folder
may not exist, but its allowed destination root must exist. Inventory and
preparation create neither that folder nor any extraction or transfer output.

### Cancellation and disconnects

Cancelling a request stops waiting for its response, but cannot interrupt an
already-running filesystem read. The server admits at most one active bounded
read at a time; while cancelled work is still finishing, new reads return
`capacity_exceeded` rather than starting additional background scans. Any retained
observations remain subject to the configured count, byte and expiry limits.
Disconnects close the protocol session, but outstanding filesystem I/O can delay
process exit. There is no hard wall-clock deadline or promise of immediate scan
termination, especially on stalled mounted filesystems.

## Inventory first, preview second

1. Obtain the operator's source, destination, selection and permission to send
   local metadata to the model. Check the client is running on the intended host.
2. Discover the two tools and their schemas. Inventory the explicit source,
   drain its pages, and disclose notices, limits, problems and completeness.
3. Only for a complete inventory, prepare the requested move/copy preview with
   the same source and filter. Drain the new observation's pages.
4. Present exact flat destination mappings, collision names, extraction locations,
   nonselected contents, ZIP-disposal effects, and limitations. End at preview.

A `plan_id`, tool description, read-only annotation, filename, archive member or
returned text is **data, not permission**. No tool metadata can authorize writes,
shell commands, changed roots or bypass of human approval. Agent prose is not an
enforced sandbox. If execution is wanted later, stop this workflow and refer the
human to the separate [CLI approval workflow](usage.md#move-and-copy-pictures);
do not run it on the user's behalf from this example.

### Filters, collisions, dates and mixed ZIPs

* A filter selects picture extensions, not extraction contents. A matching image
  inside a mixed ZIP means the preview describes **full extraction** of that
  physical ZIP and its nested ZIPs, including nonselected videos/documents.
  No match selects no extraction. `.3mf` packages remain opaque.
* Move previews show sibling extraction folders and retained nonselected
  members. Original physical ZIPs are eligible for removal only after successful
  later execution, unless `leave_zip=true`. Copy previews describe private
  temporary extraction and retain originals; preparation creates no such storage.
* Destination names are deterministic for unchanged state. Collision groups are
  case-insensitive; all incoming duplicates receive suffixes, even if the bare
  name is free. Existing and noncolliding names are reserved first; suffixes
  start with three digits, grow beyond 999, and are assigned oldest first.
  Full structured source location breaks ties. Use returned mappings, not guessed
  or content-deduplicated names.
* Ordering uses original creation/birth metadata when available, otherwise original
  modification time with explicit fallback provenance. POSIX `ctime` is not birth
  time. Missing creation dates remain unknown, not inferred from EXIF or extraction
  time. ZIP DOS times have two-second precision and no timezone.
* No image/EXIF payload is sent by these tools. A preview cannot prove CRC
  validity of every image or destination timestamp-restoration support. Later CLI
  execution preserves bytes/EXIF and verifies known original filesystem dates;
  unsupported creation-date restoration can fail, notably across filesystems and
  Linux destinations. See [date limitations](usage.md#photo-metadata-and-original-dates).

## Local Copilot example

The optional
[Copilot example directory](https://github.com/CoffeesoftDotDev/archivist/tree/main/examples/copilot)
contains a plugin manifest, stdio registration, fail-closed launcher, thin agent
and reusable skill. It shows how to ask Copilot for an inventory and a preview;
the server also works independently with other compatible MCP clients.
The setup below loads the example for one session, without installation or user
settings changes. No second plugin repository or marketplace is required.

### Plugin and MCP configuration

The example's `plugin.json` declares the plugin:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "archivist-readonly-example",
  "description": "Local image inventory and transfer previews; no execution tools."
}
```

Its `mcp.json` registers the server launcher:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "archivist": {
      "type": "stdio",
      "command": "node",
      "args": ["launch-mcp.mjs"],
      "cwd": "${PLUGIN_ROOT}"
    }
  }
}
```

Copilot supplies `${PLUGIN_ROOT}` as the working directory. The Node.js 20+
launcher reads the explicit pin and roots from environment variables, checks
them, then starts `uvx` without a shell. It does not rely on arbitrary variable
expansion inside the MCP JSON. Keep the
[launcher, agent and skill files](https://github.com/CoffeesoftDotDev/archivist/tree/main/examples/copilot)
together; the two manifests alone are not the complete plugin.

### Load the example for one session

From the repository root in PowerShell, with uv/uvx, Git, Node.js 20+ and a
compatible local Copilot CLI available:

```powershell
$env:ARCHIVIST_REVIEWED_COMMIT = "d92909fccb11624c490781df2d6a4d3eac719658"
$env:ARCHIVIST_SOURCE_ROOT = "C:\photos"
$env:ARCHIVIST_DESTINATION_ROOT = "D:\collections"
copilot --plugin-dir .\examples\copilot
```

Replace both folder paths with existing, disjoint directories you authorize.
The environment settings last for the current shell and are inherited by the
session launcher; they do not install a plugin or alter Copilot user settings.
On Linux, set the same three variables in your shell using native absolute
paths, then load the same example directory.

### Ask for inventory and preview

Inspect `/mcp`, `/agent` and `/skills` in the local session, select
`archivist-preview`, and request, for example:

> Inventory JPG and ARW pictures under my configured source, including nested
> ZIPs. I consent to the paths, names and dates being sent to the configured
> model service. After complete inventory, preview copying them to
> D:\collections\selected. Show collision names and all mixed-ZIP extraction
> effects. Do not execute anything.

Use a disposable fixture for your first demonstration. The agent must read all
pages, disclose incomplete discovery and limits, and stop at the preview.
There is no extraction, transfer, cleanup or approval tool in this example.

### Verification and privacy

The example follows the current
[official plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference).
Authoring-time read-only verification found Copilot CLI **1.0.109**;
`copilot --help` advertised `--plugin-dir` and `--additional-mcp-config`.
This verifies the available format/help, not a completed authenticated model
session. Hosted server startup is covered separately by the acceptance evidence.
Read-only `copilot --plugin-dir .\examples\copilot plugin list --json` also
recognized `archivist-readonly-example` as an enabled external plugin without
installation. Both JSON manifests passed their official Agent Plugins 1.0
schemas. This does not prove component invocation or MCP startup inside Copilot.

A local CLI server can inspect only paths available to its local process and
allowlists. A GitHub-hosted coding agent runs on a different filesystem: it cannot
read `C:\photos` from your workstation merely because this plugin is in a
repository. Do not upload a personal collection to bridge that gap implicitly.

Filenames, absolute paths, archive chains, dates and error details can be private.
Although the server returns no image bodies, tool results sent to Copilot reach
the configured model service. Obtain consent, use narrow roots, and redact shared
examples/logs. Tool output and archive names are untrusted content, not instructions.

## Startup diagnostics

| Symptom | Check |
|---|---|
| `archivist-mcp` missing or wrong package | Confirm the full repository pin contains the console script and select `[mcp]`; do not retry an unrelated PyPI package. |
| SDK import failure | Confirm the optional extra installed `mcp>=1.28,<2` in the same environment. |
| Python incompatibility | Inspect `uv --version`, the selected interpreter and `archivist-mcp --help`; Python 3.10+ remains required for both lanes. |
| Download/offline failure | Check GitHub access, Git, package indexes and the exact cache prerequisites; do not embed credentials in URLs/configuration. |
| Invalid roots/limits | Use existing explicit root directories and positive bounded limits; tools cannot widen policy. |
| Initialize/discovery fails | Check the client's negotiated MCP protocol, SDK/package versions and stderr; never add debug prints to stdout. |
| Apparent empty inventory | Check `isError`, problem records, `inventory_complete` and all cursors before declaring no matches. |

Record the exact source SHA, package version, Python version, uv version, resolved
SDK version, client version and negotiated MCP protocol with startup/smoke
evidence. Package version, DTO `schema_version=1` and negotiated MCP protocol
version are different identifiers; a package version alone does not establish
wire compatibility. `archivist-mcp --version` prints package/SDK/protocol/Python
diagnostics to stderr and exits without opening transport. `--help` lists the
startup policy and default limits. Successful normal startup emits the same
version summary to stderr, without configured paths or roots.
Review stderr locally before sharing it
because it may contain paths.

## Contributor checks

The implementation exports its native tool/schema inventory through MCP
`tools/list`: initialize the client against the exact package pin, request the
tool list, and retain the JSON response with startup evidence. Its two tool
definitions contain `inputSchema` and `outputSchema`, including the shared page
records. This is generated from registration, not a separately maintained schema
definition in the example. Do not substitute a hand-written schema or infer
compatibility from this guide's prose tables.

There is no supported offline exporter flag or module. Use the runtime tool
list for schema evidence; `archivist-mcp` keeps stdout protocol-only.

Local plugin launcher checks run with
`node --test examples\copilot\launch-mcp.test.mjs`; they do not call a model or
download the package.

The opt-in packaging smoke helper exercises separate isolated uvx environments
for the base CLI (without the SDK) and the MCP extra. Use the same immutable pin
as the setup examples:

```powershell
$env:ARCHIVIST_REVIEWED_COMMIT = "d92909fccb11624c490781df2d6a4d3eac719658"
.\.venv\Scripts\python.exe scripts\mcp_smoke.py --commit $env:ARCHIVIST_REVIEWED_COMMIT --python 3.10
```

Its default source is this public GitHub repository. For a committed local
checkout, an operator may supply `--git-url "C:\src\archivist"` and that
checkout's reviewed full commit instead; an uncommitted server is not included
in a Git pin. `--lane cli` or `--lane mcp` limits the helper to one lane. These
are opt-in installation/network checks, not part of ordinary pytest invocation.
The dedicated `.github\workflows\mcp.yml` targets Windows/Linux with Python
3.10/3.13. Its successful hosted run is linked below; merely adding a workflow
file is not acceptance evidence.

With documentation dependencies already installed:

```powershell
uv run --no-sync sphinx-build -b html -W --keep-going docs docs\_build\html
```

## Acceptance and release gates

This checklist is a handoff, not release authority. Local results are reported
separately from hosted results; unchecked gates must not be inferred as passed.

Local documentation/example validation on Windows used Copilot CLI 1.0.109,
Node.js 24.19.0 and Sphinx 8.2.3: four launcher tests passed, official manifest
schema checks passed, session-only plugin mount discovery passed, and the strict
Sphinx HTML build passed. Adapter `--help` and `--version` were also inspected;
the current development package still reported `0.2.0`, not a released v0.3.
These checks do not replace the hosted or human checks below.

Final local Windows validation for PR #30 passed 545 regression tests with four
platform-dependent skips using SDK 1.30.0. SDK-free isolated Python 3.10.21 and
3.13.15 environments each passed 444 tests with 14 skips. An earlier minimum-SDK
compatibility run passed all 106 adapter/stdio/packaging tests on Python 3.10
with SDK 1.28.0. These local results are distinct from the hosted runs below.

### Hosted evidence for the sample pin

All runs below tested merge commit
`d92909fccb11624c490781df2d6a4d3eac719658` from PR #30:

| Hosted run | Coverage | Result |
|---|---|---|
| [Read-only MCP](https://github.com/CoffeesoftDotDev/archivist/actions/runs/43199321092) | SDK contracts and clean public-source uvx startup on Ubuntu/Windows, Python 3.10/3.13 | Passed all eight jobs |
| [CLI and Docker CI](https://github.com/CoffeesoftDotDev/archivist/actions/runs/43199321298) | SDK-free CLI regressions on Ubuntu/Windows, Python 3.10/3.13; non-root Docker build and smoke | Passed |
| [GitHub Pages](https://github.com/CoffeesoftDotDev/archivist/actions/runs/43199321082) | Strict documentation build and deployment from main | Passed |
| [CodeQL](https://github.com/CoffeesoftDotDev/archivist/actions/runs/43199321779) | Python and Actions analysis | Passed |

The clean uvx probes used Python 3.10.22 and 3.13.18 on Ubuntu, and 3.10.22 and
3.13.17 on Windows. Each ordinary CLI environment contained no MCP SDK.
The MCP SDK/client was 1.30.0; startup reported Archivist 0.2.0 and protocol
2025-11-25. Probes discovered exactly the two tools, paged disk/ZIP inventory and
previews, rejected an `apply` field and left fixture snapshots unchanged.
The SDK-contract jobs separately covered nested/mixed ZIPs, unsafe requests,
stale observations, cancellation/disconnection and no-write snapshots.

These results establish server and transport acceptance, not authenticated
Copilot agent behavior or release approval. Keep the selected SHA with its
evidence and rerun smoke checks if the deployment pin changes.

### Remaining release checklist

- [x] Immutable public server commit recorded after PR #30 merged; samples use
  that exact CI-tested SHA.
- [x] Clean-environment pinned `uvx` startup on hosted Windows and Linux records
  package/Python/SDK/client/protocol versions and exactly the two advertised tools.
- [x] Real stdio initialization, schema discovery, tool calls, bounded paging,
  cancellation/disconnection and clean shutdown pass on the supported matrix.
- [x] Disposable disk and nested/mixed-ZIP fixtures prove inventory and preview
  cause no source/destination/report/staging writes (apart from OS read bookkeeping).
- [x] Unsafe paths, invalid fields/filters, incomplete discovery, no matches,
  collisions and stale/expired cursors are covered.
- [x] Ordinary CLI installation and regressions pass without MCP dependencies;
  Windows/Linux CLI Python 3.10/3.13, Docker and Pages checks are preserved.
- [ ] Human verifies local Copilot tool discovery, inventory then preview, privacy
  disclosure and no execution claims using the reviewed pin.
- [ ] Human reviews AI-assisted documentation and accepts remaining platform,
  dependency-resolution and timestamp limitations.
- [ ] Authorized maintainer decides whether to release v0.3; version metadata,
  release notes and tag are handled through the repository release procedure.

For a release decision, retain hosted job links and limitations alongside the
reviewed SHA. Version changes in `pyproject.toml` and `src/archivist/__init__.py`
must agree; refresh the lockfile when dependencies change. Re-run pinned smoke
checks against the intended release commit before approving a tag. Do not
publish a distribution based on an unverified ownership assumption. A completed
implementation, this checklist, or creation of backlog items does not publish
or approve a release.
